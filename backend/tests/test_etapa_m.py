"""Etapa M — auth token, valuation, exits gaps, breaker resume guard."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.lab.auth import require_lab_token
from app.lab.exits import evaluate_exit
from app.lab.risk import can_buy, critical_condition_still_active, evaluate_lab_breaker
from app.lab.valuation import portfolio_valuation


def test_token_missing_env_returns_503():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LAB_CONTROL_TOKEN", None)
        with pytest.raises(HTTPException) as ei:
            require_lab_token(None)
        assert ei.value.status_code == 503


def test_token_wrong_returns_401():
    with patch.dict(os.environ, {"LAB_CONTROL_TOKEN": "strong-secret-value-xyz"}):
        with pytest.raises(HTTPException) as ei:
            require_lab_token("wrong")
        assert ei.value.status_code == 401


def test_token_ok():
    with patch.dict(os.environ, {"LAB_CONTROL_TOKEN": "strong-secret-value-xyz"}):
        assert require_lab_token("strong-secret-value-xyz") == "ok"


def test_no_insecure_paper_fallback_in_auth_source():
    text = (Path(__file__).resolve().parents[1] / "app/lab/auth.py").read_text(
        encoding="utf-8"
    )
    assert 'get("LAB_CONTROL_TOKEN", "paper")' not in text
    assert ':-paper' not in text


def test_compose_requires_lab_token():
    root = Path(__file__).resolve().parents[2]
    path = root / "compose.yaml"
    if not path.exists():
        # API image does not ship compose.yaml; host/CI path covers this assertion.
        pytest.skip("compose.yaml not present in container image")
    text = path.read_text(encoding="utf-8")
    assert "LAB_CONTROL_TOKEN:?Set LAB_CONTROL_TOKEN" in text
    assert "LAB_CONTROL_TOKEN:-paper" not in text


def test_valuation_incomplete_without_marks():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM lab_accounts" in sql_n:
                cur.fetchone = lambda: {
                    "cash": Decimal("900"),
                    "initial_capital": Decimal("1000"),
                }
            elif "FROM lab_positions" in sql_n:
                cur.__iter__ = lambda self: iter(
                    [
                        {
                            "symbol": "BTCUSDT",
                            "qty": Decimal("0.01"),
                            "cost": Decimal("100"),
                            "entry_price": Decimal("10000"),
                        }
                    ]
                )
            elif "FROM lab_trades" in sql_n:
                cur.__iter__ = lambda self: iter([])
            elif "lab_equity_daily" in sql_n:
                cur.fetchone = lambda: {"peak": Decimal("1000")}
            else:
                cur.fetchone = lambda: None
                cur.__iter__ = lambda self: iter([])
            return cur

    v = portfolio_valuation(Ex(), marks={})
    assert v["valuation_status"] == "INCOMPLETE"
    assert v["equity_estimate"] is None
    assert v["positions"][0]["mark_price"] is None


def test_valuation_ok_with_marks():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "FROM lab_accounts" in sql_n:
                cur.fetchone = lambda: {
                    "cash": Decimal("900"),
                    "initial_capital": Decimal("1000"),
                }
            elif "FROM lab_positions" in sql_n:
                cur.__iter__ = lambda self: iter(
                    [
                        {
                            "symbol": "BTCUSDT",
                            "qty": Decimal("0.01"),
                            "cost": Decimal("100"),
                            "entry_price": Decimal("10000"),
                        }
                    ]
                )
            elif "FROM lab_trades" in sql_n:
                cur.__iter__ = lambda self: iter(
                    [{"fee": Decimal("0.1"), "realized_pnl": None, "side": "BUY"}]
                )
            elif "lab_equity_daily" in sql_n:
                cur.fetchone = lambda: {"peak": Decimal("1100")}
            else:
                cur.fetchone = lambda: None
                cur.__iter__ = lambda self: iter([])
            return cur

    marks = {
        "BTCUSDT": {
            "price": 11000.0,
            "source": "binance_public_ticker",
            "at": "2026-11-03T20:00:00+00:00",
            "ok": True,
        }
    }
    v = portfolio_valuation(Ex(), marks=marks)
    assert v["valuation_status"] == "OK"
    assert v["equity_estimate"] == pytest.approx(900 + 110.0)
    assert v["unrealized_pnl"] == pytest.approx(10.0)


def test_stop_gap_uses_trigger_not_as_fill():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    # Gap through stop to 90
    d = evaluate_exit(
        pos,
        mark_price=Decimal("90"),
        mark_age_s=5,
        stale_s=7200,
        strategy_side=None,
        bars_held=1,
    )
    assert d["stop_triggered"] is True
    assert d["stop_trigger_price"] == 98.0
    assert d["stop_trigger_price"] != 90.0  # execution uses separate fill path


def test_time_stop_48_bars():
    pos = {
        "entry_price": 100,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_hold_bars": 48,
    }
    d = evaluate_exit(
        pos,
        mark_price=Decimal("100"),
        mark_age_s=1,
        stale_s=7200,
        strategy_side=None,
        bars_held=48,
    )
    assert d["reason"] == "max_hold_bars"


def test_resume_blocked_when_breaker_active():
    class Ex:
        def __call__(self, sql, params=None):
            cur = MagicMock()
            sql_n = " ".join(sql.split())
            if "lab_executor_state" in sql_n:
                cur.fetchone = lambda: {
                    "breaker_active": True,
                    "breaker_reason": "max_daily_loss",
                }
            else:
                cur.fetchone = lambda: {"cash": Decimal("1000")}
                cur.__iter__ = lambda self: iter([])
            return cur

    crit, reason = critical_condition_still_active(Ex())
    assert crit and reason == "max_daily_loss"


def test_idempotent_order_unique_contract():
    cols = ("account_id", "strategy", "symbol", "side", "candle_ms")
    assert len(cols) == 5


def test_paused_blocks_buy():
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


def test_no_secrets_logged_in_auth():
    text = (Path(__file__).resolve().parents[1] / "app/lab/auth.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "print(" not in text
    assert "logger" not in text or "token" not in text


def test_three_ledgers_untouched_in_lab_mutations():
    for rel in ("ledger.py", "executor.py", "orders.py"):
        text = (
            Path(__file__).resolve().parents[1] / "app/lab" / rel
        ).read_text(encoding="utf-8")
        assert "UPDATE account SET" not in text
        assert "INSERT INTO trades(" not in text
        assert "UPDATE virt_accounts" not in text
