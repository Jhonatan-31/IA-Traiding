"""Historical comparison A (demo 4/5) vs B (crossover) — paper simulation only.

Walks closed 1m bars; builds synthetic 5m from 1m. No look-ahead: signal uses
bar i only after it is closed; fills at close[i] * (1±slip).

Does NOT write to operational ledgers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..demo.indicators import compute_bundle as compute_a
from ..demo.policy import (
    BUY_MIN_FLAGS as A_MIN_FLAGS,
    BUY_SCORE_MIN as A_SCORE_MIN,
    FEE_RATE as A_FEE,
    MAX_EXPOSURE_USDT as A_EXPO,
    MAX_POS_USDT as A_POS,
    MAX_POSITIONS as A_MAXPOS,
    SLIP_RATE as A_SLIP,
    STOP_LOSS_PCT as A_SL,
    TAKE_PROFIT_PCT as A_TP,
)
from ..express.indicators import _ema, _rsi  # noqa: F401 — available for diagnostics
from .indicators_b import compute_bundle as compute_b
from .indicators_b import evaluate_entry, evaluate_exit
from .policy_b import (
    FEE_RATE as B_FEE,
    MAX_EXPOSURE_USDT as B_EXPO,
    MAX_POS_USDT as B_POS,
    MAX_POSITIONS as B_MAXPOS,
    POLICY_VERSION as B_VER,
    SLIP_RATE as B_SLIP,
)


BASE = "https://api.binance.com/api/v3"


def _agg_5m(c1: list[dict]) -> list[dict]:
    out: list[dict] = []
    bucket: list[dict] = []
    for c in c1:
        bucket.append(c)
        if len(bucket) == 5:
            out.append(
                {
                    "open_time": bucket[0]["open_time"],
                    "open": bucket[0]["open"],
                    "high": max(float(x["high"]) for x in bucket),
                    "low": min(float(x["low"]) for x in bucket),
                    "close": bucket[-1]["close"],
                    "volume": sum(float(x["volume"]) for x in bucket),
                    "is_closed": True,
                }
            )
            bucket = []
    return out


async def fetch_1m(symbol: str, limit: int = 1000) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{BASE}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": limit},
        )
        r.raise_for_status()
        rows = r.json()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candles = []
    for row in rows:
        ot = int(row[0])
        # exclude forming candle
        if ot + 60_000 > now_ms:
            continue
        candles.append(
            {
                "open_time": ot,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "is_closed": True,
            }
        )
    return candles


@dataclass
class Pos:
    qty: float
    entry: float
    cost: float


@dataclass
class Book:
    cash: float = 1000.0
    peak: float = 1000.0
    positions: dict[str, Pos] = field(default_factory=dict)
    buys: int = 0
    sells: int = 0
    holds: int = 0
    signals_buy: int = 0
    realized: float = 0.0
    fees: float = 0.0
    slips: float = 0.0
    reasons: dict[str, int] = field(default_factory=dict)

    def mark_equity(self, marks: dict[str, float]) -> float:
        inv = 0.0
        for s, p in self.positions.items():
            inv += p.qty * marks.get(s, p.entry)
        return self.cash + inv


def _fill_buy(book: Book, symbol: str, px: float, fee_r: float, slip_r: float, budget: float) -> bool:
    fill = px * (1 + slip_r)
    notional = min(budget, book.cash * 0.99)
    if notional < 5:
        return False
    fee = notional * fee_r
    qty = (notional - fee) / fill
    if qty <= 0:
        return False
    book.cash -= notional
    book.positions[symbol] = Pos(qty=qty, entry=fill, cost=notional)
    book.buys += 1
    book.fees += fee
    book.slips += notional * slip_r
    return True


def _fill_sell(book: Book, symbol: str, px: float, fee_r: float, slip_r: float) -> bool:
    pos = book.positions.get(symbol)
    if not pos:
        return False
    fill = px * (1 - slip_r)
    gross = pos.qty * fill
    fee = gross * fee_r
    net = gross - fee
    rpnl = net - pos.cost
    book.cash += net
    book.realized += rpnl
    book.fees += fee
    book.slips += gross * slip_r
    book.sells += 1
    del book.positions[symbol]
    return True


def simulate(
    symbols_data: dict[str, list[dict]],
    *,
    mode: str,
) -> dict[str, Any]:
    """mode: 'A' demo flags or 'B' active crossover."""
    book = Book()
    # align by index using shortest series length
    n = min(len(v) for v in symbols_data.values())
    warm = 80
    for i in range(warm, n):
        marks = {s: float(symbols_data[s][i]["close"]) for s in symbols_data}
        equity = book.mark_equity(marks)
        book.peak = max(book.peak, equity)
        pause = equity <= book.peak * 0.97
        invested = sum(p.cost for p in book.positions.values())

        # exits first
        for sym in list(book.positions.keys()):
            c1 = symbols_data[sym][: i + 1]
            c5 = _agg_5m(c1)
            if mode == "A":
                b = compute_a(c1[-120:], c5[-80:])
                if not b:
                    continue
                entry = book.positions[sym].entry
                mark = float(b["close"])
                action, reason = "HOLD", "hold_position"
                if mark <= entry * (1 - A_SL):
                    action, reason = "SELL", "stop_loss_1pct"
                elif mark >= entry * (1 + A_TP):
                    action, reason = "SELL", "take_profit_2pct"
                elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                    action, reason = "SELL", "trend_break_1m"
            else:
                b = compute_b(c1[-120:], c5[-80:])
                if not b:
                    continue
                action, reason = evaluate_exit(b, book.positions[sym].entry)
            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if action == "SELL":
                fee, slip = (A_FEE, A_SLIP) if mode == "A" else (B_FEE, B_SLIP)
                _fill_sell(book, sym, float(b["close"]), fee, slip)
            else:
                book.holds += 1

        # entries
        fee = A_FEE if mode == "A" else B_FEE
        slip = A_SLIP if mode == "A" else B_SLIP
        max_pos = A_MAXPOS if mode == "A" else B_MAXPOS
        expo = A_EXPO if mode == "A" else B_EXPO
        budget = A_POS if mode == "A" else B_POS
        for sym in symbols_data:
            if sym in book.positions:
                continue
            if pause or len(book.positions) >= max_pos or invested >= expo - 1e-9:
                continue
            c1 = symbols_data[sym][: i + 1]
            c5 = _agg_5m(c1)
            if mode == "A":
                b = compute_a(c1[-120:], c5[-80:])
                if not b:
                    continue
                n_true = int(b["flags_true"])
                score = float(b["signal_score"])
                if n_true >= A_MIN_FLAGS and score >= A_SCORE_MIN:
                    action, reason = "BUY", f"policy_{n_true}_of_5_flags"
                else:
                    action, reason = "HOLD", f"flags_{n_true}_of_5_insufficient"
            else:
                b = compute_b(c1[-120:], c5[-80:])
                if not b:
                    continue
                action, reason = evaluate_entry(b)
            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if action == "BUY":
                book.signals_buy += 1
                if _fill_buy(book, sym, float(b["close"]), fee, slip, budget):
                    invested = sum(p.cost for p in book.positions.values())
            else:
                book.holds += 1

    final_marks = {s: float(symbols_data[s][-1]["close"]) for s in symbols_data}
    equity = book.mark_equity(final_marks)
    return {
        "mode": mode,
        "policy": "demo_policy_v1_20261103" if mode == "A" else B_VER,
        "bars": n - warm,
        "buys": book.buys,
        "sells": book.sells,
        "holds": book.holds,
        "signals_buy": book.signals_buy,
        "realized_pnl": round(book.realized, 6),
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "cash": round(book.cash, 4),
        "equity": round(equity, 4),
        "open_positions": len(book.positions),
        "net_vs_initial": round(equity - 1000.0, 4),
        "max_drawdown_proxy": round(1.0 - (equity / book.peak) if book.peak else 0.0, 6),
        "reasons_top": dict(sorted(book.reasons.items(), key=lambda x: -x[1])[:12]),
        "note": "Historical paper sim; not proof of future returns. Costs included.",
    }


async def run(symbols: list[str], limit: int) -> dict[str, Any]:
    data: dict[str, list[dict]] = {}
    for s in symbols:
        data[s] = await fetch_1m(s, limit=limit)
    # trim to common length
    n = min(len(v) for v in data.values())
    data = {s: v[-n:] for s, v in data.items()}
    a = simulate(data, mode="A")
    b = simulate(data, mode="B")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "bars_per_symbol": n,
        "strategy_a": a,
        "strategy_b": b,
        "comparison_note": (
            "Same window and costs model. B uses EMA crossover structure; "
            "A uses 4/5 flags. Insufficient sample ⇒ no winner declaration."
        ),
        "sample_sufficient_for_claim": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=720, help="1m bars per symbol (~12h)")
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    result = asyncio.run(run(symbols, args.limit))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
