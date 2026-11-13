"""AC0 — inventario de arquitectura (estático + runtime opcional)."""
from __future__ import annotations

import subprocess
from typing import Any


COMPONENTS: list[dict[str, Any]] = [
    {
        "component": "PostgreSQL paper_data",
        "state": "IMPLEMENTADO Y VERIFICADO",
        "evidence": "compose db healthy; schemas demo/active/lab/express/virt",
        "risk": "bajo si backups OK",
        "action": "mantener dumps pre/post etapa",
    },
    {
        "component": "FastAPI api",
        "state": "IMPLEMENTADO Y VERIFICADO",
        "evidence": "backend/app/main.py + research/api.py",
        "risk": "superficie de endpoints de control",
        "action": "auditar auth por ruta",
    },
    {
        "component": "market-stream WS",
        "state": "IMPLEMENTADO Y VERIFICADO",
        "evidence": "hub.py reconnect/backoff/STALE_AFTER_S=5; test_market_stream.py",
        "risk": "solo viz; runners usan REST/ohlcv aparte",
        "action": "no confundir stream UI con precios de ejecución",
    },
    {
        "component": "demo-runner (A)",
        "state": "PARCIAL",
        "evidence": "código+tests stop protections; contenedor Exited(137)",
        "risk": "protecciones no corren si exited",
        "action": "alerta runners; no auto-start en AC",
    },
    {
        "component": "active-runner (B)",
        "state": "PARCIAL",
        "evidence": "STOPPED + Exited; paper_only meta",
        "risk": "igual que A",
        "action": "mantener STOPPED",
    },
    {
        "component": "lab trade-executor",
        "state": "PARCIAL",
        "evidence": "lab/ledger aislamiento; contenedor Exited",
        "risk": "lab no cicla",
        "action": "documentar",
    },
    {
        "component": "Historial Parquet Vision",
        "state": "IMPLEMENTADO CON EVIDENCIA INSUFICIENTE",
        "evidence": "OHLCV OK; campos taker/quote ausentes",
        "risk": "microestructura limitada",
        "action": "migración no destructiva futura",
    },
    {
        "component": "Research Z/AA/AB",
        "state": "IMPLEMENTADO Y VERIFICADO",
        "evidence": "artifacts + hash 5326edb8a539cfe5 + tests",
        "risk": "holdout consumido",
        "action": "no reusar AA como indep.",
    },
    {
        "component": "AB-PROSPECT-v1",
        "state": "PARCIAL",
        "evidence": "protocolo congelado; sin job/writer; DISABLED",
        "risk": "activar prematuro",
        "action": "no activar",
    },
    {
        "component": "Observabilidad unificada",
        "state": "PARCIAL",
        "evidence": "heartbeats dispersos; panel AC nuevo",
        "risk": "falsos 'saludables'",
        "action": "panel auditoría",
    },
    {
        "component": "Seguridad red/secrets",
        "state": "IMPLEMENTADO Y VERIFICADO",
        "evidence": "dashboard 127.0.0.1; LAB_CONTROL_TOKEN required; sin keys trading",
        "risk": "token en env",
        "action": "no loguear secretos",
    },
    {
        "component": "Órdenes reales",
        "state": "AUSENTE",
        "evidence": "PAPER_ONLY; sin private API trading",
        "risk": "ninguno operativo real",
        "action": "mantener",
    },
]


def runtime_services() -> dict[str, Any]:
    try:
        out = subprocess.check_output(
            ["docker", "compose", "ps", "-a", "--format", "{{.Service}}\t{{.Status}}"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
        rows = {}
        for line in out.splitlines():
            if "\t" in line:
                svc, st = line.split("\t", 1)
                rows[svc.strip()] = st.strip()
        return {"ok": True, "services": rows}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}


def inventory_report() -> dict[str, Any]:
    return {
        "components": COMPONENTS,
        "runtime": runtime_services(),
        "spof": [
            "Host Windows/Docker Desktop (suspend/kill → runners 137)",
            "Único Postgres volume paper_data",
            "market-stream no alimenta fills de runners (acoplamiento débil = bueno/malo)",
        ],
    }
