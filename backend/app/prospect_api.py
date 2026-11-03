"""API for prospective research — separated from SMA paper portfolio."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .prospect.schema import ensure_prospect_schema

router = APIRouter(prefix="/api/prospect", tags=["prospect"])


@router.get("/status")
def prospect_status():
    from .main import db, serial, _age_seconds, _status_from_age
    from .prospect.decisions import decision_counts
    from .prospect.degradation import THRESHOLDS
    from .prospect.ledger import accounting_identity_ok, ledger_snapshot
    from .prospect.metrics import prospective_metrics

    with db() as c:
        ensure_prospect_schema(c.execute)
        counts = decision_counts(c.execute)
        by_type = {}
        for t in ("BACKTEST", "SHADOW_REPLAY", "SHADOW_LIVE", "PAPER_TRADE"):
            by_type[t] = decision_counts(c.execute, t)
        exps = list(
            c.execute(
                """SELECT id, created_at, experiment_type, name, strategy, status
                   FROM prospect_experiments ORDER BY id DESC LIMIT 20"""
            )
        )
        breaker = c.execute(
            "SELECT * FROM circuit_breaker_state WHERE id=1"
        ).fetchone()
        virt = ledger_snapshot(c.execute)
        identity = accounting_identity_ok(c.execute)
        sched = c.execute(
            "SELECT * FROM shadow_scheduler_state WHERE id=1"
        ).fetchone()
        alerts = list(
            c.execute(
                """SELECT * FROM prospect_alerts WHERE status='OPEN'
                   ORDER BY id DESC LIMIT 20"""
            )
        )
        metrics = prospective_metrics(c.execute, experiment_type="SHADOW_LIVE")
        last_pred = c.execute(
            """SELECT MAX(d.created_at) AS at FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE'"""
        ).fetchone()
        last_res = c.execute(
            "SELECT MAX(resolved_at) AS at FROM prospect_outcomes"
        ).fetchone()
        runtime = c.execute("SELECT * FROM ml_runtime WHERE id=1").fetchone()
    hb_age = _age_seconds(sched["heartbeat_at"] if sched else None)
    if not sched or not sched.get("heartbeat_at"):
        sched_health = "UNKNOWN"
    elif sched.get("status") == "ERROR":
        sched_health = "ERROR"
    else:
        sched_health = _status_from_age(
            hb_age, THRESHOLDS["scheduler_warn_s"], THRESHOLDS["scheduler_stale_s"]
        )
    return serial(
        {
            "counts": counts,
            "counts_by_type": by_type,
            "experiments": exps,
            "circuit_breaker": breaker,
            "virtual_ledger": virt,
            "accounting_identity": identity,
            "paper_sma_untouched": True,
            "paper_ai_authorized": False,
            "real_trading": False,
            "scheduler": {
                "health": sched_health,
                "heartbeat_age_s": hb_age,
                "state": sched,
                "last_prediction_at": last_pred["at"] if last_pred else None,
                "last_resolve_at": last_res["at"] if last_res else None,
                "active_model_version": (sched or {}).get("active_model_version")
                or (runtime or {}).get("active_model_version"),
            },
            "metrics_shadow_live": metrics,
            "open_alerts": alerts,
            "data_classes": {
                "observed": "precios/velas Binance públicas",
                "simulated": "retornos netos hipotéticos, ledger virtual, costos estimados",
            },
        }
    )


@router.get("/decisions")
def prospect_decisions(
    limit: int = 50,
    experiment_type: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
):
    from .main import db, serial

    limit = max(1, min(200, limit))
    clauses = ["1=1"]
    params: list = []
    if experiment_type:
        clauses.append("e.experiment_type=%s")
        params.append(experiment_type)
    if strategy:
        clauses.append("d.strategy=%s")
        params.append(strategy)
    if symbol:
        clauses.append("d.symbol=%s")
        params.append(symbol.upper())
    if status:
        clauses.append("d.resolution_status=%s")
        params.append(status)
    params.append(limit)
    sql = f"""
        SELECT d.*, e.experiment_type, e.name AS experiment_name,
               o.observed_net_return, o.observed_label, o.data_quality AS outcome_quality
        FROM prospect_decisions d
        JOIN prospect_experiments e ON e.id=d.experiment_id
        LEFT JOIN prospect_outcomes o ON o.decision_id=d.id
        WHERE {' AND '.join(clauses)}
        ORDER BY d.id DESC
        LIMIT %s
    """
    with db() as c:
        ensure_prospect_schema(c.execute)
        rows = list(c.execute(sql, tuple(params)))
    return serial(rows)


@router.get("/protocols")
def prospect_protocols():
    from .main import db, serial
    from .prospect.protocols import list_protocols

    with db() as c:
        ensure_prospect_schema(c.execute)
        rows = list_protocols(c.execute)
    return serial(rows)


@router.post("/shadow-live/run")
async def prospect_shadow_live_run(limit_symbols: int = 5):
    from .main import db, serial
    from .prospect.engine import run_shadow_live_cycle

    with db() as c:
        ensure_prospect_schema(c.execute)
        breaker = c.execute(
            "SELECT active, reason FROM circuit_breaker_state WHERE id=1"
        ).fetchone()
    result = await run_shadow_live_cycle(
        db,
        symbols=None,
        breaker_active=bool(breaker and breaker.get("active")),
        breaker_reason=(breaker or {}).get("reason"),
    )
    # optionally trim symbols
    if limit_symbols < 5:
        result["items"] = result.get("items", [])[:limit_symbols]
    return serial(result)


@router.post("/resolve")
async def prospect_resolve(limit: int = 100):
    from .main import db, serial
    from .prospect.resolve import resolve_pending

    return serial(await resolve_pending(db, limit=limit))


@router.get("/ledger")
def prospect_ledger():
    from .main import db, serial
    from .prospect.ledger import accounting_identity_ok, ledger_snapshot

    with db() as c:
        ensure_prospect_schema(c.execute)
        return serial(
            {
                "virtual": ledger_snapshot(c.execute),
                "identity": accounting_identity_ok(c.execute),
                "warning": "Do not confuse with /api/overview SMA paper portfolio.",
            }
        )


@router.get("/benchmarks")
def prospect_benchmarks():
    """Prospective resolved nets vs cash benchmark (SHADOW_LIVE only)."""
    from .main import db, serial
    from .prospect.metrics import prospective_metrics

    with db() as c:
        ensure_prospect_schema(c.execute)
        metrics = prospective_metrics(c.execute, experiment_type="SHADOW_LIVE")
        rows = list(
            c.execute(
                """SELECT d.action, o.observed_net_return, o.status
                   FROM prospect_decisions d
                   JOIN prospect_experiments e ON e.id=d.experiment_id
                   JOIN prospect_outcomes o ON o.decision_id=d.id
                   WHERE e.experiment_type='SHADOW_LIVE' AND o.status='RESOLVED'"""
            )
        )
    buys = [
        float(r["observed_net_return"])
        for r in rows
        if r["action"] == "BUY" and r["observed_net_return"] is not None
    ]
    holds = [r for r in rows if r["action"] == "HOLD"]
    return serial(
        {
            "experiment_type": "SHADOW_LIVE",
            "resolved_buy_n": len(buys),
            "mean_buy_net": sum(buys) / len(buys) if buys else None,
            "hold_n": len(holds),
            "cash_benchmark_net": 0.0,
            "metrics": metrics,
            "note": (
                "Prospective only. Not mixed with BACKTEST or SHADOW_REPLAY. "
                "Insufficient n ⇒ no edge claim. HOLD is not a profitable trade."
            ),
        }
    )


@router.get("/scheduler")
def prospect_scheduler():
    from .main import db, serial
    from .prospect.decisions import decision_counts
    from .prospect.degradation import THRESHOLDS

    with db() as c:
        ensure_prospect_schema(c.execute)
        state = c.execute("SELECT * FROM shadow_scheduler_state WHERE id=1").fetchone()
        cycles = list(
            c.execute(
                """SELECT * FROM shadow_scheduler_cycles ORDER BY id DESC LIMIT 20"""
            )
        )
        live = decision_counts(c.execute, "SHADOW_LIVE")
        last_pred = c.execute(
            """SELECT MAX(d.created_at) AS at FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE'"""
        ).fetchone()
        last_res = c.execute(
            "SELECT MAX(resolved_at) AS at FROM prospect_outcomes"
        ).fetchone()
    from .main import _age_seconds, _status_from_age

    hb_age = _age_seconds(state["heartbeat_at"] if state else None)
    if not state or not state.get("heartbeat_at"):
        health = "UNKNOWN"
    elif state.get("status") == "ERROR":
        health = "ERROR"
    else:
        health = _status_from_age(
            hb_age, THRESHOLDS["scheduler_warn_s"], THRESHOLDS["scheduler_stale_s"]
        )
    return serial(
        {
            "health": health,
            "heartbeat_age_s": hb_age,
            "state": state,
            "counts_shadow_live": live,
            "last_prediction_at": last_pred["at"] if last_pred else None,
            "last_resolve_at": last_res["at"] if last_res else None,
            "recent_cycles": cycles,
            "thresholds": THRESHOLDS,
            "note": "Salud por heartbeat, no por estado del contenedor.",
        }
    )


@router.get("/metrics")
def prospect_metrics_api(experiment_type: str = "SHADOW_LIVE"):
    from .main import db, serial
    from .prospect.metrics import prospective_metrics

    if experiment_type not in ("SHADOW_LIVE", "SHADOW_REPLAY", "BACKTEST", "PAPER_TRADE"):
        raise HTTPException(400, "invalid experiment_type")
    with db() as c:
        ensure_prospect_schema(c.execute)
        return serial(prospective_metrics(c.execute, experiment_type=experiment_type))


@router.get("/alerts")
def prospect_alerts_list(status: str = "OPEN"):
    from .main import db, serial

    with db() as c:
        ensure_prospect_schema(c.execute)
        rows = list(
            c.execute(
                """SELECT * FROM prospect_alerts
                   WHERE (%s='' OR status=%s)
                   ORDER BY id DESC LIMIT 100""",
                (status or "", status or ""),
            )
        )
    return serial(rows)


@router.post("/alerts/evaluate")
def prospect_alerts_evaluate():
    from .main import db, serial
    from .prospect.degradation import evaluate_degradation

    with db() as c:
        ensure_prospect_schema(c.execute)
        result = evaluate_degradation(c.execute)
    return serial(result)


@router.get("/reconcile")
def prospect_reconcile_get():
    from .main import db, serial
    from .prospect.reconcile import run_reconciliation

    with db() as c:
        ensure_prospect_schema(c.execute)
        return serial(run_reconciliation(c.execute))


@router.post("/reconcile")
def prospect_reconcile_run():
    from .main import db, serial
    from .prospect.reconcile import run_reconciliation

    with db() as c:
        ensure_prospect_schema(c.execute)
        return serial(run_reconciliation(c.execute))


@router.get("/horizons")
def prospect_horizons():
    """Exact horizon expiry for PENDING SHADOW_LIVE — no early resolve."""
    from .main import db, serial
    from .prospect.reconcile import horizon_audit

    with db() as c:
        ensure_prospect_schema(c.execute)
        rows = horizon_audit(c.execute)
    ready = sum(1 for r in rows if r.get("horizon_ready"))
    return serial(
        {
            "pending": rows,
            "ready_count": ready,
            "not_ready_count": len(rows) - ready,
            "note": "Resolver solo cuando horizon_ready=true; no adelantar.",
        }
    )


@router.get("/audit")
def prospect_audit():
    """Operational audit bundle for Etapa J — evidence only."""
    from .main import db, serial, _age_seconds, _status_from_age
    from .prospect.decisions import decision_counts
    from .prospect.degradation import THRESHOLDS
    from .prospect.metrics import prospective_metrics
    from .prospect.reconcile import run_reconciliation

    with db() as c:
        ensure_prospect_schema(c.execute)
        state = c.execute("SELECT * FROM shadow_scheduler_state WHERE id=1").fetchone()
        cycles = list(
            c.execute(
                """SELECT id, started_at, finished_at, ok, decisions_new, decisions_skipped,
                          resolved, invalid, error, meta_json,
                          EXTRACT(EPOCH FROM (finished_at - started_at)) AS duration_s
                   FROM shadow_scheduler_cycles ORDER BY id DESC LIMIT 20"""
            )
        )
        live = decision_counts(c.execute, "SHADOW_LIVE")
        recon = run_reconciliation(c.execute)
        metrics = prospective_metrics(c.execute, experiment_type="SHADOW_LIVE")
        # Next closed 1h candle open after last decision candle
        last_candle = c.execute(
            """SELECT MAX(candle_open_ms) AS ms FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE'"""
        ).fetchone()
        next_infer_ms = (
            int(last_candle["ms"]) + 3_600_000 if last_candle and last_candle["ms"] else None
        )
    hb_age = _age_seconds(state["heartbeat_at"] if state else None)
    if not state or not state.get("heartbeat_at"):
        health = "UNKNOWN"
    elif state.get("status") == "ERROR":
        health = "ERROR"
    else:
        health = _status_from_age(
            hb_age, THRESHOLDS["scheduler_warn_s"], THRESHOLDS["scheduler_stale_s"]
        )
    # Resolution lag: for pending, mean seconds until ready (from recon horizons)
    lags = [
        r["seconds_until_ready"]
        for r in recon.get("horizons_pending") or []
        if r.get("seconds_until_ready") is not None
    ]
    return serial(
        {
            "scheduler_health": health,
            "heartbeat_age_s": hb_age,
            "state": state,
            "cycles": cycles,
            "counts_shadow_live": live,
            "duplicates_avoided_recent": sum(
                int(c.get("decisions_skipped") or 0) for c in cycles
            ),
            "next_candle_open_ms_for_inference": next_infer_ms,
            "resolution_lag_s_mean": (sum(lags) / len(lags)) if lags else None,
            "reconciliation": recon,
            "metrics_shadow_live": metrics,
            "evidence_label": (metrics.get("virtual_portfolio") or {}).get("evidence_label"),
            "paper_ai_authorized": False,
            "real_trading": False,
        }
    )
