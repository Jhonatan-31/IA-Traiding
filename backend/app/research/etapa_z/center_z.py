"""Payload UI — Laboratorio de Estrategias Avanzadas."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .hypotheses import list_hypotheses


def research_center_z(base: dict[str, Any], etapa_z: dict[str, Any] | None) -> dict[str, Any]:
    z = etapa_z or {}
    available = bool(z.get("available"))
    oos = z.get("oos") or {}
    rows = []
    for hid, pack in oos.items():
        rows.append(
            {
                "id": hid,
                "title": pack.get("title") or hid,
                "kind": pack.get("kind"),
                "tf": pack.get("tf"),
                "net": pack.get("net_vs_initial"),
                "drawdown": pack.get("max_drawdown"),
                "exposure": pack.get("avg_exposure"),
                "costs": pack.get("fees_and_frictions"),
                "sharpe": pack.get("sharpe_proxy"),
                "stress": pack.get("cost_stress_net"),
                "bars": pack.get("period_bars"),
                "weakness": (pack.get("meta") or {}).get("reject_if") or (pack.get("meta") or {}).get("warning"),
            }
        )
    lab = {
        "title": "Laboratorio de Estrategias Avanzadas",
        "available": available,
        "verdict": (z.get("claim") or {}).get("verdict") or "Pendiente de ejecutar Z",
        "reason": (z.get("claim") or {}).get("reason"),
        "experiment_id": z.get("experiment_id"),
        "config_hash": z.get("config_hash"),
        "executive": {
            "investigated": len(list_hypotheses()),
            "discarded": len((z.get("classification") or {}).get("discarded") or []),
            "exploratory": len((z.get("classification") or {}).get("exploratory") or []),
            "candidates": len((z.get("classification") or {}).get("candidates_for_virtual_validation") or []),
            "evidence_quality": "exploratoria" if available else "pendiente",
        },
        "comparison_rows": rows,
        "discarded": (z.get("classification") or {}).get("discarded") or [],
        "exploratory": (z.get("classification") or {}).get("exploratory") or [],
        "audit_ok": (z.get("audit_z0") or {}).get("continue_to_economic_research"),
        "micro_verdict": (z.get("microstructure") or {}).get("verdict"),
        "derivatives_verdict": (z.get("derivatives") or {}).get("verdict"),
        "adversarial_summary": (z.get("adversarial") or {}).get("summary"),
        "limitations": [
            "Holdout W consumido — sin OOS temporal virgen",
            "Universo solo BTC/ETH/SOL",
            "Sin BBO/libro histórico; spread proxy",
            "Sin activación automática",
        ],
        "hypotheses_human": [
            {
                "id": h["id"],
                "title": h.get("title"),
                "what": h.get("economic") or h.get("rule"),
                "kind": h.get("kind"),
            }
            for h in list_hypotheses()
        ],
    }
    return {
        **base,
        "etapa": "Z",
        "advanced_lab": lab,
        "etapa_z": {"available": available, "claim": z.get("claim")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa Z: laboratorio avanzado. "
            + str((z.get("claim") or {}).get("verdict") or "Ejecuta el laboratorio Z.")
            + " A y B detenidos. Sin activación."
        ),
    }


def attach_center_z(execute: Callable, *, base_builder: Callable, etapa_z=None, **kwargs):
    base = base_builder(execute, **kwargs)
    return research_center_z(base, etapa_z)
