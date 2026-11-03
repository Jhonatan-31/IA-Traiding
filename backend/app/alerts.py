"""Persistent internal alerts with deduplication by fingerprint."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


Severity = str  # INFO | WARNING | ERROR | CRITICAL


def ensure_alert_schema(execute: Callable):
    execute(
        """CREATE TABLE IF NOT EXISTS alerts(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            fingerprint TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS alerts_open_fingerprint
           ON alerts(fingerprint) WHERE status='OPEN'"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS risk_limits(
            id INTEGER PRIMARY KEY,
            max_daily_loss_pct NUMERIC NOT NULL DEFAULT 5,
            max_drawdown_pct NUMERIC NOT NULL DEFAULT 15,
            max_exposure_pct NUMERIC NOT NULL DEFAULT 80,
            max_positions INTEGER NOT NULL DEFAULT 10,
            max_trades_per_day INTEGER NOT NULL DEFAULT 50,
            stale_data_seconds INTEGER NOT NULL DEFAULT 7200,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """INSERT INTO risk_limits(id) VALUES(1) ON CONFLICT DO NOTHING"""
    )


def upsert_open_alert(
    execute: Callable,
    *,
    severity: Severity,
    code: str,
    title: str,
    detail: str,
    fingerprint: str,
) -> None:
    row = execute(
        "SELECT id FROM alerts WHERE fingerprint=%s AND status='OPEN'",
        (fingerprint,),
    ).fetchone()
    if row:
        execute(
            "UPDATE alerts SET updated_at=NOW(), detail=%s, severity=%s, title=%s WHERE id=%s",
            (detail, severity, title, row["id"]),
        )
    else:
        execute(
            """INSERT INTO alerts(severity, code, title, detail, status, fingerprint)
               VALUES(%s,%s,%s,%s,'OPEN',%s)""",
            (severity, code, title, detail, fingerprint),
        )


def resolve_alert(execute: Callable, fingerprint: str) -> None:
    execute(
        "UPDATE alerts SET status='RESOLVED', updated_at=NOW() WHERE fingerprint=%s AND status='OPEN'",
        (fingerprint,),
    )


def evaluate_alerts(conn_factory, risk_report: dict[str, Any], system: dict[str, Any]) -> int:
    """Create/resolve alerts from current evidence. Returns open count."""
    raised = 0
    with conn_factory() as c:
        ensure_alert_schema(c.execute)
        limits = c.execute("SELECT * FROM risk_limits WHERE id=1").fetchone() or {}
        stale_sec = int(limits.get("stale_data_seconds") or 7200)

        checks: list[tuple[bool, dict]] = []

        binance_ok = system.get("binance", {}).get("status") == "ok"
        checks.append(
            (
                not binance_ok,
                {
                    "severity": "ERROR",
                    "code": "BINANCE_DOWN",
                    "title": "Binance público inaccesible",
                    "detail": str(system.get("binance", {})),
                    "fingerprint": "BINANCE_DOWN",
                },
            )
        )

        db_ok = system.get("db") == "ok"
        checks.append(
            (
                not db_ok,
                {
                    "severity": "CRITICAL",
                    "code": "POSTGRES_DOWN",
                    "title": "PostgreSQL inaccesible",
                    "detail": "Health check DB falló",
                    "fingerprint": "POSTGRES_DOWN",
                },
            )
        )

        last_scan = system.get("last_scan")
        worker_stale = False
        if not last_scan:
            worker_stale = True
        else:
            at = last_scan.get("at")
            if isinstance(at, str):
                ts = datetime.fromisoformat(at.replace("Z", "+00:00"))
            else:
                ts = at
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            # Warning if older than 2x scan period
            period = int(system.get("scan_every_seconds") or 3600)
            worker_stale = age > max(period * 2, stale_sec)
        checks.append(
            (
                worker_stale,
                {
                    "severity": "WARNING",
                    "code": "WORKER_STALE",
                    "title": "Worker sin actividad reciente",
                    "detail": f"last_scan={last_scan}",
                    "fingerprint": "WORKER_STALE",
                },
            )
        )

        prices_at = system.get("prices_max_at")
        data_stale = False
        if prices_at:
            if isinstance(prices_at, str):
                ts = datetime.fromisoformat(prices_at.replace("Z", "+00:00"))
            else:
                ts = prices_at
            data_stale = (datetime.now(timezone.utc) - ts).total_seconds() > stale_sec
        else:
            data_stale = True
        checks.append(
            (
                data_stale,
                {
                    "severity": "WARNING",
                    "code": "MARKET_DATA_STALE",
                    "title": "Datos de mercado desactualizados",
                    "detail": f"prices_max_at={prices_at}",
                    "fingerprint": "MARKET_DATA_STALE",
                },
            )
        )

        errors = int((last_scan or {}).get("errors") or 0)
        checks.append(
            (
                errors >= 3,
                {
                    "severity": "WARNING",
                    "code": "REPEATED_MARKET_ERRORS",
                    "title": "Errores repetidos en ciclo",
                    "detail": f"errors={errors}",
                    "fingerprint": "REPEATED_MARKET_ERRORS",
                },
            )
        )

        breaches = set(risk_report.get("breaches") or [])
        if "exposure_limit" in breaches:
            checks.append(
                (
                    True,
                    {
                        "severity": "WARNING",
                        "code": "EXPOSURE_LIMIT",
                        "title": "Exposición sobre el límite",
                        "detail": str(risk_report.get("total_exposure_pct_of_initial")),
                        "fingerprint": "EXPOSURE_LIMIT",
                    },
                )
            )
        else:
            resolve_alert(c.execute, "EXPOSURE_LIMIT")

        if "max_drawdown_limit" in breaches:
            checks.append(
                (
                    True,
                    {
                        "severity": "ERROR",
                        "code": "DRAWDOWN_LIMIT",
                        "title": "Drawdown máximo excedido",
                        "detail": str(risk_report.get("drawdown")),
                        "fingerprint": "DRAWDOWN_LIMIT",
                    },
                )
            )
        else:
            resolve_alert(c.execute, "DRAWDOWN_LIMIT")

        # Accounting integrity: cash + invested_cost should equal initial if no sells
        cash = risk_report.get("cash")
        invested = risk_report.get("invested_cost")
        initial = risk_report.get("initial_capital")
        realized = risk_report.get("realized_pnl")
        accounting_ok = True
        if cash is not None and invested is not None and initial is not None:
            # Allow drift after sells: cash + invested ~= initial + realized - fees (approx)
            # Strict check when no realized yet:
            if (realized or 0) == 0:
                accounting_ok = abs((cash + invested) - initial) < 0.01
        checks.append(
            (
                not accounting_ok,
                {
                    "severity": "CRITICAL",
                    "code": "ACCOUNTING_MISMATCH",
                    "title": "Desajuste contable detectado",
                    "detail": f"cash={cash} invested={invested} initial={initial}",
                    "fingerprint": "ACCOUNTING_MISMATCH",
                },
            )
        )

        for active, payload in checks:
            if active:
                upsert_open_alert(c.execute, **payload)
                raised += 1
            else:
                resolve_alert(c.execute, payload["fingerprint"])

        open_n = c.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE status='OPEN'"
        ).fetchone()["n"]
    return int(open_n)


def list_alerts(execute: Callable, limit: int = 100) -> list[dict]:
    return list(
        execute(
            "SELECT * FROM alerts ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        )
    )


def ack_alert(execute: Callable, alert_id: int) -> dict | None:
    row = execute("SELECT * FROM alerts WHERE id=%s", (alert_id,)).fetchone()
    if not row:
        return None
    execute(
        "UPDATE alerts SET status='ACKED', updated_at=NOW() WHERE id=%s AND status='OPEN'",
        (alert_id,),
    )
    return execute("SELECT * FROM alerts WHERE id=%s", (alert_id,)).fetchone()
