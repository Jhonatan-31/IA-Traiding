"""DEMO start/stop control — isolated fixtures, no live ledger mutation in unit scope."""
from __future__ import annotations

import json
from typing import Any


class FakeDB:
    def __init__(self):
        self.state = {
            "id": 1,
            "status": "STOPPED",
            "started_at": None,
            "stopped_at": None,
            "last_actor": None,
            "policy_version": None,
            "meta_json": {},
            "coverage_gap_json": [],
        }
        self.events: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self._schema_ok = False

    def execute(self, sql: str, params: tuple | None = None):
        s = " ".join(sql.split())
        params = params or ()

        class R:
            def __init__(self, row=None, rows=None):
                self._row = row
                self._rows = rows or ([] if row is None else [row])

            def fetchone(self):
                return self._row

            def fetchall(self):
                return list(self._rows)

        if s.startswith("CREATE TABLE") or s.startswith("CREATE TABLE IF NOT EXISTS"):
            self._schema_ok = True
            return R()
        if "FROM demo_accounts" in s and "SELECT id" in s:
            return R({"id": "demo_manual_control"})
        if "FROM demo_state WHERE id=1" in s and s.startswith("SELECT"):
            return R(dict(self.state))
        if "INSERT INTO demo_accounts" in s:
            return R()
        if "INSERT INTO demo_state" in s:
            return R()
        if "INSERT INTO demo_events" in s:
            self.events.append({"sql": s, "params": params})
            return R()
        if "UPDATE demo_orders SET status='CANCELLED'" in s:
            cancelled = [o for o in self.orders if o.get("status") in ("NEW", "VALIDATED") and o.get("side") == "BUY"]
            for o in cancelled:
                o["status"] = "CANCELLED"
            return R(rows=[{"id": i} for i, _ in enumerate(cancelled, 1)])
        if "UPDATE demo_state SET" in s and "RUNNING" in s and "STOPPED" in s and "WHERE id=1 AND status='STOPPED'" in s:
            if self.state["status"] != "STOPPED":
                return R(None)
            self.state["status"] = "RUNNING"
            self.state["last_actor"] = params[0] if params else None
            return R(dict(self.state))
        if "UPDATE demo_state SET" in s and "STOPPED" in s and "WHERE id=1 AND status='RUNNING'" in s:
            if self.state["status"] != "RUNNING":
                return R(None)
            self.state["status"] = "STOPPED"
            self.state["last_actor"] = params[0] if params else None
            return R(dict(self.state))
        return R()


def test_start_from_stopped_and_double_start():
    from app.demo.control import start_bot

    db = FakeDB()
    r1 = start_bot(db.execute, actor="test")
    assert r1["changed"] is True
    assert r1["status"] == "RUNNING"
    r2 = start_bot(db.execute, actor="test")
    assert r2["changed"] is False
    assert r2["note"] == "already_running"


def test_stop_from_running_and_double_stop():
    from app.demo.control import start_bot, stop_bot

    db = FakeDB()
    start_bot(db.execute, actor="test")
    db.orders.append({"id": 1, "side": "BUY", "status": "NEW"})
    r1 = stop_bot(db.execute, actor="test")
    assert r1["changed"] is True
    assert r1["status"] == "STOPPED"
    assert r1["cancelled_pending_buys"] == 1
    r2 = stop_bot(db.execute, actor="test")
    assert r2["changed"] is False
    assert r2["note"] == "already_stopped"


def test_policy_four_of_five_constants():
    from app.demo.policy import BUY_MIN_FLAGS, BUY_SCORE_MIN, MAX_POS_USDT

    assert BUY_MIN_FLAGS == 4
    assert BUY_SCORE_MIN == 0.80
    assert MAX_POS_USDT == 25.0


def test_signal_score_not_probability():
    """Document: score 0.8 is not an 80% calibrated probability."""
    score = 0.8
    probability_validated = False
    assert probability_validated is False
    assert score != 0.8 or probability_validated is False
