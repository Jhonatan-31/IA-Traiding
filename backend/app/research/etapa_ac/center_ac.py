"""Payload UI — Auditoría profesional + origen ventaja D28H5."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def research_center_ac(base: dict[str, Any], etapa_ac: dict[str, Any] | None) -> dict[str, Any]:
    ac = etapa_ac or {}
    available = bool(ac.get("available"))
    eco = (ac.get("economic") or {}).get("reconcile") or {}
    pl = eco.get("pl") or {}
    attr = eco.get("attribution") or {}
    costs = eco.get("costs") or {}
    findings = ac.get("findings") or {}
    verdicts = ac.get("verdicts") or {}

    audit_panel = {
        "title": "Auditoría profesional del sistema",
        "available": available,
        "verdicts": verdicts,
        "runners_down": ac.get("runners_down") or [],
        "f01_critical_now": ac.get("f01_critical_now"),
        "positions": ac.get("positions"),
        "findings_n": findings.get("n"),
        "by_priority": findings.get("by_priority"),
        "top_findings": [
            {"id": f["id"], "priority": f["priority"], "title": f["title"]}
            for f in (findings.get("top10") or [])[:8]
        ],
        "prospect_status": (ac.get("prospect") or {}).get("status"),
        "hash_match": ac.get("hash_match"),
    }
    advantage_panel = {
        "title": "¿De dónde viene la ventaja de D28H5?",
        "available": available and bool(pl),
        "verdict": (ac.get("economic") or {}).get("verdict"),
        "d28h5_net": pl.get("d28h5"),
        "fixed55_net": pl.get("fixed55"),
        "bh_eq_net": pl.get("bh_eq"),
        "cash_net": pl.get("cash"),
        "diff_vs_fixed55": pl.get("vs_fixed55"),
        "diff_vs_bh_eq": pl.get("vs_bh_eq"),
        "market_component": attr.get("market_full_bh_eq"),
        "exposure_component": attr.get("exposure_reduction_descriptive"),
        "active_component": attr.get("active_vs_exp_match"),
        "residual": attr.get("residual"),
        "costs_total": costs.get("total"),
        "cost_split": {k: costs.get(k) for k in ("fee", "slip", "spread")},
        "limitations": [
            "Holdout AA consumido — no es prueba independiente nueva",
            "P/L absoluto negativo vs efectivo",
            "Simulador sin BBO histórico",
            "AB-PROSPECT desactivado",
        ],
        "labels": {
            "exploratory": "Historial exploratorio Z",
            "holdout": "Holdout AA consumido",
            "attribution": "Atribución AB/AC descriptiva",
            "prospect": "Observación prospectiva desactivada",
            "paper": "PAPER — no autorizado aquí",
            "real": "Operaciones reales inexistentes",
        },
    }
    return {
        **base,
        "etapa": "AC",
        "system_audit": audit_panel,
        "d28h5_advantage": advantage_panel,
        "etapa_ac": {"available": available, "claim": ac.get("claim")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa AC: auditoría institucional. "
            + str((ac.get("economic") or {}).get("verdict") or "")
            + " Sin activación."
        ),
    }
