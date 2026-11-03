"""Etapa K — prospective report, premature resolve guard, evidence label."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.ml.resolve import resolve_from_candles
from app.prospect.reconcile import horizon_audit
from app.prospect.report import prospective_report
from app.prospect.resolve import apply_outcome


def test_premature_horizon_not_ready_nov3():
    open_ms = int(datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)
    now = datetime(2026, 11, 3, 20, 18, tzinfo=timezone.utc)

    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            cur.__iter__ = lambda self: iter(
                [
                    {
                        "id": 1,
                        "symbol": "BTCUSDT",
                        "interval": "1h",
                        "action": "HOLD",
                        "candle_open_ms": open_ms,
                        "horizon_bars": 6,
                        "created_at": now,
                        "decision_ts": now,
                        "observed_price": 77584,
                        "resolution_status": "PENDING",
                    }
                ]
            )
            return cur

    rows = horizon_audit(Ex(), now=now)
    assert rows[0]["horizon_ready"] is False


def test_resolve_candles_no_future_leak_incomplete():
    open_ms = 1_700_000_000_000
    step = 3_600_000
    candles = [
        {"open_time": open_ms + i * step, "close": 100.0, "is_closed": True}
        for i in range(4)
    ]
    r = resolve_from_candles(candles, candle_open_ms=open_ms, interval="1h", horizon=6)
    assert r["status"] == "PENDING"
    assert "entry_close" not in r or r.get("status") == "PENDING"


def test_hold_not_winning_trade_in_report():
    def execute(sql, params=None):
        cur = MagicMock()
        sql_n = " ".join(sql.split())
        if "LEFT JOIN prospect_outcomes" in sql_n and "ORDER BY d.id ASC" in sql_n:
            cur.__iter__ = lambda self: iter(
                [
                    {
                        "id": 1,
                        "created_at": datetime.now(timezone.utc),
                        "decision_ts": datetime.now(timezone.utc),
                        "symbol": "BTCUSDT",
                        "interval": "1h",
                        "action": "HOLD",
                        "reason": "sma10_le_sma50",
                        "observed_price": 100.0,
                        "estimated_costs_json": {"fee_rate": 0.001, "slip_rate": 0.001},
                        "system_state_json": {},
                        "candle_open_ms": 1,
                        "horizon_bars": 6,
                        "resolution_status": "RESOLVED",
                        "outcome_status": "RESOLVED",
                        "observed_net_return": 0.0,
                        "observed_label": None,
                        "data_quality": "ok",
                        "result_json": {"reason": "hold_no_trade"},
                        "resolved_at": datetime.now(timezone.utc),
                        "experiment_type": "SHADOW_LIVE",
                    },
                    {
                        "id": 2,
                        "created_at": datetime.now(timezone.utc),
                        "decision_ts": datetime.now(timezone.utc),
                        "symbol": "ETHUSDT",
                        "interval": "1h",
                        "action": "BUY",
                        "reason": "sma10_gt_sma50",
                        "observed_price": 200.0,
                        "estimated_costs_json": {"fee_rate": 0.001, "slip_rate": 0.001},
                        "system_state_json": {},
                        "candle_open_ms": 1,
                        "horizon_bars": 6,
                        "resolution_status": "RESOLVED",
                        "outcome_status": "RESOLVED",
                        "observed_net_return": 0.01,
                        "observed_label": 1,
                        "data_quality": "ok",
                        "result_json": {
                            "entry_close": 200.0,
                            "exit_close": 204.0,
                            "reason": "ok",
                        },
                        "resolved_at": datetime.now(timezone.utc),
                        "experiment_type": "SHADOW_LIVE",
                    },
                ]
            )
        else:
            # metrics query
            cur.__iter__ = lambda self: iter(
                [
                    {
                        "action": "HOLD",
                        "symbol": "BTCUSDT",
                        "observed_price": 100,
                        "estimated_costs_json": {},
                        "observed_net_return": 0.0,
                        "observed_label": None,
                        "outcome_status": "RESOLVED",
                        "data_quality": "ok",
                        "resolution_status": "RESOLVED",
                    },
                    {
                        "action": "BUY",
                        "symbol": "ETHUSDT",
                        "observed_price": 200,
                        "estimated_costs_json": {},
                        "observed_net_return": 0.01,
                        "observed_label": 1,
                        "outcome_status": "RESOLVED",
                        "data_quality": "ok",
                        "resolution_status": "RESOLVED",
                    },
                ]
            )
        return cur

    rep = prospective_report(execute, experiment_type="SHADOW_LIVE")
    assert rep["evidence_label"] == "Evidencia insuficiente"
    assert rep["show_portfolio_pnl"] is False
    hold = next(d for d in rep["decisions"] if d["action"] == "HOLD")
    buy = next(d for d in rep["decisions"] if d["action"] == "BUY")
    assert hold["hypothetical_net_if_buy"] is None
    assert hold["hold_counted_as_trade"] is False
    assert buy["hypothetical_net_if_buy"] == 0.01
    assert buy["executed_trade"] is False
    assert rep["probability_scores"]["applicable"] is False
    assert rep["counts"]["buy_resolved"] == 1
    assert rep["counts"]["hold_resolved"] == 1


def test_outcome_idempotent_k():
    class Ex:
        def __init__(self):
            self.outcomes = {}
            self.decisions = {9: {"resolution_status": "PENDING"}}
            self._last = None

        def __call__(self, sql, params=None):
            sql_n = " ".join(sql.split())
            cur = MagicMock()
            if sql_n.startswith("SELECT decision_id FROM prospect_outcomes"):
                did = params[0]
                cur.fetchone = lambda: {"decision_id": did} if did in self.outcomes else None
            elif sql_n.startswith("UPDATE prospect_decisions"):
                did = params[1]
                if self.decisions[did]["resolution_status"] == "PENDING":
                    self.decisions[did]["resolution_status"] = params[0]
                    cur.fetchone = lambda: {"id": did}
                else:
                    cur.fetchone = lambda: None
            elif sql_n.startswith("INSERT INTO prospect_outcomes"):
                self.outcomes[params[0]] = params
                cur.fetchone = lambda: None
            return cur

    ex = Ex()
    assert apply_outcome(ex, 9, status="RESOLVED", data_quality="ok",
                         observed_net_return=0.02, observed_label=1, result={}) is True
    assert apply_outcome(ex, 9, status="RESOLVED", data_quality="ok",
                         observed_net_return=0.99, observed_label=0, result={}) is False


def test_no_real_orders_report_module():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/prospect/report.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "/api/v3/order" not in text
    assert "paper_ai" not in text or "never" in text
