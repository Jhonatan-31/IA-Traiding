"""Lab control authentication — no insecure defaults; never log secrets."""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def require_lab_token(x_lab_token: str | None = Header(default=None, alias="X-Lab-Token")) -> str:
    expected = os.environ.get("LAB_CONTROL_TOKEN")
    if not expected or not str(expected).strip():
        # Misconfiguration: refuse mutations rather than falling back to a weak token
        raise HTTPException(
            status_code=503,
            detail="lab_control_token_not_configured",
        )
    if not x_lab_token or x_lab_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized_lab_control")
    # Return a non-secret marker only
    return "ok"
