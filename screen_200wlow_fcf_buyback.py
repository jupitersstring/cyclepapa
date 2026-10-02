"""200-week-low + normalized FCF yield + buyback machine screener.

Backend: EODHD All-In-One.

Usage:
    export EODHD_KEY=your_key
    python screen_200wlow_fcf_buyback.py \
        --universe SP500,SP400,FTSE100,FTSE250,STOXX600 \
        --within-low-pct 15 \
        --min-norm-fcf-yield 0.07 \
        --min-buyback-yield 0.04 \
        --max-net-debt-ebitda 4.5 \
        --out shortlist.csv

Notes:
  * "Normalized FCF yield" = mean(FCF / market_cap) over the trailing 5 fiscal
    years, recomputed using the CURRENT market cap. Avoids the trap where a
    transient earnings hit kills TTM FCF and the name screens out exactly when
    you want it.
  * Buyback yield = abs(repurchase_of_common_stock_TTM) / current_market_cap.
    Net of issuance is more honest; toggle with --net-buyback.
  * Capital structure reset and transience scores are NOT computed here. They
    are the qualitative overlay you apply by hand to the ~30-50 survivors.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import requests

EODHD = "https://eodhd.com/api"
KEY = os.environ.get("EODHD_KEY")
if not KEY:
    sys.exit("Set EODHD_KEY env var")


# ----- universe construction -----

INDEX_TO_EODHD = {
    # EODHD index constituent endpoints
    "SP500":    "GSPC.INDX",
    "SP400":    "MID.INDX",
    "FTSE100":  "UKX.INDX",
    "FTSE250":  "MCX.INDX",
    "STOXX600": "STOXX.INDX",
}


def get_constituents(idx: str) -> list[str]:
    sym = INDEX_TO_EODHD[idx]
    url = f"{EODHD}/fundamentals/{sym}?api_token={KEY}&fmt=json"
    r = requests.get(url, timeout=30).json()
    comps = r.get("Components", {})
    return [v["Code"] + "." + v["Exchange"] for v in comps.values()]


# ----- price history & 200-week low -----

def weekly_prices(ticker: str, years: int = 5) -> Optional[pd.Series]:
    url = f"{EODHD}/eod/{ticker}"
    params = {
        "api_token": KEY,
        "period": "w",
        "fmt": "json",
        "from": (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d"),
    }
    try:
        data = requests.get(url, params=params, timeout=30).json()
        if not isinstance(data, list) or not data:
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["adjusted_close"].astype(float)
    except Exception:
        return None


def pct_above_200w_low(prices: pd.Series) -> Optional[float]:
    # Use the last ~200 weekly bars (5 years ~= 260 weeks; "200-week" is the
    # commonly-displayed window).
    tail = prices.tail(200)
    if len(tail) < 150:  # need most of the window
        return None
    low = tail.min()
    cur = prices.iloc[-1]
    return (cur / low) - 1.0


# ----- fundamentals: FCF, buybacks, debt, market cap -----

@dataclass
class Fundamentals:
    ticker: str
    market_cap: float
    fcf_5y_avg: float        # mean of last 5 fiscal-year FCFs
    fcf_ttm: float
    buyback_ttm: float       # abs value of repurchases
    issuance_ttm: float      # offset for net buyback
    net_debt: float
    ebitda_5y_avg: float
    name: str
    sector: str
    country: str


def fundamentals(ticker: str) -> Optional[Fundamentals]:
    url = f"{EODHD}/fundamentals/{ticker}?api_token={KEY}&fmt=json"
    try:
        f = requests.get(url, timeout=30).json()
    except Exception:
        return None

    g = f.get("General", {})
    h = f.get("Highlights", {})
    fin = f.get("Financials", {})
    cf_y = fin.get("Cash_Flow", {}).get("yearly", {})
    cf_q = fin.get("Cash_Flow", {}).get("quarterly", {})
    bs_q = fin.get("Balance_Sheet", {}).get("quarterly", {})
    is_y = fin.get("Income_Statement", {}).get("yearly", {})

    if not cf_y or not bs_q:
        return None

    # 5y FCF history
    fcf_years = []
    for _, row in sorted(cf_y.items(), reverse=True)[:5]:
        ocf = row.get("totalCashFromOperatingActivities")
        capex = row.get("capitalExpenditures")
        if ocf is not None and capex is not None:
            # EODHD reports capex as negative outflow
            fcf_years.append(float(ocf) + float(capex))
    if len(fcf_years) < 3:
        return None
    fcf_5y_avg = float(np.mean(fcf_years))

    # TTM FCF from last 4 quarters
    q_sorted = sorted(cf_q.items(), reverse=True)[:4]
    fcf_ttm = sum(
        float(r.get("totalCashFromOperatingActivities") or 0)
        + float(r.get("capitalExpenditures") or 0)
        for _, r in q_sorted
    )

    # TTM buybacks and issuance
    buyback_ttm = sum(
        abs(float(r.get("salePurchaseOfStock") or 0))
        if (float(r.get("salePurchaseOfStock") or 0) < 0) else 0.0
        for _, r in q_sorted
    )
    issuance_ttm = sum(
        float(r.get("salePurchaseOfStock") or 0)
        if (float(r.get("salePurchaseOfStock") or 0) > 0) else 0.0
        for _, r in q_sorted
    )

    # Latest balance sheet for net debt
    latest_bs = sorted(bs_q.items(), reverse=True)[0][1]
    total_debt = float(
        latest_bs.get("shortLongTermDebtTotal")
        or (float(latest_bs.get("shortTermDebt") or 0)
            + float(latest_bs.get("longTermDebt") or 0))
    )
    cash = float(
        latest_bs.get("cashAndShortTermInvestments")
        or latest_bs.get("cash") or 0
    )
    net_debt = total_debt - cash

    # 5y avg EBITDA
    ebitda_years = []
    for _, row in sorted(is_y.items(), reverse=True)[:5]:
        e = row.get("ebitda")
        if e is not None:
            ebitda_years.append(float(e))
    ebitda_5y_avg = float(np.mean(ebitda_years)) if ebitda_years else float("nan")

    return Fundamentals(
        ticker=ticker,
        market_cap=float(h.get("MarketCapitalization") or 0),
        fcf_5y_avg=fcf_5y_avg,
        fcf_ttm=fcf_ttm,
        buyback_ttm=buyback_ttm,
        issuance_ttm=issuance_ttm,
        net_debt=net_debt,
        ebitda_5y_avg=ebitda_5y_avg,
        name=g.get("Name", ""),
        sector=g.get("Sector", ""),
        country=g.get("CountryName", ""),
    )


# ----- composite -----

def screen(args):
    universe = []
    for idx in args.universe.split(","):
        universe.extend(get_constituents(idx.strip()))
    universe = sorted(set(universe))
    print(f"Universe: {len(universe)} tickers")

    # Stage 1: 200w low filter (cheap, prices only)
    near_low = []
    for i, t in enumerate(universe):
        s = weekly_prices(t)
        if s is None:
            continue
        d = pct_above_200w_low(s)
        if d is not None and d <= args.within_low_pct / 100.0:
            near_low.append((t, d))
        if i % 50 == 0:
            print(f"  prices {i}/{len(universe)} | survivors {len(near_low)}")
        time.sleep(0.05)
    print(f"Stage 1 survivors (within {args.within_low_pct}% of 200w low): {len(near_low)}")

    # Stage 2: fundamentals
    rows = []
    for t, dist in near_low:
        f = fundamentals(t)
        if not f or f.market_cap <= 0:
            continue
        norm_fcf_yield = f.fcf_5y_avg / f.market_cap
        ttm_fcf_yield = f.fcf_ttm / f.market_cap
        buyback_yield = f.buyback_ttm / f.market_cap
        net_buyback_yield = (f.buyback_ttm - f.issuance_ttm) / f.market_cap
        nd_ebitda = (f.net_debt / f.ebitda_5y_avg) if f.ebitda_5y_avg > 0 else float("inf")

        if norm_fcf_yield < args.min_norm_fcf_yield:
            continue
        if (net_buyback_yield if args.net_buyback else buyback_yield) < args.min_buyback_yield:
            continue
        if nd_ebitda > args.max_net_debt_ebitda:
            continue

        rows.append({
            "ticker": t,
            "name": f.name,
            "sector": f.sector,
            "country": f.country,
            "pct_above_200w_low": round(dist * 100, 1),
            "norm_fcf_yield_5y": round(norm_fcf_yield * 100, 2),
            "ttm_fcf_yield": round(ttm_fcf_yield * 100, 2),
            "buyback_yield_ttm": round(buyback_yield * 100, 2),
            "net_buyback_yield_ttm": round(net_buyback_yield * 100, 2),
            "net_debt_5y_ebitda": round(nd_ebitda, 2),
            "market_cap_usd_m": round(f.market_cap / 1e6, 0),
        })
        time.sleep(0.05)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No survivors. Loosen filters.")
        return

    # Composite score (qualitative overlays default to 0.5 = neutral).
    df["transience_score"] = 0.5
    df["capital_reset_score"] = 0.5
    nfy_max = df["norm_fcf_yield_5y"].max() or 1.0
    nbby_clip = df["net_buyback_yield_ttm"].clip(lower=0)
    nbby_max = nbby_clip.max() or 1.0
    df["composite"] = (
        0.30 * (df["norm_fcf_yield_5y"] / nfy_max)
        + 0.25 * (nbby_clip / nbby_max)
        + 0.25 * df["transience_score"]
        + 0.20 * df["capital_reset_score"]
    )
    df = df.sort_values("composite", ascending=False)
    df.to_csv(args.out, index=False)
    print(f"\nWrote {len(df)} names to {args.out}")
    print(df.head(40).to_string(index=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--universe", default="SP500,SP400,FTSE100,FTSE250,STOXX600")
    p.add_argument("--within-low-pct", type=float, default=15.0)
    p.add_argument("--min-norm-fcf-yield", type=float, default=0.07)
    p.add_argument("--min-buyback-yield", type=float, default=0.04)
    p.add_argument("--max-net-debt-ebitda", type=float, default=4.5)
    p.add_argument("--net-buyback", action="store_true",
                   help="Use net buyback (repurchases minus issuance) instead of gross")
    p.add_argument("--out", default="shortlist.csv")
    screen(p.parse_args())
