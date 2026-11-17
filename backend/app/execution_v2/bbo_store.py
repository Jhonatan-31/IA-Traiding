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
    exchange_ts_ms: int | None = None  # only if stream provides it — never invented
    update_id: int | None = None  # bookTicker REST often lacks u; WS may include
    received_mono_ns: int | None = None
    connection_id: str | None = None

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
            "received_mono_ns": self.received_mono_ns,
            "exchange_ts_ms": self.exchange_ts_ms,
            "exchange_ts_note": (
                None
                if self.exchange_ts_ms is not None
                else "not_provided_by_source_not_invented"
            ),
            "update_id": self.update_id,
            "connection_id": self.connection_id,
            "age_ms": age,
            "stale": age > int(max_age_ms),
            "fresh": age <= int(max_age_ms),
            "source": self.source,
            "book_depth": "top_of_book_only",
            "connection": "ok" if age <= int(max_age_ms) else "stale_or_disconnected",
        }


class BboRegistry:
    """Process-local BBO cache. Never fabricates missing quotes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._quotes: dict[str, BboQuote] = {}
        self._last_error: str | None = None
        self._connected = False
        self._reject_counts: dict[str, int] = {}
        self._accepted = 0
        self._connection_id = f"rest-{int(time.time())}"

    def _reject(self, reason: str) -> None:
        self._last_error = reason
        self._reject_counts[reason] = self._reject_counts.get(reason, 0) + 1

    def upsert_book_ticker(
        self,
        payload: dict[str, Any],
        *,
        received_at_ms: int | None = None,
        connection_id: str | None = None,
        source: str = "binance_bookTicker",
    ) -> BboQuote | None:
        """Accept Binance bookTicker REST/WS payload. Returns None if invalid."""
        try:
            sym = str(payload.get("symbol") or payload.get("s") or "").upper()
            bid = float(payload.get("bidPrice") or payload.get("b") or 0)
            ask = float(payload.get("askPrice") or payload.get("a") or 0)
            bid_q = float(payload.get("bidQty") or payload.get("B") or 0)
            ask_q = float(payload.get("askQty") or payload.get("A") or 0)
        except (TypeError, ValueError):
            self._reject("parse_error")
            return None
        if not sym:
            self._reject("missing_symbol")
            return None
        if bid <= 0 or ask <= 0:
            self._reject("non_positive_price")
            return None
        if bid_q < 0 or ask_q < 0:
            self._reject("negative_qty")
            return None
        if ask < bid:
            self._reject("ask_below_bid")
            return None
        upd = payload.get("u") or payload.get("updateId")
        try:
            update_id = int(upd) if upd is not None else None
        except (TypeError, ValueError):
            update_id = None
        # Do NOT invent exchange event time — bookTicker REST has no E field typically
        ex_ts = payload.get("E") or payload.get("eventTime")
        try:
            exchange_ts_ms = int(ex_ts) if ex_ts is not None else None
        except (TypeError, ValueError):
            exchange_ts_ms = None
        now = int(received_at_ms if received_at_ms is not None else time.time() * 1000)
        q = BboQuote(
            symbol=sym,
            bid_price=bid,
            bid_qty=bid_q,
            ask_price=ask,
            ask_qty=ask_q,
            received_at_ms=now,
            source=source,
            exchange_ts_ms=exchange_ts_ms,
            update_id=update_id,
            received_mono_ns=time.monotonic_ns(),
            connection_id=connection_id or self._connection_id,
        )
        with self._lock:
            prev = self._quotes.get(sym)
            if (
                prev
                and prev.update_id is not None
                and update_id is not None
                and update_id < prev.update_id
            ):
                self._reject("out_of_order_update_id")
                return None
            if (
                prev
                and prev.update_id is not None
                and update_id is not None
                and update_id == prev.update_id
            ):
                self._reject("duplicate_update_id")
                # still refresh age with latest receive — but count duplicate
            self._quotes[sym] = q
            self._connected = True
            self._last_error = None
            self._accepted += 1
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
            stale_n = sum(1 for q in quotes.values() if q.get("stale"))
            return {
                "connected": self._connected,
                "connection_id": self._connection_id,
                "last_error": self._last_error,
                "max_age_ms": max_age_ms,
                "n_symbols": len(quotes),
                "n_accepted": self._accepted,
                "n_stale": stale_n,
                "reject_counts": dict(self._reject_counts),
                "quotes": quotes,
                "sync_state": "top_of_book_cache_not_full_order_book",
                "note": (
                    "Cotizaciones observadas en vivo vía bookTicker público. "
                    "No hay BBO histórico inventado. Stale ≠ usable para fills V2. "
                    "REST y WS no se afirman reconciliables sin update id común."
                ),
            }

    def mark_disconnected(self, reason: str) -> None:
        with self._lock:
            self._connected = False
            self._last_error = reason
            self._reject_counts[reason] = self._reject_counts.get(reason, 0) + 1


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
