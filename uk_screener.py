"""UK systematic screener.

For each LSE/AIM ticker in uk_universe.UK_UNIVERSE:
  - pull yfinance fundamentals (price, mcap, P/B, dividend yield,
    52w range, FCF, EPS growth, ROE, debt/equity)
  - compute discount-to-book and discount-to-fair-value proxy
  - score sector tailwind from the user's archetype mapping
  - compose a UK-Munger asymmetry score

Output: ranked CSV + console table. Use top_picks-style filtering and
add `--top N` for shortlist.

This intentionally mirrors the US pipeline's *fundamentals-only* layer.
RNS event detection (special committee, sale process, RSA) would require
a separate scrape and is out of scope here -- the user's qualitative
picks from the message act as ground truth for spot-checking.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import yfinance as yf

import cache
from uk_universe import UK_UNIVERSE


# ---------------------------------------------------------------------------
# Sector tailwind weights (from the user's UK message)
# ---------------------------------------------------------------------------

SECTOR_TAILWIND = {
    "DEFENCE":   1.20,   # NATO 2%+ tailwind, BAE / Babcock / Chemring
    "ASSETMGR":  1.15,   # M&A at 1.5-3% AUM vs trading 0.5-1% AUM
    "MEDTECH":   1.10,   # AIM medtech monopoly pricing
    "ENERGY":    1.05,   # North Sea / windfall tax noise creating gaps
    "MARINE":    1.05,   # James Fisher SOTP
    "BUILD":     1.05,   # UK housing recovery cycle
    "OUTSOURCE": 1.00,
    "TECH":      1.00,
    "FIN":       1.00,
    "RETAIL":    0.95,
    "MEDIA":     0.95,
    "PROP":      0.95,
    "CONSUMER":  0.90,
    "INDUST":    1.00,
    "SPECIAL":   1.05,
}


def _safe(d: dict, k: str) -> float | None:
    v = d.get(k)
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


@cache_decorator := (lambda f: f)  # placeholder; cached via cache.get_price
def fetch_uk_fundamentals(ticker: str) -> dict:
    """Pull yfinance fundamentals. Returns {} on failure."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return {}
    if not info:
        return {}
    return {
        "name":        info.get("longName") or info.get("shortName"),
        "currency":    info.get("financialCurrency") or info.get("currency"),
        "price":       _safe(info, "currentPrice") or _safe(info, "regularMarketPrice") or _safe(info, "previousClose"),
        "market_cap":  _safe(info, "marketCap"),
        "p_b":         _safe(info, "priceToBook"),
        "p_s":         _safe(info, "priceToSalesTrailing12Months"),
        "ev_ebitda":   _safe(info, "enterpriseToEbitda"),
        "trailing_pe": _safe(info, "trailingPE"),
        "forward_pe":  _safe(info, "forwardPE"),
        "div_yield":   _safe(info, "dividendYield"),
        "payout":      _safe(info, "payoutRatio"),
        "fcf":         _safe(info, "freeCashflow"),
        "ebitda":      _safe(info, "ebitda"),
        "revenue":     _safe(info, "totalRevenue"),
        "roe":         _safe(info, "returnOnEquity"),
        "debt_eq":     _safe(info, "debtToEquity"),
        "rev_growth":  _safe(info, "revenueGrowth"),
        "earn_growth": _safe(info, "earningsGrowth"),
        "peg":         _safe(info, "pegRatio"),
        "fwk_low":     _safe(info, "fiftyTwoWeekLow"),
        "fwk_high":    _safe(info, "fiftyTwoWeekHigh"),
        "shares_out":  _safe(info, "sharesOutstanding"),
        "held_insid":  _safe(info, "heldPercentInsiders"),
        "held_inst":   _safe(info, "heldPercentInstitutions"),
    }


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _ratio_score(value: float | None, target: float, higher_is_better: bool = True) -> float:
    if value is None or value == 0:
        return 0.5
    s = value / target
    if not higher_is_better:
        s = 1.0 / s if s > 0 else 0.0
    return _clip01(s)


def score_uk(fund: dict, sector: str) -> dict:
    """Return UK Munger composite (0-100) plus sub-scores."""
    if not fund:
        return {"composite": 0, "valuation": 0, "income": 0, "quality": 0,
                "drawdown": 0, "tailwind": 1.0}

    # Valuation (lower P/B and lower P/E = higher score). UK historical
    # market average P/B ~1.7; below that earns marks.
    pb = fund.get("p_b")
    pb_score = _ratio_score(pb if pb else 5.0, target=1.0, higher_is_better=False)
    pe = fund.get("trailing_pe") or fund.get("forward_pe")
    pe_score = _ratio_score(pe if pe and pe > 0 else 30.0, target=10.0, higher_is_better=False)
    eve = fund.get("ev_ebitda")
    eve_score = _ratio_score(eve if eve and eve > 0 else 15.0, target=6.0, higher_is_better=False)
    valuation = 100.0 * (0.4 * pb_score + 0.4 * pe_score + 0.2 * eve_score)

    # Income (UK gilt is ~4.5%, so 6%+ yield is a real cushion).
    div = fund.get("div_yield") or 0
    income = 100.0 * _ratio_score(div, target=0.06, higher_is_better=True)

    # Quality (ROE + EPS growth).
    roe = fund.get("roe") or 0
    roe_score = _ratio_score(max(0, roe), target=0.15, higher_is_better=True)
    eg = fund.get("earn_growth") or 0
    eg_score = _ratio_score(max(0, eg), target=0.15, higher_is_better=True)
    quality = 100.0 * (0.6 * roe_score + 0.4 * eg_score)

    # Drawdown (closer to 52w low + further from high = bigger margin).
    px = fund.get("price")
    lo = fund.get("fwk_low")
    hi = fund.get("fwk_high")
    if px and lo and hi and hi > lo:
        pos = (px - lo) / (hi - lo)
        drawdown = 100.0 * (1.0 - _clip01(pos))
    else:
        drawdown = 50.0

    tailwind = SECTOR_TAILWIND.get(sector, 1.0)

    composite_raw = (
        0.35 * valuation
        + 0.25 * income
        + 0.20 * quality
        + 0.20 * drawdown
    )
    composite = round(composite_raw * tailwind, 1)
    return {
        "composite":  composite,
        "valuation":  round(valuation, 1),
        "income":     round(income, 1),
        "quality":    round(quality, 1),
        "drawdown":   round(drawdown, 1),
        "tailwind":   tailwind,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="uk_scorecard.csv")
    p.add_argument("--json", default="uk_detail.json")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--sleep", type=float, default=0.30)
    p.add_argument("--min-mcap-mgbp", type=float, default=50.0,
                   help="Minimum market cap in £M (default 50).")
    args = p.parse_args()

    rows: list[dict] = []
    items = list(UK_UNIVERSE.items())
    for i, (tk, meta) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {tk} {meta['name']}", file=sys.stderr, flush=True)
        try:
            fund = fetch_uk_fundamentals(tk)
        except Exception as e:
            fund = {}
            print(f"   error: {e}", file=sys.stderr)
        sc = score_uk(fund, meta["sector"])
        row = {
            "ticker": tk,
            "name": meta["name"],
            "sector": meta["sector"],
            "tag": meta.get("tag", ""),
            **fund,
            **sc,
        }
        rows.append(row)
        time.sleep(args.sleep)

    # Filter to actively-listed names with viable size.
    eligible = [r for r in rows if r.get("market_cap") and r["market_cap"] / 1e6 >= args.min_mcap_mgbp]
    eligible.sort(key=lambda r: r.get("composite") or 0, reverse=True)

    fields = [
        "ticker", "name", "sector", "tag", "currency",
        "price", "market_cap",
        "composite", "valuation", "income", "quality", "drawdown", "tailwind",
        "p_b", "p_s", "ev_ebitda", "trailing_pe", "forward_pe",
        "div_yield", "payout", "roe", "debt_eq", "rev_growth", "earn_growth",
        "fwk_low", "fwk_high",
    ]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in eligible:
            w.writerow({k: r.get(k) for k in fields})

    Path(args.json).write_text(json.dumps(rows, indent=2, default=str))

    print()
    print(f"=== TOP {args.top} UK NAMES (eligible {len(eligible)} of {len(rows)}) ===")
    print(f"{'TICKER':<9}{'COMP':>6}{'VAL':>5}{'INC':>5}{'QUA':>5}{'DD':>5}{'TW':>5}  "
          f"{'PRICE':>9}{'MCAP':>8}  SECTOR     NAME")
    for r in eligible[: args.top]:
        mc = (r.get("market_cap") or 0) / 1e6
        px = r.get("price") or 0
        cur = r.get("currency", "")
        print(f"{r['ticker']:<9}{r.get('composite') or 0:>6.1f}"
              f"{r.get('valuation') or 0:>5.0f}"
              f"{r.get('income') or 0:>5.0f}"
              f"{r.get('quality') or 0:>5.0f}"
              f"{r.get('drawdown') or 0:>5.0f}"
              f"{r.get('tailwind') or 1:>5.2f}  "
              f"{px:>8.2f}{cur[:1] if cur else ' ':<1}"
              f"{mc:>7.0f}M  "
              f"{r['sector']:<10} {r['name'][:40]}"
              f"{(' [' + r.get('tag', '') + ']') if r.get('tag') else ''}")

    print(f"\nWrote {args.out} ({len(eligible)} ranked rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
