"""Universe-wide fundamentals from the SEC XBRL frames API.

COVERAGE_AUDIT item C -- the highest-leverage sourcing change available.
One frames call returns ONE concept for EVERY filer in a period
(StockholdersEquity CY2026Q1I -> ~5,200 companies), so ~12 concepts x a
few quarters build a universe-wide quarterly fundamentals store without
per-ticker fetching and without the yfinance dependence that gates a
dozen layers today.

This lifts balance-sheet coverage from ~164 (the quarterly_10q --limit
200 sample) toward ~5,000, and supplies the operating-inflection /
deleveraging / NCAV / leverage inputs over the whole universe instead of
a 28-name shortlist.

Raw frames are cached under xbrl_frames/ so re-runs are cheap; the pivot
xbrl_frames_store.json is keyed by ticker:
  {TICKER: {equity, assets, cur_assets, cur_liab, cash, debt,
            revenue, revenue_prior, gross_profit, gross_profit_prior,
            interest_expense, interest_expense_prior, op_income,
            period_instant, period_duration}}
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "xbrl_frames"
OUT = ROOT / "xbrl_frames_store.json"

# concept -> (list of us-gaap tag fallbacks, kind). instant = balance
# sheet (period like CY2026Q1I); duration = flow (CY2026Q1).
CONCEPTS = {
    "equity":            (["StockholdersEquity"], "instant"),
    "assets":            (["Assets"], "instant"),
    "cur_assets":        (["AssetsCurrent"], "instant"),
    "cur_liab":          (["LiabilitiesCurrent"], "instant"),
    "cash":              (["CashAndCashEquivalentsAtCarryingValue",
                           "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], "instant"),
    "debt":              (["LongTermDebtNoncurrent", "LongTermDebt"], "instant"),
    "revenue":           (["RevenueFromContractWithCustomerExcludingAssessedTax",
                           "Revenues", "SalesRevenueNet"], "duration"),
    "gross_profit":      (["GrossProfit"], "duration"),
    "interest_expense":  (["InterestExpense", "InterestExpenseDebt"], "duration"),
    "op_income":         (["OperatingIncomeLoss"], "duration"),
}


def quarters(n: int, latest_year: int, latest_q: int):
    """Yield the last n (year, q) pairs descending from (latest_year,q)."""
    y, q = latest_year, latest_q
    for _ in range(n):
        yield y, q
        q -= 1
        if q == 0:
            q = 4; y -= 1


def _period(y, q, kind):
    return f"CY{y}Q{q}" + ("I" if kind == "instant" else "")


def fetch_frame(tag, period):
    """Cached frame pull. Returns {cik(int): val} or {}."""
    cf = CACHE / f"{tag}_{period}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    from edgar import _get
    url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json"
    try:
        d = _get(url).json()
    except Exception:
        return {}
    out = {str(row["cik"]): row["val"] for row in d.get("data", [])
           if row.get("cik") is not None and row.get("val") is not None}
    io_util.write_json(cf, out)
    return out


def concept_series(tags, kind, periods):
    """Return {cik: {period: val}} across tag fallbacks (first tag with a
    value for a given cik/period wins)."""
    series: dict[str, dict] = {}
    for period in periods:
        for tag in tags:
            frame = fetch_frame(tag, period)
            time.sleep(0.15)
            for cik, val in frame.items():
                series.setdefault(cik, {}).setdefault(period, val)
    return series


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--q", type=int, default=1, help="latest complete quarter")
    ap.add_argument("--nq", type=int, default=6, help="how many quarters back")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)

    from recent import _cik_to_ticker_map
    cik_map = _cik_to_ticker_map()   # "0000320193" -> "AAPL"
    # frames give bare int cik; normalise both sides to int-string
    cik_tk = {str(int(k)): v for k, v in cik_map.items()}

    qs = list(quarters(args.nq, args.year, args.q))
    inst_periods = [_period(y, q, "instant") for y, q in qs]
    dur_periods = [_period(y, q, "duration") for y, q in qs]
    print(f"frames pull: {len(CONCEPTS)} concepts x {args.nq} quarters "
          f"({qs[0]} .. {qs[-1]})", file=sys.stderr)

    concept_data = {}
    for name, (tags, kind) in CONCEPTS.items():
        periods = inst_periods if kind == "instant" else dur_periods
        concept_data[name] = concept_series(tags, kind, periods)
        n = len(concept_data[name])
        print(f"  {name:<18} {n:>5} filers", file=sys.stderr, flush=True)

    # pivot to per-ticker latest + year-ago
    store: dict[str, dict] = {}
    latest_inst, prior_inst = inst_periods[0], (inst_periods[4] if len(inst_periods) > 4 else inst_periods[-1])
    latest_dur, prior_dur = dur_periods[0], (dur_periods[4] if len(dur_periods) > 4 else dur_periods[-1])

    all_ciks = set()
    for cd in concept_data.values():
        all_ciks |= set(cd.keys())

    for cik in all_ciks:
        tk = cik_tk.get(str(int(cik))) if cik.isdigit() else None
        if not tk:
            continue
        rec = {"cik": cik}
        for name, (tags, kind) in CONCEPTS.items():
            per = concept_data[name].get(cik, {})
            if kind == "instant":
                rec[name] = per.get(latest_inst)
                if name in ("revenue",):  # not instant
                    pass
            else:
                rec[name] = per.get(latest_dur)
                rec[name + "_prior"] = per.get(prior_dur)
        # derived
        eq, cur_a, cur_l = rec.get("equity"), rec.get("cur_assets"), rec.get("cur_liab")
        rec["current_ratio"] = round(cur_a / cur_l, 3) if cur_a and cur_l else None
        rec["net_cash"] = (rec.get("cash") or 0) - (rec.get("debt") or 0) \
            if (rec.get("cash") is not None or rec.get("debt") is not None) else None
        rec["period_instant"] = latest_inst
        rec["period_duration"] = latest_dur
        # drop all-empty rows
        if any(rec.get(k) is not None for k in
               ("equity", "assets", "revenue", "gross_profit")):
            store[tk] = rec

    io_util.write_json(OUT, store)
    print(f"wrote {OUT} ({len(store)} tickers with fundamentals)")
    have_eq = sum(1 for r in store.values() if r.get("equity") is not None)
    have_rev = sum(1 for r in store.values() if r.get("revenue") is not None)
    print(f"  equity: {have_eq}   revenue: {have_rev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
