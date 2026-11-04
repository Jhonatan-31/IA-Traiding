"""DEMO indicators — closed 1m/5m candles with policy v1 bands."""
from __future__ import annotations

from typing import Any

from ..express.indicators import _atr, _ema, _rsi
from .policy import ATR_PCT_MAX, RSI_BUY_HI, RSI_BUY_LO


def compute_bundle(candles_1m: list[dict], candles_5m: list[dict]) -> dict[str, Any] | None:
    c1 = [c for c in candles_1m if c.get("is_closed", True)]
    c5 = [c for c in candles_5m if c.get("is_closed", True)]
    if len(c1) < 40 or len(c5) < 30:
        return None
    closes1 = [float(c["close"]) for c in c1]
    closes5 = [float(c["close"]) for c in c5]
    vols1 = [float(c["volume"]) for c in c1]
    ema9_1 = _ema(closes1, 9)
    ema21_1 = _ema(closes1, 21)
    ema9_5 = _ema(closes5, 9)
    ema21_5 = _ema(closes5, 21)
    rsi = _rsi(closes1, 14)
    atr = _atr(c1, 14)
    vol_sma = sum(vols1[-20:]) / 20.0
    last = c1[-1]
    close = float(last["close"])
    if None in (ema9_1, ema21_1, ema9_5, ema21_5, rsi, atr) or close <= 0:
        return None
    atr_pct = float(atr) / close
    flags = {
        "trend_5m": bool(ema9_5 > ema21_5),
        "trend_1m": bool(ema9_1 > ema21_1),
        "rsi_ok": bool(RSI_BUY_LO <= float(rsi) <= RSI_BUY_HI),
        "vol_ok": bool(vols1[-1] > vol_sma),
        "atr_ok": bool(atr_pct <= ATR_PCT_MAX),
    }
    n_true = sum(1 for v in flags.values() if v)
    score = n_true / len(flags)
    return {
        "candle_1m_ms": int(last["open_time"]),
        "close": close,
        "ema9_1m": ema9_1,
        "ema21_1m": ema21_1,
        "ema9_5m": ema9_5,
        "ema21_5m": ema21_5,
        "rsi14_1m": rsi,
        "atr14_1m": atr,
        "atr_pct": atr_pct,
        "vol_1m": vols1[-1],
        "vol_sma20": vol_sma,
        "flags": flags,
        "flags_true": n_true,
        "signal_score": score,
    }
