"""Event-sourced SQLite state store for the pipeline.

Replaces the monolithic cancel_10b5_1.json read-modify-rewrite pattern
(O(n^2) I/O, corruptible mid-write) with three tables:

  filings   -- which filings we have scanned per ticker (immutable log).
               Also powers INCREMENTAL fetch: the max accession date per
               ticker tells the refresher where to resume.
  events    -- raw extracted 10b5-1 / Form 144 events (immutable log,
               keyed by extraction version so re-extraction under a new
               regex version coexists with the old rows).
  scores    -- derived per-ticker scores (cheap, regenerable, versioned).

Design rules:
  - events are NEVER mutated; a new extractor version INSERTs new rows
    with its own extract_version.
  - scores are DELETE+INSERT per (ticker, score_version) -- regenerable
    from events at any time.
  - WAL mode so a reader (composite) and writer (refresher) coexist.

Migration: `python3 state.py migrate` ports cancel_10b5_1.json into the
DB. The JSON remains the canonical artifact in git until the DB has
burned in; both are written by daily_refresh.py during the transition.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
DB_PATH = ROOT / "pipeline.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    ticker        TEXT NOT NULL,
    accession     TEXT NOT NULL,
    form          TEXT,
    filing_date   TEXT,
    scanned_at    TEXT,
    PRIMARY KEY (ticker, accession)
);
CREATE INDEX IF NOT EXISTS idx_filings_ticker_date
    ON filings (ticker, filing_date DESC);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT '10b5_1',  -- or 'form144'
    accession       TEXT,
    filing_date     TEXT,
    action          TEXT,
    plan_type       TEXT,
    neo             TEXT,
    role            TEXT,
    shares          INTEGER,
    value_usd       REAL,
    is_retrospective INTEGER DEFAULT 0,
    is_corporate    INTEGER DEFAULT 0,
    modification_pair INTEGER DEFAULT 0,
    snippet         TEXT,
    extract_version TEXT NOT NULL,
    extracted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ticker
    ON events (ticker, extract_version);

CREATE TABLE IF NOT EXISTS scores (
    ticker        TEXT NOT NULL,
    score_version TEXT NOT NULL,
    score         REAL,
    counts_json   TEXT,
    reasons_json  TEXT,
    data_available INTEGER,
    scored_at     TEXT,
    PRIMARY KEY (ticker, score_version)
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Incremental-fetch support
# ---------------------------------------------------------------------------

def last_scanned_date(conn: sqlite3.Connection, ticker: str) -> str | None:
    """Most recent filing_date we have processed for this ticker.
    The refresher only fetches filings strictly newer than this."""
    row = conn.execute(
        "SELECT MAX(filing_date) FROM filings WHERE ticker = ?",
        (ticker,)).fetchone()
    return row[0] if row and row[0] else None


def known_accessions(conn: sqlite3.Connection, ticker: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT accession FROM filings WHERE ticker = ?", (ticker,))}


def record_filing(conn: sqlite3.Connection, ticker: str, accession: str,
                  form: str | None, filing_date: str | None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO filings "
        "(ticker, accession, form, filing_date, scanned_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, accession, form, filing_date, now_iso()))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def insert_events(conn: sqlite3.Connection, ticker: str,
                  events: list[dict], extract_version: str,
                  source: str = "10b5_1") -> int:
    n = 0
    for e in events:
        conn.execute(
            "INSERT INTO events (ticker, source, accession, filing_date, "
            "action, plan_type, neo, role, shares, value_usd, "
            "is_retrospective, is_corporate, modification_pair, snippet, "
            "extract_version, extracted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker, source, e.get("accession"), e.get("filing_date"),
             e.get("action"), e.get("plan_type"), e.get("neo"),
             e.get("role"), e.get("shares"), e.get("value_usd"),
             1 if e.get("is_retrospective") else 0,
             1 if e.get("is_corporate") else 0,
             1 if e.get("modification_pair") else 0,
             (e.get("snippet") or "")[:600],
             extract_version, now_iso()))
        n += 1
    return n


def events_for(conn: sqlite3.Connection, ticker: str,
               extract_version: str, source: str = "10b5_1") -> list[dict]:
    cols = ["id", "ticker", "source", "accession", "filing_date", "action",
            "plan_type", "neo", "role", "shares", "value_usd",
            "is_retrospective", "is_corporate", "modification_pair",
            "snippet"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM events "
        "WHERE ticker = ? AND extract_version = ? AND source = ?",
        (ticker, extract_version, source)).fetchall()
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

def upsert_score(conn: sqlite3.Connection, ticker: str, score_version: str,
                 score: float, counts: dict, reasons: list,
                 data_available: bool) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO scores "
        "(ticker, score_version, score, counts_json, reasons_json, "
        "data_available, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticker, score_version, score, json.dumps(counts),
         json.dumps(reasons), 1 if data_available else 0, now_iso()))


def all_scores(conn: sqlite3.Connection, score_version: str) -> dict:
    out = {}
    for tk, sc, cj, rj, da in conn.execute(
            "SELECT ticker, score, counts_json, reasons_json, "
            "data_available FROM scores WHERE score_version = ?",
            (score_version,)):
        out[tk] = {
            "score": sc,
            "counts": json.loads(cj) if cj else {},
            "reasons": json.loads(rj) if rj else [],
            "data_available": bool(da),
        }
    return out


# ---------------------------------------------------------------------------
# Migration from the JSON artifact
# ---------------------------------------------------------------------------

def migrate_from_json(json_path: Path = ROOT / "cancel_10b5_1.json",
                      extract_version: str = "v3-dedup-foreign-aware",
                      score_version: str = "v3.3") -> None:
    data = json.loads(json_path.read_text())
    conn = connect()
    n_f = n_e = n_s = 0
    with conn:
        for tk, v in data.items():
            for q in v.get("quarters_scanned") or []:
                record_filing(conn, tk, q.get("accession") or "",
                              None, q.get("filing_date"))
                n_f += 1
            evs = v.get("events") or []
            # Idempotency: skip if this ticker already has rows for
            # this extract_version
            existing = conn.execute(
                "SELECT COUNT(*) FROM events WHERE ticker = ? AND "
                "extract_version = ?", (tk, extract_version)).fetchone()[0]
            if not existing and evs:
                n_e += insert_events(conn, tk, evs, extract_version)
            upsert_score(conn, tk, score_version,
                         v.get("score") or 0.0,
                         v.get("counts") or {},
                         v.get("reasons") or [],
                         bool(v.get("data_available")))
            n_s += 1
    conn.close()
    print(f"Migrated: {n_f} filings, {n_e} events, {n_s} scores -> {DB_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        migrate_from_json()
    else:
        conn = connect()
        for table in ("filings", "events", "scores"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {n} rows")
        conn.close()
