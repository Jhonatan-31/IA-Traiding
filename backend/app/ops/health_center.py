"""Continuity / protection status — evidence-based; container Up ≠ healthy."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

from .continuity import classify_gap, heartbeat_gap_seconds, reconcile_after_gap

# Thresholds (seconds) — configurable via env after measuring legitimate intervals.
DEMO_EVERY_S = float(os.environ.get("DEMO_EVERY_SECONDS", "60"))
ACTIVE_EVERY_S = float(os.environ.get("ACTIVE_EVERY_SECONDS", "60"))
WORKER_EVERY_S = float(os.environ.get("SCAN_EVERY_SECONDS", "3600"))
SHADOW_EVERY_S = float(os.environ.get("SHADOW_EVERY_SECONDS", "300"))
LAB_EVERY_S = float(os.environ.get("LAB_EVERY_SECONDS", "300"))
STALE_PRICE_S = float(os.environ.get("AE_STALE_PRICE_SECONDS", "120"))
DEPLOY_COMMIT = os.environ.get("DEPLOY_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "unknown"


def protection_status(
    *,
    bot_status: str | None,
    open_positions: int,
    gap: dict[str, Any],
    price_stale: bool,
    entries_authorized: bool | None = None,
) -> dict[str, Any]:
    """
    Separate ENTRIES from PROTECTION capacity.

    ENTRIES_DISABLED: strategy STOPPED or entries not authorized.
    PROTECTION_AVAILABLE / DEGRADED / UNAVAILABLE based on supervisor evidence.
    """
    status = (bot_status or "UNKNOWN").upper()
    entries = "ENTRIES_DISABLED" if status != "RUNNING" else "ENTRIES_ENABLED"
    if entries_authorized is False:
        entries = "ENTRIES_DISABLED"

    if open_positions <= 0:
        # No open risk — supervisor health still reported separately.
        prot = "SIN_POSICIONES_QUE_PROTEGER"
        note = "ausencia_de_posiciones_no_prueba_stop_loss_ni_supervisor_sano"
    elif gap.get("status") == "OK" and not price_stale:
        prot = "PROTECTION_AVAILABLE"
        note = "heartbeat_fresco_y_precios_ok"
    elif gap.get("status") in ("WARNING", "UNKNOWN") or price_stale:
        prot = "PROTECTION_DEGRADED"
        note = "datos_o_heartbeat_degradados"
    else:
        prot = "PROTECTION_UNAVAILABLE"
        note = "no_se_puede_evaluar_salida_protectora"

    return {
        "entries": entries,
        "protection": prot,
        "bot_status": status,
        "open_positions": open_positions,
        "note": note,
        "claims_continuous_coverage": prot == "PROTECTION_AVAILABLE",
    }


def ensure_continuity_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS continuity_gap_events(
            id BIGSERIAL PRIMARY KEY,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source TEXT NOT NULL,
            gap_s DOUBLE PRECISION,
            status TEXT NOT NULL,
            host_suspend_suspected BOOLEAN NOT NULL DEFAULT FALSE,
            open_positions INTEGER NOT NULL DEFAULT 0,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            resolved_at TIMESTAMPTZ
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS deploy_meta(
            id INTEGER PRIMARY KEY CHECK (id=1),
            git_commit TEXT,
            deployed_at TIMESTAMPTZ,
            notes TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """INSERT INTO deploy_meta(id, git_commit, notes)
           VALUES(1, %s, 'ae_bootstrap')
           ON CONFLICT (id) DO NOTHING""",
        (DEPLOY_COMMIT,),
    )


def record_gap_if_needed(
    execute: Callable,
    *,
    source: str,
    gap: dict[str, Any],
    open_positions: int,
) -> None:
    """Persist gap events when WARNING/CRITICAL; resolve when OK."""
    ensure_continuity_schema(execute)
    st = gap.get("status") or "UNKNOWN"
    fp_open = execute(
        """SELECT id FROM continuity_gap_events
           WHERE source=%s AND resolved_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (source,),
    ).fetchone()
    if st in ("WARNING", "CRITICAL", "UNKNOWN"):
        if fp_open:
            execute(
                """UPDATE continuity_gap_events
                   SET gap_s=%s, status=%s, host_suspend_suspected=%s,
                       open_positions=%s, detail_json=%s::jsonb
                   WHERE id=%s""",
                (
                    gap.get("gap_s"),
                    st,
                    bool(gap.get("host_suspend_suspected")),
                    open_positions,
                    json.dumps(gap, default=str),
                    fp_open["id"],
                ),
            )
        else:
            execute(
                """INSERT INTO continuity_gap_events(
                     source, gap_s, status, host_suspend_suspected, open_positions, detail_json)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    source,
                    gap.get("gap_s"),
                    st,
                    bool(gap.get("host_suspend_suspected")),
                    open_positions,
                    json.dumps(gap, default=str),
                ),
            )
    elif st == "OK" and fp_open:
        execute(
            "UPDATE continuity_gap_events SET resolved_at=NOW() WHERE id=%s",
            (fp_open["id"],),
        )


def build_service_row(
    *,
    name: str,
    bot_status: str | None,
    heartbeat_at: Any,
    last_eval_at: Any,
    last_error: Any,
    open_positions: int,
    expected_every_s: float,
    price_age_s: float | None,
    entries_authorized: bool | None = None,
) -> dict[str, Any]:
    gap_s = heartbeat_gap_seconds(heartbeat_at)
    warn_s = max(expected_every_s * 3, 180.0)
    crit_s = max(expected_every_s * 10, 600.0)
    gap = classify_gap(gap_s, warn_s=warn_s, crit_s=crit_s, expected_every_s=expected_every_s)
    price_stale = price_age_s is None or price_age_s >= STALE_PRICE_S
    prot = protection_status(
        bot_status=bot_status,
        open_positions=open_positions,
        gap=gap,
        price_stale=price_stale,
        entries_authorized=entries_authorized,
    )
    # Functional readiness (not Docker Up)
    if gap.get("status") == "OK":
        functional = "READY"
    elif gap.get("status") == "WARNING":
        functional = "DEGRADED"
    elif gap.get("status") == "UNKNOWN":
        functional = "UNKNOWN"
    else:
        functional = "DOWN"

    return {
        "service": name,
        "docker_note": "Estado Docker no visible desde API; usar health/heartbeat de aplicación.",
        "bot_status": bot_status,
        "functional_status": functional,
        "heartbeat_at": heartbeat_at.isoformat() if hasattr(heartbeat_at, "isoformat") else heartbeat_at,
        "heartbeat_age_s": gap_s,
        "last_eval_at": last_eval_at.isoformat() if hasattr(last_eval_at, "isoformat") else last_eval_at,
        "last_error": last_error,
        "expected_every_s": expected_every_s,
        "gap": gap,
        "entries_protection": prot,
        "price_stale": price_stale,
    }


def build_continuity_snapshot(
    *,
    demo_st: dict | None,
    active_st: dict | None,
    demo_pos_n: int,
    active_pos_n: int,
    price_age_s: float | None,
    shadow_hb: Any = None,
    worker_scan_age_s: float | None = None,
    market_stream: dict | None = None,
    deploy_meta: dict | None = None,
    recent_gaps: list | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    demo = build_service_row(
        name="demo_runner",
        bot_status=(demo_st or {}).get("status"),
        heartbeat_at=(demo_st or {}).get("heartbeat_at"),
        last_eval_at=(demo_st or {}).get("last_eval_at"),
        last_error=(demo_st or {}).get("last_error"),
        open_positions=demo_pos_n,
        expected_every_s=DEMO_EVERY_S,
        price_age_s=price_age_s,
    )
    active = build_service_row(
        name="active_runner",
        bot_status=(active_st or {}).get("status"),
        heartbeat_at=(active_st or {}).get("heartbeat_at"),
        last_eval_at=(active_st or {}).get("last_eval_at"),
        last_error=(active_st or {}).get("last_error"),
        open_positions=active_pos_n,
        expected_every_s=ACTIVE_EVERY_S,
        price_age_s=price_age_s,
        entries_authorized=None,  # flag lives in process env; exposed separately if needed
    )
    gaps = [
        x
        for x in (
            demo["gap"].get("gap_s"),
            active["gap"].get("gap_s"),
            heartbeat_gap_seconds(shadow_hb),
            worker_scan_age_s,
        )
        if x is not None
    ]
    overall_gap = max(gaps) if gaps else None
    continuity = reconcile_after_gap(
        gap_s=overall_gap,
        price_age_s=price_age_s,
        open_positions=demo_pos_n + active_pos_n,
    )

    # Overall system verdict — never claim 24/7 from a single OK snapshot.
    statuses = {demo["functional_status"], active["functional_status"]}
    if "DOWN" in statuses:
        overall = "DEGRADED"
    elif "DEGRADED" in statuses or "UNKNOWN" in statuses:
        overall = "DEGRADED"
    else:
        overall = "OK_SNAPSHOT"

    critical: list[dict[str, Any]] = []
    for row in (demo, active):
        prot = row["entries_protection"]
        if prot["open_positions"] > 0 and prot["protection"] == "PROTECTION_UNAVAILABLE":
            critical.append(
                {
                    "id": f"{row['service']}_protection_unavailable",
                    "severity": "CRITICAL",
                    "message": f"{row['service']}: posiciones abiertas sin protección evaluable",
                }
            )
        elif row["functional_status"] in ("DOWN", "DEGRADED", "UNKNOWN"):
            critical.append(
                {
                    "id": f"{row['service']}_functional_{row['functional_status'].lower()}",
                    "severity": "WARNING" if row["functional_status"] != "DOWN" else "CRITICAL",
                    "message": f"{row['service']} functional={row['functional_status']} gap={row['gap'].get('gap_s')}",
                    "open_positions": row["entries_protection"]["open_positions"],
                }
            )

    return {
        "checked_at": now.isoformat(),
        "mode": "PAPER_ONLY",
        "overall": overall,
        "overall_note": (
            "OK_SNAPSHOT = evidencia reciente OK; no prueba continuidad 24/7 longitudinal. "
            "Caída completa del host EBZ no es detectable desde dentro del mismo host."
        ),
        "services": {
            "demo_runner": demo,
            "active_runner": active,
            "worker": {
                "service": "worker",
                "functional_status": (
                    "READY"
                    if worker_scan_age_s is not None and worker_scan_age_s < WORKER_EVERY_S * 1.5
                    else ("DEGRADED" if worker_scan_age_s is not None else "UNKNOWN")
                ),
                "scan_age_s": worker_scan_age_s,
                "expected_every_s": WORKER_EVERY_S,
            },
            "shadow_scheduler": {
                "service": "shadow_scheduler",
                "heartbeat_age_s": heartbeat_gap_seconds(shadow_hb),
                "expected_every_s": SHADOW_EVERY_S,
                "gap": classify_gap(
                    heartbeat_gap_seconds(shadow_hb),
                    warn_s=max(SHADOW_EVERY_S * 2, 600),
                    crit_s=max(SHADOW_EVERY_S * 3, 900),
                    expected_every_s=SHADOW_EVERY_S,
                ),
            },
            "market_stream": market_stream or {"functional_status": "UNKNOWN", "note": "probe_from_api_optional"},
        },
        "continuity": continuity,
        "critical_alerts": critical,
        "deploy": deploy_meta
        or {
            "git_commit": DEPLOY_COMMIT,
            "note": "Set DEPLOY_GIT_COMMIT at deploy time for accurate version.",
        },
        "recent_gap_events": recent_gaps or [],
        "verification_levels": {
            "implemented": True,
            "verified_in_test": False,
            "verified_in_production_snapshot": True,
            "pending_longitudinal_observation": True,
        },
    }
