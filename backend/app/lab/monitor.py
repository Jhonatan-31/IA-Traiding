"""Lab execution monitor — internal alerts, no auto-restart on critical conditions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .config import ACCOUNT_ID, INTERVAL_MS, MAX_POSITIONS, PRICE_STALE_S


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_alert(
    execute: Callable,
    *,
    code: str,
    severity: str,
    message: str,
    fingerprint: str,
    evidence: dict | None = None,
) -> bool:
    """Insert or refresh active alert. Returns True if newly created."""
    row = execute(
        "SELECT id, active FROM lab_alerts WHERE fingerprint=%s",
        (fingerprint,),
    ).fetchone()
    if row and row.get("active"):
        execute(
            """UPDATE lab_alerts SET at=NOW(), message=%s, evidence_json=%s::jsonb
               WHERE fingerprint=%s""",
            (message[:500], json.dumps(evidence or {}), fingerprint),
        )
        return False
    execute(
        """INSERT INTO lab_alerts(code, severity, message, active, fingerprint, evidence_json)
           VALUES(%s,%s,%s,TRUE,%s,%s::jsonb)
           ON CONFLICT (fingerprint) DO UPDATE SET
             active=TRUE,
             at=NOW(),
             resolved_at=NULL,
             message=EXCLUDED.message,
             severity=EXCLUDED.severity,
             evidence_json=EXCLUDED.evidence_json""",
        (code, severity, message[:500], fingerprint, json.dumps(evidence or {})),
    )
    return True


def resolve_alert(execute: Callable, fingerprint: str) -> None:
    execute(
        """UPDATE lab_alerts SET active=FALSE, resolved_at=NOW()
           WHERE fingerprint=%s AND active=TRUE""",
        (fingerprint,),
    )


def run_monitor(
    execute: Callable,
    *,
    expected_cycle_s: float = 300.0,
    binance_errors: int = 0,
) -> dict[str, Any]:
    """
    Detect operational anomalies. Does NOT resume trading or clear breaker.
    """
    raised: list[str] = []
    resolved: list[str] = []
    state = execute("SELECT * FROM lab_executor_state WHERE id=1").fetchone()
    now = _now()

    def _age_s(ts) -> float | None:
        if ts is None:
            return None
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now - ts).total_seconds()

    hb_age = _age_s(state.get("heartbeat_at") if state else None)
    cycle_age = _age_s(state.get("last_cycle_at") if state else None)
    lag_limit = expected_cycle_s * 2 + 90

    fp_hb = "executor_no_heartbeat"
    if hb_age is None or hb_age > lag_limit:
        upsert_alert(
            execute,
            code="executor_no_heartbeat",
            severity="ERROR",
            message=f"Heartbeat ausente o atrasado ({hb_age}s).",
            fingerprint=fp_hb,
            evidence={"heartbeat_age_s": hb_age, "limit_s": lag_limit},
        )
        raised.append(fp_hb)
    else:
        resolve_alert(execute, fp_hb)
        resolved.append(fp_hb)

    fp_cycle = "cycles_delayed"
    if cycle_age is None or cycle_age > lag_limit:
        upsert_alert(
            execute,
            code="cycles_delayed",
            severity="WARNING",
            message=f"Último ciclo atrasado ({cycle_age}s; límite {lag_limit}s).",
            fingerprint=fp_cycle,
            evidence={"cycle_age_s": cycle_age, "limit_s": lag_limit},
        )
        raised.append(fp_cycle)
    else:
        resolve_alert(execute, fp_cycle)
        resolved.append(fp_cycle)

    fp_bn = "binance_errors_persistent"
    if binance_errors >= 3:
        upsert_alert(
            execute,
            code="binance_errors_persistent",
            severity="ERROR",
            message=f"Fallos Binance repetidos en ciclo ({binance_errors}).",
            fingerprint=fp_bn,
            evidence={"errors": binance_errors},
        )
        raised.append(fp_bn)
    else:
        resolve_alert(execute, fp_bn)
        resolved.append(fp_bn)

    # Stale / incomplete valuation hint from last meta
    meta = (state or {}).get("meta_json") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    fp_stale = "stale_or_incomplete_marks"
    if meta.get("valuation_status") == "INCOMPLETE":
        upsert_alert(
            execute,
            code="stale_or_incomplete_marks",
            severity="WARNING",
            message="Valoración incompleta o marcas ausentes.",
            fingerprint=fp_stale,
            evidence={"valuation_status": "INCOMPLETE", "stale_s_threshold": PRICE_STALE_S},
        )
        raised.append(fp_stale)
    else:
        resolve_alert(execute, fp_stale)
        resolved.append(fp_stale)

    from .risk import accounting_ok

    fp_acct = "accounting_mismatch"
    if not accounting_ok(execute):
        upsert_alert(
            execute,
            code="accounting_mismatch",
            severity="CRITICAL",
            message="Descuadre contable lab detectado. No se auto-reanuda.",
            fingerprint=fp_acct,
            evidence={},
        )
        raised.append(fp_acct)
    else:
        resolve_alert(execute, fp_acct)
        resolved.append(fp_acct)

    # Pending orders stuck
    stuck = execute(
        """SELECT COUNT(*) AS n FROM lab_orders
           WHERE account_id=%s AND status IN ('NEW','VALIDATED')
             AND created_at < NOW() - INTERVAL '1 hour'""",
        (ACCOUNT_ID,),
    ).fetchone()
    fp_pend = "pending_orders_stuck"
    n_stuck = int(stuck["n"] if stuck else 0)
    if n_stuck > 0:
        upsert_alert(
            execute,
            code="pending_orders_stuck",
            severity="WARNING",
            message=f"{n_stuck} órdenes pendientes >1h.",
            fingerprint=fp_pend,
            evidence={"count": n_stuck},
        )
        raised.append(fp_pend)
    else:
        resolve_alert(execute, fp_pend)
        resolved.append(fp_pend)

    pos_n = execute(
        "SELECT COUNT(*) AS n FROM lab_positions WHERE account_id=%s",
        (ACCOUNT_ID,),
    ).fetchone()
    fp_exp = "exposure_limit_violation"
    n_pos = int(pos_n["n"] if pos_n else 0)
    if n_pos > MAX_POSITIONS:
        upsert_alert(
            execute,
            code="exposure_limit_violation",
            severity="CRITICAL",
            message=f"Posiciones {n_pos} > máximo {MAX_POSITIONS}.",
            fingerprint=fp_exp,
            evidence={"positions": n_pos, "max": MAX_POSITIONS},
        )
        raised.append(fp_exp)
    else:
        resolve_alert(execute, fp_exp)
        resolved.append(fp_exp)

    active = list(
        execute(
            """SELECT id, at, code, severity, message, fingerprint
               FROM lab_alerts WHERE active=TRUE ORDER BY id DESC LIMIT 30"""
        )
    )
    return {
        "raised": raised,
        "resolved_checks": resolved,
        "active": [dict(a) for a in active],
        "note": "Monitor no reinicia operaciones ni limpia circuit breaker.",
        "interval_ms_ref": INTERVAL_MS,
    }
