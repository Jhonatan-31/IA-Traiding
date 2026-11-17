"""Captura experimental acotada de bookTicker (manual). No servicio 24/7.

Estimación: ~1 evento REST/poll/símbolo → bytes pequeños; retención explícita.
No inventa histórico previo al start_ms real.
AM: límites autorizados máx. 30 min / 100 MB / 250k eventos; stop al primer límite.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .bbo_feed import PUBLIC_BASE, refresh_book_ticker
from .bbo_store import get_registry

DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
PARSER_VERSION = "am_bbo_jsonl_v1"

# Absolute authorized ceilings (AM2) — never auto-expand
AM_MAX_SECONDS = 1800.0
AM_MAX_BYTES = 100 * 1024 * 1024
AM_MAX_EVENTS = 250_000

_CAPTURE_LOCK = threading.Lock()
_CAPTURE_ACTIVE = False


@dataclass
class CapturePlan:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    poll_interval_s: float = 1.0
    max_seconds: float = 30.0
    max_events: int = 120
    max_bytes: int = 2_000_000
    retention_note: str = "manual_ephemeral_or_explicit_path"
    experiment_id: str | None = None
    commit: str | None = None
    authorized: bool = False


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
    n_invalid: int = 0
    bytes_written: int = 0
    path: str | None = None
    manifest_path: str | None = None
    errors: list[str] = field(default_factory=list)
    events_sample: list[dict[str, Any]] = field(default_factory=list)
    permanent_service: bool = False
    stop_reason: str | None = None
    experiment_id: str | None = None
    parser_version: str = PARSER_VERSION
    note: str = "Bounded manual capture only; not 24/7 depth recorder."


def am_authorized_plan(
    *,
    max_seconds: float = 600.0,
    poll_interval_s: float = 2.0,
    commit: str | None = None,
    experiment_id: str | None = None,
) -> CapturePlan:
    """Plan AM: clamps to authorized ceilings; default reduced for Wi‑Fi risk."""
    sec = min(float(max_seconds), AM_MAX_SECONDS)
    # events ceiling from time*symbols/poll, then clamp
    est_events = int(sec / max(poll_interval_s, 0.1)) * len(DEFAULT_SYMBOLS) + 10
    return CapturePlan(
        symbols=DEFAULT_SYMBOLS,
        poll_interval_s=float(poll_interval_s),
        max_seconds=sec,
        max_events=min(est_events, AM_MAX_EVENTS),
        max_bytes=min(AM_MAX_BYTES, 50 * 1024 * 1024),  # practical 50MB < 100MB cap
        retention_note="etapa_am_experimental_dataset",
        experiment_id=experiment_id or f"AM-BBO-{int(time.time())}",
        commit=commit or os.environ.get("DEPLOY_GIT_COMMIT"),
        authorized=True,
    )


def estimate_disk_usage(plan: CapturePlan) -> dict[str, Any]:
    events = min(
        plan.max_events,
        int(plan.max_seconds / max(plan.poll_interval_s, 0.1)) * len(plan.symbols),
    )
    est = events * 400
    return {
        "symbols": list(plan.symbols),
        "estimated_events": events,
        "estimated_bytes": est,
        "max_bytes_cap": plan.max_bytes,
        "within_cap": est <= plan.max_bytes,
        "retention": plan.retention_note,
        "authorization_required_for_24_7": True,
        "am_ceilings": {
            "max_seconds": AM_MAX_SECONDS,
            "max_bytes": AM_MAX_BYTES,
            "max_events": AM_MAX_EVENTS,
        },
    }


def capture_is_active() -> bool:
    return _CAPTURE_ACTIVE


async def run_bounded_capture(
    plan: CapturePlan | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    global _CAPTURE_ACTIVE
    plan = plan or CapturePlan()
    # Clamp hard ceilings even if caller passes larger values
    plan.max_seconds = min(float(plan.max_seconds), AM_MAX_SECONDS)
    plan.max_events = min(int(plan.max_events), AM_MAX_EVENTS)
    plan.max_bytes = min(int(plan.max_bytes), AM_MAX_BYTES)

    if not _CAPTURE_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "reason": "capture_already_active",
            "permanent_service": False,
        }
    _CAPTURE_ACTIVE = True
    try:
        return await _run_capture_body(plan, out_dir=out_dir)
    finally:
        _CAPTURE_ACTIVE = False
        _CAPTURE_LOCK.release()


async def _run_capture_body(plan: CapturePlan, *, out_dir: Path | None) -> dict[str, Any]:
    started = int(time.time() * 1000)
    reg = get_registry()
    events_sample: list[dict[str, Any]] = []
    errors: list[str] = []
    duplicates = 0
    invalid = 0
    n_events = 0
    nbytes = 0
    last_upd: dict[str, int] = {}
    stop_reason = "completed_time"
    path = None
    manifest_path = None
    fh = None
    path_obj = None

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path_obj = out_dir / f"bbo_capture_{started}.jsonl"
        fh = path_obj.open("w", encoding="utf-8")
        path = str(path_obj)

    deadline = time.time() + plan.max_seconds
    polls = 0
    try:
        while True:
            if time.time() >= deadline:
                stop_reason = "max_seconds"
                break
            if n_events >= plan.max_events:
                stop_reason = "max_events"
                break
            if nbytes >= plan.max_bytes:
                stop_reason = "max_bytes"
                break

            res = await refresh_book_ticker(list(plan.symbols))
            if not res.get("ok"):
                errors.append(str(res.get("reason") or "refresh_failed"))
            snap = reg.snapshot()
            for sym, q in (snap.get("quotes") or {}).items():
                if sym.upper() not in {s.upper() for s in plan.symbols}:
                    invalid += 1
                    continue
                uid = q.get("update_id")
                if uid is not None and last_upd.get(sym) == uid:
                    duplicates += 1
                if uid is not None:
                    last_upd[sym] = int(uid)
                ev = {
                    "captured_at_ms": int(time.time() * 1000),
                    "experiment_id": plan.experiment_id,
                    "parser_version": PARSER_VERSION,
                    "sync_state": snap.get("sync_state"),
                    **q,
                }
                # never invent exchange_ts
                if ev.get("exchange_ts_ms") is None:
                    ev["exchange_ts_note"] = "not_provided_by_source_not_invented"
                line = json.dumps(ev, ensure_ascii=False)
                line_bytes = len(line) + 1
                if nbytes + line_bytes > plan.max_bytes:
                    stop_reason = "max_bytes"
                    errors.append("max_bytes_reached")
                    break
                if fh is not None:
                    fh.write(line + "\n")
                    fh.flush()
                nbytes += line_bytes
                n_events += 1
                if len(events_sample) < 5:
                    events_sample.append(ev)
                if n_events >= plan.max_events:
                    stop_reason = "max_events"
                    break
            if stop_reason in ("max_bytes", "max_events"):
                break
            polls += 1
            await _sleep(plan.poll_interval_s)
    finally:
        if fh is not None:
            fh.close()

    ended = int(time.time() * 1000)
    expected = max(1, int(plan.max_seconds / plan.poll_interval_s)) * len(plan.symbols)
    gaps = max(0, expected - n_events)

    manifest = {
        "experiment_id": plan.experiment_id,
        "started_at_ms": started,
        "ended_at_ms": ended,
        "duration_ms": ended - started,
        "symbols": list(plan.symbols),
        "commit": plan.commit,
        "parser_version": PARSER_VERSION,
        "limits": {
            "max_seconds": plan.max_seconds,
            "max_events": plan.max_events,
            "max_bytes": plan.max_bytes,
            "poll_interval_s": plan.poll_interval_s,
        },
        "n_events": n_events,
        "n_duplicates": duplicates,
        "n_invalid": invalid,
        "n_gaps_heuristic": gaps,
        "n_errors": len(errors),
        "bytes_written": nbytes,
        "stop_reason": stop_reason,
        "authorized": plan.authorized,
        "permanent_service": False,
        "path": path,
        "polls": polls,
    }
    if out_dir is not None and path_obj is not None:
        man = path_obj.with_suffix(".manifest.json")
        man.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest_path = str(man)

    result = CaptureResult(
        ok=n_events > 0,
        started_at_ms=started,
        ended_at_ms=ended,
        symbols=list(plan.symbols),
        n_events=n_events,
        n_duplicates=duplicates,
        n_gaps=gaps,
        n_errors=len(errors),
        n_invalid=invalid,
        bytes_written=nbytes,
        path=path,
        manifest_path=manifest_path,
        errors=errors[:20],
        events_sample=events_sample,
        stop_reason=stop_reason,
        experiment_id=plan.experiment_id,
    )
    out = asdict(result)
    out["manifest"] = manifest
    return out


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def public_book_ticker_once(symbol: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(
            f"{PUBLIC_BASE}/ticker/bookTicker", params={"symbol": symbol.upper()}
        )
        return {"status": r.status_code, "body": r.json() if r.status_code == 200 else None}
