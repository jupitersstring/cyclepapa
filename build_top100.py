"""Consolidated Top-100 master watchlist.

Aggregates conviction across every screen in the workbook. The thesis:
a name that surfaces in MULTIPLE independent lenses (cheap-on-growth,
quality compounder, segment inflection, insider buying, ...) is a
higher-conviction idea than one that tops a single list. So the master
score rewards BREADTH (how many screens flag it) first, DEPTH (how well
it stands within each) second.

Within-screen standing is a percentile (1.0 = best in that screen, 0 =
worst), sign-corrected for lower-is-better metrics. The broad universe
ranks (Composite, Financials) only count as a "hit" when the name is in
the top quartile — mere presence there isn't selective.

Produces results_peg/top100.csv consumed by build_workbook's Top 100 tab.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

OUT = Path('results_peg')

# (label, csv, score_col, lower_is_better, selective)
#   selective=True  -> any appearance counts as a hit (the creative screens
#                      already filtered to a shortlist)
#   selective=False -> only a top-quartile standing counts as a hit (broad
#                      universe ranks)
SCREENS = [
    ('Composite (growth-adj)', 'results_peg/growth_adj_value.csv', 'ev_ebitda_g_bv', True,  False),
    ('Financials',             'results_peg/financials_value.csv', 'fin_composite',  False, False),
    ('Akre Compounder',        'results_akre/screener.csv',                'akre_score',     False, True),
    ('Clean Top-Line',         'results_clean_topline/screener.csv',       'quality_score',  False, True),
    ('Operating Leverage',     'results_operating_leverage/screener.csv',  'leverage_score', False, True),
    ('Multiple Compression',   'results_multiple_compression/screener.csv', None,            False, True),
    ('EV Compression',         'results_ev_compression/screener.csv',       None,            False, True),
    ('EV/FCF Leverage',        'results_ev_fcf_leverage/screener.csv',     'leverage_score', False, True),
    ('FCF Yield',              'results_fcf_yield/screener.csv',            None,             False, True),
    ('Flat + Inflection',      'results_flat_inflection/screener.csv',     'gap_score',      False, True),
    ('Segment Inflection',     'results_xbrl_segments/screener.csv',       'seg_score',      False, True),
    ('Unpriced Segment',       'results_unpriced_segment/screener.csv',    'unpriced_score', False, True),
    ('Analyst & Insider',      'results_extras/screener.csv',              'extras_composite', False, True),
]


def _norm_ticker(t) -> str:
    return str(t).strip().upper()


def _within_screen_standing(df: pd.DataFrame, score_col: str | None,
                            lower_is_better: bool) -> pd.Series:
    """Return a 0..1 standing per row (1 = best in screen)."""
    if score_col and score_col in df.columns:
        s = pd.to_numeric(df[score_col], errors='coerce')
        if s.notna().sum() >= 3:
            pct = s.rank(pct=True)
            return (1 - pct) if lower_is_better else pct
    # No usable score column → flat standing (presence is the signal)
    return pd.Series(0.6, index=df.index)


def build() -> pd.DataFrame:
    # ticker -> {screens: set, standings: list, ...}
    agg: dict[str, dict] = {}
    for label, csv, score_col, lower, selective in SCREENS:
        p = Path(csv)
        if not p.exists():
            continue
        df = pd.read_csv(p)
        tcol = 'ticker' if 'ticker' in df.columns else ('symbol' if 'symbol' in df.columns else None)
        if tcol is None:
            continue
        standing = _within_screen_standing(df, score_col, lower)
        for i, row in df.iterrows():
            tk = _norm_ticker(row[tcol])
            if not tk or tk == 'NAN':
                continue
            st = float(standing.loc[i]) if i in standing.index else 0.6
            # Broad ranks: only a top-quartile standing is a "hit"
            is_hit = selective or st >= 0.75
            e = agg.setdefault(tk, {'screens': [], 'standings': [], 'hit_screens': []})
            e['screens'].append(label)
            e['standings'].append(st)
            if is_hit:
                e['hit_screens'].append(label)

    rows = []
    for tk, e in agg.items():
        n_hit = len(set(e['hit_screens']))
        if n_hit == 0:
            continue
        avg_standing = float(np.mean(e['standings'])) if e['standings'] else 0.0
        # Master score: breadth dominates (each cross-validating screen is
        # worth ~1.0), depth is a tie-breaker (0..1). Distinct hit-screens
        # only, so duplicate listings (e.g. EV Compression all + screener)
        # don't inflate.
        master = n_hit + avg_standing
        rows.append({
            'ticker': tk,
            'n_screens': n_hit,
            'screens_in': ', '.join(sorted(set(e['hit_screens']))),
            'avg_standing': round(avg_standing, 3),
            'master_score': round(master, 3),
        })
    out = pd.DataFrame(rows).sort_values(
        ['master_score', 'n_screens', 'avg_standing'], ascending=False)
    return out


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add company / sector / country / key valuation from the info cache."""
    YF = Path('.cache/yf')
    def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(t))
    recs = []
    for tk in df['ticker']:
        p = YF / f'{safe(tk)}__info_metrics.parquet'
        rec = {'ticker': tk, 'company': '', 'sector': '', 'country': '',
               'market_cap': None, 'trailingPE': None, 'priceToBook': None,
               'enterpriseToEbitda': None}
        if p.exists():
            try:
                d = pd.read_parquet(p).iloc[0]
                rec['company'] = (d.get('longName') or d.get('shortName') or '')[:42]
                rec['sector'] = d.get('sector') or ''
                rec['country'] = d.get('country') or ''
                for k in ('market_cap','trailingPE','priceToBook','enterpriseToEbitda'):
                    src = {'market_cap':'marketCap'}.get(k, k)
                    v = d.get(src)
                    if v is not None and pd.notna(v): rec[k] = v
            except Exception:
                pass
        recs.append(rec)
    info = pd.DataFrame(recs)
    return df.merge(info, on='ticker', how='left')


def main():
    df = build()
    df = enrich(df).head(100)
    cols = ['ticker','company','sector','country','n_screens','screens_in',
            'market_cap','trailingPE','priceToBook','enterpriseToEbitda',
            'avg_standing','master_score']
    df = df[[c for c in cols if c in df.columns]]
    df.to_csv(OUT / 'top100.csv', index=False)
    print(f'Wrote {len(df)} names to {OUT/"top100.csv"}')
    print('\nTop 20 cross-validated names:')
    show = df.head(20)[['ticker','company','n_screens','screens_in','master_score']].copy()
    show['screens_in'] = show['screens_in'].str.slice(0, 60)
    pd.set_option('display.width', 240); pd.set_option('display.max_colwidth', 62)
    print(show.to_string(index=False))


if __name__ == '__main__':
    main()
