"""Resolve prospective decisions after horizon — idempotent, never mutates decision payload."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..ml.labels import net_forward_return
from ..ml.resolve import INTERVAL_MS, expected_exit_open_ms, resolve_from_candles
from ..ohlcv import fetch_klines


def apply_outcome(
    execute: Callable,
    decision_id: int,
    *,
    status: str,
    data_quality: str | None,
    observed_net_return: float | None,
    observed_label: int | None,
    result: dict,
) -> bool:
    """
    Insert outcome once and flip resolution_status only if still PENDING.
    Returns True if newly written.
    """
    existing = execute(
        "SELECT decision_id FROM prospect_outcomes WHERE decision_id=%s",
        (decision_id,),
    ).fetchone()
    if existing:
        return False
    cur = execute(
        """UPDATE prospect_decisions
           SET resolution_status=%s
           WHERE id=%s AND resolution_status='PENDING'
           RETURNING id""",
        (status, decision_id),
    ).fetchone()
    if not cur:
        return False
    execute(
        """INSERT INTO prospect_outcomes(
            decision_id, status, data_quality, observed_net_return, observed_label, result_json)
           VALUES(%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (decision_id) DO NOTHING""",
        (
            decision_id,
            status,
            data_quality,
            observed_net_return,
            observed_label,
            json.dumps(result),
        ),
    )
    return True


async def resolve_pending(
    db_factory,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    from .schema import ensure_prospect_schema

    summary = {
        "checked": 0,
        "resolved": 0,
        "invalid": 0,
        "still_pending": 0,
        "items": [],
    }
    with db_factory() as c:
        ensure_prospect_schema(c.execute)
        rows = list(
            c.execute(
                """SELECT d.*, e.experiment_type
                   FROM prospect_decisions d
                   JOIN prospect_experiments e ON e.id=d.experiment_id
                   WHERE d.resolution_status='PENDING'
                   ORDER BY d.id ASC
                   LIMIT %s""",
                (limit,),
            )
        )

    if not rows:
        return summary

    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": "ResearchPaperBot/prospect-resolve"}
    ) as client:
        for pred in rows:
            summary["checked"] += 1
            # HOLD: resolve as no-trade when horizon elapsed (label optional)
            interval = pred["interval"] or "1h"
            horizon = int(pred["horizon_bars"])
            candle_ms = pred.get("candle_open_ms")
            try:
                if candle_ms is None:
                    result = {
                        "status": "INVALID",
                        "reason": "missing_candle_open_ms",
                        "data_quality": "missing_ref",
                    }
                else:
                    payload = await fetch_klines(
                        client, pred["symbol"], interval, limit=120, use_cache=False
                    )
                    candles = payload["candles"]
                    if pred["action"] == "HOLD":
                        # Still wait for horizon so we don't peek early; mark resolved with null pnl
                        exit_open = expected_exit_open_ms(
                            int(candle_ms), interval, horizon
                        )
                        by_open = {
                            int(c["open_time"]): c
                            for c in candles
                            if c.get("is_closed", True)
                        }
                        if max(by_open, default=0) < exit_open:
                            result = {
                                "status": "PENDING",
                                "reason": "horizon_not_complete",
                                "data_quality": "incomplete_horizon",
                            }
                        else:
                            result = {
                                "status": "RESOLVED",
                                "reason": "hold_no_trade",
                                "observed_label": None,
                                "observed_net_return": 0.0,
                                "data_quality": "ok",
                                "note": "HOLD — no position; net_return recorded as 0",
                            }
                    else:
                        result = resolve_from_candles(
                            candles,
                            candle_open_ms=int(candle_ms),
                            interval=interval,
                            horizon=horizon,
                        )
            except Exception as exc:
                result = {
                    "status": "INVALID",
                    "reason": f"fetch_error:{type(exc).__name__}",
                    "data_quality": "fetch_error",
                    "observed_label": None,
                    "observed_net_return": None,
                }

            item = {
                "id": pred["id"],
                "symbol": pred["symbol"],
                "experiment_type": pred["experiment_type"],
                "status": result["status"],
                "reason": result.get("reason"),
            }
            if result["status"] == "PENDING":
                summary["still_pending"] += 1
                summary["items"].append(item)
                continue

            status = result["status"]
            with db_factory() as c:
                written = apply_outcome(
                    c.execute,
                    int(pred["id"]),
                    status=status,
                    data_quality=result.get("data_quality"),
                    observed_net_return=result.get("observed_net_return"),
                    observed_label=result.get("observed_label"),
                    result={
                        **{k: v for k, v in result.items() if k != "status"},
                        "resolved_wall": datetime.now(timezone.utc).isoformat(),
                        "experiment_type": pred["experiment_type"],
                    },
                )
            if status == "RESOLVED" and written:
                summary["resolved"] += 1
            elif status == "INVALID":
                summary["invalid"] += 1
            summary["items"].append(item)
    return summary
