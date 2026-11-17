"""Etapa AK — ejecución V2, BBO, Vision, costos D28H5, adversariales."""
from __future__ import annotations

import time
from pathlib import Path

from app.execution_v2.bbo_store import BboQuote, BboRegistry
from app.execution_v2.cost_reconcile import COST_FRAC, reconcile_d28h5_costs_from_artifact
from app.execution_v2.engine_v2 import ExecutionV2Assumptions, compare_v1_v2, simulate_fill_v2
from app.execution_v2.vision_ingest import audit_vision_loss_vs_v1_parser, parse_klines_csv_vision
from app.prospect.execution import estimate_fill_price, ExecutionAssumptions

ROOT = Path(__file__).resolve().parents[2]


def _bbo(bid=100.0, ask=100.2, bid_q=1.0, ask_q=0.5, age_ms=0) -> BboQuote:
    now = int(time.time() * 1000)
    return BboQuote(
        symbol="BTCUSDT",
        bid_price=bid,
        bid_qty=bid_q,
        ask_price=ask,
        ask_qty=ask_q,
        received_at_ms=now - age_ms,
    )


def test_ak_v1_preserved_and_v2_uses_ask_bid():
    bbo = _bbo()
    buy = simulate_fill_v2(side="BUY", qty=0.1, bbo=bbo)
    sell = simulate_fill_v2(side="SELL", qty=0.1, bbo=bbo)
    assert buy["ok"] and sell["ok"]
    assert buy["executable_price"] == 100.2
    assert sell["executable_price"] == 100.0
    # V1 still callable
    v1 = estimate_fill_price(
        side="BUY", mid_or_ref=100.1, assumptions=ExecutionAssumptions(spread_bps=2, base_slip_rate=0, fee_rate=0.001)
    )
    assert v1["ok"]


def test_ak_stale_bbo_rejected():
    bbo = _bbo(age_ms=60_000)
    out = simulate_fill_v2(
        side="BUY", qty=0.01, bbo=bbo, assumptions=ExecutionV2Assumptions(max_quote_age_ms=5000)
    )
    assert out["ok"] is False
    assert out["reason"] == "stale_bbo"


def test_ak_missing_bbo_rejected_by_default():
    out = simulate_fill_v2(side="BUY", qty=0.01, ref_mid=100.0, bbo=None)
    assert out["ok"] is False
    assert out["reason"] == "missing_bbo"


def test_ak_wide_spread_and_partial_top_qty():
    bbo = _bbo(bid=100.0, ask=101.0, ask_q=0.01)
    out = simulate_fill_v2(side="BUY", qty=1.0, bbo=bbo)
    assert out["ok"]
    assert out["partial"] is True
    assert out["fill_qty"] == 0.01
    assert out["spread_abs"] == 1.0


def test_ak_no_double_fee_in_v2_cash_delta():
    bbo = _bbo(bid=100.0, ask=100.0, ask_q=10)
    out = simulate_fill_v2(
        side="BUY",
        qty=1.0,
        bbo=bbo,
        assumptions=ExecutionV2Assumptions(fee_rate=0.001, extra_slip_rate=0.0),
    )
    # cash_delta should equal -(qty * price_all_in); fee already in all-in
    assert abs(out["cash_delta"] + out["fill_qty"] * out["price_all_in"]) < 1e-9


def test_ak_insufficient_implicit_via_zero_top_qty_uncertainty():
    # top qty 0 → respect_top_qty no cap (unknown depth) but uncertainty path via compare
    bbo = _bbo(ask_q=0.0, bid_q=0.0)
    out = simulate_fill_v2(side="BUY", qty=1.0, bbo=bbo)
    assert out["ok"]
    assert out["partial"] is False  # cannot cap without positive top qty


def test_ak_compare_v1_v2_deterministic():
    bbo = _bbo()
    a = compare_v1_v2(side="BUY", qty=0.2, ref_mid=100.1, bbo=bbo)
    b = compare_v1_v2(side="BUY", qty=0.2, ref_mid=100.1, bbo=bbo)
    assert a["v2"]["price_all_in"] == b["v2"]["price_all_in"]
    assert a["pl_delta_v2_minus_model_gap"] is not None


def test_ak_registry_rejects_invalid_and_tracks_stale():
    reg = BboRegistry()
    assert reg.upsert_book_ticker({"symbol": "ETHUSDT", "bidPrice": "1", "askPrice": "0.5"}) is None
    q = reg.upsert_book_ticker(
        {"symbol": "ETHUSDT", "bidPrice": "10", "askPrice": "10.1", "bidQty": "1", "askQty": "2"}
    )
    assert q is not None
    snap = reg.snapshot(max_age_ms=1)
    # force stale by rewriting age
    reg._quotes["ETHUSDT"].received_at_ms = int(time.time() * 1000) - 10_000
    snap2 = reg.snapshot(max_age_ms=1000)
    assert snap2["quotes"]["ETHUSDT"]["stale"] is True


def test_ak_vision_parser_keeps_microstructure_fields():
    csv = (
        b"open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_base,taker_buy_quote,ignore\n"
        b"1700000000000,1,2,0.5,1.5,10,1700000060000,15.5,7,4,6.2,0\n"
    )
    rows = parse_klines_csv_vision(csv)
    assert len(rows) == 1
    assert rows[0]["quote_volume"] == 15.5
    assert rows[0]["number_of_trades"] == 7
    assert rows[0]["taker_buy_base_volume"] == 4.0
    assert rows[0]["taker_buy_quote_volume"] == 6.2
    audit = audit_vision_loss_vs_v1_parser(csv)
    assert audit["rows_match"]
    assert "quote_volume" in audit["v1_omits_when_present_in_csv"]
    assert audit["destructive"] is False


def test_ak_d28h5_cost_reconcile_decimal():
    out = reconcile_d28h5_costs_from_artifact()
    assert out["ok"] is True
    assert out["hash_match"] is True
    assert out["frozen_params"]["unchanged"] is True
    assert out["identity_checks"]["split_sums_to_total"] is True
    # notional * cost_frac ≈ total
    assert float(out["identity_checks"]["vs_reported_total_abs_delta"]) < 0.05
    assert COST_FRAC == 0.001 + 0.0005 + (1.0 / 20_000.0)


def test_ak_docs_exist():
    docs = ROOT / "docs" / "etapa_ak"
    for name in (
        "AUDITORIA_SIMULADOR.md",
        "MOTOR_V2.md",
        "COSTOS_D28H5.md",
        "INFORME_ETAPA_AK.md",
    ):
        assert (docs / name).is_file(), name


def test_ak_no_real_orders_in_v2_module():
    src = (ROOT / "backend" / "app" / "execution_v2" / "engine_v2.py").read_text(encoding="utf-8")
    assert "api.binance.com/api/v3/order" not in src
    assert "create_order" not in src
