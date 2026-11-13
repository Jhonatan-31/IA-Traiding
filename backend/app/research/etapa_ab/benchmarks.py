"""Comparadores justos — distingue descriptivos vs causalmente implementables."""
from __future__ import annotations

from typing import Any, Callable

from ..etapa_z.engine import make_tsmom, _w_bh_btc, _w_bh_eq
from .simulate_ledger import simulate_ledger


def _w_cash(i, closes):
    return {s: 0.0 for s in closes}


def make_fixed_exposure_eq(target_exp: float) -> Callable:
    """Exposición fija target_exp en equiponderado; resto cash. DESCRIPTIVO si target_exp es ex-post."""

    def _w(i, closes):
        n = len(closes)
        if n == 0:
            return {}
        w = target_exp / n
        return {s: w for s in closes}

    return _w


def make_bh_eq_no_daily_rebalance(times, closes, i0, i1):
    """Buy&hold equiponderado: compra 1/3 una vez al inicio, sin rebalance diario.

    Implementado como pesos que mantienen cantidades fijas tras compra inicial
    vía simulación especial: primer día target 1/3, luego pesos = actuales (no force).
    """
    bought = {"done": False}

    def _w(i, closes_):
        if not bought["done"]:
            bought["done"] = True
            return {s: 1.0 / 3.0 for s in closes_}
        # señal "mantener" ≈ no rebalance: devolver pesos actuales aproximados
        # El motor rebalancea hacia w_tgt; para B&H puro usamos umbral alto vía
        # pesos que siguen el valor relativo si no forzamos — aquí devolvemos
        # los mismos 1/3 lo cual SÍ rebalancea. Por eso usamos simulación aparte.
        return {s: 1.0 / 3.0 for s in closes_}

    return _w


def simulate_true_bh_eq(times, closes, i0, i1, *, capital: float = 1000.0) -> dict[str, Any]:
    """Compra única equiponderada al close de i0; hold hasta i1-1. Costo solo al buy."""
    from .simulate_ledger import trade_cost

    symbols = list(closes.keys())
    px0 = {s: closes[s][i0] for s in symbols}
    # gastar capital en 1/3 cada uno con costo
    cash = capital
    holdings = {s: 0.0 for s in symbols}
    fees = 0.0
    for s in symbols:
        tgt = capital / 3.0
        cost = trade_cost(tgt)
        spend = tgt + cost
        if spend > cash:
            tgt = max(0.0, cash - cost)
            cost = trade_cost(tgt)
            spend = tgt + cost
        cash -= spend
        holdings[s] = tgt / px0[s] if px0[s] else 0.0
        fees += cost
    peak = capital
    max_dd = 0.0
    exp_sum = 0.0
    n = 0
    for i in range(i0, i1):
        px = {s: closes[s][i] for s in symbols}
        eq = cash + sum(holdings[s] * px[s] for s in symbols)
        peak = max(peak, eq)
        max_dd = max(max_dd, 1.0 - eq / peak if peak else 0.0)
        inv = sum(holdings[s] * px[s] for s in symbols)
        exp_sum += inv / eq if eq else 0.0
        n += 1
    px = {s: closes[s][i1 - 1] for s in symbols}
    equity = cash + sum(holdings[s] * px[s] for s in symbols)
    return {
        "id": "BH-EQ-HOLD",
        "kind": "benchmark_causal",
        "note": "compra única 1/3 al inicio; sin rebalance diario",
        "net_vs_initial": round(equity - capital, 4),
        "equity_final": round(equity, 4),
        "fees_and_frictions": round(fees, 6),
        "max_drawdown": round(max_dd, 6),
        "avg_exposure": round(exp_sum / max(1, n), 6),
        "turnover_events": 3,
        "cash_days": 0,
    }


def make_vol_scaled_eq(closes: dict[str, list[float]], vol_lb: int = 20, target_vol: float = 0.40):
    """Escala exposición con vol pasada del EQ (causal). Exploratorio/pasivo."""

    def _w(i, closes_):
        if i < vol_lb + 1:
            return {s: 0.0 for s in closes_}
        # retorno diario EQ sintético
        rets = []
        for j in range(i - vol_lb + 1, i + 1):
            r = 0.0
            ok = True
            for s, series in closes_.items():
                if series[j - 1] <= 0:
                    ok = False
                    break
                r += (series[j] / series[j - 1] - 1.0) / len(closes_)
            if ok:
                rets.append(r)
        if len(rets) < 5:
            return {s: 0.0 for s in closes_}
        m = sum(rets) / len(rets)
        var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
        vol = (var ** 0.5) * (365 ** 0.5)
        scale = min(1.0, target_vol / vol) if vol > 1e-8 else 0.0
        w = scale / len(closes_)
        return {s: w for s in closes_}

    return _w


def make_simple_trend(lookback: int = 100) -> Callable:
    """Tendencia simple: long EQ si retorno lookback >0. Exploratorio."""

    def _w(i, closes):
        if i < lookback:
            return {s: 0.0 for s in closes}
        active = []
        for s, series in closes.items():
            if series[i - lookback] > 0 and series[i] / series[i - lookback] - 1.0 > 0:
                active.append(s)
        if not active:
            return {s: 0.0 for s in closes}
        w = 1.0 / len(active)
        return {s: (w if s in active else 0.0) for s in closes}

    return _w


def run_benchmark_suite(
    times: list[int],
    closes: dict[str, list[float]],
    *,
    i0: int,
    i1: int,
    d28_avg_exposure: float,
) -> dict[str, Any]:
    d28 = simulate_ledger(times, closes, make_tsmom(28), i0=i0, i1=i1)
    cash = {
        "id": "CASH",
        "kind": "benchmark_causal",
        "net_vs_initial": 0.0,
        "equity_final": 1000.0,
        "fees_and_frictions": 0.0,
        "max_drawdown": 0.0,
        "avg_exposure": 0.0,
        "turnover_events": 0,
        "cash_days": i1 - i0,
        "note": "efectivo 100%",
    }
    bh_eq_daily = simulate_ledger(times, closes, _w_bh_eq, i0=i0, i1=i1)
    bh_eq_daily["id"] = "Z-BH-EQ"
    bh_eq_daily["kind"] = "benchmark_causal"
    bh_eq_daily["note"] = "equiponderado rebalanceado diariamente (mismo motor Z)"

    bh_hold = simulate_true_bh_eq(times, closes, i0, i1)
    exp_match = simulate_ledger(
        times, closes, make_fixed_exposure_eq(d28_avg_exposure), i0=i0, i1=i1
    )
    exp_match["id"] = "EXP-MATCH-EQ"
    exp_match["kind"] = "control_descriptivo_ex_post"
    exp_match["note"] = (
        f"exposición fija {d28_avg_exposure:.4f} = media observada D28H5 (ex post); "
        "NO es estrategia causalmente ejecutable sin conocer el futuro"
    )

    vol_scaled = simulate_ledger(times, closes, make_vol_scaled_eq(closes), i0=i0, i1=i1)
    vol_scaled["id"] = "VOL-SCALE-EQ"
    vol_scaled["kind"] = "benchmark_causal_pasivo"
    vol_scaled["note"] = "escala exposición con vol pasada del EQ (target_vol=40% ann)"

    fixed55 = simulate_ledger(times, closes, make_fixed_exposure_eq(0.55), i0=i0, i1=i1)
    fixed55["id"] = "FIXED-55-EQ"
    fixed55["kind"] = "benchmark_causal"
    fixed55["note"] = "exposición fija 55% EQ + cash; costos realistas; prerregistrable"

    trend = simulate_ledger(times, closes, make_simple_trend(100), i0=i0, i1=i1)
    trend["id"] = "TREND-LB100"
    trend["kind"] = "exploratorio"
    trend["note"] = "tendencia lookback 100d; no ajuste retrospectivo de parámetros"

    btc = simulate_ledger(times, closes, _w_bh_btc, i0=i0, i1=i1)
    btc["id"] = "Z-BH-BTC"
    btc["kind"] = "benchmark_causal"

    def slim(r: dict) -> dict:
        keys = (
            "id",
            "kind",
            "note",
            "net_vs_initial",
            "equity_final",
            "fees_and_frictions",
            "max_drawdown",
            "avg_exposure",
            "turnover_events",
            "cash_days",
            "buys",
            "sells",
            "rebalances_real",
            "notional_traded",
            "cost_per_rebalance",
            "worst_week",
            "worst_month",
            "monthly_returns",
            "cost_by_symbol",
            "cost_split",
            "accounting",
        )
        return {k: r[k] for k in keys if k in r}

    return {
        "D28H5": {**slim(d28), "id": "Z-TSMOM-D28H5", "kind": "strategy_frozen"},
        "CASH": cash,
        "Z-BH-EQ": slim(bh_eq_daily),
        "BH-EQ-HOLD": bh_hold,
        "EXP-MATCH-EQ": slim(exp_match),
        "FIXED-55-EQ": slim(fixed55),
        "VOL-SCALE-EQ": slim(vol_scaled),
        "TREND-LB100": slim(trend),
        "Z-BH-BTC": slim(btc),
        "_full_d28": d28,
        "_full_exp_match": exp_match,
        "_full_bh_eq": bh_eq_daily,
    }
