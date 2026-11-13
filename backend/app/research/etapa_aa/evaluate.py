"""AA4 — evaluación one-pass de D28H5 congelada + benchmarks."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ..etapa_z import INITIAL_CAPITAL
from ..etapa_z.engine import (
    WEIGHT_BUILDERS,
    _align,
    load_panel,
    simulate_weights,
)
from . import EVAL_END_MS, EVAL_START_MS, SYMBOLS, TARGET_ID


def _idx_range(times: list[int], start_ms: int, end_ms: int) -> tuple[int, int]:
    i0 = next((i for i, t in enumerate(times) if t >= start_ms), None)
    i1 = next((i for i, t in enumerate(times) if t > end_ms), len(times))
    if i0 is None:
        return 0, 0
    return i0, i1


def _daily_equity_curve(
    times: list[int],
    closes: dict[str, list[float]],
    weights_fn,
    *,
    i0: int,
    i1: int,
) -> dict[str, Any]:
    """Misma lógica que simulate_weights pero guarda equity diaria y pesos."""
    from ..etapa_z import FEE_RATE, SLIP_RATE, SPREAD_BPS

    def trade_cost(notional: float) -> float:
        return abs(notional) * (FEE_RATE + SLIP_RATE + SPREAD_BPS / 20_000.0)

    symbols = list(closes.keys())
    cash = INITIAL_CAPITAL
    holdings = {s: 0.0 for s in symbols}
    fees = 0.0
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    curve: list[dict[str, Any]] = []
    turns = 0
    exposure_sum = 0.0
    cash_days = 0
    monthly: dict[str, list[float]] = {}
    asset_pnl_proxy = {s: 0.0 for s in symbols}

    for i in range(i0, i1):
        px = {s: closes[s][i] for s in symbols}
        eq = cash + sum(holdings[s] * px[s] for s in symbols)
        peak = max(peak, eq)
        dd = 1.0 - eq / peak if peak else 0.0
        max_dd = max(max_dd, dd)
        invested = sum(holdings[s] * px[s] for s in symbols)
        exposure_sum += invested / eq if eq else 0.0
        if invested / eq < 0.05 if eq else True:
            cash_days += 1
        curve.append(
            {
                "t": times[i],
                "iso": datetime.fromtimestamp(times[i] / 1000, tz=timezone.utc).date().isoformat(),
                "equity": round(eq, 6),
                "exposure": round(invested / eq, 6) if eq else 0.0,
            }
        )
        ym = curve[-1]["iso"][:7]
        monthly.setdefault(ym, []).append(eq)

        w_tgt = weights_fn(i, closes)
        w_tgt = {s: max(0.0, float(w_tgt.get(s, 0.0))) for s in symbols}
        ssum = sum(w_tgt.values())
        if ssum > 1.0:
            w_tgt = {s: w_tgt[s] / ssum for s in symbols}

        for s in symbols:
            tgt_val = eq * w_tgt[s]
            cur_val = holdings[s] * px[s]
            delta = tgt_val - cur_val
            if abs(delta) < 1.0:
                continue
            cost = trade_cost(delta)
            if delta > 0:
                spend = delta + cost
                if spend > cash:
                    delta = max(0.0, cash - cost)
                    if delta < 1.0:
                        continue
                    cost = trade_cost(delta)
                    spend = delta + cost
                cash -= spend
                holdings[s] += delta / px[s]
                fees += cost
                turns += 1
            else:
                sell_val = min(-delta, holdings[s] * px[s])
                qty = sell_val / px[s]
                proceeds = sell_val - cost
                cash += max(0.0, proceeds)
                holdings[s] -= qty
                fees += cost
                turns += 1
                asset_pnl_proxy[s] += proceeds - (qty * px[s])  # rough

    px = {s: closes[s][i1 - 1] for s in symbols}
    equity = cash + sum(holdings[s] * px[s] for s in symbols)
    n_bars = max(1, i1 - i0)
    rets = []
    for j in range(1, len(curve)):
        a, b = curve[j - 1]["equity"], curve[j]["equity"]
        if a > 0:
            rets.append(b / a - 1.0)
    mu = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1)) if len(rets) > 1 else 0.0
    downside = [x for x in rets if x < 0]
    dsd = math.sqrt(sum(x * x for x in downside) / max(1, len(downside))) if downside else 0.0
    sharpe = (mu / sd) * math.sqrt(365.0) if sd > 1e-12 else None
    sortino = (mu / dsd) * math.sqrt(365.0) if dsd > 1e-12 else None
    month_rets = {}
    for ym, eqs in monthly.items():
        if len(eqs) >= 2:
            month_rets[ym] = round(eqs[-1] / eqs[0] - 1.0, 6)

    worst_day = min(rets) if rets else None
    # worst week approx 7-day rolling
    worst_week = None
    for j in range(7, len(curve)):
        a, b = curve[j - 7]["equity"], curve[j]["equity"]
        if a > 0:
            w = b / a - 1.0
            worst_week = w if worst_week is None else min(worst_week, w)

    return {
        "net_vs_initial": round(equity - INITIAL_CAPITAL, 4),
        "equity_final": round(equity, 4),
        "equity_initial": INITIAL_CAPITAL,
        "max_drawdown": round(max_dd, 6),
        "fees_and_frictions": round(fees, 6),
        "turnover_events": turns,
        "avg_exposure": round(exposure_sum / n_bars, 6),
        "cash_days": cash_days,
        "n_bars": n_bars,
        "sharpe_proxy": round(sharpe, 4) if sharpe is not None else None,
        "sortino_proxy": round(sortino, 4) if sortino is not None else None,
        "vol_daily": round(sd, 6),
        "worst_day": round(worst_day, 6) if worst_day is not None else None,
        "worst_week": round(worst_week, 6) if worst_week is not None else None,
        "cost_stress_net": round(equity - INITIAL_CAPITAL - 0.5 * fees, 4),
        "monthly_returns": month_rets,
        "daily_returns": rets,
        "equity_curve": curve,
        "final_weights_proxy": {s: round(holdings[s] * px[s] / equity, 4) if equity else 0 for s in symbols},
    }


def evaluate_aa_period() -> dict[str, Any]:
    panel = load_panel(SYMBOLS, "1d")
    times, closes = _align(panel)
    # warm-up: need index >= 28 before eval start for signal; i0 is first bar of eval period
    i0, i1 = _idx_range(times, EVAL_START_MS, EVAL_END_MS)
    if i1 - i0 < 30:
        return {"ok": False, "reason": "insufficient_eval_bars", "i0": i0, "i1": i1, "n_times": len(times)}
    if i0 < 28:
        return {
            "ok": False,
            "reason": "insufficient_warmup_before_eval",
            "i0": i0,
            "need": 28,
            "hint": "requiere historial 1d previo a 2025-11-01",
        }

    strategies = [TARGET_ID, "Z-BH-EQ", "Z-BH-BTC"]
    results: dict[str, Any] = {}
    for hid in strategies:
        pack = _daily_equity_curve(times, closes, WEIGHT_BUILDERS[hid](), i0=i0, i1=i1)
        chk = simulate_weights(times, closes, WEIGHT_BUILDERS[hid](), i0=i0, i1=i1)
        pack["reconcile_net_vs_simulate_weights"] = round(
            pack["net_vs_initial"] - chk["net_vs_initial"], 6
        )
        pack["id"] = hid
        results[hid] = pack

    d = results[TARGET_ID]
    b = results["Z-BH-EQ"]
    excess = round(d["net_vs_initial"] - b["net_vs_initial"], 4)
    months = d.get("monthly_returns") or {}
    best_month = max(months.items(), key=lambda x: x[1]) if months else None

    slim = {}
    for k, v in results.items():
        slim[k] = {kk: vv for kk, vv in v.items() if kk not in {"daily_returns", "equity_curve"}}
        slim[k]["equity_curve_len"] = len(v.get("equity_curve") or [])
        slim[k]["daily_returns_n"] = len(v.get("daily_returns") or [])

    return {
        "ok": True,
        "period": {
            "start_iso": datetime.fromtimestamp(times[i0] / 1000, tz=timezone.utc).isoformat(),
            "end_iso": datetime.fromtimestamp(times[i1 - 1] / 1000, tz=timezone.utc).isoformat(),
            "n_bars": i1 - i0,
            "i0": i0,
            "i1": i1,
        },
        "results": slim,
        "curves": {
            TARGET_ID: results[TARGET_ID]["equity_curve"],
            "Z-BH-EQ": results["Z-BH-EQ"]["equity_curve"],
        },
        "daily_returns": {
            TARGET_ID: results[TARGET_ID]["daily_returns"],
            "Z-BH-EQ": results["Z-BH-EQ"]["daily_returns"],
        },
        "primary": {
            "d28h5_net": d["net_vs_initial"],
            "bh_eq_net": b["net_vs_initial"],
            "excess_net": excess,
            "d28h5_dd": d["max_drawdown"],
            "bh_eq_dd": b["max_drawdown"],
            "d28h5_exposure": d["avg_exposure"],
            "bh_eq_exposure": b["avg_exposure"],
            "d28h5_costs": d["fees_and_frictions"],
            "bh_eq_costs": b["fees_and_frictions"],
            "best_month_d28h5": best_month,
        },
        "consumed": True,
        "consumed_note": "Cualquier análisis posterior sobre este período es exploratorio, no nueva prueba independiente",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
