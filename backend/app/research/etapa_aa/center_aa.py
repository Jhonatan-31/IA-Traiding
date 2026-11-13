"""Payload UI — Validación independiente."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def research_center_aa(base: dict[str, Any], etapa_aa: dict[str, Any] | None) -> dict[str, Any]:
    aa = etapa_aa or {}
    available = bool(aa.get("available"))
    primary = ((aa.get("evaluation") or {}).get("primary")) or {}
    period = ((aa.get("evaluation") or {}).get("period")) or {}
    decision = aa.get("decision") or aa.get("claim") or {}
    curves = aa.get("equity_curves") or {}

    def _spark(curve: list[dict]) -> list[dict]:
        # downsample for UI
        if not curve:
            return []
        step = max(1, len(curve) // 120)
        return [{"iso": c["iso"], "equity": c["equity"]} for c in curve[::step]]

    panel = {
        "title": "Validación independiente",
        "available": available,
        "strategy": "Z-TSMOM-D28H5",
        "version_hash": aa.get("config_hash"),
        "hash_match": aa.get("hash_match"),
        "period": period,
        "independence": ((aa.get("ingest") or {}).get("independence") or {}).get("label"),
        "verdict": decision.get("verdict") or (aa.get("claim") or {}).get("verdict"),
        "reason": (aa.get("claim") or {}).get("reason"),
        "d28h5_net": primary.get("d28h5_net"),
        "bh_eq_net": primary.get("bh_eq_net"),
        "excess_net": primary.get("excess_net"),
        "d28h5_dd": primary.get("d28h5_dd"),
        "bh_eq_dd": primary.get("bh_eq_dd"),
        "d28h5_exposure": primary.get("d28h5_exposure"),
        "bh_eq_exposure": primary.get("bh_eq_exposure"),
        "d28h5_costs": primary.get("d28h5_costs"),
        "bh_eq_costs": primary.get("bh_eq_costs"),
        "consumed": True if available else False,
        "stats": aa.get("stats"),
        "adversarial_summary": (aa.get("adversarial") or {}).get("summary"),
        "z_reconcile": aa.get("z_reconcile"),
        "equity_spark": {
            "d28h5": _spark(curves.get("Z-TSMOM-D28H5") or []),
            "bh_eq": _spark(curves.get("Z-BH-EQ") or []),
        },
        "labels": {
            "exploratory_z": "Investigación histórica exploratoria (Etapa Z)",
            "temporal_aa": "Validación temporal (Etapa AA)",
            "paper_trial": "Prueba prospectiva PAPER — no autorizada aquí",
        },
        "limitations": [
            "Evaluación consumida — no reutilizar como nueva prueba independiente",
            "Sin BBO histórico",
            "Universo N=3",
            "Sin activación automática",
        ],
    }
    return {
        **base,
        "etapa": "AA",
        "independent_validation": panel,
        "etapa_aa": {"available": available, "claim": aa.get("claim")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa AA: validación temporal de D28H5. "
            + str(panel.get("verdict") or "Ejecuta validación AA.")
            + " A y B detenidos. Sin activación."
        ),
    }
