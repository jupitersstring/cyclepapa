"""Backtest the 10b5-1 termination signal against subsequent price action.

For each ticker with a bullish (sell-plan termination) or bearish
(sell-plan adoption) 10b5-1 event in the past 18 months, fetch the
price on the disclosure date and the price N trading days later.
Compute mean / median forward returns by bucket.

This is the minimum honest sanity check: does the signal we just built
have any directional power historically? Without this, every claim
about "alpha" is conjecture.

Output:
  backtest_10b5_1.csv   per-event returns
  backtest_10b5_1.json  bucketed summary
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "cancel_10b5_1.json"))
    ap.add_argument("--forward-days", type=int, nargs="+",
                    default=[30, 90, 180])
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--limit", type=int, default=600,
                    help="Cap on number of events to backtest")
    ap.add_argument("--csv", default=str(ROOT / "backtest_10b5_1.csv"))
    ap.add_argument("--summary", default=str(ROOT / "backtest_10b5_1.json"))
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr); return 1

    d = json.loads(Path(args.json).read_text())

    events_to_test = []
    for tk, v in d.items():
        for e in v.get("events") or []:
            if e.get("modification_pair"):
                continue
            if e.get("plan_type") not in ("sell", "buy"):
                continue
            if e.get("action") not in ("TERMINATE", "ADOPT"):
                continue
            fd = e.get("filing_date")
            if not fd:
                continue
            events_to_test.append({
                "ticker": tk,
                "filing_date": fd,
                "action": e["action"],
                "plan_type": e["plan_type"],
                "role": e.get("role") or "",
                "shares": e.get("shares") or 0,
                "neo": e.get("neo") or "",
            })

    # Sort by filing_date ascending so the oldest events (with the
    # most price-action history available) are tested first. New events
    # at the head of the list would lack forward returns and waste API
    # calls.
    events_to_test.sort(key=lambda x: x["filing_date"])
    events_to_test = events_to_test[: args.limit]
    print(f"Backtesting {len(events_to_test)} 10b5-1 events", file=sys.stderr)

    # Group events by ticker for batched yfinance pulls
    by_ticker: dict[str, list] = {}
    for e in events_to_test:
        by_ticker.setdefault(e["ticker"], []).append(e)

    # SPY benchmark pull (one history; cached in memory)
    print("Loading SPY benchmark history...", file=sys.stderr)
    spy_df = yf.Ticker("SPY").history(period="2y")
    spy_close = {ts.strftime("%Y-%m-%d"): float(c)
                 for ts, c in spy_df["Close"].items()}
    spy_keys = sorted(spy_close.keys())

    def spy_closest(target):
        for k in spy_keys:
            if k >= target:
                return spy_close[k]
        return None

    rows = []
    max_forward = max(args.forward_days)
    for i, (tk, tk_events) in enumerate(by_ticker.items(), 1):
        try:
            # Pull from oldest filing date - 5d to today
            min_fd = min(e["filing_date"] for e in tk_events)
            start = (datetime.strptime(min_fd[:10], "%Y-%m-%d")
                     - timedelta(days=10)).strftime("%Y-%m-%d")
            df = yf.Ticker(tk).history(start=start, period=None)
        except Exception as ex:
            print(f"  {tk}: history fail: {ex}", file=sys.stderr)
            time.sleep(args.sleep)
            continue
        if df.empty:
            time.sleep(args.sleep)
            continue
        closes = df["Close"]
        # Index by date string
        date_to_close = {
            ts.strftime("%Y-%m-%d"): float(c)
            for ts, c in closes.items()
        }
        date_keys = sorted(date_to_close.keys())

        def closest_at_or_after(target: str):
            for d_str in date_keys:
                if d_str >= target:
                    return d_str, date_to_close[d_str]
            return None, None

        for e in tk_events:
            fd0_str, fd0_px = closest_at_or_after(e["filing_date"])
            if not fd0_px or fd0_px <= 0:
                continue
            for nd in args.forward_days:
                target = (datetime.strptime(e["filing_date"][:10], "%Y-%m-%d")
                          + timedelta(days=int(nd * 1.45))).strftime("%Y-%m-%d")
                fd_t_str, fd_t_px = closest_at_or_after(target)
                if not fd_t_px:
                    continue
                ret = (fd_t_px / fd0_px - 1.0) * 100
                # Benchmark-adjusted return: SPY return over the same window
                spy_t0 = spy_closest(e["filing_date"])
                spy_t = spy_closest(target)
                spy_ret = ((spy_t / spy_t0 - 1.0) * 100
                           if spy_t0 and spy_t and spy_t0 > 0 else None)
                excess = round(ret - spy_ret, 2) if spy_ret is not None else None
                rows.append({
                    "ticker": tk,
                    "filing_date": e["filing_date"],
                    "action": e["action"],
                    "plan_type": e["plan_type"],
                    "role": e["role"][:40],
                    "neo": e["neo"][:40],
                    "shares": e["shares"],
                    "forward_days": nd,
                    "px_at_disclosure": round(fd0_px, 2),
                    "px_forward": round(fd_t_px, 2),
                    "return_pct": round(ret, 2),
                    "spy_return_pct": round(spy_ret, 2) if spy_ret is not None else None,
                    "excess_return_pct": excess,
                    "bucket": (
                        "term_sell" if e["action"] == "TERMINATE" and e["plan_type"] == "sell"
                        else "adopt_sell" if e["action"] == "ADOPT" and e["plan_type"] == "sell"
                        else "term_buy" if e["action"] == "TERMINATE" and e["plan_type"] == "buy"
                        else "adopt_buy"
                    ),
                })
        if i % 25 == 0:
            print(f"  [{i}/{len(by_ticker)}] tickers processed", flush=True)
        time.sleep(args.sleep)

    with open(args.csv, "w", newline="") as f:
        fields = ["ticker", "filing_date", "action", "plan_type",
                  "role", "neo", "shares", "forward_days",
                  "px_at_disclosure", "px_forward", "return_pct",
                  "spy_return_pct", "excess_return_pct", "bucket"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Bucket summary
    import statistics
    summary = {}
    for bucket in ("term_sell", "adopt_sell", "term_buy", "adopt_buy"):
        for nd in args.forward_days:
            bucket_rows = [r for r in rows
                           if r["bucket"] == bucket and r["forward_days"] == nd]
            if not bucket_rows:
                continue
            rets = [r["return_pct"] for r in bucket_rows]
            excess = [r["excess_return_pct"] for r in bucket_rows
                      if r["excess_return_pct"] is not None]
            key = f"{bucket}_{nd}d"
            summary[key] = {
                "n": len(rets),
                "mean_return_pct": round(statistics.mean(rets), 2),
                "median_return_pct": round(statistics.median(rets), 2),
                "stdev_pct": round(statistics.stdev(rets), 2) if len(rets) > 1 else None,
                "win_rate_pct": round(
                    sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                "n_excess": len(excess),
                "mean_excess_pct": round(statistics.mean(excess), 2) if excess else None,
                "median_excess_pct": round(statistics.median(excess), 2) if excess else None,
                "beat_spy_rate_pct": round(
                    sum(1 for r in excess if r > 0) / len(excess) * 100, 1
                ) if excess else None,
            }

    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {args.csv} ({len(rows)} rows) + {args.summary}\n")
    print(f"=== BUCKETED FORWARD RETURNS (vs SPY benchmark) ===")
    print(f"{'bucket':<15}{'fwd':>5}{'n':>5}{'mean%':>8}{'med%':>8}"
          f"{'win%':>6}{'ex_mean%':>10}{'ex_med%':>10}{'beat%':>7}")
    print("-" * 90)
    for key, s in sorted(summary.items()):
        bucket, nd = key.rsplit("_", 1)
        nd_n = nd.rstrip("d")
        ex_mean = f"{s['mean_excess_pct']:>9.2f}" if s.get('mean_excess_pct') is not None else "        ?"
        ex_med = f"{s['median_excess_pct']:>9.2f}" if s.get('median_excess_pct') is not None else "        ?"
        beat = f"{s['beat_spy_rate_pct']:>6.1f}" if s.get('beat_spy_rate_pct') is not None else "     ?"
        print(f"{bucket:<15}{nd_n:>5}{s['n']:>5}{s['mean_return_pct']:>8.2f}"
              f"{s['median_return_pct']:>8.2f}{s['win_rate_pct']:>6.1f}"
              f"{ex_mean}{ex_med}{beat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
