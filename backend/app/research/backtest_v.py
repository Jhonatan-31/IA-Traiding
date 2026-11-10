"""Backtest Etapa V — V-TREND / V-BREAK / V-MEAN vs baselines. Sin look-ahead.

Decisiones en vela cerrada; fill en close*(1±slip); fee taker; walk-forward 70/30.
No escribe ledgers operativos.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..active.backtest_b import Book, _agg_5m, _fill_buy, _fill_sell, fetch_1m, simulate as simulate_ab
from ..demo.indicators import compute_bundle as compute_a
from ..demo.policy import BUY_MIN_FLAGS, BUY_SCORE_MIN, FEE_RATE as A_FEE, SLIP_RATE as A_SLIP
from .policies_v import FEE_RATE, MAX_EXPOSURE_USDT, MAX_POS_USDT, MAX_POSITIONS, SLIP_RATE
from .regimes import _ema, classify_regime


def _agg_n(c1: list[dict], n: int) -> list[dict]:
    out: list[dict] = []
    bucket: list[dict] = []
    for c in c1:
        bucket.append(c)
        if len(bucket) == n:
            out.append(
                {
                    "open_time": bucket[0]["open_time"],
                    "open": float(bucket[0]["open"]),
                    "high": max(float(x["high"]) for x in bucket),
                    "low": min(float(x["low"]) for x in bucket),
                    "close": float(bucket[-1]["close"]),
                    "volume": sum(float(x["volume"]) for x in bucket),
                    "is_closed": True,
                }
            )
            bucket = []
    return out


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))


@dataclass
class Aux:
    last_entry: dict[str, int] = field(default_factory=dict)
    regime_pnl: dict[str, list[float]] = field(default_factory=dict)


def _metrics(book: Book, closed_pnls: list[float], warm: int, i1: int, data: dict) -> dict[str, Any]:
    marks = {s: float(data[s][i1 - 1]["close"]) for s in data}
    equity = book.mark_equity(marks)
    wins = [x for x in closed_pnls if x > 0]
    losses = [x for x in closed_pnls if x < 0]
    gw, gl = sum(wins), abs(sum(losses))
    n = len(closed_pnls)
    pf = (gw / gl) if gl > 0 else None
    bh0 = sum(float(data[s][warm]["close"]) for s in data) / len(data)
    bh1 = sum(float(data[s][i1 - 1]["close"]) for s in data) / len(data)
    rets = []
    # crude equity path not stored — skip sharpe if insufficient
    return {
        "equity": round(equity, 4),
        "net_vs_initial": round(equity - 1000.0, 4),
        "gross_return_proxy": round(book.realized, 6),
        "net_return_proxy": round(equity - 1000.0, 4),
        "buys": book.buys,
        "sells": book.sells,
        "closed_rounds": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 6) if n else None,
        "profit_factor": round(pf, 6) if pf is not None else None,
        "expectancy": round(sum(closed_pnls) / n, 6) if n else None,
        "max_drawdown_proxy": round(1.0 - (equity / book.peak) if book.peak else 0.0, 6),
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "cash_benchmark_net": 0.0,
        "buy_hold_proxy_return": round(bh1 / bh0 - 1.0, 6) if bh0 else None,
        "open_positions": len(book.positions),
        "declare_profitable": False,
        "time_in_market_note": "Aprox. por nº de barras con posición (no persistido en este corte).",
    }


def simulate_v(
    data: dict[str, list[dict]],
    *,
    variant: str,
    i0: int,
    i1: int,
) -> dict[str, Any]:
    book = Book()
    aux = Aux()
    closed_pnls: list[float] = []
    warm = max(120, i0)
    fee, slip = FEE_RATE, SLIP_RATE

    for i in range(warm, i1):
        marks = {s: float(data[s][i]["close"]) for s in data}
        equity = book.mark_equity(marks)
        book.peak = max(book.peak, equity)
        pause = equity <= book.peak * 0.97
        invested = sum(p.cost for p in book.positions.values())

        # exits
        for sym in list(book.positions.keys()):
            c1 = data[sym][: i + 1]
            entry = book.positions[sym].entry
            mark = float(c1[-1]["close"])
            action, reason = "HOLD", "hold"
            if variant == "V_TREND":
                c60 = _agg_n(c1, 60)
                closes_h = [float(x["close"]) for x in c60[-40:]]
                e20, e50 = _ema(closes_h, 20), _ema(closes_h, 50)
                if mark <= entry * (1 - 0.012):
                    action, reason = "SELL", "sl"
                elif mark >= entry * (1 + 0.024):
                    action, reason = "SELL", "tp"
                elif e20 is not None and e50 is not None and e20 < e50:
                    action, reason = "SELL", "htf_invalidation"
            elif variant == "V_BREAK":
                c15 = _agg_n(c1, 15)
                if len(c15) >= 13:
                    window = c15[-13:-1]
                    lo = min(float(x["low"]) for x in window)
                    hi = max(float(x["high"]) for x in window)
                    rng = max(hi - lo, entry * 0.002)
                    sl = max(lo, entry * (1 - 0.02))
                    tp = entry + min(1.5 * rng, entry * 0.03)
                    if mark <= sl:
                        action, reason = "SELL", "sl_range"
                    elif mark >= tp:
                        action, reason = "SELL", "tp_range"
                else:
                    if mark <= entry * 0.98:
                        action, reason = "SELL", "sl"
            elif variant == "V_MEAN":
                if mark <= entry * (1 - 0.008):
                    action, reason = "SELL", "sl"
                elif mark >= entry * (1 + 0.012):
                    action, reason = "SELL", "tp"
            else:  # A-like fallback
                b = compute_a(c1[-120:], _agg_5m(c1)[-80:])
                if b:
                    if mark <= entry * 0.99:
                        action, reason = "SELL", "stop_loss_1pct"
                    elif mark >= entry * 1.02:
                        action, reason = "SELL", "take_profit_2pct"
                    elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                        action, reason = "SELL", "trend_break_1m"

            if action == "SELL":
                before = book.realized
                reg = classify_regime(c1[-120:])["regime"]
                _fill_sell(book, sym, mark, fee, slip)
                delta = book.realized - before
                closed_pnls.append(delta)
                aux.regime_pnl.setdefault(reg, []).append(delta)
            else:
                book.holds += 1

        # entries
        for sym in data:
            if sym in book.positions or pause:
                continue
            if len(book.positions) >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT - 1e-9:
                continue
            last = aux.last_entry.get(sym, -10_000)
            c1 = data[sym][: i + 1]
            reg = classify_regime(c1[-120:])
            allow = False
            reason = "no_signal"

            if variant == "V_TREND":
                if i - last < 60:
                    reason = "cooldown"
                else:
                    c60 = _agg_n(c1, 60)
                    c15 = _agg_n(c1, 15)
                    if len(c60) >= 50 and len(c15) >= 30:
                        ch = [float(x["close"]) for x in c60]
                        e20, e50 = _ema(ch[-40:], 20), _ema(ch[-60:], 50)
                        c15c = [float(x["close"]) for x in c15]
                        e21 = _ema(c15c[-30:], 21)
                        rsi = _rsi(c15c, 14)
                        vols = [float(x["volume"]) for x in c15]
                        vsma = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
                        close = c15c[-1]
                        near = e21 is not None and abs(close - e21) / close <= 0.0035
                        vol_ok = vsma is not None and vols[-1] >= vsma
                        allow = (
                            e20 is not None
                            and e50 is not None
                            and e20 > e50
                            and near
                            and rsi is not None
                            and 40 <= rsi <= 55
                            and vol_ok
                        )
                        reason = "v_trend_entry" if allow else "v_trend_filter"
            elif variant == "V_BREAK":
                if i - last < 90:
                    reason = "cooldown"
                else:
                    c15 = _agg_n(c1, 15)
                    if len(c15) >= 14:
                        window = c15[-14:-1]
                        hi = max(float(x["high"]) for x in window)
                        lo = min(float(x["low"]) for x in window)
                        lastc = c15[-1]
                        vols = [float(x["volume"]) for x in c15]
                        vsma = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
                        atr_ok = True
                        from .regimes import _atr_pct

                        atrp = _atr_pct(c1[-40:])
                        if atrp is not None and atrp < 1.2 * (FEE_RATE + SLIP_RATE):
                            atr_ok = False
                            reason = "cost_filter"
                        elif (
                            float(lastc["close"]) > hi
                            and vsma is not None
                            and float(lastc["volume"]) > 1.2 * vsma
                            and atr_ok
                        ):
                            allow = True
                            reason = "v_break_entry"
                        else:
                            reason = "no_break"
            elif variant == "V_MEAN":
                if reg["trend"] != "sideways":
                    reason = "regime_block"
                else:
                    closes = [float(x["close"]) for x in c1]
                    rsi = _rsi(closes, 14)
                    e21 = _ema(closes[-40:], 21)
                    close = closes[-1]
                    if rsi is not None and e21 is not None and rsi < 30 and close < e21 * 0.995:
                        allow = True
                        reason = "v_mean_entry"
                    else:
                        reason = "no_mean_signal"
            elif variant == "A_BASELINE":
                b = compute_a(c1[-120:], _agg_5m(c1)[-80:])
                if b and int(b["flags_true"]) >= BUY_MIN_FLAGS and float(b["signal_score"]) >= BUY_SCORE_MIN:
                    allow = True
                    reason = "demo_buy"
                    fee, slip = A_FEE, A_SLIP

            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if allow:
                book.signals_buy += 1
                if _fill_buy(book, sym, float(c1[-1]["close"]), fee, slip, MAX_POS_USDT):
                    aux.last_entry[sym] = i
                    invested = sum(p.cost for p in book.positions.values())

    m = _metrics(book, closed_pnls, warm, i1, data)
    m["variant"] = variant
    m["regime_pnl"] = {
        k: {"n": len(v), "sum": round(sum(v), 6), "avg": round(sum(v) / len(v), 6) if v else None}
        for k, v in aux.regime_pnl.items()
    }
    m["bars"] = i1 - warm
    return m


async def run_etapa_v(symbols: list[str], limit: int = 1000) -> dict[str, Any]:
    data: dict[str, list[dict]] = {}
    for s in symbols:
        data[s] = await fetch_1m(s, limit=limit)
    n = min(len(v) for v in data.values())
    data = {s: v[-n:] for s, v in data.items()}
    split = int(n * 0.70)
    variants = ["A_BASELINE", "V_TREND", "V_BREAK", "V_MEAN"]
    # Also run B via existing simulate on same window slices roughly
    is_res = {v: simulate_v(data, variant=v, i0=120, i1=split) for v in variants}
    oos_res = {v: simulate_v(data, variant=v, i0=split, i1=n) for v in variants}

    # B baseline full-window compare (same data) — descriptive only
    b_full = simulate_ab(data, mode="B")

    approval = []
    for vid, r in oos_res.items():
        if vid == "A_BASELINE":
            continue
        ok = True
        reasons = []
        if (r.get("closed_rounds") or 0) < 5:
            ok = False
            reasons.append("pocas_operaciones_oos")
        if (r.get("net_vs_initial") or 0) <= 0:
            ok = False
            reasons.append("neto_oos_no_positivo")
        if r.get("profit_factor") is not None and r["profit_factor"] < 1.0:
            ok = False
            reasons.append("profit_factor_oos_<1")
        approval.append(
            {
                "id": vid,
                "promote_to_paper_trial": False,  # never auto
                "passes_research_filters": ok and False,  # require positive OOS AND manual auth
                "filter_notes": reasons or ["filtros_basicos_ok_pero_sin_autorizacion_prospectiva"],
                "status": "rejected" if not ok else "research_only",
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "symbols": symbols,
        "bars_per_symbol": n,
        "data_span_note": (
            f"Ventana ~{n} barras 1m (~{n/60:.1f} h). Meta 12–24m requiere ingesta histórica "
            "persistida; este corte usa API pública limitada (~1000 velas)."
        ),
        "walk_forward": {"is_end": split, "oos_start": split, "oos_end": n},
        "in_sample": is_res,
        "out_of_sample": oos_res,
        "b_baseline_full_window": {
            "net_vs_initial": b_full.get("net_vs_initial"),
            "buys": b_full.get("buys"),
            "fees": b_full.get("fees"),
            "note": "Misma ventana corta; no equivalente a periodo operativo de B STOPPED.",
        },
        "approval_gate": approval,
        "claim": {
            "declare_winner": False,
            "declare_profitable": False,
            "reason": "Ninguna variante se declara rentable ni se activa sin autorización explícita.",
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(json.dumps(asyncio.run(run_etapa_v(symbols, args.limit)), indent=2))


if __name__ == "__main__":
    main()
