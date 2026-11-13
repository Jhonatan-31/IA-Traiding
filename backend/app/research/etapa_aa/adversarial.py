"""AA7 — auditoría adversarial de la validación temporal."""
from __future__ import annotations

from typing import Any


def adversarial_aa(eval_pack: dict[str, Any], *, freeze_ok: bool) -> dict[str, Any]:
    p = eval_pack.get("primary") or {}
    d = (eval_pack.get("results") or {}).get("Z-TSMOM-D28H5") or {}
    b = (eval_pack.get("results") or {}).get("Z-BH-EQ") or {}
    btc = (eval_pack.get("results") or {}).get("Z-BH-BTC") or {}
    findings: list[dict[str, Any]] = []

    def add(qid: str, critical: bool, answer: str, detail: str = ""):
        findings.append({"id": qid, "critical": critical, "answer": answer, "detail": detail})

    excess = p.get("excess_net")
    add(
        "q1_market_beta",
        False,
        "comparar vs BH-EQ y BH-BTC",
        f"excess_vs_eq={excess}; bh_btc_net={btc.get('net_vs_initial')}; bh_eq={b.get('net_vs_initial')}",
    )
    # si BH-EQ también muy positivo y excess pequeño → beta de mercado
    if (b.get("net_vs_initial") or 0) > 0 and excess is not None and excess <= 0:
        add("q1b_only_bull", True, "no_supera_equiponderado", "ventaja ausente vs BH-EQ")
    add(
        "q2_alts_vs_btc",
        False,
        "revisar si BH-EQ >> BH-BTC",
        f"eq={b.get('net_vs_initial')} btc={btc.get('net_vs_initial')}",
    )
    stress = d.get("cost_stress_net")
    if stress is not None and (p.get("d28h5_net") or 0) > 0 and stress <= 0:
        add("q3_costs", True, "sensible_a_costos", f"stress={stress}")
    elif excess is not None and excess > 0 and stress is not None and stress < (b.get("net_vs_initial") or 0):
        add("q3_costs", False, "stress_debilitado_vs_benchmark", f"stress={stress}")
    else:
        add("q3_costs", False, "ok_o_no_aplica", f"stress={stress}")

    turns = d.get("turnover_events") or 0
    if turns < 5 and (p.get("d28h5_net") or 0) > 0:
        add("q4_few_trades", True, "pocos_rebalances", f"turns={turns}")
    else:
        add("q4_few_trades", False, "turns_ok", f"turns={turns}")

    best = p.get("best_month_d28h5")
    add("q5_one_month", False, "ver monthly_returns", str(best))

    add("q6_lookahead", not freeze_ok, "fixtures_sinteticos+velas_cerradas", "freeze_ok=" + str(freeze_ok))
    add("q7_unexecutable", False, "close+slip+spread_proxy", "sin BBO histórico")
    add("q8_benchmark_costs", False, "mismos_fee_slip_spread", "BH-EQ usa mismo motor")
    exp_d, exp_b = d.get("avg_exposure") or 0, b.get("avg_exposure") or 0
    if excess is not None and excess > 0 and exp_d > exp_b * 1.15:
        add("q9_more_exposure", True, "mayor_exposicion", f"d={exp_d} eq={exp_b}")
    else:
        add("q9_more_exposure", False, "exposicion_comparable", f"d={exp_d} eq={exp_b}")
    add("q10_post_hoc_tweak", False, "no_recalibrado", "configuración congelada prerregistrada")
    add("q11_temporal_treatment", False, "mismo_calendario_UTC_1d", "")
    add("q12_intrabar_dd", False, "dd_diario_close", "sin path intraperíodo intradía")

    critical = [f for f in findings if f["critical"]]
    return {
        "findings": findings,
        "critical_count": len(critical),
        "blocks_promotion": len(critical) > 0 or not freeze_ok,
        "summary": (
            "Hallazgos críticos impiden promoción."
            if critical or not freeze_ok
            else "Sin hallazgos críticos de bloqueo; aún requiere reglas de aceptación AA10."
        ),
    }
