"""Normalize Binance kline payloads for dashboard consumers."""
from __future__ import annotations

from typing import Any


def validate_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s.endswith("USDT") or len(s) < 6 or len(s) > 20 or not s.isalnum():
        raise ValueError("invalid_symbol")
    return s


def validate_interval(interval: str) -> str:
    from . import ALLOWED_INTERVALS

    iv = (interval or "").strip()
    if iv not in ALLOWED_INTERVALS:
        raise ValueError("invalid_interval")
    return iv


def stream_name(symbol: str, interval: str) -> str:
    return f"{symbol.lower()}@kline_{interval}"


def normalize_kline_message(raw: dict[str, Any], *, source: str = "binance_ws") -> dict[str, Any] | None:
    """
    Accept combined or raw kline event.
    Returns None if not a kline / invalid.
    """
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        return None
    if data.get("e") not in (None, "kline") and "k" not in data:
        # combined wrapper already unwrapped above
        pass
    k = data.get("k")
    if not isinstance(k, dict):
        return None
    try:
        symbol = str(k["s"]).upper()
        interval = str(k["i"])
        open_ms = int(k["t"])
        event_ms = int(data.get("E") or k.get("T") or open_ms)
        return {
            "type": "kline",
            "symbol": symbol,
            "interval": interval,
            "candle_open_ms": open_ms,
            "event_time_ms": event_ms,
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "is_closed": bool(k.get("x")),
            "source": source,
        }
    except (KeyError, TypeError, ValueError):
        return None


def should_apply_update(
    existing_open_ms: int | None,
    existing_event_ms: int | None,
    incoming: dict[str, Any],
) -> bool:
    """Reject stale updates that would overwrite newer candle state."""
    open_ms = int(incoming["candle_open_ms"])
    event_ms = int(incoming["event_time_ms"])
    if existing_open_ms is None:
        return True
    if open_ms > existing_open_ms:
        return True
    if open_ms < existing_open_ms:
        return False
    # same candle: only accept equal or newer event time
    if existing_event_ms is None:
        return True
    return event_ms >= existing_event_ms
