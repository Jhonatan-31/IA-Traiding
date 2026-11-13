"""AG2 — Dashboard read access control (feature-flagged; OFF by default).

DASHBOARD_READ_AUTH=0|false|off  → no enforcement (PREPARADO_SIN_ACTIVAR)
DASHBOARD_READ_AUTH=1|true|on   → require X-Dashboard-Read-Token

Uses a token DISTINCT from LAB_CONTROL_TOKEN (mutations).
Never logs token values.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException, Request


def read_auth_enabled() -> bool:
    v = str(os.environ.get("DASHBOARD_READ_AUTH", "0")).strip().lower()
    return v in ("1", "true", "yes", "on")


def read_auth_status() -> dict[str, Any]:
    enabled = read_auth_enabled()
    token_configured = bool(str(os.environ.get("DASHBOARD_READ_TOKEN", "")).strip())
    if not enabled:
        return {
            "status": "PREPARADO_SIN_ACTIVAR",
            "enforced": False,
            "token_configured": token_configured,
            "header": "X-Dashboard-Read-Token",
            "note": "Auth de lectura lista en código; no activa en producción hasta autorización.",
        }
    if not token_configured:
        return {
            "status": "FALLIDO",
            "enforced": True,
            "token_configured": False,
            "note": "DASHBOARD_READ_AUTH=on pero falta DASHBOARD_READ_TOKEN.",
        }
    return {
        "status": "ACTIVADO",
        "enforced": True,
        "token_configured": True,
        "header": "X-Dashboard-Read-Token",
    }


def require_dashboard_read(
    request: Request,
    x_dashboard_read_token: str | None = Header(default=None, alias="X-Dashboard-Read-Token"),
) -> str:
    """Dependency for sensitive GET routes. No-op when auth disabled."""
    if not read_auth_enabled():
        return "auth_disabled"
    expected = str(os.environ.get("DASHBOARD_READ_TOKEN", "")).strip()
    if not expected:
        raise HTTPException(status_code=503, detail="dashboard_read_token_not_configured")
    if not x_dashboard_read_token or x_dashboard_read_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized_dashboard_read")
    return "ok"


# Paths that remain reachable without read auth even when enabled.
PUBLIC_PATH_PREFIXES = (
    "/api/public/",
    "/api/health",  # container healthcheck
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Sensitive API prefixes protected when DASHBOARD_READ_AUTH is on.
SENSITIVE_API_PREFIXES = (
    "/api/overview",
    "/api/trades",
    "/api/positions",
    "/api/scans",
    "/api/markets",
    "/api/system",
    "/api/continuity",
    "/api/reliability",
    "/api/security",
    "/api/diagnostics",
    "/api/candles",
    "/api/risk",
    "/api/performance",
    "/api/alerts",
    "/api/demo",
    "/api/active",
    "/api/lab",
    "/api/express",
    "/api/research",
    "/api/ml",
    "/api/prospect",
)


def path_requires_read_auth(path: str) -> bool:
    if path.startswith("/api/public/"):
        return False
    if path == "/api/health":
        return False
    if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
        return False
    # Static UI assets / SPA — auth enforced at API layer, not HTML shell.
    if not path.startswith("/api/"):
        return False
    return True
