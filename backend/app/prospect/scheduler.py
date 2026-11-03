"""Autonomous Shadow scheduler — inference + resolve, no training, no real orders.

Uses PostgreSQL advisory lock to prevent concurrent cycles across restarts/replicas.
Dedupes decisions via UNIQUE(experiment_id, symbol, interval, candle_open_ms).
"""
from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .engine import run_shadow_live_cycle
from .reconcile import run_reconciliation
from .resolve import resolve_pending
from .schema import ensure_prospect_schema

# Stable advisory lock key for shadow-scheduler
ADVISORY_LOCK_KEY = 81420031


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def _now():
    return datetime.now(timezone.utc)


def heartbeat(execute, *, status: str, error: str | None = None, **extra) -> None:
    execute(
        """UPDATE shadow_scheduler_state SET
             status=%s,
             heartbeat_at=NOW(),
             last_error=%s,
             active_model_version=COALESCE(%s, active_model_version),
             meta_json=meta_json || %s::jsonb,
             updated_at=NOW()
           WHERE id=1""",
        (
            status,
            error,
            extra.get("active_model_version"),
            json.dumps({"last_heartbeat_extra": {k: v for k, v in extra.items() if k != "active_model_version"}}),
        ),
    )


def try_acquire_lock(conn) -> bool:
    row = conn.execute(
        "SELECT pg_try_advisory_lock(%s) AS ok", (ADVISORY_LOCK_KEY,)
    ).fetchone()
    return bool(row and row["ok"])


def release_lock(conn) -> None:
    conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))


async def run_one_cycle() -> dict[str, Any]:
    started = _now()
    result: dict[str, Any] = {
        "started_at": started.isoformat(),
        "ok": False,
        "decisions_new": 0,
        "decisions_skipped": 0,
        "resolved": 0,
        "invalid": 0,
    }
    conn = db()
    try:
        ensure_prospect_schema(conn.execute)
        if not try_acquire_lock(conn):
            result["error"] = "concurrent_cycle_locked"
            result["ok"] = True  # another instance is running — not a hard failure
            heartbeat(conn.execute, status="LOCKED", error=None)
            conn.commit()
            return result

        try:
            runtime = conn.execute(
                "SELECT active_model_version, mode FROM ml_runtime WHERE id=1"
            ).fetchone()
            breaker = conn.execute(
                "SELECT active, reason FROM circuit_breaker_state WHERE id=1"
            ).fetchone()
            model_ver = (runtime or {}).get("active_model_version")
            heartbeat(
                conn.execute,
                status="RUNNING",
                error=None,
                active_model_version=model_ver,
            )
            conn.commit()

            # 1) Resolve first (idempotent)
            try:
                res = await resolve_pending(db, limit=200)
                result["resolved"] = int(res.get("resolved") or 0)
                result["invalid"] = int(res.get("invalid") or 0)
                conn.execute(
                    """UPDATE shadow_scheduler_state SET
                         last_resolve_at=NOW(),
                         resolve_errors=resolve_errors + %s,
                         updated_at=NOW()
                       WHERE id=1""",
                    (0,),
                )
                conn.commit()
            except Exception as rex:
                conn.execute(
                    """UPDATE shadow_scheduler_state SET
                         resolve_errors=resolve_errors+1,
                         last_error=%s, updated_at=NOW() WHERE id=1""",
                    (f"resolve:{type(rex).__name__}: {rex}"[:500],),
                )
                conn.commit()
                raise

            # 2) Reconciliation — may block new simulated BUY entries
            recon = run_reconciliation(conn.execute)
            conn.commit()
            result["recon_block"] = bool(recon.get("block_new_entries"))
            result["recon_critical_n"] = len(recon.get("critical") or [])

            # 3) Infer / register SHADOW_LIVE (dedupe by unique index)
            try:
                inf = await run_shadow_live_cycle(
                    db,
                    breaker_active=bool(breaker and breaker.get("active")),
                    breaker_reason=(breaker or {}).get("reason"),
                    block_new_entries=bool(recon.get("block_new_entries")),
                    block_reason="recon_critical" if recon.get("block_new_entries") else None,
                )
                items = inf.get("items") or []
                new = sum(1 for x in items if "decision_id" in x)
                skipped = sum(1 for x in items if x.get("skipped"))
                errs = sum(1 for x in items if "error" in x)
                result["decisions_new"] = new
                result["decisions_skipped"] = skipped
                conn.execute(
                    """UPDATE shadow_scheduler_state SET
                         last_inference_at=NOW(),
                         inference_errors=inference_errors+%s,
                         active_model_version=%s,
                         meta_json=meta_json || %s::jsonb,
                         updated_at=NOW()
                       WHERE id=1""",
                    (
                        errs,
                        model_ver,
                        json.dumps(
                            {
                                "last_recon": {
                                    "block_new_entries": recon.get("block_new_entries"),
                                    "critical": recon.get("critical"),
                                    "warnings": recon.get("warnings"),
                                    "checked_at": recon.get("checked_at"),
                                }
                            }
                        ),
                    ),
                )
                conn.commit()
            except Exception as iex:
                conn.execute(
                    """UPDATE shadow_scheduler_state SET
                         inference_errors=inference_errors+1,
                         last_error=%s, updated_at=NOW() WHERE id=1""",
                    (f"inference:{type(iex).__name__}: {iex}"[:500],),
                )
                conn.commit()
                raise

            result["ok"] = True
            duration_s = (_now() - started).total_seconds()
            conn.execute(
                """UPDATE shadow_scheduler_state SET
                     status='OK',
                     last_cycle_at=NOW(),
                     last_cycle_ok=TRUE,
                     last_error=NULL,
                     cycle_count=cycle_count+1,
                     heartbeat_at=NOW(),
                     updated_at=NOW()
                   WHERE id=1"""
            )
            conn.execute(
                """INSERT INTO shadow_scheduler_cycles(
                    started_at, finished_at, ok, decisions_new, decisions_skipped,
                    resolved, invalid, meta_json)
                   VALUES(%s, NOW(), TRUE, %s, %s, %s, %s, %s::jsonb)""",
                (
                    started,
                    result["decisions_new"],
                    result["decisions_skipped"],
                    result["resolved"],
                    result["invalid"],
                    json.dumps(
                        {
                            "model_version": model_ver,
                            "duration_s": duration_s,
                            "recon_block": result.get("recon_block"),
                            "duplicates_avoided": result["decisions_skipped"],
                        }
                    ),
                ),
            )
            conn.commit()
        finally:
            release_lock(conn)
            conn.commit()
    except psycopg.OperationalError as e:
        result["error"] = f"postgres:{type(e).__name__}"
        try:
            with db() as c2:
                ensure_prospect_schema(c2.execute)
                c2.execute(
                    """UPDATE shadow_scheduler_state SET
                         status='ERROR',
                         connection_errors=connection_errors+1,
                         last_error=%s,
                         last_cycle_ok=FALSE,
                         heartbeat_at=NOW(),
                         updated_at=NOW()
                       WHERE id=1""",
                    (str(e)[:500],),
                )
        except Exception:
            pass
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        try:
            with db() as c2:
                ensure_prospect_schema(c2.execute)
                c2.execute(
                    """UPDATE shadow_scheduler_state SET
                         status='ERROR',
                         last_error=%s,
                         last_cycle_ok=FALSE,
                         last_cycle_at=NOW(),
                         heartbeat_at=NOW(),
                         cycle_count=cycle_count+1,
                         updated_at=NOW()
                       WHERE id=1""",
                    (result["error"][:500],),
                )
                c2.execute(
                    """INSERT INTO shadow_scheduler_cycles(
                        started_at, finished_at, ok, error, meta_json)
                       VALUES(%s, NOW(), FALSE, %s, %s::jsonb)""",
                    (started, result["error"][:500], json.dumps({"trace": traceback.format_exc()[-1000:]})),
                )
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    result["finished_at"] = _now().isoformat()
    return result


async def main_loop() -> None:
    every = max(60, int(os.environ.get("SHADOW_EVERY_SECONDS", "300")))
    print(f"SHADOW_SCHEDULER start every={every}s UTC", flush=True)
    # bootstrap schema
    with db() as c:
        ensure_prospect_schema(c.execute)
        heartbeat(c.execute, status="STARTING")
    while True:
        try:
            summary = await run_one_cycle()
            print("SHADOW_CYCLE", json.dumps(summary, default=str), flush=True)
        except Exception as exc:
            print("SHADOW_CYCLE_FATAL", type(exc).__name__, exc, flush=True)
        await asyncio.sleep(every)


def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
