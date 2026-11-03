"""Etapa F tests — resolution, calibration, circuit breaker, economics."""
from __future__ import annotations

import numpy as np

from app.ml.calibration import expected_calibration_error, score_calibration
from app.ml.circuit_breaker import evaluate_circuit_breaker, recovery_allowed
from app.ml.economics import trade_stats
from app.ml.labels import HORIZON, net_forward_return
from app.ml.resolve import (
    STATUS_PENDING,
    STATUS_RESOLVED,
    expected_exit_open_ms,
    resolve_from_candles,
)


def _candles(n=40, start=1_700_000_000_000, step=3_600_000):
    rows = []
    px = 100.0
    for i in range(n):
        px *= 1.002
        ot = start + i * step
        rows.append(
            {
                "open_time": ot,
                "close_time": ot + step - 1,
                "open": px * 0.999,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 1000,
                "is_closed": True,
            }
        )
    return rows


def test_expected_exit_timing():
    assert expected_exit_open_ms(1000, "1h", 6) == 1000 + 6 * 3_600_000


def test_resolve_pending_until_horizon():
    candles = _candles(8)  # not enough for horizon 6 from index 0 with full set... 
    # decision at first candle; need index 6
    decision = candles[0]["open_time"]
    # only provide candles 0..5 → pending
    short = candles[:6]
    r = resolve_from_candles(short, candle_open_ms=decision, interval="1h", horizon=6)
    assert r["status"] == STATUS_PENDING


def test_resolve_correct_label_and_idempotent_logic():
    candles = _candles(20)
    decision = candles[2]["open_time"]
    r = resolve_from_candles(candles, candle_open_ms=decision, interval="1h", horizon=6)
    assert r["status"] == STATUS_RESOLVED
    entry = candles[2]["close"]
    exit_px = candles[8]["close"]
    expected_net = net_forward_return(entry, exit_px)
    assert abs(r["observed_net_return"] - expected_net) < 1e-12
    assert r["observed_label"] == (1 if expected_net > 0 else 0)


def test_resolve_invalid_missing_entry():
    candles = _candles(20)
    r = resolve_from_candles(
        candles, candle_open_ms=999, interval="1h", horizon=6
    )
    assert r["status"] == "INVALID"


def test_ece_and_calibration_scores():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, size=200)
    proba = np.clip(y + rng.normal(0, 0.2, size=200), 0, 1)
    ece = expected_calibration_error(y, proba, n_bins=8)
    assert ece is not None and ece >= 0
    sc = score_calibration(y, proba)
    assert sc["brier"] is not None


def test_circuit_breaker_trips_and_recovery_rules():
    block, reason, ev = evaluate_circuit_breaker(
        equity=800,
        initial_capital=1000,
        equity_series=[1000, 950, 900, 850, 800],
        day_start_equity=1000,
        data_age_s=10,
        recent_binance_errors=0,
        missing_marks=0,
        invested_cost=100,
        cash=700,
        critical_down=False,
        limits={"max_daily_loss_pct": 5.0, "max_drawdown_pct": 50.0},
    )
    assert block and reason == "max_daily_loss"
    ok, msg = recovery_allowed(
        active=True,
        reason="manual_lock",
        evidence={},
        recheck=(False, None, {}),
    )
    assert not ok and "manual_lock" in msg


def test_circuit_breaker_stale_data():
    block, reason, _ = evaluate_circuit_breaker(
        equity=1000,
        initial_capital=1000,
        equity_series=[1000],
        day_start_equity=1000,
        data_age_s=10_000,
        recent_binance_errors=0,
        missing_marks=0,
        invested_cost=0,
        cash=1000,
        critical_down=False,
    )
    assert block and reason == "stale_market_data"


def test_trade_stats_empty_and_costs():
    assert trade_stats([])["trades"] == 0
    assert net_forward_return(100, 100) < 0
    s = trade_stats([0.01, -0.02, 0.03])
    assert s["trades"] == 3
    assert abs(s["net_return_sum"] - 0.02) < 1e-12


def test_horizon_constant():
    assert HORIZON == 6
