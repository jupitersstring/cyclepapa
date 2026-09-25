"""NOL shell / Section 382 tax-asset scanner (live).

A Tax Benefits Preservation Rights Plan (a Section 382 "NOL poison pill") is
a near-certain tell that a company has MATERIAL net-operating-loss
carryforwards it is actively protecting from an ownership change -- the
WMIH / Clark Street Value archetype. The NOLs are a hidden tax asset worth
up to ~21c per dollar of loss to a future acquirer, and the rights plan
signals management knows it. The framework was not sourcing these live (the
old nol_shells.csv was a frozen June snapshot).

This wires recent.recent_nol_rights_plan_range into a fresh, dated feed and
enriches it: the sweet spot is a small, cash-rich or asset-light SHELL where
the NOL is large relative to the market cap.

Output: nol_shell.json keyed by ticker.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import io_util
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "nol_shell.json"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()
    from recent import recent_nol_rights_plan_range
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}
    frames = json.loads((ROOT / "xbrl_frames_store.json").read_text()) \
        if (ROOT / "xbrl_frames_store.json").exists() else {}

    filings = recent_nol_rights_plan_range(start, end, limit=args.limit)

    out = {}
    for r in filings:
        tk = (r.ticker or "").upper()
        if not tk:
            continue
        bad, _ = is_excluded(tk)
        if bad:
            continue
        rec = out.setdefault(tk, {
            "ticker": tk, "company": r.company,
            "date": r.filing_date, "accession": r.accession, "score": 0.0})
        if r.filing_date > rec["date"]:
            rec["date"] = r.filing_date

    for tk, rec in out.items():
        y = yf.get(tk) or {}
        fr = frames.get(tk) or {}
        mcap = _num(y.get("mcap")); pb = _num(y.get("p_b"))
        net_cash = _num(fr.get("net_cash"))
        s = 10.0                                    # base: §382 plan = real NOL
        if mcap and mcap < 3e8:
            s += 6; rec["micro_cap"] = True          # shell-scale: NOL >> mcap
        elif mcap and mcap < 1e9:
            s += 3
        if net_cash is not None and mcap and net_cash > 0.3 * mcap:
            s += 5; rec["cash_rich"] = True          # cash-rich NOL vehicle
        if pb is not None and 0 < pb < 1.0:
            s += 3; rec["below_book"] = True
        rec["mcap"] = mcap; rec["p_b"] = pb; rec["net_cash"] = net_cash
        rec["score"] = round(s, 1)

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print(f"wrote {OUT} ({len(out)} Section-382 NOL-protection names, "
          f"{start}..{end})")
    print(f"{'TKR':<8}{'SCORE':>6}  COMPANY")
    for r in ranked[:25]:
        flags = " ".join(k for k in ("micro_cap", "cash_rich", "below_book")
                         if r.get(k))
        print(f"{r['ticker']:<8}{r['score']:>6.1f}  {(r.get('company') or '')[:34]}  {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
