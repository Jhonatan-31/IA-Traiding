"""API Etapa U — mejora / investigación (solo lectura + backtest en memoria)."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Query

from ..ohlcv import fetch_klines
from .backtest_u import run_etapa_u
from .improve import improve_report

router = APIRouter(prefix="/api/research", tags=["research"])

_BT_CACHE: dict[str, Any] | None = None
_BT_LOCK = asyncio.Lock()


@router.get("/improve")
async def research_improve(run_backtest: bool = Query(False)):
    """Informe de mejora. No reactiva A/B. Backtest opcional (puede tardar)."""
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
    """Ejecuta backtest walk-forward aislado (sin mutar carteras)."""
    from ..main import serial

    global _BT_CACHE
    async with _BT_LOCK:
        _BT_CACHE = await run_etapa_u(["BTCUSDT", "ETHUSDT", "SOLUSDT"], limit=limit)
        return serial(_BT_CACHE)
