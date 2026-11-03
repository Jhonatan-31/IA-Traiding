"""Binance public kline hub — one upstream stream fan-out to many browsers."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import websockets

from .normalize import (
    normalize_kline_message,
    should_apply_update,
    stream_name,
    validate_interval,
    validate_symbol,
)

log = logging.getLogger("market_stream.hub")

BINANCE_COMBINED = "wss://stream.binance.com:9443/stream"
MAX_BACKOFF_S = 60.0
STALE_AFTER_S = 15.0
# Binance docs: connections may live up to 24h — renew earlier
RENEW_AFTER_S = 20 * 3600


@dataclass
class ClientSub:
    queue: asyncio.Queue
    symbol: str
    interval: str


@dataclass
class StreamState:
    last_msg: dict[str, Any] | None = None
    last_event_ms: int | None = None
    last_open_ms: int | None = None
    last_recv_mono: float = 0.0
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class MarketHub:
    def __init__(self) -> None:
        self._streams: dict[str, StreamState] = {}
        self._desired: set[str] = set()
        self._lock = asyncio.Lock()
        self._upstream: Any | None = None
        self._runner: asyncio.Task | None = None
        self._started = False
        self.metrics: dict[str, Any] = {
            "upstream_connected": False,
            "reconnects": 0,
            "messages": 0,
            "clients": 0,
            "last_error": None,
            "latency_ms_ewma": None,
        }

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._runner = asyncio.create_task(self._run_upstream_loop(), name="binance-hub")

    async def stop(self) -> None:
        self._started = False
        if self._runner:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
        if self._upstream:
            await self._upstream.close()
            self._upstream = None

    def key(self, symbol: str, interval: str) -> str:
        return stream_name(symbol, interval)

    async def subscribe_client(
        self, queue: asyncio.Queue, symbol: str, interval: str
    ) -> str:
        symbol = validate_symbol(symbol)
        interval = validate_interval(interval)
        k = self.key(symbol, interval)
        async with self._lock:
            st = self._streams.setdefault(k, StreamState())
            st.subscribers.add(queue)
            self._desired.add(k)
            self.metrics["clients"] = sum(len(s.subscribers) for s in self._streams.values())
            if st.last_msg:
                await queue.put({"type": "snapshot", **st.last_msg})
        await self._ensure_resubscribe()
        await queue.put(
            {
                "type": "status",
                "state": "CONNECTED" if self.metrics["upstream_connected"] else "RECONNECTING",
                "symbol": symbol,
                "interval": interval,
                "stream": k,
            }
        )
        return k

    async def unsubscribe_client(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            empty_keys: list[str] = []
            for k, st in self._streams.items():
                if queue in st.subscribers:
                    st.subscribers.discard(queue)
                if not st.subscribers:
                    empty_keys.append(k)
            for k in empty_keys:
                self._streams.pop(k, None)
                self._desired.discard(k)
            self.metrics["clients"] = sum(len(s.subscribers) for s in self._streams.values())
        await self._ensure_resubscribe()

    async def _ensure_resubscribe(self) -> None:
        # Wake upstream loop by closing socket so it reconnects with new streams
        if self._upstream is not None:
            try:
                await self._upstream.close()
            except Exception:
                pass

    def freshness(self, symbol: str, interval: str) -> dict[str, Any]:
        k = self.key(symbol, interval)
        st = self._streams.get(k)
        if not st or not st.last_recv_mono:
            return {"state": "DISCONNECTED", "age_s": None}
        age = time.monotonic() - st.last_recv_mono
        if not self.metrics["upstream_connected"]:
            return {"state": "RECONNECTING", "age_s": age}
        if age > STALE_AFTER_S:
            return {"state": "STALE", "age_s": age}
        return {"state": "CONNECTED", "age_s": age}

    async def _run_upstream_loop(self) -> None:
        backoff = 1.0
        connected_at = 0.0
        while self._started:
            streams = sorted(self._desired)
            if not streams:
                self.metrics["upstream_connected"] = False
                await asyncio.sleep(0.5)
                continue
            # Combined stream URL
            streams_q = "/".join(streams)
            url = f"{BINANCE_COMBINED}?streams={streams_q}"
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_queue=1024,
                    open_timeout=20,
                ) as ws:
                    self._upstream = ws
                    self.metrics["upstream_connected"] = True
                    self.metrics["last_error"] = None
                    connected_at = time.monotonic()
                    backoff = 1.0
                    log.info("upstream connected streams=%s", streams)
                    while self._started:
                        if time.monotonic() - connected_at > RENEW_AFTER_S:
                            log.info("preventive renew after %.0fs", RENEW_AFTER_S)
                            break
                        if set(streams) != self._desired:
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=STALE_AFTER_S + 5)
                        except asyncio.TimeoutError:
                            self.metrics["upstream_connected"] = False
                            log.warning("upstream idle timeout")
                            break
                        await self._handle_raw(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.metrics["last_error"] = f"{type(exc).__name__}:{exc}"
                self.metrics["upstream_connected"] = False
                self.metrics["reconnects"] += 1
                log.warning("upstream error: %s", exc)
            finally:
                self._upstream = None
                self.metrics["upstream_connected"] = False
            jitter = random.uniform(0, backoff * 0.3)
            await asyncio.sleep(backoff + jitter)
            backoff = min(MAX_BACKOFF_S, backoff * 2)

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        msg = normalize_kline_message(payload)
        if not msg:
            return
        k = self.key(msg["symbol"], msg["interval"])
        async with self._lock:
            st = self._streams.get(k)
            if not st:
                return
            if not should_apply_update(st.last_open_ms, st.last_event_ms, msg):
                return
            now = time.monotonic()
            # latency vs event time (best-effort)
            try:
                lat = max(0.0, (time.time() * 1000) - msg["event_time_ms"])
                prev = self.metrics["latency_ms_ewma"]
                self.metrics["latency_ms_ewma"] = (
                    lat if prev is None else (0.8 * float(prev) + 0.2 * lat)
                )
            except Exception:
                pass
            st.last_msg = msg
            st.last_event_ms = msg["event_time_ms"]
            st.last_open_ms = msg["candle_open_ms"]
            st.last_recv_mono = now
            self.metrics["messages"] += 1
            subs = list(st.subscribers)
        for q in subs:
            try:
                q.put_nowait({"type": "kline", **msg})
            except asyncio.QueueFull:
                pass


HUB = MarketHub()
