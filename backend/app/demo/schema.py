"""Isolated DEMO ledger — never mutates sma/lab/research/express."""
from __future__ import annotations

from typing import Callable

from . import ACCOUNT_ID, INITIAL_CASH, POLICY_VERSION


def ensure_demo_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS demo_accounts (
            id TEXT PRIMARY KEY,
            cash NUMERIC NOT NULL,
            initial_capital NUMERIC NOT NULL,
            peak_equity NUMERIC NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS demo_positions (
            account_id TEXT NOT NULL REFERENCES demo_accounts(id),
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
        """CREATE TABLE IF NOT EXISTS demo_orders (
            id BIGSERIAL PRIMARY KEY,
            order_uid UUID NOT NULL UNIQUE,
            account_id TEXT NOT NULL REFERENCES demo_accounts(id),
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
            correlation_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (account_id, symbol, side, candle_1m_ms)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS demo_trades (
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES demo_accounts(id),
            order_id BIGINT REFERENCES demo_orders(id),
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
        """CREATE TABLE IF NOT EXISTS demo_decisions (
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
        """CREATE TABLE IF NOT EXISTS demo_events (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_type TEXT NOT NULL,
            actor TEXT,
            detail TEXT,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS demo_rejects (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT,
            reason TEXT NOT NULL,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS demo_state (
            id INT PRIMARY KEY DEFAULT 1 CHECK (id=1),
            status TEXT NOT NULL DEFAULT 'STOPPED'
                CHECK (status IN ('STOPPED','RUNNING')),
            started_at TIMESTAMPTZ,
            stopped_at TIMESTAMPTZ,
            last_actor TEXT,
            heartbeat_at TIMESTAMPTZ,
            last_eval_at TIMESTAMPTZ,
            next_eval_at TIMESTAMPTZ,
            cycle_count BIGINT NOT NULL DEFAULT 0,
            last_error TEXT,
            connection_ok BOOLEAN DEFAULT TRUE,
            policy_version TEXT,
            coverage_gap_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS demo_equity_ticks (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            equity NUMERIC NOT NULL,
            cash NUMERIC NOT NULL,
            invested NUMERIC NOT NULL
        )"""
    )

    if not execute("SELECT id FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone():
        execute(
            """INSERT INTO demo_accounts(id, cash, initial_capital, peak_equity, meta_json)
               VALUES (%s,%s,%s,%s,%s::jsonb)""",
            (
                ACCOUNT_ID,
                INITIAL_CASH,
                INITIAL_CASH,
                INITIAL_CASH,
                '{"paper_only":true,"isolated":true,"reset_forbidden_auto":true}',
            ),
        )
    if not execute("SELECT id FROM demo_state WHERE id=1").fetchone():
        execute(
            """INSERT INTO demo_state(id, status, policy_version, meta_json)
               VALUES (1,'STOPPED',%s,'{}'::jsonb)""",
            (POLICY_VERSION,),
        )
