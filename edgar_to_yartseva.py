"""Convert edgar_universe_facts.csv into us_edgar_yartseva.csv that
slots into the same downstream pipeline as the yfinance-derived
yartseva CSVs.

EDGAR XBRL is higher-quality (audited filings) than yfinance for US
issuers. For any symbol present in both, the EDGAR row supersedes the
yfinance row when build_asymmetry_global.sh aggregates everything.

This script adds:
  - Price-to-tangible-book (P/TB) using yfinance for the latest price
  - 12m momentum and 52w high context (from yfinance history)
  - The full set of yartseva-schema columns (rev_yoy, ebitda_yoy,
    rev_accel, inflection flags, etc.) computed from EDGAR's
    multi-period XBRL data via additional company-facts queries.

For speed, the price + momentum step uses yfinance.download in bulk
for all symbols rather than per-ticker info calls.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


CACHE_DIR = Path("edgar_cache")


# --- Per-ticker price + momentum (bulk yfinance) -------------------------
def fetch_prices_cached() -> pd.DataFrame:
    """Pull prices + market caps + momentum + sector from already-cached
    *_yartseva.csv files. Avoids re-hitting yfinance (which is often
    rate-limited). Returns a DataFrame keyed by symbol with the same
    columns the bulk-yf version produced — anything not derivable from
    cache is left NaN. Also surfaces sector/industry so EDGAR-only rows
    can be hydrated with financedatabase tags (audit #3 §6 fix).
    """
    import glob
    keep = ['symbol', 'price', 'market_cap', 'momentum_12m',
            'enterprise_value', 'sector', 'industry']
    frames = []
    for f in sorted(glob.glob('*_yartseva.csv')):
        # Skip our own output so we don't pick up empty-price rows from a
        # prior failed run — that would shadow the populated cached prices.
        if f == 'us_edgar_yartseva.csv':
            continue
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if not frames:
        return pd.DataFrame(columns=keep)
    # Sort rows so non-NaN market_cap + sector wins the dedup. We rank
    # "has data" rows first, then keep='first'. Prefer sector-populated
    # rows over sector-NaN rows so EDGAR rows get the financedatabase
    # sector tag when it's available in the cache.
    df = pd.concat(frames, ignore_index=True)
    df['_has_mcap'] = df['market_cap'].notna().astype(int)
    df['_has_sector'] = df.get('sector', pd.Series(dtype=object)).notna().astype(int) \
        if 'sector' in df.columns else 0
    df = (df.sort_values(['symbol', '_has_mcap', '_has_sector'],
                         ascending=[True, False, False])
            .drop_duplicates('symbol', keep='first')
            .drop(columns=[c for c in ('_has_mcap', '_has_sector') if c in df.columns]))
    # Approximate 52w high from price + momentum: not directly available,
    # so leave pct_off_52w_high NaN here. (When yfinance is back, a
    # follow-up pass can fill this.)
    df['pct_off_52w_high'] = np.nan
    return df


def fetch_prices_bulk(symbols: list[str]) -> pd.DataFrame:
    """yfinance.download in batches. Falls back to fetch_prices_cached
    when yfinance is unreachable (rate-limited or network-blocked).
    """
    try:
        import yfinance as yf
    except ImportError:
        return fetch_prices_cached()

    out_rows = []
    BATCH = 100
    failed = 0
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        try:
            data = yf.download(batch, period="1y", interval="1d",
                               group_by="ticker", auto_adjust=True,
                               progress=False, threads=True, timeout=20)
        except Exception:
            failed += 1
            if failed >= 3:
                print(f"  yfinance unreachable after {failed} batches — "
                      f"falling back to cached prices", file=sys.stderr)
                return fetch_prices_cached()
            continue
        for sym in batch:
            try:
                if len(batch) == 1:
                    close = data["Close"].dropna()
                else:
                    close = data[sym]["Close"].dropna()
                if close.empty:
                    continue
                p_now = float(close.iloc[-1])
                p_1y = float(close.iloc[0])
                hi_52w = float(close.max())
                mom = (p_now - p_1y) / p_1y if p_1y else None
                off_hi = (p_now - hi_52w) / hi_52w if hi_52w else None
                out_rows.append({
                    "symbol": sym, "price": p_now,
                    "momentum_12m": mom, "price_52w_high": hi_52w,
                    "pct_off_52w_high": off_hi,
                })
            except (KeyError, IndexError, AttributeError, TypeError):
                continue
        time.sleep(0.5)
    if not out_rows:
        return fetch_prices_cached()
    return pd.DataFrame(out_rows)


# --- Map EDGAR fields to yartseva schema ---------------------------------
def build_yartseva_row(edgar_row: pd.Series, price_row: pd.Series | None) -> dict:
    """Produce a row matching yartseva's column conventions."""
    r = {}
    sym = edgar_row.get("symbol")
    name = edgar_row.get("name") or ""
    r["symbol"] = sym
    r["name"] = str(name).title() if isinstance(name, str) else name
    r["src"] = "US"
    r["currency"] = "USD"
    # Hydrate sector/industry from the cached *_yartseva.csv data when
    # available (financedatabase tags). Blank if no source has them.
    if price_row is not None:
        sec = price_row.get("sector")
        ind = price_row.get("industry")
        r["sector"] = str(sec) if (sec is not None and not pd.isna(sec)) else ""
        r["industry"] = str(ind) if (ind is not None and not pd.isna(ind)) else ""
    else:
        r["sector"] = ""
        r["industry"] = ""

    # Price + shares -> market cap. Prefer the cached price+mcap rows
    # over re-deriving from EDGAR shares × price (which is brittle for
    # restated share counts and post-split data).
    price = None
    market_cap = None
    if price_row is not None:
        if pd.notna(price_row.get("price")):
            price = float(price_row["price"])
        if pd.notna(price_row.get("market_cap")):
            market_cap = float(price_row["market_cap"])
    shares = edgar_row.get("shares_outstanding")
    # Fallback: derive mcap from EDGAR shares × yfinance price if cache
    # had a price but no mcap.
    if market_cap is None and price is not None and shares and pd.notna(shares):
        market_cap = price * shares
    if market_cap is not None and market_cap > 0:
        r["market_cap"] = market_cap
        r["enterprise_value"] = market_cap + (edgar_row.get("total_debt") or 0) - (edgar_row.get("cash") or 0)
    r["price"] = price

    # Bucket from FDB convention (USD)
    if market_cap is not None:
        if market_cap < 50e6:
            r["market_cap_bucket"] = "Nano Cap"
        elif market_cap < 300e6:
            r["market_cap_bucket"] = "Micro Cap"
        elif market_cap < 2e9:
            r["market_cap_bucket"] = "Small Cap"
        elif market_cap < 10e9:
            r["market_cap_bucket"] = "Mid Cap"
        elif market_cap < 200e9:
            r["market_cap_bucket"] = "Large Cap"
        else:
            r["market_cap_bucket"] = "Mega Cap"

    # Levels
    r["revenue_ttm"] = edgar_row.get("revenue_ttm")
    r["ebitda_ttm"] = edgar_row.get("ebitda_ttm")
    r["cfo_ttm"] = edgar_row.get("cfo_ttm")
    r["fcf_ttm"] = edgar_row.get("fcf_ttm")
    r["balance_sheet_date"] = edgar_row.get("assets_end") or edgar_row.get("equity_end")
    # Surface raw balance-sheet levels so downstream gates can use them
    # as scale proxies when market_cap is missing.
    r["equity"] = edgar_row.get("equity")
    r["assets"] = edgar_row.get("assets")
    r["cash"] = edgar_row.get("cash")
    r["total_debt"] = edgar_row.get("total_debt")
    r["tangible_equity"] = edgar_row.get("tangible_equity")
    r["goodwill"] = edgar_row.get("goodwill")
    r["intangibles"] = edgar_row.get("intangibles")
    r["shares_outstanding"] = edgar_row.get("shares_outstanding")
    # NEW (audit June 2026): capital-allocation + quality fields
    r["dividends_ttm"] = edgar_row.get("dividends_ttm")
    r["buybacks_ttm"] = edgar_row.get("buybacks_ttm")
    r["capital_return_ttm"] = edgar_row.get("capital_return_ttm")
    r["sbc_ttm"] = edgar_row.get("sbc_ttm")
    r["sbc_pct_revenue"] = edgar_row.get("sbc_pct_revenue")
    r["effective_tax_rate"] = edgar_row.get("effective_tax_rate")
    r["pretax_income_ttm"] = edgar_row.get("pretax_income_ttm")
    r["tax_expense_ttm"] = edgar_row.get("tax_expense_ttm")
    r["roic_after_sbc"] = edgar_row.get("roic_after_sbc")
    r["interest_coverage"] = edgar_row.get("interest_coverage")
    r["retained_earnings"] = edgar_row.get("retained_earnings")
    r["ppe_net"] = edgar_row.get("ppe_net")
    r["eps_basic_ttm"] = edgar_row.get("eps_basic_ttm")
    r["eps_diluted_ttm"] = edgar_row.get("eps_diluted_ttm")

    # Margins
    r["ebitda_margin"] = edgar_row.get("ebitda_margin")
    r["op_margin"] = edgar_row.get("op_margin")
    r["net_margin"] = edgar_row.get("net_margin")
    r["fcf_margin"] = edgar_row.get("fcf_margin")
    r["gross_margin"] = None  # not separately extracted from XBRL; left for downstream

    # Quality / capital efficiency
    if r.get("cfo_ttm") and r.get("ebitda_ttm") and r["ebitda_ttm"] != 0:
        r["cash_conversion"] = r["cfo_ttm"] / r["ebitda_ttm"]
    r["roce"] = edgar_row.get("roce")
    if edgar_row.get("total_debt") and edgar_row.get("ebitda_ttm") and edgar_row["ebitda_ttm"] != 0:
        nd = edgar_row["total_debt"] - (edgar_row.get("cash") or 0)
        r["net_debt_ebitda"] = nd / edgar_row["ebitda_ttm"]
    if edgar_row.get("total_debt") is not None and edgar_row.get("equity") and edgar_row["equity"] > 0:
        r["debt_to_equity"] = edgar_row["total_debt"] / edgar_row["equity"]

    # Valuation ratios (mcap- or EV-based)
    if market_cap and r.get("revenue_ttm"):
        r["p_s"] = market_cap / r["revenue_ttm"]
        if r.get("enterprise_value"):
            r["ev_sales"] = r["enterprise_value"] / r["revenue_ttm"]
    if r.get("enterprise_value") and r.get("ebitda_ttm") and r["ebitda_ttm"] > 0:
        r["ev_ebitda"] = r["enterprise_value"] / r["ebitda_ttm"]
    opinc = edgar_row.get("opinc_ttm")
    if r.get("enterprise_value") and opinc and opinc > 0:
        r["ev_ebit"] = r["enterprise_value"] / opinc
    if market_cap and edgar_row.get("equity") and edgar_row["equity"] > 0:
        r["pb"] = market_cap / edgar_row["equity"]
    # Price-to-tangible-book — the headline new metric
    te = edgar_row.get("tangible_equity")
    if market_cap and te and te > 0:
        r["p_tb"] = market_cap / te
    netinc = edgar_row.get("netinc_ttm")
    if market_cap and netinc and netinc > 0:
        r["p_e"] = market_cap / netinc
    if market_cap and r.get("fcf_ttm"):
        r["fcf_yield"] = r["fcf_ttm"] / market_cap

    # Capital-return yield = (dividends + buybacks paid TTM) / market_cap
    cr = edgar_row.get("capital_return_ttm")
    if cr is not None and market_cap and market_cap > 0:
        r["capital_return_yield"] = cr / market_cap
        # Dividend + buyback yield separately
        div = edgar_row.get("dividends_ttm")
        bb = edgar_row.get("buybacks_ttm")
        if div is not None:
            r["dividend_yield"] = div / market_cap
        if bb is not None:
            r["buyback_yield"] = bb / market_cap

    # Tangible book per share
    if edgar_row.get("tangible_book_per_share"):
        r["tangible_book_per_share"] = edgar_row["tangible_book_per_share"]
        if price:
            r["pct_above_tb"] = (price - edgar_row["tangible_book_per_share"]) / edgar_row["tangible_book_per_share"]

    # NCAV (Graham): current_assets - total_liabilities
    if edgar_row.get("current_assets") is not None and edgar_row.get("liabilities") is not None:
        ncav = edgar_row["current_assets"] - edgar_row["liabilities"]
        r["ncav"] = ncav
        if market_cap:
            r["ncav_pct_mcap"] = ncav / market_cap
            if ncav > 0:
                r["mcap_to_ncav"] = market_cap / ncav
                r["graham_net_net_flag"] = int(market_cap / ncav < (2.0 / 3.0))

    # Cash / EV signals
    cash = edgar_row.get("cash")
    if cash is not None and market_cap and market_cap > 0:
        r["cash_pct_mcap"] = cash / market_cap
    if cash is not None and r.get("enterprise_value") and r["enterprise_value"] > 0:
        r["cash_pct_ev"] = cash / r["enterprise_value"]
    if edgar_row.get("net_cash") is not None and market_cap and market_cap > 0:
        r["net_cash"] = edgar_row["net_cash"]
        r["net_cash_pct_mcap"] = edgar_row["net_cash"] / market_cap
    if r.get("cash_pct_ev") and r["cash_pct_ev"] > 1.0 and (edgar_row.get("net_cash") or 0) > 0:
        r["cash_gt_ev_flag"] = 1

    # Tangible value flag - new from EDGAR
    if edgar_row.get("equity") and edgar_row["equity"] > 0:
        r["tangible_equity_pct"] = (edgar_row.get("tangible_equity") or 0) / edgar_row["equity"]

    # Price / momentum
    if price_row is not None:
        r["momentum_12m"] = price_row.get("momentum_12m")
        r["pct_off_52w_high"] = price_row.get("pct_off_52w_high")

    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edgar-facts", default="edgar_universe_facts.csv")
    ap.add_argument("--out", default="us_edgar_yartseva.csv")
    ap.add_argument("--skip-prices", action="store_true",
                    help="don't fetch yfinance prices (no mcap / momentum cols)")
    ap.add_argument("--refresh-prices", action="store_true",
                    help="hit yfinance.download for fresh prices "
                         "(slow / often rate-limited; use only when needed)")
    args = ap.parse_args()

    print("loading EDGAR facts...", file=sys.stderr)
    edgar = pd.read_csv(args.edgar_facts)
    print(f"  {len(edgar):,} rows", file=sys.stderr)
    # Drop rows with no XBRL data (concept_count == 0)
    edgar = edgar[edgar["concept_count"].fillna(0) > 0]
    print(f"  {len(edgar):,} rows with non-empty XBRL", file=sys.stderr)

    # Prices: prefer cache (always reachable). yfinance.download is
    # available with --refresh-prices but rate-limits make it brittle.
    prices = pd.DataFrame()
    if not args.skip_prices:
        if args.refresh_prices:
            symbols = edgar["symbol"].dropna().unique().tolist()
            print(f"fetching prices for {len(symbols):,} symbols via yfinance...", file=sys.stderr)
            prices = fetch_prices_bulk(symbols)
        else:
            print("loading cached prices from existing *_yartseva.csv...", file=sys.stderr)
            prices = fetch_prices_cached()
        print(f"  got {len(prices):,} price rows", file=sys.stderr)

    # Merge
    pmap = prices.set_index("symbol").to_dict("index") if not prices.empty else {}

    rows = []
    for _, er in edgar.iterrows():
        pr_dict = pmap.get(er["symbol"])
        pr = pd.Series(pr_dict) if pr_dict else None
        rows.append(build_yartseva_row(er, pr))
    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(out):,} rows", file=sys.stderr)
    # Coverage
    for c in ["market_cap", "ebitda_margin", "ev_ebitda", "ev_ebit", "pb", "p_tb",
              "fcf_yield", "roce", "net_debt_ebitda", "momentum_12m",
              "tangible_equity_pct"]:
        if c in out.columns:
            n = out[c].notna().sum()
            print(f"  {c:25s} {n:,} / {len(out):,} ({100*n/len(out):.1f}%)",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
