"""FCF-yield inflection & acceleration screener.

Two distinct setups it surfaces:

  1. INFLECTION  -- FCF yield (LTM FCF / share / share price) crossed from
                    negative to positive recently. The market is still
                    pricing the legacy cash-burn era; the actual cash
                    machine just turned on.

  2. ACCELERATION -- FCF yield is now higher than 4 quarters ago, which
                     is itself higher than 8 quarters ago. Each year the
                     business spits out more cash per dollar of equity
                     value. Compounding the right way.

For each ticker:
  series of LTM FCF per share at quarter-end dates
  series of price at those same dates (from cached daily, asof-aligned)
  fcf_yield_t = ltm_fcf_per_share_t / price_t

  yield_now, yield_y_ago, yield_2y_ago, yield_3y_ago
  is_inflection: yield_now > 0 AND yield_y_ago <= 0
  is_acceleration: yield_now > yield_y_ago > yield_2y_ago, all positive
  yield_trend_pp = yield_now - yield_y_ago (percentage-point change)

Default filter:
  market_cap > $200M
  AND (is_inflection OR is_acceleration)
  AND yield_now > 2% (real cash yield, not a tiny positive print)

Output: results_fcf_yield/screener.csv
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_fcf_yield'); OUTDIR.mkdir(exist_ok=True)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


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
    except Exception: return None


def load_info(ticker: str) -> dict:
    p = CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        return d.iloc[0].to_dict() if not d.empty else {}
    except Exception: return {}


_CIK_MAP = None
def cik_for(ticker: str) -> Optional[int]:
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            with open(EDGAR / 'company_tickers.json') as f:
                raw = json.load(f)
            _CIK_MAP = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}
        except Exception: _CIK_MAP = {}
    return _CIK_MAP.get(ticker.upper())


def load_edgar_fcf_ps(cik: int) -> pd.Series:
    """LTM FCF per share series (quarterly) from EDGAR XBRL."""
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return pd.Series(dtype=float)
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception: return pd.Series(dtype=float)

    import sys; sys.path.insert(0, '.')
    from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4

    def get(candidates, unit='USD'):
        for tag in candidates:
            node = facts.get(tag)
            if not node: continue
            recs = node.get('units', {}).get(unit)
            if not recs: continue
            qs = _quarterly_records(recs)
            if not qs: continue
            q, a = _series_from_records(qs)
            return _derive_q4(q, a)
        return pd.Series(dtype=float)

    ocf = get(['NetCashProvidedByUsedInOperatingActivities',
                'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'])
    capex = get(['PaymentsToAcquirePropertyPlantAndEquipment',
                  'PaymentsToAcquireProductiveAssets'])
    shares = get(['WeightedAverageNumberOfDilutedSharesOutstanding',
                   'WeightedAverageNumberOfSharesOutstandingBasic'], unit='shares')

    if ocf.empty or capex.empty or shares.empty:
        return pd.Series(dtype=float)
    idx = ocf.index.union(capex.index)
    fcf = (ocf.reindex(idx) - capex.reindex(idx).abs()).dropna()
    if fcf.empty: return pd.Series(dtype=float)
    # FCF per share at each quarter end
    idx2 = fcf.index.union(shares.index)
    fcf_ps = (fcf.reindex(idx2) / shares.reindex(idx2).replace(0, np.nan)).dropna()
    # Build LTM (rolling 4-quarter sum) of fcf per share
    fcf_ps = fcf_ps.sort_index()
    ltm_fcf_ps = fcf_ps.rolling(4).sum().dropna()
    return ltm_fcf_ps


def yield_at_dates(prices: pd.Series, ltm_fcf_ps: pd.Series) -> pd.Series:
    """For each LTM FCF/share date, compute price-aligned yield."""
    if prices is None or prices.empty or ltm_fcf_ps.empty: return pd.Series(dtype=float)
    p_at = prices.reindex(prices.index.union(ltm_fcf_ps.index)).ffill().reindex(ltm_fcf_ps.index)
    yld = ltm_fcf_ps / p_at.replace(0, np.nan)
    return yld.dropna()


def analyze(ticker: str) -> Optional[dict]:
    cik = cik_for(ticker)
    if cik is None: return None
    ltm = load_edgar_fcf_ps(cik)
    if ltm.empty or len(ltm) < 9: return None
    prices = load_price(ticker)
    if prices is None or len(prices) < 252: return None

    yld = yield_at_dates(prices, ltm)
    if len(yld) < 9: return None

    yld_now      = float(yld.iloc[-1])
    yld_y_ago    = float(yld.iloc[-5])  # 4Q back
    yld_2y_ago   = float(yld.iloc[-9])  # 8Q back
    yld_3y_ago   = float(yld.iloc[-13]) if len(yld) >= 13 else float('nan')

    is_inflection   = (yld_now > 0) and (yld_y_ago <= 0)
    is_acceleration = (yld_now > yld_y_ago > yld_2y_ago) and (yld_now > 0)
    yield_trend_pp_1y = (yld_now - yld_y_ago) * 100
    yield_trend_pp_2y = (yld_now - yld_2y_ago) * 100 if pd.notna(yld_2y_ago) else float('nan')

    # ROC of yield
    if yld_y_ago > 0:
        yield_yoy_growth_pct = (yld_now - yld_y_ago) / yld_y_ago * 100
    else:
        yield_yoy_growth_pct = float('nan')

    info = load_info(ticker)
    return {
        'ticker': ticker,
        'fcf_yield_now_pct':    yld_now * 100,
        'fcf_yield_y_ago_pct':  yld_y_ago * 100,
        'fcf_yield_2y_ago_pct': yld_2y_ago * 100,
        'fcf_yield_3y_ago_pct': yld_3y_ago * 100 if pd.notna(yld_3y_ago) else float('nan'),
        'yield_trend_pp_1y':    yield_trend_pp_1y,
        'yield_trend_pp_2y':    yield_trend_pp_2y,
        'yield_yoy_growth_pct': yield_yoy_growth_pct,
        'is_inflection':        is_inflection,
        'is_acceleration':      is_acceleration,
        'ltm_fcf_ps_now':       float(ltm.iloc[-1]),
        'market_cap':           info.get('marketCap'),
        'ev_ebitda_now':        info.get('enterpriseToEbitda'),
        'ps_now':               info.get('priceToSalesTrailing12Months'),
        'pb_now':               info.get('priceToBook'),
        'sector':               info.get('sector'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--min-yield-now', type=float, default=2.0, help='min current FCF yield (pct)')
    ap.add_argument('--mode', choices=['both','inflection','acceleration','all'], default='both')
    args = ap.parse_args()

    tickers = sorted({f.name.split('__')[0] for f in CACHE.glob('*__price.parquet')})
    print(f"Candidate tickers: {len(tickers)}")
    rows = []
    for i, tk in enumerate(tickers):
        yft = tk.replace('_','^') if tk.startswith('_') else tk
        r = analyze(yft)
        if r is not None: rows.append(r)
        if (i+1) % 500 == 0:
            print(f"  {i+1}/{len(tickers)}  rows={len(rows)}")
    if not rows:
        print("No rows survived filters; nothing to write."); return
    df = pd.DataFrame(rows).set_index('ticker')
    df.to_csv(OUTDIR / 'all.csv')
    print(f"\nWith data: {len(df)} tickers")

    f = df[df['market_cap'].fillna(0) > args.min_mcap].copy()
    if args.mode == 'inflection':
        f = f[f['is_inflection']]
    elif args.mode == 'acceleration':
        f = f[f['is_acceleration']]
    elif args.mode == 'both':
        f = f[f['is_inflection'] | f['is_acceleration']]
    f = f[f['fcf_yield_now_pct'] > args.min_yield_now]
    f = f.sort_values('fcf_yield_now_pct', ascending=False)
    f.to_csv(OUTDIR / 'screener.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print(f"\n=== FCF YIELD INFLECTIONS + ACCELERATIONS ===")
    print(f"Filter: cap>${args.min_mcap/1e6:.0f}M, FCF yield > {args.min_yield_now}%, "
          f"mode={args.mode}")
    print(f"Count: {len(f)}\n")

    cols = ['fcf_yield_now_pct','fcf_yield_y_ago_pct','fcf_yield_2y_ago_pct',
            'yield_trend_pp_1y','yield_trend_pp_2y','yield_yoy_growth_pct',
            'is_inflection','is_acceleration','ltm_fcf_ps_now',
            'ev_ebitda_now','ps_now','pb_now','market_cap','sector']
    show = f.head(40)[cols].copy()
    show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show and c not in ('market_cap','sector','is_inflection','is_acceleration','ltm_fcf_ps_now'):
            show[c] = pd.to_numeric(show[c],errors='coerce').round(2)
    if 'ltm_fcf_ps_now' in show:
        show['ltm_fcf_ps_now'] = pd.to_numeric(show['ltm_fcf_ps_now'],errors='coerce').round(2)
    if 'sector' in show:
        show['sector'] = show['sector'].apply(lambda x: x[:18] if isinstance(x,str) else x)
    print(show.to_string())

    # Inflections only
    print()
    print("=== INFLECTIONS (FCF yield crossed from negative -> positive) ===")
    infl = df[
        (df['market_cap'].fillna(0) > args.min_mcap)
        & (df['is_inflection'])
        & (df['fcf_yield_now_pct'] > args.min_yield_now)
    ].sort_values('fcf_yield_now_pct', ascending=False)
    print(f"Count: {len(infl)}\n")
    show2 = infl.head(25)[cols].copy()
    show2['market_cap'] = (pd.to_numeric(show2['market_cap'],errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show2 and c not in ('market_cap','sector','is_inflection','is_acceleration','ltm_fcf_ps_now'):
            show2[c] = pd.to_numeric(show2[c],errors='coerce').round(2)
    if 'ltm_fcf_ps_now' in show2:
        show2['ltm_fcf_ps_now'] = pd.to_numeric(show2['ltm_fcf_ps_now'],errors='coerce').round(2)
    if 'sector' in show2:
        show2['sector'] = show2['sector'].apply(lambda x: x[:18] if isinstance(x,str) else x)
    print(show2.to_string())


if __name__ == '__main__':
    main()
