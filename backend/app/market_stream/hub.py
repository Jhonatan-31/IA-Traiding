"""Binance public trade+kline hub — shared upstream fan-out (visualization only)."""
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
from .latency import LatencyTracker, mono_delta_ms, wall_delta_ms
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
STALE_AFTER_S = 5.0
RENEW_AFTER_S = 20 * 3600
COALESCE_MS = 16.0
RESUB_DEBOUNCE_S = 0.08


@dataclass
class SymbolIntervalState:
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    last_msg: dict[str, Any] | None = None
    last_recv_mono: float = 0.0
    pending: dict[str, Any] | None = None
    pending_recv_mono: float | None = None
    flush_task: asyncio.Task | None = None


class MarketHub:
    """
    Subscription registry:
      key SYMBOL:interval → N browser queues
      desired Binance streams derived from active keys
      one combined upstream connection fan-out to all clients
    """

    def __init__(self) -> None:
        self._si: dict[str, SymbolIntervalState] = {}
        self._symbol_intervals: dict[str, set[str]] = {}
        self._agg = CandleAggregator()
        self._lock = asyncio.Lock()
        self._upstream: Any | None = None
        self._runner: asyncio.Task | None = None
        self._resub_task: asyncio.Task | None = None
        self._started = False
        self._active_streams: list[str] = []
        self._lat = LatencyTracker()
        self.metrics: dict[str, Any] = {
            "upstream_connected": False,
            "upstream_connections": 0,
            "reconnects": 0,
            "messages": 0,
            "trades": 0,
            "klines": 0,
            "ticks_emitted": 0,
            "clients": 0,
            "subscriptions": {},
            "last_error": None,
            "streams": [],
            "coalesce_ms": COALESCE_MS,
            "latency": {},
        }

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._runner = asyncio.create_task(self._run_upstream_loop(), name="binance-hub")

    async def stop(self) -> None:
        self._started = False
        if self._resub_task:
            self._resub_task.cancel()
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

    def _refresh_subscription_metrics(self) -> None:
        subs = {k: len(st.subscribers) for k, st in self._si.items() if st.subscribers}
        self.metrics["subscriptions"] = subs
        self.metrics["clients"] = sum(subs.values())
        self.metrics["streams"] = self._desired_streams()
        self.metrics["latency"] = self._lat.snapshot()

    async def subscribe_client(
        self, queue: asyncio.Queue, symbol: str, interval: str
    ) -> str:
        symbol = validate_symbol(symbol)
        interval = validate_interval(interval)
        k = self._si_key(symbol, interval)
        snap: dict[str, Any] | None = None
        clients_for_key = 1
        async with self._lock:
            st = self._si.setdefault(k, SymbolIntervalState())
            st.subscribers.add(queue)
            clients_for_key = len(st.subscribers)
            self._symbol_intervals.setdefault(symbol, set()).add(interval)
            self._refresh_subscription_metrics()
            if st.last_msg:
                snap = dict(st.last_msg)
            else:
                candle = self._agg.get(symbol, interval)
                if candle:
                    snap = candle.to_msg()
        if snap:
            body = {kk: vv for kk, vv in snap.items() if kk != "type"}
            await queue.put({"type": "snapshot", **body})
        await self._ensure_resubscribe()
        await queue.put(
            {
                "type": "status",
                "state": "CONNECTED" if self.metrics["upstream_connected"] else "RECONNECTING",
                "symbol": symbol,
                "interval": interval,
                "streams": self._desired_streams(),
                "clients_for_key": clients_for_key,
                "upstream_connections": self.metrics["upstream_connections"],
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
                if st.flush_task and not st.flush_task.done():
                    st.flush_task.cancel()
                symbol, interval = k.split(":", 1)
                ivs = self._symbol_intervals.get(symbol)
                if ivs:
                    ivs.discard(interval)
                    if not ivs:
                        self._symbol_intervals.pop(symbol, None)
            self._refresh_subscription_metrics()
        await self._ensure_resubscribe()

    async def _ensure_resubscribe(self) -> None:
        """Debounced reconnect only when desired Binance streams change."""

        async def debounced() -> None:
            try:
                await asyncio.sleep(RESUB_DEBOUNCE_S)
                desired = self._desired_streams()
                if desired == self._active_streams and self.metrics["upstream_connected"]:
                    return
                if self._upstream is not None:
                    try:
                        await self._upstream.close()
                    except Exception:
                        pass
            except asyncio.CancelledError:
                return

        if self._resub_task and not self._resub_task.done():
            self._resub_task.cancel()
            try:
                await self._resub_task
            except asyncio.CancelledError:
                pass
        self._resub_task = asyncio.create_task(debounced())

    def freshness(self, symbol: str, interval: str) -> dict[str, Any]:
        k = self._si_key(symbol, interval)
        st = self._si.get(k)
        if not st or not st.last_recv_mono:
            return {"state": "DISCONNECTED", "age_s": None, "clients": 0}
        age = time.monotonic() - st.last_recv_mono
        clients = len(st.subscribers)
        if not self.metrics["upstream_connected"]:
            return {"state": "RECONNECTING", "age_s": age, "clients": clients}
        if age > STALE_AFTER_S:
            return {"state": "STALE", "age_s": age, "clients": clients}
        return {"state": "CONNECTED", "age_s": age, "clients": clients}

    def registry_snapshot(self) -> dict[str, Any]:
        return {
            "subscriptions": dict(self.metrics.get("subscriptions") or {}),
            "clients": self.metrics["clients"],
            "upstream_connections": self.metrics["upstream_connections"],
            "upstream_connected": self.metrics["upstream_connected"],
            "streams": list(self.metrics.get("streams") or []),
            "latency": self._lat.snapshot(),
            "coalesce_ms": COALESCE_MS,
        }

    async def _run_upstream_loop(self) -> None:
        backoff = 1.0
        connected_at = 0.0
        while self._started:
            streams = self._desired_streams()
            self.metrics["streams"] = streams
            if not streams:
                self.metrics["upstream_connected"] = False
                self.metrics["upstream_connections"] = 0
                self._active_streams = []
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
                    self.metrics["upstream_connections"] = 1
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
                self.metrics["upstream_connections"] = 0
                self.metrics["reconnects"] += 1
                log.warning("upstream error: %s", exc)
            finally:
                self._upstream = None
                self.metrics["upstream_connected"] = False
                self.metrics["upstream_connections"] = 0
            jitter = random.uniform(0, backoff * 0.3)
            await asyncio.sleep(backoff + jitter)
            backoff = min(MAX_BACKOFF_S, backoff * 2)

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        hub_recv_ms = int(time.time() * 1000)
        hub_recv_mono = time.monotonic()
        trade = normalize_trade_message(payload)
        if trade:
            await self._on_trade(trade, hub_recv_ms, hub_recv_mono)
            return
        kline = normalize_kline_message(payload)
        if kline:
            await self._on_kline(kline, hub_recv_ms, hub_recv_mono)

    async def _on_trade(
        self, trade: dict[str, Any], hub_recv_ms: int, hub_recv_mono: float
    ) -> None:
        symbol = trade["symbol"]
        b2h = wall_delta_ms(hub_recv_ms, trade["event_time_ms"])
        self._lat.push_binance_to_hub(b2h)
        self.metrics["messages"] += 1
        self.metrics["trades"] += 1
        to_emit: list[tuple[str, str, dict[str, Any], float]] = []
        async with self._lock:
            intervals = list(self._symbol_intervals.get(symbol, ()))
            for interval in intervals:
                candle = self._agg.apply_trade(trade, interval)
                if not candle:
                    continue
                msg = candle.to_msg(
                    extra={
                        "hub_recv_ms": hub_recv_ms,
                        "binance_to_hub_ms": b2h,
                        "trade_price": trade["price"],
                        "trade_qty": trade["qty"],
                    }
                )
                to_emit.append((symbol, interval, msg, hub_recv_mono))
            self.metrics["latency"] = self._lat.snapshot()
        for symbol, interval, msg, recv_mono in to_emit:
            await self._schedule_emit(symbol, interval, msg, recv_mono)

    async def _on_kline(
        self, kline: dict[str, Any], hub_recv_ms: int, hub_recv_mono: float
    ) -> None:
        self.metrics["messages"] += 1
        self.metrics["klines"] += 1
        b2h = wall_delta_ms(hub_recv_ms, kline["event_time_ms"])
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
                    "binance_to_hub_ms": b2h,
                }
            )
            if candle.is_closed:
                immediate = {**msg, "type": "kline"}
            else:
                coalesce = msg
        if immediate:
            await self._emit_now(symbol, interval, immediate, hub_recv_mono)
        elif coalesce:
            await self._schedule_emit(symbol, interval, coalesce, hub_recv_mono)

    async def _schedule_emit(
        self,
        symbol: str,
        interval: str,
        msg: dict[str, Any],
        hub_recv_mono: float,
    ) -> None:
        k = self._si_key(symbol, interval)
        async with self._lock:
            st = self._si.get(k)
            if not st or not st.subscribers:
                return
            st.pending = msg
            st.pending_recv_mono = hub_recv_mono
            st.last_recv_mono = time.monotonic()
            st.last_msg = msg
            if st.flush_task and not st.flush_task.done():
                return

            async def flush() -> None:
                await asyncio.sleep(COALESCE_MS / 1000.0)
                pending = None
                recv_mono = hub_recv_mono
                async with self._lock:
                    st2 = self._si.get(k)
                    if not st2 or not st2.pending:
                        return
                    pending = st2.pending
                    recv_mono = st2.pending_recv_mono or hub_recv_mono
                    st2.pending = None
                    st2.pending_recv_mono = None
                    st2.flush_task = None
                if pending:
                    await self._emit_now(symbol, interval, pending, recv_mono)

            st.flush_task = asyncio.create_task(flush())

    async def _emit_now(
        self,
        symbol: str,
        interval: str,
        msg: dict[str, Any],
        hub_recv_mono: float,
    ) -> None:
        k = self._si_key(symbol, interval)
        async with self._lock:
            st = self._si.get(k)
            if not st:
                return
            send_ms = int(time.time() * 1000)
            send_mono = time.monotonic()
            internal = mono_delta_ms(send_mono, hub_recv_mono)
            self._lat.push_hub_internal(internal)
            out = {
                **msg,
                "server_send_ms": send_ms,
                "hub_internal_ms": internal,
            }
            st.last_msg = out
            st.last_recv_mono = send_mono
            subs = list(st.subscribers)
            self.metrics["ticks_emitted"] += 1
            self.metrics["latency"] = self._lat.snapshot()
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
