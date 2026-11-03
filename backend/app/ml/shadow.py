"""Shadow AI inference — records predictions, never executes trades."""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from ..ohlcv import fetch_klines
from . import TARGET_SPEC
from .features import FEATURE_NAMES, build_feature_matrix, row_is_complete
from .labels import HORIZON


def load_model(path: str):
    return pickle.loads(Path(path).read_bytes())


def risk_gate(
    *,
    runtime_mode: str,
    model_row: dict | None,
    paused: bool,
    data_age_s: float | None,
    probability: float,
    calibrated: bool,
) -> tuple[bool, str]:
    if paused:
        return False, "engine_paused"
    if not model_row:
        return False, "model_unavailable"
    if runtime_mode not in ("SHADOW_AI", "PAPER_AI"):
        return False, "mode_disabled"
    if not model_row.get("validated_for_research"):
        return False, "model_not_validated"
    if model_row.get("status") in ("degraded", "disabled"):
        return False, f"model_{model_row.get('status')}"
    if data_age_s is not None and data_age_s > 7200:
        return False, "stale_market_data"
    if not calibrated and probability > 0.9:
        return False, "uncalibrated_extreme_probability"
    if runtime_mode == "SHADOW_AI":
        # accept for logging only
        return True, "shadow_log_only"
    if runtime_mode == "PAPER_AI" and not model_row.get("validated_for_paper_ai"):
        return False, "paper_ai_not_approved"
    return False, "execution_not_enabled"


async def predict_symbol(
    client: httpx.AsyncClient,
    model,
    symbol: str,
    interval: str = "1h",
) -> dict[str, Any] | None:
    payload = await fetch_klines(client, symbol, interval, limit=120, use_cache=True)
    candles = [c for c in payload["candles"] if c["is_closed"]]
    if len(candles) < 60:
        return None
    feats, names = build_feature_matrix(candles)
    assert names == FEATURE_NAMES
    row = feats[-1]
    if not row_is_complete(row):
        return None
    x = np.asarray([[float(v) for v in row]], dtype=float)  # type: ignore
    proba = float(model.predict_proba(x)[0, 1])
    last = candles[-1]
    return {
        "symbol": symbol,
        "interval": interval,
        "candle_open_ms": last["open_time"],
        "decision_ts": datetime.now(timezone.utc).isoformat(),
        "horizon": HORIZON,
        "probability": proba,
        "proposed_action": "BUY_CANDIDATE" if proba >= 0.55 else "HOLD",
        "feature_version": "features_v1",
        "target": TARGET_SPEC["name"],
    }
