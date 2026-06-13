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
import rotation_screener as rot
import early_inflection as ei
from midcap_weekly_anomalies import get_universe

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def anomaly_board(today: str) -> str:
    """Consolidated cross-timeframe anomaly board from the dated breadth + FCF
    CSVs: names whose DIRECTIONAL breadth aligns on weekly AND daily, flagged
    with 💰 when they also clear the 200w-low/FCF/buyback value screen."""
    import glob
    wk, dl = {}, {}
    for f in glob.glob(os.path.join(RESULTS, f"breadth_*_weekly_{today}.csv")):
        for _, r in pd.read_csv(f).iterrows():
            wk[r["symbol"]] = r["net"]
    for f in glob.glob(os.path.join(RESULTS, f"breadth_*_daily_{today}.csv")):
        for _, r in pd.read_csv(f).iterrows():
            dl[r["symbol"]] = r["net"]
    fcf = set()
    for f in glob.glob(os.path.join(RESULTS, f"fcf_*_{today}.csv")):
        d = pd.read_csv(f)
        if "pass_all" in d:
            fcf |= set(d[d["pass_all"] == True]["symbol"])
    common = set(wk) & set(dl)
    tag = lambda s: f"{s}(w{int(wk[s]):+d}/d{int(dl[s]):+d})" + ("💰" if s in fcf else "")
    lines = [f"\n## Anomaly board — cross-timeframe agreement (universe={len(common)})\n"]
    for lab, lo in (("≥+3", 3), ("≥+2", 2)):
        bull = sorted([s for s in common if wk[s] >= lo and dl[s] >= lo],
                      key=lambda s: -(wk[s] + dl[s]))
        bear = sorted([s for s in common if wk[s] <= -lo and dl[s] <= -lo],
                      key=lambda s: wk[s] + dl[s])
        lines.append(f"- **Bullish net {lab} both TFs ({len(bull)}):** "
                     + ("  ".join(tag(s) for s in bull) or "none"))
        lines.append(f"- **Bearish net {lab} both TFs ({len(bear)}):** "
                     + ("  ".join(tag(s) for s in bear) or "none"))
    conf = [s for s in common if wk[s] >= 2 and dl[s] >= 2 and s in fcf]
    lines.append(f"- **Triple confluence (breadth≥+2 both + value 💰): "
                 + (", ".join(conf) or "none") + "**")
    return "\n".join(lines)


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

    # --- consolidated anomaly board from the dated breadth + FCF CSVs ---
    out.append(anomaly_board(today))

    # --- cross-universe rotation + early-inflection (run once over all cuts) ---
    out.append("\n## Rotation — where money IS (realised flow)\n```")
    rns = argparse.Namespace(universes=args.universes, k=8, top=15, pairs=8,
                             min_industry=4, yf_labels=0)
    out.append(_capture(rot.run, rns).strip())
    out.append("```")
    out.append("\n## Early inflection — where money is ABOUT to turn (smoothed)\n```")
    ens = argparse.Namespace(universes=args.universes, fast=10, slow=21, recent=5,
                             top=20, min_industry=4)
    out.append(_capture(ei.run, ens).strip())
    out.append("```")

    report = os.path.join(RESULTS, f"scan_{today}.md")
    with open(report, "w") as f:
        f.write("\n".join(out))
    print(f"[run_scan] report -> {report}")


if __name__ == "__main__":
    main()
