"""Durability layer — DB ⇄ git-safe snapshot.

The SQLite DB itself is a build artifact that should be cheaply rebuildable
from primary sources, BUT the EDGAR Form-4 XML fetches, Yahoo price snapshots,
and discovery sweeps are rate-limited and time-expensive. Losing the DB =
hours of re-fetching.

This module dumps every table to a deterministic CSV under data/snapshot/.
Those CSVs ARE committed, are human-diffable, and survive any sandbox reset.
`restore` rebuilds the DB from them in seconds — no network required.

Run order:
  make refresh   ends with `python3 pipeline/snapshot.py dump`
  fresh sandbox  `python3 pipeline/snapshot.py restore` rebuilds everything
"""
import csv, os, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
SNAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "snapshot")

# Tables whose data is EXPENSIVE to refetch (EDGAR + price + parsed Form 4s).
# We always dump these. Other (derived) tables are dumped too for completeness
# but are also rebuildable from these + the CSV inputs + source code.
EXPENSIVE_TABLES = {"edgar_filings", "form4_transactions", "prices", "discovery",
                    "discovery_13d", "discovery_13d_subjects", "insider_clusters",
                    "ticker_meta", "ticker_valuation", "catalysts_8k", "holder_13d"}
ALWAYS_SKIP = set()  # views handled separately

def list_tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        if r[0] not in ALWAYS_SKIP and not r[0].startswith("sqlite_")]

def dump():
    os.makedirs(SNAP, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    summary = []
    for t in list_tables(conn):
        rows = list(conn.execute(f"SELECT * FROM '{t}'"))
        path = os.path.join(SNAP, f"{t}.csv")
        if not rows:
            # write empty file with header if schema can be discovered
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info('{t}')")]
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(cols)
            summary.append((t, 0, "empty"))
            continue
        cols = rows[0].keys()
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([r[c] if r[c] is not None else "" for c in cols])
        flag = "EXPENSIVE" if t in EXPENSIVE_TABLES else ""
        summary.append((t, len(rows), flag))
    # write a manifest with row counts so diff reveals drift
    with open(os.path.join(SNAP, "_MANIFEST.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["table", "rows", "flag"])
        for t, n, fl in summary: w.writerow([t, n, fl])
    print(f"dumped {len(summary)} tables to {SNAP}/")
    for t, n, fl in summary:
        marker = "  ★" if fl else "   "
        print(f"  {marker} {t:<28} {n:>6}")
    return summary

def restore():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    if not os.path.isdir(SNAP):
        print(f"FATAL: no snapshot directory at {SNAP}")
        sys.exit(1)
    # rebuild schema first by running db.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import db
    conn = sqlite3.connect(DB)
    db.init(conn); conn.commit()
    # additionally schemas defined by other pipeline modules
    import_modules = ["backtest", "populate_metadata", "cluster_detector",
                      "expected_return", "archetype_status", "fund_monitor",
                      "ingest_fund_xlsx", "ingest_prices", "ingest_edgar",
                      "discover", "styles_view", "conviction", "entry_intact"]
    for m in import_modules:
        try: __import__(m)
        except Exception: pass
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS discovery (
      ticker TEXT PRIMARY KEY, issuer TEXT, n_filings INTEGER, n_buyers INTEGER,
      total_usd_m REAL, top_buyer TEXT, top_role TEXT, avg_px REAL,
      last_close REAL, off_52w_high REAL, off_52w_low REAL,
      window TEXT, asof TEXT);
    CREATE TABLE IF NOT EXISTS discovery_13d (
      cik TEXT, company TEXT, filed TEXT, path TEXT, PRIMARY KEY (cik, filed));
    CREATE TABLE IF NOT EXISTS discovery_13d_subjects (
      accession TEXT PRIMARY KEY, subject TEXT, subject_cik TEXT, ticker TEXT,
      filer_hint TEXT, filed TEXT, last_close REAL, off_52w_high REAL, asof TEXT);
    CREATE TABLE IF NOT EXISTS insider_clusters (
      ticker TEXT PRIMARY KEY, window_start TEXT, window_end TEXT,
      n_insiders INTEGER, total_usd_m REAL, avg_price REAL,
      top_buyer TEXT, top_buyer_usd_m REAL, trigger TEXT, asof TEXT);
    CREATE TABLE IF NOT EXISTS base_rates (
      factor TEXT PRIMARY KEY, hit_rate REAL, avg_excess_12m REAL, sample_n INTEGER);
    CREATE TABLE IF NOT EXISTS fund_meta (
      fund TEXT PRIMARY KEY, fund_group TEXT, source_block TEXT, total_rows INTEGER);
    CREATE TABLE IF NOT EXISTS fund_positions (
      id INTEGER PRIMARY KEY, fund TEXT, ticker TEXT, company TEXT, section INTEGER,
      pct_value REAL, pct_kind TEXT, dollar_m REAL, change_text TEXT,
      event_date TEXT, raw_text TEXT, asof TEXT);
    CREATE TABLE IF NOT EXISTS fund_style (
      fund TEXT PRIMARY KEY, sub_group TEXT, macro_style TEXT,
      total_rows INTEGER, conviction_n INTEGER, threshold_n INTEGER,
      new_n INTEGER, adds_n INTEGER);
    CREATE TABLE IF NOT EXISTS style_summary (
      macro_style TEXT PRIMARY KEY, n_funds INTEGER, total_rows INTEGER,
      n_conviction INTEGER, n_threshold INTEGER, n_new INTEGER, n_adds INTEGER,
      top_funds TEXT, top_consensus TEXT);
    CREATE TABLE IF NOT EXISTS style_consensus (
      macro_style TEXT, ticker TEXT, n_funds INTEGER, dollar_m REAL,
      sections_seen TEXT, in_tier1 INTEGER, has_cluster INTEGER, entry_bucket TEXT,
      PRIMARY KEY (macro_style, ticker));
    CREATE TABLE IF NOT EXISTS fund_conviction (
      fund TEXT, ticker TEXT, signals TEXT, raw_score REAL, style_weight REAL,
      score REAL, macro_style TEXT, pct_book REAL, pct_company REAL, dollar_m REAL,
      PRIMARY KEY (fund, ticker));
    CREATE TABLE IF NOT EXISTS ticker_conviction (
      ticker TEXT PRIMARY KEY, score REAL, raw_score REAL, n_funds INTEGER,
      n_hyper INTEGER, n_top_pick INTEGER, n_activist_13d INTEGER, n_passive_13g INTEGER,
      n_new_init INTEGER, n_material_add INTEGER, n_public_letter INTEGER,
      n_follow_on INTEGER, n_persist INTEGER, has_insider_cobuy INTEGER,
      sum_dollar_m REAL, max_pct_book REAL, max_pct_company REAL,
      fund_signals_summary TEXT, styles_summary TEXT);
    CREATE TABLE IF NOT EXISTS ticker_style_conviction (
      ticker TEXT, macro_style TEXT, score REAL, n_funds INTEGER,
      n_hyper INTEGER, dollar_m REAL, PRIMARY KEY (ticker, macro_style));
    CREATE TABLE IF NOT EXISTS ticker_entry_intact (
      ticker TEXT PRIMARY KEY, current_px REAL, anchor_px REAL, anchor_source TEXT,
      vs_entry_pct REAL, bucket TEXT, conviction_score REAL, n_funds INTEGER,
      n_hyper INTEGER, has_insider_cobuy INTEGER, sum_dollar_m REAL, anchors_seen TEXT);
    CREATE TABLE IF NOT EXISTS expected_return (
      ticker TEXT PRIMARY KEY, tags_n INTEGER, weighted_excess_12m REAL,
      best_tag TEXT, best_tag_excess REAL, worst_tag TEXT, worst_tag_excess REAL,
      cluster_live INTEGER, asof TEXT);
    CREATE TABLE IF NOT EXISTS archetype_member_status (
      archetype TEXT, ticker TEXT, status TEXT, er REAL, factor_tags TEXT,
      thesis TEXT, PRIMARY KEY (archetype, ticker));
    CREATE TABLE IF NOT EXISTS backtest_events (
      id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, bucket TEXT NOT NULL,
      event_date TEXT NOT NULL, description TEXT NOT NULL, source_note TEXT);
    CREATE TABLE IF NOT EXISTS backtest_results (
      event_id INTEGER PRIMARY KEY, entry_date TEXT, entry_px REAL,
      ret_6m REAL, ret_12m REAL, ret_18m REAL,
      spy_6m REAL, spy_12m REAL, spy_18m REAL,
      excess_6m REAL, excess_12m REAL, excess_18m REAL);
    CREATE TABLE IF NOT EXISTS archetype_status (
      archetype TEXT PRIMARY KEY, mapped_factor TEXT, base_rate_excess REAL,
      members_total INTEGER, members_live_t1 INTEGER, members_live_t2 INTEGER,
      members_live_t3 INTEGER, members_demoted INTEGER, members_graduated INTEGER,
      members_dead INTEGER, members_untracked INTEGER, members_excluded INTEGER,
      best_member TEXT, best_member_er REAL, verdict TEXT);
    """)

    # Load each CSV into its table
    loaded = 0
    # NOT-NULL fallback map: tables where a NOT NULL TEXT column should
    # accept empty-string when CSV value is blank (preserves the row).
    EMPTY_OK = {("candidates", "source_url"): "",
                ("signals", "source_url"): "",
                ("form4_transactions", "source_url"): "",
                ("edgar_filings", "url"): ""}
    for fname in sorted(os.listdir(SNAP)):
        if not fname.endswith(".csv") or fname.startswith("_"):
            continue
        t = fname[:-4]
        path = os.path.join(SNAP, fname)
        with open(path) as f:
            r = csv.reader(f)
            cols = next(r, None)
            if not cols:
                continue
            rows = []
            for row in r:
                rows.append([
                    EMPTY_OK[(t, cols[i])] if (v == "" and (t, cols[i]) in EMPTY_OK)
                    else (v if v != "" else None)
                    for i, v in enumerate(row)
                ])
            if not rows:
                continue
            # check table exists
            tinfo = conn.execute(f"PRAGMA table_info('{t}')").fetchall()
            if not tinfo:
                print(f"  skip {t}: table not in schema")
                continue
            try:
                conn.execute(f"DELETE FROM '{t}'")
                ph = ",".join("?" * len(cols))
                conn.executemany(f"INSERT INTO '{t}' ({','.join(cols)}) VALUES ({ph})", rows)
                loaded += 1
                print(f"  restored {t:<28} {len(rows):>6} rows")
            except sqlite3.Error as e:
                print(f"  FAIL {t}: {e}")
    conn.commit()
    print(f"\nrestore complete: {loaded} tables hydrated into {DB}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        dump()
    elif cmd == "restore":
        restore()
    else:
        print("usage: snapshot.py [dump|restore]")
        sys.exit(1)
