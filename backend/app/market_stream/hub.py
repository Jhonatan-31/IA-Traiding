"""Binance public trade+kline hub — fan-out to browsers (visualization only)."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import websockets

from .aggregator import CandleAggregator
from .normalize import (
    normalize_kline_message,
    normalize_trade_message,
    stream_name,
    trade_stream_name,
    validate_interval,
    validate_symbol,
)

log = logging.getLogger("market_stream.hub")

BINANCE_COMBINED = "wss://stream.binance.com:9443/stream"
MAX_BACKOFF_S = 60.0
STALE_AFTER_S = 5.0  # trades are frequent; shorter stale window
RENEW_AFTER_S = 20 * 3600
# Coalesce fan-out to browsers (~1 frame); no 1s artificial delay
COALESCE_MS = 16.0


@dataclass
class ClientSub:
    queue: asyncio.Queue
    symbol: str
    interval: str


@dataclass
class SymbolIntervalState:
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    last_msg: dict[str, Any] | None = None
    last_recv_mono: float = 0.0
    pending: dict[str, Any] | None = None
    flush_task: asyncio.Task | None = None


class MarketHub:
    def __init__(self) -> None:
        # key = "SYMBOL:interval"
        self._si: dict[str, SymbolIntervalState] = {}
        # symbol -> intervals with active clients
        self._symbol_intervals: dict[str, set[str]] = {}
        self._agg = CandleAggregator()
        self._lock = asyncio.Lock()
        self._upstream: Any | None = None
        self._runner: asyncio.Task | None = None
        self._started = False
        self._active_streams: list[str] = []
        self.metrics: dict[str, Any] = {
            "upstream_connected": False,
            "reconnects": 0,
            "messages": 0,
            "trades": 0,
            "klines": 0,
            "ticks_emitted": 0,
            "clients": 0,
            "last_error": None,
            "latency_ms_ewma": None,
            "trade_latency_ms_p50": None,
            "streams": [],
        }
        self._lat_samples: list[float] = []

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

    def _si_key(self, symbol: str, interval: str) -> str:
        return f"{symbol}:{interval}"

    def _desired_streams(self) -> list[str]:
        streams: set[str] = set()
        for symbol, intervals in self._symbol_intervals.items():
            if not intervals:
                continue
            streams.add(trade_stream_name(symbol))
            for iv in intervals:
                streams.add(stream_name(symbol, iv))
        return sorted(streams)

    async def subscribe_client(
        self, queue: asyncio.Queue, symbol: str, interval: str
    ) -> str:
        symbol = validate_symbol(symbol)
        interval = validate_interval(interval)
        k = self._si_key(symbol, interval)
        async with self._lock:
            st = self._si.setdefault(k, SymbolIntervalState())
            st.subscribers.add(queue)
            self._symbol_intervals.setdefault(symbol, set()).add(interval)
            self.metrics["clients"] = sum(len(s.subscribers) for s in self._si.values())
            snap = st.last_msg or (
                self._agg.get(symbol, interval).to_msg()
                if self._agg.get(symbol, interval)
                else None
            )
            if snap:
                await queue.put({"type": "snapshot", **{kk: vv for kk, vv in snap.items() if kk != "type"}})
        await self._ensure_resubscribe()
        await queue.put(
            {
                "type": "status",
                "state": "CONNECTED" if self.metrics["upstream_connected"] else "RECONNECTING",
                "symbol": symbol,
                "interval": interval,
                "streams": self._desired_streams(),
            }
        )
        return k

    async def unsubscribe_client(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            empty: list[str] = []
            for k, st in self._si.items():
                if queue in st.subscribers:
                    st.subscribers.discard(queue)
                if not st.subscribers:
                    empty.append(k)
            for k in empty:
                st = self._si.pop(k)
                if st.flush_task:
                    st.flush_task.cancel()
                symbol, interval = k.split(":", 1)
                ivs = self._symbol_intervals.get(symbol)
                if ivs:
                    ivs.discard(interval)
                    if not ivs:
                        self._symbol_intervals.pop(symbol, None)
            self.metrics["clients"] = sum(len(s.subscribers) for s in self._si.values())
        await self._ensure_resubscribe()

    async def _ensure_resubscribe(self) -> None:
        """Reconnect upstream only when the Binance stream set actually changes."""
        desired = self._desired_streams()
        if desired == self._active_streams and self.metrics["upstream_connected"]:
            return
        if self._upstream is not None:
            try:
                await self._upstream.close()
            except Exception:
                pass

    def freshness(self, symbol: str, interval: str) -> dict[str, Any]:
        k = self._si_key(symbol, interval)
        st = self._si.get(k)
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
            streams = self._desired_streams()
            self.metrics["streams"] = streams
            if not streams:
                self.metrics["upstream_connected"] = False
                await asyncio.sleep(0.5)
                continue
            streams_q = "/".join(streams)
            url = f"{BINANCE_COMBINED}?streams={streams_q}"
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_queue=8192,
                    open_timeout=20,
                ) as ws:
                    self._upstream = ws
                    self.metrics["upstream_connected"] = True
                    self.metrics["last_error"] = None
                    connected_at = time.monotonic()
                    backoff = 1.0
                    self._active_streams = list(streams)
                    log.info("upstream connected streams=%s", streams)
                    while self._started:
                        if time.monotonic() - connected_at > RENEW_AFTER_S:
                            log.info("preventive renew after %.0fs", RENEW_AFTER_S)
                            break
                        if streams != self._desired_streams():
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=STALE_AFTER_S + 8)
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
        hub_recv_ms = int(time.time() * 1000)
        trade = normalize_trade_message(payload)
        if trade:
            await self._on_trade(trade, hub_recv_ms)
            return
        kline = normalize_kline_message(payload)
        if kline:
            await self._on_kline(kline, hub_recv_ms)

    def _record_latency(self, event_ms: int, hub_recv_ms: int) -> None:
        lat = max(0.0, hub_recv_ms - event_ms)
        prev = self.metrics["latency_ms_ewma"]
        self.metrics["latency_ms_ewma"] = lat if prev is None else (0.85 * float(prev) + 0.15 * lat)
        self._lat_samples.append(lat)
        if len(self._lat_samples) > 500:
            self._lat_samples = self._lat_samples[-500:]
        xs = sorted(self._lat_samples)
        mid = xs[len(xs) // 2]
        self.metrics["trade_latency_ms_p50"] = mid

    async def _on_trade(self, trade: dict[str, Any], hub_recv_ms: int) -> None:
        symbol = trade["symbol"]
        self._record_latency(trade["event_time_ms"], hub_recv_ms)
        self.metrics["messages"] += 1
        self.metrics["trades"] += 1
        to_emit: list[tuple[str, str, dict[str, Any]]] = []
        async with self._lock:
            intervals = list(self._symbol_intervals.get(symbol, ()))
            for interval in intervals:
                candle = self._agg.apply_trade(trade, interval)
                if not candle:
                    continue
                msg = candle.to_msg(
                    extra={
                        "hub_recv_ms": hub_recv_ms,
                        "binance_to_hub_ms": hub_recv_ms - trade["event_time_ms"],
                        "trade_price": trade["price"],
                        "trade_qty": trade["qty"],
                    }
                )
                to_emit.append((symbol, interval, msg))
        for symbol, interval, msg in to_emit:
            await self._schedule_emit(symbol, interval, msg)

    async def _on_kline(self, kline: dict[str, Any], hub_recv_ms: int) -> None:
        self.metrics["messages"] += 1
        self.metrics["klines"] += 1
        immediate: dict[str, Any] | None = None
        coalesce: dict[str, Any] | None = None
        symbol = kline["symbol"]
        interval = kline["interval"]
        async with self._lock:
            candle = self._agg.apply_kline(kline)
            if not candle:
                return
            msg = candle.to_msg(
                extra={
                    "hub_recv_ms": hub_recv_ms,
                    "binance_to_hub_ms": hub_recv_ms - kline["event_time_ms"],
                }
            )
            if candle.is_closed:
                immediate = {**msg, "type": "kline"}
            else:
                coalesce = msg
        if immediate:
            await self._emit_now(symbol, interval, immediate)
        elif coalesce:
            await self._schedule_emit(symbol, interval, coalesce)

    async def _schedule_emit(self, symbol: str, interval: str, msg: dict[str, Any]) -> None:
        k = self._si_key(symbol, interval)
        async with self._lock:
            st = self._si.get(k)
            if not st or not st.subscribers:
                return
            st.pending = msg
            st.last_recv_mono = time.monotonic()
            st.last_msg = msg
            if st.flush_task and not st.flush_task.done():
                return

            async def flush() -> None:
                await asyncio.sleep(COALESCE_MS / 1000.0)
                pending = None
                async with self._lock:
                    st2 = self._si.get(k)
                    if not st2 or not st2.pending:
                        return
                    pending = st2.pending
                    st2.pending = None
                    st2.flush_task = None
                if pending:
                    await self._emit_now(symbol, interval, pending)

            st.flush_task = asyncio.create_task(flush())

    async def _emit_now(self, symbol: str, interval: str, msg: dict[str, Any]) -> None:
        k = self._si_key(symbol, interval)
        async with self._lock:
            st = self._si.get(k)
            if not st:
                return
            send_ms = int(time.time() * 1000)
            out = {**msg, "server_send_ms": send_ms}
            st.last_msg = out
            st.last_recv_mono = time.monotonic()
            subs = list(st.subscribers)
            self.metrics["ticks_emitted"] += 1
        for q in subs:
            try:
                q.put_nowait(out)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(out)
                except Exception:
                    pass


HUB = MarketHub()
