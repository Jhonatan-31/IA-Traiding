"""Etapa AM — anomalía AL, captura límites, comparación, Lab RO, Vision µs."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.execution_v2.am_experiment import (
    evaluate_event,
    run_analysis_on_capture,
    subsample_by_bucket,
)
from app.execution_v2.bbo_capture import (
    CapturePlan,
    am_authorized_plan,
    capture_is_active,
    run_bounded_capture,
)
from app.execution_v2.cost_decomposition import (
    decompose_pair_costs,
    reconstruct_al_anomaly_buy,
)
from app.execution_v2.lab_historical_audit import (
    audit_lab_sells_readonly,
    classify_sell_row,
)
from app.execution_v2.vision_ingest import (
    normalize_vision_open_time_ms,
    parse_klines_csv_vision,
)
from app.execution_v2.bbo_store import BboQuote
from app.lab.ledger import apply_sell

ROOT = Path(__file__).resolve().parents[2]


def test_am_al_anomaly_reconstruction_matches_reported_direction():
    r = reconstruct_al_anomaly_buy()
    assert r["diff_unit_v2_minus_v1"] < 0  # V2 cheaper under default mismatch
    assert abs(r["diff_unit_v2_minus_v1"] + 64.0) < 5.0  # ~−64 USDT/BTC
    assert "base_slip_rate=0.001" in r["decomposition"]["primary_cause"]
    assert r["auditable_original_timestamps"] is False


def test_am_no_double_fee_lab_sell_regression():
    class DB:
        def __init__(self):
            self.cash = Decimal("100")
            self.positions = {
                "BTCUSDT": {
                    "account_id": "lab",
                    "symbol": "BTCUSDT",
                    "qty": Decimal("1"),
                    "cost": Decimal("50"),
                }
            }

        def execute(self, sql, params=None):
            s = " ".join(sql.split()).upper()
            params = params or ()

            class R:
                def __init__(self, row=None):
                    self._row = row

                def fetchone(self):
                    return self._row

            if "SELECT CASH" in s:
                return R({"cash": self.cash})
            if "SELECT * FROM LAB_POSITIONS" in s:
                return R(self.positions.get(params[1]))
            if "UPDATE LAB_ACCOUNTS" in s:
                self.cash = Decimal(str(params[0]))
                return R()
            if "DELETE FROM LAB_POSITIONS" in s:
                self.positions.pop(params[1], None)
                return R()
            return R()

    db = DB()
    before = db.cash
    apply_sell(
        db.execute,
        order_uid="00000000-0000-0000-0000-000000000099",
        symbol="BTCUSDT",
        fill_price=Decimal("10"),
        candle_ms=1,
        strategy="t",
        reason="s",
        fee=Decimal("0.01"),
        fill_price_is_all_in=True,
    )
    assert float(db.cash - before) == pytest.approx(10.0)


def test_am_capture_concurrent_blocked(monkeypatch):
    async def _run():
        # Force first capture to hold the lock while sleeping inside refresh
        from app.execution_v2 import bbo_capture as bc

        held = asyncio.Event()

        async def slow_refresh(symbols):
            held.set()
            await asyncio.sleep(0.4)
            return {"ok": True}

        monkeypatch.setattr(bc, "refresh_book_ticker", slow_refresh)
        plan = CapturePlan(max_seconds=1.0, max_events=50, poll_interval_s=0.05)

        t1 = asyncio.create_task(run_bounded_capture(plan, out_dir=None))
        await held.wait()
        t2 = await run_bounded_capture(plan, out_dir=None)
        await t1
        assert t2.get("ok") is False and t2.get("reason") == "capture_already_active"
        assert capture_is_active() is False

    asyncio.run(_run())


def test_am_authorized_plan_clamped():
    p = am_authorized_plan(max_seconds=99999)
    assert p.max_seconds <= 1800
    assert p.max_events <= 250_000
    assert p.max_bytes <= 100 * 1024 * 1024
    assert p.authorized is True


def test_am_subsample_anti_pseudoreplication():
    base = int(time.time() * 1000)
    evs = [
        {
            "symbol": "BTCUSDT",
            "received_at_ms": base + i * 1000,
            "bid_price": 1,
            "ask_price": 1.1,
            "bid_qty": 1,
            "ask_qty": 1,
        }
        for i in range(60)
    ]
    sub = subsample_by_bucket(evs, bucket_ms=30_000)
    assert len(sub) <= 3


def test_am_misaligned_bbo_not_comparable():
    now = int(time.time() * 1000)
    ev = {
        "symbol": "BTCUSDT",
        "bid_price": 100,
        "ask_price": 100.1,
        "bid_qty": 1,
        "ask_qty": 1,
        "received_at_ms": now + 10_000,
        "captured_at_ms": now,
    }
    row = evaluate_event(ev, side="BUY", notional_usdt=25)
    assert row["comparable"] is False
    assert row["reason"] == "bbo_after_decision"


def test_am_size_liquidity_warning():
    now = int(time.time() * 1000)
    ev = {
        "symbol": "BTCUSDT",
        "bid_price": 100,
        "ask_price": 100.1,
        "bid_qty": 0.01,
        "ask_qty": 0.01,
        "received_at_ms": now,
        "captured_at_ms": now,
    }
    row = evaluate_event(ev, side="BUY", notional_usdt=500)
    # may be comparable partial or liquidity warn
    if row.get("comparable"):
        assert row.get("liquidity_warning") or row.get("partial")


def test_am_cost_decomp_no_double_spread_flag():
    now = int(time.time() * 1000)
    bbo = BboQuote(
        symbol="ETHUSDT",
        bid_price=10,
        bid_qty=2,
        ask_price=10.02,
        ask_qty=2,
        received_at_ms=now,
    )
    d = decompose_pair_costs(side="BUY", qty=0.1, ref_mid=bbo.mid, bbo=bbo, now_ms=now)
    assert d["ok"]
    assert d["no_double_fee"]
    assert d["v2_components"]["spread_already_in_executable"] is True


def test_am_lab_classify_probable_not_auto_confirmado():
    c = classify_sell_row(
        qty=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("0.1"),
        fee_rate=Decimal("0.001"),
        fill_price_was_all_in=True,
    )
    assert c["status"] == "PROBABLE"


def test_am_lab_audit_readonly_fake_db():
    class Cur:
        def execute(self, sql, params=None):
            return self

        def __iter__(self):
            return iter(
                [
                    {
                        "id": 1,
                        "account_id": "lab",
                        "at": "2026-01-01",
                        "symbol": "BTCUSDT",
                        "qty": Decimal("1"),
                        "price": Decimal("50"),
                        "fee": Decimal("0.05"),
                        "slip": Decimal("0"),
                        "realized_pnl": Decimal("1"),
                        "reason": "x",
                        "strategy": "t",
                    }
                ]
            )

    report = audit_lab_sells_readonly(lambda sql, params=None: Cur())
    assert report["readonly"] is True
    assert report["regularization_executed"] is False
    assert report["n_sells_examined"] == 1


def test_am_vision_microseconds_normalized():
    # µs-scale timestamp (~2025+)
    info = normalize_vision_open_time_ms(1_700_000_000_000_000)
    assert info["unit_detected"] == "microseconds"
    assert info["open_time_ms"] == 1_700_000_000_000
    csv = b"1700000000000000,1,2,0.5,1.5,10,1700000060000000,15.5,7,4,6.2,0\n"
    rows = parse_klines_csv_vision(csv)
    assert rows[0]["open_time_unit"] == "microseconds"
    assert rows[0]["quote_volume"] == 15.5


def test_am_analysis_on_synthetic_capture():
    now = int(time.time() * 1000)
    events = []
    for i, sym in enumerate(("BTCUSDT", "ETHUSDT", "SOLUSDT")):
        events.append(
            {
                "symbol": sym,
                "bid_price": 100 + i,
                "ask_price": 100.1 + i,
                "bid_qty": 5,
                "ask_qty": 5,
                "received_at_ms": now + i * 1000,
                "captured_at_ms": now + i * 1000,
            }
        )
    out = run_analysis_on_capture(events, bucket_ms=1000)
    assert out["n_comparable"] > 0
    assert out["meta"]["anti_pseudoreplication"] is True
    assert "n25" in out["by_size"]


def test_am_docs_exist():
    d = ROOT / "docs" / "etapa_am"
    assert (d / "INFORME_ETAPA_AM.md").is_file()
