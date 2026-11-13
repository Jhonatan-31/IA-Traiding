"""Public Binance market monitoring, paper-only, no private API keys or live trades."""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from psycopg.rows import dict_row

from . import alerts as alerts_mod
from . import chart_overlay
from . import indicators
from . import ohlcv as ohlcv_mod
from . import performance_compare
from . import risk as risk_mod
from .ml.schema import ensure_ml_schema
from .ml_api import router as ml_router
from .lab.schema import ensure_lab_schema
from .lab_api import router as lab_router
from .prospect.schema import ensure_prospect_schema
from .prospect_api import router as prospect_router
from .express.api import router as express_router
from .demo.api import router as demo_router
from .active.api import router as active_router
from .research.api import router as research_router

DATABASE_URL = os.environ["DATABASE_URL"]
BASE = "https://data-api.binance.vision/api/v3"
LIMIT = max(1, min(500, int(os.environ.get("SCAN_LIMIT", "25"))))
PERIOD = max(120, int(os.environ.get("SCAN_EVERY_SECONDS", "3600")))
START = Decimal("1000")
FEE = Decimal("0.001")
SLIP = Decimal("0.001")
STRATEGY = "SMA10_SMA50_1H"
MAX_POSITIONS = 10
BUDGET = Decimal("25")
MIN_BUDGET = Decimal("10")
MIN_QUOTE_VOLUME = Decimal("1000000")


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def setup():
    """Idempotent schema bootstrap. Additive only — never drops data."""
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY, cash NUMERIC NOT NULL)"
        )
        c.execute(
            "INSERT INTO account(id, cash) VALUES(1, %s) ON CONFLICT DO NOTHING",
            (START,),
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS positions(
                symbol TEXT PRIMARY KEY,
                qty NUMERIC NOT NULL,
                cost NUMERIC NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS trades(
                id BIGSERIAL PRIMARY KEY,
                at TIMESTAMPTZ DEFAULT NOW(),
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty NUMERIC NOT NULL,
                price NUMERIC NOT NULL,
                candle_ms BIGINT NOT NULL,
                UNIQUE(symbol, side, candle_ms)
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS scans(
                id BIGSERIAL PRIMARY KEY,
                at TIMESTAMPTZ DEFAULT NOW(),
                markets INT,
                errors INT,
                equity NUMERIC
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS prices(
                symbol TEXT PRIMARY KEY,
                price NUMERIC NOT NULL,
                at TIMESTAMPTZ DEFAULT NOW()
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS engine_state(
                id INTEGER PRIMARY KEY,
                paused BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                reason TEXT
            )"""
        )
        c.execute(
            "INSERT INTO engine_state(id, paused, reason) VALUES(1, FALSE, 'boot') ON CONFLICT DO NOTHING"
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS audit_log(
                id BIGSERIAL PRIMARY KEY,
                at TIMESTAMPTZ DEFAULT NOW(),
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS collector_events(
                id BIGSERIAL PRIMARY KEY,
                at TIMESTAMPTZ DEFAULT NOW(),
                level TEXT NOT NULL,
                message TEXT NOT NULL
            )"""
        )
        for stmt in (
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS fee_rate NUMERIC",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS slip_rate NUMERIC",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy TEXT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS reason TEXT",
            "ALTER TABLE prices ADD COLUMN IF NOT EXISTS source TEXT",
            "ALTER TABLE scans ADD COLUMN IF NOT EXISTS cycle_ms INTEGER",
            "ALTER TABLE scans ADD COLUMN IF NOT EXISTS last_candle_ms BIGINT",
        ):
            c.execute(stmt)
        alerts_mod.ensure_alert_schema(c.execute)
        ensure_ml_schema(c.execute)
        ensure_prospect_schema(c.execute)
        ensure_lab_schema(c.execute)


def log_event(level: str, message: str) -> None:
    try:
        with db() as c:
            c.execute(
                "INSERT INTO collector_events(level, message) VALUES(%s,%s)",
                (level, message[:500]),
            )
    except Exception:
        print("EVENT_LOG_FAIL", level, message, flush=True)


def is_paused() -> bool:
    with db() as c:
        row = c.execute("SELECT paused FROM engine_state WHERE id=1").fetchone()
        return bool(row and row["paused"])


def set_paused(paused: bool, reason: str, actor: str = "api") -> dict:
    with db() as c:
        c.execute(
            "UPDATE engine_state SET paused=%s, updated_at=NOW(), reason=%s WHERE id=1",
            (paused, reason),
        )
        c.execute(
            "INSERT INTO audit_log(actor, action, detail) VALUES(%s,%s,%s)",
            (actor, "PAUSE" if paused else "RESUME", reason),
        )
        row = c.execute("SELECT * FROM engine_state WHERE id=1").fetchone()
    return serial(row)


def signal(bars):
    """Only closed bars must be passed by caller."""
    if len(bars) < 51:
        return "HOLD"
    closes = [Decimal(str(r[4])) for r in bars]
    a = sum(closes[-10:]) / 10
    b = sum(closes[-50:]) / 50
    pa = sum(closes[-11:-1]) / 10
    pb = sum(closes[-51:-1]) / 50
    if pa <= pb and a > b:
        return "BUY"
    if pa >= pb and a < b:
        return "SELL"
    return "HOLD"


async def get(client: httpx.AsyncClient, path: str, retries: int = 4, **params):
    delay = 1.0
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            r = await client.get(BASE + path, params=params)
            if r.status_code in (418, 429):
                last_exc = RuntimeError(f"API rate limited HTTP {r.status_code}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 500:
                last_exc = RuntimeError(f"API upstream HTTP {r.status_code}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            last_exc = exc
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"Binance request failed after retries: {last_exc}")


def _record_scan(scanned, errors, equity, cycle_ms, last_candle_ms):
    with db() as c:
        c.execute(
            """INSERT INTO scans(markets, errors, equity, cycle_ms, last_candle_ms)
               VALUES(%s,%s,%s,%s,%s)""",
            (scanned, errors, equity, cycle_ms, last_candle_ms),
        )


async def cycle(client: httpx.AsyncClient):
    t0 = time.perf_counter()
    last_candle_ms = None
    if is_paused():
        print("PAPER_ONLY paused — skipping entries/exits", flush=True)
        with db() as c:
            holdings = list(c.execute("SELECT * FROM positions"))
            cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        try:
            allprices = await get(client, "/ticker/price")
            lookup = {x["symbol"]: Decimal(str(x["price"])) for x in allprices}
            with db() as c:
                for p in holdings:
                    if p["symbol"] in lookup:
                        c.execute(
                            """INSERT INTO prices(symbol, price, source) VALUES(%s,%s,'live_ticker')
                               ON CONFLICT(symbol) DO UPDATE
                               SET price=excluded.price, at=NOW(), source=excluded.source""",
                            (p["symbol"], lookup[p["symbol"]]),
                        )
                equity = (
                    cash + sum(p["qty"] * lookup[p["symbol"]] for p in holdings)
                    if holdings and all(p["symbol"] in lookup for p in holdings)
                    else cash
                )
            cycle_ms = int((time.perf_counter() - t0) * 1000)
            _record_scan(0, 0, equity, cycle_ms, None)
            print("PAPER_ONLY paused markets 0 errors 0 equity", equity, flush=True)
        except Exception as exc:
            log_event("ERROR", f"paused_refresh {type(exc).__name__}: {exc}")
            print("COLLECTOR_ERROR paused_refresh", type(exc).__name__, str(exc), flush=True)
        return

    info = await get(client, "/exchangeInfo")
    candidates = {
        s["symbol"]
        for s in info["symbols"]
        if s.get("status") == "TRADING"
        and s.get("quoteAsset") == "USDT"
        and s.get("isSpotTradingAllowed")
    }
    tickers = await get(client, "/ticker/24hr")
    eligible = sorted(
        (
            (Decimal(str(t.get("quoteVolume", 0))), t["symbol"])
            for t in tickers
            if t["symbol"] in candidates
            and Decimal(str(t.get("quoteVolume", 0))) >= MIN_QUOTE_VOLUME
        ),
        reverse=True,
    )
    selected = [s for _, s in eligible[:LIMIT]]
    with db() as c:
        held = [r["symbol"] for r in c.execute("SELECT symbol FROM positions")]
    selected = list(dict.fromkeys(selected + held))

    errors = 0
    scanned = 0
    for symbol in selected:
        try:
            rows = await get(client, "/klines", symbol=symbol, interval="1h", limit=55)
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            bars = [r for r in rows if int(r[6]) < now]  # closed only for signals
            if len(bars) < 51:
                continue
            end = int(bars[-1][6])
            last_candle_ms = end
            price = Decimal(str(bars[-1][4]))
            side = signal(bars)
            with db() as c:
                c.execute(
                    """INSERT INTO prices(symbol, price, source) VALUES(%s,%s,'closed_candle')
                       ON CONFLICT(symbol) DO UPDATE
                       SET price=excluded.price, at=NOW(), source=excluded.source""",
                    (symbol, price),
                )
                past = c.execute(
                    "SELECT 1 FROM trades WHERE symbol=%s AND side=%s AND candle_ms=%s",
                    (symbol, side, end),
                ).fetchone()
                position = c.execute(
                    "SELECT * FROM positions WHERE symbol=%s", (symbol,)
                ).fetchone()
                if side == "BUY" and not past and not position:
                    breaker = c.execute(
                        "SELECT active, reason FROM circuit_breaker_state WHERE id=1"
                    ).fetchone()
                    if breaker and breaker.get("active"):
                        log_event(
                            "WARN",
                            f"circuit_breaker_block_buy {symbol} {breaker.get('reason')}",
                        )
                    else:
                        n = c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
                        cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
                        budget = min(BUDGET, cash)
                        if n < MAX_POSITIONS and budget >= MIN_BUDGET:
                            fill = price * (1 + SLIP)
                            qty = (budget * (1 - FEE)) / fill
                            c.execute("UPDATE account SET cash=cash-%s WHERE id=1", (budget,))
                            c.execute(
                                "INSERT INTO positions VALUES(%s,%s,%s)",
                                (symbol, qty, budget),
                            )
                            c.execute(
                                """INSERT INTO trades(symbol,side,qty,price,candle_ms,fee_rate,slip_rate,strategy,reason)
                                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (
                                    symbol,
                                    "BUY",
                                    qty,
                                    fill,
                                    end,
                                    FEE,
                                    SLIP,
                                    STRATEGY,
                                    "sma10_cross_above_sma50",
                                ),
                            )
                elif side == "SELL" and not past and position:
                    qty = position["qty"]
                    fill = price * (1 - SLIP)
                    proceeds = qty * fill * (1 - FEE)
                    c.execute("UPDATE account SET cash=cash+%s WHERE id=1", (proceeds,))
                    c.execute("DELETE FROM positions WHERE symbol=%s", (symbol,))
                    c.execute(
                        """INSERT INTO trades(symbol,side,qty,price,candle_ms,fee_rate,slip_rate,strategy,reason)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            symbol,
                            "SELL",
                            qty,
                            fill,
                            end,
                            FEE,
                            SLIP,
                            STRATEGY,
                            "sma10_cross_below_sma50",
                        ),
                    )
            scanned += 1
        except (httpx.HTTPError, ValueError, KeyError, IndexError, RuntimeError) as e:
            errors += 1
            log_event("ERROR", f"MARKET_ERROR {symbol}: {e}")
            print("MARKET_ERROR", symbol, str(e), flush=True)
        await asyncio.sleep(0.15)

    allprices = await get(client, "/ticker/price")
    lookup = {x["symbol"]: Decimal(str(x["price"])) for x in allprices}
    with db() as c:
        holdings = list(c.execute("SELECT * FROM positions"))
        cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        for sym in {p["symbol"] for p in holdings} | set(selected):
            if sym in lookup:
                c.execute(
                    """INSERT INTO prices(symbol, price, source) VALUES(%s,%s,'live_ticker')
                       ON CONFLICT(symbol) DO UPDATE
                       SET price=excluded.price, at=NOW(), source=excluded.source""",
                    (sym, lookup[sym]),
                )
        equity = (
            cash + sum(p["qty"] * lookup[p["symbol"]] for p in holdings)
            if all(p["symbol"] in lookup for p in holdings)
            else None
        )
    cycle_ms = int((time.perf_counter() - t0) * 1000)
    _record_scan(scanned, errors, equity, cycle_ms, last_candle_ms)
    print(
        "PAPER_ONLY markets",
        scanned,
        "errors",
        errors,
        "equity",
        equity,
        "cycle_ms",
        cycle_ms,
        flush=True,
    )
    try:
        await _refresh_alerts_safe()
    except Exception as exc:
        log_event("ERROR", f"alerts_eval {type(exc).__name__}: {exc}")


async def _binance_probe() -> dict:
    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(
            timeout=10, headers={"User-Agent": "ResearchPaperBot/0.5-diag"}
        ) as client:
            r = await client.get(BASE + "/ping")
            r.raise_for_status()
            latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            return {
                "status": "ok",
                "http_status": r.status_code,
                "latency_ms": round(latency_ms, 1),
                "base": BASE,
                "checked_at": started.isoformat(),
            }
    except Exception as exc:
        return {
            "status": "error",
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
            "base": BASE,
            "checked_at": started.isoformat(),
        }


def _load_risk_report() -> dict:
    with db() as c:
        cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        positions = list(
            c.execute(
                """SELECT p.*, pr.price, pr.source AS price_source
                   FROM positions p LEFT JOIN prices pr USING(symbol)"""
            )
        )
        trades = list(c.execute("SELECT * FROM trades ORDER BY id"))
        scans = list(c.execute("SELECT * FROM scans ORDER BY id"))
        limits = c.execute("SELECT * FROM risk_limits WHERE id=1").fetchone() or {}
    return risk_mod.build_risk_report(
        cash=Decimal(str(cash)),
        positions=positions,
        trades=trades,
        scans=scans,
        initial_capital=START,
        limits=dict(limits),
    )


async def _refresh_alerts_safe():
    binance = await _binance_probe()
    db_status = "ok"
    try:
        with db() as c:
            c.execute("SELECT 1")
            last_scan = c.execute(
                "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
            price_age = c.execute("SELECT MAX(at) AS at FROM prices").fetchone()
    except Exception:
        db_status = "error"
        last_scan = None
        price_age = None
    system = {
        "db": db_status,
        "binance": binance,
        "last_scan": serial(last_scan) if last_scan else None,
        "prices_max_at": serial(price_age["at"]) if price_age and price_age["at"] else None,
        "scan_every_seconds": PERIOD,
    }
    risk_report = _load_risk_report() if db_status == "ok" else {"breaches": []}
    alerts_mod.evaluate_alerts(db, risk_report, system)


async def work():
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/0.5"}
    ) as client:
        while True:
            try:
                await cycle(client)
                # Etapa F: resolve completed Shadow horizons (no orders)
                try:
                    from .ml.resolve import resolve_pending_predictions

                    summary = await resolve_pending_predictions(db, limit=50)
                    if summary.get("resolved"):
                        print("SHADOW_RESOLVE", summary["resolved"], flush=True)
                except Exception as rex:
                    print("SHADOW_RESOLVE_ERR", type(rex).__name__, rex, flush=True)
                # Etapa H: prospective resolve + occasional SHADOW_LIVE log (no SMA capital)
                try:
                    from .prospect.resolve import resolve_pending as prospect_resolve

                    ps = await prospect_resolve(db, limit=50)
                    if ps.get("resolved") or ps.get("invalid"):
                        print(
                            "PROSPECT_RESOLVE",
                            ps.get("resolved"),
                            ps.get("invalid"),
                            flush=True,
                        )
                except Exception as pex:
                    print("PROSPECT_RESOLVE_ERR", type(pex).__name__, pex, flush=True)
            except Exception as exc:
                log_event("ERROR", f"COLLECTOR_ERROR {type(exc).__name__}: {exc}")
                print("COLLECTOR_ERROR", type(exc).__name__, str(exc), flush=True)
            await asyncio.sleep(PERIOD)


async def _reliability_sampler_loop():
    """AF: accumulate real SLI samples without relying on dashboard polling."""
    from .ops.reliability import SAMPLE_INTERVAL_S, probe_and_record_sample

    await asyncio.sleep(8)
    while True:
        try:
            with db() as c:
                probe_and_record_sample(c.execute, source="background")
        except Exception:
            pass
        await asyncio.sleep(max(30, int(SAMPLE_INTERVAL_S)))


@asynccontextmanager
async def lifespan(app):
    for attempt in range(30):
        try:
            setup()
            break
        except psycopg.OperationalError:
            if attempt == 29:
                raise
            await asyncio.sleep(2)
    sampler = asyncio.create_task(_reliability_sampler_loop())
    try:
        yield
    finally:
        sampler.cancel()
        try:
            await sampler
        except asyncio.CancelledError:
            pass


app = FastAPI(title="AI Trading Bot - PAPER ONLY", lifespan=lifespan)
app.include_router(ml_router)
app.include_router(prospect_router)
app.include_router(lab_router)
app.include_router(express_router)
app.include_router(demo_router)
app.include_router(active_router)
app.include_router(research_router)


@app.middleware("http")
async def dashboard_read_auth_middleware(request, call_next):
    """AH: enforce read auth only when DASHBOARD_READ_AUTH is enabled (header or cookie)."""
    from .ops.access_guard import (
        extract_read_credential,
        path_requires_read_auth,
        read_auth_enabled,
        record_denial,
        token_matches,
    )

    path = request.url.path
    if read_auth_enabled() and path_requires_read_auth(path):
        from fastapi.responses import JSONResponse

        expected = str(os.environ.get("DASHBOARD_READ_TOKEN", "")).strip()
        if not expected:
            return JSONResponse(
                status_code=503,
                content={"detail": "dashboard_read_token_not_configured"},
            )
        got = extract_read_credential(request)
        if not token_matches(got):
            record_denial(path, "unauthorized")
            return JSONResponse(
                status_code=401,
                content={"detail": "unauthorized_dashboard_read"},
            )
    return await call_next(request)


def serial(rows):
    def normalize(x):
        if isinstance(x, Decimal):
            return float(x)
        if isinstance(x, datetime):
            return x.isoformat()
        if isinstance(x, dict):
            return {k: normalize(v) for k, v in x.items()}
        if isinstance(x, list):
            return [normalize(v) for v in x]
        return x

    return normalize(rows)


def _age_seconds(ts) -> float | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - ts).total_seconds()


def _status_from_age(age: float | None, warn_s: float, err_s: float) -> str:
    if age is None:
        return "UNKNOWN"
    if age <= warn_s:
        return "OK"
    if age <= err_s:
        return "WARNING"
    return "ERROR"


@app.get("/api/overview")
def overview():
    with db() as c:
        cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        scan = c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        pos = c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
        trades = c.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
        invested = c.execute(
            "SELECT COALESCE(SUM(cost),0) AS v FROM positions"
        ).fetchone()["v"]
        engine = c.execute("SELECT * FROM engine_state WHERE id=1").fetchone()
        mv = c.execute(
            """SELECT COALESCE(SUM(p.qty * pr.price),0) AS v
               FROM positions p LEFT JOIN prices pr USING(symbol)"""
        ).fetchone()["v"]
        open_alerts = c.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE status='OPEN'"
        ).fetchone()["n"]
    equity = float(cash) + float(mv) if mv is not None else None
    return serial(
        {
            "mode": "PAPER_ONLY",
            "initial_capital": float(START),
            "cash": cash,
            "invested_cost": invested,
            "positions_market_value": mv,
            "equity_estimate": equity,
            "latest": scan,
            "positions": pos,
            "trades": trades,
            "engine": engine,
            "open_alerts": open_alerts,
            "strategy": STRATEGY,
            "disclaimer": "Simulación ilustrativa. No es consejo financiero ni promesa de ganancias.",
        }
    )


@app.get("/api/trades")
def trades(limit: int = 50):
    limit = max(1, min(500, limit))
    with db() as c:
        return serial(
            list(c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT %s", (limit,)))
        )


@app.get("/api/positions")
def positions():
    with db() as c:
        return serial(
            list(
                c.execute(
                    """SELECT p.*, pr.price, pr.source AS price_source, pr.at AS price_at,
                              p.qty * pr.price AS market_value,
                              (p.qty * pr.price) - p.cost AS unrealized_pnl
                       FROM positions p
                       LEFT JOIN prices pr USING(symbol)
                       ORDER BY symbol"""
                )
            )
        )


@app.get("/api/scans")
def scans():
    with db() as c:
        return serial(
            list(
                c.execute(
                    "SELECT * FROM (SELECT * FROM scans ORDER BY id DESC LIMIT 100) x ORDER BY id"
                )
            )
        )


@app.get("/api/markets")
def markets():
    with db() as c:
        return serial(
            list(
                c.execute(
                    """SELECT symbol, price, source, at,
                              EXISTS(SELECT 1 FROM positions p WHERE p.symbol=prices.symbol) AS has_position
                       FROM prices ORDER BY symbol"""
                )
            )
        )


@app.get("/api/health")
def health():
    payload = {
        "status": "ok",
        "mode": "PAPER_ONLY",
        "db": "unknown",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with db() as c:
            c.execute("SELECT 1 AS ok")
            engine = c.execute("SELECT paused FROM engine_state WHERE id=1").fetchone()
        payload["db"] = "ok"
        payload["paused"] = bool(engine and engine["paused"])
        return payload
    except Exception as exc:
        payload["status"] = "error"
        payload["db"] = "error"
        payload["error"] = type(exc).__name__
        raise HTTPException(status_code=503, detail=payload) from exc


@app.get("/api/auth/status")
def auth_status(request: Request):
    """AH: estado de auth de lectura — sin secretos. Público (necesario para UI)."""
    from .ops.access_guard import (
        extract_read_credential,
        read_auth_enabled,
        read_auth_status,
        token_matches,
        websocket_policy,
    )

    st = read_auth_status()
    authed = False
    if read_auth_enabled():
        authed = token_matches(extract_read_credential(request))
    return {
        "mode": "PAPER_ONLY",
        "read_auth": st,
        "session_valid": authed if st.get("enforced") else True,
        "websocket_policy": websocket_policy(),
        "roles": {
            "visitor": "solo estáticos + /api/public/* + /api/health + /api/auth/*",
            "reader": "consulta dashboard; sin mutaciones de bots",
            "control": "mutaciones con X-Lab-Token (separado)",
        },
    }


@app.post("/api/auth/login")
async def auth_login(request: Request):
    """AH: establece cookie HttpOnly de lectura. No-op útil cuando auth OFF."""
    from .ops.access_guard import (
        read_auth_enabled,
        set_session_cookie,
        token_matches,
    )
    from fastapi.responses import JSONResponse

    try:
        body = await request.json()
    except Exception:
        body = {}
    token = str((body or {}).get("token") or "").strip()
    if not read_auth_enabled():
        return {
            "ok": True,
            "enforced": False,
            "status": "PREPARADO_SIN_ACTIVAR",
            "message": "Auth de lectura no está activa; no se requiere acceso.",
        }
    from .ops.access_guard import check_login_rate_limit, record_denial

    client_key = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(client_key):
        record_denial("/api/auth/login", "rate_limited")
        raise HTTPException(status_code=429, detail="too_many_login_attempts")
    if not token_matches(token):
        record_denial("/api/auth/login", "login_invalid")
        raise HTTPException(status_code=401, detail="unauthorized_dashboard_read")
    secure = request.url.scheme == "https" or (
        str(request.headers.get("x-forwarded-proto", "")).lower() == "https"
    )
    resp = JSONResponse(
        content={
            "ok": True,
            "enforced": True,
            "secure_cookie": secure,
            "message": "Sesión de lectura iniciada.",
        }
    )
    set_session_cookie(resp, token, secure=secure)
    return resp


@app.post("/api/auth/logout")
def auth_logout():
    from .ops.access_guard import clear_session_cookie
    from fastapi.responses import JSONResponse

    resp = JSONResponse(content={"ok": True, "message": "Sesión cerrada."})
    clear_session_cookie(resp)
    return resp


@app.get("/api/public/health")
def public_health():
    """
    AF5/AF6: endpoint mínimo de observación — sin balances, posiciones, estrategias ni secretos.
    Apto para probe externo futuro (NOT_CONFIGURED hasta autorización).
    """
    out = {
        "ok": False,
        "service": "ia-bot-trading",
        "mode": "PAPER_ONLY",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "db": "unknown",
        "deploy_commit": None,
    }
    try:
        with db() as c:
            c.execute("SELECT 1")
            out["db"] = "ok"
            try:
                from .ops.health_center import ensure_continuity_schema

                ensure_continuity_schema(c.execute)
                row = c.execute("SELECT git_commit FROM deploy_meta WHERE id=1").fetchone()
                out["deploy_commit"] = (row or {}).get("git_commit")
            except Exception:
                pass
        out["ok"] = True
        return out
    except Exception as exc:
        out["db"] = "error"
        out["error_type"] = type(exc).__name__
        raise HTTPException(status_code=503, detail=out) from exc


@app.get("/api/system")
async def system():
    t_api = time.perf_counter()
    binance = await _binance_probe()
    api_ms = round((time.perf_counter() - t_api) * 1000, 1)
    with db() as c:
        from .prospect.schema import ensure_prospect_schema
        from .prospect.decisions import decision_counts as prospect_decision_counts

        ensure_prospect_schema(c.execute)
        engine = c.execute("SELECT * FROM engine_state WHERE id=1").fetchone()
        last_scan = c.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_trade = c.execute(
            "SELECT at FROM trades ORDER BY id DESC LIMIT 1"
        ).fetchone()
        price_age = c.execute("SELECT MAX(at) AS at FROM prices").fetchone()
        audit = list(c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 20"))
        events = list(
            c.execute(
                "SELECT * FROM collector_events ORDER BY id DESC LIMIT 30"
            )
        )
        open_alerts = c.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE status='OPEN'"
        ).fetchone()["n"]
        failed_reqs = c.execute(
            "SELECT COUNT(*) AS n FROM collector_events WHERE level='ERROR' AND at > NOW() - INTERVAL '24 hours'"
        ).fetchone()["n"]
        counts = {
            "positions": c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"],
            "trades": c.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"],
            "prices": c.execute("SELECT COUNT(*) AS n FROM prices").fetchone()["n"],
            "scans": c.execute("SELECT COUNT(*) AS n FROM scans").fetchone()["n"],
        }
        sched = c.execute(
            "SELECT * FROM shadow_scheduler_state WHERE id=1"
        ).fetchone()
        demo_st = None
        active_st = None
        try:
            demo_st = c.execute("SELECT * FROM demo_state WHERE id=1").fetchone()
        except Exception:
            demo_st = None
        try:
            active_st = c.execute("SELECT * FROM active_state WHERE id=1").fetchone()
        except Exception:
            active_st = None
        demo_pos_n = 0
        active_pos_n = 0
        try:
            demo_pos_n = int(
                c.execute("SELECT COUNT(*) AS n FROM demo_positions").fetchone()["n"]
            )
            active_pos_n = int(
                c.execute("SELECT COUNT(*) AS n FROM active_positions").fetchone()["n"]
            )
        except Exception:
            pass
        last_pred = c.execute(
            """SELECT MAX(d.created_at) AS at FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE'"""
        ).fetchone()
        last_res = c.execute(
            "SELECT MAX(resolved_at) AS at FROM prospect_outcomes"
        ).fetchone()
        prospect_counts = prospect_decision_counts(c.execute, "SHADOW_LIVE")
        prospect_open_alerts = c.execute(
            "SELECT COUNT(*) AS n FROM prospect_alerts WHERE status='OPEN'"
        ).fetchone()["n"]
        recent_cycles = list(
            c.execute(
                """SELECT id, started_at, finished_at, ok, decisions_new, resolved, invalid, error
                   FROM shadow_scheduler_cycles ORDER BY id DESC LIMIT 10"""
            )
        )

    from .ops.continuity import classify_gap, heartbeat_gap_seconds, reconcile_after_gap

    scan_age = _age_seconds(last_scan["at"] if last_scan else None)
    price_age_s = _age_seconds(price_age["at"] if price_age else None)
    hb_age = _age_seconds(sched["heartbeat_at"] if sched else None)
    demo_hb_age = heartbeat_gap_seconds(demo_st["heartbeat_at"] if demo_st else None)
    active_hb_age = heartbeat_gap_seconds(active_st["heartbeat_at"] if active_st else None)
    demo_gap = classify_gap(demo_hb_age, warn_s=180, crit_s=600, expected_every_s=60)
    active_gap = classify_gap(active_hb_age, warn_s=180, crit_s=600, expected_every_s=60)
    continuity = reconcile_after_gap(
        gap_s=max(
            [x for x in (demo_hb_age, active_hb_age, hb_age) if x is not None],
            default=None,
        ),
        price_age_s=price_age_s,
        open_positions=demo_pos_n + active_pos_n,
    )
    # Evidence-based: container up ≠ healthy. Heartbeat must be fresh.
    if not sched or not sched.get("heartbeat_at"):
        sched_status = "UNKNOWN"
    elif sched.get("status") == "ERROR":
        sched_status = "ERROR"
    else:
        sched_status = _status_from_age(hb_age, 600, 900)
    components = {
        "fastapi": {
            "status": "OK",
            "evidence": f"handler_latency_ms={api_ms}",
            "latency_ms": api_ms,
        },
        "postgres": {"status": "OK", "evidence": "SELECT 1 succeeded"},
        "binance": {
            "status": "OK"
            if binance.get("status") == "ok"
            else "ERROR",
            "evidence": binance,
            "latency_ms": binance.get("latency_ms"),
        },
        "worker": {
            "status": _status_from_age(scan_age, PERIOD * 1.5, PERIOD * 3),
            "evidence": {
                "last_scan_at": serial(last_scan["at"]) if last_scan else None,
                "age_seconds": scan_age,
                "cycle_ms": last_scan.get("cycle_ms") if last_scan else None,
                "markets": last_scan.get("markets") if last_scan else None,
                "errors": last_scan.get("errors") if last_scan else None,
                "last_candle_ms": last_scan.get("last_candle_ms") if last_scan else None,
            },
        },
        "market_data": {
            "status": _status_from_age(price_age_s, PERIOD * 1.5, PERIOD * 3),
            "evidence": {
                "prices_max_at": serial(price_age["at"]) if price_age else None,
                "age_seconds": price_age_s,
            },
        },
        "engine": {
            "status": "WARNING" if engine and engine["paused"] else "OK",
            "evidence": serial(engine),
        },
        "shadow_scheduler": {
            "status": sched_status,
            "evidence": {
                "db_status": sched.get("status") if sched else None,
                "heartbeat_at": serial(sched["heartbeat_at"]) if sched and sched.get("heartbeat_at") else None,
                "heartbeat_age_s": hb_age,
                "last_cycle_at": serial(sched["last_cycle_at"]) if sched and sched.get("last_cycle_at") else None,
                "last_cycle_ok": sched.get("last_cycle_ok") if sched else None,
                "last_inference_at": serial(sched["last_inference_at"]) if sched and sched.get("last_inference_at") else None,
                "last_resolve_at": serial(sched["last_resolve_at"]) if sched and sched.get("last_resolve_at") else None,
                "last_prediction_at": serial(last_pred["at"]) if last_pred and last_pred.get("at") else None,
                "last_outcome_at": serial(last_res["at"]) if last_res and last_res.get("at") else None,
                "pending": prospect_counts.get("PENDING"),
                "resolved": prospect_counts.get("RESOLVED"),
                "invalid": prospect_counts.get("INVALID"),
                "inference_errors": sched.get("inference_errors") if sched else None,
                "resolve_errors": sched.get("resolve_errors") if sched else None,
                "connection_errors": sched.get("connection_errors") if sched else None,
                "active_model_version": sched.get("active_model_version") if sched else None,
                "last_error": sched.get("last_error") if sched else None,
                "cycle_count": sched.get("cycle_count") if sched else None,
                "note": "Salud por heartbeat DB, no por contenedor Docker.",
            },
        },
        "demo_runner": {
            "status": demo_gap["status"] if demo_st else "UNKNOWN",
            "evidence": {
                "bot_status": (demo_st or {}).get("status"),
                "heartbeat_at": serial(demo_st["heartbeat_at"]) if demo_st and demo_st.get("heartbeat_at") else None,
                "heartbeat_age_s": demo_hb_age,
                "last_eval_at": serial(demo_st["last_eval_at"]) if demo_st and demo_st.get("last_eval_at") else None,
                "open_positions": demo_pos_n,
                "gap": demo_gap,
                "note": (
                    "Sin posiciones ≠ supervisor sano. "
                    "Si runner detenido, no afirmar protecciones activas."
                ),
            },
        },
        "active_runner": {
            "status": active_gap["status"] if active_st else "UNKNOWN",
            "evidence": {
                "bot_status": (active_st or {}).get("status"),
                "heartbeat_at": serial(active_st["heartbeat_at"]) if active_st and active_st.get("heartbeat_at") else None,
                "heartbeat_age_s": active_hb_age,
                "last_eval_at": serial(active_st["last_eval_at"]) if active_st and active_st.get("last_eval_at") else None,
                "open_positions": active_pos_n,
                "gap": active_gap,
                "note": (
                    "Entradas gated por B_EXECUTION_AUTHORIZED + RUNNING; "
                    "salidas protectoras deben evaluarse aunque entradas bloqueadas."
                ),
            },
        },
    }
    from .ops.continuity import safe_auto_recoveries
    from .ops.health_center import (
        build_continuity_snapshot,
        ensure_continuity_schema,
        record_gap_if_needed,
    )

    deploy_meta = None
    recent_gaps: list = []
    try:
        with db() as c2:
            ensure_continuity_schema(c2.execute)
            record_gap_if_needed(
                c2.execute, source="demo_runner", gap=demo_gap, open_positions=demo_pos_n
            )
            record_gap_if_needed(
                c2.execute, source="active_runner", gap=active_gap, open_positions=active_pos_n
            )
            deploy_meta = c2.execute("SELECT * FROM deploy_meta WHERE id=1").fetchone()
            recent_gaps = list(
                c2.execute(
                    """SELECT id, detected_at, source, gap_s, status, host_suspend_suspected,
                              open_positions, resolved_at
                       FROM continuity_gap_events ORDER BY id DESC LIMIT 20"""
                )
            )
    except Exception:
        pass

    continuity_center = build_continuity_snapshot(
        demo_st=demo_st,
        active_st=active_st,
        demo_pos_n=demo_pos_n,
        active_pos_n=active_pos_n,
        price_age_s=price_age_s,
        shadow_hb=sched["heartbeat_at"] if sched else None,
        worker_scan_age_s=scan_age,
        deploy_meta=serial(deploy_meta) if deploy_meta else None,
        recent_gaps=serial(recent_gaps),
    )

    reliability = None
    try:
        from .ops.reliability import maybe_record_sample, reliability_dashboard

        demo_fn = (
            (continuity_center.get("services") or {}).get("demo_runner") or {}
        ).get("functional_status") or "UNKNOWN"
        active_fn = (
            (continuity_center.get("services") or {}).get("active_runner") or {}
        ).get("functional_status") or "UNKNOWN"
        with db() as c3:
            maybe_record_sample(
                c3.execute,
                api_ok=True,
                db_ok=True,
                demo_functional=str(demo_fn),
                active_functional=str(active_fn),
                market_stale=bool((continuity or {}).get("stale_prices")),
                detail={"source": "api_system"},
            )
            reliability = reliability_dashboard(c3.execute)
    except Exception:
        reliability = {"error": "reliability_unavailable", "external_monitor": {"status": "NOT_CONFIGURED"}}

    security_recovery = None
    try:
        from .ops.security_recovery import security_recovery_dashboard

        with db() as c4:
            security_recovery = security_recovery_dashboard(c4.execute)
    except Exception:
        security_recovery = {"error": "security_recovery_unavailable"}

    critical = list(continuity_center.get("critical_alerts") or [])
    for a in (
        {
            "id": "demo_runner_gap",
            "severity": demo_gap["status"],
            "message": f"demo heartbeat gap={demo_gap.get('gap_s')}s",
            "open_positions": demo_pos_n,
        }
        if demo_gap["status"] in ("WARNING", "CRITICAL", "UNKNOWN")
        else None,
        {
            "id": "active_runner_gap",
            "severity": active_gap["status"],
            "message": f"active heartbeat gap={active_gap.get('gap_s')}s",
            "open_positions": active_pos_n,
        }
        if active_gap["status"] in ("WARNING", "CRITICAL", "UNKNOWN")
        else None,
    ):
        if a and a["id"] not in {x.get("id") for x in critical}:
            critical.append(a)

    return serial(
        {
            "mode": "PAPER_ONLY",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "continuity": continuity,
            "continuity_center": continuity_center,
            "reliability": reliability,
            "security_recovery": security_recovery,
            "auto_recovery_policy": safe_auto_recoveries(),
            "critical_alerts": critical,
            "engine": engine,
            "last_scan": last_scan,
            "last_trade_at": last_trade["at"] if last_trade else None,
            "prices_max_at": price_age["at"] if price_age else None,
            "counts": counts,
            "binance_base": BASE,
            "binance": binance,
            "scan_limit": LIMIT,
            "scan_every_seconds": PERIOD,
            "failed_requests_24h": failed_reqs,
            "open_alerts": open_alerts,
            "prospect_open_alerts": prospect_open_alerts,
            "shadow_scheduler": sched,
            "shadow_scheduler_cycles": recent_cycles,
            "recent_errors": events,
            "audit": audit,
            "ohlcv_cache": ohlcv_mod.cache_stats(),
            "notes": [
                "Sin acceso al socket Docker desde el dashboard.",
                "CPU/RAM host: usar docker stats en el host EBZ.",
                "UNKNOWN/WARNING/ERROR se basan en evidencia temporal.",
                "shadow_scheduler: heartbeat >900s ⇒ ERROR; contenedor up ≠ saludable.",
                "OK_SNAPSHOT ≠ prueba de continuidad 24/7 longitudinal.",
                "Dashboard :8090 en LAN sin auth de lectura — no equivale a autenticación.",
            ],
        }
    )


@app.get("/api/continuity")
async def continuity_center_api():
    """Centro de salud y continuidad — evidencia de aplicación, no Docker socket."""
    system_payload = await system()
    return {
        "mode": "PAPER_ONLY",
        "continuity_center": system_payload.get("continuity_center"),
        "continuity": system_payload.get("continuity"),
        "critical_alerts": system_payload.get("critical_alerts"),
        "auto_recovery_policy": system_payload.get("auto_recovery_policy"),
        "components": {
            k: system_payload.get("components", {}).get(k)
            for k in ("demo_runner", "active_runner", "shadow_scheduler", "worker", "postgres", "binance")
        },
        "reliability": system_payload.get("reliability"),
    }


@app.get("/api/reliability")
async def reliability_api():
    """SLI longitudinal — ventanas 24h/7d/30d con cobertura real (sin inventar historial)."""
    from .ops.reliability import reliability_dashboard

    with db() as c:
        dash = reliability_dashboard(c.execute)
    return {"mode": "PAPER_ONLY", "reliability": serial(dash)}


@app.get("/api/security/recovery")
async def security_recovery_api():
    """AG9: seguridad y recuperación — sin secretos."""
    from .ops.security_recovery import security_recovery_dashboard

    with db() as c:
        dash = security_recovery_dashboard(c.execute)
    return {"mode": "PAPER_ONLY", "security_recovery": serial(dash)}


@app.get("/api/diagnostics/binance")
async def diagnostics_binance():
    return await _binance_probe()


@app.post("/api/engine/pause")
def engine_pause(reason: str = "manual_pause"):
    return {"mode": "PAPER_ONLY", "engine": set_paused(True, reason)}


@app.post("/api/engine/resume")
def engine_resume(reason: str = "manual_resume"):
    return {"mode": "PAPER_ONLY", "engine": set_paused(False, reason)}


@app.get("/api/candles")
async def candles(
    symbol: str = Query(..., min_length=5, max_length=20),
    interval: str = Query("1h"),
    limit: int = Query(300, ge=10, le=1000),
    indicators_flag: bool = Query(True, alias="indicators"),
    end_time: int | None = Query(
        None, description="Binance endTime (ms) for historical pagination"
    ),
):
    try:
        async with httpx.AsyncClient(
            timeout=25, headers={"User-Agent": "ResearchPaperBot/0.5"}
        ) as client:
            payload = await ohlcv_mod.fetch_klines(
                client, symbol, interval, limit, end_time=end_time
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    last_close = None
    if payload.get("candles"):
        last_close = float(payload["candles"][-1]["close"])

    with db() as c:
        markers = chart_overlay.build_trade_markers(c.execute, payload["symbol"])
        overlays = chart_overlay.build_open_position_overlays(
            c.execute, payload["symbol"], mark_price=last_close
        )
    # Backward compatible: trade_markers keeps SMA-shaped fields + extras
    payload["trade_markers"] = serial(markers)
    payload["markers"] = serial(markers)
    payload["position_overlays"] = serial(overlays)
    payload["history_cursor"] = {
        "oldest_open_ms": payload["candles"][0]["open_time"] if payload["candles"] else None,
        "newest_open_ms": payload["candles"][-1]["open_time"] if payload["candles"] else None,
        "end_time_requested": end_time,
        "has_more": len(payload["candles"]) >= limit,
    }

    if indicators_flag:
        cs = payload["candles"]
        # Indicators use all candles for display; trading path still uses closed-only.
        opens = [x["open"] for x in cs]
        highs = [x["high"] for x in cs]
        lows = [x["low"] for x in cs]
        closes = [x["close"] for x in cs]
        bundle = indicators.compute_bundle(opens, highs, lows, closes)
        # Mark last bar as preliminary when forming (visualization only).
        forming = bool(cs) and not cs[-1].get("is_closed", True)
        payload["indicators"] = bundle
        payload["indicators_meta"] = {
            "last_bar_preliminary": forming,
            "note": "Valores de la vela abierta son preliminares; el motor usa solo cerradas.",
        }
    return payload


@app.get("/api/risk")
def risk_endpoint():
    return _load_risk_report()


@app.get("/api/performance/compare")
async def performance_compare_endpoint():
    """Etapa Q — factual multi-ledger comparison (PAPER_ONLY, no invented Shadow PnL)."""
    sma_risk = _load_risk_report()
    lab_val: dict | None = None
    try:
        from .lab.ledger import snapshot as lab_snapshot
        from .lab.valuation import fetch_marks, portfolio_valuation

        with db() as c:
            ensure_lab_schema(c.execute)
            snap = lab_snapshot(c.execute)
            syms = [p["symbol"] for p in (snap.get("positions") or [])]
        marks = await fetch_marks(syms)
        with db() as c:
            ensure_lab_schema(c.execute)
            lab_val = portfolio_valuation(c.execute, marks=marks)
    except Exception as exc:
        lab_val = {"valuation_status": "ERROR", "error": f"{type(exc).__name__}:{exc}"}
    with db() as c:
        ensure_lab_schema(c.execute)
        ensure_prospect_schema(c.execute)
        payload = performance_compare.build_performance_compare(
            c.execute, lab_valuation=lab_val, sma_risk=sma_risk
        )
    return serial(payload)


@app.get("/api/alerts")
def alerts_list(status: str | None = None, limit: int = 100):
    limit = max(1, min(500, limit))
    with db() as c:
        if status:
            rows = list(
                c.execute(
                    "SELECT * FROM alerts WHERE status=%s ORDER BY updated_at DESC LIMIT %s",
                    (status.upper(), limit),
                )
            )
        else:
            rows = alerts_mod.list_alerts(c.execute, limit)
    return serial(rows)


@app.post("/api/alerts/{alert_id}/ack")
def alerts_ack(alert_id: int):
    with db() as c:
        row = alerts_mod.ack_alert(c.execute, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="alert not found")
    return serial(row)


@app.post("/api/alerts/evaluate")
async def alerts_evaluate():
    await _refresh_alerts_safe()
    with db() as c:
        open_n = c.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE status='OPEN'"
        ).fetchone()["n"]
        rows = alerts_mod.list_alerts(c.execute, 50)
    return serial({"open": open_n, "alerts": rows})
