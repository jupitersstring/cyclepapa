#!/usr/bin/env python3
"""
inbox_db.py — a queryable SQLite index over data/inbox/.

The framework's data layer is thousands of flat JSON files under
data/inbox/, re-scanned with rglob by every consumer (corroborate,
emergence_master, postreorg_score, source_health, …). That is slow, makes
cross-source joins ad-hoc, and re-implements entity normalization in each
module. This builds a single, indexed store the consumers can query.

IMPORTANT — durability contract: the JSON files remain the SOURCE OF TRUTH
(git-tracked, the durable record). This SQLite file is a DERIVED, fully
rebuildable index — `build()` recreates it from the JSON at any time. It is
committed only so `make audit` sees no untracked data; delete it and
`make db` regenerates it byte-for-byte from the tracked JSON.

Schema:
  filings(one row per inbox JSON) — poller, tier, query_label, cik, ticker,
      name, name_norm, form, filed, source, emergence fields, raw JSON.
  A derived `entities` query rolls filings up by canonical entity
  (CIK, else normalized name) with per-source corroboration counts.

Usage:
    python -m src.inbox_db --build            # (re)build the index
    python -m src.inbox_db --stats            # summary counts
    python -m src.inbox_db --sql "SELECT ..." # ad-hoc query
    python -m src.inbox_db --entity AAPL      # all signals for an entity
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
DB = REPO / "data" / "inbox_index.db"

_STOP = {"inc", "corp", "corporation", "ltd", "limited", "plc", "llc",
         "lp", "holdings", "holding", "group", "co", "company", "the",
         "sa", "nv", "ag", "se", "spa", "as", "oyj", "ab", "of", "and"}


def norm_name(n) -> str:
    """Canonical entity key shared with emergence_master: drop parentheticals,
    fold S.A.==SA punctuation, tokenize, drop corporate-form stopwords."""
    if isinstance(n, (list, tuple)):
        n = " ".join(map(str, n))
    s = str(n or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = s.replace(".", "")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _STOP]
    return "".join(toks)


def ticker_stem(t) -> str:
    tk = re.sub(r"[^A-Za-z0-9]", "", (t or "").split(":")[-1]).upper()
    if len(tk) >= 4 and tk.endswith("Q"):        # Q = still-in-bankruptcy
        tk = tk[:-1]
    return tk


SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    path          TEXT PRIMARY KEY,
    poller        TEXT,
    tier          TEXT,
    query_label   TEXT,
    sublabel      TEXT,
    cik           TEXT,
    ticker        TEXT,
    ticker_stem   TEXT,
    name          TEXT,
    name_norm     TEXT,
    entity_key    TEXT,
    form          TEXT,
    filed         TEXT,
    source        TEXT,
    jurisdiction  TEXT,
    url           TEXT,
    accession     TEXT,
    emergence_tier TEXT,
    item_1_03     INTEGER,
    pre_emergence INTEGER
);
CREATE INDEX IF NOT EXISTS ix_cik       ON filings(cik);
CREATE INDEX IF NOT EXISTS ix_name_norm ON filings(name_norm);
CREATE INDEX IF NOT EXISTS ix_ticker    ON filings(ticker_stem);
CREATE INDEX IF NOT EXISTS ix_entity    ON filings(entity_key);
CREATE INDEX IF NOT EXISTS ix_label     ON filings(query_label);
CREATE INDEX IF NOT EXISTS ix_poller    ON filings(poller);
CREATE INDEX IF NOT EXISTS ix_filed     ON filings(filed);
"""


def _row(path: Path, rec: dict) -> tuple:
    poller = path.name.split("_")[0]
    lbl = rec.get("query_label") or ""
    cik = str(rec.get("cik") or "")
    try:
        cik = str(int(cik)) if cik else ""
    except ValueError:
        pass
    name = rec.get("name") or ""
    if isinstance(name, (list, tuple)):
        name = " ".join(map(str, name))
    nn = norm_name(name)
    tk = rec.get("ticker") or ""
    tks = ticker_stem(tk)
    entity_key = f"CIK:{cik}" if cik else (f"NAME:{nn}" if nn else f"PATH:{path.name}")
    return (
        str(path.relative_to(REPO)), poller, rec.get("tier") or "",
        lbl, lbl.split(".")[-1], cik, tk, tks, str(name)[:200], nn,
        entity_key, str(rec.get("form") or rec.get("form_code") or ""),
        (rec.get("filed") or "")[:10], rec.get("source") or "",
        rec.get("jurisdiction") or "", rec.get("url") or "",
        rec.get("accession") or "",
        rec.get("emergence_tier") or "",
        1 if rec.get("item_1_03") else 0,
        1 if rec.get("pre_emergence") else 0,
    )


def build(verbose: bool = True) -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()                       # full rebuild = deterministic
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    cols = ("path,poller,tier,query_label,sublabel,cik,ticker,ticker_stem,"
            "name,name_norm,entity_key,form,filed,source,jurisdiction,url,"
            "accession,emergence_tier,item_1_03,pre_emergence")
    ph = ",".join(["?"] * len(cols.split(",")))
    n = bad = 0
    batch = []
    for jf in INBOX.rglob("*.json"):
        try:
            rec = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            bad += 1
            continue
        if not isinstance(rec, dict):
            bad += 1
            continue
        batch.append(_row(jf, rec))
        n += 1
        if len(batch) >= 1000:
            con.executemany(f"INSERT OR REPLACE INTO filings ({cols}) "
                            f"VALUES ({ph})", batch)
            batch = []
    if batch:
        con.executemany(f"INSERT OR REPLACE INTO filings ({cols}) "
                        f"VALUES ({ph})", batch)
    con.commit()
    con.close()
    if verbose:
        print(f"Indexed {n} filings ({bad} unparseable) into {DB}")
    return n


def connect() -> sqlite3.Connection:
    if not DB.exists():
        build(verbose=False)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


# --- convenience queries the other modules can share ----------------------

def entities_multi_source(min_sources: int = 2) -> list[sqlite3.Row]:
    """Entities independently flagged by >= min_sources distinct pollers."""
    con = connect()
    rows = con.execute(
        "SELECT entity_key, MAX(name) name, MAX(ticker) ticker, "
        "COUNT(DISTINCT poller) n_pollers, COUNT(DISTINCT source) n_sources, "
        "COUNT(*) n_filings, MIN(filed) first_filed, MAX(filed) last_filed, "
        "GROUP_CONCAT(DISTINCT query_label) labels "
        "FROM filings WHERE entity_key NOT LIKE 'PATH:%' "
        "GROUP BY entity_key HAVING n_pollers >= ? "
        "ORDER BY n_pollers DESC, n_filings DESC", (min_sources,)).fetchall()
    con.close()
    return rows


def entity_signals(token: str) -> list[sqlite3.Row]:
    """All filings for an entity by ticker stem, CIK, or name substring."""
    con = connect()
    t = token.upper()
    rows = con.execute(
        "SELECT poller, query_label, form, filed, name, ticker, source, url "
        "FROM filings WHERE ticker_stem=? OR cik=? OR "
        "UPPER(name) LIKE ? ORDER BY filed DESC",
        (t, token, f"%{t}%")).fetchall()
    con.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--sql")
    ap.add_argument("--entity")
    ap.add_argument("--multi-source", type=int, metavar="N",
                    help="show entities flagged by >= N pollers")
    args = ap.parse_args()

    if args.build or not (args.stats or args.sql or args.entity
                          or args.multi_source):
        build()

    if args.stats:
        con = connect()
        total = con.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
        ents = con.execute("SELECT COUNT(DISTINCT entity_key) FROM "
                           "filings").fetchone()[0]
        print(f"filings: {total}  ·  distinct entities: {ents}")
        print("\nby poller:")
        for r in con.execute("SELECT poller, COUNT(*) c FROM filings "
                             "GROUP BY poller ORDER BY c DESC LIMIT 25"):
            print(f"  {r[0]:16} {r[1]}")
        con.close()

    if args.multi_source:
        for r in entities_multi_source(args.multi_source)[:40]:
            print(f"  {r['n_pollers']}src {(r['ticker'] or '—'):8} "
                  f"{(r['name'] or '')[:34]:34} {r['labels'][:50]}")

    if args.entity:
        for r in entity_signals(args.entity):
            print(f"  {r['filed']}  {r['poller']:12} {r['query_label']:28} "
                  f"{r['name'][:30]}")

    if args.sql:
        con = connect()
        for r in con.execute(args.sql).fetchall():
            print(tuple(r))
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
