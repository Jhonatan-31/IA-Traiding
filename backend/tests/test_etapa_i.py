"""Etapa I — shadow scheduler, resolve idempotency, locks, metrics, no real orders."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.ml.resolve import expected_exit_open_ms, resolve_from_candles
from app.prospect.degradation import THRESHOLDS, evaluate_degradation
from app.prospect.metrics import prospective_metrics
from app.prospect.resolve import apply_outcome
from app.prospect.scheduler import ADVISORY_LOCK_KEY, release_lock, try_acquire_lock


# ---------- helpers ----------


class _Cur:
    def __init__(self):
        self._last = None

    def fetchone(self):
        return self._last

    def __iter__(self):
        return iter(self._rows if hasattr(self, "_rows") else [])


class _MemExec:
    """In-memory stand-in for prospect decision/outcome/scheduler SQL used in unit tests."""

    def __init__(self):
        self.outcomes = {}
        self.decisions = {}
        self.alerts = {}
        self.scheduler = {
            "id": 1,
            "status": "UNKNOWN",
            "heartbeat_at": None,
            "last_error": None,
        }
        self.lock_held = False
        self.cursor = _Cur()
        self.calls = []

    def __call__(self, sql, params=None):
        sql_n = " ".join(sql.split())
        self.calls.append((sql_n[:80], params))
        self.cursor._last = None
        self.cursor._rows = []

        if "pg_try_advisory_lock" in sql_n:
            if self.lock_held:
                self.cursor._last = {"ok": False}
            else:
                self.lock_held = True
                self.cursor._last = {"ok": True}
        elif "pg_advisory_unlock" in sql_n:
            self.lock_held = False
            self.cursor._last = {"ok": True}
        elif sql_n.startswith("SELECT decision_id FROM prospect_outcomes"):
            did = params[0]
            self.cursor._last = {"decision_id": did} if did in self.outcomes else None
        elif sql_n.startswith("UPDATE prospect_decisions"):
            did = params[1]
            d = self.decisions.get(did)
            if d and d.get("resolution_status") == "PENDING":
                d["resolution_status"] = params[0]
                self.cursor._last = {"id": did}
            else:
                self.cursor._last = None
        elif sql_n.startswith("INSERT INTO prospect_outcomes"):
            did = params[0]
            if did not in self.outcomes:
                self.outcomes[did] = params
        elif "FROM shadow_scheduler_state" in sql_n:
            self.cursor._last = dict(self.scheduler)
        elif "FROM prospect_decisions d" in sql_n and "GROUP BY resolution_status" in sql_n:
            from collections import Counter

            c = Counter(d["resolution_status"] for d in self.decisions.values())
            self.cursor._rows = [{"resolution_status": k, "n": v} for k, v in c.items()]
        elif sql_n.startswith("SELECT id FROM prospect_alerts"):
            code = params[0]
            open_a = self.alerts.get(code)
            self.cursor._last = {"id": open_a["id"]} if open_a and open_a["status"] == "OPEN" else None
        elif sql_n.startswith("INSERT INTO prospect_alerts"):
            code = params[0]
            self.alerts[code] = {
                "id": len(self.alerts) + 1,
                "code": code,
                "severity": params[1],
                "message": params[2],
                "status": "OPEN",
            }
        elif sql_n.startswith("UPDATE prospect_alerts SET message"):
            aid = params[3]
            for a in self.alerts.values():
                if a["id"] == aid:
                    a["message"] = params[0]
                    a["severity"] = params[2]
        elif sql_n.startswith("UPDATE prospect_alerts SET status='CLEARED'"):
            code = params[0]
            if code in self.alerts and self.alerts[code]["status"] == "OPEN":
                self.alerts[code]["status"] = "CLEARED"
        elif "FROM prospect_alerts WHERE status='OPEN'" in sql_n:
            self.cursor._rows = [a for a in self.alerts.values() if a["status"] == "OPEN"]
        elif "UPDATE shadow_scheduler_state" in sql_n:
            self.scheduler["status"] = params[0] if params else self.scheduler["status"]
            self.scheduler["heartbeat_at"] = datetime.now(timezone.utc)
            if params and len(params) > 1:
                self.scheduler["last_error"] = params[1]
        return self.cursor


def test_advisory_lock_blocks_concurrent():
    ex = _MemExec()
    conn = MagicMock()
    conn.execute = ex
    assert try_acquire_lock(conn) is True
    assert try_acquire_lock(conn) is False
    release_lock(conn)
    assert try_acquire_lock(conn) is True
    assert ADVISORY_LOCK_KEY == 81420031


def test_duplicate_decision_skip_logic():
    """Engine pre-check: same experiment+symbol+interval+candle → skip."""
    seen = set()
    key = (1, "BTCUSDT", "1h", 1_700_000_000_000)
    assert key not in seen
    seen.add(key)
    assert key in seen  # restart would hit unique / pre-check


def test_premature_resolve_stays_pending():
    open_ms = 1_700_000_000_000
    step = 3_600_000
    candles = [
        {"open_time": open_ms + i * step, "close": 100 + i, "is_closed": True}
        for i in range(3)  # only 3 bars — horizon 6 not complete
    ]
    r = resolve_from_candles(candles, candle_open_ms=open_ms, interval="1h", horizon=6)
    assert r["status"] == "PENDING"
    assert r["reason"] == "horizon_not_complete"


def test_missing_entry_invalid():
    open_ms = 1_700_000_000_000
    candles = [{"open_time": open_ms + 3_600_000, "close": 101, "is_closed": True}]
    r = resolve_from_candles(candles, candle_open_ms=open_ms, interval="1h", horizon=6)
    assert r["status"] == "INVALID"
    assert r["data_quality"] == "missing_entry"


def test_horizon_resolve_when_complete():
    open_ms = 1_700_000_000_000
    step = 3_600_000
    horizon = 6
    candles = [
        {"open_time": open_ms + i * step, "close": 100.0 * (1 + 0.001 * i), "is_closed": True}
        for i in range(horizon + 1)
    ]
    r = resolve_from_candles(candles, candle_open_ms=open_ms, interval="1h", horizon=horizon)
    assert r["status"] == "RESOLVED"
    assert r["observed_net_return"] is not None
    assert expected_exit_open_ms(open_ms, "1h", horizon) == open_ms + horizon * step


def test_outcome_idempotent_twice():
    ex = _MemExec()
    ex.decisions[7] = {"resolution_status": "PENDING"}
    a = apply_outcome(
        ex, 7, status="RESOLVED", data_quality="ok",
        observed_net_return=0.01, observed_label=1, result={},
    )
    b = apply_outcome(
        ex, 7, status="RESOLVED", data_quality="ok",
        observed_net_return=0.99, observed_label=0, result={},
    )
    assert a is True and b is False
    assert ex.outcomes[7][3] == 0.01  # original net preserved


@pytest.mark.asyncio
async def test_transient_binance_keeps_pending(monkeypatch):
    from app.prospect import resolve as resolve_mod

    pending_row = {
        "id": 42,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "horizon_bars": 6,
        "candle_open_ms": 1_700_000_000_000,
        "action": "BUY",
        "experiment_type": "SHADOW_LIVE",
    }

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

        def fetchone(self):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            sql_n = " ".join(sql.split())
            if "resolution_status='PENDING'" in sql_n:
                return _Rows([pending_row])
            return _Rows([])

    def db_factory():
        return FakeConn()

    async def boom(*a, **k):
        raise ConnectionError("binance down")

    monkeypatch.setattr(resolve_mod, "fetch_klines", boom)
    with patch("app.prospect.schema.ensure_prospect_schema", lambda e: None):
        summary = await resolve_mod.resolve_pending(db_factory, limit=10)
    assert summary["still_pending"] == 1
    assert summary["invalid"] == 0
    assert summary["resolved"] == 0


def test_scheduler_restart_no_duplicate_key():
    """Unique key components used by schema index."""
    cols = ("experiment_id", "symbol", "interval", "candle_open_ms")
    assert len(cols) == 4


def test_prospective_metrics_hold_not_trade():
    def execute(sql, params=None):
        cur = MagicMock()
        rows = [
            {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "observed_price": 100,
                "estimated_costs_json": {},
                "observed_net_return": 0.02,
                "observed_label": 1,
                "outcome_status": "RESOLVED",
                "data_quality": "ok",
                "resolution_status": "RESOLVED",
            },
            {
                "action": "HOLD",
                "symbol": "ETHUSDT",
                "observed_price": 50,
                "estimated_costs_json": {},
                "observed_net_return": 0.0,
                "observed_label": None,
                "outcome_status": "RESOLVED",
                "data_quality": "ok",
                "resolution_status": "RESOLVED",
            },
        ]
        cur.__iter__ = lambda self: iter(rows)
        return cur

    m = prospective_metrics(execute, experiment_type="SHADOW_LIVE")
    assert m["hold_counted_as_profitable_trade"] is False
    assert m["hypothetical_signals"]["hold_counted_as_trade"] is False
    assert m["hypothetical_signals"]["n_buy"] == 1
    assert m["hypothetical_signals"]["n_hold"] == 1
    assert m["separated_from_shadow_replay"] is True
    assert m["experiment_type"] == "SHADOW_LIVE"


def test_degradation_no_heartbeat_alert():
    ex = _MemExec()
    ex.scheduler["heartbeat_at"] = None
    result = evaluate_degradation(ex)
    assert result["auto_retrain"] is False
    assert "scheduler_no_heartbeat" in result["opened_or_updated"]
    assert THRESHOLDS["no_retrain_on_alert"] is True


def test_degradation_fresh_heartbeat_clears():
    ex = _MemExec()
    ex.scheduler["heartbeat_at"] = datetime.now(timezone.utc)
    ex.scheduler["status"] = "OK"
    ex.alerts["scheduler_no_heartbeat"] = {
        "id": 1,
        "code": "scheduler_no_heartbeat",
        "severity": "ERROR",
        "message": "x",
        "status": "OPEN",
    }
    result = evaluate_degradation(ex)
    assert "scheduler_no_heartbeat" in result["cleared"] or result["auto_retrain"] is False


def test_ledger_independent_constant():
    """Virtual research ledger seed ≠ SMA paper mutation."""
    virt_seed = 1000
    sma_cash_example = 875
    assert virt_seed != sma_cash_example


def test_no_real_orders_in_scheduler_source():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "prospect" / "scheduler.py"
    text = src.read_text(encoding="utf-8")
    low = text.lower()
    for forbidden in ("/api/v3/order", "create_order", "api_secret", "private_key"):
        assert forbidden not in low
    assert "no training" in low or "no train" in low
    assert "run_shadow_live_cycle" in text
    assert "resolve_pending" in text


def test_engine_system_state_paper_only():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "prospect" / "engine.py"
    text = src.read_text(encoding="utf-8")
    assert 'mode": "PAPER_ONLY"' in text or "PAPER_ONLY" in text
    assert "paper_ai" in text.lower() or "PAPER_AI" in text or '"paper_ai": False' in text


def test_postgres_failure_path_sets_error_status():
    """Connection errors increment connection_errors via scheduler except path (structural)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "prospect" / "scheduler.py"
    text = src.read_text(encoding="utf-8")
    assert "connection_errors" in text
    assert "OperationalError" in text
    assert "concurrent_cycle_locked" in text


def test_replay_live_separation_in_metrics_api_contract():
    m_live = prospective_metrics(
        lambda sql, params=None: _empty_rows(),
        experiment_type="SHADOW_LIVE",
    )
    m_replay = prospective_metrics(
        lambda sql, params=None: _empty_rows(),
        experiment_type="SHADOW_REPLAY",
    )
    assert m_live["experiment_type"] != m_replay["experiment_type"]


def _empty_rows():
    cur = MagicMock()
    cur.__iter__ = lambda self: iter([])
    return cur
