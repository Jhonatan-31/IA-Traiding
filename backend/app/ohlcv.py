"""OHLCV fetch from public Binance with validation and in-memory cache."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

BASE = "https://data-api.binance.vision/api/v3"
ALLOWED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")
MAX_LIMIT = 1000
DEFAULT_LIMIT = 300
CACHE_TTL_SEC = {
    "1m": 15,
    "5m": 30,
    "15m": 45,
    "1h": 60,
    "4h": 120,
    "1d": 300,
}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_stats = {"hits": 0, "misses": 0, "errors": 0}


def cache_stats() -> dict[str, int]:
    return dict(_stats)


def clear_cache() -> None:
    _cache.clear()


def validate_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if not SYMBOL_RE.match(s):
        raise ValueError("invalid symbol")
    return s


def validate_interval(interval: str) -> str:
    i = interval.strip()
    if i not in ALLOWED_INTERVALS:
        raise ValueError(f"interval must be one of {sorted(ALLOWED_INTERVALS)}")
    return i


def validate_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if not isinstance(limit, int):
        raise ValueError("limit must be int")
    if limit < 10 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be between 10 and {MAX_LIMIT}")
    return limit


def _parse_klines(rows: list, now_ms: int) -> list[dict[str, Any]]:
    candles = []
    for r in rows:
        open_time = int(r[0])
        close_time = int(r[6])
        candles.append(
            {
                "open_time": open_time,
                "close_time": close_time,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
                "quote_volume": float(r[7]),
                "is_closed": close_time < now_ms,
            }
        )
    return candles


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    limit: int = DEFAULT_LIMIT,
    use_cache: bool = True,
    end_time: int | None = None,
) -> dict[str, Any]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    limit = validate_limit(limit)
    if end_time is not None:
        end_time = int(end_time)
        if end_time <= 0:
            raise ValueError("end_time must be positive ms")
    # Historical pages (end_time set) skip shared live cache to avoid collisions.
    key = f"{symbol}:{interval}:{limit}:{end_time or 'live'}"
    now = time.time()
    ttl = CACHE_TTL_SEC[interval]
    if use_cache and end_time is None and key in _cache:
        ts, payload = _cache[key]
        if now - ts < ttl:
            _stats["hits"] += 1
            out = dict(payload)
            out["cache"] = "HIT"
            return out

    _stats["misses"] += 1
    try:
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if end_time is not None:
            params["endTime"] = end_time
        r = await client.get(
            BASE + "/klines",
            params=params,
            timeout=25,
        )
        if r.status_code in (418, 429):
            _stats["errors"] += 1
            raise RuntimeError(f"rate_limited:{r.status_code}")
        if r.status_code >= 500:
            _stats["errors"] += 1
            raise RuntimeError(f"upstream:{r.status_code}")
        if r.status_code == 400:
            _stats["errors"] += 1
            raise ValueError("binance rejected symbol/interval")
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list):
            raise RuntimeError("unexpected klines payload")
    except httpx.HTTPError as exc:
        _stats["errors"] += 1
        raise RuntimeError(f"http_error:{type(exc).__name__}") from exc

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candles = _parse_klines(rows, now_ms)
    closed = [c for c in candles if c["is_closed"]]
    forming = next((c for c in reversed(candles) if not c["is_closed"]), None)
    payload = {
        "symbol": symbol,
        "interval": interval,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE,
        "count": len(candles),
        "closed_count": len(closed),
        "forming": forming,
        "candles": candles,
        "cache": "MISS",
        "disclaimer": "Datos públicos de mercado. La vela en formación no debe usarse para señales.",
    }
    if end_time is None:
        _cache[key] = (now, {k: v for k, v in payload.items() if k != "cache"})
    return payload
