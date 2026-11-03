"""One-shot verifiable lab BUY→SELL using live public ticker (not an SMA claim)."""
from __future__ import annotations

import asyncio

import httpx

from app.lab.config import ACCOUNT_ID, BUDGET, STRATEGY
from app.lab.executor import process_orders
from app.lab.ledger import snapshot
from app.lab.orders import enqueue_order
from app.lab.schema import ensure_lab_schema
from app.main import db


async def main() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://data-api.binance.vision/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
        )
        px = float(r.json()["price"])
    candle_ms = 1_700_000_000_000
    with db() as c:
        ensure_lab_schema(c.execute)
        c.execute("DELETE FROM lab_orders WHERE candle_ms IN (%s,%s)", (candle_ms, candle_ms + 1))
        c.execute("DELETE FROM lab_trades WHERE candle_ms IN (%s,%s)", (candle_ms, candle_ms + 1))
        c.execute(
            "DELETE FROM lab_positions WHERE account_id=%s AND symbol='BTCUSDT'",
            (ACCOUNT_ID,),
        )
        c.execute("UPDATE lab_accounts SET cash=1000 WHERE id=%s", (ACCOUNT_ID,))
        buy = enqueue_order(
            c.execute,
            signal_id=None,
            symbol="BTCUSDT",
            side="BUY",
            candle_ms=candle_ms,
            ref_price=px,
            budget=BUDGET,
            strategy=STRATEGY,
            meta={"demo_verification": True, "note": "forced_example_not_live_sma_cross"},
        )
        print("enqueue_buy", buy.get("created"), buy.get("reason"))
    print("process_buy", await process_orders(db))
    with db() as c:
        print("snap_after_buy", snapshot(c.execute))
        sell = enqueue_order(
            c.execute,
            signal_id=None,
            symbol="BTCUSDT",
            side="SELL",
            candle_ms=candle_ms + 1,
            ref_price=px,
            strategy=STRATEGY,
            meta={"exit_reason": "demo_verification_sell", "demo_verification": True},
        )
        print("enqueue_sell", sell.get("created"))
    print("process_sell", await process_orders(db))
    with db() as c:
        print("snap_final", snapshot(c.execute))
        for row in c.execute(
            """SELECT side, symbol, qty, price, fee, reason, realized_pnl
               FROM lab_trades WHERE account_id=%s ORDER BY id""",
            (ACCOUNT_ID,),
        ):
            print("TRADE", dict(row))
        sma = c.execute("SELECT cash FROM account WHERE id=1").fetchone()
        print("SMA_CASH_UNCHANGED", float(sma["cash"]))


if __name__ == "__main__":
    asyncio.run(main())
