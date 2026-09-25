"""International (non-US, non-UK) fundamentals screener.

Mirrors uk_screener.py but for AU / CA / HK / SG / JP / DE / FR / IT.
Output: intl_detail.json with same composite/valuation/income/quality/
drawdown/neglect schema, ready to merge into governance_psu_overlap.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from intl_universe import INTL_UNIVERSE


SECTOR_TAILWIND = {
    "DEFENCE": 1.20, "ASSETMGR": 1.10, "MEDTECH": 1.10,
    "ENERGY": 1.05, "MARINE": 1.05, "BUILD": 1.05,
    "OUTSOURCE": 1.00, "TECH": 1.00, "FIN": 1.00,
    "RETAIL": 0.95, "MEDIA": 0.95, "PROP": 0.95,
    "CONSUMER": 0.95, "INDUST": 1.00, "SPECIAL": 1.05,
    "METALS": 1.00, "TELECOM": 0.95,
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


def fetch_fund(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return {}
    if not info:
        # fast_info fallback
        try:
            fi = getattr(t, "fast_info", None)
            if fi is not None:
                info = {"currentPrice": fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None),
                        "marketCap": fi.get("market_cap") if hasattr(fi, "get") else getattr(fi, "market_cap", None),
                        "currency": fi.get("currency") if hasattr(fi, "get") else getattr(fi, "currency", None)}
        except Exception:
            pass
    if not info:
        return {}
    return {
        "name": info.get("longName") or info.get("shortName"),
        "currency": info.get("financialCurrency") or info.get("currency"),
        "price": _safe(info, "currentPrice") or _safe(info, "regularMarketPrice") or _safe(info, "previousClose"),
        "market_cap": _safe(info, "marketCap"),
        "p_b": _safe(info, "priceToBook"),
        "p_s": _safe(info, "priceToSalesTrailing12Months"),
        "ev_ebitda": _safe(info, "enterpriseToEbitda"),
        "trailing_pe": _safe(info, "trailingPE"),
        "forward_pe": _safe(info, "forwardPE"),
        "div_yield": _safe(info, "dividendYield"),
        "payout": _safe(info, "payoutRatio"),
        "fcf": _safe(info, "freeCashflow"),
        "ebitda": _safe(info, "ebitda"),
        "revenue": _safe(info, "totalRevenue"),
        "roe": _safe(info, "returnOnEquity"),
        "debt_eq": _safe(info, "debtToEquity"),
        "rev_growth": _safe(info, "revenueGrowth"),
        "earn_growth": _safe(info, "earningsGrowth"),
        "fwk_low": _safe(info, "fiftyTwoWeekLow"),
        "fwk_high": _safe(info, "fiftyTwoWeekHigh"),
        "held_inst": _safe(info, "heldPercentInstitutions"),
        "held_insid": _safe(info, "heldPercentInsiders"),
    }


def _clip01(x):
    return max(0.0, min(1.0, x))


def _ratio_score(value, target, higher_is_better=True):
    if value is None or value == 0: return 0.5
    s = value / target
    if not higher_is_better:
        s = 1.0 / s if s > 0 else 0.0
    return _clip01(s)


def score(fund: dict, sector: str) -> dict:
    if not fund:
        return {"composite": 0, "valuation": 0, "income": 0, "quality": 0,
                "drawdown": 0, "neglect": 0, "tailwind": 1.0}
    pb_score = _ratio_score(fund.get("p_b") or 5.0, target=1.0, higher_is_better=False)
    pe = fund.get("trailing_pe") or fund.get("forward_pe")
    pe_score = _ratio_score(pe if pe and pe > 0 else 30.0, target=10.0, higher_is_better=False)
    eve = fund.get("ev_ebitda")
    eve_score = _ratio_score(eve if eve and eve > 0 else 15.0, target=6.0, higher_is_better=False)
    valuation = 100.0 * (0.4 * pb_score + 0.4 * pe_score + 0.2 * eve_score)

    div = fund.get("div_yield") or 0
    income = 100.0 * _ratio_score(div, target=0.06, higher_is_better=True)

    roe = fund.get("roe") or 0
    eg = fund.get("earn_growth") or 0
    quality = 100.0 * (0.6 * _ratio_score(max(0, roe), target=0.15)
                       + 0.4 * _ratio_score(max(0, eg), target=0.15))

    px, lo, hi = fund.get("price"), fund.get("fwk_low"), fund.get("fwk_high")
    if px and lo and hi and hi > lo:
        pos = (px - lo) / (hi - lo)
        drawdown = 100.0 * (1.0 - _clip01(pos))
    else:
        drawdown = 50.0

    mcap = fund.get("market_cap") or 0
    held_inst = fund.get("held_inst") or 0
    if mcap > 0:
        size_factor = max(0.0, min(1.0, (5e9 - mcap) / 4.5e9))
    else:
        size_factor = 0.5
    inst_factor = max(0.0, min(1.0, (0.5 - held_inst) / 0.5))
    neglect = 100.0 * (0.6 * size_factor + 0.4 * inst_factor)

    tailwind = SECTOR_TAILWIND.get(sector, 1.0)
    composite = (0.30 * valuation + 0.20 * income + 0.18 * quality
                 + 0.17 * drawdown + 0.15 * neglect) * tailwind

    return {
        "composite": round(composite, 1),
        "valuation": round(valuation, 1),
        "income": round(income, 1),
        "quality": round(quality, 1),
        "drawdown": round(drawdown, 1),
        "neglect": round(neglect, 1),
        "tailwind": tailwind,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="intl_scorecard.csv")
    p.add_argument("--json", default="intl_detail.json")
    p.add_argument("--sleep", type=float, default=0.30)
    args = p.parse_args()

    rows = []
    items = list(INTL_UNIVERSE.items())
    for i, (tk, meta) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {tk}", file=sys.stderr, flush=True)
        try:
            f = fetch_fund(tk)
        except Exception as e:
            f = {}; print(f"   error: {e}", file=sys.stderr)
        sc = score(f, meta["sector"])
        rows.append({"ticker": tk, "name": meta["name"], "sector": meta["sector"], **f, **sc})
        time.sleep(args.sleep)

    Path(args.json).write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {args.json} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
