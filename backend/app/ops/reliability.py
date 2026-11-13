"""Longitudinal reliability SLIs — real samples only; UNKNOWN ≠ available."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .health_center import DEPLOY_COMMIT

SAMPLE_INTERVAL_S = int(os.environ.get("AF_SAMPLE_INTERVAL_SECONDS", "60"))
RETENTION_DAYS = int(os.environ.get("AF_SAMPLE_RETENTION_DAYS", "40"))


def ensure_reliability_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS reliability_meta(
            id INTEGER PRIMARY KEY CHECK (id=1),
            measurements_started_at TIMESTAMPTZ NOT NULL,
            last_sample_at TIMESTAMPTZ,
            sample_interval_s INTEGER NOT NULL DEFAULT 60,
            notes TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS reliability_samples(
            id BIGSERIAL PRIMARY KEY,
            sampled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sample_bucket TIMESTAMPTZ NOT NULL,
            api_ok BOOLEAN NOT NULL,
            db_ok BOOLEAN NOT NULL,
            demo_functional TEXT NOT NULL,
            active_functional TEXT NOT NULL,
            market_stale BOOLEAN,
            overall TEXT NOT NULL,
            deploy_commit TEXT,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS reliability_samples_bucket_uidx
           ON reliability_samples(sample_bucket)"""
    )
    execute(
        """INSERT INTO reliability_meta(id, measurements_started_at, sample_interval_s, notes)
           VALUES (1, NOW(), %s, 'af_bootstrap')
           ON CONFLICT (id) DO NOTHING""",
        (SAMPLE_INTERVAL_S,),
    )


def _bucket(now: datetime) -> datetime:
    # Floor to minute for idempotent sampling
    return now.replace(second=0, microsecond=0)


def classify_overall(
    *,
    api_ok: bool,
    db_ok: bool,
    demo_functional: str,
    active_functional: str,
) -> str:
    if not api_ok or not db_ok:
        return "DOWN"
    funcs = {demo_functional, active_functional}
    if "DOWN" in funcs:
        return "DOWN"
    if "UNKNOWN" in funcs:
        return "UNKNOWN"
    if "DEGRADED" in funcs:
        return "DEGRADED"
    if funcs <= {"READY"}:
        return "OPERATIONAL"
    return "UNKNOWN"


def maybe_record_sample(
    execute: Callable,
    *,
    api_ok: bool,
    db_ok: bool,
    demo_functional: str,
    active_functional: str,
    market_stale: bool | None,
    detail: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Idempotent sample at most once per minute bucket."""
    ensure_reliability_schema(execute)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    bucket = _bucket(ref)
    overall = classify_overall(
        api_ok=api_ok,
        db_ok=db_ok,
        demo_functional=demo_functional or "UNKNOWN",
        active_functional=active_functional or "UNKNOWN",
    )
    execute(
        """INSERT INTO reliability_samples(
             sampled_at, sample_bucket, api_ok, db_ok, demo_functional, active_functional,
             market_stale, overall, deploy_commit, detail_json)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (sample_bucket) DO NOTHING""",
        (
            ref,
            bucket,
            api_ok,
            db_ok,
            demo_functional or "UNKNOWN",
            active_functional or "UNKNOWN",
            market_stale,
            overall,
            DEPLOY_COMMIT,
            json.dumps(detail or {}, default=str),
        ),
    )
    execute(
        "UPDATE reliability_meta SET last_sample_at=%s, updated_at=NOW() WHERE id=1",
        (ref,),
    )
    # Retention prune (lightweight)
    execute(
        "DELETE FROM reliability_samples WHERE sampled_at < NOW() - (%s || ' days')::interval",
        (str(RETENTION_DAYS),),
    )
    meta = execute("SELECT * FROM reliability_meta WHERE id=1").fetchone()
    return {"recorded_bucket": bucket.isoformat(), "overall": overall, "meta": meta}


def window_stats(
    execute: Callable,
    *,
    window_s: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Compute availability for a window.

    UNKNOWN / missing samples are NOT counted as available.
    """
    ensure_reliability_schema(execute)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    meta = execute("SELECT * FROM reliability_meta WHERE id=1").fetchone()
    started = meta["measurements_started_at"] if meta else ref
    if hasattr(started, "tzinfo") and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    window_start = ref - timedelta(seconds=window_s)
    # Evidence cannot predate measurements_started_at
    effective_start = max(window_start, started)
    interval = int((meta or {}).get("sample_interval_s") or SAMPLE_INTERVAL_S)
    elapsed = max(0.0, (ref - effective_start).total_seconds())
    expected = int(elapsed // interval) if interval > 0 else 0

    rows = list(
        execute(
            """SELECT overall, sampled_at FROM reliability_samples
               WHERE sampled_at >= %s AND sampled_at <= %s
               ORDER BY sampled_at ASC""",
            (effective_start, ref),
        )
    )
    counts = {"OPERATIONAL": 0, "DEGRADED": 0, "DOWN": 0, "UNKNOWN": 0}
    for r in rows:
        o = str(r["overall"] or "UNKNOWN")
        if o not in counts:
            o = "UNKNOWN"
        counts[o] += 1

    valid = len(rows)
    missing = max(0, expected - valid)
    # Coverage: fraction of expected slots with a sample
    coverage = (valid / expected) if expected > 0 else 0.0
    # Observed availability among valid samples only (operational)
    observed_up = counts["OPERATIONAL"] / valid if valid > 0 else None
    # Strict availability treating missing as UNKNOWN (not up)
    denom = expected if expected > 0 else None
    strict_up = (counts["OPERATIONAL"] / denom) if denom else None

    evidence_status = "EVIDENCIA_EN_ACUMULACION"
    if elapsed >= window_s * 0.95 and coverage >= 0.8:
        evidence_status = "COBERTURA_SUFICIENTE_PARA_VENTANA"
    elif valid == 0:
        evidence_status = "SIN_MUESTRAS"

    return {
        "window_s": window_s,
        "window_label": {86400: "24h", 604800: "7d", 2592000: "30d"}.get(window_s, f"{window_s}s"),
        "measurements_started_at": started.isoformat() if hasattr(started, "isoformat") else started,
        "effective_start": effective_start.isoformat(),
        "checked_at": ref.isoformat(),
        "elapsed_s": round(elapsed, 1),
        "sample_interval_s": interval,
        "expected_samples": expected,
        "valid_samples": valid,
        "missing_samples": missing,
        "coverage": round(coverage, 4),
        "counts": counts,
        "observed_operational_ratio": round(observed_up, 6) if observed_up is not None else None,
        "strict_operational_ratio": round(strict_up, 6) if strict_up is not None else None,
        "unknown_not_counted_as_up": True,
        "evidence_status": evidence_status,
        "note": (
            "No inventar historial anterior a measurements_started_at. "
            "UNKNOWN/missing ≠ disponible. Ventanas 7d/30d mostrarán EVIDENCIA_EN_ACUMULACION "
            "hasta acumular datos reales."
        ),
    }


def reliability_dashboard(execute: Callable, *, now: datetime | None = None) -> dict[str, Any]:
    ensure_reliability_schema(execute)
    meta = execute("SELECT * FROM reliability_meta WHERE id=1").fetchone()
    windows = {
        "24h": window_stats(execute, window_s=86400, now=now),
        "7d": window_stats(execute, window_s=604800, now=now),
        "30d": window_stats(execute, window_s=2592000, now=now),
    }
    recent = list(
        execute(
            """SELECT sampled_at, overall, api_ok, db_ok, demo_functional, active_functional, market_stale
               FROM reliability_samples ORDER BY sampled_at DESC LIMIT 48"""
        )
    )
    open_gaps = list(
        execute(
            """SELECT id, detected_at, source, gap_s, status, open_positions, resolved_at
               FROM continuity_gap_events
               WHERE resolved_at IS NULL
               ORDER BY id DESC LIMIT 20"""
        )
    )
    return {
        "measurements_started_at": (
            meta["measurements_started_at"].isoformat()
            if meta and hasattr(meta["measurements_started_at"], "isoformat")
            else (meta or {}).get("measurements_started_at")
        ),
        "last_sample_at": (
            meta["last_sample_at"].isoformat()
            if meta and meta.get("last_sample_at") and hasattr(meta["last_sample_at"], "isoformat")
            else (meta or {}).get("last_sample_at")
        ),
        "sample_interval_s": (meta or {}).get("sample_interval_s") or SAMPLE_INTERVAL_S,
        "windows": windows,
        "recent_samples": recent,
        "open_gap_events": open_gaps,
        "external_monitor": {
            "status": "NOT_CONFIGURED",
            "note": "Monitor independiente fuera de EBZ requiere autorización explícita.",
        },
        "verification": {
            "system_implemented": True,
            "system_tested": True,
            "longitudinal_evidence": "ACCUMULATING",
            "availability_30d_verified": False,
        },
    }
