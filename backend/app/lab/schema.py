"""Lab paper ledger schema — never touches account/positions/trades SMA tables."""
from __future__ import annotations

from typing import Callable

from . import LAB_ACCOUNT_ID, LAB_INITIAL_CAPITAL


def ensure_lab_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS lab_accounts(
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            label TEXT NOT NULL,
            cash NUMERIC NOT NULL,
            initial_capital NUMERIC NOT NULL,
            notes TEXT
        )"""
    )
    execute(
        """INSERT INTO lab_accounts(id, label, cash, initial_capital, notes)
           VALUES(%s, 'Lab auto paper trading', %s, %s,
                  'Isolated from SMA paper (account) and research_sim virt ledger')
           ON CONFLICT DO NOTHING""",
        (LAB_ACCOUNT_ID, LAB_INITIAL_CAPITAL, LAB_INITIAL_CAPITAL),
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_positions(
            account_id TEXT NOT NULL REFERENCES lab_accounts(id),
            symbol TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            cost NUMERIC NOT NULL,
            entry_price NUMERIC,
            opened_at TIMESTAMPTZ DEFAULT NOW(),
            opened_candle_ms BIGINT,
            stop_loss_pct NUMERIC DEFAULT 0.02,
            take_profit_pct NUMERIC DEFAULT 0.04,
            max_hold_bars INT DEFAULT 48,
            PRIMARY KEY(account_id, symbol)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_trades(
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES lab_accounts(id),
            at TIMESTAMPTZ DEFAULT NOW(),
            order_uid UUID,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            fee NUMERIC NOT NULL DEFAULT 0,
            slip NUMERIC NOT NULL DEFAULT 0,
            candle_ms BIGINT NOT NULL,
            strategy TEXT NOT NULL,
            reason TEXT,
            realized_pnl NUMERIC,
            UNIQUE(account_id, symbol, side, candle_ms)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_signals(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            signal_uid UUID NOT NULL UNIQUE,
            strategy TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            candle_ms BIGINT NOT NULL,
            ref_price NUMERIC,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE(strategy, symbol, side, candle_ms)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_orders(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            order_uid UUID NOT NULL UNIQUE,
            account_id TEXT NOT NULL REFERENCES lab_accounts(id),
            signal_id BIGINT REFERENCES lab_signals(id),
            strategy TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            candle_ms BIGINT NOT NULL,
            requested_qty NUMERIC,
            filled_qty NUMERIC DEFAULT 0,
            budget NUMERIC,
            ref_price NUMERIC,
            avg_price NUMERIC,
            fee NUMERIC DEFAULT 0,
            slip NUMERIC DEFAULT 0,
            reject_reason TEXT,
            stop_triggered BOOLEAN DEFAULT FALSE,
            stop_trigger_price NUMERIC,
            execution_price NUMERIC,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT lab_orders_status_chk CHECK (status IN (
              'NEW','VALIDATED','REJECTED','FILLED','PARTIALLY_FILLED','CANCELLED'
            )),
            UNIQUE(account_id, strategy, symbol, side, candle_ms)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_executor_state(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'UNKNOWN',
            paused BOOLEAN NOT NULL DEFAULT FALSE,
            pause_reason TEXT,
            heartbeat_at TIMESTAMPTZ,
            last_cycle_at TIMESTAMPTZ,
            last_cycle_ok BOOLEAN,
            last_error TEXT,
            cycle_count BIGINT NOT NULL DEFAULT 0,
            orders_filled BIGINT NOT NULL DEFAULT 0,
            orders_rejected BIGINT NOT NULL DEFAULT 0,
            breaker_active BOOLEAN NOT NULL DEFAULT FALSE,
            breaker_reason TEXT,
            authorized_strategy TEXT NOT NULL DEFAULT 'SMA10_SMA50_1H',
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """INSERT INTO lab_executor_state(id, status, paused, pause_reason)
           VALUES(1, 'UNKNOWN', FALSE, NULL) ON CONFLICT DO NOTHING"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_equity_daily(
            account_id TEXT NOT NULL REFERENCES lab_accounts(id),
            day DATE NOT NULL,
            start_equity NUMERIC NOT NULL,
            end_equity NUMERIC,
            PRIMARY KEY(account_id, day)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_audit(
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ DEFAULT NOW(),
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_cycles(
            id BIGSERIAL PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            duration_ms INT,
            ok BOOLEAN,
            paused BOOLEAN DEFAULT FALSE,
            symbols_scanned INT DEFAULT 0,
            signals_buy INT DEFAULT 0,
            signals_sell INT DEFAULT 0,
            signals_hold INT DEFAULT 0,
            orders_generated INT DEFAULT 0,
            orders_rejected INT DEFAULT 0,
            orders_filled INT DEFAULT 0,
            errors INT DEFAULT 0,
            hold_sample_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS lab_breaker_events(
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ DEFAULT NOW(),
            active BOOLEAN NOT NULL,
            reason TEXT,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
