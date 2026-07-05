"""Asymmetry scanner — hunts "1-foot hurdle" setups across the full universe.

Twelve independent scan angles, each encoding a different flavor of
asymmetric risk/reward. A name flagged by SEVERAL angles at once is the
headline output. Every scan applies currency-sanity + primary-exchange
filters first (secondary German venues and digit-prefixed London lines mix
listing-currency market caps with reporting-currency financials, producing
garbage ratios).

Scans:
  A  negative_ev        net cash > market cap, FCF-positive, real revenue
  B  fcf_machine        FCF yield 25-80% with revenue growing
  C  deep_value_growth  EV/EBITDA 0.5-4.5x with revenue growth >15%
  D  crashed_quality    down >40% in 52w, still >10% op margin + growing
  E  graham             P/E < 8, earnings growing, non-financial
  F  below_book         P/B < 0.7 while profitable (P/E 0-15)
  G  insider_cluster    insiders net-bought >20% of holdings in 6m, cheap
  H  analyst_gap        mean target >50% above price, EV/EBITDA < 10
  I  multi_screen       flagged by >=5 workbook screens and EV/EBITDA < 12
  J  unpriced_segment   top profitable+growing unpriced segment setups
  K  net_cash_growth    net cash >50% of mcap + revenue growth >10% + profit
  L  ev_fcf             EV/FCF < 5 (cash-on-cash cheapness incl. debt)

Output: results_peg/asymmetry.csv — ranked by scans-hit then avg strength.
"""
from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path('results_peg')
SECONDARY_SUFFIX = ('_F', '_SG', '_DU', '_MU', '_BE', '_HM', '_HA')


def load_universe() -> pd.DataFrame:
    rows = []
    for p in glob.glob('.cache/yf/*__info_metrics.parquet'):
        try:
            d = pd.read_parquet(p)
            if d.empty:
                continue
            r = d.iloc[0]
            rows.append({
                'key': p.split('/')[-1].split('__')[0],
                'company': (r.get('longName') or r.get('shortName') or ''),
                'sector': r.get('sector'), 'country': r.get('country'),
                'mcap': r.get('marketCap'), 'cash': r.get('totalCash'),
                'debt': r.get('totalDebt'), 'fcf': r.get('freeCashflow'),
                'ev': r.get('enterpriseValue'), 'ev_ebitda': r.get('enterpriseToEbitda'),
                'ev_rev': r.get('enterpriseToRevenue'), 'pe': r.get('trailingPE'),
                'pb': r.get('priceToBook'), 'rev_g': r.get('revenueGrowth'),
                'earn_g': r.get('earningsGrowth'), 'op_marg': r.get('operatingMargins'),
                'revenue': r.get('totalRevenue'), 'ebitda': r.get('ebitda'),
                'chg52w': r.get('fiftyTwoWeekChange'),
            })
        except Exception:
            pass
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c not in ('key', 'company', 'sector', 'country'):
            df[c] = pd.to_numeric(df[c], errors='coerce')
    # Primary-exchange + share-class filters
    df = df[~df.key.str.endswith(SECONDARY_SUFFIX)]
    df = df[~(df.key.str.endswith('_L') & df.key.str[0].str.isdigit())]
    df = df[~df.key.str.contains(r'-P[A-Z]?$|-WT$|-WS$|-UN?$|-RT?$', regex=True, na=False)]
    df['net_cash'] = df.cash - df.debt.fillna(0)
    df['fcf_yield'] = df.fcf / df.mcap
    df['ev_fcf'] = df.ev / df.fcf
    return df


def run_scans(df: pd.DataFrame) -> pd.DataFrame:
    hits: dict[str, dict] = {}

    def flag(sub: pd.DataFrame, scan: str, strength: pd.Series):
        for k, s in zip(sub.key, strength):
            e = hits.setdefault(k, {'scans': [], 'strength': []})
            e['scans'].append(scan)
            e['strength'].append(float(np.clip(s, 0, 1)))

    base = df[df.mcap > 75e6]

    # A. negative EV (currency-sane bounds), FCF positive, real business
    a = base[(base.net_cash > base.mcap) & (base.net_cash < 4 * base.mcap)
             & (base.revenue > 20e6) & (base.fcf > 0)]
    flag(a, 'negative_ev', (a.net_cash / a.mcap - 1) / 3)

    # B. FCF machine
    b = base[(base.fcf_yield > 0.25) & (base.fcf_yield < 0.8) & (base.rev_g > 0.05)]
    flag(b, 'fcf_machine', (b.fcf_yield - 0.25) / 0.55)

    # C. deep value + growth
    c = base[(base.ev_ebitda > 0.5) & (base.ev_ebitda < 4.5) & (base.rev_g > 0.15)
             & (base.mcap > 150e6)]
    flag(c, 'deep_value_growth', (4.5 - c.ev_ebitda) / 4)

    # D. crashed quality: down big, still profitable + growing
    d = base[(base.chg52w < -0.40) & (base.op_marg > 0.10) & (base.rev_g > 0)
             & (base.ev_ebitda > 0) & (base.ev_ebitda < 10)]
    flag(d, 'crashed_quality', (-d.chg52w - 0.40) / 0.5)

    # E. Graham: single-digit P/E, growing, non-financial
    e = base[(base.pe > 0) & (base.pe < 8) & (base.earn_g > 0) & (base.mcap > 150e6)
             & (~base.sector.astype(str).str.contains('Financial', na=False))]
    flag(e, 'graham', (8 - e.pe) / 7)

    # F. below book while profitable
    f = base[(base.pb > 0) & (base.pb < 0.7) & (base.pe > 0) & (base.pe < 15)]
    flag(f, 'below_book', (0.7 - f.pb) / 0.6)

    # K. net-cash growth: fortress balance sheet + growth + profit
    k = base[(base.net_cash > 0.5 * base.mcap) & (base.net_cash < 4 * base.mcap)
             & (base.rev_g > 0.10) & (base.pe > 0) & (base.revenue > 20e6)]
    flag(k, 'net_cash_growth', (k.net_cash / k.mcap - 0.5) / 2)

    # L. EV/FCF < 5 (cash cheapness including the debt picture)
    l = base[(base.ev_fcf > 0) & (base.ev_fcf < 5) & (base.fcf > 20e6)]
    flag(l, 'ev_fcf', (5 - l.ev_fcf) / 4.5)

    # G. insider cluster (from extras screener)
    try:
        xt = pd.read_csv('results_extras/screener.csv')
        xt['ev_e'] = pd.to_numeric(xt.get('enterpriseToEbitda'), errors='coerce')
        g = xt[(pd.to_numeric(xt['insider_net_pct_6m'], errors='coerce') > 20)]
        g = g.rename(columns={'ticker': 'key'})
        flag(g, 'insider_cluster',
             (pd.to_numeric(g['insider_net_pct_6m'], errors='coerce') - 20) / 60)
    except Exception:
        pass

    # H. analyst gap
    try:
        xt = pd.read_csv('results_extras/screener.csv')
        h = xt[(pd.to_numeric(xt['upside_to_mean_target_pct'], errors='coerce') > 50)]
        h = h.rename(columns={'ticker': 'key'})
        mc = pd.to_numeric(h.get('market_cap'), errors='coerce')
        h = h[mc > 300e6]
        flag(h, 'analyst_gap',
             (pd.to_numeric(h['upside_to_mean_target_pct'], errors='coerce') - 50) / 150)
    except Exception:
        pass

    # I. multi-screen + cheap (from top100)
    try:
        top = pd.read_csv('results_peg/top100.csv')
        i = top[(top.n_screens >= 5)
                & (pd.to_numeric(top['enterpriseToEbitda'], errors='coerce') < 12)]
        i = i.rename(columns={'ticker': 'key'})
        flag(i, 'multi_screen', (i.n_screens - 5) / 3)
    except Exception:
        pass

    # J. unpriced segment (profitable+growing tier, top 25)
    try:
        u = pd.read_csv('results_unpriced_segment/screener.csv')
        j = u[u['viability_tier'] == 'profitable + growing'].head(25)
        j = j.rename(columns={'ticker': 'key'})
        flag(j, 'unpriced_segment',
             pd.to_numeric(j['unpriced_score'], errors='coerce') / 12)
    except Exception:
        pass

    rows = []
    for k, e in hits.items():
        scans = sorted(set(e['scans']))
        rows.append({
            'key': k,
            'n_scans': len(scans),
            'scans': ', '.join(scans),
            'avg_strength': round(float(np.mean(e['strength'])), 3),
            'asym_score': round(len(scans) + float(np.mean(e['strength'])), 3),
        })
    out = pd.DataFrame(rows).sort_values(
        ['asym_score', 'n_scans'], ascending=False)
    return out


def main():
    df = load_universe()
    print(f'Universe after filters: {len(df):,}')
    scans = run_scans(df)
    print(f'Names flagged by >=1 scan: {len(scans):,}')
    # Enrich with fundamentals for the display
    merged = scans.merge(
        df[['key', 'company', 'sector', 'country', 'mcap', 'pe', 'pb',
            'ev_ebitda', 'fcf_yield', 'net_cash', 'rev_g', 'chg52w']],
        on='key', how='left')
    merged = merged.rename(columns={'key': 'ticker'})
    keep = merged[merged.n_scans >= 2].head(150)
    keep.to_csv(OUT / 'asymmetry.csv', index=False)
    print(f'Wrote {len(keep)} multi-scan names to {OUT/"asymmetry.csv"}')
    show = keep.head(25)[['ticker', 'company', 'n_scans', 'scans',
                          'ev_ebitda', 'pe', 'fcf_yield', 'chg52w']].copy()
    pd.set_option('display.width', 250)
    pd.set_option('display.max_colwidth', 55)
    print('\nTop 25 multi-scan asymmetry:')
    print(show.to_string(index=False))


if __name__ == '__main__':
    main()
