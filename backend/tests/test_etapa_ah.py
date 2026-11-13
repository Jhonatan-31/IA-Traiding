"""Etapa AH — auth lectura, sesiones, websocket policy, bypass API."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from app.ops.access_guard import (
    COOKIE_NAME,
    extract_read_credential,
    path_requires_read_auth,
    read_auth_enabled,
    read_auth_status,
    token_matches,
    websocket_policy,
)


def test_ah_auth_off_by_default_compat():
    with patch.dict(os.environ, {"DASHBOARD_READ_AUTH": "0"}, clear=False):
        assert read_auth_enabled() is False
        assert read_auth_status()["status"] == "PREPARADO_SIN_ACTIVAR"
        assert path_requires_read_auth("/api/system") is True  # would gate IF enabled
        # but middleware no-ops when disabled


def test_ah_public_and_auth_bootstrap_not_gated():
    assert path_requires_read_auth("/api/public/health") is False
    assert path_requires_read_auth("/api/health") is False
    assert path_requires_read_auth("/api/auth/status") is False
    assert path_requires_read_auth("/api/auth/login") is False
    assert path_requires_read_auth("/api/auth/logout") is False
    assert path_requires_read_auth("/api/overview") is True
    assert path_requires_read_auth("/api/positions") is True


def test_ah_token_compare_constant_time_and_no_lab_reuse_doc():
    with patch.dict(os.environ, {"DASHBOARD_READ_TOKEN": "read-only-secret"}, clear=False):
        assert token_matches("read-only-secret") is True
        assert token_matches("wrong") is False
        assert token_matches(None) is False
        st = read_auth_status()
        assert st.get("lab_token_reused") is False


def test_ah_cookie_or_header_credential():
    class _Req:
        def __init__(self, headers=None, cookies=None):
            self.headers = headers or {}
            self.cookies = cookies or {}

    with patch.dict(os.environ, {"DASHBOARD_READ_TOKEN": "from-header"}, clear=False):
        assert extract_read_credential(_Req(headers={"X-Dashboard-Read-Token": "from-header"})) == "from-header"
        assert extract_read_credential(_Req(cookies={COOKIE_NAME: "from-header"})) == "from-header"
        assert token_matches("from-header")


def test_ah_websocket_market_is_public_fanout():
    pol = websocket_policy()
    assert pol["carries_balances"] is False
    assert pol["carries_positions"] is False
    assert pol["auth_required_when_read_auth_on"] is False
    assert pol["classification"] == "PUBLIC_MARKET_FANOUT"


def test_ah_frontend_no_localstorage_token():
    gate = Path(__file__).resolve().parents[2] / "frontend" / "src" / "auth" / "AuthGate.tsx"
    src = gate.read_text(encoding="utf-8")
    assert "localStorage.setItem" not in src
    assert "sessionStorage.setItem" not in src
    assert "password" in src
    assert "credentials" not in src  # login via api helper only


def test_ah_api_credentials_include():
    api = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api.ts"
    src = api.read_text(encoding="utf-8")
    assert 'credentials: "include"' in src
    assert "loginReadAccess" in src


def test_ah_activation_plan_exists():
    doc = Path(__file__).resolve().parents[2] / "docs" / "etapa_ah" / "PLAN_ACTIVACION.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "DASHBOARD_READ_AUTH=1" in text
    assert "NO ejecutar" in text or "No activar" in text or "no activar" in text.lower()


def test_ah_middleware_uses_extract_credential():
    main = Path(__file__).resolve().parents[1] / "app" / "main.py"
    src = main.read_text(encoding="utf-8")
    assert "extract_read_credential" in src
    assert "token_matches" in src
    assert "/api/auth/login" in src
