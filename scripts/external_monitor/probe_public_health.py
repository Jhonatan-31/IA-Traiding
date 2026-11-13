#!/usr/bin/env python3
"""AG6 — Probe externo de solo lectura contra /api/public/health.

Diseñado para ejecutarse FUERA de EBZ (otro dispositivo).
Estado del producto: PREPARADO / NOT_CONFIGURED hasta autorización.

No usa tokens administrativos. No imprime cuerpos con datos sensibles
(el endpoint público no debe contenerlos).

Ejemplo:
  python probe_public_health.py --url http://100.x.x.x:8090/api/public/health
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_KEYS = {
    "ok",
    "service",
    "mode",
    "checked_at",
    "db",
    "deploy_commit",
}
FORBIDDEN_SUBSTRINGS = (
    "balance",
    "position",
    "token",
    "password",
    "secret",
    "cash",
    "ledger",
)


def probe(url: str, timeout: float) -> dict:
    started = time.monotonic()
    out: dict = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "ok": False,
        "http_status": None,
        "latency_ms": None,
        "error_class": None,
        "error": None,
        "body_keys": [],
        "sensitive_leak_suspected": False,
    }
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(65536)
            out["http_status"] = int(resp.status)
            out["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            text = raw.decode("utf-8", errors="replace")
            low = text.lower()
            out["sensitive_leak_suspected"] = any(s in low for s in FORBIDDEN_SUBSTRINGS)
            data = json.loads(text)
            if not isinstance(data, dict):
                out["error_class"] = "invalid_json_shape"
                return out
            out["body_keys"] = sorted(data.keys())
            extra = set(data.keys()) - ALLOWED_KEYS
            if extra:
                out["error_class"] = "unexpected_keys"
                out["error"] = ",".join(sorted(extra))
            out["ok"] = bool(data.get("ok")) and out["http_status"] == 200 and not extra
            return out
    except socket.timeout:
        out["error_class"] = "timeout"
        out["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    except urllib.error.HTTPError as e:
        out["http_status"] = int(e.code)
        out["error_class"] = "http_error"
        out["error"] = str(e.code)
        out["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        if "Name or service not known" in reason or "getaddrinfo" in reason:
            out["error_class"] = "dns_failure"
        else:
            out["error_class"] = "connection_failure"
        out["error"] = reason[:200]
        out["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    except Exception as e:
        out["error_class"] = type(e).__name__
        out["error"] = str(e)[:200]
        out["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="External public health probe (AG6)")
    p.add_argument("--url", required=True)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--state", default="", help="JSON state file for dedup incidents")
    args = p.parse_args()
    result = probe(args.url, args.timeout)
    print(json.dumps(result, ensure_ascii=False))

    if args.state:
        path = Path(args.state)
        prev = {}
        if path.exists():
            try:
                prev = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        incident = prev.get("incident") or {}
        now = result["probed_at"]
        if result["ok"]:
            if incident.get("active"):
                incident = {
                    "active": False,
                    "resolved_at": now,
                    "started_at": incident.get("started_at"),
                    "last_error_class": incident.get("last_error_class"),
                }
        else:
            # Debounce: require 2 consecutive failures before opening incident
            fails = int(prev.get("consecutive_failures") or 0) + 1
            prev["consecutive_failures"] = fails
            if fails >= 2 and not incident.get("active"):
                incident = {
                    "active": True,
                    "started_at": now,
                    "last_error_class": result.get("error_class"),
                }
            elif incident.get("active"):
                incident["last_error_class"] = result.get("error_class")
            prev["incident"] = incident
            path.write_text(json.dumps(prev, indent=2), encoding="utf-8")
            return 2 if fails >= 2 else 1
        prev["consecutive_failures"] = 0
        prev["incident"] = incident
        prev["last_ok_at"] = now
        path.write_text(json.dumps(prev, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
