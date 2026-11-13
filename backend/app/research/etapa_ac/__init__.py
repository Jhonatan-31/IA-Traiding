"""Etapa AC PRO V2 — auditoría institucional del sistema.

No activa A/B. No activa AB-PROSPECT. No modifica D28H5 ni ledgers.
"""
from __future__ import annotations

ETAPA = "AC"
PAPER_ONLY = True
ACTIVATE_FORBIDDEN = True
AB_COMMIT = "e2d95bed4dcf0d4103d29082f39b9ab4614f2101"
EXPECTED_CONFIG_HASH = "5326edb8a539cfe5"
PROSPECT_MUST_REMAIN = "PREPARED_DISABLED"
