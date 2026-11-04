"""Atomic DEMO start/stop — persisted, idempotent-aware."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from . import POLICY_VERSION
from .schema import ensure_demo_schema


def get_status(execute: Callable) -> dict[str, Any] | None:
    ensure_demo_schema(execute)
    return execute("SELECT * FROM demo_state WHERE id=1").fetchone()


def start_bot(execute: Callable, *, actor: str = "dashboard") -> dict[str, Any]:
    ensure_demo_schema(execute)
    row = execute(
        """UPDATE demo_state SET
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
            POLICY_VERSION,
            json.dumps({"last_start_at": datetime.now(timezone.utc).isoformat()}),
        ),
    ).fetchone()
    if row:
        execute(
            """INSERT INTO demo_events(event_type, actor, detail, meta_json)
               VALUES ('START',%s,'demo_started',%s::jsonb)""",
            (actor[:80], json.dumps({"from": "STOPPED", "to": "RUNNING"})),
        )
        return {"ok": True, "changed": True, "status": "RUNNING", "state": dict(row)}
    cur = execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    execute(
        """INSERT INTO demo_events(event_type, actor, detail, meta_json)
           VALUES ('START_NOOP',%s,'already_running',%s::jsonb)""",
        (actor[:80], json.dumps({"status": (cur or {}).get("status")})),
    )
    return {
        "ok": True,
        "changed": False,
        "status": (cur or {}).get("status"),
        "state": dict(cur) if cur else None,
        "note": "already_running",
    }


def stop_bot(execute: Callable, *, actor: str = "dashboard") -> dict[str, Any]:
    ensure_demo_schema(execute)
    # Cancel pending entry orders (no fills yet)
    cancelled = execute(
        """UPDATE demo_orders SET status='CANCELLED', updated_at=NOW(),
             reject_reason='stop_cancel_pending_entry',
             meta_json=meta_json || '{"cancelled_on_stop":true}'::jsonb
           WHERE account_id='demo_manual_control'
             AND side='BUY'
             AND status IN ('NEW','VALIDATED')
           RETURNING id"""
    ).fetchall()
    row = execute(
        """UPDATE demo_state SET
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
            """INSERT INTO demo_events(event_type, actor, detail, meta_json)
               VALUES ('STOP',%s,'demo_stopped',%s::jsonb)""",
            (
                actor[:80],
                json.dumps(
                    {
                        "from": "RUNNING",
                        "to": "STOPPED",
                        "cancelled_pending_buys": [int(r["id"]) for r in cancelled],
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
    cur = execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    execute(
        """INSERT INTO demo_events(event_type, actor, detail, meta_json)
           VALUES ('STOP_NOOP',%s,'already_stopped',%s::jsonb)""",
        (actor[:80], json.dumps({"status": (cur or {}).get("status")})),
    )
    return {
        "ok": True,
        "changed": False,
        "status": (cur or {}).get("status"),
        "cancelled_pending_buys": len(cancelled),
        "state": dict(cur) if cur else None,
        "note": "already_stopped",
    }
