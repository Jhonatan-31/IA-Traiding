"""Payload UI Etapa AB."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def research_center_ab(base: dict[str, Any], etapa_ab: dict[str, Any] | None) -> dict[str, Any]:
    ab = etapa_ab or {}
    available = bool(ab.get("available"))
    suite = ab.get("suite") or {}
    attr = ab.get("attribution") or {}
    comps = attr.get("components_usdt") or {}
    prospect = ab.get("prospect") or {}
    d = suite.get("D28H5") or {}
    eq = suite.get("Z-BH-EQ") or {}
    em = suite.get("EXP-MATCH-EQ") or {}
    cash = suite.get("CASH") or {}
    f55 = suite.get("FIXED-55-EQ") or {}

    value_panel = {
        "title": "¿La estrategia aporta valor o simplemente reduce el riesgo?",
        "available": available,
        "verdict": (ab.get("claim") or {}).get("verdict"),
        "d28h5_net": d.get("net_vs_initial"),
        "bh_eq_net": eq.get("net_vs_initial"),
        "exp_match_net": em.get("net_vs_initial"),
        "cash_net": cash.get("net_vs_initial"),
        "fixed55_net": f55.get("net_vs_initial"),
        "excess_vs_bh_eq": (attr.get("comparisons") or {}).get("vs_bh_eq_daily"),
        "excess_vs_exp_match": (attr.get("comparisons") or {}).get("vs_exp_match_descriptive"),
        "drawdown_d28": d.get("max_drawdown"),
        "drawdown_eq": eq.get("max_drawdown"),
        "costs": d.get("fees_and_frictions"),
        "turnover": d.get("turnover_events"),
        "cash_days": d.get("cash_days"),
        "avg_exposure": d.get("avg_exposure"),
        "selection_contribution": comps.get("active_selection_timing_vs_exp_match"),
        "exposure_contribution": comps.get("exposure_reduction_descriptive"),
        "market_contribution": comps.get("market_full_BH_EQ"),
        "warnings": [
            "Holdout AA consumido — AB es atribución descriptiva, no prueba independiente",
            "EXP-MATCH usa exposición media ex post",
            "No supera efectivo en la ventana AA",
        ],
        "labels": {
            "historical": "Resultados históricos (Z/AA)",
            "simulation": "Simulaciones / atribución AB",
            "prospect": "Observación prospectiva (no trading)",
            "virtual": "Operaciones virtuales — no en AB",
            "real": "Operaciones reales — inexistentes",
        },
    }
    obs = {
        "title": "Observación de señales futuras",
        "available": bool(prospect),
        "status": prospect.get("status"),
        "enabled": prospect.get("enabled"),
        "start_at": prospect.get("start_at"),
        "decisions": prospect.get("decisions_recorded"),
        "last_signal": prospect.get("last_signal"),
        "coverage": prospect.get("coverage"),
        "errors": prospect.get("errors"),
        "limitations": prospect.get("limitations"),
        "reason_disabled": prospect.get("reason_disabled"),
        "protocol_version": ((prospect.get("protocol") or {}).get("protocol_version")),
    }
    return {
        **base,
        "etapa": "AB",
        "value_vs_risk": value_panel,
        "prospect_observation": obs,
        "etapa_ab": {"available": available, "claim": ab.get("claim")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa AB: " + str(value_panel.get("verdict") or "Ejecuta análisis AB.") + " Sin activación."
        ),
    }
