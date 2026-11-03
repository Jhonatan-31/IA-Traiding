"""Offline ML research package — Shadow AI only by default."""

SHADOW_MODE = "SHADOW_AI"
PAPER_AI_MODE = "PAPER_AI"  # requires explicit promotion; never live trading

TARGET_SPEC = {
    "name": "net_positive_next_6_1h",
    "interval": "1h",
    "horizon_bars": 6,
    "entry": "close of decision bar (closed candle only)",
    "exit": "close of bar t+6",
    "costs": {
        "fee_rate": 0.001,
        "slip_rate": 0.001,
        "roundtrip_cost_approx": 0.004,  # 2*(fee+slip)
    },
    "label": "1 if net return after costs > 0 else 0",
    "limitations": [
        "No order-book depth; fills are illustrative.",
        "Does not model partial fills or gaps beyond bar close.",
        "Label uses future closes only for training/eval, never as features.",
        "A positive probability is not a trade recommendation.",
    ],
}
