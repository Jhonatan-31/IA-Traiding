"""Strategy B cycle — PAPER only; entries when RUNNING; protective exits always."""
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
from . import ACCOUNT_B, B_EXECUTION_AUTHORIZED, POLICY_B_VERSION, SYMBOLS
from .indicators_b import compute_bundle, evaluate_entry, evaluate_exit
from .policy_b import (
    COOLDOWN_SEC,
    FEE_RATE,
    MAX_ENTRIES_PER_HOUR,
    MAX_EXPOSURE_USDT,
    MAX_POS_USDT,
    MAX_POSITIONS,
    PEAK_DD_PAUSE_PCT,
    SLIP_RATE,
    human_reason,
)
from .schema import ensure_active_schema

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


def _insert_decision(execute, symbol, action, price, bundle, reason, cycle_id, corr, risk, executed):
    row = execute(
        """INSERT INTO active_decisions(
            account_id, symbol, action, observed_price, signal_score, flags_true,
            probability_validated, reason, human_reason, indicators_json, risk_json,
            candle_1m_ms, cycle_id, executed, correlation_id, meta_json)
           VALUES (%s,%s,%s,%s,%s,%s,FALSE,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb)
           RETURNING id""",
        (
            ACCOUNT_B,
            symbol,
            action,
            price,
            bundle.get("signal_score"),
            bundle.get("flags_true"),
            reason,
            human_reason(reason),
            json.dumps({**{k: v for k, v in bundle.items() if k != "flags"}, "flags": bundle.get("flags")}),
            json.dumps(risk),
            bundle.get("candle_1m_ms"),
            cycle_id,
            executed,
            str(corr),
            json.dumps({"policy_version": POLICY_B_VERSION, "paper_only": True}),
        ),
    ).fetchone()
    return int(row["id"])


async def run_cycle(db_factory, *, every_seconds: int = 60) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "at": now.isoformat(),
        "decisions": [],
        "fills": [],
        "rejects": [],
        "ok": True,
        "strategy": "B",
        "policy_version": POLICY_B_VERSION,
    }
    if not B_EXECUTION_AUTHORIZED:
        summary["ok"] = False
        summary["rejects"].append({"reason": "b_execution_not_authorized"})
        return summary

    with db_factory() as c:
        ensure_active_schema(c.execute)
        st = c.execute("SELECT * FROM active_state WHERE id=1").fetchone()
        allow_entries = bool(st and st["status"] == "RUNNING")
        summary["bot_status"] = (st or {}).get("status")
        summary["allow_entries"] = allow_entries

    assumptions = ExecutionAssumptions(fee_rate=FEE_RATE, base_slip_rate=SLIP_RATE)
    bundles: dict[str, dict] = {}
    marks: dict[str, float] = {}
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/active-b"}
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
            ensure_active_schema(c.execute)
            acc = c.execute(
                "SELECT * FROM active_accounts WHERE id=%s", (ACCOUNT_B,)
            ).fetchone()
            positions = list(
                c.execute(
                    "SELECT * FROM active_positions WHERE account_id=%s", (ACCOUNT_B,)
                )
            )
            cash = _d(acc["cash"])
            peak = _d(acc["peak_equity"])
            equity, invested = _mark_equity(cash, positions, marks)
            if equity > peak:
                peak = equity
                c.execute(
                    "UPDATE active_accounts SET peak_equity=%s WHERE id=%s",
                    (peak, ACCOUNT_B),
                )
            pause_buys = equity <= peak * (D("1") - _d(PEAK_DD_PAUSE_PCT))
            pos_by = {p["symbol"]: p for p in positions}

            c.execute(
                """UPDATE active_state SET cycle_count=cycle_count+1, heartbeat_at=NOW(),
                     last_eval_at=NOW(), next_eval_at=%s, connection_ok=%s,
                     last_error=NULL, updated_at=NOW() WHERE id=1""",
                (now + timedelta(seconds=every_seconds), len(bundles) > 0),
            )
            cycle_id = int(
                c.execute("SELECT cycle_count FROM active_state WHERE id=1").fetchone()[
                    "cycle_count"
                ]
            )

            # Protective exits always
            for sym, pos in list(pos_by.items()):
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                action, reason = evaluate_exit(b, float(pos["entry_price"]))
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
                            "UPDATE active_decisions SET executed=TRUE WHERE id=%s", (dec_id,)
                        )
                        summary["fills"].append(fill_res)
                        cash = _d(
                            c.execute(
                                "SELECT cash FROM active_accounts WHERE id=%s", (ACCOUNT_B,)
                            ).fetchone()["cash"]
                        )
                        positions = list(
                            c.execute(
                                "SELECT * FROM active_positions WHERE account_id=%s",
                                (ACCOUNT_B,),
                            )
                        )
                        pos_by = {p["symbol"]: p for p in positions}
                        equity, invested = _mark_equity(cash, positions, marks)
                    else:
                        summary["rejects"].append(fill_res)

            positions = list(
                c.execute(
                    "SELECT * FROM active_positions WHERE account_id=%s", (ACCOUNT_B,)
                )
            )
            pos_by = {p["symbol"]: p for p in positions}
            cash = _d(
                c.execute(
                    "SELECT cash FROM active_accounts WHERE id=%s", (ACCOUNT_B,)
                ).fetchone()["cash"]
            )
            equity, invested = _mark_equity(cash, positions, marks)

            entries_hour = int(
                c.execute(
                    """SELECT COUNT(*) n FROM active_trades
                       WHERE account_id=%s AND side='BUY' AND at > NOW() - INTERVAL '1 hour'""",
                    (ACCOUNT_B,),
                ).fetchone()["n"]
            )

            for sym in SYMBOLS:
                if sym in pos_by:
                    continue
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                corr = uuid.uuid4()
                action, reason = evaluate_entry(b)
                if not allow_entries:
                    action, reason = "HOLD", "bot_stopped_entries_blocked"
                elif pause_buys:
                    action, reason = "HOLD", "peak_drawdown_pause"
                elif len(pos_by) >= MAX_POSITIONS:
                    action, reason = "HOLD", "max_positions"
                elif float(invested) >= MAX_EXPOSURE_USDT - 1e-9:
                    action, reason = "HOLD", "max_exposure"
                elif entries_hour >= MAX_ENTRIES_PER_HOUR:
                    action, reason = "HOLD", "max_entries_hour"
                else:
                    last_fill = c.execute(
                        """SELECT at FROM active_trades
                           WHERE account_id=%s AND symbol=%s
                           ORDER BY at DESC LIMIT 1""",
                        (ACCOUNT_B, sym),
                    ).fetchone()
                    if last_fill and last_fill["at"]:
                        age = (now - last_fill["at"]).total_seconds()
                        if age < COOLDOWN_SEC and action == "BUY":
                            action, reason = "HOLD", "cooldown"

                dec_id = _insert_decision(
                    c.execute, sym, action, mark, b, reason, cycle_id, corr,
                    risk={
                        "allow_entries": allow_entries,
                        "pause_buys": pause_buys,
                        "open_positions": len(pos_by),
                        "entries_hour": entries_hour,
                    },
                    executed=False,
                )
                summary["decisions"].append(
                    {"symbol": sym, "action": action, "reason": reason, "score": b.get("signal_score")}
                )
                if action != "BUY":
                    continue
                fill_res = await _try_buy(
                    client, c.execute, sym, mark, b["candle_1m_ms"], dec_id,
                    cash, invested, assumptions, corr,
                )
                if fill_res.get("ok"):
                    c.execute(
                        "UPDATE active_decisions SET executed=TRUE WHERE id=%s", (dec_id,)
                    )
                    summary["fills"].append(fill_res)
                    entries_hour += 1
                    cash = _d(
                        c.execute(
                            "SELECT cash FROM active_accounts WHERE id=%s", (ACCOUNT_B,)
                        ).fetchone()["cash"]
                    )
                    positions = list(
                        c.execute(
                            "SELECT * FROM active_positions WHERE account_id=%s",
                            (ACCOUNT_B,),
                        )
                    )
                    pos_by = {p["symbol"]: p for p in positions}
                    equity, invested = _mark_equity(cash, positions, marks)
                else:
                    summary["rejects"].append(fill_res)

            if equity > peak:
                peak = equity
            c.execute(
                "UPDATE active_accounts SET peak_equity=%s WHERE id=%s",
                (max(peak, equity), ACCOUNT_B),
            )
            c.execute(
                "INSERT INTO active_equity_ticks(equity, cash, invested) VALUES (%s,%s,%s)",
                (equity, cash, invested),
            )

    return summary


async def _try_buy(client, execute, symbol, mark, candle_ms, decision_id, cash, invested, assumptions, corr):
    st = execute("SELECT status FROM active_state WHERE id=1").fetchone()
    if not st or st["status"] != "RUNNING":
        return {"ok": False, "reason": "bot_stopped_entries_blocked", "symbol": symbol}
    existing = execute(
        """SELECT id FROM active_orders WHERE account_id=%s AND symbol=%s AND side='BUY' AND candle_1m_ms=%s""",
        (ACCOUNT_B, symbol, candle_ms),
    ).fetchone()
    if existing:
        return {"ok": False, "reason": "duplicate_candle_buy", "symbol": symbol}
    if execute(
        "SELECT 1 FROM active_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_B, symbol),
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
    cash_now = _d(execute("SELECT cash FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()["cash"])
    if _d(total) > cash_now:
        return {"ok": False, "reason": "insufficient_cash", "symbol": symbol}

    uid = str(uuid.uuid4())
    try:
        ord_row = execute(
            """INSERT INTO active_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, meta_json)
               VALUES (%s::uuid,%s,%s,'BUY','FILLED',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid, ACCOUNT_B, symbol, decision_id, candle_ms, mark, px, qty, fee, slip_cost,
                json.dumps({"execution_class": fill.get("execution_class"), "paper_only": True, "corr": str(corr)}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute("UPDATE active_accounts SET cash=cash-%s WHERE id=%s", (_d(total), ACCOUNT_B))
    execute(
        """INSERT INTO active_positions(account_id, symbol, qty, cost, entry_price, meta_json)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
        (ACCOUNT_B, symbol, qty, qty * px, px, json.dumps({"decision_id": decision_id})),
    )
    if not execute(
        "SELECT 1 FROM active_positions WHERE account_id=%s AND symbol=%s", (ACCOUNT_B, symbol)
    ).fetchone():
        return {"ok": False, "reason": "position_not_created", "symbol": symbol}
    execute(
        """INSERT INTO active_trades(account_id, order_id, symbol, side, qty, price, fee, slip, reason, correlation_id, meta_json)
           VALUES (%s,%s,%s,'BUY',%s,%s,%s,%s,'active_b_buy',%s,%s::jsonb)""",
        (ACCOUNT_B, ord_row["id"], symbol, qty, px, fee, slip_cost, str(corr), json.dumps({"ref": mark})),
    )
    return {"ok": True, "side": "BUY", "symbol": symbol, "qty": qty, "price": px, "fee": fee, "slip": slip_cost, "ref": mark}


async def _try_sell(client, execute, pos, mark, candle_ms, decision_id, reason, assumptions, corr):
    symbol = pos["symbol"]
    existing = execute(
        """SELECT id FROM active_orders WHERE account_id=%s AND symbol=%s AND side='SELL' AND candle_1m_ms=%s""",
        (ACCOUNT_B, symbol, candle_ms),
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
            """INSERT INTO active_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, meta_json)
               VALUES (%s::uuid,%s,%s,'SELL','FILLED',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid, ACCOUNT_B, symbol, decision_id, candle_ms, mark, px, qty, fee, slip_cost,
                json.dumps({"exit_reason": reason, "paper_only": True, "corr": str(corr)}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute("UPDATE active_accounts SET cash=cash+%s WHERE id=%s", (_d(net), ACCOUNT_B))
    execute("DELETE FROM active_positions WHERE account_id=%s AND symbol=%s", (ACCOUNT_B, symbol))
    execute(
        """INSERT INTO active_trades(account_id, order_id, symbol, side, qty, price, fee, slip,
              realized_pnl, reason, correlation_id, meta_json)
           VALUES (%s,%s,%s,'SELL',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (ACCOUNT_B, ord_row["id"], symbol, qty, px, fee, slip_cost, rpnl, reason, str(corr), json.dumps({"ref": mark})),
    )
    return {
        "ok": True, "side": "SELL", "symbol": symbol, "qty": qty, "price": px,
        "fee": fee, "slip": slip_cost, "realized_pnl": rpnl, "reason": reason, "ref": mark,
    }
