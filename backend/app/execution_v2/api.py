"""API de calidad de ejecución — solo lectura / simulación aislada."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .bbo_feed import refresh_book_ticker
from .bbo_store import get_registry
from .cost_reconcile import reconcile_d28h5_costs_from_artifact
from .engine_v2 import ExecutionV2Assumptions, compare_v1_v2, simulate_fill_v2
from . import ENGINE_VERSION, V1_ENGINE

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
        "verdict_hint": "SIMULACIÓN MEJORADA CON LIMITACIONES",
    }
