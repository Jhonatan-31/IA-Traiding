"""One express cycle — PAPER fills only, isolated account."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import httpx

from ..ohlcv import fetch_klines
from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from . import ACCOUNT_ID, SYMBOLS
from .indicators import compute_bundle
from .policy import (
    BUY_SCORE_MIN,
    FEE_RATE,
    MAX_EXPOSURE_USDT,
    MAX_POS_USDT,
    MAX_POSITIONS,
    PEAK_DD_PAUSE_PCT,
    POLICY_VERSION,
    RSI_BUY_HI,
    RSI_BUY_LO,
    SLIP_RATE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    is_ended,
)
from .schema import ensure_express_schema

D = Decimal


def _d(x: Any) -> Decimal:
    return D(str(x))


_filters_cache: dict[str, dict] = {}


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


def _mark_equity(cash: Decimal, positions: list[dict], marks: dict[str, float]) -> tuple[Decimal, Decimal]:
    invested = D("0")
    mv = D("0")
    for p in positions:
        invested += _d(p["cost"])
        m = marks.get(p["symbol"])
        if m is None:
            continue
        mv += _d(p["qty"]) * _d(m)
    return cash + mv, invested


async def run_cycle(db_factory) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "at": now.isoformat(),
        "ended": is_ended(now),
        "decisions": [],
        "fills": [],
        "rejects": [],
        "ok": True,
    }
    with db_factory() as c:
        ensure_express_schema(c.execute)
        st = c.execute("SELECT * FROM express_state WHERE id=1").fetchone()
        if st and st["status"] == "ENDED":
            summary["status"] = "ENDED"
            return summary
        if is_ended(now):
            c.execute(
                """UPDATE express_state SET status='ENDED', ended_at=NOW(),
                     heartbeat_at=NOW(), updated_at=NOW(),
                     meta_json=meta_json || '{"end_reason":"absolute_deadline"}'::jsonb
                   WHERE id=1"""
            )
            summary["status"] = "ENDED"
            summary["note"] = "Deadline reached — no new experimental decisions"
            return summary
        if st and st["status"] in ("READY", "INIT"):
            c.execute(
                """UPDATE express_state SET status='RUNNING', started_at=COALESCE(started_at,NOW()),
                     heartbeat_at=NOW(), policy_version=%s, updated_at=NOW() WHERE id=1""",
                (POLICY_VERSION,),
            )

    assumptions = ExecutionAssumptions(fee_rate=FEE_RATE, base_slip_rate=SLIP_RATE)
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/express-test"}
    ) as client:
        bundles: dict[str, dict] = {}
        marks: dict[str, float] = {}
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
                    {"symbol": sym, "reason": f"fetch:{type(exc).__name__}", "detail": str(exc)[:200]}
                )

        with db_factory() as c:
            ensure_express_schema(c.execute)
            acc = c.execute(
                "SELECT * FROM express_accounts WHERE id=%s FOR UPDATE", (ACCOUNT_ID,)
            ).fetchone()
            positions = list(
                c.execute(
                    "SELECT * FROM express_positions WHERE account_id=%s", (ACCOUNT_ID,)
                )
            )
            cash = _d(acc["cash"])
            peak = _d(acc["peak_equity"])
            equity, invested = _mark_equity(cash, positions, marks)
            if equity > peak:
                peak = equity
                c.execute(
                    "UPDATE express_accounts SET peak_equity=%s WHERE id=%s",
                    (peak, ACCOUNT_ID),
                )
            pause_buys = equity <= peak * (D("1") - _d(PEAK_DD_PAUSE_PCT))
            pos_by = {p["symbol"]: p for p in positions}
            cycle_id = int(acc.get("meta_json") and 0 or 0)
            c.execute(
                """UPDATE express_state SET cycle_count=cycle_count+1, heartbeat_at=NOW(),
                     connection_ok=%s, last_error=NULL, updated_at=NOW() RETURNING cycle_count""",
                (len(bundles) > 0,),
            )
            cycle_row = c.execute(
                "SELECT cycle_count FROM express_state WHERE id=1"
            ).fetchone()
            cycle_id = int(cycle_row["cycle_count"])

            # 1) Protective / signal exits first (fresh mark = closed 1m close)
            for sym, pos in list(pos_by.items()):
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                entry = float(pos["entry_price"])
                action = "HOLD"
                reason = "hold_position"
                if mark <= entry * (1 - STOP_LOSS_PCT):
                    action, reason = "SELL", "stop_loss_1pct"
                elif mark >= entry * (1 + TAKE_PROFIT_PCT):
                    action, reason = "SELL", "take_profit_2pct"
                elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 45:
                    action, reason = "SELL", "trend_break_1m"
                dec_id = _insert_decision(
                    c.execute,
                    sym,
                    action,
                    mark,
                    b,
                    reason,
                    cycle_id,
                    risk={"pause_buys": pause_buys, "equity": float(equity)},
                )
                summary["decisions"].append({"symbol": sym, "action": action, "reason": reason})
                if action == "SELL":
                    fill_res = await _try_sell(
                        client, c.execute, pos, mark, b["candle_1m_ms"], dec_id, reason, assumptions
                    )
                    if fill_res.get("ok"):
                        summary["fills"].append(fill_res)
                        cash = _d(
                            c.execute(
                                "SELECT cash FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)
                            ).fetchone()["cash"]
                        )
                        positions = list(
                            c.execute(
                                "SELECT * FROM express_positions WHERE account_id=%s",
                                (ACCOUNT_ID,),
                            )
                        )
                        pos_by = {p["symbol"]: p for p in positions}
                        equity, invested = _mark_equity(cash, positions, marks)
                    else:
                        summary["rejects"].append(fill_res)
                        _reject(c.execute, sym, fill_res.get("reason") or "sell_reject", fill_res)

            # Refresh after exits
            positions = list(
                c.execute(
                    "SELECT * FROM express_positions WHERE account_id=%s", (ACCOUNT_ID,)
                )
            )
            pos_by = {p["symbol"]: p for p in positions}
            cash = _d(
                c.execute(
                    "SELECT cash FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)
                ).fetchone()["cash"]
            )
            equity, invested = _mark_equity(cash, positions, marks)

            # 2) Entries
            for sym in SYMBOLS:
                if sym in pos_by:
                    continue  # already decided above if held
                b = bundles.get(sym)
                if not b:
                    continue
                mark = float(b["close"])
                flags = b["flags"]
                score = float(b["signal_score"])
                all_ok = all(flags.values()) and score >= BUY_SCORE_MIN
                action = "HOLD"
                reason = "no_clear_signal"
                if pause_buys:
                    reason = "peak_drawdown_pause"
                elif len(pos_by) >= MAX_POSITIONS:
                    reason = "max_positions"
                elif float(invested) >= MAX_EXPOSURE_USDT - 1e-9:
                    reason = "max_exposure"
                elif all_ok:
                    action, reason = "BUY", "policy_all_flags_score"
                elif not flags["trend_5m"] or not flags["trend_1m"]:
                    reason = "trend_not_aligned"
                elif not flags["rsi_ok"]:
                    reason = f"rsi_out_of_band_{RSI_BUY_LO}_{RSI_BUY_HI}"
                elif not flags["vol_ok"]:
                    reason = "volume_below_sma20"
                elif not flags["atr_ok"]:
                    reason = "atr_too_high"

                # Skip duplicate HOLD spam if we already logged SELL path for held — for flat only
                dec_id = _insert_decision(
                    c.execute,
                    sym,
                    action,
                    mark,
                    b,
                    reason,
                    cycle_id,
                    risk={
                        "pause_buys": pause_buys,
                        "open_positions": len(pos_by),
                        "invested": float(invested),
                    },
                )
                summary["decisions"].append(
                    {"symbol": sym, "action": action, "reason": reason, "score": score}
                )
                if action != "BUY":
                    continue
                fill_res = await _try_buy(
                    client,
                    c.execute,
                    sym,
                    mark,
                    b["candle_1m_ms"],
                    dec_id,
                    cash,
                    invested,
                    assumptions,
                )
                if fill_res.get("ok"):
                    summary["fills"].append(fill_res)
                    cash = _d(
                        c.execute(
                            "SELECT cash FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)
                        ).fetchone()["cash"]
                    )
                    positions = list(
                        c.execute(
                            "SELECT * FROM express_positions WHERE account_id=%s",
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
                "UPDATE express_accounts SET peak_equity=%s WHERE id=%s",
                (max(peak, equity), ACCOUNT_ID),
            )
            c.execute(
                """INSERT INTO express_equity_ticks(equity, cash, invested)
                   VALUES (%s,%s,%s)""",
                (equity, cash, invested),
            )
            for rj in summary["rejects"]:
                if rj.get("symbol") and rj.get("reason") and "fetch" in str(rj.get("reason")):
                    _reject(c.execute, rj.get("symbol"), rj["reason"], rj)

    return summary


def _insert_decision(
    execute, symbol, action, price, bundle, reason, cycle_id, risk
) -> int:
    row = execute(
        """INSERT INTO express_decisions(
            account_id, symbol, action, observed_price, signal_score,
            probability_validated, probability, reason, indicators_json, risk_json,
            candle_1m_ms, cycle_id, meta_json)
           VALUES (%s,%s,%s,%s,%s,FALSE,NULL,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb)
           RETURNING id""",
        (
            ACCOUNT_ID,
            symbol,
            action,
            price,
            bundle.get("signal_score"),
            reason,
            json.dumps({**{k: v for k, v in bundle.items() if k != "flags"}, "flags": bundle.get("flags")}),
            json.dumps(risk),
            bundle.get("candle_1m_ms"),
            cycle_id,
            json.dumps({"policy_version": POLICY_VERSION, "probability_validated": False}),
        ),
    ).fetchone()
    return int(row["id"])


def _reject(execute, symbol, reason, detail) -> None:
    execute(
        """INSERT INTO express_rejects(symbol, reason, detail_json)
           VALUES (%s,%s,%s::jsonb)""",
        (symbol, reason[:200], json.dumps(detail, default=str)[:2000]),
    )


async def _try_buy(
    client, execute, symbol, mark, candle_ms, decision_id, cash, invested, assumptions
) -> dict:
    existing = execute(
        """SELECT id FROM express_orders
           WHERE account_id=%s AND symbol=%s AND side='BUY' AND candle_1m_ms=%s""",
        (ACCOUNT_ID, symbol, candle_ms),
    ).fetchone()
    if existing:
        return {"ok": False, "reason": "duplicate_candle_buy", "symbol": symbol}

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
    min_notional = float(notional.get("minNotional") or notional.get("minNotional") or 5)

    fill = estimate_fill_price(
        side="BUY", mid_or_ref=mark, assumptions=assumptions
    )
    if not fill.get("ok"):
        return {"ok": False, "reason": fill.get("reason") or "fill_model", "symbol": symbol}
    px = float(fill["price"])
    qty = _round_step(budget / px, step)
    if qty < min_qty or qty * px < min_notional:
        return {
            "ok": False,
            "reason": "lot_or_notional_reject",
            "symbol": symbol,
            "qty": qty,
            "min_qty": min_qty,
            "min_notional": min_notional,
        }
    fee = qty * px * FEE_RATE
    slip_cost = qty * px * SLIP_RATE
    total = qty * px + fee
    cash_now = _d(
        execute("SELECT cash FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()["cash"]
    )
    if _d(total) > cash_now:
        return {"ok": False, "reason": "insufficient_cash", "symbol": symbol}

    uid = str(uuid.uuid4())
    try:
        ord_row = execute(
            """INSERT INTO express_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, meta_json)
               VALUES (%s::uuid,%s,%s,'BUY','FILLED',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid,
                ACCOUNT_ID,
                symbol,
                decision_id,
                candle_ms,
                mark,
                px,
                qty,
                fee,
                slip_cost,
                json.dumps({"execution_class": fill.get("execution_class"), "paper_only": True}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute(
        "UPDATE express_accounts SET cash=cash-%s WHERE id=%s",
        (_d(total), ACCOUNT_ID),
    )
    execute(
        """INSERT INTO express_positions(account_id, symbol, qty, cost, entry_price, meta_json)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (account_id, symbol) DO NOTHING""",
        (ACCOUNT_ID, symbol, qty, qty * px, px, json.dumps({"decision_id": decision_id})),
    )
    # If conflict (duplicate symbol), rollback-ish: should not happen due to pre-check
    pos = execute(
        "SELECT * FROM express_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    ).fetchone()
    if not pos:
        return {"ok": False, "reason": "position_not_created_duplicate", "symbol": symbol}

    execute(
        """INSERT INTO express_trades(account_id, order_id, symbol, side, qty, price, fee, slip, reason, meta_json)
           VALUES (%s,%s,%s,'BUY',%s,%s,%s,%s,'express_policy_buy',%s::jsonb)""",
        (ACCOUNT_ID, ord_row["id"], symbol, qty, px, fee, slip_cost, json.dumps({"ref": mark})),
    )
    return {
        "ok": True,
        "side": "BUY",
        "symbol": symbol,
        "qty": qty,
        "price": px,
        "fee": fee,
        "slip": slip_cost,
        "ref": mark,
    }


async def _try_sell(
    client, execute, pos, mark, candle_ms, decision_id, reason, assumptions
) -> dict:
    symbol = pos["symbol"]
    existing = execute(
        """SELECT id FROM express_orders
           WHERE account_id=%s AND symbol=%s AND side='SELL' AND candle_1m_ms=%s""",
        (ACCOUNT_ID, symbol, candle_ms),
    ).fetchone()
    if existing:
        return {"ok": False, "reason": "duplicate_candle_sell", "symbol": symbol}

    qty = float(pos["qty"])
    fill = estimate_fill_price(
        side="SELL", mid_or_ref=mark, assumptions=assumptions
    )
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
            """INSERT INTO express_orders(
                order_uid, account_id, symbol, side, status, decision_id, candle_1m_ms,
                ref_price, fill_price, qty, fee, slip, meta_json)
               VALUES (%s::uuid,%s,%s,'SELL','FILLED',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               RETURNING id""",
            (
                uid,
                ACCOUNT_ID,
                symbol,
                decision_id,
                candle_ms,
                mark,
                px,
                qty,
                fee,
                slip_cost,
                json.dumps({"exit_reason": reason, "paper_only": True}),
            ),
        ).fetchone()
    except Exception as exc:
        return {"ok": False, "reason": f"order_insert:{type(exc).__name__}", "symbol": symbol}

    execute(
        "UPDATE express_accounts SET cash=cash+%s WHERE id=%s",
        (_d(net), ACCOUNT_ID),
    )
    execute(
        "DELETE FROM express_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    )
    execute(
        """INSERT INTO express_trades(account_id, order_id, symbol, side, qty, price, fee, slip,
              realized_pnl, reason, meta_json)
           VALUES (%s,%s,%s,'SELL',%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (
            ACCOUNT_ID,
            ord_row["id"],
            symbol,
            qty,
            px,
            fee,
            slip_cost,
            rpnl,
            reason,
            json.dumps({"ref": mark}),
        ),
    )
    return {
        "ok": True,
        "side": "SELL",
        "symbol": symbol,
        "qty": qty,
        "price": px,
        "fee": fee,
        "slip": slip_cost,
        "realized_pnl": rpnl,
        "reason": reason,
        "ref": mark,
    }
