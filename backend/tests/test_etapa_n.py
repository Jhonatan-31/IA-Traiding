"""Etapa N — signal audit, exit priority, monitor dedup, organic SMA, persistence."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from app.lab.exits import EXIT_PRIORITY, evaluate_exit
from app.lab.monitor import run_monitor, upsert_alert
from app.lab.signals import analyze_sma_cross, sma_cross_signal


def _closes_golden() -> list[float]:
    # Closed-bar golden: bar leaving window low, bar entering high → SMA10 crosses above SMA50
    closes = [100.0] * 60
    closes[-11] = 10.0
    closes[-1] = 300.0
    return closes


def _closes_death() -> list[float]:
    closes = [100.0] * 60
    closes[-11] = 300.0
    closes[-1] = 10.0
    return closes


def test_analyze_sma_buy_and_sell_synthetic():
    buy = analyze_sma_cross(_closes_golden())
    assert buy["decision"] == "BUY"
    assert buy["cross_state"] == "golden"
    assert buy["data_status"] == "ok"
    assert buy["sma10"] is not None and buy["sma50"] is not None
    assert sma_cross_signal(_closes_golden()) == "BUY"

    sell = analyze_sma_cross(_closes_death())
    assert sell["decision"] == "SELL"
    assert sell["cross_state"] == "death"
    assert sma_cross_signal(_closes_death()) == "SELL"


def test_analyze_hold_flat_no_lookahead():
    flat = [100.0] * 60
    h = analyze_sma_cross(flat)
    assert h["decision"] == "HOLD"
    assert h["cross_state"] == "none"
    assert "no_sma_cross" in (h["reason"] or "")


def test_insufficient_bars():
    h = analyze_sma_cross([1.0] * 10)
    assert h["decision"] == "HOLD"
    assert h["data_status"] == "insufficient_bars"


def test_exit_priority_stop_before_strategy():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    # Gap through stop while strategy also wants SELL
    d = evaluate_exit(
        pos,
        mark_price=Decimal("90"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=10,
    )
    assert d["reason"] == "stop_loss"
    assert d["priority"] < EXIT_PRIORITY.index("strategy_exit")


def test_exit_priority_tp_before_time_stop():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    d = evaluate_exit(
        pos,
        mark_price=Decimal("105"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=100,
    )
    assert d["reason"] == "take_profit"


def test_exit_stale_blocks_execution():
    pos = {"entry_price": 100, "stop_loss_pct": 0.02, "take_profit_pct": 0.04, "max_hold_bars": 48}
    d = evaluate_exit(
        pos,
        mark_price=Decimal("90"),
        mark_age_s=99999,
        stale_s=7200,
        strategy_side="SELL",
        bars_held=100,
    )
    assert d["action"] == "HOLD"
    assert d["allow_execution"] is False


def test_monitor_alert_dedup():
    store: dict[str, dict] = {}

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "SELECT id, active FROM lab_alerts" in sql_n:
                fp = params[0]
                row = store.get(fp)
                cur.fetchone = lambda: row
            elif "INSERT INTO lab_alerts" in sql_n:
                fp = params[3]
                store[fp] = {"id": 1, "active": True, "fingerprint": fp}
            elif "UPDATE lab_alerts SET at=NOW()" in sql_n:
                pass
            elif "UPDATE lab_alerts SET active=FALSE" in sql_n:
                fp = params[0]
                if fp in store:
                    store[fp]["active"] = False
            else:
                cur.fetchone = lambda: None
            return cur

    ex = Ex()
    assert upsert_alert(
        ex, code="x", severity="WARNING", message="a", fingerprint="fp1"
    ) is True
    assert upsert_alert(
        ex, code="x", severity="WARNING", message="b", fingerprint="fp1"
    ) is False


def test_monitor_no_autoresume_note():
    from datetime import datetime, timezone
    from unittest.mock import patch

    now = datetime.now(timezone.utc)

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "lab_executor_state" in sql_n and "SELECT" in sql_n:
                cur.fetchone = lambda: {
                    "heartbeat_at": now,
                    "last_cycle_at": now,
                    "meta_json": {"valuation_status": "OK"},
                    "breaker_active": False,
                }
            elif "FROM lab_alerts WHERE active" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "COUNT(*)" in sql_n:
                cur.fetchone = lambda: {"n": 0}
            else:
                cur.fetchone = lambda: {"n": 0}
                cur.__iter__ = lambda self: iter([])
            return cur

    with patch("app.lab.risk.accounting_ok", return_value=True):
        out = run_monitor(Ex(), expected_cycle_s=300, binance_errors=0)
    assert "no reinicia" in out["note"].lower()


def test_idempotency_unique_contract_still_present():
    text = (Path(__file__).resolve().parents[1] / "app/lab/schema.py").read_text(
        encoding="utf-8"
    )
    assert "UNIQUE(account_id, strategy, symbol, side, candle_ms)" in text
    assert "lab_signal_evals" in text
    assert "lab_alerts" in text


def test_no_real_order_endpoints_in_lab_api():
    text = (Path(__file__).resolve().parents[1] / "app/lab_api.py").read_text(
        encoding="utf-8"
    )
    assert "binance.com/api/v3/order" not in text
    assert "real_trading" in text


def test_three_ledgers_untouched_etapa_n():
    for rel in ("signals.py", "monitor.py", "executor.py"):
        text = (Path(__file__).resolve().parents[1] / "app/lab" / rel).read_text(
            encoding="utf-8"
        )
        assert "UPDATE account SET" not in text
        assert "UPDATE virt_accounts" not in text
