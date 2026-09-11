"""Accumulation Scanner -- find RSE-style pre-news setups.

The RSE pattern:
  1. Closed-end fund / investment trust / activist target / managed-
     wind-down vehicle
  2. Long flat base at a deep discount to NAV / book / spin-off value
  3. Recent weekly volume spike vs the 13-week trailing baseline
  4. Price clinging near the volume Point-of-Control of the base
  5. Optional MFI green (money-flow accumulation)

This module pulls weekly OHLCV via yfinance for the merged universe and
flags names where:
  - latest_week_volume / avg_13w_volume >= 3.0  (volume spike)
  - latest_close within 20% of the 6m low      (still basing)
  - 6m volatility < some threshold              (flat base, not chasing)
  - Bonus for managed-wind-down / realisation language in RNS or proxy
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from universe_filter import is_excluded


WIND_DOWN_KEYWORDS = re.compile(
    r"\b("
    r"managed wind[- ]?down|orderly wind[- ]?down|"
    r"realisation portfolio|realization portfolio|"
    r"orderly (disposal|realisation|realization|liquidation)|"
    r"return of capital programme|"
    r"wind[- ]?down vote|continuation vote|"
    r"discontinuation resolution|"
    r"strategy review|"
    r"liquidation preference|"
    r"compulsory redemption|"
    r"matched bargain|"
    r"trust (in )?(managed wind[- ]?down|wind[- ]?down)|"
    r"intent to wind up|"
    r"voluntary liquidation"
    r")\b",
    re.I,
)


def collect_universe() -> list[str]:
    sources = [
        "uk_v2_detail.json", "intl_detail.json",
        "yfinance_enrichment.json",
        "v2_detail.json", "wide180_detail.json", "wide365_detail.json",
        "induce_detail.json", "restruct_v10.json", "restruct_v7.json",
        "targets_v4.json", "missing_v8.json", "missing_v10.json",
    ]
    out: set[str] = set()
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                # yfinance_enrichment / enrichment_overlay are keyed by ticker
                out.update(data.keys())
            else:
                for r in data:
                    tk = r.get("ticker")
                    if tk:
                        out.add(tk.upper())
        except Exception:
            pass
    # Also include curated wind-down trust universe + broader roster
    try:
        from wind_down_trusts import WIND_DOWN_UNIVERSE
        out.update(WIND_DOWN_UNIVERSE.keys())
    except Exception:
        pass
    try:
        from broader_universe import fresh_universe
        out.update(fresh_universe())
    except Exception:
        pass
    return sorted(out)


def scan_one(ticker: str) -> dict | None:
    """Returns dict of accumulation features, or None on failure."""
    try:
        t = yf.Ticker(ticker)
        # Pull 1y of weekly bars
        h = t.history(period="2y", interval="1wk", auto_adjust=False)
        if h is None or len(h) < 20:
            return None
    except Exception:
        return None

    h = h.dropna(subset=["Close", "Volume"])
    if len(h) < 20:
        return None

    last = h.iloc[-1]
    last_close = float(last["Close"])
    last_volume = float(last["Volume"])

    # Volume baseline (excluding latest 4 weeks so the spike doesn't
    # contaminate the baseline)
    if len(h) < 26:
        return None
    baseline = h.iloc[-26:-4]
    avg_baseline_vol = float(baseline["Volume"].mean())
    if avg_baseline_vol <= 0:
        return None
    vol_spike = last_volume / avg_baseline_vol

    # Recent 4w max volume vs baseline (catches very recent spikes)
    recent4 = h.iloc[-4:]
    max_recent_vol = float(recent4["Volume"].max())
    max_spike = max_recent_vol / avg_baseline_vol

    # 6-month range
    last26 = h.iloc[-26:]
    low_6m = float(last26["Low"].min())
    high_6m = float(last26["High"].max())
    pos_in_range = (
        (last_close - low_6m) / (high_6m - low_6m)
        if high_6m > low_6m else 0.5
    )

    # Volatility (last 13w std as % of mean)
    last13 = h.iloc[-13:]
    if len(last13) >= 5 and float(last13["Close"].mean()) > 0:
        volatility = float(last13["Close"].std()) / float(last13["Close"].mean())
    else:
        volatility = 0.0

    # Distance from 6m low (% above the low)
    above_low = (last_close - low_6m) / low_6m if low_6m > 0 else 0

    # Money Flow Index (14-period weekly, simplified)
    if len(h) >= 15:
        # typical price
        tp = (h["High"] + h["Low"] + h["Close"]) / 3
        mf = tp * h["Volume"]
        gain_mf = mf.diff().where(mf.diff() > 0, 0).rolling(14).sum()
        loss_mf = (-mf.diff()).where(mf.diff() < 0, 0).rolling(14).sum()
        if loss_mf.iloc[-1] > 0:
            mfi = 100 - (100 / (1 + gain_mf.iloc[-1] / loss_mf.iloc[-1]))
            mfi = float(mfi)
        else:
            mfi = 100.0
    else:
        mfi = 50.0

    return {
        "ticker": ticker,
        "last_close": round(last_close, 4),
        "last_volume": int(last_volume),
        "avg_baseline_vol": int(avg_baseline_vol),
        "vol_spike": round(vol_spike, 2),
        "max_4w_spike": round(max_spike, 2),
        "low_6m": round(low_6m, 4),
        "high_6m": round(high_6m, 4),
        "pos_in_6m_range": round(pos_in_range, 3),
        "above_low_pct": round(above_low * 100, 1),
        "volatility_13w": round(volatility, 3),
        "mfi": round(mfi, 1),
    }


def score_accumulation(f: dict, has_wind_down: bool = False) -> tuple[int, list[str]]:
    """0-100 accumulation score.
       - High volume spike (vs trailing 13w) => up to 40
       - Near 6m low (pos_in_6m_range <= 0.30) => up to 25
       - Low volatility (flat base) => up to 15
       - MFI green (>=50) => up to 10
       - Managed wind-down language => up to 10
    """
    score = 0.0
    reasons: list[str] = []

    spike = max(f["vol_spike"], f["max_4w_spike"])
    if spike >= 5.0:
        score += 40; reasons.append(f"vol spike {spike:.1f}x baseline")
    elif spike >= 3.0:
        score += 30; reasons.append(f"vol spike {spike:.1f}x baseline")
    elif spike >= 2.0:
        score += 15; reasons.append(f"mild vol spike {spike:.1f}x")

    pos = f["pos_in_6m_range"]
    if pos <= 0.20:
        score += 25; reasons.append(f"near 6m low ({pos:.0%} of range)")
    elif pos <= 0.40:
        score += 15; reasons.append(f"low-third of 6m range ({pos:.0%})")
    elif pos <= 0.60:
        score += 5

    vol = f["volatility_13w"]
    if vol <= 0.05:
        score += 15; reasons.append(f"flat base (vol {vol:.1%})")
    elif vol <= 0.10:
        score += 10
    elif vol <= 0.20:
        score += 5

    mfi = f["mfi"]
    if mfi >= 60:
        score += 10; reasons.append(f"MFI green ({mfi:.0f})")
    elif mfi >= 50:
        score += 5

    if has_wind_down:
        score += 10; reasons.append("Managed wind-down language detected")

    return int(round(min(100, score))), reasons


def load_wind_down_overlay() -> set[str]:
    """Tickers with managed-wind-down language in RNS or any cached
    detail JSON."""
    out: set[str] = set()
    rns_path = Path("uk_rns_overlay.json")
    if rns_path.exists():
        try:
            data = json.loads(rns_path.read_text())
            for tk, d in data.items():
                titles = d.get("news_titles") or []
                if any(WIND_DOWN_KEYWORDS.search(t) for t in titles):
                    out.add(tk.upper())
        except Exception:
            pass
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="accumulation_scan.json")
    p.add_argument("--csv", default="accumulation_scan.csv")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--region", choices=["US", "UK", "INTL", "ALL"], default="ALL")
    p.add_argument("--sleep", type=float, default=0.20)
    p.add_argument("--min-spike", type=float, default=2.0,
                   help="Min vol spike vs baseline to keep in output.")
    p.add_argument("--max-pos", type=float, default=0.50,
                   help="Max pos_in_6m_range to keep (0.30 = lower third).")
    p.add_argument("--limit", type=int, default=10000)
    args = p.parse_args()

    universe = collect_universe()
    # Region filter
    if args.region != "ALL":
        def matches(t):
            is_uk = t.endswith(".L")
            is_intl = any(t.endswith(s) for s in (".AX", ".TO", ".V", ".HK", ".SI",
                                                    ".T", ".DE", ".PA", ".MI", ".F"))
            is_us = "." not in t
            if args.region == "US": return is_us
            if args.region == "UK": return is_uk
            if args.region == "INTL": return is_intl
            return True
        universe = [t for t in universe if matches(t)]
    universe = [t for t in universe if not is_excluded(t)[0]]

    print(f"Scanning {len(universe)} tickers (region={args.region})",
          file=sys.stderr)

    wind_down_set = load_wind_down_overlay()

    out_path = Path(args.out)
    results: dict[str, dict] = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text())
        except Exception:
            results = {}

    for i, tk in enumerate(universe, 1):
        if i > args.limit:
            break
        if tk in results:
            continue
        f = scan_one(tk)
        if f is None:
            results[tk] = {"_error": "no data"}
        else:
            score, reasons = score_accumulation(f, has_wind_down=tk in wind_down_set)
            f["wind_down"] = tk in wind_down_set
            f["accumulation_score"] = score
            f["reasons"] = reasons
            results[tk] = f
        if i % 50 == 0:
            print(f"  [{i}/{len(universe)}] processed", file=sys.stderr,
                  flush=True)
            out_path.write_text(json.dumps(results, indent=2, default=str))
        time.sleep(args.sleep)
    out_path.write_text(json.dumps(results, indent=2, default=str))

    # Filter and sort
    rows = [r for r in results.values()
            if isinstance(r, dict)
            and not r.get("_error")
            and max(r.get("vol_spike", 0), r.get("max_4w_spike", 0)) >= args.min_spike
            and r.get("pos_in_6m_range", 1) <= args.max_pos]
    rows.sort(key=lambda r: r.get("accumulation_score", 0), reverse=True)

    if args.csv:
        import csv as _csv
        fields = ["rank", "ticker", "last_close", "vol_spike", "max_4w_spike",
                  "pos_in_6m_range", "above_low_pct", "volatility_13w", "mfi",
                  "wind_down", "accumulation_score", "reasons",
                  "low_6m", "high_6m", "last_volume", "avg_baseline_vol"]
        with Path(args.csv).open("w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for i, r in enumerate(rows[: args.top], 1):
                row = dict(r)
                row["rank"] = i
                row["reasons"] = " | ".join(r.get("reasons") or [])
                w.writerow(row)
        print(f"\nWrote ranked CSV to {args.csv}", file=sys.stderr)

    print(f"\n=== TOP {min(args.top, len(rows))} ACCUMULATION SETUPS ===\n",
          file=sys.stderr)
    print(f"{'#':<3}{'TKR':<11}{'PX':>9}{'SPIKE':>7}{'POS':>5}{'VOL':>5}{'MFI':>5}{'WD':>4}{'SCR':>5}  REASONS")
    for i, r in enumerate(rows[: args.top], 1):
        spike = max(r.get("vol_spike", 0), r.get("max_4w_spike", 0))
        print(f"{i:<3}{r['ticker']:<11}"
              f"{r['last_close']:>9.2f}"
              f"{spike:>7.1f}"
              f"{r['pos_in_6m_range']*100:>4.0f}%"
              f"{r['volatility_13w']*100:>4.0f}%"
              f"{r['mfi']:>5.0f}"
              f"{('Y' if r.get('wind_down') else ''):>4}"
              f"{r['accumulation_score']:>5}"
              f"  {' | '.join(r.get('reasons') or [])[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
