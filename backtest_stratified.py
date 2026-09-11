"""Stratified backtest of the 10b5-1 signal.

Builds on backtest_10b5_1.py by slicing the same event population
along three axes:

  role_tier:    CEO/Chair, CFO, Other (Director / VP / SVP / etc.)
  size_tier:    >=250K shares, 50K-250K, <50K, unknown
  age_bucket:   2025-H1, 2025-H2, 2026-H1 (filing-date based)

For each (bucket, action, plan_type, horizon) we report:
  n, mean return, median return, mean excess vs SPY, median excess,
  win rate (return > 0), beat-SPY rate.

Reuses the per-ticker yfinance pull from backtest_10b5_1.py via a
small shared price cache; the SPY benchmark is loaded once.

This is the honest sanity check: does the signal hold up when we
slice it? Bullish CEO sell-plan terminations should be the strongest
single bucket if the directional thesis is right.

Output:
  backtest_stratified.csv     all per-event rows
  backtest_stratified.json    bucketed summaries
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def role_tier(role: str) -> str:
    r = (role or "").lower()
    if any(t in r for t in ("ceo", "chief executive", "chair",
                              "executive chair", "president and ceo")):
        return "CEO_or_Chair"
    if any(t in r for t in ("cfo", "chief financial")):
        return "CFO"
    return "Other"


def size_tier(shares: int) -> str:
    if not shares:
        return "unknown"
    if shares >= 250_000:
        return "ge_250k"
    if shares >= 50_000:
        return "50k_to_250k"
    return "lt_50k"


def age_bucket(filing_date: str) -> str:
    try:
        d = datetime.strptime(filing_date[:10], "%Y-%m-%d")
    except Exception:
        return "unknown"
    y, m = d.year, d.month
    if y == 2025 and m <= 6: return "2025_H1"
    if y == 2025: return "2025_H2"
    if y == 2026 and m <= 6: return "2026_H1"
    return f"{y}_other"


def bucket_label(action: str, plan_type: str) -> str:
    if action == "TERMINATE" and plan_type == "sell": return "term_sell"
    if action == "ADOPT" and plan_type == "sell": return "adopt_sell"
    if action == "TERMINATE" and plan_type == "buy": return "term_buy"
    if action == "ADOPT" and plan_type == "buy": return "adopt_buy"
    return f"{action}_{plan_type}"


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return None
    rets = [r["return_pct"] for r in rows]
    excess = [r["excess_return_pct"] for r in rows
              if r["excess_return_pct"] is not None]
    out = {
        "n": len(rets),
        "mean_return_pct": round(statistics.mean(rets), 2),
        "median_return_pct": round(statistics.median(rets), 2),
        "win_rate_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
    }
    if excess:
        out.update({
            "n_excess": len(excess),
            "mean_excess_pct": round(statistics.mean(excess), 2),
            "median_excess_pct": round(statistics.median(excess), 2),
            "beat_spy_rate_pct": round(
                sum(1 for r in excess if r > 0) / len(excess) * 100, 1),
        })
    if len(rets) > 1:
        out["stdev_pct"] = round(statistics.stdev(rets), 2)
        # 95% confidence interval on mean (rough, t-distribution approx)
        se = out["stdev_pct"] / (len(rets) ** 0.5)
        out["mean_se_pct"] = round(se, 2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "cancel_10b5_1.json"))
    ap.add_argument("--forward-days", type=int, nargs="+",
                    default=[30, 90, 180])
    ap.add_argument("--sleep", type=float, default=0.20)
    ap.add_argument("--limit", type=int, default=2000,
                    help="Cap on number of events tested")
    ap.add_argument("--csv", default=str(ROOT / "backtest_stratified.csv"))
    ap.add_argument("--summary", default=str(ROOT / "backtest_stratified.json"))
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr); return 1

    d = json.loads(Path(args.json).read_text())

    events = []
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
            events.append({
                "ticker": tk,
                "filing_date": fd,
                "action": e["action"],
                "plan_type": e["plan_type"],
                "role": e.get("role") or "",
                "shares": e.get("shares") or 0,
                "neo": e.get("neo") or "",
                "role_tier": role_tier(e.get("role") or ""),
                "size_tier": size_tier(e.get("shares") or 0),
                "age_bucket": age_bucket(fd),
                "bucket": bucket_label(e["action"], e["plan_type"]),
            })

    # Sort by date ascending so events with verifiable forward returns
    # come first
    events.sort(key=lambda x: x["filing_date"])
    events = events[: args.limit]
    print(f"Testing {len(events)} events", file=sys.stderr)

    # Per-ticker grouping
    by_ticker = {}
    for e in events:
        by_ticker.setdefault(e["ticker"], []).append(e)

    # SPY benchmark
    print("Loading SPY benchmark history...", file=sys.stderr)
    spy_df = yf.Ticker("SPY").history(period="2y")
    spy_close = {ts.strftime("%Y-%m-%d"): float(c)
                 for ts, c in spy_df["Close"].items()}
    spy_keys = sorted(spy_close.keys())

    def spy_closest(target: str):
        for k in spy_keys:
            if k >= target:
                return spy_close[k]
        return None

    rows = []
    for i, (tk, tk_events) in enumerate(by_ticker.items(), 1):
        try:
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
        close_map = {ts.strftime("%Y-%m-%d"): float(c)
                     for ts, c in df["Close"].items()}
        date_keys = sorted(close_map.keys())

        def closest_at_or_after(target: str):
            for d_str in date_keys:
                if d_str >= target:
                    return d_str, close_map[d_str]
            return None, None

        for e in tk_events:
            _, fd0_px = closest_at_or_after(e["filing_date"])
            if not fd0_px or fd0_px <= 0:
                continue
            for nd in args.forward_days:
                target = (datetime.strptime(e["filing_date"][:10], "%Y-%m-%d")
                          + timedelta(days=int(nd * 1.45))).strftime("%Y-%m-%d")
                _, fd_t_px = closest_at_or_after(target)
                if not fd_t_px:
                    continue
                ret = (fd_t_px / fd0_px - 1.0) * 100
                spy_t0 = spy_closest(e["filing_date"])
                spy_t = spy_closest(target)
                spy_ret = ((spy_t / spy_t0 - 1.0) * 100
                           if spy_t0 and spy_t and spy_t0 > 0 else None)
                excess = (round(ret - spy_ret, 2)
                          if spy_ret is not None else None)
                row = {
                    **e,
                    "forward_days": nd,
                    "return_pct": round(ret, 2),
                    "spy_return_pct": round(spy_ret, 2) if spy_ret is not None else None,
                    "excess_return_pct": excess,
                }
                rows.append(row)
        if i % 25 == 0:
            print(f"  [{i}/{len(by_ticker)}] tickers", flush=True)
        time.sleep(args.sleep)

    with open(args.csv, "w", newline="") as f:
        fields = ["ticker", "filing_date", "action", "plan_type", "role",
                  "neo", "shares", "role_tier", "size_tier", "age_bucket",
                  "bucket", "forward_days", "return_pct",
                  "spy_return_pct", "excess_return_pct"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Stratify and summarize
    summary = {"by_bucket": {}, "by_role_tier": {}, "by_size_tier": {},
               "by_age_bucket": {}, "by_bucket_x_role": {}}
    for nd in args.forward_days:
        nd_rows = [r for r in rows if r["forward_days"] == nd]
        for bucket in ("term_sell", "adopt_sell", "term_buy", "adopt_buy"):
            br = [r for r in nd_rows if r["bucket"] == bucket]
            s = summarize(br)
            if s:
                summary["by_bucket"].setdefault(f"{nd}d", {})[bucket] = s
        for rt in ("CEO_or_Chair", "CFO", "Other"):
            for bucket in ("term_sell", "adopt_sell"):
                br = [r for r in nd_rows
                      if r["role_tier"] == rt and r["bucket"] == bucket]
                s = summarize(br)
                if s:
                    summary["by_bucket_x_role"].setdefault(
                        f"{nd}d", {}).setdefault(rt, {})[bucket] = s
        for st in ("ge_250k", "50k_to_250k", "lt_50k", "unknown"):
            for bucket in ("term_sell", "adopt_sell"):
                br = [r for r in nd_rows
                      if r["size_tier"] == st and r["bucket"] == bucket]
                s = summarize(br)
                if s:
                    summary["by_size_tier"].setdefault(
                        f"{nd}d", {}).setdefault(st, {})[bucket] = s
        for ab in ("2025_H1", "2025_H2", "2026_H1"):
            for bucket in ("term_sell", "adopt_sell"):
                br = [r for r in nd_rows
                      if r["age_bucket"] == ab and r["bucket"] == bucket]
                s = summarize(br)
                if s:
                    summary["by_age_bucket"].setdefault(
                        f"{nd}d", {}).setdefault(ab, {})[bucket] = s

    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {args.csv} ({len(rows)} rows) + {args.summary}\n")

    # Print key results at 180d
    print(f"\n=== BUCKET x ROLE TIER, 180d horizon ===")
    print(f"{'role_tier':<14}{'bucket':<12}{'n':>5}{'mean%':>8}"
          f"{'med%':>8}{'ex_mean%':>10}{'ex_med%':>10}{'beat%':>7}")
    print("-" * 75)
    bxr_180 = summary["by_bucket_x_role"].get("180d", {})
    for rt in ("CEO_or_Chair", "CFO", "Other"):
        for bucket in ("term_sell", "adopt_sell"):
            s = bxr_180.get(rt, {}).get(bucket)
            if not s:
                continue
            ex_m = f"{s.get('mean_excess_pct', 0):>9.2f}" if s.get('mean_excess_pct') is not None else "        ?"
            ex_med = f"{s.get('median_excess_pct', 0):>9.2f}" if s.get('median_excess_pct') is not None else "        ?"
            beat = f"{s.get('beat_spy_rate_pct', 0):>6.1f}" if s.get('beat_spy_rate_pct') is not None else "     ?"
            print(f"{rt:<14}{bucket:<12}{s['n']:>5}{s['mean_return_pct']:>8.2f}"
                  f"{s['median_return_pct']:>8.2f}{ex_m}{ex_med}{beat}")

    print(f"\n=== BUCKET x SIZE TIER, 180d horizon ===")
    print(f"{'size_tier':<14}{'bucket':<12}{'n':>5}{'mean%':>8}"
          f"{'med%':>8}{'ex_mean%':>10}{'ex_med%':>10}{'beat%':>7}")
    print("-" * 75)
    bxs_180 = summary["by_size_tier"].get("180d", {})
    for st in ("ge_250k", "50k_to_250k", "lt_50k", "unknown"):
        for bucket in ("term_sell", "adopt_sell"):
            s = bxs_180.get(st, {}).get(bucket)
            if not s:
                continue
            ex_m = f"{s.get('mean_excess_pct', 0):>9.2f}" if s.get('mean_excess_pct') is not None else "        ?"
            ex_med = f"{s.get('median_excess_pct', 0):>9.2f}" if s.get('median_excess_pct') is not None else "        ?"
            beat = f"{s.get('beat_spy_rate_pct', 0):>6.1f}" if s.get('beat_spy_rate_pct') is not None else "     ?"
            print(f"{st:<14}{bucket:<12}{s['n']:>5}{s['mean_return_pct']:>8.2f}"
                  f"{s['median_return_pct']:>8.2f}{ex_m}{ex_med}{beat}")

    print(f"\n=== BUCKET x AGE, 180d horizon ===")
    print(f"{'age':<10}{'bucket':<12}{'n':>5}{'mean%':>8}"
          f"{'med%':>8}{'ex_mean%':>10}{'ex_med%':>10}{'beat%':>7}")
    print("-" * 75)
    bxa_180 = summary["by_age_bucket"].get("180d", {})
    for ab in ("2025_H1", "2025_H2", "2026_H1"):
        for bucket in ("term_sell", "adopt_sell"):
            s = bxa_180.get(ab, {}).get(bucket)
            if not s:
                continue
            ex_m = f"{s.get('mean_excess_pct', 0):>9.2f}" if s.get('mean_excess_pct') is not None else "        ?"
            ex_med = f"{s.get('median_excess_pct', 0):>9.2f}" if s.get('median_excess_pct') is not None else "        ?"
            beat = f"{s.get('beat_spy_rate_pct', 0):>6.1f}" if s.get('beat_spy_rate_pct') is not None else "     ?"
            print(f"{ab:<10}{bucket:<12}{s['n']:>5}{s['mean_return_pct']:>8.2f}"
                  f"{s['median_return_pct']:>8.2f}{ex_m}{ex_med}{beat}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
