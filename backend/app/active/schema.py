"""Isolated active_exp_v1 ledger — never mutates demo/lab/sma/express/research."""
from __future__ import annotations

from typing import Callable

from . import ACCOUNT_B, INITIAL_CASH, POLICY_B_VERSION


def ensure_active_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS active_accounts (
            id TEXT PRIMARY KEY,
            cash NUMERIC NOT NULL,
            initial_capital NUMERIC NOT NULL,
            peak_equity NUMERIC NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_positions (
            account_id TEXT NOT NULL REFERENCES active_accounts(id),
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
        """CREATE TABLE IF NOT EXISTS active_orders (
            id BIGSERIAL PRIMARY KEY,
            order_uid UUID NOT NULL UNIQUE,
            account_id TEXT NOT NULL REFERENCES active_accounts(id),
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
        """CREATE TABLE IF NOT EXISTS active_trades (
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES active_accounts(id),
            order_id BIGINT REFERENCES active_orders(id),
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            fee NUMERIC NOT NULL DEFAULT 0,
            slip NUMERIC NOT NULL DEFAULT 0,
            realized_pnl NUMERIC,
            reason TEXT,
            correlation_id UUID,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_decisions (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('BUY','SELL','HOLD')),
            observed_price NUMERIC,
            signal_score NUMERIC,
            flags_true INT,
            probability_validated BOOLEAN NOT NULL DEFAULT FALSE,
            reason TEXT NOT NULL,
            human_reason TEXT,
            indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            risk_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            candle_1m_ms BIGINT,
            cycle_id BIGINT,
            executed BOOLEAN NOT NULL DEFAULT FALSE,
            correlation_id UUID,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_rejects (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT,
            reason TEXT NOT NULL,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_state (
            id INT PRIMARY KEY CHECK (id = 1),
            status TEXT NOT NULL DEFAULT 'STOPPED',
            policy_version TEXT,
            started_at TIMESTAMPTZ,
            stopped_at TIMESTAMPTZ,
            last_actor TEXT,
            cycle_count BIGINT NOT NULL DEFAULT 0,
            last_eval_at TIMESTAMPTZ,
            next_eval_at TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            connection_ok BOOLEAN,
            last_error TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_events (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_type TEXT NOT NULL,
            actor TEXT,
            detail TEXT,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS active_equity_ticks (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            equity NUMERIC NOT NULL,
            cash NUMERIC NOT NULL,
            invested NUMERIC NOT NULL
        )"""
    )
    row = execute("SELECT id FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()
    if not row:
        execute(
            """INSERT INTO active_accounts(id, cash, initial_capital, peak_equity, meta_json)
               VALUES (%s,%s,%s,%s,%s::jsonb)""",
            (
                ACCOUNT_B,
                INITIAL_CASH,
                INITIAL_CASH,
                INITIAL_CASH,
                '{"isolated":true,"paper_only":true,"strategy":"B","reset_forbidden_auto":true}',
            ),
        )
    st = execute("SELECT id FROM active_state WHERE id=1").fetchone()
    if not st:
        execute(
            """INSERT INTO active_state(id, status, policy_version, meta_json)
               VALUES (1,'STOPPED',%s,'{"paper_only":true}'::jsonb)""",
            (POLICY_B_VERSION,),
        )
