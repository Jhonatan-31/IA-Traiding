"""Measure Binance trade vs kline cadence (public streams only)."""
from __future__ import annotations

import asyncio
import json
import time

import websockets


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round((p / 100) * (len(xs) - 1)))))
    return xs[i]


def gaps(items: list[dict]) -> list[float]:
    if len(items) < 2:
        return []
    return [items[i]["recv"] - items[i - 1]["recv"] for i in range(1, len(items))]


async def measure(window_s: float = 12.0) -> dict:
    url = "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@kline_1m"
    trades: list[dict] = []
    klines: list[dict] = []
    t0 = time.time()
    async with websockets.connect(url, ping_interval=20, open_timeout=20) as ws:
        while time.time() - t0 < window_s:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            now_ms = time.time() * 1000
            msg = json.loads(raw)
            data = msg.get("data") or msg
            stream = msg.get("stream", "")
            if "trade" in stream or data.get("e") == "trade":
                e = int(data["E"])
                T = int(data["T"])
                trades.append(
                    {
                        "recv": now_ms,
                        "E": e,
                        "T": T,
                        "recv_E": now_ms - e,
                        "p": data["p"],
                    }
                )
            elif "kline" in stream or data.get("e") == "kline":
                e = int(data["E"])
                k = data["k"]
                klines.append(
                    {
                        "recv": now_ms,
                        "E": e,
                        "recv_E": now_ms - e,
                        "c": k["c"],
                        "x": k["x"],
                    }
                )
    tr_lat = [t["recv_E"] for t in trades]
    kl_lat = [k["recv_E"] for k in klines]
    tg, kg = gaps(trades), gaps(klines)
    return {
        "window_s": window_s,
        "trade_count": len(trades),
        "kline_count": len(klines),
        "trade_interarrival_ms_p50": pct(tg, 50),
        "trade_interarrival_ms_p95": pct(tg, 95),
        "kline_interarrival_ms_p50": pct(kg, 50),
        "kline_interarrival_ms_p95": pct(kg, 95),
        "trade_recv_minus_E_p50": pct(tr_lat, 50),
        "trade_recv_minus_E_p95": pct(tr_lat, 95),
        "trade_recv_minus_E_p99": pct(tr_lat, 99),
        "kline_recv_minus_E_p50": pct(kl_lat, 50),
        "kline_recv_minus_E_p95": pct(kl_lat, 95),
        "note": "recv-E includes clock skew; not pure network RTT. Kline updates ~1-2s, not 60s.",
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(measure()), indent=2))
