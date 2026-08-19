"""Watchlist-driven alerts.

After a screen run + diff, generate an alerts.csv with rows for any
threshold crossing on a watchlist name:

  RESOLUTION_CROSS_40       — resolution_score crossed from <0.40 to >=0.40
  NEW_INSIDER_BUYS          — PDMR buy count delta >= 3
  NEW_ACTIVIST_TR1          — activist TR-1 buy count delta >= 1
  SLEEVE_ENTERED_SETUP      — moved INTO setup sleeve
  SLEEVE_EXITED_FUNDAMENTALS — moved OUT of fundamentals sleeve
  IRR_JUMP                  — IRR moved >= 10pp
  AVWAP_BREAKDOWN           — price_vs_avwap_pct dropped below -5%

Outputs: alerts_YYYYMMDD.csv

Send/log/email plumbing is intentionally left to the user.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


HERE = Path(os.path.dirname(os.path.abspath(__file__)))


def _watchlist() -> set[str]:
    p = HERE / "watchlist.csv"
    if not p.exists():
        return set()
    out = set()
    with open(p) as f:
        for r in csv.DictReader(f):
            t = r.get("ticker", "").strip()
            if t:
                out.add(t)
    return out


def detect(today: pd.DataFrame, prior: pd.DataFrame) -> list[dict]:
    wl = _watchlist()
    if not wl:
        return []
    today = today[today["ticker"].isin(wl)].set_index("ticker")
    prior = prior[prior["ticker"].isin(wl)].set_index("ticker")
    out: list[dict] = []
    for t in today.index.intersection(prior.index):
        a = today.loc[t]
        b = prior.loc[t]

        def _f(v, default=0.0):
            try:
                return float(v) if pd.notna(v) else default
            except (TypeError, ValueError):
                return default

        # Resolution crossing 0.40
        r_now = _f(a.get("resolution_score"))
        r_prior = _f(b.get("resolution_score"))
        if r_prior < 0.40 <= r_now:
            out.append({"ticker": t, "kind": "RESOLUTION_CROSS_40",
                        "from": round(r_prior, 3), "to": round(r_now, 3),
                        "summary": f"resolution {r_prior:.2f} → {r_now:.2f}"})
        # New PDMR buys
        p_now = _f(a.get("rns_pdmr_buys"))
        p_prior = _f(b.get("rns_pdmr_buys"))
        if p_now - p_prior >= 3:
            out.append({"ticker": t, "kind": "NEW_INSIDER_BUYS",
                        "from": int(p_prior), "to": int(p_now),
                        "summary": f"PDMR buys {int(p_prior)} → {int(p_now)} "
                                   f"(+{int(p_now - p_prior)})"})
        # New activist TR-1
        ab_now = _f(a.get("rns_tr1_activist_buys"))
        ab_prior = _f(b.get("rns_tr1_activist_buys"))
        if ab_now - ab_prior >= 1:
            holders = a.get("activist_holders") or ""
            out.append({"ticker": t, "kind": "NEW_ACTIVIST_TR1",
                        "from": int(ab_prior), "to": int(ab_now),
                        "summary": f"activist TR-1 +{int(ab_now - ab_prior)}; "
                                   f"{str(holders)[:60]}"})
        # Sleeve membership changes
        for sleeve, alert_in, alert_out in [
            ("in_setup_sleeve", "SLEEVE_ENTERED_SETUP", "SLEEVE_EXITED_SETUP"),
            ("in_fundamentals_sleeve", "SLEEVE_ENTERED_FUND",
             "SLEEVE_EXITED_FUND"),
        ]:
            s_now = bool(a.get(sleeve, False))
            s_prior = bool(b.get(sleeve, False))
            if s_now and not s_prior:
                out.append({"ticker": t, "kind": alert_in,
                            "from": "no", "to": "yes",
                            "summary": f"{sleeve} entered"})
            elif s_prior and not s_now:
                out.append({"ticker": t, "kind": alert_out,
                            "from": "yes", "to": "no",
                            "summary": f"{sleeve} exited"})
        # IRR jump
        irr_now = _f(a.get("expected_irr"))
        irr_prior = _f(b.get("expected_irr"))
        if abs(irr_now - irr_prior) >= 0.10:
            arrow = "▲" if irr_now > irr_prior else "▼"
            out.append({"ticker": t, "kind": "IRR_JUMP",
                        "from": round(irr_prior * 100, 1),
                        "to": round(irr_now * 100, 1),
                        "summary": f"IRR {irr_prior * 100:.1f}% → "
                                   f"{irr_now * 100:.1f}% {arrow}"})
        # Anchored VWAP breakdown
        av_now = _f(a.get("price_vs_avwap_pct"))
        av_prior = _f(b.get("price_vs_avwap_pct"))
        if av_now <= -0.05 and av_prior > -0.05:
            out.append({"ticker": t, "kind": "AVWAP_BREAKDOWN",
                        "from": round(av_prior, 3),
                        "to": round(av_now, 3),
                        "summary": f"price vs avwap "
                                   f"{av_prior * 100:+.1f}% → "
                                   f"{av_now * 100:+.1f}%"})
    return out


def latest_results() -> list[Path]:
    out = []
    for p in HERE.glob("results_*.csv"):
        if "_top30" in p.name or "_sleeves" in p.name:
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--today", default=None)
    p.add_argument("--prior", default=None)
    args = p.parse_args()
    candidates = latest_results()
    if len(candidates) < 2 and not (args.today and args.prior):
        print("Need two results CSVs to diff", file=sys.stderr)
        return 1
    today_path = Path(args.today) if args.today else candidates[0]
    prior_path = Path(args.prior) if args.prior else candidates[1]
    today = pd.read_csv(today_path)
    prior = pd.read_csv(prior_path)
    alerts = detect(today, prior)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    out_path = HERE / f"alerts_{stamp}.csv"
    cols = ["ticker", "kind", "from", "to", "summary"]
    if alerts:
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for a in alerts:
                w.writerow(a)
        print(f"[alerts] {len(alerts)} alerts written to {out_path}",
              file=sys.stderr)
        for a in alerts:
            print(f"  ALERT  {a['ticker']:<10}  {a['kind']:<24}  "
                  f"{a['summary']}", file=sys.stderr)
    else:
        print("[alerts] none", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
