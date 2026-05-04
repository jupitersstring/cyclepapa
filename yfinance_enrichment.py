"""yfinance enrichment overlay for the merged universe.

Adds these fields to every ticker we've already touched:
  - short_pct_float       % of float held short (yfinance shortPercentOfFloat)
  - short_ratio           days to cover
  - earnings_date_days    days until next earnings (negative if past)
  - analyst_count         numberOfAnalystOpinions (0-2 = neglected)
  - target_mean_pct       mean analyst target % vs current
  - drawdown_pct          (price - 52w_low) / (52w_high - 52w_low)
  - inst_pct, insider_pct beneficial-ownership tiers
  - sector, industry      sector tagging when missing

Output: yfinance_enrichment.json keyed by ticker. Resumable -- safe to
re-run after a partial completion.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from universe_filter import is_excluded


def collect_tickers() -> list[str]:
    sources = [
        "v2_detail.json", "wide180_detail.json",
        "induce_detail.json",
        "restruct_v10.json", "restruct_v7.json",
        "targets_v4.json", "missing_v8.json", "missing_v10.json",
        "uk_v2_detail.json",
    ]
    out: set[str] = set()
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            for r in json.loads(p.read_text()):
                tk = (r.get("ticker") or "").upper()
                if tk:
                    out.add(tk)
        except Exception:
            pass
    return sorted(out)


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


def fetch_one(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return {}
    if not info:
        return {}

    px = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice") or _safe(info, "previousClose")
    fwk_low = _safe(info, "fiftyTwoWeekLow")
    fwk_high = _safe(info, "fiftyTwoWeekHigh")
    drawdown_pct = None
    if px and fwk_high and fwk_high > 0:
        # 0% = at 52w low; 100% = at 52w high
        if fwk_low and fwk_high > fwk_low:
            drawdown_pct = round((px - fwk_low) / (fwk_high - fwk_low) * 100, 1)

    # Earnings date
    ed_days = None
    ed_ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    if ed_ts:
        try:
            ed_dt = datetime.fromtimestamp(int(ed_ts), tz=timezone.utc)
            ed_days = (ed_dt - datetime.now(timezone.utc)).days
        except Exception:
            pass

    target_mean = _safe(info, "targetMeanPrice")
    target_pct = None
    if target_mean and px and px > 0:
        target_pct = round((target_mean - px) / px * 100, 1)

    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": info.get("financialCurrency") or info.get("currency"),
        "price": px,
        "market_cap": _safe(info, "marketCap"),
        "fwk_low": fwk_low,
        "fwk_high": fwk_high,
        "drawdown_pct": drawdown_pct,
        "short_pct_float": _safe(info, "shortPercentOfFloat"),
        "short_ratio": _safe(info, "shortRatio"),
        "earnings_date_days": ed_days,
        "analyst_count": _safe(info, "numberOfAnalystOpinions"),
        "target_mean": target_mean,
        "target_mean_pct": target_pct,
        "recommendation": info.get("recommendationKey"),
        "inst_pct": _safe(info, "heldPercentInstitutions"),
        "insider_pct": _safe(info, "heldPercentInsiders"),
        "div_yield": _safe(info, "dividendYield"),
        "p_b": _safe(info, "priceToBook"),
        "p_s": _safe(info, "priceToSalesTrailing12Months"),
        "ev_ebitda": _safe(info, "enterpriseToEbitda"),
        "ev_revenue": _safe(info, "enterpriseToRevenue"),
        "fcf_yield": (
            _safe(info, "freeCashflow") / _safe(info, "marketCap")
            if _safe(info, "freeCashflow") and _safe(info, "marketCap") else None
        ),
        "rev_growth": _safe(info, "revenueGrowth"),
        "earn_growth": _safe(info, "earningsGrowth"),
        "debt_eq": _safe(info, "debtToEquity"),
        "roe": _safe(info, "returnOnEquity"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="yfinance_enrichment.json")
    p.add_argument("--sleep", type=float, default=0.20)
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--skip-excluded", action="store_true",
                   help="Drop SPAC warrants / preferreds before enriching.")
    args = p.parse_args()

    tickers = collect_tickers()
    print(f"Collected {len(tickers)} tickers from cached sweeps.",
          file=sys.stderr)

    overlay: dict[str, dict] = {}
    out_path = Path(args.out)
    if out_path.exists():
        try:
            overlay = json.loads(out_path.read_text())
            print(f"Resuming -- overlay already has {len(overlay)} tickers.",
                  file=sys.stderr)
        except Exception:
            overlay = {}

    n_processed = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in overlay:
            continue
        if args.skip_excluded:
            bad, _ = is_excluded(tk)
            if bad:
                continue
        try:
            row = fetch_one(tk)
        except Exception as e:
            row = {"_error": str(e)}
        if row:
            overlay[tk] = row
            n_processed += 1
        if i % 50 == 0:
            print(f"  [{i}/{len(tickers)}] processed (new this run: {n_processed})",
                  file=sys.stderr, flush=True)
            out_path.write_text(json.dumps(overlay, indent=2, default=str))
        time.sleep(args.sleep)

    out_path.write_text(json.dumps(overlay, indent=2, default=str))
    n_short = sum(1 for v in overlay.values() if (v.get("short_pct_float") or 0) >= 0.10)
    n_neg_anal = sum(1 for v in overlay.values() if (v.get("analyst_count") or 99) <= 2)
    n_drawdown = sum(1 for v in overlay.values() if (v.get("drawdown_pct") is not None and v["drawdown_pct"] <= 25))
    print(f"\nWrote {args.out} ({len(overlay)} tickers).", file=sys.stderr)
    print(f"  short_pct_float >= 10%: {n_short}", file=sys.stderr)
    print(f"  analyst_count <= 2:     {n_neg_anal}", file=sys.stderr)
    print(f"  near 52w-low (<25%):    {n_drawdown}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
