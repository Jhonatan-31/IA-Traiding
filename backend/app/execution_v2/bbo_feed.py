"""Fetch público bookTicker (data-api.binance.vision) — sin API keys."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .bbo_store import get_registry

PUBLIC_BASE = "https://data-api.binance.vision/api/v3"


async def refresh_book_ticker(
    symbols: list[str] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Actualiza el registro BBO. No escribe ledgers ni lanza órdenes."""
    reg = get_registry()
    own = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        if symbols:
            out_quotes = []
            errors = []
            for sym in symbols:
                url = f"{PUBLIC_BASE}/ticker/bookTicker"
                try:
                    r = await http.get(url, params={"symbol": sym.upper()})
                    if r.status_code != 200:
                        errors.append({"symbol": sym, "status": r.status_code})
                        continue
                    q = reg.upsert_book_ticker(r.json(), received_at_ms=int(time.time() * 1000))
                    if q:
                        out_quotes.append(q.symbol)
                except Exception as exc:
                    errors.append({"symbol": sym, "error": type(exc).__name__})
            return {
                "ok": len(out_quotes) > 0,
                "updated": out_quotes,
                "errors": errors,
                "snapshot": reg.snapshot(),
            }
        # all symbols (paginated payload)
        r = await http.get(f"{PUBLIC_BASE}/ticker/bookTicker")
        if r.status_code != 200:
            reg.mark_disconnected(f"http_{r.status_code}")
            return {"ok": False, "reason": f"http_{r.status_code}", "snapshot": reg.snapshot()}
        data = r.json()
        if not isinstance(data, list):
            reg.mark_disconnected("unexpected_payload")
            return {"ok": False, "reason": "unexpected_payload", "snapshot": reg.snapshot()}
        n = 0
        now = int(time.time() * 1000)
        for row in data:
            if reg.upsert_book_ticker(row, received_at_ms=now):
                n += 1
        return {"ok": True, "updated_n": n, "snapshot": reg.snapshot()}
    except Exception as exc:
        reg.mark_disconnected(type(exc).__name__)
        return {"ok": False, "reason": type(exc).__name__, "snapshot": reg.snapshot()}
    finally:
        if own:
            await http.aclose()
