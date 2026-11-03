"""Technical indicators — no look-ahead. Warmup returns None."""
from __future__ import annotations

from typing import Sequence


Number = float | int


def _f(xs: Sequence[Number]) -> list[float]:
    return [float(x) for x in xs]


def sma(values: Sequence[Number], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    xs = _f(values)
    out: list[float | None] = [None] * len(xs)
    if len(xs) < period:
        return out
    window = sum(xs[:period])
    out[period - 1] = window / period
    for i in range(period, len(xs)):
        window += xs[i] - xs[i - period]
        out[i] = window / period
    return out


def ema(values: Sequence[Number], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    xs = _f(values)
    out: list[float | None] = [None] * len(xs)
    if len(xs) < period:
        return out
    k = 2 / (period + 1)
    seed = sum(xs[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(xs)):
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[Number], period: int = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    xs = _f(values)
    out: list[float | None] = [None] * len(xs)
    if len(xs) < period + 1:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = xs[i] - xs[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - (100 / (1 + rs))
    return out


def macd(
    values: Sequence[Number],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    if not (1 <= fast < slow):
        raise ValueError("require 1 <= fast < slow")
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: list[float | None] = [None] * len(values)
    for i, (a, b) in enumerate(zip(ema_fast, ema_slow)):
        if a is not None and b is not None:
            line[i] = a - b
    # Signal EMA over available MACD line values (skip leading Nones)
    first = next((i for i, v in enumerate(line) if v is not None), None)
    sig: list[float | None] = [None] * len(line)
    hist: list[float | None] = [None] * len(line)
    if first is None:
        return {"macd": line, "signal": sig, "histogram": hist}
    # After first non-null, MACD line is continuous by construction.
    continuous = [float(v) for v in line[first:]]  # type: ignore[arg-type]
    sig_cont = ema(continuous, signal)
    for j, s in enumerate(sig_cont):
        idx = first + j
        sig[idx] = s
        if s is not None and line[idx] is not None:
            hist[idx] = float(line[idx]) - s  # type: ignore[arg-type]
    return {"macd": line, "signal": sig, "histogram": hist}


def bollinger(
    values: Sequence[Number], period: int = 20, mult: float = 2.0
) -> dict[str, list[float | None]]:
    xs = _f(values)
    mid = sma(xs, period)
    upper: list[float | None] = [None] * len(xs)
    lower: list[float | None] = [None] * len(xs)
    for i in range(len(xs)):
        if mid[i] is None:
            continue
        window = xs[i - period + 1 : i + 1]
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in window) / period  # type: ignore[operator]
        std = var**0.5
        upper[i] = mean + mult * std  # type: ignore[operator]
        lower[i] = mean - mult * std  # type: ignore[operator]
    return {"middle": mid, "upper": upper, "lower": lower}


def atr(
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    period: int = 14,
) -> list[float | None]:
    h, l, c = _f(highs), _f(lows), _f(closes)
    n = len(c)
    if not (len(h) == len(l) == n):
        raise ValueError("high/low/close length mismatch")
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    trs: list[float] = [0.0] * n
    trs[0] = h[0] - l[0]
    for i in range(1, n):
        trs[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    first = sum(trs[1 : period + 1]) / period
    out[period] = first
    prev = first
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def compute_bundle(
    opens: Sequence[Number],
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
) -> dict:
    """Compute standard indicator pack aligned to candle index."""
    c = _f(closes)
    return {
        "sma10": sma(c, 10),
        "sma20": sma(c, 20),
        "sma50": sma(c, 50),
        "sma200": sma(c, 200),
        "ema9": ema(c, 9),
        "ema21": ema(c, 21),
        "ema50": ema(c, 50),
        "rsi14": rsi(c, 14),
        "macd": macd(c, 12, 26, 9),
        "bollinger": bollinger(c, 20, 2.0),
        "atr14": atr(highs, lows, closes, 14),
    }
