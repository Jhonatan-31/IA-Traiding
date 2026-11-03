"""Offline walk-forward training — never shuffle; scalers fit on train only."""
from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
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
from .calibration import bootstrap_ci, fit_calibrators_on_val, score_calibration
from .dataset import load_jsonl
from .economics import (
    aggregate_strategy_table,
    policy_pnls,
    sensitivity_to_costs,
    trade_stats,
)
from .features import FEATURE_NAMES, build_feature_matrix, row_is_complete
from .labels import HORIZON, label_series, sma_crossover_signal


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
        out["roc_auc"] = (
            float(roc_auc_score(y_true, proba)) if len(np.unique(y_true)) > 1 else None
        )
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
    out["calibration"] = score_calibration(y_true, proba)
    return out


def simulate_policy_returns(
    meta_slice: list[dict],
    rows_by_sym: dict[str, list[dict]],
    take_mask: np.ndarray,
) -> dict[str, Any]:
    pnls = policy_pnls(meta_slice, rows_by_sym, take_mask, HORIZON)
    return trade_stats(pnls)


def _pipe_hgb():
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05)),
        ]
    )


def _pipe_lr():
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, class_weight="balanced")),
        ]
    )


def _pipe_rf():
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=100, max_depth=6, random_state=42, n_jobs=1
                ),
            ),
        ]
    )


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
    final_test_report = None
    calibration_summary: dict[str, Any] = {"folds": []}

    # Reserve last fold as final untouched test if we have >=3 folds
    modeling_folds = folds[:-1] if len(folds) >= 3 else folds
    final_holdout = folds[-1] if len(folds) >= 3 else None

    for fi, (tr, te) in enumerate(modeling_folds):
        # inner val split: last 20% of train chronologically for calibration selection
        tr_sorted = np.asarray(sorted(tr, key=lambda i: meta[i]["open_time"]))
        val_cut = max(int(len(tr_sorted) * 0.8), 1)
        tr_fit = tr_sorted[: max(val_cut - HORIZON, 1)]
        tr_val = tr_sorted[val_cut:]
        if len(tr_val) < 30:
            tr_fit, tr_val = tr_sorted[: max(len(tr_sorted) - 30, 1)], tr_sorted[-30:]

        Xtr, ytr = X[tr_fit], y[tr_fit]
        Xval, yval = X[tr_val], y[tr_val]
        Xte, yte = X[te], y[te]
        meta_te = [meta[i] for i in te]

        naive_proba = np.full(len(yte), float(ytr.mean() if len(ytr) else 0.5))
        sma_probs = []
        for m in meta_te:
            candles = rows_by_sym[m["symbol"]]
            closes = [float(c["close"]) for c in candles]
            sig = sma_crossover_signal(closes)
            sma_probs.append(0.65 if sig[m["index"]] == 1 else 0.35)
        sma_proba = np.asarray(sma_probs, dtype=float)

        pipe_lr = _pipe_lr()
        pipe_hgb = _pipe_hgb()
        pipe_rf = _pipe_rf()
        pipe_lr.fit(Xtr, ytr)
        pipe_hgb.fit(Xtr, ytr)
        pipe_rf.fit(Xtr, ytr)
        proba_lr = pipe_lr.predict_proba(Xte)[:, 1]
        proba_hgb = pipe_hgb.predict_proba(Xte)[:, 1]
        proba_rf = pipe_rf.predict_proba(Xte)[:, 1]

        # Calibration: select method on val only, then transform test
        cal_pack = fit_calibrators_on_val(_pipe_hgb(), Xtr, ytr, Xval, yval)
        cal_est = cal_pack["selected_estimator"]
        proba_hgb_cal = cal_est.predict_proba(Xte)[:, 1]
        cal_test = score_calibration(yte, proba_hgb_cal)
        calibration_summary["folds"].append(
            {
                "fold": fi,
                "selected": cal_pack["selected_on_validation"],
                "val_methods": {
                    k: {kk: vv for kk, vv in v.items() if kk != "reliability"}
                    if isinstance(v, dict)
                    else v
                    for k, v in cal_pack["methods"].items()
                },
                "test_after_selection": {
                    k: cal_test[k]
                    for k in ("n", "brier", "log_loss", "ece")
                    if k in cal_test
                },
            }
        )

        sens = sensitivity_to_costs(
            meta_te,
            rows_by_sym,
            proba_hgb >= 0.55,
            HORIZON,
            [(0.001, 0.001), (0.0005, 0.0005), (0.002, 0.002)],
        )

        report = {
            "fold": fi,
            "train_n": int(len(tr_fit)),
            "val_n": int(len(tr_val)),
            "test_n": int(len(te)),
            "test_time_from": meta_te[0]["open_time"],
            "test_time_to": meta_te[-1]["open_time"],
            "logistic": _metrics(yte, proba_lr),
            "hist_gb": _metrics(yte, proba_hgb),
            "hist_gb_calibrated": _metrics(yte, proba_hgb_cal),
            "random_forest": _metrics(yte, proba_rf),
            "naive": _metrics(yte, naive_proba),
            "sma_proxy": _metrics(yte, sma_proba),
            "calibration_selected": cal_pack["selected_on_validation"],
            "policy_hist_gb": simulate_policy_returns(
                meta_te, rows_by_sym, proba_hgb >= 0.55
            ),
            "policy_hist_gb_calibrated": simulate_policy_returns(
                meta_te, rows_by_sym, proba_hgb_cal >= 0.55
            ),
            "policy_logistic": simulate_policy_returns(
                meta_te, rows_by_sym, proba_lr >= 0.55
            ),
            "policy_sma": simulate_policy_returns(
                meta_te, rows_by_sym, sma_proba >= 0.5
            ),
            "policy_always_long": simulate_policy_returns(
                meta_te, rows_by_sym, np.ones(len(meta_te), dtype=bool)
            ),
            "policy_cash": {
                "trades": 0,
                "net_return_sum": 0.0,
                "note": "stay_in_cash",
            },
            "cost_sensitivity_hist_gb": sens,
        }
        fold_reports.append(report)

    # Final holdout — no model selection here
    if final_holdout is not None:
        tr, te = final_holdout
        # train on all prior modeling data (union of earlier trains) ~ all before holdout with embargo
        Xtr, ytr = X[tr], y[tr]
        Xte, yte = X[te], y[te]
        meta_te = [meta[i] for i in te]
        pipe_hgb = _pipe_hgb()
        pipe_lr = _pipe_lr()
        pipe_hgb.fit(Xtr, ytr)
        pipe_lr.fit(Xtr, ytr)
        # calibrate with last 15% of train as val
        tr_sorted = np.asarray(sorted(tr, key=lambda i: meta[i]["open_time"]))
        val_cut = max(int(len(tr_sorted) * 0.85), 1)
        fit_idx, val_idx = tr_sorted[:val_cut], tr_sorted[val_cut:]
        cal_pack = fit_calibrators_on_val(
            _pipe_hgb(), X[fit_idx], y[fit_idx], X[val_idx], y[val_idx]
        )
        proba_raw = pipe_hgb.predict_proba(Xte)[:, 1]
        proba_cal = cal_pack["selected_estimator"].predict_proba(Xte)[:, 1]
        final_test_report = {
            "role": "final_holdout_no_tuning",
            "train_n": int(len(tr)),
            "test_n": int(len(te)),
            "test_time_from": meta_te[0]["open_time"],
            "test_time_to": meta_te[-1]["open_time"],
            "hist_gb": _metrics(yte, proba_raw),
            "hist_gb_calibrated": _metrics(yte, proba_cal),
            "logistic": _metrics(yte, pipe_lr.predict_proba(Xte)[:, 1]),
            "calibration_selected": cal_pack["selected_on_validation"],
            "policy_hist_gb": simulate_policy_returns(
                meta_te, rows_by_sym, proba_raw >= 0.55
            ),
            "policy_hist_gb_calibrated": simulate_policy_returns(
                meta_te, rows_by_sym, proba_cal >= 0.55
            ),
            "policy_logistic": simulate_policy_returns(
                meta_te,
                rows_by_sym,
                pipe_lr.predict_proba(Xte)[:, 1] >= 0.55,
            ),
            "policy_sma": simulate_policy_returns(
                meta_te,
                rows_by_sym,
                np.asarray(
                    [
                        (
                            0.65
                            if sma_crossover_signal(
                                [float(c["close"]) for c in rows_by_sym[m["symbol"]]]
                            )[m["index"]]
                            == 1
                            else 0.35
                        )
                        >= 0.5
                        for m in meta_te
                    ]
                ),
            ),
            "policy_always_long": simulate_policy_returns(
                meta_te, rows_by_sym, np.ones(len(meta_te), dtype=bool)
            ),
            "policy_cash": {"trades": 0, "net_return_sum": 0.0},
        }
        calibration_summary["final_holdout"] = {
            "selected": cal_pack["selected_on_validation"],
            "test_raw": score_calibration(yte, proba_raw),
            "test_calibrated": score_calibration(yte, proba_cal),
        }

    strategy_table = aggregate_strategy_table(fold_reports)
    # Mark robust_edge only if mean net > cash AND CI low > 0 (strict)
    for row in strategy_table:
        ci = row.get("net_return_ci") or {}
        row["robust_edge"] = bool(
            row.get("mean_net_return_sum") is not None
            and row["mean_net_return_sum"] > 0
            and ci.get("low") is not None
            and ci["low"] > 0
        )

    order = np.argsort([m["open_time"] for m in meta])
    cut = int(len(order) * 0.85)
    final_tr = order[: max(cut - HORIZON, 1)]
    final_model = _pipe_hgb()
    final_model.fit(X[final_tr], y[final_tr])

    blob = pickle.dumps(final_model)
    model_hash = hashlib.sha256(blob).hexdigest()
    version = datetime.now(timezone.utc).strftime("v%Y%m%dT%H%M%SZ")
    model_path = artifact_dir / f"model_{version}_{model_hash[:12]}.pkl"
    model_path.write_bytes(blob)

    importance = None
    try:
        lr = _pipe_lr()
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

    aucs = [
        f["hist_gb"]["roc_auc"]
        for f in fold_reports
        if f["hist_gb"]["roc_auc"] is not None
    ]
    naive_aucs = [
        f["naive"]["roc_auc"]
        for f in fold_reports
        if f["naive"]["roc_auc"] is not None
    ]
    mean_auc = float(np.mean(aucs)) if aucs else None
    mean_naive = float(np.mean(naive_aucs)) if naive_aucs else None
    research_ok = (
        mean_auc is not None
        and mean_naive is not None
        and mean_auc > mean_naive
        and mean_auc >= 0.52
        and len(aucs) >= 1
    )

    # Aggregate calibration ECE on modeling folds (test after selection)
    eces = [
        f.get("test_after_selection", {}).get("ece")
        for f in calibration_summary["folds"]
        if isinstance(f.get("test_after_selection"), dict)
    ]
    eces = [e for e in eces if e is not None]

    result = {
        "status": "trained",
        "mode_allowed": "SHADOW_AI" if research_ok else "RESEARCH_ONLY",
        "validated_for_research": research_ok,
        "validated_for_paper_ai": False,
        "model_version": version,
        "model_hash": model_hash,
        "model_path": str(model_path),
        "algorithm": "HistGradientBoostingClassifier",
        "baseline_algorithms": [
            "LogisticRegression",
            "RandomForestClassifier",
            "naive_prior",
            "SMA10_50_proxy",
        ],
        "feature_names": FEATURE_NAMES,
        "target": TARGET_SPEC,
        "n_samples": int(len(X)),
        "n_symbols": len(rows_by_sym),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "walk_forward": fold_reports,
        "final_holdout": final_test_report,
        "strategy_comparison": strategy_table,
        "calibration": calibration_summary,
        "mean_roc_auc_hist_gb": mean_auc,
        "mean_roc_auc_naive": mean_naive,
        "roc_auc_ci": bootstrap_ci(aucs) if aucs else None,
        "mean_ece_calibrated_test": float(np.mean(eces)) if eces else None,
        "feature_importance_proxy": importance,
        "disclaimer": (
            "Resultados de investigación paper-only. Una AUC > 0.5 no implica rentabilidad. "
            "Shadow AI no ejecuta operaciones. No se afirma edge económico sin CI>0."
        ),
        "dependencies": {
            "sklearn": __import__("sklearn").__version__,
            "numpy": np.__version__,
        },
    }
    meta_path = artifact_dir / f"metrics_{version}.json"
    # Drop non-serializable estimator refs already avoided
    meta_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["metrics_path"] = str(meta_path)
    return result
