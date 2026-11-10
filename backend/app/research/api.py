"""API investigación Etapa U/V — solo lectura + backtests en memoria."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Query

from ..ohlcv import fetch_klines
from .backtest_u import run_etapa_u
from .backtest_v import run_etapa_v
from .center_v import research_center
from .forensic_a import forensic_rounds
from .improve import improve_report

router = APIRouter(prefix="/api/research", tags=["research"])

_BT_CACHE: dict[str, Any] | None = None
_BT_V_CACHE: dict[str, Any] | None = None
_BT_LOCK = asyncio.Lock()


@router.get("/improve")
async def research_improve(run_backtest: bool = Query(False)):
    from ..main import db, serial

    marks: dict[str, float] = {}
    with db() as c:
        pos = list(
            c.execute(
                "SELECT symbol FROM demo_positions WHERE account_id=%s",
                ("demo_manual_control",),
            )
        )
    if pos:
        try:
            async with httpx.AsyncClient(
                timeout=10, headers={"User-Agent": "ResearchPaperBot/etapa-u"}
            ) as client:
                for p in pos:
                    try:
                        k = await fetch_klines(client, p["symbol"], "1m", limit=3, use_cache=True)
                        closed = [x for x in k["candles"] if x.get("is_closed", True)]
                        if closed:
                            marks[p["symbol"]] = float(closed[-1]["close"])
                    except Exception:
                        continue
        except Exception:
            pass

    global _BT_CACHE
    bt = _BT_CACHE
    if run_backtest:
        async with _BT_LOCK:
            try:
                _BT_CACHE = await asyncio.wait_for(
                    run_etapa_u(["BTCUSDT", "ETHUSDT", "SOLUSDT"], limit=900),
                    timeout=120,
                )
                bt = _BT_CACHE
            except Exception as exc:
                bt = {
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"declare_winner": False, "declare_profitable": False},
                }

    with db() as c:
        return serial(improve_report(c.execute, marks=marks, backtest=bt))


@router.get("/backtest-u")
async def research_backtest_u(limit: int = Query(900, ge=300, le=1000)):
    from ..main import serial

    global _BT_CACHE
    async with _BT_LOCK:
        _BT_CACHE = await run_etapa_u(["BTCUSDT", "ETHUSDT", "SOLUSDT"], limit=limit)
        return serial(_BT_CACHE)


@router.get("/forensic-a")
async def research_forensic_a():
    """Auditoría forense de A. No muta estado ni reactiva bots."""
    from ..main import db, serial

    with db() as c:
        return serial(forensic_rounds(c.execute))


@router.get("/backtest-v")
async def research_backtest_v(limit: int = Query(1000, ge=300, le=1000)):
    from ..main import serial

    global _BT_V_CACHE
    async with _BT_LOCK:
        _BT_V_CACHE = await run_etapa_v(["BTCUSDT", "ETHUSDT", "SOLUSDT"], limit=limit)
        return serial(_BT_V_CACHE)


@router.get("/center")
async def research_center_api(run_backtest: bool = Query(False)):
    """Centro de Investigación de Estrategias (Etapa V)."""
    from ..main import db, serial

    global _BT_V_CACHE
    bt = _BT_V_CACHE
    if run_backtest:
        async with _BT_LOCK:
            try:
                _BT_V_CACHE = await asyncio.wait_for(
                    run_etapa_v(["BTCUSDT", "ETHUSDT", "SOLUSDT"], limit=1000),
                    timeout=180,
                )
                bt = _BT_V_CACHE
            except Exception as exc:
                bt = {
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"declare_winner": False, "declare_profitable": False},
                }
    with db() as c:
        return serial(research_center(c.execute, backtest_v=bt))
