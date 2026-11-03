"""Prospective research engine — immutable decisions, separate from paper SMA ledger.

Experiment kinds (never mixed in metrics):
  BACKTEST | SHADOW_REPLAY | SHADOW_LIVE | PAPER_TRADE

PAPER_TRADE here means a *separate virtual research ledger*, not the existing SMA paper account.
No real orders. PAPER_AI is never auto-enabled.
"""

EXPERIMENT_KINDS = ("BACKTEST", "SHADOW_REPLAY", "SHADOW_LIVE", "PAPER_TRADE")
DECISION_ACTIONS = ("BUY", "SELL", "HOLD")
RESOLUTION_STATES = ("PENDING", "RESOLVED", "INVALID")
