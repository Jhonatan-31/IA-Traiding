"""API de calidad de ejecución — solo lectura / simulación aislada / captura autorizada."""
from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .am_experiment import load_jsonl, run_analysis_on_capture
from .bbo_capture import (
    CapturePlan,
    am_authorized_plan,
    capture_is_active,
    estimate_disk_usage,
    run_bounded_capture,
)
from .bbo_feed import refresh_book_ticker
from .bbo_store import get_registry
from .compare_experiment import HypotheticalDecision, evaluate_pair, summarize_pairs
from .cost_decomposition import reconstruct_al_anomaly_buy
from .cost_reconcile import reconcile_d28h5_costs_from_artifact
from .engine_v2 import ExecutionV2Assumptions, compare_v1_v2, simulate_fill_v2
from .lab_historical_audit import audit_lab_sells_readonly
from . import ENGINE_VERSION, V1_ENGINE

router = APIRouter(prefix="/api/execution-quality", tags=["execution-quality"])

ETAPA_AM_DIR = Path(os.environ.get("MARKET_HISTORY_DIR", "/artifacts/history")) / "etapa_am"


def _require_capture_token(
    x_lab_token: str | None = Header(default=None, alias="X-Lab-Token"),
) -> str:
    """Capturas largas / AM requieren el mismo token de control lab (no secreto en logs)."""
    expected = os.environ.get("LAB_CONTROL_TOKEN")
    if not expected or not str(expected).strip():
        raise HTTPException(status_code=503, detail="lab_control_token_not_configured")
    if not x_lab_token or x_lab_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized_capture_control")
    return "ok"


class SimulateBody(BaseModel):
    side: str
    qty: float = Field(..., gt=0)
    symbol: str = "BTCUSDT"
    ref_mid: float | None = None
    use_registry_bbo: bool = True
    allow_mid_fallback: bool = False

    def normalized_side(self) -> str:
        s = (self.side or "").upper()
        if s not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        return s


@router.get("/status")
async def execution_quality_status():
    snap = get_registry().snapshot()
    return {
        "engine_v2": ENGINE_VERSION,
        "engine_v1_preserved": V1_ENGINE,
        "paper_only": True,
        "mutates_ledgers": False,
        "activates_strategies": False,
        "capture_active": capture_is_active(),
        "bbo": snap,
        "limitations": [
            "Sin BBO histórico inventado",
            "Top-of-book ≠ profundidad completa",
            "D28H5 congelada; V2 no la recalibra",
            "V1 (mid+proxy) sigue siendo el motor paper/demo/active actual",
            "V1 default slip 10bps ≠ V2 extra_slip 2bps — ver /al-anomaly",
        ],
    }


@router.post("/bbo/refresh")
async def bbo_refresh(symbols: str | None = Query(default="BTCUSDT,ETHUSDT")):
    """Refresca bookTicker público. No requiere API keys."""
    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    return await refresh_book_ticker(syms or None)


@router.get("/bbo")
async def bbo_snapshot(max_age_ms: int = Query(default=5000, ge=100, le=60_000)):
    return get_registry().snapshot(max_age_ms=max_age_ms)


@router.post("/simulate")
async def simulate(body: SimulateBody):
    try:
        side = body.normalized_side()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reg = get_registry()
    bbo = reg.get(body.symbol) if body.use_registry_bbo else None
    ref = body.ref_mid
    if ref is None and bbo is not None:
        ref = bbo.mid
    if ref is None:
        ref = 0.0
    v2 = simulate_fill_v2(
        side=side,
        qty=body.qty,
        ref_mid=ref or None,
        bbo=bbo,
        assumptions=ExecutionV2Assumptions(allow_mid_fallback=body.allow_mid_fallback),
    )
    cmp = compare_v1_v2(
        side=side,
        qty=body.qty,
        ref_mid=float(ref or 0) or 1.0,
        bbo=bbo,
        v2=ExecutionV2Assumptions(allow_mid_fallback=body.allow_mid_fallback),
    )
    return {
        "symbol": body.symbol.upper(),
        "bbo_used": bbo.to_public_dict() if bbo else None,
        "v2": v2,
        "comparison": cmp,
        "labels": {
            "historical_research": "close + fee/slip/spread proxy (D28H5 V1)",
            "paper_engines": "estimate_fill_price mid+proxy (V1)",
            "live_quote": "bookTicker BBO observado",
            "v2_sim": "ask/bid + fee + slip + top-qty cap",
        },
    }


@router.get("/d28h5-costs")
async def d28h5_costs():
    return reconcile_d28h5_costs_from_artifact()


@router.get("/audit-summary")
async def audit_summary():
    costs = reconcile_d28h5_costs_from_artifact()
    return {
        "v1_assumptions": {
            "ref": "mid or close",
            "spread": "proxy bps (no BBO)",
            "slip": "fixed rate ± volume heuristic (default base_slip_rate=0.001)",
            "fee": "embedded in all-in price",
            "partial_fills": "only vs bar_volume cap",
            "book": "optional; rarely supplied in paper path",
        },
        "v2_assumptions": {
            "ref": "bid/ask when fresh BBO present",
            "stale": "rejected",
            "missing_bbo": "rejected unless allow_mid_fallback",
            "size": "capped at top-of-book qty when known",
            "historical_bbo": "not fabricated",
            "extra_slip_rate_default": 0.0002,
        },
        "d28h5_costs": costs,
        "lab_accounting": {
            "sell_cash_model": "all_in_price_no_double_fee",
            "historical_lab_sells": "NOT_REWRITTEN",
            "note": "AL1 fixed forward Lab SELL double fee; historical rows preserved",
        },
        "verdict_hint": "EXPERIMENTO V1/V2 VALIDADO CON LIMITACIONES",
    }


@router.get("/al-anomaly")
async def al_anomaly():
    """AM1 — reconstrucción de la comparación AL anómala (V2 más barato)."""
    return reconstruct_al_anomaly_buy()


class CompareBody(BaseModel):
    side: str = "BUY"
    qty: float = Field(..., gt=0)
    symbol: str = "BTCUSDT"
    ref_mid: float | None = None
    assumed_send_latency_ms: int = 0


@router.post("/compare-once")
async def compare_once(body: CompareBody):
    """Una observación V1 vs V2. Sin BBO fresco → NO_COMPARABLE."""
    await refresh_book_ticker([body.symbol.upper()])
    reg = get_registry()
    bbo = reg.get(body.symbol)
    ref = body.ref_mid if body.ref_mid is not None else (bbo.mid if bbo else None)
    if ref is None:
        return {
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "missing_ref_and_bbo",
            "fabricated": False,
        }
    now = int(time.time() * 1000)
    row = evaluate_pair(
        HypotheticalDecision(
            decision_ts_ms=now,
            symbol=body.symbol.upper(),
            side=body.side,
            qty=body.qty,
            ref_mid=float(ref),
            assumed_send_latency_ms=body.assumed_send_latency_ms,
        ),
        bbo,
        now_ms=now,
    )
    return {"observation": row, "summary": summarize_pairs([row])}


@router.get("/capture/plan")
async def capture_plan():
    plan = CapturePlan()
    am = am_authorized_plan()
    return {
        "plan": {
            "symbols": list(plan.symbols),
            "poll_interval_s": plan.poll_interval_s,
            "max_seconds": plan.max_seconds,
            "max_events": plan.max_events,
            "max_bytes": plan.max_bytes,
        },
        "am_authorized_defaults": {
            "symbols": list(am.symbols),
            "max_seconds": am.max_seconds,
            "max_events": am.max_events,
            "max_bytes": am.max_bytes,
            "poll_interval_s": am.poll_interval_s,
            "requires_token": True,
        },
        "disk": estimate_disk_usage(plan),
        "disk_am": estimate_disk_usage(am),
        "permanent_24_7": False,
        "requires_authorization_for_permanent": True,
        "capture_active": capture_is_active(),
    }


@router.post("/capture/run-bounded")
async def capture_run_bounded(seconds: float = Query(default=5.0, ge=1.0, le=30.0)):
    """Captura manual corta (≤30s). No activa grabación permanente."""
    if capture_is_active():
        raise HTTPException(status_code=409, detail="capture_already_active")
    plan = CapturePlan(max_seconds=float(seconds), max_events=max(3, int(seconds) * 3))
    return await run_bounded_capture(plan, out_dir=None)


@router.post("/capture/run-am-authorized")
async def capture_run_am_authorized(
    seconds: float = Query(default=600.0, ge=60.0, le=1800.0),
    _auth: str = Depends(_require_capture_token),
):
    """Única captura AM autorizada (token). Stop al primer límite. No 24/7."""
    if capture_is_active():
        raise HTTPException(status_code=409, detail="capture_already_active")
    plan = am_authorized_plan(
        max_seconds=float(seconds),
        commit=os.environ.get("DEPLOY_GIT_COMMIT"),
    )
    ETAPA_AM_DIR.mkdir(parents=True, exist_ok=True)
    result = await run_bounded_capture(plan, out_dir=ETAPA_AM_DIR)
    if result.get("path") and Path(result["path"]).exists():
        events = load_jsonl(Path(result["path"]))
        analysis = run_analysis_on_capture(
            events, commit=os.environ.get("DEPLOY_GIT_COMMIT")
        )
        analysis_path = Path(result["path"]).with_name(
            Path(result["path"]).stem + "_analysis.json"
        )
        analysis_path.write_text(
            __import__("json").dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result["analysis_path"] = str(analysis_path)
        result["analysis_summary"] = {
            "n_comparable": analysis.get("n_comparable"),
            "n_rejected": analysis.get("n_rejected"),
            "by_size": analysis.get("by_size"),
            "price_diff_v2_minus_v1": analysis.get("price_diff_v2_minus_v1"),
            "spread_abs_distribution": analysis.get("spread_abs_distribution"),
            "meta": analysis.get("meta"),
        }
        summary = ETAPA_AM_DIR / "last_experiment.json"
        summary.write_text(
            __import__("json").dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result["summary_path"] = str(summary)
    return result


@router.get("/experiment/latest")
async def experiment_latest():
    """Lectura del último experimento AM (si existe). No inicia captura."""
    summary = ETAPA_AM_DIR / "last_experiment.json"
    if not summary.exists():
        return {
            "ok": False,
            "reason": "no_experiment_yet",
            "dir": str(ETAPA_AM_DIR),
            "labels": {
                "observed": "BBO",
                "hypothetical": "decisions",
                "estimated_fill": "V1/V2",
                "paper_or_real": "NONE",
            },
        }
    import json

    data = json.loads(summary.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "experiment": data,
        "labels": {
            "observed": "BBO bookTicker",
            "hypothetical": "decisions",
            "estimated_fill": "V1/V2 sim",
            "paper_or_real": "NONE",
        },
    }


@router.get("/lab-sells-audit")
async def lab_sells_audit():
    """AM8/AN7 — solo lectura. No regulariza."""
    import psycopg
    from psycopg.rows import dict_row

    url = os.environ.get("DATABASE_URL")
    if not url:
        return {"ok": False, "reason": "DATABASE_URL_missing", "readonly": True}
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:

            def execute(sql, params=None):
                cur.execute(sql, params or ())
                return cur

            report = audit_lab_sells_readonly(execute)
    report["ok"] = True
    return report


ETAPA_AN_DIR = Path(os.environ.get("MARKET_HISTORY_DIR", "/artifacts/history")) / "etapa_an"


@router.get("/cost-contract")
async def cost_contract():
    from .cost_contract import CONTRACT_SPEC

    return CONTRACT_SPEC


@router.get("/am-audit")
async def am_audit_endpoint():
    """AN0 — relee dataset AM si existe en disco; no lo modifica."""
    from .am_audit import audit_am_dataset

    jsonl = ETAPA_AM_DIR / "bbo_capture_1794948090084.jsonl"
    man = ETAPA_AM_DIR / "bbo_capture_1794948090084.manifest.json"
    if not jsonl.exists():
        # fallback: docs copy not on server path — try glob
        cands = list(ETAPA_AM_DIR.glob("bbo_capture_*.jsonl"))
        if not cands:
            return {"ok": False, "reason": "am_dataset_missing", "dir": str(ETAPA_AM_DIR)}
        jsonl = cands[0]
        man = jsonl.with_suffix(".manifest.json")
    return {"ok": True, **audit_am_dataset(jsonl, man if man.exists() else None)}


@router.get("/fair-compare")
async def fair_compare_endpoint(
    source: str = Query(default="am"),
):
    """LEGACY + MATCHED sobre dataset AM o AN. Solo lectura."""
    from .fair_compare import run_fair_analysis

    if source not in ("am", "an-rest", "an-ws"):
        raise HTTPException(status_code=400, detail="source must be am|an-rest|an-ws")
    if source == "am":
        base = ETAPA_AM_DIR
        cands = list(base.glob("bbo_capture_*.jsonl"))
    elif source == "an-rest":
        base = ETAPA_AN_DIR / "rest"
        cands = list(base.glob("bbo_capture_*.jsonl"))
    else:
        base = ETAPA_AN_DIR / "ws"
        cands = list(base.glob("bbo_ws_*.jsonl"))
    if not cands:
        return {"ok": False, "reason": "dataset_missing", "source": source, "dir": str(base)}
    path = sorted(cands)[-1]
    analysis = run_fair_analysis(load_jsonl(path))
    out_path = ETAPA_AN_DIR / f"fair_{source.replace('-', '_')}.json"
    ETAPA_AN_DIR.mkdir(parents=True, exist_ok=True)
    import json

    out_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "ok": True,
        "source": source,
        "dataset": str(path),
        "analysis": analysis,
        "saved": str(out_path),
    }


@router.get("/dual-experiment/latest")
async def dual_experiment_latest():
    path = ETAPA_AN_DIR / "last_dual_experiment.json"
    if not path.exists():
        return {"ok": False, "reason": "no_dual_experiment_yet", "dir": str(ETAPA_AN_DIR)}
    import json

    return {"ok": True, "experiment": json.loads(path.read_text(encoding="utf-8"))}


@router.post("/compare-fair-once")
async def compare_fair_once(body: CompareBody):
    """Una decisión: LEGACY + MATCHED contemporáneos. Sin órdenes."""
    from .fair_compare import evaluate_legacy, evaluate_matched

    await refresh_book_ticker([body.symbol.upper()])
    reg = get_registry()
    bbo = reg.get(body.symbol)
    if bbo is None:
        return {"comparable": False, "reason": "missing_bbo"}
    mid = float(body.ref_mid) if body.ref_mid is not None else bbo.mid
    now = int(time.time() * 1000)
    return {
        "legacy": evaluate_legacy(
            side=body.side, qty=body.qty, mid=mid, bbo=bbo, now_ms=now
        ),
        "matched": evaluate_matched(side=body.side, qty=body.qty, mid=mid, bbo=bbo),
        "labels": {
            "LEGACY": "defaults V1 vs V2 as deployed",
            "MATCHED": "same fee+slip; isolates mid→touch BBO",
            "paper_or_real": "NONE",
        },
    }
