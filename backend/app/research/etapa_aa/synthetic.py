"""AA3 — pruebas sintéticas del motor (sin usar el período nuevo)."""
from __future__ import annotations

from typing import Any

from ..etapa_z.engine import make_tsmom, simulate_weights, _w_bh_eq


def _series(n: int, start: float, daily_ret: float) -> list[float]:
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1.0 + daily_ret))
    return out


def _flat(n: int, px: float) -> list[float]:
    return [px] * n


def run_synthetic_suite() -> dict[str, Any]:
    n = 80
    times = list(range(n))
    cases: list[dict[str, Any]] = []

    # tendencia alcista fuerte
    up = {
        "BTCUSDT": _series(n, 100, 0.01),
        "ETHUSDT": _series(n, 50, 0.01),
        "SOLUSDT": _series(n, 10, 0.01),
    }
    r_up = simulate_weights(times, up, make_tsmom(28), i0=40, i1=n)
    cases.append(
        {
            "name": "uptrend",
            "ok": r_up["net_vs_initial"] > 0,
            "net": r_up["net_vs_initial"],
            "expect": "neto_positivo",
        }
    )

    # tendencia bajista
    dn = {
        "BTCUSDT": _series(n, 100, -0.01),
        "ETHUSDT": _series(n, 50, -0.01),
        "SOLUSDT": _series(n, 10, -0.01),
    }
    r_dn = simulate_weights(times, dn, make_tsmom(28), i0=40, i1=n)
    cases.append(
        {
            "name": "downtrend_to_cash",
            "ok": r_dn["avg_exposure"] < 0.2 and r_dn["net_vs_initial"] > -50,
            "net": r_dn["net_vs_initial"],
            "exposure": r_dn["avg_exposure"],
            "expect": "cash_dominante_perdidas_limitadas",
        }
    )

    # precios constantes → señal 0 → cash
    flat = {s: _flat(n, 100.0) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    r_fl = simulate_weights(times, flat, make_tsmom(28), i0=40, i1=n)
    cases.append(
        {
            "name": "flat_cash",
            "ok": abs(r_fl["net_vs_initial"]) < 1.0 and r_fl["avg_exposure"] < 0.05,
            "net": r_fl["net_vs_initial"],
            "exposure": r_fl["avg_exposure"],
            "expect": "casi_cero_sin_exposicion",
        }
    )

    # BH-EQ en uptrend gana
    r_eq = simulate_weights(times, up, _w_bh_eq, i0=40, i1=n)
    cases.append(
        {
            "name": "bh_eq_uptrend",
            "ok": r_eq["net_vs_initial"] > 0,
            "net": r_eq["net_vs_initial"],
            "expect": "benchmark_positivo",
        }
    )

    # salto brusco: un día +50% en SOL solo
    jump = {
        "BTCUSDT": _flat(n, 100.0),
        "ETHUSDT": _flat(n, 100.0),
        "SOLUSDT": _flat(n, 100.0),
    }
    jump["SOLUSDT"] = list(jump["SOLUSDT"])
    for i in range(50, n):
        jump["SOLUSDT"][i] = 150.0
    r_j = simulate_weights(times, jump, make_tsmom(28), i0=40, i1=n)
    cases.append(
        {
            "name": "jump_no_crash",
            "ok": (r_j.get("equity") or 0) > 0 and r_j["max_drawdown"] < 1.0,
            "net": r_j["net_vs_initial"],
            "expect": "motor_estable",
        }
    )

    passed = sum(1 for c in cases if c["ok"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "n_ok": passed,
        "n_cases": len(cases),
        "cases": cases,
        "lookahead_note": "señal usa closes[:i] vía índice i; no lee i+1",
    }
