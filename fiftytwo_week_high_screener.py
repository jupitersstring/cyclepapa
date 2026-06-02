"""52-week-high screener with valuation-on-growth overlay.

Surfaces the rare setups where a stock is making 52-week highs (absolute
and/or vs the benchmark) BUT remains cheap on growth-adjusted multiples:

  EV/EBITDA / EBITDA growth      — PEG-style using enterprise multiple
  EV/EBITDA / sales growth       — PEG-style with sales growth
  EV/EBITDA on its own           — absolute cheapness
  P/B                            — book-value floor

This is the GARP-at-breakout intersection: momentum + value. Most breakouts
re-rate the multiple; the rare names that don't are usually under-followed
or just-turning-the-corner.

Inputs (all cached from prior runs):
  .cache/yf/{ticker}__price.parquet    -- daily Close prices
  .cache/yf/{ticker}__info_metrics.parquet  -- valuation snapshot
  universe_three_window.csv             -- growth_windows from US-wide run
  results_uk/growth_uk.csv              -- UK-specific growth
  results_canada/growth_windows.csv     -- Canada
  results_eu_relaxed/growth_windows.csv -- EU

Output: results_52wh/screener.csv
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd
pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)

CACHE = Path('.cache/yf')
OUTDIR = Path('results_52wh'); OUTDIR.mkdir(exist_ok=True)
BENCH = '_GSPC'   # ^GSPC stored with safe filename


def _safe(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)


def load_price(ticker: str) -> Optional[pd.Series]:
    p = CACHE / f'{_safe(ticker)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Close' not in df.columns: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if getattr(s.index, 'tz', None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception:
        return None


def load_info(ticker: str) -> dict:
    p = CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        if d.empty: return {}
        return d.iloc[0].to_dict()
    except Exception:
        return {}


def fifty_two_week_metrics(price: pd.Series, bench: pd.Series,
                            window_days: int = 252) -> dict:
    """52-week-high metrics: absolute and benchmark-relative."""
    out = {}
    if price is None or len(price) < window_days:
        return out

    latest = float(price.iloc[-1])
    window = price.tail(window_days)
    hi = float(window.max())
    lo = float(window.min())
    out['price_latest']  = latest
    out['52w_high']      = hi
    out['52w_low']       = lo
    out['pct_off_high']  = (latest / hi - 1) * 100 if hi > 0 else float('nan')
    out['pct_from_low']  = (latest / lo - 1) * 100 if lo > 0 else float('nan')
    out['at_52w_high']   = latest >= hi * 0.98          # within 2% of high
    out['new_52w_high']  = latest >= window.iloc[:-5].max() * 1.001  # exceeds last 247 by 0.1%

    # SPX-relative: build ratio series, then 52-w high on the ratio
    if bench is not None and not bench.empty:
        b = bench.reindex(price.index).ffill()
        if b.notna().sum() >= window_days:
            rel = (price / b).dropna()
            rel_win = rel.tail(window_days)
            rel_latest = float(rel.iloc[-1])
            rel_hi = float(rel_win.max())
            out['rel_pct_off_high'] = (rel_latest / rel_hi - 1) * 100 if rel_hi > 0 else float('nan')
            out['rel_at_52w_high']  = rel_latest >= rel_hi * 0.98
            out['rel_new_52w_high'] = rel_latest >= rel_win.iloc[:-5].max() * 1.001
    return out


def main():
    # Build a unified universe across all regions: load every available growth file
    # so we have growth rates for each ticker.
    growth_sources = {
        'us_wide':    Path('results_us_wide/growth_windows.csv'),
        'eu_relaxed': Path('results_eu_relaxed/growth_windows.csv'),
        'canada':     Path('results_canada/growth_windows.csv'),
    }
    growth_frames = {}
    for label, p in growth_sources.items():
        if not p.exists(): continue
        df = pd.read_csv(p)
        df['_source'] = label
        growth_frames[label] = df

    if not growth_frames:
        print("No growth_windows files found.")
        return

    gw = pd.concat(growth_frames.values(), ignore_index=True)
    # Per (ticker, metric) keep the row with most history
    gw = gw.sort_values('n_history', ascending=False).drop_duplicates(['ticker','metric'])

    # UK growth file has different schema (uk_scanner output)
    uk_path = Path('results_uk/growth_uk.csv')
    uk_growth = None
    if uk_path.exists():
        uk = pd.read_csv(uk_path, index_col=0)
        uk_growth = uk

    # Pivot growth to wide: ticker × metric, with LTM growth
    rev_ltm = gw[gw['metric']=='revenue'].set_index('ticker')['ltm']
    ebitda_ltm = gw[gw['metric']=='ebitda'].set_index('ticker')['ltm']
    fcf_ltm = gw[gw['metric']=='fcf'].set_index('ticker')['ltm']
    rev_yoy = gw[gw['metric']=='revenue'].set_index('ticker')['yoy']
    ebitda_yoy = gw[gw['metric']=='ebitda'].set_index('ticker')['yoy']

    # Universe = all tickers with at least some growth data
    all_tickers = set(gw['ticker'].unique())
    if uk_growth is not None:
        all_tickers.update(uk_growth.index.astype(str))

    # ALSO include every ticker with a price + info_metrics in the cache
    # (compute growth on-the-fly from yfinance income for these), so we
    # cover Japan/Korea/HK/Australia/etc that weren't in any multi_variant run.
    price_only_universe = {p.name.split('__')[0]
                            for p in CACHE.glob('*__price.parquet')}
    info_universe = {p.name.split('__')[0]
                      for p in CACHE.glob('*__info_metrics.parquet')}
    cache_universe = price_only_universe & info_universe
    new_tickers = cache_universe - all_tickers
    all_tickers |= cache_universe
    print(f"Universe: {len(all_tickers)} tickers ({len(new_tickers)} added from full cache)")

    # Helper to compute LTM rev/EBITDA growth from cached income for tickers
    # without growth_windows entries
    def cache_growth(tk):
        p = CACHE / f'{_safe(tk)}__income.parquet'
        if not p.exists(): return None, None
        try:
            inc = pd.read_parquet(p)
        except Exception: return None, None
        if inc.empty: return None, None
        # Schema detection: dates in index (US/EU) or in columns (Korea/Asia)
        items_in_index = pd.api.types.is_datetime64_any_dtype(inc.columns) or \
                         any(isinstance(c, pd.Timestamp) for c in inc.columns[:3])
        def getseries(cands):
            for c in cands:
                if items_in_index:
                    matches = [ix for ix in inc.index if str(ix) == c or str(ix).startswith(c[:10])]
                    if matches:
                        s = pd.to_numeric(inc.loc[matches[0]], errors='coerce').dropna()
                        if not s.empty: return s.sort_index()
                else:
                    if c in inc.columns:
                        s = pd.to_numeric(inc[c], errors='coerce').dropna()
                        if not s.empty: return s.sort_index()
            return None
        rev = getseries(['Total Revenue','Revenue'])
        ebd = getseries(['Normalized EBITDA','EBITDA'])
        # YoY: latest vs same period prior year (5 quarters back) if quarterly
        def yoy(s):
            if s is None or len(s) < 2: return None
            if len(s) >= 5:
                cur, prv = float(s.iloc[-1]), float(s.iloc[-5])
            else:
                cur, prv = float(s.iloc[-1]), float(s.iloc[0])
            return (cur/prv - 1) * 100 if prv > 0 else None
        return yoy(rev), yoy(ebd)

    # Benchmark
    bench = load_price('^GSPC')
    if bench is None or bench.empty:
        bench = load_price('_GSPC')
    if bench is None or bench.empty:
        p = CACHE / '_GSPC__price.parquet'
        if p.exists():
            try:
                df = pd.read_parquet(p)
                bench = pd.to_numeric(df['Close'], errors='coerce').dropna()
                if getattr(bench.index,'tz',None) is not None:
                    bench.index = bench.index.tz_localize(None)
                bench = bench.sort_index()
            except Exception: bench = None
    if bench is None:
        print("WARNING: no benchmark prices found; SPX-relative metrics will be NaN")

    rows = []
    skipped_no_price = 0
    for tkr in all_tickers:
        price = load_price(tkr)
        if price is None:
            skipped_no_price += 1; continue
        m52 = fifty_two_week_metrics(price, bench)
        if not m52: continue
        info = load_info(tkr)

        # Cheap-on-growth ratios. Use LTM growth, clip absurd small denominators.
        ev_ebitda = info.get('enterpriseToEbitda')
        pb        = info.get('priceToBook')
        ps        = info.get('priceToSalesTrailing12Months')
        mcap      = info.get('marketCap')
        pe        = info.get('trailingPE')

        # Growth rates (LTM symmetric)
        r_g  = rev_ltm.get(tkr)
        eb_g = ebitda_ltm.get(tkr)
        ry_g = rev_yoy.get(tkr)
        eb_y = ebitda_yoy.get(tkr)

        # UK uses different naming
        if uk_growth is not None and tkr in uk_growth.index:
            ur = uk_growth.loc[tkr]
            if pd.isna(r_g): r_g = ur.get('revenue_ltm_chg') or ur.get('revenue_yoy_a')
            if pd.isna(eb_g): eb_g = ur.get('ebitda_ltm_chg') or ur.get('ebitda_yoy_a')

        # Fallback: compute growth from cached income for tickers without
        # any growth_windows entry (Japan/Korea/HK/Australia/etc.)
        if pd.isna(r_g) and pd.isna(eb_g):
            rev_cache, ebd_cache = cache_growth(tkr)
            # express as fraction (the LTM column is in fraction form)
            if rev_cache is not None: r_g = rev_cache / 100
            if ebd_cache is not None: eb_g = ebd_cache / 100
            if pd.isna(ry_g) and rev_cache is not None: ry_g = rev_cache / 100
            if pd.isna(eb_y) and ebd_cache is not None: eb_y = ebd_cache / 100

        def safe_div(num, den):
            try:
                n = float(num); d = float(den)
                if d <= 0.05 or not np.isfinite(n) or not np.isfinite(d): return float('nan')
                return n / d
            except (TypeError, ValueError):
                return float('nan')

        evebitda_per_rev_growth = safe_div(ev_ebitda, r_g)
        evebitda_per_ebitda_growth = safe_div(ev_ebitda, eb_g)

        rows.append({
            'ticker': tkr,
            'market_cap': mcap,
            **m52,
            'ev_ebitda': ev_ebitda,
            'priceToBook': pb,
            'priceToSales': ps,
            'pe': pe,
            'revenue_growth_ltm': r_g,
            'ebitda_growth_ltm': eb_g,
            'evebitda_per_revg': evebitda_per_rev_growth,
            'evebitda_per_ebitdag': evebitda_per_ebitda_growth,
        })

    print(f"Built rows for {len(rows)} tickers (skipped {skipped_no_price} without prices)")
    df = pd.DataFrame(rows).set_index('ticker')
    df.to_csv(OUTDIR / 'screener.csv')

    # The killer filter: at 52w high (absolute OR relative) AND cheap-on-growth
    target = df.copy()
    # Convert boolean flags safely
    target['at_52w'] = target['at_52w_high'].fillna(False).astype(bool)
    target['rel_at_52w'] = target.get('rel_at_52w_high', pd.Series(False, index=target.index)).fillna(False).astype(bool)
    target['new_52w'] = target['new_52w_high'].fillna(False).astype(bool)
    target['rel_new_52w'] = target.get('rel_new_52w_high', pd.Series(False, index=target.index)).fillna(False).astype(bool)

    target = target[(target['market_cap'].fillna(0) > 200e6)]   # >$200M

    print()
    print("=" * 100)
    print("AT 52-WEEK HIGH (abs OR vs SPX) + CHEAP ON GROWTH")
    print("=" * 100)
    flag52 = target['at_52w'] | target['rel_at_52w']
    pos_growth = (target['ebitda_growth_ltm'].fillna(0) > 0.05) | (target['revenue_growth_ltm'].fillna(0) > 0.05)
    cheap_evpgrowth = (target['evebitda_per_ebitdag'].between(0, 30)) | (target['evebitda_per_revg'].between(0, 30))
    cheap_pb = target['priceToBook'].between(0, 2.5)

    setup = target[flag52 & pos_growth & (cheap_evpgrowth | cheap_pb)]
    setup = setup.sort_values('evebitda_per_ebitdag').head(40)

    cols = ['market_cap','price_latest','pct_off_high','rel_pct_off_high',
            'ev_ebitda','priceToBook','revenue_growth_ltm','ebitda_growth_ltm',
            'evebitda_per_revg','evebitda_per_ebitdag','at_52w','rel_at_52w']
    cols = [c for c in cols if c in setup.columns]
    show = setup[cols].copy()
    if 'market_cap' in show: show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('revenue_growth_ltm','ebitda_growth_ltm'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').apply(lambda x: f"{x*100:+.0f}%" if pd.notna(x) else "")
    for c in ('ev_ebitda','priceToBook','evebitda_per_revg','evebitda_per_ebitdag'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    for c in ('pct_off_high','rel_pct_off_high'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    print(f"Count: {len(setup)} names\n")
    print(show.to_string())

    print()
    print("=" * 100)
    print("NEW 52-WEEK HIGH (just broke out) + CHEAP ON GROWTH (rarest)")
    print("=" * 100)
    nh = target[(target['new_52w'] | target['rel_new_52w'])
                & pos_growth & (cheap_evpgrowth | cheap_pb)]
    nh = nh.sort_values('evebitda_per_ebitdag').head(25)
    show = nh[cols].copy()
    if 'market_cap' in show: show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('revenue_growth_ltm','ebitda_growth_ltm'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').apply(lambda x: f"{x*100:+.0f}%" if pd.notna(x) else "")
    for c in ('ev_ebitda','priceToBook','evebitda_per_revg','evebitda_per_ebitdag'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    for c in ('pct_off_high','rel_pct_off_high'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    print(f"Count: {len(nh)} names\n")
    print(show.to_string())


if __name__ == '__main__':
    main()
