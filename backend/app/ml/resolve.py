"""Resolve Shadow predictions after the 6-bar horizon — idempotent, no probability mutation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..ohlcv import fetch_klines
from .labels import HORIZON, net_forward_return

INTERVAL_MS = {
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}

STATUS_PENDING = "PENDING"
STATUS_RESOLVED = "RESOLVED"
STATUS_INVALID = "INVALID"


def expected_exit_open_ms(candle_open_ms: int, interval: str, horizon: int = HORIZON) -> int:
    step = INTERVAL_MS.get(interval)
    if step is None:
        raise ValueError(f"unsupported interval {interval}")
    return int(candle_open_ms) + int(horizon) * step


def resolve_from_candles(
    candles: list[dict],
    *,
    candle_open_ms: int,
    interval: str,
    horizon: int = HORIZON,
) -> dict[str, Any]:
    """
    Compute observed outcome for a decision bar.
    Returns status PENDING if exit bar not yet closed / missing.
    """
    by_open = {int(c["open_time"]): c for c in candles if c.get("is_closed", True)}
    entry = by_open.get(int(candle_open_ms))
    if not entry:
        return {
            "status": STATUS_INVALID,
            "reason": "entry_candle_missing",
            "observed_label": None,
            "observed_net_return": None,
            "data_quality": "missing_entry",
        }
    exit_open = expected_exit_open_ms(candle_open_ms, interval, horizon)
    exit_c = by_open.get(exit_open)
    if not exit_c:
        # maybe horizon not complete
        newest = max(by_open) if by_open else 0
        if newest < exit_open:
            return {
                "status": STATUS_PENDING,
                "reason": "horizon_not_complete",
                "observed_label": None,
                "observed_net_return": None,
                "data_quality": "incomplete_horizon",
                "exit_open_ms": exit_open,
            }
        return {
            "status": STATUS_INVALID,
            "reason": "exit_candle_gap",
            "observed_label": None,
            "observed_net_return": None,
            "data_quality": "gap_at_exit",
            "exit_open_ms": exit_open,
        }
    entry_px = float(entry["close"])
    exit_px = float(exit_c["close"])
    if entry_px <= 0 or exit_px <= 0:
        return {
            "status": STATUS_INVALID,
            "reason": "corrupt_prices",
            "observed_label": None,
            "observed_net_return": None,
            "data_quality": "corrupt",
        }
    net = net_forward_return(entry_px, exit_px)
    return {
        "status": STATUS_RESOLVED,
        "reason": "ok",
        "observed_label": 1 if net > 0 else 0,
        "observed_net_return": float(net),
        "data_quality": "ok",
        "exit_open_ms": exit_open,
        "entry_close": entry_px,
        "exit_close": exit_px,
    }


def apply_resolution_row(execute: Callable, pred_id: int, result: dict[str, Any]) -> bool:
    """
    Persist resolution if still pending. Returns True if a row was updated.
    Never overwrites probability or prior RESOLVED/INVALID outcomes.
    """
    if result["status"] == STATUS_PENDING:
        execute(
            """UPDATE ml_predictions
               SET resolution_status=%s
               WHERE id=%s AND (resolution_status IS NULL OR resolution_status=%s)
                 AND observed_label IS NULL""",
            (STATUS_PENDING, pred_id, STATUS_PENDING),
        )
        return False
    if result["status"] == STATUS_RESOLVED:
        cur = execute(
            """UPDATE ml_predictions SET
                 resolution_status=%s,
                 observed_label=%s,
                 observed_net_return=%s,
                 observed_at=NOW(),
                 data_quality=%s,
                 resolve_meta=%s::jsonb
               WHERE id=%s
                 AND observed_label IS NULL
                 AND (resolution_status IS NULL OR resolution_status=%s)""",
            (
                STATUS_RESOLVED,
                int(result["observed_label"]),
                float(result["observed_net_return"]),
                result.get("data_quality"),
                __import__("json").dumps(
                    {
                        "reason": result.get("reason"),
                        "exit_open_ms": result.get("exit_open_ms"),
                        "entry_close": result.get("entry_close"),
                        "exit_close": result.get("exit_close"),
                        "resolved_wall": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                pred_id,
                STATUS_PENDING,
            ),
        )
        return True
    # INVALID
    execute(
        """UPDATE ml_predictions SET
             resolution_status=%s,
             observed_at=NOW(),
             data_quality=%s,
             resolve_meta=%s::jsonb
           WHERE id=%s
             AND observed_label IS NULL
             AND (resolution_status IS NULL OR resolution_status=%s)""",
        (
            STATUS_INVALID,
            result.get("data_quality"),
            __import__("json").dumps({"reason": result.get("reason")}),
            pred_id,
            STATUS_PENDING,
        ),
    )
    return True


async def resolve_pending_predictions(
    execute_factory,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """
    execute_factory: context manager yielding connection with .execute returning rowcount-capable cursor
    Actually we pass a db() context manager from main.
    """
    from .schema import ensure_ml_schema

    summary = {"checked": 0, "resolved": 0, "invalid": 0, "still_pending": 0, "items": []}
    with execute_factory() as c:
        ensure_ml_schema(c.execute)
        # migrate columns if needed already in ensure
        rows = list(
            c.execute(
                """SELECT id, symbol, interval, candle_open_ms, horizon, probability, resolution_status
                   FROM ml_predictions
                   WHERE observed_label IS NULL
                     AND (resolution_status IS NULL OR resolution_status=%s)
                   ORDER BY id ASC
                   LIMIT %s""",
                (STATUS_PENDING, limit),
            )
        )
    if not rows:
        return summary

    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": "ResearchPaperBot/ml-resolve"}
    ) as client:
        for pred in rows:
            summary["checked"] += 1
            interval = pred["interval"] or "1h"
            horizon = int(pred["horizon"] or HORIZON)
            try:
                payload = await fetch_klines(
                    client, pred["symbol"], interval, limit=120, use_cache=False
                )
                candles = payload["candles"]
                result = resolve_from_candles(
                    candles,
                    candle_open_ms=int(pred["candle_open_ms"]),
                    interval=interval,
                    horizon=horizon,
                )
            except Exception as exc:
                result = {
                    "status": STATUS_INVALID,
                    "reason": f"fetch_error:{type(exc).__name__}",
                    "observed_label": None,
                    "observed_net_return": None,
                    "data_quality": "fetch_error",
                }
            with execute_factory() as c:
                changed = apply_resolution_row(c.execute, int(pred["id"]), result)
            item = {
                "id": pred["id"],
                "symbol": pred["symbol"],
                "status": result["status"],
                "observed_label": result.get("observed_label"),
                "observed_net_return": result.get("observed_net_return"),
                "reason": result.get("reason"),
            }
            summary["items"].append(item)
            if result["status"] == STATUS_RESOLVED and changed:
                summary["resolved"] += 1
            elif result["status"] == STATUS_INVALID:
                summary["invalid"] += 1
            else:
                summary["still_pending"] += 1
    return summary
