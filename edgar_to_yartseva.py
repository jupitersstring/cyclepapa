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
            'enterprise_value', 'sector', 'industry', 'price_asof']
    frames = []
    import os as _os
    # FRESHEST source first (mtime): the dedup keeps the first populated
    # row per symbol, so file order IS the vintage preference (audit Y1 —
    # the old alphabetical order could keep an arbitrarily stale price).
    for f in sorted(glob.glob('*_yartseva.csv'),
                    key=lambda p: _os.path.getmtime(p), reverse=True):
        # Skip our own output so we don't pick up empty-price rows from a
        # prior failed run — that would shadow the populated cached prices.
        if f == 'us_edgar_yartseva.csv':
            continue
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' in d.columns:
            d['price_asof'] = pd.Timestamp(_os.path.getmtime(f), unit='s').strftime('%Y-%m-%d')
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
                if len(close) < 230:   # a 3-month IPO is not 12m momentum
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
        # price vintage and share-count vintage may straddle a split —
        # identifiable provenance, never silent (audit Y2)
        market_cap = price * shares
        r["mcap_src"] = "derived_price_x_shares"
    if market_cap is not None and market_cap > 0:
        r["market_cap"] = market_cap
        # constructed EV owes preferred + NCI alongside debt (concepts review)
        _pref_ev = edgar_row.get("preferred_equity"); _nci_ev = edgar_row.get("minority_interest")
        _pref_ev = 0.0 if (_pref_ev is None or pd.isna(_pref_ev)) else float(_pref_ev)
        _nci_ev = 0.0 if (_nci_ev is None or pd.isna(_nci_ev)) else float(_nci_ev)
        r["enterprise_value"] = (market_cap + (edgar_row.get("total_debt") or 0)
                                 + _pref_ev + _nci_ev
                                 - (edgar_row.get("cash") or 0))
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
    # Graham/Templeton multi-year averages (levered flows -> yields vs MCAP)
    r["oe_avg"] = edgar_row.get("oe_avg")
    r["ni_avg"] = edgar_row.get("ni_avg")
    r["fcf_avg"] = edgar_row.get("fcf_avg")
    r["oe_avg_years"] = edgar_row.get("oe_avg_years")
    if market_cap:
        for _src_c, _y_c in (("oe_avg", "oe_avg_yield"),
                             ("ni_avg", "avg_earnings_yield"),
                             ("fcf_avg", "fcf_avg_yield")):
            _v = edgar_row.get(_src_c)
            if _v is not None:
                r[_y_c] = _v / market_cap
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
    # forensic round 2 fields
    r["capex_avg"] = edgar_row.get("capex_avg")
    r["capex_ttm"] = edgar_row.get("capex_ttm")   # audited primary for the capex waterfall
    r["equity_cagr_5y"] = edgar_row.get("equity_cagr_5y")
    r["financing_cf_ttm"] = edgar_row.get("financing_cf_ttm")
    _ca_f = edgar_row.get("current_assets"); _cl_f = edgar_row.get("current_liab")   # extractor key
    if _ca_f is not None and _cl_f is not None:
        r["net_working_capital"] = _ca_f - _cl_f
    # CSV NaN is truthy — "or 0" never fired, NaN-poisoning the ratio for
    # every goodwill-free company (exactly the tangible-value names).
    _gw_f = edgar_row.get("goodwill"); _ig_f = edgar_row.get("intangibles")
    _gw_f = 0 if (_gw_f is None or pd.isna(_gw_f)) else _gw_f
    _ig_f = 0 if (_ig_f is None or pd.isna(_ig_f)) else _ig_f
    _as_f = edgar_row.get("assets")
    if _as_f:
        r["goodwill_intangibles_pct_assets"] = (_gw_f + _ig_f) / _as_f
    r["ppe_net"] = edgar_row.get("ppe_net")
    r["da_ttm"] = edgar_row.get("da_ttm")                       # AUDITED D&A (over implied EBITDA-EBIT)
    r["deferred_revenue"] = edgar_row.get("deferred_revenue")  # customer-prepayment float (XR12)
    r["investments_associates"] = edgar_row.get("investments_associates")  # look-through value (XR C)
    r["minority_interest"] = edgar_row.get("minority_interest")
    r["preferred_equity"] = edgar_row.get("preferred_equity")
    # TTM provenance passthrough (audit Y6): downstream can distinguish a
    # real roll-forward TTM from an FY served as TTM, and see staleness.
    for _pv in ("revenue_ttm_end", "revenue_ttm_kind", "cfo_ttm_end",
                "cfo_ttm_kind", "netinc_ttm_end", "netinc_ttm_kind"):
        if edgar_row.get(_pv) is not None:
            r[_pv] = edgar_row.get(_pv)
    if price_row is not None and price_row.get("price_asof") is not None:
        r["price_asof"] = price_row.get("price_asof")
    r["eps_basic_ttm"] = edgar_row.get("eps_basic_ttm")
    r["eps_diluted_ttm"] = edgar_row.get("eps_diluted_ttm")

    # Margins
    r["ebitda_margin"] = edgar_row.get("ebitda_margin")
    r["op_margin"] = edgar_row.get("op_margin")
    r["net_margin"] = edgar_row.get("net_margin")
    r["fcf_margin"] = edgar_row.get("fcf_margin")
    r["gross_margin"] = None  # not separately extracted from XBRL; left for downstream

    # Quality / capital efficiency
    # positive-EBITDA guard: CFO over a NEGATIVE EBITDA prints a
    # sign-flipped "conversion" (both-negative reads healthy); and a
    # legitimate zero CFO must not be dropped by truthiness.
    if r.get("cfo_ttm") is not None and r.get("ebitda_ttm") is not None \
            and not pd.isna(r["cfo_ttm"]) and not pd.isna(r["ebitda_ttm"]) \
            and r["ebitda_ttm"] > 0:
        r["cash_conversion"] = r["cfo_ttm"] / r["ebitda_ttm"]
    r["roce"] = edgar_row.get("roce")
    # net_debt/EBITDA: EBITDA must be POSITIVE (negative EBITDA under
    # positive debt printed a negative ratio any "nde < x" screen reads
    # as net cash — sign-inverted risk); and a debt-free company
    # (total_debt == 0) is a MEANINGFUL net-cash ratio, not a skip.
    _td_map = edgar_row.get("total_debt")
    _eb_map = edgar_row.get("ebitda_ttm")
    if _td_map is not None and not pd.isna(_td_map) \
            and _eb_map is not None and not pd.isna(_eb_map) and _eb_map > 0:
        nd = _td_map - (edgar_row.get("cash") or 0)
        r["net_debt_ebitda"] = nd / _eb_map
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
    # (audit Y1) the payout YIELDS are NOT written here any more — a yield
    # frozen against the map-time mcap goes stale the moment price moves.
    # The audited LEVELS below are the payload; the harmonizer recomputes
    # capital_return_yield / buyback_yield from them against the CURRENT
    # market cap on every run. dividend_yield stays Yahoo-fresh there too.
    # store the LEVELS too — a yield frozen against map-time mcap goes
    # stale the moment price moves; the harmonizer recomputes the yields
    # from these audited flows against the CURRENT mcap every run.
    for _lvl_k in ("capital_return_ttm", "dividends_ttm", "buybacks_ttm"):
        if edgar_row.get(_lvl_k) is not None:
            r[_lvl_k] = edgar_row[_lvl_k]

    # Tangible book per share
    if edgar_row.get("tangible_book_per_share"):
        r["tangible_book_per_share"] = edgar_row["tangible_book_per_share"]
        if price:
            r["pct_above_tb"] = (price - edgar_row["tangible_book_per_share"]) / edgar_row["tangible_book_per_share"]

    # NCAV (Graham, concepts review): the COMMON holder's claim — current
    # assets minus total liabilities minus claims senior/parallel to common
    # (preferred stock; noncontrolling interests sit in EQUITY under GAAP so
    # "Liabilities" never includes them). Unobserved legitimately means none.
    if edgar_row.get("current_assets") is not None and edgar_row.get("liabilities") is not None:
        def _nz(k):
            v = edgar_row.get(k)
            return 0.0 if (v is None or pd.isna(v)) else float(v)
        ncav = (edgar_row["current_assets"] - edgar_row["liabilities"]
                - _nz("preferred_equity") - _nz("minority_interest"))
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
