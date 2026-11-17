"""API de calidad de ejecución — solo lectura / simulación aislada."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .bbo_capture import CapturePlan, estimate_disk_usage, run_bounded_capture
from .bbo_feed import refresh_book_ticker
from .bbo_store import get_registry
from .compare_experiment import HypotheticalDecision, evaluate_pair, summarize_pairs
from .cost_reconcile import reconcile_d28h5_costs_from_artifact
from .engine_v2 import ExecutionV2Assumptions, compare_v1_v2, simulate_fill_v2
from . import ENGINE_VERSION, V1_ENGINE
import time

router = APIRouter(prefix="/api/execution-quality", tags=["execution-quality"])


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
        "bbo": snap,
        "limitations": [
            "Sin BBO histórico inventado",
            "Top-of-book ≠ profundidad completa",
            "D28H5 congelada; V2 no la recalibra",
            "V1 (mid+proxy) sigue siendo el motor paper/demo/active actual",
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
    from fastapi import HTTPException

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
            "slip": "fixed rate ± volume heuristic",
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
        },
        "d28h5_costs": costs,
        "lab_accounting": {
            "sell_cash_model": "all_in_price_no_double_fee",
            "historical_lab_sells": "NOT_REWRITTEN",
            "note": "AL1 fixed forward Lab SELL double fee; historical rows preserved",
        },
        "verdict_hint": "V2 MEJORADO CON LIMITACIONES",
    }


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
    return {
        "plan": {
            "symbols": list(plan.symbols),
            "poll_interval_s": plan.poll_interval_s,
            "max_seconds": plan.max_seconds,
            "max_events": plan.max_events,
            "max_bytes": plan.max_bytes,
        },
        "disk": estimate_disk_usage(plan),
        "permanent_24_7": False,
        "requires_authorization_for_permanent": True,
    }


@router.post("/capture/run-bounded")
async def capture_run_bounded(seconds: float = Query(default=5.0, ge=1.0, le=30.0)):
    """Captura manual corta. No activa grabación permanente."""
    plan = CapturePlan(max_seconds=float(seconds), max_events=max(3, int(seconds) * 3))
    return await run_bounded_capture(plan, out_dir=None)
