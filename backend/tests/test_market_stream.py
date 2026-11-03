"""Market-stream normalization & stale-guard — no real orders."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.market_stream.normalize import (
    normalize_kline_message,
    should_apply_update,
    stream_name,
    validate_interval,
    validate_symbol,
)


def test_validate_symbol_and_interval():
    assert validate_symbol("btcusdt") == "BTCUSDT"
    assert validate_interval("1m") == "1m"
    with pytest.raises(ValueError):
        validate_symbol("BTC")
    with pytest.raises(ValueError):
        validate_interval("2m")


def test_stream_name():
    assert stream_name("BTCUSDT", "1m") == "btcusdt@kline_1m"


def test_normalize_combined_kline():
    raw = {
        "stream": "btcusdt@kline_1m",
        "data": {
            "e": "kline",
            "E": 1_700_000_000_100,
            "k": {
                "t": 1_700_000_000_000,
                "T": 1_700_000_059_999,
                "s": "BTCUSDT",
                "i": "1m",
                "o": "100",
                "h": "110",
                "l": "90",
                "c": "105",
                "v": "12.5",
                "x": False,
            },
        },
    }
    msg = normalize_kline_message(raw)
    assert msg is not None
    assert msg["symbol"] == "BTCUSDT"
    assert msg["interval"] == "1m"
    assert msg["candle_open_ms"] == 1_700_000_000_000
    assert msg["close"] == 105.0
    assert msg["is_closed"] is False
    assert msg["source"] == "binance_ws"


def test_reject_stale_and_accept_newer_same_candle():
    base = {
        "candle_open_ms": 1000,
        "event_time_ms": 1100,
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "volume": 1,
        "is_closed": False,
        "symbol": "BTCUSDT",
        "interval": "1m",
        "source": "t",
    }
    assert should_apply_update(None, None, base)
    assert not should_apply_update(2000, 2000, base)  # older open
    assert not should_apply_update(1000, 1200, {**base, "event_time_ms": 1100})
    assert should_apply_update(1000, 1100, {**base, "event_time_ms": 1150})
    assert should_apply_update(1000, 1100, {**base, "candle_open_ms": 2000, "event_time_ms": 2001})


def test_duplicate_open_same_event_allowed():
    msg = {
        "candle_open_ms": 1000,
        "event_time_ms": 1100,
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 1.5,
        "volume": 1,
        "is_closed": False,
        "symbol": "BTCUSDT",
        "interval": "1m",
        "source": "t",
    }
    assert should_apply_update(1000, 1100, msg)  # equal event ok (idempotent refresh)


def test_no_private_trading_in_market_stream():
    root = Path(__file__).resolve().parents[1] / "app" / "market_stream"
    for p in root.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "api/v3/order" not in text
        assert "API_SECRET" not in text
        assert "BINANCE_API_KEY" not in text
