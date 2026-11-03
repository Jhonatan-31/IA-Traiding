"""Authorized SMA signal → lab queue. Never writes to SMA paper account/trades."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import httpx

from ..ohlcv import fetch_klines
from .config import ACCOUNT_ID, BUDGET, MIN_QUOTE_VOLUME, STRATEGY
from .orders import enqueue_order
from .schema import ensure_lab_schema


def sma_cross_signal(closes: list[float]) -> str:
    """Same crossover logic as main.signal but on float closes of closed bars."""
    if len(closes) < 51:
        return "HOLD"
    a = sum(closes[-10:]) / 10
    b = sum(closes[-50:]) / 50
    pa = sum(closes[-11:-1]) / 10
    pb = sum(closes[-51:-1]) / 50
    if pa <= pb and a > b:
        return "BUY"
    if pa >= pb and a < b:
        return "SELL"
    return "HOLD"


def record_signal(execute, *, strategy: str, symbol: str, side: str, candle_ms: int, ref_price: float, meta: dict | None = None) -> dict[str, Any]:
    existing = execute(
        """SELECT * FROM lab_signals
           WHERE strategy=%s AND symbol=%s AND side=%s AND candle_ms=%s""",
        (strategy, symbol, side, candle_ms),
    ).fetchone()
    if existing:
        return {"created": False, "signal": dict(existing)}
    uid = str(uuid.uuid4())
    row = execute(
        """INSERT INTO lab_signals(signal_uid, strategy, symbol, side, candle_ms, ref_price, meta_json)
           VALUES(%s::uuid,%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (strategy, symbol, side, candle_ms) DO NOTHING
           RETURNING *""",
        (uid, strategy, symbol.upper(), side, candle_ms, ref_price, json.dumps(meta or {})),
    ).fetchone()
    if not row:
        row = execute(
            """SELECT * FROM lab_signals
               WHERE strategy=%s AND symbol=%s AND side=%s AND candle_ms=%s""",
            (strategy, symbol, side, candle_ms),
        ).fetchone()
        return {"created": False, "signal": dict(row) if row else None}
    return {"created": True, "signal": dict(row)}


async def scan_and_enqueue(db_factory, *, symbols: list[str] | None = None, limit: int = 15) -> dict[str, Any]:
    """Fetch public klines, emit SMA signals into lab_orders queue only."""
    ensure_lab_schema  # noqa — used below
    summary = {
        "scanned": 0,
        "signals": 0,
        "signals_buy": 0,
        "signals_sell": 0,
        "signals_hold": 0,
        "enqueued": 0,
        "duplicates": 0,
        "errors": 0,
        "hold_sample": [],
        "items": [],
    }
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/lab-executor"}
    ) as client:
        # universe: optional fixed list or top from exchange via tickers
        if not symbols:
            try:
                base = "https://data-api.binance.vision/api/v3"
                info = (await client.get(base + "/exchangeInfo")).json()
                candidates = {
                    s["symbol"]
                    for s in info["symbols"]
                    if s.get("status") == "TRADING"
                    and s.get("quoteAsset") == "USDT"
                    and s.get("isSpotTradingAllowed")
                }
                tickers = (await client.get(base + "/ticker/24hr")).json()
                eligible = sorted(
                    (
                        (Decimal(str(t.get("quoteVolume", 0))), t["symbol"])
                        for t in tickers
                        if t["symbol"] in candidates
                        and Decimal(str(t.get("quoteVolume", 0))) >= MIN_QUOTE_VOLUME
                    ),
                    reverse=True,
                )
                symbols = [s for _, s in eligible[:limit]]
            except Exception as exc:
                summary["errors"] += 1
                summary["items"].append({"error": f"universe:{type(exc).__name__}:{exc}"})
                return summary

        for sym in symbols:
            summary["scanned"] += 1
            try:
                payload = await fetch_klines(client, sym, "1h", limit=80, use_cache=True)
                candles = [c for c in payload["candles"] if c.get("is_closed")]
                if len(candles) < 55:
                    continue
                closes = [float(c["close"]) for c in candles]
                side = sma_cross_signal(closes)
                last = candles[-1]
                if side == "HOLD":
                    summary["signals_hold"] += 1
                    if len(summary["hold_sample"]) < 8:
                        summary["hold_sample"].append(
                            {
                                "symbol": sym,
                                "reason": "no_sma_cross_on_closed_bar",
                                "candle_open_ms": int(last["open_time"]),
                                "closed_only": True,
                            }
                        )
                    continue
                if side == "BUY":
                    summary["signals_buy"] += 1
                elif side == "SELL":
                    summary["signals_sell"] += 1
                # only closed bars used above
                candle_ms = int(last["open_time"])
                ref = float(last["close"])
                with db_factory() as c:
                    ensure_lab_schema(c.execute)
                    sig = record_signal(
                        c.execute,
                        strategy=STRATEGY,
                        symbol=sym,
                        side=side,
                        candle_ms=candle_ms,
                        ref_price=ref,
                        meta={"source": "lab_executor", "not_sma_paper": True},
                    )
                    if not sig.get("created"):
                        summary["duplicates"] += 1
                    else:
                        summary["signals"] += 1
                    signal_id = (sig.get("signal") or {}).get("id")
                    enq = enqueue_order(
                        c.execute,
                        signal_id=signal_id,
                        symbol=sym,
                        side=side,
                        candle_ms=candle_ms,
                        ref_price=ref,
                        budget=BUDGET if side == "BUY" else None,
                        strategy=STRATEGY,
                        meta={"account": ACCOUNT_ID},
                    )
                    if enq.get("created"):
                        summary["enqueued"] += 1
                    else:
                        summary["duplicates"] += 1
                    summary["items"].append(
                        {
                            "symbol": sym,
                            "side": side,
                            "candle_ms": candle_ms,
                            "enqueued": enq.get("created"),
                            "reason": enq.get("reason"),
                        }
                    )
            except Exception as exc:
                summary["errors"] += 1
                summary["items"].append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})
    return summary
