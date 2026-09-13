#!/usr/bin/env python3
"""AUDITED long growth streaks from EDGAR quarterly observations.

Yahoo's earnings_history caps the beat streak at 4 quarters; the raw
EDGAR cache holds ~7 YEARS of quarterly filings. This pass computes,
per symbol, from SINGLE-CONCEPT consecutive quarterly series:

  rev_yoy_streak_q   consecutive quarters (newest first) with revenue
                     above the same quarter a year earlier
  ni_yoy_streak_q    same for net income (parent-attributable)
  rev_yoy_pos_share_12q  share of the last 12 quarters with positive
                     revenue YoY (durability, gap-tolerant)
  streak_quarters_n  how many YoY comparisons were available (window
                     honesty — a streak of 6 from 6 observations is
                     weaker evidence than 6 from 20)

Methodology (inherits the audited rules): one concept per series
(first alias with data), consecutive ~90-day quarters only (60-130d
gaps), YoY = 4 quarters back within the same chain, positive-prior
base guard (|prior| must be > 0; sign-crossing from a negative prior
counts as growth only when current > 0).
Output: us_edgar_streaks.csv
"""
from __future__ import annotations

import gzip
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("edgar_cache")

REV_ALIASES = ["RevenueFromContractWithCustomerExcludingAssessedTax",
               "Revenues", "SalesRevenueNet", "Revenue",
               "RevenueFromContractsWithCustomers"]
NI_ALIASES = ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent",
              "ProfitLoss"]


def _quarters(facts, aliases):
    """First alias with data -> list of (end_date, val) consecutive
    ~quarterly rows, newest first, single concept."""
    for ns in ("us-gaap", "ifrs-full"):
        for c in aliases:
            obs = (((facts.get(ns) or {}).get(c) or {})
                   .get("units") or {}).get("USD") or []
            rows = {}
            for o in obs:
                s, e, v = o.get("start"), o.get("end"), o.get("val")
                if not (s and e) or v is None:
                    continue
                try:
                    dur = (datetime.strptime(e, "%Y-%m-%d")
                           - datetime.strptime(s, "%Y-%m-%d")).days
                except ValueError:
                    continue
                if 60 <= dur <= 100:            # true quarters
                    rows[(s, e)] = ("Q", float(v))
                elif 330 <= dur <= 380:          # fiscal years
                    rows[(s, e)] = ("FY", float(v))
            qrows = {e: v for (s, e), (k, v) in rows.items() if k == "Q"}
            # SYNTHESIZE the structurally-missing Q4 (10-Ks carry only the
            # FY duration): Q4 = FY - (Q1+Q2+Q3) when exactly three true
            # quarters fall inside the FY window — without this every
            # chain broke at the annual boundary (AAPL max chain = 3).
            for (fs, fe), (k, fv) in rows.items():
                if k != "FY" or fe in qrows:
                    continue
                inside = [(e2, v2) for e2, v2 in qrows.items()
                          if fs <= e2 < fe]
                if len(inside) == 3:
                    qrows[fe] = fv - sum(v2 for _e2, v2 in inside)
            if len(qrows) >= 5:
                return sorted(qrows.items(), reverse=True)
    return []


def _streaks(qrows):
    """(streak, pos_share_12, n_comparisons) from newest-first rows,
    chained on consecutive gaps and YoY at 4-back within the chain."""
    if len(qrows) < 5:
        return 0, None, 0
    dates = [datetime.strptime(d, "%Y-%m-%d") for d, _ in qrows]
    vals = [v for _, v in qrows]
    # build the maximal consecutive chain from the newest row
    chain = [0]
    for i in range(1, len(qrows)):
        gap = (dates[chain[-1]] - dates[i]).days
        if 60 <= gap <= 130:
            chain.append(i)
        elif gap > 130:
            break
    yoy = []
    for pos in range(len(chain) - 4):
        cur, prior = vals[chain[pos]], vals[chain[pos + 4]]
        if prior > 0:
            yoy.append(cur > prior)
        elif cur > 0 >= prior:
            yoy.append(True)                     # loss -> profit counts
        else:
            yoy.append(False)
    if not yoy:
        return 0, None, 0
    streak = 0
    for grew in yoy:
        if grew:
            streak += 1
        else:
            break
    share12 = (sum(yoy[:12]) / min(12, len(yoy))) if yoy else None
    return streak, round(share12, 3) if share12 is not None else None, len(yoy)


def one(path):
    try:
        with gzip.open(path, "rt") as fh:
            data = json.load(fh)
    except Exception:
        return None
    facts = data.get("facts") or {}
    rev_s, rev_share, rev_n = _streaks(_quarters(facts, REV_ALIASES))
    ni_s, _ni_share, ni_n = _streaks(_quarters(facts, NI_ALIASES))
    if rev_n == 0 and ni_n == 0:
        return None
    return {"cik": int(path.name.replace("CIK", "").replace(".json.gz", "")),
            "rev_yoy_streak_q": rev_s, "rev_yoy_pos_share_12q": rev_share,
            "ni_yoy_streak_q": ni_s, "streak_quarters_n": max(rev_n, ni_n)}


def main():
    files = sorted(CACHE_DIR.glob("CIK*.json.gz"))
    print(f"{len(files)} raw caches", file=sys.stderr)
    rows = []
    with ProcessPoolExecutor(max_workers=6) as ex:
        for i, r in enumerate(ex.map(one, files, chunksize=50), 1):
            if r:
                rows.append(r)
            if i % 2000 == 0:
                print(f"  {i}/{len(files)}", file=sys.stderr)
    df = pd.DataFrame(rows)
    # cik -> symbols
    tmap = json.loads(Path("sec_company_tickers.json").read_text())
    sym = pd.DataFrame([{"cik": v["cik_str"], "symbol": v["ticker"]}
                        for v in tmap.values()])
    out = sym.merge(df, on="cik", how="inner").drop(columns=["cik"])
    out.to_csv("us_edgar_streaks.csv", index=False)
    print(f"wrote us_edgar_streaks.csv: {len(out)} symbols; "
          f"streak>=6: {(out['ni_yoy_streak_q']>=6).sum()} NI / "
          f"{(out['rev_yoy_streak_q']>=6).sum()} rev; "
          f">=8: {(out['ni_yoy_streak_q']>=8).sum()} / "
          f"{(out['rev_yoy_streak_q']>=8).sum()}", file=sys.stderr)


if __name__ == "__main__":
    main()
