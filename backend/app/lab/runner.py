"""trade-executor main loop — Docker service entrypoint."""
from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from .executor import run_lab_cycle
from .schema import ensure_lab_schema

ADVISORY_LOCK_KEY = 81420032


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def run_one() -> dict:
    started = datetime.now(timezone.utc)
    conn = db()
    try:
        ensure_lab_schema(conn.execute)
        locked = conn.execute(
            "SELECT pg_try_advisory_lock(%s) AS ok", (ADVISORY_LOCK_KEY,)
        ).fetchone()
        if not locked or not locked["ok"]:
            conn.execute(
                """UPDATE lab_executor_state SET status='LOCKED', heartbeat_at=NOW()
                   WHERE id=1"""
            )
            conn.commit()
            return {"ok": True, "error": "concurrent_cycle_locked"}
        try:
            conn.commit()
            result = await run_lab_cycle(db)
            result["started_at"] = started.isoformat()
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            return result
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            conn.commit()
    except psycopg.OperationalError as e:
        try:
            with db() as c2:
                ensure_lab_schema(c2.execute)
                c2.execute(
                    """UPDATE lab_executor_state SET
                         status='ERROR', last_error=%s, last_cycle_ok=FALSE,
                         heartbeat_at=NOW(), updated_at=NOW() WHERE id=1""",
                    (f"postgres:{e}"[:500],),
                )
        except Exception:
            pass
        return {"ok": False, "error": f"postgres:{type(e).__name__}"}
    except Exception as e:
        try:
            with db() as c2:
                ensure_lab_schema(c2.execute)
                c2.execute(
                    """UPDATE lab_executor_state SET
                         status='ERROR', last_error=%s, last_cycle_ok=FALSE,
                         heartbeat_at=NOW(), cycle_count=cycle_count+1,
                         updated_at=NOW() WHERE id=1""",
                    (f"{type(e).__name__}: {e}"[:500],),
                )
                c2.execute(
                    """INSERT INTO lab_audit(actor, action, detail)
                       VALUES('trade-executor','cycle_error',%s)""",
                    (traceback.format_exc()[-1500:],),
                )
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def main_loop() -> None:
    every = max(60, int(os.environ.get("LAB_EVERY_SECONDS", "300")))
    print(f"TRADE_EXECUTOR start every={every}s PAPER_ONLY UTC", flush=True)
    with db() as c:
        ensure_lab_schema(c.execute)
        c.execute(
            """UPDATE lab_executor_state SET status='STARTING', heartbeat_at=NOW()
               WHERE id=1"""
        )
    while True:
        try:
            summary = await run_one()
            print("LAB_CYCLE", json.dumps(summary, default=str)[:2000], flush=True)
        except Exception as exc:
            print("LAB_CYCLE_FATAL", type(exc).__name__, exc, flush=True)
        await asyncio.sleep(every)


def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
