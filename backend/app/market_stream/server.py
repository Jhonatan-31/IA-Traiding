"""Market-stream FastAPI — public fan-out WebSocket for charts (PAPER visualization only)."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .hub import HUB
from .normalize import validate_interval, validate_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("market_stream")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await HUB.start()
    log.info("market-stream hub started (Binance public klines only)")
    yield
    await HUB.stop()
    log.info("market-stream hub stopped")


app = FastAPI(title="AI Trading Bot Pro — market-stream", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "market-stream",
        "paper_only": True,
        "real_trading": False,
        "metrics": HUB.metrics,
    }


@app.get("/api/market/status")
def market_status(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1m"),
):
    try:
        symbol = validate_symbol(symbol)
        interval = validate_interval(interval)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    fresh = HUB.freshness(symbol, interval)
    return {
        "ok": True,
        "symbol": symbol,
        "interval": interval,
        "connection": fresh,
        "metrics": HUB.metrics,
        "note": "Visualization only. Does not drive SMA/Shadow/Lab execution.",
    }


@app.websocket("/ws/market")
async def ws_market(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    subscribed = False
    try:
        # Optional query defaults
        q_symbol = websocket.query_params.get("symbol", "BTCUSDT")
        q_interval = websocket.query_params.get("interval", "1m")
        try:
            await HUB.subscribe_client(queue, q_symbol, q_interval)
            subscribed = True
        except ValueError as exc:
            await websocket.send_json({"type": "error", "error": str(exc)})
            await websocket.close(code=1008)
            return

        async def reader() -> None:
            nonlocal subscribed
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await queue.put({"type": "error", "error": "invalid_json"})
                    continue
                action = msg.get("action")
                if action == "subscribe":
                    sym = msg.get("symbol", q_symbol)
                    iv = msg.get("interval", q_interval)
                    await HUB.unsubscribe_client(queue)
                    try:
                        await HUB.subscribe_client(queue, sym, iv)
                        subscribed = True
                    except ValueError as exc:
                        await queue.put({"type": "error", "error": str(exc)})
                elif action == "ping":
                    await queue.put({"type": "pong", "t": msg.get("t")})
                elif action == "unsubscribe":
                    await HUB.unsubscribe_client(queue)
                    subscribed = False

        async def writer() -> None:
            while True:
                item: dict[str, Any] = await queue.get()
                await websocket.send_json(item)

        reader_task = asyncio.create_task(reader())
        writer_task = asyncio.create_task(writer())
        done, pending = await asyncio.wait(
            {reader_task, writer_task}, return_when=asyncio.FIRST_EXCEPTION
        )
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                log.info("ws client ended: %s", exc)
    except WebSocketDisconnect:
        pass
    finally:
        if subscribed:
            await HUB.unsubscribe_client(queue)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.market_stream.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
