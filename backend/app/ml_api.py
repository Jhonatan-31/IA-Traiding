"""FastAPI routes for ML research / Shadow AI — no live trading."""
from __future__ import annotations

import os
from datetime import datetime, timezone
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
        preds = c.execute(
            "SELECT COUNT(*) AS n FROM ml_predictions"
        ).fetchone()["n"]
        pending = c.execute(
            "SELECT COUNT(*) AS n FROM ml_predictions WHERE observed_label IS NULL"
        ).fetchone()["n"]
        datasets = c.execute(
            "SELECT COUNT(*) AS n FROM ml_datasets"
        ).fetchone()["n"]

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
                "disclaimer": (metrics or {}).get("disclaimer")
                if isinstance(metrics, dict)
                else None,
            }
            if latest
            else None,
            "prediction_count": preds,
            "pending_resolution": pending,
            "datasets": datasets,
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
def ml_predictions(limit: int = 100, unresolved: bool = False):
    from .main import db, serial

    limit = max(1, min(500, limit))
    with db() as c:
        ensure_ml_schema(c.execute)
        if unresolved:
            rows = list(
                c.execute(
                    "SELECT * FROM ml_predictions WHERE observed_label IS NULL ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
            )
        else:
            rows = list(
                c.execute(
                    "SELECT * FROM ml_predictions ORDER BY id DESC LIMIT %s", (limit,)
                )
            )
    return serial(rows)


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
    folds = m.get("walk_forward") if isinstance(m, dict) else None
    return serial(
        {
            "available": True,
            "mean_roc_auc_hist_gb": m.get("mean_roc_auc_hist_gb") if isinstance(m, dict) else None,
            "mean_roc_auc_naive": m.get("mean_roc_auc_naive") if isinstance(m, dict) else None,
            "walk_forward": folds,
            "disclaimer": m.get("disclaimer") if isinstance(m, dict) else None,
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
    artifact = model_row["artifact_path"]
    if not Path(artifact).exists():
        # try under ML_ARTIFACT_DIR mount
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
            # Shadow never executes; accepted means logged as proposed
            with db() as c:
                c.execute(
                    """INSERT INTO ml_predictions(
                        model_version, symbol, interval, decision_ts, candle_open_ms, horizon,
                        probability, proposed_action, accepted, reject_reason, feature_version)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
