"""Smoke: dashboard WS should emit multiple candle_tick within one minute."""
from __future__ import annotations

import asyncio
import json
import time

import websockets


async def main() -> None:
    url = "ws://dashboard:80/ws/market?symbol=BTCUSDT&interval=1m"
    # via nginx host from outside: use 127.0.0.1:8088 — this script runs in container
    ticks = 0
    sources: set[str] = set()
    prices: list[float] = []
    t0 = time.time()
    async with websockets.connect(url, open_timeout=10) as ws:
        await ws.send(json.dumps({"action": "subscribe", "symbol": "BTCUSDT", "interval": "1m"}))
        while time.time() - t0 < 8:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            if msg.get("type") in ("candle_tick", "kline", "snapshot"):
                ticks += 1
                sources.add(msg.get("source") or msg.get("type"))
                if msg.get("close") is not None:
                    prices.append(float(msg["close"]))
    print(
        json.dumps(
            {
                "ok": ticks >= 5 and len(set(prices)) >= 1,
                "ticks": ticks,
                "unique_closes": len(set(prices)),
                "sources": sorted(sources),
                "price_span": [min(prices), max(prices)] if prices else None,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
