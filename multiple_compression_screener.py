"""Multiple-compression screener.

Finds tickers where:
  1. Earnings (EPS or net income) are growing YoY
  2. Stock has become CHEAPER on book or earnings basis -- i.e., price has
     lagged the earnings growth, mechanically compressing the multiple
  3. (Optional flag, not a filter): below 200-week SMA

The setup: fundamentals improving while the market multiple contracts.
Classic value-with-catalyst pattern -- either the market doesn't yet
believe the earnings will hold, or it's late-cycle multiple compression
even as the operating story keeps working.

Methodology (per ticker):
  eps_now    = latest LTM EPS (sum of last 4 quarters)
  eps_y_ago  = LTM EPS 4 quarters earlier  (non-overlapping)
  eps_growth = (eps_now - eps_y_ago) / |eps_y_ago|   -- positive = growing
  price_now  = latest close
  price_y    = close from ~252 trading days ago
  price_chg  = price_now / price_y - 1
  multiple_compression = price_chg - eps_growth      -- negative = cheaper now
  pe_now     = price_now / eps_now                  (if eps_now > 0)
  pe_y_ago   = price_y / eps_y_ago                  (if eps_y_ago > 0)
  pe_change  = pe_now - pe_y_ago                    -- negative = cheaper

  pb_now     = current P/B from yfinance.info
  implied_pb_y_ago = pb_now * (price_y / price_now)  -- approximate
  pb_change  = pb_now - implied_pb_y_ago

  sma_200w   = mean of last 200 weekly closes (weekly resample)
  below_200w = price_now < sma_200w

Output: results_multiple_compression/screener.csv

Filter (default): eps_growth > 0.05 AND (pe_change < 0 OR pb_change < 0 OR
                                            multiple_compression < -0.05)
"""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR_CACHE = Path('.cache/edgar')
OUTDIR = Path('results_multiple_compression'); OUTDIR.mkdir(exist_ok=True)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_price(ticker: str) -> Optional[pd.Series]:
    p = CACHE / f'{_safe(ticker)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Close' not in df.columns: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if getattr(s.index,'tz',None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception:
        return None


def load_eps_history(ticker: str) -> Optional[pd.Series]:
    """Quarterly EPS history. Prefer EDGAR-derived eps_diluted if cached;
    fall back to yfinance get_earnings_dates."""
    # yfinance EPS cache
    p = CACHE / f'{_safe(ticker)}__eps_history.parquet'
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if not df.empty and 'Reported EPS' in df.columns:
                s = pd.to_numeric(df['Reported EPS'], errors='coerce').dropna()
                if getattr(s.index,'tz',None) is not None:
                    s.index = s.index.tz_localize(None)
                return s.sort_index()
        except Exception: pass
    return None


def load_info(ticker: str) -> dict:
    p = CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        if d.empty: return {}
        return d.iloc[0].to_dict()
    except Exception: return {}


def load_ebitda_quarterly(ticker: str) -> Optional[pd.Series]:
    """Reconstruct quarterly EBITDA from cached income statement.
    Prefer 'EBITDA' line; fall back to 'Operating Income' + 'D&A' if missing."""
    p = CACHE / f'{_safe(ticker)}__income.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df is None or df.empty: return None
        items_in_index = (pd.api.types.is_datetime64_any_dtype(df.columns)
                          or any(isinstance(c, pd.Timestamp) for c in df.columns[:3]))
        def _row(*names):
            for n in names:
                if items_in_index:
                    for ix in df.index:
                        if str(ix).strip() == n:
                            return pd.to_numeric(df.loc[ix], errors='coerce').dropna()
                else:
                    if n in df.columns:
                        return pd.to_numeric(df[n], errors='coerce').dropna()
            return None
        ebitda = _row('EBITDA','Normalized EBITDA')
        if ebitda is None:
            op = _row('Operating Income','Operating Income or Loss')
            da = _row('Reconciled Depreciation','Depreciation And Amortization','Depreciation')
            if op is not None and da is not None:
                idx = op.index.intersection(da.index)
                ebitda = (op.reindex(idx) + da.reindex(idx).abs()).dropna()
        if ebitda is None or ebitda.empty: return None
        # If indexed by datetime, sort. If transposed (columns as dates), pandas dot-on-row should already be a Series indexed by date.
        if not isinstance(ebitda.index, pd.DatetimeIndex):
            ebitda.index = pd.to_datetime(ebitda.index, errors='coerce')
            ebitda = ebitda.dropna()
        return ebitda.sort_index()
    except Exception:
        return None


def _historical_multiples(price: pd.Series, eps_q: pd.Series,
                          ebitda_q: Optional[pd.Series],
                          shares_out: Optional[float],
                          net_debt_now: Optional[float],
                          lookback_years: int = 5) -> dict:
    """Reconstruct historical P/E and EV/EBITDA series from price + rolling-4Q
    EPS + rolling-4Q EBITDA. Return:
      pe_peak / ev_peak (max over lookback window, with dates)
      pe_y_ago_recon / ev_y_ago_recon (value approximately 12 months ago)

    EV approximation: shares_out and net_debt held constant at current values.
    This biases historical EV LOWER (debt typically accumulates), which means
    the peak EV/EBITDA estimate is conservative — under-reports compression.
    """
    out = {'pe_peak': None, 'pe_peak_date': None,
           'ev_peak': None, 'ev_peak_date': None,
           'pe_y_ago_recon': None, 'ev_y_ago_recon': None}
    if price is None or eps_q is None or len(eps_q) < 4:
        return out
    eps_q = eps_q.sort_index()
    # De-duplicate index (some EPS series have duplicated quarter-end dates)
    if eps_q.index.has_duplicates:
        eps_q = eps_q[~eps_q.index.duplicated(keep='last')]
    eps_ltm = eps_q.rolling(4).sum().dropna()
    if eps_ltm.empty: return out
    if eps_ltm.index.has_duplicates:
        eps_ltm = eps_ltm[~eps_ltm.index.duplicated(keep='last')]
    price = price.sort_index()
    if price.index.has_duplicates:
        price = price[~price.index.duplicated(keep='last')]
    eps_daily = eps_ltm.reindex(price.index, method='ffill').dropna()
    if eps_daily.empty: return out
    cutoff = price.index[-1] - pd.Timedelta(days=365 * lookback_years)
    p_window = price[price.index >= cutoff].copy()
    eps_window = eps_daily.reindex(p_window.index, method='ffill').dropna()
    if eps_window.empty: return out
    common = p_window.index.intersection(eps_window.index)
    if len(common) < 30: return out
    pe_series = (p_window.loc[common] / eps_window.loc[common]).where(eps_window.loc[common] > 0).dropna()
    if not pe_series.empty:
        out['pe_peak'] = float(pe_series.max())
        out['pe_peak_date'] = pe_series.idxmax()
        # PE at ~1y ago
        target = price.index[-1] - pd.Timedelta(days=365)
        prior = pe_series[pe_series.index <= target]
        if not prior.empty:
            out['pe_y_ago_recon'] = float(prior.iloc[-1])
    if ebitda_q is not None and shares_out and shares_out > 0:
        ebitda_ltm = ebitda_q.sort_index().rolling(4).sum().dropna()
        if not ebitda_ltm.empty:
            ebitda_daily = ebitda_ltm.reindex(p_window.index, method='ffill').dropna()
            common2 = p_window.index.intersection(ebitda_daily.index)
            if len(common2) >= 30:
                mcap_t = p_window.loc[common2] * float(shares_out)
                ev_t = mcap_t + (net_debt_now if net_debt_now is not None else 0)
                ev_series = (ev_t / ebitda_daily.loc[common2]).where(ebitda_daily.loc[common2] > 0).dropna()
                if not ev_series.empty:
                    out['ev_peak'] = float(ev_series.max())
                    out['ev_peak_date'] = ev_series.idxmax()
                    target = price.index[-1] - pd.Timedelta(days=365)
                    prior = ev_series[ev_series.index <= target]
                    if not prior.empty:
                        out['ev_y_ago_recon'] = float(prior.iloc[-1])
    return out


def analyze(ticker: str) -> Optional[dict]:
    price = load_price(ticker)
    if price is None or len(price) < 260: return None
    eps = load_eps_history(ticker)
    if eps is None or len(eps) < 8: return None
    info = load_info(ticker)

    # LTM EPS now and 4Q ago (non-overlapping)
    eps_sorted = eps.sort_index()
    ltm_series = eps_sorted.rolling(4).sum().dropna()
    if len(ltm_series) < 5: return None
    eps_now = float(ltm_series.iloc[-1])
    eps_y_ago = float(ltm_series.iloc[-5])  # 4 quarters earlier
    if eps_y_ago == 0:
        eps_growth = float('nan')
    else:
        eps_growth = (eps_now - eps_y_ago) / abs(eps_y_ago)

    # Price now vs ~12 months ago
    price_now = float(price.iloc[-1])
    target_date = price.index[-1] - pd.Timedelta(days=365)
    prev_prices = price[price.index <= target_date]
    if prev_prices.empty: return None
    price_y_ago = float(prev_prices.iloc[-1])
    price_change = (price_now / price_y_ago) - 1 if price_y_ago > 0 else float('nan')

    # Multiple compression (YoY)
    if pd.notna(eps_growth) and pd.notna(price_change):
        multiple_compression = price_change - eps_growth
    else:
        multiple_compression = float('nan')

    # P/E now / y-ago
    pe_now = price_now / eps_now if eps_now > 0 else float('nan')
    pe_y_ago = price_y_ago / eps_y_ago if eps_y_ago > 0 else float('nan')
    pe_change_pct = ((pe_now - pe_y_ago) / pe_y_ago) if (pd.notna(pe_now) and pd.notna(pe_y_ago) and pe_y_ago > 0) else float('nan')

    # P/B approx
    pb_now = info.get('priceToBook')
    try: pb_now = float(pb_now) if pb_now is not None else float('nan')
    except (TypeError, ValueError): pb_now = float('nan')
    if pd.notna(pb_now) and price_y_ago > 0:
        pb_implied_y_ago = pb_now * (price_y_ago / price_now)
        pb_change_pct = (pb_now - pb_implied_y_ago) / pb_implied_y_ago
    else:
        pb_implied_y_ago = float('nan'); pb_change_pct = float('nan')

    # === PEAK MULTIPLES — turns and % off peak ===
    shares_out = info.get('sharesOutstanding')
    try: shares_out = float(shares_out) if shares_out else None
    except: shares_out = None
    # Net debt = totalDebt - totalCash (yfinance scalars)
    td = info.get('totalDebt'); tc = info.get('totalCash')
    try: net_debt_now = (float(td) if td else 0) - (float(tc) if tc else 0)
    except: net_debt_now = None
    # EBITDA from cached income_stmt
    ebitda_q = load_ebitda_quarterly(ticker)

    h = _historical_multiples(price, eps_sorted, ebitda_q, shares_out, net_debt_now,
                              lookback_years=5)
    pe_peak       = h['pe_peak']
    pe_peak_date  = h['pe_peak_date']
    ev_peak       = h['ev_peak']
    ev_peak_date  = h['ev_peak_date']
    pe_y_ago_recon = h['pe_y_ago_recon']
    ev_y_ago_recon = h['ev_y_ago_recon']

    # EV/EBITDA now: prefer info.enterpriseToEbitda
    ev_ebitda_now = info.get('enterpriseToEbitda')
    try: ev_ebitda_now = float(ev_ebitda_now) if ev_ebitda_now is not None else float('nan')
    except: ev_ebitda_now = float('nan')

    # Peak comparison (turns + %)
    pe_turns_off_peak = (pe_now - pe_peak) if (pd.notna(pe_now) and pe_peak) else float('nan')
    pe_pct_off_peak   = ((pe_now / pe_peak - 1) * 100) if (pd.notna(pe_now) and pe_peak and pe_peak > 0) else float('nan')
    ev_turns_off_peak = (ev_ebitda_now - ev_peak) if (pd.notna(ev_ebitda_now) and ev_peak) else float('nan')
    ev_pct_off_peak   = ((ev_ebitda_now / ev_peak - 1) * 100) if (pd.notna(ev_ebitda_now) and ev_peak and ev_peak > 0) else float('nan')

    # YoY in turns (price-derived, more reliable than scalar pe_y_ago)
    pe_turns_yoy = (pe_now - pe_y_ago) if (pd.notna(pe_now) and pd.notna(pe_y_ago)) else float('nan')
    ev_turns_yoy = (ev_ebitda_now - ev_y_ago_recon) if (pd.notna(ev_ebitda_now) and ev_y_ago_recon) else float('nan')
    ev_yoy_pct = ((ev_ebitda_now / ev_y_ago_recon - 1) * 100) if (pd.notna(ev_ebitda_now) and ev_y_ago_recon and ev_y_ago_recon > 0) else float('nan')

    # 200-week SMA
    weekly = price.resample('W').last().dropna()
    if len(weekly) >= 50:
        sma_window = min(200, len(weekly))
        sma_200w = float(weekly.tail(sma_window).mean())
        below_200w = price_now < sma_200w
        pct_off_sma = (price_now / sma_200w - 1) * 100
    else:
        sma_200w = float('nan'); below_200w = False; pct_off_sma = float('nan')

    return {
        'ticker': ticker,
        'price_now': price_now,
        'price_y_ago': price_y_ago,
        'price_change_pct': price_change * 100 if pd.notna(price_change) else float('nan'),
        'eps_now_ltm': eps_now,
        'eps_y_ago_ltm': eps_y_ago,
        'eps_growth_pct': eps_growth * 100 if pd.notna(eps_growth) else float('nan'),
        'multiple_compression_pct': multiple_compression * 100 if pd.notna(multiple_compression) else float('nan'),
        # Year-over-year (turns and %)
        'pe_now': pe_now,
        'pe_y_ago': pe_y_ago,
        'pe_change_pct': pe_change_pct * 100 if pd.notna(pe_change_pct) else float('nan'),
        'pe_turns_yoy': pe_turns_yoy,
        'ev_ebitda_now': ev_ebitda_now,
        'ev_ebitda_y_ago_recon': ev_y_ago_recon,
        'ev_turns_yoy': ev_turns_yoy,
        'ev_yoy_pct': ev_yoy_pct,
        # Peak-vs-now (turns and %)
        'pe_peak_5y': pe_peak,
        'pe_peak_date': pe_peak_date.date().isoformat() if pe_peak_date is not None else None,
        'pe_turns_off_peak': pe_turns_off_peak,
        'pe_pct_off_peak': pe_pct_off_peak,
        'ev_ebitda_peak_5y': ev_peak,
        'ev_peak_date': ev_peak_date.date().isoformat() if ev_peak_date is not None else None,
        'ev_turns_off_peak': ev_turns_off_peak,
        'ev_pct_off_peak': ev_pct_off_peak,
        # P/B (existing)
        'pb_now': pb_now,
        'pb_implied_y_ago': pb_implied_y_ago,
        'pb_change_pct': pb_change_pct * 100 if pd.notna(pb_change_pct) else float('nan'),
        # Momentum context
        'sma_200w': sma_200w,
        'pct_off_sma_200w': pct_off_sma,
        'below_200w': below_200w,
        'market_cap': info.get('marketCap'),
        'priceToSales': info.get('priceToSalesTrailing12Months'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6, help='min market cap')
    ap.add_argument('--min-eps-growth', type=float, default=0.05, help='min EPS YoY growth')
    ap.add_argument('--require-compression', action='store_true',
                    help='require multiple_compression < -5%% (price lagged eps growth)')
    args = ap.parse_args()

    # Universe = all tickers with BOTH cached price AND eps_history (we need EPS
    # series to build the historical multiple. Names lacking EPS get skipped
    # silently in analyze().)
    eps_tickers = {f.name.split('__')[0] for f in CACHE.glob('*__eps_history.parquet')}
    pr_tickers  = {f.name.split('__')[0] for f in CACHE.glob('*__price.parquet')}
    tickers = sorted(eps_tickers & pr_tickers)
    print(f"Candidates with cached price + eps history: {len(tickers)}")
    # yfinance safe-name → ticker (most are identical)
    rows = []
    for tkr in tickers:
        # Restore yfinance ticker form
        yfticker = tkr.replace('_','^') if tkr.startswith('_') else tkr
        r = analyze(yfticker)
        if r is not None: rows.append(r)
    print(f"Computed metrics for {len(rows)} tickers")
    df = pd.DataFrame(rows).set_index('ticker')
    df.to_csv(OUTDIR / 'all.csv')

    # Apply filter
    f = df[
        (df['market_cap'].fillna(0) > args.min_mcap)
        & (df['eps_growth_pct'].fillna(-999) > args.min_eps_growth * 100)
        & (
            (df['pe_change_pct'] < 0)
            | (df['pb_change_pct'] < 0)
            | (df['multiple_compression_pct'] < -5)
        )
    ].copy()
    if args.require_compression:
        f = f[f['multiple_compression_pct'] < -5]
    # Sort by largest compression
    f = f.sort_values('multiple_compression_pct')
    f.to_csv(OUTDIR / 'screener.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print(f"\n=== EARNINGS GROWING + GETTING CHEAPER ON BOOK OR EARNINGS ===")
    print(f"Filter: market_cap > ${args.min_mcap/1e6:.0f}M, EPS YoY > {args.min_eps_growth*100:.0f}%, "
          f"AND (PE down OR PB down OR price lagged EPS by 5pp)")
    print(f"Count: {len(f)} names\n")

    cols = ['eps_growth_pct','price_change_pct','multiple_compression_pct',
            'pe_now','pe_y_ago','pe_turns_yoy','pe_change_pct',
            'pe_peak_5y','pe_turns_off_peak','pe_pct_off_peak',
            'ev_ebitda_now','ev_ebitda_peak_5y','ev_turns_off_peak','ev_pct_off_peak',
            'pb_now','pb_change_pct',
            'market_cap','priceToSales','pct_off_sma_200w','below_200w']
    show = f.head(40)[cols].copy()
    show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('pe_now','pe_y_ago','pe_peak_5y','pe_turns_off_peak','pe_turns_yoy',
              'ev_ebitda_now','ev_ebitda_peak_5y','ev_turns_off_peak',
              'pb_now','priceToSales'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    for c in ('eps_growth_pct','price_change_pct','multiple_compression_pct',
              'pe_change_pct','pe_pct_off_peak','ev_pct_off_peak','pb_change_pct','pct_off_sma_200w'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    print(show.to_string())

    # Also show: the set below 200w SMA (often the deepest setups)
    print()
    print("=== ALSO BELOW 200-WEEK SMA (deeper drawdown subset) ===")
    bsma = f[f['below_200w'] == True].sort_values('multiple_compression_pct')
    print(f"Count: {len(bsma)} names\n")
    show2 = bsma.head(30)[cols].copy()
    show2['market_cap'] = (pd.to_numeric(show2['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('pe_now','pe_y_ago','pe_peak_5y','pe_turns_off_peak','pe_turns_yoy',
              'ev_ebitda_now','ev_ebitda_peak_5y','ev_turns_off_peak',
              'pb_now','priceToSales'):
        if c in show2: show2[c] = pd.to_numeric(show2[c],errors='coerce').round(1)
    for c in ('eps_growth_pct','price_change_pct','multiple_compression_pct',
              'pe_change_pct','pe_pct_off_peak','ev_pct_off_peak','pb_change_pct','pct_off_sma_200w'):
        if c in show2: show2[c] = pd.to_numeric(show2[c],errors='coerce').round(1)
    print(show2.to_string())


if __name__ == '__main__':
    main()
