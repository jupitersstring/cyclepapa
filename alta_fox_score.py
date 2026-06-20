"""Alta Fox 'Makings of a Multibagger' scoring leg.

Source: https://www.altafoxcapital.com/s/Makings-of-a-MultiBagger.pdf
(Alta Fox 2020 Summer Intern Class Project, n=104 stocks with 350%+ TSR
over 5 years).

Initial universe screen (per the PDF, not "<$2B"): market cap **$150M-$10B**,
positive TTM EBITDA, positive YoY revenue growth, avg daily volume above
$200k, domiciled in North America / Western Europe / Australia, all
sectors except Energy / Materials / Financials. 130 names returned; the
study focused on the 104 smallest. 84% of the sample *ended* below $2B
(post-hoc; not the entry filter).

TSR decomposition - what actually drove the 5-year returns:
  * average TSR = 59.8% EBITDA growth + 44.8% multiple expansion + 1.6% dividends
  * median TSR = 33.65% / 65.71% / 0%  (multiple expansion was MORE than half)
This contradicts a naive reading of "don't rely on multiples." The
correct reading: don't DEMAND a cheap starting multiple. Multiple
expansion *did* drive most of the TSR; the names just didn't all start
cheap. Our weighting therefore treats cheap multiples as a *not-extreme*
filter, not a positive cheapness signal.

Five high-level takeaways from the PDF:
  1. Advantageous positioning - **91% had moats** (any), 80% had
     moderate-to-high barriers to entry (42% high + 38% medium). We cannot
     assess moats qualitatively for a 15k-name universe, but we add
     quantitative proxies (gross margin level, ROCE level).
  2. Financial health - 88% started healthy, NOT turnarounds.
  3. Acquisitions create value - 56% used acquisitions as a growth
     driver, 19% had at least one transformative acquisition. Again not
     assessable qualitatively at this scale; we add a quantitative hint
     via revenue-growth-above-organic-norm.
  4. Don't rely on multiples (see TSR decomposition above).
  5. International - US under-represented vs investable universe;
     UK / Sweden / Germany / Norway / Australia over-represented.

Their specific final screening criteria:
  - Country: UK, Sweden, Germany, Norway, Australia (over-represented)
  - Industry: Technology or Healthcare
  - Trading below 3x NTM Sales, 20x NTM EBITDA, 30x NTM P/E
    (82% of set traded below these or had no forward multiples)

Financial-metric distribution at the START (FY15):
  - Median EBITDA margin: 10.22% (room to expand)
  - Median gross margin: 46.40%
  - Revenue 3y CAGR median: 20.88%
  - EBITDA 3y CAGR median: 28.19%
  - Median P/S: 1.68x  EV/EBITDA: 10.26x  P/E: 17.57x

Per the user's audit: we DO NOT score size (the >$10B universe was
excluded by Alta Fox's own filter, not a discriminator within the set),
and we do not pretend to qualitatively assess moats or M&A across the
universe. Instead we add lightweight quantitative proxies that don't
demand we trust them too far:
  - moat proxies: ROCE level, gross margin level, insider ownership
  - M&A hint: revenue 3y CAGR above plausible organic norm

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
    # Clip obvious data anomalies that survived the per-country scans:
    # ROCE values > 500 pct or < -100 pct are unit / negative-equity artifacts;
    # EV/EBIT < 2 (and > 0) is almost always a stale-data or unit scaling
    # error rather than a genuine 0.5x multiple.
    if 'roce' in df.columns:
        df.loc[(df['roce'] > 5.0) | (df['roce'] < -1.0), 'roce'] = float('nan')
    if 'ev_ebit' in df.columns:
        df.loc[(df['ev_ebit'] < 2.0), 'ev_ebit'] = float('nan')
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

    # Country code + USD-converted market cap from asymmetry_global.
    if os.path.exists('asymmetry_global.csv'):
        asym_cols = ['symbol', 'src']
        peek = pd.read_csv('asymmetry_global.csv', nrows=0).columns
        if 'market_cap_usd' in peek:
            asym_cols.append('market_cap_usd')
        asym = pd.read_csv('asymmetry_global.csv', usecols=asym_cols)
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
    # NOTE: Alta Fox excluded Energy/Materials/Financials in their original
    # screen, so we have NO data on whether those sectors produce
    # multibaggers. Score them as 0.5 (neutral / unknown) rather than 0.0,
    # which would incorrectly conflate 'we did not look' with 'evidence
    # against'. This lets sector-excluded names still surface if their
    # other Alta Fox signals are strong (size, geo, valuation, growth).
    sector_score = sector.map(
        lambda s: 1.0 if s in OVERREP_SECTORS
        else (0.5 if s in EXCLUDED_SECTORS  # neutral, not negative
              else (0.6 if s in {'Consumer Discretionary', 'Industrials',
                                 'Communication Services', 'Consumer Staples'}
                    else 0.3))
    )

    # AF3: Size - the <$2B finding was post-hoc (84% of Alta Fox set ended
    # below $2B), not a discriminator within their universe (which itself
    # was already filtered to $150M-$10B at entry). Per user audit: size
    # is NOT scored as a positive signal in this composite. We retain the
    # boolean flags for downstream filters but do not weight them.
    # USD-converted mcap when available, so non-USD names aren't
    # mis-bucketed (e.g. Dongwoo 088910.KQ at 57.87B KRW = ~$42M USD).
    if 'market_cap_usd' in df.columns:
        mcap = df['market_cap_usd'].fillna(0)
    else:
        mcap = df['market_cap'].fillna(0)
    df['af_size_lt_300m'] = (mcap < 300e6).astype(int)
    df['af_size_lt_2b'] = (mcap < 2e9).astype(int)
    df['af_size_lt_10b'] = (mcap < 10e9).astype(int)
    # No size_score - size is informational only.

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

    # AF6: Margin - starting EBITDA margin in 5-25% range gets full credit
    # (Alta Fox median start was 10.22%, expanded to 17.75% over 5 years).
    # We do NOT penalise margins above 25% - high margins indicate the
    # moat 91% of Alta Fox names had. Above-band margins still score 1.0.
    ebm = df['ebitda_margin'].fillna(-99)
    df['af_margin_5_25'] = ((ebm >= 0.05) & (ebm <= 0.25)).astype(int)
    df['af_margin_positive'] = (ebm > 0).astype(int)
    margin_score = pd.Series(0.0, index=df.index)
    margin_score = margin_score.where(~(ebm >= 0.05), 1.0)            # >=5% margin = 1.0
    margin_score = margin_score.where(~((ebm > 0.0) & (ebm < 0.05)), 0.5)  # 0-5% = 0.5
    margin_score = margin_score.where(ebm > 0, 0.0)                    # <=0 = 0

    # AF7: Financial health (Alta Fox: 88% started healthy, not turnarounds)
    nde = df['net_debt_ebitda'].fillna(99)
    ebm_pos = ebm > 0
    health_score = (
        (ebm_pos & (nde <= 2.0)).astype(float) * 1.0
        + (ebm_pos & (nde > 2.0) & (nde <= 3.5)).astype(float) * 0.5
    )
    df['af_financially_healthy'] = ((ebm_pos) & (nde <= 2.5)).astype(int)

    # AF8 (quantitative moat proxy 1): ROCE level. High ROCE is the
    # quantitative tell for the moat that 91% of Alta Fox names had.
    # >=20% scores 1.0 (Mayer/Greenblatt/Huber threshold); 10-20% scores 0.5.
    roce = df['roce'].fillna(-99) if 'roce' in df.columns else pd.Series(-99, index=df.index)
    df['af_roce_ge_20'] = (roce >= 0.20).astype(int)
    df['af_roce_ge_10'] = (roce >= 0.10).astype(int)
    roce_score = pd.Series(0.0, index=df.index)
    roce_score = roce_score.where(~(roce >= 0.20), 1.0)
    roce_score = roce_score.where(~((roce >= 0.10) & (roce < 0.20)), 0.5)
    roce_score = roce_score.where(~((roce > 0.0) & (roce < 0.10)), 0.2)

    # AF9 (quantitative moat proxy 2): Gross margin level. High gross
    # margin signals pricing power - Alta Fox median start was 46.4%.
    # >=40% scores 1.0; 25-40% scores 0.5; <25% scores 0.
    gm = df['gross_margin'].fillna(-99) if 'gross_margin' in df.columns else pd.Series(-99, index=df.index)
    df['af_gross_margin_ge_40'] = (gm >= 0.40).astype(int)
    gm_score = pd.Series(0.0, index=df.index)
    gm_score = gm_score.where(~(gm >= 0.40), 1.0)
    gm_score = gm_score.where(~((gm >= 0.25) & (gm < 0.40)), 0.5)

    # AF10 (insider ownership / owner-operator proxy). Mayer 100 Baggers
    # and Russo "capacity to suffer" both emphasise owner-operators.
    # >=10% scores 1.0; 5-10% scores 0.6.
    ins = df['insider_ownership_pct'].fillna(-1) if 'insider_ownership_pct' in df.columns else pd.Series(-1, index=df.index)
    df['af_insider_ge_10'] = (ins >= 0.10).astype(int)
    insider_score = pd.Series(0.0, index=df.index)
    insider_score = insider_score.where(~(ins >= 0.10), 1.0)
    insider_score = insider_score.where(~((ins >= 0.05) & (ins < 0.10)), 0.6)

    # AF11 (M&A hint - quantitative only; do not over-weight). Alta Fox
    # found 56% used acquisitions as growth driver. We can't verify M&A
    # qualitatively at scale; we use revenue 3y CAGR above plausible
    # organic norm (>30%) as a weak indicator a name MIGHT be acquisitive.
    # Could equally be hyper-organic growth, hence small weight.
    rev_3y = df['rev_3y_cagr'].fillna(-99) if 'rev_3y_cagr' in df.columns else pd.Series(-99, index=df.index)
    df['af_rev_3y_ge_30'] = (rev_3y >= 0.30).astype(int)
    ma_hint_score = (rev_3y >= 0.30).astype(float) * 0.7 + (rev_3y >= 0.50).astype(float) * 0.3

    # COMPOSITE - no size weight; cheapness downweighted (it's a
    # not-extreme filter, not a positive signal, per the TSR
    # decomposition); moat proxies (ROCE + gross margin + insider) added
    # with moderate weights; M&A hint added with light weight.
    df['alta_fox_score'] = (
        geo_score.astype(float)         * 0.15
        + sector_score.astype(float)    * 0.15
        + val_score.astype(float)       * 0.10  # was 0.20; not-extreme filter only
        + growth_score.astype(float)    * 0.15
        + margin_score.astype(float)    * 0.10
        + health_score.clip(0, 1)       * 0.10  # was 0.05; raised toward 88% prevalence
        + roce_score.astype(float)      * 0.10  # NEW - moat proxy 1
        + gm_score.astype(float)        * 0.05  # NEW - moat proxy 2
        + insider_score.astype(float)   * 0.05  # NEW - owner-operator proxy
        + ma_hint_score.astype(float)   * 0.05  # NEW - light M&A hint
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
                'af_financially_healthy',
                'af_roce_ge_20', 'af_roce_ge_10',
                'af_gross_margin_ge_40',
                'af_insider_ge_10',
                'af_rev_3y_ge_30']
    out_cols = [c for c in out_cols if c in df.columns]
    out = df[out_cols].copy()
    # Dedupe by symbol: keep the highest-scoring row when the same symbol
    # appeared in multiple per-country scan files (e.g. PL names in
    # pl_yartseva + pl_largecap_yartseva + pl_unc_yartseva each contributed
    # one row pre-fix).
    out = out.sort_values('alta_fox_score', ascending=False) \
             .drop_duplicates('symbol', keep='first') \
             .sort_values('alta_fox_score', ascending=False)
    out.to_csv(out_path, index=False)

    n_strict = int(df['alta_fox_strict_match'].sum())
    n_top = int((df['alta_fox_score'] >= 0.65).sum())
    print(f'wrote {out_path}: {len(out)} rows', file=sys.stderr)
    print(f'  strict Alta Fox checklist match: {n_strict}', file=sys.stderr)
    print(f'  alta_fox_score >= 0.65 (strong fit): {n_top}', file=sys.stderr)
    return out


if __name__ == '__main__':
    compute()
