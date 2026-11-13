"""Etapa AA PRO — validación temporal independiente de Z-TSMOM-D28H5.

No modifica la estrategia. No activa carteras. PAPER_ONLY.
"""
from __future__ import annotations

from datetime import datetime, timezone

ETAPA = "AA"
PAPER_ONLY = True
ACTIVATE_FORBIDDEN = True
TARGET_ID = "Z-TSMOM-D28H5"
EXPECTED_CONFIG_HASH = "5326edb8a539cfe5"
Z_COMMIT = "614bb9d78710a4c27bd50505577f05b582a00d7a"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

EVAL_START = datetime(2025, 11, 1, tzinfo=timezone.utc)
EVAL_END_EXCLUSIVE = datetime(2026, 11, 1, tzinfo=timezone.utc)  # hasta 2026-10-31 inclusive
EVAL_START_MS = int(EVAL_START.timestamp() * 1000)
EVAL_END_MS = int(EVAL_END_EXCLUSIVE.timestamp() * 1000) - 60_000  # last 1d open_time 2026-10-31
