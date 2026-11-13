"""Etapa AB — atribución, benchmarks, prospecto, aislamiento."""
from __future__ import annotations

from app.research.etapa_ab import ACTIVATE_FORBIDDEN, EXPECTED_CONFIG_HASH, PAPER_ONLY
from app.research.etapa_ab.attribution import attribute_aa_window
from app.research.etapa_ab.prospect import OBSERVATION_ENABLED, frozen_protocol
from app.research.etapa_ab.simulate_ledger import COST_FRAC, trade_cost
from app.research.etapa_z.engine import make_tsmom
from app.research.etapa_ab.simulate_ledger import simulate_ledger


def test_ab_safety():
    assert PAPER_ONLY is True
    assert ACTIVATE_FORBIDDEN is True
    assert EXPECTED_CONFIG_HASH == "5326edb8a539cfe5"
    assert OBSERVATION_ENABLED is False


def test_trade_cost_components():
    c = trade_cost(1000.0)
    assert abs(c - 1000.0 * COST_FRAC) < 1e-9


def test_attribution_reconciles():
    suite = {
        "D28H5": {"net_vs_initial": -100.0, "fees_and_frictions": 50.0, "equity_final": 900.0},
        "Z-BH-EQ": {"net_vs_initial": -400.0},
        "EXP-MATCH-EQ": {"net_vs_initial": -200.0},
        "CASH": {"net_vs_initial": 0.0},
        "BH-EQ-HOLD": {"net_vs_initial": -390.0},
        "FIXED-55-EQ": {"net_vs_initial": -220.0},
        "VOL-SCALE-EQ": {"net_vs_initial": -180.0},
    }
    a = attribute_aa_window(suite)
    assert a["reconcile_ok"] is True
    assert a["components_usdt"]["d28h5_net"] == -100.0


def test_causal_weights_no_future():
    # make_tsmom only uses closes[i-lb:i]
    closes = {
        "BTCUSDT": [100.0 + i for i in range(40)],
        "ETHUSDT": [50.0 + i * 0.5 for i in range(40)],
        "SOLUSDT": [10.0 + i * 0.1 for i in range(40)],
    }
    w = make_tsmom(28)
    # mutating future should not change weight at i=30
    w1 = w(30, closes)
    closes["BTCUSDT"][39] = 1e9
    w2 = w(30, closes)
    assert w1 == w2


def test_prospect_protocol_frozen():
    p = frozen_protocol()
    assert p["horizon_calendar_days"] == 90
    assert p["aa_holdout_reuse_forbidden"] is True
    assert p["primary_benchmark"] == "FIXED-55-EQ"


def test_ledger_flat_market_near_zero():
    n = 50
    times = list(range(n))
    flat = {s: [100.0] * n for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    r = simulate_ledger(times, flat, make_tsmom(28), i0=30, i1=n)
    assert abs(r["net_vs_initial"]) < 2.0
    assert r["avg_exposure"] < 0.05
