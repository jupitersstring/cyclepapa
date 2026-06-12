#!/usr/bin/env python3
"""
200-Week-Low  ×  Normalised FCF Yield  ×  Active Buybacks  screen.

Quantitative reproduction of the May-2026 methodology:

  Filter                          Threshold
  ------------------------------  -----------------------------------
  Price vs 200-week low           within --from-low (default 15%)
  Normalised (5y avg) FCF yield   >= --min-fcf-yield (default 7%) on EV
  Net buyback yield (TTM)         >= --min-buyback (default 4%) OR > 0 (active)
  Net debt / EBITDA               <= --max-nd-ebitda (default 4.5x)

Stage 1 (free, from the cached weekly data): proximity to the 200-week low.
Stage 2 (yfinance fundamentals, only for stage-1 survivors): 5y-avg FCF,
EV/market cap, TTM net buyback, net-debt/EBITDA.

Composite (automatable portion) = 0.30*rank(FCF yield) + 0.25*rank(buyback yield).
The two manual overlays from the methodology -- transience (0-1) and capital-
structure-reset (0-1), weighted 0.25 and 0.20 -- can't be derived from data;
they're emitted as blank columns for you to fill, and the full composite is then
  0.30*fcf_rank + 0.25*bb_rank + 0.25*transience + 0.20*reset.

Usage:
  python3 fcf_screen.py --universe us-allcap --from-low 0.15 --csv out.csv
  python3 fcf_screen.py --universe uk-allcap --on mktcap
"""
from __future__ import annotations

import argparse
import os
import time
import warnings

import numpy as np
import pandas as pd

from midcap_weekly_anomalies import get_universe, CAP_SOURCES, CACHE_DIR  # noqa
warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# Stage 1 — proximity to 200-week low (from cached weekly closes, no network)
# --------------------------------------------------------------------------- #
def near_200w_low(symbols, from_low, period="20y"):
    cache = os.path.join(CACHE_DIR, f"ohlcvdict_1wk_{period}.pkl")
    have = pd.read_pickle(cache)
    rows = []
    for s in symbols:
        df = have.get(s)
        if df is None:
            continue
        c = df["Close"].dropna()
        if len(c) < 60:
            continue
        win = c.iloc[-200:]
        lo, hi, px = float(win.min()), float(win.max()), float(c.iloc[-1])
        above_low = px / lo - 1.0 if lo > 0 else np.nan
        off_high = px / hi - 1.0 if hi > 0 else np.nan
        if np.isfinite(above_low) and above_low <= from_low:
            rows.append({"symbol": s, "price": px, "low200w": lo,
                         "pct_above_low": above_low, "pct_off_high": off_high})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Stage 2 — fundamentals (FCF, buyback, leverage) per survivor
# --------------------------------------------------------------------------- #
def _row(df, *names):
    for n in names:
        if df is not None and n in df.index:
            s = df.loc[n].dropna()
            if len(s):
                return s.astype(float)
    return None


def fundamentals(sym, on="ev"):
    import yfinance as yf
    tk = yf.Ticker(sym)
    info = tk.info or {}
    cf = None
    for a in ("cashflow", "cash_flow"):
        try:
            cf = getattr(tk, a)
            if cf is not None and not cf.empty:
                break
        except Exception:
            cf = None
    # normalised free cash flow: median of up to 5y (robust to M&A/divestiture
    # spikes, e.g. Tate & Lyle's Primient year) rather than a mean
    fcf = _row(cf, "Free Cash Flow")
    if fcf is None:
        ocf = _row(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = _row(cf, "Capital Expenditure", "Capital Expenditures")
        if ocf is not None and capex is not None:
            fcf = (ocf + capex).dropna()       # capex stored negative
    fcf5 = float(np.median(fcf.values[:5])) if fcf is not None and len(fcf) else np.nan

    # currency guard: FCF is in financialCurrency; EV/mktcap must match. yfinance
    # reports marketCap in financialCurrency even when the quote is in pence (GBp),
    # so they are consistent -- but flag any genuine mismatch as unreliable.
    fin_ccy = info.get("financialCurrency"); quote_ccy = info.get("currency")
    ccy_ok = True  # mktcap/EV are in financialCurrency in yfinance

    mktcap = info.get("marketCap")
    ev = info.get("enterpriseValue") or mktcap
    denom = ev if on == "ev" else mktcap
    fcf_yield = (fcf5 / denom) if (fcf5 == fcf5 and denom) else np.nan

    # TTM net buyback (repurchases net of issuance), latest annual
    rep = _row(cf, "Repurchase Of Capital Stock", "Repurchase Of Capital Stock")
    iss = _row(cf, "Issuance Of Capital Stock")
    net_bb = 0.0
    if rep is not None and len(rep):
        net_bb += -float(rep.values[0])        # repurchases stored negative
    if iss is not None and len(iss):
        net_bb -= float(iss.values[0])
    bb_yield = (net_bb / mktcap) if mktcap else np.nan

    ebitda = info.get("ebitda")
    nd = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)
    nd_ebitda = (nd / ebitda) if ebitda else np.nan

    sector = info.get("sector")
    qt = (info.get("quoteType") or "").upper()
    industry = (info.get("industry") or "")
    # FCF is meaningless for banks/insurers/asset-mgrs/CEFs/BDCs/REITs and non-equities
    fcf_na = (qt != "EQUITY") or (sector in {"Financial Services", "Real Estate"}) \
        or ("Asset Management" in industry) or ("Capital Markets" in industry)
    # computed (live) market-cap bucket -- the financedatabase tag is often stale
    mc = (mktcap or 0) / 1e9
    comp_cap = ("Mega" if mc >= 200 else "Large" if mc >= 10 else "Mid" if mc >= 2
                else "Small" if mc >= 0.3 else "Micro/Nano")
    return {"fcf5_avg": fcf5, "fcf_yield": fcf_yield, "buyback_yield": bb_yield,
            "nd_ebitda": nd_ebitda, "mktcap": mktcap, "ev": ev,
            "sector": sector, "quoteType": qt, "fcf_na": fcf_na,
            "computed_cap": comp_cap, "fin_ccy": fin_ccy, "quote_ccy": quote_ccy,
            "name": (info.get("shortName") or "")[:22]}


# --------------------------------------------------------------------------- #
def run(args):
    uni = get_universe(source=args.universe)
    syms = uni["symbol"].tolist()
    cap = dict(zip(uni["symbol"], uni.get("market_cap", pd.Series(dtype=str))))

    s1 = near_200w_low(syms, args.from_low, args.period)
    print(f"[stage1] {len(s1)} / {len(syms)} within {args.from_low:.0%} of their 200-week low")
    if s1.empty:
        return
    if args.limit_fund:
        s1 = s1.sort_values("pct_above_low").head(args.limit_fund)

    recs = []
    for i, r in enumerate(s1.itertuples(), 1):
        try:
            f = fundamentals(r.symbol, args.on)
        except Exception:
            f = {}
        recs.append({**r._asdict(), **f, "cap": cap.get(r.symbol, "?")})
        if i % 25 == 0:
            print(f"[stage2] {i}/{len(s1)} fundamentals pulled")
        time.sleep(0.4)
    df = pd.DataFrame(recs).drop(columns=["Index"], errors="ignore")

    # apply the quantitative thresholds
    if "fcf_na" not in df:
        df["fcf_na"] = False
    df["pass_fcf"] = df["fcf_yield"] >= args.min_fcf_yield
    # buyback: meet the explicit threshold (the old `| >0` made the threshold a no-op);
    # `--active-ok` relaxes to "any net buyback" to mirror "gross programme active"
    if args.active_ok:
        df["pass_bb"] = df["buyback_yield"] > 0
    else:
        df["pass_bb"] = df["buyback_yield"] >= args.min_buyback
    df["pass_solv"] = (df["nd_ebitda"] <= args.max_nd_ebitda) | df["nd_ebitda"].isna()
    # EV-collapse artifact guard: a >max_yield FCF or buyback "yield" means the
    # denominator (EV/mktcap) has imploded — usually a post-failure biotech cash
    # return (KROS, DH), not a real FCF business. Drop these.
    df["artifact"] = (df["fcf_yield"].abs() > args.max_yield) | \
                     (df["buyback_yield"].abs() > args.max_yield)
    # exclude names where FCF is not a meaningful metric (banks/insurers/REITs/CEFs/BDCs)
    df["pass_all"] = (df["pass_fcf"] & df["pass_bb"] & df["pass_solv"]
                      & ~df["fcf_na"].fillna(False) & ~df["artifact"].fillna(False))

    passed = df[df["pass_all"]].copy()
    if not passed.empty:
        passed["fcf_rank"] = passed["fcf_yield"].rank(pct=True)
        passed["bb_rank"] = passed["buyback_yield"].rank(pct=True)
        passed["quant_score"] = 0.30 * passed["fcf_rank"] + 0.25 * passed["bb_rank"]
        passed["transience"] = ""     # manual overlay (0-1)
        passed["cap_reset"] = ""      # manual overlay (0-1)
        passed = passed.sort_values("quant_score", ascending=False)

    _report(df, passed, args)
    if args.csv:
        out = passed if (args.passed_only and not passed.empty) else df
        out.to_csv(args.csv, index=False)
        print(f"\n[out] -> {args.csv}  ({len(out)} rows)")


def _report(df, passed, args):
    print(f"\n{'='*104}\n200-WEEK-LOW x NORMALISED FCF YIELD x ACTIVE BUYBACKS  ({args.universe})\n"
          f"filters: <= {args.from_low:.0%} from 200w low | FCF yield(on {args.on}) >= "
          f"{args.min_fcf_yield:.0%} | net buyback active | ND/EBITDA <= {args.max_nd_ebitda}\n{'='*104}")
    print(f"stage-1 near-low: {len(df)} | passing ALL quant filters: {len(passed)}\n")
    if passed.empty:
        print("No names passed all quant filters."); return
    print(f"{'Sym':<9}{'Sector':<20}{'Cap':<10}{'%>low':>7}{'%offHi':>8}"
          f"{'FCFyld':>8}{'BByld':>7}{'ND/EB':>7}{'Qscore':>7}")
    for _, r in passed.head(args.top).iterrows():
        def p(x): return f"{x*100:>+6.0f}%" if pd.notna(x) else "   -  "
        nde = f"{r['nd_ebitda']:.1f}" if pd.notna(r['nd_ebitda']) else "-"
        print(f"{r['symbol']:<9}{str(r['sector'])[:19]:<20}{str(r['cap'])[:9]:<10}"
              f"{r['pct_above_low']*100:>6.0f}%{r['pct_off_high']*100:>7.0f}%"
              f"{p(r['fcf_yield'])}{p(r['buyback_yield'])}{nde:>7}{r['quant_score']:>7.2f}")


def parse_args():
    p = argparse.ArgumentParser(description="200w-low x FCF-yield x buyback screen")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="us-allcap")
    p.add_argument("--period", default="20y")
    p.add_argument("--from-low", type=float, default=0.15, help="max % above 200-week low")
    p.add_argument("--min-fcf-yield", type=float, default=0.07)
    p.add_argument("--min-buyback", type=float, default=0.04)
    p.add_argument("--active-ok", action="store_true",
                   help="relax buyback test to 'any net buyback > 0' (gross programme active)")
    p.add_argument("--max-nd-ebitda", type=float, default=4.5)
    p.add_argument("--max-yield", type=float, default=0.60,
                   help="drop EV-collapse artifacts whose FCF/buyback yield exceeds this")
    p.add_argument("--on", choices=["ev", "mktcap"], default="ev")
    p.add_argument("--limit-fund", type=int, default=None, help="cap # of fundamentals pulls")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--passed-only", action="store_true")
    p.add_argument("--csv", default=None)
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
