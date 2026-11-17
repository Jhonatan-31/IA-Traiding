"""AN4/AN5 — captura experimental bookTicker WebSocket (público, one-shot).

No es order book L2. No autostart. No modifica market-stream hub permanente.
Binance combined: wss://stream.binance.com:9443/stream?streams=btcusdt@bookTicker/...
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PARSER_VERSION = "an_bbo_ws_v1"
WS_BASE = "wss://stream.binance.com:9443/stream"

# Authorized ceilings AN5
AN_MAX_SECONDS = 600.0
AN_MAX_BYTES = 25 * 1024 * 1024
AN_MAX_EVENTS = 30_000


@dataclass
class WsCapturePlan:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    max_seconds: float = 180.0
    max_events: int = 15_000
    max_bytes: int = 10 * 1024 * 1024
    experiment_id: str | None = None
    commit: str | None = None


@dataclass
class WsCaptureResult:
    ok: bool
    source: str = "websocket_bookTicker"
    started_at_ms: int = 0
    ended_at_ms: int = 0
    n_events: int = 0
    n_duplicates: int = 0
    n_reconnects: int = 0
    n_errors: int = 0
    bytes_written: int = 0
    stop_reason: str | None = None
    path: str | None = None
    manifest_path: str | None = None
    errors: list[str] = field(default_factory=list)
    permanent_service: bool = False
    note: str = "bookTicker push ≠ synchronized L2 depth"


def _stream_url(symbols: tuple[str, ...]) -> str:
    parts = [f"{s.lower()}@bookTicker" for s in symbols]
    return f"{WS_BASE}?streams={'/'.join(parts)}"


async def run_ws_book_ticker_capture(
    plan: WsCapturePlan | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    import websockets

    plan = plan or WsCapturePlan()
    plan.max_seconds = min(float(plan.max_seconds), AN_MAX_SECONDS)
    plan.max_events = min(int(plan.max_events), AN_MAX_EVENTS)
    plan.max_bytes = min(int(plan.max_bytes), AN_MAX_BYTES)
    started = int(time.time() * 1000)
    exp_id = plan.experiment_id or f"AN-WS-{started}"
    connection_id = f"ws-{started}"
    n_events = 0
    n_dup = 0
    n_err = 0
    n_reconn = 0
    nbytes = 0
    errors: list[str] = []
    last_u: dict[str, int] = {}
    stop_reason = "completed_time"
    path = None
    manifest_path = None
    fh = None
    deadline = time.time() + plan.max_seconds
    url = _stream_url(plan.symbols)

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path_obj = out_dir / f"bbo_ws_{started}.jsonl"
        fh = path_obj.open("w", encoding="utf-8")
        path = str(path_obj)

    try:
        while time.time() < deadline and n_events < plan.max_events and nbytes < plan.max_bytes:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    while time.time() < deadline and n_events < plan.max_events:
                        if nbytes >= plan.max_bytes:
                            stop_reason = "max_bytes"
                            break
                        timeout = max(0.1, deadline - time.time())
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            stop_reason = "max_seconds"
                            break
                        recv_ms = int(time.time() * 1000)
                        mono = time.monotonic_ns()
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            n_err += 1
                            errors.append("json_decode")
                            continue
                        data = msg.get("data") if isinstance(msg, dict) and "data" in msg else msg
                        if not isinstance(data, dict):
                            n_err += 1
                            continue
                        sym = str(data.get("s") or "").upper()
                        if sym not in {s.upper() for s in plan.symbols}:
                            continue
                        try:
                            bid = float(data["b"])
                            ask = float(data["a"])
                            bid_q = float(data["B"])
                            ask_q = float(data["A"])
                        except (KeyError, TypeError, ValueError):
                            n_err += 1
                            continue
                        if bid <= 0 or ask <= 0 or ask < bid:
                            n_err += 1
                            continue
                        upd = data.get("u")
                        try:
                            update_id = int(upd) if upd is not None else None
                        except (TypeError, ValueError):
                            update_id = None
                        if update_id is not None and last_u.get(sym) == update_id:
                            n_dup += 1
                        if update_id is not None:
                            # bookTicker u is not a dense gap-free sequence across symbols;
                            # only flag out-of-order per symbol when decreasing
                            prev = last_u.get(sym)
                            if prev is not None and update_id < prev:
                                errors.append(f"out_of_order:{sym}:{prev}->{update_id}")
                            last_u[sym] = update_id
                        # Do NOT invent exchange event time — bookTicker may lack E
                        ex_ts = data.get("E")
                        try:
                            exchange_ts_ms = int(ex_ts) if ex_ts is not None else None
                        except (TypeError, ValueError):
                            exchange_ts_ms = None
                        ev = {
                            "source": "websocket_bookTicker",
                            "parser_version": PARSER_VERSION,
                            "experiment_id": exp_id,
                            "connection_id": connection_id,
                            "symbol": sym,
                            "bid_price": bid,
                            "bid_qty": bid_q,
                            "ask_price": ask,
                            "ask_qty": ask_q,
                            "spread_abs": ask - bid,
                            "mid": (ask + bid) / 2.0,
                            "update_id": update_id,
                            "received_at_ms": recv_ms,
                            "received_mono_ns": mono,
                            "captured_at_ms": recv_ms,
                            "exchange_ts_ms": exchange_ts_ms,
                            "exchange_ts_note": (
                                None
                                if exchange_ts_ms is not None
                                else "not_provided_by_source_not_invented"
                            ),
                            "book_depth": "top_of_book_only",
                        }
                        line = json.dumps(ev, ensure_ascii=False)
                        lb = len(line) + 1
                        if nbytes + lb > plan.max_bytes:
                            stop_reason = "max_bytes"
                            break
                        if fh:
                            fh.write(line + "\n")
                        nbytes += lb
                        n_events += 1
                        if n_events >= plan.max_events:
                            stop_reason = "max_events"
                            break
                    if time.time() >= deadline:
                        stop_reason = "max_seconds"
            except Exception as exc:  # noqa: BLE001
                n_err += 1
                n_reconn += 1
                errors.append(str(exc)[:200])
                await asyncio.sleep(0.5)
                if time.time() >= deadline:
                    stop_reason = "max_seconds"
                    break
    finally:
        if fh:
            fh.close()

    ended = int(time.time() * 1000)
    rate = n_events / max((ended - started) / 1000.0, 1e-6)
    manifest = {
        "experiment_id": exp_id,
        "source": "websocket_bookTicker",
        "started_at_ms": started,
        "ended_at_ms": ended,
        "duration_ms": ended - started,
        "symbols": list(plan.symbols),
        "commit": plan.commit,
        "parser_version": PARSER_VERSION,
        "connection_id": connection_id,
        "n_events": n_events,
        "n_duplicates": n_dup,
        "n_reconnects": n_reconn,
        "n_errors": n_err,
        "bytes_written": nbytes,
        "msg_rate_per_s": rate,
        "stop_reason": stop_reason,
        "limits": {
            "max_seconds": plan.max_seconds,
            "max_events": plan.max_events,
            "max_bytes": plan.max_bytes,
        },
        "permanent_service": False,
        "update_id_gap_policy": (
            "Per-symbol decreasing u flagged; omitted u values are NOT treated as "
            "lost messages (bookTicker semantics ≠ depth diff stream)."
        ),
        "path": path,
    }
    if out_dir is not None and path:
        man = Path(path).with_suffix(".manifest.json")
        man.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest_path = str(man)
    result = WsCaptureResult(
        ok=n_events > 0,
        started_at_ms=started,
        ended_at_ms=ended,
        n_events=n_events,
        n_duplicates=n_dup,
        n_reconnects=n_reconn,
        n_errors=n_err,
        bytes_written=nbytes,
        stop_reason=stop_reason,
        path=path,
        manifest_path=manifest_path,
        errors=errors[:30],
    )
    out = asdict(result)
    out["manifest"] = manifest
    return out
