"""AA6 — estadística con dependencia temporal (bootstrap por bloques)."""
from __future__ import annotations

import math
import random
from typing import Any


def block_bootstrap_mean_diff(
    a: list[float],
    b: list[float],
    *,
    block: int = 5,
    n_boot: int = 400,
    seed: int = 42,
) -> dict[str, Any]:
    """IC aproximado para media(a-b) con bootstrap por bloques."""
    n = min(len(a), len(b))
    if n < max(20, block * 3):
        return {"ok": False, "reason": "sample_too_small", "n": n}
    diff = [a[i] - b[i] for i in range(n)]
    rng = random.Random(seed)
    means = []
    n_blocks = max(1, n // block)
    for _ in range(n_boot):
        sample = []
        while len(sample) < n:
            start = rng.randint(0, n - block)
            sample.extend(diff[start : start + block])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    m = sum(diff) / n
    return {
        "ok": True,
        "n": n,
        "block": block,
        "n_boot": n_boot,
        "mean_diff_daily": round(m, 8),
        "ci95": [round(lo, 8), round(hi, 8)],
        "ci_includes_zero": lo <= 0 <= hi,
    }


def summarize_stats(eval_pack: dict[str, Any]) -> dict[str, Any]:
    rets = eval_pack.get("daily_returns") or {}
    a = rets.get("Z-TSMOM-D28H5") or []
    b = rets.get("Z-BH-EQ") or []
    boot = block_bootstrap_mean_diff(a, b)
    # concentración: top 5 días del exceso
    n = min(len(a), len(b))
    diffs = sorted((a[i] - b[i] for i in range(n)), reverse=True)
    top5 = sum(diffs[:5]) if diffs else 0.0
    total_pos = sum(x for x in diffs if x > 0) or 1e-12
    return {
        "bootstrap_excess_daily": boot,
        "top5_positive_diff_share_of_positive": round(top5 / total_pos, 4) if diffs else None,
        "n_daily": n,
        "note": "p-value aislado no es evidencia de rentabilidad futura",
    }
