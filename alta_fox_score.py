"""Alta Fox 'Makings of a Multibagger' scoring leg.

Source: https://www.altafoxcapital.com/s/Makings-of-a-MultiBagger.pdf
(Alta Fox 2020 Summer Intern Class Project, n=104 stocks with 350%+ TSR
over 5 years, ex Energy/Materials/Financials, NA + Western Europe + AU).

Their five high-level takeaways:
  1. Look for businesses with advantageous positioning (80% had moderate-
     to-high barriers to entry, 91% had moderate-to-high competitive advantages)
  2. Spend time on financially healthy companies (88% started healthy, not
     turnarounds - turnaround thesis is RISKIER, not the multibagger pattern)
  3. Acquisitions can create value (56% used acquisitions as growth driver,
     19% had at least one transformative acquisition)
  4. Don't rely on multiples - many top performers started at healthy
     multiples that expanded further
  5. Be open to international companies - US was UNDER-represented vs investable
     universe; UK/Sweden/Germany/Norway/Australia were OVER-represented

Their specific final screening criteria:
  - Country: UK, Sweden, Germany, Norway, Australia (over-represented)
  - Industry: Technology or Healthcare
  - Market cap below $2B
  - Trading below 3x NTM Sales, 20x NTM EBITDA, 30x NTM PE
    (82% of set traded below these or had no forward multiples)

Their financial-metrics distribution at the START (FY15):
  - Median EBITDA margin: 10.22% (room to expand)
  - Median gross margin: 46.40%
  - Revenue 3y CAGR median: 20.88%
  - EBITDA 3y CAGR median: 28.19%
  - Median P/S: 1.68x  EV/EBITDA: 10.26x  P/E: 17.57x

This module emits an `alta_fox_score` per ticker [0..1] plus boolean
checklist columns (one per criterion).
"""
from __future__ import annotations
import glob
import os
import sys

import numpy as np
import pandas as pd
import financedatabase as fd


OVERREP_COUNTRIES = {'UK', 'SE', 'DE', 'NO', 'AU'}
FAVORED_COUNTRIES = OVERREP_COUNTRIES | {'US', 'CA', 'IE', 'FR', 'NL', 'CH', 'DK', 'FI', 'BE', 'AT'}
EXCLUDED_SECTORS = {'Energy', 'Materials', 'Financials'}  # per Alta Fox screen
OVERREP_SECTORS = {'Health Care', 'Information Technology'}  # 23% + 34% of set

YARTSEVA_GLOBS = ['*_yartseva.csv', 'italian_yartseva.csv', 'us_nano_micro_small_yartseva.csv']


def _load_fundamentals() -> pd.DataFrame:
    paths = sorted({p for g in YARTSEVA_GLOBS for p in glob.glob(g)})
    keep = ['symbol', 'name', 'sector', 'industry', 'market_cap',
            'revenue_ttm', 'ebitda_ttm', 'fcf_ttm',
            'ebitda_margin', 'fcf_margin', 'gross_margin', 'roce',
            'net_debt_ebitda', 'ev_ebit', 'ev_ebitda', 'ev_sales',
            'p_e', 'p_s', 'pb',
            'rev_yoy', 'ebitda_yoy', 'rev_3y_cagr',
            'fcf_yield', 'net_cash_pct_mcap', 'cash_pct_ev',
            'insider_ownership_pct',
            'yartseva_score', 'berezin_score']
    frames = []
    for f in paths:
        try:
            frames.append(pd.read_csv(f, usecols=lambda c: c in keep))
        except Exception:
            continue
    df = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
    return df


def compute(out_path: str = 'alta_fox_scores.csv') -> pd.DataFrame:
    df = _load_fundamentals()
    print(f'loaded fundamentals: {len(df)}', file=sys.stderr)

    # Live FD lookup for current sector/industry/country
    eq = fd.Equities()
    fdf = eq.select().reset_index()
    fl = fdf[['symbol', 'name', 'sector', 'industry', 'country']].rename(columns={
        'name': 'fd_name', 'sector': 'fd_sector',
        'industry': 'fd_industry', 'country': 'fd_country'})
    df = df.merge(fl, on='symbol', how='left')
    df['name'] = df['fd_name'].combine_first(df.get('name'))
    df['sector'] = df['fd_sector'].combine_first(df.get('sector'))
    df['industry'] = df['fd_industry'].combine_first(df.get('industry'))

    # Pull 3y/5y CAGR from PEW where available
    if os.path.exists('pew_global.csv'):
        pew = pd.read_csv('pew_global.csv',
                          usecols=['symbol', 'rev_3y_cagr', 'rev_5y_cagr', 'avg_dollar_volume'])
        # PEW takes precedence for rev_3y_cagr (more reliable than yartseva column)
        pew = pew.rename(columns={'rev_3y_cagr': 'pew_rev_3y_cagr'})
        df = df.merge(pew, on='symbol', how='left')
        df['rev_3y_cagr'] = df.get('pew_rev_3y_cagr', pd.Series(dtype=float)).combine_first(
            df['rev_3y_cagr'] if 'rev_3y_cagr' in df.columns else pd.Series(dtype=float)
        )

    # Country code from asymmetry_global (src field)
    if os.path.exists('asymmetry_global.csv'):
        asym = pd.read_csv('asymmetry_global.csv', usecols=['symbol', 'src'])
        df = df.merge(asym, on='symbol', how='left')

    # === Component checks ===

    # AF1: Country - over-represented geographies (1.0) or favored (0.5)
    src = df['src'].fillna('').str.upper() if 'src' in df.columns else pd.Series('', index=df.index)
    df['af_country_overrep'] = src.isin(OVERREP_COUNTRIES).astype(int)
    df['af_country_favored'] = src.isin(FAVORED_COUNTRIES).astype(int)
    geo_score = src.map(
        lambda x: 1.0 if x in OVERREP_COUNTRIES
        else (0.6 if x in FAVORED_COUNTRIES else 0.2)
    )

    # AF2: Sector - Tech / Healthcare over-represented; exclude Energy/Materials/Financials
    sector = df['sector'].fillna('')
    df['af_sector_overrep'] = sector.isin(OVERREP_SECTORS).astype(int)
    df['af_sector_excluded'] = sector.isin(EXCLUDED_SECTORS).astype(int)
    sector_score = sector.map(
        lambda s: 1.0 if s in OVERREP_SECTORS
        else (0.0 if s in EXCLUDED_SECTORS
              else (0.6 if s in {'Consumer Discretionary', 'Industrials',
                                 'Communication Services', 'Consumer Staples'}
                    else 0.3))
    )

    # AF3: Size - <$2B is the multibagger sweet spot (84% of Alta Fox set)
    mcap = df['market_cap'].fillna(0)
    df['af_size_lt_300m'] = (mcap < 300e6).astype(int)
    df['af_size_lt_2b'] = (mcap < 2e9).astype(int)
    df['af_size_lt_10b'] = (mcap < 10e9).astype(int)
    size_score = pd.cut(
        mcap,
        bins=[0, 50e6, 300e6, 2e9, 10e9, 1e15],
        labels=[1.0, 0.95, 0.85, 0.5, 0.15],
    ).astype(float).fillna(0.5)

    # AF4: Valuation - below 3x P/S, 20x EV/EBITDA, 30x P/E (or no forward multiple)
    p_s = df['p_s'].fillna(-1)
    ev_ebitda = df['ev_ebitda'].fillna(-1)
    p_e = df['p_e'].fillna(-1)

    cheap_ps = (p_s > 0) & (p_s <= 3.0)
    cheap_ev_ebitda = (ev_ebitda > 0) & (ev_ebitda <= 20.0)
    cheap_pe = (p_e > 0) & (p_e <= 30.0)
    df['af_cheap_p_s_lt_3'] = cheap_ps.astype(int)
    df['af_cheap_ev_ebitda_lt_20'] = cheap_ev_ebitda.astype(int)
    df['af_cheap_p_e_lt_30'] = cheap_pe.astype(int)
    df['af_cheap_count'] = (
        df['af_cheap_p_s_lt_3'] + df['af_cheap_ev_ebitda_lt_20']
        + df['af_cheap_p_e_lt_30']
    )
    # 82% of Alta Fox set traded below these (cheap_count >= 2 = strong match)
    val_score = (df['af_cheap_count'] / 3.0).clip(0, 1)

    # AF5: Growth - median Alta Fox starting rev CAGR was 20.88%, 25th pct 13.81%
    rev_3y = df['rev_3y_cagr'].fillna(-99)
    rev_yoy = df['rev_yoy'].fillna(-99)
    growth_proxy = rev_3y.where(rev_3y > -99, rev_yoy)  # fall back to yoy if 3y missing
    df['af_growth_14pct'] = (growth_proxy >= 0.14).astype(int)  # 25th pct
    df['af_growth_21pct'] = (growth_proxy >= 0.21).astype(int)  # 50th pct
    df['af_growth_38pct'] = (growth_proxy >= 0.38).astype(int)  # 75th pct
    growth_score = (
        df['af_growth_14pct'] * 0.4
        + df['af_growth_21pct'] * 0.3
        + df['af_growth_38pct'] * 0.3
    ).clip(0, 1)

    # AF6: Margin - starting EBITDA margin in 5-25% range (room to expand)
    # Alta Fox median start was 10.22%, expanded to 17.75% over 5 years
    ebm = df['ebitda_margin'].fillna(-99)
    df['af_margin_5_25'] = ((ebm >= 0.05) & (ebm <= 0.25)).astype(int)
    df['af_margin_positive'] = (ebm > 0).astype(int)
    margin_score = pd.Series(0.0, index=df.index)
    margin_score = margin_score.where(~((ebm >= 0.05) & (ebm <= 0.25)), 1.0)
    margin_score = margin_score.where(~((ebm > 0.25) & (ebm <= 0.40)), 0.6)
    margin_score = margin_score.where(~((ebm > 0.0) & (ebm < 0.05)), 0.5)
    margin_score = margin_score.where(ebm > 0, 0.0)

    # AF7: Financial health (Alta Fox: 88% started healthy, not turnarounds)
    nde = df['net_debt_ebitda'].fillna(99)
    ebm_pos = ebm > 0
    health_score = (
        (ebm_pos & (nde <= 2.0)).astype(float) * 1.0
        + (ebm_pos & (nde > 2.0) & (nde <= 3.5)).astype(float) * 0.5
    )
    df['af_financially_healthy'] = ((ebm_pos) & (nde <= 2.5)).astype(int)

    # COMPOSITE
    df['alta_fox_score'] = (
        geo_score.astype(float) * 0.20
        + sector_score.astype(float) * 0.15
        + size_score.astype(float) * 0.15
        + val_score.astype(float) * 0.20
        + growth_score.astype(float) * 0.15
        + margin_score.astype(float) * 0.10
        + health_score.clip(0, 1) * 0.05
    ).round(3)

    # Also surface a 'strict Alta Fox checklist' boolean
    df['alta_fox_strict_match'] = (
        df['af_country_overrep']
        & df['af_sector_overrep']
        & df['af_size_lt_2b']
        & (df['af_cheap_count'] >= 2)
        & df['af_growth_14pct']
        & df['af_financially_healthy']
    ).astype(int)

    out_cols = ['symbol', 'name', 'sector', 'industry', 'market_cap',
                'alta_fox_score', 'alta_fox_strict_match',
                'af_country_overrep', 'af_country_favored',
                'af_sector_overrep', 'af_sector_excluded',
                'af_size_lt_300m', 'af_size_lt_2b', 'af_size_lt_10b',
                'af_cheap_p_s_lt_3', 'af_cheap_ev_ebitda_lt_20',
                'af_cheap_p_e_lt_30', 'af_cheap_count',
                'af_growth_14pct', 'af_growth_21pct', 'af_growth_38pct',
                'af_margin_5_25', 'af_margin_positive',
                'af_financially_healthy']
    out_cols = [c for c in out_cols if c in df.columns]
    out = df[out_cols].copy()
    out.to_csv(out_path, index=False)

    n_strict = int(df['alta_fox_strict_match'].sum())
    n_top = int((df['alta_fox_score'] >= 0.65).sum())
    print(f'wrote {out_path}: {len(out)} rows', file=sys.stderr)
    print(f'  strict Alta Fox checklist match: {n_strict}', file=sys.stderr)
    print(f'  alta_fox_score >= 0.65 (strong fit): {n_top}', file=sys.stderr)
    return out


if __name__ == '__main__':
    compute()
