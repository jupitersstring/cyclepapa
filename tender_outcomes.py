"""Tender-outcome extractor — parse `result-of-tender` RNS bodies for
oversubscription signal.

Tender outcomes are heterogeneous (no single numeric format), so we
flag the qualitative signal first:

  oversubscribed = True  if any of:
    - "excess applications" present + "pro rata" applied
    - "scaled back"
    - "oversubscribed"
    - "applications totalled X" where X > offer size (when parseable)

Per-ticker rollup: count of oversubscribed tenders in last 24 months.
A trust with multiple oversubscribed tenders is under-served by its
current tender size — pressure for a larger return-of-capital.

Outputs: data/tender_outcomes.csv (one row per tender)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
TENDER_DIR = INV_DIR / "tender"
OUT_PATH = HERE / "data" / "tender_outcomes.csv"

USER_AGENT = "Mozilla/5.0 (compatible; CyclepapaTender/1.0)"

_OVERSUB_RE = re.compile(
    r"oversubscribed|excess applications|scaled back|"
    r"pro rata.{0,40}(application|entitlement)|"
    r"in excess of.{0,30}(tender size|tender amount)",
    re.IGNORECASE,
)
_TENDERED_RE = re.compile(
    r"([\d,]+)\s+(?:ordinary|shares?|securities?)\s+(?:were\s+)?(?:validly\s+)?tender",
    re.IGNORECASE,
)
_PURCHASED_RE = re.compile(
    r"(?:will\s+)?purchase\s+([\d,]+)\s+(?:ordinary\s+)?shares?",
    re.IGNORECASE,
)
_PCT_OF_ISC_RE = re.compile(
    r"(\d+\.\d+)%\s+of\s+the\s+(?:company's\s+)?issued\s+share\s+capital",
    re.IGNORECASE,
)
_TENDER_PRICE_RE = re.compile(
    r"tender\s+price\s+of\s+([\d.]+)\s*(pence|p\b|£)?\s+per\s+share",
    re.IGNORECASE,
)


def _cache_path(url: str) -> Path:
    TENDER_DIR.mkdir(parents=True, exist_ok=True)
    rns_id = re.sub(r"[^A-Za-z0-9]+", "_", url.rstrip("/").split("/")[-1])
    return TENDER_DIR / f"{rns_id}.json"


def fetch_tender(url: str, use_cache: bool = True) -> dict | None:
    cp = _cache_path(url)
    if use_cache and cp.exists():
        try:
            return json.loads(cp.read_text())
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    import html as _html
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    oversub = bool(_OVERSUB_RE.search(text))
    tendered = None
    m = _TENDERED_RE.search(text)
    if m:
        try:
            tendered = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    purchased = None
    m = _PURCHASED_RE.search(text)
    if m:
        try:
            purchased = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    pct_isc = None
    m = _PCT_OF_ISC_RE.search(text)
    if m:
        try:
            pct_isc = float(m.group(1))
        except ValueError:
            pass
    tender_price = None
    m = _TENDER_PRICE_RE.search(text)
    if m:
        try:
            tender_price = float(m.group(1))
        except ValueError:
            pass
    rec = {
        "oversubscribed": oversub,
        "n_tendered": tendered,
        "n_purchased": purchased,
        "pct_issued_share_capital": pct_isc,
        "tender_price": tender_price,
    }
    if use_cache:
        try:
            cp.write_text(json.dumps(rec))
        except Exception:
            pass
    return rec


def collect(lookback_days: int = 730) -> list[dict]:
    """Walk per-EPIC announcement files for tender results."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out = []
    for jf in INV_DIR.glob("*.json"):
        if jf.parent.name != "investegate":
            continue
        epic = jf.stem
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for a in data:
            if a.get("category") != "tender":
                continue
            t = (a.get("title") or "").lower()
            if "result" not in t and "outcome" not in t:
                continue
            d = a.get("date") or ""
            try:
                dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if dt < cutoff:
                continue
            det = fetch_tender(a.get("url") or "")
            if not det:
                continue
            out.append({
                "ticker": f"{epic}.L",
                "epic": epic,
                "date": d,
                "title": (a.get("title") or "")[:80],
                "oversubscribed": det.get("oversubscribed", False),
                "n_tendered": det.get("n_tendered"),
                "n_purchased": det.get("n_purchased"),
                "pct_isc": det.get("pct_issued_share_capital"),
                "tender_price": det.get("tender_price"),
            })
    return out


def rollup(rows: list[dict]) -> dict[str, dict]:
    """Per-ticker summary: counts of oversubscribed tenders, last
    tender date, total % of ISC tendered."""
    by_ticker: dict[str, dict] = defaultdict(
        lambda: {"n_tenders": 0, "n_oversubscribed": 0,
                 "last_date": "", "total_pct_isc": 0.0})
    for r in rows:
        x = by_ticker[r["ticker"]]
        x["n_tenders"] += 1
        if r["oversubscribed"]:
            x["n_oversubscribed"] += 1
        if r["date"] > x["last_date"]:
            x["last_date"] = r["date"]
        if r.get("pct_isc"):
            x["total_pct_isc"] += r["pct_isc"]
    return dict(by_ticker)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lookback-days", type=int, default=730)
    args = p.parse_args()
    rows = collect(lookback_days=args.lookback_days)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(OUT_PATH, "w", newline="") as f:
            cols = ["ticker", "epic", "date", "title", "oversubscribed",
                    "n_tendered", "n_purchased", "pct_isc", "tender_price"]
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"Wrote {len(rows)} rows to {OUT_PATH}", file=sys.stderr)
        roll = rollup(rows)
        chronic = [(t, x) for t, x in roll.items() if x["n_oversubscribed"] >= 2]
        chronic.sort(key=lambda kv: -kv[1]["n_oversubscribed"])
        if chronic:
            print("\nChronically oversubscribed (>=2 in 2y):", file=sys.stderr)
            for t, x in chronic:
                print(f"  {t:<10}  {x['n_oversubscribed']} of "
                      f"{x['n_tenders']} oversubscribed, total "
                      f"{x['total_pct_isc']:.1f}% ISC, last "
                      f"{x['last_date']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
