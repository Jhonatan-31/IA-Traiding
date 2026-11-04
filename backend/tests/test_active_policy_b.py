"""Isolated unit tests for Strategy B signals — no DB, no live fills."""
from __future__ import annotations

from app.active.indicators_b import compute_bundle, evaluate_entry, evaluate_exit
from app.active.policy_b import FEE_RATE, SLIP_RATE


def _candle(i: int, close: float, vol: float = 100.0, high=None, low=None):
    return {
        "open_time": 1_700_000_000_000 + i * 60_000,
        "open": close * 0.999,
        "high": high if high is not None else close * 1.001,
        "low": low if low is not None else close * 0.999,
        "close": close,
        "volume": vol,
        "is_closed": True,
    }


def _series_uptrend(n: int = 80, start: float = 100.0):
    """Rising closes to encourage EMA9 > EMA21 and a late cross."""
    out = []
    px = start
    for i in range(n):
        # flat then sharp rise to force cross near the end
        if i < n - 8:
            px = start + i * 0.01
            vol = 50.0
        else:
            px = start + (n - 8) * 0.01 + (i - (n - 8)) * 0.8
            vol = 200.0
        out.append(_candle(i, px, vol=vol, high=px * 1.01, low=px * 0.99))
    return out


def _agg_5m(c1):
    out = []
    bucket = []
    for c in c1:
        bucket.append(c)
        if len(bucket) == 5:
            out.append(
                {
                    "open_time": bucket[0]["open_time"],
                    "open": bucket[0]["open"],
                    "high": max(x["high"] for x in bucket),
                    "low": min(x["low"] for x in bucket),
                    "close": bucket[-1]["close"],
                    "volume": sum(x["volume"] for x in bucket),
                    "is_closed": True,
                }
            )
            bucket = []
    return out


def test_bundle_and_hold_without_cross():
    # Need >=30 closed 5m bars ⇒ >=150 closed 1m bars
    c1 = [_candle(i, 100 + (i % 3) * 0.05, vol=80) for i in range(180)]
    c5 = _agg_5m(c1)
    b = compute_bundle(c1, c5)
    assert b is not None
    action, reason = evaluate_entry(b)
    assert action == "HOLD"
    assert reason in {
        "no_5m_trend",
        "no_ema_cross",
        "rsi_out_of_band",
        "vol_floor_reject",
        "cost_filter_reject",
        "atr_extreme",
    }


def test_exit_stop_loss():
    c1 = _series_uptrend(180)
    c5 = _agg_5m(c1)
    b = compute_bundle(c1, c5)
    assert b is not None
    entry = float(b["close"])
    action, reason = evaluate_exit({**b, "close": entry * 0.985}, entry)
    assert action == "SELL"
    assert reason == "stop_loss_1pct"


def test_exit_take_profit():
    c1 = _series_uptrend(180)
    b = compute_bundle(c1, _agg_5m(c1))
    assert b is not None
    entry = float(b["close"]) / 1.025
    action, reason = evaluate_exit({**b, "close": entry * 1.025}, entry)
    assert action == "SELL"
    assert reason == "take_profit_2pct"


def test_cost_filter_math():
    from app.active.policy_b import COST_ATR_MULT

    assert FEE_RATE + SLIP_RATE == 0.0015
    min_atr = COST_ATR_MULT * (FEE_RATE + SLIP_RATE)
    assert min_atr > 0
    assert abs(min_atr - 0.00225) < 1e-12


def test_buy_path_possible_on_synthetic_cross():
    """Build a path where cross_up is plausible; accept BUY or filtered HOLD."""
    c1 = _series_uptrend(200, start=50.0)
    b = compute_bundle(c1, _agg_5m(c1))
    assert b is not None
    action, reason = evaluate_entry(b)
    assert action in ("BUY", "HOLD")
    if action == "BUY":
        assert reason == "ema_cross_up_active"
    else:
        assert reason in {
            "no_5m_trend",
            "no_ema_cross",
            "rsi_out_of_band",
            "vol_floor_reject",
            "cost_filter_reject",
            "atr_extreme",
        }
