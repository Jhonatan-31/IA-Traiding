"""API investigación Etapa U/V/W — lectura + backtests + historial Vision."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Query

from ..ohlcv import fetch_klines
from .backtest_u import run_etapa_u
from .backtest_v import run_etapa_v
from .center_y import research_center_y
from .etapa_aa.center_aa import research_center_aa
from .etapa_aa.run_aa import run_etapa_aa
from .etapa_ab.center_ab import research_center_ab
from .etapa_ab.run_ab import run_etapa_ab
from .etapa_ac.center_ac import research_center_ac
from .etapa_ac.run_ac import run_etapa_ac
from .etapa_z.center_z import research_center_z
from .etapa_z.run_z import run_etapa_z
from .forensic_a import forensic_rounds
from .history.backtest_w import run_etapa_w
from .history.coverage import full_coverage_report
from .history.diagnose_x import run_diagnose_x
from .history.exits_y import run_etapa_y
from .history.pipeline import run_expand, run_smoke, sync_coverage_to_db
from .history.schema import ensure_history_schema
from .improve import improve_report

router = APIRouter(prefix="/api/research", tags=["research"])

_BT_CACHE: dict[str, Any] | None = None
_BT_V_CACHE: dict[str, Any] | None = None
_BT_W_CACHE: dict[str, Any] | None = None
_DX_CACHE: dict[str, Any] | None = None
_EY_CACHE: dict[str, Any] | None = None
_EZ_CACHE: dict[str, Any] | None = None
_EAA_CACHE: dict[str, Any] | None = None
_EAB_CACHE: dict[str, Any] | None = None
_EAC_CACHE: dict[str, Any] | None = None
_BT_LOCK = asyncio.Lock()
_HIST_LOCK = asyncio.Lock()


def _load_json_artifact(*candidates: str) -> dict[str, Any] | None:
    from pathlib import Path
    import json

    for raw in candidates:
        p = Path(raw)
        try:
            if p.is_file() and p.stat().st_size > 100:
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict) and d.get("available"):
                    return d
        except Exception:
            continue
    return None


def _load_exits_y_artifact() -> dict[str, Any] | None:
    return _load_json_artifact(
        "/artifacts/history/etapa_y_results.json",
        "data/market_history/etapa_y_results.json",
    )


def _load_etapa_z_artifact() -> dict[str, Any] | None:
    return _load_json_artifact(
        "/artifacts/history/etapa_z_results.json",
        "data/market_history/etapa_z_results.json",
    )


def _load_etapa_aa_artifact() -> dict[str, Any] | None:
    return _load_json_artifact(
        "/artifacts/history/etapa_aa_results.json",
        "data/market_history/etapa_aa_results.json",
    )


def _load_etapa_ab_artifact() -> dict[str, Any] | None:
    return _load_json_artifact(
        "/artifacts/history/etapa_ab_results.json",
        "data/market_history/etapa_ab_results.json",
    )


def _load_etapa_ac_artifact() -> dict[str, Any] | None:
    return _load_json_artifact(
        "/artifacts/history/etapa_ac_results.json",
        "data/market_history/etapa_ac_results.json",
    )


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
async def research_center_api(
    run_backtest: bool = Query(False),
    run_backtest_w: bool = Query(False),
    run_diagnose_x: bool = Query(False),
    run_exits_y: bool = Query(False),
    run_etapa_z: bool = Query(False),
    run_etapa_aa: bool = Query(False),
    run_etapa_ab: bool = Query(False),
    run_etapa_ac: bool = Query(False),
):
    """Centro de Investigación de Estrategias (Etapa V/W/X/Y/Z/AA/AB/AC)."""
    from ..main import db, serial

    global _BT_V_CACHE, _BT_W_CACHE, _DX_CACHE, _EY_CACHE, _EZ_CACHE, _EAA_CACHE, _EAB_CACHE, _EAC_CACHE
    bt = _BT_V_CACHE
    btw = _BT_W_CACHE
    dx = _DX_CACHE
    ey = _EY_CACHE
    ez = _EZ_CACHE
    eaa = _EAA_CACHE
    eab = _EAB_CACHE
    eac = _EAC_CACHE
    if ey is None:
        ey = _load_exits_y_artifact()
        _EY_CACHE = ey
    if ez is None:
        ez = _load_etapa_z_artifact()
        _EZ_CACHE = ez
    if eaa is None:
        eaa = _load_etapa_aa_artifact()
        _EAA_CACHE = eaa
    if eab is None:
        eab = _load_etapa_ab_artifact()
        _EAB_CACHE = eab
    if eac is None:
        eac = _load_etapa_ac_artifact()
        _EAC_CACHE = eac
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
    if run_backtest_w:
        async with _BT_LOCK:
            try:
                _BT_W_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_w, ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
                    timeout=600,
                )
                btw = _BT_W_CACHE
            except Exception as exc:
                btw = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"declare_winner": False, "declare_profitable": False},
                }
    if run_diagnose_x:
        async with _BT_LOCK:
            try:
                _DX_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_diagnose_x, ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
                    timeout=600,
                )
                dx = _DX_CACHE
            except Exception as exc:
                dx = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"declare_profitable": False, "activate_strategy": False},
                }
    if run_exits_y:
        async with _BT_LOCK:
            try:
                _EY_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_y, ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
                    timeout=900,
                )
                ey = _EY_CACHE
            except Exception as exc:
                ey = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"activate": False, "declare_profitable": False},
                }
    if run_etapa_z:
        async with _BT_LOCK:
            try:
                _EZ_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_z, ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
                    timeout=900,
                )
                ez = _EZ_CACHE
            except Exception as exc:
                ez = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"activate": False, "verdict": "ERROR"},
                }
    if run_etapa_aa:
        async with _BT_LOCK:
            try:
                _EAA_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_aa),
                    timeout=1200,
                )
                eaa = _EAA_CACHE
            except Exception as exc:
                eaa = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"activate": False, "verdict": "INCONCLUSA"},
                }
    if run_etapa_ab:
        async with _BT_LOCK:
            try:
                _EAB_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_ab),
                    timeout=900,
                )
                eab = _EAB_CACHE
            except Exception as exc:
                eab = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"activate": False, "verdict": "SIN VENTAJA DEMOSTRADA"},
                }
    if run_etapa_ac:
        async with _BT_LOCK:
            try:
                _EAC_CACHE = await asyncio.wait_for(
                    asyncio.to_thread(run_etapa_ac),
                    timeout=300,
                )
                eac = _EAC_CACHE
            except Exception as exc:
                eac = {
                    "available": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "claim": {"activate": False},
                }
    with db() as c:
        base = research_center_y(
            c.execute,
            backtest_v=bt,
            backtest_w=btw,
            diagnose_x=dx,
            exits_y=ey,
        )
        zpay = research_center_z(base, ez)
        aapay = research_center_aa(zpay, eaa)
        abpay = research_center_ab(aapay, eab)
        return serial(research_center_ac(abpay, eac))


@router.get("/diagnose-x")
async def research_diagnose_x():
    from ..main import serial

    global _DX_CACHE
    async with _BT_LOCK:
        _DX_CACHE = await asyncio.to_thread(run_diagnose_x, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        return serial(_DX_CACHE)


@router.get("/exits-y")
async def research_exits_y():
    from ..main import serial

    global _EY_CACHE
    async with _BT_LOCK:
        _EY_CACHE = await asyncio.to_thread(run_etapa_y, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        return serial(_EY_CACHE)


@router.get("/etapa-z")
async def research_etapa_z():
    from ..main import serial

    global _EZ_CACHE
    async with _BT_LOCK:
        _EZ_CACHE = await asyncio.to_thread(run_etapa_z, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        return serial(_EZ_CACHE)


@router.get("/etapa-aa")
async def research_etapa_aa():
    from ..main import serial

    global _EAA_CACHE
    async with _BT_LOCK:
        _EAA_CACHE = await asyncio.to_thread(run_etapa_aa)
        return serial(_EAA_CACHE)


@router.get("/etapa-ab")
async def research_etapa_ab():
    from ..main import serial

    global _EAB_CACHE
    async with _BT_LOCK:
        _EAB_CACHE = await asyncio.to_thread(run_etapa_ab)
        return serial(_EAB_CACHE)


@router.get("/etapa-ac")
async def research_etapa_ac_api():
    from ..main import serial

    global _EAC_CACHE
    async with _BT_LOCK:
        _EAC_CACHE = await asyncio.to_thread(run_etapa_ac)
        return serial(_EAC_CACHE)


@router.get("/history/coverage")
async def research_history_coverage():
    from ..main import db, serial

    with db() as c:
        ensure_history_schema(c.execute)
        sync_coverage_to_db(c.execute)
    return serial(full_coverage_report())


@router.post("/history/smoke")
async def research_history_smoke():
    """Descarga+valida 1 mes BTCUSDT. No toca carteras."""
    from ..main import db, serial

    async with _HIST_LOCK:
        with db() as c:
            ensure_history_schema(c.execute)
            out = await run_smoke(execute=c.execute)
            sync_coverage_to_db(c.execute)
            return serial(out)


@router.post("/history/expand")
async def research_history_expand(
    start: str = Query("2024-11"),
    end: str = Query("2025-10"),
):
    """Amplía historial ~12m. Pesado; no bloquea runners (lock propio)."""
    from ..main import db, serial

    def _parse(ym: str) -> tuple[int, int]:
        y, m = ym.split("-")
        return int(y), int(m)

    async with _HIST_LOCK:
        with db() as c:
            ensure_history_schema(c.execute)
            out = await run_expand(start=_parse(start), end=_parse(end), execute=c.execute)
            sync_coverage_to_db(c.execute)
            return serial(out)


@router.get("/backtest-w")
async def research_backtest_w():
    from ..main import serial

    global _BT_W_CACHE
    async with _BT_LOCK:
        _BT_W_CACHE = await asyncio.to_thread(run_etapa_w, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        return serial(_BT_W_CACHE)
