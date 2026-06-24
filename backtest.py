"""Minimal event-study backtest harness.

Idea: for each historical wind-down / strategic-review / tender RNS
filing in data/investegate/*.json, compute the realised price return
over the N-month window after the filing date. Aggregate by catalyst
class and compare to the prior expected_total_return / IRR that the
screener WOULD have predicted at that moment.

KNOWN LIMITATION — total-return vs price-return.
  For WIND_DOWN_COMMITTED names the price legitimately falls toward
  zero as capital is returned to shareholders. The current
  price-return-only computation therefore understates true holder
  return for wind-downs by the value of cash distributions, which
  often constitute the majority of return for these names. A future
  iteration should look up `Dividends` from yfinance / AIC and add
  the cumulative cash payouts back. Pre-event 12m / pre-event 24m
  returns (i.e. measuring whether *entering* at the RNS date would
  have made money TO HERE) is also a useful cross-check that doesn't
  have this problem — added below as `pre_event_to_today`.

This is the first calibration tool — every catalyst probability and
duration in params.py was hand-picked; this lets us check the priors
against actual UK CEF event history.

Outputs:
  backtest_events.csv   — per-event rows with date / class / realised
                          T+6 / T+12 / T+24 returns
  backtest_summary.csv  — by catalyst class, median realised return
                          and predicted from params
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import params


HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
PRICES_DIR = HERE / "data" / "prices_daily"


# Map RNS category to catalyst class for backtest scoring.
# Coarse — a winddown filing is the start of WIND_DOWN_COMMITTED;
# review is STRATEGIC_REVIEW; tender is RETURN_OF_CAPITAL_LIVE.
CATEGORY_TO_CATALYST = {
    "winddown":        "WIND_DOWN_COMMITTED",
    "review":          "STRATEGIC_REVIEW",
    "tender":          "RETURN_OF_CAPITAL_LIVE",
    "capdistribution": "RETURN_OF_CAPITAL_LIVE",
}


def _load_prices(ticker: str) -> pd.DataFrame | None:
    """Load the daily-OHLCV parquet for a ticker if present."""
    fp = PRICES_DIR / f"{ticker}.parquet"
    if not fp.exists():
        return None
    try:
        df = pd.read_parquet(fp)
    except Exception:
        return None
    if df.empty:
        return None
    if "Close" not in df.columns:
        return None
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _return_from(df: pd.DataFrame, anchor: pd.Timestamp,
                 months: int) -> float | None:
    """Return between the anchor date and `months` after."""
    anchor = pd.Timestamp(anchor).tz_localize(None) if anchor.tz is not None else pd.Timestamp(anchor)
    target = anchor + pd.DateOffset(months=months)
    p_start_rows = df.loc[df.index <= anchor]
    p_end_rows = df.loc[df.index <= target]
    if p_start_rows.empty or p_end_rows.empty:
        return None
    p_start = float(p_start_rows["Close"].iloc[-1])
    p_end = float(p_end_rows["Close"].iloc[-1])
    if p_start <= 0:
        return None
    return (p_end / p_start) - 1.0


def collect_events(min_year: int = 2022) -> list[dict]:
    events = []
    for jf in sorted(INV_DIR.glob("*.json")):
        epic = jf.stem
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for a in data:
            cat = a.get("category")
            if cat not in CATEGORY_TO_CATALYST:
                continue
            date = a.get("date")
            if not date or len(date) < 4:
                continue
            try:
                yr = int(date[:4])
            except ValueError:
                continue
            if yr < min_year:
                continue
            events.append({
                "ticker": f"{epic}.L",
                "epic": epic,
                "date": date,
                "rns_category": cat,
                "catalyst": CATEGORY_TO_CATALYST[cat],
                "title": (a.get("title") or "")[:80],
            })
    # Deduplicate per (ticker, catalyst) — multiple winddown filings
    # within 3 months collapse into the first one.
    events.sort(key=lambda r: (r["ticker"], r["catalyst"], r["date"]))
    deduped = []
    last: dict | None = None
    for e in events:
        if last and last["ticker"] == e["ticker"] and last["catalyst"] == e["catalyst"]:
            last_dt = datetime.fromisoformat(last["date"])
            cur_dt = datetime.fromisoformat(e["date"])
            if (cur_dt - last_dt).days < 90:
                continue
        deduped.append(e)
        last = e
    return deduped


def score_events(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        df = _load_prices(e["ticker"])
        if df is None:
            continue
        anchor = pd.Timestamp(e["date"])
        if anchor > df.index.max():
            continue
        row = dict(e)
        row["realised_6m"] = _return_from(df, anchor, 6)
        row["realised_12m"] = _return_from(df, anchor, 12)
        row["realised_24m"] = _return_from(df, anchor, 24)
        # "to today" — useful cross-check for ongoing wind-downs
        today = df.index.max()
        days_held = (today - anchor).days
        if days_held > 0:
            try:
                p_anchor = float(df.loc[df.index <= anchor]["Close"].iloc[-1])
                p_today = float(df["Close"].iloc[-1])
                row["return_to_today"] = (p_today / p_anchor) - 1.0 if p_anchor > 0 else None
                row["days_held"] = days_held
            except Exception:
                pass
        row["predicted_prob"] = params.CATALYST_PROB_BASE.get(e["catalyst"])
        row["predicted_duration_m"] = params.CATALYST_DURATION_MONTHS.get(
            e["catalyst"])
        out.append(row)
    return out


def summarise(rows: list[dict]) -> list[dict]:
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    out = []
    for cat, g in df.groupby("catalyst"):
        summary = {
            "catalyst": cat,
            "n_events": len(g),
            "median_realised_12m": (g["realised_12m"].median()
                                    if g["realised_12m"].notna().any() else None),
            "median_realised_24m": (g["realised_24m"].median()
                                    if g["realised_24m"].notna().any() else None),
            "p25_realised_12m": (g["realised_12m"].quantile(0.25)
                                 if g["realised_12m"].notna().any() else None),
            "p75_realised_12m": (g["realised_12m"].quantile(0.75)
                                 if g["realised_12m"].notna().any() else None),
            "predicted_prob": params.CATALYST_PROB_BASE.get(cat),
            "predicted_duration_m": params.CATALYST_DURATION_MONTHS.get(cat),
        }
        out.append(summary)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-events",
                   default=str(HERE / "backtest_events.csv"))
    p.add_argument("--out-summary",
                   default=str(HERE / "backtest_summary.csv"))
    p.add_argument("--min-year", type=int, default=2022)
    args = p.parse_args()
    events = collect_events(min_year=args.min_year)
    print(f"Collected {len(events)} events from {args.min_year}+",
          file=sys.stderr)
    scored = score_events(events)
    print(f"Scored {len(scored)} (had price data)", file=sys.stderr)
    if scored:
        cols = sorted({k for r in scored for k in r})
        with open(args.out_events, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in scored:
                w.writerow(r)
        print(f"Wrote {args.out_events}", file=sys.stderr)
    summary = summarise(scored)
    if summary:
        cols = sorted({k for r in summary for k in r})
        with open(args.out_summary, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in summary:
                w.writerow(r)
        print(f"Wrote {args.out_summary}", file=sys.stderr)
        print("\nCalibration summary:", file=sys.stderr)
        for s in summary:
            m12 = s["median_realised_12m"]
            print(f"  {s['catalyst']:<28} n={s['n_events']:>3}  "
                  f"P_predicted={s['predicted_prob']}  "
                  f"med 12m realised: "
                  f"{m12*100:+.1f}%" if m12 is not None else "n/a",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
