"""Rich Howe "40% volume rule" spinoff entry timer.

The signal: post-distribution, forced selling exhausts when
cumulative trading volume reaches 40-50% of shares outstanding
(typically ~9 trading days). Entry then captures the rebound as
forced sellers are done and natural holders take over.

This module:
  1. Loads the Form 10 spinoff registrations (from
     special_situations_unified.csv kind=FORM_10_SPINOFF) and any
     other recently-traded spinoff candidates.
  2. For each child ticker, fetches daily volume from yfinance and
     compares cumulative volume to a shares-outstanding estimate.
  3. Flags tickers near the 40-50% threshold as ENTRY candidates;
     flags those past 80% as POST-EXHAUSTION (forced sellers done).

Output: spinoff_volume_timer.json
  {ticker: {distribution_date, shares_out_est, cum_vol_M, pct_of_shares,
            status, score}}
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "spinoff_volume_timer.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr)
        return 1

    # Sources of spinoff candidates
    candidates = {}   # ticker -> filing_date

    # 1. From special_situations_unified.csv (Form 10 hits)
    ss = ROOT / "special_situations_unified.csv"
    if ss.exists():
        for r in csv.DictReader(ss.open()):
            if r.get("kind") == "FORM_10_SPINOFF":
                tk = r.get("ticker", "").upper()
                if tk and not tk.startswith("CIK"):
                    fd = r.get("filing_date", "")
                    if tk not in candidates or fd > candidates[tk]:
                        candidates[tk] = fd

    # 2. From recent_incentive_asymmetry_120d.csv for FORM_10 kind
    for fn in ("recent_incentive_asymmetry_120d.csv",
                "recent_incentive_asymmetry.csv"):
        p = ROOT / fn
        if not p.exists():
            continue
        for r in csv.DictReader(p.open()):
            if r.get("latest_event_kind") == "FORM_10_SPINOFF":
                tk = r.get("ticker", "").upper()
                if tk and not tk.startswith("CIK"):
                    # BUGFIX (silent-drop audit): unconditional assignment
                    # let this source clobber a valid Form-10 date from
                    # source-1 with a possibly-empty date. Keep the
                    # latest non-empty date, mirroring source-1's guard.
                    fd = r.get("latest_event_date") or ""
                    if fd and (tk not in candidates or fd > candidates[tk]):
                        candidates[tk] = fd
                    elif tk not in candidates:
                        candidates[tk] = fd

    print(f"Candidate spinoff tickers: {len(candidates)}", file=sys.stderr)

    today = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = today - timedelta(days=args.days)

    out = {}
    n_processed = 0
    for tk, fd in candidates.items():
        # METHODOLOGY FIX (audit finding A7): `fd` is the Form 10
        # FILING date, not the distribution date -- distribution
        # typically follows registration by 3-6 months. The old code
        # labeled pre-listing names EARLY_FORCED_SELLING. We now
        # derive the true first-trade date from the first session with
        # non-zero volume; if none exists yet, the name is
        # PRE_DISTRIBUTION (registered, not yet trading).
        try:
            reg_dt = datetime.strptime(fd[:10], "%Y-%m-%d")
        except Exception:
            continue
        if reg_dt < cutoff:
            continue

        # Fetch daily volume + shares outstanding
        try:
            t = yf.Ticker(tk)
            info = t.info or {}
            so = info.get("sharesOutstanding") or info.get("floatShares")
            if not so:
                continue
            hist = t.history(start=reg_dt.strftime("%Y-%m-%d"),
                              end=today.strftime("%Y-%m-%d"))
        except Exception:
            continue

        first_trade_dt = None
        cum_vol = 0
        if hist is not None and len(hist) > 0:
            traded = hist[hist["Volume"] > 0]
            if len(traded) > 0:
                first_trade_dt = traded.index[0].to_pydatetime()\
                    .replace(tzinfo=None)
                cum_vol = int(traded["Volume"].sum())

        if first_trade_dt is None:
            out[tk] = {
                "registration_date": fd[:10],
                "distribution_date": None,
                "first_trade_date": None,
                "days_since_first_trade": None,
                "shares_out_est": so,
                "cum_volume": 0,
                "pct_of_shares": 0.0,
                "status": "PRE_DISTRIBUTION",
                "score": 0,
            }
            n_processed += 1
            time.sleep(args.sleep)
            continue

        pct_of_shares = cum_vol / so * 100 if so else 0
        days_since = (today - first_trade_dt).days

        if pct_of_shares < 20:
            status = "EARLY_FORCED_SELLING"
            score = 0
        elif 20 <= pct_of_shares < 40:
            status = "APPROACHING_EXHAUSTION"
            score = 15
        elif 40 <= pct_of_shares < 55:
            status = "ENTRY_ZONE"   # Howe 40-50% sweet spot
            score = 30
        elif 55 <= pct_of_shares < 80:
            status = "POST_ENTRY_HOLDING"
            score = 18
        elif pct_of_shares < 150:
            status = "POST_EXHAUSTION"  # forced sellers done
            score = 10
        else:
            status = "OLD_SPIN"   # liquid, signal gone
            score = 0

        out[tk] = {
            "registration_date": fd[:10],
            # kept for backward compatibility; now the true first-trade
            # date rather than the Form 10 filing date
            "distribution_date": first_trade_dt.strftime("%Y-%m-%d"),
            "first_trade_date": first_trade_dt.strftime("%Y-%m-%d"),
            "days_since_first_trade": days_since,
            "days_since_distribution": days_since,
            "shares_out_est": so,
            "cum_volume": cum_vol,
            "pct_of_shares": round(pct_of_shares, 1),
            "status": status,
            "score": score,
        }
        n_processed += 1
        time.sleep(args.sleep)
        if n_processed % 10 == 0:
            print(f"  processed {n_processed}/{len(candidates)}",
                  file=sys.stderr, flush=True)

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)})")

    from collections import Counter
    dist = Counter(v["status"] for v in out.values())
    print(f"\nStatus distribution:")
    for s, n in dist.most_common():
        print(f"  {s:<25} {n}")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 15 spinoff-volume-timer ===")
    for tk, v in ranked[:15]:
        print(f"  {tk:<7} {v['status']:<22} "
              f"pct={v['pct_of_shares']:>6.1f}% "
              f"days={v['days_since_distribution']:<3} score={v['score']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
