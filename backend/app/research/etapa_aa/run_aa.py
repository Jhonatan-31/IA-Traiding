"""Orquestador Etapa AA — freeze → ingest → synthetic → one-pass → adversarial → veredicto."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..etapa_z.engine import WEIGHT_BUILDERS, _align, load_panel, simulate_weights
from . import EXPECTED_CONFIG_HASH, TARGET_ID, Z_COMMIT
from .adversarial import adversarial_aa
from .evaluate import evaluate_aa_period
from .freeze import manifest_digest, verify_freeze
from .ingest import independence_audit, run_ingest_aa
from .stats import summarize_stats
from .synthetic import run_synthetic_suite


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def reconcile_z_oos() -> dict[str, Any]:
    """Re-ejecuta ventana OOS de Z (índices 255:328 sobre panel 1d alineado) para fidelidad."""
    panel = load_panel(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "1d")
    times, closes = _align(panel)
    # panel ahora incluye post-2025; recortar a span Z original hasta 2025-10-31
    end_z = int(datetime(2025, 11, 1, tzinfo=timezone.utc).timestamp() * 1000) - 1
    times_z = [t for t in times if t <= end_z]
    n = len(times_z)
    closes_z = {s: closes[s][:n] for s in closes}
    is_end = int(n * 0.70)
    oos_end = int(n * 0.90)
    r = simulate_weights(
        times_z, closes_z, WEIGHT_BUILDERS[TARGET_ID](), i0=is_end, i1=oos_end
    )
    expected = 340.5377
    delta = abs(r["net_vs_initial"] - expected)
    return {
        "expected_net": expected,
        "reproduced_net": r["net_vs_initial"],
        "abs_delta": round(delta, 6),
        "ok": delta < 1.0,  # tolerancia por extensión de panel/alineación
        "turns": r.get("turnover_events"),
        "n_bars_z_span": n,
        "oos_i0": is_end,
        "oos_i1": oos_end,
        "note": "136 turnover_events en Z = ajustes de notional, no 136 round-trips",
    }


def decide(eval_pack: dict[str, Any], adv: dict[str, Any], stats: dict[str, Any], indep: dict[str, Any]) -> dict[str, Any]:
    p = eval_pack.get("primary") or {}
    d = (eval_pack.get("results") or {}).get(TARGET_ID) or {}
    b = (eval_pack.get("results") or {}).get("Z-BH-EQ") or {}
    reasons: list[str] = []
    excess = p.get("excess_net")
    if excess is None or excess <= 0:
        reasons.append("exceso_neto_no_positivo")
    dd_d, dd_b = d.get("max_drawdown") or 0, b.get("max_drawdown") or 0.01
    if dd_d > max(0.05, 1.5 * dd_b):
        reasons.append("drawdown_desproporcionado")
    if (d.get("cost_stress_net") or 0) <= 0:
        reasons.append("stress_costos_neto_no_positivo")
    if adv.get("blocks_promotion"):
        reasons.append("adversarial_critico")
    boot = (stats.get("bootstrap_excess_daily") or {})
    if boot.get("ok") and boot.get("ci_includes_zero"):
        reasons.append("ic95_exceso_diario_incluye_cero")
    if (stats.get("top5_positive_diff_share_of_positive") or 0) > 0.8:
        reasons.append("concentracion_top5_dias")
    if indep.get("label") == "evaluacion_adicional_no_independiente":
        reasons.append("independencia_insuficiente")

    n = (eval_pack.get("period") or {}).get("n_bars") or 0
    if n < 60:
        verdict = "INCONCLUSA"
        reasons.append("muestra_corta")
    elif reasons:
        # si solo IC incluye cero pero exceso puntual >0 → inconclusa; si exceso≤0 → rechazada
        if excess is not None and excess <= 0:
            verdict = "RECHAZADA"
        elif "adversarial_critico" in reasons or "independencia_insuficiente" in reasons:
            verdict = "RECHAZADA" if excess is not None and excess <= 0 else "INCONCLUSA"
        elif excess is not None and excess > 0 and set(reasons) <= {"ic95_exceso_diario_incluye_cero"}:
            verdict = "INCONCLUSA"
        else:
            verdict = "RECHAZADA" if excess is not None and excess <= 0 else "INCONCLUSA"
    else:
        verdict = "CANDIDATA PARA REVISIÓN DE PRUEBA PROSPECTIVA PAPER"

    return {
        "verdict": verdict,
        "reasons": reasons,
        "activate": False,
        "authorize_paper_trial": False,
        "note": "Candidata ≠ autorización de activación",
    }


def run_etapa_aa(*, skip_ingest: bool = False) -> dict[str, Any]:
    exp_id = f"AA-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    freeze = verify_freeze()
    if not freeze.get("ok"):
        return {
            "etapa": "AA",
            "experiment_id": exp_id,
            "available": False,
            "blocked_by": "AA0_freeze",
            "freeze": freeze,
            "claim": {"verdict": "INCONCLUSA", "activate": False},
        }

    # Independencia: clasificar ANTES de la ingesta AA (post-download ≠ uso previo).
    indep_pre = independence_audit()
    ingest = {"skipped": True, "independence": indep_pre, "independence_pre_ingest": indep_pre}
    if not skip_ingest:
        print("AA: ingest 1d…", flush=True)
        ingest = run_ingest_aa(force=False)
        ingest["independence_pre_ingest"] = indep_pre
        # Decisión usa pre_ingest; post_ingest solo documenta que AA ya escribió Parquet.
        ingest["independence_post_ingest"] = ingest.get("independence")
        ingest["independence"] = indep_pre

    print("AA: synthetic…", flush=True)
    synthetic = run_synthetic_suite()
    if not synthetic.get("ok"):
        return {
            "etapa": "AA",
            "experiment_id": exp_id,
            "available": False,
            "blocked_by": "AA3_synthetic",
            "freeze": freeze,
            "synthetic": synthetic,
            "ingest": ingest,
            "claim": {"verdict": "INCONCLUSA", "activate": False},
        }

    print("AA: reconcile Z OOS…", flush=True)
    recon = reconcile_z_oos()

    print("AA: one-pass eval…", flush=True)
    evaluation = evaluate_aa_period()
    if not evaluation.get("ok"):
        return {
            "etapa": "AA",
            "experiment_id": exp_id,
            "available": False,
            "blocked_by": "AA4_eval",
            "freeze": freeze,
            "ingest": ingest,
            "synthetic": synthetic,
            "z_reconcile": recon,
            "evaluation": evaluation,
            "claim": {"verdict": "INCONCLUSA", "activate": False},
        }

    stats = summarize_stats(evaluation)
    adv = adversarial_aa(evaluation, freeze_ok=True)
    indep = (ingest.get("independence") if isinstance(ingest, dict) else None) or indep_pre
    decision = decide(evaluation, adv, stats, indep)

    # strip heavy arrays from top-level persistence duplicate — keep curves for dashboard
    out = {
        "etapa": "AA",
        "experiment_id": exp_id,
        "paper_only": True,
        "available": True,
        "git_rev": _git_rev(),
        "z_commit": Z_COMMIT,
        "config_hash": freeze["config_hash"],
        "expected_config_hash": EXPECTED_CONFIG_HASH,
        "hash_match": True,
        "manifest_digest": manifest_digest(freeze),
        "freeze": freeze,
        "ingest": {
            k: ingest.get(k)
            for k in ("ok", "ingested_months", "expected_months", "independence", "coverage_1d", "period_candidate", "downloaded_at", "skipped")
            if k in ingest
        },
        "synthetic": synthetic,
        "z_reconcile": recon,
        "evaluation": {
            "ok": True,
            "period": evaluation["period"],
            "results": evaluation["results"],
            "primary": evaluation["primary"],
            "consumed": True,
            "consumed_note": evaluation["consumed_note"],
            "evaluated_at": evaluation["evaluated_at"],
        },
        "equity_curves": evaluation.get("curves"),
        "stats": stats,
        "adversarial": adv,
        "decision": decision,
        "claim": {
            "verdict": decision["verdict"],
            "activate": False,
            "declare_profitable": False,
            "authorize_paper_trial": False,
            "reason": "; ".join(decision["reasons"]) or "cumple reglas prerregistradas (sin autorización de activación)",
        },
        "microstructure_aa8": {
            "status": "not_mixed_with_primary",
            "note": "Sin BBO/taker en Parquet; no se alteró D28H5",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return out


def persist(result: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    archive = p.with_name(p.stem + "_" + result.get("experiment_id", "x") + p.suffix)
    text = json.dumps(result, indent=2, default=str)
    archive.write_text(text, encoding="utf-8")
    p.write_text(text, encoding="utf-8")
    return archive


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/artifacts/history/etapa_aa_results.json")
    ap.add_argument("--skip-ingest", action="store_true")
    args = ap.parse_args()
    r = run_etapa_aa(skip_ingest=args.skip_ingest)
    path = persist(r, args.out)
    print(
        json.dumps(
            {
                "wrote": str(path),
                "verdict": (r.get("claim") or {}).get("verdict"),
                "primary": (r.get("evaluation") or {}).get("primary"),
                "exp": r.get("experiment_id"),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
