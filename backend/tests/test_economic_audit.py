"""Auditoría económica — FIFO, win rate solo en cerradas, sin inventar fills."""
from __future__ import annotations

from datetime import datetime, timezone

from app.active.economic_audit import _fifo_rounds, _stats_closed


def _t(i, side, sym, qty, price, fee=0.01, slip=0.005, rpnl=None, reason="demo_policy_buy", minutes=0):
    return {
        "id": i,
        "at": datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc).replace(minute=minutes),
        "symbol": sym,
        "side": side,
        "qty": qty,
        "price": price,
        "fee": fee,
        "slip": slip,
        "realized_pnl": rpnl,
        "reason": reason,
    }


def test_fifo_closed_and_open_not_counted_as_wins():
    trades = [
        _t(1, "BUY", "BTCUSDT", 1.0, 100.0, minutes=0),
        _t(2, "SELL", "BTCUSDT", 1.0, 102.0, rpnl=1.5, reason="take_profit_2pct", minutes=10),
        _t(3, "BUY", "ETHUSDT", 2.0, 50.0, minutes=20),
        _t(4, "SELL", "ETHUSDT", 2.0, 49.0, rpnl=-2.2, reason="stop_loss_1pct", minutes=30),
        _t(5, "BUY", "SOLUSDT", 3.0, 10.0, minutes=40),  # open — must not be a win
    ]
    closed, open_lots = _fifo_rounds(trades)
    assert len(closed) == 2
    assert len(open_lots) == 1
    assert open_lots[0]["symbol"] == "SOLUSDT"
    st = _stats_closed(closed)
    assert st["closed_rounds"] == 2
    assert st["wins"] == 1
    assert st["losses"] == 1
    assert abs(st["win_rate"] - 0.5) < 1e-9
    assert st["expectancy"] == round((1.5 - 2.2) / 2, 6)
    # open buy never appears in wins
    assert st["wins"] + st["losses"] + st["breakeven"] == st["closed_rounds"]


def test_profit_factor_and_avg_win_loss():
    closed = [
        {"realized_pnl": 2.0, "fees": 0.1, "slip": 0.05, "duration_seconds": 60},
        {"realized_pnl": 1.0, "fees": 0.1, "slip": 0.05, "duration_seconds": 120},
        {"realized_pnl": -1.0, "fees": 0.1, "slip": 0.05, "duration_seconds": 90},
    ]
    st = _stats_closed(closed)
    assert st["wins"] == 2
    assert st["losses"] == 1
    assert abs(st["avg_win"] - 1.5) < 1e-9
    assert abs(st["avg_loss"] - (-1.0)) < 1e-9
    assert abs(st["profit_factor"] - 3.0) < 1e-9
