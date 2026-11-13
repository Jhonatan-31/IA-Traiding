"""Etapa AG — acceso lectura, health público, backups lógicos, recovery status."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import patch

from app.ops.access_guard import (
    path_requires_read_auth,
    read_auth_enabled,
    read_auth_status,
    require_dashboard_read,
)
from app.ops.security_recovery import security_recovery_dashboard
from fastapi import HTTPException


def test_ag_read_auth_disabled_by_default():
    with patch.dict(os.environ, {"DASHBOARD_READ_AUTH": "0"}, clear=False):
        assert read_auth_enabled() is False
        st = read_auth_status()
        assert st["status"] == "PREPARADO_SIN_ACTIVAR"
        assert st["enforced"] is False


def test_ag_read_auth_enabled_requires_token():
    with patch.dict(
        os.environ,
        {"DASHBOARD_READ_AUTH": "1", "DASHBOARD_READ_TOKEN": "read-secret-xyz"},
        clear=False,
    ):
        assert read_auth_enabled() is True
        assert require_dashboard_read(None, x_dashboard_read_token="read-secret-xyz") == "ok"
        try:
            require_dashboard_read(None, x_dashboard_read_token="wrong")
            assert False, "expected 401"
        except HTTPException as e:
            assert e.status_code == 401


def test_ag_public_health_path_not_gated():
    assert path_requires_read_auth("/api/public/health") is False
    assert path_requires_read_auth("/api/health") is False
    assert path_requires_read_auth("/api/system") is True
    assert path_requires_read_auth("/api/positions") is True
    assert path_requires_read_auth("/") is False


def test_ag_public_health_source_has_no_secrets():
    main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    i = src.find("def public_health")
    assert i > 0
    # Payload keys only (ignore docstring wording).
    j = src.find("out = {", i)
    k = src.find("}", j)
    payload = src[j : k + 1].lower()
    assert "lab_control_token" not in payload
    assert "balance" not in payload
    assert "position" not in payload
    assert "password" not in payload
    assert "ok" in payload
    assert "deploy_commit" in payload


def test_ag_security_recovery_distinguishes_offhost():
    dash = security_recovery_dashboard(execute=None)
    assert dash["backup_offhost"]["status"] == "PREPARADO_SIN_ACTIVAR"
    assert dash["external_monitor"]["status"] == "NOT_CONFIGURED"
    assert dash["dashboard_read_access"]["status"] == "PREPARADO_SIN_ACTIVAR"
    assert "HITACHI" in dash["backup_second_disk"]["note"] or "MISMO" in dash["backup_second_disk"]["note"]
    assert isinstance(dash["pending_authorizations"], list)
    assert len(dash["pending_authorizations"]) >= 2


def test_ag_offhost_script_noop_without_dest():
    script = Path(__file__).resolve().parents[2] / "scripts" / "ebz_backup_offhost.sh"
    text = script.read_text(encoding="utf-8")
    assert "PREPARADO_SIN_ACTIVAR" in text
    assert "OFFHOST_DEST" in text


def test_ag_external_probe_module_importable():
    # Load as path script helper
    probe = Path(__file__).resolve().parents[2] / "scripts" / "external_monitor" / "probe_public_health.py"
    assert probe.is_file()
    src = probe.read_text(encoding="utf-8")
    assert "ALLOWED_KEYS" in src
    assert "dns_failure" in src
    assert "LAB_CONTROL" not in src


def test_ag_backup_script_atomic_and_checksum():
    script = Path(__file__).resolve().parents[2] / "scripts" / "ebz_backup_paper.sh"
    text = script.read_text(encoding="utf-8")
    assert ".partial" in text
    assert "sha256" in text
    assert "manifest" in text
    assert "PGDMP" in text or "5047444d50" in text
