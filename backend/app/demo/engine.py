"""DEMO evaluation cycle — entries only when RUNNING; protective exits always."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from ..ohlcv import fetch_klines
from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from . import ACCOUNT_ID, POLICY_VERSION, SYMBOLS
from .indicators import compute_bundle
from .policy import (
    BUY_MIN_FLAGS,
    BUY_SCORE_MIN,
    FEE_RATE,
    MAX_EXPOSURE_USDT,
    MAX_POS_USDT,
    MAX_POSITIONS,
    PEAK_DD_PAUSE_PCT,
    RSI_EXIT,
    SLIP_RATE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)
from .schema import ensure_demo_schema

D = Decimal
_filters_cache: dict[str, dict] = {}


def _d(x: Any) -> Decimal:
    return D(str(x))


async def _load_filters(client: httpx.AsyncClient, symbol: str) -> dict:
    if symbol in _filters_cache:
        return _filters_cache[symbol]
    r = await client.get(
        "https://data-api.binance.vision/api/v3/exchangeInfo",
        params={"symbol": symbol},
    )
    r.raise_for_status()
    info = r.json()["symbols"][0]
    out = {"status": info.get("status"), "filters": {}}
    for f in info.get("filters") or []:
        out["filters"][f["filterType"]] = f
    _filters_cache[symbol] = out
    return out


def _round_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    precision = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    floored = math.floor(qty / step) * step
    return float(f"{floored:.{precision}f}")


def _mark_equity(cash: Decimal, positions: list[dict], marks: dict[str, float]):
    invested = D("0")
    mv = D("0")
    for p in positions:
        invested += _d(p["cost"])
        m = marks.get(p["symbol"])
        if m is not None:
            mv += _d(p["qty"]) * _d(m)
    return cash + mv, invested


async def run_cycle(db_factory, *, every_seconds: int = 60) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "at": now.isoformat(),
        "decisions": [],
        "fills": [],
        "rejects": [],
        "ok": True,
    }
    with db_factory() as c:
        ensure_demo_schema(c.execute)
        st = c.execute("SELECT * FROM demo_state WHERE id=1").fetchone()
        allow_entries = bool(st and st["status"] == "RUNNING")
        summary["bot_status"] = (st or {}).get("status")
        summary["allow_entries"] = allow_entries
        # coverage gap detection (host sleep / long pause)
        if st and st.get("heartbeat_at"):
            hb = st["heartbeat_at"]
            if hb.tzinfo is None:
                hb = hb.replace(tzinfo=timezone.utc)
            gap = (now - hb).total_seconds()
            if gap > max(180, every_seconds * 2.5):
                gaps = list(st.get("coverage_gap_json") or [])
                if isinstance(gaps, str):
                    gaps = json.loads(gaps)
                gaps.append(
                    {
                        "from": hb.isoformat(),
                        "to": now.isoformat(),
                        "gap_sec": int(gap),
                        "note": "No retroactive fills reconstructed",
                    }
                )
                c.execute(
                    """UPDATE demo_state SET coverage_gap_json=%s::jsonb, updated_at=NOW() WHERE id=1""",
                    (json.dumps(gaps[-20:]),),
                )
                c.execute(
                    """INSERT INTO demo_events(event_type, actor, detail, meta_json)
                       VALUES ('COVERAGE_GAP','runner',%s,%s::jsonb)""",
                    (f"gap_sec={int(gap)}", json.dumps({"gap_sec": int(gap)})),
                )

    assumptions = ExecutionAssumptions(fee_rate=FEE_RATE, base_slip_rate=SLIP_RATE)
    bundles: dict[str, dict] = {}
    marks: dict[str, float] = {}
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/demo-manual"}
    ) as client:
        for sym in SYMBOLS:
            try:
                k1 = await fetch_klines(client, sym, "1m", limit=120, use_cache=False)
                k5 = await fetch_klines(client, sym, "5m", limit=80, use_cache=False)
                b = compute_bundle(k1["candles"], k5["candles"])
                if not b:
                    summary["rejects"].append({"symbol": sym, "reason": "indicators_incomplete"})
                    continue
                bundles[sym] = b
                marks[sym] = float(b["close"])
            except Exception as exc:
                summary["rejects"].append(
                    {"symbol": sym, "reason": f"fetch:{type(exc).__name__}", "detail": str(exc)[:160]}
                )

        with db_factory() as c:
            ensure_demo_schema(c.execute)
            acc = c.execute(
                "SELECT * FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)
            ).fetchone()
            positions = list(
                c.execute(
                    "SELECT * FROM demo_positions WHERE account_id=%s", (ACCOUNT_ID,)
                )
            )
            cash = _d(acc["cash"])
            peak = _d(acc["peak_equity"])
            equity, invested = _mark_equity(cash, positions, marks)
            if equity > peak:
                peak = equity
                c.execute(
                    "UPDATE demo_accounts SET peak_equity=%s WHERE id=%s",
                    (peak, ACCOUNT_ID),
                )
            pause_buys = equity <= peak * (D("1") - _d(PEAK_DD_PAUSE_PCT))
            pos_by = {p["symbol"]: p for p in positions}

            c.execute(
                """UPDATE demo_state SET cycle_count=cycle_count+1, heartbeat_at=NOW(),
                     last_eval_at=NOW(), next_eval_at=%s, connection_ok=%s,
                     last_error=NULL, updated_at=NOW() WHERE id=1""",
                (now + timedelta(seconds=every_seconds), len(bundles) > 0),
            )
            cycle_id = int(
                c.execute("SELECT cycle_count FROM demo_state WHERE id=1").fetchone()[
                    "cycle_count"
                ]
            )

            # Protective / signal exits — always, even when STOPPED
            for sym, pos in list(pos_by.items()):
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                entry = float(pos["entry_price"])
                action, reason = "HOLD", "hold_position"
                if mark <= entry * (1 - STOP_LOSS_PCT):
                    action, reason = "SELL", "stop_loss_1pct"
                elif mark >= entry * (1 + TAKE_PROFIT_PCT):
                    action, reason = "SELL", "take_profit_2pct"
                elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < RSI_EXIT:
                    action, reason = "SELL", "trend_break_1m"
                corr = uuid.uuid4()
                dec_id = _insert_decision(
                    c.execute, sym, action, mark, b, reason, cycle_id, corr,
                    risk={"protective": True, "bot_status": summary["bot_status"]},
                    executed=False,
                )
                summary["decisions"].append({"symbol": sym, "action": action, "reason": reason})
                if action == "SELL":
                    fill_res = await _try_sell(
                        client, c.execute, pos, mark, b["candle_1m_ms"], dec_id, reason, assumptions, corr
                    )
                    if fill_res.get("ok"):
                        c.execute(
                            "UPDATE demo_decisions SET executed=TRUE WHERE id=%s", (dec_id,)
                        )
                        summary["fills"].append(fill_res)
                        cash = _d(
                            c.execute(
                                "SELECT cash FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)
                            ).fetchone()["cash"]
                        )
                        positions = list(
                            c.execute(
                                "SELECT * FROM demo_positions WHERE account_id=%s",
                                (ACCOUNT_ID,),
                            )
                        )
                        pos_by = {p["symbol"]: p for p in positions}
                        equity, invested = _mark_equity(cash, positions, marks)
                    else:
                        summary["rejects"].append(fill_res)
                        _reject(c.execute, sym, fill_res.get("reason") or "sell_reject", fill_res)

            positions = list(
                c.execute(
                    "SELECT * FROM demo_positions WHERE account_id=%s", (ACCOUNT_ID,)
                )
            )
            pos_by = {p["symbol"]: p for p in positions}
            cash = _d(
                c.execute(
                    "SELECT cash FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)
                ).fetchone()["cash"]
            )
            equity, invested = _mark_equity(cash, positions, marks)

            # Entries — only when RUNNING
            for sym in SYMBOLS:
                if sym in pos_by:
                    continue
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                flags = b["flags"]
                score = float(b["signal_score"])
                n_true = int(b["flags_true"])
                corr = uuid.uuid4()
                action, reason = "HOLD", "no_clear_signal"
                if not allow_entries:
                    reason = "bot_stopped_entries_blocked"
                elif pause_buys:
                    reason = "peak_drawdown_pause"
                elif len(pos_by) >= MAX_POSITIONS:
                    reason = "max_positions"
                elif float(invested) >= MAX_EXPOSURE_USDT - 1e-9:
                    reason = "max_exposure"
                elif n_true >= BUY_MIN_FLAGS and score >= BUY_SCORE_MIN:
                    action, reason = "BUY", f"policy_{n_true}_of_5_flags"
                elif n_true < BUY_MIN_FLAGS:
                    reason = f"flags_{n_true}_of_5_insufficient"

                dec_id = _insert_decision(
                    c.execute, sym, action, mark, b, reason, cycle_id, corr,
                    risk={
                        "allow_entries": allow_entries,
                        "pause_buys": pause_buys,
                        "open_positions": len(pos_by),
                    },
                    executed=False,
                )
                summary["decisions"].append(
                    {"symbol": sym, "action": action, "reason": reason, "score": score}
                )
                if action != "BUY":
                    continue
                fill_res = await _try_buy(
                    client, c.execute, sym, mark, b["candle_1m_ms"], dec_id,
                    cash, invested, assumptions, corr,
                )
                if fill_res.get("ok"):
                    c.execute(
                        "UPDATE demo_decisions SET executed=TRUE WHERE id=%s", (dec_id,)
                    )
                    summary["fills"].append(fill_res)
                    cash = _d(
                        c.execute(
                            "SELECT cash FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)
                        ).fetchone()["cash"]
                    )
                    positions = list(
                        c.execute(
                            "SELECT * FROM demo_positions WHERE account_id=%s",
                            (ACCOUNT_ID,),
                        )
                    )
                    pos_by = {p["symbol"]: p for p in positions}
                    equity, invested = _mark_equity(cash, positions, marks)
                else:
                    summary["rejects"].append(fill_res)
                    _reject(c.execute, sym, fill_res.get("reason") or "buy_reject", fill_res)

            equity, invested = _mark_equity(cash, positions, marks)
            if equity > peak:
                peak = equity
            c.execute(
                "UPDATE demo_accounts SET peak_equity=%s WHERE id=%s",
                (max(peak, equity), ACCOUNT_ID),
            )
            c.execute(
                "INSERT INTO demo_equity_ticks(equity, cash, invested) VALUES (%s,%s,%s)",
                (equity, cash, invested),
            )
            for rj in summary["rejects"]:
                if "fetch" in str(rj.get("reason") or ""):
                    _reject(c.execute, rj.get("symbol"), rj["reason"], rj)

    return summary


def _insert_decision(execute, symbol, action, price, bundle, reason, cycle_id, corr, risk, executed):
    row = execute(
        """INSERT INTO demo_decisions(
            account_id, symbol, action, observed_price, signal_score, flags_true,
            probability_validated, reason, indicators_json, risk_json,
            candle_1m_ms, cycle_id, executed, correlation_id, meta_json)
           VALUES (%s,%s,%s,%s,%s,%s,FALSE,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb)
           RETURNING id""",
        (
            ACCOUNT_ID,
            symbol,
            action,
            price,
            bundle.get("signal_score"),
            bundle.get("flags_true"),
            reason,
            json.dumps({**{k: v for k, v in bundle.items() if k != "flags"}, "flags": bundle.get("flags")}),
            json.dumps(risk),
            bundle.get("candle_1m_ms"),
            cycle_id,
            executed,
            str(corr),
            json.dumps({"policy_version": POLICY_VERSION, "probability_validated": False}),
        ),
    ).fetchone()
    return int(row["id"])


def _reject(execute, symbol, reason, detail) -> None:
    execute(
        """INSERT INTO demo_rejects(symbol, reason, detail_json) VALUES (%s,%s,%s::jsonb)""",
        (symbol, str(reason)[:200], json.dumps(detail, default=str)[:2000]),
    )


async def _try_buy(client, execute, symbol, mark, candle_ms, decision_id, cash, invested, assumptions, corr):
    # Execution-layer block if stopped (race guard)
    st = execute("SELECT status FROM demo_state WHERE id=1").fetchone()
    if not st or st["status"] != "RUNNING":
        return {"ok": False, "reason": "bot_stopped_entries_blocked", "symbol": symbol}

    existing = execute(
        """SELECT id FROM demo_orders WHERE account_id=%s AND symbol=%s AND side='BUY' AND candle_1m_ms=%s""",
        (ACCOUNT_ID, symbol, candle_ms),
    ).fetchone()
    if existing:
        return {"ok": False, "reason": "duplicate_candle_buy", "symbol": symbol}
    if execute(
        "SELECT 1 FROM demo_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    ).fetchone():
        return {"ok": False, "reason": "duplicate_symbol_position", "symbol": symbol}

    budget = min(MAX_POS_USDT, float(cash) * 0.99, MAX_EXPOSURE_USDT - float(invested))
    if budget < 5.0:
        return {"ok": False, "reason": "budget_below_min_notional", "symbol": symbol, "budget": budget}

    try:
        filt = await _load_filters(client, symbol)
    except Exception as exc:
        return {"ok": False, "reason": f"exchange_info:{type(exc).__name__}", "symbol": symbol}
    if filt.get("status") != "TRADING":
        return {"ok": False, "reason": "symbol_not_trading", "symbol": symbol}

    lot = filt["filters"].get("LOT_SIZE") or {}
    notional = filt["filters"].get("NOTIONAL") or filt["filters"].get("MIN_NOTIONAL") or {}
    step = float(lot.get("stepSize") or 0.00001)
    min_qty = float(lot.get("minQty") or 0)
    min_notional = float(notional.get("minNotional") or 5)

    fill = estimate_fill_price(side="BUY", mid_or_ref=mark, assumptions=assumptions)
    if not fill.get("ok"):
        return {"ok": False, "reason": fill.get("reason") or "fill_model", "symbol": symbol}
    px = float(fill["price"])
    qty = _round_step(budget / px, step)
    if qty < min_qty or qty * px < min_notional:
        return {"ok": False, "reason": "lot_or_notional_reject", "symbol": symbol, "qty": qty}

    fee = qty * px * FEE_RATE
    slip_cost = qty * px * SLIP_RATE
    total = qty * px + fee
    cash_now = _d(execute("SELECT cash FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()["cash"])
    if _d(total) > cash_now:
        return {"ok": False, "reason": "insufficient_cash", "symbol": symbol}

    uid = str(uuid.uuid4())
    try:
        ord_row = execute(
            """INSERT INTO demo_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, correlation_id, meta_json)
               VALUES (%s::uuid,%s,%s,'BUY','FILLED',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid, ACCOUNT_ID, symbol, decision_id, candle_ms, mark, px, qty, fee, slip_cost, str(corr),
                json.dumps({"execution_class": fill.get("execution_class"), "paper_only": True}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute("UPDATE demo_accounts SET cash=cash-%s WHERE id=%s", (_d(total), ACCOUNT_ID))
    execute(
        """INSERT INTO demo_positions(account_id, symbol, qty, cost, entry_price, meta_json)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
        (ACCOUNT_ID, symbol, qty, qty * px, px, json.dumps({"decision_id": decision_id})),
    )
    if not execute(
        "SELECT 1 FROM demo_positions WHERE account_id=%s AND symbol=%s", (ACCOUNT_ID, symbol)
    ).fetchone():
        return {"ok": False, "reason": "position_not_created", "symbol": symbol}
    execute(
        """INSERT INTO demo_trades(account_id, order_id, symbol, side, qty, price, fee, slip, reason, correlation_id, meta_json)
           VALUES (%s,%s,%s,'BUY',%s,%s,%s,%s,'demo_policy_buy',%s,%s::jsonb)""",
        (ACCOUNT_ID, ord_row["id"], symbol, qty, px, fee, slip_cost, str(corr), json.dumps({"ref": mark})),
    )
    return {"ok": True, "side": "BUY", "symbol": symbol, "qty": qty, "price": px, "fee": fee, "slip": slip_cost, "ref": mark}


async def _try_sell(client, execute, pos, mark, candle_ms, decision_id, reason, assumptions, corr):
    symbol = pos["symbol"]
    existing = execute(
        """SELECT id FROM demo_orders WHERE account_id=%s AND symbol=%s AND side='SELL' AND candle_1m_ms=%s""",
        (ACCOUNT_ID, symbol, candle_ms),
    ).fetchone()
    if existing:
        return {"ok": False, "reason": "duplicate_candle_sell", "symbol": symbol}
    qty = float(pos["qty"])
    fill = estimate_fill_price(side="SELL", mid_or_ref=mark, assumptions=assumptions)
    if not fill.get("ok"):
        return {"ok": False, "reason": fill.get("reason") or "fill_model", "symbol": symbol}
    px = float(fill["price"])
    proceeds = qty * px
    fee = proceeds * FEE_RATE
    slip_cost = proceeds * SLIP_RATE
    net = proceeds - fee
    cost = float(pos["cost"])
    rpnl = net - cost
    uid = str(uuid.uuid4())
    try:
        ord_row = execute(
            """INSERT INTO demo_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, correlation_id, meta_json)
               VALUES (%s::uuid,%s,%s,'SELL','FILLED',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid, ACCOUNT_ID, symbol, decision_id, candle_ms, mark, px, qty, fee, slip_cost, str(corr),
                json.dumps({"exit_reason": reason, "paper_only": True}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute("UPDATE demo_accounts SET cash=cash+%s WHERE id=%s", (_d(net), ACCOUNT_ID))
    execute("DELETE FROM demo_positions WHERE account_id=%s AND symbol=%s", (ACCOUNT_ID, symbol))
    execute(
        """INSERT INTO demo_trades(account_id, order_id, symbol, side, qty, price, fee, slip,
              realized_pnl, reason, correlation_id, meta_json)
           VALUES (%s,%s,%s,'SELL',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (ACCOUNT_ID, ord_row["id"], symbol, qty, px, fee, slip_cost, rpnl, reason, str(corr), json.dumps({"ref": mark})),
    )
    return {
        "ok": True, "side": "SELL", "symbol": symbol, "qty": qty, "price": px,
        "fee": fee, "slip": slip_cost, "realized_pnl": rpnl, "reason": reason, "ref": mark,
    }
