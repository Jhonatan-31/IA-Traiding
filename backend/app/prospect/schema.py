"""Additive schema for prospective experiments — never drops paper tables."""
from __future__ import annotations

from typing import Callable


def ensure_prospect_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS research_protocols(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            name TEXT NOT NULL UNIQUE,
            hypothesis TEXT NOT NULL,
            universe_json JSONB NOT NULL,
            period_json JSONB NOT NULL,
            strategy TEXT NOT NULL,
            params_json JSONB NOT NULL,
            costs_json JSONB NOT NULL,
            success_criteria TEXT NOT NULL,
            abandon_criteria TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS prospect_experiments(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            protocol_id BIGINT REFERENCES research_protocols(id),
            experiment_type TEXT NOT NULL,
            name TEXT NOT NULL,
            strategy TEXT NOT NULL,
            strategy_version TEXT NOT NULL DEFAULT 'v1',
            model_version TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT prospect_experiments_type_chk
              CHECK (experiment_type IN ('BACKTEST','SHADOW_REPLAY','SHADOW_LIVE','PAPER_TRADE'))
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS prospect_decisions(
            id BIGSERIAL PRIMARY KEY,
            decision_uid UUID NOT NULL UNIQUE,
            experiment_id BIGINT NOT NULL REFERENCES prospect_experiments(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decision_ts TIMESTAMPTZ NOT NULL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            strategy TEXT NOT NULL,
            strategy_version TEXT NOT NULL,
            model_version TEXT,
            data_ref_json JSONB NOT NULL,
            observed_price DOUBLE PRECISION,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            system_state_json JSONB NOT NULL,
            risk_state_json JSONB NOT NULL,
            estimated_costs_json JSONB NOT NULL,
            horizon_bars INT NOT NULL,
            candle_open_ms BIGINT,
            resolution_status TEXT NOT NULL DEFAULT 'PENDING',
            CONSTRAINT prospect_decisions_action_chk
              CHECK (action IN ('BUY','SELL','HOLD')),
            CONSTRAINT prospect_decisions_res_chk
              CHECK (resolution_status IN ('PENDING','RESOLVED','INVALID'))
        )"""
    )
    # Outcomes are append-only; decision row fields above are never rewritten except resolution_status
    execute(
        """CREATE TABLE IF NOT EXISTS prospect_outcomes(
            decision_id BIGINT PRIMARY KEY REFERENCES prospect_decisions(id),
            resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status TEXT NOT NULL,
            data_quality TEXT,
            observed_net_return DOUBLE PRECISION,
            observed_label INT,
            result_json JSONB NOT NULL,
            CONSTRAINT prospect_outcomes_status_chk
              CHECK (status IN ('RESOLVED','INVALID'))
        )"""
    )
    # Separate virtual research ledger (NOT account/positions/trades SMA paper)
    execute(
        """CREATE TABLE IF NOT EXISTS virt_accounts(
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            label TEXT NOT NULL,
            cash NUMERIC NOT NULL,
            initial_capital NUMERIC NOT NULL,
            notes TEXT
        )"""
    )
    execute(
        """INSERT INTO virt_accounts(id, label, cash, initial_capital, notes)
           VALUES('research_sim','Virtual research ledger',1000,1000,
                  'Separated from SMA paper account — Etapa H')
           ON CONFLICT DO NOTHING"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS virt_positions(
            account_id TEXT NOT NULL REFERENCES virt_accounts(id),
            symbol TEXT NOT NULL,
            qty NUMERIC NOT NULL,
            cost NUMERIC NOT NULL,
            opened_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(account_id, symbol)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS virt_ledger(
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES virt_accounts(id),
            at TIMESTAMPTZ DEFAULT NOW(),
            entry_type TEXT NOT NULL,
            symbol TEXT,
            amount NUMERIC NOT NULL,
            balance_after NUMERIC NOT NULL,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS virt_orders(
            id BIGSERIAL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES virt_accounts(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            decision_id BIGINT REFERENCES prospect_decisions(id),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_qty NUMERIC,
            filled_qty NUMERIC DEFAULT 0,
            avg_price NUMERIC,
            fee NUMERIC DEFAULT 0,
            slip NUMERIC DEFAULT 0,
            reason TEXT,
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT virt_orders_status_chk
              CHECK (status IN ('PENDING','REJECTED','PARTIAL','FILLED','CANCELLED'))
        )"""
    )
