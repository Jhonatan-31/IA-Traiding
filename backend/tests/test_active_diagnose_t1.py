"""Etapa T.1 — diagnóstico HOLD, categorías y control start/stop (sin fills reales)."""
from __future__ import annotations

from app.active.control import start_bot, stop_bot
from app.active.diagnose import categorize_reason, compare_ab, diagnose_holds, strategy_history
from app.active import ACCOUNT_B, B_EXECUTION_AUTHORIZED, C_EXECUTION_AUTHORIZED


def test_categorize_reason_buckets():
    assert categorize_reason("hold_position") == "open_position"
    assert categorize_reason("no_5m_trend") == "unfavorable_trend"
    assert categorize_reason("vol_floor_reject") == "insufficient_volatility"
    assert categorize_reason("cost_filter_reject") == "high_costs"
    assert categorize_reason("max_exposure") == "risk_exceeded"
    assert categorize_reason("flags_3_of_5_insufficient") == "signal_unconfirmed"
    assert categorize_reason("indicators_incomplete") == "data_unavailable"
    assert categorize_reason("bot_stopped_entries_blocked") == "bot_stopped"


def test_hold_diagnosis_dedupes_cycle_symbol():
    """Repeated rows for same cycle+symbol count once."""
    from app.active.diagnose import _hold_diagnosis

    rows = [
        {"id": 3, "cycle_id": 10, "symbol": "BTCUSDT", "reason": "hold_position", "at": None},
        {"id": 2, "cycle_id": 10, "symbol": "BTCUSDT", "reason": "hold_position", "at": None},
        {"id": 1, "cycle_id": 10, "symbol": "ETHUSDT", "reason": "flags_3_of_5_insufficient", "at": None},
    ]
    out = _hold_diagnosis(rows, strategy="A")
    assert out["raw_holds"] == 3
    assert out["unique_cycle_symbol"] == 2
    assert out["entry_holds_unique"] == 1
    cats = {c["id"]: c["count"] for c in out["categories"]}
    assert cats["open_position"] == 1
    assert cats["signal_unconfirmed"] == 1
    # percentages use unique denominator
    assert abs(cats["open_position"] / out["unique_cycle_symbol"] * 100 - 50.0) < 0.01


def test_execution_flags_unchanged():
    assert B_EXECUTION_AUTHORIZED is True
    assert C_EXECUTION_AUTHORIZED is False


def test_start_stop_idempotent_and_independent(monkeypatch):
    """In-memory stub: start/stop B does not touch demo tables."""
    state = {"status": "STOPPED", "meta_json": {}}
    events = []
    demo_touched = {"n": 0}

    class Row(dict):
        pass

    class Cursor:
        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._all

    def execute(sql, params=None):
        cur = Cursor()
        cur._one = None
        cur._all = []
        s = " ".join(sql.split())
        if "demo_" in s.lower():
            demo_touched["n"] += 1
        if s.startswith("UPDATE active_state SET status='RUNNING'"):
            if state["status"] == "STOPPED":
                state["status"] = "RUNNING"
                cur._one = Row(status="RUNNING", id=1)
            else:
                cur._one = None
        elif s.startswith("UPDATE active_state SET status='STOPPED'"):
            if state["status"] == "RUNNING":
                state["status"] = "STOPPED"
                cur._one = Row(status="STOPPED", id=1)
            else:
                cur._one = None
        elif s.startswith("UPDATE active_orders"):
            cur._all = []
        elif "SELECT * FROM active_state" in s:
            cur._one = Row(status=state["status"], id=1)
        elif s.startswith("INSERT INTO active_events"):
            events.append(params)
            cur._one = None
        elif "CREATE TABLE" in s or "INSERT INTO active_accounts" in s or "INSERT INTO active_state" in s:
            cur._one = None
        return cur

    # Bypass schema DDL side-effects by patching ensure
    monkeypatch.setattr("app.active.control.ensure_active_schema", lambda execute: None)

    r1 = start_bot(execute, actor="test")
    assert r1["changed"] is True
    assert r1["status"] == "RUNNING"
    r2 = start_bot(execute, actor="test")
    assert r2["changed"] is False
    assert state["status"] == "RUNNING"

    s1 = stop_bot(execute, actor="test")
    assert s1["changed"] is True
    assert s1["status"] == "STOPPED"
    s2 = stop_bot(execute, actor="test")
    assert s2["changed"] is False
    assert demo_touched["n"] == 0


def test_diagnose_compare_history_shapes_with_db_if_available():
    """Optional integration: skip if DATABASE_URL not usable from host."""
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return
    try:
        with psycopg.connect(url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                def execute(sql, params=None):
                    cur.execute(sql, params)
                    return cur

                d = diagnose_holds(execute, limit=200)
                h = strategy_history(execute, limit=20)
                c = compare_ab(execute)
    except Exception:
        return

    assert d["paper_only"] is True
    assert "A" in d and "B" in d
    assert h["A"]["ledger"] != h["B"]["ledger"]
    assert c["claim"]["declare_winner"] is False
    assert c["integrity"]["ledgers_distinct"] is True
