#!/usr/bin/env python3
"""
One orchestrator for the whole anomaly pipeline. Reads cached data (no network
by default), runs the corrected scanners across a universe set, and writes a
single dated, committable report to results/ (so analysis survives the session).

  python3 run_scan.py                         # default cuts, cached-only
  python3 run_scan.py --universes us-midcap uk-allcap --min-net 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import sys
from contextlib import redirect_stdout

import pandas as pd

import measure_bandpass as mb
import fcf_screen as fs
from midcap_weekly_anomalies import get_universe

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def _capture(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            fn(*a, **k)
        except SystemExit:
            pass
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universes", nargs="+",
                    default=["us-midcap", "us-smallcap", "us-microcap", "uk-allcap"])
    ap.add_argument("--min-net", type=int, default=3)
    ap.add_argument("--band", default="B1")
    ap.add_argument("--from-low", type=float, default=0.15)
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    today = dt.date.today().isoformat()
    out = [f"# Anomaly scan — {today}", ""]

    for u in args.universes:
        out.append(f"\n## {u}\n")
        for tf in ("weekly", "daily"):
            ns = argparse.Namespace(
                universe=u, limit=None, period="20y", weekly=(tf == "weekly"),
                daily=(tf == "daily"), m90=False, band=args.band, window=13,
                window_m90=20, recent_daily=5, recent_weekly=2, recent_m90=6,
                top=200, cached_only=True, refresh=False, min_net=args.min_net,
                csv=os.path.join(RESULTS, f"breadth_{u}_{tf}_{today}.csv"))
            out.append(f"### {u} {tf} (DIRECTIONAL breadth, net>=+/-{args.min_net})\n```")
            out.append(_capture(mb.run, ns).strip())
            out.append("```")

        # FCF / 200w-low value screen (cached weekly stage-1; fundamentals are live)
        fns = argparse.Namespace(
            universe=u, period="20y", from_low=args.from_low, min_fcf_yield=0.07,
            min_buyback=0.04, active_ok=False, max_nd_ebitda=4.5, max_yield=0.60, on="ev",
            limit_fund=120, top=40, passed_only=False,
            csv=os.path.join(RESULTS, f"fcf_{u}_{today}.csv"))
        out.append(f"### {u} 200w-low x FCF x buyback\n```")
        out.append(_capture(fs.run, fns).strip())
        out.append("```")

    report = os.path.join(RESULTS, f"scan_{today}.md")
    with open(report, "w") as f:
        f.write("\n".join(out))
    print(f"[run_scan] report -> {report}")


if __name__ == "__main__":
    main()
