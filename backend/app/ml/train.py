"""Offline walk-forward training — never shuffle; scalers fit on train only."""
from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import TARGET_SPEC
from .dataset import load_jsonl
from .features import FEATURE_NAMES, build_feature_matrix, row_is_complete
from .labels import HORIZON, label_series, net_forward_return, sma_crossover_signal


def _group_by_symbol(rows: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = {}
    for r in rows:
        g.setdefault(r["symbol"], []).append(r)
    for s in g:
        g[s] = sorted(g[s], key=lambda x: x["open_time"])
    return g


def build_xy(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    groups = _group_by_symbol(rows)
    X_list: list[list[float]] = []
    y_list: list[int] = []
    meta: list[dict] = []
    for sym, candles in groups.items():
        feats, _ = build_feature_matrix(candles)
        labels = label_series(candles)
        closes = [float(c["close"]) for c in candles]
        for i, (feat, lab) in enumerate(zip(feats, labels)):
            if lab is None or not row_is_complete(feat):
                continue
            # embargo: need horizon future bars already enforced by label None
            X_list.append([float(v) for v in feat])  # type: ignore
            y_list.append(int(lab))
            meta.append(
                {
                    "symbol": sym,
                    "open_time": candles[i]["open_time"],
                    "close_time": candles[i]["close_time"],
                    "close": closes[i],
                    "index": i,
                }
            )
    return np.asarray(X_list, dtype=float), np.asarray(y_list, dtype=int), meta


def chronological_splits(
    meta: list[dict], n_folds: int = 3, embargo: int = HORIZON
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Time-ordered folds with purge/embargo gap between train and test."""
    order = np.argsort([m["open_time"] for m in meta])
    folds = []
    n = len(order)
    fold_size = n // (n_folds + 1)
    if fold_size < 50:
        # single holdout 70/30
        cut = int(n * 0.7)
        train_idx = order[: max(cut - embargo, 1)]
        test_idx = order[cut:]
        return [(train_idx, test_idx)]
    for k in range(1, n_folds + 1):
        test_start = k * fold_size
        test_end = min((k + 1) * fold_size, n) if k < n_folds else n
        train_end = max(test_start - embargo, 1)
        train_idx = order[:train_end]
        test_idx = order[test_start:test_end]
        if len(train_idx) >= 50 and len(test_idx) >= 20:
            folds.append((train_idx, test_idx))
    return folds


def _metrics(y_true: np.ndarray, proba: np.ndarray) -> dict[str, Any]:
    y_pred = (proba >= 0.5).astype(int)
    out: dict[str, Any] = {
        "n": int(len(y_true)),
        "positive_rate": float(y_true.mean()) if len(y_true) else None,
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, proba)) if len(np.unique(y_true)) > 1 else None
    except ValueError:
        out["roc_auc"] = None
    out["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    out["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
    try:
        out["brier"] = float(brier_score_loss(y_true, proba))
    except ValueError:
        out["brier"] = None
    try:
        out["log_loss"] = float(log_loss(y_true, proba, labels=[0, 1]))
    except ValueError:
        out["log_loss"] = None
    if len(y_true) >= 20 and len(np.unique(y_true)) > 1:
        frac_pos, mean_pred = calibration_curve(y_true, proba, n_bins=8, strategy="quantile")
        out["calibration_curve"] = {
            "fraction_positives": [float(x) for x in frac_pos],
            "mean_predicted": [float(x) for x in mean_pred],
        }
    else:
        out["calibration_curve"] = None
    return out


def simulate_policy_returns(
    meta_slice: list[dict],
    rows_by_sym: dict[str, list[dict]],
    take_mask: np.ndarray,
) -> dict[str, Any]:
    """When take_mask[i]=1, enter at close and exit after HORIZON bars."""
    pnls = []
    for keep, m in zip(take_mask, meta_slice):
        if not keep:
            continue
        candles = rows_by_sym[m["symbol"]]
        i = m["index"]
        j = i + HORIZON
        if j >= len(candles):
            continue
        pnls.append(
            net_forward_return(float(candles[i]["close"]), float(candles[j]["close"]))
        )
    if not pnls:
        return {
            "trades": 0,
            "net_return_sum": 0.0,
            "avg_trade": None,
            "max_drawdown": None,
            "profit_factor": None,
        }
    equity = [0.0]
    for r in pnls:
        equity.append(equity[-1] + r)
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = min(max_dd, e - peak)
    gains = sum(x for x in pnls if x > 0)
    losses = sum(-x for x in pnls if x < 0)
    pf = (gains / losses) if losses > 0 else None
    return {
        "trades": len(pnls),
        "net_return_sum": float(sum(pnls)),
        "avg_trade": float(sum(pnls) / len(pnls)),
        "max_drawdown": float(max_dd),
        "profit_factor": float(pf) if pf is not None else None,
    }


def walk_forward_train(dataset_path: Path, artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(dataset_path)
    X, y, meta = build_xy(rows)
    if len(X) < 100:
        return {
            "status": "insufficient_data",
            "n_samples": int(len(X)),
            "message": "Need >=100 complete labeled samples",
        }

    folds = chronological_splits(meta)
    rows_by_sym = _group_by_symbol(rows)
    fold_reports = []
    for fi, (tr, te) in enumerate(folds):
        Xtr, ytr = X[tr], y[tr]
        Xte, yte = X[te], y[te]
        meta_te = [meta[i] for i in te]

        # baselines on test
        naive_proba = np.full(len(yte), float(ytr.mean() if len(ytr) else 0.5))
        # SMA proxy: use signal as probability 0.35/0.65
        sma_probs = []
        for m in meta_te:
            candles = rows_by_sym[m["symbol"]]
            closes = [float(c["close"]) for c in candles]
            sig = sma_crossover_signal(closes)
            sma_probs.append(0.65 if sig[m["index"]] == 1 else 0.35)
        sma_proba = np.asarray(sma_probs, dtype=float)

        pipe_lr = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(max_iter=500, class_weight="balanced"),
                ),
            ]
        )
        pipe_hgb = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05),
                ),
            ]
        )
        pipe_lr.fit(Xtr, ytr)
        pipe_hgb.fit(Xtr, ytr)
        proba_lr = pipe_lr.predict_proba(Xte)[:, 1]
        proba_hgb = pipe_hgb.predict_proba(Xte)[:, 1]

        report = {
            "fold": fi,
            "train_n": int(len(tr)),
            "test_n": int(len(te)),
            "test_time_from": meta_te[0]["open_time"],
            "test_time_to": meta_te[-1]["open_time"],
            "logistic": _metrics(yte, proba_lr),
            "hist_gb": _metrics(yte, proba_hgb),
            "naive": _metrics(yte, naive_proba),
            "sma_proxy": _metrics(yte, sma_proba),
            "policy_hist_gb": simulate_policy_returns(
                meta_te, rows_by_sym, proba_hgb >= 0.55
            ),
            "policy_sma": simulate_policy_returns(
                meta_te, rows_by_sym, sma_proba >= 0.5
            ),
            "policy_always_long": simulate_policy_returns(
                meta_te, rows_by_sym, np.ones(len(meta_te), dtype=bool)
            ),
            "policy_cash": {"trades": 0, "net_return_sum": 0.0, "note": "stay_in_cash"},
        }
        fold_reports.append(report)

    # Fit final model on all but last embargoed segment for artifact
    order = np.argsort([m["open_time"] for m in meta])
    cut = int(len(order) * 0.85)
    final_tr = order[: max(cut - HORIZON, 1)]
    final_model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05)),
        ]
    )
    final_model.fit(X[final_tr], y[final_tr])

    blob = pickle.dumps(final_model)
    model_hash = hashlib.sha256(blob).hexdigest()
    version = datetime.now(timezone.utc).strftime("v%Y%m%dT%H%M%SZ")
    model_path = artifact_dir / f"model_{version}_{model_hash[:12]}.pkl"
    model_path.write_bytes(blob)

    # crude feature importance via logistic on last fold train if available
    importance = None
    try:
        lr = Pipeline(
            [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=400))]
        )
        lr.fit(X[final_tr], y[final_tr])
        coefs = lr.named_steps["clf"].coef_[0]
        importance = sorted(
            [
                {"feature": FEATURE_NAMES[i], "abs_coef": float(abs(coefs[i]))}
                for i in range(len(FEATURE_NAMES))
            ],
            key=lambda x: x["abs_coef"],
            reverse=True,
        )[:15]
    except Exception:
        importance = None

    # promotion gate: validated for research if mean AUC > naive and > 0.52
    aucs = [f["hist_gb"]["roc_auc"] for f in fold_reports if f["hist_gb"]["roc_auc"] is not None]
    naive_aucs = [f["naive"]["roc_auc"] for f in fold_reports if f["naive"]["roc_auc"] is not None]
    mean_auc = float(np.mean(aucs)) if aucs else None
    mean_naive = float(np.mean(naive_aucs)) if naive_aucs else None
    research_ok = (
        mean_auc is not None
        and mean_naive is not None
        and mean_auc > mean_naive
        and mean_auc >= 0.52
        and len(aucs) >= 1
    )

    result = {
        "status": "trained",
        "mode_allowed": "SHADOW_AI" if research_ok else "RESEARCH_ONLY",
        "validated_for_research": research_ok,
        "validated_for_paper_ai": False,  # never auto-promote
        "model_version": version,
        "model_hash": model_hash,
        "model_path": str(model_path),
        "algorithm": "HistGradientBoostingClassifier",
        "baseline_algorithms": ["LogisticRegression", "naive_prior", "SMA10_50_proxy"],
        "feature_names": FEATURE_NAMES,
        "target": TARGET_SPEC,
        "n_samples": int(len(X)),
        "n_symbols": len(rows_by_sym),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "walk_forward": fold_reports,
        "mean_roc_auc_hist_gb": mean_auc,
        "mean_roc_auc_naive": mean_naive,
        "feature_importance_proxy": importance,
        "disclaimer": (
            "Resultados de investigación paper-only. Una AUC > 0.5 no implica rentabilidad. "
            "Shadow AI no ejecuta operaciones."
        ),
        "dependencies": {
            "sklearn": __import__("sklearn").__version__,
            "numpy": np.__version__,
        },
    }
    meta_path = artifact_dir / f"metrics_{version}.json"
    meta_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["metrics_path"] = str(meta_path)
    return result
