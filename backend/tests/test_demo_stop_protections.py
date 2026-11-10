"""Pausa segura A: BUY bloqueado en STOPPED; salidas protectoras siguen en el motor."""
from __future__ import annotations

import inspect

from app.demo import engine as demo_engine
from app.demo.control import stop_bot


def test_engine_doc_and_allow_entries_gate():
    src = inspect.getsource(demo_engine.run_cycle)
    assert "allow_entries = bool(st and st[\"status\"] == \"RUNNING\")" in src
    assert "Protective / signal exits — always, even when STOPPED" in src
    assert "bot_stopped_entries_blocked" in src


def test_try_buy_blocked_when_stopped():
    calls = {"status": "STOPPED"}

    class Cur:
        def fetchone(self):
            return self._row

    def execute(sql, params=None):
        cur = Cur()
        cur._row = None
        if "SELECT status FROM demo_state" in sql:
            cur._row = {"status": calls["status"]}
        return cur

    import asyncio

    res = asyncio.run(
        demo_engine._try_buy(
            client=None,
            execute=execute,
            symbol="BTCUSDT",
            mark=70000.0,
            candle_ms=1,
            decision_id=1,
            cash=1000.0,
            invested=0.0,
            assumptions=None,
            corr="00000000-0000-0000-0000-000000000001",
        )
    )
    assert res["ok"] is False
    assert res["reason"] == "bot_stopped_entries_blocked"


def test_stop_bot_persists_and_flags_protections(monkeypatch):
    state = {"status": "RUNNING"}
    events = []

    class Row(dict):
        pass

    class Cur:
        def __init__(self):
            self._one = None
            self._all = []

        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._all

    def execute(sql, params=None):
        cur = Cur()
        s = " ".join(sql.split())
        if s.startswith("UPDATE demo_orders SET status='CANCELLED'"):
            cur._all = []
        elif s.startswith("UPDATE demo_state SET status='STOPPED'"):
            if state["status"] == "RUNNING":
                state["status"] = "STOPPED"
                cur._one = Row(status="STOPPED", id=1)
        elif "SELECT * FROM demo_state" in s:
            cur._one = Row(status=state["status"], id=1)
        elif s.startswith("INSERT INTO demo_events"):
            events.append((params or (None, None))[1])
        return cur

    monkeypatch.setattr("app.demo.control.ensure_demo_schema", lambda execute: None)
    r = stop_bot(execute, actor="test")
    assert r["changed"] is True
    assert r["status"] == "STOPPED"
    assert state["status"] == "STOPPED"
    assert any("protective_exits_remain" in str(e) for e in events)


def test_sell_guards_present_in_source():
    src = inspect.getsource(demo_engine)
    # Idempotency / inventory guards for sells
    assert "duplicate_candle" in src or "candle_1m_ms" in src
    assert "demo_positions" in src
    assert "stop_loss_1pct" in src and "take_profit_2pct" in src
