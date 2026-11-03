"""Explicit target labels using only future closes for y — never mixed into X."""
from __future__ import annotations

from . import TARGET_SPEC

FEE = float(TARGET_SPEC["costs"]["fee_rate"])
SLIP = float(TARGET_SPEC["costs"]["slip_rate"])
HORIZON = int(TARGET_SPEC["horizon_bars"])


def net_forward_return(entry_close: float, exit_close: float) -> float:
    """Long-only illustrative fill: buy with slip+fee, sell with slip+fee."""
    buy = entry_close * (1 + SLIP) * (1 + FEE)
    sell = exit_close * (1 - SLIP) * (1 - FEE)
    return sell / buy - 1.0


def label_series(candles: list[dict], horizon: int = HORIZON) -> list[int | None]:
    """
    At index t (decision on closed candle t), label uses closes[t+horizon].
    Returns None when future bars are unavailable (cannot leak into training by dropping).
    """
    n = len(candles)
    out: list[int | None] = [None] * n
    for t in range(n):
        j = t + horizon
        if j >= n:
            out[t] = None
            continue
        entry = float(candles[t]["close"])
        exit_px = float(candles[j]["close"])
        net = net_forward_return(entry, exit_px)
        out[t] = 1 if net > 0 else 0
    return out


def sma_crossover_signal(closes: list[float], fast: int = 10, slow: int = 50) -> list[int]:
    """1 = long bias after bullish cross state, else 0. Causal."""
    from ..indicators import sma

    f = sma(closes, fast)
    s = sma(closes, slow)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if f[i] is None or s[i] is None:
            out[i] = 0
        else:
            out[i] = 1 if f[i] > s[i] else 0  # type: ignore
    return out
