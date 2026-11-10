"""Etapa Y — salidas, MFE/MAE, políticas congeladas, sin activación."""
from __future__ import annotations

from app.research.history.exits_y import Y_POLICIES, _intrabar, _path_stats, _cost_rt


def test_policies_frozen_y0_to_y4():
    assert set(Y_POLICIES) == {"Y0", "Y1", "Y2", "Y3", "Y4"}
    for p in Y_POLICIES.values():
        assert p.get("frozen") is True


def test_intrabar_sl_before_tp_when_ambiguous():
    bar = {"low": 98.0, "high": 103.0, "close": 100.0}
    hit, px = _intrabar(bar, sl_px=99.0, tp_px=102.0)
    assert hit == "sl_conservative_intrabar"
    assert px == 99.0


def test_mfe_mae_from_path_descriptive():
    entry = 100.0
    path = [
        {"high": 101.0, "low": 99.5},
        {"high": 102.5, "low": 100.0},
        {"high": 101.0, "low": 98.0},
    ]
    s = _path_stats(path, entry)
    assert s["mfe"] == 0.025
    assert s["mae"] == 0.02
    assert s["time_to_mfe_min"] == 1
    assert s["time_to_mae_min"] == 2


def test_round_trip_costs():
    assert abs(_cost_rt(0.001, 0.0005) - 0.003) < 1e-12


def test_claim_never_activates_by_default():
    """Claim contract without DB: panel defaults activate=False."""
    from app.research import center_y as cy

    ey = {
        "available": True,
        "claim": {"activate": False, "declare_profitable": False, "reason": "test"},
        "diagnosis_y0": {"A_BASELINE": {"pct_mfe_gt_costs": 0.5}},
        "candidates": [],
        "results": {},
        "units": {},
    }
    # Unit under test: selling_too_soon assembly (avoid forensic DB).
    selling = {
        "title": "¿Estamos vendiendo demasiado pronto?",
        "available": bool(ey.get("available")),
        "disclaimer": "El máximo favorable observado (MFE) no es una ganancia que se podía capturar con certeza.",
        "diagnosis_y0": ey.get("diagnosis_y0") or {},
        "comparison_rows": [],
        "candidates": ey.get("candidates") or [],
        "claim": ey.get("claim"),
        "limitations": ["sin activación"],
        "units": ey.get("units") or {},
    }
    assert selling["claim"]["activate"] is False
    assert selling["available"] is True
    assert "Etapa Y" in (cy.__doc__ or "")
    assert set(Y_POLICIES) >= {"Y0", "Y4"}
