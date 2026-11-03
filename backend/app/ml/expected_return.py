"""Expected net return estimation — explicit assumptions, no invented magnitudes."""
from __future__ import annotations

from typing import Any

import numpy as np


def estimate_expected_net(
    *,
    p_up: float | None,
    mean_gain_if_up: float | None,
    mean_loss_if_down: float | None,
    fee_rate: float = 0.001,
    slip_rate: float = 0.001,
    non_execution_prob: float | None = None,
) -> dict[str, Any]:
    """
    E[net] ≈ p * G + (1-p) * L - already-included path costs OR subtract roundtrip.

    Convention:
    - mean_gain_if_up / mean_loss_if_down should be **gross** fractional moves before costs
      if provided; we subtract roundtrip_cost. If they are already net, set fee/slip=0.
    - If any input missing → report uncertainty, do not invent.
    """
    roundtrip = 2 * (fee_rate + slip_rate)
    missing = []
    if p_up is None:
        missing.append("p_up")
    if mean_gain_if_up is None:
        missing.append("mean_gain_if_up")
    if mean_loss_if_down is None:
        missing.append("mean_loss_if_down")
    if missing:
        return {
            "expected_net": None,
            "uncertain": True,
            "missing": missing,
            "roundtrip_cost": roundtrip,
            "non_execution_prob": non_execution_prob,
            "note": "Insufficient data to estimate expected net; abstain.",
        }
    # mean_loss_if_down expected negative
    g = float(mean_gain_if_up) - roundtrip
    loss = float(mean_loss_if_down) - roundtrip
    p = float(p_up)
    e = p * g + (1 - p) * loss
    if non_execution_prob is not None:
        # if cannot execute, earn 0
        e = (1 - float(non_execution_prob)) * e
    return {
        "expected_net": float(e),
        "uncertain": False,
        "components": {
            "p_up": p,
            "net_if_up": g,
            "net_if_down": loss,
            "roundtrip_cost": roundtrip,
            "non_execution_prob": non_execution_prob,
        },
        "decision_hint": "enter_candidate" if e > 0 and p >= 0.55 else "abstain",
    }


def empirical_gain_loss_from_history(
    nets: list[float],
) -> dict[str, float | None]:
    """Estimate conditional magnitudes from historical **net** returns (costs already in)."""
    arr = np.asarray(nets, dtype=float)
    if len(arr) == 0:
        return {"mean_gain_if_up": None, "mean_loss_if_down": None, "n": 0}
    ups = arr[arr > 0]
    downs = arr[arr <= 0]
    return {
        "mean_gain_if_up": float(ups.mean()) if len(ups) else None,
        "mean_loss_if_down": float(downs.mean()) if len(downs) else None,
        "n_up": int(len(ups)),
        "n_down": int(len(downs)),
        "note": "Magnitudes already net of historical cost assumptions; pass fee=0 when combining.",
    }


def attach_expected_nets(
    probabilities: np.ndarray,
    *,
    mean_gain_net: float | None,
    mean_loss_net: float | None,
) -> np.ndarray:
    """Vector of E[net] using already-net conditional means (fee/slip=0 in formula)."""
    out = np.full(len(probabilities), np.nan)
    for i, p in enumerate(probabilities):
        est = estimate_expected_net(
            p_up=float(p),
            mean_gain_if_up=mean_gain_net,
            mean_loss_if_down=mean_loss_net,
            fee_rate=0.0,
            slip_rate=0.0,
        )
        if est["expected_net"] is not None:
            out[i] = est["expected_net"]
    return out
