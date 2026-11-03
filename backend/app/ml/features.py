"""Chronological feature engineering — no future peeking."""
from __future__ import annotations

import math
from typing import Any

from ..indicators import atr, bollinger, ema, macd, rsi, sma


FEATURE_NAMES = [
    "log_ret_1",
    "log_ret_3",
    "log_ret_6",
    "log_ret_12",
    "sma10_dist",
    "sma20_dist",
    "sma50_dist",
    "ema9_dist",
    "ema21_dist",
    "rsi14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "bb_pctb",
    "bb_width",
    "atr14_pct",
    "vol_change_1",
    "vol_ma20_ratio",
    "realized_vol_20",
    "momentum_10",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


def _log_ret(a: float, b: float) -> float | None:
    if a <= 0 or b <= 0:
        return None
    return math.log(a / b)


def build_feature_matrix(candles: list[dict]) -> tuple[list[list[float | None]], list[str]]:
    """Return aligned feature rows (same length as candles). Leading warmup = None cells."""
    n = len(candles)
    if n == 0:
        return [], FEATURE_NAMES
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]
    opens_t = [int(c["open_time"]) for c in candles]

    s10 = sma(closes, 10)
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    r14 = rsi(closes, 14)
    m = macd(closes)
    bb = bollinger(closes, 20, 2)
    a14 = atr(highs, lows, closes, 14)
    vol_ma20 = sma(vols, 20)

    rows: list[list[float | None]] = []
    for i in range(n):
        c = closes[i]
        feat: dict[str, float | None] = {k: None for k in FEATURE_NAMES}
        if i >= 1:
            feat["log_ret_1"] = _log_ret(closes[i], closes[i - 1])
        if i >= 3:
            feat["log_ret_3"] = _log_ret(closes[i], closes[i - 3])
        if i >= 6:
            feat["log_ret_6"] = _log_ret(closes[i], closes[i - 6])
        if i >= 12:
            feat["log_ret_12"] = _log_ret(closes[i], closes[i - 12])
        if s10[i] and c:
            feat["sma10_dist"] = (c - s10[i]) / s10[i]  # type: ignore
        if s20[i] and c:
            feat["sma20_dist"] = (c - s20[i]) / s20[i]  # type: ignore
        if s50[i] and c:
            feat["sma50_dist"] = (c - s50[i]) / s50[i]  # type: ignore
        if e9[i] and c:
            feat["ema9_dist"] = (c - e9[i]) / e9[i]  # type: ignore
        if e21[i] and c:
            feat["ema21_dist"] = (c - e21[i]) / e21[i]  # type: ignore
        feat["rsi14"] = r14[i]
        feat["macd_line"] = m["macd"][i]
        feat["macd_signal"] = m["signal"][i]
        feat["macd_hist"] = m["histogram"][i]
        if bb["upper"][i] is not None and bb["lower"][i] is not None and bb["middle"][i]:
            width = bb["upper"][i] - bb["lower"][i]  # type: ignore
            feat["bb_width"] = width / bb["middle"][i] if bb["middle"][i] else None  # type: ignore
            if width:
                feat["bb_pctb"] = (c - bb["lower"][i]) / width  # type: ignore
        if a14[i] is not None and c:
            feat["atr14_pct"] = a14[i] / c  # type: ignore
        if i >= 1 and vols[i - 1] > 0:
            feat["vol_change_1"] = (vols[i] - vols[i - 1]) / vols[i - 1]
        if vol_ma20[i] and vol_ma20[i] > 0:
            feat["vol_ma20_ratio"] = vols[i] / vol_ma20[i]  # type: ignore
        if i >= 20:
            rets = []
            ok = True
            for j in range(i - 19, i + 1):
                lr = _log_ret(closes[j], closes[j - 1]) if j >= 1 else None
                if lr is None:
                    ok = False
                    break
                rets.append(lr)
            if ok and rets:
                mean = sum(rets) / len(rets)
                var = sum((x - mean) ** 2 for x in rets) / len(rets)
                feat["realized_vol_20"] = math.sqrt(var)
        if i >= 10 and closes[i - 10] > 0:
            feat["momentum_10"] = closes[i] / closes[i - 10] - 1
        # temporal from open_time UTC
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(opens_t[i] / 1000, tz=timezone.utc)
        hour = dt.hour + dt.minute / 60
        dow = dt.weekday()
        feat["hour_sin"] = math.sin(2 * math.pi * hour / 24)
        feat["hour_cos"] = math.cos(2 * math.pi * hour / 24)
        feat["dow_sin"] = math.sin(2 * math.pi * dow / 7)
        feat["dow_cos"] = math.cos(2 * math.pi * dow / 7)
        rows.append([feat[k] for k in FEATURE_NAMES])
    return rows, FEATURE_NAMES


def row_is_complete(row: list[float | None]) -> bool:
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in row)


def assert_no_feature_uses_future(
    candles: list[dict], features: list[list[float | None]], idx: int
) -> None:
    """Sanity: features at idx must be computable from candles[: idx+1] only."""
    sub_feat, _ = build_feature_matrix(candles[: idx + 1])
    a = features[idx]
    b = sub_feat[-1]
    for x, y in zip(a, b):
        if x is None and y is None:
            continue
        if x is None or y is None:
            raise AssertionError("feature availability mismatch — possible leakage")
        if abs(float(x) - float(y)) > 1e-9:
            raise AssertionError("feature value mismatch — possible leakage")
