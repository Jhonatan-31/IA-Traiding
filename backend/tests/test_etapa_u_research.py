"""Etapa U — hipótesis congeladas y backtest aislado no muta ledgers."""
from __future__ import annotations

from app.research.hypotheses_u import HYPOTHESES, list_hypotheses
from app.research.backtest_u import simulate_variant, _agg_15m


def _flat_candles(n=200, start=100.0):
    out = []
    px = start
    for i in range(n):
        px = start + (i % 20) * 0.05
        out.append(
            {
                "open_time": 1_700_000_000_000 + i * 60_000,
                "open": px,
                "high": px * 1.002,
                "low": px * 0.998,
                "close": px,
                "volume": 100.0 + (i % 5),
                "is_closed": True,
            }
        )
    return out


def test_hypotheses_frozen_and_named():
    hs = list_hypotheses()
    assert len(hs) >= 4
    assert all(h.get("frozen") is True for h in hs)
    ids = {h["id"] for h in hs}
    assert "U1_TREND15" in ids
    assert HYPOTHESES[0]["version"].startswith("u1_")


def test_simulate_variant_isolated_shape():
    c = _flat_candles(220)
    data = {"BTCUSDT": c, "ETHUSDT": c, "SOLUSDT": c}
    r = simulate_variant(data, variant="A_BASELINE", i0=80, i1=180)
    assert r["declare_profitable"] is False
    assert "net_vs_initial" in r
    assert r["buys"] >= 0
    r2 = simulate_variant(data, variant="U4_COOLDOWN", i0=80, i1=180)
    assert r2["variant"] == "U4_COOLDOWN"


def test_agg_15m_buckets():
    c = _flat_candles(45)
    a = _agg_15m(c)
    assert len(a) == 3
