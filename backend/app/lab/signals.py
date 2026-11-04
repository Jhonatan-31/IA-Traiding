"""Authorized SMA signal → lab queue. Never writes to SMA paper account/trades."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from ..ohlcv import fetch_klines
from .config import ACCOUNT_ID, BUDGET, MIN_QUOTE_VOLUME, STRATEGY
from .orders import enqueue_order
from .schema import ensure_lab_schema


def analyze_sma_cross(closes: list[float]) -> dict[str, Any]:
    """
    Closed-bar SMA10/SMA50 cross without look-ahead.
    Uses only completed closes; prev window excludes the latest closed bar.
    """
    if len(closes) < 51:
        return {
            "decision": "HOLD",
            "reason": "insufficient_closed_bars",
            "cross_state": "none",
            "sma10": None,
            "sma50": None,
            "sma10_prev": None,
            "sma50_prev": None,
            "data_status": "insufficient_bars",
        }
    a = sum(closes[-10:]) / 10
    b = sum(closes[-50:]) / 50
    pa = sum(closes[-11:-1]) / 10
    pb = sum(closes[-51:-1]) / 50
    if pa <= pb and a > b:
        decision, cross, reason = "BUY", "golden", "sma10_cross_above_sma50_closed"
    elif pa >= pb and a < b:
        decision, cross, reason = "SELL", "death", "sma10_cross_below_sma50_closed"
    else:
        decision, cross, reason = "HOLD", "none", "no_sma_cross_on_closed_bar"
    return {
        "decision": decision,
        "reason": reason,
        "cross_state": cross,
        "sma10": a,
        "sma50": b,
        "sma10_prev": pa,
        "sma50_prev": pb,
        "data_status": "ok",
    }


def sma_cross_signal(closes: list[float]) -> str:
    """Same crossover logic as main.signal but on float closes of closed bars."""
    return str(analyze_sma_cross(closes)["decision"])


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


def record_eval(
    execute,
    *,
    cycle_started_at: datetime,
    symbol: str,
    candle_ms: int | None,
    analysis: dict[str, Any],
    risk_status: str,
    meta: dict | None = None,
) -> None:
    execute(
        """INSERT INTO lab_signal_evals(
            cycle_started_at, symbol, candle_ms,
            sma10, sma50, sma10_prev, sma50_prev,
            cross_state, decision, reason, data_status, risk_status,
            closed_only, meta_json)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s::jsonb)""",
        (
            cycle_started_at,
            symbol.upper(),
            candle_ms,
            analysis.get("sma10"),
            analysis.get("sma50"),
            analysis.get("sma10_prev"),
            analysis.get("sma50_prev"),
            analysis.get("cross_state") or "none",
            analysis.get("decision") or "HOLD",
            analysis.get("reason"),
            analysis.get("data_status") or "ok",
            risk_status,
            json.dumps(meta or {}),
        ),
    )


async def scan_and_enqueue(
    db_factory,
    *,
    symbols: list[str] | None = None,
    limit: int = 15,
    cycle_started_at: datetime | None = None,
) -> dict[str, Any]:
    """Fetch public klines, emit SMA signals into lab_orders queue only."""
    started = cycle_started_at or datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "scanned": 0,
        "signals": 0,
        "signals_buy": 0,
        "signals_sell": 0,
        "signals_hold": 0,
        "crosses_detected": 0,
        "enqueued": 0,
        "duplicates": 0,  # sum of signal+order idempotent skips (not double fills)
        "duplicates_signal": 0,
        "duplicates_order": 0,
        "errors": 0,
        "hold_sample": [],
        "eval_sample": [],
        "items": [],
        "last_candle_ms": None,
        "cycle_started_at": started.isoformat(),
    }
    with db_factory() as c:
        ensure_lab_schema(c.execute)
        st = c.execute("SELECT paused, breaker_active, breaker_reason FROM lab_executor_state WHERE id=1").fetchone()
    if st and st.get("paused"):
        risk_status = "paused"
    elif st and st.get("breaker_active"):
        risk_status = f"breaker:{st.get('breaker_reason') or 'active'}"
    else:
        risk_status = "ok"

    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/lab-executor"}
    ) as client:
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
                    analysis = {
                        "decision": "HOLD",
                        "reason": "insufficient_closed_bars",
                        "cross_state": "none",
                        "sma10": None,
                        "sma50": None,
                        "sma10_prev": None,
                        "sma50_prev": None,
                        "data_status": "insufficient_bars",
                    }
                    with db_factory() as c:
                        ensure_lab_schema(c.execute)
                        record_eval(
                            c.execute,
                            cycle_started_at=started,
                            symbol=sym,
                            candle_ms=None,
                            analysis=analysis,
                            risk_status=risk_status,
                        )
                    summary["signals_hold"] += 1
                    continue
                closes = [float(c["close"]) for c in candles]
                analysis = analyze_sma_cross(closes)
                last = candles[-1]
                candle_ms = int(last["open_time"])
                ref = float(last["close"])
                summary["last_candle_ms"] = candle_ms
                side = analysis["decision"]

                with db_factory() as c:
                    ensure_lab_schema(c.execute)
                    record_eval(
                        c.execute,
                        cycle_started_at=started,
                        symbol=sym,
                        candle_ms=candle_ms,
                        analysis=analysis,
                        risk_status=risk_status,
                        meta={"ref_price": ref, "closed_only": True},
                    )

                if len(summary["eval_sample"]) < 12:
                    summary["eval_sample"].append(
                        {
                            "symbol": sym,
                            "candle_ms": candle_ms,
                            "sma10": analysis.get("sma10"),
                            "sma50": analysis.get("sma50"),
                            "cross_state": analysis.get("cross_state"),
                            "decision": side,
                            "reason": analysis.get("reason"),
                            "data_status": analysis.get("data_status"),
                            "risk_status": risk_status,
                        }
                    )

                if side == "HOLD":
                    summary["signals_hold"] += 1
                    if len(summary["hold_sample"]) < 8:
                        summary["hold_sample"].append(
                            {
                                "symbol": sym,
                                "reason": analysis.get("reason"),
                                "candle_open_ms": candle_ms,
                                "sma10": analysis.get("sma10"),
                                "sma50": analysis.get("sma50"),
                                "closed_only": True,
                            }
                        )
                    continue

                summary["crosses_detected"] += 1
                if side == "BUY":
                    summary["signals_buy"] += 1
                elif side == "SELL":
                    summary["signals_sell"] += 1

                meta_sig = {
                    "source": "lab_executor",
                    "not_sma_paper": True,
                    "sma10": analysis.get("sma10"),
                    "sma50": analysis.get("sma50"),
                    "sma10_prev": analysis.get("sma10_prev"),
                    "sma50_prev": analysis.get("sma50_prev"),
                    "cross_state": analysis.get("cross_state"),
                    "reason": analysis.get("reason"),
                    "data_status": analysis.get("data_status"),
                    "risk_status": risk_status,
                    "closed_only": True,
                }
                with db_factory() as c:
                    ensure_lab_schema(c.execute)
                    sig = record_signal(
                        c.execute,
                        strategy=STRATEGY,
                        symbol=sym,
                        side=side,
                        candle_ms=candle_ms,
                        ref_price=ref,
                        meta=meta_sig,
                    )
                    if not sig.get("created"):
                        # Idempotent skip: signal already exists for (strategy,symbol,side,candle_ms)
                        summary["duplicates_signal"] += 1
                        summary["duplicates"] += 1
                    else:
                        # Newly persisted lab_signals row (not the same as signals_buy)
                        summary["signals"] += 1
                    signal_id = (sig.get("signal") or {}).get("id")
                    # Never enqueue SELL without open lab inventory (no phantom sells)
                    if side == "SELL":
                        pos = c.execute(
                            """SELECT 1 FROM lab_positions
                               WHERE account_id=%s AND symbol=%s""",
                            (ACCOUNT_ID, sym.upper()),
                        ).fetchone()
                        if not pos:
                            summary["items"].append(
                                {
                                    "symbol": sym,
                                    "side": side,
                                    "candle_ms": candle_ms,
                                    "enqueued": False,
                                    "reason": "sell_skipped_no_position",
                                    "cross_state": analysis.get("cross_state"),
                                }
                            )
                            continue
                    enq = enqueue_order(
                        c.execute,
                        signal_id=signal_id,
                        symbol=sym,
                        side=side,
                        candle_ms=candle_ms,
                        ref_price=ref,
                        budget=BUDGET if side == "BUY" else None,
                        strategy=STRATEGY,
                        meta={
                            "account": ACCOUNT_ID,
                            "signal_reason": analysis.get("reason"),
                            "exit_reason": "strategy_exit" if side == "SELL" else None,
                        },
                    )
                    if enq.get("created"):
                        summary["enqueued"] += 1
                    else:
                        # Idempotent skip: order already exists for unique key
                        summary["duplicates_order"] += 1
                        summary["duplicates"] += 1
                    summary["items"].append(
                        {
                            "symbol": sym,
                            "side": side,
                            "candle_ms": candle_ms,
                            "enqueued": enq.get("created"),
                            "signal_created": bool(sig.get("created")),
                            "reason": enq.get("reason") or analysis.get("reason"),
                            "cross_state": analysis.get("cross_state"),
                            "idempotency": {
                                "signal_key": ["strategy", "symbol", "side", "candle_ms"],
                                "order_key": [
                                    "account_id",
                                    "strategy",
                                    "symbol",
                                    "side",
                                    "candle_ms",
                                ],
                            },
                        }
                    )
            except Exception as exc:
                summary["errors"] += 1
                summary["items"].append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})
                with db_factory() as c:
                    ensure_lab_schema(c.execute)
                    record_eval(
                        c.execute,
                        cycle_started_at=started,
                        symbol=sym,
                        candle_ms=None,
                        analysis={
                            "decision": "HOLD",
                            "reason": f"fetch_error:{type(exc).__name__}",
                            "cross_state": "none",
                            "data_status": "error",
                        },
                        risk_status=risk_status,
                    )
    return summary
