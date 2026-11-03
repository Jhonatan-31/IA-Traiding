"""Shared subscription registry + latency helpers (no real Binance orders)."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.market_stream.hub import COALESCE_MS, MarketHub
from app.market_stream.latency import (
    LatencyTracker,
    mono_delta_ms,
    percentile,
    wall_delta_ms,
)


def test_percentile_and_negatives():
    assert percentile([], 50) is None
    assert percentile([10.0], 95) == 10.0
    xs = [1, 2, 3, 4, 100]
    assert percentile(xs, 50) == 3
    assert wall_delta_ms(100, 120) is None
    assert wall_delta_ms(120, 100) == 20
    assert mono_delta_ms(1.02, 1.0) == pytest.approx(20.0)
    assert mono_delta_ms(1.0, 1.1) is None


def test_latency_tracker_discards_negatives():
    t = LatencyTracker(maxlen=10)
    t.push_binance_to_hub(None)
    t.push_binance_to_hub(50)
    t.push_hub_internal(16)
    snap = t.snapshot()
    assert snap["negatives_discarded"] == 1
    assert snap["binance_to_hub_ms"]["n"] == 1
    assert snap["hub_internal_ms"]["p50"] == 16


@pytest.mark.asyncio
async def test_two_clients_same_symbol_share_registry():
    hub = MarketHub()
    q1: asyncio.Queue = asyncio.Queue(maxsize=32)
    q2: asyncio.Queue = asyncio.Queue(maxsize=32)
    await hub.subscribe_client(q1, "BTCUSDT", "1m")
    await hub.subscribe_client(q2, "BTCUSDT", "1m")
    reg = hub.registry_snapshot()
    assert reg["clients"] == 2
    assert reg["subscriptions"].get("BTCUSDT:1m") == 2
    streams = set(hub._desired_streams())
    assert "btcusdt@trade" in streams
    assert "btcusdt@kline_1m" in streams
    # drain status/snapshot noise
    while not q1.empty():
        q1.get_nowait()
    while not q2.empty():
        q2.get_nowait()
    # fan-out emit
    await hub._emit_now(
        "BTCUSDT",
        "1m",
        {
            "type": "candle_tick",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "candle_open_ms": 1,
            "event_time_ms": 2,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "is_closed": False,
            "source": "test",
        },
        hub_recv_mono=time.monotonic(),
    )
    m1 = await asyncio.wait_for(q1.get(), timeout=1)
    m2 = await asyncio.wait_for(q2.get(), timeout=1)
    assert m1["type"] == "candle_tick" and m2["type"] == "candle_tick"
    assert "hub_internal_ms" in m1
    await hub.unsubscribe_client(q1)
    assert hub.registry_snapshot()["subscriptions"].get("BTCUSDT:1m") == 1
    await hub.unsubscribe_client(q2)
    assert hub.registry_snapshot()["clients"] == 0
    assert hub._desired_streams() == []


@pytest.mark.asyncio
async def test_rapid_symbol_switch_cleans_desired():
    hub = MarketHub()
    q: asyncio.Queue = asyncio.Queue(maxsize=16)
    await hub.subscribe_client(q, "BTCUSDT", "1m")
    await hub.unsubscribe_client(q)
    await hub.subscribe_client(q, "ETHUSDT", "5m")
    streams = hub._desired_streams()
    assert "ethusdt@trade" in streams
    assert "ethusdt@kline_5m" in streams
    assert "btcusdt@trade" not in streams
    await hub.unsubscribe_client(q)
    assert hub._desired_streams() == []


@pytest.mark.asyncio
async def test_coalesce_emits_latest_only():
    hub = MarketHub()
    q: asyncio.Queue = asyncio.Queue(maxsize=32)
    await hub.subscribe_client(q, "BTCUSDT", "1m")
    while not q.empty():
        q.get_nowait()
    mono = time.monotonic()
    await hub._schedule_emit(
        "BTCUSDT",
        "1m",
        {
            "type": "candle_tick",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "candle_open_ms": 1,
            "event_time_ms": 1,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "is_closed": False,
            "source": "a",
        },
        mono,
    )
    await hub._schedule_emit(
        "BTCUSDT",
        "1m",
        {
            "type": "candle_tick",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "candle_open_ms": 1,
            "event_time_ms": 2,
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
            "volume": 2,
            "is_closed": False,
            "source": "b",
        },
        mono,
    )
    await asyncio.sleep(COALESCE_MS / 1000.0 + 0.05)
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    ticks = [m for m in msgs if m.get("type") == "candle_tick"]
    assert len(ticks) == 1
    assert ticks[0]["close"] == 2
    await hub.unsubscribe_client(q)
