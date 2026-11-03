"""Unit tests — drawdown peak bugfix + lab valuation reconciliation."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.lab.reconcile_valuation import (
    drawdown_fraction,
    peak_equity_from_daily_rows,
    reconcile_lab_snapshot,
)


def test_peak_uses_start_when_end_lower():
    rows = [{"day": "2026-11-03", "start_equity": 1000, "end_equity": 999.57}]
    peak = peak_equity_from_daily_rows(rows, Decimal("1000"))
    assert peak == Decimal("1000")


def test_peak_coalesce_bug_regression():
    """Document buggy MAX(COALESCE(end,start)) would return 999.57."""
    end, start = Decimal("999.57"), Decimal("1000")
    buggy = end  # COALESCE(end, start) → end
    correct = max(start, end)
    assert buggy < correct
    assert peak_equity_from_daily_rows(
        [{"start_equity": start, "end_equity": end}], Decimal("1000")
    ) == correct


def test_drawdown_vs_peak_matches_user_expectation():
    peak = Decimal("1000")
    equity = Decimal("999.57")
    dd = drawdown_fraction(equity=equity, peak=peak)
    assert dd == pytest.approx(0.00043, rel=1e-3)
    assert dd * 100 == pytest.approx(0.043, rel=1e-3)


def test_drawdown_zero_when_equity_at_peak():
    assert drawdown_fraction(equity=Decimal("1000"), peak=Decimal("1000")) == 0.0


def test_reconcile_cash_plus_mv_identity():
    marks = {
        "BTCUSDT": {
            "ok": True,
            "price": 78000.0,
            "source": "t",
            "at": "2026-11-03T22:00:00+00:00",
        }
    }
    out = reconcile_lab_snapshot(
        cash=Decimal("925"),
        positions=[
            {
                "symbol": "BTCUSDT",
                "qty": Decimal("0.001"),
                "cost": Decimal("25"),
                "entry_price": Decimal("78000"),
            }
        ],
        marks=marks,
        fees_accumulated=Decimal("0.1"),
        realized_pnl=Decimal("-0.13"),
        initial_capital=Decimal("1000"),
    )
    assert out["status"] == "OK"
    assert out["identity_ok"] is True
    assert out["market_value"] == pytest.approx(78.0)
    assert out["equity_gross"] == pytest.approx(925 + 78)
    assert out["unrealized_pnl"] == pytest.approx(78 - 25)
    assert out["estimated_exit_fees"] is not None
    assert out["estimated_exit_slippage_cost"] is not None
    assert out["equity_net_after_exit_costs_est"] < out["equity_gross"]


def test_reconcile_incomplete_without_marks():
    out = reconcile_lab_snapshot(
        cash=Decimal("900"),
        positions=[{"symbol": "ETHUSDT", "qty": 1, "cost": 100, "entry_price": 100}],
        marks={},
        fees_accumulated=Decimal("0"),
        realized_pnl=Decimal("0"),
        initial_capital=Decimal("1000"),
    )
    assert out["status"] == "INCOMPLETE"
    assert out["equity_gross"] is None
    assert out["positions"][0]["complete"] is False
