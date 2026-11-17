"""Etapa AK — Execution simulation V2 (isolated; does not replace V1 engines).

PAPER_ONLY. No strategy activation. No ledger mutation by default.
"""
from __future__ import annotations

from .engine_v2 import ExecutionV2Assumptions, simulate_fill_v2, compare_v1_v2
from .bbo_store import BboQuote, BboRegistry, get_registry
from .cost_reconcile import reconcile_d28h5_costs_from_artifact

__all__ = [
    "ExecutionV2Assumptions",
    "simulate_fill_v2",
    "compare_v1_v2",
    "BboQuote",
    "BboRegistry",
    "get_registry",
    "reconcile_d28h5_costs_from_artifact",
]

ENGINE_VERSION = "execution_v2.1"
V1_ENGINE = "prospect.execution.estimate_fill_price"
