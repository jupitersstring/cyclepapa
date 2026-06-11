"""Buyback verification: did the share count actually fall?

The step-change layer scores buyback AUTHORIZATIONS from filing text,
but an authorization is a press release until shares are retired. This
module pulls the diluted share-count time series from yfinance
(`get_shares_full`) and computes the realized change, then classifies:

  EXECUTING    count fell >= 1.5% over the trailing 2 quarters
  TOKEN        fell, but < 1.5% (likely offsetting SBC only)
  DILUTING     count ROSE despite an announced buyback (red flag --
               authorization is cover for issuance)
  NO_AUTH      no buyback authorization on record (informational)

Signal points (applied in unified_composite):
  EXECUTING  +8   authorization is real, supply shrinking
  TOKEN       0
  DILUTING  -10   says-buyback-does-dilution divergence

Universe: tickers with a buyback_authorisation_musd in any detail JSON,
plus the unified composite top names. Output buyback_verify.json
(resumable) + summary CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "buyback_verify.json"
OUT_CSV = ROOT / "buyback_verify.csv"

DETAIL_SOURCES = [
    "v2_detail.json", "wide180_detail.json", "wide365_detail.json",
    "induce_detail.json", "restruct_v10.json", "missing_v10.json",
    "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json",
    "spinoffs_detail.json",
]


def collect_buyback_universe() -> dict[str, dict]:
    """ticker -> {auth_musd, auth_date} for names with an authorization."""
    out: dict[str, dict] = {}
    for fn in DETAIL_SOURCES:
        p = ROOT / fn
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for r in data:
            tk = (r.get("ticker") or "").upper()
            amt = r.get("buyback_authorisation_musd")
            if not tk or not amt:
                continue
            cur = out.get(tk)
            fd = r.get("filing_date") or ""
            if not cur or fd > (cur.get("auth_date") or ""):
                out[tk] = {"auth_musd": float(amt), "auth_date": fd}
    return out


def share_count_change(yf, ticker: str,
                       lookback_days: int = 200) -> dict | None:
    """Realized diluted share-count change over the trailing window,
    SPLIT-ADJUSTED. Raw get_shares_full counts jump by the split
    factor on split dates (TPL 3:1 showed +197%; reverse splits show
    -90%+). We divide the end count by the cumulative split ratio
    inside the window so only true issuance/retirement remains."""
    try:
        t = yf.Ticker(ticker)
        start_dt = (datetime.now(timezone.utc)
                    - timedelta(days=lookback_days + 30))
        s = t.get_shares_full(start=start_dt.strftime("%Y-%m-%d"))
    except Exception:
        return None
    if s is None or len(s) < 2:
        return None
    s = s.dropna()
    if len(s) < 2:
        return None
    first = float(s.iloc[0])
    last = float(s.iloc[-1])
    if first <= 0:
        return None

    # Cumulative split factor between the first and last observation
    split_factor = 1.0
    try:
        splits = t.splits
        if splits is not None and len(splits):
            t0 = s.index[0]
            t1 = s.index[-1]
            for ts, ratio in splits.items():
                ts_naive = ts.tz_localize(None) if ts.tzinfo else ts
                t0n = t0.tz_localize(None) if t0.tzinfo else t0
                t1n = t1.tz_localize(None) if t1.tzinfo else t1
                if t0n < ts_naive <= t1n and ratio and ratio > 0:
                    split_factor *= float(ratio)
    except Exception:
        pass

    adj_last = last / split_factor
    span_days = (s.index[-1] - s.index[0]).days or 1
    change_pct = round((adj_last / first - 1.0) * 100, 2)
    return {
        "shares_start": first,
        "shares_end": last,
        "split_factor": split_factor,
        "shares_end_adj": adj_last,
        "change_pct": change_pct,
        "span_days": span_days,
        "first_date": s.index[0].strftime("%Y-%m-%d"),
        "last_date": s.index[-1].strftime("%Y-%m-%d"),
        # Residual sanity flag: even after split adjustment, >30% moves
        # are usually M&A share issuance or data error, not buybacks.
        "large_residual": abs(change_pct) > 30,
    }


def classify_buyback(chg: dict | None,
                     has_auth: bool) -> tuple[str, int]:
    if not chg or chg.get("change_pct") is None:
        return "UNKNOWN", 0
    change_pct = chg["change_pct"]
    # After split adjustment, residual >30% moves are usually M&A share
    # issuance, ATM offerings at scale, or bad data -- score 0 and flag
    # for manual review rather than ±points on unreliable input.
    if chg.get("large_residual"):
        return "ANOMALY_REVIEW", 0
    if not has_auth:
        if change_pct <= -1.5:
            return "SHRINKING_NO_AUTH", 5
        return "NO_AUTH", 0
    if change_pct <= -1.5:
        return "EXECUTING", 8
    if change_pct < 0.5:
        return "TOKEN", 0
    return "DILUTING", -10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.30)
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--also-composite-top", type=int, default=100,
                    help="Also verify the top N unified-composite names "
                         "even without a recorded authorization.")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr)
        return 1

    universe = collect_buyback_universe()
    print(f"{len(universe)} tickers with recorded buyback authorizations",
          file=sys.stderr)

    comp = ROOT / "unified_composite.csv"
    if comp.exists():
        for i, r in enumerate(csv.DictReader(open(comp))):
            if i >= args.also_composite_top:
                break
            tk = r["ticker"].upper()
            universe.setdefault(tk, {"auth_musd": None, "auth_date": None})

    out: dict = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}

    n_done = 0
    for i, (tk, meta) in enumerate(sorted(universe.items()), 1):
        if i > args.limit:
            break
        if tk in out and out[tk].get("_complete"):
            continue
        chg = share_count_change(yf, tk)
        has_auth = bool(meta.get("auth_musd"))
        status, points = classify_buyback(chg, has_auth)
        out[tk] = {
            "ticker": tk,
            "auth_musd": meta.get("auth_musd"),
            "auth_date": meta.get("auth_date"),
            "share_change": chg,
            "status": status,
            "points": points,
            "_complete": True,
        }
        n_done += 1
        time.sleep(args.sleep)
        if n_done % 25 == 0:
            tmp = OUT_JSON.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2, default=str))
            tmp.replace(OUT_JSON)
            print(f"  [{i}/{len(universe)}] verified={n_done}", flush=True)

    tmp = OUT_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str))
    tmp.replace(OUT_JSON)

    rows = []
    for tk, v in out.items():
        chg = v.get("share_change") or {}
        rows.append({
            "ticker": tk,
            "status": v.get("status"),
            "points": v.get("points"),
            "auth_musd": v.get("auth_musd"),
            "change_pct": chg.get("change_pct"),
            "span_days": chg.get("span_days"),
        })
    rows.sort(key=lambda r: (r["points"] or 0))
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "status", "points",
                                           "auth_musd", "change_pct",
                                           "span_days"])
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    dist = Counter(r["status"] for r in rows)
    print(f"\nWrote {OUT_CSV} + {OUT_JSON} ({len(rows)} tickers)")
    print(f"Status distribution: {dict(dist)}\n")
    print("=== DILUTING (says buyback, does dilution) ===")
    for r in rows:
        if r["status"] == "DILUTING":
            print(f"  {r['ticker']:<8} auth=${r['auth_musd'] or 0:.0f}M "
                  f"shares {r['change_pct']:+.1f}% over {r['span_days']}d")
    print("\n=== EXECUTING (top 20 by shrinkage) ===")
    ex = sorted([r for r in rows if r["status"] in
                 ("EXECUTING", "SHRINKING_NO_AUTH")],
                key=lambda r: r["change_pct"] or 0)
    for r in ex[:20]:
        print(f"  {r['ticker']:<8} auth=${r['auth_musd'] or 0:.0f}M "
              f"shares {r['change_pct']:+.1f}% over {r['span_days']}d "
              f"[{r['status']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
