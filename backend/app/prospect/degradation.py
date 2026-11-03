"""Degradation / anomaly alerts — documented thresholds, no auto-retrain."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

# Documented thresholds (Etapa I)
THRESHOLDS = {
    "scheduler_stale_s": 900,  # no heartbeat → ERROR
    "scheduler_warn_s": 600,
    "invalid_rate_warn": 0.20,  # invalid / (resolved+invalid)
    "min_resolved_for_invalid_rate": 20,
    "api_errors_24h_warn": 10,
    "no_retrain_on_alert": True,
}


def upsert_alert(
    execute: Callable,
    *,
    code: str,
    severity: str,
    message: str,
    evidence: dict,
) -> None:
    existing = execute(
        "SELECT id FROM prospect_alerts WHERE code=%s AND status='OPEN'",
        (code,),
    ).fetchone()
    if existing:
        execute(
            """UPDATE prospect_alerts SET message=%s, evidence_json=%s::jsonb, severity=%s
               WHERE id=%s""",
            (message, json.dumps(evidence), severity, existing["id"]),
        )
    else:
        execute(
            """INSERT INTO prospect_alerts(code, severity, message, evidence_json, status)
               VALUES(%s,%s,%s,%s::jsonb,'OPEN')
               ON CONFLICT DO NOTHING""",
            (code, severity, message, json.dumps(evidence)),
        )


def clear_alert(execute: Callable, code: str) -> None:
    execute(
        """UPDATE prospect_alerts SET status='CLEARED'
           WHERE code=%s AND status='OPEN'""",
        (code,),
    )


def evaluate_degradation(execute: Callable) -> dict[str, Any]:
    """Inspect scheduler + prospect quality; open/clear alerts. Never retrains."""
    now = datetime.now(timezone.utc)
    state = execute("SELECT * FROM shadow_scheduler_state WHERE id=1").fetchone()
    counts = execute(
        """SELECT resolution_status, COUNT(*) AS n FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE'
           GROUP BY resolution_status"""
    )
    cdict = {r["resolution_status"]: int(r["n"]) for r in counts}
    resolved = cdict.get("RESOLVED", 0)
    invalid = cdict.get("INVALID", 0)
    pending = cdict.get("PENDING", 0)

    opened = []
    cleared = []

    # Scheduler heartbeat
    if not state or not state.get("heartbeat_at"):
        upsert_alert(
            execute,
            code="scheduler_no_heartbeat",
            severity="ERROR",
            message="Shadow scheduler sin heartbeat registrado.",
            evidence={"state": dict(state) if state else None, "thresholds": THRESHOLDS},
        )
        opened.append("scheduler_no_heartbeat")
    else:
        hb = state["heartbeat_at"]
        if getattr(hb, "tzinfo", None) is None:
            hb = hb.replace(tzinfo=timezone.utc)
        age = (now - hb).total_seconds()
        if age > THRESHOLDS["scheduler_stale_s"]:
            upsert_alert(
                execute,
                code="scheduler_stale",
                severity="ERROR",
                message=f"Heartbeat del scheduler atrasado {int(age)}s.",
                evidence={"age_s": age, "threshold": THRESHOLDS["scheduler_stale_s"]},
            )
            opened.append("scheduler_stale")
            clear_alert(execute, "scheduler_no_heartbeat")
        elif age > THRESHOLDS["scheduler_warn_s"]:
            upsert_alert(
                execute,
                code="scheduler_stale",
                severity="WARNING",
                message=f"Heartbeat del scheduler atrasado {int(age)}s (aviso).",
                evidence={"age_s": age, "threshold": THRESHOLDS["scheduler_warn_s"]},
            )
            opened.append("scheduler_stale")
        else:
            clear_alert(execute, "scheduler_stale")
            clear_alert(execute, "scheduler_no_heartbeat")
            cleared.extend(["scheduler_stale", "scheduler_no_heartbeat"])

    # Invalid rate
    denom = resolved + invalid
    if denom >= THRESHOLDS["min_resolved_for_invalid_rate"]:
        rate = invalid / denom
        if rate >= THRESHOLDS["invalid_rate_warn"]:
            upsert_alert(
                execute,
                code="high_invalid_rate",
                severity="WARNING",
                message=f"Tasa de decisiones inválidas {rate:.1%} ≥ umbral.",
                evidence={"rate": rate, "resolved": resolved, "invalid": invalid},
            )
            opened.append("high_invalid_rate")
        else:
            clear_alert(execute, "high_invalid_rate")
            cleared.append("high_invalid_rate")

    # Scheduler status ERROR
    if state and state.get("status") == "ERROR":
        upsert_alert(
            execute,
            code="scheduler_error",
            severity="ERROR",
            message=state.get("last_error") or "Scheduler en ERROR",
            evidence={"status": state.get("status"), "last_error": state.get("last_error")},
        )
        opened.append("scheduler_error")
    else:
        clear_alert(execute, "scheduler_error")
        cleared.append("scheduler_error")

    alerts = list(
        execute(
            """SELECT * FROM prospect_alerts WHERE status='OPEN'
               ORDER BY id DESC LIMIT 50"""
        )
    )
    return {
        "thresholds": THRESHOLDS,
        "opened_or_updated": opened,
        "cleared": cleared,
        "open_alerts": [dict(a) for a in alerts],
        "counts": {"pending": pending, "resolved": resolved, "invalid": invalid},
        "auto_retrain": False,
        "note": "Deterioro no dispara reentrenamiento automático.",
    }
