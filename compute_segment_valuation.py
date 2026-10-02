"""Segment sum-of-parts / mix-shift valuation features from the EDGAR segment
harvest (edgar_segment_detail.csv). Per multi-segment symbol:

  seg_best_ebit_usd   highest single-segment operating EBIT (rev*op_margin)
  seg_total_ebit_usd  sum of segment operating EBIT
  seg_blended_margin  revenue-weighted blended operating margin
  seg_mix_uplift      fastest-growing segment's margin - blended (mix accretion)
  seg_core_declining  1 if a >=25%-of-revenue segment is shrinking >=10% YoY

CURRENCY RECONCILIATION: revenue_latest in the segment detail is NOT reliably
USD-normalized for foreign filers (e.g. LGPS reports $20.6bn of segment revenue
against $138m consolidated — a raw local-currency/scale artifact). The absolute
_usd EBIT figures are therefore only trustworthy when the segment revenue TOTAL
reconciles with the company's consolidated revenue_ttm_usd within a sane band;
outside it, we NULL the _usd EBIT columns so no downstream SOTP archetype can
compare a mis-scaled segment EBIT against a USD enterprise value. The margin /
mix / core-decline columns are dimensionless ratios (currency-independent) and
are always emitted.

Importable as compute_segment_valuation(detail_df, cons_rev) so the segment
signals builder can fold these columns in at source (durable), or run as a
standalone script that reads edgar_segment_detail.csv + asymmetry_global.csv.
"""
import pandas as pd, numpy as np, sys, os

RECON_LO, RECON_HI = 0.5, 2.0     # segment-total / consolidated revenue must land here for _usd figures to be trusted


def compute_segment_valuation(detail_df, cons_rev=None):
    """detail_df: per-(symbol,segment) rows (edgar_segment_detail schema).
    cons_rev: optional {symbol: consolidated revenue_ttm_usd} for the currency
    reconciliation; when absent, absolute _usd EBIT figures are dropped (can't
    be verified). Returns a symbol-keyed DataFrame of the valuation columns."""
    cons_rev = cons_rev or {}
    d = detail_df[detail_df['period_type'].isin(['FY', 'T3Q', 'H', 'Q'])].copy()
    # prefer FY rows per (symbol, segment)
    d['_p'] = d['period_type'].map({'FY': 0, 'T3Q': 1, 'H': 2, 'Q': 3}).fillna(9)
    d = d.sort_values(['symbol', 'segment_name', '_p']).drop_duplicates(['symbol', 'segment_name'], keep='first')
    rev = pd.to_numeric(d['revenue_latest'], errors='coerce')
    om = pd.to_numeric(d['op_margin'], errors='coerce')
    d['_ebit'] = rev * om
    d['_rev'] = rev
    d['_om'] = om
    d['_sh'] = pd.to_numeric(d['share_of_revenue'], errors='coerce')
    d['_gy'] = pd.to_numeric(d['yoy_growth'], errors='coerce')

    rows = []
    for sym, g in d.groupby('symbol'):
        g = g[g['_rev'].notna() & (g['_rev'] > 0)]
        if len(g) < 2:
            continue   # multi-segment only
        tot_rev = g['_rev'].sum()
        gm = g[g['_om'].notna()]
        blended = (gm['_ebit'].sum() / gm['_rev'].sum()) if gm['_rev'].sum() > 0 else np.nan
        best_ebit = g['_ebit'].max() if g['_ebit'].notna().any() else np.nan
        total_ebit = g['_ebit'].sum() if g['_ebit'].notna().any() else np.nan
        # currency/scale reconciliation vs consolidated USD revenue
        cr = cons_rev.get(sym, np.nan)
        reconciled = pd.notna(cr) and cr > 0 and (RECON_LO <= tot_rev / cr <= RECON_HI)
        if not reconciled:
            best_ebit = np.nan
            total_ebit = np.nan   # can't trust absolute _usd EBIT — mis-scaled or unverifiable
        # fastest-growing segment's margin vs blended (dimensionless, always kept)
        gg = g[g['_gy'].notna()]
        mix_uplift = np.nan
        if len(gg) and gg['_gy'].notna().any():
            fg = gg.loc[gg['_gy'].idxmax()]
            if pd.notna(fg['_om']) and pd.notna(blended):
                mix_uplift = fg['_om'] - blended
        core_decl = int(((g['_sh'] >= 0.25) & (g['_gy'] <= -0.10)).any())
        rows.append({'symbol': sym, 'seg_best_ebit_usd': best_ebit, 'seg_total_ebit_usd': total_ebit,
                     'seg_blended_margin': round(blended, 4) if pd.notna(blended) else np.nan,
                     'seg_mix_uplift': round(mix_uplift, 4) if pd.notna(mix_uplift) else np.nan,
                     'seg_core_declining': core_decl})
    return pd.DataFrame(rows)


def _load_cons_rev(path='asymmetry_global.csv'):
    if not os.path.exists(path):
        return {}
    a = pd.read_csv(path, low_memory=False, usecols=lambda c: c in ('symbol', 'revenue_ttm_usd'))
    return dict(zip(a['symbol'], pd.to_numeric(a['revenue_ttm_usd'], errors='coerce')))


def main():
    d = pd.read_csv('edgar_segment_detail.csv', low_memory=False)
    out = compute_segment_valuation(d, _load_cons_rev())
    out.to_csv('segment_valuation.csv', index=False)
    print('symbols', len(out), '| best_ebit cov (reconciled)', out['seg_best_ebit_usd'].notna().sum(),
          '| mix_uplift cov', out['seg_mix_uplift'].notna().sum(),
          '| core_declining', int(out['seg_core_declining'].sum()), file=sys.stderr)


if __name__ == '__main__':
    main()
