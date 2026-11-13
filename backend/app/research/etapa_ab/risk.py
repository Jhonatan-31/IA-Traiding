"""AB4 — riesgo y preservación de capital."""
from __future__ import annotations

from typing import Any


def analyze_risk(suite: dict[str, Any], attr: dict[str, Any]) -> dict[str, Any]:
    d = suite["D28H5"]
    eq = suite["Z-BH-EQ"]
    em = suite["EXP-MATCH-EQ"]
    comps = attr.get("components_usdt") or {}
    active = comps.get("active_selection_timing_vs_exp_match") or 0
    exp_eff = comps.get("exposure_reduction_descriptive") or 0

    protection_by_exposure = abs(exp_eff) >= abs(active) and exp_eff > 0
    return {
        "d28h5": {
            "max_drawdown": d.get("max_drawdown"),
            "dd_duration_bars": d.get("max_dd_duration_bars"),
            "avg_exposure": d.get("avg_exposure"),
            "cash_days": d.get("cash_days"),
            "worst_week": d.get("worst_week"),
            "worst_month": d.get("worst_month"),
            "final_weights": d.get("final_weights"),
            "vol_daily": d.get("vol_daily"),
        },
        "bh_eq": {
            "max_drawdown": eq.get("max_drawdown"),
            "avg_exposure": eq.get("avg_exposure"),
            "worst_week": eq.get("worst_week"),
        },
        "exp_match": {
            "max_drawdown": em.get("max_drawdown"),
            "avg_exposure": em.get("avg_exposure"),
            "net": em.get("net_vs_initial"),
        },
        "counterfactual": {
            "question": "¿Protección = menor exposición o selección adicional?",
            "exposure_reduction_usdt": exp_eff,
            "active_vs_same_exposure_usdt": active,
            "conclusion": (
                "VENTAJA RELATIVA EXPLICADA POR MENOR EXPOSICIÓN"
                if protection_by_exposure
                else (
                    "POSIBLE VALOR ADICIONAL, AÚN NO VALIDADO"
                    if active > 5
                    else "SIN VENTAJA DEMOSTRADA"
                )
            ),
            "caveat": "EXP-MATCH es descriptivo (exposición media ex post). FIXED-55/VOL-SCALE son controles causales.",
        },
        "concentration": d.get("final_weights"),
        "regime_note": "Mercado AA bajista Spot; protección relativa vs BH-EQ no implica alpha en alcistas.",
    }
