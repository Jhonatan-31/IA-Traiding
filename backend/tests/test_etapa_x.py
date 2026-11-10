"""Etapa X — regímenes causales, segmentos y unidades."""
from __future__ import annotations

from app.research.history.diagnose_x import (
    HOLDOUT_W_CONSUMED,
    MIN_SEGMENT_N,
    _units_note,
    block_bootstrap_expectancy,
)
from app.research.history.regimes_x import classify_regime_x


def _bars(n: int = 80, trend: float = 0.0):
    rows = []
    px = 100.0
    for i in range(n):
        px = px * (1 + trend)
        rows.append(
            {
                "open_time": 1_700_000_000_000 + i * 3_600_000,
                "open": px,
                "high": px * 1.002,
                "low": px * 0.998,
                "close": px,
                "volume": 10.0 + (5.0 if i % 7 == 0 else 0.0),
                "is_closed": True,
            }
        )
    return rows


def test_regime_causal_and_volume():
    r = classify_regime_x(_bars(80, trend=0.0))
    assert r["look_ahead_safe"] is True
    assert "volume" in r
    assert r["regime_tv"].count("|") == 1


def test_holdout_w_consumed_flag():
    assert HOLDOUT_W_CONSUMED is True
    assert MIN_SEGMENT_N == 30


def test_units_are_usdt_not_percent_by_default():
    u = _units_note()
    assert "USDT" in u["net_pnl"]
    assert "parquet" in u["source"].lower() or "Parquet" in u["source"]


def test_block_bootstrap_small_sample():
    assert block_bootstrap_expectancy([0.1, -0.1], block=5)["ok"] is False
    boot = block_bootstrap_expectancy([0.1] * 40 + [-0.05] * 10, block=5, n_boot=50)
    assert boot["ok"] is True
    assert "ci95" in boot
