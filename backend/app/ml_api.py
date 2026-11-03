"""FastAPI routes for ML research / Shadow AI — no live trading."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from .ml.schema import ensure_ml_schema
from .ml.shadow import load_model, predict_symbol, risk_gate

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/status")
def ml_status():
    from .main import db, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        runtime = c.execute("SELECT * FROM ml_runtime WHERE id=1").fetchone()
        model = None
        if runtime and runtime.get("active_model_version"):
            model = c.execute(
                "SELECT version, algorithm, created_at, status, validated_for_research, validated_for_paper_ai, metrics_json, model_hash FROM ml_models WHERE version=%s",
                (runtime["active_model_version"],),
            ).fetchone()
        latest = c.execute(
            "SELECT version, status, created_at, validated_for_research, metrics_json FROM ml_models ORDER BY id DESC LIMIT 1"
        ).fetchone()
        preds = c.execute("SELECT COUNT(*) AS n FROM ml_predictions").fetchone()["n"]
        pending = c.execute(
            """SELECT COUNT(*) AS n FROM ml_predictions
               WHERE observed_label IS NULL
                 AND (resolution_status IS NULL OR resolution_status='PENDING')"""
        ).fetchone()["n"]
        resolved = c.execute(
            "SELECT COUNT(*) AS n FROM ml_predictions WHERE resolution_status='RESOLVED'"
        ).fetchone()["n"]
        datasets = c.execute("SELECT COUNT(*) AS n FROM ml_datasets").fetchone()["n"]
        breaker = c.execute(
            "SELECT * FROM circuit_breaker_state WHERE id=1"
        ).fetchone()

    state = "untrained"
    metrics = None
    if latest:
        metrics = latest.get("metrics_json")
        if latest["status"] == "validation_insufficient":
            state = "validation_insufficient"
        elif latest.get("validated_for_research") and runtime and runtime["mode"] == "SHADOW_AI":
            state = "shadow_ai_active"
        elif latest.get("validated_for_research"):
            state = "validated_research"
        elif latest["status"] == "degraded":
            state = "model_degraded"
        elif latest["status"] == "disabled":
            state = "model_disabled"
        else:
            state = "trained"
    return serial(
        {
            "state": state,
            "runtime": runtime,
            "active_model": model,
            "latest_model": {
                "version": latest["version"],
                "status": latest["status"],
                "created_at": latest["created_at"],
                "validated_for_research": latest["validated_for_research"],
                "mean_roc_auc_hist_gb": (metrics or {}).get("mean_roc_auc_hist_gb")
                if isinstance(metrics, dict)
                else None,
                "mean_roc_auc_naive": (metrics or {}).get("mean_roc_auc_naive")
                if isinstance(metrics, dict)
                else None,
                "mean_ece_calibrated_test": (metrics or {}).get("mean_ece_calibrated_test")
                if isinstance(metrics, dict)
                else None,
                "disclaimer": (metrics or {}).get("disclaimer")
                if isinstance(metrics, dict)
                else None,
            }
            if latest
            else None,
            "prediction_count": preds,
            "pending_resolution": pending,
            "resolved_count": resolved,
            "datasets": datasets,
            "circuit_breaker": breaker,
            "execution_policy": "SHADOW_AI never places paper or live orders",
        }
    )


@router.get("/models")
def ml_models():
    from .main import db, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        rows = list(
            c.execute(
                "SELECT id, created_at, version, algorithm, status, validated_for_research, validated_for_paper_ai, model_hash FROM ml_models ORDER BY id DESC LIMIT 20"
            )
        )
    return serial(rows)


@router.get("/models/{version}")
def ml_model_detail(version: str):
    from .main import db, serial

    with db() as c:
        row = c.execute(
            "SELECT * FROM ml_models WHERE version=%s", (version,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "model not found")
    return serial(row)


@router.get("/predictions")
def ml_predictions(
    limit: int = 100,
    unresolved: bool = False,
    resolved_only: bool = False,
):
    from .main import db, serial

    limit = max(1, min(500, limit))
    with db() as c:
        ensure_ml_schema(c.execute)
        if unresolved:
            rows = list(
                c.execute(
                    """SELECT * FROM ml_predictions
                       WHERE observed_label IS NULL
                         AND (resolution_status IS NULL OR resolution_status='PENDING')
                       ORDER BY id DESC LIMIT %s""",
                    (limit,),
                )
            )
        elif resolved_only:
            rows = list(
                c.execute(
                    """SELECT * FROM ml_predictions
                       WHERE resolution_status='RESOLVED'
                       ORDER BY observed_at DESC NULLS LAST, id DESC LIMIT %s""",
                    (limit,),
                )
            )
        else:
            rows = list(
                c.execute(
                    "SELECT * FROM ml_predictions ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
            )
    return serial(rows)


@router.get("/predictions/summary")
def ml_predictions_summary():
    from .main import db, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        pending = c.execute(
            """SELECT COUNT(*) AS n FROM ml_predictions
               WHERE resolution_status IS NULL OR resolution_status='PENDING'"""
        ).fetchone()["n"]
        resolved = list(
            c.execute(
                """SELECT observed_label, probability, observed_net_return, proposed_action, source
                   FROM ml_predictions WHERE resolution_status='RESOLVED'"""
            )
        )
    n = len(resolved)
    if n == 0:
        return {
            "pending": pending,
            "resolved": 0,
            "accuracy": None,
            "mean_net_return": None,
            "brier_proxy": None,
            "note": "Sin predicciones resueltas todavía",
        }
    correct = sum(
        1
        for r in resolved
        if (r["probability"] >= 0.5 and r["observed_label"] == 1)
        or (r["probability"] < 0.5 and r["observed_label"] == 0)
    )
    nets = [float(r["observed_net_return"]) for r in resolved if r["observed_net_return"] is not None]
    # simple Brier on stored probs
    brier = sum((float(r["probability"]) - float(r["observed_label"])) ** 2 for r in resolved) / n
    return serial(
        {
            "pending": pending,
            "resolved": n,
            "accuracy": correct / n,
            "mean_net_return": sum(nets) / len(nets) if nets else None,
            "brier_proxy": brier,
            "by_source": {
                "shadow_live": sum(1 for r in resolved if (r.get("source") or "shadow_live") == "shadow_live"),
                "shadow_replay": sum(1 for r in resolved if r.get("source") == "shadow_replay"),
            },
        }
    )


@router.get("/metrics-audit")
def ml_metrics_audit():
    from .ml.metrics_audit import METRIC_UNITS

    return {
        "units": METRIC_UNITS,
        "etapa_f_net_return_sum": (
            "Sum of per-trade fractional returns after costs — NOT portfolio equity %."
        ),
        "shadow_replay_mean_net_return": (
            "Average of hypothetical long nets including HOLD rows; not executable PnL."
        ),
        "etapa_g_portfolio": (
            "total_return_fraction = final_equity/initial - 1 under next-bar open execution."
        ),
        "ci_warning": (
            "IID bootstrap overstates precision with overlapping trades and cross-asset correlation. "
            "Prefer block bootstrap and portfolio holdout."
        ),
        "calibration_logloss": (
            "Isotonic may worsen LogLoss while improving Brier/ECE; not an economic edge."
        ),
        "doc": "docs/ETAPA_G_METRICS_AUDIT.md",
    }


@router.get("/research/latest")
def ml_research_latest():
    from .main import serial

    path = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts")) / "research" / "last_research.json"
    if not path.exists():
        return {
            "available": False,
            "message": "Sin informe de investigación. Ejecute: docker compose --profile ml run --rm ml-research",
        }
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    # Keep response bounded
    return serial(
        {
            "available": True,
            "created_at": data.get("created_at"),
            "conclusion": data.get("conclusion"),
            "robust_edge_any": data.get("robust_edge_any"),
            "paper_ai_authorized": data.get("paper_ai_authorized"),
            "execution_model": data.get("execution_model"),
            "dataset": data.get("dataset"),
            "selection_best": data.get("selection_window", {}).get("best_by_total_return"),
            "selection_results": data.get("selection_window", {}).get("results"),
            "holdout_results": data.get("final_holdout", {}).get("results"),
            "preselected_holdout": data.get("final_holdout", {}).get("preselected_holdout"),
            "cost_sensitivity": data.get("cost_sensitivity"),
            "expected_return_example": data.get("expected_return_example"),
            "shadow_replay_caveat": data.get("shadow_replay_caveat"),
            "multiple_testing": data.get("multiple_testing"),
            "metric_units": data.get("metric_units"),
        }
    )


@router.get("/strategies")
def ml_strategies():
    from .ml.strategies import list_strategy_specs

    return {
        "strategies": list_strategy_specs(),
        "note": "Ninguna estrategia se auto-activa. Solo investigación / Shadow.",
    }


@router.get("/comparison")
def ml_comparison():
    from .main import db, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        latest = c.execute(
            "SELECT metrics_json FROM ml_models ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not latest:
        return {"available": False, "message": "Modelo no disponible"}
    m = latest["metrics_json"]
    return serial(
        {
            "available": True,
            "mean_roc_auc_hist_gb": m.get("mean_roc_auc_hist_gb") if isinstance(m, dict) else None,
            "mean_roc_auc_naive": m.get("mean_roc_auc_naive") if isinstance(m, dict) else None,
            "roc_auc_ci": m.get("roc_auc_ci") if isinstance(m, dict) else None,
            "strategy_comparison": m.get("strategy_comparison") if isinstance(m, dict) else None,
            "calibration": m.get("calibration") if isinstance(m, dict) else None,
            "final_holdout": m.get("final_holdout") if isinstance(m, dict) else None,
            "walk_forward": m.get("walk_forward") if isinstance(m, dict) else None,
            "mean_ece_calibrated_test": m.get("mean_ece_calibrated_test")
            if isinstance(m, dict)
            else None,
            "disclaimer": m.get("disclaimer") if isinstance(m, dict) else None,
        }
    )


@router.get("/circuit-breaker")
def ml_circuit_breaker():
    from .main import db, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        state = c.execute("SELECT * FROM circuit_breaker_state WHERE id=1").fetchone()
        events = list(
            c.execute(
                "SELECT * FROM circuit_breaker_events ORDER BY id DESC LIMIT 30"
            )
        )
    return serial({"state": state, "events": events})


@router.post("/circuit-breaker/evaluate")
def ml_circuit_breaker_evaluate():
    from .main import START, db, serial
    from .ml.circuit_breaker import evaluate_circuit_breaker, persist_breaker_state

    with db() as c:
        ensure_ml_schema(c.execute)
        cash = float(c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"])
        positions = list(
            c.execute(
                """SELECT p.symbol, p.qty, p.cost, pr.price
                   FROM positions p
                   LEFT JOIN prices pr ON pr.symbol = p.symbol"""
            )
        )
        scans = list(
            c.execute(
                "SELECT equity FROM scans WHERE equity IS NOT NULL ORDER BY id ASC"
            )
        )
        latest = c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        invested = float(sum(float(p["cost"]) for p in positions))
        missing = sum(1 for p in positions if p.get("price") is None)
        equities = [float(s["equity"]) for s in scans]
        equity = equities[-1] if equities else cash + invested
        day_start = equities[0] if equities else equity
        data_age = None
        if latest and latest.get("at"):
            from datetime import datetime, timezone

            at = latest["at"]
            if getattr(at, "tzinfo", None) is None:
                at = at.replace(tzinfo=timezone.utc)
            data_age = (datetime.now(timezone.utc) - at).total_seconds()
        block, reason, evidence = evaluate_circuit_breaker(
            equity=equity,
            initial_capital=float(START),
            equity_series=equities,
            day_start_equity=day_start,
            data_age_s=data_age,
            recent_binance_errors=int((latest or {}).get("errors") or 0),
            missing_marks=missing,
            invested_cost=invested,
            cash=cash,
            critical_down=False,
        )
        persist_breaker_state(
            c.execute, active=block, reason=reason, evidence=evidence
        )
        state = c.execute("SELECT * FROM circuit_breaker_state WHERE id=1").fetchone()
    return serial(
        {
            "blocked_new_entries": block,
            "reason": reason,
            "evidence": evidence,
            "state": state,
            "policy": "No cierra posiciones automáticamente ante fallos de datos.",
        }
    )


@router.post("/resolve")
async def ml_resolve(limit: int = 100):
    from .main import db, serial
    from .ml.resolve import resolve_pending_predictions

    summary = await resolve_pending_predictions(db, limit=limit)
    return serial(summary)


@router.post("/shadow/replay")
def ml_shadow_replay(max_per_symbol: int = 6):
    """Insert historically resolvable Shadow predictions from latest dataset artifact."""
    from .main import db, serial
    from .ml.dataset import load_jsonl
    from .ml.replay import load_model, persist_replay, replay_resolved_predictions

    with db() as c:
        ensure_ml_schema(c.execute)
        runtime = c.execute("SELECT * FROM ml_runtime WHERE id=1").fetchone()
        if not runtime or not runtime.get("active_model_version"):
            raise HTTPException(409, "model_unavailable")
        model_row = c.execute(
            "SELECT * FROM ml_models WHERE version=%s",
            (runtime["active_model_version"],),
        ).fetchone()
        ds = c.execute(
            "SELECT * FROM ml_datasets ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not model_row or not ds:
        raise HTTPException(409, "model_or_dataset_unavailable")
    artifact = model_row["artifact_path"]
    if not Path(artifact).exists():
        alt = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts")) / "models" / Path(artifact).name
        if not alt.exists():
            raise HTTPException(409, detail={"status": "artifact_missing"})
        artifact = str(alt)
    data_path = Path(ds["data_path"])
    if not data_path.exists():
        # try artifacts mount basename
        alt_d = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts")) / "datasets" / data_path.name
        if alt_d.exists():
            data_path = alt_d
        else:
            raise HTTPException(409, detail={"status": "dataset_missing", "path": str(data_path)})
    model = load_model(artifact)
    rows = load_jsonl(data_path)
    preds = replay_resolved_predictions(
        rows,
        model,
        model_version=runtime["active_model_version"],
        max_per_symbol=max(1, min(20, max_per_symbol)),
    )
    with db() as c:
        before = c.execute("SELECT COUNT(*) AS n FROM ml_predictions").fetchone()["n"]
        persist_replay(c.execute, preds)
        after = c.execute("SELECT COUNT(*) AS n FROM ml_predictions").fetchone()["n"]
    return serial(
        {
            "attempted": len(preds),
            "inserted_delta": after - before,
            "model_version": runtime["active_model_version"],
            "note": "Replay histórico resuelto; no ejecuta órdenes. Distinto de shadow_live pendiente.",
        }
    )


@router.post("/shadow/run")
async def ml_shadow_run(limit_symbols: int = 10):
    """Generate shadow predictions for top liquid symbols already in prices table."""
    from .main import db, is_paused, serial

    with db() as c:
        ensure_ml_schema(c.execute)
        runtime = c.execute("SELECT * FROM ml_runtime WHERE id=1").fetchone()
        if not runtime or not runtime.get("active_model_version"):
            raise HTTPException(409, detail={"status": "model_unavailable"})
        model_row = c.execute(
            "SELECT * FROM ml_models WHERE version=%s",
            (runtime["active_model_version"],),
        ).fetchone()
        breaker = c.execute(
            "SELECT active, reason FROM circuit_breaker_state WHERE id=1"
        ).fetchone()
        symbols = [
            r["symbol"]
            for r in c.execute(
                "SELECT symbol FROM prices ORDER BY at DESC LIMIT %s",
                (max(1, min(50, limit_symbols)),),
            )
        ]
        paused = is_paused()

    if not model_row:
        raise HTTPException(409, detail={"status": "model_unavailable"})
    if breaker and breaker.get("active"):
        raise HTTPException(
            409,
            detail={
                "status": "circuit_breaker_active",
                "reason": breaker.get("reason"),
                "note": "Nuevas entradas simuladas bloqueadas; Shadow log también bloqueado.",
            },
        )
    artifact = model_row["artifact_path"]
    if not Path(artifact).exists():
        alt = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts")) / "models" / Path(artifact).name
        if alt.exists():
            artifact = str(alt)
        else:
            raise HTTPException(409, detail={"status": "artifact_missing", "path": artifact})

    model = load_model(artifact)
    created = []
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/shadow"}
    ) as client:
        for sym in symbols:
            try:
                pred = await predict_symbol(client, model, sym, "1h")
            except Exception as exc:
                created.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if not pred:
                continue
            ok, reason = risk_gate(
                runtime_mode=runtime["mode"],
                model_row=model_row,
                paused=paused,
                data_age_s=0,
                probability=pred["probability"],
                calibrated=bool(model_row.get("validated_for_research")),
            )
            accepted = bool(ok and runtime["mode"] == "SHADOW_AI")
            with db() as c:
                c.execute(
                    """INSERT INTO ml_predictions(
                        model_version, symbol, interval, decision_ts, candle_open_ms, horizon,
                        probability, proposed_action, accepted, reject_reason, feature_version,
                        resolution_status, source)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING','shadow_live')
                       ON CONFLICT(model_version, symbol, interval, candle_open_ms, horizon)
                       DO NOTHING""",
                    (
                        runtime["active_model_version"],
                        pred["symbol"],
                        pred["interval"],
                        pred["decision_ts"],
                        pred["candle_open_ms"],
                        pred["horizon"],
                        pred["probability"],
                        pred["proposed_action"],
                        accepted,
                        None if accepted else reason,
                        pred["feature_version"],
                    ),
                )
            created.append({**pred, "accepted_for_log": accepted, "gate": reason})
    return serial(
        {
            "mode": runtime["mode"],
            "model_version": runtime["active_model_version"],
            "generated": len([x for x in created if "probability" in x]),
            "items": created,
            "note": "Shadow AI does not send paper or live orders.",
        }
    )
