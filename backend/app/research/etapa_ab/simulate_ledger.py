"""Simulación con ledger de trades para atribución y auditoría de costos."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

from ..etapa_z import FEE_RATE, INITIAL_CAPITAL, SLIP_RATE, SPREAD_BPS

COST_FRAC = FEE_RATE + SLIP_RATE + SPREAD_BPS / 20_000.0
FEE_SHARE = FEE_RATE / COST_FRAC if COST_FRAC else 0.0
SLIP_SHARE = SLIP_RATE / COST_FRAC if COST_FRAC else 0.0
SPREAD_SHARE = (SPREAD_BPS / 20_000.0) / COST_FRAC if COST_FRAC else 0.0


def trade_cost(notional: float) -> float:
    return abs(notional) * COST_FRAC


def simulate_ledger(
    times: list[int],
    closes: dict[str, list[float]],
    weights_fn: Callable,
    *,
    i0: int,
    i1: int,
    min_delta: float = 1.0,
) -> dict[str, Any]:
    symbols = list(closes.keys())
    cash = float(INITIAL_CAPITAL)
    holdings = {s: 0.0 for s in symbols}
    fees = 0.0
    fee_fee = fee_slip = fee_spread = 0.0
    peak = float(INITIAL_CAPITAL)
    max_dd = 0.0
    dd_start = None
    max_dd_dur = 0
    cur_dd_len = 0
    trades: list[dict[str, Any]] = []
    days: list[dict[str, Any]] = []
    turns = 0
    buys = sells = 0
    notional_traded = 0.0
    exposure_sum = 0.0
    cash_days = 0
    signal_changes = 0
    prev_sig: tuple | None = None
    rebalances_real = 0
    cost_by_sym = {s: 0.0 for s in symbols}
    cost_by_month: dict[str, float] = {}
    monthly_eq: dict[str, list[float]] = {}

    for i in range(i0, i1):
        px = {s: closes[s][i] for s in symbols}
        eq_pre = cash + sum(holdings[s] * px[s] for s in symbols)
        peak = max(peak, eq_pre)
        dd = 1.0 - eq_pre / peak if peak else 0.0
        if dd > max_dd + 1e-15:
            max_dd = dd
            dd_start = i
            cur_dd_len = 0
        if dd > 1e-9:
            cur_dd_len += 1
            max_dd_dur = max(max_dd_dur, cur_dd_len)
        else:
            cur_dd_len = 0

        invested = sum(holdings[s] * px[s] for s in symbols)
        exp = invested / eq_pre if eq_pre else 0.0
        exposure_sum += exp
        if exp < 0.05:
            cash_days += 1

        w_tgt = weights_fn(i, closes)
        w_tgt = {s: max(0.0, float(w_tgt.get(s, 0.0))) for s in symbols}
        ssum = sum(w_tgt.values())
        if ssum > 1.0:
            w_tgt = {s: w_tgt[s] / ssum for s in symbols}

        sig = tuple(round(w_tgt[s], 6) for s in symbols)
        if prev_sig is not None and sig != prev_sig:
            signal_changes += 1
        prev_sig = sig

        day_cost = 0.0
        day_trades = 0
        for s in symbols:
            tgt_val = eq_pre * w_tgt[s]
            cur_val = holdings[s] * px[s]
            delta = tgt_val - cur_val
            if abs(delta) < min_delta:
                continue
            cost = trade_cost(delta)
            side = "BUY" if delta > 0 else "SELL"
            if delta > 0:
                spend = delta + cost
                if spend > cash:
                    delta = max(0.0, cash - cost)
                    if delta < min_delta:
                        continue
                    cost = trade_cost(delta)
                    spend = delta + cost
                cash -= spend
                holdings[s] += delta / px[s]
                buys += 1
                notional = delta
            else:
                sell_val = min(-delta, holdings[s] * px[s])
                qty = sell_val / px[s]
                proceeds = sell_val - cost
                cash += max(0.0, proceeds)
                holdings[s] -= qty
                sells += 1
                notional = sell_val
            fees += cost
            fee_fee += cost * FEE_SHARE
            fee_slip += cost * SLIP_SHARE
            fee_spread += cost * SPREAD_SHARE
            cost_by_sym[s] += cost
            day_cost += cost
            turns += 1
            day_trades += 1
            notional_traded += abs(notional)
            iso = datetime.fromtimestamp(times[i] / 1000, tz=timezone.utc).date().isoformat()
            ym = iso[:7]
            cost_by_month[ym] = cost_by_month.get(ym, 0.0) + cost
            trades.append(
                {
                    "t": times[i],
                    "iso": iso,
                    "symbol": s,
                    "side": side,
                    "notional": round(abs(notional), 6),
                    "cost": round(cost, 6),
                    "price": px[s],
                    "w_tgt": round(w_tgt[s], 6),
                }
            )
        if day_trades > 0:
            rebalances_real += 1

        eq_post = cash + sum(holdings[s] * px[s] for s in symbols)
        iso = datetime.fromtimestamp(times[i] / 1000, tz=timezone.utc).date().isoformat()
        monthly_eq.setdefault(iso[:7], []).append(eq_post)
        w_act = {s: (holdings[s] * px[s] / eq_post) if eq_post else 0.0 for s in symbols}
        days.append(
            {
                "i": i,
                "t": times[i],
                "iso": iso,
                "equity": eq_post,
                "exposure": sum(w_act.values()),
                "cash_w": cash / eq_post if eq_post else 1.0,
                "w_tgt": dict(w_tgt),
                "w_act": w_act,
                "day_cost": day_cost,
                "px": dict(px),
            }
        )

    px = {s: closes[s][i1 - 1] for s in symbols}
    equity = cash + sum(holdings[s] * px[s] for s in symbols)
    n_bars = max(1, i1 - i0)
    rets = []
    for j in range(1, len(days)):
        a, b = days[j - 1]["equity"], days[j]["equity"]
        if a > 0:
            rets.append(b / a - 1.0)
    month_rets = {}
    for ym, eqs in monthly_eq.items():
        if len(eqs) >= 2:
            month_rets[ym] = round(eqs[-1] / eqs[0] - 1.0, 6)

    worst_week = None
    for j in range(7, len(days)):
        a, b = days[j - 7]["equity"], days[j]["equity"]
        if a > 0:
            w = b / a - 1.0
            worst_week = w if worst_week is None else min(worst_week, w)

    return {
        "equity_initial": INITIAL_CAPITAL,
        "equity_final": round(equity, 6),
        "net_vs_initial": round(equity - INITIAL_CAPITAL, 4),
        "gross_approx": round(equity - INITIAL_CAPITAL + fees, 4),
        "fees_and_frictions": round(fees, 6),
        "cost_split": {
            "fee": round(fee_fee, 6),
            "slip": round(fee_slip, 6),
            "spread": round(fee_spread, 6),
            "formula": "cost = |notional| * (fee+slip+spread/20000); split proporcional",
        },
        "max_drawdown": round(max_dd, 6),
        "max_dd_duration_bars": max_dd_dur,
        "avg_exposure": round(exposure_sum / n_bars, 6),
        "cash_days": cash_days,
        "n_bars": n_bars,
        "n_evaluations": n_bars,
        "signal_changes": signal_changes,
        "rebalances_real": rebalances_real,
        "turnover_events": turns,
        "buys": buys,
        "sells": sells,
        "notional_traded": round(notional_traded, 4),
        "turnover_vs_capital": round(notional_traded / INITIAL_CAPITAL, 4),
        "cost_per_rebalance": round(fees / rebalances_real, 6) if rebalances_real else None,
        "cost_per_unit_capital": round(fees / INITIAL_CAPITAL, 6),
        "cost_by_symbol": {k: round(v, 6) for k, v in cost_by_sym.items()},
        "cost_by_month": {k: round(v, 6) for k, v in sorted(cost_by_month.items())},
        "monthly_returns": month_rets,
        "worst_week": round(worst_week, 6) if worst_week is not None else None,
        "worst_month": min(month_rets.items(), key=lambda x: x[1]) if month_rets else None,
        "best_month": max(month_rets.items(), key=lambda x: x[1]) if month_rets else None,
        "vol_daily": round(
            math.sqrt(sum((x - (sum(rets) / len(rets))) ** 2 for x in rets) / max(1, len(rets) - 1))
            if len(rets) > 1
            else 0.0,
            6,
        ),
        "daily_returns": rets,
        "days": days,
        "trades": trades,
        "final_weights": {
            s: round(holdings[s] * px[s] / equity, 6) if equity else 0.0 for s in symbols
        },
        "accounting": {
            "initial": INITIAL_CAPITAL,
            "final": round(equity, 6),
            "net": round(equity - INITIAL_CAPITAL, 6),
            "costs": round(fees, 6),
            "gross_net_plus_costs": round(equity - INITIAL_CAPITAL + fees, 6),
            "identity": "final = initial + gross_approx - costs (approx; mark-to-market path)",
        },
    }
