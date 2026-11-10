"""Etapa Z PRO — laboratorio de investigación cuantitativa avanzada.

PAPER_ONLY. Sin activación. Sin modificación de carteras operativas.
"""
from __future__ import annotations

ETAPA = "Z"
PAPER_ONLY = True
ACTIVATE_FORBIDDEN = True
HOLDOUT_W_CONSUMED = True
INITIAL_CAPITAL = 1000.0
FEE_RATE = 0.001  # 10 bps taker spot retail
SLIP_RATE = 0.0005  # 5 bps conservador
SPREAD_BPS = 1.0  # 1 bp half-spread proxy cuando no hay BBO histórico
COST_RT = 2.0 * (FEE_RATE + SLIP_RATE) + (SPREAD_BPS / 10_000.0)
