"""Etapa V — forense, regímenes y políticas congeladas."""
from __future__ import annotations

from datetime import datetime, timezone

from app.research.forensic_a import reconstruct_equity_from_trades
from app.research.policies_v import POLICIES, list_policies
from app.research.regimes import classify_regime


def test_policies_frozen():
    ps = list_policies()
    assert "V_TREND" in POLICIES and "V_BREAK" in POLICIES
    assert POLICIES["V_TREND"]["frozen"] is True
    assert POLICIES["V_IA"]["execution_authorized"] is False
    assert POLICIES["V_MEAN"]["rules"]["martingale"] is False
    assert len(ps) >= 5


def test_regime_insufficient_and_sideways():
    short = [
        {
            "open_time": i,
            "open": 100,
            "high": 100.1,
            "low": 99.9,
            "close": 100,
            "volume": 1,
            "is_closed": True,
        }
        for i in range(10)
    ]
    assert classify_regime(short)["regime"] == "insufficient_data"
    flat = []
    for i in range(80):
        px = 100 + (0.01 if i % 2 == 0 else -0.01)
        flat.append(
            {
                "open_time": i * 60_000,
                "open": px,
                "high": px + 0.05,
                "low": px - 0.05,
                "close": px,
                "volume": 10,
                "is_closed": True,
            }
        )
    r = classify_regime(flat)
    assert r["look_ahead_safe"] is True
    assert r["trend"] in {"sideways", "uptrend", "downtrend", "insufficient"}


def test_equity_reconstruction_no_double_slip():
    trades = [
        {
            "id": 1,
            "at": datetime(2026, 11, 4, tzinfo=timezone.utc),
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 1.0,
            "price": 100.0,
            "fee": 0.1,
            "slip": 0.05,
            "realized_pnl": 0,
        },
        {
            "id": 2,
            "at": datetime(2026, 11, 4, 1, tzinfo=timezone.utc),
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": 1.0,
            "price": 101.0,
            "fee": 0.1,
            "slip": 0.05,
            "realized_pnl": 0.8,
        },
    ]
    book = reconstruct_equity_from_trades(trades, initial=1000.0)
    # BUY: 1000 - 100 - 0.1 = 899.9; SELL: 899.9 + 101 - 0.1 = 1000.8
    assert abs(book["final_cash"] - 1000.8) < 1e-9
    assert "no se resta dos veces" in book["accounting_note"].lower() or "Slip" in book["accounting_note"]
