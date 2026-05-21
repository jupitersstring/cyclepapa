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
    # Find price ~252 trading days before
    target_date = price.index[-1] - pd.Timedelta(days=365)
    prev_prices = price[price.index <= target_date]
    if prev_prices.empty: return None
    price_y_ago = float(prev_prices.iloc[-1])
    price_change = (price_now / price_y_ago) - 1 if price_y_ago > 0 else float('nan')

    # Multiple compression: how much LESS the price moved than earnings
    if pd.notna(eps_growth) and pd.notna(price_change):
        multiple_compression = price_change - eps_growth
    else:
        multiple_compression = float('nan')

    # P/E now and a year ago
    pe_now = price_now / eps_now if eps_now > 0 else float('nan')
    pe_y_ago = price_y_ago / eps_y_ago if eps_y_ago > 0 else float('nan')
    pe_change_pct = ((pe_now - pe_y_ago) / pe_y_ago) if (pd.notna(pe_now) and pd.notna(pe_y_ago) and pe_y_ago > 0) else float('nan')

    # P/B approximation: current P/B from info, implied year-ago P/B = current_PB * (P_y/P_now)
    pb_now = info.get('priceToBook')
    try: pb_now = float(pb_now) if pb_now is not None else float('nan')
    except (TypeError, ValueError): pb_now = float('nan')
    if pd.notna(pb_now) and price_y_ago > 0:
        pb_implied_y_ago = pb_now * (price_y_ago / price_now)
        pb_change_pct = (pb_now - pb_implied_y_ago) / pb_implied_y_ago
    else:
        pb_implied_y_ago = float('nan')
        pb_change_pct = float('nan')

    # 200-week SMA: resample to weekly, mean of last 200
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
        'pe_now': pe_now,
        'pe_y_ago': pe_y_ago,
        'pe_change_pct': pe_change_pct * 100 if pd.notna(pe_change_pct) else float('nan'),
        'pb_now': pb_now,
        'pb_implied_y_ago': pb_implied_y_ago,
        'pb_change_pct': pb_change_pct * 100 if pd.notna(pb_change_pct) else float('nan'),
        'sma_200w': sma_200w,
        'pct_off_sma_200w': pct_off_sma,
        'below_200w': below_200w,
        'market_cap': info.get('marketCap'),
        'priceToSales': info.get('priceToSalesTrailing12Months'),
        'evEbitda': info.get('enterpriseToEbitda'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6, help='min market cap')
    ap.add_argument('--min-eps-growth', type=float, default=0.05, help='min EPS YoY growth')
    ap.add_argument('--require-compression', action='store_true',
                    help='require multiple_compression < -5%% (price lagged eps growth)')
    args = ap.parse_args()

    # Universe = all tickers with cached eps_history + price
    tickers = sorted({
        f.name.split('__')[0] for f in CACHE.glob('*__eps_history.parquet')
    })
    print(f"Candidates with cached eps history: {len(tickers)}")
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
            'pe_now','pe_y_ago','pe_change_pct','pb_now','pb_change_pct',
            'market_cap','priceToSales','evEbitda','pct_off_sma_200w','below_200w']
    show = f.head(40)[cols].copy()
    show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('pe_now','pe_y_ago','pb_now','priceToSales','evEbitda'):
        show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    for c in ('eps_growth_pct','price_change_pct','multiple_compression_pct',
              'pe_change_pct','pb_change_pct','pct_off_sma_200w'):
        show[c] = pd.to_numeric(show[c],errors='coerce').round(1)
    print(show.to_string())

    # Also show: the set below 200w SMA (often the deepest setups)
    print()
    print("=== ALSO BELOW 200-WEEK SMA (deeper drawdown subset) ===")
    bsma = f[f['below_200w'] == True].sort_values('multiple_compression_pct')
    print(f"Count: {len(bsma)} names\n")
    show2 = bsma.head(30)[cols].copy()
    show2['market_cap'] = (pd.to_numeric(show2['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('pe_now','pe_y_ago','pb_now','priceToSales','evEbitda'):
        show2[c] = pd.to_numeric(show2[c],errors='coerce').round(1)
    for c in ('eps_growth_pct','price_change_pct','multiple_compression_pct',
              'pe_change_pct','pb_change_pct','pct_off_sma_200w'):
        show2[c] = pd.to_numeric(show2[c],errors='coerce').round(1)
    print(show2.to_string())


if __name__ == '__main__':
    main()
