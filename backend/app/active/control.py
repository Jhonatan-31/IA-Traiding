"""Atomic Strategy B start/stop — persisted, independent from Demo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from . import ACCOUNT_B, B_EXECUTION_AUTHORIZED, POLICY_B_VERSION
from .schema import ensure_active_schema


def get_status(execute: Callable) -> dict[str, Any] | None:
    ensure_active_schema(execute)
    return execute("SELECT * FROM active_state WHERE id=1").fetchone()


def start_bot(execute: Callable, *, actor: str = "dashboard") -> dict[str, Any]:
    ensure_active_schema(execute)
    if not B_EXECUTION_AUTHORIZED:
        return {
            "ok": False,
            "changed": False,
            "status": "STOPPED",
            "note": "strategy_b_not_authorized",
        }
    row = execute(
        """UPDATE active_state SET
             status='RUNNING',
             started_at=COALESCE(started_at, NOW()),
             stopped_at=NULL,
             last_actor=%s,
             policy_version=%s,
             updated_at=NOW(),
             meta_json=meta_json || %s::jsonb
           WHERE id=1 AND status='STOPPED'
           RETURNING *""",
        (
            actor[:80],
            POLICY_B_VERSION,
            json.dumps({"last_start_at": datetime.now(timezone.utc).isoformat()}),
        ),
    ).fetchone()
    if row:
        execute(
            """INSERT INTO active_events(event_type, actor, detail, meta_json)
               VALUES ('START',%s,'active_b_started',%s::jsonb)""",
            (actor[:80], json.dumps({"from": "STOPPED", "to": "RUNNING"})),
        )
        return {"ok": True, "changed": True, "status": "RUNNING", "state": dict(row)}
    cur = execute("SELECT * FROM active_state WHERE id=1").fetchone()
    return {
        "ok": True,
        "changed": False,
        "status": (cur or {}).get("status"),
        "state": dict(cur) if cur else None,
        "note": "already_running",
    }


def stop_bot(execute: Callable, *, actor: str = "dashboard") -> dict[str, Any]:
    ensure_active_schema(execute)
    cancelled = execute(
        """UPDATE active_orders SET status='CANCELLED',
             reject_reason='stop_cancel_pending_entry',
             meta_json=meta_json || '{"cancelled_on_stop":true}'::jsonb
           WHERE account_id=%s
             AND side='BUY'
             AND status IN ('NEW','VALIDATED')
           RETURNING id""",
        (ACCOUNT_B,),
    ).fetchall()
    row = execute(
        """UPDATE active_state SET
             status='STOPPED',
             stopped_at=NOW(),
             last_actor=%s,
             updated_at=NOW(),
             meta_json=meta_json || %s::jsonb
           WHERE id=1 AND status='RUNNING'
           RETURNING *""",
        (
            actor[:80],
            json.dumps(
                {
                    "last_stop_at": datetime.now(timezone.utc).isoformat(),
                    "cancelled_pending_buys": len(cancelled),
                }
            ),
        ),
    ).fetchone()
    if row:
        execute(
            """INSERT INTO active_events(event_type, actor, detail, meta_json)
               VALUES ('STOP',%s,'active_b_stopped',%s::jsonb)""",
            (
                actor[:80],
                json.dumps(
                    {
                        "from": "RUNNING",
                        "to": "STOPPED",
                        "cancelled_pending_buys": len(cancelled),
                        "protective_exits_remain": True,
                    }
                ),
            ),
        )
        return {
            "ok": True,
            "changed": True,
            "status": "STOPPED",
            "cancelled_pending_buys": len(cancelled),
            "state": dict(row),
        }
    cur = execute("SELECT * FROM active_state WHERE id=1").fetchone()
    return {
        "ok": True,
        "changed": False,
        "status": (cur or {}).get("status"),
        "cancelled_pending_buys": len(cancelled),
        "state": dict(cur) if cur else None,
        "note": "already_stopped",
    }
