"""Buyback run-rate + NAV-accretion analysis.

A closed-end fund buying back its own shares below NAV mechanically
accretes NAV-per-share for continuing holders — a real, catalyst-
independent return we otherwise score only as a raw "buyback count".

  NAV accretion / yr ≈ buyback_yield × discount / (1 − buyback_yield)

The hard part is estimating the yield HONESTLY. A single "transaction
in own shares" filing must NOT be annualised — it may be a one-off
(a block unwind, an index-rebalance mop-up, a single opportunistic
day). We only annualise a programme that is demonstrably SUSTAINED:

  * at least MIN_FILINGS distinct filings, AND
  * spanning at least MIN_SPAN_DAYS, AND
  * appearing in at least MIN_DISTINCT_MONTHS calendar months.

Otherwise the name is flagged one_off=True: we report the raw fraction
retired over the observed window but do NOT annualise or feed accretion
into scoring. Even for sustained programmes the annualised yield is
capped (MAX_ANNUAL_YIELD) — a burst inside the window shouldn't
extrapolate to an implausible retirement pace.

Per-filing bodies are parsed for shares-purchased and issued-share-
capital and cached forever (RNS is immutable). Output:
data/buyback_runrate.csv (one row per ticker).
"""
from __future__ import annotations

import argparse
import csv
import html as _html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
BUYBACK_DIR = INV_DIR / "buyback"
OUT_PATH = HERE / "data" / "buyback_runrate.csv"
USER_AGENT = "Mozilla/5.0 (compatible; CyclepapaBuyback/1.0)"

# Sustained-programme thresholds (the anti-one-off guard)
LOOKBACK_DAYS = 365
MIN_FILINGS = 4
MIN_SPAN_DAYS = 60
MIN_DISTINCT_MONTHS = 3
MAX_ANNUAL_YIELD = 0.25          # cap annualised retirement at 25%/yr
MAX_BODY_FETCHES = 40            # per-ticker HTTP ceiling per run

_SHARES_RE = re.compile(
    r"(?:number of (?:ordinary )?shares? |shares? |)"
    r"purchased\s*:?\s*([\d,]+)", re.IGNORECASE)
_ISC_RE = re.compile(
    r"(?:issued share capital (?:comprises|will comprise(?:s)?(?: of)?)|"
    r"total (?:number of )?(?:issued )?(?:ordinary )?shares?(?: in issue)?"
    r"(?: will comprise(?:s)?(?: of)?| is| comprises)?|"
    r")\s*([\d,]{7,})\s*(?:ordinary )?shares?", re.IGNORECASE)
# Fallback: "<big number> ordinary shares with voting rights"
_ISC_VR_RE = re.compile(
    r"([\d,]{7,})\s*ordinary shares? with voting rights", re.IGNORECASE)


def _cache_path(url: str) -> Path:
    BUYBACK_DIR.mkdir(parents=True, exist_ok=True)
    rns_id = re.sub(r"[^A-Za-z0-9]+", "_", url.rstrip("/").split("/")[-1])
    return BUYBACK_DIR / f"{rns_id}.json"


def fetch_buyback_detail(url: str, *, use_cache: bool = True,
                         announce_date: str | None = None) -> dict:
    """Parse one buyback body for shares_purchased + issued_share_capital.
    Cached per-URL. Returns {shares, isc, date}."""
    cp = _cache_path(url)
    if use_cache and cp.exists():
        try:
            rec = json.loads(cp.read_text())
            if announce_date and not rec.get("date"):
                rec["date"] = announce_date
                cp.write_text(json.dumps(rec))
            return rec
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {"shares": None, "isc": None, "date": announce_date}
    text = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html)))
    shares = None
    m = _SHARES_RE.search(text)
    if m:
        try:
            shares = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    isc = None
    m = _ISC_RE.search(text) or _ISC_VR_RE.search(text)
    if m:
        try:
            isc = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    rec = {"shares": shares, "isc": isc, "date": announce_date}
    if use_cache:
        try:
            cp.write_text(json.dumps(rec))
        except Exception:
            pass
    return rec


def analyse_ticker(epic: str) -> dict | None:
    """Return the run-rate summary for one EPIC, or None if no buyback
    filings in the window."""
    fp = INV_DIR / f"{epic}.json"
    if not fp.exists():
        return None
    try:
        items = json.loads(fp.read_text())
    except Exception:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    filings = []
    for a in items:
        if a.get("category") != "buyback" or not a.get("date"):
            continue
        try:
            dt = datetime.fromisoformat(a["date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        filings.append((dt, a))
    if not filings:
        return None
    filings.sort(key=lambda x: x[0])

    n_filings = len(filings)
    span_days = (filings[-1][0] - filings[0][0]).days
    months = {(dt.year, dt.month) for dt, _ in filings}
    n_months = len(months)
    sustained = (n_filings >= MIN_FILINGS and span_days >= MIN_SPAN_DAYS
                 and n_months >= MIN_DISTINCT_MONTHS)

    # Body-parse filings for shares + latest ISC, MOST-RECENT FIRST so
    # the HTTP cap never silently drops the recent activity that drives
    # the run-rate. Annualisation later uses the span actually parsed,
    # not the full filing span — parsing 40 of 108 filings but dividing
    # by the full-period days would understate the yield inconsistently.
    total_shares = 0
    latest_isc = None
    fetched = 0
    parsed = 0
    parsed_dates: list = []
    for dt, a in reversed(filings):   # newest -> oldest
        cp = _cache_path(a["url"])
        had_cache = cp.exists()
        if not had_cache and fetched >= MAX_BODY_FETCHES:
            continue
        det = fetch_buyback_detail(a["url"], announce_date=a["date"])
        if not had_cache:
            fetched += 1
        if det.get("shares"):
            total_shares += det["shares"]
            parsed += 1
            parsed_dates.append(dt)
        if det.get("isc") and latest_isc is None:
            latest_isc = det["isc"]   # newest-first -> first ISC seen is latest
    # Span actually covered by the parsed filings (for honest annualising)
    parsed_span_days = ((max(parsed_dates) - min(parsed_dates)).days
                        if len(parsed_dates) >= 2 else span_days)

    result = {
        "ticker": f"{epic}.L",
        "n_filings_12m": n_filings,
        "span_days": span_days,
        "n_distinct_months": n_months,
        "sustained": sustained,
        "one_off": not sustained,
        "shares_bought_parsed": total_shares,
        "filings_parsed": parsed,
        "issued_share_capital": latest_isc,
        "retired_frac_observed": None,
        "buyback_yield_annualised": None,
        "buyback_accel": None,
    }
    if latest_isc and total_shares and parsed > 0:
        # Fraction retired = shares / (ISC + shares already retired).
        # ISC is post-buyback, so add the bought-back shares to the
        # denominator to approximate the starting base.
        base = latest_isc + total_shares
        retired = total_shares / base if base > 0 else None
        result["retired_frac_observed"] = round(retired, 5) if retired else None
        # Annualise over the PARSED span (>= ~30d to avoid a short burst
        # extrapolating wildly). Sustained flag already gates one-offs.
        if sustained and retired and parsed_span_days >= 30:
            annualised = retired * (365.0 / parsed_span_days)
            annualised = min(MAX_ANNUAL_YIELD, annualised)
            result["buyback_yield_annualised"] = round(annualised, 4)

    # Acceleration: recent-90d filing rate vs prior-90d. Only meaningful
    # when both windows carry activity (never extrapolate from silence).
    now = datetime.now(timezone.utc)
    recent = sum(1 for dt, _ in filings if (now - dt).days <= 90)
    prior = sum(1 for dt, _ in filings if 90 < (now - dt).days <= 180)
    if prior > 0 and recent > 0:
        result["buyback_accel"] = round(recent / prior, 2)
    return result


def nav_accretion(yield_annualised: float | None,
                  discount: float | None) -> float | None:
    """NAV-per-share accretion / yr from buying back at a discount.
    Only defined for a sustained (annualised) yield."""
    if not yield_annualised or not discount or discount <= 0:
        return None
    y = yield_annualised
    if y >= 1:
        return None
    return round(y * discount / (1.0 - y), 4)


def all_tickers_with_buybacks() -> list[str]:
    out = []
    for jf in INV_DIR.glob("*.json"):
        if jf.parent.name != "investegate":
            continue
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        if any(a.get("category") == "buyback" for a in data):
            out.append(jf.stem)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(OUT_PATH))
    p.add_argument("--tickers", nargs="*")
    args = p.parse_args()
    epics = ([t.replace(".L", "").upper() for t in args.tickers]
             if args.tickers else all_tickers_with_buybacks())
    print(f"Analysing buybacks for {len(epics)} issuer(s)", file=sys.stderr)
    rows = []
    for i, epic in enumerate(epics, 1):
        res = analyse_ticker(epic)
        if res:
            rows.append(res)
        if i % 25 == 0:
            print(f"  [{i}/{len(epics)}]", file=sys.stderr, flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if rows:
        cols = list(rows[0].keys())
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"Wrote {len(rows)} rows to {args.out}", file=sys.stderr)
        sustained = [r for r in rows if r["sustained"]
                     and r["buyback_yield_annualised"]]
        sustained.sort(key=lambda r: -(r["buyback_yield_annualised"] or 0))
        print(f"\nSustained programmes: {len(sustained)}  "
              f"(one-offs excluded from annualisation: "
              f"{sum(1 for r in rows if r['one_off'])})", file=sys.stderr)
        for r in sustained[:12]:
            print(f"  {r['ticker']:<9} yield≈{r['buyback_yield_annualised']*100:4.1f}%/yr  "
                  f"{r['n_filings_12m']:>3} filings / {r['n_distinct_months']}mo / "
                  f"{r['span_days']}d  accel={r['buyback_accel']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
