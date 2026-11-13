"""Atribución económica reconciliable (orden documentado)."""
from __future__ import annotations

from typing import Any


def attribute_aa_window(suite: dict[str, Any]) -> dict[str, Any]:
    """Orden de atribución (AA holdout — descriptivo, no nueva prueba independiente):

    1. Efectivo = 0
    2. Efecto mercado a plena exposición ≈ P/L(Z-BH-EQ)
    3. Efecto menor exposición media (descriptivo) = P/L(EXP-MATCH) − P/L(BH-EQ)
    4. Efecto activo vs misma exposición media = P/L(D28H5) − P/L(EXP-MATCH)
    5. Costos D28H5 (ya neteados en P/L; reportados aparte)
    6. Chequeo: (2)+(3)+(4) ≈ P/L(D28H5)  [respecto a cash]
    """
    d = suite["D28H5"]
    eq = suite["Z-BH-EQ"]
    em = suite["EXP-MATCH-EQ"]
    cash = suite["CASH"]
    hold = suite.get("BH-EQ-HOLD") or {}
    fixed = suite.get("FIXED-55-EQ") or {}
    vol = suite.get("VOL-SCALE-EQ") or {}

    pl_d = d["net_vs_initial"]
    pl_eq = eq["net_vs_initial"]
    pl_em = em["net_vs_initial"]
    pl_cash = cash["net_vs_initial"]

    market_full = pl_eq - pl_cash
    exposure_effect = pl_em - pl_eq  # en bear: positivo si menor exposición ayuda
    active_vs_exp = pl_d - pl_em
    sum_parts = market_full + exposure_effect + active_vs_exp
    residual = round(pl_d - sum_parts, 6)

    # costos: ya dentro del neto; gross = net + costs
    costs = d.get("fees_and_frictions") or 0.0
    gross = pl_d + costs

    return {
        "order": [
            "cash_baseline",
            "market_full_exposure_BH_EQ",
            "lower_avg_exposure_descriptive_EXP_MATCH",
            "active_vs_same_avg_exposure",
            "costs_reported_separately_already_in_net",
        ],
        "components_usdt": {
            "cash": pl_cash,
            "market_full_BH_EQ": round(market_full, 4),
            "exposure_reduction_descriptive": round(exposure_effect, 4),
            "active_selection_timing_vs_exp_match": round(active_vs_exp, 4),
            "sum_to_d28h5": round(sum_parts, 4),
            "d28h5_net": pl_d,
            "residual": residual,
        },
        "reconcile_ok": abs(residual) < 0.05,
        "costs": {
            "d28h5_frictions": costs,
            "gross_approx_net_plus_costs": round(gross, 4),
            "note": "costos ya deducidos en net_vs_initial; no sumar otra vez al P/L",
        },
        "comparisons": {
            "vs_cash": round(pl_d - pl_cash, 4),
            "vs_bh_eq_daily": round(pl_d - pl_eq, 4),
            "vs_bh_eq_hold": round(pl_d - (hold.get("net_vs_initial") or 0), 4),
            "vs_exp_match_descriptive": round(pl_d - pl_em, 4),
            "vs_fixed_55_causal": round(pl_d - (fixed.get("net_vs_initial") or 0), 4),
            "vs_vol_scale_causal": round(pl_d - (vol.get("net_vs_initial") or 0), 4),
        },
        "interpretation": {
            "exposure_drives_protection": exposure_effect > 0 and abs(exposure_effect) > abs(active_vs_exp),
            "active_adds_value_vs_same_exposure": active_vs_exp > 5.0,
            "beats_cash": pl_d > pl_cash,
            "beats_bh_eq": pl_d > pl_eq,
            "note": (
                "EXP-MATCH usa exposición media ex post → control descriptivo. "
                "FIXED-55 y VOL-SCALE son causalmente implementables."
            ),
        },
        "accounting": d.get("accounting")
        or {
            "initial": 1000.0,
            "final": d.get("equity_final"),
            "net": pl_d,
            "costs": costs,
        },
    }
