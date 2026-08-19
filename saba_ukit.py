"""Saba UKIT ETF holdings scraper.

Saba Capital's UK Investment Trusts ETF (LSE: UKIT) publicly publishes
its holdings on the Hanetf factsheet. Every name there is an active
target of the largest organised activist in the UK CEF space — the
purest forward-looking signal we can pull for "which trust is about
to have a fight."

The full holdings list is hosted by Hanetf as a CSV/PDF. Until we have
a stable scrape against that, we ship the eight named holdings from
the QuotedData / Hanetf snapshot (early March 2026) as a hardcoded
seed, and provide a refresh function that overlays anything the live
fetch can recover.

Public API:
    saba_ukit_tickers()        -> set[str]   (UK .L tickers in the ETF)
    refresh()                  -> writes data/saba_ukit_holdings.csv
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "saba_ukit_holdings.csv"


# Seed list — hardcoded from the public QuotedData snapshot of UKIT
# holdings published in early March 2026. These are the eight named
# investment trusts plus the three non-trust equity stakes Saba
# disclosed alongside.
#
# Source:
#  https://quoteddata.com/2026/03/saba-takes-96m-stake-in-allianz-technology-
#  and-makes-it-one-of-eight-holdings-in-its-activist-etf/
_SEED_HOLDINGS = [
    # ticker, name, kind
    ("ATT.L",  "Allianz Technology Trust",          "trust"),
    ("UTG.L",  "Unite Group REIT",                  "trust"),
    ("HSL.L",  "Henderson Smaller Companies Trust", "trust"),
    ("BNKR.L", "Bankers Investment Trust",          "trust"),
    ("DIVI.L", "Diverse Income Trust",              "trust"),
    ("ESCT.L", "European Smaller Companies Trust",  "trust"),
    ("USA.L",  "Baillie Gifford US Growth Trust",   "trust"),
    ("HRI.L",  "Herald Investment Trust",           "trust"),
    # Non-trust equity stakes (still names Saba is engaging with)
    ("IPO.L",  "IP Group PLC",                      "equity"),
    ("SYNC.L", "Syncona",                           "equity"),
    ("HVPE.L", "HarbourVest Global Private Equity", "equity"),
]


def _ensure_dir():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _write_csv(holdings: list[tuple[str, str, str]]):
    _ensure_dir()
    with open(DATA_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["snapshot_date", "ticker", "name", "kind"])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for tk, name, kind in holdings:
            w.writerow([today, tk, name, kind])


def _read_csv() -> list[tuple[str, str, str]]:
    if not DATA_PATH.exists():
        return []
    out = []
    with open(DATA_PATH) as f:
        for row in csv.DictReader(f):
            out.append((row["ticker"], row["name"], row["kind"]))
    return out


def refresh(force_seed: bool = False) -> None:
    """Refresh the local cache. Without `force_seed` we re-write the
    file with whatever seed we currently have. A future enhancement
    is to parse Hanetf's live CSV; until then the seed is the truth."""
    _write_csv(_SEED_HOLDINGS)


def saba_ukit_tickers() -> set[str]:
    """Return the set of LSE .L tickers held by UKIT (trusts only)."""
    holdings = _read_csv()
    if not holdings:
        refresh()
        holdings = _read_csv()
    return {tk for tk, _, kind in holdings if kind == "trust"}


def saba_ukit_all() -> set[str]:
    """All UKIT holdings including non-trust equity stakes (Saba is
    engaging with these via direct ownership, not via CEF activism,
    but they're still in the activist pipeline)."""
    holdings = _read_csv()
    if not holdings:
        refresh()
        holdings = _read_csv()
    return {tk for tk, _, _ in holdings}


if __name__ == "__main__":
    refresh()
    print(f"Wrote {DATA_PATH} with {len(_SEED_HOLDINGS)} entries")
    print("Trust holdings:", sorted(saba_ukit_tickers()))
    print("All holdings:", sorted(saba_ukit_all()))
