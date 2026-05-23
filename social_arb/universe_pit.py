"""Point-in-time historical universe -- Russell 3000 / Russell 1000.

Spec note: backtesting on the *current* index constituency creates
survivorship bias because the universe over-represents winners. The
fix is point-in-time (PIT) constituents: at each historical date, use
the index members AT THAT DATE, not today's snapshot.

Sources for free PIT data:
  - **CRSP** (paywall)
  - **iShares (BlackRock) IWV holdings PDF/CSV history** -- free via
    https://www.ishares.com/us/products/239714/ — current snapshot is
    a CSV. Historical snapshots can be archived month-by-month.
  - **Russell Reconstitution** announcements (annual rebalance late June)
    via Russell's site.
  - **Stooq**'s historical Russell components -- partial.
  - **Wikipedia** "Russell 1000 Index" history — sparse.

Pragmatic approach we expose here:
  1. `fetch_iwv_holdings_current()` -- downloads BlackRock's free
     iShares Russell 3000 (IWV) CSV holdings dump. ~3000 names.
  2. `save_constituents_snapshot(date)` -- writes the current snapshot
     to data/universe_pit/YYYY-MM-DD.csv. Daily cron over a year
     accumulates a PIT history with no other dependencies.
  3. `pit_universe(as_of)` -- loads the latest snapshot at or before
     the given date for backtest use.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import Config

log = logging.getLogger(__name__)


IWV_CSV_URL = (
    "https://www.ishares.com/us/products/239714/"
    "ishares-russell-3000-etf/1467271812596.ajax"
    "?fileType=csv&fileName=IWV_holdings&dataType=fund"
)


def fetch_iwv_holdings_current(timeout: float = 30.0) -> pd.DataFrame:
    """Pull the current iShares Russell 3000 (IWV) constituent CSV.

    BlackRock serves a CSV with ~3000 rows, free, no auth.
    Columns vary slightly month-to-month but always include
    Ticker, Name, Sector, Asset Class, Weight (%), Market Currency,
    Exchange.
    """
    try:
        r = requests.get(IWV_CSV_URL, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; social-arb/0.1)",
            "Accept": "text/csv,*/*",
        })
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("iShares IWV CSV fetch failed: %s", exc)
        return pd.DataFrame()
    text = r.text
    # The CSV has a multi-line preamble before the actual table; find the
    # row that starts with "Ticker".
    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Ticker,") or line.startswith('"Ticker"'):
            start_idx = i
            break
    if start_idx is None:
        log.warning("iShares CSV: couldn't find Ticker header row")
        return pd.DataFrame()
    body = "\n".join(lines[start_idx:])
    try:
        df = pd.read_csv(io.StringIO(body))
    except Exception as exc:  # noqa: BLE001
        log.warning("iShares CSV parse failed: %s", exc)
        return pd.DataFrame()
    return df


def save_constituents_snapshot(cfg: Config) -> Path | None:
    """Save today's IWV constituents to data/universe_pit/YYYY-MM-DD.csv."""
    df = fetch_iwv_holdings_current()
    if df.empty:
        return None
    out_dir = cfg.data_dir / "universe_pit"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    path = out_dir / f"{today}.csv"
    df.to_csv(path, index=False)
    log.info("saved IWV snapshot (%d rows) -> %s", len(df), path)
    return path


def pit_universe(cfg: Config, as_of: datetime | None = None) -> pd.DataFrame:
    """Return the latest snapshot at or before `as_of` for PIT backtests."""
    out_dir = cfg.data_dir / "universe_pit"
    if not out_dir.exists():
        return pd.DataFrame()
    snapshots = sorted(out_dir.glob("*.csv"))
    if not snapshots:
        return pd.DataFrame()
    target = (as_of or datetime.now(timezone.utc)).date()
    chosen = None
    for p in snapshots:
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d <= target:
            chosen = p
        else:
            break
    if chosen is None:
        chosen = snapshots[0]
    return pd.read_csv(chosen)
