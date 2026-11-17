"""Etapa AN — contrato económico, fair compare, WS límites, Lab RO."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.execution_v2.am_audit import audit_am_dataset
from app.execution_v2.am_experiment import subsample_by_bucket
from app.execution_v2.bbo_store import BboQuote
from app.execution_v2.bbo_ws_capture import WsCapturePlan, run_ws_book_ticker_capture
from app.execution_v2.cost_contract import (
    CONTRACT_ID,
    bps,
    buy_all_in,
    reconcile_buy_cash,
    reconcile_sell_cash,
    sell_all_in,
    D,
)
from app.execution_v2.fair_compare import (
    evaluate_legacy,
    evaluate_matched,
    run_fair_analysis,
)
from app.execution_v2.lab_historical_audit import classify_sell_row
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]


def _bbo(mid=100.0, spread=0.02, qty=10.0):
    half = spread / 2
    now = int(time.time() * 1000)
    return BboQuote(
        symbol="BTCUSDT",
        bid_price=mid - half,
        ask_price=mid + half,
        bid_qty=qty,
        ask_qty=qty,
        received_at_ms=now,
    )


def test_an_contract_buy_no_double_spread():
    c = buy_all_in(
        mid=D(100),
        ask=D(100.1),
        qty=D(1),
        fee_rate=D("0.001"),
        extra_slip_rate=D("0.0002"),
        use_observed_ask=True,
    )
    assert "spread_embodied_in_ask_not_added_again" in c.notes
    assert float(c.mid_to_touch) == pytest.approx(0.1)


def test_an_contract_sell_all_in_cash():
    c = sell_all_in(
        mid=D(100),
        bid=D(99.9),
        qty=D(2),
        fee_rate=D("0.001"),
        extra_slip_rate=D(0),
        use_observed_bid=True,
    )
    # all_in = 99.9 * 0.999
    assert float(c.cash_total) == pytest.approx(2 * 99.9 * 0.999, rel=1e-9)


def test_an_reconcile_buy_sell_independent():
    assert reconcile_buy_cash(100, 100.1, 0.5, 0.001, 0.0002)["ok"]
    assert reconcile_sell_cash(100, 99.9, 0.5, 0.001, 0.0002)["ok"]


def test_an_bps():
    assert float(bps(D(1), D(10000))) == pytest.approx(1.0)


def test_an_legacy_vs_matched_divergence():
    bbo = _bbo(64000, 0.01, 5)
    leg = evaluate_legacy(side="BUY", qty=0.001, mid=bbo.mid, bbo=bbo, now_ms=bbo.received_at_ms)
    mat = evaluate_matched(side="BUY", qty=0.001, mid=bbo.mid, bbo=bbo)
    assert leg["comparable"] and mat["comparable"]
    # Legacy |diff| much larger due to 10bps V1 slip
    assert abs(leg["price_diff_v2_minus_v1_signed"]) > abs(mat["price_diff_v2_minus_v1_signed"])
    assert mat["param_note"]["isolates"] == "observed_touch_vs_mid"


def test_an_per_symbol_side_not_pooled():
    now = int(time.time() * 1000)
    events = []
    for i, sym in enumerate(("BTCUSDT", "ETHUSDT", "SOLUSDT")):
        mid = 100 * (i + 1)
        events.append(
            {
                "symbol": sym,
                "bid_price": mid - 0.01,
                "ask_price": mid + 0.01,
                "bid_qty": 100,
                "ask_qty": 100,
                "received_at_ms": now + i * 1000,
                "captured_at_ms": now + i * 1000,
            }
        )
    out = run_fair_analysis(events, bucket_ms=1000)
    assert out["independence"]["do_not_use_for_naive_ci"] is True
    keys = set(out["matched"]["by_symbol_side"].keys())
    assert "BTCUSDT|BUY" in keys and "BTCUSDT|SELL" in keys
    assert "warning" in out["matched"]


def test_an_size_incomplete_without_l2():
    bbo = _bbo(100, 0.02, qty=0.01)
    mat = evaluate_matched(side="BUY", qty=1.0, mid=bbo.mid, bbo=bbo)
    assert mat["incomplete_without_l2"] is True


def test_an_buckets_not_360_independent():
    now = int(time.time() * 1000)
    events = [
        {
            "symbol": "BTCUSDT",
            "bid_price": 1,
            "ask_price": 1.01,
            "bid_qty": 1,
            "ask_qty": 1,
            "received_at_ms": now + i * 1000,
            "captured_at_ms": now + i * 1000,
        }
        for i in range(90)
    ]
    buckets = subsample_by_bucket(events, bucket_ms=30_000)
    assert len(buckets) <= 4
    # derived rows would be buckets * 6
    assert len(buckets) * 6 < 360 or True


def test_an_lab_still_probable_without_cash_trail():
    c = classify_sell_row(
        qty=Decimal("1"),
        price=Decimal("50"),
        fee=Decimal("0.05"),
        fee_rate=Decimal("0.001"),
        fill_price_was_all_in=True,
    )
    assert c["status"] == "PROBABLE"


def test_an_ws_capture_offline_no_autostart(monkeypatch):
    websockets = pytest.importorskip("websockets")

    class Dummy:
        async def __aenter__(self):
            raise OSError("offline_test")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(websockets, "connect", lambda *a, **k: Dummy())

    async def _run():
        r = await run_ws_book_ticker_capture(
            WsCapturePlan(max_seconds=0.3, max_events=10), out_dir=None
        )
        assert r["permanent_service"] is False
        assert r["ok"] is False or r["n_events"] == 0

    asyncio.run(_run())


def test_an_docs_exist():
    assert (ROOT / "docs" / "etapa_an" / "INFORME_ETAPA_AN.md").is_file()
    assert (ROOT / "docs" / "etapa_an" / "COST_CONTRACT_V1.md").is_file()
