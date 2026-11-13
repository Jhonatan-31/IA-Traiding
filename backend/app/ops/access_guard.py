"""AH — Dashboard read access control (feature-flagged; OFF by default).

DASHBOARD_READ_AUTH=0|false|off  → no enforcement (PREPARADO_SIN_ACTIVAR)
DASHBOARD_READ_AUTH=1|true|on   → require read credential

Credential sources (either):
  - Header X-Dashboard-Read-Token
  - Cookie ib_read_session (HttpOnly; Secure only when HTTPS)

Distinct from LAB_CONTROL_TOKEN (mutations).
Never logs token values.
"""
from __future__ import annotations

import hmac
import logging
import os
import time
from typing import Any

from fastapi import Header, HTTPException, Request, Response

log = logging.getLogger("access_guard")

COOKIE_NAME = "ib_read_session"
HEADER_NAME = "X-Dashboard-Read-Token"

# In-memory denial counters (process-local; no secrets).
_denials = 0
_last_denial_at: float | None = None
# Simple login rate limit: ip -> list of attempt timestamps
_login_attempts: dict[str, list[float]] = {}
LOGIN_WINDOW_S = int(os.environ.get("DASHBOARD_LOGIN_WINDOW_S", "300"))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("DASHBOARD_LOGIN_MAX_ATTEMPTS", "20"))


def check_login_rate_limit(client_key: str) -> bool:
    """Return True if allowed; False if rate-limited. Never stores secrets."""
    now = time.time()
    key = (client_key or "unknown")[:128]
    bucket = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_WINDOW_S]
    if len(bucket) >= LOGIN_MAX_ATTEMPTS:
        _login_attempts[key] = bucket
        return False
    bucket.append(now)
    _login_attempts[key] = bucket
    return True


def read_auth_enabled() -> bool:
    v = str(os.environ.get("DASHBOARD_READ_AUTH", "0")).strip().lower()
    return v in ("1", "true", "yes", "on")


def _expected_token() -> str:
    return str(os.environ.get("DASHBOARD_READ_TOKEN", "")).strip()


def token_matches(provided: str | None) -> bool:
    expected = _expected_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def read_auth_status() -> dict[str, Any]:
    enabled = read_auth_enabled()
    token_configured = bool(_expected_token())
    base = {
        "header": HEADER_NAME,
        "cookie": COOKIE_NAME,
        "denials_process": _denials,
        "last_denial_at": _last_denial_at,
        "lab_token_reused": False,
        "note_transport": (
            "Sobre HTTP LAN, cookie Secure no aplica. Preferir Tailscale Serve HTTPS "
            "antes de activar en producción; ver docs/etapa_ah/SESIONES_Y_TRANSPORTE.md"
        ),
    }
    if not enabled:
        return {
            **base,
            "status": "PREPARADO_SIN_ACTIVAR",
            "enforced": False,
            "token_configured": token_configured,
            "note": "Auth de lectura lista; no activa en producción hasta autorización.",
        }
    if not token_configured:
        return {
            **base,
            "status": "FALLIDO",
            "enforced": True,
            "token_configured": False,
            "note": "DASHBOARD_READ_AUTH=on pero falta DASHBOARD_READ_TOKEN.",
        }
    return {
        **base,
        "status": "ACTIVADO",
        "enforced": True,
        "token_configured": True,
    }


def extract_read_credential(request: Request) -> str | None:
    hdr = request.headers.get(HEADER_NAME)
    if hdr and str(hdr).strip():
        return str(hdr).strip()
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and str(cookie).strip():
        return str(cookie).strip()
    return None


def record_denial(path: str, reason: str) -> None:
    global _denials, _last_denial_at
    _denials += 1
    _last_denial_at = time.time()
    # Never log credential material
    log.warning("dashboard_read_denied path=%s reason=%s", path, reason)


def require_dashboard_read(
    request: Request,
    x_dashboard_read_token: str | None = Header(default=None, alias=HEADER_NAME),
) -> str:
    """Dependency for sensitive routes. No-op when auth disabled."""
    if not read_auth_enabled():
        return "auth_disabled"
    expected = _expected_token()
    if not expected:
        raise HTTPException(status_code=503, detail="dashboard_read_token_not_configured")
    provided = (x_dashboard_read_token or "").strip() or extract_read_credential(request)
    if not token_matches(provided):
        path = getattr(getattr(request, "url", None), "path", "unknown")
        record_denial(str(path), "unauthorized")
        raise HTTPException(status_code=401, detail="unauthorized_dashboard_read")
    return "ok"


def set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=int(os.environ.get("DASHBOARD_READ_SESSION_SECONDS", "43200")),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def path_requires_read_auth(path: str) -> bool:
    if path.startswith("/api/public/"):
        return False
    if path == "/api/health":
        return False
    # Auth bootstrap endpoints must remain reachable when enforcement is on.
    if path.startswith("/api/auth/"):
        return False
    if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
        return False
    # Static UI / SPA shell — API layer enforces data access.
    if not path.startswith("/api/"):
        return False
    return True


def websocket_policy() -> dict[str, Any]:
    """AH3: /ws/market is public Binance fan-out (no ledger data)."""
    return {
        "market_stream_path": "/ws/market",
        "classification": "PUBLIC_MARKET_FANOUT",
        "carries_balances": False,
        "carries_positions": False,
        "auth_required_when_read_auth_on": False,
        "note": (
            "Stream de velas/trades públicos de Binance vía market-stream. "
            "Datos de cartera solo por /api/* (sí protegidos cuando auth ON)."
        ),
    }
