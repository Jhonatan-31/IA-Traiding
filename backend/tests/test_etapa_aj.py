"""Etapa AJ — activación controlada: docs, Secure cookie, bypass, matrix aislada."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.ops.access_guard import (
    COOKIE_NAME,
    check_login_rate_limit,
    clear_session_cookie,
    extract_read_credential,
    path_requires_read_auth,
    read_auth_enabled,
    set_session_cookie,
    token_matches,
    websocket_policy,
    _login_attempts,
)

ROOT = Path(__file__).resolve().parents[2]
AJ_DOCS = ROOT / "docs" / "etapa_aj"


def _secure_from_request(request: Request) -> bool:
    return request.url.scheme == "https" or (
        str(request.headers.get("x-forwarded-proto", "")).lower() == "https"
    )


def _aj_app() -> FastAPI:
    from app.ops.access_guard import (
        path_requires_read_auth as needs,
        read_auth_enabled,
        record_denial,
        token_matches as tm,
        extract_read_credential,
    )

    app = FastAPI()

    @app.middleware("http")
    async def mw(request, call_next):
        if read_auth_enabled() and needs(request.url.path):
            got = extract_read_credential(request)
            if not tm(got):
                record_denial(request.url.path, "unauthorized")
                return JSONResponse({"detail": "unauthorized_dashboard_read"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/public/health")
    def pub():
        return {"ok": True, "service": "ia-bot-trading", "mode": "PAPER_ONLY"}

    @app.get("/api/system")
    def system():
        return {"cash": 42, "mode": "PAPER_ONLY"}

    @app.get("/api/positions")
    def positions():
        return [{"symbol": "BTCUSDT"}]

    @app.post("/api/auth/login")
    async def login(request: Request):
        body = await request.json()
        token = str((body or {}).get("token") or "").strip()
        if not read_auth_enabled():
            return {"ok": True, "enforced": False}
        if not tm(token):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        secure = _secure_from_request(request)
        resp = JSONResponse({"ok": True, "secure_cookie": secure})
        set_session_cookie(resp, token, secure=secure)
        return resp

    @app.post("/api/auth/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        clear_session_cookie(resp)
        return resp

    @app.post("/api/lab/start")
    def lab_start(request: Request):
        # Mutaciones: token de lectura NO basta; requiere X-Lab-Token (simulado).
        lab = request.headers.get("X-Lab-Token", "")
        if lab != "lab-secret":
            return JSONResponse({"detail": "forbidden_lab"}, status_code=403)
        return {"started": False, "note": "simulated_no_wallet_touch"}

    return app


def test_aj1_no_session_rejected():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        assert c.get("/api/system").status_code == 401


def test_aj2_authorized_header_ok():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        r = c.get("/api/system", headers={"X-Dashboard-Read-Token": "aj-read"})
        assert r.status_code == 200
        assert r.json()["cash"] == 42


def test_aj3_valid_session_cookie():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        login = c.post("/api/auth/login", json={"token": "aj-read"})
        assert login.status_code == 200
        assert c.get("/api/positions").status_code == 200


def test_aj4_invalid_session_rejected():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        c.cookies.set(COOKIE_NAME, "not-the-token")
        assert c.get("/api/system").status_code == 401


def test_aj5_tampered_cookie_rejected():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        c.cookies.set(COOKIE_NAME, "aj-read-tampered")
        assert c.get("/api/system").status_code == 401


def test_aj6_secure_cookie_with_forwarded_proto():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        r = c.post(
            "/api/auth/login",
            json={"token": "aj-read"},
            headers={"X-Forwarded-Proto": "https"},
        )
        assert r.status_code == 200
        assert r.json()["secure_cookie"] is True
        # Set-Cookie debe incluir Secure
        sc = r.headers.get("set-cookie", "")
        assert "Secure" in sc or "secure" in sc.lower()


def test_aj7_read_token_cannot_mutate():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        r = c.post(
            "/api/lab/start",
            headers={"X-Dashboard-Read-Token": "aj-read"},
        )
        assert r.status_code == 403
        # Mutación exige X-Lab-Token además de lectura (middleware).
        ok = c.post(
            "/api/lab/start",
            headers={
                "X-Dashboard-Read-Token": "aj-read",
                "X-Lab-Token": "lab-secret",
            },
        )
        assert ok.status_code == 200
        assert ok.json()["started"] is False


def test_aj8_public_health_and_ws_policy():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        assert c.get("/api/public/health").status_code == 200
        assert c.get("/api/health").status_code == 200
        pol = websocket_policy()
        assert pol["carries_balances"] is False
        assert pol["auth_required_when_read_auth_on"] is False


def test_aj9_auth_off_preserves_access_and_data_shape():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "0", "DASHBOARD_READ_TOKEN": "aj-read"}, clear=False
    ):
        c = TestClient(_aj_app())
        r = c.get("/api/system")
        assert r.status_code == 200
        assert r.json()["cash"] == 42


def test_aj10_docs_activation_no_funnel_port_conflict():
    guia = (AJ_DOCS / "GUIA_ACTIVACION_EBZ.md").read_text(encoding="utf-8")
    arch = (AJ_DOCS / "ARQUITECTURA_HTTPS.md").read_text(encoding="utf-8")
    bypass = (AJ_DOCS / "RUTAS_ALTERNATIVAS.md").read_text(encoding="utf-8")
    assert "10000" in guia and "10000" in arch
    assert "funnel" in guia.lower() or "Funnel" in guia
    assert "NO EJECUTAR" in guia or "REQUIERE AUTORIZACIÓN" in guia
    assert "127.0.0.1:8090" in bypass
    assert "8443" in (AJ_DOCS / "AUDITORIA_EBZ.md").read_text(encoding="utf-8")
    ex = (AJ_DOCS / "examples" / "tailscale_serve_trading.example.json").read_text(encoding="utf-8")
    assert "10000" in ex
    assert "8090" in ex
    assert "funnel" in ex.lower() or "Funnel" in ex or "Sin Funnel" in ex


def test_aj11_preflight_script_readonly():
    script = (ROOT / "scripts" / "aj_activation_preflight.sh").read_text(encoding="utf-8")
    assert "NO modifica" in script or "sin cambios" in script.lower()
    for bad in ("serve --bg", "DASHBOARD_READ_AUTH=1", "funnel --", "iptables", "down -v"):
        assert bad not in script
    assert "funnel status" in script  # solo inspección


def test_aj12_main_secure_uses_forwarded_proto():
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "x-forwarded-proto" in main.lower()
    assert "set_session_cookie" in main
