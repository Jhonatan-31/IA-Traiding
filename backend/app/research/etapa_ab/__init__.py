"""Etapa AB PRO — atribución económica, comparadores justos, observación preparada.

No modifica D28H5. No activa carteras. PAPER_ONLY.
Holdout AA (2025-11→2026-10) consumido: aquí solo análisis descriptivo/atribución.
"""
from __future__ import annotations

ETAPA = "AB"
PAPER_ONLY = True
ACTIVATE_FORBIDDEN = True
TARGET_ID = "Z-TSMOM-D28H5"
EXPECTED_CONFIG_HASH = "5326edb8a539cfe5"
AA_COMMIT = "759b971b08182fac9b0618f332db394c76006b66"
AA_HOLDOUT_CONSUMED = True
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
