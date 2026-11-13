"""Etapa AI — seguridad auth, middleware, rate-limit, bundle, schemas."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ops.access_guard import (
    COOKIE_NAME,
    check_login_rate_limit,
    path_requires_read_auth,
    read_auth_status,
    token_matches,
    websocket_policy,
    _login_attempts,
)


def _mini_app() -> FastAPI:
    from app.ops.access_guard import (
        extract_read_credential,
        path_requires_read_auth as needs,
        read_auth_enabled,
        record_denial,
        token_matches as tm,
    )

    app = FastAPI()

    @app.middleware("http")
    async def mw(request, call_next):
        from fastapi.responses import JSONResponse

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
        return {"cash": 1000, "secret_should_not_leak_without_auth": True}

    @app.get("/api/positions")
    def positions():
        return [{"symbol": "BTCUSDT", "qty": 1}]

    return app


def test_ai_auth_off_allows_sensitive():
    with patch.dict(os.environ, {"DASHBOARD_READ_AUTH": "0", "DASHBOARD_READ_TOKEN": "x"}, clear=False):
        c = TestClient(_mini_app())
        assert c.get("/api/system").status_code == 200
        assert c.get("/api/positions").status_code == 200


def test_ai_auth_on_blocks_without_cred():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "good-token"}, clear=False
    ):
        c = TestClient(_mini_app())
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/public/health").status_code == 200
        assert c.get("/api/system").status_code == 401
        assert c.get("/api/positions").status_code == 401


def test_ai_auth_on_header_ok():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "good-token"}, clear=False
    ):
        c = TestClient(_mini_app())
        r = c.get("/api/system", headers={"X-Dashboard-Read-Token": "good-token"})
        assert r.status_code == 200
        assert "cash" in r.json()


def test_ai_auth_on_forged_cookie_rejected():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "good-token"}, clear=False
    ):
        c = TestClient(_mini_app())
        c.cookies.set(COOKIE_NAME, "forged-value")
        assert c.get("/api/system").status_code == 401


def test_ai_auth_on_valid_cookie_ok():
    with patch.dict(
        os.environ, {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "good-token"}, clear=False
    ):
        c = TestClient(_mini_app())
        c.cookies.set(COOKIE_NAME, "good-token")
        assert c.get("/api/positions").status_code == 200


def test_ai_wrong_token_rejected():
    with patch.dict(os.environ, {"DASHBOARD_READ_TOKEN": "good-token"}, clear=False):
        assert token_matches("good-token")
        assert not token_matches("GOOD-TOKEN")
        assert not token_matches("")


def test_ai_login_rate_limit():
    _login_attempts.clear()
    with patch.dict(
        os.environ,
        {"DASHBOARD_LOGIN_WINDOW_S": "300", "DASHBOARD_LOGIN_MAX_ATTEMPTS": "3"},
        clear=False,
    ):
        # re-import constants not needed — function reads env each call for window via module consts
        # Module consts already loaded; force small by clearing and hammering with patched module attrs
        import app.ops.access_guard as ag

        ag.LOGIN_MAX_ATTEMPTS = 3
        ag.LOGIN_WINDOW_S = 300
        ag._login_attempts.clear()
        assert check_login_rate_limit("1.2.3.4")
        assert check_login_rate_limit("1.2.3.4")
        assert check_login_rate_limit("1.2.3.4")
        assert check_login_rate_limit("1.2.3.4") is False


def test_ai_public_health_payload_keys_safe():
    pub = Path(__file__).resolve().parents[1] / "app" / "main.py"
    src = pub.read_text(encoding="utf-8")
    i = src.find("def public_health")
    j = src.find("out = {", i)
    k = src.find("}", j)
    payload = src[j : k + 1].lower()
    for bad in ("balance", "position", "password", "token", "cash"):
        assert bad not in payload


def test_ai_js_bundle_sources_no_hardcoded_secrets():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    for rel in ("auth/AuthGate.tsx", "api.ts"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "LAB_CONTROL_TOKEN" not in text
        assert "DASHBOARD_READ_TOKEN" not in text
        assert "localStorage.setItem" not in text or rel != "auth/AuthGate.tsx"


def test_ai_websocket_policy_public_only():
    p = websocket_policy()
    assert p["carries_balances"] is False
    assert p["auth_required_when_read_auth_on"] is False


def test_ai_schema_reconciliation_doc_exists():
    doc = Path(__file__).resolve().parents[2] / "docs" / "etapa_ai" / "ESQUEMAS_63_VS_69.md"
    assert doc.is_file()
    t = doc.read_text(encoding="utf-8")
    assert "63" in t and "69" in t
    assert "no pérdida" in t.lower() or "no es pérdida" in t.lower() or "diferentes entornos" in t.lower()


def test_ai_https_example_has_no_secrets():
    ex = Path(__file__).resolve().parents[2] / "docs" / "etapa_ai" / "examples" / "tailscale_serve.example.json"
    assert ex.is_file()
    text = ex.read_text(encoding="utf-8")
    low = text.lower()
    assert "password" not in low
    assert "secret" not in low
    assert "127.0.0.1:8090" in text
    assert '"HTTPS": true' in text
