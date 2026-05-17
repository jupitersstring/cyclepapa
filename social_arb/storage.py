"""DuckDB-backed storage for the social arbitrage pipeline.

DuckDB is zero-ops, embedded, columnar, and scales to ~100M rows on a laptop.
Tables:

    mentions(timestamp, source, source_id, ticker, alias, confidence,
             via, text, sentiment, sentiment_label, url, author)
    counts(date, ticker, source, mentions, sentiment_mean)

`upsert_mentions` is idempotent on (source, source_id, ticker).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


DDL = [
    """
    CREATE TABLE IF NOT EXISTS mentions (
        timestamp TIMESTAMP,
        source VARCHAR,
        source_id VARCHAR,
        ticker VARCHAR,
        alias VARCHAR,
        confidence DOUBLE,
        via VARCHAR,
        text VARCHAR,
        sentiment DOUBLE,
        sentiment_label VARCHAR,
        url VARCHAR,
        author VARCHAR,
        PRIMARY KEY (source, source_id, ticker)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_mentions_ticker_ts
    ON mentions(ticker, timestamp)
    """,
]


@contextmanager
def connect(cfg: Config) -> Iterator:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("duckdb not installed; pip install duckdb") from exc
    cfg.ensure_dirs()
    con = duckdb.connect(str(cfg.duckdb_path))
    try:
        for stmt in DDL:
            con.execute(stmt)
        yield con
    finally:
        con.close()


REQUIRED_COLUMNS = [
    "timestamp", "source", "source_id", "ticker", "alias", "confidence",
    "via", "text", "sentiment", "sentiment_label", "url", "author",
]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out = out[REQUIRED_COLUMNS]
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce").fillna(0.0)
    out["sentiment"] = pd.to_numeric(out["sentiment"], errors="coerce").fillna(0.0)
    for col in ("source", "source_id", "ticker", "alias", "via", "sentiment_label", "url", "author", "text"):
        out[col] = out[col].astype("string")
    return out


def upsert_mentions(cfg: Config, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    norm = _normalize(df).dropna(subset=["timestamp", "source", "source_id", "ticker"])
    if norm.empty:
        return 0
    with connect(cfg) as con:
        con.register("incoming", norm)
        before = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        con.execute(
            """
            INSERT INTO mentions
            SELECT * FROM incoming
            ON CONFLICT (source, source_id, ticker) DO NOTHING
            """
        )
        after = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        con.unregister("incoming")
    inserted = after - before
    log.info("upserted %d new mentions (%d duplicates skipped)", inserted, len(norm) - inserted)
    return inserted


def daily_counts(cfg: Config, ticker: str | None = None, source: str | None = None) -> pd.DataFrame:
    where = []
    if ticker:
        where.append(f"ticker = '{ticker.upper()}'")
    if source:
        where.append(f"source = '{source}'")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT
            CAST(timestamp AS DATE) AS date,
            ticker,
            source,
            COUNT(*) AS mentions,
            AVG(sentiment) AS sentiment_mean
        FROM mentions
        {clause}
        GROUP BY 1, 2, 3
        ORDER BY 1
    """
    with connect(cfg) as con:
        return con.execute(sql).df()


def recent_mentions(cfg: Config, ticker: str | None = None, limit: int = 200) -> pd.DataFrame:
    where = f"WHERE ticker = '{ticker.upper()}'" if ticker else ""
    with connect(cfg) as con:
        return con.execute(
            f"SELECT * FROM mentions {where} ORDER BY timestamp DESC LIMIT {int(limit)}"
        ).df()


def all_tickers(cfg: Config) -> list[str]:
    with connect(cfg) as con:
        rows = con.execute("SELECT DISTINCT ticker FROM mentions ORDER BY 1").fetchall()
    return [r[0] for r in rows]
