"""Etapa H — prospective decisions, execution classes, ledger, breakers."""
from __future__ import annotations

from decimal import Decimal

from app.ml.circuit_breaker import evaluate_circuit_breaker
from app.prospect.execution import ExecutionAssumptions, decide_order_status, estimate_fill_price
from app.prospect.resolve import apply_outcome


class _FakeCursor:
    def __init__(self, store):
        self.store = store
        self._last = None

    def fetchone(self):
        return self._last


class _FakeExec:
    """Minimal execute stub for idempotent outcome tests."""

    def __init__(self):
        self.outcomes = {}
        self.decisions = {1: {"resolution_status": "PENDING"}}
        self.cursor = _FakeCursor(self)

    def __call__(self, sql, params=None):
        sql_n = " ".join(sql.split())
        if sql_n.startswith("SELECT decision_id FROM prospect_outcomes"):
            did = params[0]
            self.cursor._last = {"decision_id": did} if did in self.outcomes else None
        elif sql_n.startswith("UPDATE prospect_decisions"):
            did = params[1]
            if self.decisions.get(did, {}).get("resolution_status") == "PENDING":
                self.decisions[did]["resolution_status"] = params[0]
                self.cursor._last = {"id": did}
            else:
                self.cursor._last = None
        elif sql_n.startswith("INSERT INTO prospect_outcomes"):
            did = params[0]
            if did not in self.outcomes:
                self.outcomes[did] = params
            self.cursor._last = None
        else:
            self.cursor._last = None
        return self.cursor


def test_fill_without_book_is_theoretical():
    f = estimate_fill_price(
        side="BUY",
        mid_or_ref=100.0,
        assumptions=ExecutionAssumptions(),
        bar_volume=1000,
        order_qty=10,
        order_book=None,
    )
    assert f["ok"] is True
    assert f["execution_class"] == "theoretical_no_book"
    assert f["price"] > 100


def test_partial_when_order_large_vs_volume():
    f = estimate_fill_price(
        side="BUY",
        mid_or_ref=50.0,
        assumptions=ExecutionAssumptions(),
        bar_volume=100,
        order_qty=40,
        order_book=None,
    )
    assert f["partial"] is True
    assert f["fill_qty"] == 25.0  # 25% of volume


def test_book_backed_when_asks_provided():
    f = estimate_fill_price(
        side="BUY",
        mid_or_ref=100.0,
        assumptions=ExecutionAssumptions(),
        order_book={"asks": [[101.5, 2]], "bids": [[99.5, 2]]},
    )
    assert f["execution_class"] == "book_backed_top_of_book"


def test_breaker_blocks_order_status():
    st, reason = decide_order_status(
        breaker_active=True,
        breaker_reason="max_daily_loss",
        stale_data=False,
        cash_ok=True,
        fill={"ok": True},
    )
    assert st == "REJECTED" and "circuit_breaker" in reason


def test_circuit_breaker_accounting_and_db():
    block, reason, _ = evaluate_circuit_breaker(
        equity=1000,
        initial_capital=1000,
        equity_series=[1000],
        day_start_equity=1000,
        data_age_s=10,
        recent_binance_errors=0,
        missing_marks=0,
        invested_cost=0,
        cash=1000,
        critical_down=False,
        accounting_error=True,
    )
    assert block and reason == "accounting_error"
    block2, reason2, _ = evaluate_circuit_breaker(
        equity=1000,
        initial_capital=1000,
        equity_series=[1000],
        day_start_equity=1000,
        data_age_s=10,
        recent_binance_errors=0,
        missing_marks=0,
        invested_cost=0,
        cash=1000,
        critical_down=False,
        db_unreachable=True,
    )
    assert block2 and reason2 == "postgres_unreachable"


def test_outcome_idempotent():
    ex = _FakeExec()
    ok1 = apply_outcome(
        ex,
        1,
        status="RESOLVED",
        data_quality="ok",
        observed_net_return=0.01,
        observed_label=1,
        result={"x": 1},
    )
    ok2 = apply_outcome(
        ex,
        1,
        status="RESOLVED",
        data_quality="ok",
        observed_net_return=0.01,
        observed_label=1,
        result={"x": 1},
    )
    assert ok1 is True
    assert ok2 is False


def test_ledger_budget_math():
    # pure decimal conservation check without DB
    cash = Decimal("1000")
    budget = Decimal("25")
    fee = Decimal("0.025")
    px = Decimal("50")
    qty = (budget - fee) / px
    new_cash = cash - budget
    assert new_cash + budget == cash
    assert qty > 0
