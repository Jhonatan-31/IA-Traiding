"""Orquestador Etapa AC — auditoría, reconciliación AB, sin activación."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..etapa_aa.freeze import verify_freeze
from ..etapa_ab.prospect import OBSERVATION_ENABLED, observation_status
from . import AB_COMMIT, EXPECTED_CONFIG_HASH, PROSPECT_MUST_REMAIN
from .findings import findings_summary
from .inventory import inventory_report
from .reconcile_ab import reconcile_ab_economics


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _position_counts() -> dict[str, Any]:
    import os

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:120]}

    url = os.environ.get("DATABASE_URL")
    if not url:
        return {"ok": False, "reason": "DATABASE_URL_missing"}
    try:
        counts = {}
        with psycopg.connect(url, row_factory=dict_row) as conn:
            with conn.cursor() as c:
                for name, table in (
                    ("demo", "demo_positions"),
                    ("active", "active_positions"),
                    ("lab", "lab_positions"),
                    ("express", "express_positions"),
                    ("virt", "virt_positions"),
                ):
                    c.execute(f"SELECT count(*) AS n FROM {table}")
                    counts[name] = int(c.fetchone()["n"])
                c.execute("SELECT status FROM demo_state WHERE id=1")
                demo_st = c.fetchone()
                c.execute("SELECT status FROM active_state WHERE id=1")
                active_st = c.fetchone()
        return {
            "ok": True,
            "positions": counts,
            "demo_status": demo_st["status"] if demo_st else None,
            "active_status": active_st["status"] if active_st else None,
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}


def cost_sensitivity_note(fees: str, net: str) -> dict[str, Any]:
    """Sensibilidad descriptiva sin recalibrar estrategia."""
    from decimal import Decimal

    f = Decimal(fees)
    n = Decimal(net)
    return {
        "baseline_net": str(n),
        "baseline_fees": str(f),
        "if_fees_x1_5_net_approx": str(n - (f * Decimal("0.5"))),
        "if_fees_x2_net_approx": str(n - f),
        "note": "Aprox. lineal: restar fricción adicional al neto ya cargado; no es re-simulación",
    }


def run_etapa_ac() -> dict[str, Any]:
    exp_id = f"AC-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    freeze = verify_freeze()
    recon = reconcile_ab_economics()
    findings = findings_summary()
    inv = inventory_report()
    prospect = observation_status()
    positions = _position_counts()

    # Escalate F01 if positions > 0 and runners down
    runtime = inv.get("runtime") or {}
    services = runtime.get("services") or {}
    runners_down = []
    for svc in ("demo-runner", "active-runner", "trade-executor"):
        st = services.get(svc, "")
        if st and "Up" not in st:
            runners_down.append(svc)

    pos = (positions.get("positions") or {}) if positions.get("ok") else {}
    open_n = sum(int(v or 0) for v in pos.values())
    f01_critical_now = open_n > 0 and len(runners_down) > 0

    verdicts = {
        "infraestructura": "PARCIAL" if runners_down else "VERIFICADO",
        "datos_live": "VERIFICADO",
        "datos_historicos": "PARCIAL",
        "estrategias_research": "VERIFICADO",
        "ejecucion_simulada": "PARCIAL",
        "riesgo": "PARCIAL" if runners_down else "VERIFICADO",
        "contabilidad": "VERIFICADO",
        "backtesting": "VERIFICADO",
        "seguridad": "VERIFICADO",
        "confiabilidad_operativa": "CRÍTICO" if f01_critical_now else "PARCIAL",
        "observacion_prospectiva": "PARCIAL",
        "dashboard": "PARCIAL",
    }

    economic = recon.get("economic_verdict_ac")
    assert prospect.get("enabled") is False or OBSERVATION_ENABLED is False
    prospect_ok = (
        prospect.get("status") == PROSPECT_MUST_REMAIN
        or prospect.get("enabled") is False
    )

    out = {
        "etapa": "AC",
        "experiment_id": exp_id,
        "available": True,
        "paper_only": True,
        "git_rev": _git_rev(),
        "ab_commit_expected": AB_COMMIT,
        "config_hash": freeze.get("config_hash"),
        "hash_match": freeze.get("hash_match") and freeze.get("config_hash") == EXPECTED_CONFIG_HASH,
        "freeze_ok": freeze.get("ok"),
        "verdicts": verdicts,
        "economic": {
            "verdict": economic,
            "reconcile": recon,
            "cost_sensitivity": cost_sensitivity_note(
                recon["costs"]["total"], recon["pl"]["d28h5"]
            ),
        },
        "findings": findings,
        "inventory": inv,
        "positions": positions,
        "runners_down": runners_down,
        "f01_critical_now": f01_critical_now,
        "prospect": {
            **prospect,
            "audit_ok_disabled": prospect_ok,
            "must_remain": PROSPECT_MUST_REMAIN,
            "activated": False,
        },
        "roadmap": [
            {
                "stage": 1,
                "title": "Integridad y seguridad",
                "focus": "P0 runners/protecciones; permisos",
                "verifiable": "runners alineados XOR posiciones=0 + alertas",
            },
            {
                "stage": 2,
                "title": "Ejecución y costos",
                "focus": "modelo fill versionado; no reescribir Z/AA/AB",
                "verifiable": "suite sensibilidad documentada",
            },
            {
                "stage": 3,
                "title": "Continuidad",
                "focus": "detector suspensión/huecos",
                "verifiable": "SLI gap heartbeats",
            },
            {
                "stage": 4,
                "title": "Contabilidad/evidencia",
                "focus": "invariantes ledger + campos Vision",
                "verifiable": "tests invariantes + schema enrich",
            },
            {
                "stage": 5,
                "title": "Observación prospectiva",
                "focus": "implementar writer; revisión autorización",
                "verifiable": "AB-PROSPECT still disabled until user OK",
            },
            {
                "stage": 6,
                "title": "Nuevas variantes investigación",
                "focus": "solo tras confianza datos/simulador; no holdout AA",
                "verifiable": "prerregistro fuera de AA",
            },
        ],
        "claim": {
            "activate": False,
            "activate_prospect": False,
            "economic_verdict": economic,
            "reason": recon.get("rationale"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return out


def persist(result: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2, default=str)
    archive = p.with_name(p.stem + "_" + result.get("experiment_id", "x") + p.suffix)
    archive.write_text(text, encoding="utf-8")
    p.write_text(text, encoding="utf-8")
    return archive


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/artifacts/history/etapa_ac_results.json")
    args = ap.parse_args()
    r = run_etapa_ac()
    path = persist(r, args.out)
    print(
        json.dumps(
            {
                "wrote": str(path),
                "economic": (r.get("claim") or {}).get("economic_verdict"),
                "findings_n": (r.get("findings") or {}).get("n"),
                "runners_down": r.get("runners_down"),
                "f01_critical_now": r.get("f01_critical_now"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
