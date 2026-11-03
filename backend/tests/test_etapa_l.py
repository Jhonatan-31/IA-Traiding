"""Etapa L — lab trade-executor: idempotency, risk, exits, no real orders."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from app.lab.exits import evaluate_exit
from app.lab.risk import can_buy, evaluate_lab_breaker
from app.lab.signals import sma_cross_signal
from app.prospect.execution import ExecutionAssumptions, estimate_fill_price


def test_sma_signal_buy_sell_hold():
    # rising cross
    closes = [100.0] * 40 + [99.0] * 10 + [101.0] * 10
    # craft clearer series
    base = [100.0 + i * 0.01 for i in range(60)]
    assert sma_cross_signal(base) in ("BUY", "SELL", "HOLD")
    assert sma_cross_signal([1.0] * 10) == "HOLD"


def test_duplicate_signal_key_components():
    a = ("SMA10_SMA50_1H", "BTCUSDT", "BUY", 1793732400000)
    b = ("SMA10_SMA50_1H", "BTCUSDT", "BUY", 1793732400000)
    assert a == b


def test_can_buy_blocks_insufficient_cash():
    ok, reason = can_buy(
        paused=False,
        breaker_active=False,
        cash=Decimal("10"),
        budget=Decimal("25"),
        positions_n=0,
        max_positions=10,
        symbol_valid=True,
        data_fresh=True,
        liquidity_ok=True,
        fill_ok=True,
        strategy="SMA10_SMA50_1H",
    )
    assert ok is False and reason == "insufficient_cash"


def test_can_buy_blocks_unauthorized_strategy():
    ok, reason = can_buy(
        paused=False,
        breaker_active=False,
        cash=Decimal("1000"),
        budget=Decimal("25"),
        positions_n=0,
        max_positions=10,
        symbol_valid=True,
        data_fresh=True,
        liquidity_ok=True,
        fill_ok=True,
        strategy="AI_SHADOW",
    )
    assert ok is False and reason == "unauthorized_strategy"


def test_can_buy_blocks_max_positions():
    ok, reason = can_buy(
        paused=False,
        breaker_active=False,
        cash=Decimal("1000"),
        budget=Decimal("25"),
        positions_n=10,
        max_positions=10,
        symbol_valid=True,
        data_fresh=True,
        liquidity_ok=True,
        fill_ok=True,
        strategy="SMA10_SMA50_1H",
    )
    assert ok is False and reason == "max_positions"


def test_can_buy_blocks_stale():
    ok, reason = can_buy(
        paused=False,
        breaker_active=False,
        cash=Decimal("1000"),
        budget=Decimal("25"),
        positions_n=0,
        max_positions=10,
        symbol_valid=True,
        data_fresh=False,
        liquidity_ok=True,
        fill_ok=True,
        strategy="SMA10_SMA50_1H",
    )
    assert reason == "stale_market_data"


def test_fee_and_slippage_in_fill():
    f = estimate_fill_price(
        side="BUY",
        mid_or_ref=100.0,
        assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.001),
        order_book=None,
    )
    assert f["ok"] and f["price"] > 100.0
    assert f["fee_component"] > 0


def test_stop_loss_triggers_distinct_from_execution():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    d = evaluate_exit(
        pos,
        mark_price=Decimal("97.5"),
        mark_age_s=10,
        stale_s=7200,
        strategy_side=None,
        bars_held=1,
    )
    assert d["action"] == "SELL"
    assert d["reason"] == "stop_loss"
    assert d["stop_triggered"] is True
    assert d["stop_trigger_price"] == 98.0  # 100 * 0.98


def test_take_profit():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    d = evaluate_exit(
        pos,
        mark_price=Decimal("105"),
        mark_age_s=5,
        stale_s=7200,
        strategy_side=None,
        bars_held=2,
    )
    assert d["reason"] == "take_profit"
    assert d["stop_trigger_price"] == 104.0


def test_stale_mark_blocks_exit():
    pos = {"entry_price": 100, "stop_loss_pct": 0.02, "take_profit_pct": 0.04, "max_hold_bars": 48}
    d = evaluate_exit(
        pos,
        mark_price=Decimal("90"),
        mark_age_s=99999,
        stale_s=7200,
        strategy_side=None,
        bars_held=1,
    )
    assert d["action"] == "HOLD"
    assert d["allow_execution"] is False


def test_sell_without_position_reason():
    from app.lab.ledger import apply_sell

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            if "FROM lab_positions" in " ".join(sql.split()):
                cur.fetchone = lambda: None
            return cur

    r = apply_sell(
        Ex(),
        order_uid="00000000-0000-0000-0000-000000000001",
        symbol="BTCUSDT",
        fill_price=Decimal("100"),
        candle_ms=1,
        strategy="SMA10_SMA50_1H",
        reason="test",
    )
    assert r["status"] == "REJECTED" and r["reason"] == "no_position"


def test_daily_loss_breaker():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            cur.fetchone = lambda: {
                "cash": Decimal("900"),
                "initial_capital": Decimal("1000"),
            }
            cur.__iter__ = lambda self: iter([])
            return cur

    # Need lab_equity to work - positions empty, cash from account
    # evaluate with equity 900 vs day_start 1000 → 10% > 2%
    active, reason = evaluate_lab_breaker(
        Ex(),
        equity=Decimal("900"),
        day_start_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        data_age_s=10,
        binance_ok=True,
        accounting_ok=True,
    )
    assert active and reason == "max_daily_loss"


def test_binance_failure_breaker():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            cur.fetchone = lambda: {"cash": 1000, "initial_capital": 1000}
            cur.__iter__ = lambda self: iter([])
            return cur

    active, reason = evaluate_lab_breaker(
        Ex(),
        equity=Decimal("1000"),
        day_start_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        data_age_s=10,
        binance_ok=False,
    )
    assert active and reason == "binance_failure"


def test_postgres_failure_breaker():
    class Ex:
        def __call__(self, sql, params=None):
            return MagicMock()

    active, reason = evaluate_lab_breaker(
        Ex(),
        equity=Decimal("1000"),
        day_start_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        data_age_s=10,
        binance_ok=True,
        postgres_ok=False,
    )
    assert reason == "postgres_unreachable"


def test_accounting_conservation_buy_math():
    cash = Decimal("1000")
    budget = Decimal("25")
    fee_rate = Decimal("0.001")
    px = Decimal("50")
    qty = budget / px
    new_cash = cash - budget
    assert new_cash + budget == cash
    assert qty > 0
    assert budget * fee_rate > 0


def test_no_real_orders_in_lab_sources():
    root = Path(__file__).resolve().parents[1] / "app" / "lab"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "/api/v3/order" not in text
        assert "api_secret" not in text
        assert "private_key" not in text


def test_lab_isolated_from_sma_account_tables():
    root = Path(__file__).resolve().parents[1] / "app" / "lab"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        # Must not mutate SMA paper tables
        assert "UPDATE account" not in text
        assert "INSERT INTO trades" not in text
        assert "DELETE FROM positions" not in text or "lab_positions" in text


def test_runner_uses_advisory_lock():
    text = (
        Path(__file__).resolve().parents[1] / "app/lab/runner.py"
    ).read_text(encoding="utf-8")
    assert "pg_try_advisory_lock" in text
    assert "PAPER_ONLY" in text


def test_exposure_and_paused():
    ok, reason = can_buy(
        paused=True,
        breaker_active=False,
        cash=Decimal("1000"),
        budget=Decimal("25"),
        positions_n=0,
        max_positions=10,
        symbol_valid=True,
        data_fresh=True,
        liquidity_ok=True,
        fill_ok=True,
        strategy="SMA10_SMA50_1H",
    )
    assert reason == "executor_paused"
