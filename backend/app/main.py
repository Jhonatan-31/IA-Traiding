"""Public Binance market monitoring, paper-only, no private API keys or live trades."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row

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
        # Additive columns for richer trade journal (safe if already present)
        for stmt in (
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS fee_rate NUMERIC",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS slip_rate NUMERIC",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy TEXT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS reason TEXT",
            "ALTER TABLE prices ADD COLUMN IF NOT EXISTS source TEXT",
        ):
            c.execute(stmt)


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
    for attempt in range(retries):
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


async def cycle(client: httpx.AsyncClient):
    if is_paused():
        print("PAPER_ONLY paused — skipping entries/exits", flush=True)
        with db() as c:
            holdings = list(c.execute("SELECT * FROM positions"))
            cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        # Still refresh live marks while paused (no new trades)
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
                c.execute(
                    "INSERT INTO scans(markets, errors, equity) VALUES(%s,%s,%s)",
                    (0, 0, equity),
                )
            print("PAPER_ONLY paused markets 0 errors 0 equity", equity, flush=True)
        except Exception as exc:
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
            bars = [r for r in rows if int(r[6]) < now]
            if len(bars) < 51:
                continue
            end = int(bars[-1][6])
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
                    n = c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
                    cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
                    budget = min(BUDGET, cash)
                    if n < MAX_POSITIONS and budget >= MIN_BUDGET:
                        fill = price * (1 + SLIP)
                        qty = (budget * (1 - FEE)) / fill
                        c.execute(
                            "UPDATE account SET cash=cash-%s WHERE id=1", (budget,)
                        )
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
                    c.execute(
                        "UPDATE account SET cash=cash+%s WHERE id=1", (proceeds,)
                    )
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
            print("MARKET_ERROR", symbol, str(e), flush=True)
        await asyncio.sleep(0.15)

    allprices = await get(client, "/ticker/price")
    lookup = {x["symbol"]: Decimal(str(x["price"])) for x in allprices}
    with db() as c:
        holdings = list(c.execute("SELECT * FROM positions"))
        cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        # Refresh marks with live ticker for open positions + scanned set
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
        c.execute(
            "INSERT INTO scans(markets, errors, equity) VALUES(%s,%s,%s)",
            (scanned, errors, equity),
        )
    print("PAPER_ONLY markets", scanned, "errors", errors, "equity", equity, flush=True)


async def work():
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/0.4"}
    ) as client:
        while True:
            try:
                await cycle(client)
            except Exception as exc:
                print("COLLECTOR_ERROR", type(exc).__name__, str(exc), flush=True)
            await asyncio.sleep(PERIOD)


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
    yield


app = FastAPI(title="AI Trading Bot - PAPER ONLY", lifespan=lifespan)


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
            "strategy": STRATEGY,
            "disclaimer": "Simulación ilustrativa. No es consejo financiero ni promesa de ganancias.",
        }
    )


@app.get("/api/trades")
def trades(limit: int = 50):
    limit = max(1, min(500, limit))
    with db() as c:
        return serial(
            list(
                c.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT %s", (limit,)
                )
            )
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


@app.get("/api/system")
def system():
    with db() as c:
        engine = c.execute("SELECT * FROM engine_state WHERE id=1").fetchone()
        last_scan = c.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_trade = c.execute(
            "SELECT at FROM trades ORDER BY id DESC LIMIT 1"
        ).fetchone()
        price_age = c.execute(
            "SELECT MAX(at) AS at FROM prices"
        ).fetchone()
        audit = list(
            c.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT 20"
            )
        )
        counts = {
            "positions": c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"],
            "trades": c.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"],
            "prices": c.execute("SELECT COUNT(*) AS n FROM prices").fetchone()["n"],
            "scans": c.execute("SELECT COUNT(*) AS n FROM scans").fetchone()["n"],
        }
    return serial(
        {
            "mode": "PAPER_ONLY",
            "engine": engine,
            "last_scan": last_scan,
            "last_trade_at": last_trade["at"] if last_trade else None,
            "prices_max_at": price_age["at"] if price_age else None,
            "counts": counts,
            "binance_base": BASE,
            "scan_limit": LIMIT,
            "scan_every_seconds": PERIOD,
            "audit": audit,
            "notes": [
                "CPU/memoria host solo disponibles si el orquestador las expone; no se inventan aquí.",
                "Binance latency se mide en /api/diagnostics/binance (solo lectura).",
            ],
        }
    )


@app.get("/api/diagnostics/binance")
async def diagnostics_binance():
    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(
            timeout=10, headers={"User-Agent": "ResearchPaperBot/0.4-diag"}
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


@app.post("/api/engine/pause")
def engine_pause(reason: str = "manual_pause"):
    return {"mode": "PAPER_ONLY", "engine": set_paused(True, reason)}


@app.post("/api/engine/resume")
def engine_resume(reason: str = "manual_resume"):
    return {"mode": "PAPER_ONLY", "engine": set_paused(False, reason)}
