"""Analyst & insider extras screener — ranks names by 4 new signals from
the yfinance-extras cache:

  1. upside_to_mean_target   — analyst mean target / current price - 1
  2. insider_net_pct         — net shares insiders bought (last 6m) / total
                               insider-held shares (positive = buying)
  3. consensus_buy_share     — (strongBuy + buy) / total ratings (0..1)
  4. fwd_growth_avg          — average of +1q + +1y consensus growth (decimal)

Each ticker that has ≥2 of these signals gets a composite score, ranked
within the universe. Joins with the cached info_metrics for company
name / sector / industry / country.

Output: results_extras/screener.csv
"""
from __future__ import annotations
import pandas as pd, numpy as np
from pathlib import Path

CACHE = Path('.cache/yf')
OUT = Path('results_extras'); OUT.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _load_first_row(path: Path) -> dict | None:
    if not path.exists(): return None
    try:
        df = pd.read_parquet(path)
        return df.iloc[0].to_dict() if not df.empty else None
    except Exception:
        return None


def _load_df(path: Path) -> pd.DataFrame | None:
    if not path.exists(): return None
    try:
        df = pd.read_parquet(path)
        return df if not df.empty else None
    except Exception:
        return None


def _upside(key: str) -> float | None:
    """(mean_target / current_price) - 1, expressed in %."""
    d = _load_first_row(CACHE / f'{key}__analyst_price_targets.parquet')
    if not d: return None
    cur = d.get('current'); mean = d.get('mean')
    if cur is None or mean is None or cur <= 0: return None
    return (mean / cur - 1) * 100


def _insider_net_pct(key: str) -> float | None:
    """% net shares insiders bought over the last 6m, relative to total
    insider-held shares. Positive = net buying. Yahoo presents this as
    either a fraction (0.05) or already-as-pct (5.0); we normalise to %."""
    df = _load_df(CACHE / f'{key}__insider_purchases.parquet')
    if df is None: return None
    label_col = df.columns[0]
    # Match the % row exactly (NOT the raw-shares "Net Shares Purchased (Sold)")
    row = df[df[label_col].astype(str).str.startswith('% Net Shares Purchased')]
    if row.empty: return None
    val = row.iloc[0].get('Shares')
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    # If |v| <= 1, Yahoo returned a decimal fraction → scale to %
    if abs(v) <= 1:
        v *= 100
    return v


def _consensus_buy_share(key: str) -> float | None:
    """Most recent broker recs: (strongBuy + buy) / total."""
    df = _load_df(CACHE / f'{key}__recommendations_summary.parquet')
    if df is None: return None
    # Most-recent month is 0m
    r0 = df[df['period'] == '0m']
    if r0.empty: r0 = df.head(1)
    r0 = r0.iloc[0]
    try:
        sb = float(r0.get('strongBuy', 0) or 0)
        b  = float(r0.get('buy', 0) or 0)
        h  = float(r0.get('hold', 0) or 0)
        s  = float(r0.get('sell', 0) or 0)
        ss = float(r0.get('strongSell', 0) or 0)
    except (TypeError, ValueError):
        return None
    total = sb + b + h + s + ss
    if total <= 0: return None
    return (sb + b) / total * 100


def _fwd_growth(key: str) -> float | None:
    """Average of +1q and +1y consensus growth, in % (yfinance stores decimal)."""
    df = _load_df(CACHE / f'{key}__growth_estimates.parquet')
    if df is None or 'stockTrend' not in df.columns: return None
    vals = []
    for period in ('+1q', '+1y'):
        if period in df.index:
            v = df.loc[period, 'stockTrend']
            if pd.notna(v):
                vals.append(float(v))
    if not vals: return None
    return sum(vals) / len(vals) * 100


def _company_info(key: str) -> dict:
    d = _load_first_row(CACHE / f'{key}__info_metrics.parquet') or {}
    return {
        'company': (d.get('longName') or d.get('shortName') or '')[:42],
        'sector':  d.get('sector') or '',
        'industry': d.get('industry') or '',
        'country': d.get('country') or '',
        'market_cap': d.get('marketCap'),
        'priceToBook': d.get('priceToBook'),
        'trailingPE': d.get('trailingPE'),
        'enterpriseToEbitda': d.get('enterpriseToEbitda'),
    }


_KNOWN_SUFFIXES = {'T','L','DE','F','PA','TO','V','AX','SW','MI','AS','MC','ST','OL','CO','BR',
                    'HE','IR','VI','LS','AT','KS','KQ','HK','TW','TWO','SI','NZ','TA','SS','SZ',
                    'NS','BO','SA','MX','JO','IS','BK','JK'}
def _key_to_ticker(k):
    if '_' in k:
        head, _, tail = k.rpartition('_')
        if tail in _KNOWN_SUFFIXES: return f'{head}.{tail}'
    return k


def main():
    keys = sorted({p.name.split('__')[0]
                   for p in CACHE.glob('*__info_metrics.parquet')})
    print(f'Scanning {len(keys):,} tickers...')

    rows = []
    for i, key in enumerate(keys):
        if (i + 1) % 2000 == 0:
            print(f'  {i+1:,}/{len(keys):,}  hits={len(rows):,}')

        upside = _upside(key)
        ins    = _insider_net_pct(key)
        rec    = _consensus_buy_share(key)
        fwd    = _fwd_growth(key)

        signals = [s for s in (upside, ins, rec, fwd) if s is not None]
        if len(signals) < 2:
            continue

        info = _company_info(key)
        rows.append({
            'ticker': _key_to_ticker(key),
            **info,
            'upside_to_mean_target_pct': upside,
            'insider_net_pct_6m': ins,
            'consensus_buy_share_pct': rec,
            'fwd_growth_avg_pct': fwd,
            'n_signals': len(signals),
        })

    if not rows:
        print('No hits. Has fetch_yfinance_extras populated the cache yet?')
        return
    df = pd.DataFrame(rows)

    # Composite: z-score each signal across the universe, average the
    # z-scores (higher = better). Missing signals are treated as the
    # universe median (z=0) — penalises only relative to peers, not absolute.
    for col in ('upside_to_mean_target_pct','insider_net_pct_6m',
                'consensus_buy_share_pct','fwd_growth_avg_pct'):
        s = pd.to_numeric(df[col], errors='coerce')
        z = (s - s.mean()) / s.std(ddof=0)
        df[f'_z_{col}'] = z.fillna(0)
    z_cols = [c for c in df.columns if c.startswith('_z_')]
    df['extras_composite'] = df[z_cols].mean(axis=1)
    df = df.drop(columns=z_cols)
    df = df.sort_values('extras_composite', ascending=False)
    df.to_csv(OUT / 'screener.csv', index=False)
    print(f'\nWrote {len(df):,} ranked names to {OUT/"screener.csv"}')

    cols = ['ticker','company','sector','country','upside_to_mean_target_pct',
            'insider_net_pct_6m','consensus_buy_share_pct','fwd_growth_avg_pct',
            'n_signals','extras_composite']
    cols = [c for c in cols if c in df.columns]
    show = df.head(15)[cols].copy()
    for c in ('upside_to_mean_target_pct','insider_net_pct_6m',
              'consensus_buy_share_pct','fwd_growth_avg_pct','extras_composite'):
        if c in show: show[c] = pd.to_numeric(show[c], errors='coerce').round(1)
    pd.set_option('display.width', 220); pd.set_option('display.max_columns', 20)
    print('\nTop 15:')
    print(show.to_string(index=False))


if __name__ == '__main__':
    main()
