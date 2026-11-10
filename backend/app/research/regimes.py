"""Clasificador determinista de régimen — solo datos hasta la barra i (sin look-ahead)."""
from __future__ import annotations

from typing import Any


def _ema(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _atr_pct(c1: list[dict], n: int = 14) -> float | None:
    if len(c1) < n + 1:
        return None
    trs = []
    for i in range(1, len(c1)):
        h, l, pc = float(c1[i]["high"]), float(c1[i]["low"]), float(c1[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    atr = sum(trs[-n:]) / n
    close = float(c1[-1]["close"])
    return atr / close if close else None


def classify_regime(c1: list[dict], c5: list[dict] | None = None) -> dict[str, Any]:
    """Regímenes: uptrend/downtrend/sideways + high/low vol + insufficient."""
    if len(c1) < 60:
        return {"regime": "insufficient_data", "trend": "insufficient", "volatility": "insufficient"}

    closes = [float(x["close"]) for x in c1]
    e20 = _ema(closes[-40:], 20)
    e50 = _ema(closes[-60:], 50)
    atrp = _atr_pct(c1[-40:])
    # slope proxy: close vs close[-20]
    slope = (closes[-1] / closes[-21] - 1.0) if len(closes) > 21 and closes[-21] else 0.0

    if e20 is None or e50 is None:
        trend = "insufficient"
    elif e20 > e50 * 1.001 and slope > 0.002:
        trend = "uptrend"
    elif e20 < e50 * 0.999 and slope < -0.002:
        trend = "downtrend"
    else:
        trend = "sideways"

    if atrp is None:
        vol = "insufficient"
    elif atrp >= 0.012:
        vol = "high_volatility"
    elif atrp <= 0.004:
        vol = "low_volatility"
    else:
        vol = "normal_volatility"

    regime = f"{trend}|{vol}"
    return {
        "regime": regime,
        "trend": trend,
        "volatility": vol,
        "atr_pct": atrp,
        "ema20": e20,
        "ema50": e50,
        "slope_20": slope,
        "look_ahead_safe": True,
    }
