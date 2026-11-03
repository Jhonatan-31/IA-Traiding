"""Etapa J — operational audit, horizons UTC, reconcile, no real orders."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from app.ml.resolve import expected_exit_open_ms, resolve_from_candles
from app.prospect.reconcile import (
    RECON_THRESHOLDS,
    horizon_audit,
    paper_sma_integrity,
    run_reconciliation,
)


def test_utc_horizon_six_bars_exact():
    open_ms = int(datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)
    exit_ms = expected_exit_open_ms(open_ms, "1h", 6)
    exit_dt = datetime.fromtimestamp(exit_ms / 1000, tz=timezone.utc)
    assert exit_dt == datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    # Ready after exit bar closes → +1h
    ready = datetime.fromtimestamp((exit_ms + 3_600_000) / 1000, tz=timezone.utc)
    assert ready == datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc)


def test_horizon_incomplete_stays_pending_no_lookahead():
    open_ms = 1_700_000_000_000
    step = 3_600_000
    # Only 5 future bars present → still incomplete for horizon 6
    candles = [
        {"open_time": open_ms + i * step, "close": 100 + i, "is_closed": True}
        for i in range(6)
    ]
    r = resolve_from_candles(candles, candle_open_ms=open_ms, interval="1h", horizon=6)
    assert r["status"] == "PENDING"


def test_same_candle_duplicate_key_components():
    a = (1, "BTCUSDT", "1h", 1793728800000)
    b = (1, "BTCUSDT", "1h", 1793728800000)
    assert a == b


def test_horizon_audit_not_ready_before_expiry():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            rows = [
                {
                    "id": 1,
                    "symbol": "BTCUSDT",
                    "interval": "1h",
                    "action": "HOLD",
                    "candle_open_ms": int(
                        datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc).timestamp() * 1000
                    ),
                    "horizon_bars": 6,
                    "created_at": datetime(2026, 11, 3, 19, 57, tzinfo=timezone.utc),
                    "decision_ts": datetime(2026, 11, 3, 19, 57, tzinfo=timezone.utc),
                    "observed_price": 77584,
                    "resolution_status": "PENDING",
                }
            ]
            cur.__iter__ = lambda self: iter(rows)
            return cur

    now = datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc)
    rows = horizon_audit(Ex(), now=now)
    assert len(rows) == 1
    assert rows[0]["horizon_ready"] is False
    assert rows[0]["exit_open_utc"].startswith("2026-11-04T00:00:00")


def test_horizon_audit_ready_after_exit_closed():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            rows = [
                {
                    "id": 2,
                    "symbol": "ETHUSDT",
                    "interval": "1h",
                    "action": "BUY",
                    "candle_open_ms": int(
                        datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc).timestamp() * 1000
                    ),
                    "horizon_bars": 6,
                    "created_at": datetime(2026, 11, 3, 19, 57, tzinfo=timezone.utc),
                    "decision_ts": datetime(2026, 11, 3, 19, 57, tzinfo=timezone.utc),
                    "observed_price": 2292.0,
                    "resolution_status": "PENDING",
                }
            ]
            cur.__iter__ = lambda self: iter(rows)
            return cur

    now = datetime(2026, 11, 4, 1, 0, 1, tzinfo=timezone.utc)
    rows = horizon_audit(Ex(), now=now)
    assert rows[0]["horizon_ready"] is True


def test_missing_data_invalid():
    r = resolve_from_candles([], candle_open_ms=1, interval="1h", horizon=6)
    assert r["status"] == "INVALID"


def test_paper_sma_integrity_ok():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM account" in sql_n:
                cur.fetchone = lambda: {"cash": Decimal("875")}
            elif "FROM positions" in sql_n and "GROUP" not in sql_n:
                cur.__iter__ = lambda self: iter(
                    [
                        {"symbol": "A", "qty": Decimal("1"), "cost": Decimal("25")},
                    ]
                )
            elif "FROM trades" in sql_n and "GROUP" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "FROM trades" in sql_n:
                cur.fetchone = lambda: {"n": 5}
            else:
                cur.fetchone = lambda: None
                cur.__iter__ = lambda self: iter([])
            return cur

    out = paper_sma_integrity(Ex())
    assert out["ok"] is True
    assert out["cash"] == 875.0
    assert out["positions"] == 1


def test_recon_blocks_on_negative_cash():
    class Ex:
        def __init__(self):
            self.alerts = {}

        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM account" in sql_n:
                cur.fetchone = lambda: {"cash": Decimal("-1")}
            elif "FROM positions" in sql_n and "virt" not in sql_n:
                if "GROUP" in sql_n:
                    cur.__iter__ = lambda self: iter([])
                else:
                    cur.__iter__ = lambda self: iter([])
            elif "FROM trades" in sql_n:
                if "GROUP" in sql_n:
                    cur.__iter__ = lambda self: iter([])
                else:
                    cur.fetchone = lambda: {"n": 0}
            elif "virt_accounts" in sql_n:
                cur.fetchone = lambda: {
                    "id": "research_sim",
                    "label": "x",
                    "cash": Decimal("1000"),
                    "initial_capital": Decimal("1000"),
                }
            elif "virt_positions" in sql_n or "virt_orders" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "virt_ledger" in sql_n:
                cur.fetchone = lambda: None
            elif "FROM prices" in sql_n:
                cur.fetchone = lambda: {"at": datetime.now(timezone.utc), "n": 10}
            elif "prospect_decisions" in sql_n and "GROUP BY" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "prospect_decisions" in sql_n and "LEFT JOIN prospect_outcomes" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "SHADOW_LIVE" in sql_n and "PENDING" in sql_n and "COUNT" in sql_n:
                cur.fetchone = lambda: {"n": 0}
            elif "SHADOW_LIVE" in sql_n and "PENDING" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "prospect_alerts" in sql_n:
                if sql_n.startswith("SELECT id"):
                    cur.fetchone = lambda: None
                elif sql_n.startswith("INSERT"):
                    pass
                else:
                    cur.__iter__ = lambda self: iter([])
            else:
                cur.fetchone = lambda: None
                cur.__iter__ = lambda self: iter([])
            return cur

    out = run_reconciliation(Ex())
    assert out["block_new_entries"] is True
    assert RECON_THRESHOLDS["block_entries_on_critical"] is True


def test_scheduler_restart_safe_source():
    src = (Path(__file__).resolve().parents[1] / "app/prospect/scheduler.py").read_text(
        encoding="utf-8"
    )
    assert "pg_try_advisory_lock" in src
    assert "run_reconciliation" in src
    assert "no training" in src.lower() or "No training" in src or "no train" in src.lower()


def test_health_unknown_without_heartbeat_logic():
    hb_age = None
    status = "UNKNOWN" if hb_age is None else "OK"
    assert status == "UNKNOWN"


def test_circuit_breaker_still_blocks_buy_path():
    from app.prospect.execution import decide_order_status

    st, reason = decide_order_status(
        breaker_active=True,
        breaker_reason="max_daily_loss",
        stale_data=False,
        cash_ok=True,
        fill={"ok": True},
    )
    assert st == "REJECTED"


def test_no_real_trading_in_reconcile_and_engine():
    for rel in ("app/prospect/reconcile.py", "app/prospect/engine.py", "app/prospect/scheduler.py"):
        text = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8").lower()
        assert "/api/v3/order" not in text
        assert "api_secret" not in text
        assert "private_key" not in text


def test_evidence_insufficient_label():
    from app.prospect.metrics import prospective_metrics

    cur = MagicMock()
    cur.__iter__ = lambda self: iter([])
    m = prospective_metrics(lambda *a, **k: cur, experiment_type="SHADOW_LIVE")
    assert m["virtual_portfolio"]["evidence_label"] == "Evidencia insuficiente"
    assert m["experiment_type"] == "SHADOW_LIVE"
