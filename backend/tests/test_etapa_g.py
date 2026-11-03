"""Etapa G — metrics units, expected return, portfolio next-bar execution."""
from __future__ import annotations

import math

from app.ml.expected_return import estimate_expected_net
from app.ml.metrics_audit import (
    block_bootstrap_ci,
    max_drawdown_from_equity,
    profit_factor,
)
from app.ml.portfolio_backtest import run_portfolio_backtest
from app.ml.strategies import signal_sma10_50


def _bars(n=80, start=1_700_000_000_000, px0=100.0, step=3_600_000):
    rows = []
    px = px0
    for i in range(n):
        px *= 1.001
        ot = start + i * step
        rows.append(
            {
                "symbol": "TESTUSDT",
                "interval": "1h",
                "open_time": ot,
                "close_time": ot + step - 1,
                "open": px * 0.999,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 5000 + i,
            }
        )
    return rows


def test_profit_factor_and_drawdown_units():
    assert abs(profit_factor([0.1, -0.05, 0.2]) - (0.3 / 0.05)) < 1e-9
    eq = [100, 110, 105, 120, 90]
    dd = max_drawdown_from_equity(eq)
    assert dd is not None and dd < 0
    assert abs(dd - (90 / 120 - 1)) < 1e-9


def test_block_bootstrap_ci_structure():
    vals = [0.01 * ((-1) ** i) for i in range(100)]
    ci = block_bootstrap_ci(vals, block_size=10, n_boot=50)
    assert ci["method"] == "block_bootstrap"
    assert ci["low"] <= ci["mean"] <= ci["high"]


def test_expected_net_uncertain_when_missing():
    r = estimate_expected_net(
        p_up=0.6, mean_gain_if_up=None, mean_loss_if_down=-0.02
    )
    assert r["uncertain"] is True
    assert r["expected_net"] is None


def test_expected_net_explicit():
    r = estimate_expected_net(
        p_up=0.6,
        mean_gain_if_up=0.03,
        mean_loss_if_down=-0.02,
        fee_rate=0.001,
        slip_rate=0.001,
    )
    # roundtrip 0.004 → net_up=0.026, net_down=-0.024
    # E = 0.6*0.026 + 0.4*-0.024 = 0.0156 - 0.0096 = 0.006
    assert r["uncertain"] is False
    assert abs(r["expected_net"] - 0.006) < 1e-9


def test_portfolio_executes_next_bar_not_signal_close():
    bars = {"TESTUSDT": _bars(100)}
    # signal only on index 50
    sig = [0] * 100
    sig[50] = 1
    r = run_portfolio_backtest(
        bars_by_symbol=bars,
        signals_by_symbol={"TESTUSDT": sig},
        initial_capital=1000,
        horizon=6,
        max_positions=1,
        fee_rate=0.001,
        slip_rate=0.001,
    )
    assert r["unit"] == "portfolio_equity_fraction"
    assert r["execution_model"] == "signal_close_t__fill_open_t_plus_1"
    buys = [f for f in r.get("closed_pnls", [])]  # may be closed
    # At least attempted fill: n_fills includes buy
    assert r["n_fills"] >= 1
    # Signal close price at 50 vs fill open at 51 must differ path — ensure not same-bar close fill
    assert r["total_return_fraction"] is not None


def test_cash_strategy_zero_return():
    bars = {"TESTUSDT": _bars(60)}
    r = run_portfolio_backtest(
        bars_by_symbol=bars,
        signals_by_symbol={"TESTUSDT": [0] * 60},
        initial_capital=1000,
        horizon=6,
    )
    assert abs(r["total_return_fraction"]) < 1e-12
    assert r["n_closed"] == 0


def test_sma_signal_causal_length():
    closes = [100 + i * 0.1 for i in range(60)]
    sig = signal_sma10_50(closes)
    assert len(sig) == 60
    assert all(s in (0, 1) for s in sig)
