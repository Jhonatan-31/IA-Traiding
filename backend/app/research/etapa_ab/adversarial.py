"""AB10 — auditoría adversarial."""
from __future__ import annotations

from typing import Any


def adversarial_ab(suite: dict[str, Any], attr: dict[str, Any], costs: dict[str, Any]) -> dict[str, Any]:
    d = suite["D28H5"]
    findings = []

    def add(qid, critical, answer, detail=""):
        findings.append({"id": qid, "critical": critical, "answer": answer, "detail": detail})

    pl = d["net_vs_initial"]
    add("q1_vs_cash", pl <= 0, "no_supera_efectivo" if pl <= 0 else "supera_efectivo", f"pl={pl}")
    em = suite["EXP-MATCH-EQ"]["net_vs_initial"]
    add(
        "q2_vs_exp_match",
        False,
        "comparar",
        f"d28={pl} exp_match={em} delta={pl - em} (exp_match descriptivo)",
    )
    f55 = suite["FIXED-55-EQ"]["net_vs_initial"]
    add("q3_vs_fixed55", pl <= f55, "no_supera_fixed55" if pl <= f55 else "supera_fixed55", f"f55={f55}")
    add("q4_single_asset", False, "universo_N3", str(d.get("final_weights")))
    exp_eff = (attr.get("components_usdt") or {}).get("exposure_reduction_descriptive") or 0
    active = (attr.get("components_usdt") or {}).get("active_selection_timing_vs_exp_match") or 0
    add(
        "q5_just_lower_exposure",
        abs(exp_eff) >= abs(active),
        "si_mayormente_exposicion" if abs(exp_eff) >= abs(active) else "posible_activo",
        f"exp_eff={exp_eff} active={active}",
    )
    cost_ratio = (d.get("fees_and_frictions") or 0) / max(1.0, abs(pl) if pl else 1.0)
    add(
        "q6_cost_disproportion",
        (d.get("fees_and_frictions") or 0) > 50,
        "costos_materiales",
        f"fees={d.get('fees_and_frictions')} ratio_vs_|pl|={cost_ratio:.2f}",
    )
    add("q7_higher_spread", False, "stress_no_recalibrado", "AA stress_net negativo; AB no altera costos congelados")
    add("q8_period_selection", False, "holdout_AA_consumido", "análisis AB descriptivo sobre misma ventana")
    add("q9_stat_inconclusive", True, "aa_fue_INCONCLUSA", "IC exceso incluye cero; no nueva prueba indep.")
    add("q10_holdout_fitting", False, "hipotesis_AB_no_corridas", "H1-H3 solo registradas")

    critical = [f for f in findings if f["critical"]]
    beats_f55 = pl > (suite["FIXED-55-EQ"]["net_vs_initial"] or 0)
    return {
        "findings": findings,
        "critical_count": len(critical),
        "summary": (
            f"No supera efectivo (pl={pl}). "
            + (
                "Sí supera FIXED-55 causal — posible timing/selección, no validado prospectivamente."
                if beats_f55
                else "No supera FIXED-55; protección vs BH-EQ compatible con menor exposición."
            )
        ),
    }
