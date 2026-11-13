"""Etapa AD — integridad transaccional, auth salidas B, fees, dedupe, gaps."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ops.continuity import classify_gap, heartbeat_gap_seconds, reconcile_after_gap
from app.prospect.execution import ExecutionAssumptions, estimate_fill_price
from app.market_stream.aggregator import CandleAggregator, _MAX_SEEN_IDS, candle_open_ms


# ---------------------------------------------------------------------------
# AD-FIN-01 fee model
# ---------------------------------------------------------------------------


def test_ad_fee_all_in_buy_no_double_debit():
    fill = estimate_fill_price(
        side="BUY", mid_or_ref=100.0, assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.0, spread_bps=0.0)
    )
    assert fill["ok"]
    px = float(fill["price"])
    qty = 10.0
    # Correct cash model: debit qty * all-in px (fee already inside px)
    total_correct = qty * px
    fee_report = float(fill["fee_component"]) * qty
    # Bug model would be qty*px + qty*px*fee_rate ≈ double fee effect
    total_buggy = qty * px + qty * px * 0.001
    assert total_correct < total_buggy
    assert abs(px - 100.0 * 1.001) < 1e-9
    assert fee_report > 0
    assert abs(total_correct - (qty * 100.0 + fee_report)) < 1e-6


def test_ad_fee_all_in_sell_no_double_debit():
    fill = estimate_fill_price(
        side="SELL", mid_or_ref=100.0, assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.0, spread_bps=0.0)
    )
    px = float(fill["price"])
    qty = 10.0
    net_correct = qty * px
    net_buggy = qty * px - qty * px * 0.001
    assert net_correct > net_buggy
    assert abs(px - 100.0 * 0.999) < 1e-9


# ---------------------------------------------------------------------------
# AD-DATA-01 eviction LRU
# ---------------------------------------------------------------------------


def test_ad_trade_id_lru_eviction_keeps_recent():
    agg = CandleAggregator()
    t0 = candle_open_ms(1_700_000_000_000, "1m")
    # Force small max via temporary patch
    import app.market_stream.aggregator as mod

    old = mod._MAX_SEEN_IDS
    try:
        mod._MAX_SEEN_IDS = 8
        for i in range(1, 12):
            c = agg.apply_trade(
                {
                    "symbol": "BTCUSDT",
                    "price": 100 + i,
                    "qty": 0.01,
                    "trade_id": i,
                    "event_time_ms": t0 + i,
                    "trade_time_ms": t0 + i,
                },
                "1m",
            )
            assert c is not None
        cur = agg.get("BTCUSDT", "1m")
        assert cur is not None
        assert len(cur.seen_ids) <= 8
        # oldest should be gone; recent present
        assert 1 not in cur.seen_ids
        assert 11 in cur.seen_ids
        # replaying a recently seen id must still dedupe
        assert (
            agg.apply_trade(
                {
                    "symbol": "BTCUSDT",
                    "price": 200,
                    "qty": 1,
                    "trade_id": 11,
                    "event_time_ms": t0 + 50,
                    "trade_time_ms": t0 + 50,
                },
                "1m",
            )
            is None
        )
    finally:
        mod._MAX_SEEN_IDS = old


# ---------------------------------------------------------------------------
# AD-OPS-01 continuity
# ---------------------------------------------------------------------------


def test_ad_heartbeat_gap_critical_and_no_false_coverage():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(seconds=900)
    gap = heartbeat_gap_seconds(old, now=now)
    assert gap == 900.0
    c = classify_gap(gap, warn_s=180, crit_s=600)
    assert c["status"] == "CRITICAL"
    assert c["host_suspend_suspected"] is True
    assert c["protective_coverage_claimed"] is False
    assert c["safe_to_trade_entries"] is False


def test_ad_reconcile_after_gap_recommends_actions():
    r = reconcile_after_gap(gap_s=700, price_age_s=200, open_positions=2)
    assert r["status"] == "CRITICAL"
    assert "evaluar_protecciones_con_precio_fresco" in r["recommended_actions"]
    assert "no_afirmar_cobertura_durante_hueco" in r["recommended_actions"]


# ---------------------------------------------------------------------------
# AD-P0-02 authorization separates entries vs protective path
# ---------------------------------------------------------------------------


def test_ad_b_unauthorized_does_not_early_return_before_exits():
    """Source-level: run_cycle must not return solely on B_EXECUTION_AUTHORIZED=False."""
    import inspect
    from app.active import engine as eng

    src = inspect.getsource(eng.run_cycle)
    assert "protective_exits_still_evaluated" in src or "entries_authorized" in src
    assert "return summary" not in src.split("entries_authorized")[0] or "b_entries_not_authorized" in src
    # Early return on unauthorized must be gone
    assert 'rejects"].append({"reason": "b_execution_not_authorized"})' not in src
    assert "b_entries_not_authorized" in src


def test_ad_try_buy_blocked_when_unauthorized():
    from app.active import engine as eng

    async def _run():
        with patch.object(eng, "B_EXECUTION_AUTHORIZED", False):
            execute = MagicMock()
            res = await eng._try_buy(
                client=MagicMock(),
                execute=execute,
                symbol="BTCUSDT",
                mark=100.0,
                candle_ms=1,
                decision_id=1,
                cash=Decimal("1000"),
                invested=Decimal("0"),
                assumptions=ExecutionAssumptions(),
                corr=uuid.uuid4(),
            )
            assert res["ok"] is False
            assert res["reason"] == "b_entries_not_authorized"
            execute.assert_not_called()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# AD-P0-01 atomic buy SAVEPOINT behavior (fixture, no operational ledger)
# ---------------------------------------------------------------------------


class _FakeConn:
    """Minimal SAVEPOINT-aware fake for atomic buy regression."""

    def __init__(self, cash: Decimal = Decimal("1000")):
        self.cash = cash
        self.positions: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.trades: list[dict] = []
        self._sp: list[dict] | None = None
        self.fail_on: str | None = None
        self._oid = 0

    def execute(self, sql: str, params=None):
        s = " ".join(sql.split()).lower()
        params = params or ()
        if s.startswith("savepoint"):
            self._sp = {
                "cash": self.cash,
                "positions": dict(self.positions),
                "orders": list(self.orders),
                "trades": list(self.trades),
                "oid": self._oid,
            }
            return self
        if s.startswith("release savepoint"):
            self._sp = None
            return self
        if s.startswith("rollback to savepoint"):
            assert self._sp is not None
            self.cash = self._sp["cash"]
            self.positions = dict(self._sp["positions"])
            self.orders = list(self._sp["orders"])
            self.trades = list(self._sp["trades"])
            self._oid = self._sp["oid"]
            self._sp = None
            return self
        if "for update" in s and "cash" in s and "select" in s:
            return _Res({"cash": self.cash})
        if s.startswith("select 1 from demo_positions") or s.startswith(
            "select 1 from active_positions"
        ):
            sym = params[1]
            return _Res({"x": 1} if sym in self.positions else None)
        if "from demo_positions" in s or "from active_positions" in s:
            if "select 1" in s:
                sym = params[1]
                return _Res({"x": 1} if sym in self.positions else None)
        if "insert into demo_orders" in s or "insert into active_orders" in s:
            if self.fail_on == "order":
                raise RuntimeError("order_boom")
            self._oid += 1
            row = {"id": self._oid}
            self.orders.append(row)
            return _Res(row)
        if "update demo_accounts" in s or "update active_accounts" in s:
            if self.fail_on == "cash":
                raise RuntimeError("cash_boom")
            amt = Decimal(str(params[0]))
            if self.cash < amt:
                return _Res(None)
            self.cash -= amt
            return _Res({"cash": self.cash})
        if "insert into demo_positions" in s or "insert into active_positions" in s:
            if self.fail_on == "position":
                raise RuntimeError("position_boom")
            sym = params[1]
            if sym in self.positions:
                raise RuntimeError("unique_violation")
            self.positions[sym] = {
                "symbol": sym,
                "qty": params[2],
                "cost": params[3],
                "entry_price": params[4],
            }
            return self
        if "insert into demo_trades" in s or "insert into active_trades" in s:
            if self.fail_on == "trade":
                raise RuntimeError("trade_boom")
            self.trades.append({"id": len(self.trades) + 1})
            return self
        if "select status from" in s:
            return _Res({"status": "RUNNING"})
        if "from demo_orders" in s or "from active_orders" in s:
            return _Res(None)
        if "from demo_positions where account_id" in s and "select 1" not in s:
            return _Res(None)
        if "select cash from" in s:
            return _Res({"cash": self.cash})
        return self

    def fetchone(self):
        return None


class _Res:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_ad_atomic_buy_rolls_back_cash_on_position_failure():
    from app.demo import engine as demo_eng

    conn = _FakeConn(Decimal("1000"))
    conn.fail_on = "position"

    async def _run():
        with patch.object(
            demo_eng,
            "_load_filters",
            new=AsyncMock(
                return_value={
                    "status": "TRADING",
                    "filters": {
                        "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
                        "MIN_NOTIONAL": {"minNotional": "5"},
                    },
                }
            ),
        ):
            res = await demo_eng._try_buy(
                client=MagicMock(),
                execute=conn.execute,
                symbol="BTCUSDT",
                mark=100.0,
                candle_ms=1_700_000_000_000,
                decision_id=1,
                cash=Decimal("1000"),
                invested=Decimal("0"),
                assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.0, spread_bps=0.0),
                corr=uuid.uuid4(),
            )
            assert res["ok"] is False
            assert "buy_atomic_rollback" in res["reason"]
            assert conn.cash == Decimal("1000")
            assert conn.positions == {}
            assert conn.orders == []
            assert conn.trades == []

    asyncio.run(_run())


def test_ad_atomic_buy_success_debits_all_in_once():
    from app.demo import engine as demo_eng

    conn = _FakeConn(Decimal("1000"))

    async def _run():
        with patch.object(
            demo_eng,
            "_load_filters",
            new=AsyncMock(
                return_value={
                    "status": "TRADING",
                    "filters": {
                        "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
                        "MIN_NOTIONAL": {"minNotional": "5"},
                    },
                }
            ),
        ):
            res = await demo_eng._try_buy(
                client=MagicMock(),
                execute=conn.execute,
                symbol="ETHUSDT",
                mark=100.0,
                candle_ms=1_700_000_000_000,
                decision_id=2,
                cash=Decimal("1000"),
                invested=Decimal("0"),
                assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.0, spread_bps=0.0),
                corr=uuid.uuid4(),
            )
            assert res["ok"] is True
            assert "ETHUSDT" in conn.positions
            assert len(conn.trades) == 1
            # cash dropped by qty*px only (all-in), not qty*px*(1+fee) again
            assert conn.cash < Decimal("1000")
            assert abs(float(res["cash_debited"]) - float(res["qty"]) * float(res["price"])) < 1e-9

    asyncio.run(_run())


def test_ad_express_control_requires_token_marker():
    import inspect
    from app.express import api as express_api

    src = inspect.getsource(express_api.express_control)
    assert "require_lab_token" in inspect.getsource(express_api)
    assert "express_ended_mutations_disabled" in src


def test_ad_max_seen_constant_documented():
    assert _MAX_SEEN_IDS == 4096
