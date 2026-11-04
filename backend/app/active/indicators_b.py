"""Strategy B indicators — closed 1m/5m candles, EMA crossover + filters."""
from __future__ import annotations

from typing import Any

from ..express.indicators import _atr, _ema, _rsi
from .policy_b import (
    ATR_PCT_MAX,
    COST_ATR_MULT,
    FEE_RATE,
    RSI_BUY_HI,
    RSI_BUY_LO,
    SLIP_RATE,
    VOL_FLOOR_MULT,
)


def _ema_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return out
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    out[period - 1] = e
    for i in range(period, len(closes)):
        e = closes[i] * k + e * (1 - k)
        out[i] = e
    return out


def compute_bundle(candles_1m: list[dict], candles_5m: list[dict]) -> dict[str, Any] | None:
    c1 = [c for c in candles_1m if c.get("is_closed", True)]
    c5 = [c for c in candles_5m if c.get("is_closed", True)]
    if len(c1) < 40 or len(c5) < 30:
        return None
    closes1 = [float(c["close"]) for c in c1]
    closes5 = [float(c["close"]) for c in c5]
    vols1 = [float(c["volume"]) for c in c1]
    ema9_s = _ema_series(closes1, 9)
    ema21_s = _ema_series(closes1, 21)
    ema9_1 = ema9_s[-1]
    ema21_1 = ema21_s[-1]
    ema9_1_prev = ema9_s[-2]
    ema21_1_prev = ema21_s[-2]
    ema9_5 = _ema(closes5, 9)
    ema21_5 = _ema(closes5, 21)
    rsi = _rsi(closes1, 14)
    atr = _atr(c1, 14)
    vol_sma = sum(vols1[-20:]) / 20.0
    last = c1[-1]
    close = float(last["close"])
    if None in (ema9_1, ema21_1, ema9_1_prev, ema21_1_prev, ema9_5, ema21_5, rsi, atr) or close <= 0:
        return None
    atr_pct = float(atr) / close
    round_trip = 2.0 * (FEE_RATE + SLIP_RATE)
    cross_up = bool(ema9_1_prev <= ema21_1_prev and ema9_1 > ema21_1)
    cross_down = bool(ema9_1_prev >= ema21_1_prev and ema9_1 < ema21_1)
    trend_5m = bool(ema9_5 > ema21_5)
    trend_1m = bool(ema9_1 > ema21_1)
    # Momentum: close above close of 5 bars ago (closed bars only)
    momentum = bool(len(closes1) >= 6 and closes1[-1] > closes1[-6])
    rsi_ok = bool(RSI_BUY_LO <= float(rsi) <= RSI_BUY_HI)
    vol_ok = bool(vols1[-1] >= VOL_FLOOR_MULT * vol_sma)
    cost_ok = bool(atr_pct >= COST_ATR_MULT * (FEE_RATE + SLIP_RATE))
    atr_ok = bool(atr_pct <= ATR_PCT_MAX)
    # Freshness: new cross OR EMA spread widening vs 3 bars ago
    ema9_3 = ema9_s[-4] if len(ema9_s) >= 4 else None
    ema21_3 = ema21_s[-4] if len(ema21_s) >= 4 else None
    spread_now = float(ema9_1) - float(ema21_1)
    spread_prev = (
        float(ema9_3) - float(ema21_3) if ema9_3 is not None and ema21_3 is not None else None
    )
    fresh = bool(cross_up or (spread_prev is not None and spread_now > spread_prev and spread_now > 0))
    flags = {
        "trend_5m": trend_5m,
        "trend_1m": trend_1m,
        "momentum": momentum,
        "fresh_impulse": fresh,  # informational / soft preference
        "rsi_ok": rsi_ok,
        "vol_floor": vol_ok,
        "cost_ok": cost_ok,
        "atr_ok": atr_ok,
    }
    n_true = sum(1 for v in flags.values() if v)
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
        "round_trip_cost": round_trip,
        "cross_up": cross_up,
        "cross_down": cross_down,
        "flags": flags,
        "flags_true": n_true,
        "signal_score": n_true / len(flags),
    }


def evaluate_entry(bundle: dict[str, Any]) -> tuple[str, str]:
    """BUY with explicit structure (not Demo 4/5 counting).

    Required: trend 5m, (trend 1m OR momentum), RSI, vol floor, cost cover, ATR cap.
    Differentiator vs A: mandatory cost-vs-ATR filter; volume is a floor (0.6×SMA)
    not a spike test; 1m impulse uses OR of alignment/momentum.
    """
    f = bundle["flags"]
    if not f["trend_5m"]:
        return "HOLD", "no_5m_trend"
    if not (f["trend_1m"] or f["momentum"]):
        return "HOLD", "no_ema_cross"
    if not f["rsi_ok"]:
        return "HOLD", "rsi_out_of_band"
    if not f["vol_floor"]:
        return "HOLD", "vol_floor_reject"
    if not f["cost_ok"]:
        return "HOLD", "cost_filter_reject"
    if not f["atr_ok"]:
        return "HOLD", "atr_extreme"
    return "BUY", "ema_cross_up_active"


def evaluate_exit(bundle: dict[str, Any], entry_price: float) -> tuple[str, str]:
    mark = float(bundle["close"])
    if mark <= entry_price * (1 - 0.01):
        return "SELL", "stop_loss_1pct"
    if mark >= entry_price * (1 + 0.02):
        return "SELL", "take_profit_2pct"
    if bundle.get("cross_down") or (
        bundle["ema9_1m"] < bundle["ema21_1m"] and float(bundle["rsi14_1m"]) < 40.0
    ):
        return "SELL", "ema_cross_down_exit"
    return "HOLD", "hold_position"
