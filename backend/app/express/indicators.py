"""Closed-candle indicators for express policy."""
from __future__ import annotations

from typing import Any


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    for x in closes[period:]:
        e = x * k + e * (1 - k)
    return e


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    if len(gains) < period:
        return None
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for x in trs[period:]:
        atr = (atr * (period - 1) + x) / period
    return atr


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
        "rsi_ok": bool(45.0 <= float(rsi) <= 68.0),
        "vol_ok": bool(vols1[-1] > vol_sma),
        "atr_ok": bool(atr_pct <= 0.015),
    }
    score = sum(1.0 for v in flags.values() if v) / len(flags)
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
        "signal_score": score,
    }
