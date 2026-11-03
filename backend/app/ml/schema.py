"""ML persistence schema — additive only."""
from __future__ import annotations

from typing import Callable


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
