"""Historical Shadow replay — predictions at past bars with known outcomes (research only)."""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .features import FEATURE_NAMES, build_feature_matrix, row_is_complete
from .labels import HORIZON, label_series, net_forward_return
from .resolve import STATUS_RESOLVED


def load_model(path: str | Path):
    return pickle.loads(Path(path).read_bytes())


def replay_resolved_predictions(
    rows: list[dict],
    model,
    *,
    model_version: str,
    max_per_symbol: int = 8,
    stride: int = 12,
) -> list[dict[str, Any]]:
    """
    Emit resolved prediction dicts for bars where horizon outcome is known.
    Does not touch live trading. Probabilities are model outputs at decision time.
    """
    by_sym: dict[str, list[dict]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    for s in by_sym:
        by_sym[s] = sorted(by_sym[s], key=lambda x: x["open_time"])

    out: list[dict[str, Any]] = []
    for sym, candles in by_sym.items():
        feats, names = build_feature_matrix(candles)
        assert names == FEATURE_NAMES
        labels = label_series(candles)
        count = 0
        # walk from older complete bars; skip most recent incomplete horizon
        for i in range(60, len(candles) - HORIZON, stride):
            if count >= max_per_symbol:
                break
            if labels[i] is None or not row_is_complete(feats[i]):
                continue
            x = np.asarray([[float(v) for v in feats[i]]], dtype=float)  # type: ignore
            proba = float(model.predict_proba(x)[0, 1])
            entry = float(candles[i]["close"])
            exit_px = float(candles[i + HORIZON]["close"])
            net = net_forward_return(entry, exit_px)
            lab = 1 if net > 0 else 0
            out.append(
                {
                    "model_version": model_version,
                    "symbol": sym,
                    "interval": candles[i].get("interval", "1h"),
                    "decision_ts": datetime.fromtimestamp(
                        candles[i]["close_time"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "candle_open_ms": int(candles[i]["open_time"]),
                    "horizon": HORIZON,
                    "probability": proba,
                    "proposed_action": "BUY_CANDIDATE" if proba >= 0.55 else "HOLD",
                    "accepted": True,
                    "reject_reason": "shadow_replay_log",
                    "feature_version": "features_v1",
                    "source": "shadow_replay",
                    "resolution_status": STATUS_RESOLVED,
                    "observed_label": lab,
                    "observed_net_return": float(net),
                    "data_quality": "ok",
                }
            )
            count += 1
    return out


def persist_replay(execute, preds: list[dict[str, Any]]) -> int:
    import json

    n = 0
    for p in preds:
        execute(
            """INSERT INTO ml_predictions(
                model_version, symbol, interval, decision_ts, candle_open_ms, horizon,
                probability, proposed_action, accepted, reject_reason, feature_version,
                source, resolution_status, observed_label, observed_net_return,
                observed_at, data_quality, resolve_meta)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s::jsonb)
               ON CONFLICT(model_version, symbol, interval, candle_open_ms, horizon)
               DO NOTHING""",
            (
                p["model_version"],
                p["symbol"],
                p["interval"],
                p["decision_ts"],
                p["candle_open_ms"],
                p["horizon"],
                p["probability"],
                p["proposed_action"],
                p["accepted"],
                p["reject_reason"],
                p["feature_version"],
                p["source"],
                p["resolution_status"],
                p["observed_label"],
                p["observed_net_return"],
                p["data_quality"],
                json.dumps({"source": "shadow_replay", "horizon": HORIZON}),
            ),
        )
        n += 1
    return n
