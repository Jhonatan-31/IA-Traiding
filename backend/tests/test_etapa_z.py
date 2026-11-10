"""Etapa Z — auditoría, causalidad, hipótesis congeladas, sin activación."""
from __future__ import annotations

from app.research.etapa_z import ACTIVATE_FORBIDDEN, COST_RT, HOLDOUT_W_CONSUMED, PAPER_ONLY
from app.research.etapa_z.adversarial import adversarial_review
from app.research.etapa_z.audit_z0 import _check_lookahead_contract
from app.research.etapa_z.hypotheses import HYPOTHESES
from app.research.history.aggregate import aggregate_bars


def test_safety_flags():
    assert PAPER_ONLY is True
    assert ACTIVATE_FORBIDDEN is True
    assert HOLDOUT_W_CONSUMED is True
    assert COST_RT > 0


def test_hypotheses_frozen_and_limited():
    assert len(HYPOTHESES) <= 8
    for h in HYPOTHESES.values():
        assert h.get("frozen") is True


def test_aggregation_no_lookahead_close():
    rows = []
    t0 = 1_730_419_200_000  # aligned
    px = 100.0
    for i in range(60 * 24):
        ot = t0 + i * 60_000
        rows.append(
            {
                "open_time": ot,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + (0.1 if i == 60 * 24 - 1 else 0.0),
                "volume": 1.0,
                "is_closed": True,
            }
        )
    d1 = aggregate_bars(rows, "1d")
    assert len(d1) == 1
    assert d1[0]["is_closed"] is True
    assert abs(float(d1[0]["close"]) - (px + 0.1)) < 1e-9


def test_causality_contract():
    c = _check_lookahead_contract()
    assert c["ok"] is True
    assert c["holdout_w_consumed"] is True


def test_adversarial_blocks_negative():
    fake = {
        "oos": {
            "Z-BH-EQ": {"kind": "benchmark", "ok": True, "net_vs_initial": 10.0},
            "Z-TSMOM-D28H5": {
                "kind": "hypothesis",
                "ok": True,
                "net_vs_initial": -5.0,
                "cost_stress_net": -8.0,
                "avg_exposure": 0.5,
                "turnover_events": 20,
            },
        }
    }
    adv = adversarial_review(fake)
    assert adv["promote_any"] is False
    assert any(f["blocks_promotion"] for f in adv["findings"])
