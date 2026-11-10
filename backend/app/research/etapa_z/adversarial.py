"""Z9 — auditoría adversarial de resultados favorables."""
from __future__ import annotations

from typing import Any


def adversarial_review(results: dict[str, Any]) -> dict[str, Any]:
    """Intenta refutar candidatas. Bloquea promoción si hay hallazgos críticos."""
    findings: list[dict[str, Any]] = []
    oos = results.get("oos") or {}
    bh = (oos.get("Z-BH-EQ") or {}).get("net_vs_initial")
    bh_btc = (oos.get("Z-BH-BTC") or {}).get("net_vs_initial")

    for hid, pack in oos.items():
        if pack.get("kind") == "benchmark" or not pack.get("ok"):
            continue
        notes: list[str] = []
        critical = False
        net = pack.get("net_vs_initial")
        if net is not None and bh is not None and net <= bh:
            notes.append("no_supera_benchmark_equiponderado")
            critical = True
        if net is not None and net <= 0:
            notes.append("neto_no_positivo")
            critical = True
        if (pack.get("cost_stress_net") or 0) <= 0:
            notes.append("sensible_a_costos")
            critical = True
        if (pack.get("avg_exposure") or 0) > 0.95 and net is not None and bh_btc is not None:
            if abs(net - bh_btc) < abs(bh_btc) * 0.05:
                notes.append("posible_proxy_de_buy_and_hold")
        if (pack.get("turnover_events") or 0) < 5:
            notes.append("pocas_rebalances_dependencia_muestra")
            critical = True
        # universo pequeño
        if hid.startswith("Z-RS"):
            notes.append("universo_N3_no_generalizable")
        findings.append(
            {
                "id": hid,
                "critical": critical,
                "notes": notes,
                "blocks_promotion": critical,
            }
        )

    # preguntas obligatorias (checklist)
    checklist = {
        "future_info": False,
        "winner_markets_selected_ex_post": "universo fijo BTC/ETH/SOL predefinido",
        "too_many_params": False,
        "optimistic_costs": "fee 10bps + slip 5bps + spread proxy; stress +50% frictions",
        "few_trades_dependency": "revisar turnover_events por hipótesis",
        "higher_exposure_artifact": "comparar vs BH-EQ y BH-BTC",
        "mismatched_periods": False,
        "unexecutable_prices": "close+slip; sin BBO histórico",
        "omitted_failed_orders": "simulación completa long-only",
        "overstated_precision": "sin reconstrucción de libro",
        "cost_increase_kills_edge": "ver cost_stress_net",
        "vanishes_vs_simple_benchmark": "ver vs Z-BH-EQ / Z-BH-BTC",
    }
    unblocked = [f for f in findings if not f["blocks_promotion"]]
    return {
        "findings": findings,
        "checklist": checklist,
        "promote_any": False,  # sin holdout virgen + política etapa: nunca auto-promover
        "unblocked_but_not_promoted": [f["id"] for f in unblocked],
        "summary": (
            "Hay líneas no bloqueadas por adversarial duro, pero sin holdout temporal virgen "
            "no se promueven. El resto queda descartado por benchmark/costos/muestra/universo."
            if unblocked
            else "Todas las hipótesis quedan bloqueadas por controles adversariales o neto no positivo."
        ),
    }
