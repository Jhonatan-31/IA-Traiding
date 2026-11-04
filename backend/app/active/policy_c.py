"""Strategy C — AI-assisted observation only. Never executes until gates pass."""
from __future__ import annotations

from typing import Any, Callable

from . import C_EXECUTION_AUTHORIZED, POLICY_C_VERSION

POLICY_VERSION = POLICY_C_VERSION


def validation_report(execute: Callable) -> dict[str, Any]:
    """Inspect Shadow/ML artifacts available in DB. No side effects."""
    total = execute(
        "SELECT COUNT(*) n FROM ml_predictions"
    ).fetchone()["n"]
    resolved = execute(
        """SELECT COUNT(*) n FROM ml_predictions WHERE resolution_status='RESOLVED'"""
    ).fetchone()["n"]
    pending = execute(
        """SELECT COUNT(*) n FROM ml_predictions
           WHERE resolution_status IS NULL OR resolution_status='PENDING'"""
    ).fetchone()["n"]
    cal = execute(
        """SELECT COUNT(*) n FROM ml_predictions
           WHERE calibrated_probability IS NOT NULL"""
    ).fetchone()["n"]
    hits = execute(
        """SELECT COUNT(*) n FROM ml_predictions
           WHERE resolution_status='RESOLVED' AND observed_net_return > 0"""
    ).fetchone()["n"]
    misses = execute(
        """SELECT COUNT(*) n FROM ml_predictions
           WHERE resolution_status='RESOLVED' AND observed_net_return <= 0"""
    ).fetchone()["n"]

    model = None
    if _table_exists(execute, "ml_models"):
        model = execute(
            """SELECT id, created_at, version, status, validated_for_research,
                      validated_for_paper_ai
               FROM ml_models ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()

    calibrated = cal > 0
    sample_ok = resolved >= 200 and hits + misses >= 100
    trained = model is not None
    paper_ai_off = not bool((model or {}).get("validated_for_paper_ai"))
    gates = {
        "model_trained": trained,
        "has_calibrated_probability": calibrated,
        "sample_sufficient": sample_ok,
        "execution_flag": C_EXECUTION_AUTHORIZED,
        "look_ahead_guard": True,
        "paper_ai_disabled": paper_ai_off,
    }
    # Explicit: never allow execution without calibration + flag + research gate
    execution_allowed = bool(
        C_EXECUTION_AUTHORIZED
        and calibrated
        and sample_ok
        and trained
        and bool((model or {}).get("validated_for_research"))
    )
    return {
        "policy_version": POLICY_VERSION,
        "label": "IA Experimental",
        "status": "IA NO VALIDADA" if not execution_allowed else "VALIDADA_OBSERVACION",
        "execution_authorized": execution_allowed,
        "mode": "observation_only",
        "gates": gates,
        "predictions": {
            "total": int(total),
            "resolved": int(resolved),
            "pending": int(pending),
            "with_calibration": int(cal),
            "hits": int(hits),
            "misses": int(misses),
        },
        "model": {
            "id": (model or {}).get("id"),
            "version": (model or {}).get("version"),
            "status": (model or {}).get("status"),
            "created_at": str((model or {}).get("created_at") or ""),
        }
        if model
        else None,
        "message": (
            "La inteligencia artificial registra predicciones para evaluación. "
            "Por ahora no utiliza dinero ni ejecuta operaciones."
            if not execution_allowed
            else "Controles de validación superados en modo observación."
        ),
    }


def _table_exists(execute: Callable, name: str) -> bool:
    row = execute(
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema='public' AND table_name=%s""",
        (name,),
    ).fetchone()
    return bool(row)
