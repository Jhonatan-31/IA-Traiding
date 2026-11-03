"""Persistent order queue — idempotent enqueue; restart-safe."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Callable

from .config import ACCOUNT_ID, STRATEGY


def enqueue_order(
    execute: Callable,
    *,
    signal_id: int | None,
    symbol: str,
    side: str,
    candle_ms: int,
    ref_price: float | None,
    budget: Decimal | None = None,
    strategy: str = STRATEGY,
    meta: dict | None = None,
) -> dict[str, Any]:
    """Insert NEW order; on unique conflict return existing (no duplicate)."""
    existing = execute(
        """SELECT * FROM lab_orders
           WHERE account_id=%s AND strategy=%s AND symbol=%s AND side=%s AND candle_ms=%s""",
        (ACCOUNT_ID, strategy, symbol.upper(), side.upper(), candle_ms),
    ).fetchone()
    if existing:
        return {"created": False, "order": dict(existing), "reason": "duplicate_signal"}
    uid = str(uuid.uuid4())
    row = execute(
        """INSERT INTO lab_orders(
            order_uid, account_id, signal_id, strategy, symbol, side, status,
            candle_ms, budget, ref_price, meta_json)
           VALUES(%s::uuid,%s,%s,%s,%s,%s,'NEW',%s,%s,%s,%s::jsonb)
           ON CONFLICT (account_id, strategy, symbol, side, candle_ms) DO NOTHING
           RETURNING *""",
        (
            uid,
            ACCOUNT_ID,
            signal_id,
            strategy,
            symbol.upper(),
            side.upper(),
            candle_ms,
            budget,
            ref_price,
            json.dumps(meta or {}),
        ),
    ).fetchone()
    if not row:
        existing = execute(
            """SELECT * FROM lab_orders
               WHERE account_id=%s AND strategy=%s AND symbol=%s AND side=%s AND candle_ms=%s""",
            (ACCOUNT_ID, strategy, symbol.upper(), side.upper(), candle_ms),
        ).fetchone()
        return {"created": False, "order": dict(existing) if existing else None, "reason": "race_duplicate"}
    return {"created": True, "order": dict(row)}


def claim_new_orders(execute: Callable, limit: int = 50) -> list[dict]:
    """Claim NEW → VALIDATED atomically for processing (skip locked)."""
    rows = list(
        execute(
            """SELECT * FROM lab_orders
               WHERE status='NEW' AND account_id=%s
               ORDER BY id ASC LIMIT %s
               FOR UPDATE SKIP LOCKED""",
            (ACCOUNT_ID, limit),
        )
    )
    claimed = []
    for r in rows:
        execute(
            """UPDATE lab_orders SET status='VALIDATED', updated_at=NOW()
               WHERE id=%s AND status='NEW'""",
            (r["id"],),
        )
        claimed.append(dict(r))
    return claimed


def mark_order(
    execute: Callable,
    order_id: int,
    *,
    status: str,
    reject_reason: str | None = None,
    filled_qty: Decimal | None = None,
    avg_price: Decimal | None = None,
    fee: Decimal | None = None,
    slip: Decimal | None = None,
    stop_triggered: bool | None = None,
    stop_trigger_price: Decimal | None = None,
    execution_price: Decimal | None = None,
    meta: dict | None = None,
) -> None:
    execute(
        """UPDATE lab_orders SET
             status=%s,
             reject_reason=%s,
             filled_qty=COALESCE(%s, filled_qty),
             avg_price=COALESCE(%s, avg_price),
             fee=COALESCE(%s, fee),
             slip=COALESCE(%s, slip),
             stop_triggered=COALESCE(%s, stop_triggered),
             stop_trigger_price=COALESCE(%s, stop_trigger_price),
             execution_price=COALESCE(%s, execution_price),
             meta_json=CASE WHEN %s::jsonb IS NULL THEN meta_json ELSE meta_json || %s::jsonb END,
             updated_at=NOW()
           WHERE id=%s""",
        (
            status,
            reject_reason,
            filled_qty,
            avg_price,
            fee,
            slip,
            stop_triggered,
            stop_trigger_price,
            execution_price,
            json.dumps(meta) if meta else None,
            json.dumps(meta) if meta else None,
            order_id,
        ),
    )
