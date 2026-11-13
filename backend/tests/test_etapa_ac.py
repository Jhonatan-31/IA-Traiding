"""Etapa AC — reconciliación AB, campos Vision, prospect disabled, hallazgos."""
from __future__ import annotations

import inspect

from app.research.etapa_ab.prospect import OBSERVATION_ENABLED
from app.research.etapa_ac import EXPECTED_CONFIG_HASH, PROSPECT_MUST_REMAIN
from app.research.etapa_ac.findings import findings_summary
from app.research.etapa_ac.reconcile_ab import reconcile_ab_economics
from app.research.history import download as hist_download
from app.research.history import store as hist_store


def test_ac_prospect_disabled():
    assert OBSERVATION_ENABLED is False
    assert PROSPECT_MUST_REMAIN == "PREPARED_DISABLED"
    assert EXPECTED_CONFIG_HASH == "5326edb8a539cfe5"


def test_ac_findings_have_priorities():
    s = findings_summary()
    assert s["n"] >= 8
    assert "P0" in s["by_priority"] or "P1" in s["by_priority"]
    for f in s["items"]:
        assert f["id"].startswith("AC-F")
        assert f["priority"] in {"P0", "P1", "P2", "P3"}


def test_vision_fields_dropped_in_parser():
    """Binance Vision CSV tiene ≥11 columnas; el parser solo conserva OHLCV."""
    src = inspect.getsource(hist_download.parse_klines_csv)
    assert "taker" not in src.lower()
    assert "quote_volume" not in src
    assert '"volume"' in src or "'volume'" in src
    store_src = inspect.getsource(hist_store.write_month_parquet)
    assert "taker" not in store_src.lower()
    assert "quote_volume" not in store_src


def test_parse_klines_ignores_extra_columns():
    # open_time,o,h,l,c,volume,close_time,quote,trades,taker_base,taker_quote,ignore
    raw = (
        b"1609459200000,100,110,90,105,12.5,1609545599999,1000.0,42,5.0,400.0,0\n"
    )
    rows = hist_download.parse_klines_csv(raw)
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"open_time", "open", "high", "low", "close", "volume", "is_closed"}
    assert rows[0]["volume"] == 12.5


def test_ac_p0_patterns_remediated_in_ad():
    """AC P0 documentados; AD debe haber mitigado early-return y compra no atómica."""
    import inspect

    from app.active import engine as active_engine
    from app.active import B_EXECUTION_AUTHORIZED
    from app.demo import engine as demo_engine
    from app.market_stream import aggregator as agg

    demo_src = inspect.getsource(demo_engine._try_buy)
    assert "SAVEPOINT ad_buy_atomic" in demo_src
    assert "buy_atomic_rollback" in demo_src
    assert "all_in_price_no_double_fee" in demo_src
    act_src = inspect.getsource(active_engine.run_cycle)
    assert "b_entries_not_authorized" in act_src
    assert "protective_exits_still_evaluated" in act_src
    assert 'b_execution_not_authorized' not in act_src
    assert B_EXECUTION_AUTHORIZED is True
    assert getattr(agg, "_MAX_SEEN_IDS", 0) == 4096
    buy_src = inspect.getsource(active_engine._try_buy)
    assert "SAVEPOINT ad_buy_atomic" in buy_src


def test_reconcile_ab_if_artifact_present():
    from pathlib import Path

    paths = [
        Path("/artifacts/history/etapa_ab_results.json"),
        Path("data/market_history/etapa_ab_results.json"),
    ]
    if not any(p.is_file() for p in paths):
        return  # skip silently if no artifact in unit env
    r = reconcile_ab_economics()
    assert r["attribution"]["residual"] in {"0", "0.0", "0.0000"} or float(r["attribution"]["residual"]) == 0.0
    assert r["ok"] is True
    assert "90.7526" in r["pl"]["vs_fixed55"] or float(r["pl"]["vs_fixed55"]) > 90.0
