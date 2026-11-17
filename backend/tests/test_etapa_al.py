"""Etapa AL — adversariales V2, BBO, comparación, Vision, latencia/costos."""
from __future__ import annotations

import time
from pathlib import Path

from app.execution_v2.bbo_capture import CapturePlan, estimate_disk_usage
from app.execution_v2.bbo_store import BboQuote, BboRegistry
from app.execution_v2.compare_experiment import (
    HypotheticalDecision,
    evaluate_pair,
    summarize_pairs,
)
from app.execution_v2.engine_v2 import ExecutionV2Assumptions, simulate_fill_v2
from app.execution_v2.vision_ingest import (
    audit_vision_loss_vs_v1_parser,
    parse_klines_csv_vision,
    write_vision_ext_parquet,
)
from app.lab.ledger import apply_sell
from app.prospect.execution import ExecutionAssumptions, estimate_fill_price

ROOT = Path(__file__).resolve().parents[2]


def _q(**kw) -> BboQuote:
    now = int(time.time() * 1000)
    return BboQuote(
        symbol=kw.get("symbol", "BTCUSDT"),
        bid_price=kw.get("bid", 100.0),
        bid_qty=kw.get("bid_q", 1.0),
        ask_price=kw.get("ask", 100.2),
        ask_qty=kw.get("ask_q", 0.5),
        received_at_ms=now - kw.get("age_ms", 0),
        update_id=kw.get("update_id"),
    )


def test_al_fresh_bbo_ok():
    out = simulate_fill_v2(side="BUY", qty=0.01, bbo=_q())
    assert out["ok"] and out["data_quality"] == "LIVE_BBO"


def test_al_stale_bbo():
    out = simulate_fill_v2(
        side="BUY",
        qty=0.01,
        bbo=_q(age_ms=20_000),
        assumptions=ExecutionV2Assumptions(max_quote_age_ms=2000),
    )
    assert out["ok"] is False and out["reason"] == "stale_bbo"


def test_al_invalid_ask_below_bid_rejected_at_registry():
    reg = BboRegistry()
    assert reg.upsert_book_ticker({"symbol": "X", "bidPrice": "2", "askPrice": "1"}) is None
    assert reg.snapshot()["reject_counts"].get("ask_below_bid", 0) >= 1


def test_al_zero_qty_rejected():
    assert simulate_fill_v2(side="BUY", qty=0, bbo=_q())["ok"] is False


def test_al_excessive_qty_partial_top_of_book():
    out = simulate_fill_v2(side="BUY", qty=10.0, bbo=_q(ask_q=0.05))
    assert out["ok"] and out["partial"] and out["fill_qty"] == 0.05


def test_al_missing_depth_no_fabricated_levels():
    out = simulate_fill_v2(side="BUY", qty=1.0, bbo=_q(ask_q=0.0))
    assert out["ok"] is False
    assert out["reason"] == "insufficient_top_of_book_qty"
    assert "levels" not in out


def test_al_wide_spread_recorded():
    out = simulate_fill_v2(side="BUY", qty=0.01, bbo=_q(bid=100.0, ask=105.0))
    assert out["spread_abs"] == 5.0


def test_al_duplicate_and_out_of_order_update_id():
    reg = BboRegistry()
    assert reg.upsert_book_ticker(
        {"symbol": "BTCUSDT", "bidPrice": "1", "askPrice": "1.1", "u": 10}
    )
    assert reg.upsert_book_ticker(
        {"symbol": "BTCUSDT", "bidPrice": "1", "askPrice": "1.1", "u": 10}
    )
    assert reg.snapshot()["reject_counts"].get("duplicate_update_id", 0) >= 1
    assert (
        reg.upsert_book_ticker(
            {"symbol": "BTCUSDT", "bidPrice": "1", "askPrice": "1.1", "u": 5}
        )
        is None
    )


def test_al_compare_missing_bbo_not_comparable():
    row = evaluate_pair(
        HypotheticalDecision(
            decision_ts_ms=int(time.time() * 1000),
            symbol="BTCUSDT",
            side="BUY",
            qty=0.01,
            ref_mid=100.0,
        ),
        None,
    )
    assert row["comparable"] is False
    assert row["status"] == "NO_COMPARABLE"


def test_al_compare_with_bbo_summary():
    now = int(time.time() * 1000)
    bbo = _q()
    rows = [
        evaluate_pair(
            HypotheticalDecision(now, "BTCUSDT", "BUY", 0.01, bbo.mid),
            bbo,
            now_ms=now,
        ),
        evaluate_pair(
            HypotheticalDecision(now, "BTCUSDT", "BUY", 0.01, 100.0),
            None,
        ),
    ]
    summary = summarize_pairs(rows)
    assert summary["n_comparable"] == 1
    assert summary["n_not_comparable"] == 1
    assert summary["fabricated_observations"] is False


def test_al_order_qty_used_in_v1_and_v2_compare():
    bbo = _q(ask_q=0.002)
    now = int(time.time() * 1000)
    row = evaluate_pair(
        HypotheticalDecision(now, "BTCUSDT", "BUY", 1.0, bbo.mid),
        bbo,
        now_ms=now,
    )
    assert row["comparable"]
    assert row["qty_executable_est"] == 0.002
    assert row["partial"] is True


def test_al_latency_labeled_hypothetical():
    now = int(time.time() * 1000)
    row = evaluate_pair(
        HypotheticalDecision(now, "BTCUSDT", "BUY", 0.01, 100.0, assumed_send_latency_ms=250),
        _q(),
        now_ms=now,
    )
    assert "hypothetical" in row["latency_note"]


def test_al_no_double_spread_accounting_note():
    now = int(time.time() * 1000)
    row = evaluate_pair(
        HypotheticalDecision(now, "BTCUSDT", "BUY", 0.01, 100.1),
        _q(bid=100.0, ask=100.2),
        now_ms=now,
    )
    assert "spread_already_in_executable=True" in row["accounting_note"]


def test_al_vision_enriched_sidecar_nondestructive(tmp_path: Path):
    csv = (
        b"1700000000000,1,2,0.5,1.5,10,1700000060000,15.5,7,4,6.2,0\n"
    )
    rows = parse_klines_csv_vision(csv)
    assert len(rows) == 1
    assert rows[0]["quote_volume"] == 15.5
    assert rows[0]["number_of_trades"] == 7
    audit = audit_vision_loss_vs_v1_parser(csv)
    assert "quote_volume" in audit["v1_omits_when_present_in_csv"]
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        # Entorno local sin pyarrow: parser+audit bastan; Parquet se valida en imagen Docker.
        return
    meta = write_vision_ext_parquet("BTCUSDT", "1m", 2023, 11, rows, dest_dir=tmp_path)
    assert meta["replaces_v1_ohlcv"] is False
    assert Path(meta["path"]).exists()


def test_al_capture_plan_disk_estimate():
    est = estimate_disk_usage(CapturePlan(max_seconds=30, poll_interval_s=1))
    assert est["authorization_required_for_24_7"] is True
    assert est["within_cap"] is True


def test_al_docs_exist():
    d = ROOT / "docs" / "etapa_al"
    for name in (
        "AUDITORIA_V2.md",
        "LAB_CONTABILIDAD.md",
        "COMPARACION_V1_V2.md",
        "INFORME_ETAPA_AL.md",
    ):
        assert (d / name).is_file(), name


def test_al_v1_engine_untouched_signature():
    fill = estimate_fill_price(
        side="SELL",
        mid_or_ref=50.0,
        assumptions=ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0, spread_bps=0),
    )
    assert fill["ok"] and fill["price"] < 50.0
