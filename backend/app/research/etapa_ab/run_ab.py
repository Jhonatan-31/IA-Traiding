"""Orquestador Etapa AB."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..etapa_aa import EVAL_END_MS, EVAL_START_MS
from ..etapa_z.engine import _align, load_panel, make_tsmom
from . import EXPECTED_CONFIG_HASH, TARGET_ID
from .adversarial import adversarial_ab
from .attribution import attribute_aa_window
from .benchmarks import run_benchmark_suite
from .costs import audit_costs
from .hypotheses import list_hypotheses
from .prospect import observation_status
from .risk import analyze_risk
from .simulate_ledger import simulate_ledger
from .validity import audit_validity


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def decide(attr: dict[str, Any], risk: dict[str, Any], adv: dict[str, Any], suite: dict[str, Any]) -> dict[str, Any]:
    pl = suite["D28H5"]["net_vs_initial"]
    f55 = suite["FIXED-55-EQ"]["net_vs_initial"]
    comps = attr.get("components_usdt") or {}
    active = comps.get("active_selection_timing_vs_exp_match") or 0
    exp_eff = comps.get("exposure_reduction_descriptive") or 0
    beats_cash = pl > 0
    beats_f55 = pl > f55 + 1.0
    active_material = active > 20.0

    # Prioridad: evidencia causal vs FIXED-55 > narrativa solo-exposición vs BH-EQ.
    if beats_f55 and active_material:
        # Valor vs exposición fija causal; aún no supera efectivo ni está validado OOS nuevo.
        verdict = "POSIBLE VALOR ADICIONAL, AÚN NO VALIDADO"
    elif not beats_cash and abs(exp_eff) >= abs(active) and exp_eff > 0:
        verdict = "VENTAJA RELATIVA EXPLICADA POR MENOR EXPOSICIÓN"
    elif not beats_cash and active <= 5 and not beats_f55:
        verdict = "SIN VENTAJA DEMOSTRADA"
    elif beats_cash and beats_f55:
        verdict = "POSIBLE VALOR ADICIONAL, AÚN NO VALIDADO"
    else:
        verdict = "VENTAJA RELATIVA EXPLICADA POR MENOR EXPOSICIÓN"

    return {
        "verdict": verdict,
        "activate": False,
        "authorize_paper": False,
        "reasons": {
            "beats_cash": beats_cash,
            "beats_fixed55": beats_f55,
            "exposure_effect": exp_eff,
            "active_vs_exp_match": active,
            "adversarial_critical": adv.get("critical_count"),
        },
    }


def run_etapa_ab() -> dict[str, Any]:
    exp_id = f"AB-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    validity = audit_validity()
    if not validity.get("ok"):
        return {
            "etapa": "AB",
            "experiment_id": exp_id,
            "available": False,
            "blocked_by": "AB0_validity",
            "validity": validity,
            "claim": {"verdict": "SIN VENTAJA DEMOSTRADA", "activate": False},
        }

    print("AB: load panel…", flush=True)
    panel = load_panel(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "1d")
    times, closes = _align(panel)
    i0 = next(i for i, t in enumerate(times) if t >= EVAL_START_MS)
    i1 = next((i for i, t in enumerate(times) if t > EVAL_END_MS), len(times))

    # exposición media D28 para control descriptivo (ex post)
    d28_pre = simulate_ledger(times, closes, make_tsmom(28), i0=i0, i1=i1)
    avg_exp = d28_pre["avg_exposure"]

    print("AB: benchmarks…", flush=True)
    suite_raw = run_benchmark_suite(times, closes, i0=i0, i1=i1, d28_avg_exposure=avg_exp)
    full_d28 = suite_raw.pop("_full_d28")
    suite_raw.pop("_full_exp_match", None)
    suite_raw.pop("_full_bh_eq", None)
    # attach duration fields from full
    suite_raw["D28H5"]["max_dd_duration_bars"] = full_d28.get("max_dd_duration_bars")
    suite_raw["D28H5"]["vol_daily"] = full_d28.get("vol_daily")
    suite_raw["D28H5"]["final_weights"] = full_d28.get("final_weights")
    suite_raw["D28H5"]["worst_week"] = full_d28.get("worst_week")
    suite_raw["D28H5"]["worst_month"] = full_d28.get("worst_month")
    suite_raw["D28H5"]["monthly_returns"] = full_d28.get("monthly_returns")
    suite_raw["D28H5"]["cost_split"] = full_d28.get("cost_split")
    suite_raw["D28H5"]["accounting"] = full_d28.get("accounting")
    suite_raw["D28H5"]["buys"] = full_d28.get("buys")
    suite_raw["D28H5"]["sells"] = full_d28.get("sells")
    suite_raw["D28H5"]["rebalances_real"] = full_d28.get("rebalances_real")
    suite_raw["D28H5"]["signal_changes"] = full_d28.get("signal_changes")
    suite_raw["D28H5"]["notional_traded"] = full_d28.get("notional_traded")
    suite_raw["D28H5"]["cost_per_rebalance"] = full_d28.get("cost_per_rebalance")
    suite_raw["D28H5"]["cost_by_symbol"] = full_d28.get("cost_by_symbol")
    suite_raw["D28H5"]["cost_by_month"] = full_d28.get("cost_by_month")

    attr = attribute_aa_window(suite_raw)
    costs = audit_costs(full_d28, aa_reported_costs=72.73)
    risk = analyze_risk(suite_raw, attr)
    adv = adversarial_ab(suite_raw, attr, costs)
    decision = decide(attr, risk, adv, suite_raw)
    hyp = list_hypotheses()
    prospect = observation_status()

    # strip heavy
    suite = {k: v for k, v in suite_raw.items() if not k.startswith("_")}
    for k, v in suite.items():
        if isinstance(v, dict):
            v.pop("daily_returns", None)
            v.pop("days", None)
            v.pop("trades", None)

    out = {
        "etapa": "AB",
        "experiment_id": exp_id,
        "available": True,
        "paper_only": True,
        "git_rev": _git_rev(),
        "config_hash": EXPECTED_CONFIG_HASH,
        "hash_match": True,
        "period": {
            "start_ms": EVAL_START_MS,
            "end_ms": EVAL_END_MS,
            "i0": i0,
            "i1": i1,
            "n_bars": i1 - i0,
            "label": "AA holdout — análisis descriptivo AB, no nueva prueba independiente",
            "consumed_holdout": True,
        },
        "validity": {
            "ok": validity["ok"],
            "checks": validity["checks"],
            "d28h5_rules": validity["d28h5_rules"],
        },
        "suite": suite,
        "attribution": attr,
        "costs_audit": costs,
        "risk": risk,
        "adversarial": adv,
        "hypotheses_exploratory": hyp,
        "prospect": prospect,
        "decision": decision,
        "claim": {
            "verdict": decision["verdict"],
            "activate": False,
            "authorize_paper": False,
            "declare_profitable": False,
            "reason": decision["verdict"],
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
    ap.add_argument("--out", default="/artifacts/history/etapa_ab_results.json")
    args = ap.parse_args()
    r = run_etapa_ab()
    path = persist(r, args.out)
    print(
        json.dumps(
            {
                "wrote": str(path),
                "verdict": (r.get("claim") or {}).get("verdict"),
                "attr": (r.get("attribution") or {}).get("components_usdt"),
                "exp": r.get("experiment_id"),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
