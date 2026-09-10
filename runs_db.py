"""Run-history persistence.

Each screen run writes a snapshot to runs.db (sqlite). Persistence
queries answer "which names have been in sleeve X for N runs running"
or "show me the resolution-score trajectory of SEIT over the last 30
runs" — single-shot rankings are noisy; the truth is in the curve.

Schema:
  runs(run_id PK, run_date, universe_size, n_investable, n_setup,
       n_fundamentals, n_activist_watch)
  scores(run_id FK, ticker, sleeve, resolution_score, expected_irr,
         composite_score, catalyst, phase)

CLI:
  python3 runs_db.py ingest results_20260624.csv
  python3 runs_db.py persistent --sleeve setup --runs 5
  python3 runs_db.py trajectory SEIT.L --field resolution_score
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


HERE = Path(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = HERE / "runs.db"

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    csv_filename TEXT,
    universe_size INTEGER,
    n_investable INTEGER,
    n_setup INTEGER,
    n_fundamentals INTEGER,
    n_activist_watch INTEGER
);
CREATE TABLE IF NOT EXISTS scores (
    run_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    sleeve TEXT,
    resolution_score REAL,
    expected_irr REAL,
    composite_score REAL,
    catalyst TEXT,
    phase TEXT,
    rns_pdmr_buys INTEGER,
    rns_tr1_activist_buys INTEGER,
    PRIMARY KEY (run_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_scores_ticker ON scores(ticker);
CREATE INDEX IF NOT EXISTS idx_scores_sleeve ON scores(sleeve);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)
    return conn


def _sleeve_of(row) -> str:
    if row.get("in_setup_sleeve"):
        return "setup"
    if row.get("in_fundamentals_sleeve"):
        return "fundamentals"
    if row.get("in_micro_sleeve"):
        return "micro"
    if float(row.get("resolution_score") or 0) >= 0.20:
        return "activist"
    return ""


def ingest(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    inv = df[(df["error"].isna()) & (df["investable"] == True)]
    conn = _conn()
    cur = conn.cursor()
    run_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO runs(run_date, csv_filename, universe_size, "
        "n_investable, n_setup, n_fundamentals, n_activist_watch) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_date, csv_path.name, len(df), len(inv),
         int((inv["in_setup_sleeve"] == True).sum()),
         int((inv["in_fundamentals_sleeve"] == True).sum()),
         int((inv["resolution_score"].fillna(0) > 0.20).sum())),
    )
    run_id = cur.lastrowid
    rows = []
    for _, r in inv.iterrows():
        rows.append((
            run_id, r["ticker"], _sleeve_of(r),
            float(r["resolution_score"] or 0) if pd.notna(r.get("resolution_score")) else None,
            float(r["expected_irr"] or 0) if pd.notna(r.get("expected_irr")) else None,
            float(r["composite_score"] or 0) if pd.notna(r.get("composite_score")) else None,
            r.get("catalyst") or "",
            r.get("phase") or "",
            int(r["rns_pdmr_buys"]) if pd.notna(r.get("rns_pdmr_buys")) else None,
            int(r["rns_tr1_activist_buys"]) if pd.notna(r.get("rns_tr1_activist_buys")) else None,
        ))
    cur.executemany(
        "INSERT OR REPLACE INTO scores(run_id, ticker, sleeve, "
        "resolution_score, expected_irr, composite_score, catalyst, "
        "phase, rns_pdmr_buys, rns_tr1_activist_buys) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return run_id


def persistent_in_sleeve(sleeve: str, n_runs: int) -> list[tuple]:
    """Tickers that appear in `sleeve` in each of the last `n_runs` runs."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT run_id FROM runs ORDER BY run_id DESC LIMIT ?",
                (n_runs,))
    run_ids = [r[0] for r in cur.fetchall()]
    if len(run_ids) < n_runs:
        conn.close()
        return []
    placeholders = ",".join("?" * len(run_ids))
    cur.execute(
        f"SELECT ticker, COUNT(*) as c, AVG(resolution_score), "
        f"  AVG(expected_irr) "
        f"FROM scores "
        f"WHERE run_id IN ({placeholders}) AND sleeve = ? "
        f"GROUP BY ticker HAVING c = ? "
        f"ORDER BY AVG(composite_score) DESC",
        (*run_ids, sleeve, n_runs),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def trajectory(ticker: str, field: str = "resolution_score") -> list[tuple]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT r.run_date, s.{field}, s.sleeve, s.catalyst, s.phase "
        "FROM scores s JOIN runs r ON s.run_id = r.run_id "
        "WHERE s.ticker = ? ORDER BY r.run_id ASC", (ticker,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    ing = sub.add_parser("ingest")
    ing.add_argument("csv")
    pers = sub.add_parser("persistent")
    pers.add_argument("--sleeve", default="setup")
    pers.add_argument("--runs", type=int, default=3)
    traj = sub.add_parser("trajectory")
    traj.add_argument("ticker")
    traj.add_argument("--field", default="resolution_score")
    args = p.parse_args()
    if args.cmd == "ingest":
        run_id = ingest(Path(args.csv))
        print(f"Ingested as run_id={run_id}", file=sys.stderr)
        return 0
    if args.cmd == "persistent":
        rows = persistent_in_sleeve(args.sleeve, args.runs)
        print(f"{len(rows)} ticker(s) in {args.sleeve} for {args.runs} runs:",
              file=sys.stderr)
        for t, c, r_res, r_irr in rows:
            print(f"  {t:<10}  mean_resolution={r_res or 0:.2f}  "
                  f"mean_IRR={(r_irr or 0)*100:.1f}%")
        return 0
    if args.cmd == "trajectory":
        rows = trajectory(args.ticker, args.field)
        print(f"{args.ticker}  trajectory of {args.field} ({len(rows)} pts):",
              file=sys.stderr)
        for date, val, sleeve, cat, phase in rows:
            v = f"{val:.3f}" if val is not None else "-"
            print(f"  {date}  {v:<8}  sleeve={sleeve}  cat={cat}  phase={phase}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
