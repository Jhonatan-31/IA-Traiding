"""Clasificadores de régimen Etapa X — solo información hasta la barra actual."""
from __future__ import annotations

from typing import Any

from ..regimes import _atr_pct, _ema, classify_regime


def _sma(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def classify_regime_x(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Extiende el clasificador base con volumen relativo (causal)."""
    base = classify_regime(bars)
    vols = [float(x.get("volume") or 0.0) for x in bars]
    sma20 = _sma(vols, 20)
    vol_now = vols[-1] if vols else 0.0
    if sma20 is None or sma20 <= 0:
        volume = "insufficient"
        vol_ratio = None
    else:
        vol_ratio = vol_now / sma20
        if vol_ratio >= 1.5:
            volume = "high_volume"
        elif vol_ratio <= 0.7:
            volume = "low_volume"
        else:
            volume = "normal_volume"

    hour_utc = None
    if bars:
        # open_time ms → hour UTC
        hour_utc = int((int(bars[-1]["open_time"]) // 3_600_000) % 24)

    regime = f"{base['trend']}|{base['volatility']}|{volume}"
    return {
        **base,
        "volume": volume,
        "volume_ratio": round(vol_ratio, 4) if vol_ratio is not None else None,
        "hour_utc": hour_utc,
        "regime": regime,
        "regime_tv": f"{base['trend']}|{base['volatility']}",
        "look_ahead_safe": True,
        "definition": {
            "trend": "EMA20 vs EMA50 + slope 20 barras (solo pasado)",
            "volatility": "ATR% 14 vs umbrales 0.4%/1.2%",
            "volume": "volumen / SMA20 (≥1.5 alto, ≤0.7 bajo)",
        },
    }


def regime_histogram(bars: list[dict[str, Any]], step: int = 1) -> dict[str, int]:
    """Cuenta barras por régimen (causal en cada i)."""
    counts: dict[str, int] = {}
    warm = 60
    for i in range(warm, len(bars), step):
        r = classify_regime_x(bars[: i + 1])["regime_tv"]
        counts[r] = counts.get(r, 0) + 1
    return counts
