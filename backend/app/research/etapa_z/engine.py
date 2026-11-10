"""Motor de evaluación económica Etapa Z (spot long-only, costos explícitos)."""
from __future__ import annotations

import math
from typing import Any, Callable

from ..history.aggregate import aggregate_bars
from ..history.store import load_range
from . import COST_RT, FEE_RATE, INITIAL_CAPITAL, SLIP_RATE, SPREAD_BPS
from .hypotheses import HYPOTHESES


def load_panel(symbols: list[str], tf: str) -> dict[str, list[dict]]:
    """Carga TF preagregado desde Parquet; si falta, agrega desde 1m."""
    panel = {s: load_range(s, tf) for s in symbols}
    if all(len(v) >= 50 for v in panel.values()):
        n = min(len(v) for v in panel.values())
        return {s: v[-n:] for s, v in panel.items()}
    raw = {s: load_range(s, "1m") for s in symbols}
    n = min(len(v) for v in raw.values())
    raw = {s: v[-n:] for s, v in raw.items()}
    return {s: aggregate_bars(rows, tf) for s, rows in raw.items()}


def _align(panel: dict[str, list[dict]]) -> tuple[list[int], dict[str, list[float]]]:
    times = sorted(set.intersection(*[{int(b["open_time"]) for b in rows} for rows in panel.values()]))
    closes: dict[str, list[float]] = {s: [] for s in panel}
    idx = {s: {int(b["open_time"]): float(b["close"]) for b in rows} for s, rows in panel.items()}
    for t in times:
        for s in panel:
            closes[s].append(idx[s][t])
    return times, closes


def _ret(closes: list[float], i: int, lb: int) -> float | None:
    if i < lb or closes[i - lb] <= 0:
        return None
    return closes[i] / closes[i - lb] - 1.0


def _vol(closes: list[float], i: int, lb: int) -> float | None:
    if i < lb + 1:
        return None
    rets = []
    for j in range(i - lb + 1, i + 1):
        if closes[j - 1] <= 0:
            return None
        rets.append(closes[j] / closes[j - 1] - 1.0)
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    # anualizar asumiendo 365 días si tf diario; para 4h ≈ 6 barras/día → 2190
    return math.sqrt(var)


def _trade_cost(notional: float) -> float:
    """Costo one-way: fee + slip + half-spread proxy."""
    return abs(notional) * (FEE_RATE + SLIP_RATE + SPREAD_BPS / 20_000.0)


def simulate_weights(
    times: list[int],
    closes: dict[str, list[float]],
    weights_fn,
    *,
    i0: int,
    i1: int,
    bars_per_year: float = 365.0,
) -> dict[str, Any]:
    """Simula cartera long-only con pesos objetivo en [0,1] sum≤1 (resto cash).

    Ejecución: tras señal en i, rebalance al close[i] con costos sobre turnover.
    """
    symbols = list(closes.keys())
    cash = INITIAL_CAPITAL
    holdings = {s: 0.0 for s in symbols}  # qty
    fees = 0.0
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    equity_curve: list[float] = []
    turns = 0
    exposure_sum = 0.0

    for i in range(i0, i1):
        px = {s: closes[s][i] for s in symbols}
        eq = cash + sum(holdings[s] * px[s] for s in symbols)
        peak = max(peak, eq)
        max_dd = max(max_dd, 1.0 - eq / peak if peak else 0.0)
        equity_curve.append(eq)

        w_tgt = weights_fn(i, closes)
        # normalizar / clip
        w_tgt = {s: max(0.0, float(w_tgt.get(s, 0.0))) for s in symbols}
        ssum = sum(w_tgt.values())
        if ssum > 1.0:
            w_tgt = {s: w_tgt[s] / ssum for s in symbols}
        invested = sum(holdings[s] * px[s] for s in symbols)
        exposure_sum += invested / eq if eq else 0.0

        # target notional
        for s in symbols:
            tgt_val = eq * w_tgt[s]
            cur_val = holdings[s] * px[s]
            delta = tgt_val - cur_val
            if abs(delta) < 1.0:  # umbral mínimo USDT
                continue
            cost = _trade_cost(delta)
            if delta > 0:
                # comprar
                spend = delta + cost
                if spend > cash:
                    delta = max(0.0, cash - cost)
                    spend = delta + cost
                    if delta < 1.0:
                        continue
                    cost = _trade_cost(delta)
                    spend = delta + cost
                cash -= spend
                holdings[s] += delta / px[s]
                fees += cost
                turns += 1
            else:
                # vender
                sell_val = min(-delta, holdings[s] * px[s])
                qty = sell_val / px[s]
                proceeds = sell_val - cost
                cash += max(0.0, proceeds)
                holdings[s] -= qty
                fees += cost
                turns += 1

    # mark final
    px = {s: closes[s][i1 - 1] for s in symbols}
    equity = cash + sum(holdings[s] * px[s] for s in symbols)
    n_bars = max(1, i1 - i0)
    rets = []
    for j in range(1, len(equity_curve)):
        if equity_curve[j - 1] > 0:
            rets.append(equity_curve[j] / equity_curve[j - 1] - 1.0)
    mu = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1)) if len(rets) > 1 else 0.0
    sharpe = (mu / sd) * math.sqrt(bars_per_year) if sd > 1e-12 else None
    return {
        "net_vs_initial": round(equity - INITIAL_CAPITAL, 4),
        "equity": round(equity, 4),
        "max_drawdown": round(max_dd, 6),
        "fees_and_frictions": round(fees, 6),
        "turnover_events": turns,
        "avg_exposure": round(exposure_sum / n_bars, 6),
        "n_bars": n_bars,
        "sharpe_proxy": round(sharpe, 4) if sharpe is not None else None,
        "cost_rt_frac_assumed": COST_RT,
    }


def _w_bh_btc(i, closes):
    return {"BTCUSDT": 1.0, "ETHUSDT": 0.0, "SOLUSDT": 0.0}


def _w_bh_eq(i, closes):
    return {s: 1.0 / 3.0 for s in closes}


def make_tsmom(lookback: int, vol_target: float | None = None, vol_lb: int = 20):
    def _w(i, closes):
        out = {s: 0.0 for s in closes}
        active = []
        for s, series in closes.items():
            r = _ret(series, i, lookback)
            if r is not None and r > 0:
                active.append(s)
        if not active:
            return out
        base = 1.0 / len(active)
        for s in active:
            if vol_target is None:
                out[s] = base
            else:
                # vol diaria → anual
                v = _vol(closes[s], i, vol_lb)
                if v is None or v <= 1e-8:
                    out[s] = 0.0
                else:
                    ann = v * math.sqrt(365.0)
                    scale = min(1.0, vol_target / ann)
                    out[s] = base * scale
        return out

    return _w


def make_rs_top1(lookback: int, every: int):
    state: dict[str, Any] = {"w": None, "last": -10**9}

    def _w(i, closes):
        if state["w"] is not None and (i - int(state["last"])) < every:
            return dict(state["w"])
        out = {s: 0.0 for s in closes}
        best_s, best_r = None, 0.0
        for s, series in closes.items():
            r = _ret(series, i, lookback)
            if r is not None and r > best_r:
                best_r, best_s = r, s
        if best_s is not None and best_r > 0:
            out[best_s] = 1.0
        state["w"] = dict(out)
        state["last"] = i
        return out

    return _w


def make_4h_mom(lookback: int):
    def _w(i, closes):
        out = {s: 0.0 for s in closes}
        active = []
        for s, series in closes.items():
            r = _ret(series, i, lookback)
            if r is not None and r > 0:
                active.append(s)
        if not active:
            return out
        w = 1.0 / len(active)
        for s in active:
            out[s] = w
        return out

    return _w


WEIGHT_BUILDERS = {
    "Z-BH-BTC": lambda: _w_bh_btc,
    "Z-BH-EQ": lambda: _w_bh_eq,
    "Z-TSMOM-D28H5": lambda: make_tsmom(28),
    "Z-TSMOM-VOL": lambda: make_tsmom(28, vol_target=0.10, vol_lb=20),
    "Z-RS-TOP1": lambda: make_rs_top1(30, 7),
    "Z-4H-MOM12": lambda: make_4h_mom(12),
}


def evaluate_hypothesis(
    hid: str,
    *,
    i0: int,
    i1: int,
    panel_cache: dict[str, tuple[list[int], dict[str, list[float]]]] | None = None,
) -> dict[str, Any]:
    meta = HYPOTHESES[hid]
    tf = meta["tf"]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    if panel_cache and tf in panel_cache:
        times, closes = panel_cache[tf]
    else:
        panel = load_panel(symbols, tf)
        times, closes = _align(panel)
        if panel_cache is not None:
            panel_cache[tf] = (times, closes)
    warm = 40
    a0 = max(warm, i0)
    a1 = min(i1, len(times))
    if a1 - a0 < 30:
        return {"id": hid, "ok": False, "reason": "insufficient_bars"}
    bpy = 365.0 if tf == "1d" else 365.0 * 6.0
    res = simulate_weights(
        times, closes, WEIGHT_BUILDERS[hid](), i0=a0, i1=a1, bars_per_year=bpy
    )
    stress_net = res["net_vs_initial"] - 0.5 * res["fees_and_frictions"]
    return {
        "id": hid,
        "ok": True,
        "title": meta["title"],
        "kind": meta["kind"],
        "tf": tf,
        "period_bars": a1 - a0,
        "n_times_available": len(times),
        **res,
        "cost_stress_net": round(stress_net, 4),
        "meta": {k: meta[k] for k in ("economic", "reject_if", "advance_if", "warning") if k in meta},
    }
