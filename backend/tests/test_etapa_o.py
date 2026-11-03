"""Etapa O — exits, protective sells, fees/slip, inventory, PAPER_ONLY."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.lab.exits import EXIT_PRIORITY, evaluate_exit
from app.lab.ledger import apply_sell
from app.lab.positions_audit import enrich_position
from app.lab.risk import PROTECTIVE_SELL_POLICY, can_buy, can_protective_sell


def _pos(**kw):
    base = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
        "qty": Decimal("1"),
        "cost": Decimal("100"),
        "symbol": "BTCUSDT",
        "opened_candle_ms": 1_000_000,
    }
    base.update(kw)
    return base


def test_stop_loss_isolated():
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("97"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side=None,
        bars_held=1,
    )
    assert d["reason"] == "stop_loss"
    assert d["stop_trigger_price"] == pytest.approx(98.0)
    assert d["stop_trigger_price"] != 97.0


def test_take_profit_isolated():
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("105"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side=None,
        bars_held=1,
    )
    assert d["reason"] == "take_profit"
    assert d["stop_trigger_price"] == pytest.approx(104.0)


def test_time_stop_isolated():
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("100"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side=None,
        bars_held=48,
    )
    assert d["reason"] == "max_hold_bars"


def test_sma_sell_strategy_exit():
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("100"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=2,
    )
    assert d["reason"] == "strategy_exit"
    assert d["allow_execution"] is True


def test_exit_priority_sl_over_tp_and_strategy():
    # Price through SL; strategy also SELL; bars over limit — SL wins
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("90"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=100,
    )
    assert d["reason"] == "stop_loss"
    assert d["priority"] == EXIT_PRIORITY.index("stop_loss")


def test_stale_blocks_all_exits():
    d = evaluate_exit(
        _pos(),
        mark_price=Decimal("90"),
        mark_age_s=99999,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=100,
    )
    assert d["action"] == "HOLD"
    assert d["allow_execution"] is False


def test_breaker_blocks_buy_allows_protective_sell_policy():
    assert PROTECTIVE_SELL_POLICY["allowed_when_breaker_active"] is True
    ok, why = can_buy(
        paused=False,
        breaker_active=True,
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
    assert not ok and why == "circuit_breaker"
    ok_s, why_s = can_protective_sell(
        paused=False,
        breaker_active=True,
        data_fresh=True,
        fill_ok=True,
        has_position=True,
        exit_reason="stop_loss",
    )
    assert ok_s and why_s == "ok"


def test_pause_blocks_protective_sell():
    ok, why = can_protective_sell(
        paused=True,
        breaker_active=False,
        data_fresh=True,
        fill_ok=True,
        has_position=True,
        exit_reason="stop_loss",
    )
    assert not ok and why == "executor_paused"


def test_no_inventory_blocks_sell():
    ok, why = can_protective_sell(
        paused=False,
        breaker_active=False,
        data_fresh=True,
        fill_ok=True,
        has_position=False,
        exit_reason="strategy_exit",
    )
    assert not ok and why == "no_position"


def test_apply_sell_no_position_and_idempotent_second():
    calls = {"cash": Decimal("900"), "pos": True, "deleted": False}

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM lab_positions" in sql_n and "SELECT" in sql_n:
                if calls["pos"] and not calls["deleted"]:
                    cur.fetchone = lambda: {
                        "qty": Decimal("0.01"),
                        "cost": Decimal("25"),
                    }
                else:
                    cur.fetchone = lambda: None
            elif "FROM lab_accounts" in sql_n:
                cur.fetchone = lambda: {"cash": calls["cash"]}
            elif "UPDATE lab_accounts" in sql_n:
                calls["cash"] = params[0]
            elif "DELETE FROM lab_positions" in sql_n:
                calls["deleted"] = True
            elif "INSERT INTO lab_trades" in sql_n:
                pass
            return cur

    ex = Ex()
    r1 = apply_sell(
        ex,
        order_uid="00000000-0000-0000-0000-000000000001",
        symbol="BTCUSDT",
        fill_price=Decimal("100"),
        candle_ms=1,
        strategy="SMA10_SMA50_1H",
        reason="stop_loss",
        stop_triggered=True,
        stop_trigger_price=Decimal("98"),
    )
    assert r1["status"] == "FILLED"
    assert r1["execution_price"] == 100.0
    assert r1["stop_trigger_price"] == 98.0
    assert r1["fee"] > 0
    # restart / duplicate sell attempt
    r2 = apply_sell(
        ex,
        order_uid="00000000-0000-0000-0000-000000000002",
        symbol="BTCUSDT",
        fill_price=Decimal("100"),
        candle_ms=1,
        strategy="SMA10_SMA50_1H",
        reason="stop_loss",
    )
    assert r2["status"] == "REJECTED"
    assert r2["reason"] == "no_position"


def test_fee_and_slip_on_sell():
    calls = {"cash": Decimal("900")}

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM lab_positions" in sql_n:
                cur.fetchone = lambda: {"qty": Decimal("1"), "cost": Decimal("100")}
            elif "FROM lab_accounts" in sql_n:
                cur.fetchone = lambda: {"cash": calls["cash"]}
            elif "UPDATE lab_accounts" in sql_n:
                calls["cash"] = params[0]
            return cur

    r = apply_sell(
        Ex(),
        order_uid="00000000-0000-0000-0000-000000000099",
        symbol="ETHUSDT",
        fill_price=Decimal("100"),
        candle_ms=2,
        strategy="SMA10_SMA50_1H",
        reason="take_profit",
    )
    assert r["status"] == "FILLED"
    # fee = proceeds * 0.001 = 0.1; net = 99.9; realized = 99.9 - 100 = -0.1
    assert r["fee"] == pytest.approx(0.1)
    assert r["realized_pnl"] == pytest.approx(-0.1)
    assert calls["cash"] == pytest.approx(Decimal("999.9"))


def test_enrich_distinguishes_mark_vs_exec():
    e = enrich_position(
        {
            "symbol": "BTCUSDT",
            "qty": 0.01,
            "cost": 25,
            "entry_price": 100,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04,
            "max_hold_bars": 48,
            "opened_candle_ms": 0,
        },
        {"ok": True, "price": 110.0, "source": "binance_public_ticker", "at": "t"},
    )
    assert e["mark_price_observed"] == 110.0
    assert e["estimated_sell_execution_price"] < 110.0
    assert e["stop_loss_price"] == pytest.approx(98.0)
    assert e["take_profit_price"] == pytest.approx(104.0)


def test_paper_only_no_real_orders_in_lab():
    root = Path(__file__).resolve().parents[1] / "app"
    for rel in ("lab/executor.py", "lab_api.py", "lab/ledger.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "api/v3/order" not in text
        assert "PAPER" in text or "paper" in text or "lab_" in text


def test_sell_skip_no_position_in_signals_source():
    text = (
        Path(__file__).resolve().parents[1] / "app/lab/signals.py"
    ).read_text(encoding="utf-8")
    assert "sell_skipped_no_position" in text


def test_accounting_three_ledgers_untouched():
    for rel in ("ledger.py", "executor.py", "signals.py"):
        text = (
            Path(__file__).resolve().parents[1] / "app/lab" / rel
        ).read_text(encoding="utf-8")
        assert "UPDATE account SET" not in text
        assert "UPDATE virt_accounts" not in text
