"""Metadatos de historial en PostgreSQL (no OHLC operativo)."""
from __future__ import annotations

from typing import Any, Callable


DDL = """
CREATE TABLE IF NOT EXISTS research_history_files (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  year INT NOT NULL,
  month INT NOT NULL,
  source_url TEXT,
  sha256 TEXT,
  checksum_match BOOLEAN,
  n_bars INT,
  gap_count INT,
  missing_bars_est INT,
  ohlc_violations INT,
  duplicates INT,
  parquet_path TEXT,
  parquet_sha256 TEXT,
  bytes BIGINT,
  validation_ok BOOLEAN,
  downloaded_at TIMESTAMPTZ,
  written_at TIMESTAMPTZ DEFAULT NOW(),
  meta_json JSONB DEFAULT '{}'::jsonb,
  UNIQUE(symbol, interval, year, month)
);

CREATE TABLE IF NOT EXISTS research_history_coverage (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  first_open_time BIGINT,
  last_open_time BIGINT,
  n_bars BIGINT,
  gap_count INT,
  missing_bars_est BIGINT,
  coverage_pct DOUBLE PRECISION,
  source TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(symbol, interval)
);

CREATE TABLE IF NOT EXISTS research_history_jobs (
  id BIGSERIAL PRIMARY KEY,
  job_name TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def ensure_history_schema(execute: Callable) -> None:
    for stmt in [s.strip() for s in DDL.split(";") if s.strip()]:
        execute(stmt)


def upsert_file_meta(execute: Callable, meta: dict[str, Any]) -> None:
    ensure_history_schema(execute)
    v = meta.get("validation") or {}
    execute(
        """
        INSERT INTO research_history_files(
          symbol, interval, year, month, source_url, sha256, checksum_match,
          n_bars, gap_count, missing_bars_est, ohlc_violations, duplicates,
          parquet_path, parquet_sha256, bytes, validation_ok, downloaded_at, meta_json
        ) VALUES (
          %(symbol)s, %(interval)s, %(year)s, %(month)s, %(source_url)s, %(sha256)s, %(checksum_match)s,
          %(n_bars)s, %(gap_count)s, %(missing_bars_est)s, %(ohlc_violations)s, %(duplicates)s,
          %(parquet_path)s, %(parquet_sha256)s, %(bytes)s, %(validation_ok)s,
          %(downloaded_at)s, %(meta_json)s::jsonb
        )
        ON CONFLICT (symbol, interval, year, month) DO UPDATE SET
          source_url=EXCLUDED.source_url,
          sha256=EXCLUDED.sha256,
          checksum_match=EXCLUDED.checksum_match,
          n_bars=EXCLUDED.n_bars,
          gap_count=EXCLUDED.gap_count,
          missing_bars_est=EXCLUDED.missing_bars_est,
          ohlc_violations=EXCLUDED.ohlc_violations,
          duplicates=EXCLUDED.duplicates,
          parquet_path=EXCLUDED.parquet_path,
          parquet_sha256=EXCLUDED.parquet_sha256,
          bytes=EXCLUDED.bytes,
          validation_ok=EXCLUDED.validation_ok,
          downloaded_at=EXCLUDED.downloaded_at,
          written_at=NOW(),
          meta_json=EXCLUDED.meta_json
        """,
        {
            "symbol": meta["symbol"],
            "interval": meta["interval"],
            "year": meta["year"],
            "month": meta["month"],
            "source_url": (meta.get("source") or {}).get("source")
            or (meta.get("source") or {}).get("url"),
            "sha256": (meta.get("source") or {}).get("sha256"),
            "checksum_match": (meta.get("source") or {}).get("checksum_match"),
            "n_bars": meta.get("n_bars"),
            "gap_count": v.get("gap_count"),
            "missing_bars_est": v.get("missing_bars_est"),
            "ohlc_violations": v.get("ohlc_violations"),
            "duplicates": v.get("duplicates"),
            "parquet_path": meta.get("path"),
            "parquet_sha256": meta.get("parquet_sha256"),
            "bytes": meta.get("bytes"),
            "validation_ok": bool(v.get("ok")),
            "downloaded_at": (meta.get("source") or {}).get("downloaded_at"),
            "meta_json": __import__("json").dumps(
                {"validation": {k: v[k] for k in v if k != "gaps"}, "gaps_sample": (v.get("gaps") or [])[:5]}
            ),
        },
    )


def upsert_coverage(execute: Callable, cov: dict[str, Any]) -> None:
    ensure_history_schema(execute)
    execute(
        """
        INSERT INTO research_history_coverage(
          symbol, interval, first_open_time, last_open_time, n_bars,
          gap_count, missing_bars_est, coverage_pct, source, updated_at
        ) VALUES (
          %(symbol)s, %(interval)s, %(first)s, %(last)s, %(n)s,
          %(gaps)s, %(missing)s, %(pct)s, %(source)s, NOW()
        )
        ON CONFLICT (symbol, interval) DO UPDATE SET
          first_open_time=EXCLUDED.first_open_time,
          last_open_time=EXCLUDED.last_open_time,
          n_bars=EXCLUDED.n_bars,
          gap_count=EXCLUDED.gap_count,
          missing_bars_est=EXCLUDED.missing_bars_est,
          coverage_pct=EXCLUDED.coverage_pct,
          source=EXCLUDED.source,
          updated_at=NOW()
        """,
        {
            "symbol": cov["symbol"],
            "interval": cov["interval"],
            "first": cov.get("first_open_time"),
            "last": cov.get("last_open_time"),
            "n": cov.get("n_bars"),
            "gaps": cov.get("gap_count"),
            "missing": cov.get("missing_bars_est"),
            "pct": cov.get("coverage_pct"),
            "source": cov.get("source") or "binance_vision",
        },
    )


def coverage_snapshot(execute: Callable) -> list[dict[str, Any]]:
    ensure_history_schema(execute)
    rows = execute(
        """SELECT symbol, interval, first_open_time, last_open_time, n_bars,
                  gap_count, missing_bars_est, coverage_pct, source, updated_at
           FROM research_history_coverage ORDER BY symbol, interval"""
    ).fetchall()
    return [dict(r) for r in rows]


def files_snapshot(execute: Callable) -> list[dict[str, Any]]:
    ensure_history_schema(execute)
    rows = execute(
        """SELECT symbol, interval, year, month, n_bars, gap_count, missing_bars_est,
                  validation_ok, checksum_match, bytes, written_at
           FROM research_history_files ORDER BY symbol, interval, year, month"""
    ).fetchall()
    return [dict(r) for r in rows]
