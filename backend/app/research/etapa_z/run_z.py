"""Orquestador Etapa Z PRO — auditar, evaluar, adversariar, persistir."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adversarial import adversarial_review
from .audit_z0 import run_audit_z0
from .engine import evaluate_hypothesis, _align
from .hypotheses import HYPOTHESES, list_hypotheses
from .micro_diag import diagnose_derivatives, diagnose_microstructure
from . import COST_RT, FEE_RATE, HOLDOUT_W_CONSUMED, INITIAL_CAPITAL, SLIP_RATE, SPREAD_BPS


def _git_rev() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _config_hash() -> str:
    blob = json.dumps(
        {
            "hypotheses": {k: {kk: vv for kk, vv in v.items() if kk != "economic"} for k, v in HYPOTHESES.items()},
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
            "spread_bps": SPREAD_BPS,
            "capital": INITIAL_CAPITAL,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _splits(n: int) -> dict[str, Any]:
    """70% IS / 20% OOS-Z / 10% holdout W consumido (no evaluar como independiente)."""
    is_end = int(n * 0.70)
    oos_end = int(n * 0.90)
    return {
        "n": n,
        "is": {"i0": 40, "i1": is_end},
        "oos": {"i0": is_end, "i1": oos_end},
        "holdout_w_consumed_slice": {"i0": oos_end, "i1": n, "usable_as_independent": False},
        "note": "Holdout W ya examinado en etapas W/X/Y — no se reporta como OOS virgen",
    }


def run_etapa_z(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    exp_id = f"Z-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    audit = run_audit_z0(symbols)
    if not audit.get("continue_to_economic_research"):
        return {
            "etapa": "Z",
            "experiment_id": exp_id,
            "available": False,
            "blocked_by": "Z0",
            "audit": audit,
            "claim": {"activate": False, "verdict": "BLOQUEADO_INTEGRIDAD"},
        }

    from .engine import load_panel

    print("Z: loading 1d/4h parquet…", flush=True)
    panel_d = load_panel(symbols, "1d")
    panel_4 = load_panel(symbols, "4h")
    times_d, closes_d = _align(panel_d)
    times_4, closes_4 = _align(panel_4)
    split_d = _splits(len(times_d))
    split_4 = _splits(len(times_4))
    cache = {"1d": (times_d, closes_d), "4h": (times_4, closes_4)}
    print(f"Z: bars 1d={len(times_d)} 4h={len(times_4)}", flush=True)

    is_res: dict[str, Any] = {}
    oos_res: dict[str, Any] = {}
    for hid, meta in HYPOTHESES.items():
        sp = split_4 if meta["tf"] == "4h" else split_d
        print(f"Z: eval {hid}…", flush=True)
        is_res[hid] = evaluate_hypothesis(
            hid, i0=sp["is"]["i0"], i1=sp["is"]["i1"], panel_cache=cache
        )
        oos_res[hid] = evaluate_hypothesis(
            hid, i0=sp["oos"]["i0"], i1=sp["oos"]["i1"], panel_cache=cache
        )

    adv = adversarial_review({"oos": oos_res})

    # clasificación
    discarded, exploratory, candidates = [], [], []
    bh_eq = (oos_res.get("Z-BH-EQ") or {}).get("net_vs_initial") or 0.0
    for hid, pack in oos_res.items():
        if pack.get("kind") == "benchmark":
            continue
        row = {
            "id": hid,
            "net_oos": pack.get("net_vs_initial"),
            "dd": pack.get("max_drawdown"),
            "vs_bh_eq": None if pack.get("net_vs_initial") is None else round(pack["net_vs_initial"] - bh_eq, 4),
            "stress": pack.get("cost_stress_net"),
            "exposure": pack.get("avg_exposure"),
        }
        adv_f = next((f for f in adv["findings"] if f["id"] == hid), {})
        if pack.get("net_vs_initial", 0) <= 0 or adv_f.get("blocks_promotion"):
            discarded.append({**row, "reason": adv_f.get("notes") or ["neto_no_positivo"]})
        elif pack.get("net_vs_initial", 0) > bh_eq and (pack.get("cost_stress_net") or 0) > 0:
            # aún exploratorio: sin holdout virgen
            exploratory.append({**row, "status": "exploratory_no_virgin_holdout"})
        else:
            discarded.append({**row, "reason": ["no_mejora_benchmark_o_stress"]})

    micro = diagnose_microstructure()
    deriv = diagnose_derivatives()

    if candidates:
        verdict = "EXISTE UNA CANDIDATA PARA VALIDACIÓN PROSPECTIVA VIRTUAL"
    elif exploratory:
        verdict = "EXISTEN HIPÓTESIS EXPLORATORIAS, SIN VALIDAR"
    else:
        verdict = "NINGUNA HIPÓTESIS PROMETEDORA"

    out = {
        "etapa": "Z",
        "experiment_id": exp_id,
        "paper_only": True,
        "available": True,
        "git_rev": _git_rev(),
        "config_hash": _config_hash(),
        "costs": {
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
            "spread_bps": SPREAD_BPS,
            "cost_rt": COST_RT,
            "capital": INITIAL_CAPITAL,
        },
        "data": {
            "symbols": symbols,
            "span": "2024-11-01 → 2025-10-31",
            "source": "binance_vision_parquet_ohlcv",
            "holdout_w_consumed": HOLDOUT_W_CONSUMED,
        },
        "splits_1d": split_d,
        "splits_4h": split_4,
        "audit_z0": audit,
        "hypotheses": list_hypotheses(),
        "in_sample": is_res,
        "oos": oos_res,
        "adversarial": adv,
        "classification": {
            "discarded": discarded,
            "exploratory": exploratory,
            "candidates_for_virtual_validation": candidates,
        },
        "microstructure": micro,
        "derivatives": deriv,
        "literature_summary": {
            "tsmom_classic": "Moskowitz, Ooi, Pedersen (2012) JFE — TSMOM 1–12m en futuros",
            "crypto_realistic_costs": (
                "Han/Kang/Ryu (ACFR PDF) — con costos reales muchos portfolios momentum "
                "se liquidan; TSMOM más fuerte que CSMOM"
            ),
            "liu_tsyviniski": "Momentum cripto a 1–8 semanas documentado; no garantiza edge spot retail post-costos",
            "our_inference": "Horizontes mayores merecen prueba; no implica rentabilidad en BTC/ETH/SOL 2024-25",
        },
        "claim": {
            "activate": False,
            "declare_profitable": False,
            "verdict": verdict,
            "reason": (
                "Sin holdout temporal virgen post-consumo W; "
                + (
                    "ninguna hipótesis supera benchmark+costos+adversarial."
                    if not exploratory and not candidates
                    else "hallazgos solo exploratorios."
                )
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return out


def persist(result: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # no sobrescribir: si existe, añadir timestamp
    if p.exists():
        p = p.with_name(p.stem + "_" + result.get("experiment_id", "x") + p.suffix)
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/artifacts/history/etapa_z_results.json")
    args = ap.parse_args()
    r = run_etapa_z()
    path = persist(r, args.out)
    # también copia estable para el dashboard (último)
    latest = Path(args.out)
    latest.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(path), "latest": str(latest), "verdict": r["claim"]["verdict"], "exp": r["experiment_id"]}, indent=2))


if __name__ == "__main__":
    main()
