"""Aggressive buyback + price-flat detector.

Finds companies that have:
  (a) authorised / are executing a meaningful buyback (>5% of mcap)
  (b) recent 90-day price return is near zero or negative -- so the
      buyback supply is being absorbed without lifting the price

The intuition: if a company is buying back X% of its float and the
price hasn't moved, either:
  - someone is selling alongside (institutional rebalancing,
    deferred-tax-loss harvesting, forced sellers like IHT-AIM
    holders) AND the buyback is the only natural buyer
  - the buyback per share is genuinely accretive but the market
    hasn't yet priced it
Either way, the company is acquiring its own shares cheaply and
the eventual squeeze higher is mechanical when supply abates.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import yfinance as yf

from universe_filter import is_excluded


def load_buyback_signals() -> dict[str, dict]:
    """Pull buyback authorisation $ from all our cached scoring runs."""
    out: dict[str, dict] = {}
    for fn in ("v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "restruct_v10.json", "induce_detail.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json"):
        p = Path(fn)
        if not p.exists():
            continue
        try:
            for r in json.loads(p.read_text()):
                if r.get("error"):
                    continue
                tk = r.get("ticker")
                amt = r.get("buyback_authorisation_musd")
                if not tk or not amt:
                    continue
                cur = out.get(tk)
                if cur is None or amt > (cur.get("buyback_musd") or 0):
                    out[tk] = {
                        "ticker": tk,
                        "company": r.get("company"),
                        "buyback_musd": amt,
                        "market_cap": r.get("market_cap"),
                        "filing_date": r.get("filing_date"),
                        "filing_url": r.get("filing_url"),
                    }
        except Exception:
            pass
    return out


def price_history(ticker: str) -> dict | None:
    """Compute 30d / 90d / 180d returns + drawdown via yfinance."""
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="1y", interval="1d", auto_adjust=False)
        if h is None or len(h) < 30:
            return None
    except Exception:
        return None
    h = h.dropna(subset=["Close"])
    if len(h) < 30:
        return None
    last = float(h["Close"].iloc[-1])
    def _ret(days):
        if len(h) <= days:
            return None
        prior = float(h["Close"].iloc[-days])
        return (last / prior - 1.0) * 100 if prior > 0 else None
    high_90 = float(h["High"].iloc[-90:].max()) if len(h) >= 90 else None
    low_90 = float(h["Low"].iloc[-90:].min()) if len(h) >= 90 else None
    high_1y = float(h["High"].max())
    low_1y = float(h["Low"].min())
    return {
        "last": last,
        "ret_30d_pct": _ret(30),
        "ret_60d_pct": _ret(60),
        "ret_90d_pct": _ret(90),
        "ret_180d_pct": _ret(180),
        "high_90d": high_90,
        "low_90d": low_90,
        "drawdown_from_1y_high_pct": (last / high_1y - 1.0) * 100 if high_1y > 0 else None,
        "pos_in_1y_range_pct": ((last - low_1y) / (high_1y - low_1y)) * 100 if high_1y > low_1y else 50,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--min-buyback-pct", type=float, default=5.0,
                   help="Min buyback authorisation as %% of mcap.")
    p.add_argument("--max-90d-return", type=float, default=10.0,
                   help="Max 90-day return %% (price-flat filter).")
    p.add_argument("--out", default="buyback_flat.csv")
    p.add_argument("--sleep", type=float, default=0.30)
    args = p.parse_args()

    signals = load_buyback_signals()
    print(f"Loaded {len(signals)} tickers with buyback authorisations",
          file=sys.stderr)

    rows = []
    for i, (tk, sig) in enumerate(signals.items(), 1):
        bad, _ = is_excluded(tk, sig.get("company"))
        if bad:
            continue
        mc = sig.get("market_cap")
        bb = sig.get("buyback_musd") or 0
        if not mc or mc <= 0:
            continue
        bb_pct = (bb * 1e6) / mc * 100
        if bb_pct < args.min_buyback_pct:
            continue
        ph = price_history(tk)
        if i % 20 == 0:
            print(f"  [{i}/{len(signals)}] processed", file=sys.stderr,
                  flush=True)
        time.sleep(args.sleep)
        if not ph:
            continue
        # Price-flat filter: 90d return below threshold (could be negative)
        ret90 = ph.get("ret_90d_pct")
        if ret90 is None or ret90 > args.max_90d_return:
            continue

        # Score: higher buyback %, more negative 90d return = better
        score = bb_pct - (ret90 or 0)
        rows.append({
            "ticker": tk,
            "company": sig.get("company"),
            "current_price": ph["last"],
            "market_cap_musd": round(mc / 1e6, 1),
            "buyback_musd": bb,
            "buyback_pct_mcap": round(bb_pct, 1),
            "ret_30d_pct": ph.get("ret_30d_pct"),
            "ret_60d_pct": ph.get("ret_60d_pct"),
            "ret_90d_pct": ret90,
            "ret_180d_pct": ph.get("ret_180d_pct"),
            "pos_in_1y_range_pct": ph.get("pos_in_1y_range_pct"),
            "drawdown_from_1y_high_pct": ph.get("drawdown_from_1y_high_pct"),
            "score": round(score, 1),
            "filing_url": sig.get("filing_url"),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "buyback_musd", "buyback_pct_mcap",
              "ret_30d_pct", "ret_60d_pct", "ret_90d_pct", "ret_180d_pct",
              "pos_in_1y_range_pct", "drawdown_from_1y_high_pct",
              "score", "filing_url"]
    with Path(args.out).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\n=== Buyback >= {args.min_buyback_pct}% + 90d ret <= {args.max_90d_return}% ===")
    print(f"Eligible: {len(rows)}\n")
    print(f"{'#':<3}{'TKR':<10}{'PX':>9}{'MCAP':>8}{'BB$':>9}{'BB%':>5}"
          f"{'30d':>7}{'90d':>7}{'180d':>7}  COMPANY")
    for i, r in enumerate(rows[: args.top], 1):
        mc = r["market_cap_musd"]
        bb = r["buyback_musd"]
        co = (r.get("company") or "")[:38]
        d30 = r.get("ret_30d_pct"); d90 = r.get("ret_90d_pct"); d180 = r.get("ret_180d_pct")
        print(f"{i:<3}{r['ticker']:<10}{r['current_price']:>9.2f}"
              f"{mc:>7.0f}M{bb:>8.0f}M{r['buyback_pct_mcap']:>5.0f}%"
              f"{d30 or 0:>6.1f}%{d90:>6.1f}%{d180 or 0:>6.1f}%  {co}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
