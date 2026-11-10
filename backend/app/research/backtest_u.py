"""Backtests Etapa U — variantes aisladas vs baseline A. Sin escribir a DB operativa.

Costos: fee 10 bps + slip 5 bps. Fill en close de vela cerrada (sin look-ahead).
Walk-forward: 70% IS / 30% OOS por índice de barras.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..active.backtest_b import Book, _agg_5m, _fill_buy, _fill_sell, fetch_1m
from ..demo.indicators import compute_bundle as compute_a
from ..demo.policy import (
    BUY_MIN_FLAGS,
    BUY_SCORE_MIN,
    FEE_RATE,
    MAX_EXPOSURE_USDT,
    MAX_POS_USDT,
    MAX_POSITIONS,
    SLIP_RATE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)
from .hypotheses_u import HYPOTHESES

FEE = FEE_RATE
SLIP = SLIP_RATE


def _ema(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _agg_15m(c1: list[dict]) -> list[dict]:
    out: list[dict] = []
    bucket: list[dict] = []
    for c in c1:
        bucket.append(c)
        if len(bucket) == 15:
            out.append(
                {
                    "open_time": bucket[0]["open_time"],
                    "close": bucket[-1]["close"],
                    "high": max(float(x["high"]) for x in bucket),
                    "low": min(float(x["low"]) for x in bucket),
                    "volume": sum(float(x["volume"]) for x in bucket),
                    "is_closed": True,
                }
            )
            bucket = []
    return out


def _atr_pct(c1: list[dict], n: int = 14) -> float | None:
    if len(c1) < n + 1:
        return None
    trs = []
    for i in range(1, len(c1)):
        h = float(c1[i]["high"])
        l = float(c1[i]["low"])
        pc = float(c1[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    atr = sum(trs[-n:]) / n
    close = float(c1[-1]["close"])
    return atr / close if close else None


@dataclass
class State:
    last_entry_i: dict[str, int] = field(default_factory=dict)
    entries_hour: list[int] = field(default_factory=list)  # bar indices of entries


def simulate_variant(
    symbols_data: dict[str, list[dict]],
    *,
    variant: str,
    i0: int,
    i1: int,
) -> dict[str, Any]:
    book = Book()
    st = State()
    warm = max(80, i0)
    wins = losses = 0
    closed_pnls: list[float] = []

    for i in range(warm, i1):
        marks = {s: float(symbols_data[s][i]["close"]) for s in symbols_data}
        equity = book.mark_equity(marks)
        book.peak = max(book.peak, equity)
        pause = equity <= book.peak * 0.97
        invested = sum(p.cost for p in book.positions.values())

        # --- exits ---
        for sym in list(book.positions.keys()):
            c1 = symbols_data[sym][: i + 1]
            c5 = _agg_5m(c1)
            b = compute_a(c1[-120:], c5[-80:])
            if not b:
                continue
            entry = book.positions[sym].entry
            mark = float(b["close"])
            action, reason = "HOLD", "hold_position"
            if variant == "U3_ATR_EXITS":
                atrp = _atr_pct(c1[-40:]) or 0.01
                sl = min(0.02, max(0.006, 1.5 * atrp))
                tp = min(0.04, max(0.01, 2.5 * atrp))
                if mark <= entry * (1 - sl):
                    action, reason = "SELL", "atr_stop"
                elif mark >= entry * (1 + tp):
                    action, reason = "SELL", "atr_take"
                elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 40:
                    action, reason = "SELL", "trend_break_1m"
            else:
                if mark <= entry * (1 - STOP_LOSS_PCT):
                    action, reason = "SELL", "stop_loss_1pct"
                elif mark >= entry * (1 + TAKE_PROFIT_PCT):
                    action, reason = "SELL", "take_profit_2pct"
                elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                    action, reason = "SELL", "trend_break_1m"
            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if action == "SELL":
                before = book.realized
                _fill_sell(book, sym, mark, FEE, SLIP)
                delta = book.realized - before
                closed_pnls.append(delta)
                if delta > 0:
                    wins += 1
                elif delta < 0:
                    losses += 1
            else:
                book.holds += 1

        # --- entries ---
        for sym in symbols_data:
            if sym in book.positions:
                continue
            if pause or len(book.positions) >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT - 1e-9:
                continue
            c1 = symbols_data[sym][: i + 1]
            c5 = _agg_5m(c1)
            b = compute_a(c1[-120:], c5[-80:])
            if not b:
                continue

            n_true = int(b["flags_true"])
            score = float(b["signal_score"])
            base_ok = n_true >= BUY_MIN_FLAGS and score >= BUY_SCORE_MIN

            allow = False
            reason = f"flags_{n_true}_of_5_insufficient"

            if variant == "A_BASELINE":
                allow = base_ok
                reason = f"policy_{n_true}_of_5_flags" if allow else reason
            elif variant == "U1_TREND15":
                c15 = _agg_15m(c1)
                closes15 = [float(x["close"]) for x in c15[-40:]]
                e9 = _ema(closes15, 9)
                e21 = _ema(closes15, 21)
                trend15 = e9 is not None and e21 is not None and e9 > e21
                allow = base_ok and trend15
                reason = "u1_trend15_buy" if allow else ("no_15m_trend" if base_ok else reason)
            elif variant == "U2_PULLBACK":
                trend5 = float(b["ema9_5m"]) > float(b["ema21_5m"])
                close = float(b["close"])
                ema21 = float(b["ema21_1m"])
                near = abs(close - ema21) / close <= 0.004 if close else False
                allow = trend5 and near and float(b["rsi14_1m"]) >= 40 and float(b["rsi14_1m"]) <= 60
                reason = "u2_pullback_buy" if allow else "no_pullback"
            elif variant == "U3_ATR_EXITS":
                atrp = _atr_pct(c1[-40:])
                cost_ok = atrp is not None and atrp >= 1.5 * (FEE + SLIP)
                allow = base_ok and bool(cost_ok)
                reason = "u3_cost_ok_buy" if allow else ("cost_filter_reject" if base_ok else reason)
            elif variant == "U4_COOLDOWN":
                last = st.last_entry_i.get(sym, -10_000)
                cool_ok = (i - last) >= 45
                st.entries_hour = [x for x in st.entries_hour if i - x < 60]
                hour_ok = len(st.entries_hour) < 2
                allow = base_ok and cool_ok and hour_ok
                reason = "u4_buy" if allow else ("cooldown_or_cap" if base_ok else reason)
            else:
                allow = False
                reason = "unknown_variant"

            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if allow:
                book.signals_buy += 1
                if _fill_buy(book, sym, float(b["close"]), FEE, SLIP, MAX_POS_USDT):
                    st.last_entry_i[sym] = i
                    st.entries_hour.append(i)
                    invested = sum(p.cost for p in book.positions.values())
            else:
                book.holds += 1

    final_marks = {s: float(symbols_data[s][i1 - 1]["close"]) for s in symbols_data}
    equity = book.mark_equity(final_marks)
    n_closed = wins + losses
    gross_win = sum(x for x in closed_pnls if x > 0)
    gross_loss = abs(sum(x for x in closed_pnls if x < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    bh_start = sum(float(symbols_data[s][warm]["close"]) for s in symbols_data) / len(symbols_data)
    bh_end = sum(float(symbols_data[s][i1 - 1]["close"]) for s in symbols_data) / len(symbols_data)
    bh_ret = (bh_end / bh_start - 1.0) if bh_start else None

    return {
        "variant": variant,
        "bars": i1 - warm,
        "buys": book.buys,
        "sells": book.sells,
        "closed_rounds": n_closed,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / n_closed, 6) if n_closed else None,
        "realized_pnl": round(book.realized, 6),
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "equity": round(equity, 4),
        "net_vs_initial": round(equity - 1000.0, 4),
        "cash_benchmark_net": 0.0,
        "buy_hold_proxy_return": round(bh_ret, 6) if bh_ret is not None else None,
        "profit_factor": round(pf, 6) if pf is not None else None,
        "expectancy": round(sum(closed_pnls) / n_closed, 6) if n_closed else None,
        "max_drawdown_proxy": round(1.0 - (equity / book.peak) if book.peak else 0.0, 6),
        "open_positions": len(book.positions),
        "reasons_top": dict(sorted(book.reasons.items(), key=lambda x: -x[1])[:10]),
        "declare_profitable": False,
    }


async def run_etapa_u(symbols: list[str], limit: int = 1000) -> dict[str, Any]:
    data: dict[str, list[dict]] = {}
    for s in symbols:
        data[s] = await fetch_1m(s, limit=limit)
    n = min(len(v) for v in data.values())
    data = {s: v[-n:] for s, v in data.items()}
    split = int(n * 0.70)
    variants = ["A_BASELINE", "U1_TREND15", "U2_PULLBACK", "U3_ATR_EXITS", "U4_COOLDOWN"]
    is_results = {v: simulate_variant(data, variant=v, i0=80, i1=split) for v in variants}
    oos_results = {v: simulate_variant(data, variant=v, i0=split, i1=n) for v in variants}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "symbols": symbols,
        "bars_per_symbol": n,
        "walk_forward": {"is_end_index": split, "oos_start_index": split, "oos_end_index": n},
        "hypotheses": HYPOTHESES,
        "in_sample": is_results,
        "out_of_sample": oos_results,
        "claim": {
            "declare_winner": False,
            "declare_profitable": False,
            "reason": (
                "Resultados descriptivos en una ventana corta. "
                "No elegir estrategia solo por ser la mejor en IS. "
                "OOS debe confirmarse prospectivamente antes de activar."
            ),
        },
        "note": "No escribe en ledgers A/B. Costos fee+slip incluidos. Fill en close cerrado.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    result = asyncio.run(run_etapa_u(symbols, args.limit))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
