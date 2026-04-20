"""Fetch current index constituents from official ETF/index provider files.

Each index is pulled from its tracking ETF's public holdings file. State
Street (SPDR) ships XLSX, BlackRock (iShares) ships CSV. We normalise to
data/constituents/<INDEX>.csv with columns: ticker, name, weight, sector.

Caveats:
- These are *current* constituents only — vendors don't publish history.
- Vendor URLs change occasionally; failures are logged but don't abort.
- iShares' CSVs have ~9 lines of metadata before the real table.

Run:
    pip install requests openpyxl
    python3 fetch_index_constituents.py
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests

OUT_DIR = Path(__file__).parent / "data" / "constituents"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)


def fetch(url: str) -> bytes:
    resp = requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "*/*"},
        timeout=60,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_ssga_xlsx(blob: bytes) -> list[dict]:
    """SSGA / SPDR holdings XLSX. Header row sits a few rows in; we scan
    down for a row containing 'Ticker' to anchor the table."""
    from openpyxl import load_workbook  # lazy import

    wb = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    for i, row in enumerate(rows):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if any(cell.lower() == "ticker" for cell in cells):
            header_idx = i
            break
    if header_idx is None:
        return []
    header = [str(c).strip() if c is not None else "" for c in rows[header_idx]]
    out = []
    for r in rows[header_idx + 1:]:
        d = {h: r[i] for i, h in enumerate(header) if h}
        ticker = (d.get("Ticker") or "").strip() if isinstance(d.get("Ticker"), str) else ""
        if not ticker or ticker == "-":
            continue
        out.append(
            {
                "ticker": ticker,
                "name": str(d.get("Name", "")).strip(),
                "weight": str(d.get("Weight", "")).strip(),
                "sector": str(d.get("Sector", "")).strip(),
            }
        )
    return out


def parse_ishares_csv(blob: bytes) -> list[dict]:
    """iShares CSV. Skip leading metadata until we find the 'Ticker,Name,...'
    header row."""
    text = blob.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.lower().startswith("ticker,"):
            header_idx = i
            break
    if header_idx is None:
        return []
    reader = csv.DictReader(lines[header_idx:])
    out = []
    for row in reader:
        ticker = (row.get("Ticker") or "").strip()
        if not ticker or ticker == "-":
            continue
        out.append(
            {
                "ticker": ticker,
                "name": (row.get("Name") or "").strip(),
                "weight": (row.get("Weight (%)") or "").strip(),
                "sector": (row.get("Sector") or "").strip(),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

SSGA = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{}.xlsx"

ISHARES = "https://www.ishares.com/us/products/{pid}/.ajax?fileType=csv&fileName={t}_holdings&dataType=fund"

# Each entry: (index name, url, parser, source description)
SOURCES = [
    # SPDR XLSX
    ("SP500",         SSGA.format("spy"), parse_ssga_xlsx, "SPDR SPY"),
    ("Dow_Jones",     SSGA.format("dia"), parse_ssga_xlsx, "SPDR DIA"),
    ("SP_MidCap_400", SSGA.format("mdy"), parse_ssga_xlsx, "SPDR MDY"),
    ("SP_SmallCap_600", SSGA.format("ijr"), parse_ssga_xlsx, "SPDR? "),
    # iShares CSV (US listings — broad market / Russell / sectors)
    ("Russell_1000",  ISHARES.format(pid=239707, t="IWB"), parse_ishares_csv, "iShares IWB"),
    ("Russell_2000",  ISHARES.format(pid=239710, t="IWM"), parse_ishares_csv, "iShares IWM"),
    ("Russell_3000",  ISHARES.format(pid=239714, t="IWV"), parse_ishares_csv, "iShares IWV"),
    ("NASDAQ_100",    ISHARES.format(pid=239779, t="IUSG"), parse_ishares_csv, "iShares IUSG"),
    # iShares country / region MSCI funds — these aren't 1:1 with the named
    # local indices but they cover the same large/mid-cap universe.
    ("MSCI_United_Kingdom", ISHARES.format(pid=239690, t="EWU"), parse_ishares_csv, "iShares EWU"),
    ("MSCI_Germany",  ISHARES.format(pid=239676, t="EWG"), parse_ishares_csv, "iShares EWG"),
    ("MSCI_France",   ISHARES.format(pid=239674, t="EWQ"), parse_ishares_csv, "iShares EWQ"),
    ("MSCI_Italy",    ISHARES.format(pid=239680, t="EWI"), parse_ishares_csv, "iShares EWI"),
    ("MSCI_Spain",    ISHARES.format(pid=239693, t="EWP"), parse_ishares_csv, "iShares EWP"),
    ("MSCI_Netherlands", ISHARES.format(pid=239686, t="EWN"), parse_ishares_csv, "iShares EWN"),
    ("MSCI_Belgium",  ISHARES.format(pid=239669, t="EWK"), parse_ishares_csv, "iShares EWK"),
    ("MSCI_Switzerland", ISHARES.format(pid=239695, t="EWL"), parse_ishares_csv, "iShares EWL"),
    ("MSCI_Sweden",   ISHARES.format(pid=239692, t="EWD"), parse_ishares_csv, "iShares EWD"),
    ("MSCI_Austria",  ISHARES.format(pid=239667, t="EWO"), parse_ishares_csv, "iShares EWO"),
    ("MSCI_Japan",    ISHARES.format(pid=239665, t="EWJ"), parse_ishares_csv, "iShares EWJ"),
    ("MSCI_Hong_Kong",ISHARES.format(pid=239678, t="EWH"), parse_ishares_csv, "iShares EWH"),
    ("MSCI_Australia",ISHARES.format(pid=239668, t="EWA"), parse_ishares_csv, "iShares EWA"),
    ("MSCI_Canada",   ISHARES.format(pid=239670, t="EWC"), parse_ishares_csv, "iShares EWC"),
    ("MSCI_Mexico",   ISHARES.format(pid=239685, t="EWW"), parse_ishares_csv, "iShares EWW"),
    ("MSCI_Brazil",   ISHARES.format(pid=239612, t="EWZ"), parse_ishares_csv, "iShares EWZ"),
    ("MSCI_South_Korea", ISHARES.format(pid=239681, t="EWY"), parse_ishares_csv, "iShares EWY"),
    ("MSCI_Taiwan",   ISHARES.format(pid=239696, t="EWT"), parse_ishares_csv, "iShares EWT"),
    ("MSCI_Singapore",ISHARES.format(pid=239691, t="EWS"), parse_ishares_csv, "iShares EWS"),
    ("MSCI_Emerging_Markets", ISHARES.format(pid=239637, t="EEM"), parse_ishares_csv, "iShares EEM"),
    ("MSCI_EAFE",     ISHARES.format(pid=239623, t="EFA"), parse_ishares_csv, "iShares EFA"),
    ("MSCI_Europe",   ISHARES.format(pid=239625, t="IEUR"), parse_ishares_csv, "iShares IEUR"),
    ("MSCI_Pacific",  ISHARES.format(pid=239640, t="IPAC"), parse_ishares_csv, "iShares IPAC"),
]


def write(name: str, rows: list[dict]) -> None:
    out = OUT_DIR / f"{name}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "weight", "sector"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {out.name}: {len(rows)} rows", flush=True)


def main() -> None:
    for name, url, parser, label in SOURCES:
        print(f"[{name}] <- {label}", flush=True)
        try:
            blob = fetch(url)
            rows = parser(blob)
            write(name, rows)
        except Exception as e:
            print(f"  FAILED ({type(e).__name__}): {e}", file=sys.stderr)
            write(name, [])


if __name__ == "__main__":
    main()
