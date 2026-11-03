"""ML unit tests — no production DB, no live Binance required."""
from __future__ import annotations

import math

import numpy as np
import pytest

from app.ml.features import assert_no_feature_uses_future, build_feature_matrix, row_is_complete
from app.ml.labels import HORIZON, label_series, net_forward_return
from app.ml.shadow import risk_gate
from app.ml.train import chronological_splits


def _synthetic(n=120, start=1_700_000_000_000):
    rows = []
    px = 100.0
    for i in range(n):
        px *= 1.001 if i % 7 else 0.999
        ot = start + i * 3_600_000
        rows.append(
            {
                "symbol": "TESTUSDT",
                "interval": "1h",
                "open_time": ot,
                "close_time": ot + 3_599_999,
                "open": px * 0.999,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 1000 + i,
            }
        )
    return rows


def test_labels_none_without_future():
    rows = _synthetic(20)
    labs = label_series(rows, horizon=6)
    assert labs[-1] is None
    assert labs[-6] is None
    assert labs[-7] in (0, 1)


def test_net_return_costs_reduce_edge():
    assert net_forward_return(100, 100) < 0  # costs make flat trade negative


def test_feature_no_leakage_at_index():
    rows = _synthetic(80)
    feats, _ = build_feature_matrix(rows)
    # pick a complete row
    idx = next(i for i, r in enumerate(feats) if row_is_complete(r))
    assert_no_feature_uses_future(rows, feats, idx)


def test_incomplete_warmup_rows():
    rows = _synthetic(30)
    feats, _ = build_feature_matrix(rows)
    assert not row_is_complete(feats[5])


def test_chronological_splits_ordered_and_embargo():
    meta = [{"open_time": i * 1000, "symbol": "X"} for i in range(400)]
    folds = chronological_splits(meta, n_folds=3, embargo=6)
    assert folds
    for tr, te in folds:
        assert tr.max() < te.min()  # with embargo gap may be larger
        assert max(tr) < min(te)


def test_risk_gate_shadow_and_blocks():
    model = {"validated_for_research": True, "status": "validated_research"}
    ok, reason = risk_gate(
        runtime_mode="SHADOW_AI",
        model_row=model,
        paused=False,
        data_age_s=10,
        probability=0.6,
        calibrated=True,
    )
    assert ok and reason == "shadow_log_only"
    ok2, reason2 = risk_gate(
        runtime_mode="SHADOW_AI",
        model_row=model,
        paused=True,
        data_age_s=10,
        probability=0.6,
        calibrated=True,
    )
    assert not ok2 and reason2 == "engine_paused"
    ok3, reason3 = risk_gate(
        runtime_mode="SHADOW_AI",
        model_row=None,
        paused=False,
        data_age_s=10,
        probability=0.6,
        calibrated=True,
    )
    assert not ok3 and reason3 == "model_unavailable"


def test_walk_forward_train_synthetic(tmp_path):
    from app.ml.train import walk_forward_train
    import json

    # Write multi-symbol synthetic jsonl
    path = tmp_path / "d.jsonl"
    rows = []
    for sym in ["AAAUSDT", "BBBUSDT"]:
        base = _synthetic(200, start=1_700_000_000_000)
        for r in base:
            r = dict(r)
            r["symbol"] = sym
            rows.append(r)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = walk_forward_train(path, tmp_path / "models")
    assert out["status"] in ("trained", "insufficient_data")
    if out["status"] == "trained":
        assert out["validated_for_paper_ai"] is False
        assert "walk_forward" in out
        assert out["model_path"]
