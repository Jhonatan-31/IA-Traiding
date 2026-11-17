"""AM4–AM7 — experimento temporal V1/V2 sobre captura BBO (sin órdenes)."""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..prospect.execution import ExecutionAssumptions
from .bbo_store import BboQuote
from .compare_experiment import HypotheticalDecision, evaluate_pair, summarize_pairs
from .cost_decomposition import decompose_pair_costs
from .engine_v2 import ExecutionV2Assumptions

PARSER_VERSION = "am_bbo_jsonl_v1"
EXPERIMENT_ID_PREFIX = "AM-BBO"


@dataclass
class SizeScenario:
    label: str
    notional_usdt: float


DEFAULT_SIZES = (
    SizeScenario("n25", 25.0),
    SizeScenario("n100", 100.0),
    SizeScenario("n500", 500.0),
)


def experiment_hash(meta: dict[str, Any]) -> str:
    raw = json.dumps(meta, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _quote_from_event(ev: dict[str, Any]) -> BboQuote | None:
    try:
        return BboQuote(
            symbol=str(ev["symbol"]).upper(),
            bid_price=float(ev["bid_price"]),
            bid_qty=float(ev["bid_qty"]),
            ask_price=float(ev["ask_price"]),
            ask_qty=float(ev["ask_qty"]),
            received_at_ms=int(ev.get("received_at_ms") or ev.get("captured_at_ms") or 0),
            update_id=int(ev["update_id"]) if ev.get("update_id") is not None else None,
            received_mono_ns=ev.get("received_mono_ns"),
            connection_id=ev.get("connection_id"),
            source=str(ev.get("source") or "binance_bookTicker"),
            exchange_ts_ms=ev.get("exchange_ts_ms"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def subsample_by_bucket(
    events: list[dict[str, Any]],
    *,
    bucket_ms: int = 30_000,
) -> list[dict[str, Any]]:
    """Anti-pseudorreplicación: una muestra por (symbol, bucket temporal)."""
    chosen: dict[tuple[str, int], dict[str, Any]] = {}
    for ev in events:
        sym = str(ev.get("symbol") or "").upper()
        ts = int(ev.get("received_at_ms") or ev.get("captured_at_ms") or 0)
        if not sym or ts <= 0:
            continue
        key = (sym, ts // bucket_ms)
        # keep freshest in bucket
        prev = chosen.get(key)
        if prev is None or ts >= int(prev.get("received_at_ms") or 0):
            chosen[key] = ev
    return sorted(chosen.values(), key=lambda e: int(e.get("received_at_ms") or 0))


def qty_from_notional(notional_usdt: float, mid: float) -> float | None:
    if mid <= 0 or notional_usdt <= 0:
        return None
    return float(notional_usdt) / float(mid)


def evaluate_event(
    ev: dict[str, Any],
    *,
    side: str,
    qty: float | None = None,
    notional_usdt: float | None = None,
    max_bbo_age_ms: int = 5000,
    v1: ExecutionAssumptions | None = None,
    v2: ExecutionV2Assumptions | None = None,
) -> dict[str, Any]:
    bbo = _quote_from_event(ev)
    if bbo is None:
        return {
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "invalid_event",
            "quality": "BAD_EVENT",
        }
    decision_ts = int(ev.get("captured_at_ms") or bbo.received_at_ms)
    # Temporal alignment: BBO must be known at decision (received <= decision)
    if bbo.received_at_ms > decision_ts + 1:
        return {
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "bbo_after_decision",
            "quality": "MISALIGNED",
            "decision_ts_ms": decision_ts,
            "bbo_received_at_ms": bbo.received_at_ms,
        }
    age = max(0, decision_ts - bbo.received_at_ms)
    if age > max_bbo_age_ms:
        return {
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "stale_at_decision",
            "quality": "STALE",
            "bbo_age_ms": age,
        }
    mid = bbo.mid
    if qty is None:
        if notional_usdt is None:
            return {
                "comparable": False,
                "status": "NO_COMPARABLE",
                "reason": "missing_qty",
            }
        qty = qty_from_notional(notional_usdt, mid)
        if qty is None or qty <= 0:
            return {
                "comparable": False,
                "status": "NO_COMPARABLE",
                "reason": "invalid_qty_from_notional",
            }
    # Causal V1 ref = mid of same contemporaneous BBO (same instant as decision)
    decision = HypotheticalDecision(
        decision_ts_ms=decision_ts,
        symbol=bbo.symbol,
        side=side,
        qty=float(qty),
        ref_mid=mid,
    )
    row = evaluate_pair(
        decision,
        bbo,
        v1=v1 or ExecutionAssumptions(),
        v2=v2 or ExecutionV2Assumptions(max_quote_age_ms=max_bbo_age_ms),
        now_ms=decision_ts,
    )
    decomp = None
    if row.get("comparable"):
        decomp = decompose_pair_costs(
            side=side,
            qty=float(qty),
            ref_mid=mid,
            bbo=bbo,
            v1=v1 or ExecutionAssumptions(),
            v2=v2 or ExecutionV2Assumptions(max_quote_age_ms=max_bbo_age_ms),
            now_ms=decision_ts,
        )
    top_qty = bbo.ask_qty if side.upper() == "BUY" else bbo.bid_qty
    return {
        **row,
        "quality": "ALIGNED" if row.get("comparable") else row.get("reason"),
        "ref_v1": mid,
        "ref_v1_ts_ms": bbo.received_at_ms,
        "ref_v1_age_ms": age,
        "bbo_received_at_ms": bbo.received_at_ms,
        "top_qty_visible": top_qty,
        "cover_pct_top": None if qty <= 0 else min(1.0, float(top_qty) / float(qty)),
        "liquidity_warning": bool(qty > top_qty),
        "cost_decomposition": decomp,
        "notional_usdt": notional_usdt,
        "hypothesis_label": "HYPOTHETICAL_DECISION_NOT_A_FILL",
    }


def _pctiles(xs: list[float]) -> dict[str, float | None]:
    if not xs:
        return {"p5": None, "p25": None, "p50": None, "p75": None, "p95": None, "max": None}

    def q(p: float) -> float:
        return float(statistics.quantiles(xs, n=100)[p - 1]) if len(xs) >= 2 else float(xs[0])

    return {
        "p5": q(5) if len(xs) >= 20 else float(sorted(xs)[0]),
        "p25": q(25) if len(xs) >= 4 else float(sorted(xs)[0]),
        "p50": float(statistics.median(xs)),
        "p75": q(75) if len(xs) >= 4 else float(sorted(xs)[-1]),
        "p95": q(95) if len(xs) >= 20 else float(sorted(xs)[-1]),
        "max": float(max(xs)),
    }


def run_analysis_on_capture(
    events: list[dict[str, Any]],
    *,
    sides: Iterable[str] = ("BUY", "SELL"),
    sizes: Iterable[SizeScenario] = DEFAULT_SIZES,
    bucket_ms: int = 30_000,
    commit: str | None = None,
) -> dict[str, Any]:
    subsampled = subsample_by_bucket(events, bucket_ms=bucket_ms)
    rows: list[dict[str, Any]] = []
    spreads: list[float] = []
    for ev in subsampled:
        bbo = _quote_from_event(ev)
        if bbo is None:
            continue
        spreads.append(float(bbo.spread_abs))
        for side in sides:
            for sc in sizes:
                rows.append(
                    evaluate_event(
                        ev,
                        side=side,
                        notional_usdt=sc.notional_usdt,
                    )
                )
                rows[-1]["size_label"] = sc.label

    comparable = [r for r in rows if r.get("comparable")]
    rejected = [r for r in rows if not r.get("comparable")]
    diffs = [float(r["price_diff_v2_minus_v1_signed"]) for r in comparable]
    cost_gaps = [float(r["cost_gap_adverse_to_trader"]) for r in comparable]
    by_size: dict[str, Any] = {}
    for sc in sizes:
        sub = [r for r in comparable if r.get("size_label") == sc.label]
        d = [float(r["price_diff_v2_minus_v1_signed"]) for r in sub]
        by_size[sc.label] = {
            "n": len(sub),
            "notional_usdt": sc.notional_usdt,
            "median_price_diff": float(statistics.median(d)) if d else None,
            "n_partial_or_liquidity_warn": sum(
                1 for r in sub if r.get("liquidity_warning") or r.get("partial")
            ),
        }
    coverage: dict[str, int] = {}
    for ev in events:
        sym = str(ev.get("symbol") or "").upper()
        coverage[sym] = coverage.get(sym, 0) + 1

    meta = {
        "experiment_id": f"{EXPERIMENT_ID_PREFIX}-{int(time.time())}",
        "parser_version": PARSER_VERSION,
        "commit": commit,
        "n_events_raw": len(events),
        "n_events_bucketed": len(subsampled),
        "bucket_ms": bucket_ms,
        "anti_pseudoreplication": True,
    }
    meta["experiment_hash"] = experiment_hash(meta)
    summary = summarize_pairs(rows)
    return {
        "meta": meta,
        "coverage_by_symbol": coverage,
        "spread_abs_distribution": _pctiles(spreads),
        "price_diff_v2_minus_v1": _pctiles(diffs),
        "cost_gap_adverse": _pctiles(cost_gaps),
        "by_size": by_size,
        "summary": summary,
        "n_rows": len(rows),
        "n_comparable": len(comparable),
        "n_rejected": len(rejected),
        "reject_reasons": {
            k: sum(1 for r in rejected if r.get("reason") == k)
            for k in sorted({str(r.get("reason")) for r in rejected})
        },
        "sample_rows": comparable[:5] + rejected[:3],
        "limitations": [
            "Captura breve ≠ robustez estadística multi-régimen",
            "Top-of-book qty no garantiza hasta el fill",
            "V1 defaults (slip 10bps) ≠ V2 extra_slip 2bps — documentar al interpretar",
            "Sin L2: size>top_qty es incertidumbre/parcial, no fill real",
        ],
        "labels": {
            "observed": "BBO bookTicker",
            "hypothetical": "decisions",
            "estimated_fill": "V1/V2 sim",
            "paper_or_real": "NONE",
        },
    }


def write_analysis(path: Path, analysis: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
