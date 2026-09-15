"""Going-dark / Form 15 scanner (live).

A Form 15 deregisters a company from SEC reporting -- it stops filing
10-K/10-Q and the equity trades OTC pink without public financials. It is
the Oddball-Stocks / squeeze-out terrain: often a controlling holder taking
the company dark to buy out minority holders cheaply, or a deep-value orphan
shedding reporting cost. Form 25 (exchange delisting) frequently pairs with
it. Either way it is a value EVENT that the framework was not sourcing live
(the old going_dark.csv was a frozen June snapshot).

This wires the existing recent.recent_form15_range / recent_form25_range
pullers into a fresh, dated feed and enriches it with valuation so the
squeeze-out / deep-value candidates surface.

Output: going_dark.json keyed by ticker.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import io_util
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "going_dark.json"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=270)
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()
    from recent import recent_form15_range, recent_form25_range
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}

    f15 = recent_form15_range(start, end, limit=args.limit)
    f25 = recent_form25_range(start, end, limit=args.limit)
    forms = {"15": f15, "25": f25}

    out = {}
    for code, filings in forms.items():
        for r in filings:
            tk = (r.ticker or "").upper()
            if not tk:
                continue
            bad, _ = is_excluded(tk)
            if bad:
                continue
            rec = out.setdefault(tk, {
                "ticker": tk, "company": r.company, "forms": [],
                "date": r.filing_date, "score": 0.0})
            if code not in rec["forms"]:
                rec["forms"].append(code)
            if r.filing_date > rec["date"]:
                rec["date"] = r.filing_date

    # enrich + score. Form 15 (deregistration) is the real going-dark tell;
    # Form 25 ALONE is often a routine security-specific delisting (a note, a
    # warrant, a post-merger delisting of the acquired shell) -- noisy for
    # large caps -- so it scores low unless the company is micro/controlled.
    for tk, rec in out.items():
        y = yf.get(tk) or {}
        mcap = _num(y.get("mcap")); pb = _num(y.get("p_b"))
        insider = _num(y.get("insider_pct"))
        has15 = "15" in rec["forms"]
        s = 8.0 if has15 else 3.0                    # Form 15 >> Form 25 alone
        if mcap and mcap < 3e8:
            s += 5; rec["micro_cap"] = True          # the going-dark sweet spot
        elif mcap and mcap < 1e9:
            s += 2
        elif mcap and mcap > 1e10:
            s -= 4                                    # big-cap delisting = routine
        if insider is not None and insider >= 0.30:
            s += 4; rec["controlled"] = True         # controlling-holder squeeze-out
        if pb is not None and 0 < pb < 1.0:
            s += 2; rec["below_book"] = True
        rec["mcap"] = mcap; rec["p_b"] = pb
        rec["insider_pct"] = insider
        rec["score"] = round(max(0.0, s), 1)

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print(f"wrote {OUT} ({len(out)} going-dark / delisting names, "
          f"{start}..{end})")
    print(f"{'TKR':<8}{'SCORE':>6}{'FORMS':>7}  COMPANY")
    for r in ranked[:25]:
        print(f"{r['ticker']:<8}{r['score']:>6.1f}{'/'.join(r['forms']):>7}  "
              f"{(r.get('company') or '')[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
