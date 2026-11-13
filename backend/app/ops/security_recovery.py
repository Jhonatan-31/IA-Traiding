"""AG9 — Security & recovery status for dashboard (no secrets)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .access_guard import read_auth_status


def ensure_backup_runs_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS backup_runs(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            scope TEXT NOT NULL,
            path TEXT,
            bytes BIGINT,
            sha256 TEXT,
            git_commit TEXT,
            pg_version TEXT,
            status TEXT NOT NULL,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )


def record_backup_run(
    execute: Callable,
    *,
    scope: str,
    path: str | None,
    bytes_: int | None,
    sha256: str | None,
    git_commit: str | None,
    pg_version: str | None,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    import json

    ensure_backup_runs_schema(execute)
    execute(
        """INSERT INTO backup_runs(scope, path, bytes, sha256, git_commit, pg_version, status, detail_json)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (
            scope,
            path,
            bytes_,
            sha256,
            git_commit,
            pg_version,
            status,
            json.dumps(detail or {}, default=str),
        ),
    )


def _latest_backup(execute: Callable, scope: str) -> dict[str, Any] | None:
    ensure_backup_runs_schema(execute)
    row = execute(
        """SELECT created_at, path, bytes, sha256, git_commit, pg_version, status
           FROM backup_runs WHERE scope=%s ORDER BY id DESC LIMIT 1""",
        (scope,),
    ).fetchone()
    if not row:
        return None
    created = row["created_at"]
    age_s = None
    if created is not None:
        if getattr(created, "tzinfo", None) is None:
            created = created.replace(tzinfo=timezone.utc)
        age_s = (datetime.now(timezone.utc) - created).total_seconds()
    return {
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
        "age_seconds": round(age_s, 1) if age_s is not None else None,
        "path": row.get("path"),
        "bytes": row.get("bytes"),
        "sha256": row.get("sha256"),
        "git_commit": row.get("git_commit"),
        "pg_version": row.get("pg_version"),
        "status": row.get("status"),
    }


def security_recovery_dashboard(execute: Callable | None = None) -> dict[str, Any]:
    """Status flags for UI — distinguishes VERIFICADO / PREPARADO / PENDIENTE."""
    read = read_auth_status()
    last_paper = None
    last_restore = None
    if execute is not None:
        try:
            last_paper = _latest_backup(execute, "ia-bot-trading-paper")
            last_restore = _latest_backup(execute, "restore-isolated")
        except Exception:
            pass

    # Cron: authorized post-AF by user (00:00/12:00 Bogota). Not inventing — reported by ops.
    cron_status = os.environ.get("EBZ_BACKUP_CRON_STATUS", "ACTIVADO")
    # Off-host second physical disk on same host is NOT off-host.
    hitachi = {
        "status": "CONFIGURADO",
        "mount": "/srv/backups",
        "note": "Segundo disco físico en el MISMO servidor EBZ. No es off-host.",
        "areas": ["ia-bot-trading", "consultate"],
    }
    offhost = {
        "status": "PREPARADO_SIN_ACTIVAR",
        "note": "Script/docs listos; falta destino externo + autorización.",
    }
    monitor = {
        "status": "NOT_CONFIGURED",
        "note": "Cliente probe preparado; instalación fuera de EBZ requiere autorización.",
    }

    # Age classification for last backup
    backup_freshness = "PENDIENTE"
    if last_paper and last_paper.get("status") == "OK":
        age = last_paper.get("age_seconds")
        if age is not None and age <= 86400 * 2:
            backup_freshness = "VERIFICADO"
        elif age is not None:
            backup_freshness = "CONFIGURADO"
        else:
            backup_freshness = "CONFIGURADO"

    total_loss_risk = (
        "ALTO: backup en EBZ (NVMe + HITACHI local). Pérdida total del host "
        "puede perder ambos discos. Off-host NO activado."
    )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_read_access": read,
        "backup_ebz": {
            "status": backup_freshness if last_paper else "PENDIENTE",
            "last": last_paper,
            "cron": cron_status,
            "schedule_note": "CRON_TZ=America/Bogota 00:00 y 12:00 (autorizado por usuario).",
            "retention_default": 14,
        },
        "backup_second_disk": hitachi,
        "backup_offhost": offhost,
        "disaster_recovery": {
            "status": "PREPARADO",
            "isolated_restore": last_restore or {
                "status": "VERIFICADO_EN_AE",
                "note": "Restore aislado AE documentado; re-ejecutable con script AG.",
            },
            "rpo_proposed_hours": 12,
            "rto_proposed_hours": 4,
            "note": "RPO/RTO son objetivos propuestos, no garantías medidas post-pérdida total.",
        },
        "external_monitor": monitor,
        "risk_total_server_loss": total_loss_risk,
        "pending_authorizations": [
            "Activar DASHBOARD_READ_AUTH en producción (+ token + migración acceso).",
            "Seleccionar destino off-host y autorizar sincronización cifrada.",
            "Instalar monitor externo en dispositivo independiente / Tailscale ACL.",
        ],
    }
