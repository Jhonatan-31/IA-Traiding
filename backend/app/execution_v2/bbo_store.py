"""Registro verificable de best bid/ask (bookTicker público). Sin inventar histórico."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class BboQuote:
    symbol: str
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    received_at_ms: int
    source: str = "binance_bookTicker"
    exchange_ts_ms: int | None = None

    @property
    def spread_abs(self) -> float:
        return float(self.ask_price - self.bid_price)

    @property
    def spread_rel(self) -> float:
        mid = (self.bid_price + self.ask_price) / 2.0
        if mid <= 0:
            return float("nan")
        return self.spread_abs / mid

    @property
    def mid(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0

    def age_ms(self, now_ms: int | None = None) -> int:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        return max(0, now - int(self.received_at_ms))

    def is_stale(self, max_age_ms: int, now_ms: int | None = None) -> bool:
        return self.age_ms(now_ms) > int(max_age_ms)

    def to_public_dict(self, *, now_ms: int | None = None, max_age_ms: int = 5000) -> dict[str, Any]:
        age = self.age_ms(now_ms)
        return {
            "symbol": self.symbol,
            "bid_price": self.bid_price,
            "bid_qty": self.bid_qty,
            "ask_price": self.ask_price,
            "ask_qty": self.ask_qty,
            "spread_abs": self.spread_abs,
            "spread_rel": self.spread_rel,
            "mid": self.mid,
            "received_at_ms": self.received_at_ms,
            "exchange_ts_ms": self.exchange_ts_ms,
            "age_ms": age,
            "stale": age > int(max_age_ms),
            "source": self.source,
            "connection": "ok" if age <= int(max_age_ms) else "stale_or_disconnected",
        }


class BboRegistry:
    """Process-local BBO cache. Never fabricates missing quotes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._quotes: dict[str, BboQuote] = {}
        self._last_error: str | None = None
        self._connected = False

    def upsert_book_ticker(self, payload: dict[str, Any], *, received_at_ms: int | None = None) -> BboQuote | None:
        """Accept Binance bookTicker REST/WS payload. Returns None if invalid."""
        try:
            sym = str(payload.get("symbol") or payload.get("s") or "").upper()
            bid = float(payload.get("bidPrice") or payload.get("b") or 0)
            ask = float(payload.get("askPrice") or payload.get("a") or 0)
            bid_q = float(payload.get("bidQty") or payload.get("B") or 0)
            ask_q = float(payload.get("askQty") or payload.get("A") or 0)
        except (TypeError, ValueError):
            self._last_error = "parse_error"
            return None
        if not sym or bid <= 0 or ask <= 0 or ask < bid:
            self._last_error = "invalid_bbo"
            return None
        now = int(received_at_ms if received_at_ms is not None else time.time() * 1000)
        q = BboQuote(
            symbol=sym,
            bid_price=bid,
            bid_qty=bid_q,
            ask_price=ask,
            ask_qty=ask_q,
            received_at_ms=now,
            source="binance_bookTicker",
        )
        with self._lock:
            self._quotes[sym] = q
            self._connected = True
            self._last_error = None
        return q

    def get(self, symbol: str) -> BboQuote | None:
        with self._lock:
            return self._quotes.get(symbol.upper())

    def snapshot(self, *, max_age_ms: int = 5000) -> dict[str, Any]:
        now = int(time.time() * 1000)
        with self._lock:
            quotes = {
                s: q.to_public_dict(now_ms=now, max_age_ms=max_age_ms) for s, q in self._quotes.items()
            }
            return {
                "connected": self._connected,
                "last_error": self._last_error,
                "max_age_ms": max_age_ms,
                "n_symbols": len(quotes),
                "quotes": quotes,
                "note": (
                    "Cotizaciones observadas en vivo vía bookTicker público. "
                    "No hay BBO histórico inventado. Stale ≠ usable para fills V2."
                ),
            }

    def mark_disconnected(self, reason: str) -> None:
        with self._lock:
            self._connected = False
            self._last_error = reason


_REGISTRY: BboRegistry | None = None
_REG_LOCK = threading.Lock()


def get_registry() -> BboRegistry:
    global _REGISTRY
    with _REG_LOCK:
        if _REGISTRY is None:
            _REGISTRY = BboRegistry()
        return _REGISTRY


def quote_to_dict(q: BboQuote) -> dict[str, Any]:
    return asdict(q)
