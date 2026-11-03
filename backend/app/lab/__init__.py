"""Lab auto paper-trading — isolated from SMA paper account and Shadow research ledger.

Authorized strategy for automatic execution: SMA10_SMA50_1H only.
AI / Shadow remains observational — never auto-promoted here.
PAPER_ONLY: no real Binance orders, no private keys.
"""

AUTHORIZED_STRATEGY = "SMA10_SMA50_1H"
LAB_ACCOUNT_ID = "lab_auto"
LAB_INITIAL_CAPITAL = 1000
ORDER_STATUSES = (
    "NEW",
    "VALIDATED",
    "REJECTED",
    "FILLED",
    "PARTIALLY_FILLED",
    "CANCELLED",
)
