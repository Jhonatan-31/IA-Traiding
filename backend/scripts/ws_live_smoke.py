"""Smoke: receive at least one live kline from local market-stream."""
from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def main() -> None:
    uri = "ws://127.0.0.1:8000/ws/market?symbol=BTCUSDT&interval=1m"
    async with websockets.connect(uri, open_timeout=20) as ws:
        for _ in range(15):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            print(
                "MSG",
                msg.get("type"),
                msg.get("state"),
                msg.get("close"),
                msg.get("is_closed"),
            )
            if msg.get("type") in ("kline", "snapshot") and msg.get("close") is not None:
                print(
                    "LIVE_OK",
                    msg.get("symbol"),
                    msg.get("interval"),
                    msg.get("close"),
                    msg.get("candle_open_ms"),
                )
                return
    raise SystemExit("no_kline")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
