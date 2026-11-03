"""ML persistence schema — additive only."""
from __future__ import annotations

from typing import Callable


def _add_column(execute: Callable, table: str, column: str, ddl: str) -> None:
    execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")


def ensure_ml_schema(execute: Callable) -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS ml_datasets(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            interval TEXT NOT NULL,
            checksum TEXT NOT NULL UNIQUE,
            row_count INT NOT NULL,
            meta_json JSONB NOT NULL,
            data_path TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ml_models(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            version TEXT NOT NULL UNIQUE,
            algorithm TEXT NOT NULL,
            model_hash TEXT NOT NULL,
            artifact_path TEXT NOT NULL,
            metrics_json JSONB NOT NULL,
            status TEXT NOT NULL,
            validated_for_research BOOLEAN NOT NULL DEFAULT FALSE,
            validated_for_paper_ai BOOLEAN NOT NULL DEFAULT FALSE,
            feature_names JSONB NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ml_predictions(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            model_version TEXT NOT NULL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            decision_ts TIMESTAMPTZ NOT NULL,
            candle_open_ms BIGINT NOT NULL,
            horizon INT NOT NULL,
            probability DOUBLE PRECISION NOT NULL,
            proposed_action TEXT NOT NULL,
            accepted BOOLEAN NOT NULL DEFAULT FALSE,
            reject_reason TEXT,
            feature_version TEXT,
            observed_label INT,
            observed_at TIMESTAMPTZ,
            UNIQUE(model_version, symbol, interval, candle_open_ms, horizon)
        )"""
    )
    # Etapa F additive columns
    _add_column(execute, "ml_predictions", "resolution_status", "TEXT")
    _add_column(execute, "ml_predictions", "observed_net_return", "DOUBLE PRECISION")
    _add_column(execute, "ml_predictions", "data_quality", "TEXT")
    _add_column(execute, "ml_predictions", "resolve_meta", "JSONB")
    _add_column(execute, "ml_predictions", "source", "TEXT DEFAULT 'shadow_live'")
    _add_column(execute, "ml_predictions", "calibrated_probability", "DOUBLE PRECISION")

    execute(
        """CREATE TABLE IF NOT EXISTS ml_runtime(
            id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL DEFAULT 'SHADOW_AI',
            active_model_version TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            notes TEXT
        )"""
    )
    execute(
        """INSERT INTO ml_runtime(id, mode, notes)
           VALUES(1, 'SHADOW_AI', 'default shadow — no simulated execution by AI')
           ON CONFLICT DO NOTHING"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ml_experiments(
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            name TEXT NOT NULL,
            params_json JSONB NOT NULL,
            metrics_json JSONB NOT NULL,
            notes TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS circuit_breaker_state(
            id INTEGER PRIMARY KEY,
            active BOOLEAN NOT NULL DEFAULT FALSE,
            reason TEXT,
            evidence_json JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    execute(
        """INSERT INTO circuit_breaker_state(id, active, reason)
           VALUES(1, FALSE, NULL) ON CONFLICT DO NOTHING"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS circuit_breaker_events(
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ DEFAULT NOW(),
            reason TEXT NOT NULL,
            evidence_json JSONB,
            action TEXT NOT NULL
        )"""
    )
    # Backfill pending status for unresolved rows
    execute(
        """UPDATE ml_predictions
           SET resolution_status='PENDING'
           WHERE observed_label IS NULL
             AND (resolution_status IS NULL OR resolution_status='')"""
    )
