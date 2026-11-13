"""Etapa AA — freeze, causalidad sintética, decisión, aislamiento."""
from __future__ import annotations

from app.research.etapa_aa import (
    ACTIVATE_FORBIDDEN,
    EXPECTED_CONFIG_HASH,
    PAPER_ONLY,
    TARGET_ID,
)
from app.research.etapa_aa.adversarial import adversarial_aa
from app.research.etapa_aa.freeze import verify_freeze
from app.research.etapa_aa.run_aa import decide
from app.research.etapa_aa.stats import block_bootstrap_mean_diff
from app.research.etapa_aa.synthetic import run_synthetic_suite


def test_aa_safety_flags():
    assert PAPER_ONLY is True
    assert ACTIVATE_FORBIDDEN is True
    assert TARGET_ID == "Z-TSMOM-D28H5"
    assert EXPECTED_CONFIG_HASH == "5326edb8a539cfe5"


def test_aa_freeze_hash():
    f = verify_freeze()
    assert f["ok"] is True
    assert f["hash_match"] is True
    assert f["config_hash"] == EXPECTED_CONFIG_HASH
    assert f["executable_behavior"]["min_hold_in_code"] is False


def test_aa_synthetic_suite():
    s = run_synthetic_suite()
    assert s["ok"] is True
    assert s["n_ok"] == s["n_cases"]


def test_aa_bootstrap_small_sample():
    r = block_bootstrap_mean_diff([0.01] * 5, [0.0] * 5)
    assert r["ok"] is False


def test_aa_decide_rejects_negative_excess():
    eval_pack = {
        "primary": {"excess_net": -10.0},
        "results": {
            "Z-TSMOM-D28H5": {
                "max_drawdown": 0.1,
                "cost_stress_net": -5.0,
                "avg_exposure": 0.9,
            },
            "Z-BH-EQ": {"max_drawdown": 0.1, "avg_exposure": 0.9},
        },
        "period": {"n_bars": 200},
    }
    d = decide(eval_pack, {"blocks_promotion": False}, {}, {"label": "evaluacion_temporal_nueva_previa_no_utilizada"})
    assert d["verdict"] == "RECHAZADA"
    assert d["activate"] is False


def test_aa_adversarial_blocks_when_no_excess():
    pack = {
        "primary": {"excess_net": -1.0, "d28h5_net": 5.0},
        "results": {
            "Z-TSMOM-D28H5": {
                "net_vs_initial": 5.0,
                "cost_stress_net": 3.0,
                "turnover_events": 20,
                "avg_exposure": 0.9,
            },
            "Z-BH-EQ": {"net_vs_initial": 6.0, "avg_exposure": 0.9},
            "Z-BH-BTC": {"net_vs_initial": 1.0},
        },
    }
    adv = adversarial_aa(pack, freeze_ok=True)
    assert adv["blocks_promotion"] is True
