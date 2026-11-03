"""Process lab order queue and exits — PAPER_ONLY, no real orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from .config import (
    ACCOUNT_ID,
    BUDGET,
    FEE_RATE,
    INTERVAL_MS,
    MAX_POSITIONS,
    MIN_BUDGET,
    PRICE_STALE_S,
    SLIP_RATE,
    STRATEGY,
)
from .exits import evaluate_exit
from .ledger import apply_buy, apply_sell, snapshot
from .orders import claim_new_orders, enqueue_order, mark_order
from .risk import (
    accounting_ok,
    can_buy,
    ensure_daily_equity,
    evaluate_lab_breaker,
    lab_equity,
    persist_lab_breaker,
)
from .schema import ensure_lab_schema


def _d(x) -> Decimal:
    return Decimal(str(x))


def _now():
    return datetime.now(timezone.utc)


async def _spot_valid(client: httpx.AsyncClient, symbol: str) -> bool:
    try:
        r = await client.get(
            "https://data-api.binance.vision/api/v3/exchangeInfo",
            params={"symbol": symbol},
        )
        if r.status_code != 200:
            return False
        data = r.json()
        syms = data.get("symbols") or []
        if not syms:
            return False
        s = syms[0]
        return (
            s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed")
            and s.get("quoteAsset") == "USDT"
        )
    except Exception:
        return False


async def _ticker(client: httpx.AsyncClient, symbol: str) -> tuple[Decimal | None, float | None]:
    try:
        r = await client.get(
            "https://data-api.binance.vision/api/v3/ticker/price",
            params={"symbol": symbol},
        )
        r.raise_for_status()
        px = Decimal(str(r.json()["price"]))
        return px, 0.0  # live ticker ≈ fresh
    except Exception:
        return None, None


async def process_orders(db_factory) -> dict[str, Any]:
    summary = {"processed": 0, "filled": 0, "rejected": 0, "items": []}
    assumptions = ExecutionAssumptions(
        fee_rate=float(FEE_RATE), base_slip_rate=float(SLIP_RATE)
    )

    with db_factory() as c:
        ensure_lab_schema(c.execute)
        state = c.execute("SELECT * FROM lab_executor_state WHERE id=1").fetchone()
        paused = bool(state and state.get("paused"))
        claimed = claim_new_orders(c.execute, limit=40)

    if not claimed:
        return summary

    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ResearchPaperBot/lab-executor"}
    ) as client:
        binance_ok = True
        try:
            ping = await client.get("https://data-api.binance.vision/api/v3/ping")
            binance_ok = ping.status_code == 200
        except Exception:
            binance_ok = False

        for order in claimed:
            summary["processed"] += 1
            oid = int(order["id"])
            side = order["side"]
            symbol = order["symbol"]
            try:
                with db_factory() as c:
                    ensure_lab_schema(c.execute)
                    eq = lab_equity(c.execute)
                    day_start = ensure_daily_equity(c.execute, eq["equity"])
                    peak = max(eq["equity"], day_start, eq["initial_capital"])
                    acct_ok = accounting_ok(c.execute)
                    active, reason = evaluate_lab_breaker(
                        c.execute,
                        equity=eq["equity"],
                        day_start_equity=day_start,
                        peak_equity=peak,
                        data_age_s=0.0,
                        binance_ok=binance_ok,
                        accounting_ok=acct_ok,
                        strategy=order.get("strategy") or STRATEGY,
                    )
                    persist_lab_breaker(c.execute, active, reason)

                if side == "BUY":
                    spot_ok = await _spot_valid(client, symbol)
                    mark, age = await _ticker(client, symbol)
                    fill = (
                        estimate_fill_price(
                            side="BUY",
                            mid_or_ref=float(mark),
                            assumptions=assumptions,
                            bar_volume=None,
                            order_qty=None,
                            order_book=None,
                        )
                        if mark
                        else {"ok": False, "reason": "no_price"}
                    )
                    budget = _d(order.get("budget") or BUDGET)
                    if budget < MIN_BUDGET:
                        budget = MIN_BUDGET
                    with db_factory() as c:
                        eq = lab_equity(c.execute)
                        ok, why = can_buy(
                            paused=paused,
                            breaker_active=active,
                            cash=eq["cash"],
                            budget=budget,
                            positions_n=eq["positions_n"],
                            max_positions=MAX_POSITIONS,
                            symbol_valid=spot_ok,
                            data_fresh=age is not None and age <= PRICE_STALE_S,
                            liquidity_ok=True,  # volume gate at signal scan
                            fill_ok=bool(fill.get("ok")),
                            strategy=order.get("strategy") or STRATEGY,
                        )
                        if not ok:
                            mark_order(
                                c.execute, oid, status="REJECTED", reject_reason=why
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["rejected"] += 1
                            summary["items"].append({"id": oid, "status": "REJECTED", "reason": why})
                            continue
                        uid = str(order["order_uid"])
                        result = apply_buy(
                            c.execute,
                            order_uid=uid,
                            symbol=symbol,
                            budget=budget,
                            fill_price=_d(fill["price"]),
                            candle_ms=int(order["candle_ms"]),
                            strategy=STRATEGY,
                            reason="lab_auto_buy",
                        )
                        if result["status"] != "FILLED":
                            mark_order(
                                c.execute,
                                oid,
                                status="REJECTED",
                                reject_reason=result.get("reason"),
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["rejected"] += 1
                        else:
                            mark_order(
                                c.execute,
                                oid,
                                status="FILLED",
                                filled_qty=_d(result["qty"]),
                                avg_price=_d(fill["price"]),
                                fee=_d(result["fee"]),
                                slip=_d(result.get("slip") or 0),
                                execution_price=_d(fill["price"]),
                                meta={"execution_class": fill.get("execution_class")},
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_filled=orders_filled+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["filled"] += 1
                        summary["items"].append({"id": oid, "status": result["status"], **result})

                elif side == "SELL":
                    mark, age = await _ticker(client, symbol)
                    with db_factory() as c:
                        if mark is None or (age is not None and age > PRICE_STALE_S):
                            mark_order(
                                c.execute,
                                oid,
                                status="REJECTED",
                                reject_reason="stale_or_missing_mark",
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["rejected"] += 1
                            summary["items"].append(
                                {
                                    "id": oid,
                                    "status": "REJECTED",
                                    "reason": "stale_or_missing_mark",
                                }
                            )
                            continue
                        # Risk exits still process when breaker active; only skip if paused
                        if paused:
                            mark_order(
                                c.execute,
                                oid,
                                status="CANCELLED",
                                reject_reason="executor_paused",
                            )
                            summary["rejected"] += 1
                            continue
                        fill = estimate_fill_price(
                            side="SELL",
                            mid_or_ref=float(mark),
                            assumptions=assumptions,
                            order_book=None,
                        )
                        if not fill.get("ok"):
                            mark_order(
                                c.execute,
                                oid,
                                status="REJECTED",
                                reject_reason=str(fill.get("reason")),
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["rejected"] += 1
                            continue
                        uid = str(order["order_uid"])
                        meta = order.get("meta_json") or {}
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        result = apply_sell(
                            c.execute,
                            order_uid=uid,
                            symbol=symbol,
                            fill_price=_d(fill["price"]),
                            candle_ms=int(order["candle_ms"]),
                            strategy=STRATEGY,
                            reason=meta.get("exit_reason") or "lab_auto_sell",
                            stop_triggered=bool(meta.get("stop_triggered")),
                            stop_trigger_price=_d(meta["stop_trigger_price"])
                            if meta.get("stop_trigger_price") is not None
                            else None,
                        )
                        if result["status"] != "FILLED":
                            mark_order(
                                c.execute,
                                oid,
                                status="REJECTED",
                                reject_reason=result.get("reason"),
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["rejected"] += 1
                        else:
                            mark_order(
                                c.execute,
                                oid,
                                status="FILLED",
                                filled_qty=_d(result["qty"]),
                                avg_price=_d(fill["price"]),
                                fee=_d(result["fee"]),
                                execution_price=_d(result["execution_price"]),
                                stop_triggered=result.get("stop_triggered"),
                                stop_trigger_price=_d(result["stop_trigger_price"])
                                if result.get("stop_trigger_price") is not None
                                else None,
                            )
                            c.execute(
                                """UPDATE lab_executor_state SET
                                     orders_filled=orders_filled+1, updated_at=NOW() WHERE id=1"""
                            )
                            summary["filled"] += 1
                        summary["items"].append({"id": oid, **result})
                else:
                    with db_factory() as c:
                        mark_order(
                            c.execute, oid, status="REJECTED", reject_reason="invalid_side"
                        )
                        c.execute(
                            """UPDATE lab_executor_state SET
                                 orders_rejected=orders_rejected+1, updated_at=NOW() WHERE id=1"""
                        )
                    summary["rejected"] += 1
            except Exception as exc:
                with db_factory() as c:
                    mark_order(
                        c.execute,
                        oid,
                        status="REJECTED",
                        reject_reason=f"exec_error:{type(exc).__name__}",
                    )
                    c.execute(
                        """UPDATE lab_executor_state SET
                             orders_rejected=orders_rejected+1,
                             last_error=%s, updated_at=NOW() WHERE id=1""",
                        (str(exc)[:500],),
                    )
                summary["rejected"] += 1
                summary["items"].append({"id": oid, "error": str(exc)})
    return summary


async def scan_exits(db_factory) -> dict[str, Any]:
    """Enqueue SELL orders from exit policy without fabricating fills on stale data."""
    summary = {"checked": 0, "enqueued": 0, "held": 0}
    with db_factory() as c:
        ensure_lab_schema(c.execute)
        positions = list(
            c.execute("SELECT * FROM lab_positions WHERE account_id=%s", (ACCOUNT_ID,))
        )
    if not positions:
        return summary

    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ResearchPaperBot/lab-exits"}
    ) as client:
        for pos in positions:
            summary["checked"] += 1
            symbol = pos["symbol"]
            mark, age = await _ticker(client, symbol)
            opened = pos.get("opened_candle_ms")
            bars_held = None
            if opened is not None:
                bars_held = int((_now().timestamp() * 1000 - int(opened)) // INTERVAL_MS)
            decision = evaluate_exit(
                pos,
                mark_price=mark,
                mark_age_s=age,
                stale_s=float(PRICE_STALE_S),
                strategy_side=None,  # strategy exits come via signal enqueue
                bars_held=bars_held,
            )
            if decision["action"] != "SELL" or not decision.get("allow_execution"):
                summary["held"] += 1
                continue
            candle_ms = int(_now().timestamp() * 1000) // INTERVAL_MS * INTERVAL_MS
            with db_factory() as c:
                enq = enqueue_order(
                    c.execute,
                    signal_id=None,
                    symbol=symbol,
                    side="SELL",
                    candle_ms=candle_ms,
                    ref_price=float(mark) if mark else None,
                    strategy=STRATEGY,
                    meta={
                        "exit_reason": decision["reason"],
                        "stop_triggered": decision.get("stop_triggered"),
                        "stop_trigger_price": decision.get("stop_trigger_price"),
                    },
                )
                if enq.get("created"):
                    summary["enqueued"] += 1
                else:
                    summary["held"] += 1
    return summary


async def run_lab_cycle(db_factory) -> dict[str, Any]:
    from .signals import scan_and_enqueue
    from .valuation import fetch_marks, portfolio_valuation

    started = _now()
    with db_factory() as c:
        ensure_lab_schema(c.execute)
        state = c.execute("SELECT paused FROM lab_executor_state WHERE id=1").fetchone()
        if state and state.get("paused"):
            c.execute(
                """UPDATE lab_executor_state SET
                     heartbeat_at=NOW(), status='PAUSED', updated_at=NOW() WHERE id=1"""
            )
            finished = _now()
            c.execute(
                """INSERT INTO lab_cycles(
                    started_at, finished_at, duration_ms, ok, paused, meta_json)
                   VALUES(%s,%s,%s,TRUE,TRUE,%s::jsonb)""",
                (
                    started,
                    finished,
                    int((finished - started).total_seconds() * 1000),
                    json.dumps({"note": "paused_skip"}),
                ),
            )
            return {"ok": True, "paused": True}

    signals = await scan_and_enqueue(db_factory, cycle_started_at=started)
    exits = await scan_exits(db_factory)
    orders = await process_orders(db_factory)

    with db_factory() as c:
        snap = snapshot(c.execute)
        pos_syms = [p["symbol"] for p in snap["positions"]]
    marks = await fetch_marks(pos_syms)
    with db_factory() as c:
        valuation = portfolio_valuation(c.execute, marks)
        # Update daily end equity when complete
        if valuation.get("equity_estimate") is not None:
            from datetime import date

            c.execute(
                """INSERT INTO lab_equity_daily(account_id, day, start_equity, end_equity)
                   VALUES(%s,%s,%s,%s)
                   ON CONFLICT (account_id, day) DO UPDATE
                   SET end_equity=EXCLUDED.end_equity""",
                (
                    ACCOUNT_ID,
                    date.today(),
                    valuation["equity_estimate"],
                    valuation["equity_estimate"],
                ),
            )
        finished = _now()
        duration_ms = int((finished - started).total_seconds() * 1000)
        import os

        slip_est = sum(
            float(i.get("slip") or 0)
            for i in (orders.get("items") or [])
            if isinstance(i, dict)
        )
        # Heartbeat first so monitor sees a fresh pulse for this successful cycle
        c.execute(
            """UPDATE lab_executor_state SET
                 status='OK',
                 heartbeat_at=NOW(),
                 last_cycle_at=NOW(),
                 last_cycle_ok=TRUE,
                 last_error=NULL,
                 cycle_count=cycle_count+1,
                 meta_json=meta_json || %s::jsonb,
                 updated_at=NOW()
               WHERE id=1""",
            (
                json.dumps(
                    {
                        "last_signals": {
                            "buy": signals.get("signals_buy"),
                            "sell": signals.get("signals_sell"),
                            "hold": signals.get("signals_hold"),
                            "crosses": signals.get("crosses_detected"),
                            "enqueued": signals.get("enqueued"),
                            "duplicates": signals.get("duplicates"),
                        },
                        "last_exits": exits,
                        "last_orders": {
                            "filled": orders.get("filled"),
                            "rejected": orders.get("rejected"),
                        },
                        "valuation_status": valuation.get("valuation_status"),
                        "last_candle_ms": signals.get("last_candle_ms"),
                        "snapshot": {
                            "cash": snap["cash"],
                            "positions": len(snap["positions"]),
                        },
                    }
                ),
            ),
        )
        from .monitor import run_monitor

        expected_cycle_s = float(os.environ.get("LAB_EVERY_SECONDS", "300"))
        monitor = run_monitor(
            c.execute,
            expected_cycle_s=expected_cycle_s,
            binance_errors=int(signals.get("errors") or 0),
        )
        c.execute(
            """UPDATE lab_executor_state SET
                 meta_json=meta_json || %s::jsonb, updated_at=NOW() WHERE id=1""",
            (json.dumps({"monitor_active": len(monitor.get("active") or [])}),),
        )
        c.execute(
            """INSERT INTO lab_cycles(
                started_at, finished_at, duration_ms, ok, paused,
                symbols_scanned, signals_buy, signals_sell, signals_hold,
                orders_generated, orders_rejected, orders_filled, errors,
                hold_sample_json, meta_json)
               VALUES(%s,%s,%s,TRUE,FALSE,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
            (
                started,
                finished,
                duration_ms,
                int(signals.get("scanned") or 0),
                int(signals.get("signals_buy") or 0),
                int(signals.get("signals_sell") or 0),
                int(signals.get("signals_hold") or 0),
                int(signals.get("enqueued") or 0) + int(exits.get("enqueued") or 0),
                int(orders.get("rejected") or 0),
                int(orders.get("filled") or 0),
                int(signals.get("errors") or 0),
                json.dumps(signals.get("hold_sample") or []),
                json.dumps(
                    {
                        "exits": exits,
                        "orders": {
                            "processed": orders.get("processed"),
                            "filled": orders.get("filled"),
                            "rejected": orders.get("rejected"),
                        },
                        "valuation_status": valuation.get("valuation_status"),
                        "crosses_detected": signals.get("crosses_detected"),
                        "last_candle_ms": signals.get("last_candle_ms"),
                        "eval_sample": signals.get("eval_sample") or [],
                        "slippage_estimate_cycle": slip_est,
                        "monitor": {
                            "raised": monitor.get("raised"),
                            "active_n": len(monitor.get("active") or []),
                        },
                    }
                ),
            ),
        )
    return {
        "ok": True,
        "paused": False,
        "signals": signals,
        "exits": exits,
        "orders": orders,
        "valuation": valuation,
        "monitor": monitor,
        "duration_ms": duration_ms,
        "note": "PAPER_ONLY lab ledger; SMA paper account untouched; Shadow AI not executing.",
    }
