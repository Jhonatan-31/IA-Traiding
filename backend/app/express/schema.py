"""Isolated express ledger — never mutates lab/sma/research_sim."""
from __future__ import annotations

from typing import Callable

from . import ACCOUNT_ID, INITIAL_CASH
from .policy import END_UTC_ISO, POLICY_VERSION


def ensure_express_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS express_accounts (
            id TEXT PRIMARY KEY,
            cash NUMERIC NOT NULL,
            initial_capital NUMERIC NOT NULL,
            peak_equity NUMERIC NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_positions (
            account_id TEXT NOT NULL REFERENCES express_accounts(id),
            symbol TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            cost NUMERIC NOT NULL,
            entry_price NUMERIC NOT NULL,
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (account_id, symbol)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_orders (
            id BIGSERIAL PRIMARY KEY,
            order_uid UUID NOT NULL UNIQUE,
            account_id TEXT NOT NULL REFERENCES express_accounts(id),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
            status TEXT NOT NULL,
            decision_id BIGINT,
            candle_1m_ms BIGINT,
            ref_price NUMERIC,
            fill_price NUMERIC,
            qty NUMERIC,
            fee NUMERIC DEFAULT 0,
            slip NUMERIC DEFAULT 0,
            reject_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (account_id, symbol, side, candle_1m_ms)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_trades (
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES express_accounts(id),
            order_id BIGINT REFERENCES express_orders(id),
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            fee NUMERIC NOT NULL DEFAULT 0,
            slip NUMERIC NOT NULL DEFAULT 0,
            realized_pnl NUMERIC,
            reason TEXT,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_decisions (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('BUY','SELL','HOLD')),
            observed_price NUMERIC,
            signal_score NUMERIC,
            probability_validated BOOLEAN NOT NULL DEFAULT FALSE,
            probability NUMERIC,
            reason TEXT NOT NULL,
            indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            risk_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            candle_1m_ms BIGINT,
            cycle_id BIGINT,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_rejects (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT,
            reason TEXT NOT NULL,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_state (
            id INT PRIMARY KEY DEFAULT 1 CHECK (id=1),
            status TEXT NOT NULL DEFAULT 'INIT',
            started_at TIMESTAMPTZ,
            ended_at TIMESTAMPTZ,
            end_deadline TIMESTAMPTZ NOT NULL,
            heartbeat_at TIMESTAMPTZ,
            cycle_count BIGINT NOT NULL DEFAULT 0,
            last_error TEXT,
            policy_version TEXT,
            connection_ok BOOLEAN DEFAULT TRUE,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS express_equity_ticks (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            equity NUMERIC NOT NULL,
            cash NUMERIC NOT NULL,
            invested NUMERIC NOT NULL
        )"""
    )

    acc = execute(
        "SELECT id FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)
    ).fetchone()
    if not acc:
        execute(
            """INSERT INTO express_accounts(id, cash, initial_capital, peak_equity, meta_json)
               VALUES (%s,%s,%s,%s,%s::jsonb)""",
            (
                ACCOUNT_ID,
                INITIAL_CASH,
                INITIAL_CASH,
                INITIAL_CASH,
                '{"paper_only":true,"isolated":true}',
            ),
        )
    st = execute("SELECT id FROM express_state WHERE id=1").fetchone()
    if not st:
        execute(
            """INSERT INTO express_state(id, status, end_deadline, policy_version, meta_json)
               VALUES (1,'READY',%s::timestamptz,%s,'{}'::jsonb)""",
            (END_UTC_ISO, POLICY_VERSION),
        )
