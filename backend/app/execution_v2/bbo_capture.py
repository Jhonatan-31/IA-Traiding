"""Captura experimental acotada de bookTicker (manual). No servicio 24/7.

Estimación: ~1 evento REST/poll/símbolo → bytes pequeños; retención explícita.
No inventa histórico previo al start_ms real.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .bbo_feed import PUBLIC_BASE, refresh_book_ticker
from .bbo_store import get_registry

DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


@dataclass
class CapturePlan:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    poll_interval_s: float = 1.0
    max_seconds: float = 30.0
    max_events: int = 120
    max_bytes: int = 2_000_000
    retention_note: str = "manual_ephemeral_or_explicit_path"


@dataclass
class CaptureResult:
    ok: bool
    started_at_ms: int
    ended_at_ms: int
    symbols: list[str]
    n_events: int = 0
    n_duplicates: int = 0
    n_gaps: int = 0
    n_errors: int = 0
    bytes_written: int = 0
    path: str | None = None
    errors: list[str] = field(default_factory=list)
    events_sample: list[dict[str, Any]] = field(default_factory=list)
    permanent_service: bool = False
    note: str = "Bounded manual capture only; not 24/7 depth recorder."


def estimate_disk_usage(plan: CapturePlan) -> dict[str, Any]:
    # ~400 bytes JSON/event rough
    events = min(plan.max_events, int(plan.max_seconds / max(plan.poll_interval_s, 0.1)) * len(plan.symbols))
    est = events * 400
    return {
        "symbols": list(plan.symbols),
        "estimated_events": events,
        "estimated_bytes": est,
        "max_bytes_cap": plan.max_bytes,
        "within_cap": est <= plan.max_bytes,
        "retention": plan.retention_note,
        "authorization_required_for_24_7": True,
    }


async def run_bounded_capture(
    plan: CapturePlan | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    plan = plan or CapturePlan()
    started = int(time.time() * 1000)
    reg = get_registry()
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    duplicates = 0
    last_upd: dict[str, int] = {}
    deadline = time.time() + plan.max_seconds
    while time.time() < deadline and len(events) < plan.max_events:
        res = await refresh_book_ticker(list(plan.symbols))
        if not res.get("ok"):
            errors.append(str(res.get("reason") or "refresh_failed"))
        snap = reg.snapshot()
        for sym, q in (snap.get("quotes") or {}).items():
            uid = q.get("update_id")
            if uid is not None and last_upd.get(sym) == uid:
                duplicates += 1
            if uid is not None:
                last_upd[sym] = int(uid)
            events.append({"captured_at_ms": int(time.time() * 1000), **q})
        await _sleep(plan.poll_interval_s)

    ended = int(time.time() * 1000)
    path = None
    nbytes = 0
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path_obj = out_dir / f"bbo_capture_{started}.jsonl"
        with path_obj.open("w", encoding="utf-8") as f:
            for ev in events:
                line = json.dumps(ev, ensure_ascii=False)
                f.write(line + "\n")
                nbytes += len(line) + 1
                if nbytes >= plan.max_bytes:
                    errors.append("max_bytes_reached")
                    break
        path = str(path_obj)

    # gaps: simple heuristic — expected polls vs events/symbols
    expected = max(1, int(plan.max_seconds / plan.poll_interval_s)) * len(plan.symbols)
    gaps = max(0, expected - len(events))

    result = CaptureResult(
        ok=len(events) > 0,
        started_at_ms=started,
        ended_at_ms=ended,
        symbols=list(plan.symbols),
        n_events=len(events),
        n_duplicates=duplicates,
        n_gaps=gaps,
        n_errors=len(errors),
        bytes_written=nbytes,
        path=path,
        errors=errors[:20],
        events_sample=events[:5],
    )
    return asdict(result)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def public_book_ticker_once(symbol: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(f"{PUBLIC_BASE}/ticker/bookTicker", params={"symbol": symbol.upper()})
        return {"status": r.status_code, "body": r.json() if r.status_code == 200 else None}
