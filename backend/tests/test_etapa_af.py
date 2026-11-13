"""Etapa AF — SLI longitudinal, UNKNOWN≠up, public health, alertas."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.ops.reliability import (
    classify_overall,
    maybe_record_sample,
    window_stats,
)


class _Store:
    def __init__(self):
        self.meta = {
            "measurements_started_at": datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc),
            "last_sample_at": None,
            "sample_interval_s": 60,
        }
        self.samples: list[dict] = []

    def execute(self, sql: str, params=None):
        s = " ".join(sql.split()).lower()
        params = params or ()
        if "create table" in s or "create unique index" in s:
            return self
        if "insert into reliability_meta" in s:
            return self
        if "insert into reliability_samples" in s:
            bucket = params[1]
            if any(x["sample_bucket"] == bucket for x in self.samples):
                return self  # conflict do nothing
            self.samples.append(
                {
                    "sampled_at": params[0],
                    "sample_bucket": bucket,
                    "overall": params[7],
                    "api_ok": params[2],
                    "db_ok": params[3],
                    "demo_functional": params[4],
                    "active_functional": params[5],
                    "market_stale": params[6],
                }
            )
            return self
        if "update reliability_meta" in s:
            self.meta["last_sample_at"] = params[0]
            return self
        if "delete from reliability_samples" in s:
            return self
        if "from reliability_meta" in s:
            return _Res(self.meta)
        if "from reliability_samples" in s and "order by sampled_at asc" in s:
            start, end = params[0], params[1]
            rows = [r for r in self.samples if start <= r["sampled_at"] <= end]
            return _ResList(rows)
        if "from reliability_samples" in s:
            return _ResList(list(reversed(self.samples[-48:])))
        if "continuity_gap_events" in s:
            return _ResList([])
        return self

    def fetchone(self):
        return None


class _Res:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _ResList:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_af_classify_overall():
    assert classify_overall(api_ok=True, db_ok=True, demo_functional="READY", active_functional="READY") == "OPERATIONAL"
    assert classify_overall(api_ok=False, db_ok=True, demo_functional="READY", active_functional="READY") == "DOWN"
    assert classify_overall(api_ok=True, db_ok=True, demo_functional="UNKNOWN", active_functional="READY") == "UNKNOWN"
    assert classify_overall(api_ok=True, db_ok=True, demo_functional="DEGRADED", active_functional="READY") == "DEGRADED"


def test_af_idempotent_sample_bucket():
    st = _Store()
    t0 = datetime(2026, 11, 13, 16, 10, 5, tzinfo=timezone.utc)
    maybe_record_sample(
        st.execute,
        api_ok=True,
        db_ok=True,
        demo_functional="READY",
        active_functional="READY",
        market_stale=False,
        now=t0,
    )
    maybe_record_sample(
        st.execute,
        api_ok=True,
        db_ok=True,
        demo_functional="READY",
        active_functional="READY",
        market_stale=False,
        now=t0 + timedelta(seconds=20),
    )
    assert len(st.samples) == 1


def test_af_unknown_and_missing_not_counted_as_up():
    st = _Store()
    start = st.meta["measurements_started_at"]
    # 3 operational + 1 down in first 4 minutes; expect ~4 slots if now = start+4min
    for i, overall_pair in enumerate(
        [("READY", "READY"), ("READY", "READY"), ("READY", "READY"), ("DOWN", "READY")]
    ):
        maybe_record_sample(
            st.execute,
            api_ok=True,
            db_ok=True,
            demo_functional=overall_pair[0],
            active_functional=overall_pair[1],
            market_stale=False,
            now=start + timedelta(minutes=i),
        )
    now = start + timedelta(minutes=10)  # expected ~10 samples; missing many
    w = window_stats(st.execute, window_s=86400, now=now)
    assert w["unknown_not_counted_as_up"] is True
    assert w["missing_samples"] > 0
    assert w["evidence_status"] in {"EVIDENCIA_EN_ACUMULACION", "COBERTURA_SUFICIENTE_PARA_VENTANA", "SIN_MUESTRAS"}
    # strict ratio uses expected denom — missing pulls availability down
    assert w["strict_operational_ratio"] is not None
    assert w["strict_operational_ratio"] < 1.0


def test_af_public_health_source_has_no_balances():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("app", "main.py").read_text(encoding="utf-8")
    # Isolate the public_health function body
    start = src.index("def public_health")
    end = src.index("\n@app.", start + 1) if "\n@app." in src[start + 1 :] else start + 1200
    chunk = src[start:end]
    assert "positions" not in chunk
    assert "LAB_CONTROL_TOKEN" not in chunk
    assert "DB_PASSWORD" not in chunk
    assert "deploy_commit" in chunk
    assert "PAPER_ONLY" in chunk
    assert "balances" in chunk.lower()


def test_af_protection_label_no_positions():
    from app.ops.health_center import protection_status
    from app.ops.continuity import classify_gap

    p = protection_status(
        bot_status="STOPPED",
        open_positions=0,
        gap=classify_gap(10.0),
        price_stale=False,
    )
    assert p["protection"] == "SIN_POSICIONES_QUE_PROTEGER"
