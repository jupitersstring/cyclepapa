"""Tag every ticker in the universe with the archetype clusters that fit it.

Implements four clusters from the Yellowbrick deep-research taxonomy where
the trigger is fully observable from data we already collected.  Cluster A
(Narrative Lag) is computed and surfaced as a column but does NOT get its
own sheet - it is folded into the other four sheets as a modifier.

Cluster C5: Fixed-Cost Asset + Demand Shock
Cluster E:  Discounted Vehicle + Capital Discipline Re-rating
Cluster F:  Regime-Change Cyclical + Option Mispriced as Dead
Cluster G:  Operating KPI Threshold + Regional Blind-Spot
Cluster A:  Narrative Lag (modifier - flat 12m return + a printed inflection)

Output: archetype_tags.csv keyed by symbol, plus per-archetype boolean cols
and a human-readable archetype_tags_str.
"""
from __future__ import annotations
import glob
import os
import sys

import numpy as np
import pandas as pd


YARTSEVA_GLOBS = ['*_yartseva.csv', 'italian_yartseva.csv', 'us_nano_micro_small_yartseva.csv']
ASYM_PATH = 'asymmetry_global.csv'
PEW_PATH = 'pew_global.csv'

# Country buckets used for the Regional Blind-Spot tag - markets that the
# Yellowbrick corpus is structurally under-weight (per the research note).
BLINDSPOT_COUNTRIES = {
    'KR','GR','ID','TH','ZA','MX','BR','CO','AR','PH','VN',
    'HU','CZ','EE','LV','LT','PL','TR','SA','RO','ML','PE','CL','IL'
}

# Sectors where capital-intensive fixed-asset operating leverage is the
# typical economic engine (used for C5 and F9).
HEAVY_ASSET_SECTORS = {
    'Industrials','Materials','Energy','Utilities',
    'Consumer Discretionary',  # autos / homebuilders / heavy retail logistics
}


def _load_yartseva_union() -> pd.DataFrame:
    """Merge every per-country yartseva CSV into one symbol-keyed frame.

    Keeps the first row per symbol; per-country files don't overlap meaningfully.
    """
    paths = sorted({p for g in YARTSEVA_GLOBS for p in glob.glob(g)})
    frames = []
    keep = [
        'symbol','sector','industry','market_cap','currency',
        'ebitda_margin','fcf_yield','pb','insider_ownership_pct','gross_margin',
        'ev_ebitda','ev_ebit','ev_sales','roce',
        'rev_yoy','ebitda_yoy','fcf_yoy','rev_accel','ebitda_accel',
        'rev_inflection','ebitda_inflection','cfo_inflection','fcf_inflection',
        'ebitda_first_positive','cfo_first_positive','fcf_first_positive',
        'net_income_first_positive','roce_first_positive','roce_inflection',
        'ebitda_margin_delta_yoy','fcf_margin_delta_yoy',
        'gross_profit_yoy','gross_margin_delta_yoy','op_margin_delta_yoy',
        'ebit_growth_yoy','shares_yoy','shares_3y_cagr','fcf_per_share_yoy',
        'net_buyback_ttm','normalized_ebitda','normalized_ebit','normalized_revenue',
        'earnings_beat_rate','avg_earnings_surprise','earnings_beat_streak',
        'earnings_surprise_inflecting','price_vs_5y_avg','price_pct_of_5y_range',
        'eps_positive_streak_q','eps_yoy_growth_streak_q','eps_yoy_positive_share',
        'price_yoy','momentum_12m','not_priced_in_score',
        'net_debt_ebitda','net_cash_pct_mcap','cash_pct_ev','ncav_pct_mcap',
        'cash_gt_ev_flag','graham_net_net_flag',
    ]
    for f in paths:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' not in d.columns:
            continue
        d['src_file'] = os.path.basename(f)
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=keep)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates('symbol', keep='first')
    return out


def _country_from_src(src: str | float) -> str:
    """Best-effort country inference from the asymmetry src column."""
    if not isinstance(src, str):
        return ''
    return src.strip().upper()


# FMP-fillable gate inputs exported post-fill as <col>_eff (see compute()).
_EFF_COLS = ('retained_earnings', 'net_working_capital', 'tangible_equity', 'p_tb',
             'ni_avg', 'capex_avg', 'oe_avg', 'financing_cf_ttm', 'effective_tax_rate',
             'income_continuing_ops_ttm', 'income_discontinued_ops_ttm', 'deferred_revenue',
             'equity', 'assets', 'pretax_income_ttm', 'sbc_pct_revenue',
             'interest_coverage', 'goodwill_intangibles_pct_assets',
             'rev_yoy_streak_q', 'ni_yoy_streak_q', 'rev_yoy_pos_share_12q',
             'revenue_3y_cagr', 'revenue_5y_cagr', 'revenue_acceleration_lindy',
             'asset_3y_cagr', 'asset_5y_cagr', 'cash_roic_lindy', 'roic_acceleration',
             'cheap_per_roiic_lindy', 'n_yrs_positive_fcf', 'n_yrs_positive_roic',
             'n_yrs_positive_opinc', 'equity_cagr_5y')


def compute(out_path: str = 'archetype_tags.csv') -> pd.DataFrame:
    asym = pd.read_csv(ASYM_PATH).drop_duplicates('symbol')
    if os.environ.get('ARCH_SMOKE'):        # a quick end-to-end run on a symbol sample (code check, not output)
        asym = asym.sample(int(os.environ['ARCH_SMOKE']), random_state=7)
    yart = _load_yartseva_union()
    pew = pd.read_csv(PEW_PATH, usecols=['symbol','avg_dollar_volume','n_analysts','country'])

    # EDGAR enrichment: ROIC / ROIIC / Lindy multi-year metrics + tangible
    # book signals. Optional — names without EDGAR coverage simply miss
    # those archetype legs.
    edgar_roiic = None
    if os.path.exists('edgar_roic_roiic.csv'):
        edgar_roiic = pd.read_csv('edgar_roic_roiic.csv')
    edgar_yart = None
    if os.path.exists('us_edgar_yartseva.csv'):
        edgar_yart = pd.read_csv('us_edgar_yartseva.csv',
                                 usecols=lambda c: c in {
                                     'symbol', 'p_tb', 'tangible_equity_pct',
                                     'pct_off_52w_high',
                                     # NEW (audit June 2026): capital-allocation
                                     # + quality + SBC + real tax rate
                                     'capital_return_yield', 'dividend_yield',
                                     'buyback_yield', 'sbc_pct_revenue',
                                     'effective_tax_rate', 'roic_after_sbc',
                                     'interest_coverage', 'retained_earnings',
                                     'pretax_income_ttm',
                                     'capex_avg', 'net_working_capital',
                                     'goodwill_intangibles_pct_assets',
                                     'oe_avg', 'ni_avg', 'fcf_avg',
                                     'oe_avg_years', 'equity_cagr_5y',
                                     'financing_cf_ttm',
                                 })

    # Segment signals from the edgartools dimensional harvest. Coverage
    # is sparse (only US filers with multi-segment 10-K disclosures) but
    # the signal is high-quality where it fires.
    segment_signals = None
    if os.path.exists('edgar_segment_signals.csv'):
        segment_signals = pd.read_csv('edgar_segment_signals.csv')

    # SEC Form 4 revealed-preference insider signals (US filers). Costly
    # actions — open-market purchases, cluster buying, officer / 10%-owner
    # buys — not language. Sparse (US only) but high-signal where it fires.
    insider_signals = None
    if os.path.exists('sec_insider_signals.csv'):
        insider_signals = pd.read_csv('sec_insider_signals.csv')

    # Merge.  Asym is the primary - everything else is enrichment.
    df = asym.merge(yart, on='symbol', how='left', suffixes=('','_y'))
    if edgar_roiic is not None:
        df = df.merge(edgar_roiic, on='symbol', how='left', suffixes=('','_er'))
    if edgar_yart is not None:
        df = df.merge(edgar_yart, on='symbol', how='left', suffixes=('','_ey'))
    if segment_signals is not None:
        df = df.merge(segment_signals, on='symbol', how='left', suffixes=('','_seg'))
    if insider_signals is not None:
        df = df.merge(insider_signals, on='symbol', how='left', suffixes=('','_ins'))
    # Investment / JV-stake forensics (cache-derived): carrying-value step-up
    # (remark event), disclosed fair-value gap, look-through associate earnings.
    if os.path.exists('investment_remark.csv'):
        _invr = pd.read_csv('investment_remark.csv').drop_duplicates('symbol')
        _invr_keep = ['symbol', 'inv_carry_now', 'inv_carry_prior', 'inv_remark_jump',
                      'inv_remark_pct', 'nonop_gain_ttm', 'em_carry', 'em_fair_value',
                      'em_fv_gap', 'em_income', 'unrealized_inv_gain']
        df = df.merge(_invr[[c for c in _invr_keep if c in _invr.columns]],
                      on='symbol', how='left', suffixes=('', '_invr'))
    # Graham quality-adjusted NNWC (cash 100% / receivables 85% / inventory 50%
    # - all liabilities) — a cash net-net vs an inventory net-net.
    if os.path.exists('nnwc.csv'):
        _nnwc = pd.read_csv('nnwc.csv').drop_duplicates('symbol')
        _nnwc_keep = ['symbol', 'nnwc', 'nnwc_asset_mix']
        df = df.merge(_nnwc[[c for c in _nnwc_keep if c in _nnwc.columns]],
                      on='symbol', how='left', suffixes=('', '_nn'))
    # Value-unlock language (EDGAR full-text search): recent filings discussing
    # realising/crystallising/unlocking latent value (strategic reviews, sale
    # processes, separations, capital return).
    if os.path.exists('value_unlock_signals.csv'):
        _vu = pd.read_csv('value_unlock_signals.csv').drop_duplicates('symbol')
        _vu_keep = ['symbol', 'unlock_hits', 'unlock_distinct_phrases',
                    'unlock_stage_phrases', 'unlock_activist',
                    'unlock_days_ago', 'unlock_phrases']
        df = df.merge(_vu[[c for c in _vu_keep if c in _vu.columns]],
                      on='symbol', how='left', suffixes=('', '_vu'))
    if os.path.exists('lynch_reward_signals.csv'):
        lynch_signals = pd.read_csv('lynch_reward_signals.csv').drop_duplicates('symbol')
        df = df.merge(lynch_signals, on='symbol', how='left', suffixes=('','_lr'))
    # EDGAR event-driven / special-situations signals (US filers): Form-10 spins,
    # tenders/mergers/going-private, NOL carryforwards, post-reorg fresh-start.
    if os.path.exists('edgar_event_signals.csv'):
        _evt = pd.read_csv('edgar_event_signals.csv').drop_duplicates('symbol')
        _evt_keep = ['symbol', 'spin_flag', 'tender_flag', 'merger_flag',
                     'going_private_flag', 'distress_flag', 'nol_usd', 'reorg_flag',
                     'spin_date', 'reorg_date']
        _evt = _evt[[c for c in _evt_keep if c in _evt.columns]]
        df = df.merge(_evt, on='symbol', how='left', suffixes=('', '_evt'))
    # pew and asym both carry n_analysts; suffix pew's copy so downstream
    # _num('n_analysts') keeps reading the asym column instead of vanishing
    # into n_analysts_x/_y (which silently zeroed the analyst-awakening gate).
    df = df.merge(pew, on='symbol', how='left', suffixes=('', '_pew'))

    # FMP (Financial Modeling Prep) overlay — a SECONDARY, source-tagged
    # source (fmp_enrich.py). Carries three things XBRL/our primary path do
    # not: (a) quality/distress scores (Piotroski, Altman Z) and TTM
    # returns/margins with near-universal coverage, (b) revealed-preference
    # insider open-market buys and executive compensation -> the
    # insider-alignment ratio the Cluseau lens wanted but XBRL cannot supply,
    # (c) analyst estimate vs actual -> earnings beat/surprise/variability.
    # Every column is fmp_-prefixed and merged the same optional way as every
    # enrichment above. NOTHING here overwrites an EDGAR-primary value; the
    # narrow, audited fills and gates below decide where an fmp_ column may
    # fill a NaN or add a signal. Forensic / NNWC inputs are never fed by FMP.
    def _merge_fmp_overlay(frame, path):
        """Merge an FMP overlay so the FRESH file always wins. enrich_asymmetry_
        global propagates selected fmp_ columns back into the master (so the
        country books can show them); without dropping those copies first, the
        stale master copy would keep the unsuffixed name and the fresh value
        would be discarded — the same freeze bug the enrich step guards against."""
        if not os.path.exists(path):
            return frame
        ov = pd.read_csv(path, low_memory=False).drop_duplicates('symbol')
        frame = frame.drop(columns=[c for c in ov.columns if c != 'symbol' and c in frame.columns])
        return frame.merge(ov, on='symbol', how='left')

    df = _merge_fmp_overlay(df, 'fmp_enrichment.csv')

    # FMP DYNAMIC (multi-period) overlay (fmp_dynamics.py): clean quarterly
    # trajectories — streak length, acceleration, first-positive inflection,
    # incremental operating margin, the multiple-vs-fundamental "unrerated"
    # divergence, and FORWARD estimate crossings / underestimate gap. Serves
    # the evolution / step-change archetypes far better than the noisy Yahoo
    # sequential proxies. Secondary, source-tagged, non-overwriting.
    df = _merge_fmp_overlay(df, 'fmp_dynamics.csv')

    # FMP STATEMENT-HISTORY overlay (fmp_statements.py): global equivalents of
    # the EDGAR-only multi-year metrics. Merged here; the fills below promote
    # the ~29k non-US names off the single-year fallback by NaN-filling the
    # EDGAR-only quality columns where EDGAR does not cover them.
    df = _merge_fmp_overlay(df, 'fmp_statements.csv')

    # FMP SEGMENT overlay (fmp_segments.py): product + geographic revenue
    # segmentation for every filer FMP covers (US and non-US). Revenue-based
    # only — segment operating margin stays EDGAR-only. Fills the EDGAR segment
    # columns where the dimensional harvest has nothing (~90% of the universe).
    df = _merge_fmp_overlay(df, 'fmp_segments.csv')
    # weekly-panel base / coil snapshot (base_snapshot.py) and the analyst
    # sentiment layer (fmp_sentiment.py): the price-path and perception inputs
    # of the "flat for two years, then re-rates" family
    df = _merge_fmp_overlay(df, 'base_snapshot.csv')
    df = _merge_fmp_overlay(df, 'fmp_sentiment.csv')
    if os.path.exists('fmp_us_filings.csv'):        # headcount + quarterly insider statistics (SEC filers)
        df = _merge_fmp_overlay(df, 'fmp_us_filings.csv')
    if os.path.exists('mb_model_scores.csv'):       # the walk-forward model's score of today's cross-section
        _ms = pd.read_csv('mb_model_scores.csv', usecols=['symbol', 'mb_model_p', 'mb_model_rank_mkt', 'mb_model_rank',
                                                          'mb_model_pct_hist'])
        df = df.drop(
            columns=[c for c in _ms.columns if c != 'symbol' and c in df.columns]).merge(
            _ms.drop_duplicates('symbol'), on='symbol', how='left')
        _ms_age = (pd.Timestamp.today().normalize() - pd.to_datetime(pd.read_csv('mb_model_scores.csv', usecols=['symbol', 'week'])
                                                                     .drop_duplicates('symbol').set_index('symbol')['week'])).dt.days
        _stale = df['symbol'].map(_ms_age) > 42
        for _c in ('mb_model_p', 'mb_model_rank_mkt', 'mb_model_rank', 'mb_model_pct_hist'):
            df.loc[_stale.fillna(False), _c] = np.nan
    # weekly time-series measures (ts_snapshot.py), through-cycle annual minima
    # (fmp_throughcycle.py), quarterly growth quality (fmp_quarterly_ext.py)
    df = _merge_fmp_overlay(df, 'ts_snapshot.csv')
    df = _merge_fmp_overlay(df, 'fmp_throughcycle.csv')
    df = _merge_fmp_overlay(df, 'fmp_quarterly_ext.csv')
    # dated events layer (fmp_events.py). Its columns are prefixed ev_ in the
    # file; ev_ already names the enterprise-value multiples here (ev_ebitda,
    # ev_sales), so they are renamed evt_ on the way in.
    if os.path.exists('fmp_events.csv'):
        _evt = pd.read_csv('fmp_events.csv', low_memory=False).drop_duplicates('symbol', keep='last')
        _evt = _evt.rename(columns={c: 'evt_' + c[3:] for c in _evt.columns if c.startswith('ev_')})
        df = df.drop(columns=[c for c in _evt.columns if c != 'symbol' and c in df.columns])
        df = df.merge(_evt, on='symbol', how='left')
    # UNIVERSE-WIDE EPS surprise history (fmp_earnings_bulk.py, esb_*): the
    # bulk feed's beat record and price reactions for ~17.5k names (8.7k
    # non-US) stand behind the per-symbol evt_* event fields wherever the
    # events layer did not reach a name (same construction, same panel).
    df = _merge_fmp_overlay(df, 'fmp_earnings_bulk.csv')
    for _k in ('beats_8q', 'beat_share_8q', 'surprise_4q', 'react_last', 'pead_4w',
               'last_report_days', 'react_beats_4q', 'ignored_beats_2y'):
        if 'esb_' + _k in df.columns:
            _prim = pd.to_numeric(df['evt_' + _k], errors='coerce') if 'evt_' + _k in df.columns \
                else pd.Series(np.nan, index=df.index)
            df['evt_' + _k] = _prim.fillna(pd.to_numeric(df['esb_' + _k], errors='coerce'))
    # PER-SHARE compounding history (fmp_financial_growth.py, fg_*) and the
    # DATED enterprise-value series (fmp_ev_history.py, evh_*): global.
    df = _merge_fmp_overlay(df, 'fmp_financial_growth.csv')
    df = _merge_fmp_overlay(df, 'fmp_ev_history.csv')

    # FMP INSTITUTIONAL overlay (fmp_institutional.py): 13F ownership
    # trajectory over the last three complete quarters (US-listed names).
    df = _merge_fmp_overlay(df, 'fmp_institutional.csv')

    # FMP QUARTERLY three-statement overlay (fmp_quarterly.py): point-in-time,
    # contiguous-TTM, single-currency balance-sheet / cash-flow / income detail
    # plus forensic tests (Beneish, Sloan accruals, DSO/DIO/DPO trajectories,
    # receivables and inventory divergence, cash vs book tax). Replaces the
    # EDGAR-only forensic inputs for every name EDGAR does not cover.
    df = _merge_fmp_overlay(df, 'fmp_quarterly.csv')

    # Coalesce suffix-shadowed copies back into the base columns. Every merge
    # above keeps the asym copy unsuffixed and shelves the incoming one
    # (_ey/_er/_pew) — but for these columns the EDGAR/pew copy often has
    # HIGHER coverage (capital_return_yield +1.4k rows, p_tb +950,
    # interest_coverage +670, sbc_pct_revenue +890...). Fill gaps from the
    # shadowed copy so the gates see the union, not just the asym slice.
    for _c in ('p_tb', 'capital_return_yield', 'dividend_yield',
               'buyback_yield', 'sbc_pct_revenue', 'effective_tax_rate',
               'roic_after_sbc', 'interest_coverage', 'pretax_income_ttm',
               'pct_off_52w_high', 'ev_ebitda', 'net_cash_pct_mcap',
               'cash_pct_mcap', 'ebitda_margin', 'fcf_ttm', 'ebitda_ttm'):
        for _suf in ('_ey', '_er', '_pew'):
            if _c in df.columns and _c + _suf in df.columns:
                df[_c] = pd.to_numeric(df[_c], errors='coerce').fillna(
                    pd.to_numeric(df[_c + _suf], errors='coerce'))

    # FRESHNESS COALESCE for the 52w system: the master's quote-time
    # pct_off_52w_high can be WEEKS stale (price-refresh enrichers pause
    # while the lynch drive owns Yahoo) — ground-truth audit caught UTZ at
    # its 52w high showing -48% in the books. The lynch tape is refetched
    # per name (age tracked); where it is live, its pct_52w_high (price/high)
    # OVERRIDES the stale quote-time column, so the displayed % and the
    # fresh high_52w flags can never disagree.
    if 'pct_52w_high' in df.columns:
        _lp = pd.to_numeric(df['pct_52w_high'], errors='coerce')
        _age = pd.to_numeric(df.get('last_bar_age_days'), errors='coerce')
        _stale = pd.to_numeric(df.get('stale_tape'), errors='coerce').fillna(0)
        _fresh = _lp.notna() & (_stale != 1) & (_age.isna() | (_age <= 21))
        df['pct_off_52w_high'] = (_lp - 1.0).where(
            _fresh, pd.to_numeric(df.get('pct_off_52w_high'), errors='coerce'))

    # Use the asymmetry sector/market_cap as primary; fall back to yartseva.
    for c in ('sector','industry','market_cap'):
        if c + '_y' in df.columns:
            df[c] = df[c].fillna(df[c + '_y'])

    # ---- FMP secondary fills (NaN-only) + derived governance/quality flags ----
    # Fills touch ONLY estimate-family and archetype-facing return/margin
    # columns, never a forensic/NNWC input, and only where our primary value
    # is missing, so coverage rises without any FMP figure displacing an
    # EDGAR-primary one. fmp_filled_<col> marks which rows a fill touched, so
    # provenance stays inspectable in the audit.
    def _num_or_nan(col):
        return pd.to_numeric(df[col], errors='coerce') if col in df.columns else pd.Series(np.nan, index=df.index)
    def _fmp_fill(base, fmp_col):
        if fmp_col not in df.columns:
            return
        prim = pd.to_numeric(df[base], errors='coerce') if base in df.columns else pd.Series(np.nan, index=df.index)
        sec = pd.to_numeric(df[fmp_col], errors='coerce')
        df['fmp_filled_' + base] = (prim.isna() & sec.notna()).astype(int)
        df[base] = prim.fillna(sec)
    # Coalesce ONLY the estimate family into base columns: it is the genuine
    # coverage gap (native earnings_beat_rate / avg_earnings_surprise are
    # 57-67% missing) and feeds a single, quality-gated score. The fundamental
    # / ratio fills (fmp_ebitda_margin, fmp_gross_margin, fmp_fcf_yield,
    # fmp_pb, fmp_ev_ebitda, fmp_dividend_yield) are deliberately NOT coalesced
    # into gate-feeding base columns: doing so silently shifted archetype
    # membership (e.g. +129 arch_negative_ev_value, +25 arch_owner_operator,
    # some of them melting "ice cubes" whose melt guard was blind on the
    # newly-filled column). They remain available as fmp_ columns so a later,
    # per-archetype step can adopt them WITH that archetype's own guards.
    for _b, _f in (('earnings_beat_rate', 'fmp_earnings_beat_rate'),
                   ('avg_earnings_surprise', 'fmp_avg_earnings_surprise'),
                   # the universe-wide bulk feed (same statistics: 4-report beat
                   # share, mean surprise, consecutive-beat streak) fills last
                   ('earnings_beat_rate', 'esb_beat_share_4q'),
                   ('avg_earnings_surprise', 'esb_surprise_4q'),
                   ('earnings_beat_streak', 'esb_beat_streak')):
        _fmp_fill(_b, _f)

    # STATEMENT-HISTORY fills: the EDGAR-only multi-year quality columns, filled
    # from the global FMP statement engine ONLY where the EDGAR value is absent
    # (i.e. the ~29k non-US names). This is the reach win — the quality /
    # compounder archetypes consume the same column names and now fire globally
    # with no gate change. Forensic/NNWC inputs are deliberately NOT in this
    # list. Each fill records fmp_filled_<col> provenance. Validated against the
    # methodology audit (quality gates require positive lindy returns, so fills
    # add durable names rather than melting ones).
    for _b, _f in (('roic_lindy', 'fmp_st_roic_lindy'),
                   ('roiic_lindy', 'fmp_st_roiic_lindy'),
                   ('n_yrs_positive_roic', 'fmp_st_n_yrs_positive_roic'),
                   ('n_yrs_positive_fcf', 'fmp_st_n_yrs_positive_fcf'),
                   ('n_yrs_positive_opinc', 'fmp_st_n_yrs_positive_opinc'),
                   ('op_margin_lindy', 'fmp_st_op_margin_lindy'),
                   ('ebitda_margin_lindy', 'fmp_st_ebitda_margin_lindy'),
                   # book-value-PER-SHARE CAGR (EDGAR's is total equity): the
                   # per-share form is the better thesis measure — a rights
                   # issue lifts total equity but not BVPS
                   ('equity_cagr_5y', 'fmp_st_equity_cagr'),
                   # 3y and 5y over EXACT spans (EDGAR definitions). Filling
                   # both from one endpoint CAGR made 3y == 5y for every FMP
                   # row, which zeroed revenue acceleration and double-counted
                   # one fact in the lynch / tenbagger lens medians.
                   ('revenue_5y_cagr', 'fmp_st_revenue_5y_cagr'),
                   ('revenue_3y_cagr', 'fmp_st_revenue_3y_cagr'),
                   ('revenue_acceleration_lindy', 'fmp_st_revenue_accel_lindy'),
                   ('asset_3y_cagr', 'fmp_st_asset_3y_cagr'),
                   ('asset_5y_cagr', 'fmp_st_asset_5y_cagr'),
                   ('cash_roic_lindy', 'fmp_st_cash_roic_lindy'),
                   ('cash_roiic_lindy', 'fmp_st_cash_roiic_lindy'),
                   ('roiic_acceleration', 'fmp_st_roiic_acceleration'),
                   ('roic_inflection_flag', 'fmp_st_roic_inflection_flag'),
                   ('cash_roic_inflection_flag', 'fmp_st_cash_roic_inflection_flag'),
                   ('roic_acceleration', 'fmp_st_roic_acceleration'),
                   ('shares_growth_3y', 'fmp_st_shares_growth_3y'),
                   ('shares_growth_5y', 'fmp_st_shares_growth_5y'),
                   ('years_of_history', 'fmp_st_years_of_history')):
        _fmp_fill(_b, _f)
    # cheap_per_roiic_lindy is DERIVED from roiic_lindy (edgar_roic_roiic.
    # cheap_per_roiic: ev_ebitda / (roiic x 100), roiic > 0); recompute it where
    # roiic_lindy was just filled, else arch_cheap_per_roiic stays EDGAR-only.
    _roiic_f = _num_or_nan('roiic_lindy')
    df['fmp_st_cheap_per_roiic'] = (_num_or_nan('ev_ebitda') / (_roiic_f * 100)).where(
        (_roiic_f > 0) & (_num_or_nan('ev_ebitda') > 0))
    _fmp_fill('cheap_per_roiic_lindy', 'fmp_st_cheap_per_roiic')

    # SEGMENT fills: FMP product/geographic revenue segmentation fills the
    # EDGAR dimensional-harvest columns only where EDGAR has nothing (~90% of
    # the universe, incl. every non-US filer), so the segment archetypes
    # (diversified / concentrated / geographic-global / fastest-segment) reach
    # every filer FMP covers. Revenue-based legs only: segment op-margin, op
    # leverage and the margin-inflection flag stay EDGAR-only (FMP has no
    # segment EBIT), so those confirm legs simply stay absent for FMP names.
    # RECONCILIATION guard: SHARE-based fields (HHI, largest / fastest share,
    # share delta) are only meaningful when the segments sum to the company
    # (0.8-1.2x the same-FY consolidated revenue). Partial disclosure (KO's
    # geographic axis covers 66% of sales) or overlapping hierarchies would
    # otherwise fake concentration / diversification. Growth rates of a
    # segment are valid either way. Unknown coverage passes (no IS revenue).
    for _pre in ('fmp_seg', 'fmp_geo'):
        _cov = _num_or_nan(f'{_pre}_coverage')
        _rec_ok = _cov.isna() | ((_cov >= 0.8) & (_cov <= 1.2))
        for _c in (f'{_pre}_hhi', f'{_pre}_largest_share', f'{_pre}_fastest_share',
                   f'{_pre}_fastest_share_delta', f'{_pre}_hhi_delta'):
            if _c in df.columns:
                df[_c + '_rec'] = _num_or_nan(_c).where(_rec_ok)
    # MATERIAL-AXIS guard for GROWTH fields: an axis covering < 50% of the
    # company's revenue is a sub-ledger, not the business — for most banks
    # FMP's "product segments" are only the fee lines (HNVR 0.7%, WBS 5%,
    # CFG 7% of revenue), so a fast-growing deposit-fee line is not a hidden
    # engine. Growth / rot / momentum fills need coverage >= 0.5 (unknown
    # coverage passes).
    _cov_p = _num_or_nan('fmp_seg_coverage')
    _mat_p = _cov_p.isna() | (_cov_p >= 0.5)
    for _c in ('fmp_seg_fastest_yoy', 'fmp_seg_fastest_yoy_q', 'fmp_seg_fastest_accel_fy',
               'fmp_seg_fastest_consec_growth_q', 'fmp_seg_core_declining',
               'fmp_seg_growth_dispersion'):
        if _c in df.columns:
            df[_c + '_mat'] = _num_or_nan(_c).where(_mat_p)
    # quarterly corroboration of the fastest segment, EDGAR definition:
    # latest-quarter YoY positive and >= half the FY rate
    _fq_y = _num_or_nan('fmp_seg_fastest_yoy_q_mat'); _ff_y = _num_or_nan('fmp_seg_fastest_yoy_mat')
    df['fmp_seg_q_confirm'] = ((_fq_y > 0) & (_ff_y.isna() | (_fq_y >= 0.5 * _ff_y))).astype(float) \
        .where(_fq_y.notna())
    for _b, _f in (('segment_count', 'fmp_seg_count'),
                   ('segment_revenue_hhi', 'fmp_seg_hhi_rec'),
                   ('largest_segment_share', 'fmp_seg_largest_share_rec'),
                   ('geographic_region_count', 'fmp_geo_count'),
                   ('largest_region_share', 'fmp_geo_largest_share_rec'),
                   ('fastest_segment_yoy', 'fmp_seg_fastest_yoy_mat'),
                   ('fastest_seg_yoy_fy', 'fmp_seg_fastest_yoy_mat'),
                   ('fastest_seg_yoy_q', 'fmp_seg_fastest_yoy_q_mat'),
                   ('fastest_seg_accel_fy', 'fmp_seg_fastest_accel_fy_mat'),
                   ('fastest_seg_q_confirm', 'fmp_seg_q_confirm'),
                   ('fastest_seg_consec_growth', 'fmp_seg_fastest_consec_growth_q_mat'),
                   ('fastest_segment_share', 'fmp_seg_fastest_share_rec'),
                   ('fastest_segment_share_delta', 'fmp_seg_fastest_share_delta_rec'),
                   ('segment_hhi_delta', 'fmp_seg_hhi_delta_rec'),
                   ('seg_core_declining', 'fmp_seg_core_declining_mat'),
                   ('segment_growth_dispersion', 'fmp_seg_growth_dispersion_mat')):
        _fmp_fill(_b, _f)
    # ---- QUARTERLY forensic fills (fmp_quarterly.py) ----
    # CURRENCY BRIDGE. fq_* levels are in the filer's REPORTING currency; the
    # master's market cap is in the LISTING currency (they differ for ADRs /
    # cross-listings — the mismatch that produced 150x yield errors earlier).
    # Use a TRUE exchange rate, not a revenue ratio (a revenue ratio mixes
    # currency with period growth: Climb Global's revenue doubled between the
    # two TTM windows, so the ratio read 0.5 for a USD-in-USD name).
    #   fx = USD per reporting-ccy unit (fmp_fx.py spot table)
    #        / USD per listing-ccy unit (the master's own market_cap_usd /
    #          market_cap, i.e. exactly the unit the comparison is made in)
    # VALIDATION: master revenue_ttm / (fq_revenue x fx) should be within
    # [0.5, 2] (period drift only). Outside that the currency label or units
    # are wrong (e.g. FMP tagging a Schibsted ADR as JPY) and the bridge is
    # voided rather than trusted.
    _frev = _num_or_nan('fq_revenue')
    _fx = pd.Series(np.nan, index=df.index)
    if os.path.exists('fmp_fx_usd.csv') and 'fmp_q_ccy' in df.columns:
        _usd = pd.read_csv('fmp_fx_usd.csv').set_index('currency')['usd_per_unit']
        _rep = df['fmp_q_ccy'].map(_usd)
        _mc, _mcu = _num_or_nan('market_cap'), _num_or_nan('market_cap_usd')
        _lst = (_mcu / _mc).where((_mc > 0) & (_mcu > 0))
        _fx = (pd.to_numeric(_rep, errors='coerce') / _lst)
        _chk = _num_or_nan('revenue_ttm') / (_frev * _fx)
        _fx = _fx.where(_chk.isna() | ((_chk >= 0.5) & (_chk <= 2.0)))
    df['fq_fx_to_master'] = _fx
    _q_ok = (df['fmp_q_status'].astype(str) == 'ok') if 'fmp_q_status' in df.columns else pd.Series(False, index=df.index)

    def _conv(col):
        return (_num_or_nan(col) * _fx).where(_q_ok)

    # LEVEL fills (converted to master currency; NaN-only, provenance-marked).
    # ONLY the EDGAR-only columns. Master-core columns (net_income_ttm,
    # cfo_ttm, capex_ttm, da_ttm, total_debt) are deliberately NOT filled —
    # the policy above: coalescing core columns silently shifts membership
    # and desynchronises them from the master ratios (p_e, fcf_yield) that
    # stay NaN. Their fq_* values remain available as confirming legs.
    # Tax columns are not filled either: the annual cash tax next to a TTM
    # book tax is a window mismatch; XR43 reads the like-for-like annual
    # fq_ rates directly.
    _lvl = {'retained_earnings': 'fq_retained_earnings', 'deferred_revenue': 'fq_defrev',
            'pretax_income_ttm': 'fq_pretax', 'income_continuing_ops_ttm': 'fq_ni_cont',
            'income_discontinued_ops_ttm': 'fq_ni_disc',
            # NOT ppe_net: FMP's propertyPlantEquipmentNet includes operating-
            # lease right-of-use assets (no separate ROU line to subtract) —
            # on the US overlap it exceeds EDGAR's net PP&E by >25% for 47% of
            # names (78% agree once ROU is added back). A lease-inflated PP&E
            # would bias the D&A/PP&E cliff and asset-heavy tests.
            'assets': 'fq_total_assets', 'equity': 'fq_equity',
            'financing_cf_ttm': 'fq_financing_cf'}
    # Retained earnings sanity: RE cannot exceed equity by more than the
    # treasury stock bought back out of it (plus 5% for AOCI); above that FMP
    # has mapped IFRS "reserves" (share premium etc.) into retainedEarnings,
    # which would fake a retained-earnings discount. Such rows are not filled.
    if 'fq_retained_earnings' in df.columns:
        _re_q = _num_or_nan('fq_retained_earnings')
        _re_cap = 1.05 * _num_or_nan('fq_equity') + _num_or_nan('fq_treasury').abs().fillna(0)
        df['fq_retained_earnings_valid'] = _re_q.where((_re_q > 0) & (_re_q <= _re_cap) | (_re_q <= 0))
        _lvl['retained_earnings'] = 'fq_retained_earnings_valid'
    # (audit 4) a total-assets figure of zero or less is a provider zero-fill,
    # not a balance sheet (2,247 names: equity then "exceeds assets" and the
    # data-quality flag fires on a clean ledger) — it is not filled
    if 'fq_total_assets' in df.columns:
        df['fq_total_assets_valid'] = _num_or_nan('fq_total_assets').where(_num_or_nan('fq_total_assets') > 0)
        _lvl['assets'] = 'fq_total_assets_valid'
    for _b, _f in _lvl.items():
        if _f in df.columns:
            df['fq_conv_' + _b] = _conv(_f)
            _fmp_fill(_b, 'fq_conv_' + _b)
    if 'fq_nwc' in df.columns:
        df['fq_conv_nwc'] = _conv('fq_nwc'); _fmp_fill('net_working_capital', 'fq_conv_nwc')
    if 'fq_equity' in df.columns and 'fq_gw_intang' in df.columns:
        df['fq_conv_tangible_equity'] = ((_num_or_nan('fq_equity') - _num_or_nan('fq_gw_intang').fillna(0)) * _fx).where(_q_ok)
        _fmp_fill('tangible_equity', 'fq_conv_tangible_equity')
        # price / tangible book, built exactly as EDGAR builds it (listing-ccy
        # market cap over converted tangible equity); positive book only
        _teq_c = df['fq_conv_tangible_equity']
        df['fq_p_tb'] = (_num_or_nan('market_cap') / _teq_c).where(_teq_c > 0)
        _fmp_fill('p_tb', 'fq_p_tb')
    # STREAKS (EDGAR edgar_streaks columns are in QUARTERS): the engine's
    # date-matched streaks are in months, so quarter-equivalents = months / 3
    # (a half-yearly filer's 2-period streak is 4 quarter-equivalents, not 2).
    df['fq_rev_yoy_streak_qeq'] = (_num_or_nan('fq_rev_yoy_streak_m') / 3.0).where(_q_ok)
    df['fq_ni_yoy_streak_qeq'] = (_num_or_nan('fq_ni_yoy_streak_m') / 3.0).where(_q_ok)
    # positive-YoY hit rate: only when the comparisons span >= 24 months
    _span_m = _num_or_nan('fq_rev_yoy_n_cmp') * 12.0 / _num_or_nan('fmp_q_periods_per_year')
    df['fq_rev_pos_share_24m'] = _num_or_nan('fq_rev_yoy_pos_share').where(_q_ok & (_span_m >= 24))
    for _b, _f in (('rev_yoy_streak_q', 'fq_rev_yoy_streak_qeq'),
                   ('ni_yoy_streak_q', 'fq_ni_yoy_streak_qeq'),
                   ('rev_yoy_pos_share_12q', 'fq_rev_pos_share_24m')):
        _fmp_fill(_b, _f)
    # MULTI-YEAR averages (EDGAR _avg_over definitions, from fmp_statements):
    # reporting-currency levels, converted with the same validated bridge.
    for _b, _f in (('ni_avg', 'fmp_st_ni_avg'), ('capex_avg', 'fmp_st_capex_avg'),
                   ('oe_avg', 'fmp_st_oe_avg')):
        if _f in df.columns:
            df['fq_conv_' + _b] = _num_or_nan(_f) * _fx
            _fmp_fill(_b, 'fq_conv_' + _b)
    # DIMENSIONLESS fills (currency cancels; no bridge needed). fq_sbc is NaN
    # where the filer does not disclose SBC (engine rule), so a non-discloser
    # is never certified "low SBC".
    # (SBC <= 0 is not a disclosure: FMP carries some IFRS filers' SBC with the
    # add-back sign flipped, e.g. CNY/HKD rows at -0.4% of sales)
    df['fq_sbc_pct_revenue'] = (_num_or_nan('fq_sbc') / _frev).where(
        _q_ok & (_frev > 0) & (_num_or_nan('fq_sbc') > 0))
    # effective tax rate: same-fiscal-year book tax / pretax, inside EDGAR's
    # validity band (-10%, 60%) — outside it the rate is a loss-year artifact
    _etr = _num_or_nan('fq_book_tax_rate_fy')
    df['fq_etr_valid'] = _etr.where((_etr > -0.10) & (_etr < 0.60))
    for _b, _f in (('goodwill_intangibles_pct_assets', 'fq_gw_pct_assets'),
                   ('sbc_pct_revenue', 'fq_sbc_pct_revenue'),
                   ('interest_coverage', 'fq_interest_cover'),
                   ('effective_tax_rate', 'fq_etr_valid')):
        if _f in df.columns:
            _fmp_fill(_b, _f)
    # (endpoint matrix, REACH: low_sbc_quality) where neither EDGAR nor the
    # quarterly TTM carries SBC, the latest fiscal year's disclosed SBC /
    # revenue from the annual cash-flow statement (same reportedCurrency, so
    # dimensionless). Disclosed = strictly positive (same sign rule as fq_sbc).
    # Filled after the TTM fill so it only reaches still-missing rows; the
    # provenance flag is kept separately so the TTM fill's flag survives.
    if 'fmp_st_sbc_pct_revenue' in df.columns:
        _st_sbc = _num_or_nan('fmp_st_sbc_pct_revenue')
        df['fmp_st_sbc_pct_revenue_valid'] = _st_sbc.where((_st_sbc > 0) & (_st_sbc < 1.0))
        _prev_sbc_flag = df.get('fmp_filled_sbc_pct_revenue')
        _fmp_fill('sbc_pct_revenue', 'fmp_st_sbc_pct_revenue_valid')
        df['fmp_filled_sbc_pct_revenue_fy'] = df['fmp_filled_sbc_pct_revenue']
        if _prev_sbc_flag is not None:
            df['fmp_filled_sbc_pct_revenue'] = _prev_sbc_flag

    # text companions (names) for the books, NaN-only as well
    for _b, _f in (('largest_segment_name', 'fmp_seg_largest_name'),
                   ('fastest_segment_name', 'fmp_seg_fastest_name'),
                   ('largest_region_name', 'fmp_geo_largest_name')):
        if _f in df.columns:
            if _b not in df.columns:
                df[_b] = np.nan
            df[_b] = df[_b].where(df[_b].notna(), df[_f])

    # Capital-return YIELD, made currency-correct by decomposition. FMP's
    # marketCap (and every yield it derives) is in the LISTING currency for
    # ADRs / cross-listings while the statements are in the reporting currency,
    # so FMP's own yield is unusable for the non-US cohort (NOAH: 56% vs a sane
    # 0.98 payout). But yield = payout_ratio x earnings_yield, and BOTH factors
    # are trustworthy: the payout ratio is currency-invariant (both figures
    # local, from FMP) and earnings_yield is our own FX-handled master column.
    # Their product is the cash returned as a fraction of what you pay — exactly
    # what arch_capital_returner (>=5% of mcap/yr) needs — with no FMP mcap used.
    # Both inputs must be economically VALID at the source, because both can be
    # currency-corrupt for foreign/ADR listings: our master's earnings_yield is
    # sometimes wrong for ADRs (UVRBF read 531%, i.e. a P/E of 0.19 — a USD
    # market cap over local net income), and FMP's payout ratio blows up when
    # FMP net income is near zero (KGGNF payout 182x). Bounding earnings_yield
    # to <= 50% (P/E >= 2) and payout to <= 300% (3y median) drops those
    # artifacts rather than clamping a real value; a legitimate cheap
    # high-returner still passes and the product is its true cash-return yield.
    # A decomposed yield above ~30% is, by the framework's own definition
    # (see the capital_returner audit), a stale-price / return-of-capital
    # artifact rather than a sustainable policy — and here it comes from an
    # inflated earnings_yield on a cheap or stale-priced name. So we fill only
    # within that trusted policy band and leave the artifact tail unfilled
    # (NaN), rather than assert an unreliable yield. This is a validity filter
    # grounded in the domain definition, not a cosmetic clamp of a real number.
    _mkt_ey = pd.to_numeric(df.get('earnings_yield'), errors='coerce') if 'earnings_yield' in df.columns else pd.Series(np.nan, index=df.index)
    _ey_ok = (_mkt_ey > 0) & (_mkt_ey <= 0.50)
    for _yldcol, _paycol in (('capital_return_yield', 'fmp_st_capital_return_payout'),
                             ('buyback_yield', 'fmp_st_buyback_payout'),
                             ('dividend_yield', 'fmp_st_dividend_payout_cf')):
        if _paycol in df.columns:
            _pay = pd.to_numeric(df[_paycol], errors='coerce')
            _decomp = (_pay * _mkt_ey).where((_pay >= 0) & (_pay <= 3.0) & _ey_ok)
            _decomp = _decomp.where(_decomp <= 0.30)   # domain validity ceiling
            df['fmp_st_' + _yldcol + '_decomp'] = _decomp
            _fmp_fill(_yldcol, 'fmp_st_' + _yldcol + '_decomp')
    # Altman-Z distress (< 1.81 = distress zone) and Piotroski quality (>= 7),
    # surfaced as flags. Distress is a DISQUALIFIER FLAG shown beside the two
    # cash-rich Cluseau value archetypes, never a gate (see the note at
    # arch_cluseau_realizable_book); Altman Z is a spirit weight elsewhere.
    df['fmp_distress_flag'] = (_num_or_nan('fmp_altman_z') < 1.81).fillna(False).astype(int)
    df['fmp_piotroski_strong_flag'] = (_num_or_nan('fmp_piotroski') >= 7).fillna(False).astype(int)
    # Insider alignment: trailing open-market buy $ >= this year's exec comp
    # (ratio >= 1) is a strong revealed-preference conviction signal.
    df['fmp_insider_aligned_flag'] = (_num_or_nan('fmp_insider_alignment_ratio') >= 1.0).fillna(False).astype(int)

    # ---- Nuanced (second-order) SURFACED flags — informational, never gates ----
    # These confirm or qualify a thesis alongside an archetype; none removes a
    # name from any archetype (the codebase surfaces disqualifiers, it does not
    # veto with them). All degrade silently to 0 where the FMP field is absent.
    _iq = _num_or_nan('fmp_income_quality')            # CFO / net income
    _cxd = _num_or_nan('fmp_capex_to_depreciation')
    _ccc = _num_or_nan('fmp_cash_conversion_cycle')
    _rd = _num_or_nan('fmp_rd_to_revenue')
    _ib = _num_or_nan('fmp_interest_burden')           # pretax / EBIT (low => heavy interest drag)
    # earnings backed by cash (positive quality corroborator for understated-
    # earnings / asleep-at-wheel); and its low-quality counterpart, SURFACED.
    df['fmp_earnings_cash_backed_flag'] = ((_iq >= 1.0)).fillna(False).astype(int)
    df['fmp_low_earnings_quality_flag'] = ((_iq < 0.7) & _iq.notna()).fillna(False).astype(int)
    # capex regime: genuine harvester (capex well below D&A) vs growth-capex
    # depressing FCF (capex well above D&A) — both are hidden-value tells when
    # paired with the relevant archetype; surfaced, not gated.
    df['fmp_asset_harvester_flag'] = ((_cxd < 0.70) & _cxd.notna()).fillna(False).astype(int)
    df['fmp_growth_capex_masked_flag'] = ((_cxd > 1.50)).fillna(False).astype(int)
    # negative cash-conversion cycle: customers fund the business (float).
    df['fmp_customer_float_flag'] = ((_ccc < 0) & _ccc.notna()).fillna(False).astype(int)
    # real expensed-growth investment (distinguishes F3 hidden value from SG&A
    # waste): a material R&D load rather than an unexplained margin gap.
    df['fmp_rd_intensive_flag'] = ((_rd >= 0.10)).fillna(False).astype(int)
    # returns leaning on leverage rather than operations (low interest burden).
    df['fmp_levered_returns_flag'] = ((_ib < 0.70) & _ib.notna()).fillna(False).astype(int)

    # ---- Dynamic (multi-period) SURFACED confirmers — informational, non-veto ----
    # From fmp_dynamics.py: clean quarterly trajectories that corroborate the
    # evolution / step-change archetypes far better than the noisy sequential
    # proxies. None gates; each rides alongside as a confirming tag.
    _dyn_gap = _num_or_nan('fmp_dyn_unrerated_gap')
    _dyn_accel = _num_or_nan('fmp_dyn_rev_accel')
    _dyn_im = _num_or_nan('fmp_dyn_incremental_ebit_margin')
    _dyn_streak = _num_or_nan('fmp_dyn_rev_streak_q')
    _dyn_fwd_cross = _num_or_nan('fmp_dyn_fwd_ebit_crossing')
    _dyn_ug = _num_or_nan('fmp_dyn_fwd_underestimate_gap')
    _beat = _num_or_nan('fmp_earnings_beat_rate')
    # fundamentals compounded but the multiple did not follow (coiled spring).
    df['fmp_dyn_unrerated_flag'] = ((_dyn_gap > 0.15)).fillna(False).astype(int)
    # revenue growth accelerating (real 2nd-derivative, not the annual fallback).
    df['fmp_dyn_accelerating_flag'] = ((_dyn_accel > 0.05)).fillna(False).astype(int)
    # operating leverage kicking in (incremental EBIT margin high).
    df['fmp_dyn_op_leverage_flag'] = ((_dyn_im >= 0.30)).fillna(False).astype(int)
    # durable audited growth streak (>= 6 consecutive positive-YoY quarters).
    # (positional 4-period lag: quarterly filers only — see XR9)
    df['fmp_dyn_growth_streak_flag'] = ((_dyn_streak >= 6)
                                        & ~(_num_or_nan('fmp_q_periods_per_year') == 2)).fillna(False).astype(int)
    # forward consensus EBIT crossing from loss to profit (before-it-crosses).
    df['fmp_dyn_fwd_inflection_flag'] = ((_dyn_fwd_cross >= 1)).fillna(False).astype(int)
    # "asleep at the wheel", forward edition: chronic beats AND forward
    # consensus lowballs the delivered trajectory (guidance off the mark).
    df['fmp_dyn_forward_asleep_flag'] = ((_dyn_ug > 0.10) & (_beat >= 0.6)).fillna(False).astype(int)

    # ---- QUARTERLY FORENSIC flags (fmp_quarterly.py) — SURFACED, never gates ----
    # Global 3-statement forensics that were EDGAR-only (or absent) before.
    # Each is a tell to read alongside an archetype, not a disqualifier.
    # Accrual / Beneish models are built for operating companies: a bank's
    # "receivables" are its loans and its CFO swings with deposits, so
    # financials are left unscored (0) rather than mis-scored.
    _sect = df['sector'].fillna('').astype(str) if 'sector' in df.columns else pd.Series('', index=df.index)
    _fq_op = _q_ok & ~_sect.str.contains('Financial', case=False)
    _fq = lambda c: _num_or_nan(c).where(_fq_op)
    _qdso, _qdso_p = _fq('fq_dso'), _fq('fq_dso_p')
    _qdio, _qdio_p = _fq('fq_dio'), _fq('fq_dio_p')
    _qccc, _qccc_p = _fq('fq_ccc'), _fq('fq_ccc_p')
    _qrevg = _fq('fq_rev_growth')
    _qacq = _fq('fq_acq_pct_assets')
    _qcfo, _qni_cf = _fq('fq_cfo'), _fq('fq_ni_cf')
    _q_rev = _fq('fq_revenue')
    # WC-release share of CFO: a CFO > NI that comes from liquidating working
    # capital is a one-off, not conservative accounting (chg_wc > 0 = release)
    _q_wc_share = (_fq('fq_chg_wc') / _qcfo.where(_qcfo > 0))
    # RED tells
    #   Beneish M > -1.78: the published manipulation threshold (Beneish 1999).
    #   Two known false-positive mechanisms are separated, not scored:
    #   * ACQUISITIONS (> 10% of assets) mechanically inflate SGI and AQI —
    #     surfaced as fq_beneish_ma_distorted instead;
    #   * pure GROWTH: SGI alone can push M over the line for a clean fast
    #     grower, so one of the manipulation-specific drivers must also be
    #     elevated (receivables index DSRI > 1.2 or accruals TATA > 0.05).
    _qm = _fq('fq_beneish_m')
    _q_ma = (_qacq > 0.10)
    _q_driver = (_fq('fq_beneish_dsri') > 1.2) | (_fq('fq_beneish_tata') > 0.05)
    df['fq_beneish_risk_flag'] = ((_qm > -1.78) & ~_q_ma.fillna(False) & _q_driver).fillna(False).astype(int)
    df['fq_beneish_ma_distorted'] = ((_qm > -1.78) & _q_ma).fillna(False).astype(int)
    #   Sloan accruals >= 10% of assets on POSITIVE, material earnings with weak
    #   cash conversion: earnings running well ahead of cash (top-decile
    #   accruals underperform — Sloan 1996).
    df['fq_high_accruals_flag'] = (
        (_fq('fq_sloan_accruals') >= 0.10) & (_qni_cf > 0) & (_qni_cf >= 0.02 * _q_rev)
        & (_fq('fq_cfo_to_ni') < 0.7)).fillna(False).astype(int)
    #   receivables outgrowing sales by 30pp AND DSO up >= 15 days on a
    #   receivables-material business (DSO >= 45): revenue pulled forward /
    #   channel stuffing. Both legs (the ratio's tail is wide), no acquisition
    #   year (bought receivables), no base-effect year (sales more than
    #   doubled). Calibrated to a tail (~6% of operating names), not a norm.
    df['fq_receivables_divergence_flag'] = (
        (_fq('fq_rec_vs_rev') >= 0.30) & ((_qdso - _qdso_p) >= 15) & (_qdso >= 45)
        & ~_q_ma.fillna(False) & ~(_qrevg > 1.0).fillna(False)).fillna(False).astype(int)
    #   inventory outgrowing COGS by 30pp AND DIO up >= 20 days: unsold build.
    df['fq_inventory_build_flag'] = (
        (_fq('fq_inv_vs_cogs') >= 0.30) & ((_qdio - _qdio_p) >= 20)
        & ~_q_ma.fillna(False)).fillna(False).astype(int)
    #   SBC >= 30% of operating cash flow (observed SBC only — the engine
    #   blanks non-disclosers): the "cash" earnings are paid in stock.
    df['fq_sbc_heavy_flag'] = (_fq('fq_sbc_to_cfo') >= 0.30).fillna(False).astype(int)
    # GREEN tells
    #   cash leading book, on FREE cash flow: CFO above NI is the norm for any
    #   D&A-heavy business, so the tell is FCF (CFO - capex) >= 1.2x NI now AND
    #   >= 1.1x a year ago (persistent, same cash-flow basis), with cash
    #   growing >= 10pp faster than NI, NOT a working-capital liquidation
    #   (<= 30% of CFO) or an SBC add-back (< 25% of CFO). The understated-
    #   earnings / conservative-accounting signature, proven not inferred.
    _qfcf = _qcfo - _fq('fq_capex').abs()
    _qfcf_p = _fq('fq_cfo_p') - _fq('fq_capex_p').abs()
    _qni_cf_p = _fq('fq_ni_cf_p')
    df['fq_cash_leads_earnings_flag'] = (
        ((_qfcf / _qni_cf.where(_qni_cf > 0)) >= 1.2)
        & ((_qfcf_p / _qni_cf_p.where(_qni_cf_p > 0)) >= 1.1)
        & (_fq('fq_cfo_growth_minus_ni_growth') >= 0.10)
        & ~(_q_wc_share > 0.30).fillna(False)
        & ~(_fq('fq_sbc_to_cfo') >= 0.25).fillna(False)).fillna(False).astype(int)
    #   working-capital release: cash-conversion cycle shortened >= 15 days YoY
    #   off a positive base, with sales holding (a shrinking business also
    #   releases working capital — that is liquidation, not efficiency).
    #   Material: >= 30 days AND >= 20% of a >= 30-day cycle.
    df['fq_wc_release_flag'] = (
        (_qccc_p >= 30) & ((_qccc_p - _qccc) >= 30) & (((_qccc_p - _qccc) / _qccc_p) >= 0.20)
        & (_qrevg >= -0.05)).fillna(False).astype(int)
    #   deleveraging PROOF: net debt fell in consecutive balance-sheet periods
    #   spanning >= 9 months and by >= 5% of assets, NOT equity-funded (share
    #   count up <= 2%) and funded by operations (CFO > 0) rather than a
    #   disposal (discontinued share <= 20%). A path, not a snapshot.
    df['fq_deleveraging_flag'] = (
        (_fq('fq_netdebt_decline_months') >= 9)
        & (_fq('fq_netdebt_change_pct_assets') <= -0.05)
        & ~(_fq('fq_shares_yoy') > 0.02).fillna(False)
        & (_qcfo > 0)
        & ~(_fq('fq_disc_ops_share') > 0.20).fillna(False)).fillna(False).astype(int)
    #   gross-margin-led inflection (pricing power / mix, visible before EBIT).
    #   A full year of year-on-year gross-margin gains (>= 12 months), the
    #   latest by >= 1pp, on growing sales.
    df['fq_gm_inflection_flag'] = (
        (_fq('fq_gm_yoy_streak_m') >= 12) & (_qrevg >= 0.05)
        & (_num_or_nan('gross_margin_delta_yoy') >= 0.01)).fillna(False).astype(int)
    #   deferred revenue outgrowing revenue by >= 5pp on a material float
    #   (>= 10% of sales): bookings running ahead of recognised sales.
    df['fq_defrev_build_flag'] = (
        (_fq('fq_defrev_to_rev') >= 0.10)
        & (_fq('fq_defrev_growth_minus_rev') >= 0.05)).fillna(False).astype(int)
    #   cash-tax shield: annual cash tax <= 60% of the same year's book tax in
    #   a normal book-tax year (deferred-tax float / NOL / accelerated
    #   depreciation), persistent over >= 2 fiscal years.
    _qbr = _fq('fq_book_tax_rate_fy')
    df['fq_cash_tax_shield_flag'] = (
        _qbr.between(0.10, 0.45) & (_fq('fq_cash_tax_rate') > 0)
        & (_fq('fq_cash_tax_rate') <= 0.6 * _qbr)
        & (_fq('fq_cash_tax_wedge_med') >= 0.40)).fillna(False).astype(int)
    # CLEAN-ACCOUNTING confirmation (the positive counterpart): Beneish well
    # inside the safe zone, low accruals, no receivable / inventory divergence,
    # with at least three of the four measures present. A forensic hidden-value
    # thesis that is ALSO clean is evidence; one that trips the red tells is a
    # warning. Surfaced / used as a confirming multiplier, never a gate.
    _cl_legs = pd.concat([
        (_qm < -2.22).where(_qm.notna()),
        (_fq('fq_sloan_accruals') <= 0.05).where(_fq('fq_sloan_accruals').notna()),
        (_fq('fq_rec_vs_rev') < 0.15).where(_fq('fq_rec_vs_rev').notna()),
        (_fq('fq_inv_vs_cogs') < 0.15).where(_fq('fq_inv_vs_cogs').notna())], axis=1).astype(float)
    df['fq_forensic_clean_confirm'] = (
        (_cl_legs.notna().sum(axis=1) >= 3) & (_cl_legs.fillna(1).min(axis=1) == 1)).astype(int)
    # composite for books / sorting: red tells minus green tells (informational)
    df['fq_forensic_red_count'] = (df['fq_beneish_risk_flag'] + df['fq_high_accruals_flag']
                                   + df['fq_receivables_divergence_flag']
                                   + df['fq_inventory_build_flag'] + df['fq_sbc_heavy_flag'])
    df['fq_forensic_green_count'] = (df['fq_cash_leads_earnings_flag'] + df['fq_wc_release_flag']
                                     + df['fq_deleveraging_flag'] + df['fq_gm_inflection_flag']
                                     + df['fq_defrev_build_flag'] + df['fq_cash_tax_shield_flag'])

    # ---------- helper accessors ----------
    _absent_cols: set = set()
    _sparse_cols: dict = {}

    def _note_coverage(col, series=None):
        if series is not None:
            cov = float(series.notna().mean())
            if cov < 0.02:
                _sparse_cols[col] = cov

    def s(col, default=0.0):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors='coerce')
            _note_coverage(col, v)
            return v.fillna(default)
        _absent_cols.add(col)
        return pd.Series(default, index=df.index)

    sector = df['sector'].fillna('') if 'sector' in df.columns else pd.Series('', index=df.index)
    country = df['src'].fillna('').astype(str).str.upper() if 'src' in df.columns else pd.Series('', index=df.index)

    # Use mcap_usd (FX-converted) when available - critical for cross-country
    # comparisons.  Falls back to raw market_cap (local currency) only if
    # fix_pipeline.py hasn't been run yet.
    mcap = s('market_cap_usd') if 'market_cap_usd' in df.columns else s('market_cap')
    price_yoy = s('price_yoy')
    mom12 = s('momentum_12m')
    rev_yoy = s('rev_yoy').clip(-1.0, 10.0)      # artifact-tail clamp at source
    rev_accel = s('rev_accel')
    ebitda_margin = s('ebitda_margin')
    ebitda_margin_delta = s('ebitda_margin_delta_yoy').clip(-1.0, 1.0)  # clamp at source
    ebitda_inflection = s('ebitda_inflection')
    cfo_inflection = s('cfo_inflection')
    fcf_inflection = s('fcf_inflection')
    rev_inflection = s('rev_inflection')
    roce_inflection = s('roce_inflection')
    ebitda_first_pos = s('ebitda_first_positive')
    cfo_first_pos = s('cfo_first_positive')
    fcf_first_pos = s('fcf_first_positive')
    ni_first_pos = s('net_income_first_positive')
    roce_first_pos = s('roce_first_positive')
    pb = s('pb', 99.0)
    fcf_yield = s('fcf_yield')
    cash_gt_ev = s('cash_gt_ev_flag')
    net_cash_pct = s('net_cash_pct_mcap')
    insider = s('insider_ownership_pct')
    # ===== SHARED ROBUSTNESS GUARDS (archetype audit 2026-09-08) =====
    # (G1) Sector guard: Financials / REITs / Utilities break EV, net-cash,
    # NCAV, margin, ROIC and coverage legs (deposits & float drive EV hugely
    # negative; "net cash" is an investment portfolio; margins/ROIC/coverage
    # aren't comparable). Rules for OPERATING businesses gate on is_operating;
    # financials get their own book-value archetypes.
    _ind_all = (df['industry'].fillna('').astype(str).str.lower()
                if 'industry' in df.columns else pd.Series('', index=df.index))
    _sec_l = sector.astype(str).str.lower()
    # (R1a) NULL-sector hole: a name whose sector is blank/NaN must NOT
    # auto-pass is_operating. Back-stop on the industry string so financial
    # names with a missing sector (banks/insurers/REITs/thrifts via industry
    # only) are still classed as financial rather than slipping through as
    # "operating". _sec_missing marks the rows where the sector is unusable.
    _sec_missing = _sec_l.isin(('', 'nan', 'none', 'null')) | sector.isna()
    _fin_ind_kw = ('bank', 'insur', 'thrift', 'mortgage', 'capital market',
                   'asset manage', 'financ', 'reit', 'brokerage',
                   'savings', 'lending', 'credit servic')
    _ind_is_financial = _ind_all.str.contains('|'.join(_fin_ind_kw))
    # (growth-audit) NULL-BOTH hole: when sector AND industry are both blank the
    # industry backstop can't fire, so insurers/banks with no classification
    # (TUGU "Tugu Insurance", SLDE "Slide Insurance") slip through as operating.
    # Fall back to the company NAME in that case only (a targeted last resort;
    # names carry the entity type — "... Insurance/Bancorp/Bank/Financial").
    _ind_missing = _ind_all.isin(('', 'nan', 'none', 'null'))
    _nm_l = (df['name'].fillna('').astype(str).str.lower()
             if 'name' in df.columns else pd.Series('', index=df.index))
    _name_is_financial = (_sec_missing & _ind_missing & _nm_l.str.contains(
        r'\binsurance\b|\bbancorp\b|\bbancshares\b|\bbank\b|reinsurance|'
        r'\bfinancial\b|\bholdings? (?:ltd|inc|corp)|'
        # (tail) foreign-language financial name terms — a NULL-sector/industry
        # insurer/bank still reads as financial (TUGU 'Asuransi').
        r'asuransi|seguros|segur|assicuraz|versicherung|banco|banque|'
        r'sigorta|ubezpiecze', regex=True))
    # (tail/fresh) known financial businesses mis-tagged as operating sectors in
    # the source data, so is_operating can't catch them and they leak into
    # operating screens: Dundee Corp (holdco tagged Consumer Staples); Jiayin /
    # 9F (Chinese consumer LENDERS tagged Communication Services / Software).
    _known_holdco = (df['symbol'].astype(str)
                     .isin({'DDEJF', 'DC-A.TO', 'DC.TO', 'JFIN', 'JFU', 'AMTD'})
                     # name backstop for the same lenders across any listing line.
                     # (deep-audit) AMTD Idea Group is a financial-services holdco
                     # (investment banking / asset management / insurance) but its
                     # sector AND industry are NaN and the name misses the finance
                     # regex, so it leaked into operating screens as an op-336%
                     # "melter" (geographic_global, diversified_segments, weschler,
                     # levered_inflection). Classify it financial at the source.
                     | _nm_l.str.contains(r'jiayin|9f inc|\bamtd\b', regex=True))
    is_financial = (_sec_l.str.contains('financ') | _ind_is_financial
                    | _name_is_financial | _known_holdco)
    is_reit = _sec_l.str.contains('real estate') | _ind_all.str.contains('reit')
    is_utility = _sec_l.str.contains('utilit') | (
        _sec_missing & _ind_all.str.contains('utilit'))
    # A NULL-sector name whose industry looks financial/REIT/utility is NOT
    # operating; a NULL-sector name with no financial industry signal is left
    # operating (genuine unknown-sector operating co) — the backstop only
    # closes the financial-leak hole, it doesn't fail every unknown sector.
    is_operating = ~(is_financial | is_reit | is_utility)
    # (G2) Denominator-sanity clamps: cash > 100% of mcap for an OPERATING
    # value thesis is a shell/holdco artifact; a real EBITDA margin sits in
    # (0, 0.6) — above that is one-off asset-sale / non-operating income.
    net_cash_pct_sane = net_cash_pct.where(net_cash_pct <= 1.0)
    ebitda_margin_sane = ebitda_margin.where((ebitda_margin > 0)
                                             & (ebitda_margin < 0.6))
    # (R4) Current-state floor for backward-looking multi-year gates. A lindy
    # ROIC streak or an n-year FCF count is a HISTORY; a name whose returns
    # have since turned negative (melting ice cube) must not still qualify as
    # "durable". _roce_now_ok requires the CURRENT roce to be non-negative
    # (NaN roce is left permissive — the multi-year gate carries the weight
    # there — but a KNOWN-negative current roce fails the durability claim).
    _roce_now = s('roce', np.nan)
    _opm_now = s('op_margin', np.nan)
    _fcf_now = s('fcf_ttm', np.nan)
    # (user directive: "cash-on-cash returns and various implementations of it
    # are as important as ROCE; be more benign if ROCE is improving; demote if
    # melt, don't bar"). CASH-ON-CASH RETURN present through ANY robust lens —
    # a name generating owner cash is NOT melting even if its accounting ROCE
    # reads poorly. Uses the durable cash yields preferentially (owner-earnings /
    # robust cash yield / CFO yield / cash conversion / FCF margin), so a single
    # working-capital FCF blip is not the whole story but real cash generation
    # exempts a name from the melt judgement.
    # NOTE: only SIGN-MEANINGFUL absolute cash yields — NOT cash_conversion
    # (=CFO/EBITDA), a ratio that reads positive when BOTH are negative (FOM.CO
    # CFO-63% shows cash_conversion 0.84) and would wrongly exempt a dead name.
    _cash_return_ok = ((fcf_yield > 0)
                       | (s('owner_earnings_yield', np.nan) > 0)
                       | (s('robust_cash_yield', np.nan) > 0)
                       | (s('cfo_yield', np.nan) > 0)
                       | (s('fcf_margin', np.nan) > 0))
    # RETURNS IMPROVING — a negative-but-inflecting name is a turnaround, not an
    # ice cube; be benign (do not bar, and demote less).
    _returns_improving = ((s('roce_delta_yoy', np.nan) > 0)
                          | (s('roce_inflection', np.nan) > 0)
                          | (s('roce_first_positive', np.nan) > 0)
                          | (s('fcf_inflection', np.nan) > 0)
                          | (s('op_margin_delta_yoy', np.nan) > 0)
                          | (s('ebitda_inflection', np.nan) > 0))
    # (R4) Current-state floor for backward-looking multi-year gates — now
    # cash-aware and improvement-lenient: a KNOWN-negative current ROCE fails
    # the durability claim ONLY when the name is ALSO not generating cash on any
    # lens AND not improving. A cash-generative or inflecting name passes.
    _roce_now_ok = ~(_roce_now.notna() & (_roce_now < 0.0)
                     & ~_cash_return_ok & ~_returns_improving)
    # "not melting" (used as the survivability leg across ~30 archetypes). A name
    # is melting ONLY when it is losing money on the operating line OR deeply
    # ROCE-negative, AND generating no cash on ANY lens, AND not improving. This
    # credits cash-on-cash returns equally with ROCE and is benign to genuine
    # turnarounds (SOGP/FORA-type one-off-EBITDA shells with real burn still
    # fail; cash-generative or inflecting names pass). Melters are additionally
    # DEMOTED (not just gate-tested) via melt_demotion in enrich_asymmetry_global.
    _not_melting = ~(((_opm_now < 0) | (_roce_now < -0.05))
                     & ~_cash_return_ok & ~_returns_improving)
    # (user #3) IMPAIRMENT-ROBUST operating viability — the MOST FLEXIBLE
    # reading, to PREVENT GOOD OPPORTUNITIES BEING LOST. op_margin is GAAP-
    # impairment contaminated (WW op -30% on +14% EBITDA / +72% gross — a
    # goodwill writedown, not an operating loss). Where a gate uses op_margin
    # as a VIABILITY FLOOR (op > threshold, "not structurally broken"), credit
    # instead a name clearly viable on EBITDA + gross margin that is generating
    # cash — so an impairment-hit-but-healthy name is kept. Paired with
    # _not_melting (already cash-aware) in every gate, so a genuine cash-burning
    # shell still fails. This is a FLOOR-substitute, deliberately NOT a change
    # to the melt gate (which must keep barring ice cubes).
    def _op_viable(op_thresh):
        return ((s('op_margin', np.nan) > op_thresh)
                | ((ebitda_margin > 0.05)
                   & (s('gross_margin', np.nan) > 0.10)
                   & _cash_return_ok))
    # (reference II) "Some measure of profitability present and robust" is the
    # ONE point every multibagger study agrees on; Yartseva further shows it is
    # the LEVEL of profitability/FCF that drives returns, not the growth RATE.
    # Our growth family gates on rate — anchor it to a profitability LEVEL so a
    # pure-rate name with no cash generation cannot qualify on growth alone.
    _profit_present = ((s('ebitda_ttm', np.nan) > 0) | (s('op_margin', np.nan) > 0)
                       | (fcf_yield > 0))
    # (judgment review — narrowed per "don't drop opportunities on a rough
    # rule") a very high CURRENT roce is only SUSPECT when it is CONTRADICTED by
    # the operating margin. A genuinely capital-light business (royalty / IP /
    # asset-light software) can earn 70-120% on capital WITH a fat op margin —
    # that is a real, rare compounder we must KEEP. What is not real is roce
    # >100% while the op margin is thin/negative (an asset-sale one-off or a
    # tiny-denominator artifact: James Warren Tea roce 1.00 on a low-margin tea
    # business, Dong A Eltek 1.38 with a base-effect print). So: suspect only if
    # roce > 1.0 AND op margin is NOT high (< 20%) AND no multi-year record
    # corroborates it. High-margin high-roce names and sub-100% roce are kept.
    _roce_corroborated = ((s('roic_lindy', np.nan) >= 0.30)
                          | (s('n_yrs_positive_roic', 0) >= 4)
                          | (s('op_margin', np.nan) >= 0.20))
    _roce_oneoff_suspect = (_roce_now.notna() & (_roce_now > 1.0)
                            & ~_roce_corroborated)
    # Genuine-net-cash guard: net_cash_pct and net_debt_ebitda sometimes
    # CONTRADICT (stale/mismatched snapshots) — a name reads "net cash" on one
    # and carries real net debt on the other (TTEC nde -93 artifact, WINE.L
    # nde 9.4, ACX.DE nde 20). A "net-cash survivability" claim must not hold
    # when net debt is KNOWN and materially positive. Missing nde stays
    # permissive (the net_cash_pct leg carries it). NaN-aware, not the 99-fill.
    _nde_known = (pd.to_numeric(df['net_debt_ebitda'], errors='coerce')
                  if 'net_debt_ebitda' in df.columns
                  else pd.Series(np.nan, index=df.index))
    _netcash_not_contradicted = ~(_nde_known >= 1.0)
    nde = s('net_debt_ebitda', 99.0)
    # Negative-EBITDA artifact guard applied AT FIRST DEFINITION (not 600
    # lines later): net_debt/EBITDA flips negative on negative EBITDA and
    # reads as net cash. Unknown (99) fails every leverage gate; genuine net
    # cash is still caught via net_cash_pct lenses.

    _TIERED = []

    def _tier(name, core, exceptional=None, elite_metric=None, higher=True, q=0.90, measured=None):
        """Core / watch / exceptional split (breadth doctrine): the PREVIOUS
        rule survives as a surfaced `<name>_watch` flag, `arch_<name>` becomes
        the tightened core (the archetype's thesis measured directly), and
        `<name>_exceptional` marks the genuinely exceptional subset (ranking /
        EXC tags; never a gate on anything else), and `<name>_elite` the BEST
        OF THE BEST on the archetype's defining continuous measure: the top
        (1-q) of core members, ranked among core members only."""
        # `measured`: where the core's defining inputs are OBSERVED. The
        # tightened core applies only there; a name the data does not reach
        # keeps the previous rule — patchy coverage is never a requirement
        # (a Lynch name with no quarterly statements is judged on its annual
        # figures, not dropped for want of a quarterly panel).
        col = 'arch_' + name
        df[name + '_watch'] = df[col].astype(int)
        _core = core.fillna(False)
        if measured is not None:
            _core = _core | ~measured.fillna(False)
        df[col] = (df[col].astype(bool) & _core).astype(int)
        if exceptional is not None:
            df[name + '_exceptional'] = (df[col].astype(bool) & exceptional.fillna(False)).astype(int)
        if elite_metric is not None:
            m = pd.to_numeric(elite_metric, errors='coerce')
            m = m if higher else -m
            inn = df[col].astype(bool) & m.notna()
            cut = m[inn].quantile(q) if inn.sum() >= 10 else np.inf
            df[name + '_elite'] = (inn & (m >= cut)).astype(int)
        _TIERED.append(name)

    def _ncol(col):
        """NaN-preserving numeric read that is Series-safe when the column
        is absent entirely (df.get on a missing column returns a scalar)."""
        if col in df.columns:
            v = pd.to_numeric(df[col], errors='coerce')
            _note_coverage(col, v)
            return v
        _absent_cols.add(col)
        return pd.Series(np.nan, index=df.index)
    def _confirm(checks):
        """checks = list of (numeric_series, predicate). Returns (any_bool,
        score_0to1). Only measures that are PRESENT count toward the score."""
        present = pd.Series(0, index=df.index)
        agree = pd.Series(0, index=df.index)
        for series, pred in checks:
            p = series.notna()
            present = present + p.astype(int)
            agree = agree + (p & pred(series).fillna(False)).astype(int)
        any_ok = agree >= 1
        score = (agree / present.where(present > 0)).fillna(0.0)
        return any_ok, score

    _ebitda_ttm_guard = _ncol('ebitda_ttm')
    # (audit 3) LEVERAGE READ WHERE nde IS UNMEASURABLE. nde is filled 99 both
    # when net debt was never fetched and when EBITDA <= 0 (the ratio is
    # meaningless), so `nde <= X` fails every loss-maker and `~(nde > X & nde
    # < 90)` passes every one. Read the balance sheet directly there: total
    # debt / total assets, debt / equity, or a known net-cash position. A
    # name with NO balance-sheet evidence at all is denoted unmeasured and
    # passes only where the gate says so (missing_ok).
    _bs_d2a = (_ncol('fq_total_debt') / _ncol('fq_total_assets').where(_ncol('fq_total_assets') > 0))
    _bs_d2e = _ncol('debt_to_equity')
    _bs_lev_known = _bs_d2a.notna() | _bs_d2e.notna() | net_cash_pct.notna()
    _bs_lev_ok = ((_bs_d2a <= 0.35) | _bs_d2e.between(0.0, 1.0)
                  | (net_cash_pct >= 0.0)).fillna(False)
    _nde_meaningful = pd.to_numeric(df['net_debt_ebitda'], errors='coerce').where(
        ~(_ebitda_ttm_guard.notna() & (_ebitda_ttm_guard <= 0))) \
        if 'net_debt_ebitda' in df.columns else pd.Series(np.nan, index=df.index)

    def _lev_ok(nde_max, missing_ok=True):
        ok = ((_nde_meaningful <= nde_max).fillna(False)
              | (_nde_meaningful.isna() & _bs_lev_ok))
        if missing_ok:
            ok = ok | (_nde_meaningful.isna() & ~_bs_lev_known)
        return ok
    # (audit 4) the DATA-QUALITY flag is computed here, before its first reader:
    # 14 XR gates read df.get('data_quality_flag', 0) before the later
    # definition existed, so the lookup returned 0 and the check was a no-op.
    # Same definition as the one recomputed further down (idempotent).
    _dq0_as = _ncol('assets'); _dq0_eq = _ncol('equity'); _dq0_teq = _ncol('tangible_equity')
    _dq0_cash = _ncol('cash'); _dq0_rev = _ncol('revenue_ttm'); _dq0_eb = _ncol('ebitda_ttm')
    df['data_quality_flag'] = (
        ((_dq0_eq > _dq0_as * 1.02) & _dq0_eq.notna() & (_dq0_as > 0))
        | ((_dq0_teq > _dq0_eq * 1.02) & (_dq0_eq > 0))
        | ((_dq0_cash > _dq0_as * 1.02) & _dq0_cash.notna() & (_dq0_as > 0))
        | ((_dq0_eb > _dq0_rev * 2.0) & (_dq0_rev > 0) & is_operating)
    ).fillna(False).astype(int)
    # (audit 3) EV SANITY BAND, universe-wide: an FX-corrupt / cross-line EV
    # (ADR, .F line) reads EV/EBITDA ~0 and passes every "cheap on EV" gate.
    # EV within 0.2-5x the USD market cap, NaN-permissive (missing EV twin).
    _ev_mcap_all = (_ncol('enterprise_value_usd') / mcap.where(mcap > 0))
    _ev_sane = ~((_ev_mcap_all < 0.2) | (_ev_mcap_all > 5.0))
    # (audit 3) clinical-stage drug developer, read early so the momentum /
    # perception setups can denote the binary-event population (the same
    # construction as is_clinical_biotech below)
    _ind_e = df['industry'].fillna('').astype(str).str.lower() if 'industry' in df.columns else pd.Series('', index=df.index)
    _sec_e = sector.astype(str).str.lower()
    _nm_e = df['name'].fillna('').astype(str).str.lower() if 'name' in df.columns else pd.Series('', index=df.index)
    _drug_dev_e = (_ind_e.str.contains('biotechnolog') | _ind_e.str.contains('pharmaceutic')
                   | _ind_e.str.contains('drug manufactur')
                   | (_sec_e.str.contains('health')
                      & _nm_e.str.contains('therapeut|biopharm|biosci|pharma|oncolog|genomic|genetic'))).fillna(False)
    _rev_e = _ncol('revenue_ttm_usd')
    _fcf_e = _ncol('fcf_ttm') * (_ncol('market_cap_usd') / _ncol('market_cap'))
    _commercial_e = ((_ncol('n_yrs_positive_fcf') >= 4) | (_ncol('n_yrs_positive_roic') >= 4)
                     | ((_rev_e >= 500e6) & (_fcf_e > 0) & (_ncol('ebitda_margin') > 0) & (_ncol('ebitda_margin') < 0.6)))
    _ind_cn = (df['industry'].fillna('').astype(str).str.lower()
               if 'industry' in df.columns else pd.Series('', index=df.index))
    _nm_cn = (df['name'].fillna('').astype(str).str.lower()
              if 'name' in df.columns else pd.Series('', index=df.index))
    # (user 2026-10-02) cannabis names are a population of their own, not
    # clinical biotech: classified here (industry label, a cannabis term in the
    # name, or a known operator — MSOs and LPs list under "Pharmaceuticals" /
    # "Drug Manufacturers" with no cannabis word in the industry), excluded
    # from the clinical-biotech scrub below, and listed in their own archetype
    # (cannabis_operator). Name matches are confined to industries a cannabis
    # business can sit in, so China Jushi (chemicals), Cresco Ltd (IT
    # services) or Hyakujushi Bank never match.
    _cann_name = _nm_cn.str.contains(
        r"cannabis|marijuana|\bhemp\b|\bcbd\b|tilray|canopy growth|curaleaf|green thumb|trulieve"
        r"|verano|cresco labs|aurora cannabis|\bsndl\b|cronos group|organigram|village farms"
        r"|ayr wellness|terrascend|glass house|planet 13|jushi holdings|ascend wellness|high tide"
        r"|ianthus|columbia care|cannabist|4front|gold flora|vext science|decibel cannabis"
        r"|cansortium|vireo|acreage holdings|grown rogue|charlotte's web|cbdmd|leafly|auxly"
        r"|red white & bloom|goodness growth", regex=True)
    _cann_ind_bar = _ind_cn.str.contains(
        r"bank|reit|real estate|chemical|building|it services|software|construction|consumer finance"
        r"|asset management|capital markets|insurance", regex=True)
    _is_cannabis = (_ind_cn.str.contains('cannabis|marijuana', regex=True)
                    | (_cann_name & ~_cann_ind_bar)).fillna(False)
    df['is_cannabis'] = _is_cannabis.astype(int)
    _clin_bio_e = (_drug_dev_e & ~_commercial_e.fillna(False)) & ~_is_cannabis   # cannabis is its own population
    # (audit 3) reverse-split guard usable by any gate: a one-period count
    # drop below -30% is a split / restructuring unless a buyback corroborates
    _no_rsplit_yoy = ~((_ncol('shares_yoy') < -0.30) & ~(_ncol('buyback_yield') > 0))
    _no_rsplit_3y = ~((_ncol('shares_growth_3y') < -0.30) & ~(_ncol('buyback_yield') > 0))
    nde = nde.where(~(_ebitda_ttm_guard.notna() & (_ebitda_ttm_guard <= 0)), 99.0)
    not_priced_in = s('not_priced_in_score')
    yart_score = s('yartseva_score')
    adv = s('avg_dollar_volume', 1e12)

    # Use price_yoy where available, otherwise momentum_12m as proxy.
    # Require at least one tape measure PRESENT — with both defaulted to 0,
    # a name with no price history read as "flat" and silently ADMITTED.
    _py_raw = _ncol('price_yoy')
    _m12_raw = _ncol('momentum_12m')
    flat_or_down = ((((_py_raw <= 0.0) | (_m12_raw <= 0.0)).fillna(False))
                    & (_py_raw.notna() | _m12_raw.notna()))

    # ---- Drawdown / extension seen through ANY available tape lens --------
    # pct_off_52w_high is missing for half the universe; a hard gate on it
    # silently dropped (or, on >= gates, ADMITTED) every such name. Triangulate
    # the same fact across the lenses we do have.
    _oh_n = _ncol('pct_off_52w_high')
    _p5r_n = _ncol('price_pct_of_5y_range')
    _pv5_n = _ncol('price_vs_5y_avg')
    _r12_n = _ncol('roc_12m')

    # (endpoint matrix A.4, shared helper) the weekly panel is the PRIMARY
    # tape: ts_dist_hi52 (close / 52w high, total-return, fresh every week,
    # 82% INV coverage) replaces the quote-time pct_off_52w_high wherever it
    # exists (the stale quote column stays the fallback), ts_r52 is a further
    # 12-month lens, and ts_dist_hi260 is the 5-year "former high".
    _ts_dd52 = _ncol('ts_dist_hi52') - 1.0              # <= 0, like pct_off_52w_high
    _ts_hi260 = _ncol('ts_dist_hi260')                  # close / 5-year high (0..1)
    _ts_r52 = _ncol('ts_r52')
    _dd52 = _ts_dd52.fillna(_oh_n)                      # primary 52w drawdown lens

    def beaten_down_any(depth):
        """Beaten down by >= depth through ANY available drawdown lens.
        A PRESENT primary 52w measure that clearly contradicts (drawdown
        shallower than half the claimed depth) VETOES the proxy lenses —
        a stock that crashed years ago and round-tripped to its high
        satisfies the 5y-average leg without being beaten down."""
        any_lens = ((_dd52 <= -depth) |
                    (_ts_hi260 <= (1.0 - depth)) |      # below the 5-year high
                    (_ts_r52 <= -depth) |
                    (_p5r_n <= max(0.10, 0.50 - depth)) |
                    (_pv5_n <= (1.0 - depth)) |
                    (_r12_n <= -depth) |
                    (_py_raw <= -depth) |
                    (_m12_raw <= -depth)).fillna(False)
        # the veto reads the PRIMARY (panel-first) 52w lens: a stale quote-time
        # drawdown can no longer veto (or admit) against a fresh weekly close
        contradicted = (_dd52.notna() & (_dd52 > -depth * 0.5))
        return any_lens & ~contradicted

    def not_too_deep_any(cap):
        """True unless a PRESENT tape measure shows a drawdown DEEPER than
        cap (missing data is not evidence of a shallow drawdown — the old
        `off_high >= -cap` on a 0-defaulted series admitted every name with
        no 52w-high data)."""
        return (~((_dd52.notna() & (_dd52 < -cap)) |
                  (_ts_r52.notna() & (_ts_r52 < -cap)) |
                  (_r12_n.notna() & (_r12_n < -cap)) |
                  (_m12_raw.notna() & (_m12_raw < -cap))))

    # (endpoint matrix A.4) "heavy fixed-cost asset" MEASURED, not a sector
    # label: the PHYSICAL asset base, net PP&E >= 30% of total assets (one
    # balance sheet, so currency cancels). Where the balance sheet is not in
    # the quarterly panel, capex >= 5% of revenue is the fallback measure, and
    # the sector label only where neither exists. D&A / revenue (a matrix
    # lens) is NOT used: it includes amortisation of acquired intangibles
    # (Hostelworld read "heavy" on it). FMP ppe_net carries lease ROU assets —
    # a leased plant / fleet is a fixed cost too, so it is not stripped here.
    # Unit-validity: a ratio outside [0, 1] (PP&E above total assets, capex
    # above revenue on a near-zero-revenue shell) is treated as unmeasured.
    _ai_ppe = _ncol('fq_ppe_net') / _ncol('fq_total_assets').where(_ncol('fq_total_assets') > 0)
    _ai_ppe = _ai_ppe.where(_ai_ppe.between(0, 1))
    _ai_cx = _ncol('capex_intensity')
    _ai_cx = _ai_cx.where(_ai_cx.between(0, 1))
    df['asset_intensity_ppe'] = _ai_ppe.round(4)

    def asset_heavy(label_mask):
        """Measured PP&E intensity, else capex intensity, else the sector label."""
        return ((_ai_ppe >= 0.30).where(_ai_ppe.notna(),
                (_ai_cx >= 0.05).where(_ai_cx.notna(), label_mask.fillna(False)))
                .fillna(False).astype(bool))

    # Dated-event recency (fmp_events, renamed evt_*): days from the filing to
    # the panel's as-of week (the data date, so a rerun is reproducible).
    _asof = (pd.to_datetime(df['ts_week'], errors='coerce').max()
             if 'ts_week' in df.columns else pd.NaT)
    if pd.isna(_asof):
        _asof = pd.Timestamp.now().normalize()

    def _evt_age_days(col):
        if col not in df.columns:
            _absent_cols.add(col)
            return pd.Series(np.nan, index=df.index)
        return (_asof - pd.to_datetime(df[col], errors='coerce')).dt.days

    # TTM incremental EBIT margin as a DROP-THROUGH measure (share of each new
    # revenue dollar reaching EBIT) is defined on [.., 1]: above 100% EBIT rose
    # by more than revenue — costs fell or losses unwound off a negative base
    # (SEDG 374%, Almirall 149%) — a different fact from operating leverage,
    # so those values are out of the lens's domain (excluded, not clamped).
    df['fqx_inc_ebit_margin_dt'] = _ncol('fqx_inc_ebit_margin').where(
        _ncol('fqx_inc_ebit_margin') <= 1.0)
    _fqx_inc = df['fqx_inc_ebit_margin_dt']

    # Augmented (non-tiered) archetypes that carry a continuous spirit score;
    # their stringency lives there and in the elite book, never in the gate.
    _SPIRITED = []
    # (user) a gate that is not explicitly part of an archetype's thesis is not
    # a gate: where it still carries information it is a WEIGHTING — extra
    # lenses blended into the archetype's spirit score (25%), never a veto.
    _DEMOTED = {}
    _DEMOTED_W = {}   # per-archetype blend share of the demoted weights (default 25%)
    # Archetypes re-measured where the matrix calls the old rule a proxy that
    # measured something else: the old rule survives as <name>_watch.
    def _reframe(name, new_rule):
        col = 'arch_' + name
        df[name + '_watch'] = df[col].astype(int)
        df[col] = new_rule.fillna(False).astype(int)
        _SPIRITED.append(name)

    # ---- Interval-robust inflection (applied throughout) ----
    # The central inflection detector `inflection_print` (used by ~15
    # archetypes) traditionally reads annual/YoY flags only, so it MISSES a
    # business that has turned on a TTM-sequential basis but whose year-ago
    # comparison hasn't caught up yet. We add a SEASONALITY-ROBUST interval
    # layer — YoY margin/growth angles + TTM-sequential turns (rolling 12mo
    # cancels seasonality) — so those early inflections are found here too.
    # Raw single-quarter sequential is deliberately EXCLUDED (it's
    # seasonality-confounded); it only contributes to the scored confirmation
    # used for ranking, never to firing.
    def _n0(c):
        if c in df.columns:
            v = pd.to_numeric(df[c], errors='coerce')
            _note_coverage(c, v)
            return v
        _absent_cols.add(c)
        return pd.Series(np.nan, index=df.index)
    interval_inflect_any = (
        (_n0('ebitda_margin_delta_yoy') > 0) | (_n0('fcf_margin_delta_yoy') > 0) |
        (_n0('gross_margin_delta_yoy') > 0)  | (_n0('op_margin_delta_yoy') > 0) |
        (_n0('operating_leverage_ratio') > 1.0) |
        (_n0('ebitda_qoq_ttm') > 0) | (_n0('cfo_qoq_ttm') > 0) |
        (_n0('fcf_qoq_ttm') > 0)    | (_n0('rev_qoq_ttm') > 0) |
        (_n0('rev_accel') > 0)      | (_n0('gross_profit_yoy') > 0.05)
    ).fillna(False)

    # Operating-leverage SHOCK interval robustness: the MARGIN / cash-turn
    # angles ONLY (excludes the pure top-line-growth angles), each held to the
    # SAME magnitude standard as the single-measure original — a >=2-point
    # margin move, disproportionate flow-through, or a material TTM turn. This
    # is triangulation in the strict sense: different accounting lenses on the
    # same-sized event, so a name qualifies when ANY lens sees the genuine
    # shock (robust to which line item the leverage shows up in), but a mere
    # positive drift on some measure never substitutes for the shock itself.
    margin_shock_any = (
        # P&L margin lenses — same >=2-point standard, three structures
        (_n0('ebitda_margin_delta_yoy') >= 0.02) |
        (_n0('op_margin_delta_yoy')     >= 0.02) |
        (_n0('gross_margin_delta_yoy')  >= 0.02) |
        # Cash lens is noisy solo (working-capital / capex timing): a 2-point
        # FCF-margin move counts only when a P&L margin lens corroborates
        # directionally — the seasonality-rule analogue for measurement noise.
        ((_n0('fcf_margin_delta_yoy') >= 0.02) &
         ((_n0('ebitda_margin_delta_yoy') > 0) | (_n0('op_margin_delta_yoy') > 0) |
          (_n0('gross_margin_delta_yoy') > 0))) |
        # Disproportionate flow-through, artifact-guarded: the ratio explodes
        # on near-zero revenue growth, so require EBITDA to have actually
        # moved (>=5%) for the ratio to count as evidence of the shock.
        ((_n0('operating_leverage_ratio') >= 1.5) & (_n0('ebitda_yoy') >= 0.05)) |
        # TTM-sequential LEVERAGE (seasonality-robust, earlier than YoY):
        # EBITDA/CFO outgrowing revenue on a TTM basis — i.e. TTM margin
        # expansion, not absolute growth (10% EBITDA on 10% revenue is flat
        # margins). Differential >=10pp ~ a 2-point move on typical margins.
        ((_n0('ebitda_qoq_ttm') - _n0('rev_qoq_ttm')) >= 0.10) |
        ((_n0('cfo_qoq_ttm')    - _n0('rev_qoq_ttm')) >= 0.10)
    ).fillna(False)

    inflection_print = (
        (ebitda_inflection > 0) | (cfo_inflection > 0) | (fcf_inflection > 0) |
        (rev_inflection > 0) | (roce_inflection > 0) |
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0) |
        (rev_yoy >= 0.10) | (ebitda_margin_delta >= 0.02) |
        interval_inflect_any                       # interval-robust turns
    )

    # ---------- Cluster A: Narrative Lag (modifier) ----------
    # Business ADVANCING while the market ignores it. inflection_print alone
    # includes weak legs (any 10% grower), which fired this on 41% of the
    # universe — require at least TWO independent advance legs (or a genuine
    # first-positive print, the strongest single signal) so the lag is on a
    # real advance, not a bare growth print.
    _adv_breadth = (
        ((ebitda_inflection > 0) | (cfo_inflection > 0) |
         (fcf_inflection > 0) | (roce_inflection > 0)).astype(int)
        + (rev_inflection > 0).astype(int)
        + ((ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
           (ni_first_pos > 0) | (roce_first_pos > 0)).astype(int)
        + (rev_yoy >= 0.10).astype(int)
        + (ebitda_margin_delta >= 0.02).astype(int)
        + interval_inflect_any.astype(int)
    )
    _first_pos_any = ((ebitda_first_pos > 0) | (cfo_first_pos > 0) |
                      (fcf_first_pos > 0) | (ni_first_pos > 0) |
                      (roce_first_pos > 0))
    # (G5) require a genuine, PRESENT, non-zero tape — a literal
    # price_yoy==0.0 & momentum_12m==0.0 stale/missing tape no longer reads as
    # "lagging". (G9) tighten beyond flat_or_down: the tape must be genuinely
    # DOWN on at least one present lens (a real lag, not merely flat/stale).
    # ...or the tape has gone NOWHERE for two years (weekly panel) while sales
    # advanced >= 20% more than the price — a lag measured over the full base,
    # which a single down year cannot see (and a flat year cannot trigger)
    _lag_tape = ((_py_raw < 0.0) | (_m12_raw < 0.0)
                 | ((_num_or_nan('bs_is_base') == 1) & (_num_or_nan('bs_coil_rev') >= np.log(1.20))).fillna(False))
    # (audit re-check) tightened from ~28% of the universe toward the spirit
    # (price/narrative LAGS genuinely improving fundamentals): require a real
    # multi-lens advance (not a lone first-positive), investable operating
    # scale, survivability (not a double cash-burner), and a cheapness anchor
    # so the narrative is actually LAGGING a reasonable valuation.
    # (audit 3) breadth counts only beside at least one SHOCK-sized lens (a
    # first positive or a >= 2pp margin / TTM shock) — two drift lenses are
    # not an advance
    _adv_shock = (_first_pos_any | margin_shock_any | (ebitda_margin_delta >= 0.02)).fillna(False)
    df['arch_narrative_lag'] = (
        _lag_tape &
        (_adv_breadth >= 2) & _adv_shock &
        is_operating & (mcap >= 10e6) &
        _roce_now_ok &                          # (tail) lag on IMPROVING fundamentals, not a deteriorating name (UCID/ILINK)
        ((s('fcf_ttm') > 0) | (s('ebitda_ttm') > 0) | _first_pos_any) &
        (((pb > 0) & (pb < 3.0)) | (fcf_yield >= 0.03))
    ).fillna(False).astype(int)
    # (re-specified) The LAG is the thesis, so it is measured directly and
    # through several lenses — each "the fundamental advance outran the price"
    # (log gaps, total-return prices) — instead of "any down print" (half the
    # universe). narrative_lag_extent = the largest gap across lenses: HOW FAR
    # the story lags. No non-thesis gates: the advancing-fundamentals legs of
    # the original rule stay; only the lag test is replaced.
    _r52 = np.log1p(_ncol('ts_r52'))
    # PER SHARE: the price is per share, so the advance must be too — total
    # revenue rising while the share count balloons is dilution, not a lag
    # (SUNE: revenue up, price -99.999% over 3y through issuance). Share
    # growth: TTM (date-matched) for 1y; the 3y figure prorated for 2y / 3y.
    _sh1 = np.log1p(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')).fillna(0))
    _sh3 = np.log1p(_ncol('shares_growth_3y').fillna(0))
    # 5y share growth only where the history really spans 5 fiscal years
    # (fmp_statements falls back to a shorter span on short histories)
    _sh5 = np.log1p(_ncol('shares_growth_5y').where(_ncol('years_of_history') >= 6))
    _lag_lens = {
        'sales_1y': np.log1p(_ncol('fq_rev_growth')) - _sh1 - _r52,
        'ebit_1y': np.log1p(_ncol('fqx_ebit_ttm_g')) - _sh1 - _r52,
        'eps_1y': np.log1p(_ncol('fqx_ni_ttm_g')) - _sh1 - _r52,
        'fcfps_1y': np.log1p(_ncol('fqx_fcf_ps_g')) - _r52,          # already per share
        'sales_2y': _ncol('bs_coil_rev') - _sh3 * (2 / 3),
        'ebit_2y': _ncol('bs_coil_ebit') - _sh3 * (2 / 3),
    }
    # LONG coils (3y / 5y): per-share sales, EBIT and FCF over exact fiscal
    # spans with 2-year-averaged endpoints (fmp_statements), against the 3y /
    # 5y total-return price change — the most persistent form of the lag.
    # Sales per share falls back to the revenue CAGR less share growth.
    _sps = {3: _ncol('fmp_st_sales_ps_3y_g').fillna(
                np.expm1(3 * np.log1p(_ncol('revenue_3y_cagr')) - _sh3)),
            5: _ncol('fmp_st_sales_ps_5y_g').fillna(
                np.expm1(5 * np.log1p(_ncol('revenue_5y_cagr')) - _sh5))}
    _rp = {3: np.log1p(_ncol('ts_r156')), 5: np.log1p(_ncol('ts_r260'))}
    _long_g = {}
    for _span in (3, 5):
        _long_g[f'sales_{_span}y'] = _sps[_span]
        _long_g[f'ebit_{_span}y'] = _ncol(f'fmp_st_ebit_ps_{_span}y_g')
        _long_g[f'fcfps_{_span}y'] = _ncol(f'fmp_st_fcf_ps_{_span}y_g')
    for _k, _g in _long_g.items():
        _lag_lens[_k] = np.log1p(_g) - _rp[int(_k.split('_')[1][0])]
    _lag_thr = {'sales_1y': np.log(1.2), 'ebit_1y': np.log(1.3), 'eps_1y': np.log(1.3),
                'fcfps_1y': np.log(1.3), 'sales_2y': np.log(1.2), 'ebit_2y': np.log(1.3),
                'sales_3y': np.log(1.3), 'ebit_3y': np.log(1.4), 'fcfps_3y': np.log(1.4),
                'sales_5y': np.log(1.5), 'ebit_5y': np.log(1.6), 'fcfps_5y': np.log(1.6)}
    _lag_h = {k: int(k.split('_')[1][0]) for k in _lag_lens}
    # A lag needs a genuine ADVANCE: each lens counts only when the fundamental
    # itself grew (a price fall with flat fundamentals is not a lag, it is
    # just a fall — without this every coil lens fired on any drawdown).
    # ...and a PLAUSIBLE advance: growth off a near-zero base (+200% in a year,
    # +300% over two, a 100% CAGR) is a base effect, not a lagging narrative —
    # excluded from the lens (same convention as the liger / evsales base-effect
    # bounds), never clamped.
    _eg2 = _ncol('bs_coil_ebit') + np.log1p(_ncol('bs_r104'))          # log 2y EBIT growth
    _adv = {'sales_1y': _ncol('fq_rev_growth').between(0.10, 2.0),
            'ebit_1y': _ncol('fqx_ebit_ttm_g').between(0.10, 2.0),
            'eps_1y': _ncol('fqx_ni_ttm_g').between(0.10, 2.0),
            'fcfps_1y': _ncol('fqx_fcf_ps_g').between(0.10, 2.0),
            'sales_2y': _ncol('bs_rev_g_2y').between(0.15, 3.0),
            'ebit_2y': (_eg2 >= np.log(1.15)) & (_eg2 <= np.log(4.0))}
    # long spans: a plausible per-share advance is 5%-60% a year compounded
    # (above that it is a base effect off a near-zero start, e.g. FCF
    # per share +4,700% from a breakeven year). Per-share SALES only count as
    # an advance where the operating margin held (>= -2pp on averaged
    # endpoints): sales bought with a collapsing margin are volume, not value.
    for _k, _g in _long_g.items():
        _span = int(_k.split('_')[1][0])
        _cg = np.expm1(np.log1p(_g) / _span)
        _ok = _cg.between(0.05, 0.60)
        if _k.startswith('sales'):
            _ok &= ~(_ncol(f'fmp_st_opm_chg_{_span}y') < -0.02)
        _adv[_k] = _ok
    # A LAG IS UNPRICED ADVANCE, NOT MULTIPLE COMPRESSION. The outrun above
    # (per-share fundamental growth minus price growth) is identically the fall
    # in the valuation multiple — and a fall from a frothy start (30x sales in
    # 2021) is the market ceasing to OVER-price a story, not failing to price
    # the fundamentals. The narrative lags only to the extent the stock is
    # priced BELOW what those fundamentals normally command today. So each
    # lens is credited with min(outrun, log(sector-norm multiple / current
    # multiple)) on the matching multiple — EV/Sales for sales, EV/EBIT (else
    # EV/EBITDA) for EBIT, P/E for EPS, P/FCF for FCF. A name still at or above
    # its sector norm has no lag however far it fell. Ratios are currency-
    # invariant; norms are medians over investable operating companies.
    _norm_base = is_operating & (mcap >= 10e6) & ~(_ncol('data_quality_flag') == 1)

    def _below_norm(mult):
        m = mult.where(mult > 0)
        norm = m.where(_norm_base).groupby(sector).transform('median')
        norm = norm.fillna(m.where(_norm_base).median())
        return np.log(norm / m)

    _fcf_y = _ncol('fcf_yield')
    _anchor = {'sales': _below_norm(_ncol('ev_sales')),
               'ebit': _below_norm(_ncol('ev_ebit')).fillna(_below_norm(_ncol('ev_ebitda'))),
               'eps': _below_norm(_ncol('p_e')),
               'fcfps': _below_norm((1.0 / _fcf_y).where(_fcf_y > 0))}
    df['narrative_lag_outrun'] = pd.concat(
        [v.where(_adv[k].fillna(False)) for k, v in _lag_lens.items()], axis=1).max(axis=1).round(4)
    _raw_lens = dict(_lag_lens)
    _lag_lens = {k: np.minimum(v, _anchor[k.split('_')[0]]) for k, v in _lag_lens.items()}
    _valid = {k: (v.where(_adv[k].fillna(False))) for k, v in _lag_lens.items()}
    _hit = {k: (v >= _lag_thr[k]).fillna(False) for k, v in _valid.items()}
    # INDEPENDENT evidence is counted by horizon, not by metric (the 1-year
    # sales / EBIT / EPS / FCF gaps share one price change)
    _hz = {}
    for _k, _hv in _lag_h.items():
        _hz[_hv] = _hz.get(_hv, pd.Series(False, index=df.index)) | _hit[_k]
    # relative lag (behind its own market while growing) and ignored evidence
    _lag_rel = ((_ncol('ts_rs_pct_mkt') <= 40) & (_ncol('fq_rev_growth') >= 0.15)).fillna(False)
    _lag_ign = (_ncol('evt_ignored_beats_2y') >= 2).fillna(False)
    df['narrative_lag_lenses'] = (sum(v.astype(int) for v in _hz.values())
                                  + _lag_rel.astype(int) + _lag_ign.astype(int)).astype(int)
    # THE LAG IS ALL THE LAGS, AND LONGER IS STRONGER. A story that has lagged
    # its fundamentals for five years is more mispriced (and more persistent)
    # than a one-year gap, and a lag visible on every horizon is more
    # pervasive than one. So:
    #   narrative_lag_extent   total lag = sum over horizons of that horizon's
    #                          gap (mean of its lagging per-share lenses, log
    #                          terms); longer lags accumulate larger gaps, and
    #                          each lagging horizon adds — nothing is a max
    #   narrative_lag_years    the longest horizon on which it lags (1/2/3/5)
    #   narrative_lag_max_gap  the single largest gap (for reference)
    _hgap = {}
    for _hv in sorted(set(_lag_h.values())):
        _ks = [k for k, h in _lag_h.items() if h == _hv]
        _g = pd.concat([_valid[k].where(_hit[k]) for k in _ks], axis=1).mean(axis=1)
        _hgap[_hv] = _g.fillna(0.0)
    df['narrative_lag_extent'] = sum(_hgap.values()).where(df['narrative_lag_lenses'] > 0).round(4)
    df['narrative_lag_years'] = pd.concat(
        [pd.Series(np.where(_hz[h], h, 0), index=df.index) for h in _hz], axis=1).max(axis=1)
    df['narrative_lag_max_gap'] = pd.concat(list(_valid.values()), axis=1).max(axis=1).round(4)
    for _k, _v in _valid.items():                      # per-lens gaps (which lens drives the lag)
        df['nl_' + _k] = _v.round(4)
    df['narrative_lag_watch'] = df['arch_narrative_lag'].astype(int)
    df['arch_narrative_lag'] = (
        (df['narrative_lag_lenses'] >= 1) &
        (_adv_breadth >= 2) & _adv_shock &
        is_operating & (mcap >= 10e6) &
        _roce_now_ok &
        ((s('fcf_ttm') > 0) | (s('ebitda_ttm') > 0) | _first_pos_any) &
        (((pb > 0) & (pb < 3.0)) | (fcf_yield >= 0.03))
    ).fillna(False).astype(int)
    # exceptional IN THE ARCHETYPE'S OWN TERMS: lagging on >= 2 independent
    # lenses, by >= 50%; elite = the top 10% by extent of the lag
    _nl = df['arch_narrative_lag'] == 1
    df['narrative_lag_exceptional'] = (_nl & (df['narrative_lag_lenses'] >= 2)
                                       & (df['narrative_lag_extent'] >= np.log(1.5))).astype(int)
    _ext = df['narrative_lag_extent'].where(_nl)
    df['narrative_lag_elite'] = (_nl & (_ext >= _ext.quantile(0.90))).astype(int)
    _TIERED.append('narrative_lag')

    # ---------- Derating Through Growth (grew into its valuation) ----------
    # The complement of the anchored narrative lag: per-share earnings power
    # compounded for years while a RICH multiple deflated — the business grew
    # into (and through) its old valuation, so the price went sideways or down
    # while the company got much bigger (SNAP / MNDY / HUBS from 2021). The
    # froth is gone and the fundamentals are real; the stock need NOT be cheap
    # against its sector (that is narrative_lag). Multi-year only (2y / 3y /
    # 5y coils — a one-year multiple move is noise), same per-share,
    # genuine-advance and margin-held rules as the lag lenses, measured on the
    # RAW outrun (multiple compression absorbed by growth).
    _dg_hit = {k: ((v >= _lag_thr[k]) & _adv[k].fillna(False)).fillna(False)
               for k, v in _raw_lens.items() if _lag_h[k] >= 2}
    _dg_hz = {}
    for _k, _hv in ((k, _lag_h[k]) for k in _dg_hit):
        _dg_hz[_hv] = _dg_hz.get(_hv, pd.Series(False, index=df.index)) | _dg_hit[_k]
    _dg_any = pd.concat(list(_dg_hz.values()), axis=1).any(axis=1)
    _dg_gap = {}
    for _hv in sorted(_dg_hz):
        _ks = [k for k in _dg_hit if _lag_h[k] == _hv]
        _dg_gap[_hv] = pd.concat([_raw_lens[k].where(_dg_hit[k]) for k in _ks], axis=1).mean(axis=1).fillna(0.0)
    df['derate_growth_extent'] = sum(_dg_gap.values()).where(_dg_any).round(4)
    df['derate_growth_years'] = pd.concat(
        [pd.Series(np.where(_dg_hz[h], h, 0), index=df.index) for h in _dg_hz], axis=1).max(axis=1)
    df['derate_growth_horizons'] = sum(v.astype(int) for v in _dg_hz.values()).astype(int)
    # the part of the outrun that was froth normalising (outrun beyond what
    # is unpriced today), for reference
    df['derate_growth_froth'] = pd.concat(
        [(_raw_lens[k] - _lag_lens[k]).where(_dg_hit[k]) for k in _dg_hit], axis=1).max(axis=1).round(4)
    # GROWTH SHARE of the derating on the longest horizon that fired (sales
    # per share): log growth / (log growth - log price change). ~1 = the price
    # held while the business compounded (the multiple was absorbed by
    # growth); a small share = the gap is mostly the price collapsing, i.e.
    # destruction rather than a business growing into its valuation.
    # When the price ROSE, all of the compression came through growth (share
    # = 1 by definition). ABSORBED = the log multiple compression that growth
    # covered, min(growth, gap): the size of what the business grew through.
    _dg_share = pd.Series(np.nan, index=df.index)
    _dg_abs = pd.Series(np.nan, index=df.index)
    _g2 = np.log1p(_ncol('bs_rev_g_2y')) - _sh3 * (2 / 3)
    for _span, _g, _p in ((2, _g2, np.log1p(_ncol('bs_r104'))),
                          (3, np.log1p(_sps[3]), _rp[3]), (5, np.log1p(_sps[5]), _rp[5])):
        _gap = _g - _p
        _ok_ = (_gap > 0) & (_g > 0) & _dg_hz.get(_span, pd.Series(False, index=df.index))
        _sh_ = np.minimum(_g / _gap, 1.0).where(_ok_)
        _ab_ = np.minimum(_g, _gap).where(_ok_)
        _dg_share = _sh_.fillna(_dg_share) if _span > 2 else _sh_
        _dg_abs = _ab_.fillna(_dg_abs) if _span > 2 else _ab_
    df['derate_growth_share'] = _dg_share.round(4)
    df['derate_growth_absorbed'] = _dg_abs.round(4)
    # (audit 3) at least HALF the multiple compression came through growth
    # (otherwise it is the fall, not the business growing into its valuation),
    # and a profitability level is present (a burner can grow into nothing)
    df['arch_derate_through_growth'] = (_dg_any & is_operating & (mcap >= 10e6)
                                        & ~(_dg_share < 0.5) & _profit_present).fillna(False).astype(int)
    _TIERED.append('derate_through_growth')

    # ---------- Cluster C5: Fixed-Cost Asset + Demand Shock ----------
    df['arch_fixed_cost_demand_shock'] = (
        sector.isin(HEAVY_ASSET_SECTORS) &
        (rev_accel > 0) &
        (rev_yoy > 0) &                 # (G8) a demand SHOCK has RISING revenue,
                                        # not a declining top line
        _not_melting &                  # (tail) not a loss NARROWING off a negative base (VEEE/NEXE/ODV)
        ~((nde > 6.0) & (nde < 90)) &   # (tail) leverage cap — exclude KNOWN 24-38x zombies (AWLCF/China Primary); nde 99 = unknown stays permissive
        # Operating-leverage leg made interval-robust WITHOUT diluting the
        # spirit: the demand shock must flow through to a SHOCK-sized margin
        # response — the same >=2-point standard, just visible through any of
        # several accounting lenses / time bases (margin_shock_any), so a name
        # whose leverage shows up in gross margin or a material TTM cash turn
        # is not missed while a mere positive drift still never qualifies.
        # (G8) the direct margin leg is capped at +20pp so a single one-off
        # margin swing cannot alone qualify the name.
        (((ebitda_margin_delta >= 0.02) & (ebitda_margin_delta <= 0.20))
         | margin_shock_any)
    ).astype(int)
    # (endpoint matrix, PROXY+LEG) the sector label is a proxy for "fixed-cost
    # asset" (Industrials + ConsDisc were 66% of firers): measure it (asset
    # intensity, sector only where unmeasurable), and accept the direct
    # drop-through proof — TTM incremental EBIT margin >= 30% — as a further
    # operating-leverage lens. Old rule surfaced as fixed_cost_demand_shock_watch.
    # (the label excluded financials / real estate implicitly; a measured
    # PP&E base does not — an investment-property owner is not a fixed-cost
    # OPERATING asset meeting demand — so that guard is explicit. Utilities
    # stay: they were in the label set.)
    _not_fin_re = ~(is_financial | is_reit)
    _reframe('fixed_cost_demand_shock', (
        _not_fin_re & asset_heavy(sector.isin(HEAVY_ASSET_SECTORS)) &
        (rev_accel >= 0.03) & (rev_yoy >= 0.05) &   # (audit 3) a demand SHOCK: >= 3pp acceleration on a >= 5% top line, not a 0.1pp drift
        _not_melting &
        (((ebitda_margin_delta >= 0.02) & (ebitda_margin_delta <= 0.20))
         | margin_shock_any | (_fqx_inc >= 0.30).fillna(False))))

    # ---------- Cluster E7: Discounted Vehicle ----------
    df['arch_discounted_vehicle'] = (
        is_operating &                                   # (G1) exclude financials/REITs/utilities
        (pb > 0) & (pb < 0.85) &
        (((cash_gt_ev > 0) & ~(net_cash_pct > 1.0)) | (net_cash_pct_sane > 0.20)) &  # (G2) drop >100%-of-mcap shells (on the flag leg too)
        ~((nde >= 1.0) & (nde < 90)) &                   # (tail) net-cash claim not contradicted by REAL net debt (nde 99 = unknown, stays permissive; Newtree nde+2.1 excluded)
        _not_melting &                                   # (deep-audit) the net-cash claim doesn't stop an OPERATING melter sitting on cash: CHGG roce-95%, WISH roce-87%, FOM roce-98% passed on one-off working-cap FCF. Sibling dead_option carries the returns floor; add it here.
        (mcap > 0) & (mcap < 2e9)   # mcap>0: missing mcap must not auto-pass the size gate
    ).astype(int)
    # (audit 3) the vehicle thesis needs a MECHANISM to close the discount —
    # surfaced, not gated: a shrinking count / buyback, a fresh 13D, a dated
    # deal, a dividend initiation; and the governance trap (a >= 60% holder
    # with no buyback) denoted
    df['discounted_vehicle_catalyst_flag'] = ((df['arch_discounted_vehicle'] == 1) & (
        (_ncol('fq_shares_yoy') <= -0.02) | (_ncol('buyback_yield') >= 0.02)
        | (_evt_age_days('evt_sc13d_date') <= 365) | (_evt_age_days('evt_tender_date') <= 270)
        | (_evt_age_days('evt_merger_proxy_date') <= 270) | (_ncol('evt_div_raise_streak') >= 1)
    ).fillna(False)).astype(int)
    df['discounted_vehicle_governance_trap_flag'] = ((df['arch_discounted_vehicle'] == 1)
        & (insider >= 0.60) & ~((_ncol('buyback_yield') > 0) | (_ncol('shares_yoy') < 0)).fillna(False)).astype(int)

    # ---------- Cluster E8: Capital Discipline Re-rating ----------
    # Proxy: founder/insider-aligned, lightly levered, durable margin, not
    # already re-rated.  We don't have a direct buyback signal in fundamentals
    # so this is a "compounder-pattern" proxy.
    # (G6) require a real capital-allocation ACTION (buyback / share shrink),
    # OR pair high insider ownership with a genuine return gate — insider
    # ownership alone is not capital discipline (91% passed on it before).
    # (gate audit #4) a buyback claim is corroborated against the share
    # count — SBC out-diluting the buyback is not discipline (TTEC class)
    # (endpoint matrix, EXC) a further ACTION lens, measured over the cycle:
    # cash flowed OUT to capital providers (debt repaid, dividends, buybacks)
    # in >= 80% of >= 5 fiscal years — persistent allocation, not one TTM.
    _fin_out_share = (_ncol('fmp_st_financing_outflow_years')
                      / _ncol('fmp_st_financing_years').where(_ncol('fmp_st_financing_years') >= 5))
    _action_leg = (((_ncol('shares_growth_3y') <= -0.01) & _no_rsplit_3y) |   # (audit 3) split-guarded shrink
                   ((_ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0')) >= 0.02)   # (audit 3) FY repurchases (global) beside the EDGAR yield
                    & ~(_ncol('shares_yoy') > 0)) |
                   # (audit 3) a financing outflow that is debt repayment with NO owner return is deleveraging, not discipline
                   ((_fin_out_share >= 0.80) & ((_ncol('dividend_yield') > 0) | (_ncol('fmp_st_buyback_yield_y0') > 0) | (_ncol('shares_yoy') < 0))))
    # (R2) roic_after_sbc is EDGAR-only (NA for all non-US filers), so the
    # returns leg used to collapse to "insider>=0.20 & any positive FCF" for
    # ex-US names. Add globally-available roce>=0.12 as the real returns leg,
    # and lift the FCF fallback to a meaningful yield (not a trivial +epsilon).
    _insider_plus_return = ((insider >= 0.20) &
                            ((_ncol('roic_after_sbc') >= 0.10) |
                             (_ncol('roce') >= 0.12) |
                             (fcf_yield >= 0.04)))
    # (audit 3) insider ownership plus a return is NOT discipline (the
    # engine's own note; 2/3 of firers rode it): the insider path counts only
    # with the persistent financing outflow behind it
    _own_aligned = (_action_leg | (_insider_plus_return & (_fin_out_share >= 0.80)))
    # (quality-audit) capital ALLOCATION discipline is not "a value-destroyer
    # bought back stock". The action leg alone had no returns/quality floor, so
    # buybacks by shrinking, lossmaking operators qualified (Hinduja op -9.9%).
    # Require a genuine returns/profitability floor AND real operating profit
    # across every path — buying back stock while destroying capital is the
    # opposite of the thesis.
    _cd_returns_floor = ((_ncol('roce') >= 0.10) | (_ncol('roic_after_sbc') >= 0.10)
                         | (fcf_yield >= 0.05))
    df['arch_capital_discipline'] = (
        is_operating &                          # (G1) exclude financials/REITs/utilities
        _own_aligned &
        _cd_returns_floor &                     # real returns on capital (not a value-destroyer)
        _roce_now_ok &                          # (verify) a one-off FCF yield must not let a capital DESTROYER through the returns-floor OR (MKTW roce-76%)
        _op_viable(0) &          # positive operating profit (impairment-robust: a writedown-hit but cash-generative operator is kept)
        (_lev_ok(1.5) | (net_cash_pct >= 0.20)) &   # (audit 4) unmeasured leverage passes (was failing: the 99-fill direction)   # (audit 3) NaN-aware clean balance sheet (a real low nde, the balance sheet where EBITDA <= 0, or a real net-cash %), not the 99 fill that dropped 37% of a Japan/Korea thesis
        ((pb < 1.5) | ((s('ev_ebit', np.nan) > 0) & (s('ev_ebit', np.nan) <= 12)) | _ncol('pb').isna()) &   # (audit 3) NOT YET RE-RATED (missing P/B passes: pb itself is 99-filled) (MR's third layer): still priced for the old cycle
        (ebitda_margin_sane >= 0.05) &          # (G2) drop one-off >60% margins
        is_operating                            # (audit 4 / user rule) the tape cut (12m <= +300%) and the Yartseva composite cut (a different family's score) are gone; Yartseva is a weight
    ).fillna(False).astype(int)
    _SPIRITED.append('capital_discipline')      # exceptional: FCF-covered payouts, persistent outflow, shrinking count
    # (audit 3) the Value-Up / PBR-reform catalyst lens: a sub-book Korean or
    # Japanese listing (the policy pressure MR names), surfaced not gated
    _sym_cd = df['symbol'].astype(str)
    df['value_up_reform_flag'] = ((_sym_cd.str.endswith('.KS') | _sym_cd.str.endswith('.KQ') | _sym_cd.str.endswith('.T'))
                                  & (pb > 0) & (pb < 1.0)).fillna(False).astype(int)

    # ---------- Cluster F9: Regime-Change Cyclical ----------
    df['arch_regime_cyclical'] = (
        sector.isin(HEAVY_ASSET_SECTORS) &
        beaten_down_any(0.20) &
        (rev_yoy > 0) &                 # (G8) a genuine regime change shows RISING
                                        # revenue, not a still-declining top line
        _not_melting &                  # (tail) not a loss narrowing off a negative base (VEEE/ODV)
        ~((nde > 6.0) & (nde < 90)) &   # (tail) leverage cap — exclude KNOWN over-levered zombies
        # REGIME CHANGE confirmed across margin/cash measures + time bases:
        # zero-crossings / first-positive prints stay, and the margin leg
        # accepts a shock-sized (>=2-point / material-TTM) move seen through
        # any lens (margin_shock_any) — never incremental drift, which is not
        # a regime change. (G8) the direct margin leg is capped at +20pp so a
        # single one-off margin swing cannot alone qualify.
        ((ebitda_inflection > 0) | (ebitda_first_pos > 0) |
         ((ebitda_margin_delta >= 0.02) & (ebitda_margin_delta <= 0.20)) |
         margin_shock_any) &
        (not_priced_in > 0.20)
    ).astype(int)
    # (endpoint matrix, PROXY) heavy asset measured, not a sector label (same
    # helper as fixed_cost); "beaten down" now reads the panel 52w / 5-year
    # lenses through beaten_down_any. Old rule surfaced as regime_cyclical_watch.
    _reframe('regime_cyclical', (
        _not_fin_re & asset_heavy(sector.isin(HEAVY_ASSET_SECTORS)) &   # (financial / real-estate guard: see fixed_cost)
        beaten_down_any(0.20) &
        (rev_yoy > 0) &
        _not_melting &
        ((ebitda_inflection > 0) | (ebitda_first_pos > 0) |
         ((ebitda_margin_delta >= 0.02) & (ebitda_margin_delta <= 0.20)) |
         (margin_shock_any & ~(ebitda_margin_delta > 0.20))) &   # (audit 3) the +20pp one-off cap applies to the shock lens too
        (not_priced_in > 0.20)))

    # ---------- Cluster F10: Option Mispriced as Dead ----------
    _cash_yield_any = ((fcf_yield > 0.05) |
                       (_ncol('owner_earnings_yield') > 0.05) |
                       (_ncol('robust_cash_yield') > 0.05) |
                       (_ncol('cash_return_ev') > 0.05))
    _DEMOTED.setdefault('dead_option', []).extend([(_ncol('ts_r13'), 1)])
    df['arch_dead_option'] = (
        is_operating &                          # (R1b) exclude financials/REITs (Wanda Hotel, Shimao)
        (mcap >= 10e6) &                        # investable scale — drops one-off-FCF sub-scale ADRs (JFU, SOGP)
        beaten_down_any(0.40) &
        _cash_yield_any &
        (ebitda_margin > 0) &
        _op_viable(0) &          # real operating cow (impairment-robust), not a one-off/near-liquidation FCF spike
        _roce_now_ok &                          # (fresh) sibling floor — not a capital-destroyer on a one-off FCF spike (TTEC roe-101%)
        (nde <= 3.0)
    ).fillna(False).astype(int)
    # (endpoint matrix) "priced as dead" now includes the 5-year high via
    # beaten_down_any; capitulation (no longer collapsing, ts_r13) and a
    # through-cycle cash record rank the members in the spirit score.
    _SPIRITED.append('dead_option')

    # ---------- Cluster G11: Operating KPI Threshold ----------
    # TIGHTENED: require BOTH a first-positive print AND confirmation that
    # the inflection is operating-level (margin or ROCE improving sequentially),
    # AND that the company is at investable scale.  Previous version fired
    # on 37 pct of universe (too broad - signal carries no information).
    # (superseded by the audit-3 legs below: an OPERATING-line first positive
    # AND a >= 2pp margin move or TTM drop-through; there is no ROCE-level
    # floor — survivability is _not_melting.)
    first_pos_print = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0)
    )
    margin_confirming = ((ebitda_margin_delta >= 0.01) |
                         (_ncol('op_margin_delta_yoy') >= 0.01) |
                         (_ncol('gross_margin_delta_yoy') >= 0.01) |
                         (_ncol('roce_delta_yoy') > 0.01)).fillna(False)
    roce_today = s('roce') >= 0.05
    # (endpoint matrix, PROXY) the threshold crossing also seen on a DATED,
    # seasonality-robust quarterly basis beside the annual first-positive
    # flags: EPS positive now after <= 0 in the same period a year earlier,
    # or TTM EBIT turned positive over the 2-year base (weekly-panel
    # snapshot). The fmp_dyn_*_turned_positive flags are deliberately NOT
    # used: they compare ONE quarter with any of the prior four (a single
    # seasonal loss quarter reads as a "turn"), the raw-sequential noise
    # this file excludes from firing.
    # (audit 3) an OPERATING-LINE crossing (EBITDA / NI / ROCE / EPS / TTM
    # EBIT); a CFO- or FCF-only first positive (the noisiest, working-capital
    # driven) counts only beside an operating turn
    _kpi_op_turn = ((ebitda_first_pos > 0) | (ni_first_pos > 0) | (roce_first_pos > 0)
                    | (_ncol('fqx_eps_turned') == 1) | (_ncol('bs_ebit_turned') == 1)).fillna(False)
    _kpi_turn = _kpi_op_turn
    # (audit 3) confirmation = a >= 2pp margin move (1pp is drift) or a real
    # TTM drop-through; the bare roce >= 5% escape is dropped
    _kpi_confirm = ((ebitda_margin_delta >= 0.02) | (_ncol('op_margin_delta_yoy') >= 0.02)
                    | (_ncol('gross_margin_delta_yoy') >= 0.02) | (_ncol('roce_delta_yoy') >= 0.02)
                    | (_ncol('fqx_inc_ebit_margin_dt') >= 0.30)).fillna(False)
    df['arch_kpi_threshold'] = (
        is_operating &                          # (R1b) exclude financials/REITs (KPI/margin lens is operating-only)
        _not_melting &                          # (tail) a loss-narrowing margin delta must not substitute for the returns floor (MKTW roce-75%)
        _kpi_turn & _kpi_confirm &
        (mcap >= 10e6)                          # (G6) restore investable-scale floor
    ).fillna(False).astype(int)
    _SPIRITED.append('kpi_threshold')

    # ---------- Cluster G12: Regional Blind-Spot ----------
    # ADV data only covers ~13% of the universe (PEW screen subset), so we
    # use ADV as a hard gate where present but fall back to mcap-only for
    # the rest of the under-covered geographies.
    adv_has = adv < 1e10  # finite ADV present
    _DEMOTED.setdefault('blindspot', []).extend([(_ncol('op_margin'), 1)])
    df['arch_blindspot'] = (
        country.isin(BLINDSPOT_COUNTRIES) &
        is_operating & (mcap > 0) & (mcap < 4e8) &
        ~(_ncol('sent_n_analysts') > 1) &                # (audit 3) neglect OBSERVED where any estimate coverage exists
        ((~adv_has) | (adv < 5e5))
    ).astype(int)
    # (tighten) the ADV leg was dead (the pew ADV field is absent for firers):
    # tradeable-but-thin in USD ($50k-$2.5M / week), observed neglect (<= 1
    # analyst), a real operating business. Exceptional: also profitable on
    # EBITDA and FCF.
    # weekly USD dollar volume from the panel; for names the panel lacks, the
    # master's daily dollar volume x 5 (same measure, daily source)
    _dv_wk = _ncol('ts_dvol26_usd').fillna(_ncol('pew_avg_dollar_volume') * 5)
    _tier('blindspot',
          is_operating & _dv_wk.between(5e4, 2.5e6) & ~(_ncol('sent_n_analysts') > 1),
          ~(_ncol('sent_n_analysts') > 0) & (_dv_wk <= 5e5),
          elite_metric=fcf_yield,
          measured=_dv_wk.notna())

    # ---------- Cluster H: Microcap Inflection + Activist Capital Allocation ----------
    # Pattern (user write-up):
    #   - microcap (<$250M mcap USD)
    #   - short-term profit inflection (margin expansion or first-positive
    #     print or accelerating sales)
    #   - cheap (~5x EV/EBITDA target, we use <8x as the gate)
    #   - clean debt-free or net-cash balance sheet
    #   - strong backlog AND a recently appointed board member with a track
    #     record of capital-allocation re-rating (CANNOT be assessed from
    #     fundamentals — both require an EDGAR / SEDAR filing scrape; see
    #     sedar_backlog_scraper.py)
    # We tag every name matching the QUANT half of the pattern; the
    # backlog / board-change confirmation is left to the scraper layer.
    ev_ebitda_col = s('ev_ebitda', 99.0)
    nde_col = nde   # the negative-EBITDA-guarded series, not a raw re-read
    profitable = ebitda_margin >= 0.05
    # (audit 3) an INFLECTION is a first-positive print or a shock-sized
    # margin move; a 5pp revenue acceleration on its own is drift
    inflection_now = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0) |
        (ebitda_margin_delta >= 0.02) | margin_shock_any
    )
    clean_balance_sheet = (
        (cash_gt_ev > 0) | (net_cash_pct > 0.05) | (nde_col <= 0.0)
    )
    cheap_on_ebitda = (((ev_ebitda_col > 0) & (ev_ebitda_col <= 8.0)) |
                       ((_ncol('p_e') > 0) & (_ncol('p_e') <= 8.0)) |
                       ((pb > 0) & (pb <= 0.8)))
    df['arch_micro_activist_inflect'] = (
        is_operating &                  # (R1b) exclude financials/REITs
        (rev_yoy > 0) &                 # (R5) inflection with a GROWING top line, not a cost-cut blip in decline
        _not_melting &                  # (tail) EBITDA-margin "profitable" alone let op-loss burners in (SOGP roce -95%)
        (mcap > 0) & (mcap < 250e6) &
        (ebitda_margin > 0) &           # (gate-audit) was ebitda_margin>=0.05, which zeroed the thesis's OWN "first-positive print" arm (a name printing its first positive EBITDA sits near 0%, not 5%): 0 of 620 firers were pre-profit, 244 blocked incl. 108 first-positive prints. _not_melting already carries survivability.
        inflection_now &
        _no_rsplit_yoy &                # (audit 3) a reverse split in the year is the delisting-avoidance tell, not an inflection
        clean_balance_sheet &
        cheap_on_ebitda
    ).fillna(False).astype(int)
    # (endpoint matrix, LEG) the missing half, where observable: a fresh SC 13D
    # (a new >= 5% holder with intent, <= 12 months) on the name. Surfaced as
    # the archetype's EXCEPTIONAL tier rather than a core gate: the filing
    # feed is US-only, so gating on it would drop every non-US member for
    # want of data, not for failing the thesis. (Restricted to < $2B market
    # caps: SC 13D is looked up by symbol, and a large company's hits are
    # mostly 13Ds it FILED on its own holdings.)
    _13d_recent = ((_evt_age_days('evt_sc13d_date') <= 365) & (mcap < 2e9)).fillna(False)
    df['micro_activist_13d_flag'] = _13d_recent.astype(int)
    df['micro_activist_inflect_exceptional'] = (
        (df['arch_micro_activist_inflect'] == 1) & _13d_recent).astype(int)

    # ---------- Cluster I-L: EDGAR XBRL-derived archetypes (US filers only) ----
    # These rely on multi-year ROIC/ROIIC fields from edgar_roic_roiic.py.
    # Names without EDGAR coverage get 0 (no signal, not negative).
    roic_lindy = s('roic_lindy', np.nan)
    cash_roic_lindy = s('cash_roic_lindy', np.nan)
    roiic_lindy = s('roiic_lindy', np.nan)
    cash_roiic_lindy = s('cash_roiic_lindy', np.nan)
    roic_inflect = s('roic_inflection_flag', 0)
    cash_roic_inflect = s('cash_roic_inflection_flag', 0)
    roiic_1y_pos = s('roiic_1y_positive_flag', 0)
    cash_roiic_1y_pos = s('cash_roiic_1y_positive_flag', 0)
    roiic_accel = s('roiic_acceleration', np.nan)
    cheap_per_roiic = s('cheap_per_roiic_lindy', np.nan)
    asset_3y_cagr = s('asset_3y_cagr', np.nan)
    p_tb = s('p_tb', np.nan)
    tangible_equity_pct = s('tangible_equity_pct', np.nan)

    # I — Durable reinvestment: lindy ROIIC > 15% over a multi-cycle history.
    # The Mauboussin / Mayer compounder signature.
    # (financial-growth) PER-SHARE COMPOUNDER, held in every window: the 5-year
    # per-share revenue AND operating-cash-flow growth >= +47% (8%/yr) on EACH
    # of the last five FY rows, no FY with diluted-share growth > 5%. Surfaced
    # for the books and the exceptional tiers, never a gate.
    df['per_share_compounder_flag'] = ((_ncol('fg_rev_ps_5y_min5') >= 0.47) & (_ncol('fg_ocf_ps_5y_min5') >= 0.47)
                                       & ~(_ncol('fg_shares_dil_g_max3') > 0.05)).fillna(False).astype(int)
    df['arch_durable_reinvestment'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok &                               # (R4) current returns not negative
        (roic_lindy >= 0.10) &                       # (G3) positive base ROIC
        (s('n_yrs_positive_roic', 0) >= 4) &         # (G3) require ROIC history
        (roiic_lindy >= 0.15) & (roiic_lindy <= 1.0) &  # (G3) sane ROIIC band
        ((asset_3y_cagr > 0.05) | (roiic_lindy >= 0.20))   # (gate-audit) asset growth OR strong ROIIC: the 5% asset-growth floor biased to asset-HEAVY reinvestment and dropped 29 top-tier asset-LIGHT compounders (IP/software/franchise) that grow earnings without growing the balance sheet — roiic already proves profitable reinvestment
    ).fillna(False).astype(int)

    # J — Cash-confirmed reinvestment: cash ROIIC lindy > 12% (lower bar than
    # NOPAT because FCF includes capex outflows).
    df['arch_cash_reinvest'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok &                               # (R4) current returns not negative
        (cash_roic_lindy >= 0.10) &                  # (G3) positive base cash ROIC
        (s('n_yrs_positive_roic', 0) >= 4) &         # (G3) require ROIC history
        (cash_roiic_lindy >= 0.12) & (cash_roiic_lindy <= 1.0) &  # (G3) sane band
        ((asset_3y_cagr > 0.05) | (cash_roiic_lindy >= 0.20))   # (audit 3) asset growth OR a strong cash ROIIC (the asset-light compounder), as durable_reinvestment
    ).fillna(False).astype(int)

    # K — ROIC inflection: latest ROIC crossed zero from below AND cash ROIC
    # also positive (confirms the inflection is real, not accounting).
    _SPIRITED.append('durable_reinvestment')     # (endpoint matrix, EXC) price-lindy + TTM path in the spirit score
    # (endpoint matrix, PROXY) the annual zero-cross gets a DATED TTM lens:
    # TTM EBIT turned positive over the 2-year base AND the TTM ROIC is now
    # positive. (Not fmp_dyn_opinc_turned_positive: that compares one quarter
    # with the prior four, a seasonality-confounded "turn".)
    _roic_turn_q = ((_ncol('bs_ebit_turned') == 1)
                    & (_ncol('fqx_roic_ttm') > 0)).fillna(False)
    df['arch_roic_inflect'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        ((roic_inflect == 1) | _roic_turn_q)          # the ACCOUNTING return crossed (annual or dated TTM); cash confirms below
        & ~(_ncol('fqx_roic_ttm') < 0.03)            # (audit 3) the turn is SIZED where the dated TTM measures it (ROIC >= 3%, not a zero-touch)
        & (cash_roic_lindy.fillna(-1) > 0)
        & (rev_yoy > 0)                              # (R5) not a cost-cut blip in a shrinking co
        & _op_viable(0)               # (R4) inflection is REAL now — positive operating result (impairment-robust: a cash-generative writedown-hit inflector is kept)
    ).fillna(False).astype(int)

    # L — Cheap per reinvestment yield (PEG analogue on ROIIC). Lower
    # cheap_per_roiic = more reinvestment yield per multiple paid. Threshold
    # 1.5 means "you're paying < 1.5x EV/EBITDA per percent of lindy ROIIC".
    _DEMOTED.setdefault('cheap_per_roiic', []).extend([(_ncol('ev_ebitda').where(_ncol('ev_ebitda') > 0), -1)])
    df['arch_cheap_per_roiic'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok & _not_melting &           # (R4/fresh) current returns not negative + not a cash-burner (KPLT fcf-41%)
        (roic_lindy >= 0.05) &                  # (G3/topcheck) POSITIVE base ROIC — ROIIC on a negative base (KPLT roic_lindy -0.15) is loss-narrowing noise, not reinvestment
        (cheap_per_roiic > 0) & (cheap_per_roiic <= 1.5) & (roiic_lindy > 0.10) &
        ~(_ncol('fqx_ebit_ttm_g') < -0.10)      # (audit 3) the reinvestment is still returning now (TTM EBIT not shrinking)
    ).fillna(False).astype(int)
    _SPIRITED.append('cheap_per_roiic')          # (endpoint matrix, EXC) cash ROIIC + real reinvestment rank the members

    # M — Tangible-value floor: P/TB < 0.7 with tangible equity > 50% of book
    # equity (real assets, not goodwill).
    _DEMOTED.setdefault('tangible_value', []).extend([(_ncol('fmp_altman_z'), 1), (_bs_d2a, -1)])
    df['arch_tangible_value'] = (
        is_operating &                          # (G1) exclude financials/REITs/utilities
        (mcap >= 10e6) &                        # investable scale (was firing on $2k shells)
        (p_tb > 0) & (p_tb < 0.7) &
        # (non-XR review) tangible_equity_pct is NOT a master column -> was
        # DEAD; derive the ratio from present levels (tangible_equity/equity),
        # permissive when either is absent so non-EDGAR names are not excluded
        (~((_ncol('tangible_equity') / _ncol('equity').where(_ncol('equity') > 0)) <= 0.50)) &
        _not_melting &                          # (gate-audit) was a positive-cash mandate (fcf>0|cfo>0) — a P/TB<0.7 Graham asset play excludes exactly the money-losing-but-asset-rich names it exists to find; _not_melting + the deep-burn guard below carry survivability
        ~(_ncol('fcf_yield') < -0.15) &         # (fresh) not deeply FCF-negative via capex burn — the CFO fallback let cyclicals melt the floor (BATL fcf -153%, MOS, HPK)
        ~(net_cash_pct > 1.0) &                 # (deep-audit) drop >100%-of-mcap cash operating shells: HOLO (net-cash 677%, pb 0.11), MLGO (366%) are RED-verdict reverse-split ADR pumps where the sub-book print is a serial-dilution artifact, not tangible value.
        is_operating                            # (user) leverage cap and Altman veto removed: weights, not gates
    ).fillna(False).astype(int)

    # ---------- N-Q: Lindy durability archetypes (EDGAR multi-year) ----------
    # All four are ADDITIVE — they fire on top of the existing point-in-time
    # archetypes, never replace them. Names without EDGAR coverage (non-US
    # filers) score 0 here but keep all their existing archetype matches.
    op_margin_lindy = s('op_margin_lindy', np.nan)
    ebitda_margin_lindy = s('ebitda_margin_lindy', np.nan)
    fcf_margin_lindy = s('fcf_margin_lindy', np.nan)
    n_yrs_fcf_pos = s('n_yrs_positive_fcf', 0)
    n_yrs_opinc_pos = s('n_yrs_positive_opinc', 0)
    n_yrs_roic_pos = s('n_yrs_positive_roic', 0)
    years_of_history = s('years_of_history', 0)
    revenue_5y_cagr = s('revenue_5y_cagr', np.nan)
    revenue_accel_lindy = s('revenue_acceleration_lindy', np.nan)
    asset_5y_cagr = s('asset_5y_cagr', np.nan)
    shares_growth_3y = s('shares_growth_3y', np.nan)

    # N — Durable Margin: high op margin AND high EBITDA margin held over
    # 5+ years (compounder signature). Distinct from the point-in-time
    # CapitalDiscipline tag, which can fire on a single good year.
    df['arch_lindy_margin'] = (
        (op_margin_lindy >= 0.10) & (op_margin_lindy <= 0.6) &   # cap: royalty holdco / one-off (INVA 95%)
        (ebitda_margin_lindy >= 0.12) & (ebitda_margin_lindy <= 0.8) &
        (years_of_history >= 5)
        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
        & _roce_now_ok   # (R4) durable margin is not a current loss-maker (MKTW roce -76%)
    ).fillna(False).astype(int)

    # O — Consistent FCF: positive FCF in 4 of last 5 years AND positive
    # operating income in 4 of last 5. Cash-generation durability test
    # that strips out the accounting noise.
    # (tighten) "durable HIGH margin" measured on the WORST year, not the
    # median: 10% lindy op margin was met by 28% of investable names once FMP
    # history went global; the through-cycle minimum is what durability means.
    # durability is measured over the years we HAVE: the worst year of >= 3
    # observed (7 years remain the exceptional / spirit lens, longer = better);
    # with fewer than 3 the statement-history median stands in
    # (audit 3) one threshold on two statistics: the WORST year >= 15% where
    # >= 3 years are on file; where only the MEDIAN exists it is judged at
    # 20% (a median is a laxer statistic than a minimum)
    _min_opm_chain = _ncol('tc_min_opm').where(_ncol('tc_years') >= 3)
    _lm_core = ((_min_opm_chain >= 0.15)
                | (_min_opm_chain.isna() & (_ncol('fmp_st_op_margin_lindy') >= 0.20)))
    _min_opm_chain = _min_opm_chain.fillna(_ncol('fmp_st_op_margin_lindy'))
    # (audit 3) STILL DURABLE: the current op margin >= 0.7x the through-cycle median
    _lm_still = ~(s('op_margin', np.nan) < 0.7 * _ncol('tc_med_opm'))
    _tier('lindy_margin',
          _lm_core & _lm_still,
          (_ncol('tc_min_opm') >= 0.20) & (_ncol('tc_min_gm') >= 0.40),
          elite_metric=_ncol('tc_min_opm'),
          measured=_min_opm_chain.notna())

    _DEMOTED.setdefault('lindy_fcf', []).extend([(_ncol('fq_sbc_pct_revenue'), -1), (_ncol('revenue_3y_cagr'), 1)])
    df['arch_lindy_fcf'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok & _not_melting &                # (R4) current returns not negative; (deep-audit) _roce_now_ok is NaN-permissive, so a NaN-roce op&fcf melter (DSNY op-21.6%/fcf-0.8%/roce NaN) slipped through — _not_melting closes the leak.
        ~(_ncol('roic_after_sbc').notna() & (_ncol('roic_after_sbc') < 0)) &  # (gate-audit) 87 firers earn NEGATIVE returns once SBC is expensed — "durable FCF" flattered by the stock-comp add-back
        (years_of_history >= 5) &                    # (R4) real multi-cycle history, not a 1-yr shell
        (n_yrs_fcf_pos >= 4) &
        (n_yrs_opinc_pos >= 4) &
        # (audit 3) a LEVEL: through-cycle FCF margin >= 10% or lindy ROIC >= 8%
        # where either is measured (FCF of +0.1% of sales every year is not lindy)
        ~((_ncol('tc_fcf_margin_avg') < 0.10) & ~(roic_lindy >= 0.08)) &
        is_operating
    ).fillna(False).astype(int)

    # (tighten) "4 of 5 positive FCF years" is the base rate of profitable
    # firms; durability = FCF positive in EVERY one of >= 7 fiscal years at a
    # real margin. Exceptional: the price has also been durable (5y max
    # drawdown shallower than -40% — owners were never asked to sit through a
    # collapse).
    _fcf_all_pos = ((_ncol('tc_fcf_pos') == _ncol('tc_fcf_years')) & (_ncol('tc_fcf_years') >= 7))
    _fcf_all_pos = _fcf_all_pos.where(_ncol('tc_fcf_years').notna(),
                                      (_ncol('fmp_st_n_yrs_positive_fcf') >= np.minimum(5, _ncol('fmp_st_years_of_history')))
                                      & (_ncol('fmp_st_years_of_history') >= 3))
    _tier('lindy_fcf',
          _fcf_all_pos,
          (_ncol('tc_fcf_years') >= 8) & (_ncol('tc_fcf_margin_avg') >= 0.15),
          elite_metric=_ncol('tc_fcf_margin_avg'),
          measured=_ncol('tc_fcf_years').notna() | _ncol('fmp_st_years_of_history').notna())

    # P — No Dilution (Clean Compounder): shares roughly flat over 3y AND
    # FCF positive 4 of 5 AND ROIC positive 4 of 5. The Mayer / Mauboussin
    # owner-operator pattern - reinvesting at high returns without
    # constantly tapping equity holders.
    # (G10) reverse-split guard: a one-period share-count drop < -30% is a
    # split / restructuring, not a buyback — it only counts as "no dilution"
    # when corroborated by a real buyback yield.
    _buyback_corrob = (_ncol('buyback_yield') > 0)
    _not_split_3y = (shares_growth_3y >= -0.30) | _buyback_corrob
    _not_split_yoy = (_ncol('shares_yoy') >= -0.30) | _buyback_corrob
    df['arch_no_dilution'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok & _not_melting &                # (deep-audit) the ONLY EDGAR-durability gate lacking a current-state floor — it fired on HISTORY (4/5y FCF+ROIC) while the name melts NOW: MED nde 84.9x/roce-7.7%, BRLT roce-19%, SLP op-76%. Add the two legs its siblings (lindy_fcf/owner_operator/buyback_compounder) already carry.
        ~(_ncol('fg_shares_dil_g_max3') > 0.05) &     # (financial-growth) no FY with diluted-share growth > 5% in the last three where measured
        (((shares_growth_3y <= 0.02) & _not_split_3y) |
         (_ncol('shares_growth_3y').isna() & (_ncol('shares_yoy') <= 0.007)   # (audit 3) the 1-year fallback at the same bar as +2% over 3 years (~0.7%/yr)
          & _not_split_yoy)) &
        ~(_ncol('shares_yoy') > 0.02) &   # (audit) CURRENT-year dilution veto: a flat 3yr count can hide a name issuing heavily NOW (STGW +91%, OMC +58% via M&A stock) — a "no dilution" gate must not pass an active diluter
        (n_yrs_fcf_pos >= 4) &
        (n_yrs_roic_pos >= 4)
    ).fillna(False).astype(int)
    # (tighten) the docstring's "reinvesting at HIGH returns" is now enforced:
    # lindy ROIC >= 10% (EDGAR or FMP statement history). Exceptional: shares
    # flat-or-down over 5y, ROIC >= 15% and FCF per share still rising.
    _tier('no_dilution',
          (_ncol('roic_lindy') >= 0.10),
          (_ncol('shares_growth_5y') <= 0) & (_ncol('roic_lindy') >= 0.15) & (_ncol('fqx_fcf_ps_g') > 0),
          elite_metric=_ncol('roic_lindy'),
          measured=_ncol('roic_lindy').notna())

    # ---------- Z-AC: Capital-allocation archetypes (audit June 2026) ---------
    # Directly extracted from EDGAR XBRL: payments of dividends + buybacks +
    # SBC + real effective tax rate. Distinct from the prior shares-growth
    # proxies in NoDilution / BuybackCompounder — these use the actual cash
    # spent rather than inferring from share count.
    capital_return_yield = s('capital_return_yield', np.nan)
    dividend_yield = s('dividend_yield', np.nan)
    buyback_yield = s('buyback_yield', np.nan)
    sbc_pct_revenue = s('sbc_pct_revenue', np.nan)
    # (audit 3) the GLOBAL book tax rate from the FMP enrichment (ratios TTM,
    # ~82% of the universe) where the EDGAR / quarterly rate is absent — the
    # tax family's 5% reach was plumbing, not a thesis limit; sane band 0-100%
    _fmp_etr = _ncol('fmp_effective_tax_rate').where(_ncol('fmp_effective_tax_rate').between(0.0, 1.0))
    effective_tax_rate = _ncol('effective_tax_rate').fillna(_fmp_etr)
    roic_after_sbc = s('roic_after_sbc', np.nan)
    interest_coverage = s('interest_coverage', np.nan)

    # Z — Capital Returner: paying back >= 5% of market cap per year via
    # dividends + buybacks combined. Greenblatt-style direct evidence.
    # Total shareholder yield seen through ANY available lens — the single
    # capital_return_yield column is 4% covered; dividends + buybacks cover
    # far more of the universe and express the same fact.
    _div_y = _ncol('dividend_yield')
    _bb_y = _ncol('buyback_yield')
    _tot_yield = _div_y.fillna(0) + _bb_y.fillna(0)
    _tot_yield = _tot_yield.where(_div_y.notna() | _bb_y.notna())
    # FCF-COVERED: the return must be funded by the cash the business
    # generates, not the balance sheet. 985 firers were paying out with FCF
    # negative (returning cash they don't earn) — those move to the
    # Balance-Sheet Return archetype below. Coverage passes when FCF is
    # positive, or unknown (don't penalise missing FCF for otherwise-covered
    # payers).
    _fcf_y = _ncol('fcf_yield')
    # (audit 3) where FCF is unknown, the count must at least not be growing
    # (a payout funded by issuance is not a return)
    _covered = (_fcf_y > 0) | (_fcf_y.isna() & ~(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')) > 0))
    df['arch_capital_returner'] = (
        is_operating &                                    # (G1) exclude REIT/BDC mandatory payouts
        (((capital_return_yield >= 0.05) & (capital_return_yield <= 0.30)) |
         ((_tot_yield >= 0.05) & (_tot_yield <= 0.30)))   # >30% total yield =
                                                          # stale price / return-
                                                          # of-capital artifact
        & _covered
    ).fillna(False).astype(int)
    # (audit 3) a > 30% yield is a TENDER / SPECIAL DIVIDEND event when the
    # cash-flow statement carries it — routed to a surfaced flag, not dropped
    df['special_return_event_flag'] = (is_operating & ((capital_return_yield > 0.30) | (_tot_yield > 0.30))
                                       & ((_ncol('fmp_st_dividend_payout_cf') > 0) | (_ncol('net_buyback_ttm') > 0))).fillna(False).astype(int)
    # (tighten) "FCF-funded" proven over time: dividends + buybacks covered by
    # FCF in EACH of the last 3 fiscal years (a single positive FCF year is not
    # coverage). Exceptional: a >= 5-year dividend-raise streak with no cut.
    _covered_now = ((capital_return_yield <= fcf_yield) & (fcf_yield > 0))
    _cov_chain = (_ncol('tc_uncov_payout_3y') == 0).where(_ncol('tc_uncov_payout_3y').notna(), _covered_now)
    _tier('capital_returner',
          _cov_chain,
          (_ncol('evt_div_raise_streak') >= 5) & ~(_ncol('evt_div_cut_2y') == 1),
          elite_metric=capital_return_yield,
          measured=_ncol('tc_uncov_payout_3y').notna() | (fcf_yield.notna() & capital_return_yield.notna()))

    # Z2 — Balance-Sheet Return / Cash-Rich Runoff: a DISTINCT thesis, not an
    # operating compounder. Companies returning cash NOT generated by
    # operations (dividends/buybacks while FCF is negative — funded from the
    # balance sheet), PLUS negative-EV businesses (net cash exceeds market
    # cap). Separated out so the operating capital-returner stays FCF-covered,
    # and so these cash-rich / self-liquidating situations get their own home.
    _returns_any = ((capital_return_yield >= 0.02) |
                    (_tot_yield >= 0.02)).fillna(False)
    # (endpoint matrix, PROXY) "returning cash the business did not earn"
    # measured over the cycle where the annual statements allow: payouts
    # exceeded FCF in >= 2 of the last 3 fiscal years (the PRIMARY lens — one
    # negative TTM FCF print is a noisy single window); the TTM test is the
    # fallback where the 3-FY history is unavailable.
    _tc_uncov = _ncol('tc_uncov_payout_3y')
    _uncovered = _returns_any & ((_tc_uncov >= 2) | (_tc_uncov.isna() & (_fcf_y < 0)))
    # (G1) the negative-EV leg must exclude financials/REITs/utilities, whose
    # EV goes hugely negative on deposits/float (not distributable cash).
    _neg_ev = (((_ncol('enterprise_value') < 0) | (cash_gt_ev > 0))
               & is_operating).fillna(False)
    # (audit 3) an UNCOVERED payout is this thesis only when the balance sheet
    # funds it — net cash >= 2x the yield (or known net cash); otherwise it is a
    # debt-funded payout. Negative EV without any payout is negative_ev_value's
    # ground, so the neg-EV branch needs a return too. Investable, not melting.
    _bsr_funded = ((net_cash_pct_sane >= 2.0 * _tot_yield.fillna(capital_return_yield).fillna(0))
                   | (_nde_known <= 0)).fillna(False)
    df['arch_balance_sheet_return'] = (
        is_operating & (mcap >= 10e6) & _not_melting
        & ((_uncovered & _bsr_funded) | (_neg_ev & _returns_any))
    ).fillna(False).astype(int)

    # AA — Low-SBC Quality: clean accounting (SBC < 2% of revenue) AND
    # genuinely profitable (EBITDA margin > 5%). Filters out SaaS /
    # crypto / hyper-growth names whose GAAP earnings are SBC-inflated.
    # SBC/EBITDA and roic_after_sbc≈roce are alternate clean-accounting
    # lenses for names lacking the revenue-based ratio.
    _roic_asbc = _ncol('roic_after_sbc')
    _roce_n = _ncol('roce')
    df['arch_low_sbc_quality'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok &                          # (R4) not a current loss-maker (SOGP roce -0.96)
        ~(_ncol('shares_growth_3y') > 0.10) &   # not a serial diluter (CCLD +135% shares); missing => pass
        # (fresh) SBC must be PRESENT and low — a MISSING sbc_pct_revenue (every
        # non-US filer) used to satisfy "<2%", so the screen degenerated to
        # "not-US + thin profit" and topped out on distressed neg-EV micro-ADRs.
        (((_ncol('sbc_pct_revenue') >= 0.0) & (_ncol('sbc_pct_revenue') < 0.02)) |
         ((_roic_asbc > 0.10) & ((_roce_n - _roic_asbc).abs() < 0.02)) |
         # FMP TTM SBC/revenue where no primary ratio exists; DISCLOSED only
         # (> 0: FMP zero-fills non-disclosers — the trap the (fresh) note closes)
         (_ncol('sbc_pct_revenue').isna() & (_ncol('fmp_sbc_to_revenue') > 0)
          & (_ncol('fmp_sbc_to_revenue') < 0.02))) &
        (ebitda_margin > 0.05) &
        ((_ncol('roce') >= 0.08) | (_roic_asbc >= 0.10))   # (fresh) a real returns floor (JFU roce 0.3% out)
    ).fillna(False).astype(int)

    # AB — Tax-Efficient (real not loss-driven): effective tax rate < 15%
    # AND positive pre-tax income. Distinguishes legitimate tax structure
    # from "no tax because no profit."
    pretax_pos = s('pretax_income_ttm', np.nan)
    df['arch_tax_efficient'] = (
        is_operating &                          # (G1) exclude financials/REITs/utilities
        (effective_tax_rate >= 0.03) & (effective_tax_rate < 0.15) &  # etr floor: a near-0% rate is NOL/credit, not structure
        ((pretax_pos > 0) | (_ncol('fq_pretax') > 0)) &   # (audit 3) positive pretax income on the EDGAR line or the quarterly panel (global)
        ~(_ncol('fq_cash_tax_rate') > 0.20) &             # (audit 3) the CASH rate agrees where measured (a low book rate at a 30% cash rate is a timing quirk, not structure)
        _op_viable(0)            # real OPERATING profit (impairment-robust), not a cash-pile interest print (WIMI op_margin -9%)
    ).fillna(False).astype(int)

    # AC — Strong Coverage: debt burden trivially serviceable, seen through
    # ANY lens — interest coverage (7% covered), EBITDA vs interest expense,
    # near-zero net leverage, or outright net cash. All require positive
    # EBITDA so a loss-maker cannot back in.
    # (G6) the coverage CLAIM uses real interest coverage; the net-cash paths
    # are alternate "no interest burden" evidence but the percent-of-mcap lens
    # must be sane (net_cash_pct_sane, <=100% of mcap). (G2) profitability
    # guard uses the sane EBITDA margin (drops one-off >60% prints). (G1)
    # operating businesses only, at investable scale.
    df['arch_strong_coverage'] = (
        is_operating & (mcap >= 50e6) &
        ((_nde_meaningful <= 4.0) |          # (audit 4) the SOURCE's number (Tillinghast: debt / EBITDA above 4x is "scary"); interest coverage is a weight
         (nde <= 0.0) |                      # outright net cash (guarded series)
         (net_cash_pct_sane >= 0.20)) &      # deep net cash, sane denominator
        (_ebitda_ttm_guard > 0) &
        ((ebitda_margin_sane > 0)            # sane operating profitability
         | ((ebitda_margin > 0.6) & (_ncol('tc_med_opm') >= 0.40)))   # (audit 3) a > 60% margin is a franchise, not a one-off, when the through-cycle median corroborates it (royalty / IP)
    ).fillna(False).astype(int)
    _SPIRITED.append('strong_coverage')      # through-cycle coverage ranks the (broad) membership
    _DEMOTED.setdefault('strong_coverage', []).extend([(_ncol('interest_coverage'), 1), (_ncol('tc_min_ic'), 1)])

    # ---------- AD-AG: Segment-level archetypes (edgartools dimensional) ----
    # These fire only on names with multi-segment 10-K disclosure that the
    # edgartools harvest has parsed. Coverage is narrower than the EDGAR
    # multi-year fields (~10% of US filers) but the signal is unique —
    # nothing else in the framework looks at segment / geographic mix.
    segment_count = s('segment_count', 0)
    segment_hhi = s('segment_revenue_hhi', np.nan)
    largest_segment_share = s('largest_segment_share', np.nan)
    geographic_region_count = s('geographic_region_count', 0)
    fastest_segment_yoy = s('fastest_segment_yoy', np.nan)
    segment_growth_dispersion = s('segment_growth_dispersion', np.nan)
    customer_concentration_flag = s('customer_concentration_flag', 0)

    # AD — Diversified Segments: 4+ segments AND HHI <= 0.40. Real
    # diversification of revenue streams, lowers single-segment risk.
    df['arch_diversified_segments'] = (
        is_operating &                          # (R1b) segment-revenue-HHI is the wrong lens for financials
        (segment_count >= 4) & (segment_hhi <= 0.40)
        # (topcheck) survivability: same distressed-shell guard the sibling
        # geographic_global already carries. Diversification is a POSITIVE
        # resilience label; a deep burner (CETX fcf -131%, AMTD op -336%) whose
        # diversification plainly did NOT protect it should not wear it. Drops
        # only genuine distress, keeps every real diversified operator.
        & ((s('fcf_ttm') > 0) | (ebitda_margin > 0.05))
        & _roce_now_ok   # (deep-audit) the last missing leg vs geographic_global: TUSK roce-27%, SLP roce-59% (one-off +fcf) slipped the fcf/ebitda guard. Now byte-identical to the guarded sibling (3 melters vs 14).
        & _not_melting   # (rebuild audit 2026-10-02) the cash-aware melt gate: HGIT (non-traded REIT, sector/industry blank so the REIT exclusion missed it) passed on a depreciation-inflated 33% EBITDA margin with op margin -51% and negative FCF
    ).fillna(False).astype(int)

    # AE — Concentrated Segment Risk: HHI >= 0.70 OR largest segment >= 70%.
    # One bad year in the dominant segment sinks the whole business.
    # FIRES as a NEGATIVE signal — kept for transparency, downstream
    # consumers can flip the sign.
    df['arch_concentrated_segments'] = (
        is_operating &                          # (tail) segment-mix lens is operating-only (sibling diversified_segments gates the same way)
        ((segment_hhi >= 0.70) | (largest_segment_share >= 0.70))
        & (segment_count >= 2)
    ).fillna(False).astype(int)

    # AF — Global Geographic Footprint: 4+ geographies reporting. Currency
    # diversification + market diversification.
    df['arch_geographic_global'] = (
        is_operating &                          # (R1b) exclude financials/REITs/utilities
        _roce_now_ok &                          # survivability: not a melting distressed name (TTEC roce -9.7%)
        (geographic_region_count >= 4) &
        ((s('fcf_ttm') > 0) | (ebitda_margin > 0.05))   # a real diversified operator, not a distressed shell
    ).fillna(False).astype(int)

    # AG — Fastest Segment Inflection: a "hidden growth engine" the
    # consolidated number masks. GENUINELY multi-lens (v2): the legs read
    # independent measures across independent time bases — quarterly YoY and
    # FY YoY segment revenue, FY acceleration, the SEGMENT MARGIN lens
    # (operating income on the segment axis — a second accounting measure),
    # segment operating leverage, mix shifting toward the winner, and the
    # consolidated inflection as a stand-alone corroboration leg (no longer
    # gated behind the revenue column, so it can rescue names with sparse
    # segment data). Legacy fastest_segment_yoy keeps the gate alive on the
    # v1 signal file until the re-harvest lands; the v2 columns take over
    # automatically as they appear.
    _fs_yoy_q = _ncol('fastest_seg_yoy_q')
    _fs_yoy_fy = _ncol('fastest_seg_yoy_fy')
    _fs_accel = _ncol('fastest_seg_accel_fy')
    _fs_omd = _ncol('fastest_seg_opmargin_delta_yoy')
    _fs_oplev = _ncol('seg_oplev')
    _fs_sh_d = _ncol('fastest_segment_share_delta')
    seg_inflect_any, seg_inflect_score = _confirm([
        (_fs_yoy_q, lambda x: (x >= 0.25) & (x <= 2.0)),     # true quarterly YoY (capped: base-effect)
        (_fs_yoy_fy, lambda x: (x >= 0.25) & (x <= 2.0)),    # annual base (capped)
        (fastest_segment_yoy, lambda x: (x >= 0.25) & (x <= 2.0)),  # legacy robust max (capped)
        (_fs_accel, lambda x: x >= 0.05),                    # 2nd derivative
        (_fs_omd, lambda x: x >= 0.02),                      # segment margin inflection
        (_fs_oplev, lambda x: x >= 0.10),                    # segment operating leverage
        (_fs_sh_d, lambda x: x >= 0.02),                     # mix shift to the winner
        (segment_growth_dispersion, lambda x: x >= 0.30),    # segments diverging
        (_adv_breadth.astype(float),
         lambda x: x >= 3),                                  # whole-co corroboration
                                                             # (local, deterministic)
    ])
    # A dispersion- or corroboration-only fire still needs a leader growing
    # double digits — keep the hidden-ENGINE spirit.
    _seg_any_growth = pd.concat(
        [_fs_yoy_q, _fs_yoy_fy, fastest_segment_yoy], axis=1).max(axis=1).clip(upper=2.0)
    # (gate-audit) _not_melting keys on CONSOLIDATED op/roce/cash — but the
    # thesis is a hidden engine the CONSOLIDATED number MASKS, so a genuine
    # mix-shift name with weak consolidated optics can be wrongly barred. Add a
    # SEGMENT-level escape (cross-referencing the segment detail): a fastest
    # segment whose OP MARGIN is inflecting up (fastest_seg_opmargin_delta_yoy>0
    # or the audited seg_margin_inflect_flag) is a real profitable engine — let
    # it pass even when consolidated melts, BOUNDED so a catastrophic burner
    # (BYAH -952% EBITDA margin) still fails and the whole-company revenue-
    # decline guard still bars wind-downs.
    _seg_engine_ok = (((_fs_omd > 0) | (s('seg_margin_inflect_flag', 0) == 1))
                      & (ebitda_margin > -0.20))
    df['arch_fastest_segment'] = (
        is_operating &                          # (R8) financials/land-sale one-offs excluded
        (_ncol('revenue_ttm_usd') >= 20e6) &    # (tail) a hidden GROWTH ENGINE needs a real base, not a $0.84M shell (CKX/BYAH)
        (_not_melting | _seg_engine_ok) &       # consolidated survivability OR a genuinely inflecting profitable SEGMENT (the masked-engine case)
        (_ncol('rev_yoy') > -0.10) & ~(_ncol('revenue_3y_cagr') < -0.05) &  # (deep-audit) whole-company decline guard: a "hidden growth engine" inside a company whose TOTAL revenue is collapsing (VISN rev-84%, TRS/THRY shrinking) is a divestiture/wind-down, not a hidden engine. Mix-shift requires the parent not to be melting away (missing => pass).
        (segment_count >= 2) & seg_inflect_any & (_seg_any_growth >= 0.10) &
        # (audit 3) MATERIAL: the fastest segment is >= 15% of revenue or has
        # gained >= 3pp of the mix where the segment share is measured
        ~((_ncol('fastest_segment_share') < 0.15) & ~(_ncol('fastest_segment_share_delta') >= 0.03))
    ).fillna(False).astype(int)
    df['seg_inflect_score'] = (seg_inflect_score
                               * df['arch_fastest_segment']).round(3)

    # Q — Durable Growth: revenue 5y CAGR >= 8% AND topline accelerating
    # (3y CAGR > 5y CAGR) AND asset base growing. Multi-cycle expansion
    # without the single-year base-effect noise.
    df['arch_lindy_growth'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok &                          # (R4) durable growth is not a current loss-maker (PRCH roe -1.03, FEED roce -449%)
        (_ncol('revenue_ttm_usd') >= 20e6) &    # (topcheck) real revenue base — this leg lacked the floor its siblings have (QDMI $13.9M)
        _profit_present &                       # (deep-audit) Yartseva "LEVEL not rate": this pure-rate gate (5y CAGR + accel + asset growth) admitted cash burners with negative incremental returns (PRCH fcf-1.1%/roic_lindy-0.20, OPRX roic_lindy-0.057). Anchor durable GROWTH to durable CASH/RETURNS.
        ((fcf_yield > 0) | (n_yrs_fcf_pos >= 3) | (roic_lindy >= 0.05)) &
        (revenue_5y_cagr >= 0.08) &
        (revenue_accel_lindy > 0) &
        (asset_5y_cagr > 0.03) &
        (years_of_history >= 5) &
        ~(_ncol('fmp_st_sales_ps_5y_g').fillna(_ncol('fg_rev_ps_5y')) < 0.47) &   # (audit 3) PER SHARE: 5-year sales per share >= +47% (8%/yr) where measured (statement engine, else financial-growth)
        ~(_ncol('rev_yoy') < 0.5 * revenue_5y_cagr)   # (audit 3) still growing now: TTM >= half the 5-year rate (where present)
    ).fillna(False).astype(int)
    # (audit 3) NOMINAL local-currency growth measures the CURRENCY in a
    # high-inflation market (TRY/ARS/EGP/NGN...): every going concern clears
    # 8%/yr on inflation alone. Those listings are denoted
    # lindy_growth_hi_inflation_watch, not the core.
    _hi_infl = country.isin({'TR', 'AR', 'EG', 'NG', 'VE', 'ZW', 'LB', 'IR', 'PK', 'GH', 'SD'})
    df['lindy_growth_hi_inflation_watch'] = ((df['arch_lindy_growth'] == 1) & _hi_infl).astype(int)
    df['arch_lindy_growth'] = ((df['arch_lindy_growth'] == 1) & ~_hi_infl).astype(int)
    _SPIRITED.append('lindy_growth')     # (endpoint matrix, EXC) TTM still >= half the 5y CAGR + price-lindy rank the members

    # ---------- R-Y: Creative multi-year archetypes (EDGAR-required) ----------
    # Each leverages the multi-year XBRL coverage to surface patterns that
    # couldn't be detected with single-period yfinance data. All additive;
    # non-EDGAR names simply don't match these and keep their other tags.
    cash_roic_lindy = s('cash_roic_lindy', np.nan)
    roic_latest = s('roic_latest', np.nan)
    roic_acceleration_v = s('roic_acceleration', np.nan)
    roiic_acceleration_v = s('roiic_acceleration', np.nan)
    cash_roic_inflect_v = s('cash_roic_inflection_flag', 0)
    roic_inflect_v = s('roic_inflection_flag', 0)
    shares_growth_5y = s('shares_growth_5y', np.nan)
    asset_3y_cagr_v = s('asset_3y_cagr', np.nan)
    revenue_3y_cagr_v = s('revenue_3y_cagr', np.nan)

    # R — Quiet Compounder: proven ROIC, not noticed yet. The "boring,
    # predictable compounder before it gets discovered" pattern that
    # appears in Mayer's 100-bagger sample.
    # (deep-audit) two-path like owner_operator: the "boring compounder before
    # it is discovered" thesis is DEFINITIONALLY the neglected (often non-US)
    # name, yet keying only on EDGAR roic_lindy zeroed the whole ex-US cohort
    # (22 firers total). Add a global current-ROIC path (base-effect-guarded)
    # alongside the strong US EDGAR path; both share the quiet-tape + insider core.
    _qc_band = _ncol('ts_r52').fillna(_m12_raw).fillna(_py_raw)   # (audit 3) the weekly total-return panel first, the snapshot only where absent
    _qc_common = (is_operating & _roce_now_ok & (insider >= 0.10)
                  & (_qc_band.between(-0.10, 0.50)   # (gate-audit) upper bound 0.30->0.50: a +30% ceiling ejected a quality compounder the moment it began re-rating (the inflection you want to still own)
                     & _qc_band.notna()))
    _qc_us = ((roic_lindy >= 0.15) & (n_yrs_roic_pos >= 4)
              & (shares_growth_3y <= 0.03) & (years_of_history >= 5))
    _qc_global = (((country != 'US') | roic_lindy.isna())   # (user #5) a FOREIGN compounder on a US OTC line carries src='US' with no EDGAR lindy — it fell through BOTH paths (Nongfu Spring roce 80%, Anta 32%, Paycom). Take the ROCE path whenever the EDGAR lindy series is absent.
                  & (s('roce', np.nan) >= 0.15)
                  & ~_roce_oneoff_suspect & _not_melting
                  & ~(_ncol('shares_yoy') > 0.03)
                  # (audit 3) the same DURABILITY as the US path where the statement
                  # history exists: lindy ROIC >= 12% (ST fill) and never a loss year
                  & ~(_ncol('fmp_st_roic_lindy') < 0.12)
                  & ~((_ncol('tc_years') >= 5) & (_ncol('tc_min_opm') < 0)))
    df['arch_quiet_compounder'] = (
        _qc_common & (_qc_us | _qc_global)
    ).fillna(False).astype(int)
    # (tighten) "QUIET" measured, not assumed: the price has not run (52w total
    # return <= +20%), no deep drawdown (a quiet compounder is not a crash),
    # and earnings are still compounding (TTM EBIT +10%). Exceptional: the
    # street is genuinely not watching (observed coverage <= 3 analysts).
    _tier('quiet_compounder',
          (_ncol('ts_r52') <= 0.20) & (_ncol('ts_maxdd_5y') > -0.45) & ~(_ncol('fqx_ebit_ttm_g') < 0.10),
          (_ncol('sent_n_analysts') <= 3) & (_ncol('fqx_ebit_ttm_g') >= 0.10),
          elite_metric=_ncol('roic_lindy'),
          measured=_ncol('ts_r52').notna() & _ncol('ts_maxdd_5y').notna())

    # S — Buyback Compounder: shrinking share count + durable ROIC + clean
    # balance sheet. Greenblatt / capital-allocation classic.
    # (G10) reverse-split guard: a share-count drop < -30% in one period is a
    # split / restructuring, not a buyback — such a drop counts only when a
    # real buyback yield corroborates it. A direct buyback_yield>=0.03 stays.
    # (audit 3) the FY buyback yield from the annual cash-flow statements
    # (repurchases / FY-end mcap, global) stands in for the EDGAR buyback_yield
    _bb_yield_g = _ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0'))
    _bb_yield_pos = (_bb_yield_g > 0)
    _shares_shrink = (
        ((shares_growth_5y <= -0.05) &
         ((shares_growth_5y >= -0.30) | _bb_yield_pos)) |
        ((_ncol('shares_growth_3y') <= -0.03) &
         ((_ncol('shares_growth_3y') >= -0.30) | _bb_yield_pos)) |
        # (non-XR review) the gross-buyback-yield leg must be corroborated by
        # net non-dilution — a serial-SBC issuer out-diluting a token buyback
        # is not a cannibal (TTEC class)
        ((_bb_yield_g >= 0.03) & ~(_ncol('shares_yoy') > 0.02)) |
        # (financial-growth) the FY diluted count shrinking >= 3% (global), split-guarded
        ((_ncol('fg_shares_dil_g1') <= -0.03) & (_ncol('fg_shares_dil_g1') >= -0.30))
    )
    df['arch_buyback_compounder'] = (
        ~(_ncol('fqx_fcf_ps_g') < -0.10) &      # (audit 3) the compounding must show per share: TTM FCF/share not shrinking where measured
        _no_rsplit_yoy &                        # (audit 3) a reverse split is not a buyback
        is_operating &                          # (R1b) exclude financials/utilities/lenders (buybacks funded by float/book)
        _roce_now_ok &                          # (R4) current returns not negative
        _shares_shrink &
        ~(_ncol('shares_yoy') > 0.02) &         # (audit) current-year non-dilution on ALL shrink legs, not just the buyback-yield leg: OMC fired via a 5yr shrink while issuing +58% NOW (IPG-merger stock)
        (roic_lindy >= 0.08) &
        (n_yrs_roic_pos >= 4)                   # (audit 4 / user rule) the nde <= 1.5 cap is a weight, not a gate
    ).fillna(False).astype(int)
    _SPIRITED.append('buyback_compounder')   # (endpoint matrix, EXC) depth/persistence of the shrink ranks the members

    # T — Owner-Operator: management with skin in the game AND multi-year
    # discipline. Russo's "capacity to suffer" / Mayer's owner-operator
    # 100-bagger archetype.
    # (deep-audit) two-path: the strong US EDGAR-corroborated path (multi-year
    # ROIC+FCF history) OR a global current-returns path — the owner-operator
    # thesis is INHERENTLY a neglected-name thesis, and keying only on EDGAR
    # lindy fields zeroed the entire non-US cohort. Both paths share the
    # skin-in-the-game (insider>=0.20) + not-collapsing + not-melting core.
    _oo_common = (is_operating & _roce_now_ok & _not_melting
                  & (rev_yoy > -0.15) & (insider >= 0.20))
    _oo_us = ((n_yrs_roic_pos >= 4) & (n_yrs_fcf_pos >= 4)
              & (shares_growth_3y <= 0.02) & (years_of_history >= 5)
              & ~(fcf_yield <= 0))   # (audit 3) the same current-FCF bar as the global path
    _oo_global = (((country != 'US') | roic_lindy.isna())   # (user #5) foreign owner-operators on US OTC lines (src='US', no EDGAR lindy) fell through both paths
                  & (s('roce', np.nan) >= 0.12)
                  & ~_roce_oneoff_suspect & (fcf_yield > 0)
                  & ~(_ncol('shares_yoy') > 0.02))
    df['arch_owner_operator'] = (
        _oo_common & (_oo_us | _oo_global)
    ).fillna(False).astype(int)
    # (tighten) Yahoo "insiders" includes corporate parents: >= 60% is usually a
    # listed SUBSIDIARY, not an owner-operator (surfaced as controlled_sub_flag).
    # Core = insider 20-60%, or revealed alignment (insider buying, buybacks,
    # a shrinking count). Exceptional: insiders buying + ROIC >= 15% + no dilution.
    df['controlled_sub_flag'] = (insider >= 0.50).fillna(False).astype(int)   # (audit 3) a >= 50% holder controls the vote — the subsidiary flag starts there
    _aligned = ((_ncol('fmp_insider_aligned_flag') == 1) | (_ncol('insider_buy_flag') == 1)
                | (_ncol('buyback_yield') >= 0.01) | (_ncol('shares_growth_3y') < 0))
    _tier('owner_operator',
          insider.between(0.20, 0.58) | _aligned,   # (audit 4) the source's own range ("20-58% in the best cases"); above it, only with revealed alignment
          insider.between(0.30, 0.60)
          & ((_ncol('insider_buy_flag') == 1) | (_ncol('fmp_insider_aligned_flag') == 1)
             | (_ncol('fmp_insider_net_usd_12m') > 0)),
          elite_metric=_ncol('roic_lindy'),
          measured=insider.notna())

    # U — Quality at a Reasonable Price (QARP): high lindy ROIIC AND not
    # already discounted as a compounder. Russo-via-Buffett pattern of
    # paying fair for great vs cheap for mediocre.
    _qarp_cheap = (((s('ev_ebitda', 999) > 0) & (s('ev_ebitda', 999) <= 12)) |
                   ((_ncol('p_e') > 0) & (_ncol('p_e') <= 18)) |
                   (((_ncol('enterprise_value')
                      / _ncol('fcf_ttm').where(_ncol('fcf_ttm') > 0)) > 0) &
                    ((_ncol('enterprise_value')
                      / _ncol('fcf_ttm').where(_ncol('fcf_ttm') > 0)) <= 15)))
    df['arch_qarp'] = (
        is_operating &                          # (tail) sibling EDGAR-quality rules all gate; closes CABO/OPFI financials leak
        _roce_now_ok &                          # (tail) current returns not negative
        ~(_ncol('roce').notna() & (_ncol('roce') < 0.03)) &  # (fresh) a high lindy-ROIIC at ~0% current ROCE is a base-effect, not QARP quality (MHH roce 0.002%)
        (roiic_lindy >= 0.15) & (roiic_lindy <= 1.0) &   # (audit 3) sane ROIIC band (a tiny-denominator artifact is not quality)
        (roic_lindy >= 0.10) &                            # (audit 3) a real base ROIC under the ROIIC
        # (audit 3) "reasonable" needs two of the multiple lenses to agree, or
        # the D&A-neutral EV/EBIT <= 12 on its own (P/E <= 18 alone is ordinary)
        ((pd.concat([((s('ev_ebitda', 999) > 0) & (s('ev_ebitda', 999) <= 12)),
                     ((_ncol('p_e') > 0) & (_ncol('p_e') <= 18)),
                     ((_ncol('enterprise_value') / _ncol('fcf_ttm').where(_ncol('fcf_ttm') > 0)).between(0, 20))],
                    axis=1).fillna(False).astype(int).sum(axis=1) >= 2)
         | ((s('ev_ebit', np.nan) > 0) & (s('ev_ebit', np.nan) <= 12))) &
        (n_yrs_roic_pos >= 4) &
        (shares_growth_3y <= 0.02)
    ).fillna(False).astype(int)
    _SPIRITED.append('qarp')                 # (endpoint matrix, EXC) price-lindy + TTM growth rank the members

    # V — Reinvestment Inflection: ROIIC accelerating from a positive
    # base AND assets actually growing (not financial-engineering). The
    # signature of a compounder finding more runway.
    df['arch_reinvest_inflect'] = (
        is_operating &                          # (R1b) exclude financials/REITs (sibling durable/cash_reinvest carry this)
        _roce_now_ok &                          # (R4) current returns not negative (melting-name guard)
        (roic_lindy >= 0.05) &                  # (audit 3) a real base (> 0 was a near-zero base)
        (roiic_lindy >= 0.05) & (roiic_lindy <= 1.0) &   # (audit 3) sane ROIIC band
        (roiic_acceleration_v >= 0.05) & (roiic_acceleration_v <= 1.0) &   # (audit 3) an artifact-sized acceleration is not a signal
        ~(_ncol('fqx_ebit_ttm_g') < 0) &        # (audit 3) confirmed on the dated TTM where measured (EBIT not shrinking)
        (asset_3y_cagr_v >= 0.05)
    ).fillna(False).astype(int)

    # W — Double Inflection: BOTH NOPAT-ROIC AND cash-ROIC crossed zero
    # from below in the latest year. Confirms the inflection is real
    # cash, not accounting-driven (D&A timing, accruals).
    df['arch_double_inflect'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        (roic_inflect_v == 1) &
        (cash_roic_inflect_v == 1) &
        ~(_ncol('fqx_roic_ttm') <= 0) &         # (audit 3) still positive on the dated TTM where measured
        (rev_yoy > 0) &                         # (R5) not a cost-cut blip in a shrinking co
        _not_melting &                          # (topcheck) a real cash inflection, not a one-off-EBITDA print (MSGM)
        ~(_ncol('shares_yoy') > 0.15)           # (topcheck) not funded by heavy dilution (MSGM +66% shares); missing => pass
    ).fillna(False).astype(int)

    # X — Cash Quality: cash-ROIC running materially ahead of NOPAT-ROIC
    # over the lindy window. "Earnings hide the cash" — quality-of-
    # earnings tell that Mauboussin emphasises.
    df['arch_cash_quality'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok &                          # (R4) current returns not negative (BRLT roce -19%, TTEC roe -1.0)
        (cash_roic_lindy > 0.08) &
        (roic_lindy > 0) &
        ((cash_roic_lindy - roic_lindy) > 0) &   # (audit 4 / user rule) cash earnings ABOVE accounting earnings is the thesis; the size of the gap is the spirit lens, not a second cut
        ~((_ncol('fq_capex_to_da') < 0.8) & (revenue_3y_cagr_v < 0)) &   # (audit 3) a harvester under-investing on a falling top line produces the same gap — not quality
        (shares_growth_3y <= 0.05) &            # non-dilution: the cash-earnings gap must not be an SBC add-back on a serial diluter
        ~(_ncol('roic_after_sbc').notna() & (_ncol('roic_after_sbc') < 0)) &  # (audit) share-count is not enough — 45/266 firers earn NEGATIVE returns once SBC is expensed (DOCU roic_after_sbc -0.16 on roce +0.25). The cash-earnings gap must not BE the SBC add-back.
        (n_yrs_fcf_pos >= 4)
    ).fillna(False).astype(int)
    _SPIRITED.append('cash_quality')         # (endpoint matrix, EXC) quarterly cash-leads-book confirmation + price-lindy

    # ---------- Large-Cap Quality (compounder at scale) ----------
    # A durable large-cap franchise: big, highly profitable, cash-generative,
    # conservatively financed, and either returning cash or compounding at a
    # high rate. The asymmetry/multibagger screen is small-cap-tilted, so
    # these quality giants never surface there — this archetype gives them a
    # home. Core gate uses GLOBALLY-available quality signals (margin / FCF /
    # leverage / payout); ROIC is a bonus qualifier where EDGAR provides it.
    _DEMOTED.setdefault('large_cap_quality', []).extend([(_ncol('fmp_interest_burden'), 1)])
    df['arch_large_cap_quality'] = (
        is_operating &                                      # (G1) exclude financials/REITs/utilities
        (mcap >= 10e9) &                                    # large + mega cap
        (ebitda_margin_sane >= 0.15) &                      # (G2) sane healthy profitability
        ((fcf_yield > 0) | (n_yrs_fcf_pos >= 3)) &          # cash-generative
        (nde < 3.0) &                                       # investment-grade leverage
        # (fresh) a QUALITY compounder needs real returns on capital — a 1.5%
        # dividend must not, on its own, admit a 3%-ROCE cyclical giant
        # (Ericsson/AngloPlat/Subaru). Require a genuine returns floor; the
        # payout is a supporting signal, not a substitute for quality.
        (((s('roce', np.nan) >= 0.10) & ~_roce_oneoff_suspect)
         | (roic_after_sbc >= 0.15)
         | (roic_lindy >= 0.12)) &
        ((capital_return_yield >= 0.02) | (dividend_yield >= 0.015) |
         (fcf_yield > 0.02))                                # ...and returns/generates cash
    ).fillna(False).astype(int)

    # Y — Capital-Light Pivot: revenue growing AND assets growing slower
    # AND ROIC turning up. The asset-light transition (franchise / IP /
    # platform mode).
    df['arch_capital_light_pivot'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok &                          # (R4) current returns not negative (melting ice cubes: RMNI, NUS, HURC)
        (revenue_3y_cagr_v >= 0.08) &
        (asset_3y_cagr_v < revenue_3y_cagr_v) &
        ~(asset_3y_cagr_v < -0.10) &            # (audit 3) a shrinking asset base (impairment / divestiture) is not a pivot in intensity
        (n_yrs_roic_pos >= 3) &
        ((roic_acceleration_v > 0) | (roic_lindy > 0.10))
    ).fillna(False).astype(int)
    # (endpoint matrix / audit A.3: the roic_lindy > 10% escape "defeats the
    # turning-up spirit" — a high-but-flat ROIC is not a pivot) core = ROIC
    # actually TURNING UP: the annual acceleration, or the TTM ROIC now above
    # its own lindy average (a dated quarterly lens). Old rule = _watch.
    _tier('capital_light_pivot',
          (roic_acceleration_v > 0) | (_ncol('fqx_roic_ttm') > roic_lindy),
          measured=roic_acceleration_v.notna() | (_ncol('fqx_roic_ttm').notna() & roic_lindy.notna()))

    # ---------- Betting-Against-Beta family (Frazzini & Pedersen 2014) ----------
    # Beta is a leverage substitute: leverage-constrained investors overpay for
    # high-beta assets to get embedded leverage, which flattens the security
    # market line and leaves low-beta QUALITY assets cheap (the model's alpha =
    # psi*(1 - beta), positive when beta < 1). The BAB long side is high-quality,
    # optically-boring businesses whose cash flows can be safely levered —
    # financially, or through reinvestment (= a yartseva multibagger). We follow
    # the paper's beta handling: clip Yahoo's noisy raw beta and SHRINK toward
    # the cross-sectional mean of 1 (w = 0.6) to tame illiquidity / non-
    # synchronous-trading artifacts before sorting.
    beta_present = (pd.to_numeric(df['yf_beta'], errors='coerce').notna()
                    if 'yf_beta' in df.columns else pd.Series(False, index=df.index))
    beta_raw = s('yf_beta', 1.0).clip(lower=-0.5, upper=4.0)
    beta_shrunk = 0.6 * beta_raw + 0.4

    fcf_margin_v = s('fcf_margin')
    cash_conv_v = s('cash_conversion')
    roce_v = s('roce')
    ev_ebit_v = s('ev_ebit', 99.0)
    cheap_7x_v = s('cheapness_under_7x_flag')
    berezin_v = s('berezin_score')

    # "Safe, leverable cash flows": profitable, cash-generative, clean balance
    # sheet, decent returns on capital. This quality gate also screens out
    # illiquid nano-caps whose low *measured* beta is a non-trading artifact
    # rather than genuine low market sensitivity.
    bab_quality = (
        is_operating &                          # (R1b) financials/REITs/utilities: margin/nde/roce not comparable
        (fcf_margin_v > 0.0) &
        (ebitda_margin >= 0.10) &
        (s('op_margin', np.nan) > 0) &          # (fresh) a D&A-heavy operating loss-maker is not "safe quality" (GENL.L op-47%)
        # (audit 4 / user rule) leverage is a weight on the BAB family, not a cap
        ((roce_v >= 0.10) | (cash_conv_v >= 0.60))
    )
    # Two ways a boring low-beta business still compounds hard: a yartseva
    # multibagger inflection, or a genuinely cheap price.
    bab_multibagger_leg = (yart_score >= 0.60) | inflection_print | (rev_accel > 0.05)
    bab_cheap_leg = (
        (cheap_7x_v > 0) |
        ((ev_ebit_v > 0) & (ev_ebit_v <= 8.0)) |
        (fcf_yield >= 0.08) |
        (berezin_v >= 0.60)
    )

    # 1) Pure BAB long side: genuine low beta + quality. Buffett in this lens —
    #    "long safe, profitable, low-beta assets" (the leg the paper levers up).
    # (G7) require the RAW beta present and >= 0.20: a stale/illiquid yf_beta
    # <= 0 is laundered by shrinkage into ~0.40 and falsely passes "low beta".
    # Liquidity floor (present-illiquid names only; missing ADV defaults high).
    df['arch_bab_low_beta'] = (
        beta_present & (beta_raw >= 0.20) &
        (beta_shrunk <= 0.85) & bab_quality &
        adv_has & (adv >= 1e5)                     # (R10) missing ADV (1e12 default) must FAIL the liquidity gate
    ).fillna(False).astype(int)

    # 2) Becoming more BAB-like: beta still moderate, but the business is
    #    de-risking — margins expanding, cash inflecting, deleveraging — trending
    #    toward the boring-safe profile before beta has fully compressed. (No beta
    #    time-series available, so improving fundamental stability stands in for
    #    the paper's beta compression.)
    df['arch_bab_becoming'] = (
        is_operating &                          # (R1b) exclude financials/REITs/utilities
        (_ncol('revenue_ttm_usd') >= 20e6) &    # real business, not a sub-scale loss-maker "becoming safe"
        (fcf_margin_v > -0.05) &                # de-risking toward safety is not a -49%-margin burner (RFT.AX)
        _roce_now_ok & (rev_yoy > -0.05) &      # (tail) "de-risking" is not a negative-ROCE / declining name (lastminute roce-24%, Ming Yuan)
        beta_present & (beta_shrunk > 0.85) & (beta_shrunk <= 1.15) &
        ((ebitda_margin_delta >= 0.01) | interval_inflect_any) &   # de-risking (any angle)
        ((fcf_inflection > 0) | (ebitda_inflection > 0) | (fcf_margin_v > 0.0)) &
        (nde <= 3.0)
    ).fillna(False).astype(int)

    # 3) BAB multibagger — the synthesis: low/declining-beta quality that is ALSO
    #    a yartseva multibagger OR very cheap. Boring safety + embedded compounding
    #    (financial or reinvestment leverage) at a price the market underrates.
    df['arch_bab_multibagger'] = (
        beta_present & (beta_raw >= 0.20) &        # (G7) raw beta present & >= 0.20
        (beta_shrunk <= 1.0) & bab_quality &
        adv_has & (adv >= 1e5) &                   # (G7/R10) liquidity floor; missing ADV must FAIL
        (bab_multibagger_leg | bab_cheap_leg)
    ).fillna(False).astype(int)

    # Continuous BAB attractiveness score (0..1) for ranking within the family:
    # lower shrunk beta + higher quality + cheaper. Zero when beta is unobserved.
    _lowbeta_sc = (1.0 - ((beta_shrunk - 0.4).clip(0, 1.2) / 1.2)).clip(0, 1)
    _quality_sc = (
        (fcf_margin_v.clip(0, 0.30) / 0.30) * 0.40 +
        (roce_v.clip(0, 0.30) / 0.30) * 0.30 +
        (1.0 - (nde.clip(0, 4.0) / 4.0)) * 0.30
    ).clip(0, 1)
    _ev_ebit_pos = ev_ebit_v.where(ev_ebit_v > 0, 20.0)
    _cheap_sc = (
        (fcf_yield.clip(0, 0.15) / 0.15) * 0.5 +
        (1.0 - (_ev_ebit_pos.clip(0, 20) / 20)) * 0.5
    ).clip(0, 1)
    df['bab_score'] = (
        beta_present.astype(float) *
        (0.45 * _lowbeta_sc + 0.35 * _quality_sc + 0.20 * _cheap_sc)
    ).round(4)

    # (endpoint matrix, PROXY+REACH) beta MEASURED on the weekly panel against
    # the local market, ranked WITHIN that market (Spearman vs Yahoo beta is
    # only 0.46, and ranks survive the pseudo-index level skew); Yahoo beta is
    # the fallback where the panel has no beta. The liquidity leg was dead
    # (pew ADV present for ~8% of names): USD weekly dollar volume >= $0.5M
    # (~ the old $100k/day) is the validity guard, pew ADV the fallback. A
    # non-positive panel beta is a non-trading artifact, not low risk.
    _pb_rk = _ncol('ts_beta_3y_rk').fillna(_ncol('ts_beta_1y_rk'))
    _pb_raw = _ncol('ts_beta_3y').fillna(_ncol('ts_beta_1y'))
    _pb_has = _pb_rk.notna() & (_pb_raw > 0)
    _dv26 = _ncol('ts_dvol26_usd')
    _bab_liquid = ((_dv26 >= 5e5) | (_dv26.isna() & adv_has & (adv >= 1e5))).fillna(False)
    _yb_low = beta_present & (beta_raw >= 0.20) & (beta_shrunk <= 0.85)
    _yb_mid = beta_present & (beta_raw >= 0.20) & (beta_shrunk <= 1.0)
    # (audit 3) where BOTH the 1-year and 3-year ranks exist, both must sit in
    # the low-beta third (no fillna-mixing of two horizons under one cut)
    _b1_rk_, _b3_rk_ = _ncol('ts_beta_1y_rk'), _ncol('ts_beta_3y_rk')
    _both_low = ~((_b1_rk_.notna() & _b3_rk_.notna()) & ((_b1_rk_ > 0.35) | (_b3_rk_ > 0.35)))
    _bab_low = ((_pb_has & (_pb_rk <= 0.35) & _both_low) | (~_pb_rk.notna() & _yb_low))
    _bab_below_avg = (_pb_has & (_pb_rk <= 0.50)) | (~_pb_rk.notna() & _yb_mid)
    # (audit 3) the paper's "safe" long leg is the high-payout one: a dividend
    # or buyback where either is measured
    _bab_bb_ = _ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0'))
    _bab_payout = (((_ncol('dividend_yield').fillna(0) + _bab_bb_.fillna(0)) > 0)
                   | (_ncol('dividend_yield').isna() & _bab_bb_.isna()))
    _reframe('bab_low_beta', _bab_low & bab_quality & _bab_liquid & _bab_payout)
    # (audit 3) the synthesis is no looser than either parent: a Yartseva
    # score >= 0.60 or a shock-sized margin move (not any inflection print),
    # the beta in the low third unless the Yartseva score carries it, and the
    # EV sanity band on the cheap leg
    _bab_mb_leg = (yart_score >= 0.60) | margin_shock_any
    _bab_beta_ok = _bab_low | (yart_score >= 0.60)
    _reframe('bab_multibagger', _bab_below_avg & _bab_beta_ok & bab_quality & _bab_liquid
             & (_bab_mb_leg | (bab_cheap_leg & _ev_sane)))
    # BECOMING BAB-like, measured (the old rule said "no beta time-series",
    # so fundamentals stood in): the within-market 1-year beta rank has fallen
    # >= 10 points below the 3-year rank, or 1-year volatility < 0.85x the
    # 3-year — from a not-yet-low 3-year beta (>= the 35th pct). The Yahoo
    # band + de-risking proxy stays the fallback where there is no panel beta.
    _b1, _b3 = _ncol('ts_beta_1y_rk'), _ncol('ts_beta_3y_rk')
    _v1, _v3 = _ncol('ts_vol_1y'), _ncol('ts_vol_3y')
    # (audit 3) the volatility leg MARKET-RELATIVE: after a market-wide
    # volatility decline every name's 1y vol is below its 3y — divide the
    # name's ratio by its market's median ratio
    _vratio = (_v1 / _v3.where(_v3 > 0))
    _vratio_mkt = _vratio.groupby(country).transform('median')
    _compress = (((_b1 <= _b3 - 0.10) | ((_vratio / _vratio_mkt.where(_vratio_mkt > 0)) <= 0.85))
                 & (_b3 > 0.35) & (_ncol('ts_beta_3y') > 0)).fillna(False)
    _becoming_proxy = (beta_present & (beta_shrunk > 0.85) & (beta_shrunk <= 1.15) &
                       ((ebitda_margin_delta >= 0.01) | interval_inflect_any) &
                       ((fcf_inflection > 0) | (ebitda_inflection > 0) | (fcf_margin_v > 0.0)))
    # (audit 3) "becoming safe" from a LOSS is not the paper's long leg: an
    # operating profit is required; the Yahoo-band fundamental proxy (no panel
    # beta) is denoted bab_becoming_proxy_watch, not the core
    df['bab_becoming_proxy_watch'] = (is_operating & (_ncol('revenue_ttm_usd') >= 20e6) &
                                      (fcf_margin_v > -0.05) & _roce_now_ok & (rev_yoy > -0.05) &
                                      _b3.isna() & _becoming_proxy).fillna(False).astype(int)
    _reframe('bab_becoming', (
        is_operating & (_ncol('revenue_ttm_usd') >= 20e6) &
        (fcf_margin_v > -0.05) & _roce_now_ok & (rev_yoy > -0.05) &
        (s('op_margin', np.nan) > 0) &
        _compress))

    # ---------- Lynch multiples (One Up on Wall Street) ----------
    # PEGY = P/E / (earnings growth% + dividend yield%). Lynch: <=1.0 is
    # fair-or-better, growth+income you aren't paying for. The EV variant
    # applies the same idea capital-structure-neutral: EV/EBITDA /
    # (EBITDA growth% + dividend yield%) — threshold scaled to 0.6 since
    # EV/EBITDA runs ~60% of P/E for the same business. Both ratios are
    # computed in derive_missing_columns.py with growth capped at 100% so a
    # one-off doubling can't manufacture a sub-0.1 multiple.
    # Neither core ratio has a fallback: PEGY has no earnings-growth column to
    # recompute it from, and the sales-based EV-GY analogues (psg / evsg) are
    # surfaced only as lynch_evgy_sales_watch (see below).
    pegy_v = s('pegy', 99.0)
    evgy_v = s('ev_ebitda_gy', 99.0)
    _psg_e = _ncol('psg')
    _evsg_e = _ncol('evsg')
    # Fallbacks fire only where the PRIMARY ratio is missing — they recover
    # coverage without re-defining the archetype in markets where the
    # sales-based analogues are structurally low. PEGY gets NO fallback:
    # its denominator is EARNINGS growth and no earnings-growth column
    # exists to recompute it — revenue growth would mislabel the ratio.
    _evgy_missing = _ncol('ev_ebitda_gy').isna()
    df['arch_lynch_pegy'] = (
        (pegy_v > 0) & (pegy_v <= 1.0)
    ).fillna(False).astype(int)
    # (tighten) PEGY on DURABLE growth: TTM net-income growth (date-matched
    # quarters) inside Lynch's 8-50% band with a consistent EPS record, instead
    # of Yahoo's single-quarter growth (38% of firers sat at its 100% cap).
    # Exceptional: PEGY <= 0.6 and operating income positive every year.
    # SAME-SPIRIT CHAIN (patchy data is never a requirement): TTM net-income
    # growth from the quarterly panel; for annual-only filers the latest-FY
    # growth from the statement history (fmp_st_ni_g1); Yahoo's growth only as
    # the last resort (its single-quarter figure sat at a 100% cap for 38% of
    # names, so it is capped at the band's top)
    # (audit 3) a Yahoo growth at/above its clip (>= 0.50 before clipping) is
    # UNMEASURED, not g = 50% (38% of firers sat at the cap); a share-issuing
    # acquirer's NI growth is netted for the count where it is measured
    # (financial-growth) Lynch's growth is the LONG-TERM per-share rate: the
    # 3-year net-income-per-share CAGR first, the TTM / latest-FY prints where
    # a loss year makes it unmeasurable, Yahoo last
    # the share netting applies to the TOTAL net-income legs only: the 3-year
    # CAGR is already PER SHARE (netting it again counts the dilution twice)
    _g_ly_tot = (_ncol('fqx_ni_ttm_g').fillna(_ncol('fmp_st_ni_g1'))
                 .fillna(_ncol('yf_earnings_growth').where(_ncol('yf_earnings_growth') < 0.50)))
    _g_ly_tot = ((1.0 + _g_ly_tot) / (1.0 + _ncol('fq_shares_yoy').fillna(0).clip(lower=-0.5)) - 1.0)
    _g_ly = _ncol('fg_ni_ps_3y_cagr').fillna(_g_ly_tot)
    _dy_ly = _ncol('dividend_yield').fillna(0)
    _pegy_ttm = (_ncol('p_e') / ((_g_ly * 100) + (_dy_ly * 100))).where(
        (_ncol('p_e') > 0) & _g_ly.between(0.08, 0.50))
    df['lynch_pegy_ttm'] = _pegy_ttm.round(4)
    _tier('lynch_pegy',
          (_pegy_ttm <= 1.0) & ((_ncol('fqx_eps_pos_share_8') >= 0.75)   # (audit 3) ONE durability definition: EPS UP year-on-year in >= 75% of the last 8 quarters, else NI UP on the year in >= 75% of the last (<= 5) FYs
                                | (_ncol('fqx_eps_pos_share_8').isna() & (_ncol('fmp_st_ni_up_share_5') >= 0.75)))
          & ~(_ncol('net_income_ttm') > 2.0 * _ncol('ni_avg')),   # (audit 3) a one-off gain year (NI > 2x the 5-year average) is not the growth
          (_pegy_ttm <= 0.6) & (_ncol('tc_years') >= 5) & (_ncol('tc_opinc_pos') >= _ncol('tc_years')),   # operating income positive every year on file
          elite_metric=_pegy_ttm, higher=False,
          measured=_g_ly.notna())
    # (G9) require real positive EBITDA on the EBITDA-yield path (a negative
    # EBITDA makes the ratio meaningless), and drop the sales (psg/evsg)
    # fallback for negative-EBITDA names while guarding a near-zero-EV
    # denominator (ev_sales >= 0.05 rejects the EV~0 artifact that otherwise
    # passes the cheap gate spuriously).
    _ebitda_ttm_e = _ncol('ebitda_ttm')
    _ev_sales_g = s('ev_sales', 99.0)
    # (audit 3) the psg / evsg branch is a SALES-growth ratio, not Lynch's
    # earnings-growth one — surfaced as lynch_evgy_sales_watch, not the core;
    # the EV sanity band guards the EV/EBITDA input
    df['lynch_evgy_sales_watch'] = (is_operating & _evgy_missing & (_ebitda_ttm_e > 0) & (_ev_sales_g >= 0.05) &
                                    (((_psg_e > 0) & (_psg_e <= 0.06)) | ((_evsg_e > 0) & (_evsg_e <= 0.05)))).fillna(False).astype(int)
    df['arch_lynch_evgy'] = (
        is_operating &                          # (tail) EV/EBITDA-based → meaningless for financials (TUGU/Indara insurers); P/E-based lynch_pegy correctly omits this
        _ev_sane &
        ((evgy_v > 0) & (evgy_v <= 0.6) & (_ebitda_ttm_e > 0))
    ).fillna(False).astype(int)
    # (tighten) growth denominator = min(TTM EBIT growth, 3y revenue CAGR),
    # capped at 50% — one hot EBITDA year no longer manufactures a cheap ratio.
    # Exceptional: <= 0.4 with operating leverage showing.
    # same-spirit chain: TTM EBIT growth -> latest-FY EBIT growth (annual-only
    # filers) -> the master's EBIT growth; 3y revenue CAGR is already filled
    # from the statement history where EDGAR has none
    _ebit_g_chain = _ncol('fqx_ebit_ttm_g').fillna(_ncol('fmp_st_ebit_g1')).fillna(_ncol('ebit_growth_yoy'))
    _g_ev = pd.concat([_ebit_g_chain, _ncol('revenue_3y_cagr')], axis=1).min(axis=1).clip(upper=0.50)
    _evgy_d = (_ncol('ev_ebitda') / ((_g_ev * 100) + (_ncol('dividend_yield').fillna(0) * 100))).where(
        (_ncol('ev_ebitda') > 0) & (_g_ev >= 0.08))
    df['lynch_evgy_durable'] = _evgy_d.round(4)
    _tier('lynch_evgy',
          (_evgy_d <= 0.6),
          (_evgy_d <= 0.4) & (_ebit_g_chain > _ncol('fq_rev_growth').fillna(rev_yoy)),   # with operating leverage: EBIT outgrowing sales
          elite_metric=_evgy_d, higher=False,
          measured=_g_ev.notna())

    # ======================================================================
    # Practitioner archetypes — Wolf of Oakville, Liger Cub / Byron Street,
    # Oak Bloke. Thresholds below were tightened against the investors' ACTUAL
    # published writing (blogs read Aug 2026); see refinement notes inline.
    #
    # Two cross-cutting corrections applied throughout:
    #  (1) Growth/margin inputs are CLAMPED to plausible bands. Raw yfinance
    #      deltas carry data artifacts (ebitda_margin_delta_yoy ranged to
    #      ±244,930; rev_yoy to 16,316x) that would otherwise satisfy any
    #      ">0" growth gate on garbage.
    #  (2) A negative EBITDA makes net_debt/EBITDA negative, so `nde <= X`
    #      silently passes loss-makers. Every "clean balance sheet" gate that
    #      uses nde now also requires ebitda_ttm > 0 (or uses net-cash %).
    # Sparse EDGAR-only columns (interest_coverage 8%, sbc_pct_revenue 9%,
    # capital_return_yield 5%) are used as SOFT guards — they exclude a name
    # only when the value is PRESENT and bad, never when it's missing —
    # otherwise the archetype would collapse to US filers.
    # ======================================================================
    cfo_ttm_v = s('cfo_ttm')
    fcf_ttm_v = s('fcf_ttm')
    ev_sales_v = s('ev_sales', 99.0)
    p_s_v = s('p_s', 99.0)
    fcf_margin_w = s('fcf_margin')
    op_margin_v = s('op_margin')
    ebitda_ttm_v = s('ebitda_ttm')
    # Negative-EBITDA artifact guard: net_debt/EBITDA flips NEGATIVE when
    # EBITDA is negative and then reads as NET CASH (Interfor screened at -4x
    # while carrying $817M of net debt). Treat the ratio as unknown (99 fails
    # every leverage gate) whenever EBITDA is not positive; genuine net cash is
    # still caught through net_cash_pct in _clean_bs.
    ev_ebitda_v = s('ev_ebitda', 99.0)
    pe_w = s('p_e', 99.0)
    cash_conv_w = s('cash_conversion')
    div_yield_v = s('dividend_yield')
    ebitda_yoy_v = s('ebitda_yoy').clip(-3.0, 10.0)
    ncav_pct = s('ncav_pct_mcap')
    n_analysts_v = (_ncol('n_analysts').fillna(_ncol('n_analysts_pew'))
                    .fillna(0.0))           # pew fallback; missing -> neglected
    # (G5, superseded) the Liger neglect gates read MISSING coverage as
    # neglected (the thesis: an uncovered microcap); no gate needs a presence mask.
    off_high = s('pct_off_52w_high')        # negative = below the 52w high
    # (drawdown helpers hoisted above — see after flat_or_down)
    # Clamped growth/margin inputs (kill the data-artifact tail)
    rev_yoy_c = rev_yoy.clip(-1.0, 10.0)
    emd_c = ebitda_margin_delta.clip(-1.0, 1.0)
    cash_pct_mcap_v = s('cash_pct_mcap').clip(0.0, 3.0)
    net_cash_pct_c = net_cash_pct.clip(-2.0, 2.0)

    # ---------- Mid-Cap+ GARP / Quality ----------
    # Reinvestment quality bought on a GROWING earnings stream, at mid-cap-
    # and-above scale: strong OR accelerating return on INCREMENTAL invested
    # capital (the compounding engine), paired with a good earnings yield
    # that is actually growing (attractive E/P where earnings are RISING — a
    # cheap-and-improving compounder, not a value trap or a priced-for-
    # perfection growth name).
    _ey = s('earnings_yield')                       # E/P (0.05 = P/E 20)
    _ebit_g = s('ebit_growth_yoy')
    # EBITDA/EV yield = EBITDA / enterprise value = 1 / (EV/EBITDA). Cheaper
    # and more globally-available than the P/E-based earnings yield (no net
    # income / EDGAR dependence). Good yield >= 0.08 (EV/EBITDA <= 12.5).
    # (R3) FX-corrupt EV (cross-listing ADR / currency mismatch) makes EV/EBITDA
    # absurdly low (Nitori 0.04 -> yield 25x, auto-passing "cheap"). Guard the
    # EV-multiple lens to a sane enterprise-value band (EV between 0.2x and 5x
    # mcap) AND a floor on EV/EBITDA itself, so a corrupt near-zero EV can't
    # read as ultra-cheap. A genuinely cheap name still clears EV/EBITDA >= 2.
    _ev_mcap_garp = (_ncol('enterprise_value_usd') / mcap.where(mcap > 0))  # (non-XR review) USD/USD
    _ev_sane_garp = (_ev_mcap_garp >= 0.2) & (_ev_mcap_garp <= 5.0)
    _ev_ebitda_yield = (1.0 / ev_ebitda_v).where(
        (ev_ebitda_v >= 2.0) & _ev_sane_garp, np.nan)
    # True ROIIC (EDGAR multi-year) for filers that have it...
    _roiic_true = (
        (roiic_lindy >= 0.15) |                     # strong ROIIC
        (roiic_acceleration_v > 0) |                # accelerating / growing ROIIC
        (cash_roiic_lindy >= 0.15)                  # strong cash ROIIC
    )
    # ...and a GLOBAL APPROXIMATION where ROIIC is unavailable (non-US filers
    # / no EDGAR history): high returns on capital (ROE or EBITDA margin) that
    # are being reinvested at improving incremental economics (margin
    # expansion, or exceptional ROE). Only substitutes when no true ROIIC
    # exists, so US names keep the exact measure.
    _roe = s('roe')
    _opmd = s('op_margin_delta_yoy')
    _roiic_absent = ~(roiic_lindy.notna() | roiic_acceleration_v.notna()
                      | cash_roiic_lindy.notna())
    _roiic_proxy = (
        # cap ebitda_margin at 0.6: a holdco whose "EBITDA margin" is >100%
        # equity-method income (PAH3 Porsche SE 106%) is not an operating return.
        # (fresh) the high-margin branch must ALSO show real returns on capital —
        # a fat EBITDA margin at 1% ROCE is not GARP quality (Jet2 airline).
        # (gate audit #5) ROE = NI/equity reads spuriously positive when
        # BOTH are negative — every ROE leg requires positive earnings
        (((_roe >= 0.15) & (s('net_income_ttm', np.nan) > 0)) |
         ((ebitda_margin >= 0.18) & (ebitda_margin <= 0.6)
          & (((s('roce', np.nan) >= 0.10) & ~_roce_oneoff_suspect)
             | ((_roe >= 0.10) & (s('net_income_ttm', np.nan) > 0))))) &
        ((emd_c > 0) | (_opmd > 0)
         | ((_roe >= 0.20) & (s('net_income_ttm', np.nan) > 0)))
    )
    _roiic_quality = _roiic_true | (_roiic_absent & _roiic_proxy)
    _val_good = (_ey >= 0.05) | (_ev_ebitda_yield >= 0.08)   # good E/P OR EBITDA/EV yield
    _ey_good_growing = (
        _val_good &                                 # attractively priced
        ((_ebit_g >= 0.08) | (rev_yoy_c >= 0.08)    # (audit 3) ...on a growing stream: >= 8%, not any positive print
         | (_ncol('fqx_ebit_ttm_g') >= 0.08).fillna(False))  # (endpoint matrix) date-matched TTM EBIT growth
        & ~(roiic_lindy < 0.05)                     # (audit 3) an accelerating ROIIC from a negative base (-20% -> -15%) is not GARP quality
    )
    df['arch_midcap_garp'] = (
        is_operating &                              # (R1b) exclude financials/REITs (Vonovia REIT, asset managers)
        (mcap >= 2e9) &                             # mid cap and above
        _roiic_quality &
        _ey_good_growing
    ).fillna(False).astype(int)

    def _soft_ok_below(colname, thresh):
        """True unless the column is PRESENT and >= thresh (soft exclude)."""
        c = pd.to_numeric(df[colname], errors='coerce') if colname in df.columns \
            else pd.Series(np.nan, index=df.index)
        return ~(c.notna() & (c >= thresh))

    def _soft_ok_above(colname, thresh):
        """True unless the column is PRESENT and < thresh (soft exclude)."""
        c = pd.to_numeric(df[colname], errors='coerce') if colname in df.columns \
            else pd.Series(np.nan, index=df.index)
        return ~(c.notna() & (c < thresh))

    # ---- Multi-perspective confirmation ----------------------------------
    # A process (e.g. operating-leverage inflection) is measured several
    # independent ways, each with different accounting blind spots. We fire
    # an archetype when ANY available measure confirms (robust to data gaps —
    # never shrinks the pool) and expose a CONFIRMATION SCORE (fraction of
    # available measures that agree) used to mildly upweight names where
    # several agree (robust to a single accounting distortion).
    # (_confirm hoisted above — see top of compute)

    def _num(col):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors='coerce')
            _note_coverage(col, v)
            return v
        _absent_cols.add(col)
        return pd.Series(np.nan, index=df.index)

    # Operating-leverage inflection, triangulated across accounting angles AND
    # time bases. Three time bases with different seasonality/latency trade-offs:
    #   YoY (same-quarter vs year-ago)      — seasonality-robust, lagging
    #   TTM-sequential (*_qoq_ttm)          — seasonality-robust (rolling 12mo
    #                                          cancels seasonality), earlier
    #   raw sequential (*_seq)              — earliest, but SEASONALITY-CONFOUNDED
    # We fire on any seasonality-robust turn (broadens the pool, catches early
    # inflections a lagging YoY misses) and count a RAW-sequential bump only
    # when a seasonality-robust measure corroborates it — i.e. a raw-seq turn
    # that the TTM/YoY view does NOT see is treated as seasonality and
    # downweighted, per the seasonality rule.
    _ebm = _num('ebitda_margin')
    yoy_any, yoy_score = _confirm([                                # YoY (margins)
        (_num('ebitda_margin_delta_yoy'), lambda x: x > 0),        # EBITDA margin up
        (_num('fcf_margin_delta_yoy'),    lambda x: x > 0),        # cash margin up
        (_num('gross_margin_delta_yoy'),  lambda x: x > 0),        # Tier B: gross margin up
        (_num('op_margin_delta_yoy'),     lambda x: x > 0),        # Tier B: EBIT margin up
        (_num('incremental_ebitda_margin'), lambda x: x > _ebm),   # marginal > average
        (_num('operating_leverage_ratio'), lambda x: x > 1.0),     # %ΔEBITDA/%ΔRev > 1
    ])
    ttmseq_any, ttmseq_score = _confirm([                          # TTM-sequential (robust)
        (_num('ebitda_qoq_ttm'), lambda x: x > 0),
        (_num('cfo_qoq_ttm'),    lambda x: x > 0),
        (_num('fcf_qoq_ttm'),    lambda x: x > 0),
        (_num('rev_qoq_ttm'),    lambda x: x > 0),
    ])
    rawseq_any, rawseq_score = _confirm([                          # raw sequential (seasonal)
        (_num('ebitda_seq'), lambda x: x > 0),
        (_num('cfo_seq'),    lambda x: x > 0),
        (_num('fcf_seq'),    lambda x: x > 0),
    ])
    season_robust = yoy_any | ttmseq_any
    # Fire on ANY turn (recover pool — even a raw-seq-only early signal), but…
    oper_lev_any = season_robust | rawseq_any
    # …a raw-sequential signal only earns full weight when a seasonality-robust
    # measure agrees; unconfirmed it contributes at 40% (probable seasonality).
    _rawseq_eff = rawseq_score * np.where(season_robust, 1.0, 0.4)
    oper_lev_score = (0.5 * yoy_score + 0.3 * ttmseq_score +
                      0.2 * _rawseq_eff).clip(0.0, 1.0)
    df['oper_leverage_score'] = oper_lev_score.round(3)

    # ---- Robust share-count / buyback detection (multi-angle) ----
    # Is the share count SHRINKING (buybacks, per-share accretive) or GROWING
    # (dilution)? Triangulated across five independent angles so no single
    # sparse field decides it. Non-gating — exposed as a score and used to
    # upweight, never to shrink the pool. (Populates as names re-enrich with
    # the Tier-B share-trajectory fields.)
    shares_yoy_v = _num('shares_yoy')
    fcf_ps_yoy_v = _num('fcf_per_share_yoy')
    buyback_any, buyback_score = _confirm([
        (shares_yoy_v,               lambda x: x < -0.01),   # diluted count falling YoY
        (_num('shares_3y_cagr'),     lambda x: x < -0.01),   # falling over 3y
        (_num('net_buyback_ttm'),    lambda x: x > 0),       # net cash-flow repurchases
        (_num('buyback_yield'),      lambda x: x > 0),       # buyback yield (EDGAR)
        (fcf_ps_yoy_v - _num('fcf_yoy'), lambda x: x > 0.02),  # per-share OUTPACES total
    ])
    df['buyback_score'] = buyback_score.round(3)
    # Clearly diluting = diluted share count up >2% (present). Used as a soft
    # guard where a low share count matters.
    not_diluting = ~((shares_yoy_v.notna()) & (shares_yoy_v > 0.02))

    # ---- Templeton normalized (mid-cycle) cheapness ----
    # Cheap vs the company's OWN mid-cycle earnings, not the trough/peak print
    # — the cyclical adjustment. EV / normalized(avg 5yr) EBITDA. Confirmation
    # angle only (never gates).
    _ev_now = _num('enterprise_value')
    ev_norm_ebitda = _ev_now / _num('normalized_ebitda').where(_num('normalized_ebitda') > 0)
    df['ev_norm_ebitda'] = ev_norm_ebitda.round(3)
    cheap_vs_normalized = (ev_norm_ebitda > 0) & (ev_norm_ebitda <= 8.0)

    # ---- Cheapness triangulation (for VALUE archetypes) ----
    # A name is "cheap" measured many independent ways, each distorted by
    # something different (P/E by tax/leverage/one-offs, EV/EBITDA by capex
    # intensity, EV/sales by margin, P/B by asset mix). Fire on ANY (recover a
    # name whose favoured multiple is missing) and score the breadth.
    cheap_any, cheap_score = _confirm([
        (_num('ev_ebitda'),        lambda x: (x > 0) & (x <= 10)),
        (_num('ev_ebit'),          lambda x: (x > 0) & (x <= 12)),
        (_num('ev_gross_profit'),  lambda x: (x > 0) & (x <= 8)),
        (_num('p_e'),              lambda x: (x > 0) & (x <= 15)),
        (_num('p_s'),              lambda x: (x > 0) & (x <= 1.0)),
        (_num('pb'),               lambda x: (x > 0) & (x < 1.0)),
        (_num('fcf_yield'),        lambda x: x >= 0.08),
        (_num('robust_cash_yield'),lambda x: x >= 0.08),
        (ev_norm_ebitda,           lambda x: (x > 0) & (x <= 8)),   # cheap vs mid-cycle
    ])
    # #3 — slight reward when the cheap earnings are CASH-BACKED (counters
    # paper-earnings value traps without gating them out).
    _fcf_backed = ((_num('fcf_yield') >= 0.05) |
                   (_num('robust_cash_yield') >= 0.05)).fillna(False)
    df['cheapness_score'] = (cheap_score
                             + 0.08 * _fcf_backed.astype(float)).clip(0, 1).round(3)

    # ---- Quality triangulation (for QUALITY archetypes) ----
    # Returns/quality confirmed across accrual AND cash-based, harder-to-game
    # angles (gross profitability and cash return resist accrual games).
    quality_any, quality_score = _confirm([
        (_num('roce'),               lambda x: x >= 0.12),
        (_num('roic_after_sbc'),     lambda x: x >= 0.10),
        (_num('gross_profitability'),lambda x: x >= 0.15),   # Novy-Marx
        (_num('cash_return_ev'),     lambda x: x >= 0.08),   # cash ROIC proxy
        (_num('cash_conversion'),    lambda x: x >= 0.70),
        (_num('fcf_conversion'),     lambda x: x >= 0.60),
    ])
    df['quality_score'] = quality_score.round(3)

    # ---- Revenue/top-line growth, same three time bases + seasonality ----
    # The interval-robustness we apply to operating leverage, applied to
    # top-line growth too (a consistent layer). YoY + gross-profit growth +
    # acceleration are seasonality-robust; TTM-sequential (rev_qoq_ttm) is
    # robust; raw sequential (rev_seq) is seasonal and downweighted unless a
    # robust base corroborates.
    rev_yoy_any2, rev_yoy_sc = _confirm([
        (_num('rev_yoy'),          lambda x: x > 0.05),
        (_num('rev_accel'),        lambda x: x > 0),
        (_num('gross_profit_yoy'), lambda x: x > 0.05),
    ])
    rev_ttm_any2, rev_ttm_sc = _confirm([(_num('rev_qoq_ttm'), lambda x: x > 0)])
    rev_raw_any2, rev_raw_sc = _confirm([(_num('rev_seq'), lambda x: x > 0)])
    # #4 — DURABLE, hard-to-game growth: a 3-yr CAGR smooths single-year M&A /
    # base effects, and per-share growth is immune to acquisition-by-dilution.
    # Upweighted so genuine multi-year compounders outrank one-year pops.
    _dur_any, _dur_sc = _confirm([
        (_num('rev_3y_cagr'),       lambda x: x >= 0.08),   # durable 3y top-line
        (_num('fcf_per_share_yoy'), lambda x: x > 0.05),    # per-share (M&A/dilution-proof)
    ])
    _rev_robust = rev_yoy_any2 | rev_ttm_any2
    _rev_raw_eff = rev_raw_sc * np.where(_rev_robust, 1.0, 0.4)
    rev_growth_score = (0.40 * rev_yoy_sc + 0.25 * rev_ttm_sc +
                        0.15 * _rev_raw_eff + 0.20 * _dur_sc).clip(0.0, 1.0)
    df['rev_growth_score'] = rev_growth_score.round(3)
    # Combined cross-archetype inflection confirmation (operating leverage +
    # top-line growth). Exposed so every book's ranking can upweight names
    # whose thesis is corroborated across measures AND time bases.
    # #5 — reward MARGIN EXPANSION (operating leverage showing up in the
    # margin line), not just the growth/oper-lev flags.
    _margin_exp = ((_num('ebitda_margin_delta_yoy') > 0.02) |
                   (_num('op_margin_delta_yoy') > 0.02)).fillna(False)
    inflection_confirm_score = (0.45 * oper_lev_score + 0.45 * rev_growth_score
                                + 0.10 * _margin_exp.astype(float)).clip(0.0, 1.0)
    df['inflection_confirm_score'] = inflection_confirm_score.round(3)
    # Overall confirmation for the cross-archetype ranking upweight: a name is
    # corroborated if strong on WHICHEVER dimension fits its thesis —
    # inflection, cheapness, or quality. Max (not sum) so a pure value name
    # cheap across measures ranks up as much as a pure grower inflecting.
    # Alignment: SEC revealed-preference insider buying (US filers). Cluster
    # buys strongest, then 10%-owner, officer, then net-buyer.
    _align = pd.concat([
        0.4 * s('insider_net_buyer_flag'), 0.6 * s('insider_officer_buy_flag'),
        0.8 * s('insider_10pct_buy_flag'), 1.0 * s('insider_cluster_buy_flag'),
    ], axis=1).max(axis=1).clip(0, 1)
    df['alignment_score'] = _align.round(3)

    # GOVERNANCE CONVICTION SCORE — weight the CLEAREST and TIMELIEST governance
    # signals highest. Revealed-preference insider BUYING (from the ~12-month
    # Form-4 window) is both the clearest (real money, hard to fake) and the
    # timeliest (recent action, vs a standing state), so it dominates the weight;
    # a CLUSTER of independent buyers is the strongest single tell, then senior
    # (officer/10%-owner) conviction, then the SIZE of the net buy vs market cap.
    # Timely capital-return ACTION (TTM buybacks / shrinking count) corroborates;
    # static skin-in-the-game (ownership) and SBC hygiene rank below (aligned but
    # not timely). Ranks the governance tab so the highest-conviction names lead.
    _mc_usd_g = _num('market_cap_usd')
    _g_cluster = (_num('insider_distinct_buyers').clip(0, 6) / 6.0).fillna(0)        # multiple independent buyers — clearest, hardest to fake
    _g_senior = (0.6 * s('insider_officer_buy_flag')
                 + 0.4 * s('insider_10pct_buy_flag')).clip(0, 1)                     # CEO/officer + major-holder conviction
    _g_mag = ((_num('insider_net_buy_value') / _mc_usd_g.where(_mc_usd_g > 0))
              .clip(0, 0.05).fillna(0) / 0.05)                                       # net $ bought vs mcap, capped at 5% = max conviction
    _g_return = (((_num('net_buyback_ttm') > 0) | (_num('buyback_yield') > 0)
                  | (_num('shares_yoy') < -0.01)).fillna(False).astype(float))       # TIMELY capital-return action
    _g_align = (_num('insider_ownership_pct').clip(0, 0.40) / 0.40).fillna(0)        # static owner-operator skin-in-the-game
    _g_hygiene = s('arch_low_sbc_quality', 0).clip(0, 1)                             # not enriching insiders via stock comp
    df['governance_score'] = (
        0.34 * _g_cluster + 0.20 * _g_senior + 0.18 * _g_mag
        + 0.12 * _g_return + 0.10 * _g_align + 0.06 * _g_hygiene
    ).clip(0, 1).round(3)
    # legible conviction tier for the book (High = clustered/senior/sized buying)
    df['governance_tier'] = pd.cut(
        df['governance_score'], bins=[-0.01, 0.001, 0.35, 0.60, 1.01],
        labels=['', 'Low', 'Medium', 'High']).astype(str).replace('nan', '')
    # #6 — reward breadth: a name corroborated across MORE independent
    # dimensions (inflection / cheap / quality / insider) is more trustworthy
    # than a one-legged fire. Max sets the base; a small per-extra-dimension
    # bonus lifts multi-confirmed names.
    _co_base = pd.concat(
        [inflection_confirm_score, cheap_score, quality_score, _align],
        axis=1).max(axis=1)
    _dims = ((inflection_confirm_score > 0.5).astype(int)
             + (cheap_score > 0.5).astype(int)
             + (quality_score > 0.5).astype(int)
             + (_align > 0.5).astype(int))
    _breadth_bonus = (0.05 * (_dims - 1).clip(lower=0)).clip(0.0, 0.12)
    df['confirm_overall'] = (_co_base + _breadth_bonus).clip(0.0, 1.0).round(3)

    # ===== NEW MEASURES (audit follow-up 2026-09-08) — homes for the cases
    # the robustness guards excluded, rather than just dropping them. =====

    # Financials Value/Quality: banks/insurers can't use EV/margin, so screen
    # them on BOOK: cheap on book (P/B < 1) with real returns (ROE >= 10%) and
    # not expensive on earnings. The home for the financials the operating
    # value archetypes now exclude.
    _fpb = _num('pb'); _froe = _num('roe'); _fpe = _num('p_e')
    # (tail) banks/insurers ONLY — a P/B<1 on a REIT is the IFRS-revaluation
    # value trap, and on a closed-end fund / BDC it is a discount-to-NAV whose
    # "ROE" is just the distribution rate. Those are NAV vehicles (they belong
    # in oak_nav_discount), not book-value-cheap operating financials.
    _fin_fund_vehicle = _ind_all.str.contains(
        r'closed-end|business development|investment trust|\bfund\b|'
        r'asset manage', regex=True)
    df['arch_financials_value'] = (
        is_financial & ~is_reit & ~_fin_fund_vehicle & (mcap >= 50e6)
        & (_ind_all.str.contains(r'bank|insur|thrift|savings', regex=True) | (_ind_all == ''))   # banks/insurers ONLY (brokers / consumer lenders are not book-value banks)
        & (_fpb >= 0.15) & (_fpb < 1.0)         # pb floor: <0.15x book is an ADR/currency artifact (FDCT 0.108), not a real bank
                                                # (NOT excluding _known_holdco here — that would also cut real lenders like JFIN; a discounted financial holdco is a legitimate member of the pool)
        & (_froe >= 0.10)
        & (((_fpe > 0) & (_fpe <= 15)) | _fpe.isna())
    ).fillna(False).astype(int)

    # Net-Cash Returner: net cash >= 30% of market cap AND the company is
    # ACTIVELY returning it (buybacks / dividends / shrinking share count) —
    # the legitimate, rewarded form of "cash exceeds EV" (vs the dormant
    # balance-sheet hoards that go to arch_balance_sheet_return). Operating
    # businesses only (financial holdcos' "cash" is a portfolio).
    _nbb = _num('net_buyback_ttm'); _nby = _num('buyback_yield')
    _ndy = _num('dividend_yield'); _nsh3 = _num('shares_3y_cagr')
    _returning = ((_nby > 0) | (_ndy > 0.01) | ((_nsh3 < -0.01) & _no_rsplit_3y)   # (audit 3) a shrinking count needs the reverse-split guard
                  | (_nbb > 0) | (_ncol('fmp_st_buyback_yield_y0') > 0.01)).fillna(False)   # (audit 3) FY repurchases (global) as a further lens
    df['arch_net_cash_returner'] = (
        is_operating & (mcap > 0)
        & (net_cash_pct_sane >= 0.30) & _netcash_not_contradicted   # (audit 3) sane (<= 100% of mcap, the shells tangible_value vetoes) and not contradicted by known net debt
        & _returning
        & _not_melting   # (deep-audit) a company returning cash while DESTROYING capital is the anti-thesis: YXT roce-97%, DCGO roce-95% passed on net-cash + a one-off FCF print. Add the returns floor.
    ).fillna(False).astype(int)
    # (endpoint matrix, EXC) FCF-covered returns over 3 FYs rank the members;
    # not a gate — distributing a genuine net-cash surplus is the thesis.
    _SPIRITED.append('net_cash_returner')

    # Sustainable Scaler: small-cap durable growth that is REAL — a genuine
    # revenue base (>= $20M, not a base-effect pop), NOT funded by dilution
    # (share count flat/down), growth confirmed either by a durable 3y CAGR or
    # by PER-SHARE FCF growth (immune to acquisition-by-dilution), self-funding
    # unit economics, and not overpriced on EV/sales. The home for genuine
    # small-cap compounders the base-effect growth guards now exclude.
    _sr3 = _num('rev_3y_cagr'); _sry = _num('rev_yoy'); _sfps = _num('fcf_per_share_yoy')
    _sfm = _num('fcf_margin'); _ssh3 = _num('shares_3y_cagr'); _srev = _num('revenue_ttm_usd')   # (R6+FX) USD revenue, not raw local currency
    _sroic = _num('roic_after_sbc'); _sevs = _num('ev_sales')
    # (endpoint matrix, PROXY) FCF PER SHARE also from the quarterly panel:
    # TTM FCF per diluted share vs a year ago (date-matched, both positive) —
    # a further per-share lens beside the snapshot fcf_per_share_yoy.
    _sfps_any = ((_sfps > 0) | (_num('fqx_fcf_ps_g') > 0)).fillna(False)
    _durable_growth = (((_sr3 >= 0.15) & (_sr3 <= 1.0))
                       | ((_sry >= 0.15) & (_sry <= 1.0) & _sfps_any))
    _self_funding = _sfps_any | (_sfm > 0.03) | (_sroic >= 0.10)
    _not_pricey = ((_sevs > 0) & (_sevs <= 8)) | _sevs.isna()
    _DEMOTED.setdefault('sustainable_scaler', []).extend([(_ncol('net_debt_ebitda'), -1)])
    df['arch_sustainable_scaler'] = (
        is_operating & (mcap < 2e9) & (_srev >= 20e6)  # (non-XR review) match documented $20M base
        & ((_ssh3 <= 0.0) | (_ssh3.isna() & ((_ncol('fq_shares_yoy') <= 0.0) | (_ncol('fg_shares_dil_g_max3') <= 0.0))))   # share count flat/down   # (audit 3) the cardinal sin must be MEASURED absent: 3-year count, else the quarterly / FY diluted count; no history does not pass
        & ~(_ncol('fqx_ebit_ttm_g') < 0)          # (audit 3) earnings growing with the sales where the TTM measures it
        & _durable_growth & _self_funding & _not_pricey
        & _profit_present                        # (reference II) profitability LEVEL present
    ).fillna(False).astype(int)
    # (audit 4) the SOURCE's numbers (Andreola-Deden / compendium: market cap < $300M,
    # EV/sales < 3x, growth >= 25%) are the core; the engine's looser rule stays
    # as sustainable_scaler_watch
    _tier('sustainable_scaler',
          (mcap < 300e6) & ((_sevs > 0) & (_sevs < 3.0)) & ((_sr3 >= 0.25) | (_sry >= 0.25)),
          measured=_sevs.notna() & (_sr3.notna() | _sry.notna()))

    # ==================================================================
    # TREND / MOMENTUM TRADER SETUPS — O'Neil (CAN SLIM), Weinstein
    # (Stage 2), Kullamagi (breakout). SETUP-DETECTION layer ONLY: this
    # database persists weekly-derived price signals + fundamentals, NOT
    # daily/intraday OHLCV or volume. The EXECUTION layer each trader
    # specifies — ADR/ATR stops, RVOL breakout volume, base-geometry
    # contraction/VDU, MA-surfing, opening-range-high triggers, position
    # sizing, exit state-machines — needs a live daily+intraday feed and is
    # OUT OF SCOPE here. Rule classes in comments: [C]=canonical (author
    # states it), [P]=proxy (our formalization of a qualitative rule),
    # [R]=research parameter (author gives no cutoff; fitted/sensitivity).
    # ==================================================================
    _mom12 = _num('momentum_12m'); _roc6 = _num('roc_6m')
    _live_tape = pd.to_numeric(df.get('stale_tape'), errors='coerce').fillna(0) != 1
    def _pctrank(x):
        return (x.where(_live_tape).rank(pct=True) * 100.0)
    _pr6 = _pctrank(_roc6); _pr12 = _pctrank(_mom12)
    _leader_pr = pd.concat([_pr6, _pr12], axis=1).max(axis=1)      # [P] union of momentum scans
    _off_high = _num('pct_off_52w_high'); _pct52 = _num('pct_52w_high')
    _is_52w = _num('is_52w_high'); _rel_52 = _num('rel_pct_52w_high')
    _rel_is_52 = _num('rel_is_52w_high'); _base_depth = _num('base_depth_12m')
    _squeeze = _num('sr_m_squeeze_run'); _price5y = _num('price_pct_of_5y_range')
    _prior_run = pd.concat([_roc6, _mom12], axis=1).max(axis=1)    # best prior advance
    def _ramp(x, lo, hi):
        return ((x - lo) / (hi - lo)).clip(0.0, 1.0).fillna(0.0)
    # tightness proxy (all three traders' "tight base"): a volatility squeeze
    # OR a shallow, contained 12m base. [P] for the concept, [R] for the cuts.
    _tight_score = pd.concat([_ramp(_squeeze, 2, 10),
                              _ramp(0.35 - _base_depth, 0.0, 0.35)], axis=1).max(axis=1)

    # ---------- Kullamagi common breakout SETUP ----------
    # [C] leader across momentum scans; [C] large prior advance (>=30%); [P]
    # orderly tightening near rising highs; consolidating, not crashed. The
    # ORH trigger + low-of-day stop within 1 ADR need intraday data (omitted).
    _kk_leader = (_pr6 >= 95) | (_pr12 >= 95)
    _kk_impulse = _prior_run >= 0.30
    _kk_tight = (_squeeze >= 3) | ((_base_depth > 0) & (_base_depth <= 0.35))
    _kk_near = (_off_high >= -0.25) & (_off_high <= -0.005)
    df['arch_kullamagie_breakout'] = (
        _live_tape & _kk_leader & _kk_impulse & _kk_tight & _kk_near
    ).fillna(False).astype(int)
    df['kullamagie_score'] = ((0.30 * _ramp(_leader_pr, 90, 100)
                               + 0.25 * _ramp(_prior_run, 0.30, 1.50)
                               + 0.20 * _tight_score
                               + 0.15 * _ramp(_pct52, 0.75, 1.0)
                               + 0.10 * _ramp(_rel_52, 0.80, 1.0))
                              * df['arch_kullamagie_breakout']).round(3)
    # (weekly panel) leadership ranked WITHIN the listing market (a global rank
    # over-weighted a few high-volatility markets 2-7x), orderly above the 30w
    # MA near highs, liquid in USD. Exceptional: top-5% RS, tight (5-week
    # range <= 10%), >= $5M / week.
    _tier('kullamagie_breakout',
          (_ncol('ts_rs_pct_mkt') >= 90) & (_ncol('ts_dist_hi52') >= 0.90)   # (audit 3) 25% off the high is a base, not a breakout
          & (_ncol('ts_above_ma30') == 1) & (_ncol('ts_dvol26_usd') >= 1e6) & ~_clin_bio_e,   # (audit 3) a clinical binary is not a breakout setup
          (_ncol('ts_rs_pct_mkt') >= 95) & (_ncol('ts_tight5') <= 0.10) & (_ncol('ts_dvol26_usd') >= 5e6),
          elite_metric=_ncol('ts_rs_raw'),
          measured=_ncol('ts_rs_pct_mkt').notna() & _ncol('ts_dist_hi52').notna())
    df['kullamagie_score'] = (df['kullamagie_score'] * df['arch_kullamagie_breakout']).round(3)

    # ---------- Weinstein Stage 2A / early Stage 2 SETUP ----------
    # [C] price advancing above its long trend into little overhead resistance
    # (near 52w/all-time high) with strengthening relative strength; NOT
    # requiring MRS>0 (improving RS below zero is allowed). [P] 30-week MA
    # slope unavailable -> proxied by 12m momentum>0 and upper 5y-range.
    _st2_trend = (_mom12 > 0) & (_price5y >= 0.55)
    _st2_rs = (_rel_52 >= 0.80) | (_rel_is_52 == 1)
    _st2_overhead = (_off_high >= -0.10) | (_is_52w == 1)
    _not_st4 = _mom12 > -0.05
    df['arch_weinstein_stage2'] = (
        _live_tape & _st2_trend & _st2_rs & _st2_overhead & _not_st4
    ).fillna(False).astype(int)
    df['weinstein_score'] = ((0.30 * _ramp(_price5y, 0.55, 1.0)
                              + 0.30 * _ramp(_rel_52, 0.80, 1.0)
                              + 0.25 * _ramp(_pct52, 0.85, 1.0)
                              + 0.15 * _ramp(_mom12, 0.0, 0.60))
                             * df['arch_weinstein_stage2']).round(3)
    # (weekly panel) Stage 2 MEASURED — price above a RISING 30-week MA with
    # positive Mansfield RS vs the local index — instead of 12m-momentum and
    # 5y-range proxies. Exceptional = Stage 2A: the MA has only just turned up
    # and RS just crossed zero or breakout volume doubled.
    # Stage 2 spans the whole advance; Weinstein's buy point is EARLY Stage 2,
    # so the core also needs little overhead (within 10% of the 52w high) and
    # not an already-extended run (52w return <= +100%).
    _tier('weinstein_stage2',
          (_ncol('ts_weinstein_stage') == 2) & (_ncol('ts_above_ma30') == 1) & (_ncol('ts_mrs') > 0)
          & (_ncol('ts_dist_hi52') >= 0.90) & (_ncol('ts_r52') <= 1.0)
          & ~(_ncol('ts_dist_hi260') < 0.90)         # (audit 3) little OVERHEAD: near the 5-year high too, where measured
          & ~_clin_bio_e,                           # (audit 3) a clinical binary is not a Stage 2 setup
          (_ncol('ts_ma30_slope13') < 0.03) & ((_ncol('ts_mrs_13ago') <= 0) | (_ncol('ts_vol_spike4') >= 2)),
          elite_metric=_ncol('ts_mrs'),
          measured=_ncol('ts_weinstein_stage').notna())
    df['weinstein_score'] = (df['weinstein_score'] * df['arch_weinstein_stage2']).round(3)

    # ---------- O'Neil CAN SLIM SETUP ----------
    # [C] C: strong/accelerating current earnings; [C] A: durable annual
    # growth + ROE>=~17% (roce proxy); [C] N: new price high; [C] L: RS leader
    # (percentile>=80). I/M/S (institutional sponsorship trend, market
    # follow-through regime, breakout volume) need ownership/index/volume
    # feeds not persisted here — noted, not faked.
    _eps_streak = _num('eps_yoy_growth_streak_q'); _eps_pos = _num('eps_yoy_positive_share')
    _revg = _num('rev_yoy'); _roce_v = _num('roce')
    _accel = ((_num('op_margin_delta_yoy') > 0) | (_num('ebit_growth_yoy') > _revg)).fillna(False)
    _on_C = (_eps_streak >= 2) | (_revg >= 0.20)
    # (deep-audit) the "A" roce leg was satisfiable by a ONE-OFF-inflated roce on a
    # deep operating loss (DDEJF op-125%/roce0.33, KURA op-350%/roce0.59) — growth
    # "off a negative base", the opposite of CANSLIM's defining "C" (strong CURRENT
    # earnings). Guard the roce with ~_roce_oneoff_suspect.
    _on_A = (_roce_v >= 0.15) & ~_roce_oneoff_suspect & ((_eps_pos >= 0.75) | (_revg >= 0.10))
    _on_N = (_off_high >= -0.15) | (_is_52w == 1)
    # (R10) a high RS PERCENTILE in a broadly-down tape can flag a name that is
    # itself DOWN on both horizons as a "leader". Require genuine positive
    # recent momentum on at least one horizon for the leadership claim.
    _on_L = (_leader_pr >= 80) & (_prior_run > 0)
    df['arch_oneil_canslim'] = (
        _live_tape & _on_C & _on_A & _on_N & _on_L
        & (s('op_margin', np.nan) > 0)   # (deep-audit) a real earnings LEADER is profitable NOW — closes the loss-maker leak (CFOO op-143%, ASMB op-47%) that revenue-growth-off-a-negative-base admitted.
    ).fillna(False).astype(int)
    df['oneil_score'] = ((0.30 * _ramp(_revg, 0.10, 0.50)
                          + 0.20 * _ramp(_roce_v, 0.10, 0.35)
                          + 0.20 * _ramp(_leader_pr, 80, 100)
                          + 0.15 * _ramp(_pct52, 0.85, 1.0)
                          + 0.15 * _accel.astype(float))
                         * df['arch_oneil_canslim']).round(3)
    # (quarterly panel + weekly panel) the real "C": latest-quarter EPS up
    # >= 25% YoY (date-matched); "L": RS top 20% of the listing market; "N":
    # within 15% of the 52w high. Exceptional: EPS accelerating, a consistent
    # EPS record, and "M" — a healthy market (>= half of it above its 30w MA).
    _tier('oneil_canslim',
          (_ncol('fqx_eps_q_yoy') >= 0.25) & (_ncol('ts_rs_pct_mkt') >= 80) & (_ncol('ts_dist_hi52') >= 0.85)
          & ~(_ncol('fqx_eps_accel') < 0)            # (audit 3) C: the latest quarter not DECELERATING (two-quarter shape)
          & ~(_ncol('fq_disc_ops_share') > 0.20)     # (audit 3) continuing operations (O'Neil excludes non-recurring items)
          & (_roce_v >= 0.15) & ~_roce_oneoff_suspect   # (audit 3) A in the core: annual returns >= 15%
          & ~(_ncol('fg_ni_ps_3y') < 0.953)            # (financial-growth) A: 3-year NI per share >= +95% (1.25^3 - 1 = 25%/yr) where measured
          & ~_clin_bio_e,                           # (audit 3) a clinical binary is not an earnings leader
          (_ncol('fqx_eps_accel') > 0) & (_ncol('fqx_eps_pos_share_8') >= 0.75) & (_ncol('ts_mkt_breadth30') >= 0.5),
          elite_metric=_ncol('fqx_eps_q_yoy'),
          measured=_ncol('fqx_eps_q_yoy').notna() & _ncol('ts_rs_pct_mkt').notna())
    df['oneil_score'] = (df['oneil_score'] * df['arch_oneil_canslim']).round(3)

    # ---------- Peter Cundill deep value ----------
    # His published six-point checklist (There's Always Something to Do). A
    # Graham-lineage, balance-sheet-first, contrarian global value discipline:
    # bought near ~2/3 of NAV with a hard margin of safety, patient, catalyst-
    # agnostic. All six points below are his stated "MUST"s [C]; the
    # "preferably" refinements become the quality score. Financials are NOT
    # excluded (Cundill bought insurers/banks on book value) but are exempted
    # from the operating-debt test, whose leverage is structural for them.
    _cpb = _num('pb'); _coff = _num('pct_off_52w_high'); _c5y = _num('price_pct_of_5y_range')
    _cpe = _num('p_e'); _croce = _num('roce'); _ceb = _num('ebitda_ttm')
    _cdiv = _num('dividend_yield'); _cnde = _num('net_debt_ebitda'); _cd2e = _num('debt_to_equity')
    _cncash = _num('net_cash_pct_mcap'); _cncav = _num('ncav_pct_mcap')
    _cgraham = _num('graham_net_net_flag'); _ceps_pos = _num('eps_yoy_positive_share')
    # (1) price < book value  [C]
    _c1 = (_cpb > 0) & (_cpb < 1.0)
    # (2) price < half the former high, or near an all-time low  [C]
    # (endpoint matrix) "the former high" read exactly: the 5-year weekly
    # high (ts_dist_hi260 <= 0.5), plus the panel-first 52w lens; the snapshot
    # 52w / 5y-range proxies stay as fallbacks.
    # (audit 3) "half the former high" = the 5-year weekly high where the
    # panel has it; the 52w / 5y-range snapshot lenses only where it is absent
    _c2 = ((_ts_hi260 <= 0.50)
           | (_ts_hi260.isna() & ((_coff <= -0.50) | (_c5y <= 0.20) | (_ts_dd52 <= -0.50))))
    # (3) P/E < min(10, 1/LT-corporate-bond-rate) — the earnings yield must
    #     also clear the bond yield [C]. In a low-rate regime 10 binds; in a
    #     high-rate regime 1/rate binds (r=12% -> P/E<8.3). Rate is a research
    #     parameter [R]; set to a current LT investment-grade corporate yield.
    _LT_CORP_BOND_RATE = 0.055
    _cundill_pe_cap = min(10.0, 1.0 / _LT_CORP_BOND_RATE)
    _c3 = (_cpe > 0) & (_cpe <= _cundill_pe_cap)
    # (4) profitable; preferably no deficits over 5y  [C]
    # (audit 3) the 5-year no-deficit test read GLOBALLY: the EDGAR EPS share,
    # else the statement-history share of NI-positive years, else the
    # through-cycle op-income count
    # eps_yoy_positive_share / fmp_st_ni_up_share_5 count GROWTH years, not
    # profitable ones: the no-deficit share is the through-cycle op-income count
    _c_nodef = (_ncol('tc_opinc_pos') / _ncol('tc_years').where(_ncol('tc_years') >= 3))
    _c4 = ((_croce > 0) | (_ceb > 0)) & ((_c_nodef >= 0.6) | _c_nodef.isna())
    # (5) paying dividends  [C]
    _c5 = _cdiv > 0
    # (6) debt judiciously employed, room to expand  [C] (financials exempt)
    _c6 = (((_cnde < 2.5) | (_cd2e < 1.0) | (_cncash > 0)
            | (_cnde.isna() & _cd2e.isna() & _cncash.isna()))   # (audit 4) unmeasured debt passes (the 99-fill made it fail)
           | is_financial)
    df['arch_cundill_deep_value'] = (
        _c1 & _c2 & _c3 & _c4 & _c5 & _c6
    ).fillna(False).astype(int)
    # Score = depth of discount to book (his 2/3-NAV sweet spot ~0.67),
    # net-net bonus, closeness to lows, cheapness, no-deficit earnings,
    # dividend, and balance-sheet strength (room to expand debt).
    _c_netnet = ((_cncav >= 1.0) | (_cgraham > 0)).fillna(False)
    # "preferably INCREASED earnings over 5yr" (criterion 4 refinement):
    # a positive EPS-growth streak captures the rising trend, distinct from
    # the no-deficit share already in the gate.
    _c_eps_rising = _ramp(_num('eps_yoy_growth_streak_q'), 1, 4)
    df['cundill_score'] = ((0.22 * _ramp(1.0 - _cpb, 0.20, 0.60)   # discount to book
                            + 0.14 * _c_netnet.astype(float)        # net-net (NWC-LTD)
                            + 0.13 * _ramp(0.30 - _c5y, 0.0, 0.30)  # near all-time low
                            + 0.13 * _ramp(_cundill_pe_cap - _cpe, 0.0, 8.0)  # cheapness vs cap
                            + 0.10 * _ramp(_c_nodef, 0.6, 1.0)      # no deficits
                            + 0.10 * _c_eps_rising                  # increasing earnings
                            + 0.08 * (_cdiv > 0).astype(float)      # dividend
                            + 0.10 * _ramp(_cncash, 0.0, 0.5))      # balance-sheet strength
                           * df['arch_cundill_deep_value']).round(3)

    low_sbc_wolf = _soft_ok_below('sbc_pct_revenue', 0.15)   # Wolf dings excess SBC
    low_sbc_liger = _soft_ok_below('sbc_pct_revenue', 0.10)  # Liger flags diluters
    # `nde` defaults to 99 when net_debt_ebitda is missing (37% of names), so
    # a `nde <= X` gate silently EXCLUDES clean names whose debt just wasn't
    # fetched — including 1,652 names that are clearly net cash. Treat a name
    # as clean-balance-sheet if EITHER a real low nde OR a real net-cash %.
    def _clean_bs(nde_max):
        return ((ebitda_ttm_v > 0) & (nde <= nde_max)) | (net_cash_pct_c >= 0.20)
    # rev_yoy defaults to 0, so `rev_yoy >= 0` passes 15k missing-growth rows.
    # Require the field actually present for "not shrinking" gates.
    rev_present = (pd.to_numeric(df['rev_yoy'], errors='coerce').notna()
                   if 'rev_yoy' in df.columns else pd.Series(False, index=df.index))
    # Wolf's most-cited discipline: a cheap ENTRY multiple ceiling. Every
    # verified winner entered <12x EV/EBITDA or <20x P/E (NCI 9x/11pe,
    # ZOMD 6.2x/8pe); he SOLD KITS at 175pe on the same rule.
    wolf_cheap_entry = (((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)) |
                        ((pe_w > 0) & (pe_w < 20.0)))
    # Neglected-microcap sectors Liger avoids (binary-outcome capital sinks).
    _ind = df['industry'].fillna('').astype(str).str.lower() if 'industry' in df.columns else pd.Series('', index=df.index)
    _nm = df['name'].fillna('').astype(str).str.lower() if 'name' in df.columns else pd.Series('', index=df.index)
    liger_sector_ok = ~_ind.str.contains(
        'biotech|pharmaceutical|mining|metals|coal|gold|silver|crypto|blockchain',
        regex=True)

    # ---------- Wolf of Oakville family ----------
    # ~105%/yr on 19 picks since 2023. Doctrine = the "Wolf Trifecta":
    # DOUBLE-DIGIT revenue growth + improving margins + operating leverage
    # (opex growing slower than sales, i.e. EBITDA outgrowing revenue),
    # bought at an undemanding multiple. (Refined: growth floor 50%->15%;
    # added the operating-leverage leg and the cheap-entry ceiling he lives
    # by; SBC guard.)
    # (endpoint matrix, PROXY) operating leverage measured directly on the
    # date-matched TTM: incremental EBIT margin >= 20% AND EBIT growing faster
    # than revenue (opex growing slower than sales — the Trifecta's own words).
    _wolf_oplev_ttm = ((_fqx_inc >= 0.20)
                       & (_ncol('fqx_ebit_ttm_g') > _ncol('fq_rev_growth'))).fillna(False)
    df['arch_wolf_trifecta'] = (
        is_operating &                              # (R1b) exclude financials/REITs
        (mcap >= 10e6) & (mcap <= 300e6) &
        (_num('revenue_ttm_usd') >= 10e6) &         # real revenue base (microcap-appropriate floor)
        (rev_yoy_c >= 0.15) &                       # "double-digit", not 50%
        # (audit 3) the TRIFECTA is three ANDs: growth AND margins up (>= 2pp
        # or an incremental margin above the current) AND leverage (EBIT
        # outgrowing sales on the TTM, or the seasonality-robust lens)
        ((ebitda_margin_delta >= 0.02) | (_ncol('op_margin_delta_yoy') >= 0.02)
         | (_fqx_inc > s('op_margin', np.nan)).fillna(False)) &
        (season_robust | _wolf_oplev_ttm) &
        ~(_num('shares_yoy') > 0.05) &              # (audit 3) the doc's equity-dilution veto
        _clean_bs(1.0) & _ev_sane &                 # (audit 3) the doc's balance-sheet table; the EV sanity band on the multiples
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &
        _not_melting &                              # (tail) survivability — now cash-on-cash-aware + improvement-lenient; a cash-generative or inflecting name is NOT barred here, only genuine ice cubes (per user: demote via melt_demotion, don't bar).
        (ev_sales_v > 0) & (ev_sales_v < 3.0) &
        wolf_cheap_entry &
        low_sbc_wolf
    ).fillna(False).astype(int)

    # B — Turnaround: loss-maker crossing into the black (incl. the OCF-
    # turns-positive shape, e.g. SBBC) while still GROWING (he avoided the
    # flat/declining Thermal Energy). Cheap-entry ceiling added.
    df['arch_wolf_turnaround'] = (
        (mcap >= 10e6) & (mcap <= 200e6) &
        (_num('revenue_ttm_usd') >= 10e6) &         # (tail) real revenue base — not a $2.8M base-effect shell (CTO.SI rev+2626%)
        # (audit 3) a CFO / FCF first positive (a working-capital swing) counts
        # only beside a P&L turn (EBITDA / EPS / TTM EBIT)
        ((ebitda_first_pos > 0) | (ni_first_pos > 0) |
         (((cfo_first_pos > 0) | (fcf_first_pos > 0) | (cfo_inflection > 0) | (fcf_inflection > 0))
          & ((ebitda_inflection > 0) | (_ncol('fqx_eps_turned') == 1) | (_ncol('bs_ebit_turned') == 1) | (ebitda_first_pos > 0))) |
         ((ebitda_inflection > 0) & oper_lev_any) |
         # (endpoint matrix, PROXY) the crossing into the black, DATED on the
         # quarterly TTM series (source: "first profitable quarter post-
         # turnaround") — alongside the annual first-positive flags
         # (same-period YoY EPS turn and the 2-year TTM EBIT turn; not the
         # one-quarter fmp_dyn turned flags, which are seasonality-confounded)
         (_ncol('fqx_eps_turned') == 1) |
         (_ncol('bs_ebit_turned') == 1)) &
        # a genuine TURNAROUND is a low-margin business crossing to black, NOT an
        # already-solidly-profitable compounder whose CFO merely ticked up. Cap
        # the current operating margin so established earners fall out; the LOWER
        # bound keeps it a name approaching black, not a deep loss-maker (op-65%).
        (s('op_margin', np.nan) < 0.15) & _op_viable(-0.30) &   # (gate-audit) raw op>-0.30 barred 230 impairment-hit deep turnarounds; _op_viable admits a writedown-hit name that is cash-healthy (the WW pattern) while keeping the "not an established earner" upper bound
        (emd_c >= 0.0) &
        # (audit 3) growing (present) OR a COST-CUT turn (the source's own
        # evidence): op margin up >= 3pp on gross profit held
        (((rev_yoy_c >= 0.0) & rev_present)
         | ((_ncol('op_margin_delta_yoy') >= 0.03) & ~(_num('gross_profit_yoy') < -0.05))) &
        wolf_cheap_entry

        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)

    # C — Value + catalyst (repurposed). He is NOT a net-net investor; his
    # real shape is a growing, cash-generative microcap with a fortress
    # balance sheet at a cheap FCF yield (Progressive Planet: ~12% FCF yld,
    # ~$32M cap, growing). Lowered net-cash floor 0.50->0.20; added growth
    # + positive CFO; FCF-yield as the cheapness catalyst.
    df['arch_wolf_value_catalyst'] = (
        (mcap > 0) & (mcap < 200e6) &
        ((net_cash_pct_c >= 0.20) | (cash_gt_ev > 0) | (ncav_pct >= 0.50)
         | ((fcf_yield >= 0.10) & (nde <= 1.5))) &   # (gate-audit) net-cash is an ALTERNATIVE strengthener, not mandatory: a growing, CFO-positive microcap cheap on a fat FCF yield with a sound balance sheet is the thesis even without a net-cash fortress (195 were excluded solely for lacking net cash)
        (rev_yoy_c >= 0.10) & rev_present &         # (audit 3) GROWING is a present double-digit print (the composite is not)
        _ev_sane &                                  # (audit 3) the EV sanity band on the EV/EBITDA lens
        (cfo_ttm_v > 0) &
        _not_melting &                              # (tail) survivability — cash-on-cash-aware + improvement-lenient (per user: demote melters via melt_demotion, don't bar cash-generative/inflecting names).
        ((fcf_yield >= 0.08) |
         ((ev_ebitda_v > 0) & (ev_ebitda_v < 6.0)))

        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)
    # (audit 3) the CATALYST, surfaced where any dated feed carries it: a
    # tender / deal / 13D within the year, or a dividend raise streak
    df['wolf_value_catalyst_dated_flag'] = ((df['arch_wolf_value_catalyst'] == 1) & (
        (_evt_age_days('evt_tender_date') <= 365) | (_evt_age_days('evt_merger_proxy_date') <= 365)
        | (_evt_age_days('evt_sc13d_date') <= 365) | (_ncol('evt_div_raise_streak') >= 1)).fillna(False)).astype(int)

    # D — Emerging-sector profitability (his cautious cannabis bets). His one
    # such pick (Simply Solventless/HASH) blew up -57% on accounting + cash
    # problems, so gate hard on POSITIVE OPERATING CASH FLOW (not just EBITDA)
    # and clean SBC — exactly what would have excluded HASH.
    # (inflection-audit) DROP 'tobacco': it dragged in mature Big Tobacco majors
    # (Gudang Garam, Sampoerna, Japan Tobacco, Scandinavian Tobacco), the exact
    # mature/declining population this "cautious cannabis bets" thesis avoids.
    # (audit 3) the population from the INDUSTRY label (Canadian LPs sit under
    # "Drug Manufacturers - Specialty & Generic" with cannabis in the name), not
    # a bare name string that catches hemp foods and textiles
    _emerging = (_is_cannabis | _ind.str.contains('psychedelic', regex=False)).fillna(False)
    # The HASH-lesson discipline that MATTERS is the hard positive-CFO + clean-SBC
    # gate; the deep-value price cut (pe<10/EV<6) is too strict for a nascent
    # grower and left the archetype empty once mature tobacco was removed. Keep
    # the cash discipline, widen the cheapness to a reasonable-multiple band.
    df['arch_wolf_emerging'] = (
        _emerging &
        (cfo_ttm_v > 0) &
        (rev_yoy_c >= 0.10) & rev_present &         # (audit 3) GROWING (the examples' leg), not a shrinking CFO-positive name
        _no_rsplit_yoy &                            # (audit 3) no reverse split (data validity)
        low_sbc_wolf &
        (((pe_w > 0) & (pe_w < 20.0)) | ((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)))
    ).fillna(False).astype(int)
    # CANNABIS OPERATOR (user 2026-10-02): the cannabis population as its own
    # archetype — every operating cannabis business with revenue (growers, MSOs,
    # LPs, CBD brands; cannabis REITs and lenders stay out via is_operating).
    # No quality gate: the sheet is the population, ranked by its spirit score
    # on what separates the survivors in this industry — revenue growth, cash
    # from operations, operating margin, net cash, and a low EV/sales.
    _cann_rev = s('revenue_ttm', np.nan)
    df['arch_cannabis_operator'] = (
        _is_cannabis & is_operating & (mcap > 0) & (_cann_rev > 0)
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('cannabis_operator', []).extend([
        (rev_yoy_c.where(rev_present), 1), (s('cfo_ttm', np.nan) / _cann_rev.where(_cann_rev > 0), 1),
        (s('op_margin', np.nan), 1), (s('net_cash_pct_mcap', np.nan), 1),
        (s('ev_sales', np.nan).where(s('ev_sales', np.nan) > 0), -1)])

    # E — "Seal of Approval" fresh trigger: an earnings inflection bought on
    # a post-earnings dip. Loosened the drawdown gate (he buys before the
    # full run) and added his valuation discipline (the KITS lesson).
    # (endpoint matrix, PROXY+EXC) momentum on the weekly total-return panel
    # (ts_r52), the quote-time 12m figure as fallback. The thesis's POST-
    # EARNINGS DIP (a negative reaction on a beat) is observable only where the
    # earnings calendar covers the name, so it RANKS members in the spirit
    # score (with the beat record and EPS acceleration) instead of gating.
    _mom_w = _ncol('ts_r52').fillna(mom12)
    # (audit 3) the SEAL is an EARNINGS inflection: a first-positive print, a
    # shock-sized margin move or a dated EPS turn — not the near-universal
    # inflection_print (any +10% revenue year)
    _seal_inflect = (_first_pos_any | margin_shock_any | (_ncol('fqx_eps_turned') == 1)
                     | (_ncol('bs_ebit_turned') == 1)).fillna(False)
    df['arch_wolf_seal'] = (
        (mcap > 0) & (mcap < 500e6) &
        _seal_inflect &
        (_mom_w >= 0.10) &
        not_too_deep_any(0.50) &
        _not_melting &   # (deep-audit) the only wolf gate with NO melting floor — inflection_print (a one-off EBITDA print) admitted confirmed op-loss+FCF-burn shells: 0128.HK op-46%/fcf-, CTO.SI op-65% on a rev+2626% base. Trims ~92 melters, keeps genuine first-positive inflections.
        (((ev_ebitda_v > 0) & (ev_ebitda_v < 15.0)) | ((pe_w > 0) & (pe_w < 25.0)))

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)
    _SPIRITED.append('wolf_seal')

    # F — NEW: Wolf Compounder — his signature winner (NCI/ZOMD/KITS-at-entry):
    # a sustained, ACCELERATING grower bought at a single-digit/low-teens
    # multiple, margins expanding, cash-positive, low dilution. Isolates the
    # multi-quarter streak the single-period trifecta gate can miss.
    df['arch_wolf_compounder'] = (
        (mcap >= 10e6) & (mcap <= 150e6) &
        (_num('revenue_ttm_usd') >= 10e6) &         # real revenue base (base-effect guard: Dong A Eltek +234%)
        (rev_yoy_c >= 0.25) & (rev_yoy_c <= 1.5) &  # accelerating streak, NOT a base-effect explosion
        (rev_accel > 0) &
        ~(_ncol('rev_yoy_streak_q_eff').fillna(_ncol('fq_rev_yoy_streak_qeq')) < 3) &   # (audit 3) a MULTI-QUARTER streak (>= 3) where the quarterly record measures it, not one accelerating print
        _op_viable(0) &              # profitable compounder (impairment-robust), not Bengal Tea op_margin -160%
        _roce_now_ok &                              # (fresh) a compounder does not destroy capital (SOGP roce-96%)
        ~(_num('shares_yoy') > 0.05) &              # (audit 3) low dilution means <= 5% (the doc's "flat or shrinking"), not 19%
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &
        (season_robust | _wolf_oplev_ttm) &         # (endpoint matrix) + the TTM operating-leverage measure; raw-sequential never fires (seasonality rule)
        ((ebitda_margin_delta > 0) | (_ncol('op_margin_delta_yoy') > 0)
         | (_fqx_inc > s('op_margin', np.nan)).fillna(False)) &   # margins expanding (the header's leg)
        (((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)) |
         ((pe_w > 0) & (pe_w < 20.0))) &
        low_sbc_wolf
        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)
    # (endpoint matrix, EXC) a beat streak + accelerating quarterly EPS rank
    # the members (spirit score), never a gate
    _SPIRITED.append('wolf_compounder')

    # ---------- Liger Cub / Byron Street family ----------
    # Long-only public-information arbitrage in NEGLECTED microcaps. His edge
    # is OSINT (unscreenable); these capture the financial preconditions his
    # documented longs (RCMT, VTSI) shared: neglect (<=3-4 analysts), no
    # dilution, survivable balance sheet, near-breakeven-or-better cash flow
    # (this gate correctly REJECTS the WATT cash-burner, whose edge was pure
    # OSINT), depressed/off-highs, and NOT mining/biotech/crypto.
    # (endpoint matrix, PROXY) neglect OBSERVED: the FMP estimate-coverage
    # count (sent_n_analysts) is the primary lens where it exists, the Yahoo /
    # pew count the fallback; missing everywhere still reads as neglected.
    _liger_cov = _ncol('sent_n_analysts').fillna(_ncol('n_analysts')).fillna(_ncol('n_analysts_pew')).fillna(0.0)
    df['arch_liger_asset_backed'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 400e6) &
        (net_cash_pct_c >= 0.20) & _netcash_not_contradicted &  # GENUINE net cash (nde not materially positive)
        ((pb > 0) & (pb < 3.0)) &                   # "asset-backed" needs a real book anchor (WINE.L pb 75 is not asset-backed)
        # (audit 3) ASSET-BACKED: the book or the cash carries the cap — net cash
        # >= 50% of mcap, NCAV >= 80%, or at/below tangible book
        ((net_cash_pct_c >= 0.50) | (ncav_pct >= 0.80) | ((p_tb > 0) & (p_tb <= 1.0))) &
        ~(_ncol('fq_shares_yoy') > 0.03) &          # (audit 3) dilution limited on the quarterly count (SBC alone misses placings)
        # (audit 3) neglect OBSERVED where any coverage field exists; a name
        # with no coverage field at all is neglected only at sub-$500M scale
        ((_ncol('sent_n_analysts').fillna(_ncol('n_analysts')).fillna(_ncol('n_analysts_pew')) <= 4)
         | (_ncol('sent_n_analysts').isna() & _ncol('n_analysts').isna() & _ncol('n_analysts_pew').isna() & (mcap < 500e6))) &
        ((op_margin_v >= -0.05) | (ebitda_margin >= 0.0)) &
        low_sbc_liger &
        liger_sector_ok
    ).fillna(False).astype(int)

    # Quiet inflection the market hasn't processed. His signal is
    # ACCELERATION (RCMT consolidated +14.7% but the segment far faster), not
    # a high absolute growth level — so the growth gate is now accel-aware.
    # Leverage loosened 1.0->1.5 (RCMT ran ~1.3-1.5x) with the ebitda>0 guard.
    df['arch_liger_lagging_inflect'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        _roce_now_ok &                              # (R4) current returns not negative (Genie Music roce -22%)
        (rev_yoy_c > 0) & (rev_yoy_c <= 1.0) &      # (R5) not declining; upper cap drops inorganic M&A pops (Newlat +130%)
        (((rev_yoy_c >= 0.10) & (rev_accel > 0)) | (rev_yoy_c >= 0.15)) &   # (audit 3) GROWTH...
        # (audit 3) ...AND MARGIN: incremental EBIT margin above the historical
        # average (the author's phrase) or a shock-sized margin move; where
        # neither is measurable the seasonality-robust lens stands in
        ((_fqx_inc > _ncol('tc_med_opm').fillna(op_margin_lindy)).fillna(False) | margin_shock_any
         | (_fqx_inc.isna() & season_robust)) &
        # (gate audit #3) cash_conversion reads falsely positive when CFO
        # and EBITDA are BOTH negative — trust it only over positive EBITDA
        (((cash_conv_w >= 0.80) & (ebitda_ttm_v > 0)) | (fcf_margin_w > 0)) &
        _clean_bs(1.5) &                            # clean b/s (nde OR net-cash)
        (~(_liger_cov > 4)) &                         # (twosided) MISSING coverage = MOST neglected (the thesis); observed coverage first (endpoint matrix)
        low_sbc_liger &
        liger_sector_ok &
        (flat_or_down | beaten_down_any(0.30)     # presence-aware lag/drawdown
         | (_num('bs_is_base') == 1).fillna(False)   # ...or a two-year flat base (weekly panel)
         # (endpoint matrix, PROXY) the lag MEASURED against the advance: TTM
         # sales grew >= 15% more than the 52-week total return (1-year coil),
         # or >= 20% more over the two-year base — "the market has not
         # processed the inflection" even when the price itself rose
         | ((np.log1p(_ncol('fq_rev_growth')) - np.log1p(_ts_r52)) >= np.log(1.15)).fillna(False)
         | (_num('bs_coil_rev') >= np.log(1.20)).fillna(False))
    ).fillna(False).astype(int)

    # NEW: Liger Neglected Survivor — the single best proxy for his edge:
    # neglected + financially survivable (no dilution) + cheap, with an early
    # inflection and room to re-rate on a material catalyst. RCMT & VTSI pass;
    # WATT is intentionally rejected by the near-breakeven gate.
    df['arch_liger_neglected_survivor'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap >= 5e6) & (mcap <= 400e6) &           # (deep-audit) floor 20e6->5e6: it was binding at exactly $20.005M, cutting the sub-$20M nano cohort this "neglected survivor, 0 analysts ideally" thesis MOST targets (RCMT/VTSI were tiny). Both siblings have no such floor; 5e6 keeps a shell guard.
        (~(_liger_cov > 3)) &                         # (audit 3) neglect read sent -> Yahoo -> pew like the siblings; missing = neglected at this cap
        (((net_cash_pct_c >= 0.15) & _netcash_not_contradicted) | ((ebitda_ttm_v > 0) & (nde <= 1.5))) &
        ((fcf_margin_w >= 0.0) | (op_margin_v >= -0.02)) &
        # (audit 3) RUNWAY TO THE CATALYST for a burner: cash / annual FCF burn
        # >= 2 years where the quarterly statements measure it
        ~((_ncol('fq_fcf') < 0) & ((_ncol('fq_cash_sti') / (-_ncol('fq_fcf'))) < 2.0)) &
        ~(_ncol('fq_shares_yoy') > 0.03) & _no_rsplit_yoy &   # (audit 3) no dilution, no reverse split (the toxic-financing tell)
        low_sbc_liger &
        (beaten_down_any(0.30) | ((ev_sales_v > 0) & (ev_sales_v <= 2.0))) &
        ((rev_accel > 0) | season_robust) &
        liger_sector_ok
    ).fillna(False).astype(int)
    # (tighten) "early inflection" must be REAL: a first-positive print, EPS
    # turning positive, or incremental EBIT margin >= 20% (not oper_lev_any's
    # sequential drift). Exceptional: observed coverage <= 1, TTM EBIT +30%.
    _tier('liger_neglected_survivor',
          (ebitda_first_pos > 0) | (ni_first_pos > 0) | (_ncol('fqx_eps_turned') == 1)
          | (_ncol('fqx_inc_ebit_margin') >= 0.20),
          (_ncol('sent_n_analysts') <= 1) & (_ncol('fqx_ebit_ttm_g') >= 0.30),   # OBSERVED coverage <= 1
          elite_metric=_ncol('fqx_ebit_ttm_g'))

    # ---------- Oak Bloke special situations ----------
    # Every Oak winner pairs cheapness with a CASH-RICH, cash-generative
    # balance sheet; every trap (Belluscura -96.6%) was a cash-burner needing
    # external capital. So each screen now carries a solvency/cash gate.
    #
    # Resource leverage — low-cost producer in the bottom half of the cost
    # curve, bought NET-CASH on price weakness (Thungela: ~75% of price was
    # cash, P/E<1). Added cash floor + high-margin (cost-curve) proxy +
    # bought-on-weakness; loosened EV/EBITDA to 8 so the very cheapest qualify.
    # (audit 3) a PRODUCER of materials (metals, uranium, oil & gas, coal),
    # not a chemicals / packaging / refining / services name under the label
    _producer_ind = _ind_all.str.contains(
        r'mining|coal|uranium|oil & gas e&p|oil & gas exploration|gold|silver|copper|lithium|steel|aluminum|metals', regex=True)
    _DEMOTED.setdefault('oak_resource_leverage', []).extend([(_ncol('shares_growth_3y'), -1)])
    df['arch_oak_resource_leverage'] = (
        sector.isin({'Materials', 'Energy'}) & _producer_ind &
        (ev_ebitda_v > 0) & (ev_ebitda_v < 8.0) & _ev_sane &
        _clean_bs(1.5) &
        (net_cash_pct_c >= 0.20) &                  # NET-cash survivability (not gross cash)
        (ebitda_margin >= 0.25) &                   # cost-curve proxy
        ~((_ncol('tc_years') >= 5) & (_ncol('tc_min_opm') < 0)) &   # (audit 3) the COST POSITION read through the cycle: never lost money at the trough where >= 5 years are on file
        ((fcf_yield >= 0.08) | (_ncol('robust_cash_yield') >= 0.08) |
         (_ncol('owner_earnings_yield') >= 0.08)) &
        beaten_down_any(0.20)                       # bought on weakness (any lens)
    ).fillna(False).astype(int)

    # Deleveraging/yield — heavy FCF, moderate debt being paid down (rising
    # EBITDA mechanically cuts the ratio = his actual thesis), material
    # shareholder return. Yield floor raised to DEC-scale; solvency soft gate.
    df['arch_oak_deleveraging'] = (
        is_operating &                              # (R1b) exclude financials/REITs (mandatory-leverage biz)
        _roce_now_ok & _op_viable(0) &  # returns floor (impairment-robust): a deleveraging compounder earns real operating profit / cash (NIC Autotec p/e 169 out)
        ((fcf_yield >= 0.10) | (_ncol('robust_cash_yield') >= 0.10) |
         (_ncol('owner_earnings_yield') >= 0.10)) &
        (ebitda_ttm_v > 0) & (nde >= 1.0) & (nde <= 3.0) &
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0) | season_robust) &   # leverage trajectory (seasonality-robust; a raw sequential uptick is not a falling ratio)
        ~(_ncol('fq_netdebt_change_pct_assets') > 0) &   # (audit 3) NET DEBT actually not rising where the quarterly balance sheets measure it (a dividend is not deleveraging)
        ~(_ncol('fq_capex_to_da') > 1.2) &               # (audit 3) low growth capex (the prose leg)
        ~(_ncol('shares_yoy') > 0.02) &   # de-levering via FCF, not equity issuance — an equity-raiser is off-thesis
        # (gate-audit) the 6% SHAREHOLDER-PAYOUT floor contradicted the thesis
        # (cash routes to LENDERS, not a fat dividend). Replaced with the
        # thesis-pure DEBT-REDUCTION confirmation: cash actually flowing OUT to
        # capital providers — a negative financing cash flow (debt repayment
        # and/or buyback) OR an actual share-count shrink. (No prior-period debt
        # column exists for a literal falling-nde-YoY; this is the closest
        # available "cash to capital providers" signal, and the rising-EBITDA
        # leg above already confirms the ratio is mechanically falling.)
        ((_ncol('financing_cf_ttm') < 0) | (_ncol('net_buyback_ttm') > 0)
         | (_ncol('shares_yoy') < 0)
         # the literal falling-net-debt PATH from quarterly balance sheets
         # (>= 9 months of consecutive declines, >= 5% of assets, operations-
         # funded) — the prior-period debt evidence the note above lacked
         | (df['fq_deleveraging_flag'] == 1)) &
        _soft_ok_above('interest_coverage', 2.0)
    ).fillna(False).astype(int)

    # Distressed deep value with a hard-asset parachute — crushed price, deep
    # discount to book OR net-net, real cash, still cash-GENERATIVE (the
    # Belluscura gate: positive EBITDA alone isn't enough, require FCF/CFO>0).
    df['arch_oak_deep_value'] = (
        is_operating &                              # (R1b) RE developers (Shimao) / brokers: book & leverage not comparable
        # (audit 3) the crash read on the 5-year weekly high where the panel has
        # it (the stale snapshot 5y-average lens only where it does not)
        (((_ts_hi260 <= 0.50) & ~(_dd52 > -0.25)) | (_ts_hi260.isna() & beaten_down_any(0.50))) &   # (the 52w lens must not contradict: a name back within 25% of its 52w high has recovered)
        # (audit 3) the author's discount legs: P/B < 0.5, P/S < 0.3 or a net-net
        # (the multiples composite is not "price / assets very low")
        (((pb > 0) & (pb < 0.5)) | ((s('p_s', np.nan) > 0) & (s('p_s', np.nan) < 0.3)) | (ncav_pct >= 0.5)) &
        (cash_pct_mcap_v >= 0.20) &
        ~(_ncol('shares_yoy') > 0.05) & _no_rsplit_yoy &   # (audit 3) "repeated dilution" is the reject; a reverse split too
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &
        _not_melting &   # (deep-audit) a one-off FCF/CFO print defeats the Belluscura burner-guard: RFT.AX roce-24%, UBI.PA op-149%/roce-69%, RENT roce-51% passed while operating-melting. Sibling oak_order_conversion carries _not_melting; add it here.
        _soft_ok_above('interest_coverage', 1.5)
    ).fillna(False).astype(int)

    # NEW: Oak NAV-discount holdco — his price/NAV<0.7 + covered-yield trusts.
    # PROXY ONLY: for investment vehicles book ~ NAV, so a Financials-sector
    # deep book discount with a high yield. Cannot capture true NAV (marks on
    # unlisted assets) or his dividend-cover >=1.2x test.
    _ptb_nav = _ncol('p_tb')
    # (rank520) narrow to REAL NAV vehicles — closed-end funds, investment
    # trusts, holdcos, asset managers — where book ~ NAV. An operating bank or
    # insurer at 0.7x book is just a cheap financial, NOT a NAV-discount holdco;
    # exclude them so the discount reads against NAV, not against a lending book.
    _nav_vehicle = (_ind_all.str.contains(
        r'asset manag|closed-end|investment trust|holding|capital market|'
        r'\bfund\b|diversified financ|investment compan', regex=True)
        # (tail/fresh) exclude OPERATING broker-dealers/exchanges. The GICS
        # INDUSTRY for an Asian securities house is "Capital Markets" (no
        # securit/broker token), so the industry filter alone can't catch them
        # (Daishin/Kyobo/Yuhwa/Hanyang/Orient Securities) — match the NAME too.
        & ~_ind_all.str.contains(
            r'bank|insur|thrift|mortgage|reinsur|credit|securit|broker|exchange',
            regex=True)
        & ~_nm_l.str.contains(r'securit|broker|\bbank\b|insur', regex=True))
    # (tail) a NAV-discount thesis needs NAV that is HOLDING, not eroding. A
    # BDC/holdco bleeding book value via losses (MLCI roce-0.84, BBXIA fcf-0.92,
    # OCCI fcf-0.50) is a melting discount, not a covered one. Require ROE not
    # known-negative (permissive on missing).
    # (gate audit #5) a negative-NAV vehicle with negative income shows a
    # falsely POSITIVE roe — treat NI<0 with book not-positive as eroding
    _nav_not_eroding = (~(_num('roe').notna() & (_num('roe') < 0.0))
                        & ~((_num('net_income_ttm') < 0) & ~(_num('pb') > 0)))
    # (audit 3) a HOLDCO / cross-holder can carry any sector label (Keisei,
    # UK property-and-stakes holdcos): the vehicle test is the industry, in
    # any sector, at a sub-0.7 book; net debt low (the recipe lists it twice);
    # and the discount being ADDRESSED is one of several lenses — the yield, a
    # shrinking count or a dated tender — not the yield alone
    _nav_addressed = ((div_yield_v >= 0.05) | (_ncol('capital_return_yield') >= 0.06)
                      | (_ncol('fq_shares_yoy') <= -0.02) | (_ncol('buyback_yield') >= 0.03)
                      | (_evt_age_days('evt_tender_date') <= 365)).fillna(False)
    df['arch_oak_nav_discount'] = (
        _nav_vehicle & _nav_not_eroding &   # (audit 3) the industry test (holdco / investment company / trust / asset manager) in ANY sector
        (((pb > 0) & (pb < 0.7)) | ((_ptb_nav > 0) & (_ptb_nav < 0.7))) &
        _lev_ok(3.0) &                      # net debt low (nde, else debt/assets, debt/equity or net cash; unmeasured passes)
        _nav_addressed
    ).fillna(False).astype(int)

    # NEW: Oak asset floor — market cap at/below cash + hard assets (CVV/PRTC).
    # Well-captured on the CASH leg (net cash or NCAV >= mcap = Graham floor);
    # does NOT see hidden real-estate-at-market or private-stake value.
    df['arch_oak_asset_floor'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 500e6) &
        # (audit 3) the author's test is mcap <= cash + tangible assets: net cash
        # >= 70% of mcap at/below tangible book, or NCAV covering the cap; the
        # old 40% / 80% / pb < 1.5 rule is surfaced as oak_asset_floor_watch
        (((net_cash_pct_c >= 0.70) & ((p_tb > 0) & (p_tb <= 1.0))) | (ncav_pct >= 1.0)) &
        (pb > 0) & (pb < 1.5) &
        # (gate-audit) the positive-cash mandate (fcf>0 | cfo>0) contradicts a
        # GRAHAM LIQUIDATION-FLOOR thesis — it excluded 549 non-melting loss-
        # making net-nets, the exact names this archetype exists to find.
        # _not_melting already carries survivability against operations eating
        # the floor (DCGO/0738.HK-type capital destroyers still fail).
        _not_melting
    ).fillna(False).astype(int)
    df['oak_asset_floor_watch'] = (is_operating & (mcap > 0) & (mcap < 500e6)
                                   & ((net_cash_pct_c >= 0.40) | (ncav_pct >= 0.80)) & (pb > 0) & (pb < 1.5)
                                   & _not_melting).fillna(False).astype(int)

    # ---------- Cundill RECOVERY-fund punt: crisis-crushed, asset-in-the-ground ----
    # The Mackenzie Cundill RECOVERY fund play (Sibir Energy, Russia 1999), a
    # DIFFERENT animal from the Value-fund six-point checklist above. A hard-
    # asset-rich OPERATING company — oil reserves, ore, plant, ships — smashed by
    # a MACRO / country / commodity crisis while the assets themselves stay
    # intact (Sibir 47p -> 10p, -79%, on Russia's 1998 default, not on any
    # reserve write-down). The margin of safety is the ASSET FLOOR, so unlike
    # oak_deep_value this deliberately does NOT require positive FCF/CFO — it is
    # the pre-turn, distressed cousin. Cundill protected the DOWNSIDE with a
    # SENIOR CONVERTIBLE (12% coupon, preferential to common); a public-equity
    # screen cannot buy that instrument, so it substitutes two protections: the
    # discount must be measured against TANGIBLE assets (real, saleable plant/
    # reserves, not goodwill), and the operation must not be an active ice cube
    # (_not_melting) — i.e. we take the punt as the returns begin to inflect, not
    # at the absolute default-day bottom where only the senior paper was safe.
    _car_ptb = _ncol('p_tb')
    _car_ppe_ratio = (_ncol('ppe_gross') / _ncol('assets'))
    # value is in the GROUND / the plant — reserves, ore, refineries, rigs, ships
    _car_asset_heavy = (asset_heavy(sector.isin({'Energy', 'Materials', 'Industrials'}))   # (audit 3) measured PP&E / capex intensity, the label only where unmeasurable
                        | (_car_ppe_ratio >= 0.40))
    # a genuine crisis WASHOUT, not an ordinary down year (Sibir was -79%)
    # (endpoint matrix) the crash also read against the 5-year weekly high
    # (a crisis washout of >= 55% off the former high, the Sibir depth)
    _car_crash = (beaten_down_any(0.55) | (_num('price_pct_of_5y_range') <= 0.15)
                  | (_ts_hi260 <= 0.45).fillna(False))
    # trading below the tangible (hard-asset) book — the reserves/plant are worth
    # more than the whole equity; below-0.8 tangible book also proves positive
    # net assets survive all senior claims (a lethal-leverage name goes negative)
    _car_below_assets = (((_car_ptb > 0) & (_car_ptb < 0.8))
                         | (_car_ptb.isna() & (pb > 0) & (pb < 0.8)))   # TANGIBLE book where measured; total book only where P/TB is absent
    _DEMOTED.setdefault('crisis_asset_backed_recovery', []).extend([(_ncol('net_debt_ebitda'), -1), (_bs_d2a, -1), (_ncol('fmp_altman_z'), 1)])
    df['arch_crisis_asset_backed_recovery'] = (
        is_operating & (mcap >= 20e6)                       # real, tradeable, not a shell
        & _car_asset_heavy & _car_crash & _car_below_assets
        & _not_melting                                      # not an active capital-destroyer
    ).fillna(False).astype(int)

    # ---------- Cluseau — "Identifying, Structuring and Sizing" ----------
    # (cluseau.com) The framework's central forensic claim: cheapness is a
    # SCREEN, not a thesis. A sub-book multiple is worth something only when
    #   (a) the BOOK IS REALIZABLE — cash and securities, not plant that cannot
    #       be sold "absent a massive discount", and not a book that is
    #       repeatedly impaired; and
    #   (b) MANAGEMENT ACTUALLY RETURNS IT — a company "squatting on cash" or
    #       "touting a significant discount to book while doing nothing to
    #       address the discount" is a value TRAP (Gravity: ~1x tangible book,
    #       almost the whole cap in cash, zero payout, 1.5%/yr for five years).
    # Capital allocation "distinguishes value investments from value traps".
    # Two positive archetypes carry the affirmative pattern; three flags carry
    # the article's disqualifiers (surfaced, never used to null a value).
    # DATA LIMITS (documented, not faked): the article's insider-alignment
    # ratio (insider $ / executive compensation, >5x healthy) needs proxy-
    # statement pay that XBRL does not carry — ownership and Form-4 buying, its
    # other alignment tells, already live in governance_score. There is no
    # marketable-securities line (realizability uses CASH alone, conservative),
    # no cash trend (deployment is read from a cash-LIGHT balance sheet beside a
    # real buyback pace), and no impairment history.
    _cl_ptb = _ncol('p_tb'); _cl_teq = _ncol('tangible_equity')
    _cl_cash = _ncol('cash'); _cl_by = _ncol('buyback_yield').fillna(0)
    _cl_dy = _ncol('dividend_yield').fillna(0); _cl_sy = _ncol('shares_yoy')
    _cl_s3 = _ncol('shares_3y_cagr'); _cl_cpm = _ncol('cash_pct_mcap')
    _cl_ni = _ncol('net_income_ttm'); _cl_cfo = _ncol('cfo_ttm')
    _cl_capex = _ncol('capex_ttm').abs()
    _cl_profitable = ((_cl_ni > 0) | (_ncol('ni_avg') > 0) | (fcf_yield > 0)).fillna(False)
    # capital actually being RETURNED: a buyback, a dividend, or a shrinking count
    _cl_returning = ((_cl_by >= 0.01) | (_cl_dy >= 0.01) | (_cl_sy < -0.01)).fillna(False)
    # REALIZABLE share of the tangible book (cash over tangible equity)
    # (audit 3) realizable = cash NET OF DEBT over tangible equity (cash owed to
    # lenders is not the owners'); a known net-cash position corroborates
    _cl_realizable = ((_cl_cash - _ncol('total_debt').fillna(0)) / _cl_teq.where(_cl_teq > 0)).where(
        _ncol('total_debt').notna() | (net_cash_pct > 0))   # unknown debt is not zero debt: a known net-cash position corroborates

    # (1) REALIZABLE-BOOK DISCOUNT — deep sub-tangible-book (article: <0.5-0.6x)
    #     where the book is CASH, not un-sellable plant, AND it is being returned.
    #     Distinct from arch_tangible_value (P/TB<0.7 alone tests neither
    #     realizability nor return) and from a net-net (cash > market cap).
    # Altman-Z distress is surfaced as a DISQUALIFIER FLAG alongside the
    # archetype (see fmp_distress_flag), consistent with the other Cluseau
    # disqualifiers (cash_squatter / capex_treadmill / earnings_variability) —
    # it informs, it does not silently remove the name from the archetype.
    df['arch_cluseau_realizable_book'] = (
        is_operating & (mcap >= 20e6)
        & (_cl_ptb > 0) & (_cl_ptb < 0.6)
        & (_cl_realizable >= 0.50)                  # >= half the tangible book is cash (net of debt)
        # (audit 3) the return must be MATERIAL against the discount: >= 3% total
        # yield or a >= 2% shrink, not a 1% token
        & (((_cl_by + _cl_dy) >= 0.03) | (_cl_sy <= -0.02))
        & ~(_ncol('tc_uncov_payout_3y') >= 2)       # (audit 3) ...and covered over the cycle where observed
        & _cl_returning & _cl_profitable & _not_melting
    ).fillna(False).astype(int)

    # (2) BUYBACKS ACCELERATING INTO A DISCOUNT WITH CASH DEPLOYED — the Georgia
    #     Capital pattern (3% -> 5% -> 7% of shares repurchased a year, cash run
    #     from 20% to 3% of the balance sheet, buying hardest into weakness).
    #     Distinct from arch_cannibal_at_discount (which only asks for a shrink
    #     below book) by requiring ACCELERATION — this year's shrink faster than
    #     the 3-year trend — a >= 3% pace, and a cash-LIGHT balance sheet.
    _cl_accel = ((_cl_sy < 0) & ((_cl_sy - _cl_s3) <= -0.01)).fillna(False)
    # (endpoint matrix, PROXY) the acceleration MEASURED where the annual
    # cash-flow history allows: buyback yield (each FY's repurchases over that
    # FY's market cap) rising year on year across the last three FYs. An
    # additional lens, not a requirement (history is patchy outside FMP's
    # multi-year coverage).
    _by0, _by1, _by2 = (_ncol('fmp_st_buyback_yield_y0'), _ncol('fmp_st_buyback_yield_y1'),
                        _ncol('fmp_st_buyback_yield_y2'))
    _cl_accel = _cl_accel | ((_by0 >= 0.03) & (_by0 > _by1) & (_by1 >= _by2)).fillna(False)
    df['arch_cluseau_buyback_accel'] = (
        is_operating & (mcap >= 20e6)
        & (_cl_ptb > 0) & (_cl_ptb < 1.0)
        & ((_cl_by >= 0.03) | (_by0 >= 0.03)) & _cl_accel   # (audit 3) the FY repurchase yield (global) satisfies the pace gate too
        & _no_rsplit_yoy                            # (audit 3) a -30% collapse is a split / restructuring unless a buyback corroborates it
        & ((_cl_cpm <= 0.15) | ((_ncol('fq_cash_sti') / _ncol('fq_total_assets').where(_ncol('fq_total_assets') > 0)) <= 0.10))   # (audit 3) cash deployed: cash / mcap, or cash <= 10% of the BALANCE SHEET (the article's own denominator)
        & _cl_profitable & _not_melting
    ).fillna(False).astype(int)

    # DISQUALIFIER FLAGS
    # cash squatter — sub-book, cash-rich, EARNING, and returning NOTHING: the
    # article's canonical value trap (GRVY). "Distrust companies touting a
    # discount to book while doing nothing to address it."
    df['cash_squatter_flag'] = (
        (_cl_ptb > 0) & (_cl_ptb < 1.0) & (_cl_cpm >= 0.30) & _cl_profitable
        & (_cl_by <= 0.005) & (_cl_dy <= 0.005) & ~(_cl_sy < -0.005)
    ).fillna(False).astype(int)
    # capex treadmill — "if a company's earnings are plowed into capex just to
    # remain competitive, assign a discount": capex >= 80% of operating cash.
    df['capex_treadmill_flag'] = (
        (_cl_cfo > 0) & (_cl_capex >= 0.80 * _cl_cfo)
    ).fillna(False).astype(int)
    # earnings variability — "wildly variable earnings will consistently trade
    # at a discount to the market" (ZIM): earnings fell in at least half the
    # years AND the current print sits far from the multi-year average.
    _cl_niavg = _ncol('ni_avg')
    # Native leg (EDGAR): earnings fell in >= half the years AND the current
    # print sits far from the multi-year average. FMP leg: a high dispersion
    # of quarterly earnings SURPRISES (winsorized, so [0,1]) over >= 6 quarters
    # is an independent tell of unpredictable earnings — the analyst consensus
    # itself cannot pin them down. Either leg fires the flag.
    _fmp_scv = _ncol('fmp_earnings_surprise_cv'); _fmp_en = _ncol('fmp_earnings_n')
    df['earnings_variability_flag'] = (
        ((_ncol('eps_yoy_positive_share') <= 0.5)
         & (((_cl_ni - _cl_niavg).abs() > 0.5 * _cl_niavg.abs()) | (_cl_niavg <= 0)))
        | ((_fmp_scv >= 0.40) & (_fmp_en >= 6))
    ).fillna(False).astype(int)
    # SIZING tier — the article sizes emerging-market / geopolitical-tail-risk
    # names as a 0.5-1% STARTER and scales in on weakness ("there is a price for
    # everything"; "easier to explain losing money on Apple than getting zeroed
    # on a Georgian conglomerate"). A screen cannot size, but it can label.
    _cl_em = df['src'].astype(str).str.upper().isin(
        {'CN', 'HK', 'IN', 'BR', 'TR', 'ZA', 'ID', 'MY', 'TH', 'AR', 'CL', 'MX',
         'GR', 'RO', 'SA', 'TW', 'KR', 'PL', 'HU', 'CZ'})
    # (FMP geography) listing domicile understates tail risk: a US- or
    # Europe-listed company earning most of its revenue in emerging markets
    # (e.g. a US ADR with 90% China revenue) carries the same geopolitical /
    # FX exposure the article sizes as a starter. Tier on WHERE THE REVENUE
    # COMES FROM (FMP geographic segmentation) as well as where it is listed.
    _cl_em = _cl_em | (_ncol('fmp_geo_em_share') >= 0.50).fillna(False)
    df['cluseau_sizing_tier'] = np.where(_cl_em, 'starter 0.5-1% (tail risk)', 'standard')

    # NEW (user request): Hidden-asset overcapitalized balance sheet — a
    # BALANCE-SHEET-NUANCE lens born from the valuation QC work. The EV
    # composition gap (EV + broad_cash - mcap - debt, as % of mcap) measures
    # assets the EV arithmetic does NOT net out: our `cash` is the broad
    # cash+investments figure while Yahoo's EV nets only narrow totalCash, so a
    # LARGE POSITIVE gap = a securities/investment portfolio sitting under the
    # operating business that the market's own EV math is not crediting
    # (Moriya 1798.T: ~58% of mcap in securities — the classic Japanese
    # overcapitalized net-net shape; also HK family holdcos). Require the gap
    # to be big, the stock priced at/below book (so the portfolio really is
    # free), a survivable cash-rich balance sheet (so the gap is ASSETS, not a
    # minority-interest/pref-claim artifact — those come with leverage), and a
    # real operating business underneath. Financials excluded (their
    # "investments" are the float, not hidden treasure).
    # ALL FOUR components in LOCAL currency (the raw master columns): the
    # tags-level `mcap` variable is the USD-normalized cap, and mixing it with
    # local-currency ev/cash/debt inflated the gap ~1500x for KRW names — the
    # exact currency-mix corruption class this pipeline guards against. The
    # ratio below is same-currency throughout, hence currency-neutral.
    _ev_ha = _ncol('enterprise_value')
    _td_ha = _ncol('total_debt')
    _ca_ha = _ncol('cash')
    _mc_ha = _ncol('market_cap')
    # (non-XR review) the old measure (providerEV - mcap - net debt) was
    # IDENTICALLY ZERO on the ~23% of rows whose EV is reconstructed as
    # mcap+debt-cash, and on provider-EV rows it captured minority/preferred,
    # NOT the off-EV investment portfolio the thesis wants. Measure the actual
    # non-operating assets directly: associate/equity-method stakes + net cash,
    # all local-currency, over mcap. Falls back to net-cash alone where the
    # associate line is absent (so non-EDGAR names still qualify on deep cash).
    _assoc_ha = _ncol('investments_associates')
    _nonop_ha = (_assoc_ha.fillna(0) + (_ca_ha - _td_ha))
    _hidden_pct = (_nonop_ha / _mc_ha.where(_mc_ha > 0))
    _fx_m_g = _ncol('market_cap_usd') / _ncol('market_cap')
    _fx_r_g = _ncol('revenue_ttm_usd') / _ncol('revenue_ttm')
    _fx_coherent = ~(((_fx_m_g / _fx_r_g) - 1).abs() > 0.10)
    # ...but twins that AGREE AT WRONG VALUES (unconverted — the JFU class)
    # defeat twin detection, so provable cross-currency LINES are excluded
    # from mcap-vs-level gates directly: Frankfurt .F cross-lines and
    # USD-quoted Shanghai B-shares (9xxxxx.SS). Their HOME listings stay in
    # the pool — no name is lost, only the wrong-basis duplicate line.
    _sym_g = df['symbol'].astype(str)
    _fx_coherent = _fx_coherent & ~(_sym_g.str.endswith('.F')
                                    | _sym_g.str.match(r'^9\d{5}\.SS$'))

    df['arch_hidden_assets'] = (
        is_operating &
        _fx_coherent &                              # (gate audit #2) the motivating cross-ccy case
        (mcap > 0) &
        (_hidden_pct >= 0.25) &                     # off-EV assets >= 25% of mcap
        ((net_cash_pct_c >= 0.10) | (cash_pct_mcap_v >= 0.30)) &  # genuinely cash/asset-rich (not a minority-interest artifact)
        # (audit 3) HIDDEN means a portfolio: associate / long-term investment
        # stakes >= 10% of mcap where the line is disclosed; a pure net-cash
        # pile with no stakes is negative_ev_value / net_cash_returner ground
        ~((_assoc_ha / _mc_ha.where(_mc_ha > 0)) < 0.10) &
        (pb > 0) & (pb <= 1.0) &                    # at/below book: the portfolio is not being paid for
        _not_melting &                              # a real business under the portfolio
        ((s('op_margin', np.nan) > 0) | (fcf_yield > 0) | (ebitda_ttm_v > 0))
    ).fillna(False).astype(int)

    # ---------- FORENSIC-ACCOUNTING archetypes (user request) ----------
    # Balance-sheet accounting NUANCES that OBSCURE deep value — forensic
    # techniques run in reverse: instead of hunting overstatement, hunt the
    # conventions that systematically UNDERSTATE. All components are LOCAL
    # currency from the same source rows (currency-neutral by construction —
    # the hidden_assets currency-mix lesson).

    # F1 — Over-depreciated asset base ("harvest mode"). Economic vs
    # accounting depreciation: implied D&A (EBITDA - EBIT) runs far above
    # replacement capex while revenue HOLDS — the book writes assets down
    # faster than they actually wear out (long-held plant/property carried at
    # depressed cost), so P/B understates the real asset backing. Buying at or
    # below that depressed book = the forensic depreciation-gap trade.
    _rev_loc = _ncol('revenue_ttm')
    _ebit_loc = s('op_margin', np.nan) * _rev_loc
    # D&A: AUDITED (EDGAR DepreciationDepletionAndAmortization) preferred over
    # the implied EBITDA-EBIT reconstruction, which mixes a level with a
    # margin-rebuild and can go negative across sources. Implied is the
    # fallback where audited is absent; floored at >=0.
    _dna_audited = _ncol('da_ttm')
    # (audit #3) the implied fallback (EBITDA − EBIT) equals D&A only when EBIT
    # is a genuine positive margin; an impairment / near-zero op_margin dumps
    # the charge (or all of EBITDA) into "D&A" — MHK.AX op −40% → implied D&A
    # 226% of revenue; HUSQF op 0% → implied D&A = full EBITDA. Now that audited
    # da_ttm covers 25.6k names, trust implied ONLY where op_margin>0 and the
    # result is bounded (≤ EBITDA and ≤ 35% of revenue); else leave D&A missing.
    _dna_implied = (_ncol('ebitda_ttm') - _ebit_loc)
    _dna_implied = _dna_implied.where(
        (s('op_margin', np.nan) > 0)
        & (_dna_implied <= _ncol('ebitda_ttm'))
        & (_dna_implied <= 0.35 * _rev_loc))
    _dna_loc = _dna_audited.where(_dna_audited.notna(), _dna_implied)
    _dna_loc = _dna_loc.where(_dna_loc >= 0)
    _capex_loc = _ncol('capex_ttm')
    # (audit #2/#4/#5) MAINTENANCE capex = the CONSERVATIVE (higher) of the
    # single TTM window and the 5yr EDGAR annual average. The harvest / owner-
    # earnings gates were faked by a momentarily-collapsed TTM window (FLNG
    # capex_ttm=$0 vs 5yr avg $59M; NVGS $1.3M vs $80.6M) — reading a "harvest"
    # or inflated owner earnings where real replacement spend is normal.
    _capex_avg_loc = _ncol('capex_avg')
    _maint_capex = pd.concat([_capex_loc, _capex_avg_loc], axis=1).max(axis=1)
    # MARGIN-BASED MID-CYCLE (inflation-neutral, per user): the nominal 5yr
    # EBITDA average is depressed by inflation vs current nominal, faking a
    # "trough". Mid-cycle MARGIN x CURRENT revenue is the correct Graham/
    # Templeton normalization and carries no inflation drift.
    _norm_eb = _ncol('normalized_ebitda')
    _norm_rv = _ncol('normalized_revenue')
    _midcyc_margin = (_norm_eb / _norm_rv).where(_norm_rv > 0)
    _midcyc_ebitda = (_midcyc_margin * _ncol('revenue_ttm')).where(_midcyc_margin.notna())
    df['arch_overdepreciated_assets'] = (
        is_operating & (mcap > 0) &
        (_dna_loc > 0) & (_rev_loc > 0) &
        ((_dna_loc / _rev_loc) >= 0.05) &          # a real fixed-asset business (D&A >= 5% of sales)
        (_maint_capex >= 0) & (_maint_capex <= 0.6 * _dna_loc) &  # replacement (incl. 5yr avg) FAR below depreciation — not a single collapsed TTM window
        ~(_ncol('fq_capex_to_da') > 0.8) &         # (audit 3) the quarterly date-matched capex / D&A agrees where measured
        ~(_ncol('rev_3y_cagr') < -0.02) &          # (audit 3) a HELD top line over three years (the melter must not wear the scrapyard label)
        ~(_ncol('fq_da_to_ppe') < 0.05) &          # (audit 3) an old, depreciating base (D&A >= 5% of net PP&E where measured)
        (s('op_margin', np.nan) > 0) &             # profitable harvest, not decay
        (rev_yoy_c >= -0.05) &                     # the "worn-out" assets still produce
        (pb > 0) & (pb < 1.2) &                    # priced at/below the depressed book
        _not_melting
    ).fillna(False).astype(int)

    # F2 — Understated earnings (the accruals red-flag INVERTED). Forensic
    # accounting flags NI >> CFO as inflation; the reverse — CFO persistently
    # far ABOVE net income (deferred-revenue float, conservative provisioning,
    # heavy non-cash charges) — means the P&L UNDERSTATES cash economics,
    # and a market pricing the understated E via P/E misprices the business.
    _ni_loc = _ncol('net_income_ttm')
    _cfo_loc = _ncol('cfo_ttm')
    _cfo_ni = (_cfo_loc / _ni_loc).where(_ni_loc > 0)
    # Global reach: FMP income quality is CFO/NI, standardized and currency-
    # invariant, so it fills the ratio where our master's CFO is absent (the
    # non-US cohort) — the CFO-above-earnings thesis then fires worldwide.
    _cfo_ni = _cfo_ni.fillna(_ncol('fmp_income_quality'))
    _pe_ue = _ncol('p_e')
    # PERSISTENCE, proven from quarterly statements: the year-ago TTM also had
    # CFO >= 1.2x NI (same cash-flow basis), so "persistently above" is
    # observed rather than inferred from one window.
    _cfo_ni_ya = (_ncol('fq_cfo_p') / _ncol('fq_ni_cf_p').where(_ncol('fq_ni_cf_p') > 0))
    # ...and the current surplus must not be a WORKING-CAPITAL LIQUIDATION
    # (changeInWorkingCapital > 50% of CFO = a one-off inventory/receivable
    # release, the opposite of conservative accounting). Only where observed.
    _wc_liq_ue = (_ncol('fq_chg_wc') / _ncol('fq_cfo').where(_ncol('fq_cfo') > 0)) > 0.5
    df['arch_understated_earnings'] = (
        is_operating & (mcap > 0) &
        (_ni_loc > 0) &
        (_cfo_ni >= 1.5) & (_cfo_ni <= 4.0) &      # cash well above book earnings; sane band (beyond 4x = distortion, not conservatism)
        ((_ncol('cash_conversion') >= 1.1) | (fcf_yield >= 0.10)
         | (_cfo_ni_ya >= 1.2)
         | ((_ncol('fcf_ttm') / _ni_loc.where(_ni_loc > 0)) >= 1.2)   # (audit 3) FCF / NI >= 1.2 (capex-aware) as a further corroboration
         | (_ncol('fq_sloan_accruals') <= -0.05)) &   # (audit 3) ...or negative accruals measured directly
        ~(_ncol('sbc_pct_revenue') >= 0.15) &      # (audit 3) the surplus must not BE the SBC add-back (the sbc_polluted rule, read from its input: the flag is defined later)
        ~_wc_liq_ue.fillna(False) &
        (_pe_ue > 0) & (_pe_ue <= 15) &            # the market is pricing the UNDERSTATED E
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # F3 — Expensed growth spend (intangible investment through the P&L).
    # Companies expensing R&D/brand/customer-acquisition show BOTH a thin op
    # margin and an understated book — the classic reason quality growth looks
    # "expensive on E, cheap on nothing". The forensic tell: FAT gross margins
    # (real IP/moat economics) with a thin op margin, while revenue grows and
    # the share count does NOT — the gap is self-funded reinvestment, and on
    # gross earnings power the name is objectively cheap (Novy-Marx lens).
    _gm_loc = s('gross_margin', np.nan)
    _mc_loc = _ncol('market_cap')
    _gp_mcap = (_gm_loc * _rev_loc / _mc_loc.where(_mc_loc > 0))
    _DEMOTED.setdefault('expensed_growth_value', []).extend([(_ncol('fcf_yield'), 1), (_ncol('fq_shares_yoy'), -1)])
    df['arch_expensed_growth_value'] = (
        is_operating &
        _fx_coherent &                              # (gate audit #2) GP/mcap is level-over-mcap
        (_ncol('revenue_ttm_usd') >= 5e6) &        # base-effect guard (microcap sweet spot kept)
        (_gm_loc >= 0.40) & (_gm_loc <= 0.98) &    # real unit economics; exactly-100% GM = missing-COGS artifact, not a margin
        (_gp_mcap >= 0.50) &                       # gross earnings power >= 50% of the price
        (s('op_margin', np.nan) < 0.10) &          # the gap IS the expensed growth spend...
        (s('op_margin', np.nan) > -0.15) &         # ...reinvestment-THIN, not collapse (ALDNE op-228% is not spending discipline)
        (rev_yoy_c >= 0.10) & (rev_yoy_c <= 1.0) & # the spend is buying growth; base-effect pops capped
        ~(_ncol('shares_yoy') > 0.05) &            # self-funded, not dilution-funded
        _not_melting
    ).fillna(False).astype(int)

    # FX-COHERENCE guard for every gate dividing a LEVEL by MARKET CAP: on a
    # cross-listed line (USD-quoted Shanghai B-shares, Frankfurt .F lines) the
    # mcap is LISTING-currency while financials are REPORTING-currency — the
    # ratio silently mixes currencies (900920.SS showed owner earnings at 5x
    # its mcap). Coherent = the fx implied by the mcap USD-twin matches the fx
    # implied by the revenue USD-twin within 10% (NaN-permissive: home-listed
    # rows without twins pass).
    # (_fx_coherent is constructed earlier, above arch_hidden_assets)

    # F4 — Cash-adjusted P/E, negative-or-cheap (user spec). The doctrine:
    # NEGATIVE is only CHEAP when the earnings are POSITIVE — a negative EV on
    # positive EBITDA means you are paid to own the earnings; the same logic at
    # the earnings line is (mcap - net cash) / NI. When net cash exceeds market
    # cap WITH real positive earnings, the multiple goes NEGATIVE: the whole
    # operating business comes free plus change. adj P/E <= 8 (negative included) is
    # the cheap band. All components LOCAL currency. CAVEAT (documented): the data has no
    # restricted-cash split, so `cash` may include some restricted balances —
    # the net-of-debt construction is the partial mitigation.
    _ni_ca = _ncol('net_income_ttm')
    _nc_ca = _ncol('cash') - _ncol('total_debt')
    _mc_ca = _ncol('market_cap')
    _adj_pe = ((_mc_ca - _nc_ca) / _ni_ca.where(_ni_ca > 0))
    df['arch_cash_adjusted_pe'] = (
        is_operating & (_mc_ca > 0) &
        _fx_coherent &
        (_ni_ca > 0) &                              # POSITIVE earnings mandatory (negative only cheap on real E)
        ((_ni_ca / _mc_ca) >= 0.02) &               # material earnings, not a rounding artifact
        (_nc_ca > 0) &                              # a genuine net-cash balance sheet
        # cheap ex-cash on the LATEST year — or on GRAHAM AVERAGE EARNINGS
        # (5-yr NI average): the average leg keeps a name whose latest E is
        # quirk-depressed and drops none (pure OR-addition).
        ((_adj_pe <= 8.0)
         | (((_mc_ca - _nc_ca)
             / _ncol('ni_avg').where(_ncol('ni_avg') > 0)) <= 8.0)) &
        # (audit 3) ONE-OFF GAIN guard: a latest NI above 2x the 5-year average
        # must also be cheap on the average (the latest leg alone is a gain year)
        ~((_ni_ca > 2.0 * _ncol('ni_avg')) & ~(((_mc_ca - _nc_ca) / _ncol('ni_avg').where(_ncol('ni_avg') > 0)) <= 8.0)) &
        ~(_ncol('shares_yoy') > 0.05) &
        # (audit) CASH corroboration: a low adj-P/E on POSITIVE reported NI is a
        # false bargain when the earnings are non-cash / one-off — 177 firers had
        # NI>0 but NEGATIVE CFO (032190.KQ NI +₩253B / CFO −₩12T). Require CFO to
        # confirm the earnings where CFO is known (missing CFO stays permissive).
        ~(_ncol('cfo_ttm').notna() & (_ncol('cfo_ttm') < 0.3 * _ni_ca)) &
        _not_melting
    ).fillna(False).astype(int)

    # F5 — Owner-earnings power (Buffett's adjustment as a forensic lens).
    # Owner earnings = NI + D&A - capex: when depreciation persistently
    # overstates true asset consumption (D&A >> replacement capex), accounting
    # NI UNDERSTATES the cash the owner actually keeps. Fire when owner
    # earnings run >=1.4x reported NI and the price is <=10x OWNER earnings —
    # cheap on the truer measure while the market prices the accounting one.
    _oe_loc = _ni_ca + (_dna_loc - _maint_capex)   # (audit #2) subtract MAINTENANCE capex (max of TTM and 5yr avg), so a collapsed TTM window (FLNG capex_ttm=$0) can't inflate owner earnings
    _oe_ratio = (_oe_loc / _ni_ca).where(_ni_ca > 0)
    df['arch_owner_earnings_power'] = (
        is_operating & (_mc_ca > 0) &
        _fx_coherent &
        (_ni_ca > 0) & (_dna_loc > 0) & (_capex_loc >= 0) &
        (_oe_ratio >= 1.4) &                        # owner earnings far above accounting earnings
        ~(_ncol('fmp_st_owner_earnings_yield') < 0.08) &   # (audit 3) cheap on the STATEMENT-HISTORY owner-earnings yield too where it exists (both sources agree)
        ~(_ncol('rev_3y_cagr') < -0.02) &           # (audit 3) the mechanism is benign: a held top line, not deferred maintenance on a decliner
        # cheap on the truer measure — LATEST OE, or (Graham/Templeton) the
        # 5-YEAR AVERAGE OE with the latest still positive: one weak or quirky
        # accounting year must neither admit nor exclude a name on its own.
        (((((_mc_ca / _oe_loc.where(_oe_loc > 0)) <= 10.0)
           & ((_mc_ca / _oe_loc.where(_oe_loc > 0)) >= 1.5))
         | ((((_mc_ca / _ncol('oe_avg').where(_ncol('oe_avg') > 0)) <= 10.0)
             & ((_mc_ca / _ncol('oe_avg').where(_ncol('oe_avg') > 0)) >= 1.5))
            & (_oe_loc > 0)))) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)


    # ---------- FORENSIC round 2 (user request): latent value via EDGAR ------
    # F7 — Retained-earnings discount (Buffett's dollar-retained test, priced).
    # Decades of ACCUMULATED retained profit exceed the whole market cap while
    # the business still earns: the market prices the company below its own
    # retained history. Audited EDGAR retained_earnings; profitability may
    # qualify on the LATEST year or the 5-YEAR AVERAGE (quirk-robust).
    _re_f7 = _ncol('retained_earnings')
    _mc_f7 = _ncol('market_cap')
    _DEMOTED.setdefault('retained_earnings_discount', []).extend([(_ncol('roe'), 1)])
    df['arch_retained_earnings_discount'] = (
        is_operating & (_mc_f7 > 0) & (_re_f7 > 0) &
        _fx_coherent &
        ((_re_f7 / _mc_f7) >= 1.0) &                 # retained history >= the whole price
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)) &
        (pb > 0) & (pb < 1.5) &
        _not_melting
    ).fillna(False).astype(int)

    # F8 — Customer float (negative working capital, INVERTED forensic read).
    # A "weak" current ratio that is actually customers funding the business:
    # negative net working capital WITH real profitability and CFO above NI
    # (the float shows up as cash before it shows up as earnings).
    _nwc_f8 = _ncol('net_working_capital')
    # A negative cash-conversion cycle (FMP, global) is the DIRECT measure of
    # customers/suppliers funding the business — an alternative to the negative-
    # working-capital sign for names where our NWC is absent. CFO/NI corroborated
    # by FMP income quality where our CFO is missing.
    _ccc_f8 = _ncol('fmp_cash_conversion_cycle')
    _cfo_ni_f8 = (_ncol('cfo_ttm') / _ncol('net_income_ttm').where(_ncol('net_income_ttm') > 0)).fillna(_ncol('fmp_income_quality'))
    df['arch_customer_float'] = (
        is_operating & (_mc_f7 > 0) &
        ((_nwc_f8 < 0) | (_ccc_f8 < 0)              # negative WC OR negative cash-conversion cycle
         # OPERATING working capital (receivables + inventory - payables -
         # deferred revenue) negative: sees the float in a cash-rich company,
         # whose total NWC is positive only because of its cash pile
         | (_ncol('fq_op_nwc_to_rev') < 0) | (_ncol('fq_ccc') < 0)) &
        (s('op_margin', np.nan) > 0.03) &
        (rev_yoy_c >= 0.0) &                         # float grows WITH the business, not a liquidation
        (_cfo_ni_f8 >= 1.1) &
        # (audit 3) a "float" that is only a stretched payables line (DPO up
        # >= 20 days while receivables and inventory days held) is supplier
        # squeezing, not customer funding
        ~((_ncol('fq_ccc_p') - _ncol('fq_ccc') >= 20)
          & ((_ncol('fq_dso') - _ncol('fq_dso_p')).abs() <= 5)
          & ((_ncol('fq_dio') - _ncol('fq_dio_p')).abs() <= 5)) &
        ~(_cfo_ni_ya < 1.0) &                        # (audit 3) CFO above NI also a year ago where measured (not one working-capital swing)
        _not_melting
    ).fillna(False).astype(int)

    # F9 — Capex-famine harvest: the investment cycle is ENDING (current capex
    # far below the audited 5-year average) while revenue holds — the FCF
    # inflection is mechanically loaded before it prints. Needs capex_avg
    # (EDGAR annual series).
    _cx_f9 = _ncol('capex_ttm')
    _cxa_f9 = _ncol('capex_avg')
    # Where the 5-yr average came from FMP, compare it with FMP's OWN current
    # capex (same source, same reporting currency, zero-fills already blanked
    # by the engines) — never a master TTM against an FMP average.
    _f9_fmp = (_ncol('fmp_filled_capex_avg') == 1)
    _cx_f9 = _cx_f9.where(~_f9_fmp, _ncol('fq_capex').abs())
    _cxa_f9 = _cxa_f9.where(~_f9_fmp, _ncol('fmp_st_capex_avg'))
    df['arch_capex_famine_harvest'] = (
        is_operating & (_mc_f7 > 0) &
        (_cxa_f9 > 0) & (_cx_f9 >= 0) &
        (_cx_f9 <= 0.6 * _cxa_f9) &                  # spending far below its own history
        ~(_ncol('fq_capex_to_da') > 1.0) &           # (audit 3) corroborated: capex at/below D&A where the quarterly statements measure it
        (rev_yoy_c >= -0.05) &                       # the installed base still produces
        (s('op_margin', np.nan) > 0) &
        (pb > 0) & (pb < 2.0) &
        _not_melting
    ).fillna(False).astype(int)

    # F10 — Dividend-verified value (GLOBAL — the non-EDGAR forensic lens).
    # Dividends are the hardest accounting item to fake: a fat payout covered
    # by BOTH earnings and FCF at a sub-book price is forensic PROOF the
    # earnings are cash. div <= 70% of NI and <= 70% of FCF.
    _dy_f10 = _ncol('dividend_yield')
    _div_paid = _dy_f10 * _mc_f7
    _ni_f10 = _ncol('net_income_ttm')
    _fcf_f10 = _ncol('fcf_ttm')
    _SPIRITED.append('dividend_verified_value')   # (endpoint matrix, EXC) raise streak / no cut / covered payouts rank members
    df['arch_dividend_verified_value'] = (
        is_operating & (_mc_f7 > 0) &
        _fx_coherent &                              # (gate audit #2, completed) payout vs local NI/FCF
        (_dy_f10 >= 0.06) &                          # a fat, real payout
        (_ni_f10 > 0) & (_div_paid <= 0.70 * _ni_f10) &
        (_fcf_f10 > 0) & (_div_paid <= 0.70 * _fcf_f10) &
        ~(_ncol('tc_uncov_payout_3y') >= 2) &        # (audit 3) covered over the cycle where the annual history is observed
        ~(_ncol('evt_div_cut_2y') == 1) &            # (audit 3) no dividend cut in the last two years where observed
        (pb > 0) & (pb < 1.0) &                      # and the market still prices sub-book
        _not_melting
    ).fillna(False).astype(int)

    # F11 — Tax-verified earnings ('Forensic-TaxProof', EDGAR). You do not pay
    # real cash taxes on fake earnings: a FULL effective tax rate (18-40%) on
    # positive pretax income is the tax authority auditing the P&L for us.
    # Cheap on those verified earnings = forensic value. (Inverse cousin of
    # arch_tax_efficient, which hunts LOW structural rates.)
    _etr_f11 = _ncol('effective_tax_rate').fillna(_ncol('fmp_effective_tax_rate').where(_ncol('fmp_effective_tax_rate').between(0.0, 1.0)))   # (audit 3) the global FMP book rate where the EDGAR rate is absent
    # (non-XR review) pretax_income_ttm is NOT a master column -> the gate was
    # DEAD (all-NaN -> False everywhere). effective_tax_rate is only written
    # when pretax > 0, so the 0.18-0.40 band already implies positive pretax;
    # corroborate with positive NI as the "verified earnings" floor.
    _DEMOTED.setdefault('tax_verified_earnings', []).extend([(_ncol('fmp_income_quality'), 1)])
    df['arch_tax_verified_earnings'] = (
        is_operating & (mcap > 0) &
        (_ncol('net_income_ttm') > 0) &
        (_etr_f11 >= 0.18) & (_etr_f11 <= 0.40) &     # really paying the state
        ~(_ncol('fq_cash_tax_rate') < 0.10) &        # (audit 3) the CASH tax rate agrees where measured (a 25% book rate at 2% cash is a deferral, not a payment)
        (_ncol('p_e') > 0) & (_ncol('p_e') <= 12.0) &  # cheap on tax-verified E
        _not_melting
    ).fillna(False).astype(int)

    # F12 — Cannibal at a discount ('Forensic-CannibalDiscount', GLOBAL).
    # Management retiring stock BELOW BOOK: every share bought back under 1x
    # book is mechanically accretive, and the buyback is the strongest
    # insider signal there is. Corroborated shrinkage only (reverse-split
    # guard via buyback_yield), positive owner economics on the latest year
    # or the 5-yr average.
    # net shrinkage is the FACT that matters: a buyback yield fully offset by
    # SBC issuance (TTEC: buybacks claimed while shares GREW +1.3%) is not
    # cannibalization — the buyback leg must not be contradicted by net growth.
    _shrink_f12 = ((_ncol('shares_yoy') <= -0.02)
                   | ((_ncol('buyback_yield') >= 0.03)
                      & ((_ncol('net_buyback_ttm') > 0) | (_ncol('shares_yoy') < 0))))  # (audit) CORROBORATE the buyback claim with real $ retired or actual shrinkage — RVP/JVA show 30%+ buyback_yield at 0% share change (a creation/redemption artifact)
    _DEMOTED.setdefault('cannibal_at_discount', []).extend([(_ncol('net_debt_ebitda'), -1)])
    df['arch_cannibal_at_discount'] = (
        is_operating & (mcap > 0) &
        (pb > 0) & (pb < 1.0) &                       # buying below book
        _shrink_f12 &
        _no_rsplit_yoy &                              # (audit 3) a -30% collapse is a split / restructuring unless a buyback corroborates it
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)
         | (fcf_yield > 0)) &
        _not_melting
    ).fillna(False).astype(int)

    # F13 — Self-funded returner ('Forensic-SelfFunded', EDGAR financing line).
    # The no-Ponzi-financing test: the FINANCING cash-flow line has been a net
    # OUTFLOW (returning capital / repaying debt, never raising) while free
    # cash is positive — self-funding proven by the statement's own plumbing,
    # not by ratios. Cheap on earnings or book.
    _fincf_f13 = _ncol('financing_cf_ttm')
    # "HAS BEEN a net outflow ... never raising": persistence is measurable
    # from FMP annual cash-flow history (financing outflow in >= 80% of the
    # available fiscal years, >= 4 years observed). A single TTM outflow is
    # one dividend cheque — most mature cheap companies pass that — not a
    # self-funding record. NaN-permissive where no annual history exists.
    _fin_share = (_ncol('fmp_st_financing_outflow_years')
                  / _ncol('fmp_st_financing_years').where(_ncol('fmp_st_financing_years') >= 4))
    _SPIRITED.append('self_funded_returner')   # (endpoint matrix, EXC) FCF-covered outflow ranks members
    _DEMOTED.setdefault('self_funded_returner', []).extend([(_ncol('fcf_yield'), 1)])
    df['arch_self_funded_returner'] = (
        is_operating & (mcap > 0) &
        (_fincf_f13 < 0) &                            # net capital OUT to providers
        ~(_fin_share < 0.8) &                         # ...persistently, where the history is observable
        ~(_ncol('fq_shares_yoy') > 0.02) &            # (audit 3) no equity issuance behind the outflow (a repay-and-issue year cannot net to "self-funded")
        (_ncol('fcf_ttm') > 0) &
        (((_ncol('p_e') > 0) & (_ncol('p_e') <= 15.0)) | ((pb > 0) & (pb < 1.5))) &
        _not_melting
    ).fillna(False).astype(int)

    # F14 — Book compounder at a discount ('Forensic-BookCompounder', EDGAR
    # equity series). Audited book value compounding >=8%/yr over the last
    # ~5 FYs while the market prices it BELOW book — BV growth is the hardest
    # series to fake (audited, cumulative), and a discount on a compounding
    # book is latent value by arithmetic. REITs excluded; financials ALLOWED
    # (book compounding is the native lens there).
    _eqc_f14 = _ncol('equity_cagr_5y').fillna(_ncol('fg_eq_ps_5y_cagr'))   # (financial-growth) book value PER SHARE, 5-year CAGR, global where the EDGAR series is absent
    df['arch_book_compounder_discount'] = (
        (is_operating | is_financial) & ~is_utility & (mcap > 0) &   # (audit) exclude UTILITY preferreds (DTE/WEL stubs) that passed ~is_reit; keep financials (book-compounding is native there)
        (_eqc_f14 >= 0.08) &
        ~(_ncol('shares_growth_5y') > 0.05) &        # (audit 3) TOTAL equity compounding on issuance is not book-per-share compounding
        (pb > 0) & (pb < 1.0) &
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- F15-F17: FORENSIC balance-sheet nuances (EDGAR scrape) --------
    # Hidden assets / tax shields the reported book and P&L understate, from the
    # freshly-extracted companyfacts lines. All levels USD (EDGAR US filers);
    # mcap is the USD-normalized cap, so the ratios are currency-coherent.

    # F15 — LIFO hidden reserve: inventory carried below current cost, so the
    # LIFO reserve is a hidden asset that understates book (and, via COGS,
    # earnings). Buy at/below the LIFO-ADJUSTED book (reported book + reserve).
    # (audit 3) the reserve is a PRE-TAX hidden asset; realising it is taxed —
    # take it after tax (the higher of the name's ETR and the 21% statutory)
    _lifo_f15 = _ncol('lifo_reserve') * (1.0 - _ncol('effective_tax_rate').clip(0.0, 0.40).fillna(0.21).clip(lower=0.21))
    _lifo_pct_f15 = (_lifo_f15 / mcap.where(mcap > 0))
    _adj_book_f15 = (1.0 / pb).where(pb > 0, np.nan) + _lifo_pct_f15   # (book + LIFO)/mcap
    _real_sector_f = ~_sec_l.isin(['', 'nan', 'none', 'null'])   # a real operating company, not a null-sector ETN/artifact mapped to an issuer CIK (VYLD = a JPMorgan ETN inheriting JPM's pension)
    df['arch_lifo_hidden_reserve'] = (
        is_operating & _real_sector_f & (mcap > 0) & (_lifo_f15 > 0)
        & (_lifo_pct_f15 >= 0.10)              # reserve material vs mcap
        & (_adj_book_f15 >= 1.0)               # priced at/below LIFO-adjusted book
        & _not_melting
    ).fillna(False).astype(int)

    # F16 — Overfunded pension: a POSITIVE funded status (plan assets > benefit
    # obligation) is a hidden asset that reverts to equity; the market prices
    # the operating business, not the surplus.
    # (audit 3) a surplus reverts only after reversion excise and corporate
    # tax (US), or as avoided service cost over years — take HALF of it
    _pfs_f16 = _ncol('pension_funded_status') * 0.5
    _pfs_pct_f16 = (_pfs_f16 / mcap.where(mcap > 0))
    df['arch_pension_overfunded'] = (
        is_operating & _real_sector_f & (mcap > 0) & (_pfs_f16 > 0)
        & (_pfs_pct_f16 >= 0.10)               # surplus material vs mcap
        & ((fcf_yield > 0.03) | ((pb > 0) & (pb < 2.0)))  # operating business itself not dear
        & _not_melting
    ).fillna(False).astype(int)

    # F17 — Deferred-tax shield / valuation-allowance reversal: a large DTA with
    # a VALUATION ALLOWANCE in a business that has TURNED profitable — the
    # allowance reverses (a one-off equity boost) and future earnings then
    # compound tax-free. The forensic, data-precise cousin of the NOL shell.
    _dtva_f17 = _ncol('deferred_tax_valuation_allowance')
    _dtva_pct_f17 = (_dtva_f17 / mcap.where(mcap > 0))
    df['arch_dta_reversal'] = (
        is_operating & _real_sector_f & (mcap > 0)
        & (_dtva_f17 > 0) & (_dtva_pct_f17 >= 0.15)   # material allowance available to reverse
        & ((s('op_margin', np.nan) > 0) | (_num('roce') > 0))  # turned profitable -> reversal becoming likely
        & ~((_ncol('fq_ni') + _ncol('fq_ni_p')) <= 0)       # (audit 3) SUSTAINED: cumulative net income over the last 8 quarters (TTM + year-ago TTM) positive where measured (an allowance reverses on a record, not one print)
        & _fx_coherent                                      # (audit 3) currency coherence (data validity)
        & _not_melting
    ).fillna(False).astype(int)

    # ---------- XR: EXCEPTIONAL RISK/REWARD (user request) ----------
    # Convexity through COINCIDENCE: independent floors under the price while
    # an upside engine runs. Each gate demands a rare conjunction — value,
    # growth and asset supports at once — so counts stay small by design.

    # XR1 — Paid to grow ('XR-NegEVGrowth'): cash covers the whole price (or
    # nearly) while the business GROWS with profitability present. The market
    # pays you to own the growth. The rarest, cleanest asymmetry in the book.
    df['arch_xr_neg_ev_growth'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &                              # net cash vs mcap is level-over-mcap
        ((cash_gt_ev > 0) | (net_cash_pct_c >= 0.80)) &
        # growth: the point YoY, or an AUDITED long streak (>=8 consecutive
        # quarters of filed revenue growth substitutes for a point estimate)
        (((rev_yoy_c >= 0.15) & (rev_yoy_c <= 1.0))
         | (_ncol('rev_yoy_streak_q') >= 8) | (_ncol('fq_rev_yoy_streak_m') >= 24)) &   # (audit 3) the streak leg global
        _profit_present &
        ((_ncol('op_margin') > 0) | (fcf_yield >= 0.03)) &   # (audit 3) a LEVEL of profitability, not bare presence
        (df.get('data_quality_flag', 0) == 0) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR2 — Triple floor ('XR-TripleFloor'): three INDEPENDENT downside
    # supports — a net-cash balance sheet, real earnings (latest or the 5-yr
    # Graham average), and a PAID dividend — while revenue still grows. Each
    # floor can fail alone; together the downside is triply covered and the
    # payout funds the wait.
    df['arch_xr_triple_floor'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &
        (net_cash_pct_c >= 0.40) &
        (_ncol('net_income_ttm') > 0) &                       # (audit 3) the earnings floor must be CURRENT (ni_avg is a lens, not a substitute)
        (_ncol('dividend_yield') >= 0.03) & ~(_ncol('evt_div_cut_2y') == 1) &   # (audit 3) paid and not cut
        (df.get('data_quality_flag', 0) == 0) &
        (rev_yoy_c >= 0.08) &
        (pb > 0) & (pb < 1.5) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR3 — Floor + inflection ('XR-FloorInflection'): Graham-and-catalyst.
    # Priced at/below a HARD asset floor (net-net, deep net cash, or the
    # hidden-asset gap) exactly as operating INFLECTION evidence appears
    # (a first-positive print, or acceleration with operating leverage), on a
    # beaten-down tape. Downside = the floor; upside = the re-rate.
    _xr_floor = ((ncav_pct >= 0.80) | (net_cash_pct_c >= 0.50)
                 | (_hidden_pct >= 0.40))
    _xr_inflect = ((ebitda_first_pos > 0) | (cfo_first_pos > 0)
                   | (fcf_first_pos > 0) | (ni_first_pos > 0)
                   | ((rev_accel > 0) & season_robust))
    df['arch_xr_floor_inflection'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &
        _xr_floor & _xr_inflect &
        beaten_down_any(0.30) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR4 — Quality at a crisis price ('XR-QualityAtCrisis'): MULTI-YEAR
    # proven quality (durable FCF years, audited book compounding, Lindy
    # ROIC, or positive 5-yr average owner earnings) marked at a CRISIS price
    # (>=40% off the 52-week or 5-year high) and cheap
    # on at least one lens. Quality that persists through its own drawdown is
    # the Templeton entry.
    _xr_quality = ((s('n_yrs_positive_fcf', 0) >= 4)
                   | (_ncol('equity_cagr_5y') >= 0.10)
                   | (roic_lindy >= 0.12)
                   | ((_ncol('oe_avg') > 0) & (_ncol('ni_avg') > 0))
                   # audited MULTI-YEAR persistence: 8+ consecutive filed
                   # quarters of NI or revenue growth (user: longer than 4Q)
                   | (_ncol('ni_yoy_streak_q') >= 8)
                   | (_ncol('rev_yoy_streak_q') >= 8))
    # (endpoint matrix) crisis price read on the weekly panel too: >= 40% below
    # the 52-week (panel-first) or the 5-year high; snapshot lenses stay.
    _xr_crisis = ((_num('pct_off_52w_high') <= -0.40)
                  | (_dd52 <= -0.40) | (_ts_hi260 <= 0.60))          # (audit 3) a drawdown from a former high only
    _xr_cheap = (((pb > 0) & (pb < 1.2))
                 | ((_ncol('p_e') > 0) & (_ncol('p_e') <= 10.0))
                 | (fcf_yield >= 0.10))
    df['arch_xr_quality_crisis'] = (
        is_operating & (mcap > 0) &
        _xr_quality & _xr_crisis & _xr_cheap &
        (ebitda_margin > -0.05) &                   # (audit) quality must PERSIST through the drawdown: a deeply-negative current EBITDA (MBLY -204%, LUCY -314%) is not "quality that held" on the strength of stale 4yr-FCF history
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)
    # (endpoint matrix, EXC) never-lost-money through the cycle, depth of the
    # crisis vs the 5y high and an intact TTM top line rank the members
    _SPIRITED.append('xr_quality_crisis')

    # ---------- XR x FORENSIC crossovers (user request) ----------
    # XR5 — Forensic floor under growth ('XR-ForensicFloorGrowth'): the floor
    # is INVISIBLE to standard screens — off-EV securities (hidden-asset gap),
    # retained earnings above 1.5x the price, or an over-depreciated asset
    # base — while the business on top GROWS. Convexity nobody screens for
    # because the support is not in standard metrics.
    _re_mc_x5 = (_ncol('retained_earnings') / _mc_ca.where(_mc_ca > 0))   # (gate-audit) currency-adjusted mcap (_mc_ca), matching the sibling multiple_gap
    _xr5_floor = ((_hidden_pct >= 0.50)
                  | ((_re_mc_x5 >= 1.5) & (_re_mc_x5 <= 5.0))   # (gate-audit) upper cap: raw RE/mcap>10x (ANG-PD, LGNDZ) is a scale/currency artifact, not a bargain — mirror the >=1.5 lower guard the sibling already carries
                  | ((_dna_loc > 0) & (_maint_capex >= 0)
                     & (_maint_capex <= 0.5 * _dna_loc) & ((_dna_loc / _rev_loc.where(_rev_loc > 0)) >= 0.05)))   # MAINTENANCE capex (TTM or 5yr avg, the higher), as F1
    df['arch_xr_forensic_floor_growth'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &
        _xr5_floor &
        (rev_yoy_c >= 0.10) & (rev_yoy_c <= 1.0) &
        _profit_present &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR6 — Headline-vs-forensic multiple gap ('XR-ForensicMultipleGap'): the
    # market prices the ACCOUNTING multiple (p_e >= 15 or meaningless) while
    # the FORENSIC earnings power — owner earnings (latest or 5-yr average) —
    # implies <= 6x. The spread between the two numbers is the upside, paid
    # out when the accounting catches up with the cash.
    _oe_best = _oe_loc.where(_oe_loc > 0).combine_first(_ncol('oe_avg').where(_ncol('oe_avg') > 0))
    _pe_head = _ncol('p_e')
    df['arch_xr_forensic_multiple_gap'] = (
        is_operating & (_mc_ca > 0) &
        _fx_coherent &
        ((_mc_ca / _oe_best) <= 6.0) &                 # forensic multiple: cheap...
        ((_mc_ca / _oe_best) >= 1.5) &                 # ...but a sub-1.5x "multiple" is a currency artifact, not a bargain (900920.SS at 0.2x)
        # (gate-audit) the thesis is a SPREAD (headline multiple >> forensic
        # owner-earnings multiple), so gate on the RATIO, not an absolute
        # headline P/E>=15 floor — a name at P/E 10 with a 2x forensic multiple
        # is a 5x gap the old floor wrongly excluded.
        (_pe_head.isna()
         | ((_pe_head > 0) & ((_pe_head / (_mc_ca / _oe_best)) >= 2.5))) &
        (_ncol('net_income_ttm') > 0) &                # real (not loss-masked) accounting
        ~(_ncol('fq_cfo_to_ni') < 1.0) &               # (audit 3) the wedge must show in CFO, not only in the reconstruction
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR7 — Harvest distribution ('XR-HarvestDistribution'): forensic evidence
    # of a CONTROLLED asset-base harvest — capex <= half of D&A (the base is
    # being converted to cash) — handed BACK to owners at >=6% combined
    # payout, priced below book as if terminally dying. The distribution
    # stream alone can return the price while the pessimism unwinds.
    _payout_x7 = (_ncol('dividend_yield').fillna(0) + _ncol('buyback_yield').fillna(0))
    df['arch_xr_harvest_distribution'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &
        (_dna_loc > 0) & (_maint_capex >= 0) & (_maint_capex <= 0.5 * _dna_loc) &  # (audit #5) harvest measured on MAINTENANCE capex (incl. 5yr avg), not a single collapsed TTM window (KSS/LKQ)
        (_payout_x7 >= 0.06) &
        (pb > 0) & (pb < 1.0) &
        ((_oe_loc > 0) | (_ncol('oe_avg') > 0)) &
        (rev_yoy_c >= -0.05) &                              # (audit 3) harvest, not decay
        ~(_ncol('shares_yoy') > 0.02) &                      # (audit 3) the payout is not funded by issuance
        _not_melting
    ).fillna(False).astype(int)

    # XR8 — Paydown yield ('XR-PaydownYield'): the FINANCING LINE proves a
    # massive annual transfer to capital providers (>=10% of mcap flowing out)
    # against a still-heavy debt load with stable EBITDA — the equity claim
    # accretes mechanically at a double-digit rate per year while priced as a
    # levered afterthought (the Weschler transfer, forensically verified).
    _paydown_y = (-_ncol('financing_cf_ttm') / _ncol('market_cap').where(_ncol('market_cap') > 0))
    df['arch_xr_paydown_yield'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &                              # (gate audit #2, completed) financing_cf vs mcap
        (_paydown_y >= 0.10) &
        ~(_ncol('fq_netdebt_change_pct_assets') > -0.03) &   # (audit 3) net debt actually falling where the quarterly path is observed
        ~(_ncol('shares_yoy') > 0.02) & (fcf_yield > 0) &     # (audit 3) operations-funded, not equity-funded
        (_nde_meaningful > 0) &                               # (user) debt exists to pay down (no fixed band)
        (ebitda_ttm_v > 0) &
        ((ebitda_yoy_v >= -0.05) | (ebitda_inflection > 0)) &
        _not_melting
    ).fillna(False).astype(int)

    # XR10 — Clean net-net, earning and paying ('XR-CleanNetNet'): the
    # concepts-hardened Graham trifecta — NCAV (now NET of preferred and
    # minority interests) covering the WHOLE price, positive earnings power
    # on the Graham average (or latest), and management PAYING owners while
    # you wait. Each leg is audited-basis; together the downside is a
    # liquidation floor that pays a coupon.
    df['arch_xr_clean_net_net'] = (
        is_operating & (mcap > 0) &
        _fx_coherent &
        (ncav_pct >= 1.0) &
        ((_ncol('ni_avg') > 0) | (_ncol('net_income_ttm') > 0)) &
        (((_ncol('dividend_yield') >= 0.02) & ~(_ncol('evt_div_cut_2y') == 1))
         | ((_ncol('buyback_yield') > 0) & ((_ncol('net_buyback_ttm') > 0) | (_ncol('shares_yoy') < 0)))) &   # (audit 3) paid and not cut, or a corroborated buyback
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR11 — Self-funded compounding deployer ('XR-CompoundingDeployer'):
    # high AUDITED incremental returns on capital actually DEPLOYED
    # (roiic_lindy under the positive-deployment rule), financed internally
    # (financing line flat/negative — no dilution, no borrowing binge),
    # revenue still compounding, and the market pricing it at an ordinary
    # multiple. The rare growth engine whose fuel is its own cash.
    df['arch_xr_compounding_deployer'] = (
        is_operating & (mcap > 0) &
        (roic_lindy >= 0.12) &
        (_ncol('roiic_lindy') >= 0.20) &
        (_ncol('financing_cf_ttm') <= 0) &
        ~((_ncol('fq_capex_to_da') < 1.0) & ~(_ncol('fq_acq_pct_assets') > 0)) &   # (audit 3) deploying now (capex above D&A or acquiring), where observed
        ((_ncol('rev_yoy_streak_q') >= 4) | (rev_yoy_c >= 0.10)) &
        (((_ncol('ev_ebit') > 0) & (_ncol('ev_ebit') <= 14))
         | ((_ncol('p_e') > 0) & (_ncol('p_e') <= 18))
         | ((_ncol('evsg') > 0) & (_ncol('evsg') <= 0.40))) &   # (gate-audit) growth-adjusted fair price, matching sibling engines (reusable_assembler/baron) — a top high-ROIIC compounder at 16-20x EV/EBIT was barred by the raw multiple ceiling alone
        ~(_ncol('shares_yoy') > 0.02) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- FINANCING FRAGILITY (Baron prehistory: the Motient lesson) --
    # "A large future market is insufficient when the investor's claim cannot
    # survive the financing PATH required to reach it." Growth that depends on
    # CONTINUOUS external capital with a weak balance sheet is the lineage the
    # 2000-02 selection event destroyed (Motient/NTL/telecom). Encoded as a
    # DEMOTION mask applied to the growth XR gates so refinancing-fragile
    # expansion is never flagged as exceptional risk/reward. Fragile =
    # burning cash (negative FCF) AND raising outside capital or diluting,
    # AND without the balance sheet to survive a closed capital market.
    _ff_burn = (fcf_yield < 0)
    _ff_raise = ((_ncol('financing_cf_ttm') > 0) | (_ncol('shares_yoy') > 0.05))
    _ff_weak = (((_ncol('interest_coverage') < 3) & _ncol('interest_coverage').notna())
                | (nde >= 3.0) | ((net_cash_pct_c < 0) & (nde >= 2.0)))
    _financing_fragile = (_ff_burn & _ff_raise & _ff_weak).fillna(False)
    # surfaced as a WARN flag (not an opportunity) — a financing-fragile
    # grower is exactly the Motient trap the record selected against
    df['financing_fragile_flag'] = _financing_fragile.astype(int)
    # QUALITY-OF-EARNINGS WARNING (SBC pollution): where stock-based comp is a
    # large share of revenue, "adjusted" EBITDA/FCF overstate true economics
    # (SBC is a real, dilutive cost added back to flatter cash). A warning
    # column OUTSIDE the arch_ namespace — it never boosts density, it marks
    # names whose apparent cash generation is SBC-inflated.
    df['sbc_polluted_flag'] = (_ncol('sbc_pct_revenue') >= 0.15).fillna(False).astype(int)

    # (user) ONE-OFF / DISCHARGE-GAIN EARNINGS marker. Net income ABOVE EBITDA
    # is anomalous — normally D&A, interest and tax pull NI below EBITDA — so
    # NI > EBITDA means a NON-OPERATING gain (fresh-start debt discharge, asset
    # sale, tax benefit, equity-method income) inflated reported earnings above
    # the operating cash proxy. That makes a 1/P·E cheapness read a mirage
    # (FriendTimes: p_e 3.8 but NI 7.4x EBITDA). A warning column OUTSIDE the
    # arch_ namespace — it never boosts density; it MARKS the names whose low
    # P/E is a one-off, so they can be isolated rather than screened as cheap.
    _ni_oe = _ncol('net_income_ttm'); _eb_oe = _ncol('ebitda_ttm')
    df['earnings_oneoff_flag'] = (
        (_eb_oe > 0) & (_ni_oe > 1.1 * _eb_oe)
    ).fillna(False).astype(int)

    # ---------- XR12-XR16: VIOLENT-RERATING ENGINES (user request) ----------
    # Each models a FAMOUS accounting nuance that forensic readers caught
    # before the market, producing some of the most violent re-ratings on
    # record. The tell is measurable; the market prices the polluted or
    # lagging headline; the re-rate is mechanical when the accounting
    # catches up.

    # XR12 — Float compounding ('XR-FloatCompounding'): customers PREPAY
    # (deferred revenue/negative working capital float) so cash collections
    # run ahead of GAAP revenue — the SaaS/Ryanair engine where the P&L
    # understates bookings. Tell: deep negative NWC, CFO far above NI
    # persistently, revenue now ACCELERATING while the market still prices
    # the trailing P&L (P/E dear or meaningless) — yet on collected CASH
    # the price is ordinary.
    _nwc_x12 = _ncol('net_working_capital')
    _cfo_ni_x12 = (_ncol('cfo_ttm') / _ncol('net_income_ttm')).where(_ncol('net_income_ttm') > 0)
    # TRUE float tell (rigour B.i): a material DEFERRED-REVENUE balance
    # (customers prepaid) — the actual SaaS/insurance/Ryanair float —
    # rather than the NWC proxy alone (which also flags stretched payables).
    # Deferred revenue >= 10% of revenue is a real prepayment book. Where the
    # audited balance is absent, the negative-NWC proxy still qualifies (so
    # non-EDGAR names are not excluded), corroborated as before.
    _defrev_x12 = _ncol('deferred_revenue')
    _defrev_ratio12 = (_defrev_x12 / _rev_loc).where(_rev_loc > 0)
    _float_exists12 = ((_defrev_ratio12 >= 0.10) | (_defrev_ratio12.isna() & (_nwc_x12 < 0)))
    df['arch_xr_float_compounding'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        _float_exists12 &                                  # the float exists (deferred-rev or NWC)
        ~(_ncol('fq_defrev_growth_minus_rev') < 0) & ~(_ncol('fq_ccc') > 0) &   # (audit 3) the float is not shrinking / the cycle not positive, where observed
        ~(_ncol('fq_sbc_to_cfo') > 0.30) &                                     # (audit 3) not an SBC add-back
        ((_cfo_ni_x12 >= 1.3) | (_ncol('cash_conversion') >= 1.2)) &
        ~(_cfo_ni_ya < 1.0) &                              # PERSISTENTLY: CFO above NI a year ago too, where measured
        ((rev_accel > 0) | (rev_yoy_c >= 0.15)) &          # bookings engine turning
        ((_ncol('p_e') >= 20) | _ncol('p_e').isna()) &     # headline looks dear/meaningless
        ((_ncol('market_cap') / _ncol('cfo_ttm').where(_ncol('cfo_ttm') > 0)) <= 15) &
        ~(_ncol('roic_after_sbc').notna() & (_ncol('roic_after_sbc') < 0)) &  # (gate-audit) exclude SBC-flattered SaaS (negative after-SBC returns)
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR13 — Big-bath rebound ('XR-BigBathRebound'): a massive one-off
    # writedown (the Renault-class unusual item) has POLLUTED the trailing
    # line — EBITDA-with-unusuals sits far below the multi-year normalized
    # base while OPERATING cash stays healthy (baths are non-cash). The
    # market prices the bath year; the re-rate is mechanical as the unusual
    # rolls off the trailing window. Basis machinery: the same-basis
    # normalized pair built after the RNO.PA fix.
    _nrm_eb_x13 = _midcyc_ebitda   # margin-based mid-cycle (inflation-neutral)
    _ev_nrm_x13 = (_ncol('enterprise_value') / _nrm_eb_x13.where(_nrm_eb_x13 > 0))
    df['arch_xr_bigbath_rebound'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_nrm_eb_x13 > 0) &
        ((ebitda_ttm_v < 0.6 * _nrm_eb_x13) | (_ncol('net_income_ttm') < 0)) &
        (_ncol('cfo_yield') > 0) &                          # the bath was non-cash
        ((_ncol('net_income_ttm') >= 0)                     # (audit 3) ...and OBSERVABLE: CFO exceeds the loss by half its size
         | ((_ncol('cfo_ttm') - _ncol('net_income_ttm')) >= 0.5 * _ncol('net_income_ttm').abs())) &
        (_ev_nrm_x13 > 0) & (_ev_nrm_x13 <= 6.0) &          # cheap on the NORMAL base
        beaten_down_any(0.30) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR14 — Depreciation cliff ('XR-DepreciationCliff'): the asset base is
    # nearly fully depreciated (implied D&A large against a small remaining
    # net PP&E) while replacement spend stays low — reported earnings are a
    # coiled spring that RELEASES mechanically as charges roll off, and the
    # cash was real all along. Priced on the depressed accounting earnings.
    _ppe_x14 = _ncol('ppe_net')
    _dna_ppe_x14 = (_dna_loc / _ppe_x14.where(_ppe_x14 > 0))
    df['arch_xr_depreciation_cliff'] = (
        is_operating & (_mc_ca > 0) & _fx_coherent &
        (_dna_loc > 0) & (_dna_ppe_x14 >= 0.35) &           # < ~3yr of book life left
        ~(_ncol('goodwill_intangibles_pct_assets') > 0.15) &   # (audit 3) depreciation, not acquired-intangible amortisation (that is amortization_mask)
        (_maint_capex >= 0) & (_maint_capex <= 0.6 * _dna_loc) &   # replacement spend low on MAINTENANCE capex, not one collapsed TTM window
        (_oe_loc > 0) & ((_mc_ca / _oe_loc) <= 10.0) &      # cheap on the true cash take
        ((_ncol('p_e') >= 12) | (_ncol('p_e').isna() & (_ncol('cfo_yield') > 0))) &   # dear/meaningless on polluted E (audit 3: a real loss is not a cliff)
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR15 — Working-capital normalization ('XR-WCNormalization'): a
    # one-cycle inventory/receivables GLUT crushed reported FCF (screens
    # flee the "cash burn") while margins and demand stay intact — the
    # Kohl's-cycle tell. When the working capital unwinds, FCF snaps back
    # violently. Entry: broken FCF optics, UNBROKEN business.
    _fy_x15 = _num('fcf_yield')
    df['arch_xr_wc_normalization'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_fy_x15 < 0.02) &                                  # FCF optics broken...
        (_num('earnings_yield') >= 0.08) &                  # ...but earnings power real
        (((_num('cfo_yield') < _num('earnings_yield') - 0.03)   # (audit 3) operating cash short of earnings — a WC fact, not CFO/EBITDA
          & ((_ncol('fq_dio') - _ncol('fq_dio_p') > 0) | (_ncol('fq_dso') - _ncol('fq_dso_p') > 0) | (_ncol('fq_inv_vs_cogs') > 0)))
         # ...or the GLUT itself, observed in the quarterly balance sheets:
         # inventory days up >= 15 or receivable days up >= 10 YoY, or
         # inventory outgrowing COGS by >= 15pp (the mechanism, not a proxy)
         | ((_ncol('fq_dio') - _ncol('fq_dio_p')) >= 15)
         | ((_ncol('fq_dso') - _ncol('fq_dso_p')) >= 10)
         | (_ncol('fq_inv_vs_cogs') >= 0.15)) &
        (ebitda_ttm_v > 0) &
        (rev_yoy_c >= -0.05) &                              # demand intact
        (_num('gross_margin_delta_yoy') >= -0.03) &         # margins intact
        (nde < 3.0) &                                       # survives the cycle
        ~(_ncol('fq_beneish_risk_flag') == 1) & ~(_ncol('fq_receivables_divergence_flag') == 1) &   # (audit 3) a DSO-led glut is the red flag, not the setup
        (df.get('data_quality_flag', 0) == 0) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR16 — Amortization mask ('XR-AmortizationMask'): the serial-acquirer
    # engine (Constellation/Heico class) — GAAP EPS is crushed by acquired-
    # intangible amortization that has NO cash cost, so owner earnings run
    # far above NI exactly where the intangible base is heavy. The market
    # prices the masked EPS; the cash compounds regardless.
    df['arch_xr_amortization_mask'] = (
        is_operating & (_mc_ca > 0) & _fx_coherent &
        (_ncol('goodwill_intangibles_pct_assets') >= 0.30) &   # the mask exists
        (_ni_ca > 0) & (_oe_ratio >= 1.5) &                    # OE >> NI through the mask
        (fcf_yield >= 0.07) &                                  # cash confirms
        ((_ncol('p_e') >= 15) | _ncol('p_e').isna()) &         # priced on masked EPS
        ((_mc_ca / _oe_loc.where(_oe_loc > 0)) <= 12.0) &      # ordinary on OWNER earnings
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- XR17-XR20: ONCE-IN-A-LIFETIME CLASSES (user request) ----------
    # The rarest, most violent asymmetries on record, each with a measurable
    # audited tell. Counts are meant to be TINY.

    # XR17 — Treasury cannibal below cash ('XR-CannibalBelowCash'): the
    # market cap sits BELOW net cash while management BUYS BACK stock —
    # every repurchased share is bought with the company's own cash at a
    # discount to that cash, mechanically accreting value per share. The
    # Teledyne/2022-China-ADR class; among the rarest trades that exist.
    df['arch_xr_cannibal_below_cash'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (net_cash_pct_c >= 1.0) &                           # price fully covered by net cash
        (_ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0')) >= 0.01) &   # (audit 3/4) a MATERIAL buyback (>= 1% of mcap): EDGAR yield, else the global FY repurchase yield
        ((_ncol('net_buyback_ttm') > 0) | (_ncol('shares_yoy') < 0)) &  # (audit) ...CORROBORATED by real $ retired or actual shrinkage — a bare buyback_yield at 0% shrinkage is a creation/redemption artifact (RVP/JVA/ETNs)
        ~(_ncol('shares_yoy') > 0.02) &                     # and NOT net-diluting (SBC-offset buyback illusion)
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)
         | (_ncol('cfo_yield') > 0)) &                      # a real business attached
        _not_melting
    ).fillna(False).astype(int)

    # XR18 — Double trough ('XR-DoubleTrough'): a TROUGH MULTIPLE on TROUGH
    # EARNINGS — price near multi-year lows, EV cheap against the MID-CYCLE
    # (normalized) base, and current earnings sitting BELOW that base (so
    # the cheapness is not peak-margin illusion), with survival assured.
    # Two discounts compound: the multiple re-rates AND earnings mean-revert.
    _nrm18 = _midcyc_ebitda   # margin-based mid-cycle
    _evn18 = (_ncol('enterprise_value') / _nrm18.where(_nrm18 > 0))
    # (user rule) no fixed coverage / leverage number on the positive-EBITDA
    # trough: survival there is _not_melting; leverage and coverage are weights
    _surv18 = pd.Series(True, index=df.index)
    # (user) a DOUBLE TROUGH is at its highest asymmetry when trailing EBITDA
    # is NEGATIVE while the MID-CYCLE base is strongly positive — the deepest
    # trough. The old `ebitda>0` floor excluded all of those (0 of 263 firers
    # were negative-EBITDA). Remove it: admit trailing EBITDA at OR BELOW the
    # trough including negative, valued on the mid-cycle base. For the
    # negative-EBITDA case, HARD survivability (net cash or genuinely low
    # leverage) does the work _not_melting otherwise would — at a real trough
    # the name IS "melting" on trailing metrics (that is the entry), so the
    # balance-sheet floor, not the melt gate, is the correct protection.
    # (endpoint matrix) the earnings trough also measured through the cycle:
    # the current operating margin >= 5 points under its own 8-FY median.
    _below_midcyc_opm = ((s('op_margin', np.nan) <= _ncol('tc_med_opm') - 0.05)
                         & (_ncol('tc_years') >= 5)).fillna(False)
    _at_trough_18 = (ebitda_ttm_v <= 0.85 * _nrm18) | _below_midcyc_opm   # includes negative trailing
    # a negative-EBITDA trough is burning cash NOW, so it needs a genuine
    # FORTRESS to survive to mean-reversion — a real net-cash cushion (>=20% of
    # mcap) or very low leverage — not merely "not net-debt" (a 2%-net-cash
    # burner has no runway).
    # (user) the protection is NET CASH: a negative-EBITDA trough must hold
    # more cash than debt (a sign, not an invented size); HOW MUCH net cash,
    # and debt / assets, are weights in the spirit score
    _deep_surv18 = (net_cash_pct_c >= 0)
    df['arch_xr_double_trough'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ((_num('pct_off_52w_high') <= -0.50)
         | (_num('price_pct_of_5y_range') <= 0.15)
         | (_dd52 <= -0.50) | (_ts_hi260 <= 0.50)) &      # (endpoint matrix) trough price on the weekly panel (5y former high)
        (_evn18 > 0) & (_evn18 <= 5.0) &                    # cheap on MID-CYCLE earnings
        _at_trough_18 &                                     # earnings AT/BELOW the trough (incl. negative)
        # positive-EBITDA trough: standard survivability + not-melting.
        # negative-EBITDA (deep) trough: HARD balance-sheet survivability
        # instead (the melt gate would bar a trough by design).
        (((ebitda_ttm_v > 0) & _surv18 & _not_melting)
         | ((ebitda_ttm_v <= 0) & _deep_surv18)) &
        ~(_ncol('shares_yoy') > 0.05)
    ).fillna(False).astype(int)

    # XR19 — Forced-seller dislocation ('XR-ForcedSeller'): the price
    # COLLAPSED >=40% in a year in which the BUSINESS GREW on both lines
    # with no dilution — a seller-driven, not business-driven, mark
    # (index deletions, fund liquidations, spin-off orphans). Buying a
    # growing business from someone who must sell at any price.
    df['arch_xr_forced_seller'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_ncol('revenue_ttm_usd') >= 10e6) &        # (audit) revenue-base floor: the "business grew" leg is pure noise on a $43K micro (WESTLEIRES.BO +185%). Sibling leverage_detonation already carries this.
        # (endpoint matrix, PROXY) the collapse on the weekly total-return
        # panel (fresh, dividend-adjusted) where present; the quote-time
        # price_yoy is only the fallback
        (_ts_r52.fillna(_num('price_yoy')) <= -0.40) &
        (rev_yoy_c >= 0.05) &
        ((ebitda_yoy_v >= 0) | (_ncol('fqx_ebit_ttm_g') >= 0)) &   # (audit 3) the profit line grew too — no NI>0 escape
        ~(_ncol('ts_r13') < -0.05) &                               # (audit 3) the selling has cleared: entry follows the calendar, not the collapse
        ~(_ncol('shares_yoy') > 0.02) &
        _not_melting
    ).fillna(False).astype(int)
    # (endpoint matrix, LEG->EXC) a NAMED forced seller where observable: the
    # 13F ownership exodus in the latest quarter ranks the members
    _SPIRITED.append('xr_forced_seller')

    # XR20 — Operating-leverage detonation ('XR-LeverageDetonation'): the
    # breakeven CROSSING with high drop-through — losses just flipped (or
    # are one step from flipping) while incremental margins run >=35% on
    # 20%+ growth. Historically the most violent PERCENTAGE re-ratings
    # occur exactly here: each new revenue dollar is suddenly mostly
    # profit, and trailing screens still price the loss-maker.
    df['arch_xr_leverage_detonation'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ~_financing_fragile &                              # Motient guard
        ((ebitda_first_pos > 0) | (fcf_first_pos > 0)
         | ((_num('fcf_eta_quarters') > 0) & (_num('fcf_eta_quarters') <= 2))) &
        ((_num('incremental_ebitda_margin').between(0.35, 1.0))    # (audit 3) > 100% is a loss unwinding, not drop-through
         | (_fqx_inc >= 0.35)) &          # (endpoint matrix) drop-through on the date-matched TTM too
        (rev_yoy_c >= 0.20) & (rev_yoy_c <= 1.5) &
        ((_ncol('p_s') <= 3.0) | (_ncol('ev_sales') <= 3.0)) &
        (_ncol('revenue_ttm_usd') >= 10e6) &                # not a base-effect shell
        ~(_ncol('shares_yoy') > 0.05) &                      # (audit 3) the siblings' dilution bar
        _not_melting
    ).fillna(False).astype(int)

    # XR22 — Baron-style compounder ('XR-BaronCompounder', user request):
    # Ron Baron's engine — FOUNDER/OWNER-led businesses with DECADE-length
    # growth durability, reinvesting so heavily that current earnings are
    # suppressed (the growth is bought through the P&L or capex), balance
    # sheet built to survive the journey, bought at a growth-ADJUSTED fair
    # price (never a cheap-screen price), while still small enough for the
    # runway to matter. Duration evidence is AUDITED (12-quarter positive
    # share / long streaks), not a single hot year.
    _ins_x22 = _ncol('insider_ownership_pct')
    _gm_x22 = s('gross_margin', np.nan)
    _om_x22 = s('op_margin', np.nan)
    df['arch_xr_baron_compounder'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ~_financing_fragile &                              # Motient guard
        (_ins_x22 >= 0.10) &                                  # owner-operator
        ((_ins_x22 < 0.60) | (_ncol('net_buyback_ttm') > 0) | (s('insider_buy_flag', 0) == 1)) &   # (audit 3) controlled-sub cap unless aligned
        ((_ncol('rev_yoy_pos_share_12q') >= 0.75)             # audited duration...
         | (_ncol('rev_yoy_streak_q') >= 6)
         | (_ncol('rev_3y_cagr') >= 0.15)) &
        (rev_yoy_c >= 0.12) &                                 # ...still alive now
        (((_gm_x22 - _om_x22) >= 0.15) & (_gm_x22 >= 0.35)    # reinvesting through P&L
         | (_ncol('capex_intensity') >= 0.08)) &              # or building ahead
        (((_ncol('evsg') > 0) & (_ncol('evsg') <= 0.40))      # growth-adjusted fair price
         | ((_ncol('p_s') > 0) & (_ncol('p_s') <= 6.0))) &
        (_ncol('revenue_ttm_usd') >= 25e6) &
        (_ncol('market_cap_usd') <= 25e9) &                   # runway still open
        ~(_ncol('roic_after_sbc').notna() & (_ncol('roic_after_sbc') < 0)) &  # (gate-audit) reinvestment SUPPRESSES current earnings, but NEGATIVE after-SBC returns is value destruction, not reinvestment — exclude the SBC-flattered ones
        ~(_ncol('shares_yoy') > 0.08) &
        _not_melting
    ).fillna(False).astype(int)

    # XR23 — Insider capitulation buy ('XR-InsiderCapitulation'): the people
    # with the MOST information CLUSTER-BUY their own crash — >=40% off the
    # high while demand and margins hold. Historically among the highest
    # hit-rate "once" signals: outside sellers capitulating into the hands
    # of the operators.
    df['arch_xr_insider_capitulation'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (s('insider_cluster_buy_flag', 0) >= 1) &
        ~(_ncol('insider_distinct_buyers') < 2) &            # (audit 3) a cluster, where the buyer count is observed
        beaten_down_any(0.40) &
        (rev_yoy_c >= -0.10) &                                # business not collapsing
        ((s('gross_margin_delta_yoy', np.nan) >= -0.03)
         | (_oe_loc > 0) | (_ncol('oe_avg') > 0)) &           # economics intact
        ((ebitda_margin > -0.10) | (fcf_yield > 0)) &         # (audit) current-economics floor: an insider cluster-buy does not redeem a -130%-margin cash bonfire (FLY, NEOV)
        _not_melting
    ).fillna(False).astype(int)

    # XR24 — Reusable assembler ('XR-ReusableAssembler', Baron Generation III,
    # the TERMINAL phenotype). The decisive variable of Baron's forty-year
    # selection: how much of the PREVIOUS assembly is reused in the next one.
    # The forensic tell of reuse is operating leverage from a built substrate:
    # incremental margins running ABOVE the average margin (each new dollar
    # mostly profit because data/software/brand/installed-base is already
    # paid for), an ASSET-LIGHT base (low capex intensity, or an intangible
    # substrate), growth that is SELF-FUNDED (no external-capital dependence,
    # no dilution — the module that SURVIVED 2000-02), durable, and bought at
    # a growth-adjusted (not cheap-screen) price. CoStar/Gartner/FactSet/
    # MSCI/IDEXX class.
    _inc_x24 = _num('incremental_ebitda_margin')
    # (endpoint matrix) + the TTM incremental EBIT margin vs the EBIT margin
    _fqx_inc24 = _fqx_inc
    _reuse_x24 = (((_inc_x24 >= 0.30) & (_inc_x24 > ebitda_margin))     # marginal >> average
                  | ((_fqx_inc24 >= 0.30) & (_fqx_inc24 > s('op_margin', np.nan))))
    _assetlite_x24 = ((_ncol('capex_intensity') <= 0.06)
                      | (_ncol('goodwill_intangibles_pct_assets') >= 0.25))
    _fin_cf_x24 = _ncol('financing_cf_ttm').where(_ncol('financing_cf_ttm').notna(), _ncol('fq_financing_cf'))
    _selffund_x24 = (_fin_cf_x24 <= 0).fillna(False)                 # (audit 3) observed, not vacuous on missing data
    df['arch_xr_reusable_assembler'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ~_financing_fragile &
        _reuse_x24 & _assetlite_x24 & _selffund_x24 &
        (ebitda_margin >= 0.15) &
        ((_ncol('rev_yoy_streak_q') >= 6) | (_ncol('rev_3y_cagr') >= 0.12)
         | (rev_yoy_c >= 0.12)) &
        (((_ncol('evsg') > 0) & (_ncol('evsg') <= 0.40))
         | ((_ncol('ev_ebit') > 0) & (_ncol('ev_ebit') <= 22))) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR25 — Asset, owner, catalyst ('XR-AssetOwnerCatalyst', Baron
    # Generation I, the original primitive: the 14-year-old's Monmouth bank
    # trade). A completed object priced BELOW its reproduction/realisable
    # value, a credible OWNER-operator who can build the next stage, and a
    # CATALYST already in motion (an inflection, capital return, or a
    # restructuring/harvest) — the special-situation ancestor of the whole
    # method, before compounding was ever the plan.
    # DEEP asset floor (a real discount to realisable value, not merely
    # sub-book) and a catalyst ALREADY IN MOTION (a first-positive
    # inflection, an accelerating operating-leverage turn, or an active
    # buyback) — harvest alone is too common to count as a catalyst here.
    _av_x25 = (((pb > 0) & (pb < 0.8)) | (net_cash_pct_c >= 0.40)
               | (ncav_pct >= 0.80) | (_hidden_pct >= 0.40))
    _cat_x25 = ((ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0)
                | (ni_first_pos > 0) | ((rev_accel > 0) & season_robust)
                | (_ncol('buyback_yield') >= 0.02) | (_ncol('net_buyback_ttm') > 0)
                # (endpoint matrix, LEG) DATED catalysts: EPS turned positive
                # on the quarterly TTM, or a fresh SC 13D (<= 12 months,
                # sub-$2B so the hit is about the name, not filed by it)
                | (_ncol('fqx_eps_turned') == 1) | _13d_recent)
    df['arch_xr_asset_owner_catalyst'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_ncol('insider_ownership_pct') >= 0.15) &         # strong owner-operator
        ((_ncol('insider_ownership_pct') < 0.60) | (_ncol('net_buyback_ttm') > 0) | (s('insider_buy_flag', 0) == 1)) &   # (audit 3) >= 60% is a controlled sub unless alignment is revealed
        _av_x25 & _cat_x25 &
        beaten_down_any(0.25) &                            # entered on a DISLOCATION
        (((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0))
         | (_ncol('cfo_yield') > 0)) &                     # a real business, not a shell
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR26 — Pre-scale margin ('XR-PreScaleMargin', user request): catch the
    # name BEFORE it re-rates, while its QUALITY (real unit economics, shown
    # in a fat GROSS margin) has not yet flowed into the OPERATING line
    # because the fixed-cost base is not yet covered — the gross-to-operating
    # GAP is the latent operating leverage the market has not priced. The
    # scaling is proven to be REAL, not hoped-for, by either a high
    # incremental drop-through (each marginal dollar mostly profit, so the
    # fixed base IS being absorbed) OR margins already beginning to inflect;
    # and revenue is growing fast enough to spread the base. Priced on the
    # thin TRAILING margin (modest EV/gross-profit), so the re-rate to the
    # scaled margin is still ahead.
    _gm_x26 = s('gross_margin', np.nan)
    _om_x26 = s('op_margin', np.nan)
    _gap_x26 = (_gm_x26 - _om_x26)
    _inc_x26 = _num('incremental_ebitda_margin')
    _scaling_x26 = (((_inc_x26 >= 0.30) & (_inc_x26 > ebitda_margin))   # marginal >> average
                    | (_num('op_margin_delta_yoy') > 0.02)             # op margin turning up
                    | ((_num('ebitda_margin_delta_yoy') > 0.02)        # ...through EBITDA too
                       & (_num('ebitda_margin_delta_yoy') <= 0.30)))
    df['arch_xr_pre_scale_margin'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ~_financing_fragile &                             # Motient guard (a growth gate)
        (_gm_x26 >= 0.40) &                               # real product economics...
        (_om_x26 <= 0.12) & (_om_x26 >= -0.15) &          # ...not yet in the operating line, but not a bonfire (audit 3)
        (_gap_x26 >= 0.30) &                              # a heavy fixed base to leverage
        _scaling_x26 &                                    # the gap is provably closing
        (rev_yoy_c >= 0.15) & (rev_yoy_c <= 1.5) &        # spreading the base, not a pop
        (((_ncol('ev_gross_profit') > 0) & (_ncol('ev_gross_profit') <= 8.0))
         | ((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 4.0))) &  # not yet re-rated
        (_ncol('revenue_ttm_usd') >= 15e6) &              # not a base-effect shell
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- XR27-XR28: LATENT + ASYMMETRIC (user request) ----------
    # The LATENT counterpart of the XR inflection theses: catch the setup one
    # stage EARLIER — while the trajectory is improving but has NOT yet
    # crossed into the confirming print — which is dangerous UNLESS floored.
    # Each requires a hard downside FLOOR (net cash, NCAV, deep book
    # discount, or hidden assets) so being early is ASYMMETRIC: the option
    # on the turn is bought below a liquidation/asset support.
    _floor_lat = ((net_cash_pct_c >= 0.20) | (ncav_pct >= 0.50)
                  | ((pb > 0) & (pb < 0.80)) | (_hidden_pct >= 0.30)
                  | (cash_pct_mcap_v >= 0.50))

    # XR27 — Latent inflection under a floor ('XR-LatentInflectionFloor'):
    # returns/margins/cash are IMPROVING toward positive but have not yet
    # crossed (so no first_positive has fired) — pre-recognition — while the
    # floor protects the wait. The early, floored version of XR3.
    _improving_lat = (((_num('roce_delta_yoy') > 0) & (_num('roce') <= 0.05))
                      | ((_num('op_margin_delta_yoy') > 0.02) & (s('op_margin', np.nan) <= 0.06))
                      | ((_num('ebitda_margin_delta_yoy') > 0.02)
                         & (_num('ebitda_margin_delta_yoy') <= 0.30) & (ebitda_margin <= 0.10))
                      | ((_num('fcf_eta_quarters') > 0) & (_num('fcf_eta_quarters') <= 5)
                         & (_num('fcf_yield') < 0)))
    _not_yet_crossed = (~((ebitda_first_pos > 0) | (cfo_first_pos > 0)
                          | (fcf_first_pos > 0) | (ni_first_pos > 0))
                        & ~(_ncol('fqx_eps_turned') == 1) & ~(_ncol('fmp_dyn_opinc_turned_positive') == 1)   # (audit 3) dated turns count
                        & ((_ncol('op_margin') <= 0) | (fcf_ttm_v < 0)))                                     # still below the line NOW
    df['arch_xr_latent_inflection_floor'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ~_financing_fragile &
        _improving_lat & _not_yet_crossed &
        _floor_lat &                                      # asymmetric floor
        (rev_yoy_c >= -0.05) &                            # business not collapsing
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR28 — Latent bath under a floor ('XR-LatentBathFloor'): a one-off has
    # DEPRESSED the trailing line (EBITDA below its normalized base, or NI
    # negative) but operating CASH is still positive (the hit was non-cash)
    # AND a hard asset/cash floor covers the price — the free option on the
    # normalization, floored. The asymmetric, pre-rebound version of XR13:
    # here the FLOOR does the work XR13 got from a beaten-down tape, so it
    # fires before the drawdown is even complete.
    _nrm28 = _midcyc_ebitda   # margin-based mid-cycle
    _evn28 = (_ncol('enterprise_value') / _nrm28.where(_nrm28 > 0))
    # a HARD floor for XR28 (cash/NCAV/hidden — not sub-book alone, which is
    # ubiquitous among depressed cyclicals) so the option is genuinely floored
    _hardfloor_28 = ((net_cash_pct_c >= 0.30) | (ncav_pct >= 0.60)
                     | (_hidden_pct >= 0.40) | (cash_pct_mcap_v >= 0.50))
    df['arch_xr_latent_bath_floor'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_nrm28 > 0) &
        ((ebitda_ttm_v < 0.7 * _nrm28) | (_ncol('net_income_ttm') < 0)) &  # depressed line
        (_evn28 > 0) & (_evn28 <= 8.0) &                  # cheap on the RECOVERED base
        (_num('cfo_yield') > 0) &                         # the hit was non-cash
        ((_ncol('net_income_ttm') >= 0)                   # (audit 3) the bath must be OBSERVABLE: CFO exceeds the loss by half its size
         | ((_ncol('cfo_ttm') - _ncol('net_income_ttm')) >= 0.5 * _ncol('net_income_ttm').abs())) &
        (df.get('data_quality_flag', 0) == 0) &
        _hardfloor_28 &                                   # asymmetric HARD floor
        (rev_yoy_c >= -0.10) &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- XR29-XR31: MORE ACCOUNTING NUANCE (user request) ----------

    # XR29 — Cyclical trough asset ('XR-CyclicalTrough', user request: the
    # sub-book depressed cyclical is its own thesis). A CYCLICAL business at
    # a genuine ASSET discount (below book) with earnings DEPRESSED against
    # its own mid-cycle (normalized) base — bought where the physical asset
    # base floors the downside and the cycle mean-reverts the earnings. Not
    # a compounder; a mean-reversion asset play priced for permanent trough.
    _cyc_sectors = {'Materials', 'Energy', 'Industrials',
                    'Consumer Discretionary'}
    _nrm29 = _midcyc_ebitda   # margin-based mid-cycle
    df['arch_xr_cyclical_trough'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        sector.isin(_cyc_sectors) &
        (pb > 0) & (pb < 1.0) &                            # asset discount
        (_nrm29 > 0) & (ebitda_ttm_v < 0.75 * _nrm29) &    # earnings BELOW mid-cycle (INCLUDING negative — the deepest trough)
        ((_ncol('enterprise_value') / _nrm29.where(_nrm29 > 0)) <= 7.0) &  # cheap on normal
        ~(_ncol('shares_yoy') > 0.05) &
        # (gate-audit) the deepest, highest-asymmetry troughs run NEGATIVE
        # trailing EBITDA against a strong mid-cycle base — the same lesson
        # applied to double_trough, un-applied here (it excluded ~213 CFO-
        # positive survivable deep troughs). Positive-EBITDA trough keeps the
        # standard viability + not-melting; the negative-EBITDA (deep) trough
        # substitutes a HARD balance-sheet fortress (the pb<1 asset discount +
        # net cash / very low leverage), since at a real trough the melt gate
        # would bar the entry by design.
        (((ebitda_ttm_v > 0)
          & _op_viable(-0.05) & _not_melting)
         | ((ebitda_ttm_v <= 0) & (net_cash_pct_c >= 0)))   # (user) net cash protects the negative-EBITDA trough; its size is a weight
    ).fillna(False).astype(int)
    # (endpoint matrix / audit A.6, PROXY) the PHYSICAL asset base that floors
    # the downside is measured (asset intensity; the cyclical-sector set only
    # where unmeasurable), and the trough is also read through the cycle (op
    # margin >= 5 points under its 8-FY median). Old rule = _watch.
    _reframe('xr_cyclical_trough', (
        is_operating & (mcap > 0) & _fx_coherent &
        asset_heavy(sector.isin(_cyc_sectors)) &
        (pb > 0) & (pb < 1.0) &
        (_nrm29 > 0) & ((ebitda_ttm_v < 0.75 * _nrm29) | _below_midcyc_opm) &
        ((_ncol('enterprise_value') / _nrm29.where(_nrm29 > 0)) <= 7.0) &
        ~(_ncol('shares_yoy') > 0.05) &
        (((ebitda_ttm_v > 0)
          & _op_viable(-0.05) & _not_melting)
         | ((ebitda_ttm_v <= 0) & (net_cash_pct_c >= 0)))))   # (user) net cash protects the negative-EBITDA trough; its size is a weight

    # XR30 — Loss-carryforward shield ('XR-NOLShield', deferred-tax nuance):
    # an accumulated DEFICIT (negative retained earnings — a bank of tax
    # losses) in a business that has TURNED profitable means little or no
    # CASH tax for years, so cash earnings run far above GAAP after-tax
    # income. The market prices the taxed GAAP number; the shielded cash is
    # the edge. Confirmed by a low effective tax rate where observed. The
    # classic post-reorg / turnaround re-rate.
    _re30 = _ncol('retained_earnings')
    _etr30 = _ncol('effective_tax_rate')
    # (rigour B.ii) the low cash-tax rate must be OBSERVED (not merely
    # missing) — a missing ETR is not evidence of a shield. And the deficit
    # must be a real LOSS deficit, not a buyback-driven negative retained
    # earnings: a heavy repurchaser shows negative RE with a HIGH roe. Require
    # modest/negative roe OR a book still discounted (pb) so we are not
    # tagging a cash-returning compounder as a tax-shield turnaround.
    _re_is_loss30 = ((~(s('roe', np.nan) > 0.20)
                      & ~((_ncol('equity') <= 0) & (_ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0')) > 0.01)))   # a negative-equity repurchaser shows NEGATIVE roe, not high
                     | ((pb > 0) & (pb < 2.0)))
    df['arch_xr_nol_shield'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_re30 < 0) &                                      # accumulated deficit
        _re_is_loss30 &                                    # ...a LOSS deficit, not buyback-driven
        (_ncol('net_income_ttm') > 0) &                    # now profitable = shield active
        (_ncol('cfo_yield') > 0) &                         # real cash, not accrual
        (((_etr30 >= 0) & (_etr30 <= 0.15))                # OBSERVED low tax rate = the shield
         | _ncol('fq_cash_tax_rate').between(0, 0.15)) &   # (audit 3) ...or the cash rate from the quarterly statements
        (df.get('data_quality_flag', 0) == 0) &
        (rev_yoy_c >= 0.05) &                              # growing into the shield
        (((_ncol('p_e') > 0) & (_ncol('p_e') <= 25)) | (fcf_yield >= 0.05)) &
        ~(_ncol('shares_yoy') > 0.08) &
        ~_financing_fragile &
        _not_melting
    ).fillna(False).astype(int)

    # XR31 — Growth-capex-masked owner earnings ('XR-GrowthCapexMasked',
    # the capex-vs-D&A nuance in the OTHER direction from the harvest):
    # capex running FAR ABOVE depreciation is VOLUNTARY growth investment,
    # not maintenance — it depresses reported FCF while the base business
    # earns high returns. Maintenance owner earnings (CFO less only
    # replacement depreciation) are far higher than reported FCF; the market
    # prices the suppressed FCF. Tell: capex >= 1.5x D&A, strong returns,
    # CFO healthy, growing — and cheap on the MAINTENANCE cash take.
    _dna31 = _dna_loc                                     # AUDITED D&A preferred
    _cx31 = _capex_loc
    _cfo31 = _ncol('cfo_ttm')
    # GREENWALD maintenance-capex split: growth-capex is roughly the capex
    # attributable to the revenue INCREASE (prior capex-intensity x revenue
    # growth); maintenance capex is the remainder. Use BOTH lenses (user):
    #  (a) CFO less REPLACEMENT depreciation (audited D&A), and
    #  (b) CFO less Greenwald MAINTENANCE capex.
    # Take the more CONSERVATIVE (lower) maintenance take so the "fat
    # maintenance cash" claim is not overstated.
    _cap_int31 = (_cx31 / _rev_loc).where(_rev_loc > 0)
    _growth_cx31 = (_cap_int31 * (_rev_loc - _rev_loc / (1.0 + rev_yoy_c.clip(lower=0)))).where(_cap_int31.notna())   # x the revenue INCREASE (not g x current revenue)
    _maint_cx31 = (_cx31 - _growth_cx31).clip(lower=0)
    _maint_oe_a = (_cfo31 - _dna31)                       # replacement-depreciation lens
    _maint_oe_b = (_cfo31 - _maint_cx31)                  # Greenwald maintenance-capex lens
    _maint_oe31 = pd.concat([_maint_oe_a, _maint_oe_b], axis=1).min(axis=1)  # conservative
    _maint_y31 = (_maint_oe31 / _mc_ca.where(_mc_ca > 0))
    # (user / endpoint matrix, REACH) GROWTH CAPEX = CAPEX - D&A (D&A as the
    # replacement / maintenance spend) for every filer the quarterly engine
    # covers, CURRENCY-FREE: capex / D&A straight from the TTM panel, and the
    # maintenance cash yield as FCF yield + growth-capex yield, where
    #   growth capex / mcap = (capex / revenue) x (1 - D&A / capex) / (P/S)
    # — each factor a within-currency ratio (capex and revenue from the same
    # statements; P/S from the FX-coherent master). Used only where the
    # level-based lenses above are missing.
    _fq_cx = _ncol('fq_capex').abs()
    _fq_ratio = _ncol('fq_capex_to_da').where(_ncol('fq_capex_to_da') > 0)
    _fq_capint = (_fq_cx / _ncol('fq_revenue').where(_ncol('fq_revenue') > 0)).where(lambda x: x < 1.0)
    _ps31 = _ncol('p_s').where(_ncol('p_s') > 0)
    _gcx_y = (_fq_capint * (1.0 - 1.0 / _fq_ratio).clip(lower=0) / _ps31)
    _maint_y31 = _maint_y31.fillna(fcf_yield + _gcx_y)
    _capex_over_da31 = (_cx31 / _dna31.where(_dna31 > 0)).fillna(_fq_ratio)
    df['arch_xr_growth_capex_masked'] = (
        is_operating & (_mc_ca > 0) & _fx_coherent &
        (_capex_over_da31 >= 1.5) &                        # capex FAR above replacement (D&A)
        (_cfo31 > 0) &
        ((s('roce', np.nan) >= 0.12) | (_ncol('roiic_lindy') >= 0.12)
         | (_ncol('fqx_ebit_ttm_g') >= _ncol('fq_rev_growth'))) &   # (audit 3) returns ON the capex — EBIT keeping pace with revenue, or the audited ROIIC
        (rev_yoy_c >= 0.10) &                              # the growth is real
        (fcf_yield < 0.04) &                               # reported FCF suppressed
        (_maint_y31 >= 0.07) &                             # ...but maintenance cash take is fat
        ~(_ncol('shares_yoy') > 0.05) &
        ~_financing_fragile &
        _not_melting
    ).fillna(False).astype(int)

    # XR32 — Look-through value ('XR-LookThroughValue', section C): equity-
    # method / associate investments carried at cost or equity value on the
    # balance sheet understate the parent's real worth — a holdco or strategic
    # owner whose off-consolidated stakes are MATERIAL relative to its own
    # market cap, while the consolidated business is real and priced cheaply.
    # The stakes are the hidden kicker the market prices at zero.
    _assoc32 = _ncol('investments_associates')
    _assoc_pct32 = (_assoc32 / mcap).where(mcap > 0)
    df['arch_xr_look_through_value'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_assoc_pct32 >= 0.30) &                          # off-consol stakes >= 30% of mcap
        _profit_present &                                  # consolidated business is real
        (((pb > 0) & (pb < 1.5)) | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 10))) &  # cheap on consol
        _not_melting
    ).fillna(False).astype(int)

    # XR33 — Cannibal below tangible book ('XR-CannibalBelowTangibleBook',
    # section C): distinct from XR17 (below net CASH) — management BUYS BACK
    # stock while it trades below TANGIBLE book and the business EARNS, so
    # every repurchased share is bought below the hard-asset value per share,
    # accreting tangible book per share mechanically. The Teledyne trade one
    # step out from pure net-cash.
    _ptb33 = _ncol('p_tb')
    df['arch_xr_cannibal_below_tbook'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_ptb33 > 0) & (_ptb33 < 1.0) &                   # below TANGIBLE book
        (_ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0')) >= 0.01) &   # (audit 3/4) a MATERIAL buyback (>= 1% of mcap): EDGAR yield, else the global FY repurchase yield
        ((_ncol('net_buyback_ttm') > 0) | (_ncol('shares_yoy') < 0)) &  # (audit) ...CORROBORATED by real $ or actual shrinkage — excludes commodity/crypto ETF lines (PALL/PPLT/FBTC) whose buyback_yield is a creation/redemption artifact
        ~(_ncol('shares_yoy') > 0.02) &                    # and NOT net-diluting (SBC-offset buyback illusion)
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)) &  # earning
        _not_melting
    ).fillna(False).astype(int)

    # XR34 — One-off LOSS mask ('XR-OneOffLossMask'): the exact inverse of the
    # earnings_oneoff_flag. A business GUSHING cash (fat EBITDA margin, real
    # gross margin, positive FCF) that nonetheless reports a GAAP NET LOSS —
    # a goodwill impairment, restructuring charge, litigation reserve or heavy
    # D&A drove reported earnings below zero. Every earnings/P·E screen marks it
    # a loss-maker and passes over it, yet it trades cheap on EV/EBITDA. Buying
    # a cash-generative franchise the headline number hides. Guard leverage
    # (nde<=3 | net cash) so the loss is a NON-STRUCTURAL charge, not an
    # interest-eaten levered zombie; cash generation (fcf>3%) proves it is not
    # actually melting despite the negative NI.
    _ni_lm = _ncol('net_income_ttm'); _eve_lm = s('ev_ebitda', np.nan)
    df['arch_xr_oneoff_loss_mask'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_ni_lm < 0) &                                    # HEADLINE loss (screens skip it)
        (ebitda_margin > 0.15) &                          # ...but a fat operating cash margin
        (s('gross_margin', np.nan) > 0.15) &              # a real business, not a shell
        (fcf_yield > 0.03) &                              # genuinely cash-generative (the loss is non-cash / one-off)
        (_eve_lm > 0) & (_eve_lm <= 9.0) &                # cheap on the D&A-immune lens
        ((nde <= 3.0) | (net_cash_pct_c >= 0)) &          # loss is a CHARGE, not leverage eating a zombie
        ((_ncol('cfo_ttm') - _ncol('net_income_ttm')) >= 0.5 * _ncol('net_income_ttm').abs()) &   # (audit 3) the charge is observable in cash vs book
        ~(_ncol('shares_yoy') > 0.05) &
        (df.get('data_quality_flag', 0) == 0)
    ).fillna(False).astype(int)

    # XR35 — Monetization trifecta ('XR-MonetizationTrifecta'): the rare
    # three-way confluence that defines a once-in-a-cycle special situation —
    #  (a) NET CASH (cannot die while the thesis plays out),
    #  (b) a monetizable NOL >= 50% of market cap (~10% in tax value; future earnings
    #      compound tax-free — the WMIH / Mr. Cooper asset), and
    #  (c) returns / FCF JUST INFLECTING positive (the turn is happening NOW).
    # Survivability + a tax asset + an earnings turn, together, is vanishingly
    # rare and is exactly the setup where the re-rate is largest.
    _nol_tri = _num('nol_usd')
    _nol_ratio_tri = (_nol_tri / mcap.where(mcap > 0))
    _inflecting_tri = ((s('roce_first_positive', np.nan) > 0)
                       | (s('fcf_first_positive', np.nan) > 0)
                       | (s('roce_inflection', np.nan) > 0)
                       | (s('cfo_first_positive', np.nan) > 0))
    df['arch_xr_monetization_trifecta'] = (
        is_operating & (mcap > 0)
        & (net_cash_pct_c >= 0.20)                        # net-cash survivability
        & (_nol_ratio_tri >= 0.50) & (_nol_ratio_tri <= 20.0)  # monetizable NOL: >= ~10% of mcap in TAX value (x0.21), sane band (audit 3)
        & ~(_ncol('shares_yoy') > 0.05)                    # (audit 3) a Section 382 change of control would impair the NOL
        & _inflecting_tri                                 # the turn is happening now
        & (ebitda_margin > 0.03)                          # GENUINE operating profitability NOW — the NOL must have real earnings to shield and the turn must be real, not a working-capital FCF blip on a still-lossmaking business (HMDCF ebitda -5%, API ebitda ~0 / fcf -6% excluded). Also excludes data-empty shells (ONCO) that pass _not_melting vacuously.
        & (fcf_yield > -0.05)                             # not burning cash while it "inflects"
        & _not_melting
    ).fillna(False).astype(int)

    # XR36 — Contracted backlog not priced in ('XR-ContractedBacklog'): the
    # remaining performance obligation (RPO) — signed contracts NOT yet in the
    # trailing top line — is >= a full year of revenue, while the market prices
    # the TRAILING numbers (cheap on sales/EBITDA). The contracted growth
    # converts mechanically; the trailing screens can't see it. A forensic
    # "contract wins the tape hasn't caught" setup. RPO is USD (EDGAR); use
    # revenue_ttm_usd for a same-currency coverage ratio.
    _rpo_x36 = _ncol('rpo')
    _rpo_cov36 = (_rpo_x36 / _ncol('revenue_ttm_usd').where(_ncol('revenue_ttm_usd') > 0))
    df['arch_xr_contracted_backlog'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_rpo_x36 > 0) & (_rpo_cov36 >= 1.0)            # >= 1yr of contracted revenue in backlog
        & (((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 4.0))
           | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 15.0))
           | (fcf_yield >= 0.03))                         # market prices TRAILING, backlog unpriced
        & (rev_yoy_c >= 0.05)                             # backlog converting (audit 3: >= 0 was too weak for "converting")
        & _not_melting
    ).fillna(False).astype(int)

    # XR37 — Hidden segment compounder ('XR-HiddenSegmentCompounder'): the
    # forensic sum-of-parts XR. A fast-growing segment whose OPERATING MARGIN is
    # inflecting (a genuinely PROFITABLE engine, not just top-line) and that is
    # GAINING SHARE of the company, but is still < 60% of it — so the sluggish
    # LEGACY segment drags the consolidated numbers and MASKS the emerging one —
    # while the market prices that cheap consolidated whole. The segment-level
    # forensics reveal the compounder the trailing consolidated figures hide;
    # the re-rate comes as the mix shifts and the market catches up.
    _seg_ct_x37 = _ncol('segment_count')
    _seg_inflecting_x37 = ((_ncol('fastest_seg_opmargin_delta_yoy') > 0)
                           | (s('seg_margin_inflect_flag', 0) == 1)
                           | (_ncol('seg_oplev') >= 0.10))   # segment MARGIN / operating leverage turning up
    _seg_cheap_x37 = (((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 3.0))
                      | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 12.0))
                      | ((pb > 0) & (pb < 2.0))
                      | (fcf_yield >= 0.03))                 # market prices the sluggish CONSOLIDATED whole
    df['arch_xr_hidden_segment_compounder'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        & (_seg_ct_x37 >= 2)                                # a real segment mix — the mask exists
        & (_ncol('fastest_segment_yoy') >= 0.20)            # fast-growing segment
        & _seg_inflecting_x37                               # ...and its MARGIN is inflecting (profitable engine)
        & (_ncol('fastest_segment_share_delta') >= 0.02)    # gaining share of the company
        & (_ncol('fastest_segment_share') <= 0.60)          # still HIDDEN — not yet the whole (consolidated masks it)
        & ~(_ncol('fastest_seg_opmargin') <= 0)             # a PROFITABLE engine where the segment margin is disclosed
        & (rev_yoy_c <= _ncol('fastest_segment_yoy') - 0.10)   # (audit 3) the consolidated wrapper LOOKS worse than the engine
        & _seg_cheap_x37
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR38 — Segment justifies the whole ('XR-SegmentJustifiesWhole'): the
    # segment-level sum-of-parts XR. The single BEST segment, valued alone at a
    # conservative ~12x its own operating EBIT, already covers the ENTIRE
    # enterprise value — so every OTHER segment (plus any net cash) comes free.
    # seg_best_ebit_usd is the highest-EBIT reportable segment's operating
    # income (USD, from the EDGAR segment harvest); enterprise_value_usd is USD,
    # so the comparison is same-currency. We require a real multi-segment mix
    # (segment_count >= 2) and that the OTHER segments are net-positive
    # contributors (seg_total_ebit > seg_best_ebit) — that is the free
    # optionality the consolidated multiple gives away. A forensic SOTP the
    # trailing whole-company numbers can't surface.
    _sbest_x38 = _ncol('seg_best_ebit_usd')
    _stot_x38 = _ncol('seg_total_ebit_usd')
    _ev_usd_x38 = _ncol('enterprise_value_usd')
    df['arch_xr_segment_justifies_whole'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        & (_ncol('segment_count') >= 2)                     # a real segment mix — "the rest" exists
        & (_sbest_x38 > 0) & (_ev_usd_x38 > 0)              # positive best-segment EBIT and a real EV
        & (_sbest_x38 * 12.0 >= _ev_usd_x38)                # best segment alone at ~12x EBIT >= the whole EV
        & (_stot_x38 > _sbest_x38)                          # other segments are NET-POSITIVE contributors (free)
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR39 — Margin mix-shift ('XR-MarginMixShift'): the fastest-growing segment
    # earns a materially HIGHER operating margin than the company's blended
    # average (seg_mix_uplift = fastest-segment margin - blended margin) AND it
    # is GAINING share of the revenue base. Mechanically, as the high-margin
    # engine takes mix from the low-margin legacy, the CONSOLIDATED margin must
    # expand — but the trailing blended figure the market prices can't yet show
    # it. A forensic margin-inflection the segment detail reveals ahead of the
    # tape, gated to a cheap consolidated whole so the re-rate is unpriced.
    _mix_x39 = _ncol('seg_mix_uplift')
    _cheap_x39 = (((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 3.0))
                  | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 12.0))
                  | ((pb > 0) & (pb < 2.0))
                  | (fcf_yield >= 0.03))
    df['arch_xr_margin_mixshift'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        & (_ncol('segment_count') >= 2)
        & (_mix_x39 >= 0.05)                                # fastest segment >=5pp richer than the blend
        & (_ncol('fastest_segment_share_delta') >= 0.02)    # ...and taking mix from the legacy (audit 3: >= 2pp, material)
        & (_ncol('fastest_segment_yoy') >= 0.05)            # (audit 3) growth, not attrition of the rest
        & _cheap_x39                                        # market prices the cheap blended whole
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # Segment rot flag (WARNING, not an archetype). seg_core_declining marks a
    # LARGE core segment (>=25% of revenue) shrinking >=10% YoY — the consolidated
    # top line may look flat only because a growing minor segment is masking a
    # rotting core. Lives outside the arch_ namespace (like earnings_oneoff_flag):
    # it never promotes a name, it warns the reader when a segment-driven thesis
    # rests on a decaying foundation.
    df['segment_rot_flag'] = (_ncol('seg_core_declining') == 1).fillna(False).astype(int)

    # XR40 — Gross-margin lead / operating-leverage coil ('XR-GrossMarginLead').
    # Backwards-induction tell (Monster-class): before the OPERATING-margin
    # explosion, GROSS margin inflects first (mix / pricing / scale) while SG&A
    # hasn't yet scaled down, so operating margin LAGS and the trailing op-margin
    # UNDERSTATES the earnings power that is coming. The coil = gross margin
    # rising materially faster than operating margin, on a GROWING revenue base
    # (so the gross gain is scale/pricing, not a shrinking-mix / attrition
    # artifact), with real gross margin to harvest. The re-rate comes as fixed
    # SG&A is absorbed and the gross gain drops through to operating.
    _gmd_x40 = _ncol('gross_margin_delta_yoy')
    _opmd_x40 = _ncol('op_margin_delta_yoy')
    df['arch_xr_gross_margin_lead'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        & (_gmd_x40 >= 0.02)                                # gross margin up >= 2pp YoY (the lead)
        & (rev_yoy_c >= 0.05)                               # ...on a GROWING base (scale/pricing, not attrition)
        & (_ncol('gross_margin') >= 0.20)                   # real gross margin exists to leverage
        & (_opmd_x40 >= 0) & (_opmd_x40 < _gmd_x40 * 0.5)   # operating margin UP but capturing < half the gross gain (audit 3: sign-aware)
        & ~(_ncol('shares_yoy') > 0.05)
        & _not_melting
    ).fillna(False).astype(int)

    # XR41 — GAAP-profitability crossover ('XR-GAAPProfitCrossover'). A mandate /
    # inclusion re-rate (gap G10): the multiple was capped near zero not by
    # economics but by WHO COULD NOT OWN IT — passive index funds (S&P inclusion
    # requires GAAP profitability), profitability-screened institutions, and the
    # simplest quant screens all exclude a loss-maker. The turn to a first GAAP
    # net profit mechanically unlocks that latent demand. We require the profit
    # to be OPERATIONAL (op or EBITDA positive) — not a one-off gain flattering
    # the line — on a listed (non-ghost, non-OTC), non-melting, real-revenue base.
    # No market-cap floor (fire-broad, rank-later): the first-profit inflection
    # sheds the loss-maker stigma for the WHOLE buyer base, not only index funds,
    # so it is a legitimate re-rate trigger at any size — larger names, where
    # index/institutional inclusion is also in play, simply rank higher on ETA.
    _ni_now_x41 = _ncol('net_income_ttm')
    _SPIRITED.append('xr_gaap_profit_crossover')   # (endpoint matrix) index-candidate evidence ranks members
    df['arch_xr_gaap_profit_crossover'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        # NI crossed <=0 -> >0 (the mandate-unlock trigger) — on the annual
        # figures OR the date-matched quarterly TTM (the turn, whichever
        # cadence shows it first; the exact window is secondary)
        & ((s('net_income_first_positive', 0) == 1) | (_ncol('fqx_eps_turned') == 1)
           | (_ncol('fmp_dyn_ni_turned_positive') == 1))
        & (_ni_now_x41 > 0)
        & (_ncol('op_margin') > 0)                          # OPERATIONAL profit, not a one-off gain (audit 3: EBITDA > 0 is not operating profit)
        & ((_ncol('net_income_ttm') / _ncol('revenue_ttm').where(_ncol('revenue_ttm') > 0) >= 0.02)
           | (_ncol('earnings_yield') >= 0.02))              # (audit 3) a crossing of substance, not within rounding of zero
        & ~(_ncol('shares_yoy') > 0.10)                      # (audit 3) the first profit of a serial issuer is the cardinal-sin case
        & ~(s('is_price_ghost', 0) == 1) & ~(s('is_otc', 0) == 1)  # listing exists for the demand to unlock into
        & _not_melting
    ).fillna(False).astype(int)

    # XR42 — Deferred-revenue forward book ('XR-DeferredRevenueLead'). A sibling
    # to contracted_backlog (RPO), using the older/broader DEFERRED-REVENUE
    # disclosure (invoiced-and-collected but not yet recognised — the SaaS /
    # subscription / prepaid book). A material forward book (>= 15% of revenue)
    # that is BUILDING (revenue growing) is contracted revenue already sitting on
    # the balance sheet, yet the market prices the CHEAP trailing tape (a
    # transition or conservative recognition depresses reported revenue). This is
    # deliberately the MIRROR of float_compounding: that catches the beloved SaaS
    # (dear/meaningless P/E); this catches the MISPRICED book — priced cheap on
    # trailing sales/FCF while the deferred balance pre-loads forward revenue.
    _defrev_x42 = _ncol('deferred_revenue')
    _defrev_ratio_x42 = (_defrev_x42 / _rev_loc).where(_rev_loc > 0)
    _cheap_x42 = (((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 3.0))
                  | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 12.0))
                  | (fcf_yield >= 0.03))
    df['arch_xr_deferred_revenue_lead'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_defrev_ratio_x42 >= 0.15)                       # a real forward book already collected
        & ((rev_yoy_c >= 0.05)                              # ...and BUILDING (subscriptions/prepayments growing)
           # or the BOOK itself building faster than recognised revenue
           # (deferred balance up >= 5pp more than sales, sales not falling):
           # the forward book leading a flat trailing tape IS the mispricing
           | ((_ncol('fq_defrev_growth_minus_rev') >= 0.05) & (rev_yoy_c >= 0)))
        & ~(_ncol('fq_defrev_growth_minus_rev') < 0)        # (audit 3) the book is not SHRINKING relative to sales where observed
        & _cheap_x42                                        # yet priced on the cheap TRAILING tape (the mispricing)
        & ~(_ncol('shares_yoy') > 0.05) & ((_ncol('net_income_ttm') > 0) | (_ncol('cfo_yield') > 0))   # (audit 3) the siblings' guards
        & _not_melting
    ).fillna(False).astype(int)

    # XR43 — Cash-tax advantage / DTL cushion ('XR-CashTaxAdvantage', N2). Gap
    # G7: the crowd anchors on GAAP EPS, which is struck after the FULL book tax
    # provision (IncomeTaxExpenseBenefit). When CASH taxes actually paid run
    # materially below that book provision, the difference is a deferred-tax-
    # liability cushion — an interest-free government loan — and owner earnings
    # are understated by the wedge. We require a real book tax charge on positive
    # pre-tax income, cash tax <= 60% of it (a >= 40% cash-vs-book wedge), a
    # material uplift to GAAP NI, and a cheapness floor (so it is a value setup,
    # not a quality premium). NB: single-period cash-tax can be timing-noisy —
    # the >=40% wedge threshold is deliberately wide to filter transient blips.
    _tax_book_x43 = _ncol('tax_expense_ttm')
    _tax_cash_x43 = _ncol('income_taxes_paid_ttm')
    _tax_wedge_x43 = (_tax_book_x43 - _tax_cash_x43)
    _ni_x43 = _ncol('net_income_ttm')
    _book_rate_x43 = (_tax_book_x43 / _ncol('pretax_income_ttm').where(_ncol('pretax_income_ttm') > 0))
    _x43_edgar = (
        (_ncol('pretax_income_ttm') > 0) & (_tax_book_x43 > 0)   # a real book tax charge on real pre-tax profit
        & _book_rate_x43.between(0.10, 0.45)                       # (refine) a NORMAL book tax year, not a distorted one-off (refund/settlement/true-up)
        & (_tax_cash_x43 > 0) & (_tax_cash_x43 <= _tax_book_x43 * 0.6)  # they DO pay cash tax, but << book (>=40% wedge; excludes refund/NOL years)
        & (_ni_x43 > 0) & (_tax_wedge_x43 / _ni_x43 >= 0.10)      # owner earnings >= 10% above GAAP NI from the wedge
    )
    # FMP path (global, only where EDGAR has no tax data): the SAME thesis on
    # like-for-like ANNUAL rates (cash tax paid / pretax vs book tax / pretax,
    # same fiscal year), plus PERSISTENCE: the median wedge over >= 2 fiscal
    # years must also be >= 40%, which answers the single-period timing-noise
    # caveat above rather than relying on a wide threshold. Uplift to NI is the
    # rate form of the EDGAR test: (book - cash) / (1 - book) >= 10%.
    _cr43, _br43 = _ncol('fq_cash_tax_rate'), _ncol('fq_book_tax_rate_fy')
    _x43_fmp = (
        _tax_book_x43.isna() & _tax_cash_x43.isna()
        & _br43.between(0.10, 0.45)
        & (_cr43 > 0) & (_cr43 <= 0.6 * _br43)
        & (_ncol('fq_cash_tax_wedge_med') >= 0.40)
        & (((_br43 - _cr43) / (1 - _br43)) >= 0.10)
        & (_ni_x43 > 0)
    )
    df['arch_xr_cash_tax_advantage'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_x43_edgar | _x43_fmp)
        & (((_ncol('p_e') > 0) & (_ncol('p_e') <= 20)) | (_ncol('earnings_yield') >= 0.05) | (fcf_yield >= 0.03))
        & _not_melting
    ).fillna(False).astype(int)

    # XR44 — Owned real estate at historical cost ('XR-OwnedRealEstateValue', N3).
    # Gap G3: US GAAP freezes property at acquisition cost and never revalues it
    # up; land is never depreciated. A property-heavy operator that OWNS (rather
    # than leases) its footprint therefore carries real estate worth a multiple
    # of net book, invisible to a P/B screen. Tell: a high accumulated-
    # depreciation ratio (assets largely written down => OLD, at historical
    # cost), gross original cost large vs. market cap, small operating-lease ROU
    # relative to owned PP&E (an OWNER, not a lessee), PP&E a big share of assets,
    # and a cheap book multiple. (is_operating already excludes financials/REITs.)
    _ppe_gross_x44 = _ncol('ppe_gross')
    _accum_dep_x44 = _ncol('accumulated_depreciation')
    _rou_x44 = _ncol('operating_lease_rou')
    _ppe_net_x44 = _ncol('ppe_net')
    _accum_ratio_x44 = (_accum_dep_x44 / _ppe_gross_x44.where(_ppe_gross_x44 > 0))
    _owns_x44 = ~(( _rou_x44 / _ppe_net_x44.where(_ppe_net_x44 > 0)) > 0.5).fillna(False)  # ROU small vs owned PPE (or ROU missing) => owner
    df['arch_xr_owned_realestate_value'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ppe_gross_x44 > 0) & (_accum_dep_x44 > 0)
        & (_accum_ratio_x44 >= 0.5)                          # assets >= half depreciated => old, at historical cost
        & (_ppe_gross_x44 / mcap >= 0.75)                    # original cost large vs. market cap (room for hidden value)
        & (_ppe_net_x44 / _ncol('assets').where(_ncol('assets') > 0) >= 0.25)  # property-heavy balance sheet
        & _owns_x44                                          # OWNS its footprint (not a lessee)
        & ((pb > 0) & (pb < 1.2))                            # (audit 3) the market pays about book or less; EV/S said nothing about property
        & (df.get('data_quality_flag', 0) == 0)
        & ((_ncol('op_margin') > 0) | (fcf_ttm_v > 0))       # (refine) a VIABLE operator — else impaired assets / forced-sale value trap, not hidden value
        & _not_melting
    ).fillna(False).astype(int)

    # XR45 — Discontinued-ops / held-for-sale mask ('XR-DiscOpsMask', N4). Gap
    # G6: consolidated net income is depressed (or negative) BECAUSE of a losing
    # unit in discontinued operations or held for sale, while CONTINUING
    # operations are solidly profitable. A screen on consolidated NI/EPS rejects
    # the name; the re-rate comes when the drag is divested and continuing-ops
    # earnings stand alone. Tell: continuing-ops income positive and well above
    # consolidated NI (or a discops drag / large held-for-sale block), with the
    # CONTINUING earnings alone making the stock cheap.
    _cont_x45 = _ncol('income_continuing_ops_ttm')
    _disc_x45 = _ncol('income_discontinued_ops_ttm')
    _ahfs_x45 = _ncol('assets_held_for_sale')
    # yield in the LISTING currency: income_continuing_ops_ttm is master-
    # currency (EDGAR USD, or FMP converted to the listing currency), so it
    # is divided by the listing-currency market cap — dividing an FMP-filled
    # JPY figure by the USD cap read ~150x too cheap. (Identical for US rows.)
    _mc_x45 = _ncol('market_cap')
    _cont_yield_x45 = (_cont_x45 / _mc_x45.where(_mc_x45 > 0))
    # FMP's continuing-ops income is pre-minority while NI is parent-only, so
    # on FMP-filled rows the "NI <= 0 but core profitable" leg can fire on a
    # non-controlling-interest gap alone: those rows need the explicit
    # discontinued-ops loss leg.
    _x45_fmp = (_ncol('fmp_filled_income_continuing_ops_ttm') == 1)
    _mask_present_x45 = (
        # (refine) require an actual consolidated LOSS with a profitable core — a
        # clean mask. (The bare NI<continuing test was noisy: continuing-ops is
        # pre-minority-interest while NI is attributable-to-parent, so the gap
        # could be just NCI, not a discontinued drag.)
        ((_ni_x43 <= 0) & (_cont_x45 > 0) & ~_x45_fmp)       # consolidated LOSS but continuing ops profitable
        | ((_disc_x45 < 0) & ((-_disc_x45) >= _cont_x45 * 0.20))  # discops loss material vs the core
        | ((_ahfs_x45 / mcap) >= 0.15)                       # a large block being divested
    )
    df['arch_xr_discops_mask'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_cont_x45 > 0)                                    # the CORE (continuing ops) is profitable
        & _mask_present_x45                                  # ...but a discontinued/held-for-sale drag masks it
        & (_cont_yield_x45 >= 0.06)                          # on continuing-ops earnings alone, the stock is cheap
        & (_ncol('cfo_yield') > 0)                           # (audit 3) cash guard (leverage cap demoted to a weight: user rule)
        & _not_melting
    ).fillna(False).astype(int)

    # XR47 — Verified deleveraging ('XR-VerifiedDeleveraging'). The equity
    # stub of a levered but cash-generative business re-rates mechanically as
    # debt is repaid: every unit of debt retired accrues to equity holders and
    # the leverage multiple falls into the range where the market will pay
    # for the earnings. The crowd waits for the ratio to print; the quarterly
    # balance sheets show the PATH already under way. Requires the deleveraging
    # proof (net debt down across >= 9 months of consecutive balance sheets, by
    # >= 5% of assets, operations-funded, not equity- or disposal-funded) on a
    # still-meaningful leverage (1.5x-4x EBITDA — enough stub leverage for the
    # paydown to matter, not so much that solvency is the thesis) at a cheap
    # EV/EBITDA.
    df['arch_xr_verified_deleveraging'] = (
        is_operating & (mcap > 0)
        & (df['fq_deleveraging_flag'] == 1)
        & (rev_yoy_c >= -0.05) & ~(_ncol('fq_interest_cover') < 2.0) & (fcf_yield > 0)   # (audit 3) operations-funded, covered, not liquidating
        & (nde >= 1.5) & (nde <= 4.0)
        & (ev_ebitda_v > 0) & (ev_ebitda_v <= 8.0)
        & (ebitda_ttm_v > 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR48 — Cash leads book ('XR-CashLeadsBook'). The accruals anomaly
    # INVERTED and proven: operating cash flow runs ahead of net income AND is
    # growing faster than it, with negative accruals, NOT from a working-
    # capital liquidation or an SBC add-back (fq_cash_leads_earnings_flag).
    # Accounting earnings are lagging the cash economics (conservative
    # provisioning, front-loaded expensing, deferred-revenue float), so a
    # market pricing the GAAP line prices the business on an understated E.
    # Cheap on that understated E (P/E <= 15) or on the cash itself (FCF
    # yield >= 6%). Distinct from F2 (a level test on CFO/NI >= 1.5): this is
    # the TRAJECTORY — cash pulling away from book.
    df['arch_xr_cash_leads_book'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 10e6)
        & (df['fq_cash_leads_earnings_flag'] == 1)
        & (((_ncol('p_e') > 0) & (_ncol('p_e') <= 15)) | (fcf_yield >= 0.06))
        & ~(_ncol('shares_yoy') > 0.05)
        & _not_melting
    ).fillna(False).astype(int)

    # XR46 — Peer-relative margin gap + self-help turn ('XR-PeerMarginGap', N5).
    # The first explicitly COMPARABLE-normalised forensic lens (gap G9): a
    # business earning an operating margin far BELOW its sector's median is either
    # structurally inferior or sitting on latent margin (bloated cost base, bad
    # mix, pre-self-help). We admit it only WITH an observed margin turn (op or
    # gross margin up >= 1pp, TTM EBIT growing, or a dated inflection) and a cheap multiple,
    # and we bar the genuinely melting (deeply negative margin, secular revenue
    # decline). The re-rate is the market pricing mean-reversion once execution
    # shows. Sector median computed over operating names with a real margin.
    _opm_x46 = _ncol('op_margin')
    _sec_g46 = df['sector'].fillna('') if 'sector' in df.columns else pd.Series('', index=df.index)
    _opm_for_med = _opm_x46.where(is_operating & (_ncol('revenue_ttm_usd') >= 20e6) & _opm_x46.between(-0.5, 0.6))
    _sec_med_opm = _opm_for_med.groupby(_sec_g46).transform('median')
    _sec_peer_n = _opm_for_med.groupby(_sec_g46).transform('count')   # (refine) peers behind the median
    # (endpoint matrix, PROXY) the PEER norm at the finest level with a well-
    # populated peer set: the INDUSTRY median where >= 20 operating peers
    # report a margin (a software company vs software, not vs "Technology"),
    # the sector median otherwise
    _ind_g46 = df['industry'].fillna('') if 'industry' in df.columns else pd.Series('', index=df.index)
    _ind_med = _opm_for_med.groupby(_ind_g46).transform('median')
    _ind_n = _opm_for_med.groupby(_ind_g46).transform('count')
    _use_ind = (_ind_n >= 20) & (_ind_g46 != '')
    _sec_med_opm = _ind_med.where(_use_ind, _sec_med_opm)
    _sec_peer_n = _ind_n.where(_use_ind, _sec_peer_n)
    _margin_gap_x46 = (_sec_med_opm - _opm_x46)
    _turn_x46 = ((_ncol('op_margin_delta_yoy') >= 0.01) | (_ncol('gross_margin_delta_yoy') >= 0.01)
                 | (_ncol('fqx_ebit_ttm_g') > 0) | (_ncol('fqx_margin_inflect_now') == 1))   # (audit 3) an observed margin turn
    df['arch_xr_peer_margin_gap'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ncol('revenue_ttm_usd') >= 20e6)
        & _sec_med_opm.notna() & (_sec_med_opm > 0.05) & (_sec_peer_n >= 20)  # a sector with a meaningful, well-populated margin norm to revert toward
        & (_margin_gap_x46 >= 0.05)                          # >= 5pp below the sector median (latent margin)
        & (_opm_x46 >= -0.05)                                # a real underearner, not a melting loss-maker
        & _turn_x46                                          # ...with a self-help TURN in evidence
        & (((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 2.0)) | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 10.0)) | (fcf_yield >= 0.04))
        & ~(_ncol('revenue_3y_cagr') < -0.05)                # not in secular decline (margin gap then is terminal, not latent)
        & _not_melting
    ).fillna(False).astype(int)

    # XR43 — Investment/JV remark ('XR-InvestmentRemark'). The LanzaTech pattern:
    # a minority JV / equity stake REMEASURED to fair value (on the investee's
    # public listing, a step-up to control, or a revaluation) — the investment's
    # CARRYING VALUE steps up and a large NON-CASH gain crystallises hidden value
    # on the balance sheet (LanzaTech Q2-2026: 8.3% Shougang LanzaTech stake
    # $15m->$223m = +$208m unrealised gain on SGLT's listing). The market often
    # hasn't repriced the now-higher NAV, or discounts the "one-off gain". Gate on
    # the BALANCE-SHEET value vs price, NOT P/E (which the non-cash gain flatters).
    _ir_pct = _ncol('inv_remark_pct'); _ir_jump = _ncol('inv_remark_jump')
    _ir_now = _ncol('inv_carry_now')
    _ir_gain = ((_ncol('unrealized_inv_gain') > 0) | (_ncol('nonop_gain_ttm') > 0))
    _ir_gain_sized = ((_ncol('unrealized_inv_gain') >= 0.5 * _ir_jump) | (_ncol('nonop_gain_ttm') >= 0.5 * _ir_jump))   # (audit 3) commensurate
    _mc_usd_ir = _ncol('market_cap_usd')
    df['arch_xr_investment_remark'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_ir_pct >= 0.5) & (_ir_jump > 0)                           # a real carrying-value step-up (>=50%)
        & (_ir_jump / _mc_usd_ir.where(_mc_usd_ir > 0) >= 0.10)       # material vs market cap (>=10%)
        & _ir_gain & _ir_gain_sized                                   # confirmed by an unrealised / non-op REMARK gain of the jump's size
        & (_ir_now / _mc_usd_ir.where(_mc_usd_ir > 0) >= 0.15)        # the stake is now a big share of mcap
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR44 — Stake fair-value gap ('XR-StakeFVGap'). The sharpest LATENT tell
    # (idea #1): the company itself DISCLOSES (EquityMethodInvestmentsFairValue-
    # Disclosure) that the fair value of its equity-method JV/associate stake
    # exceeds its CARRYING VALUE — a hidden asset the balance sheet doesn't show
    # and a P/B screen can't see, on a cheaply-priced consolidated whole.
    _fv = _ncol('em_fair_value'); _emc = _ncol('em_carry'); _fvgap = _ncol('em_fv_gap')
    _stake_cheap = (((ev_ebitda_v > 0) & (ev_ebitda_v <= 12.0))
                    | ((pb > 0) & (pb < 2.0)) | (fcf_yield >= 0.03)
                    | ((_ncol('ev_sales') > 0) & (_ncol('ev_sales') <= 3.0)))
    df['arch_xr_stake_fv_gap'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_emc > 0) & (_fv > _emc * 1.3)                             # disclosed FV >= 1.3x carrying value
        & (_fvgap / _mc_usd_ir.where(_mc_usd_ir > 0) >= 0.10)         # hidden value >= 10% of mcap
        & _stake_cheap
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR45 — Look-through earner ('XR-LookThroughEarner'). A hidden associate
    # earnings ENGINE: the share of associates' profit (IncomeLossFromEquity-
    # MethodInvestments) is a material part of the parent's pre-tax income (or
    # material vs mcap), yet the market prices the parent cheaply — the associate
    # compounds inside the consolidated numbers, unpriced.
    _emi = _ncol('em_income')
    df['arch_xr_lookthrough_earner'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & (_emi > 0)
        & (((_emi / _ncol('pretax_income_ttm').where(_ncol('pretax_income_ttm') > 0) >= 0.25)
            & (_emi / _mc_usd_ir.where(_mc_usd_ir > 0) >= 0.02))       # (audit 3) no small-pretax artefact
           | (_emi / _mc_usd_ir.where(_mc_usd_ir > 0) >= 0.05))       # material contribution
        & _stake_cheap
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # XR46 — Value-unlock catalyst ('XR-ValueUnlock'). A CHEAP security whose
    # management/board is actively SIGNALLING intent to realise / crystallise /
    # unlock latent value for shareholders — a strategic review, sale process,
    # sum-of-the-parts separation, activist-driven capital return — OR a
    # structured unlock event already in motion (spin / tender / merger /
    # going-private). The cheapness is the margin of safety; the catalyst is the
    # timing. We prioritise DISTINCTIVE, FRESH language (a boilerplate "enhance
    # shareholder value" alone does not qualify) and require the discount.
    _vu_hits = _ncol('unlock_hits'); _vu_np = _ncol('unlock_distinct_phrases')
    _vu_days = _ncol('unlock_days_ago')
    _vu_phr = df['unlock_phrases'].astype(str) if 'unlock_phrases' in df.columns else pd.Series('', index=df.index)
    _vu_distinctive = _vu_phr.str.contains(
        'strategic alternatives|sale process|sum-of-the-parts|financial advisor|'
        'separation|crystall|pursue a separation|return of capital', case=False, regex=True)
    _vu_language = ((_vu_days <= 400)                                   # a FRESH filing (live catalyst)
                    & (_vu_distinctive | (_vu_np >= 2)))                # distinctive OR multiple phrases (not lone boilerplate)
    _vu_event = ((s('spin_flag', 0) == 1) | (s('tender_flag', 0) == 1)
                 | (s('merger_flag', 0) == 1) | (s('going_private_flag', 0) == 1)
                 # (endpoint matrix, LEG) a DATED activist catalyst: an SC 13D
                 # within 180 days (sub-$2B, so the filing is about the name)
                 | ((_evt_age_days('evt_sc13d_date') <= 180) & (mcap < 2e9)).fillna(False))
    _vu_cheap = (
        ((pb > 0.05) & (pb < 1.0))                                      # below book
        | (_ncol('ncav_pct_mcap') >= 1.0)                              # net-net
        | (net_cash_pct >= 0.30)                                       # net cash
        | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 6.0))                  # deep cheap on EV
        | (_hidden_pct.where(_fx_coherent) >= 0.20)                   # hidden forensic value (forensic_hidden_pct is built only after this block)
    )
    df['arch_xr_value_unlock'] = (
        is_operating & (mcap > 0) & _fx_coherent
        & _vu_cheap & (_vu_language.fillna(False) | _vu_event)
        & (_ncol('revenue_ttm_usd') >= 10e6)                 # (audit 3) a business under the discount, not a cash shell
        & ((_ncol('ebitda_ttm') > 0) | (_ncol('ncav_pct_mcap') >= 1.0) | (_hidden_pct >= 0.20))
        & (df.get('data_quality_flag', 0) == 0)
        & _not_melting
    ).fillna(False).astype(int)

    # VALUE-UNLOCK CONVICTION (language x forensics x footprint x alignment). The
    # strongest setup is when the WORDS (catalyst), the NUMBERS (a real forensic
    # gap to unlock), the BALANCE SHEET (a divestiture actually on the books) and
    # the INCENTIVES (insider-aligned management) all point the same way — and it
    # is FRESH. A ranking score over the arch_xr_value_unlock members, plus a
    # value_unlock_confirmed flag for the subset the forensics substantiate.
    _vu_cat = (0.55 * _vu_distinctive.fillna(False).astype(float)          # distinctive language
               + 0.20 * (_vu_np.fillna(0).clip(0, 4) / 4.0)               # multiple phrases
               + 0.25 * _vu_event.astype(float)).clip(0, 1)              # structured event in motion
    _vu_fresh = (1.0 - (_vu_days.clip(0, 400) / 400.0)).fillna(0.0)       # live catalyst decay
    # forensic CONFIRMATION — a matching hidden-value archetype proves the claim
    _vu_forensic = (
        (df.get('arch_xr_segment_justifies_whole', 0) == 1)              # "sum-of-the-parts" proven
        | (df.get('arch_xr_stake_fv_gap', 0) == 1) | (df.get('arch_xr_investment_remark', 0) == 1)  # "monetise stake"
        | (df.get('arch_xr_owned_realestate_value', 0) == 1)            # "real-estate value"
        | (df.get('arch_oak_nav_discount', 0) == 1)                    # "holdco/conglomerate discount"
        | (df.get('arch_hidden_assets', 0) == 1)
        | (_hidden_pct.where(_fx_coherent) >= 0.25)                    # large hidden value (forensic_hidden_pct is built only after this block)
        | (net_cash_pct >= 0.40)                                       # cash to actually return
    ).fillna(False)
    # execution FOOTPRINT — the divestiture is really happening on the books
    _vu_footprint = ((_ncol('assets_held_for_sale') > 0)
                     | (_ncol('income_discontinued_ops_ttm').abs() > 0)).fillna(False)
    # ALIGNMENT — management personally benefits from the unlock
    _vu_align = ((s('governance_score', 0) >= 0.15)
                 | (_ncol('insider_ownership_pct') >= 0.10)).fillna(False)
    # CREDIBILITY / STAGE (#2): a committed process (named advisor / definitive
    # agreement / special committee) or an ACTIVIST forcing it (SC 13D / proxy
    # contest) is far higher-conviction than a vague board musing.
    _vu_stage = (_ncol('unlock_stage_phrases') >= 1).fillna(False)      # process underway
    _vu_activist = (_ncol('unlock_activist') == 1).fillna(False)        # 13D / proxy fight
    _vu_member = (df['arch_xr_value_unlock'] == 1)
    df['value_unlock_score'] = (
        _vu_cat * (0.4 + 0.6 * _vu_fresh)
        * (1.0 + 0.60 * _vu_forensic.astype(float)
           + 0.25 * _vu_footprint.astype(float)
           + 0.15 * _vu_align.astype(float)
           + 0.35 * _vu_stage.astype(float)                            # committed stage
           + 0.30 * _vu_activist.astype(float))                        # activist-forced
        * _vu_member.astype(float)
    ).clip(0, 3).round(3)
    # the high-conviction subset: cheap + live catalyst AND the forensics confirm
    # there is real value to unlock
    df['value_unlock_confirmed'] = (_vu_member & _vu_forensic).astype(int)

    # ------------------------------------------------------------------
    # pre_rerating_score — the ONE construction the backtest actually
    # validated on real forward returns (see BACKTEST_PRERERATING.md).
    # It is TURN x DISBELIEF: a live Piotroski-style quality score
    # (the P1 spine, IC +0.141 on our 2025->2026 cohort) INTERACTED with
    # cheapness (low P/B, IC +0.122). The interaction bucket returned
    # +25.1% mean / 69% positive vs the universe's +11.8% / 53%, beating
    # either leg alone by ~5pp. Two guards come straight from that test:
    #   (1) the accrual leg is credited only when earnings are POSITIVE
    #       — an extreme CFO>>NI gap on a loss is an impairment/distress
    #       flag, and its "cleanest" decile realized -10% (anomaly inverts);
    #   (2) the deepest-P/B tail is a VALUE TRAP (cheapest decile lagged the
    #       merely-cheap), so a bottom-decile book multiple with weak quality
    #       and no catalyst is capped out of top-pick territory.
    _pr_roa = (_ncol('roa') > 0)
    _pr_cfo = (_ncol('cfo_ttm') > 0)
    _pr_droa = (_ncol('roce_delta_yoy') > 0)                       # d(returns) up
    _pr_ni = _ncol('net_income_ttm')
    _pr_accrual = (_ncol('cfo_ttm') > _pr_ni) & (_pr_ni > 0)       # cash>earnings, GUARD: NI>0
    _pr_nodilute = (_ncol('shares_yoy') <= 0.02)                   # no dilution
    _pr_gm = (_ncol('gross_margin_delta_yoy') > 0)                 # margin up
    _pr_turn = (_ncol('rev_yoy') > 0)                              # growth/turnover proxy
    _pr_quality = (_pr_roa.fillna(False).astype(int)
                   + _pr_cfo.fillna(False).astype(int)
                   + _pr_droa.fillna(False).astype(int)
                   + _pr_accrual.fillna(False).astype(int)
                   + _pr_nodilute.fillna(False).astype(int)
                   + _pr_gm.fillna(False).astype(int)
                   + _pr_turn.fillna(False).astype(int))           # 0..7
    _pr_pb = _ncol('pb')
    _pr_pb_pos = _pr_pb.where(_pr_pb > 0)
    _pr_p40 = _pr_pb_pos.quantile(0.40)
    _pr_p10 = _pr_pb_pos.quantile(0.10)
    _pr_cheap = (_pr_pb > 0) & (_pr_pb <= _pr_p40)
    _pr_trap = (_pr_pb > 0) & (_pr_pb <= _pr_p10)                  # deepest-decile trap tail
    _pr_sweet = _pr_cheap & ~_pr_trap                             # cheap but not the trap tail
    _pr_catalyst = ((df['value_unlock_confirmed'] == 1)
                    | (_ncol('governance_score') >= 0.35)).fillna(False)
    _pr_raw = (_pr_quality
               + 2 * _pr_cheap.fillna(False).astype(int)
               + 1 * _pr_sweet.fillna(False).astype(int)).astype(float)   # 0..10
    # value-trap demotion: deepest P/B + weak quality + no catalyst can't top the book
    _pr_demote = _pr_trap.fillna(False) & (_pr_quality < 4) & ~_pr_catalyst
    _pr_raw = _pr_raw.where(~_pr_demote, _pr_raw.clip(upper=3))
    df['pre_rerating_quality'] = _pr_quality
    df['pre_rerating_score'] = _pr_raw.round(2)
    # the validated high-conviction set (the +25%/69% bucket): strong AND cheap,
    # excluding the value-trap tail unless a live catalyst redeems it
    df['pre_rerating_flag'] = (
        (_pr_quality >= 5) & _pr_cheap & (~_pr_trap | _pr_catalyst)
    ).fillna(False).astype(int)

    # F6 — Forensic payout confirmation (the user's BOOST leg). Any forensic /
    # hidden-value member that is ALSO returning capital — buying back shares
    # or paying a dividend — is flagged as a SURFACED confirmation. It is in
    # _NOT_COUNTED, so it adds NO archetype count / density (it would double-
    # count its forensic parent). Revealed preference: management monetising the
    # hidden value for owners, not hoarding it.
    # (audit 3) MATERIAL and COVERED: a >= 3% total yield (dividend + FY
    # repurchases, global) or a >= 1% shrinking count, not uncovered over the
    # cycle where observed
    _payout_any = (((_ncol('dividend_yield').fillna(0) + _ncol('buyback_yield').fillna(_ncol('fmp_st_buyback_yield_y0')).fillna(0)) >= 0.03)
                   | (_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')) <= -0.01)) & ~(_ncol('tc_uncov_payout_3y') >= 2)
    # (audit 3) the payout-DEFINED members (dividend_verified_value,
    # cannibal_at_discount, self_funded_returner) are excluded: the flag reads
    # "a non-payout forensic tell PLUS a payout", not the payout twice
    _forensic_any = ((df['arch_hidden_assets'] == 1)
                     | (df['arch_retained_earnings_discount'] == 1)
                     | (df['arch_customer_float'] == 1)
                     | (df['arch_capex_famine_harvest'] == 1)
                     | (df['arch_tax_verified_earnings'] == 1)
                     | (df['arch_book_compounder_discount'] == 1)
                     | (df['arch_overdepreciated_assets'] == 1)
                     | (df['arch_understated_earnings'] == 1)
                     | (df['arch_expensed_growth_value'] == 1)
                     | (df['arch_cash_adjusted_pe'] == 1)
                     | (df['arch_owner_earnings_power'] == 1))
    df['arch_forensic_payout_confirmed'] = (
        _forensic_any & _payout_any
    ).fillna(False).astype(int)

    # NEW: Oak order-book conversion (backlog->revenue, the MPAC pattern).
    # LAGGING proxy: we can't see order intake / book-to-bill, only the P&L
    # footprint once it lands — accelerating revenue + margin expansion.
    df['arch_oak_order_conversion'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 1e9) &
        (ebitda_ttm_v > 0) &                        # survivability: real backlog conversion has POSITIVE EBITDA (not a less-negative decliner)
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &       # cash-generative, not a melting shell (Futaba/DeTai)
        _not_melting &                              # (tail) a CFO working-capital swing must not mask a deep operating loss (PRISMX op-407%, DDEJF op-125%)
        ((rev_accel > 0) | (rev_yoy_c > 0.05)) &
        (oper_lev_any | (_fqx_inc >= 0.20).fillna(False)) &   # (endpoint matrix) + TTM drop-through
        ((ebitda_inflection > 0) | (ebitda_yoy_v > 0) | (df['fq_defrev_build_flag'] == 1))
    ).fillna(False).astype(int)
    # (audit 3) the FORWARD BOOK is the thesis (signed orders / deposits >= 10%
    # of revenue): the core requires the deferred-revenue build (prepayments
    # >= 10% of revenue outgrowing sales by >= 5pp) with the P&L footprint as
    # confirmation; the P&L-only shape is oak_order_conversion_watch. A
    # placing (the explicit reject) fails.
    df['oak_order_conversion_watch'] = df['arch_oak_order_conversion'].astype(int)
    df['arch_oak_order_conversion'] = ((df['arch_oak_order_conversion'] == 1)
                                       & (df['fq_defrev_build_flag'] == 1)
                                       & ~(_ncol('fq_shares_yoy') > 0.05)).astype(int)
    _SPIRITED.append('oak_order_conversion')

    # ---------- Ted Weschler leveraged-equity deleveraging ----------
    # (dirtcheapstocks case study, Valassis Communications). The equity is
    # CHEAP on its own cash flow (low P/FCF = high FCF yield) but the company
    # is HEAVILY indebted, so it looks expensive on EV (EV >> market cap). The
    # equity is a small, high-torque claim on a deleveraging business: as debt
    # is serviced and paid down, enterprise value migrates from lenders to the
    # (shrinking, bought-back) equity, compounding it hard. Valassis: traded
    # <1x FCF, ~$1.15B debt, EBIT covered interest even in the 2008 recession,
    # paid down $200-305M/yr from FCF, bought back 16% of shares -> ~52%/yr for
    # six years.
    # The thesis works only when the company can (a) SERVICE the debt, (b)
    # AMORTISE it from cash, and (c) has LONG-DATED maturities (no near-term
    # refinancing wall). We can screen (a) and (b); we have NO debt-maturity-
    # schedule field, so the maturity-wall risk is NOT screenable — it must be
    # checked by hand before acting on this flag.
    ev_raw = s('enterprise_value')
    mcap_raw = s('market_cap')  # same-currency as EV -> ratio is FX-neutral
    ev_over_mcap = pd.Series(np.nan, index=df.index)
    _m = (mcap_raw > 0) & (ev_raw > 0)
    ev_over_mcap[_m] = ev_raw[_m] / mcap_raw[_m]
    # NaN-preserving nde so MISSING debt (which s() fills with 99) can't
    # spuriously satisfy the "heavy debt" test.
    nde_real = pd.to_numeric(df['net_debt_ebitda'], errors='coerce') \
        if 'net_debt_ebitda' in df.columns else pd.Series(np.nan, index=df.index)
    # Cheapness is measured on a ROBUST, Lindy cash basis rather than a single
    # FCF print. robust_cash_yield (from derive) is the row-wise MEDIAN of three
    # independent yields — reported FCF (owner's earnings, after all capex),
    # operating cash flow (pre-capex), and accounting earnings — so no single
    # distorted metric (a capex spike, a working-capital swing, an accrual
    # quirk) can qualify a name. We additionally require a conservative
    # reported-FCF floor so the equity's cash is real after capex.
    robust_cy = s('robust_cash_yield')
    # The corroborating leg here always MEANT "reported FCF over mcap" (its
    # own comment said so) — reference fcf_yield by name now that
    # owner_earnings_yield honestly carries Buffett OE (NI + D&A − capex)
    # instead of an FCF alias.
    owner_ey = s('fcf_yield')              # reported FCF / mcap
    # Upper bounds reject near-zero-mcap data artifacts (a yield of 55,000,000x
    # or EV/mcap of 130,000,000x is a broken market cap, not a cheap stub).
    # Genuine Weschler zone: P/cash ~0.5-6.7x, EV a few x equity.
    # (R3) FX-corrupt EV can read a NET-CASH firm as "levered" via ev_over_mcap
    # alone. Require a REAL positive-leverage corroborator (net debt / equity)
    # on the EV path so a cross-listing artifact can't flag a net-cash balance
    # sheet as a levered stub. The nde path is already net-debt-based.
    # A levered equity stub REQUIRES positive net debt: a net-cash firm (more
    # cash than debt) is never a levered stub, whatever its FX-corrupt EV or
    # gross debt/equity says. So the EV-path corroborator is genuine net debt
    # (nde) OR simply "not net cash" — gross debt/equity alone does NOT qualify
    # a firm whose cash exceeds its debt.
    # (fresh) a convex LEVERED STUB needs MEANINGFUL net debt, not merely "not
    # net cash" — the EV-path admitted trivially-levered names (nde<1) whose
    # equity carries no real torque. Require confirmable net debt >= 1.5x EBITDA.
    _real_leverage = (nde_real >= 1.5)
    # Known-net-cash veto: some names carry CONTRADICTORY balance-sheet fields
    # (net_cash_pct says net cash, net_debt_ebitda says heavily levered — stale
    # / mismatched snapshots). For a levered-stub thesis the conservative call
    # is to NOT call a firm a levered stub whenever a balance-sheet measure
    # clearly says it is net cash. Missing net_cash_pct stays permissive.
    _not_known_netcash = ~(net_cash_pct.notna() & (net_cash_pct > 0.10))
    heavy_debt = _not_known_netcash & (
        ((nde_real >= 3.0) & (nde_real <= 30.0)) |
        ((ev_over_mcap >= 1.75) & (ev_over_mcap <= 30.0) & _real_leverage))
    df['arch_weschler_levered_equity'] = (
        is_operating &                              # (R1b) RE developers: inventory financing != Valassis fixed-debt-amortisation thesis
        (robust_cy >= 0.15) & (robust_cy <= 2.0) &  # cheap on ROBUST cash (Lindy)
        (owner_ey >= 0.08) & (owner_ey <= 2.0) &    # corroborated by reported FCF
        (ebitda_ttm_v > 0) &                     # EBITDA to service the debt
        heavy_debt &                             # enormous debt burden
        (fcf_ttm_v > 0) &                        # cash to amortise (deleverage)
        _not_melting &   # (deep-audit) the levered stub must be operationally viable — now via the cash-on-cash-aware + improvement-lenient survivability leg (AMTD, a misclassified financial holdco, is handled at the source via _known_holdco; a genuinely cash-generating levered stub is kept, per user: demote don't bar on margin alone).
        ((ebitda_yoy_v >= 0) | (ebitda_inflection > 0) | season_robust) &  # stable/rising (seasonality-robust)
        ~(_ncol('fq_netdebt_change_pct_assets') > 0) &   # (audit 3) AMORTISING: net debt not rising where the quarterly balance sheets measure it
        _soft_ok_above('interest_coverage', 1.5) &  # (audit 3) can service through a downturn (IC >= 1.5, not 1.05)
        ~(_ncol('tc_min_ic') < 1.0) &               # (audit 3) ...and never uncovered in the cached FYs
        (mcap > 0) & (mcap < 5e9)                # small/mid, where this is mispriced
    ).fillna(False).astype(int)

    # ---------- Asymmetric Assembly (PSIX-type levered inflection stub) ------
    # The rare CAUSAL SYSTEM behind exceptional asymmetry (Power Solutions
    # International, May 2024), where several engines reinforce one another —
    # remove one and the payoff distribution changes materially, so this is a
    # deliberately STRICT conjunction (rare by design, not broadened):
    #  (1) a bad HEADLINE conceals improving unit economics — revenue flat/down
    #      while margins & gross profit rise on a mix shift (an amateur screen
    #      rejects "revenue down"; the causal read sees better economics);
    #  (2) it sits beneath a HEAVY debt load — a small equity stub = convex
    #      payoff (a modest EV gain multiplies a thin equity claim);
    #  (3) operating cash is actively DELEVERAGING — value transfers from
    #      lenders to shareholders as EBITDA rises and debt falls;
    #  (4) it is priced CHEAPLY on the improving (not the headline) earnings;
    #  (5) it is BEATEN-DOWN / low-expectations — a latent recognition catalyst;
    #  (6) it is SURVIVABLE — positive pledgeable cash flow (Holmström-Tirole),
    #      not a melting-ice going-concern with no internal cash.
    # The operating-improvement leg uses the multi-angle/multi-interval
    # confirmation (robust to which margin line the mix shift shows up in).
    # The concealed improvement must be SUBSTANTIAL (PSIX: gross profit +10% on
    # revenue -18%, +6.8pp margin, net income +91%) — not a single weak signal.
    # Strong when confirmed across measures/intervals, OR EBITDA up double
    # digits, OR the exact PSIX divergence (gross profit growing while revenue
    # falls, available once names carry the Tier-B gross_profit_yoy field).
    _gpy = _num('gross_profit_yoy')
    strong_op_improvement = (
        (oper_lev_score >= 0.40) |                       # confirmed multi-angle/interval
        (ebitda_yoy_v >= 0.15) |                          # EBITDA up meaningfully
        ((_gpy > 0) & (rev_yoy_c < _gpy))                # PSIX divergence (GP up, rev down)
    )
    df['arch_asymmetric_assembly'] = (
        is_operating &                          # (R1b) RE developers/REITs: structural leverage + revaluation EBITDA fakes the thesis
        (mcap > 0) & (mcap < 5e9) &
        # (1) bad headline, SUBSTANTIALLY better economics on a flat/down top line
        (rev_yoy_c <= 0.05) & season_robust & strong_op_improvement &   # (audit 3) seasonality-robust lenses only in this strict conjunction (no raw sequential)
        # (2) levered equity stub -> convexity (EV >> equity)
        heavy_debt &
        # (3) survivable + pledgeable income actively DELEVERAGING (EBITDA
        #     rising cuts the debt/EBITDA ratio and transfers value to equity)
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0)) &
        ~(_ncol('fq_netdebt_change_pct_assets') > 0.02) &   # (audit 3) net debt NOT rising where the quarterly balance sheets are measured
        _soft_ok_above('interest_coverage', 1.0) &   # (audit 3) can service the debt (soft; IC < 1 is a solvency countdown)
        # (4) cheap on the improving earnings (two independent measures)
        (((ev_ebitda_v > 0) & (ev_ebitda_v <= 7.0)) | (robust_cy >= 0.15)) &
        # (5) beaten-down / low expectations (recognition catalyst latent)
        beaten_down_any(0.35) &
        # (6) high marginal return on an unstretched base (soft guard)
        _soft_ok_below('capex_intensity', 0.15)
    ).fillna(False).astype(int)

    # ---------- Levered Inflection Stub (looser PSIX — revenue-agnostic) -----
    # The same convex causal engine as the Asymmetric Assembly WITHOUT the
    # strict "bad headline / revenue-down" signature: a heavily-levered equity
    # stub whose operating economics are inflecting and DELEVERAGING, priced
    # cheaply and beaten down — but revenue may be flat, down, OR growing (a
    # levered grower re-rating counts too). Broader than the strict PSIX
    # conjunction; the operating improvement must still be real.
    _DEMOTED.setdefault('levered_inflection', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    df['arch_levered_inflection'] = (
        is_operating &                           # (R1b) RE developers/REITs: structural leverage + revaluation EBITDA fakes the thesis
        (mcap > 0) & (mcap < 5e9) &
        oper_lev_any & strong_op_improvement &   # real operating improvement (any rev dir.)
        (heavy_debt | nde_real.between(1.5, 3.0)) &   # (audit 4) the source's own band (ND/EBITDA 1.5-3x) admitted beside the heavier stubs
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &  # survivable + cash
        _not_melting &   # (deep-audit) the leakiest levered gate gains the survivability leg — now cash-on-cash-aware + improvement-lenient, so a genuine melting-ice stub with no cash and no inflection (LINK.JK op-47%/fcf-/roce-9%) fails, but a cash-generative or inflecting levered stub is kept (per user: demote, don't bar on op-margin alone).
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0)) &           # deleveraging (rising EBITDA)
        ~(_ncol('fq_netdebt_change_pct_assets') > 0.02) &           # (audit 3) net debt actually NOT rising where the quarterly balance sheets measure it
        _soft_ok_above('interest_coverage', 1.5) &                  # (audit 3) can service the debt (IC >= 1.5 where measured; balance sheet first)
        (((ev_ebitda_v > 0) & (ev_ebitda_v <= 8.0)) | (robust_cy >= 0.12)) &  # cheap
        beaten_down_any(0.25) &                  # beaten down / low expectations (any lens)
        _soft_ok_below('capex_intensity', 0.15)
    ).fillna(False).astype(int)
    # (audit 4) the SOURCE band is the core (ND/EBITDA 1.5-3x, net debt not rising
    # is already a leg); heavier stubs stay as levered_inflection_watch
    _tier('levered_inflection', nde_real.between(1.5, 3.0), measured=nde_real.notna())
    # (audit 3) the levered-stub tier so sizing can follow the probability of
    # zero: 1 = nde <= 4, 2 = 4-8, 3 = 8-30 (speculative); the levered_inflection
    # CORE is nde 1.5-3x (the _tier above), not tier 2
    df['levered_stub_tier'] = pd.Series(np.select(
        [nde_real <= 4.0, nde_real <= 8.0, nde_real <= 30.0], [1, 2, 3], default=0),
        index=df.index).where(heavy_debt).astype(float)

    # ---------- Insider Conviction (SEC Form 4 revealed preference) ----------
    # Alignment inferred from COSTLY ACTIONS, not language: officers,
    # directors or 10%-owners BUYING common stock in the OPEN MARKET (code P)
    # over the last ~12 months. Cluster buys (>=2 insiders) and 10%-owner
    # buys are the strongest; require a NET-buyer position (bought more than
    # sold) and a value-oriented price so it reads as conviction, not a pump.
    # US-only (SEC filers), sparse but high-signal.
    insider_cluster = s('insider_cluster_buy_flag')
    insider_10pct = s('insider_10pct_buy_flag')
    insider_officer = s('insider_officer_buy_flag')
    insider_net_flag = s('insider_net_buyer_flag')
    # (growth-audit) pb<2.5 is trivially true for banks, so the value leg
    # degenerated into "an insider bought a bank near book". Keep the genuine
    # insider signal but require financials/REITs to be at a REAL discount to
    # book (pb<1.0); operating names keep the 2.5 ceiling.
    _pb_cap_ic = pd.Series(np.where(is_financial | is_reit, 1.0, 2.5),
                           index=df.index)
    df['arch_insider_conviction'] = (
        ((insider_cluster > 0) | (insider_10pct > 0) | (insider_officer > 0)) &
        (insider_net_flag > 0) &                 # net buyer over the window
        ~((_ncol('fmp_insider_net_usd_12m') / mcap.where(mcap > 0)) < 0.0005) &   # (audit 3) a SIZE floor where the 12-month dollar record exists: net buying >= 0.05% of mcap (a token purchase is not conviction)
        (mcap > 0) & (mcap < 20e9) &
        _not_melting &                           # (tail) a bare low-P/B value leg admitted deep burners (SNES op-242%, AVX op-1323%)
        # (topcheck) financials/REITs are valued on BOOK ONLY — the EV/EBITDA,
        # FCF-yield and cheap_any lenses are meaningless for a bank and were
        # letting >1x-book banks (FXNC 1.48x, PCB 1.19x) bypass the pb<1.0 gate.
        (((is_financial | is_reit) & (pb > 0) & (pb < 1.0))
         | (~(is_financial | is_reit)
            & (((ev_ebitda_v > 0) & (ev_ebitda_v <= 15.0)) | ((pb > 0) & (pb < _pb_cap_ic))
               | (fcf_yield >= 0.03) | cheap_any)))
    ).fillna(False).astype(int)
    # (endpoint matrix, EXC) buying INTO a drawdown (panel distance from the
    # 52w high) and the breadth of buyers rank the members
    _SPIRITED.append('insider_conviction')

    # ---------- Cheap-sales scaling-to-profit ----------
    # A grower the market prices cheaply on SALES (low P/S) and cheaply
    # relative to that growth (low P/S-to-growth), whose operating margins
    # are IMPROVING (operating-leverage confirmation) and that is at or near
    # profitability. The classic un-re-rated scaling business: cheap on the
    # top line today, inflecting toward the profits that justify a re-rate.
    psg_v = s('psg', 99.0)
    op_margin_real = _num('op_margin')           # NaN-preserving (missing != 0)
    near_profit = (
        (op_margin_real >= -0.15) |              # margin PRESENT & within 15% of breakeven
        (ebitda_ttm_v > 0) |                     # already EBITDA-profitable
        (fcf_ttm_v > 0) |                        # cash-generative
        (ni_first_pos > 0) | (ebitda_first_pos > 0) | (fcf_first_pos > 0)  # just crossed
    )
    _DEMOTED.setdefault('cheap_sales_scaler', []).extend([(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')), -1)])
    df['arch_cheap_sales_scaler'] = (
        (mcap > 0) & (mcap < 5e9) &
        (_num('revenue_ttm_usd') >= 5e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (p_s_v >= 0.10) & (p_s_v <= 2.0) &       # cheap on revenues (lower bound kills
                                                 #   near-zero-mcap p_s artifacts)
        (rev_yoy_c >= 0.10) &                    # actually growing (double-digit)
        ((rev_yoy_c <= 1.0) | (_ncol('revenue_3y_cagr') >= 0.15)) &  # (non-XR review) base-effect/M&A guard (sibling has it)
        (((psg_v >= 0.005) & (psg_v <= 0.10)) |
         (_ncol('psg').isna() & (_ncol('evsg') >= 0.004) &
          (_ncol('evsg') <= 0.08))) &              # cheap RELATIVE to growth (PSG,
                                                 #   EVSG analog when PSG missing)
        (season_robust                           # (audit 3) operating margins improving on a seasonality-robust lens (no raw sequential)
         | (_fqx_inc >= 0.15).fillna(False)) &   # (endpoint matrix) or TTM incremental EBIT margin >= 15%
        near_profit                             # at / near / just-crossed profitability — (gate-audit) dropped _profit_present, which CONTRADICTED near_profit's own sub-breakeven (op>=-15%) arm and excluded 115 near-breakeven scalers the thesis targets

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

    # ---------- Exceptional EV/sales vs growth ----------
    # A fast grower priced at an EXCEPTIONALLY low EV/sales relative to that
    # growth (EVSG). Capital-structure-neutral (EV, not price) analog of PSG,
    # so it compares levered and unlevered growers fairly. We have no
    # organic-vs-total revenue split, so total revenue growth stands in for
    # organic. A light quality gate keeps out pre-revenue cash-burn shells.
    evsg_v = s('evsg', 99.0)
    _DEMOTED.setdefault('exceptional_evsg', []).extend([(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')), -1)])
    df['arch_exceptional_evsg'] = (
        (mcap > 0) & (mcap < 20e9) &
        (_num('revenue_ttm_usd') >= 5e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (((evsg_v >= 0.002) & (evsg_v <= 0.05)) |
         (_ncol('evsg').isna() & (_ncol('psg') >= 0.0025) &
          (_ncol('psg') <= 0.06))) &               # EXCEPTIONAL EV/sales-to-growth
                                                 #   (PSG analog when EVSG missing)
        # (endpoint matrix, PROXY) growth on the DATE-MATCHED TTM (quarterly
        # panel) where present, the snapshot rev_yoy only as the fallback
        (_ncol('fq_rev_growth').fillna(rev_yoy_c) >= 0.20) &   # strong (organic-proxy) growth
        ((s('ebitda_ttm', np.nan) > 0) | (s('op_margin', np.nan) > 0)) &   # (audit 3) profitability on an OPERATING lens (an FCF-only print is a working-capital year)
        ((_ncol('fq_rev_growth').fillna(rev_yoy_c) <= 1.0) | (_ncol('revenue_3y_cagr') >= 0.15)) &  # (deep-audit) BASE-EFFECT guard: a huge one-year print mechanically makes EVSG (valuation/growth) look "exceptional" off a one-off denominator (B9A.F rev+346%/PE307, 088130.KQ +234%). A >100% YoY must be corroborated by a durable 3y CAGR (mirrors tenbagger's _g_confirmed discipline).
        (ev_sales_v >= 0.15) & (ev_sales_v <= 4.0) &  # sales-multiple meaningful (lower
                                                 #   bound drops razor-margin traders /
                                                 #   near-zero-EV artifacts) yet not rich
        _profit_present                          # (reference II) a profitability LEVEL, not a -15%-margin grower on rate alone

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

    # ---------- Negative / low EV + sub-book deep value ----------
    # The market cap is at or below net cash (negative or tiny EV — you are
    # effectively PAID to own the operating business) OR the price is well
    # below book. A survivability gate (positive cash flow OR a big net-cash
    # cushion) keeps out the melting-ice cash-burners where the cash is a
    # depleting, not a protective, asset (the Belluscura lesson).
    ev_raw2 = _num('enterprise_value')
    neg_or_low_ev = (
        (ev_raw2 < 0) |                          # negative EV
        (cash_gt_ev > 0) |                       # cash exceeds EV
        (net_cash_pct_sane >= 0.75)              # (G2) net cash 75-100% of mcap (sane)
    )
    _DEMOTED.setdefault('negative_ev_value', []).extend([(_ncol('fmp_altman_z'), 1)])
    df['arch_negative_ev_value'] = (
        is_operating &                                # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 5e9) &
        # (gate-audit) the survivability floor belongs on the NEG-EV/CASH branch
        # (a cash-below-EV shell needs cash generation or a real cushion); on the
        # deep SUB-BOOK branch it reduces to a profitability floor that excludes
        # 265 non-melting cheap turnarounds the thesis wants — there, _not_melting
        # alone is the correct survivability gate.
        # (audit 3) net cash alone is not survivability: the cushion counts
        # only with a runway >= 3 years (net cash / annual FCF burn, both over
        # mcap) or a not-burning name
        ((neg_or_low_ev & ((fcf_ttm_v > 0) | (ebitda_ttm_v > 0)
                           | ((net_cash_pct_sane >= 0.5) & ~(fcf_yield < -(net_cash_pct_sane / 3.0)))))
         | ((pb > 0) & (pb < 0.7))) &
        _not_melting   # (deep-audit) FOM roce-98%, WLN roce-99% operationally melting still removed on BOTH branches
    ).fillna(False).astype(int)

    # ---------- "Growth algorithm" compounding flywheel ($DLO logic) ----------
    # The DLocal-style algorithm: gross-profit growth (~20%) + operating
    # leverage (EBIT growing FASTER, ~25%) + a shrinking share count (~-5%
    # buybacks) COMPOUND into outsized FCF/share growth (~30%), bought cheap on
    # EV/FCF (~13x de-rating toward ~5x as FCF compounds). We can screen the
    # core stack now — top-line growth, operating leverage, FCF compounding,
    # cheap EV/FCF. The PRECISE legs (gross-profit vs EBIT growth split, and
    # the share-count −5% / FCF-per-share +30% legs) need gross_profit_yoy,
    # EBIT growth and a share-count trajectory the enricher must add — the
    # buyback here is a soft bonus (buyback_yield is only ~4% covered).
    fcf_yoy_v = s('fcf_yoy')
    # (user rule) fcf_ttm is LEVERED FCF (CFO - capex, post-interest) — an
    # equity-holder cash flow — so the cheapness multiple is P/FCF (mcap/FCF),
    # never EV/FCF: pairing an enterprise numerator with a levered denominator
    # over-penalises exactly the levered growers. Same 2-15x band (P/FCF 15 ~
    # a 6.7% FCF yield; lower bound still drops near-zero artifacts).
    # (non-XR review) mcap is USD (market_cap_usd) — divide by USD FCF, not
    # local, or the P/FCF band silently excludes the ~62% non-USD universe
    _fcf_usd_ga = _num('fcf_ttm_usd')
    p_fcf = mcap / _fcf_usd_ga.where(_fcf_usd_ga > 0)
    _DEMOTED.setdefault('growth_algo', []).extend([(_ncol('fcf_margin'), 1)])
    df['arch_growth_algo'] = (
        (mcap > 0) & (mcap < 50e9) &
        (_num('revenue_ttm_usd') >= 20e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (rev_yoy_c >= 0.15) &                    # top-line (gross-profit) growth
        (season_robust | (_ncol('fqx_inc_ebit_margin_dt') >= 0.20)) &   # (audit 3) operating leverage on a seasonality-robust lens or the TTM incremental margin (no raw sequential)
        (fcf_ttm_v > 0) &
        ~(_ncol('fq_shares_yoy') > 0.02) &       # (audit 3) the count is not growing on the quarterly statements (global)
        ((fcf_yoy_v >= 0.20) |
         (_ncol('fcf_per_share_yoy') >= 0.20) |
         (_ncol('fqx_fcf_ps_g') >= 0.20) |        # (endpoint matrix) TTM FCF per diluted share, date-matched
         (_ncol('fcf_yoy').isna() & _ncol('fcf_per_share_yoy').isna()
          & (_ncol('cfo_yoy') >= 0.20))) &        # FCF compounding (any per-share/agg lens)
        (p_fcf >= 2.0) & (p_fcf <= 15.0) &       # cheap on P/FCF (levered FCF vs MCAP,
                                                 #   per the levered-measure rule; lower
                                                 #   bound drops near-zero artifacts)
        not_diluting                             # not clearly issuing shares (soft:
                                                 #   excludes only names KNOWN to dilute
                                                 #   >2%; missing data still qualifies).
                                                 #   The precise DLO share-count -5% /
                                                 #   FCF-per-share +30% legs upweight via
                                                 #   buyback_score as coverage fills in.
    
        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

    # ---------- "Asleep at the wheel" (chronic estimate beats) ----------
    # Management/analysts consistently under-estimate the business: it beats
    # the sell-side estimate quarter after quarter (high cumulative beat rate
    # + streak, or an inflecting surprise). Populates as names re-enrich with
    # the earnings-surprise fields.
    # Fire on EITHER chronic 4-quarter estimate beats OR — reaching further
    # back than the 4Q window — durable YoY EPS growth over the last ~2 years.
    beat_rate = _num('earnings_beat_rate')
    _beat_legs = ((beat_rate >= 0.75).fillna(False).astype(int)
                  + (_num('avg_earnings_surprise') > 0.02).fillna(False).astype(int)
                  + ((_num('earnings_beat_streak') >= 3) |
                     (_num('earnings_surprise_inflecting') > 0)).fillna(False).astype(int))
    # DESIGN (per user): asleep_at_wheel does NOT impose a quality FLOOR — a
    # genuinely underestimated business can beat estimates through a rough
    # patch, and gating on quality would drop exactly those names. Quality is
    # instead UPWEIGHTED in asleep_score (below), so the high-quality
    # underestimated names rank first without excluding the rest. The only
    # guards kept are VALIDITY guards (not quality): the EPS-fallback branch
    # still requires a real, non-shrinking, investable-scale operating base so
    # a growing EPS off a base-effect / sub-scale shell (a data artifact, not a
    # beat) does not fire.
    _asleep_eps_branch = (
        (_num('eps_yoy_positive_share') >= 0.75) &    # grew YoY in >=75% of recent Q…
        (_num('eps_yoy_growth_streak_q') >= 3) &      # …with a 3-quarter growth streak
        is_operating & (rev_yoy >= 0) &               # validity: not a shrinking-base artifact
        (_num('revenue_ttm_usd') >= 20e6)             # validity: investable scale
    )
    _asleep_beats_branch = ((beat_rate >= 0.75) & (_beat_legs >= 2))
    # (recipe upgrade, FMP dynamics) FORWARD edition of "asleep at the wheel":
    # the consensus is wrong not only about the PAST (beats) but about the
    # FUTURE — forward revenue growth is modelled well below the trajectory the
    # company is actually delivering (fmp_dyn_fwd_underestimate_gap), while it
    # keeps beating. Guidance off the mark is itself the underestimation signal.
    # Additive OR-branch (no veto), with the same validity guards as the EPS
    # branch so a sub-scale/shrinking artifact cannot fire it.
    _asleep_fwd_branch = (
        (_num('fmp_dyn_fwd_underestimate_gap') >= 0.10)
        & (beat_rate >= 0.60)
        & is_operating & (rev_yoy >= 0) & (_num('revenue_ttm_usd') >= 20e6)
    )
    # (audit 3) branch (b) — an EPS growth record with NO estimate behind it —
    # is not "the consensus asleep": no estimate, no wheel. It is surfaced as
    # asleep_eps_watch; the core needs a beat record or a forward gap.
    df['asleep_eps_watch'] = (_asleep_eps_branch & ~_asleep_beats_branch
                              & ~_asleep_fwd_branch.fillna(False)).fillna(False).astype(int)
    df['arch_asleep_at_wheel'] = (
        _asleep_beats_branch
        | _asleep_fwd_branch.fillna(False)
    ).fillna(False).astype(int)
    # (tighten) a 4-quarter 75% beat rate is the base rate (40% of covered
    # names). Core: 7 of the last 8 reports beat, or a perfect 4/4 with a >=2%
    # average surprise. Exceptional: 7/8 AND >= 3 of those beats the price
    # ignored (the market is asleep, not just the analysts).
    _tier('asleep_at_wheel',
          (_ncol('evt_beats_8q') >= 7) | ((_ncol('earnings_beat_rate') >= 1.0) & (_ncol('avg_earnings_surprise') >= 0.02)),
          (_ncol('evt_beats_8q') >= 7) & (_ncol('evt_ignored_beats_2y') >= 3),
          elite_metric=pd.concat([_ncol('evt_surprise_4q'), _ncol('avg_earnings_surprise')], axis=1).max(axis=1),
          measured=_ncol('evt_beats_8q').notna() | _ncol('earnings_beat_rate').notna())
    df['asleep_score'] = (df['asleep_score'] * df['arch_asleep_at_wheel']).round(3) if 'asleep_score' in df else 0
    # Quality-UPWEIGHTED ranking score: the underestimation signal earns a name
    # into the archetype, but quality (returns on capital, margins, profitability,
    # conservative leverage) carries the majority of the RANK weight, so the
    # market-underestimating-a-GOOD-business names surface first.
    _asl_quality = (
        0.35 * _ramp(s('roce'), 0.0, 0.25)                              # returns on capital
        + 0.25 * _ramp(ebitda_margin, 0.0, 0.30)                        # margin quality
        + 0.20 * (s('op_margin', np.nan) > 0).fillna(False).astype(float)  # profitable
        + 0.20 * (~((nde > 1.5) & (nde < 90))).astype(float)            # conservative leverage
    ).clip(0, 1)
    _asl_beat = (
        0.5 * _ramp(beat_rate, 0.5, 1.0)
        + 0.3 * _ramp(_num('avg_earnings_surprise'), 0.0, 0.10)
        + 0.2 * ((_num('earnings_beat_streak') >= 3)
                 | (_num('earnings_surprise_inflecting') > 0)).fillna(False).astype(float)
    ).clip(0, 1)
    df['asleep_score'] = (((0.6 * _asl_quality + 0.4 * _asl_beat).clip(0, 1))  # quality upweighted (60%)
                          * df['arch_asleep_at_wheel']).round(3)

    # ---------- "Asleep + unrerated" (chronic beats, LITTLE multiple expansion) --
    # (user spec) The deepest form of the asleep trade: the market has been
    # REPEATEDLY told (the same chronic-beats / durable-EPS entry test as
    # arch_asleep_at_wheel) and STILL has not re-rated the name — over the
    # past year the multiple expanded little or not at all, through ANY lens:
    #   (a) the EV/Sales multiple's own change <= +10% (or compressed),
    #   (b) the price return lagged the fundamentals (price_yoy <= median of
    #       revenue/EBITDA growth — the beats landed, the price did not),
    #   (c) implied P/E expansion (price return vs fundamental growth)
    #       <= +10%.
    # A modest not-already-rich guard keeps out names whose multiple never
    # expanded because it already prices perfection (missing = permissive,
    # per breadth doctrine — richness unknown is not richness).
    _esc_au = _num('ev_sales_change_yoy')
    _pyw_au = _num('price_yoy')
    _fund_g_au = pd.concat([rev_yoy, _num('ebitda_yoy')],
                           axis=1).median(axis=1, skipna=True)
    _pe_exp_au = ((1.0 + _pyw_au)
                  / (1.0 + _fund_g_au.where(_fund_g_au > -0.9)) - 1.0)
    # (recipe upgrade, FMP dynamics) The native lens reconstructs the prior
    # EV/Sales from a single price_yoy — noisy and US-tilted. fmp_dyn_unrerated_gap
    # is the REAL divergence: multi-year revenue CAGR minus the actual EV/Sales
    # change from FMP's historical enterprise-value series. A large positive gap
    # (fundamentals compounded, the multiple did not follow) is the cleanest,
    # global "still not re-rated" evidence — added as an extra lens.
    # (weekly panel + quarterly statements) the TWO-YEAR lens: TTM sales /
    # EBIT compounded well ahead of the 104-week price return — "told and
    # ignored" over the full base, not one noisy 12-month window
    # (audit 3) the 1-year coil PER SHARE (a diluter's sales growth is not
    # the holder's), and "not re-rated" needs >= 2 of the lenses to agree
    _sh1_au = np.log1p(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')).fillna(0))
    _no_rerate_lenses = pd.concat([
        (_esc_au <= 0.10),
        ((_pyw_au <= _fund_g_au - _sh1_au) & _pyw_au.notna() & _fund_g_au.notna()),
        (_pe_exp_au <= 0.10),
        (_num('fmp_dyn_unrerated_gap') >= 0.15),
        ((_num('bs_coil_rev') - _sh1_au * (2 / 3)) >= np.log(1.25)),
        (_num('bs_coil_ebit') >= np.log(1.40)),
        # (dated EV series) the multiple itself: EV/Sales down >= 10% over the
        # year, or >= 15% below its own 3-year median
        (_ncol('evh_evs_log_chg_1y') <= -0.10),
        (_ncol('evh_evs_vs_med_3y') <= -0.15)], axis=1).fillna(False).astype(int).sum(axis=1)
    _no_rerate_au = (_no_rerate_lenses >= 2)
    # (endpoint matrix, for xr_audited_streak_unrerated) the 1-year coil on
    # the panel: date-matched TTM sales growth >= the 52-week TOTAL return
    # (the multiple did not follow the sales) — a measured no-rerate lens.
    # Kept separate so asleep_unrerated (already tiered on it) is untouched.
    _coil1_xr = ((np.log1p(_ncol('fq_rev_growth')) - np.log1p(_ts_r52)) >= 0).fillna(False)
    _pe_au = _num('p_e')
    _not_rich_au = (((_pe_au > 0) & (_pe_au <= 25))
                    | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 14))
                    | (_pe_au.isna() & _num('ev_ebitda').isna()))   # ev_ebitda_v is 99-filled and never NaN
    df['arch_asleep_unrerated'] = (
        (df['arch_asleep_at_wheel'] == 1) &
        _no_rerate_au.fillna(False) &
        _not_rich_au.fillna(False) &
        _not_melting
    ).fillna(False).astype(int)
    # (tighten) "not re-rated" measured: sales growth >= the 52-week total
    # return (1-year coil >= 0) or the 2-year coil. Exceptional: the market
    # FADES the beats (average earnings-week reaction to beats <= 0).
    _c1_au = np.log1p(_ncol('fq_rev_growth')) - np.log1p(_ncol('ts_r52'))
    df['unrerated_gap_1y'] = _c1_au.round(4)
    _tier('asleep_unrerated',
          (_c1_au >= 0) | (_ncol('bs_coil_rev') >= np.log(1.25)) | (_ncol('bs_coil_ebit') >= np.log(1.40)),
          (_ncol('evt_react_beats_4q') <= 0),
          elite_metric=pd.concat([_c1_au, _ncol('bs_coil_rev')], axis=1).max(axis=1),
          measured=_c1_au.notna() | _ncol('bs_coil_rev').notna() | _ncol('bs_coil_ebit').notna())

    # XR9 — Audited streak, unrerated ('XR-AuditedStreakUnrerated'):
    # (user: streaks LONGER than four quarters) 8+ CONSECUTIVE quarters of
    # FILED growth (revenue or parent NI, from ~7yr of EDGAR quarterlies
    # with the missing-Q4 synthesized — not estimates, not provider caps),
    # with an honest window (>=8 comparisons available), while the market
    # has NOT re-rated (the asleep_unrerated no-rerate evidence) and the
    # multiple is not already rich. The longest-duration told-and-ignored
    # signal the data supports.
    # (recipe upgrade, FMP dynamics) The native streak is EDGAR US-only. Add the
    # GLOBAL streak from FMP quarterly statements (fmp_dyn_rev/ni_streak_q) and
    # its honest window (fmp_dyn_quarters) so the longest-duration told-and-
    # ignored signal fires for non-US names too — the reach win for this XR gate.
    # fmp_dyn streaks use a POSITIONAL 4-period lag: for a half-yearly filer
    # that is a 2-year comparison counted in half-years, so they are used only
    # for quarterly filers. rev/ni_yoy_streak_q already carry the DATE-matched
    # fmp_quarterly streaks (quarter-equivalents) where EDGAR is absent, with
    # the matching date-matched comparison window below.
    _dyn_q_ok = ~(_ncol('fmp_q_periods_per_year') == 2)
    _stk_best = pd.concat([_ncol('ni_yoy_streak_q'),
                           _ncol('rev_yoy_streak_q'),
                           _ncol('fmp_dyn_rev_streak_q').where(_dyn_q_ok),
                           _ncol('fmp_dyn_ni_streak_q').where(_dyn_q_ok)], axis=1).max(axis=1)
    _fq_win_qeq = _ncol('fq_rev_yoy_n_cmp') * 4.0 / _ncol('fmp_q_periods_per_year')
    _stk_window = pd.concat([_ncol('streak_quarters_n'),
                             _ncol('fmp_dyn_quarters').where(_dyn_q_ok),
                             _fq_win_qeq], axis=1).max(axis=1)
    df['arch_xr_audited_streak_unrerated'] = (
        is_operating & (mcap > 0) &
        (_stk_best >= 8) &
        (_stk_window >= 8) &
        (_no_rerate_au.fillna(False) | _coil1_xr) &
        _not_rich_au.fillna(False) &
        _not_melting
    ).fillna(False).astype(int)
    # (endpoint matrix, EXC) how many independent no-rerate lenses agree
    # (breadth of the "not re-rated" evidence) — surfaced, and ranked in the
    # spirit score, instead of a >= 2-lens gate
    df['xr_streak_norerate_lenses'] = pd.concat([
        (_esc_au <= 0.10), ((_pyw_au <= _fund_g_au) & _pyw_au.notna() & _fund_g_au.notna()),
        (_pe_exp_au <= 0.10), (_num('fmp_dyn_unrerated_gap') >= 0.15),
        (_num('bs_coil_rev') >= np.log(1.25)), (_num('bs_coil_ebit') >= np.log(1.40)),
        _coil1_xr], axis=1).fillna(False).astype(int).sum(axis=1).where(
            df['arch_xr_audited_streak_unrerated'] == 1)
    _SPIRITED.append('xr_audited_streak_unrerated')

    # XR21 — Confluence ('XR-Confluence', the once-in-a-lifetime meta-gate):
    # the historic outliers were rarely ONE signal — they were CONFLUENCE:
    # a floor AND an engine AND a forensic tell AND a dislocation at once.
    # Fires when >=3 independent XR classes agree on the same name. By
    # construction the rarest flag in the book.
    # FAMILY-BASED CONFLUENCE (rigour A4): the historic outliers were a
    # conjunction of INDEPENDENT supports, not one thesis counted many times.
    # Several XR gates key off the SAME signal (e.g. current EBITDA < mid-
    # cycle trips bigbath/double-trough/latent-bath/cyclical at once), so a
    # raw >=3-gate count overstates independence. Group the gates into four
    # independent FAMILIES and require >=3 DISTINCT families.
    _XR_FAMILIES = {
        'floor': ['arch_xr_neg_ev_growth', 'arch_xr_triple_floor',
                  'arch_xr_floor_inflection', 'arch_xr_clean_net_net',
                  'arch_xr_cannibal_below_cash', 'arch_xr_cannibal_below_tbook',
                  'arch_xr_latent_inflection_floor', 'arch_xr_latent_bath_floor',
                  'arch_xr_asset_owner_catalyst', 'arch_xr_monetization_trifecta'],
        'dislocation': ['arch_xr_forced_seller', 'arch_xr_insider_capitulation',
                        'arch_xr_double_trough', 'arch_xr_quality_crisis'],
        'forensic': ['arch_xr_forensic_floor_growth', 'arch_xr_forensic_multiple_gap',
                     'arch_xr_bigbath_rebound', 'arch_xr_depreciation_cliff',
                     'arch_xr_wc_normalization', 'arch_xr_amortization_mask',
                     'arch_xr_nol_shield', 'arch_xr_growth_capex_masked',
                     'arch_xr_look_through_value', 'arch_xr_float_compounding',
                     'arch_xr_oneoff_loss_mask',
                     'arch_xr_contracted_backlog',
                     'arch_xr_segment_justifies_whole',
                     'arch_xr_deferred_revenue_lead',
                     'arch_xr_cash_tax_advantage',
                     'arch_xr_owned_realestate_value',
                     'arch_xr_discops_mask',
                     'arch_xr_investment_remark',
                     'arch_xr_stake_fv_gap',
                     'arch_xr_lookthrough_earner',
                     'arch_xr_value_unlock',
                     'arch_xr_cash_leads_book'],
        'engine': ['arch_xr_compounding_deployer', 'arch_xr_reusable_assembler',
                   'arch_xr_pre_scale_margin', 'arch_xr_leverage_detonation',
                   'arch_xr_baron_compounder',
                   'arch_xr_harvest_distribution', 'arch_xr_paydown_yield',
                   'arch_xr_cyclical_trough', 'arch_xr_hidden_segment_compounder',
                   'arch_xr_margin_mixshift', 'arch_xr_gross_margin_lead',
                   'arch_xr_peer_margin_gap',
                   'arch_xr_verified_deleveraging'],
        # (audit 3) the two broadest gates (audited_streak_unrerated, gaap_profit_crossover) made the engine
        # family nearly free for any first-profit microcap; they no longer carry the family on their own
    }
    _fam_fired = pd.DataFrame(index=df.index)
    for _fam, _cols in _XR_FAMILIES.items():
        _present = [c for c in _cols if c in df.columns]
        _fam_fired[_fam] = (df[_present].sum(axis=1) > 0).astype(int) if _present else 0
    _xr_family_count = _fam_fired.sum(axis=1)
    df['xr_family_count'] = _xr_family_count.astype(int)
    df['arch_xr_confluence'] = (_xr_family_count >= 3).astype(int)

    # GRADED XR CONVICTION (rigour A5 / B.iv / B.v — down/up-weights that
    # modulate ranking rather than gate membership). Base = distinct families;
    # then:
    #  A5 (soft, cycles can run long): a trough/cyclical firing on a business
    #     with a long NEGATIVE revenue trend is more likely secular decline
    #     than a cycle -> downweight (never excluded).
    #  B.iv: an operating-leverage firing where the revenue DELTA is thin
    #     (< 5%) rests on a fragile incremental margin -> downweight.
    #  B.v: a once-in-a-lifetime firing WITH strong survival (deep net cash or
    #     high interest coverage) is higher-conviction -> upweight.
    _xr_conf = pd.Series(1.0, index=df.index)
    _cyc_fired = (df.get('arch_xr_double_trough', 0) + df.get('arch_xr_cyclical_trough', 0)
                  + df.get('arch_xr_bigbath_rebound', 0) + df.get('arch_xr_latent_bath_floor', 0)) > 0
    _secular_decline = (_ncol('revenue_3y_cagr') < -0.03)
    _xr_conf = _xr_conf.where(~(_cyc_fired & _secular_decline.fillna(False)), _xr_conf * 0.75)
    _oplev_fired = (df.get('arch_xr_leverage_detonation', 0) + df.get('arch_xr_reusable_assembler', 0)
                    + df.get('arch_xr_pre_scale_margin', 0)) > 0
    _thin_delta = (rev_yoy_c < 0.05)
    _xr_conf = _xr_conf.where(~(_oplev_fired & _thin_delta.fillna(False)), _xr_conf * 0.85)
    _once_fired = (df.get('arch_xr_cannibal_below_cash', 0) + df.get('arch_xr_double_trough', 0)
                   + df.get('arch_xr_forced_seller', 0) + df.get('arch_xr_leverage_detonation', 0)
                   + df.get('arch_xr_confluence', 0)) > 0
    _strong_survival = ((net_cash_pct_c >= 0.30) | (_ncol('interest_coverage') >= 5))
    _xr_conf = _xr_conf.where(~(_once_fired & _strong_survival.fillna(False)), _xr_conf * 1.20)
    df['xr_confidence'] = _xr_conf.clip(0.5, 1.5).round(3)
    # a graded XR conviction for ranking the XR tabs: families x confidence
    df['xr_score'] = (_xr_family_count * _xr_conf).round(3)


    # ---------- Templeton "maximum pessimism" (cheap vs own history) ----------
    # Cheap against the company's OWN mid-cycle earnings (EV / normalized 5yr
    # EBITDA — the cyclical adjustment that makes a trough-earnings cyclical
    # look expensive on the spot number but cheap normalized), bought when the
    # price sits near the bottom of its 5-year range / below its 5yr average.
    # Survivability-gated so it is pessimism, not terminal decline.
    # (non-XR review) margin-based mid-cycle (inflation-neutral) instead of
    # the nominal 5yr-EBITDA average, matching the XR fix — else inflationary
    # regimes bias ev_norm high (drop cheap cyclicals) and revenue-decliners
    # bias it low (admit secular decline).
    ev_norm = (_num('enterprise_value') / _midcyc_ebitda.where(_midcyc_ebitda > 0))
    _ev_norm_ebit = (_num('enterprise_value')
                     / _num('normalized_ebit').where(_num('normalized_ebit') > 0))
    df['arch_templeton_pessimism'] = (
        is_operating &                                         # (tail) EV/normalized-EBITDA lens is meaningless for financials/REITs/utilities
        (((ev_norm > 0) & (ev_norm <= 8.0)) |                   # cheap vs mid-cycle
         (ev_norm.isna() & (_ev_norm_ebit > 0) & (_ev_norm_ebit <= 10.0))) &
        # (audit 3) MAXIMUM PESSIMISM read on the 5-year weekly high where the
        # panel has the name (>= 50% off), the stale snapshot lenses only where
        # it does not
        ((_ts_hi260 <= 0.50)
         | (_ts_hi260.isna() & ((_num('price_pct_of_5y_range') <= 0.35) | (_num('price_vs_5y_avg') <= 0.85)))) &
        _ev_sane &                                             # (audit 3) the EV sanity band on ev_norm
        (_dd52 <= -0.15) &                                     # MAXIMUM PESSIMISM = not near a 52w high (a recovered name isn't pessimism); (endpoint matrix) panel-first 52w lens
        ((fcf_ttm_v > 0) | (ebitda_ttm_v > 0) | (net_cash_pct >= 0.30)) &
        _roce_now_ok   # (deep-audit) Templeton buys TROUGH cyclicals (a negative SPOT op margin at trough is the thesis, kept), but a KNOWN-negative current roce is terminal decline not pessimism: DCGO roce-95%, 1V5.F roce-5.9%. The mild _roce_now_ok cut (not _not_melting) preserves positive-op trough cyclicals.
    ).fillna(False).astype(int)
    df['ev_norm_midcyc'] = ev_norm.round(3)
    _SPIRITED.append('templeton_pessimism')   # (endpoint matrix, EXC) depth vs 5y high + never-lost-money rank the members

    # ---------- Credible 10-bagger path (probabilistic decomposition) ----------
    # No 10-bagger is high-probability: 10x over 10y = 25.9% annual compounding.
    # Decompose it and require the arithmetic to CLOSE at the growth the name is
    # ACTUALLY printing — project revenue forward at its demonstrated growth,
    # apply a conservative terminal margin and a NON-HEROIC terminal multiple,
    # and check whether that clears 10x from today's valuation. Because
    # price/sales = mktcap/revenue, absolute revenue and mktcap cancel, so the
    # test is unit-free (no FX):
    #     implied_10x = (1+g)^N * terminal_margin * terminal_multiple / (P/S)
    # Gate on (a) the arithmetic closing, (b) growth actually printed AND
    # confirmed by OPERATING LEVERAGE (profit outpacing sales — the path to the
    # terminal margin), (c) viable unit economics. Then split Credible vs Spec
    # on the reality gates the corpus flags: adjusted profit must be REAL
    # per-share owner cash (not SBC add-backs), and the share count must be
    # stable (no dilution / recent raises). Appier-type = Credible (growth
    # prints, operating leverage, real FCF); Flywire/SuperCom-type = Spec
    # (SBC-heavy adjusted profit / just did an equity raise).
    N_YRS = 10.0
    TERM_MULT = 18.0                                    # non-heroic terminal P/E
    # P/S with an EV/Sales fallback (EV/S is the conservative proxy — EV >=
    # mktcap for net-debt names, so implied_10x only shrinks).
    ps_v = _num('p_s').fillna(_num('ev_sales'))
    # DURABLE growth: median across time bases (YoY, 3y CAGR, 5y CAGR,
    # TTM-sequential annualized) instead of one YoY print — a single
    # acquisition year or COVID base effect no longer sets the whole 10-year
    # extrapolation. Confirmed = >=2 bases at 15%+ (or the robust
    # rev_growth_score agreeing) so the gate stays triangulated.
    _g_lenses = pd.concat([
        _num('rev_yoy').clip(-1.0, 10.0),        # NaN-preserving (rev_yoy_c
                                                 #   defaults missing to 0 and
                                                 #   would dilute the median)
        _num('revenue_3y_cagr'),
        _num('revenue_5y_cagr'),
        (1.0 + _num('rev_qoq_ttm')).pow(4) - 1.0,
        _num('fq_rev_growth'),                   # (endpoint matrix) date-matched TTM vs year-ago TTM
    ], axis=1)
    g10 = _g_lenses.median(axis=1, skipna=True).clip(lower=0.0, upper=0.50)
    _g_confirmed = ((_g_lenses >= 0.15).sum(axis=1) >= 2)
    # Conservative terminal NET margin: reward where already profitable; floor
    # 10%, cap 22% — never assume a fatter margin than a maturing peer holds.
    # (audit 3) op margin is PRE-tax: the terminal NET margin takes 75% of it,
    # and a name below the old 12% floor is modelled at its own (after-tax)
    # margin plus a modest expansion, so the arithmetic can actually fail
    _own_nm = pd.concat([
        _num('op_margin') * 0.75,
        _ebm * 0.65 * 0.75,                             # EBITDA scaled to a net proxy, after tax
    ], axis=1).max(axis=1)
    term_margin = (_own_nm.where(_own_nm >= 0.12,                      # at/above the old 12% floor: own margin (cap 22%)
                                 (_own_nm + 0.03).clip(0.0, 0.12))     # below it: own margin + 3pp expansion, never above 12%
                   .clip(upper=0.22).fillna(0.06))                     # margin unmeasured: the 6% placeholder as before
    # Floor the P/S denominator (a near-zero P/S exploded the ratio to 953M x)
    # and clamp the implied return to a sane ceiling — a 100x implied multiple
    # is already extraordinary; anything above is a denominator artifact.
    implied_10x = (((1.0 + g10) ** N_YRS) * term_margin * TERM_MULT
                   / ps_v.where(ps_v > 0.05)).clip(lower=0.0, upper=100.0)
    df['tenbagger_implied_return'] = implied_10x.round(2)

    # Operating leverage confirms the path to the terminal margin (profit
    # outpacing sales), triangulated across measures/time-bases.
    op_lev_confirm = (
        oper_lev_any |
        (_num('ebit_growth_yoy') > rev_yoy_c) |
        (ebitda_yoy_v > rev_yoy_c)
    )
    viable_econ = (
        (_num('gross_margin') >= 0.20) | (ebitda_ttm_v > 0) | (_num('op_margin') > 0)
    )
    df['arch_tenbagger_path'] = (
        (mcap > 0) & (mcap < 10e9) &                    # 10x easier small/mid ($18m-$2.3bn examples)
        (_num('revenue_ttm_usd') >= 5e6) &             # (R6+FX) real USD revenue base — % growth is noise below this
        (ps_v > 0) & (ps_v < 30) &                      # sane P/S (avoid near-zero-sales artifacts)
        (g10 >= 0.15) &                                 # durable growth printing (median of bases)
        (_g_confirmed | (rev_growth_score >= 0.5)) &    # >=2 bases (or robust composite) agree
        op_lev_confirm &                                # ...confirmed by operating leverage
        viable_econ &                                   # viable unit economics
        (_profit_present                                # profitability LEVEL present (Yartseva) ...
         | ((s('gross_margin', np.nan) >= 0.40)         # ...OR a genuine pre-profit hypergrowth: fat gross margin
            & ((fcf_first_pos > 0) | (fcf_inflection > 0)))) &  # with a real FCF INFLECTION (the early-Amazon path the raw floor lost)
        (implied_10x >= 10.0)                           # the 10x arithmetic closes

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)
    # (audit 3) the size tier the consensus insists on: core <= $1B, the
    # $1-10B band is tenbagger_path_watch
    df['tenbagger_path_watch'] = df['arch_tenbagger_path'].astype(int)
    df['arch_tenbagger_path'] = ((df['arch_tenbagger_path'] == 1) & (mcap <= 1e9)).astype(int)

    # Reality gates — Credible requires BOTH; failing either drops to Spec.
    # Owner-cash reality (the Flywire lesson): adjusted profit is NOT owner cash
    # when real cash is being burned. Credible owner cash requires EITHER
    # genuinely positive FCF, OR a real FCF INFLECTION — positive earnings AND
    # positive OPERATING cash conversion AND FCF only marginally negative
    # (capex / working-capital timing, not a burn). This separates Appier
    # (FCF yield -1.9%, cash conversion +0.47, positive earnings -> Credible)
    # from Flywire (FCF yield -9.9%, cash conversion -4.8, 11% SBC -> Spec).
    # Heavy SBC (>12% of revenue) disqualifies unless FCF is clearly positive.
    _fy = _num('fcf_yield')
    at_fcf_inflection = (
        (_num('earnings_yield') > 0) &
        (_num('cash_conversion') > 0) &
        (_fy >= -0.03)
    )
    # Positive owner cash through ANY lens — fcf_yield is the primary but a
    # name with fcf_ttm > 0 (yield uncomputable) or positive owner-earnings /
    # robust cash yield expresses the same fact.
    _owner_cash_pos = ((_fy > 0) | (fcf_ttm_v > 0) |
                       (_num('owner_earnings_yield') > 0) |
                       (_num('robust_cash_yield') > 0))
    real_owner_cash = (
        (_owner_cash_pos | at_fcf_inflection) &
        (_soft_ok_below('sbc_pct_revenue', 0.12) | (_fy > 0.02))
    )
    # (audit 3) read the FILLED (global) share-growth columns; "dilution is
    # the biggest risk" so MISSING share history cannot pass as stable — a
    # name with no count on any lens is credible_watch, not credible
    _tb_sh1 = _ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')).fillna(_ncol('fg_shares_dil_g1'))   # (financial-growth) the FY diluted count as the last lens
    _tb_sh3 = _ncol('shares_growth_3y').fillna(_ncol('shares_3y_cagr'))
    stable_share_count = (~(_tb_sh1 > 0.05) & ~(_tb_sh3 > 0.10)
                          & (_tb_sh1.notna() | _tb_sh3.notna()))
    df['tenbagger_credible_watch'] = ((df['arch_tenbagger_path'] == 1) & real_owner_cash
                                      & _tb_sh1.isna() & _tb_sh3.isna()).fillna(False).astype(int)
    df['arch_tenbagger_credible'] = (
        (df['arch_tenbagger_path'] == 1) & real_owner_cash & stable_share_count
    ).fillna(False).astype(int)

    # Score (ranking only): margin-of-safety on the arithmetic (how far implied
    # clears 10x, saturating at ~30x) + operating-leverage strength + cash
    # reality + share-count stability.
    _mos = ((implied_10x / 10.0 - 1.0).clip(0, 2) / 2.0).fillna(0.0)
    df['tenbagger_score'] = ((0.35 * _mos
                              + 0.25 * oper_lev_score
                              + 0.10 * rev_growth_score
                              + 0.20 * real_owner_cash.astype(float)
                              + 0.10 * stable_share_count.astype(float))
                             * df['arch_tenbagger_path']).round(3)

    # ---------- EV/Sales derating while sales rip (unpriced growth) ----------
    # The market is NOT pricing in rapid sales growth, so EV/Sales compresses
    # even as revenue compounds: when sales grow 30% but the stock is flat/down,
    # the sales multiple MECHANICALLY derates ~30%. A coiled spring — continued
    # growth plus an eventual re-rating from a depressed multiple is the double.
    # Detect the derating as sales OUTGROWING the stock (rev_yoy - price_yoy),
    # require the multiple to still have room (not already rich) and viable
    # unit economics (not a melting-ice value trap). Upweight where EV/sales-to-
    # growth is genuinely exceptional (evsg) and top-line growth is confirmed
    # across measures/time-bases (rev_growth_score).
    # Stock return through ANY lens: price_yoy with momentum/fresh-ROC
    # fallbacks — the old 0-defaulted read gave names with NO price history a
    # free "stock flat" derate. NaN everywhere now means no derate evidence.
    # Clamp the stock-return input: a data-artifact price_yoy (e.g. +14,000,000%)
    # produced a -144,130 'derate gap'. A stock can't lose >100%; cap the upside
    # at +1000%. rev_yoy_c is already clipped to [-1, 10].
    _stk_ret = (_num('price_yoy').fillna(_num('momentum_12m'))
                .fillna(_num('roc_12m'))).clip(-1.0, 10.0)
    # (dated EV series) the multiple compression READ, not inferred: minus the
    # log change of EV/Sales over the last year from quarterly enterprise
    # values paired with TTM revenue; the sales-growth-minus-return inference
    # only where the dated series does not reach the name
    mult_compression = (-_ncol('evh_evs_log_chg_1y')).fillna(rev_yoy_c - _stk_ret).clip(-11.0, 11.0)
    df['evsales_derate_gap'] = mult_compression.round(3)
    _evsg_exceptional = (evsg_v > 0) & (evsg_v <= 0.08)   # cheap per unit of growth
    # The derate itself, seen through more than one base: the 1y gap, a 3y
    # version (sales CAGR outrunning annualized 3.5y price ROC), or an
    # exceptional growth-adjusted multiple with confirmed growth.
    _roc35_ann = (1.0 + _num('roc_3_5y')).clip(lower=0.0).pow(1.0 / 3.5) - 1.0
    _derate_3y = (-_ncol('evh_evs_log_chg_3y') / 3.0).fillna(_num('revenue_3y_cagr') - _roc35_ann)   # (dated EV series) annualised 3-year compression read where the series reaches the name
    derate_any = (
        (mult_compression >= 0.15) |
        (_derate_3y >= 0.15) |
        (_num('bs_coil_rev') >= 0.15) |      # 2y: log sales growth - log price return (EV/Sales compressing)
        (_evsg_exceptional & (rev_growth_score >= 0.5) &
         ((mult_compression >= 0) | (_derate_3y >= 0)))
    ).fillna(False)
    _DEMOTED.setdefault('evsales_derating', []).extend([(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')), -1)])
    df['arch_evsales_derating'] = (
        (mcap >= 50e6) & (mcap < 20e9) &                # (G6) investable-size floor
        (_num('revenue_ttm_usd') >= 5e6) &              # (gate-audit) MISSING revenue-base floor: rev_yoy>=0.15 off a near-zero base is base-effect noise; every sibling growth gate carries this
        (rev_yoy_c >= 0.15) & ~(_ncol('revenue_3y_cagr') < 0) &  # (deep-audit) HARD positive top-line floor. The old rev_growth_score>=0.6 OR-branch admitted FALLING-sales names (TTEC rev_yoy-3.2%/3y-4.4%/roce-9.7%) because that composite stays high while sales fall, and derate_any rewards a collapsing STOCK — a melting value trap, the anti-thesis. rev_growth_score stays an upweight in the score, not a gate-opener.
        derate_any &                                    # EV/Sales compressing (any base)
        ~(_ncol('evh_evs_log_chg_1y') > 0.20) &          # (dated EV series) a multiple that EXPANDED > 20% over the year contradicts the derate
        ~(_ncol('evh_evs_log_chg_1y').isna() & (_ncol('fmp_dyn_ev_sales_change_3y') > 0.25)) &   # (audit 3) the annual series as the fallback contradiction
        (ev_sales_v > 0.10) & (ev_sales_v <= 6.0) &     # room left; lower bound drops artifacts
        ((_num('gross_margin') >= 0.20) | (ebitda_ttm_v > 0) | (fcf_ttm_v > 0)) &  # not a trap
        ~((ebitda_ttm_v < 0) & (fcf_ttm_v < 0) & (_num('gross_margin') < 0.40))   # (gate-audit) cash sanity, but EXEMPT high-gross-margin (>=40%) pre-profit SaaS scalers — the coiled-spring the thesis is built for (12 were wrongly barred)
    
        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)
    # (tighten) TTM sales growth >= 15% (not one YoY print) outrunning the
    # total return by >= 15% (1y) or the 2-year coil. Exceptional: operating
    # leverage showing (incremental EBIT margin >= 15%).
    _c1_ev = np.log1p(_ncol('fq_rev_growth')) - np.log1p(_ncol('ts_r52'))
    df['derate_gap_1y'] = _c1_ev.round(4)
    _tier('evsales_derating',
          (_ncol('fq_rev_growth') >= 0.15) & ((_c1_ev >= 0.15) | (_ncol('bs_coil_rev') >= 0.15)),
          (_c1_ev >= np.log(1.5)) | (_ncol('bs_coil_rev') >= np.log(1.5)),
          elite_metric=_c1_ev,
          measured=_ncol('fq_rev_growth').notna())
    # Score: depth of the derate + growth confirmation + exceptional evsg bonus.
    _derate_depth = (mult_compression.clip(0, 1.0)).fillna(0.0)     # 0..1
    df['evsales_derate_score'] = ((0.5 * _derate_depth
                                   + 0.4 * rev_growth_score
                                   + 0.1 * _evsg_exceptional.astype(float))
                                  * df['arch_evsales_derating']).round(3)

    # ---------- Lynch "years of progress rewarded in a year" (Fannie Mae) ----
    # The Beating-the-Street pattern: a business advances fundamentally for
    # YEARS while the stock goes nowhere, then the market pays it all at once
    # ($16 -> $42 in 1989). Legs, per the reference S&R + Volatility-Asymmetry
    # methodology (computed by lynch_reward_enrich.py on W/M/Q bars):
    #   FUNDAMENTAL progress  — multi-year business advance (any of: 5y revenue
    #     CAGR, durable EPS growth share, 4-of-5yr FCF, strong confirmed
    #     inflection).
    #   PRICE stagnation      — the long ROC says the market hasn't paid:
    #     3.5y ROC subdued, or 10y ROC modest; with ROC-of-ROC turning
    #     POSITIVE (the reward beginning to arrive).
    #   COIL                  — monthly and/or quarterly volatility asymmetry
    #     NEAR 50 with positive ROC (balanced coil tipping upward).
    #   RELEASE               — long-term (monthly) Squeeze & Release in a
    #     state of RELEASE, recently released after a sustained squeeze.
    # Fire on progress + coil + (release OR roc-setup); upweight completeness.
    # (Monthly bars only for now — the weekly tactical layer is deferred.)
    # -- Years-of-progress leg TRIANGULATED across accounting lenses (the
    #    standard _confirm treatment): the multi-year advance can show up in
    #    the top line, gross profit, EPS durability, cash generation, operating
    #    income durability, reinvestment economics, durable margins, or a
    #    confirmed inflection. Fire on ANY (broadens the pool); score breadth.
    # (Fannie Mae chapter) the business advanced PER SHARE for years
    # (-0.87 -> 0.52 -> 1.44 -> 1.55 -> 2.14): 3- and 5-year NI per share up;
    # it was REINVENTED from a cyclical into a steady earner ("no down quarter
    # since"): loss years on file, yet EPS positive in 7+ of the last 8
    # quarters; and the CORE improved beneath a quiet headline (the block of
    # granite chipped away): TTM EBIT growing faster than revenue
    _lr_transformed = (((_ncol('tc_opinc_pos') < _ncol('tc_years')) & (_ncol('tc_years') >= 5))
                       & (_ncol('fqx_eps_pos_share_8') >= 0.875)).astype(float).where(
                           _ncol('tc_years').notna() & _ncol('fqx_eps_pos_share_8').notna())
    _lr_core_gain = (_ncol('fqx_ebit_ttm_g') - _ncol('fq_rev_growth'))
    df['lynch_transformed_flag'] = (_lr_transformed == 1).fillna(False).astype(int)
    # REINVENTED = transformed for business reasons: at least one loss year
    # OUTSIDE the pandemic window (FY ending 2020-03 .. 2022-03), and the
    # earnings pattern itself changed (Maxwell's "no down quarter" measured):
    # mean |yearly change in operating income| / revenue over the last 3 FYs at
    # most two-thirds of the earlier years'. Unmeasured swing = not reinvented.
    # PANDEMIC RECOVERY = transformed, but every loss year sits inside that
    # window: a rebound to the old pattern, surfaced separately, not reinvention.
    _lr_reinvented = (_lr_transformed * ((_ncol('tc_loss_years_other') >= 1)
                                         & (_ncol('tc_swing_ratio') <= 2 / 3)).astype(float)).where(
                          _lr_transformed.notna() & _ncol('tc_loss_years_other').notna()
                          & (_ncol('tc_swing_ratio').notna() | (_lr_transformed == 0)))
    df['lynch_reinvented_flag'] = (_lr_reinvented == 1).fillna(False).astype(int)
    df['lynch_pandemic_recovery_flag'] = ((_lr_transformed == 1) & (_ncol('tc_loss_years_other') == 0)
                                          & (_ncol('tc_loss_years_covid') >= 1)).fillna(False).astype(int)
    lr_progress_any, lr_progress_score = _confirm([
        (_ncol('fg_ni_ps_3y'),             lambda x: x > 0),       # 3y NI per share up (Fannie)
        (_ncol('fg_ni_ps_5y'),             lambda x: x > 0),       # 5y NI per share up (Fannie)
        (_lr_reinvented,                   lambda x: x == 1),      # reinvented as steady, not a pandemic rebound (Fannie)
        (_lr_core_gain,                    lambda x: x > 0),       # core improving beneath the headline (Fannie)
        (revenue_5y_cagr,                  lambda x: x >= 0.08),   # 5y top line
        (revenue_3y_cagr_v,                lambda x: x >= 0.10),   # 3y top line
        # (audit 3) gross_profit_yoy (one year) and inflection_confirm_score
        # (a point score) are dropped from the FIRING set: "years of progress"
        # is multi-year; both stay in the score below
        (_num('eps_yoy_positive_share'),   lambda x: x >= 0.6),    # EPS durability
        (n_yrs_fcf_pos,                    lambda x: x >= 4),      # FCF durability
        (n_yrs_opinc_pos,                  lambda x: x >= 4),      # op-income durability
        (roiic_lindy,                      lambda x: x >= 0.10),   # reinvestment econ
        (op_margin_lindy,                  lambda x: x >= 0.08),   # durable margins
    ])
    # the ORIGINAL nine-lens breadth, kept for the exceptional leg so the
    # Fannie lenses add to it rather than dilute its share
    _, _lr_prog_orig = _confirm([
        (revenue_5y_cagr, lambda x: x >= 0.08), (revenue_3y_cagr_v, lambda x: x >= 0.10),
        (_num('eps_yoy_positive_share'), lambda x: x >= 0.6), (n_yrs_fcf_pos, lambda x: x >= 4),
        (n_yrs_opinc_pos, lambda x: x >= 4), (roiic_lindy, lambda x: x >= 0.10),
        (op_margin_lindy, lambda x: x >= 0.08)])
    # (audit 3) "years" = at least TWO multi-year lenses agree
    _lr_multi_n = sum(((sr.notna()) & pred(sr).fillna(False)).astype(int) for sr, pred in [
        (_ncol('fg_ni_ps_3y'), lambda x: x > 0), (_ncol('fg_ni_ps_5y'), lambda x: x > 0),
        (_lr_reinvented, lambda x: x == 1),
        (revenue_5y_cagr, lambda x: x >= 0.08), (revenue_3y_cagr_v, lambda x: x >= 0.10),
        (_num('eps_yoy_positive_share'), lambda x: x >= 0.6), (n_yrs_fcf_pos, lambda x: x >= 4),
        (n_yrs_opinc_pos, lambda x: x >= 4), (roiic_lindy, lambda x: x >= 0.10),
        (op_margin_lindy, lambda x: x >= 0.08)])
    lr_progress_any = lr_progress_any & (_lr_multi_n >= 2)
    # -- Fundamental ROC-of-ROC: is the progress itself ACCELERATING? The
    #    second derivative expressed through seven accounting lenses (revenue
    #    and EBITDA growth accelerating, multi-year CAGR acceleration, ROIC /
    #    ROIIC acceleration, margins expanding faster than revenue, surprises
    #    inflecting, EPS growth streaking). Broadens the gate (a name with
    #    sparse multi-year history but clearly accelerating fundamentals is a
    #    legitimate progress candidate when >= 2 lenses agree) and feeds the
    #    score — the price ROC-of-ROC's accounting mirror.
    lr_accel_any, lr_accel_score = _confirm([
        (rev_accel,                            lambda x: x > 0),      # rev growth accelerating
        (_num('ebitda_accel'),                 lambda x: x > 0),      # EBITDA growth accelerating
        (revenue_accel_lindy,                  lambda x: x > 0),      # 3y CAGR > 5y CAGR
        (roiic_accel,                          lambda x: x >= 0.03),  # reinvestment accel
        (roic_acceleration_v,                  lambda x: x > 0),      # ROIC accelerating
        (_num('op_margin_delta_yoy'),          lambda x: x > 0),      # margin expanding vs rev
        (_num('earnings_surprise_inflecting'), lambda x: x > 0),      # surprises inflecting
    ])
    # PROFIT-DURABILITY requirement (validation lesson): acquisition-driven
    # revenue CAGR (Interfor), base-effect recoveries (Singer) and "EPS
    # improving from a loss" (Methode) all passed as "years of progress" while
    # earnings collapsed. Lynch's progress is PROFIT/cash advancing for years,
    # so at least one profit-durability lens must agree — top-line growth
    # alone cannot fire it. Global lenses (ROCE, eps-share + real op margin)
    # cover non-EDGAR names.
    lr_profit_durable = ((n_yrs_opinc_pos >= 4) | (n_yrs_fcf_pos >= 4) |
                         (roiic_lindy >= 0.10) | (op_margin_lindy >= 0.08) |
                         ((_num('roce') >= 0.10) & (ebitda_ttm_v > 0)) |
                         ((_num('eps_yoy_positive_share') >= 0.75) & (_num('op_margin') > 0.05)))
    lr_progress_gate = (lr_progress_any | (lr_accel_score >= 0.28)) & lr_profit_durable
    # LOW-RETURN CAPACITY-BUILDER trap (ACE: MW doubled while profit halved at
    # 5.5% ROCE) — a business earning <6% on capital has no hidden advance for
    # the market to reward. Soft: excludes only where ROCE is PRESENT and low.
    lr_not_capacity_trap = ~(_num('roce').notna() & (_num('roce') < 0.06))
    # REWARD NOT YET PAID (the biggest systematic miss): six of the top twelve
    # had already rallied 40-160% — a monthly release + rising asymmetry AFTER
    # a big rally is the payment arriving, not the coil. Gate on the FRESH
    # 12-month ROC from the just-fetched bars (fallback: master momentum).
    _r12 = _num('roc_12m')
    # (endpoint matrix A.1) the weekly total-return panel is the primary
    # 12-month lens; the lynch-tape ROC / master momentum are fallbacks.
    # (audit 3) UNPAID = price lags progress: 3-year sales / EBIT growth
    # outruns the 3-year total return by >= 25% (log gap), where the panel
    # measures it; the 12-month +35% cut only where it does not
    _lr_gap3 = (pd.concat([np.log1p(_ncol('revenue_3y_cagr')) * 3.0,
                           np.log1p(_ncol('fmp_st_ebit_ps_3y_g'))], axis=1).max(axis=1)
                - np.log1p(_ncol('ts_r156')))
    df['lynch_reward_gap3'] = _lr_gap3.round(4)   # surfaced for the books and the audit gate
    lr_unpaid = ((_lr_gap3 >= np.log(1.25))
                 | (_lr_gap3.isna() & ((_ts_r52 <= 0.35)
                                       | (_ts_r52.isna() & ((_r12 <= 0.35)
                                                            | (_r12.isna() & (_num('momentum_12m') <= 0.35)))))))
    # LIVE TAPE (Icure: a halted stock faked stagnation + release).
    lr_live_tape = ~((_num('stale_tape') > 0) | (_num('last_bar_age_days') > 45))
    # -- Coil: firing keeps the reference near-50-rising flags (M or Q);
    #    the SCORE is continuous — closeness to 50 (1 at 50, 0 at +/-10)
    #    where the asymmetry is rising, best of the two timeframes.
    _coil_m = ((1 - (_num('asym_m') - 50).abs() / 10).clip(0, 1)
               * (_num('asym_m_roc') > 0).astype(float))
    _coil_q = ((1 - (_num('asym_q') - 50).abs() / 10).clip(0, 1)
               * (_num('asym_q_roc') > 0).astype(float))
    lr_coil_score = pd.concat([_coil_m, _coil_q], axis=1).max(axis=1).fillna(0.0)
    # Fire on the discrete near-50-rising flags OR a strong continuous coil —
    # a name at |asym-50| <= 5-and-rising just outside the reference band
    # expresses the same balanced-coil fact (doctrine: continuous over hard
    # threshold; the flags alone dropped every borderline coil).
    lr_near50 = ((_num('asym_m_near50_rising') > 0) |
                 (_num('asym_q_near50_rising') > 0) |
                 (lr_coil_score >= 0.5) |
                 # (endpoint matrix A.1) the WEEKLY coil the monthly layer
                 # deferred: 26-week volume and range contracted vs the base
                 ((_num('bs_vol_ratio') <= 0.7) & (_num('bs_range_ratio') <= 0.4)).fillna(False))
    # -- Release: state + sustained pre-release squeeze; score scales with the
    #    squeeze-run length (a 2-year coil releases harder than a 6-month one)
    #    and the recency of the release.
    lr_release_lt = ((_num('sr_m_release') > 0) &
                     ((_num('sr_m_release_recent') > 0) |
                      (_num('sr_m_squeeze_run') >= 6)))
    lr_release_score = ((_num('sr_m_release') > 0).astype(float)
                        * (_num('sr_m_squeeze_run') / 24.0).clip(0, 1)
                        * (0.6 + 0.4 * (_num('sr_m_release_recent') > 0))).fillna(0.0)
    # -- "Market hasn't paid" expressed through THREE lenses (any fires):
    #    subdued 3.5y ROC accelerating, subdued 10y ROC accelerating, or price
    #    at/below its own 5y average (Tier-B) while the 3.5y ROC accelerates —
    #    the third lens covers names with short chart history.
    _acc35 = _num('roc_accel_3_5y')
    _acc10 = _num('roc_accel_10y')
    # (endpoint matrix A.1) + the panel's 3-year total return beside
    # roc_3_5y: subdued over 3 years (<= +40%) while the last year runs ahead
    # of the 3-year annualised pace (log r52 > log r156 / 3 = accelerating)
    _l156 = np.log1p(_ncol('ts_r156'))
    _ts_acc3 = (np.log1p(_ts_r52) > _l156 / 3.0)
    lr_roc_setup = (((_num('roc_3_5y') <= 0.40) & (_acc35 > 0)) |
                    ((_num('roc_10y') <= 1.00) & (_acc10 > 0)) |
                    ((_num('price_vs_5y_avg') <= 1.00) & (_acc35 > 0)) |
                    ((_ncol('ts_r156') <= 0.40) & _ts_acc3).fillna(False))
    # continuous: how subdued the long ROC is x how strong the acceleration
    _sub35 = ((0.40 - _num('roc_3_5y')) / 0.80).clip(0, 1)
    _sub10 = ((1.00 - _num('roc_10y')) / 2.00).clip(0, 1)
    _set35 = (_sub35 * (_acc35 / 0.50).clip(0, 1)).fillna(0.0)
    _set10 = (_sub10 * (_acc10 / 0.50).clip(0, 1)).fillna(0.0)
    lr_roc_score = pd.concat([_set35, _set10], axis=1).max(axis=1)

    df['arch_lynch_reward'] = (
        (mcap > 0) & is_operating & _not_melting &   # (tail) "progress not yet paid" needs a viable operating business, not a melter (EDUC op-57%)
        lr_progress_gate & lr_not_capacity_trap &
        lr_unpaid & lr_live_tape & lr_near50 &
        (lr_release_lt | lr_roc_setup)
    ).fillna(False).astype(int)
    # Continuous completeness score: coil quality + release depth + roc setup
    # + breadth of the accounting progress (upweight where lenses agree).
    # Buyback points: Fannie announced a 5M-share buyback into the 1987
    # crash — a shrinking share count while the price sleeps is part of the
    # pattern (and the alignment evidence). buyback_score is the triangulated
    # 5-angle composite (share count YoY/3y, net repurchases, buyback yield,
    # per-share outgrowth), so this is robust, not a single field.
    df['lynch_reward_score'] = ((0.25 * lr_coil_score
                                 + 0.225 * lr_release_score
                                 + 0.175 * lr_roc_score
                                 + 0.15 * lr_progress_score
                                 + 0.10 * lr_accel_score
                                 + 0.10 * buyback_score)
                                * df['arch_lynch_reward']).round(3)
    # -- Ranking among firers + EXCEPTIONAL SINGLE LEGS. A blended score
    #    buries outliers: a 2-year-plus squeeze releasing IS the Fannie moment
    #    even when the other legs are ordinary. lynch_leg_max = the strongest
    #    single leg; lynch_exceptional_leg flags leg-specific extremes
    #    (multi-year coil released, razor-balanced coil tipping hard, deep
    #    stagnation snapping upward, or 6-of-9 progress lenses agreeing); the
    #    RANK key takes the better of the blend and the best-leg path and
    #    bonuses the exceptional flag, so both balanced setups and one-leg
    #    monsters surface.
    _legs = pd.concat([lr_coil_score, lr_release_score, lr_roc_score,
                       lr_progress_score, lr_accel_score], axis=1)
    lynch_leg_max = _legs.max(axis=1).fillna(0.0)
    # #6 — reward MORE confirming legs: a setup agreeing across several legs
    # is stronger evidence than one loud leg. Count legs meaningfully firing
    # (> 0.3) and bonus the blended score for breadth (+4% per extra leg
    # beyond the first, capped +15%).
    _lynch_n_legs = (_legs > 0.3).sum(axis=1)
    lynch_leg_breadth = (0.04 * (_lynch_n_legs - 1).clip(lower=0)).clip(0.0, 0.15)
    df['lynch_reward_score'] = ((pd.to_numeric(df['lynch_reward_score'],
                                               errors='coerce').fillna(0.0)
                                 + lynch_leg_breadth * df['arch_lynch_reward'])
                                .clip(0.0, 1.0)).round(3)
    lynch_exceptional = (
        ((_num('sr_m_squeeze_run') >= 24) & (_num('sr_m_release') > 0)) |
        (((_num('asym_m') - 50).abs() <= 2) & (_num('asym_m_roc') >= 10)) |
        (((_num('asym_q') - 50).abs() <= 2) & (_num('asym_q_roc') >= 10)) |
        ((_num('roc_3_5y') <= -0.30) & (_num('roc_accel_3_5y') >= 0.30)) |
        (_lr_reinvented == 1) |                                    # (Fannie) reinvented as a steady earner (ex pandemic rebounds)
        (_lr_prog_orig >= 0.66)
    ).fillna(False)
    # GAAP-masked flag (US-exam lesson: TENB P/E 573, NOVT 113, THRM 49 while
    # EV/EBITDA is modest — GAAP EPS depressed by one-offs/SBC/amortization,
    # which is often exactly WHY the market ignored the progress). Display
    # marker, not a gate.
    df['gaap_masked'] = ((_num('p_e') > 40) &
                         (_num('ev_ebitda') > 0) & (_num('ev_ebitda') < 16)
                         ).fillna(False).astype(int)
    df['lynch_leg_max'] = (lynch_leg_max * df['arch_lynch_reward']).round(3)
    df['lynch_exceptional_leg'] = (lynch_exceptional
                                   & (df['arch_lynch_reward'] == 1)).astype(int)
    df['lynch_rank'] = (pd.concat([df['lynch_reward_score'],
                                   0.80 * df['lynch_leg_max']], axis=1).max(axis=1)
                        + 0.10 * df['lynch_exceptional_leg']
                        + 0.05 * df['lynch_reward_score']).round(3)   # blend breaks leg ties

    # ---------- 52-week-high flags (absolute / relative-to-index) ----------
    # From the lynch price-series enricher: is_52w_high (within 3% of the
    # trailing-12-month high), rel_is_52w_high (the stock/COUNTRY-INDEX ratio
    # at ITS 52w high — strength against the market), base_depth_12m (where
    # the name stood vs its own then-high a year ago: low = the current high
    # is a FRESH emergence from a base, not mid-uptrend).
    _abs_hi = (_num('is_52w_high') > 0)
    _rel_hi = (_num('rel_is_52w_high') > 0)
    df['high_52w_abs'] = _abs_hi.astype(int)
    df['high_52w_rel'] = _rel_hi.astype(int)
    df['high_52w_both'] = (_abs_hi & _rel_hi).astype(int)

    # ---------- "Analyst awakening" (screaming buy, re-rating just begun) ----
    # Analysts are pounding the table but the market has only STARTED to pay:
    # CONVICTION triangulated across three lenses (consensus rating strength,
    # target upside, breadth of coverage — fire needs rating AND one other),
    # without an extended trailing run (fresh 12m ROC <= 50%, momentum
    # fallback where the lynch tape is not yet fetched). A fresh 52w high
    # (absolute or vs the index) emerging from a base (base_depth <= 0.85 a
    # year ago) is NOT required to fire — it is the strongest POSITIVE, the
    # robust form of "re-rating just started" (a new high AND a preceding
    # base), and carries the largest score weight so names where the tape
    # confirms the awakening rank first. Live tape required where covered.
    _rec = _num('yf_recommendation_mean')
    # analyst_target_upside_pct is a FRACTION (median +0.25 = +25%); the old
    # `>= 25` compare meant the upside lens NEVER fired and conviction
    # degenerated to a single 10.9%-covered rating column. Normalize
    # defensively (some feeds emit percent) and fire on ANY 2-of-available
    # conviction lenses rather than requiring the rating outright.
    _ups = _num('analyst_target_upside_pct')
    _ups = _ups.where(_ups.abs() <= 5.0, _ups / 100.0)
    _nan_ = _num('n_analysts').fillna(_num('n_analysts_pew'))
    # (sentiment layer) an AWAKENING is a CHANGE in perception, so the level
    # lenses are joined by momentum lenses: buy share rising, net upgrades,
    # targets being raised, new coverage arriving
    # targets being raised, new coverage arriving. They are a SECOND route in
    # (>= 2 momentum lenses), not extra denominators for the level test —
    # adding them to the level lenses made "half of available" stricter and
    # dropped covered names for the wrong reason.
    conv_any, conv_score = _confirm([
        (_rec, lambda x: (x > 0) & (x <= 2.2)),   # consensus rating strong
        (_ups, lambda x: x >= 0.25),              # >=25% target upside
        # (audit 3) deep coverage (n >= 8) dropped from the conviction stack: a
        # coverage COUNT is not a conviction signal
    ])
    _sent_turn_n = ((_num('sent_buy_share_d12') >= 0.10).fillna(False).astype(int)
                    + ((_num('sent_upgrades_12m') - _num('sent_downgrades_12m')) >= 2).fillna(False).astype(int)
                    + (_num('sent_pt_rev_q') >= 0.05).fillna(False).astype(int)
                    + (_num('sent_initiations_12m') >= 1).fillna(False).astype(int))
    _conviction = (conv_any & (conv_score >= 1.0)) | (_sent_turn_n >= 2)   # every OBSERVED level lens agrees (rating AND upside where both exist)
    # (audit 3) the weekly total-return panel is the primary tape lens; the
    # quote-time ROC / momentum only where the panel is absent
    _not_extended = ((_ncol('ts_r52') <= 0.50) |
                     (_ncol('ts_r52').isna() & ((_num('roc_12m') <= 0.50) |
                                                (_num('roc_12m').isna() & (_num('momentum_12m') <= 0.50)))))
    # (G6) require a REAL consensus rating present and reasonable (not bearish)
    # — the awakening cannot fire on price-target optimism alone (38% did).
    _rating_present = (_rec.notna()) & (_rec > 0) & (_rec <= 3.0)
    # (R9) a genuine EARLY re-rating is not a name in freefall. Target-upside
    # mechanically inflates after a crash, so a stock >35% off its 52w high with
    # no recent momentum is a falling knife, not an awakening. Require it be
    # NOT collapsing: within 35% of the high, or showing positive recent momentum.
    _not_freefall = ((_ncol('ts_dist_hi52') >= 0.65) |
                     (_ncol('ts_dist_hi52').isna() & (_num('pct_off_52w_high') >= -0.35)) |
                     (_ncol('ts_r26') > 0) | (_ncol('ts_r52') > 0) |
                     (_num('momentum_12m') > 0) | (_num('roc_6m') > 0))
    # (audit 3) a clinical-stage developer's "awakening" is a binary-event
    # bet, not a re-rating — denoted as biotech_awakening_watch, not the core
    _awak_rule = ((mcap > 0) & (_nan_ >= 3) & _rating_present & _conviction &
                  _not_extended & _not_freefall & lr_live_tape).fillna(False)
    df['biotech_awakening_watch'] = (_awak_rule & _clin_bio_e).astype(int)
    df['arch_analyst_awakening'] = (_awak_rule & ~_clin_bio_e).astype(int)
    # Score: rating strength + upside depth + breadth, upweighted where the
    # tape agrees — 52w high (abs and/or rel) scaled by base freshness.
    _rec_sc = ((2.2 - _rec) / 1.2).clip(0, 1).fillna(0)         # 1.0 -> best
    _ups_sc = (_ups / 0.60).clip(0, 1).fillna(0)                # fraction scale
    _brd_sc = (_nan_ / 12.0).clip(0, 1).fillna(0)
    _fresh_sc = ((0.85 - _num('base_depth_12m')) / 0.45).clip(0, 1).fillna(0)
    _hi_sc = ((0.4 * _abs_hi.astype(float) + 0.4 * _rel_hi.astype(float))
              * (0.5 + 0.5 * _fresh_sc)).clip(0, 1)
    # Volatility-asymmetry awakening reward: asym oscillator NEAR 50 (|a-50|
    # <= 5) AND RISING (5-period ROC > 0) on the monthly or quarterly bars —
    # two-sided volatility resolving upward, i.e. the re-rating is being
    # traded, not just written about. A reward leg, not a gate (weekly bars
    # aren't computed; monthly is the shortest asym timeframe).
    _asym_wake = ((_num('asym_m_near50_rising') == 1)
                  | (_num('asym_q_near50_rising') == 1)).fillna(False)
    _asym_sc = _asym_wake.astype(float)
    df['analyst_awakening_score'] = (((0.25 * _rec_sc + 0.20 * _ups_sc
                                       + 0.15 * _brd_sc + 0.10 * conv_score
                                       + 0.30 * _hi_sc
                                       + 0.10 * _asym_sc).clip(0, 1))
                                     * df['arch_analyst_awakening']).round(3)
    # An AWAKENING is a CHANGE: perception moving (>= 1 sentiment-change lens)
    # or the price turning (Mansfield RS rising over 13w with a positive 13w
    # return). 2,046 of 2,102 firers qualified on rating LEVELS alone.
    # Exceptional: targets raised while the price has not moved (street
    # leading), or two independent change lenses at once.
    _tier('analyst_awakening',
          (_sent_turn_n >= 1) | ((_ncol('ts_mrs') > _ncol('ts_mrs_13ago')) & (_ncol('ts_r13') > 0)),
          (_ncol('evt_pt_lead_flag') == 1) | (_sent_turn_n >= 2),
          elite_metric=df['analyst_awakening_score'],
          measured=_ncol('ts_mrs').notna() | _ncol('sent_buy_share').notna())
    df['analyst_awakening_score'] = (df['analyst_awakening_score'] * df['arch_analyst_awakening']).round(3)

    # ---------- Analyst re-rating CONFIRMED by 52-week highs ----------
    # Companion to arch_analyst_awakening. Where the awakening screen catches
    # the re-rating EARLY (not-in-freefall, not-yet-extended), THIS one requires
    # the market has already CONFIRMED it with price: the same analyst-conviction
    # legs (real rating, breadth, target upside) AND the stock is ACTUALLY
    # printing a fresh 52-week high — absolute or relative to its country index.
    # So it is the "re-rating begun AND price agrees" cut, not the "target
    # upside inflated after a crash" trap. A generous blow-off guard keeps out
    # parabolic chases (up >150% on the year is O'Neil/Kullamagie territory, not
    # an early confirmed re-rating). No _not_freefall / _not_extended gates —
    # the 52w-high requirement makes both moot.
    _at_52w_high = (_abs_hi | _rel_hi)
    _not_blownoff = ((_num('roc_12m') <= 1.5) |
                     (_num('roc_12m').isna() & (_num('momentum_12m') <= 1.5)))
    # (audit 3) a RE-RATING is a change: at least one sentiment turn or a
    # dated target revision must be present (a static Buy at a high is not one)
    _rerate_change = ((_sent_turn_n >= 1) | (_num('evt_pt_rev_90d') > 0)).fillna(False)
    df['arch_analyst_rerating_confirmed'] = (
        (mcap > 0) & (_nan_ >= 3) & _rating_present & _conviction & _rerate_change &
        _at_52w_high & _not_blownoff & lr_live_tape & ~_clin_bio_e
    ).fillna(False).astype(int)
    # Score: same conviction stack, but the 52w-high confirmation carries the
    # largest weight (it is the defining, market-validated signal here).
    df['analyst_rerating_score'] = (((0.20 * _rec_sc + 0.15 * _ups_sc
                                      + 0.12 * _brd_sc + 0.08 * conv_score
                                      + 0.45 * _hi_sc)
                                     .clip(0, 1))
                                    * df['arch_analyst_rerating_confirmed']).round(3)
    # (weekly panel) "confirmed by price" = a true absolute 52w high, or an RS
    # high while above the 30w MA (a relative high in a falling tape is not a
    # confirmation — 345 of 390 firers passed only through that leg).
    # Exceptional: analysts' targets LEAD the price (raised while it was flat).
    _tier('analyst_rerating_confirmed',
          (_ncol('ts_dist_hi52') >= 0.97) | ((_ncol('ts_rs_at_hi') == 1) & (_ncol('ts_above_ma30') == 1)),
          (_ncol('ts_dist_hi260') >= 0.98) & (_ncol('ts_rs_at_hi') == 1),
          elite_metric=_ncol('ts_mrs'),
          measured=_ncol('ts_dist_hi52').notna())
    df['analyst_rerating_score'] = (df['analyst_rerating_score'] * df['arch_analyst_rerating_confirmed']).round(3)

    # ---------- Institutional accumulation into a flat / falling tape ----------
    # (user spec) Institutions are ADDING — 13F ownership share and net share
    # count both rising — while the price consolidates or declines. That
    # divergence is the thesis: informed capital building a position the tape
    # has not yet rewarded (accumulation before mark-up). The score ADDS points
    # when the accumulation is ACCELERATING: the ownership share rising faster
    # than the prior quarter, net purchases accelerating, or buyer breadth
    # widening. Data: fmp_institutional.py — the last three complete 13F
    # quarters for US-listed names (13F covers US listings incl. ADRs).
    _io_chg0 = _num('fmp_inst_own_chg_q0')       # ownership %-pt change, latest Q
    _io_chg1 = _num('fmp_inst_own_chg_q1')
    _ish0 = _num('fmp_inst_shares_chg_pct_q0')   # net 13F shares bought, % of prior
    _ish1 = _num('fmp_inst_shares_chg_pct_q1')
    _ibr0 = _num('fmp_inst_buy_ratio_q0')        # (new + increased) / all position changes
    _ibr1 = _num('fmp_inst_buy_ratio_q1')
    _iaccq = _num('fmp_inst_accum_quarters')     # quarters (of 3) with net buying
    # CROSS-SECTIONAL DEMEANING. Raw 13F changes carry a large quarter-wide
    # effect: in 2026Q2 the MEDIAN name showed +1.9pp ownership and +2.7% net
    # 13F shares (filer-population growth, reporting seasonality, coverage
    # changes), so "institutions adding" was true of almost everything and the
    # archetype degenerated to "any flat stock". Subtracting each quarter's
    # cross-sectional median isolates accumulation ABOVE what is typical that
    # quarter — the informed-buying signal — and makes quarter-to-quarter
    # acceleration comparable (each quarter against its own baseline).
    def _xs(x):
        _m = x.median(skipna=True)
        return x - _m if pd.notna(_m) else x
    _io_x0, _io_x1 = _xs(_io_chg0), _xs(_io_chg1)
    _ish_x0, _ish_x1 = _xs(_ish0), _xs(_ish1)
    # accumulating NOW: adding in absolute terms AND more than the typical name
    # this quarter, on both the ownership-share and net-share lenses
    _inst_adding = ((_io_chg0 > 0) & (_ish0 > 0) & (_io_x0 > 0) & (_ish_x0 > 0))
    # not a one-quarter blip: net buying in >= 2 of the last 3 quarters
    _inst_persistent = (_iaccq >= 2)
    # corporate-action tail (merger/spin share issuance, stale share-count
    # denominator): a >15pp ownership swing or >50% net 13F shares in a single
    # quarter is ~1.5% of names and not accumulation — excluded as invalid data
    _inst_sane = (_io_chg0.abs() <= 15) & (_ish0 <= 0.50)
    # price consolidating (roughly flat over 6m and 12m) or declining
    _ip12 = _ncol('ts_r52').fillna(_num('roc_12m')).fillna(_num('momentum_12m')).fillna(_num('price_yoy'))   # (audit 3) weekly total-return panel first
    _ip6 = _ncol('ts_r26').fillna(_num('roc_6m'))
    _inst_flat_or_down = (((_ip12 <= 0.10) & (_ip6.isna() | (_ip6 <= 0.10)))
                          # weekly panel: a two-year base still flat over 26w
                          | ((_num('bs_is_base') == 1) & (_num('bs_r26') <= 0.10)).fillna(False))
    # validity only (no quality veto): enough holders for 13F deltas to mean
    # something, an investable listing, not a collapse / ghost / fund shell
    _inst_fund = _ind_all.str.contains(
        r'closed-end|business development|investment trust|\bfund\b|shell compan',
        regex=True)
    _inst_valid = ((_num('fmp_inst_holders') >= 15) & (mcap >= 50e6)
                   & (_ip12 >= -0.70)
                   & ~(s('is_price_ghost', 0) == 1) & ~_inst_fund)
    df['arch_institutional_accumulation'] = (
        _inst_adding & _inst_persistent & _inst_sane & _inst_flat_or_down & _inst_valid
    ).fillna(False).astype(int)
    # Points: magnitude of the accumulation, plus ADDED points for acceleration
    # (share rising faster than last quarter; purchases accelerating; broader
    # buyer base), full persistence, and a genuinely falling price (the purest
    # divergence). Ranking only — the archetype pool is unchanged.
    _pt_mag = (_io_x0 / 5.0).clip(0, 1).fillna(0)             # +5pp above typical = full
    _pt_net = (_ish_x0 / 0.10).clip(0, 1).fillna(0)           # +10% net shares above typical = full
    # Acceleration is scored against a SELECTION effect: picking names with a
    # strong latest quarter makes "this quarter > last" nearly automatic. So
    # full points only when last quarter was ALSO above-typical and this one is
    # higher (an established accumulation speeding up); half points for a
    # fresh start (below-typical last quarter, above now).
    _pt_own_acc = np.where((_io_x1 > 0) & (_io_x0 > _io_x1), 1.0,
                           np.where((_io_x1 <= 0) & (_io_x0 > 0), 0.5, 0.0))
    _pt_buy_acc = np.where((_ish_x1 > 0) & (_ish_x0 > _ish_x1), 1.0,
                           np.where((_ish_x1 <= 0) & (_ish_x0 > 0), 0.5, 0.0))
    _pt_own_acc = pd.Series(_pt_own_acc, index=df.index)
    _pt_buy_acc = pd.Series(_pt_buy_acc, index=df.index)
    _pt_breadth = ((_ibr0 > 0.5) & (_ibr0 > _ibr1)).astype(float)
    _pt_persist = (_iaccq >= 3).astype(float)
    _pt_down = (_ip12 < 0).astype(float)
    df['inst_accum_score'] = (((0.20 * _pt_mag + 0.15 * _pt_net
                                + 0.20 * _pt_own_acc + 0.20 * _pt_buy_acc
                                + 0.10 * _pt_breadth + 0.10 * _pt_persist
                                + 0.05 * _pt_down).clip(0, 1))
                              * df['arch_institutional_accumulation']).round(3)
    # ACCELERATING = an ESTABLISHED above-typical accumulation (last quarter
    # too) where both the ownership share AND the buying rose faster this
    # quarter — each measured against its own quarter's baseline
    df['inst_accum_accelerating'] = (
        (df['arch_institutional_accumulation'] == 1)
        & (_pt_own_acc >= 1.0) & (_pt_buy_acc >= 1.0)).astype(int)
    df['inst_own_excess_q0'] = _io_x0.round(3)
    df['inst_buy_excess_q0'] = _ish_x0.round(4)

    # ================= SENTIMENT (sell-side perception) flags ================
    # Surfaced, never gates. Levels say how the street sees the name; the
    # 12-month CHANGES say where perception is going — the part that moves a
    # multiple. (FMP's upgrade/downgrade feed is US-centric, so "no upgrade"
    # alone is never evidence of anything for a non-US name.)
    _sn = _num('sent_n_analysts').fillna(_num('n_analysts'))
    _sb = _num('sent_buy_share'); _sbd = _num('sent_buy_share_d12')
    _sup, _sdn = _num('sent_upgrades_12m'), _num('sent_downgrades_12m')
    _sini = _num('sent_initiations_12m'); _spt = _num('sent_pt_rev_q')
    _snd = _num('sent_n_analysts_d12')
    df['sent_warming_flag'] = (                       # perception improving
        ((_sbd >= 0.10) | ((_sup - _sdn) >= 2) | (_spt >= 0.10)) & ~(_sbd <= -0.10)
    ).fillna(False).astype(int)
    df['sent_cooling_flag'] = (
        ((_sbd <= -0.10) | ((_sdn - _sup) >= 2) | (_spt <= -0.10)) & ~(_sbd >= 0.10)
    ).fillna(False).astype(int)
    df['sent_discovery_flag'] = ((_sini >= 1) | (_snd >= 2)).fillna(False).astype(int)
    df['sent_neglected_flag'] = (~(_sn > 3)).astype(int)            # <= 3 analysts or none on file
    df['sent_skeptic_flag'] = ((_sb <= 0.50) & (_sn >= 3)).fillna(False).astype(int)

    # ============ COILED BASE / BASE IGNITION (theory-first; the base-breakout
    # event study recalibrates the weights) ============
    # The pattern: a future multi-bagger goes NOWHERE for ~2 years, then re-rates
    # violently. Mechanism: value accretes under a flat price (the COIL), the
    # market is not watching or does not believe (PERCEPTION LAG), and when the
    # first buyers arrive (IGNITION) a small, thinly-owned, under-covered stock
    # moves fast because earnings growth and multiple expansion land together.
    # Four blocks, each read through several INDEPENDENT lenses; a block is met
    # by ANY of its lenses (breadth doctrine: missing data never vetoes).
    #
    # A — TIME: a genuine two-year base from the weekly panel (104w return within
    #     +/-25%, 104w high/low <= 2x), not pinned to its low (upper 3/4 of the
    #     range) — a flat base, not a slow collapse.
    _bs = (_num('bs_is_base') == 1)
    _bs_not_low = (_num('bs_pos_in_range') >= 0.25)
    _blk_time = (_bs & _bs_not_low).fillna(False)
    # B — COIL: value accreted while the price did not.
    _coil_legs = [
        (_num('bs_coil_rev') >= np.log(1.30)).fillna(False),          # sales outgrew price by 30%+
        (_num('bs_coil_ebit') >= np.log(1.50)).fillna(False),         # EBIT outgrew price by 50%+
        (_num('bs_ebit_turned') == 1).fillna(False),                  # loss -> profit inside the base
        ((df.get('fq_gm_inflection_flag', 0) == 1)
         & (_num('bs_rev_g_2y') > 0)).fillna(False),                  # gross-margin-led, growing sales
        (_num('fmp_dyn_unrerated_gap') >= 0.15).fillna(False),        # multi-year fundamentals vs EV/Sales
    ]
    _coil_n = sum(l.astype(int) for l in _coil_legs)
    # the coil must be a REAL, surviving business: positive cash or EBIT now
    # (or the turn itself), not melting — validity, not a quality screen
    _coil_real = ((_num('fcf_ttm') > 0) | (_num('ebitda_ttm') > 0) | (_num('bs_ebit_turned') == 1)
                  ).fillna(False) & _not_melting
    _blk_coil = (_coil_n >= 1) & _coil_real
    # C — PERCEPTION LAG: nobody is watching, or nobody believes it.
    _beat_ok = (_num('fmp_earnings_beat_rate') >= 0.60) | (_num('earnings_beat_rate') >= 0.60)
    _perc_legs = [
        (df['sent_neglected_flag'] == 1),                             # <= 3 analysts
        ((df['sent_skeptic_flag'] == 1) & _beat_ok).fillna(False),    # doubted despite beats
        ((_num('sent_months_since_up') >= 12) & (_sn >= 3)
         & (_num('sent_upgrades_12m') == 0) & ~(_snd > 0)).fillna(False),  # no upgrade, coverage not growing
        (_num('yf_institution_pct') <= 0.30).fillna(False),          # thinly owned by institutions
        ((_num('analyst_target_upside_pct').where(
            _num('analyst_target_upside_pct').abs() <= 5) <= 0.10)
         & (_coil_n >= 1)).fillna(False),                             # targets anchored despite the coil
    ]
    _perc_n = sum(l.astype(int) for l in _perc_legs)
    # (audit 3) where estimate coverage is OBSERVED, a widely-covered name
    # (> 3 analysts) is not "unnoticed" whatever the other lenses say
    _blk_perc = (_perc_n >= 1) & ~(_ncol('sent_n_analysts') > 3)
    # D — IGNITION: someone is starting to notice (price/volume evidence first —
    # the event-study dry run found volume expansion and accumulation carry the
    # lift, volatility compression does not).
    _ign_legs = [
        # thresholds ~ the top 15% of current two-year bases (the dry run's lift
        # sat in the top quintile; the 65th-75th percentile fired on half of all
        # coiled bases, which is not an ignition)
        (_num('bs_dvol_trend') >= 1.60).fillna(False),                # dollar volume expanding
        (_num('bs_updown_vol') >= 1.80).fillna(False),                # up-weeks carry the volume
        ((_num('bs_rs26') >= 0.10) & (_num('bs_r26') >= 0.10)).fillna(False),  # right side strengthening vs peers
        ((df['arch_institutional_accumulation'] == 1)
         | (s('insider_buy_flag', 0) == 1)).fillna(False),            # informed buyers
        ((df['sent_warming_flag'] == 1) | (df['sent_discovery_flag'] == 1)),  # perception turning
    ]
    # (event study, out of sample) change-point ignition: a statistically
    # abnormal dollar-volume regime vs the name's own base (13w z-score or
    # upward CUSUM, test lift ~1.6-1.7x in the top quintile) and a slope break
    # (26w trend vs the prior 78w, ~1.4x). Thresholds = the top quintile of
    # CURRENT two-year bases, the study's own quintile convention.
    _in_base = _bs.fillna(False)

    def _q80(col):
        x = _num(col)
        return x >= x.where(_in_base).quantile(0.80)
    _cp_volume = (_q80('bs_cp_dvol_z13') | _q80('bs_cp_dvol_cusum')).fillna(False)
    _ign_legs += [_cp_volume, _q80('bs_cp_slope_brk').fillna(False)]
    # (audit 3) the three volume readings (dvol trend, up/down volume, the
    # change-point z/CUSUM) are one family — counted once so the >= 2-lens
    # rule means two INDEPENDENT kinds of evidence
    _ign_vol_fam = (_ign_legs[0] | _ign_legs[1] | _cp_volume).astype(int)
    _ign_n = _ign_vol_fam + sum(l.astype(int) for l in _ign_legs[2:-2]) + _ign_legs[-1].astype(int)
    # validity (not quality): tradeable, an operating business with real sales,
    # common stock, clean data
    _cb_valid = (is_operating & (_num('bs_med_dvol26') >= 250_000)
                 & (_num('revenue_ttm_usd') >= 10e6)
                 & ~(_ncol('data_quality_flag') == 1)).fillna(False)
    df['arch_coiled_base'] = (_cb_valid & _blk_time & _blk_coil & _blk_perc).astype(int)
    # ignition needs PRICE/VOLUME evidence (the lenses that carried the measured
    # lift): >= 2 lenses, at least one of them volume expansion / accumulation
    _ign_volume = _ign_legs[0] | _ign_legs[1] | _cp_volume
    df['arch_base_ignition'] = ((df['arch_coiled_base'] == 1) & (_ign_n >= 2) & _ign_volume).astype(int)
    # (event study) the FALLEN-ANGEL variants — a base formed >= 40% below the
    # prior 5-year high — carried the largest out-of-sample lift of any
    # construction (coiled 3.7x, ignition 5.6x the base-month rate, 2019+).
    # Surfaced as their own archetypes; the coiled / ignition cores are
    # unchanged.
    _fallen_ctx = ((_num('bs_prior_dd') <= 0.60).fillna(False)
                   & ~(_ncol('shares_growth_3y') > 0.20)        # (audit 3) the fall is per share, not a dilution-driven price collapse
                   # (user) no leverage cap: survival is read by the never-a-deep-loss-year leg below
                   & ~(_ncol('tc_min_opm') < -0.10)             # (audit 3) never a deep-loss year on file
                   & ~(_num('bs_coil_rev') < -0.10))            # (audit 3) business intact: sales not collapsing over the base
    df['arch_coiled_fallen_angel'] = ((df['arch_coiled_base'] == 1) & _fallen_ctx).astype(int)
    df['arch_ignition_fallen_angel'] = ((df['arch_base_ignition'] == 1) & _fallen_ctx).astype(int)
    _SPIRITED += ['coiled_fallen_angel', 'ignition_fallen_angel']

    # ============ PEER FRAMES: SECTOR AND INDUSTRY ============
    # The name against its peers today: multiples, margins, returns and growth
    # ranked within its INDUSTRY (the finer frame; an industry with fewer than
    # 12 operating names falls back to the sector), plus the industry's own
    # tape (median 1y return and distance from the 5-year high, breadth) and
    # the name's position against it. The operator study found the 10x
    # operators at the SECTOR'S lowest multiple and lowest returns — the
    # peer frame, not the absolute level, is what the market re-rates against.
    _frame_pop = is_operating & (mcap > 0)
    _ind_f = df['industry'].fillna('').astype(str).where(_frame_pop, '')
    _sec_f = sector.astype(str).where(_frame_pop, '')
    _ind_n = _ind_f.map(_ind_f.value_counts())
    _peer_key = _ind_f.where((_ind_n >= 12) & (_ind_f != ''), _sec_f)
    df['peer_frame'] = np.where(_peer_key == _ind_f, 'industry', 'sector')
    df.loc[~_frame_pop | (_peer_key == ''), 'peer_frame'] = ''

    def _peer_rank(x):
        x = pd.to_numeric(x, errors='coerce').where(_frame_pop & (_peer_key != ''))
        return x.groupby(_peer_key).rank(pct=True).round(4)

    _rel_src = {'ev_ebit': s('ev_ebit', np.nan).where(s('ev_ebit', np.nan) > 0),
                'p_s': _ncol('p_s').where(_ncol('p_s') > 0), 'pb': _ncol('pb').where(_ncol('pb') > 0),
                'fcf_yield': _ncol('fcf_yield'), 'op_margin': _ncol('op_margin'), 'gross_margin': _ncol('gross_margin'),
                'roce': _ncol('roce'), 'rev_growth': _ncol('fq_rev_growth').fillna(_ncol('yf_revenue_growth')),
                'rev_accel': rev_accel, 'r52': _ncol('ts_r52'), 'r26': _ncol('ts_r26'),
                'dist_hi260': _ncol('ts_dist_hi260'), 'mcap': mcap}
    for _k, _v in _rel_src.items():
        df['rel_ind_' + _k] = _peer_rank(_v)
    for _k in ('r52', 'r26', 'dist_hi260', 'rev_growth'):
        _v = _rel_src[_k].where(_frame_pop & (_peer_key != ''))
        _med = _v.groupby(_peer_key).transform('median')
        df['ind_tape_' + _k] = _med.round(4)
        df['vs_ind_' + _k] = (_v - _med).round(4)
    df['ind_breadth_up52'] = ((_rel_src['r52'] > 0).astype(float).where(_frame_pop & (_peer_key != ''))
                              .groupby(_peer_key).transform('mean').round(4))

    # ============ MULTIBAGGER PRE-CONDITIONS (multibagger_clusters.py) ============
    # The latent-cluster study of 3x-within-24-months episodes (entries fit
    # <= 2017, judged 2018+): the states below are the study's OWN state
    # definitions applied to today's snapshot, so the measured out-of-sample
    # lifts carry over. Every one is high-variance (the study's P(-50% within
    # 24m) is 15-35%): better-loaded lottery tickets, not safe bets.
    _mb_liquid = (_ncol('ts_dvol26_usd') >= 250_000).fillna(False)
    _mb_base = is_operating & (mcap >= 10e6) & _mb_liquid
    _hi260 = _ncol('ts_dist_hi260')
    _mb_fallen = (_hi260 <= 0.40).fillna(False)                     # >= 60% below the 5y high
    _eveb = s('ev_ebit', np.nan); _pbv = _ncol('pb'); _psv = _ncol('p_s')
    _mb_deep = (((_eveb > 0) & (_eveb <= 6)) | ((_pbv > 0) & (_pbv <= 0.7))
                | ((_psv > 0) & (_psv <= 0.3))).fillna(False)
    _mb_turn = ((_ncol('fqx_eps_turned') == 1) | (_ncol('bs_ebit_turned') == 1)
                | (ebitda_first_pos > 0) | (ni_first_pos > 0) | (fcf_first_pos > 0)
                | (_ncol('fmp_dyn_opinc_turned_positive') == 1)
                | (_ncol('fmp_dyn_ni_turned_positive') == 1)).fillna(False)
    _mb_turn = _mb_turn & ((_ncol('fqx_m_since_turn_positive') <= 12) | _ncol('fqx_m_since_turn_positive').isna())
    # acceleration date-matched where the quarterly shape exists (audit 3: rev_accel's annual fallback is a different horizon)
    _accel_now = ((_ncol('fqx_rev_accel_now') == 1) | (_ncol('fqx_rev_accel_now').isna() & (rev_accel > 0))).fillna(False)
    _mb_accel = ((((_ncol('fqx_rev_accel_now') == 1)                                   # date-matched where the quarterly shape exists,
                   | (_ncol('fqx_rev_accel_now').isna() & (rev_accel >= 0.10)))         # the annual >= 10pp only where it does not
                  & (_ncol('fq_rev_growth') >= 0)).fillna(False))                       # accelerating AND not shrinking
    _mb_stressed = (((nde >= 5) & (nde < 90)) | (_ncol('equity') < 0) | (_ncol('fq_equity') < 0)
                    | (_ncol('net_cash_pct_mcap') <= -1.0)        # EBITDA <= 0 names: net debt >= the market cap
                    | (_ncol('debt_to_equity') >= 2.0)).fillna(False)
    _opm_ttm_fq = _ncol('fqx_opm_ttm')                                  # FMP quarterly TTM operating margin
    _mb_opm_gap = (_opm_ttm_fq.where(_opm_ttm_fq.notna(), _ncol('op_margin'))   # FMP TTM first: one source vs tc_med_opm
                   - _ncol('tc_med_opm'))                                        # margin vs its own through-cycle median
    _mb_trough = ((_mb_opm_gap <= -0.05) & _accel_now).fillna(False)
    _mb_insider = ((s('insider_buy_flag', 0) == 1) | (_ncol('insider_distinct_buyers') >= 2)
                   | (_ncol('fmp_insider_net_usd_12m') > 0)).fillna(False)
    # conjunctions (robust in BOTH periods; lift fit / test)
    df['arch_mb_fallen_deep_value'] = (_mb_base & _mb_fallen & _mb_deep).astype(int)          # 2.5x / 3.4x
    df['arch_mb_fallen_value_turn'] = (_mb_base & _mb_fallen & _mb_deep & _mb_turn).astype(int)   # 2.7x / 3.6x
    df['arch_mb_fallen_value_accel'] = (_mb_base & _mb_fallen & _mb_deep & _mb_accel).astype(int)  # 3.0x / 3.3x
    df['arch_mb_fallen_stressed'] = (_mb_base & _mb_fallen & _mb_stressed).astype(int)        # 3.1x / 2.7x
    # FALLEN + INSIDER CONVICTION (the study's FAST archetype: fallen angel +
    # insiders buying in 2+ of the last 4 quarters + an OPERATING business, not
    # an asset play + margins not yet consistent; lift 15-21x on a 3x within
    # 12 months, median 7.8 months to the triple, blow-up 31%). SEC quarterly
    # statistics where they exist, the EDGAR cluster-buy / distinct-buyer
    # flags otherwise.
    _ins_2q = ((_ncol('usf_ins_buy_quarters_4q') >= 2)
               | (_ncol('usf_ins_buy_quarters_4q').isna()
                  & ((_ncol('insider_distinct_buyers') >= 2) | (_ncol('insider_cluster_buy_flag') > 0)))).fillna(False)
    # revealed CORPORATE conviction (global): a buyback executed or the share count shrinking now; and 13F new
    # positions (US-listed) — the non-SEC arrival legs the informed-buyer archetypes lacked (audit 3, #1)
    _corp_conviction = ((_ncol('fmp_st_buyback_yield_y0') > 0.01) | (_ncol('fqx_share_shrink_now') == 1)).fillna(False)
    _inst_arrival = (_ncol('fmp_inst_new_q0') >= 1).fillna(False)
    _operating_not_asset = ~(_ncol('ncav_pct_mcap') >= 0.5)
    _margins_not_consistent = ~(_ncol('fqx_opm_consist') > 0.5)
    df['arch_mb_fallen_insider'] = (_mb_base & _mb_fallen & _ins_2q & _operating_not_asset
                                    & _margins_not_consistent).astype(int)
    df['arch_mb_fallen_trough'] = (_mb_base & _mb_fallen & _mb_trough).astype(int)            # 2.8x / 2.2x
    # the two real latent clusters (continuous directions, not boxes)
    #  FALLEN BELOW ITS CYCLE (47% of 2018+ multibaggers, 1.5x): far below the
    #  5y high, margins under their own through-cycle norm, the multiple below
    #  its own history
    # the MULTIPLE below its own history (EV/sales 3y or 1y change); the price
    # vs its 5-year average was 93% implied by the drawdown leg itself (audit 3)
    _cheap_own = ((_ncol('fmp_dyn_ev_sales_change_3y') < 0) | (_ncol('ev_sales_change_yoy') < 0)).fillna(False)
    df['arch_mb_fallen_below_cycle'] = (
        _mb_base & (_hi260 <= 0.50).fillna(False) & (_mb_opm_gap <= -0.02).fillna(False) & _cheap_own
    ).astype(int)
    #  INFLECTING OPERATOR (38%, 1.1x): margins and EBIT rising, returns
    #  improving, smaller cap, a fair (not bubble) price
    _mb_margin_up = ((_ncol('op_margin_delta_yoy') >= 0.01) | (df['fqx_inc_ebit_margin_dt'] >= 0.20)).fillna(False)
    _mb_ebit_up = ((_ncol('fqx_ebit_ttm_g') >= 0.10)
                   | (_ncol('fqx_ebit_ttm_g').isna() & (_ncol('ebit_growth_yoy') >= 0.10))).fillna(False)
    _mb_roic_up = ((_ncol('fqx_roic_ttm') > _ncol('roic_lindy')) | (_ncol('roce_delta_yoy') > 0)).fillna(False)
    df['arch_mb_inflecting_operator'] = (
        _mb_base & (mcap < 2e9) & _mb_margin_up & _mb_ebit_up & _mb_roic_up
        & ((_eveb > 0) & (_eveb <= 25)).fillna(False)
    ).astype(int)
    #  QUIET TURN UNDER A WEAK TAPE (the forensic "dogs that did not bark":
    #  against same-state lookalikes, the winners had WEAKER recent price
    #  action while revenue accelerated and EBIT grew, and were cheaper than
    #  their own history; the fundamental turn leads the run by ~12 months)
    _mb_weak_tape = ((_ncol('ts_r13') < 0) & (_ncol('ts_dist_hi52') < 0.85)).fillna(False)
    _mb_fund_turning = (((rev_accel > 0) | (_ncol('fq_rev_growth') >= 0.10))
                        & ((_ncol('fqx_ebit_ttm_g') > 0) | _mb_turn)).fillna(False)
    # MARGIN INFLECTION UNDER A WEAK TAPE (upgrade of the quiet turn with the
    # study's trend shapes: operating margin rising steadily over 8 quarters,
    # or a dated inflection; ROIC trend up; the tape still weak)
    _margin_trend_up = (((_ncol('fqx_opm_slope8') > 0) & (_ncol('fqx_opm_consist') >= 0.6))
                        | (_ncol('fqx_margin_inflect_now') == 1)).fillna(False)
    _roic_trend_up = ((_ncol('fqx_roic_slope8') > 0) | (_ncol('roce_delta_yoy') > 0) | _mb_roic_up).fillna(False)
    df['arch_mb_quiet_turn'] = (_mb_base & _mb_fund_turning & _margin_trend_up & _roic_trend_up
                                & _mb_weak_tape & _cheap_own).astype(int)

    # ---- the nine archetypes from the full-sample mining (MULTIBAGGER_ARCHETYPES.md) ----
    # 1. LEFT-FOR-DEAD VALUE (the 10x archetype): fallen + deep value + FCF
    #    margin NOT yet in an improving streak — the condition present in all
    #    40 top 10x patterns; the market prices terminal decline before the
    #    cash flow turns. Lift 17-23x on a 10x within 5 years (~20% of these),
    #    3x in ~12 months, blow-up 15%.
    _fcf_not_turned = ((_ncol('fqx_fcfm_streak') <= 1)
                       | (_ncol('fqx_fcfm_streak').isna() & _ncol('fcf_margin_delta_yoy').notna()
                          & ~(_ncol('fcf_margin_delta_yoy') > 0))).fillna(False)
    df['arch_mb_left_for_dead_value'] = (_mb_base & _mb_fallen & _mb_deep & _fcf_not_turned).astype(int)
    # 3. FALLEN + IGNORED BELIEVERS: few analysts, but those few are buyers,
    #    and no dividend yield propping the name up. Lift 7-9x on a 3x within
    #    24 months, blow-up 25-40%.
    _few = _ncol('sent_n_analysts').between(1, 5)
    df['arch_mb_fallen_ignored_believers'] = (
        _mb_base & _mb_fallen & _few & (_ncol('sent_n_analysts') >= 2) & (_ncol('sent_buy_share') >= 0.6)
        & ~(_ncol('dividend_yield') > 0.02)).fillna(False).astype(int)
    # 4. SMART MONEY IN THE WRECKAGE (the mixture model's highest-lift group):
    #    fallen + deep value + informed buyers arriving — insider buying, a new
    #    >= 5% holder (SC 13D <= 12 months), or a headcount jump. Lift 2.1x as
    #    a region, blow-up 27%. The legs are SEC data (US filers); the spirit
    #    counts how many arrived.
    _smart_legs = (_ins_2q.astype(int) + _13d_recent.astype(int)
                   + (_ncol('usf_emp_g1') >= 0.10).fillna(False).astype(int)
                   + _inst_arrival.astype(int))   # (audit 4) a buyback / share shrink is not an informed buyer ARRIVING: it is a weight, not a leg
    df['mb_smart_money_legs'] = _smart_legs
    df['arch_mb_smart_money_wreckage'] = (_mb_base & _mb_fallen & _mb_deep & (_smart_legs >= 1)).astype(int)
    # 7. GREW INTO THE VALUATION, NOW TURNING: the de-rating-through-growth
    #    family where the margin / profit turn has arrived (Archetype B's
    #    medians: revenue +13%, margin at the 64th pct of its own history).
    df['arch_mb_grew_into_valuation_turning'] = (
        (df['arch_derate_through_growth'] == 1) & (_margin_trend_up | _mb_turn)
        & (_ncol('fq_rev_growth') >= 0.08).fillna(False)).astype(int)
    # 8. THE TREE RECIPE: within-country ranks — volatility top 40%, size
    #    bottom 13%, fallen top 17%, profitability bottom 46%: 16.7% of such
    #    months led to a 3x within 24 months (lift 3.9x), blow-up 30%. The 10x
    #    variant swaps the fallen leg for cheapness above the median (5.7x).
    _base_n = country.where(_mb_base).map(country.where(_mb_base).value_counts())

    def _crank(x):
        # ranks within the country AMONG THE LIQUID OPERATING BASE (the study's
        # population), not the whole universe — else the bottom-13%-by-size
        # slice is illiquid names that the base then removes. A market with
        # fewer than 50 base names (18 of 47) cannot hold a quintile; those
        # names rank against the whole base instead (audit 3, S3).
        xv = pd.to_numeric(x, errors='coerce').where(_mb_base)
        local = xv.groupby(country).rank(pct=True)
        return local.where(_base_n >= 50, xv.rank(pct=True))
    _r_vol = _crank(_ncol('ts_vol_1y')); _r_size = _crank(mcap)
    _r_fallen = _crank(1 - _ncol('ts_dist_hi260')); _r_prof = _crank(_ncol('op_margin'))
    _r_cheap = pd.concat([_crank(-_ncol('p_s').where(_ncol('p_s') > 0)), _crank(-_ncol('ev_sales').where(_ncol('ev_sales') > 0)),
                          _crank(-_ncol('pb').where(_ncol('pb') > 0)), _crank(_ncol('fcf_yield'))], axis=1).mean(axis=1)
    df['arch_mb_tree_recipe'] = (_mb_base & (_r_vol >= 0.60) & (_r_size <= 0.13) & (_r_fallen >= 0.83)
                                 & (_r_prof <= 0.46)).fillna(False).astype(int)
    df['arch_mb_tree_recipe_10x'] = (_mb_base & (_r_vol >= 0.62) & (_r_size <= 0.12) & (_r_cheap >= 0.46)
                                     & (_r_prof <= 0.45)).fillna(False).astype(int)
    # 9. THE SEQUENCE, PRE-IGNITION: the forensic timeline — revenue
    #    acceleration and margin inflection arrive ~14 months before the run,
    #    profit turning positive ~12, share count shrinking ~11; the volume
    #    change point and new highs only ~6 months before. Two or more of the
    #    fundamental signs first appeared 3-18 months ago and the tape has NOT
    #    yet ignited: the window before the move.
    _signs = sum((_ncol(f'fqx_m_since_{k}').between(3, 18)).fillna(False).astype(int)
                 for k in ('rev_accel', 'margin_inflect', 'turn_positive', 'share_shrink'))
    df['mb_sequence_signs'] = _signs
    _not_ignited = ((_ncol('ts_dist_hi52') < 0.90) & ~(_ncol('bs_cp_dvol_z13') >= 1.5)
                    & ~(_ncol('ts_r13') > 0.15)).fillna(False)
    df['arch_mb_sequence_preignition'] = (_mb_base & (_signs >= 2) & _not_ignited).astype(int)
    # INTERSECTIONS that beat their parts (second investigation, §5): insider
    # conviction inside the smart-money wreckage (lift 5.8x vs 3.9x / 4.7x,
    # blow-up 31%), and left-for-dead value with insider conviction (5.5x)
    # literal confluence: insiders PLUS a second, independent arrival (audit 3: with one leg the
    # intersection reduced algebraically to fallen_insider & deep value)
    df['arch_mb_conviction_confluence'] = ((df['arch_mb_fallen_insider'] == 1)
                                           & (df['arch_mb_smart_money_wreckage'] == 1)
                                           & (_smart_legs >= 2)).astype(int)
    df['arch_mb_left_for_dead_insider'] = ((df['arch_mb_left_for_dead_value'] == 1)
                                           & (df['arch_mb_fallen_insider'] == 1)).astype(int)
    _SPIRITED += ['mb_conviction_confluence', 'mb_left_for_dead_insider']
    # ---- the operator study (MULTIBAGGER_OPERATORS.md): profitable operators ----
    # MARKET TAPE: the country's own state (median distance from the 5-year
    # high and 1-year return across its operating names, breadth) — the
    # frame the wave archetype needs
    _mkt_v = _ncol('ts_dist_hi260').where(_frame_pop)
    df['mkt_tape_dist_hi260'] = _mkt_v.groupby(country).transform('median').round(4)
    df['mkt_tape_r52'] = _ncol('ts_r52').where(_frame_pop).groupby(country).transform('median').round(4)
    df['mkt_breadth_up52'] = ((_ncol('ts_r52') > 0).astype(float).where(_frame_pop)
                              .groupby(country).transform('mean').round(4))
    df['vs_mkt_dist_hi260'] = (_ncol('ts_dist_hi260') - df['mkt_tape_dist_hi260']).round(4)
    # 1. NEGLECTED VALUE ACCELERATING IN A DEPRESSED MARKET (the generalised
    #    form of the 10x pattern `debt not rising & deep value & neglected &
    #    accelerating` — ISCTR 84x, TURSG 47x, ASUZU 40x, SASA 35x, SUZLON
    #    33x, CS.TO 19x: lift 21x on a 10x within 5 years, ~19% went 10x,
    #    blow-up 6-13%). What made it a wave was the MARKET: those names sat
    #    in a country (or industry) that had itself spent years far below
    #    its highs. The condition is the peer group's tape, not the country.
    #    Refined on the operator study's own members (26,867 month-ends,
    #    1.31x as first boxed): the flat, low-volatility members had 0.4x
    #    the rate; the members OFF THE LOW (up_lo52 HIGH, V-shape, vol HIGH)
    #    1.6x; markets IS 8.8x / NS 3.6x / SA 2.3x, US 0.5x. So the core
    #    asks for the recovery to have begun (>= 10% off the 52-week low,
    #    not the lowest-volatility fifth) and a deeper depression of the
    #    frame; the sell side not yet turned is the strongest lens (3.6x).
    _debt_not_rising = ((_ncol('fq_netdebt_decline_months') >= 3) | (_ncol('fq_deleveraging_flag') == 1)
                        | (_ncol('net_cash_pct_mcap') >= 0) | ((nde >= 0) & (nde <= 1.0))).fillna(False)
    _neglected = (_ncol('sent_n_analysts').fillna(0) <= 2)
    _depressed_frame = (df['ind_tape_dist_hi260'] <= 0.65).fillna(False)   # the PEER group's tape, not the country's
    _deep_or_peer_cheap = _mb_deep | (df['rel_ind_ev_ebit'] <= 0.20).fillna(False)
    _off_the_low = ((_ncol('ts_dist_lo52') >= 1.10) & (_crank(_ncol('ts_vol_1y')) >= 0.20)).fillna(False)
    df['arch_mb_wave_neglected_value_accel'] = (
        _mb_base & _deep_or_peer_cheap & _neglected & (rev_accel > 0).fillna(False) & _debt_not_rising
        & _depressed_frame & _off_the_low).astype(int)
    df['mb_fund_up_unturned'] = (((_ncol('fq_rev_growth') > 0) & (_ncol('op_margin_delta_yoy') > 0)).astype(float)
                                 - (_ncol('sent_buy_share_d12') > 0).astype(float)).where(_ncol('sent_n_analysts') >= 1)
    # 2. RECOGNISED LEADER IN A WAVE (the family the fallen-dominated pooled
    #    study buried: lift 11-12x on a 3x within 24 months, blow-up 12-18%;
    #    NVDA 2019 / 2023, Fujikura, Hanwha Aerospace, Advantest, TSLA 2020):
    #    heavily covered, volatile, the PRICE AHEAD of sales per share
    #    (narrative lag negative), margins and returns rising, R&D-heavy, in
    #    an industry whose own tape is up. The opposite of every fallen
    #    archetype: it is the wave's leader, bought while still expensive.
    #    Refined (783 members, 4.1x, blow-up 24%): the 2021 cohort had ZERO
    #    winners and a 41% blow-up, the 2023 cohort 15% winners — what
    #    separated them: the leader sits nearest its high WITHIN ITS
    #    INDUSTRY (2.0x), growth is new (two-year growth already high = 0.55x),
    #    it is investing (current ratio falling, debt-to-capital rising),
    #    R&D at its own high. Core adds the industry-relative position and
    #    acceleration; the frame's euphoria is a negative lens.
    _price_ahead = ((_ncol('nl_sales_3y') < 0) | (_ncol('nl_sales_1y') < 0)).fillna(False)
    _ind_wave = ((df['ind_breadth_up52'] >= 0.5) | (df['ind_tape_r52'] > 0)).fillna(False)
    _vol_hi = (_crank(_ncol('ts_vol_1y')) >= 0.60).fillna(False)
    df['arch_mb_leader_in_wave'] = (
        _mb_base & (_ncol('sent_n_analysts') >= 8).fillna(False) & _price_ahead & _vol_hi
        & (_margin_trend_up | (_ncol('op_margin_delta_yoy') > 0.01).fillna(False))
        & (_ncol('fq_rev_growth') >= 0.15).fillna(False) & (rev_accel > 0).fillna(False) & _ind_wave
        & (df['rel_ind_dist_hi260'] >= 0.70).fillna(False)
        & _mb_roic_up                                                                   # returns rising
        & ((_ncol('fmp_rd_to_revenue') >= 0.08) | (_ncol('fmp_rd_intensive_flag') == 1)).fillna(False)).astype(int)   # R&D-heavy
    # 3. IMPROVING, SELL SIDE NOT YET TURNED (lift 11-12x, blow-up 3-10%;
    #    Celestica 2023, 5801.T, Sterling, Powell, Limbach, TRIL.NS): a
    #    LOW-gross-margin operator whose revenue and margin are rising, the
    #    tape already re-rating (P/B above its own history, wide range), but
    #    the analysts' buy share has NOT risen — the perception gap the
    #    study measures as gap_perc_buyshare.
    #    Refined (41,341 members as first boxed, 1.37x): the lift lives
    #    where the sell side EXISTS and has not turned (gap_perc_buyshare
    #    2.8x — an unknown buy share is not an unturned one), growth is
    #    real (hypergrowth 2.1x), the tape is volatile (vol LOW 0.3x, flat
    #    base 0.4x) and no dividend props the name (div yield LOW 1.7x).
    #    Strong 2020-2025, weak 2015-2018 — a re-rating needs a market that
    #    re-rates. Core tightened accordingly.
    _fund_up = ((_ncol('fq_rev_growth') >= 0.10) & (_ncol('op_margin_delta_yoy') > 0)).fillna(False)
    _sellside_unturned = ((_ncol('sent_n_analysts') >= 1) & _ncol('sent_buy_share_d12').notna()
                          & ~(_ncol('sent_buy_share_d12') > 0)).fillna(False)
    _low_gm = ((df['rel_ind_gross_margin'] <= 0.35) | (_ncol('gross_margin') < 0.25)).fillna(False)
    _tape_rerating = ((_ncol('price_vs_5y_avg') > 1.0) | (_ncol('ts_r52') > 0.20)).fillna(False)
    df['arch_mb_improving_unturned_sellside'] = (
        _mb_base & _fund_up & _sellside_unturned & _low_gm & _tape_rerating
        & (_crank(_ncol('ts_vol_1y')) >= 0.40).fillna(False) & ~(_ncol('dividend_yield') > 0.02)).astype(int)
    # 4. THE PEER GROUP'S WORST NAME AT ITS LOWEST MULTIPLE (the operators'
    #    10x recipe: lift 24-29x, 22-27% went 10x, blow-up 11-24%; Celestica
    #    2020 41x, GME 2018, PRMB 2012, AEIN.DE 2017): EV/EBIT and ROIC at
    #    the bottom of the INDUSTRY, thin FCF margin or the lowest P/S.
    _operator_early = ((_ncol('op_margin') >= 0) & (_ncol('fcf_margin') >= 0)).fillna(False)
    df['arch_mb_peer_worst_cheapest'] = (
        _mb_base & _operator_early & (df['rel_ind_ev_ebit'] <= 0.20).fillna(False) & (df['rel_ind_roce'] <= 0.25).fillna(False)
        & ((_ncol('fcf_margin') <= 0.03) | (df['rel_ind_p_s'] <= 0.25)).fillna(False)).astype(int)
    # ---- what the not-fallen, near-highs and uncovered passes surfaced ----
    # 5. THE COMPOUNDER, INSIDERS BUYING AT THE HIGH (near-highs 10x recipe:
    #    lift 90-108x on a 10x within 5 years, 55-68% of such month-ends
    #    went 10x, blow-up 0-8%; NVDA 2015 / 2019, 2059.TW 2021, MSTR 2020,
    #    TSLA 2019, ABMD 2013, ETSY 2017, AVGO 2020): within 15% of the 52w
    #    high, ROCE in the industry's top quartile, R&D-heavy, insiders
    #    buying — and the recent quarters NOT beating (expectations not yet
    #    set). Tiny support in the study; the structure recurs across a
    #    decade of names, so it is carried with that caveat in its label.
    _rd_heavy = ((_ncol('fmp_rd_to_revenue') >= 0.08) | (_ncol('fmp_rd_intensive_flag') == 1)).fillna(False)
    df['arch_mb_compounder_insiders_at_high'] = (
        _mb_base & (_ncol('ts_dist_hi52') >= 0.85).fillna(False) & (df['rel_ind_roce'] >= 0.75).fillna(False)
        & _rd_heavy & (_ins_2q | _corp_conviction)
        & ~((_ncol('evt_beat_share_8q') >= 0.6) | (_ncol('evt_surprise_4q') >= 0.05)).fillna(False)).astype(int)   # (audit 4) _ins_2q already falls back to the distinct-buyer / net-dollar record where the quarterly count is absent; a bare single purchase no longer bypasses a measured < 2 quarters
    # 6. HIRING, BEATING, UNCOVERED (the uncovered population's only lifted
    #    cluster, 2.1x, blow-up 15%; 2930.T 2015, BEL.NS 2020, HARVIA.HE
    #    2018, TRIDENT.NS 2019, TATAELXSI 2013): headcount +36%, margins at
    #    the top of their own history, beats and surprises, EV/sales already
    #    rising, new 13F holders — at 56% of the 5y high with no analyst.
    _hiring = ((_ncol('usf_emp_g1') >= 0.15)
               | (_ncol('usf_emp_g1').isna() & (_ncol('fq_rev_growth') >= 0.20))).fillna(False)
    _beating = ((_ncol('evt_beat_share_8q') >= 0.6) | (_ncol('evt_surprise_4q') >= 0.05)
                | (_ncol('fmp_earnings_beat_rate') >= 0.6)).fillna(False)
    df['arch_mb_hiring_beating_uncovered'] = (
        _mb_base & _hiring & (_mb_opm_gap >= 0.02).fillna(False) & _beating
        & ((_ncol('sent_n_analysts') <= 1) | (_ncol('sent_n_analysts').isna() & _ncol('esb_beats_8q').notna())).fillna(False)   # (audit 4) uncovered: <= 1 analyst on file, or no rating coverage at all on a name with a real earnings record
        & _hi260.between(0.35, 0.80).fillna(False)
        & ~(_ncol('evh_evs_log_chg_1y') < 0)).astype(int)   # EV/sales already rising (not falling where the dated series measures it)
    # 7. CHEAP GROWTH WITH TARGETS RISING (the largest not-fallen cluster,
    #    39% of those multibaggers, 1.25x, blow-up 8%; ISCTR 2020, ALARK
    #    2019, STRL 2021, 6920.T 2015, PGSUS 2018, TRIL.NS 2021): revenue
    #    +17%, EV/EBIT 8.5, FCF yield + growth the top axis, EV/EBIT vs
    #    growth the bottom, price targets revised up, at 70% of the 5y high.
    _pt_up = (((_ncol('sent_pt_rev_q') > 0) | (_ncol('evt_pt_rev_90d') > 0))
              & ~(_ncol('evt_pt_chase_flag') == 1)).fillna(False)        # a target lifted after the run is not "rising"
    _cheap_for_growth = (((_eveb > 0) & (_eveb <= 10))
                         | (_ncol('fcf_yield').notna() & ((_ncol('fcf_yield') + _ncol('fq_rev_growth')) >= 0.20))).fillna(False)
    df['arch_mb_cheap_growth_targets_up'] = (
        _mb_base & (_ncol('fq_rev_growth') >= 0.15).fillna(False) & _cheap_for_growth & _pt_up
        & (_hi260 >= 0.60).fillna(False)).astype(int)
    # 8. THE MODEL ARCHETYPE (multibagger_model.py): a walk-forward
    #    gradient-boosted model over every panel feature, judged year by year
    #    out of sample; today's names in the top 5% of their market by the
    #    model's probability. Holds the interactions the boxes cannot; its
    #    lift, blow-up and what it leans on are in MULTIBAGGER_MODEL.md.
    df['mb_model_rank_base'] = _crank(_ncol('mb_model_p'))          # within the country, among the liquid operating base
    df['arch_mb_model_top'] = (_mb_base & (df['mb_model_rank_base'] >= 0.95).fillna(False)).astype(int)
    # ---- the nine families of the robust mining (MULTIBAGGER_UNCOVERED.md) ----
    # Mined on USD outcomes with the search optimising the ROBUST lift: the
    # weaker of the two halves of time (to 2018 / from 2019), admitted only
    # with events over >= 3 markets (none above 60%) and >= 4 years. Cores as
    # mined; quintiles are within-country ranks among the liquid operating
    # base (the study's within-month-market ranks).
    _q_lo = lambda x: (_crank(x) <= 0.20).fillna(False)
    _q_hi = lambda x: (_crank(x) >= 0.80).fillna(False)
    _psv = _ncol('p_s').where(_ncol('p_s') > 0)
    _evsv = _ncol('ev_sales').where(_ncol('ev_sales') > 0)
    df['ind_tape_opm_d1'] = (_ncol('op_margin_delta_yoy').where(_frame_pop & (_peer_key != ''))
                             .groupby(_peer_key).transform('median').round(4))
    def _q_lo_ind(x):
        # bottom quintile among peer GROUPS (one observation per industry), mapped back to names, so
        # "the industry at its own trough" does not depend on how many names the industry has
        g = pd.Series(x.values, index=_peer_key.values).groupby(level=0).first()
        cut = g.dropna().quantile(0.20)
        return (x <= cut).fillna(False) & (_peer_key != '')
    _ind_trough = (_q_lo_ind(df['ind_tape_opm_d1']) | _q_lo_ind(df['ind_tape_rev_growth']))
    _asset_like = (sector.isin(['Energy', 'Materials', 'Real Estate', 'Utilities'])
                   | _ind_all.str.contains(r'shipping|marine|tanker|lessor|leasing|holding|reit|real estate|mining'
                                           r'|oil|gas|coal|steel|aluminum|gold|silver|uranium|timber|farm|metals', regex=True))
    _operator = ((_ncol('op_margin') >= 0) & (_ncol('fcf_margin') >= 0)).fillna(False) & ~_asset_like
    # U1. FALLEN, CHEAPEST ON SALES, IN AN INDUSTRY AT ITS OWN TROUGH: P/S bottom
    #     quintile, the INDUSTRY'S median margin change or growth in the bottom
    #     quintile, fallen. Robust 5.2-5.8x, 110-175 events, 10-12 years, 8-12
    #     markets, blow-up 8-11%, ~15 months to 3x (SARDAEN 2020, VEDL 2020,
    #     300274.SZ 2018, BTE.TO / YGR.TO 2020, ADANIENT 2013).
    df['arch_mb_industry_trough_cheapest'] = (_mb_base & _mb_fallen & _q_lo(_psv) & _ind_trough).astype(int)
    # U2. REINVESTING AT THE TROUGH: capex / revenue top quintile, P/S bottom
    #     quintile and below its own history, fallen. Robust 5.8x, 112 events,
    #     11 years, 10 markets, blow-up 18% (9107.T 2019, 8869.KL 2016, VEDL).
    df['arch_mb_reinvesting_at_trough'] = (_mb_base & _mb_fallen & _q_hi(_ncol('capex_intensity')) & _q_lo(_psv)
                                           & _cheap_own).astype(int)
    # U3. STRESSED BUT NOT DILUTING, AT THE BOTTOM OF ITS RANGE: net debt /
    #     EBITDA >= 5 or negative equity, share count not rising, fallen and
    #     near the 52-week low. Robust 6.0x, 94 events, 10 years, 9 markets,
    #     blow-up 25% (SUZLON 2020, SNBR 2020, SNH.JO 2019).
    _stressed = (((nde >= 5) & (nde < 90)) | (_ncol('equity') < 0)).fillna(False)
    _sh_g = _ncol('fq_shares_yoy').where(_ncol('fq_shares_yoy').notna(), _ncol('fmp_st_shares_growth_3y'))
    _not_diluting = (_sh_g <= 0.03).fillna(False)                      # measured, not assumed; fmp_filled_* are fill FLAGS
    df['arch_mb_stressed_not_diluting'] = (_mb_base & _mb_fallen & _stressed & _not_diluting
                                           & (_ncol('ts_dist_lo52') <= 1.15).fillna(False)).astype(int)
    # U4. GROWTH PAST ITS CAPEX PEAK (not fallen): two-year revenue growth in the
    #     top quintile (or capex / D&A high), no payout, CAPEX ROLLING OFF
    #     (this year's capex below last year's while still above D&A), ROIC at
    #     its own high or volatile vs its industry. Robust 7.1-7.5x, 80-104
    #     events, 11-14 years, 9-12 markets, blow-up 22-33% (TSLA 2018,
    #     FNOX.ST 2016-18, 001570.KS 2021, IIVI 2019, HTHT 2015).
    _capex_rolloff = ((_ncol('fq_capex').abs() < _ncol('fq_capex_p').abs()) & (_ncol('fq_capex_to_da') > 1.0)).fillna(False)
    _no_payout = ~((_ncol('dividend_yield') > 0.005) | (_ncol('buyback_yield') > 0.005)).fillna(False)
    _g2 = _ncol('bs_rev_g_2y').fillna((1.0 + _ncol('fmp_st_revenue_3y_cagr').where(_ncol('fmp_st_revenue_3y_cagr').notna(),
                                                                                    _ncol('fmp_st_revenue_cagr'))) ** 2 - 1.0)   # TWO-year growth (panel), CAGR-implied 2y as fallback
    _roic_own_hi = ((_ncol('fqx_roic_ttm') > _ncol('roic_lindy')) | (_ncol('fqx_roic_streak') >= 3)).fillna(False)
    df['arch_mb_growth_past_capex_peak'] = (
        _mb_base & (_hi260 >= 0.60).fillna(False) & (_q_hi(_g2) | _q_hi(_ncol('fq_capex_to_da'))) & _no_payout
        & _capex_rolloff & (_roic_own_hi | (_crank(_ncol('ts_vol_1y')) >= 0.8).fillna(False))).astype(int)
    # U5. FALLEN LESS THAN ITS INDUSTRY, FINANCED WHILE BOOK GROWS, NEGLECTED
    #     (fallen, 10x; the mined condition is 'distance from 5y high MINUS the
    #     industry's HIGH' — the name is >= 60% below its high but has held up
    #     BETTER than its industry): share issuance with negative FCF
    #     (financing dependence), equity compounding in the top quintile,
    #     <= 1 analyst. Robust 7.0x, 49 events, 9 years, 11
    #     markets, blow-up 29%, 10x rate 7% (ROCK-A.CO 2015, TTRAK.IS 2019,
    #     GULFNAV.AE 2022, EUZ.DE 2017, 3324.TWO 2014).
    _financed = (((_ncol('fmp_st_shares_growth_3y') >= 0.05) & (_ncol('fcf_yield') < 0))
                 | (_ncol('fq_financing_cf') > 0)).fillna(False)
    _book_growing = _q_hi(_ncol('equity_cagr_5y').fillna(_ncol('fmp_st_equity_cagr')))
    df['arch_mb_fallen_less_than_industry_financed'] = (
        _mb_base & _mb_fallen & _financed & _book_growing
        & (_crank(df['vs_ind_dist_hi260'].where(_mb_fallen)) >= 0.80).fillna(False)   # (audit 4) ranked WITHIN the fallen: among the fallen, fell LESS than its industry
        & (_ncol('sent_n_analysts').fillna(0) <= 1)).astype(int)
    # U6. LEAN R&D MANUFACTURER STOCKING UP OFF THE LOW (10x): well off the
    #     52-week low, inventory growing faster than cost of sales, R&D top
    #     quintile, SG&A bottom quintile. Robust 17.7x on THIN support (39
    #     events, 6 years, 5 markets, Japan 56%; Lasertec 2016 58x, SMCI 2019
    #     52x, CLS.TO 2020, LONGi 2013) — carried with that stated.
    _sga_rev = _ncol('fq_sga') / _ncol('fq_revenue').where(_ncol('fq_revenue') > 0)
    df['arch_mb_lean_rd_stocking_up'] = (
        _mb_base & _q_hi(_ncol('ts_dist_lo52')) & (_ncol('fq_inv_vs_cogs') > 0.05).fillna(False)
        & _q_hi(_ncol('fmp_rd_to_revenue').where(_ncol('fmp_rd_to_revenue') > 0)) & _q_lo(_sga_rev)).astype(int)
    # C7. DIVERGENCE + CHEAPEST P/B IN ITS INDUSTRY + WIDE RANGE (covered):
    #     fundamentals ahead of price (narrative lag >= log 1.5, or margins
    #     above their through-cycle norm with the price at half its high), P/B
    #     bottom quintile of the industry, volatile. Robust 4.2-4.4x, ~200
    #     events, 12-14 years, 14-23 markets, blow-up 21-33%, 10x rate 5-11%
    #     (0412.HK 2013, DAC 2020, MEG.TO 2020, AXTI 2024, PR 2020, LXU 2020).
    _divergence = ((_ncol('narrative_lag_extent') >= np.log(1.5))
                   | ((_mb_opm_gap >= 0.02) & (_hi260 <= 0.5) & (_ncol('fq_rev_growth') >= 0))).fillna(False)
    df['arch_mb_divergence_cheapest_pb'] = (
        _mb_base & _divergence & (df['rel_ind_pb'] <= 0.20).fillna(False) & (_ncol('pb') <= 1.5).fillna(False)
        & (_crank(_ncol('ts_vol_1y')) >= 0.6).fillna(False)).astype(int)
    # C8. FALLEN OPERATOR, EV/SALES LOW, IN AN INDUSTRY FAR FROM ITS HIGH (10x):
    #     a profitable operator >= 60% below its high, EV/sales bottom quintile,
    #     the INDUSTRY'S own distance from its 5-year high in the bottom
    #     quintile, two-year return low or P/S bottom of peers. Robust 9-11x,
    #     51-58 events, 7 years, 7 markets, blow-up 15-19%, 10x rate 10-12%
    #     (LMB 2020, DDS 2020, SMCI 2018, ARVIND 2020, GME 2018).
    df['arch_mb_fallen_operator_industry_low'] = (
        _mb_base & _operator & _mb_fallen & _q_lo(_evsv) & _q_lo_ind(df['ind_tape_dist_hi260'])
        & (_q_lo(_ncol('ts_r104')) | (df['rel_ind_p_s'] <= 0.20).fillna(False))).astype(int)
    #     sister: QUALITY AT DISTRESS — deep drawdown, EV/sales low, ROCE x FCF
    #     yield top quintile, P/B bottom of peers. Robust 9.2x, 52 events, 6
    #     years, 6 markets, blow-up 27-29% (CLS 2020, PRMB 2012, WAWI.OL 2020).
    _roce_x_fcfy = _ncol('roce').clip(0, 1) * _ncol('fcf_yield').clip(0, 1)   # (audit 4) gate and lens on the same bounds: a (-)x(-) product is not quality x yield
    df['arch_mb_quality_at_distress'] = (
        _mb_base & _operator & (_hi260 <= 0.5).fillna(False) & _q_lo(_evsv) & _q_hi(_roce_x_fcfy)
        & (df['rel_ind_pb'] <= 0.20).fillna(False)).astype(int)
    # C9. R&D LEADER ON VOLUME, PRICE AHEAD OF EPS (not fallen): two-year return
    #     top quintile, a volume surge, R&D top quintile, EPS per share behind
    #     the price. Robust 5.5x, 97 events, 9 years, 12 markets, blow-up 22%
    #     (NVDA 2015, TRIL.NS 2022, CLS.TO 2023, DIXON 2020).
    _vol_surge = ((_ncol('bs_cp_dvol_z13') >= 1.0) | (_ncol('ts_vol_spike') >= 2.0)      # volume / 52w median
                  | (_ncol('ts_vol_spike4') >= 2.5)).fillna(False)
    df['arch_mb_rd_leader_on_volume'] = (
        _mb_base & (_hi260 >= 0.60).fillna(False) & _q_hi(_ncol('ts_r104')) & _vol_surge
        & _q_hi(_ncol('fmp_rd_to_revenue').where(_ncol('fmp_rd_to_revenue') > 0)) & (_ncol('nl_eps_1y') < 0).fillna(False)).astype(int)
    #     sister: CHEAP VS PEERS, RECOVERING, FCF STREAK RISING — well off the
    #     52-week low, volatile, P/S bottom quintile of its peers, FCF margin
    #     rising for >= 2 quarters. Robust 4.7x, 98 events, 12 years, 16
    #     markets, blow-up 20% (ADANIENT 2020, CLS 2023, LMB 2022, SHYF 2016).
    df['arch_mb_cheap_vs_sector_recovering'] = (
        _mb_base & _q_hi(_ncol('ts_dist_lo52')) & _q_hi(_ncol('ts_vol_1y')) & (df['rel_ind_p_s'] <= 0.20).fillna(False)
        & (_ncol('fqx_fcfm_streak') >= 2).fillna(False)).astype(int)
    _SPIRITED += ['mb_industry_trough_cheapest', 'mb_reinvesting_at_trough', 'mb_stressed_not_diluting',
                  'mb_growth_past_capex_peak', 'mb_fallen_less_than_industry_financed', 'mb_lean_rd_stocking_up',
                  'mb_divergence_cheapest_pb', 'mb_fallen_operator_industry_low', 'mb_quality_at_distress',
                  'mb_rd_leader_on_volume', 'mb_cheap_vs_sector_recovering']
    _SPIRITED += ['mb_wave_neglected_value_accel', 'mb_leader_in_wave', 'mb_improving_unturned_sellside',
                  'mb_peer_worst_cheapest', 'mb_compounder_insiders_at_high', 'mb_hiring_beating_uncovered',
                  'mb_cheap_growth_targets_up', 'mb_model_top']
    _SPIRITED += ['mb_fallen_deep_value', 'mb_fallen_value_turn', 'mb_fallen_value_accel', 'mb_fallen_stressed',
                  'mb_fallen_insider', 'mb_fallen_trough', 'mb_fallen_below_cycle', 'mb_inflecting_operator',
                  'mb_quiet_turn', 'mb_left_for_dead_value', 'mb_fallen_ignored_believers',
                  'mb_smart_money_wreckage', 'mb_grew_into_valuation_turning', 'mb_tree_recipe',
                  'mb_tree_recipe_10x', 'mb_sequence_preignition']
    # Rank score (0-1), weights re-calibrated to the event study's OUT-OF-
    # SAMPLE lifts (fit <= 2018, test 2019+): fallen-angel context was the
    # strongest single ingredient (bottom prior-drawdown quintile 3.3x; with
    # the coil 3.7x), ignition next (2.3x; volume-led), the coil alone modest
    # (1.25x); low coverage / small size a tilt (few analysts 1.26x vs many
    # 0.30x). Components are clipped to [0, 1]: counts SATURATE (coil 3 of 5
    # legs, perception 2 of 5, ignition 3 of 5), depth over a 3x coil.
    _coil_depth = (_num('bs_coil_rev').clip(0, np.log(3)) / np.log(3)).fillna(0)
    _fallen = ((0.60 - _num('bs_prior_dd')) / 0.40).clip(0, 1).fillna(0)
    _small = ((9.0 - _num('bs_size_dvol')) / 3.0).clip(0, 1).fillna(0)   # < $1bn/wk dvol tilts up
    df['coiled_base_score'] = (((0.15 * (_coil_n / 3).clip(0, 1) + 0.10 * _coil_depth
                                 + 0.15 * (_perc_n / 2).clip(0, 1) + 0.25 * (_ign_n / 3).clip(0, 1)
                                 + 0.25 * _fallen + 0.10 * _small).clip(0, 1))
                               * df['arch_coiled_base']).round(3)
    df['coiled_base_legs'] = (_coil_n.astype(str) + 'C/' + _perc_n.astype(str) + 'P/'
                              + _ign_n.astype(str) + 'I').where(df['arch_coiled_base'] == 1, '')

    # ============ USER ARCHETYPES (2026-09-29) ============
    # Shared: LOW STARTING EXPECTATIONS read by sign, never by an invented size —
    # the price is below where it was a year ago, OR the EV/sales multiple is
    # below its own 3-year median, OR no sell-side coverage at all where the
    # estimate feed reaches the name. The depth of each is a weight.
    _low_expect = ((_ncol('ts_r52') <= 0) | (_ncol('evh_evs_vs_med_3y') < 0)
                   | ((_ncol('sent_n_analysts') == 0) | (_ncol('sent_n_analysts').isna() & _ncol('esb_beats_8q').notna()))
                   ).fillna(False)
    # NET CASH by sign: cash above debt on the latest balance sheet (quarterly
    # panel, same currency), else the master's net-cash share, else net debt /
    # EBITDA at or below zero
    _nc_q = (_ncol('fq_cash_sti') - _ncol('fq_total_debt').fillna(0)).where(_ncol('fq_cash_sti').notna())
    _net_cash = ((_nc_q > 0) | (_nc_q.isna() & (net_cash_pct > 0))
                 | (_nc_q.isna() & net_cash_pct.isna() & (_nde_meaningful <= 0))).fillna(False)
    # PROFIT 90%+ OF THE TIME (user's number): operating income positive in
    # >= 90% of the fiscal years on file (>= 5 years), else the statement-history
    # count, else EPS positive in >= 7 of the last 8 quarters (87.5%)
    _yrs_tc = _ncol('tc_years').where(_ncol('tc_years') >= 5)
    _prof_share = (_ncol('tc_opinc_pos') / _yrs_tc).fillna(
        _ncol('fmp_st_n_yrs_positive_opinc') / _ncol('fmp_st_years_of_history').where(_ncol('fmp_st_years_of_history') >= 5))
    _steady_profit = ((_prof_share >= 0.90)
                      | (_prof_share.isna() & (_ncol('fqx_eps_pos_share_8') >= 0.875))).fillna(False)
    # REASONABLE CAPITAL ALLOCATION by sign: the share count is not growing
    # (3-year, else the FY diluted count) and returns to owners are not paid
    # out of cash the business did not earn (no uncovered payout year of 3)
    _sh3_ca = _ncol('shares_growth_3y').fillna(_ncol('fg_shares_dil_g1'))
    _capalloc_ok = (~(_sh3_ca > 0.0) & ~(_ncol('tc_uncov_payout_3y') >= 1))
    _ev_ebit_u = s('ev_ebit', np.nan)
    # 1. CHEAP NET-CASH STEADY EARNER (user): EV/EBIT below 5x, net cash, a
    #    profit in 90%+ of years, reasonable capital allocation, low starting
    #    expectations.
    df['arch_cheap_net_cash_steady_earner'] = (
        is_operating & (mcap > 0) & _ev_sane
        & (_ev_ebit_u > 0) & (_ev_ebit_u < 5.0)
        & _net_cash & _steady_profit & _capalloc_ok & _low_expect
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('cheap_net_cash_steady_earner', []).extend([
        (_ev_ebit_u.where(_ev_ebit_u > 0), -1), (net_cash_pct, 1), (_prof_share, 1),
        (_ncol('roic_lindy'), 1), (_ncol('ts_dist_hi260'), -1), (_ncol('sent_n_analysts'), -1)])
    # 2. PSIX (user; Power Solutions International 2024): low starting
    #    expectations, balance-sheet survivorship, revenue ACCELERATING, gross
    #    margin RISING, incremental operating margin above the existing margin,
    #    capex and R&D funded internally, no dilution, valuation still low.
    _surv_psix = (_not_melting & ((_ncol('fq_interest_cover') > 1) | _net_cash
                                  | (_ncol('fq_interest_cover').isna() & (_nde_meaningful <= 0)))).fillna(False)
    _rev_accel_psix = ((_ncol('fq_rev_growth') > 0)
                       & ((_ncol('fqx_rev_accel_now') == 1) | (rev_accel > 0))).fillna(False)
    _gm_rising = ((_ncol('gross_margin_delta_yoy') > 0) | (_ncol('fq_gm_inflection_flag') == 1)).fillna(False)
    _inc_opm_high = (_ncol('fqx_inc_ebit_margin_dt') > _ncol('fqx_opm_ttm').fillna(s('op_margin', np.nan))).fillna(False)
    _self_funded = ((_ncol('fq_fcf') > 0) | (_ncol('fcf_ttm') > 0)).fillna(False)   # CFO (after R&D, expensed) covers capex
    # "no dilution": the count not growing — a rounding tolerance of 0.5% for
    # share-count noise, stated rather than hidden
    _no_dil_psix = (~(_ncol('fq_shares_yoy').fillna(_ncol('shares_yoy')).fillna(_ncol('fg_shares_dil_g1')) > 0.005)).fillna(False)
    # still LOW, not merely de-rated: EV/EBIT positive and at or below the
    # median of its own listing market (a peer comparison, not an invented
    # number), AND EV/sales not above its own 3-year median where dated (no
    # EV/EBIT history exists: fmp_ev_history carries EV/sales medians only)
    _evb_mkt_med = _ev_ebit_u.where(is_operating & (_ev_ebit_u > 0)).groupby(country).transform('median')
    _still_low = ((_ev_ebit_u > 0) & (_ev_ebit_u <= _evb_mkt_med)
                  & ~(_ncol('evh_evs_vs_med_3y') > 0)).fillna(False)
    df['arch_psix'] = (
        is_operating & (mcap > 0) & _ev_sane
        & _low_expect & _surv_psix & _rev_accel_psix & _gm_rising
        & _inc_opm_high & _self_funded & _no_dil_psix & _still_low
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('psix', []).extend([
        (_ncol('fqx_inc_ebit_margin_dt'), 1), (_ncol('gross_margin_delta_yoy'), 1),
        (_ncol('fq_rev_growth'), 1), (net_cash_pct, 1), (_ncol('evh_evs_vs_med_3y'), -1),
        (_ncol('ts_dist_hi260'), -1)])

    # ============ GAYNER (Markel) ARCHETYPES (2026-10-01; audit fixes 2026-10-02) ============
    # Tom Gayner, Ben Graham Centre fireside chat. The catechism repeated in
    # every Markel annual report for 35 years — four lenses on any investment:
    #   1. a profitable business with good returns on capital ("a profit margin
    #      is a social stamp of approval");
    #   2. management with equal measures of talent and integrity ("one without
    #      the other is worthless");
    #   3. reinvestment dynamics — organic runway, acquisitions that earn, or
    #      capital discipline in dividends / buybacks ("the single biggest
    #      change" in his thinking: lens 3 matters most);
    #   4. a FAIR price — "the least important of the four" (American Express
    #      bought the day BEFORE the salad-oil scandal: the difference dissolves
    #      over 50 years).
    # Plus two observations about the tape: Markel doubled eight times from the
    # IPO and had eight drawdowns of 20%+ along the way ("oh, I missed it" at
    # every sideways stretch), and the obsolescence test ("if this business did
    # not exist, would we start it?") that separates a temporary wiggle
    # (alcohol, bread) from a shot horse (newspapers).
    # Thresholds: Gayner's own numbers where he gives them (20% drawdowns,
    # Markel's ~15% compounding), peer frames for price (listing-market and
    # industry medians), and stated house levels for the rest (ROIC / ROIIC
    # 12%, growth 5%, payout 2%, SBC 5%, CFO/NI 0.6). Coverage: lindy ROIC / the
    # through-cycle record reach ~87% of the universe; exec-comp alignment
    # reaches <1% and is therefore a WEIGHT, never a gate.
    _g_roic = _ncol('roic_lindy').fillna(_ncol('fmp_st_roic_lindy'))
    _g_roiic = _ncol('roiic_lindy').fillna(_ncol('fmp_st_roiic_lindy'))
    _g_years = _ncol('tc_years').fillna(_ncol('fmp_st_years_of_history'))
    # share count: 3-year growth (master, else statements, else FY diluted).
    # "Not growing" allows 0.5% of rounding / option-exercise noise; the
    # integrity lens separately bars real dilution (> 5% over three years).
    _g_sh3 = _ncol('shares_growth_3y').fillna(_ncol('fmp_st_shares_growth_3y')).fillna(_ncol('fg_shares_dil_g1'))
    _g_no_dil = ~(_g_sh3 > 0.005)
    # lens 1 — profitable through the cycle with good returns on capital (lindy
    # ROIC >= 12%: the multi-year read, never a one-off spot). Both history
    # sources cap at 8 fiscal years, so "profitable through the cycle" is read
    # as at most one loss year in the window (>= 7 of 8 = 0.875; >= 5 years on
    # file) — at 8 years a 90% bar would silently mean "never a loss".
    _g_prof_share = (_ncol('tc_opinc_pos') / _ncol('tc_years').where(_ncol('tc_years') >= 5)).fillna(
        _ncol('fmp_st_n_yrs_positive_opinc')
        / _ncol('fmp_st_years_of_history').where(_ncol('fmp_st_years_of_history') >= 5))
    _g_prof_ok = (_g_prof_share >= 0.875)
    _g_lens1 = ((_g_roic >= 0.12) & _g_prof_ok & (_opm_now > 0)).fillna(False)
    # lens 2 — talent AND integrity, read from what the statements reveal:
    # talent = the business is run at or above its own through-cycle margin
    # (not coasting on a legacy franchise; the 8-quarter margin slope where no
    # through-cycle record exists; unmeasured passes). Integrity = earnings are
    # cash, no manipulation-risk print (Beneish), no data-quality flag, SBC not
    # polluting the P&L (<= 5% of revenue), no one-off-inflated earnings, no
    # real dilution (> 5% over three years). Earnings-as-cash is read on the
    # quarterly panel (CFO/NI >= 0.6), else the master TTM CFO/NI, AND on the
    # through-cycle record: average FCF margin at least a quarter of the median
    # operating margin. The fallbacks matter where no quarterly panel exists
    # (audit 2026-10-02: Brightcom, CFO/NI 0.19, FCF margin -0.4% against a
    # 22.5% operating margin, passed every quarterly test on missing data).
    _g_sbc = _ncol('sbc_pct_revenue').fillna(_ncol('fq_sbc_pct_revenue')).fillna(_ncol('fmp_sbc_to_revenue'))
    _g_tcm = _ncol('tc_med_opm')
    _g_slope = _ncol('fqx_opm_slope8')
    _g_talent = ((_g_tcm.notna() & (_opm_now >= 0.9 * _g_tcm))
                 | (_g_tcm.isna() & _g_slope.notna() & (_g_slope >= 0))
                 | (_g_tcm.isna() & _g_slope.isna()))
    _g_ni_ttm = _ncol('net_income_ttm')
    _g_cfo_ni = _ncol('fq_cfo_to_ni').fillna(_ncol('cfo_ttm') / _g_ni_ttm.where(_g_ni_ttm > 0))
    _g_cash_record = ~((_g_tcm > 0) & (_ncol('tc_fcf_margin_avg') < 0.25 * _g_tcm))
    _g_integrity = (~(_g_cfo_ni < 0.6) & _g_cash_record & ~(_ncol('fq_beneish_risk_flag') == 1)
                    & ~(_ncol('data_quality_flag') == 1) & ~(_g_sbc > 0.05)
                    & ~(_ncol('earnings_oneoff_flag') == 1) & ~(_g_sh3 > 0.05))
    _g_lens2 = (_g_talent & _g_integrity).fillna(False)
    # lens 3 — reinvestment dynamics, any of the three forms Gayner names:
    # (a) organic runway: incremental capital earns (lindy ROIIC >= 12%) and the
    #     business is actually deploying it (revenue or assets compounding
    #     >= 5%/yr over 3-5 years);
    # (b) acquisitions that earn: acquisition spend on the balance sheet (>= 2%
    #     of assets) with ROIC held >= 12% — the return survives the deals;
    # (c) capital discipline: returns to owners (>= 2% yield) out of cash the
    #     business earned (no uncovered payout year of three) with the share
    #     count not growing.
    _g_rev5 = _ncol('revenue_5y_cagr').fillna(_ncol('fmp_st_revenue_5y_cagr'))
    _g_growth = ((_g_rev5.fillna(_ncol('revenue_3y_cagr')) >= 0.05)
                 | (_ncol('asset_3y_cagr').fillna(_ncol('fmp_st_asset_3y_cagr')) >= 0.05))
    _g_organic = ((_g_roiic >= 0.12) & _g_growth).fillna(False)
    _g_acquirer = ((_ncol('fq_acq_pct_assets') >= 0.02) & (_g_roic >= 0.12)).fillna(False)
    _g_capret = _ncol('capital_return_yield').fillna(_ncol('fmp_st_capital_return_yield'))
    _g_discipline = ((_g_capret >= 0.02) & ~(_ncol('tc_uncov_payout_3y') >= 1) & _g_no_dil).fillna(False)
    _g_lens3 = _g_organic | _g_acquirer | _g_discipline
    # lens 4 — a FAIR price, not a cheap one: EV/EBIT positive and no more than
    # 1.5x the median of its own listing market (a peer frame), within the EV
    # sanity band. Gayner's point is that lenses 1-3 let you pay up a little.
    # EV/EBIT is missing for ~60% of names; where it is, it is rebuilt as
    # EV / (operating margin x revenue) for a profitable name, kept only inside
    # the 2-100x band the master's own sanity rules use.
    _g_ebit_est = _opm_now * _ncol('revenue_ttm')
    _g_evb_fb = (_ncol('enterprise_value') / _g_ebit_est.where(_g_ebit_est > 0))
    _g_evb = _ev_ebit_u.fillna(_g_evb_fb.where(_g_evb_fb.between(2.0, 100.0)))
    _g_evb_mkt_med = _g_evb.where(is_operating & (_g_evb > 0)).groupby(country).transform('median')
    _g_lens4 = ((_g_evb > 0) & (_g_evb <= 1.5 * _g_evb_mkt_med) & _ev_sane).fillna(False)
    # 1. GAYNER FOUR-LENS: all four lenses at once — the catechism as a screen.
    df['arch_gayner_four_lens'] = (
        is_operating & (mcap > 0) & _g_lens1 & _g_lens2 & _g_lens3 & _g_lens4 & _not_melting
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('gayner_four_lens', []).extend([
        (_g_roic, 1), (_g_roiic, 1), (_g_prof_share, 1), (_g_years, 1),
        (_ncol('ts_maxdd_5y'), 1), (_g_evb.where(_g_evb > 0), -1),
        (insider, 1), (_ncol('fmp_insider_alignment_ratio'), 1), (_g_sbc, -1)])
    # 2. GAYNER PAY-UP QUALITY: lenses 1-3 at their strongest (Markel's own 15%
    #    compounding: lindy ROIC and ROIIC >= 15%, revenue compounding >= 8%/yr,
    #    profitable through the window) and the FOURTH lens deliberately failed
    #    — EV/EBIT ABOVE its market's median (not cheap) but no more than 3x it
    #    (not absurd). The American-Express-the-day-before set: every
    #    conventional cheapness screen drops it; the reinvestment runway is the
    #    thesis. (Lens 3 is implied: ROIIC >= 15% with 8% growth is its organic
    #    route; a separate "7+ years" leg was a no-op at the 8-year cap.)
    _g_strong = ((_g_roic >= 0.15) & (_g_roiic >= 0.15)
                 & _g_prof_ok & (_g_rev5 >= 0.08)).fillna(False)
    _g_not_cheap = ((_g_evb > _g_evb_mkt_med) & (_g_evb <= 3.0 * _g_evb_mkt_med) & _ev_sane).fillna(False)
    df['arch_gayner_pay_up_quality'] = (
        is_operating & (mcap > 0) & _g_strong & _g_lens2 & _g_not_cheap
        & _g_no_dil & _not_melting
    ).fillna(False).astype(int)
    # 3. GAYNER "I MISSED IT": a long compounding record (per-share EBIT, net
    #    income or book compounding >= 12%/yr over 5 years, lindy ROIC >= 12%,
    #    profitable through the window) whose tape has gone sideways — flat over
    #    12 months, or in one of its 20%+ drawdowns from the 5-year high without
    #    having risen more than 20% on the year (a drawdown that a 100%+ rally
    #    has half-recovered is not "sitting at 32"; the 52-week high where the
    #    weekly panel does not reach) — while the earnings kept growing (TTM
    #    EBIT up, else the latest fiscal year). No dilution.
    #    UNITS (audit 2026-10-02): the per-share sources are CUMULATIVE 5-year
    #    growth (median +40%); they are annualised before the 12%/yr test. The
    #    book-value fallbacks are already annual rates.
    def _g_ann5(x):
        return (1.0 + x.where(x > -1.0)) ** 0.2 - 1.0
    _g_ps5 = (_g_ann5(_ncol('fmp_st_ebit_ps_5y_g')).fillna(_g_ann5(_ncol('fg_ni_ps_5y')))
              .fillna(_ncol('equity_cagr_5y')).fillna(_ncol('fmp_st_equity_cagr')))
    _DEMOTED.setdefault('gayner_pay_up_quality', []).extend([
        (_g_roiic, 1), (_g_rev5, 1), (_g_ps5, 1),
        (_g_years, 1), (_ncol('ts_maxdd_5y'), 1), (_g_evb / _g_evb_mkt_med, -1)])
    _g_record = ((_g_ps5 >= 0.12) & (_g_roic >= 0.12) & _g_prof_ok).fillna(False)
    _g_r52 = _ncol('ts_r52')
    _g_stalled = ((_g_r52 <= 0.05)
                  | ((_ts_hi260 <= 0.80) & ~(_g_r52 > 0.20))
                  | (_ts_hi260.isna() & (_ncol('pct_off_52w_high') <= -0.20) & ~(_g_r52 > 0.20))).fillna(False)
    _g_still_growing = ((_ncol('fqx_ebit_ttm_g') > 0)
                        | (_ncol('fqx_ebit_ttm_g').isna() & (_ncol('fmp_st_ebit_g1') > 0))).fillna(False)
    df['arch_gayner_missed_it'] = (
        is_operating & (mcap > 0) & _g_record & _g_stalled & _g_still_growing
        & _g_no_dil & _g_integrity & _not_melting
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('gayner_missed_it', []).extend([
        (_g_ps5, 1), (_g_roic, 1), (_ncol('fqx_ebit_ttm_g'), 1), (_ts_hi260, -1),
        (_g_r52, -1), (_ncol('ts_dd_time_share_260'), 1), (_g_years, 1)])
    # 4. GAYNER FRUGAL OPERATOR: the one factor the Davis study found in good
    #    investors — frugality — read on the company: a lean cost structure
    #    (SG&A/revenue MEASURED and not above its industry median), SBC <= 2%
    #    of revenue, operating margin not below its industry median (the
    #    frugality shows up as margin), owners' money treated as owners' money
    #    (no uncovered payout, no share-count growth), insiders aligned, good
    #    returns on capital, a profit through the cycle. Exec comp relative to
    #    profit is a weight where disclosed.
    #    Industry medians are taken over PROFITABLE operating names: a median
    #    that includes loss-making drug developers would make any profitable
    #    pharma look lean. Alignment = insiders buying, the FMP alignment ratio,
    #    or a 10-60% insider stake — the house band (flyover uses 20-60%): a
    #    holder above 60% is usually a controlling parent or the state, whose
    #    interest is not the minority owner's.
    _g_sga_rev = _ncol('fq_sga') / _ncol('fq_revenue').where(_ncol('fq_revenue') > 0)
    _ind_g = (df['industry'].fillna('').astype(str).str.lower()
              if 'industry' in df.columns else pd.Series('', index=df.index))
    _g_peer = is_operating & (_ind_g != '') & (_opm_now > 0)
    _g_sga_ind_med = _g_sga_rev.where(_g_peer).groupby(_ind_g).transform('median')
    _g_opm_ind_med = _opm_now.where(_g_peer).groupby(_ind_g).transform('median')
    _g_lean = (_g_sga_rev.notna() & ~(_g_sga_rev > _g_sga_ind_med) & ~(_opm_now < _g_opm_ind_med))
    _g_aligned = ((insider.between(0.10, 0.60)) | (_ncol('insider_buy_flag') == 1)
                  | (_ncol('fmp_insider_aligned_flag') == 1)).fillna(False)
    df['arch_gayner_frugal_operator'] = (
        is_operating & (mcap > 0) & _g_lean & ~(_g_sbc > 0.02) & _g_aligned
        & ~(_ncol('tc_uncov_payout_3y') >= 1) & _g_no_dil
        & (_g_roic >= 0.12) & _g_prof_ok & _g_integrity & _not_melting
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('gayner_frugal_operator', []).extend([
        (_g_sga_rev / _g_sga_ind_med.where(_g_sga_ind_med > 0), -1), (_opm_now - _g_opm_ind_med, 1),
        (_g_sbc, -1), (insider, 1), (_ncol('fmp_insider_alignment_ratio'), 1), (_g_roic, 1),
        (_ncol('fmp_exec_comp_total') / _ncol('net_income_ttm').where(_ncol('net_income_ttm') > 0), -1)])
    # 5. GAYNER WIGGLE, NOT OBSOLETE: a franchise with a long record (the full
    #    statement window on file — 8 fiscal years, the cap of both history
    #    sources — at most one non-COVID loss year, lindy ROIC >= 10%)
    #    whose price is 20%+ off its 5-year high while perception has turned
    #    against it (buy share falling, targets cut, or the stock down on the
    #    year) and that has NOT already rallied more than 20% on the year (a
    #    momentum pullback is not an out-of-favour franchise) — yet the
    #    business passes the "would we start it today" test as far as the
    #    statements can tell: sales not shrinking (TTM >= -5%) and the operating
    #    margin still at >= 75% of its through-cycle median. The alcohol /
    #    bread case, not the newspaper case. Clean books required (integrity,
    #    incl. the master-CFO and through-cycle cash fallbacks).
    _g_long = ((_g_years >= 8) & ~(_ncol('tc_loss_years_other') > 1) & (_g_roic >= 0.10)).fillna(False)
    _g_rev_now = _ncol('fq_rev_growth').fillna(_ncol('rev_yoy'))
    _g_intact = ((_g_rev_now >= -0.05) & (_opm_now >= 0.75 * _g_tcm) & (_opm_now > 0)).fillna(False)
    _g_out_of_favour = (((_ts_hi260 <= 0.80) | (_ts_hi260.isna() & (_ncol('pct_off_52w_high') <= -0.20)))
                        & ((_ncol('sent_buy_share_d12') < 0) | (_ncol('sent_pt_rev_q') < 0)
                           | (_g_r52 < 0))
                        & ~(_g_r52 > 0.20)).fillna(False)
    df['arch_gayner_wiggle_not_obsolete'] = (
        is_operating & (mcap > 0) & _g_long & _g_intact & _g_out_of_favour
        & _g_no_dil & _g_integrity & _not_melting
    ).fillna(False).astype(int)
    _DEMOTED.setdefault('gayner_wiggle_not_obsolete', []).extend([
        (_ncol('tc_min_opm'), 1), (_g_years, 1), (_g_roic, 1), (_g_rev_now, 1),
        (_opm_now / _g_tcm.where(_g_tcm > 0), 1), (_ts_hi260, -1), (_ncol('sent_buy_share_d12'), -1)])

    arch_cols = [
        'arch_cheap_net_cash_steady_earner', 'arch_psix',
        'arch_gayner_four_lens', 'arch_gayner_pay_up_quality', 'arch_gayner_missed_it',
        'arch_gayner_frugal_operator', 'arch_gayner_wiggle_not_obsolete',
        'arch_cannabis_operator', 'arch_senior_security_value',
        'arch_narrative_lag',
        'arch_derate_through_growth',
        'arch_fixed_cost_demand_shock',
        'arch_discounted_vehicle',
        'arch_capital_discipline',
        'arch_regime_cyclical',
        'arch_dead_option',
        'arch_kpi_threshold',
        'arch_blindspot',
        'arch_micro_activist_inflect',
        'arch_durable_reinvestment',
        'arch_cash_reinvest',
        'arch_roic_inflect',
        'arch_cheap_per_roiic',
        'arch_tangible_value',
        'arch_lindy_margin',
        'arch_lindy_fcf',
        'arch_no_dilution',
        'arch_lindy_growth',
        'arch_quiet_compounder',
        'arch_buyback_compounder',
        'arch_owner_operator',
        'arch_qarp',
        'arch_reinvest_inflect',
        'arch_double_inflect',
        'arch_cash_quality',
        'arch_large_cap_quality',
        'arch_midcap_garp',
        'arch_capital_light_pivot',
        'arch_capital_returner',
        'arch_balance_sheet_return',
        'arch_financials_value',
        'arch_net_cash_returner',
        'arch_sustainable_scaler',
        'arch_oneil_canslim',
        'arch_weinstein_stage2',
        'arch_kullamagie_breakout',
        'arch_cundill_deep_value',
        'arch_biotech_deep_value',
        'arch_low_sbc_quality',
        'arch_tax_efficient',
        'arch_strong_coverage',
        'arch_diversified_segments',
        'arch_concentrated_segments',
        'arch_geographic_global',
        'arch_fastest_segment',
        'arch_bab_low_beta',
        'arch_bab_becoming',
        'arch_bab_multibagger',
        'arch_lynch_pegy',
        'arch_lynch_evgy',
        'arch_wolf_trifecta',
        'arch_wolf_turnaround',
        'arch_wolf_value_catalyst',
        'arch_wolf_emerging',
        'arch_wolf_seal',
        'arch_liger_asset_backed',
        'arch_liger_lagging_inflect',
        'arch_wolf_compounder',
        'arch_liger_neglected_survivor',
        'arch_oak_resource_leverage',
        'arch_oak_deleveraging',
        'arch_oak_deep_value',
        'arch_oak_nav_discount',
        'arch_oak_asset_floor',
        'arch_crisis_asset_backed_recovery',
        'arch_cluseau_realizable_book',
        'arch_cluseau_buyback_accel',
        'arch_institutional_accumulation',
        'arch_hidden_assets',
        'arch_overdepreciated_assets',
        'arch_understated_earnings',
        'arch_expensed_growth_value',
        'arch_cash_adjusted_pe',
        'arch_owner_earnings_power',
        'arch_forensic_payout_confirmed',
        'arch_retained_earnings_discount',
        'arch_customer_float',
        'arch_capex_famine_harvest',
        'arch_dividend_verified_value',
        'arch_tax_verified_earnings',
        'arch_cannibal_at_discount',
        'arch_self_funded_returner',
        'arch_book_compounder_discount',
        'arch_lifo_hidden_reserve',
        'arch_pension_overfunded',
        'arch_dta_reversal',
        'arch_xr_neg_ev_growth',
        'arch_xr_triple_floor',
        'arch_xr_floor_inflection',
        'arch_xr_quality_crisis',
        'arch_xr_forensic_floor_growth',
        'arch_xr_forensic_multiple_gap',
        'arch_xr_harvest_distribution',
        'arch_xr_paydown_yield',
        'arch_xr_audited_streak_unrerated',
        'arch_xr_clean_net_net',
        'arch_xr_compounding_deployer',
        'arch_xr_float_compounding',
        'arch_xr_bigbath_rebound',
        'arch_xr_depreciation_cliff',
        'arch_xr_wc_normalization',
        'arch_xr_amortization_mask',
        'arch_xr_cannibal_below_cash',
        'arch_xr_double_trough',
        'arch_xr_forced_seller',
        'arch_xr_leverage_detonation',
        'arch_xr_confluence',
        'arch_xr_baron_compounder',
        'arch_xr_insider_capitulation',
        'arch_xr_reusable_assembler',
        'arch_xr_asset_owner_catalyst',
        'arch_xr_pre_scale_margin',
        'arch_xr_latent_inflection_floor',
        'arch_xr_latent_bath_floor',
        'arch_xr_cyclical_trough',
        'arch_xr_nol_shield',
        'arch_xr_growth_capex_masked',
        'arch_xr_look_through_value',
        'arch_xr_cannibal_below_tbook',
        'arch_xr_oneoff_loss_mask',
        'arch_xr_monetization_trifecta',
        'arch_xr_contracted_backlog',
        'arch_xr_hidden_segment_compounder',
        'arch_xr_segment_justifies_whole',
        'arch_xr_margin_mixshift',
        'arch_xr_gross_margin_lead',
        'arch_xr_gaap_profit_crossover',
        'arch_xr_deferred_revenue_lead',
        'arch_xr_cash_tax_advantage',
        'arch_xr_owned_realestate_value',
        'arch_xr_discops_mask',
        'arch_xr_verified_deleveraging',
        'arch_xr_cash_leads_book',
        'arch_coiled_base',
        'arch_base_ignition',
        'arch_coiled_fallen_angel',
        'arch_ignition_fallen_angel',
        'arch_mb_fallen_deep_value',
        'arch_mb_fallen_value_turn',
        'arch_mb_fallen_value_accel',
        'arch_mb_fallen_stressed',
        'arch_mb_fallen_insider',
        'arch_mb_fallen_trough',
        'arch_mb_fallen_below_cycle',
        'arch_mb_inflecting_operator',
        'arch_mb_quiet_turn',
        'arch_mb_left_for_dead_value',
        'arch_mb_fallen_ignored_believers',
        'arch_mb_smart_money_wreckage',
        'arch_mb_grew_into_valuation_turning',
        'arch_mb_tree_recipe',
        'arch_mb_tree_recipe_10x',
        'arch_mb_sequence_preignition',
        'arch_mb_conviction_confluence',
        'arch_mb_left_for_dead_insider',
        'arch_mb_asset_trough_informed',
        'arch_mb_preprofit_beats_rewarded',
        'arch_mb_preprofit_freefall_informed',
        'arch_mb_biotech_financed_hiring',
        'arch_mb_wave_neglected_value_accel',
        'arch_mb_leader_in_wave',
        'arch_mb_improving_unturned_sellside',
        'arch_mb_peer_worst_cheapest',
        'arch_mb_compounder_insiders_at_high',
        'arch_mb_hiring_beating_uncovered',
        'arch_mb_cheap_growth_targets_up',
        'arch_mb_model_top',
        'arch_mb_model_confluence',
        'arch_mb_model_uncovered_not_fallen',
        'arch_mb_model_region_rule',
        'arch_mb_industry_trough_cheapest',
        'arch_mb_reinvesting_at_trough',
        'arch_mb_stressed_not_diluting',
        'arch_mb_growth_past_capex_peak',
        'arch_mb_fallen_less_than_industry_financed',
        'arch_mb_lean_rd_stocking_up',
        'arch_mb_divergence_cheapest_pb',
        'arch_mb_fallen_operator_industry_low',
        'arch_mb_quality_at_distress',
        'arch_mb_rd_leader_on_volume',
        'arch_mb_cheap_vs_sector_recovering',
        'arch_xr_peer_margin_gap',
        'arch_xr_investment_remark',
        'arch_xr_stake_fv_gap',
        'arch_xr_lookthrough_earner',
        'arch_xr_value_unlock',
        'arch_oak_order_conversion',
        'arch_weschler_levered_equity',
        'arch_cheap_sales_scaler',
        'arch_exceptional_evsg',
        'arch_negative_ev_value',
        'arch_growth_algo',
        'arch_asleep_at_wheel',
        'arch_asleep_unrerated',
        'arch_templeton_pessimism',
        'arch_asymmetric_assembly',
        'arch_levered_inflection',
        'arch_insider_conviction',
        'arch_tenbagger_path',
        'arch_tenbagger_credible',
        'arch_evsales_derating',
        'arch_lynch_reward',
        'arch_analyst_awakening',
        'arch_analyst_rerating_confirmed',
        'arch_bottleneck',
        'arch_flyover',
        'arch_spinoff_value',
        'arch_spinoff_quality',
        'arch_spinoff_asset',
        'arch_greenblatt_magic',
        'arch_post_reorg',
        'arch_special_situation',
        'arch_nol_shell',
    ]
    pretty = {
        'arch_narrative_lag': 'NarrativeLag',
        'arch_derate_through_growth': 'DerateThroughGrowth',
        'arch_fixed_cost_demand_shock': 'FixedCost+DemandShock',
        'arch_discounted_vehicle': 'DiscountedVehicle',
        'arch_capital_discipline': 'CapitalDiscipline',
        'arch_regime_cyclical': 'RegimeCyclical',
        'arch_dead_option': 'DeadOption',
        'arch_kpi_threshold': 'KPIThreshold',
        'arch_blindspot': 'BlindSpot',
        'arch_micro_activist_inflect': 'MicroActivistInflect',
        'arch_durable_reinvestment': 'DurableReinvest',
        'arch_large_cap_quality': 'LargeCapQuality',
        'arch_midcap_garp': 'MidCapGARP',
        'arch_cash_reinvest': 'CashReinvest',
        'arch_roic_inflect': 'ROICInflect',
        'arch_cheap_per_roiic': 'CheapPerROIIC',
        'arch_tangible_value': 'TangibleValue',
        'arch_lindy_margin': 'LindyMargin',
        'arch_lindy_fcf': 'LindyFCF',
        'arch_no_dilution': 'NoDilution',
        'arch_lindy_growth': 'LindyGrowth',
        'arch_quiet_compounder': 'QuietCompounder',
        'arch_buyback_compounder': 'BuybackCompounder',
        'arch_owner_operator': 'OwnerOperator',
        'arch_qarp': 'QARP',
        'arch_reinvest_inflect': 'ReinvestInflect',
        'arch_double_inflect': 'DoubleInflect',
        'arch_cash_quality': 'CashQuality',
        'arch_capital_light_pivot': 'CapitalLightPivot',
        'arch_capital_returner': 'CapitalReturner',
        'arch_balance_sheet_return': 'BalanceSheetReturn',
        'arch_financials_value': 'FinancialsValue',
        'arch_net_cash_returner': 'NetCashReturner',
        'arch_sustainable_scaler': 'SustainableScaler',
        'arch_oneil_canslim': 'ONeil-CANSLIM',
        'arch_weinstein_stage2': 'Weinstein-Stage2',
        'arch_kullamagie_breakout': 'Kullamagi-Breakout',
        'arch_cundill_deep_value': 'Cundill-DeepValue',
        'arch_biotech_deep_value': 'Biotech-DeepValue',
        'arch_low_sbc_quality': 'LowSBCQuality',
        'arch_tax_efficient': 'TaxEfficient',
        'arch_strong_coverage': 'StrongCoverage',
        'arch_diversified_segments': 'DiversifiedSegments',
        'arch_concentrated_segments': 'ConcentratedSegments',
        'arch_geographic_global': 'GeographicGlobal',
        'arch_fastest_segment': 'FastestSegment',
        'arch_bab_low_beta': 'BAB-LowBetaQuality',
        'arch_bab_becoming': 'BAB-Becoming',
        'arch_bab_multibagger': 'BAB-Multibagger',
        'arch_lynch_pegy': 'LynchPEGY',
        'arch_lynch_evgy': 'LynchEV-GY',
        'arch_wolf_trifecta': 'WolfTrifecta',
        'arch_wolf_turnaround': 'WolfTurnaround',
        'arch_wolf_value_catalyst': 'WolfValueCatalyst',
        'arch_wolf_emerging': 'WolfEmergingSector',
        'arch_wolf_seal': 'WolfSeal',
        'arch_liger_asset_backed': 'LigerAssetBacked',
        'arch_liger_lagging_inflect': 'LigerLaggingInflect',
        'arch_wolf_compounder': 'WolfCompounder',
        'arch_liger_neglected_survivor': 'LigerNeglectedSurvivor',
        'arch_oak_resource_leverage': 'OakResourceLeverage',
        'arch_oak_deleveraging': 'OakDeleveraging',
        'arch_oak_deep_value': 'OakDeepValue',
        'arch_oak_nav_discount': 'OakNAVDiscount',
        'arch_oak_asset_floor': 'OakAssetFloor',
        'arch_crisis_asset_backed_recovery': 'Cundill-CrisisRecovery',
        'arch_cluseau_realizable_book': 'Cluseau-RealizableBook',
        'arch_cluseau_buyback_accel': 'Cluseau-BuybackAccel',
        'arch_institutional_accumulation': 'Inst-Accumulation',
        'arch_hidden_assets': 'HiddenAssets-Overcap',
        'arch_overdepreciated_assets': 'Forensic-OverDepreciated',
        'arch_understated_earnings': 'Forensic-UnderstatedE',
        'arch_expensed_growth_value': 'Forensic-ExpensedGrowth',
        'arch_cash_adjusted_pe': 'CashAdjPE-NegOrCheap',
        'arch_owner_earnings_power': 'Forensic-OwnerEarnings',
        'arch_forensic_payout_confirmed': 'Forensic-PayoutConfirmed',
        'arch_retained_earnings_discount': 'Forensic-RetainedEarnings',
        'arch_customer_float': 'Forensic-CustomerFloat',
        'arch_capex_famine_harvest': 'Forensic-CapexFamine',
        'arch_dividend_verified_value': 'Forensic-DividendProof',
        'arch_tax_verified_earnings': 'Forensic-TaxProof',
        'arch_cannibal_at_discount': 'Forensic-CannibalDiscount',
        'arch_self_funded_returner': 'Forensic-SelfFunded',
        'arch_book_compounder_discount': 'Forensic-BookCompounder',
        'arch_lifo_hidden_reserve': 'Forensic-LIFOReserve',
        'arch_pension_overfunded': 'Forensic-PensionSurplus',
        'arch_dta_reversal': 'Forensic-DTAReversal',
        'arch_xr_neg_ev_growth': 'XR-NegEVGrowth',
        'arch_xr_triple_floor': 'XR-TripleFloor',
        'arch_xr_floor_inflection': 'XR-FloorInflection',
        'arch_xr_quality_crisis': 'XR-QualityAtCrisis',
        'arch_xr_forensic_floor_growth': 'XR-ForensicFloorGrowth',
        'arch_xr_forensic_multiple_gap': 'XR-ForensicMultipleGap',
        'arch_xr_harvest_distribution': 'XR-HarvestDistribution',
        'arch_xr_paydown_yield': 'XR-PaydownYield',
        'arch_oak_order_conversion': 'OakOrderConversion',
        'arch_weschler_levered_equity': 'WeschlerLeveredEquity',
        'arch_cheap_sales_scaler': 'CheapSalesScaler',
        'arch_exceptional_evsg': 'ExceptionalEVSG',
        'arch_negative_ev_value': 'NegativeEV-Value',
        'arch_growth_algo': 'GrowthAlgo-Flywheel',
        'arch_asleep_at_wheel': 'AsleepAtWheel-Beats',
        'arch_asleep_unrerated': 'AsleepUnrerated-BeatsNoRerate',
        'arch_xr_audited_streak_unrerated': 'XR-AuditedStreakUnrerated',
        'arch_xr_clean_net_net': 'XR-CleanNetNet',
        'arch_xr_compounding_deployer': 'XR-CompoundingDeployer',
        'arch_xr_float_compounding': 'XR-FloatCompounding',
        'arch_xr_bigbath_rebound': 'XR-BigBathRebound',
        'arch_xr_depreciation_cliff': 'XR-DepreciationCliff',
        'arch_xr_wc_normalization': 'XR-WCNormalization',
        'arch_xr_amortization_mask': 'XR-AmortizationMask',
        'arch_xr_cannibal_below_cash': 'XR-CannibalBelowCash',
        'arch_xr_double_trough': 'XR-DoubleTrough',
        'arch_xr_forced_seller': 'XR-ForcedSeller',
        'arch_xr_leverage_detonation': 'XR-LeverageDetonation',
        'arch_xr_confluence': 'XR-Confluence',
        'arch_xr_baron_compounder': 'XR-BaronCompounder',
        'arch_xr_insider_capitulation': 'XR-InsiderCapitulation',
        'arch_xr_reusable_assembler': 'XR-ReusableAssembler',
        'arch_xr_asset_owner_catalyst': 'XR-AssetOwnerCatalyst',
        'arch_xr_pre_scale_margin': 'XR-PreScaleMargin',
        'arch_xr_latent_inflection_floor': 'XR-LatentInflectionFloor',
        'arch_xr_latent_bath_floor': 'XR-LatentBathFloor',
        'arch_xr_cyclical_trough': 'XR-CyclicalTrough',
        'arch_xr_nol_shield': 'XR-NOLShield',
        'arch_xr_growth_capex_masked': 'XR-GrowthCapexMasked',
        'arch_xr_look_through_value': 'XR-LookThroughValue',
        'arch_xr_cannibal_below_tbook': 'XR-CannibalBelowTangibleBook',
        'arch_xr_oneoff_loss_mask': 'XR-OneOffLossMask',
        'arch_xr_monetization_trifecta': 'XR-MonetizationTrifecta',
        'arch_xr_contracted_backlog': 'XR-ContractedBacklog',
        'arch_xr_hidden_segment_compounder': 'XR-HiddenSegmentCompounder',
        'arch_xr_segment_justifies_whole': 'XR-SegmentJustifiesWhole',
        'arch_xr_margin_mixshift': 'XR-MarginMixShift',
        'arch_xr_gross_margin_lead': 'XR-GrossMarginLead',
        'arch_xr_gaap_profit_crossover': 'XR-GAAPProfitCrossover',
        'arch_xr_deferred_revenue_lead': 'XR-DeferredRevenueLead',
        'arch_xr_cash_tax_advantage': 'XR-CashTaxAdvantage',
        'arch_xr_owned_realestate_value': 'XR-OwnedRealEstateValue',
        'arch_xr_discops_mask': 'XR-DiscOpsMask',
        'arch_xr_verified_deleveraging': 'XR-VerifiedDeleveraging',
        'arch_coiled_base': 'CoiledBase',
        'arch_base_ignition': 'BaseIgnition',
        'arch_coiled_fallen_angel': 'CoiledFallenAngel',
        'arch_ignition_fallen_angel': 'IgnitionFallenAngel',
        'arch_mb_fallen_deep_value': 'MB-FallenDeepValue',
        'arch_mb_fallen_value_turn': 'MB-FallenValueTurn',
        'arch_mb_fallen_value_accel': 'MB-FallenValueAccel',
        'arch_mb_fallen_stressed': 'MB-FallenStressed',
        'arch_mb_fallen_insider': 'MB-FallenInsider',
        'arch_mb_fallen_trough': 'MB-FallenTrough',
        'arch_mb_fallen_below_cycle': 'MB-FallenBelowCycle',
        'arch_mb_inflecting_operator': 'MB-InflectingOperator',
        'arch_mb_quiet_turn': 'MB-QuietTurnWeakTape',
        'arch_mb_left_for_dead_value': 'MB-LeftForDeadValue',
        'arch_mb_fallen_ignored_believers': 'MB-FallenIgnoredBelievers',
        'arch_mb_smart_money_wreckage': 'MB-SmartMoneyWreckage',
        'arch_mb_grew_into_valuation_turning': 'MB-GrewIntoValuationTurning',
        'arch_mb_tree_recipe': 'MB-TreeRecipe',
        'arch_mb_tree_recipe_10x': 'MB-TreeRecipe10x',
        'arch_mb_sequence_preignition': 'MB-SequencePreIgnition',
        'arch_mb_conviction_confluence': 'MB-ConvictionConfluence',
        'arch_mb_left_for_dead_insider': 'MB-LeftForDeadInsider',
        'arch_mb_asset_trough_informed': 'MB-AssetTroughInformed',
        'arch_mb_preprofit_beats_rewarded': 'MB-PreProfitBeatsRewarded',
        'arch_mb_preprofit_freefall_informed': 'MB-PreProfitFreefallInformed',
        'arch_mb_biotech_financed_hiring': 'MB-BiotechFinancedHiring',
        'arch_mb_wave_neglected_value_accel': 'MB-WaveNeglectedValueAccel',
        'arch_mb_leader_in_wave': 'MB-LeaderInWave',
        'arch_mb_improving_unturned_sellside': 'MB-ImprovingUnturnedSellSide',
        'arch_mb_peer_worst_cheapest': 'MB-PeerWorstCheapest',
        'arch_mb_compounder_insiders_at_high': 'MB-CompounderInsidersAtHigh',
        'arch_mb_hiring_beating_uncovered': 'MB-HiringBeatingUncovered',
        'arch_mb_cheap_growth_targets_up': 'MB-CheapGrowthTargetsUp',
        'arch_mb_model_top': 'MB-ModelTop5',
        'arch_mb_model_confluence': 'MB-ModelConfluence',
        'arch_mb_model_uncovered_not_fallen': 'MB-ModelUncoveredNotFallen',
        'arch_mb_model_region_rule': 'MB-ModelRegionRule',
        'arch_cheap_net_cash_steady_earner': 'CheapNetCashSteadyEarner',
        'arch_psix': 'PSIX',
        'arch_gayner_four_lens': 'Gayner-FourLens',
        'arch_gayner_pay_up_quality': 'Gayner-PayUpQuality',
        'arch_gayner_missed_it': 'Gayner-MissedIt',
        'arch_gayner_frugal_operator': 'Gayner-FrugalOperator',
        'arch_gayner_wiggle_not_obsolete': 'Gayner-WiggleNotObsolete',
        'arch_cannabis_operator': 'CannabisOperator',
        'arch_senior_security_value': 'SeniorSecurityValue',
        'arch_mb_industry_trough_cheapest': 'MB-IndustryTroughCheapest',
        'arch_mb_reinvesting_at_trough': 'MB-ReinvestingAtTrough',
        'arch_mb_stressed_not_diluting': 'MB-StressedNotDiluting',
        'arch_mb_growth_past_capex_peak': 'MB-GrowthPastCapexPeak',
        'arch_mb_fallen_less_than_industry_financed': 'MB-FallenLessThanIndustryFinanced',
        'arch_mb_lean_rd_stocking_up': 'MB-LeanRDStockingUp',
        'arch_mb_divergence_cheapest_pb': 'MB-DivergenceCheapestPB',
        'arch_mb_fallen_operator_industry_low': 'MB-FallenOperatorIndustryLow',
        'arch_mb_quality_at_distress': 'MB-QualityAtDistress',
        'arch_mb_rd_leader_on_volume': 'MB-RDLeaderOnVolume',
        'arch_mb_cheap_vs_sector_recovering': 'MB-CheapVsSectorRecovering',
        'arch_xr_cash_leads_book': 'XR-CashLeadsBook',
        'arch_xr_peer_margin_gap': 'XR-PeerMarginGap',
        'arch_xr_investment_remark': 'XR-InvestmentRemark',
        'arch_xr_stake_fv_gap': 'XR-StakeFVGap',
        'arch_xr_lookthrough_earner': 'XR-LookThroughEarner',
        'arch_xr_value_unlock': 'XR-ValueUnlock',
        'arch_templeton_pessimism': 'Templeton-MaxPessimism',
        'arch_asymmetric_assembly': 'AsymmetricAssembly-PSIX',
        'arch_levered_inflection': 'LeveredInflectionStub',
        'arch_insider_conviction': 'InsiderConviction-SEC',
        'arch_tenbagger_path': 'TenBaggerPath',
        'arch_tenbagger_credible': 'TenBaggerPath-Credible',
        'arch_evsales_derating': 'EVSalesDerating-UnpricedGrowth',
        'arch_lynch_reward': 'LynchReward-YearsInOne',
        'arch_analyst_awakening': 'AnalystAwakening-52wHigh',
        'arch_analyst_rerating_confirmed': 'ReratingConfirmed-52wHigh',
        'arch_bottleneck': 'Bottleneck-Chokepoint',
        'arch_flyover': 'Flyover-QuietQuality',
        'arch_spinoff_value': 'SpinOff-Value-Form10',
        'arch_spinoff_quality': 'SpinOff-Quality-Franchise',
        'arch_spinoff_asset': 'SpinOff-Asset-Backing',
        'arch_greenblatt_magic': 'Greenblatt-MagicFormula',
        'arch_post_reorg': 'PostReorg-FreshStart',
        'arch_special_situation': 'SpecialSit-Catalyst',
        'arch_nol_shell': 'NOL-Shell',
    }
    # ===== NON-COMMON SECURITY SCRUB (audit re-check 2026-09-08) =====
    # Preferred shares, warrants, units and rights are NOT common equity —
    # their P/E, book value, capital-return yield etc. belong to the parent,
    # so they were firing equity value/quality/capital screens (467 pref + 77
    # warrant/unit; e.g. BAC preferreds in Financials-Value). Zero EVERY
    # archetype flag for them at the source (the books' display-dedup already
    # hid them, but this makes the flags and counts honest).
    # ===== SYSTEMATIC BIOTECH CLASSIFIER (defined before the scrubs) =====
    # is_drug_developer: Biotech/Pharma/drug-mfr, or a health-sector drug name.
    # is_clinical_biotech: a drug developer WITHOUT sustained profitability
    # (a large self-funding pharma or a >=4yr positive-FCF/ROIC streak is
    # "commercial" and retained). Clinical names are scrubbed from every
    # FUNDAMENTAL archetype below EXCEPT price-action/catalyst ones and their
    # own dedicated deep-value screen.
    _ind_b = (df['industry'].fillna('').astype(str).str.lower()
              if 'industry' in df.columns else pd.Series('', index=df.index))
    _sec_b = (df['sector'].fillna('').astype(str).str.lower()
              if 'sector' in df.columns else pd.Series('', index=df.index))
    _nm_b = (df['name'].fillna('').astype(str).str.lower()
             if 'name' in df.columns else pd.Series('', index=df.index))
    _is_drug_dev = (
        _ind_b.str.contains('biotechnolog') | _ind_b.str.contains('pharmaceutic')
        | _ind_b.str.contains('drug manufactur')
        | (_sec_b.str.contains('health')
           & _nm_b.str.contains('therapeut|biopharm|biosci|pharma|oncolog|genomic|genetic'))
    ).fillna(False)
    # USD twins (gate audit #1): the $500M commercial floor against RAW
    # revenue_ttm let a KRW/JPY clinical-stage name clear "500e6" with a
    # few million dollars of revenue and dodge the scrub entirely.
    _revb = pd.to_numeric(df.get('revenue_ttm_usd'), errors='coerce')
    _fx_bt = (pd.to_numeric(df.get('market_cap_usd'), errors='coerce')
              / pd.to_numeric(df.get('market_cap'), errors='coerce'))
    _fcfb = pd.to_numeric(df.get('fcf_ttm'), errors='coerce') * _fx_bt
    _embg = pd.to_numeric(df.get('ebitda_margin'), errors='coerce')
    _nyfcf = pd.to_numeric(df.get('n_yrs_positive_fcf'), errors='coerce')
    _nyroic = pd.to_numeric(df.get('n_yrs_positive_roic'), errors='coerce')
    _commercial = ((_nyfcf >= 4) | (_nyroic >= 4)
                   | ((_revb >= 500e6) & (_fcfb > 0) & (_embg > 0) & (_embg < 0.6)))
    # (user 2026-10-02) cannabis operators are their own population, never
    # clinical biotech (the scrub zeroed 29 of wolf_emerging's 37 names)
    _is_drug_dev = _is_drug_dev & ~(df['is_cannabis'] == 1)
    _is_clinical_biotech = (_is_drug_dev & ~_commercial.fillna(False))
    df['is_drug_developer'] = _is_drug_dev.astype(int)
    df['is_clinical_biotech'] = _is_clinical_biotech.astype(int)

    # ============ SEGMENT MULTIBAGGERS (MULTIBAGGER_SEGMENTS.md) ============
    # The same point-in-time panel split into the populations whose value is
    # measured differently. Each population's own mining, not the pooled one.
    _seg_asset = ((sector.isin(['Energy', 'Materials', 'Real Estate', 'Utilities'])
                   | _ind_b.str.contains(r'shipping|marine|tanker|lessor|leasing|holding|reit|real estate|mining'
                                         r'|oil|gas|coal|steel|aluminum|gold|silver|uranium|timber|farm|metals',
                                         regex=True)) & ~_is_drug_dev)
    _seg_preprofit = (((_ncol('op_margin') < 0) | (_ncol('fcf_margin') < 0)).fillna(False)
                      & ~_is_drug_dev & ~_seg_asset)
    _informed = (_ins_2q | _13d_recent | _mb_insider)
    # ASSET TROUGH WITH AN INFORMED BUYER: in asset businesses the winners were
    # NOT the ones deleveraging or fixing margins — they were the ones whose
    # sales per share had run far ahead of the price (gap_sales the top
    # feature of the trough cluster), sitting on a fresh low with insiders /
    # a new 13D holder arriving (the only conviction measure that separated
    # winners from lookalikes, +0.094; the GMM's 2.2x group: activist 38%,
    # insiders 12%, weeks since the 5y low = 1). Leverage present is part of
    # the lever (deleveraging was negative), so it is a lens, not a veto.
    _nl_best = pd.concat([_ncol('nl_sales_1y'), _ncol('nl_sales_2y'), _ncol('nl_sales_3y')], axis=1).max(axis=1)
    _nl_sales_lead = (_crank(_nl_best.where(_seg_asset)) >= 0.60).fillna(False)   # top 40% of the asset segment
    _informed_g = _informed | _corp_conviction | _inst_arrival
    df['arch_mb_asset_trough_informed'] = (_mb_base & _seg_asset & _mb_fallen & _nl_sales_lead & _informed_g).astype(int)
    # PRE-PROFIT, BEATS REWARDED: the 10x family of the pre-profit population
    # (lift 30-35x on a 10x within 5 years, ~45-50% of such month-ends went
    # 10x: CELH 2019, ASPN 2018, PERI, LSCC 2017, POLA). The mined condition
    # is `ignored_beats_2y LOW`: a still-loss-making operator that beats and
    # whose beats the market REWARDS (no ignored beat in two years, >= 3
    # beats in eight quarters) — the tape is listening.
    # Blow-up 30-50%: a lottery-shaped archetype by construction.
    df['arch_mb_preprofit_beats_rewarded'] = (
        _mb_base & _seg_preprofit & (_ncol('evt_ignored_beats_2y') == 0).fillna(False)
        & (_ncol('evt_beats_8q') >= 3).fillna(False)).astype(int)
    # PRE-PROFIT IN FREEFALL WITH INFORMED BUYERS: the population's best
    # cluster (lift 1.5x, 10% of its multibaggers; GME 2019, ASPN, EAT 2020,
    # BGFV, LSCC, CAR 2019): fallen 88%, 8 weeks off the 5-year low, P/S
    # 0.30, insiders 30% (5.8x), activist 45% (5.1x), headcount SHRINKING
    # (productivity gain 8.8x). Blow-up 28%.
    df['arch_mb_preprofit_freefall_informed'] = (_mb_base & _seg_preprofit & _mb_fallen & _informed_g).astype(int)
    # DRUG DEVELOPER, FINANCED AND HIRING INTO THE FALL: the drug developers'
    # highest-lift cluster (3.65x, blow-up 35%; AXSM 2017, EXEL 2014, CORT
    # 2013, ITCI 2019): headcount growing in every member, share count +15%,
    # insiders 36% (13x), activist 59%, price 22% of the 5y high, cash on
    # hand. The 10x patterns add DOWNGRADES as a positive condition.
    _bio_financed = ((_ncol('fmp_st_shares_growth_3y') >= 0.10)
                     | (_ncol('fq_financing_cf') > 0)).fillna(False)
    _burn_q = (-_ncol('fq_cfo')).where(_ncol('fq_cfo') < 0)
    _runway_years = (_ncol('fq_cash_sti') / (_burn_q * 4)).where(_burn_q > 0)
    _bio_runway = ((_runway_years >= 1.0) | (_ncol('fq_cfo') >= 0) | (_runway_years.isna() & (_ncol('net_cash_pct_mcap') > 0.10))).fillna(False)
    _bio_committed = ((_ncol('usf_emp_g1') >= 0.10).fillna(False) | _informed_g
                      | (_ncol('usf_emp_g1').isna() & (_ncol('fmp_rd_to_revenue') > 0)
                         & ((_ncol('fq_rev_growth') >= 0.10) | (_ncol('fg_rd_g1') > 0))).fillna(False))   # (audit 4) R&D spend growing (financial-growth, global) reaches the pre-revenue clinical names
    df['arch_mb_biotech_financed_hiring'] = (
        is_operating & (mcap >= 10e6) & _is_drug_dev & (_hi260 <= 0.50).fillna(False) & _bio_financed
        & _bio_committed & _bio_runway).astype(int)
    _SPIRITED += ['mb_asset_trough_informed', 'mb_preprofit_beats_rewarded', 'mb_preprofit_freefall_informed',
                  'mb_biotech_financed_hiring']

    # ============ USING THE MODEL (MULTIBAGGER_MODEL.md) ============
    # Out of sample on USD labels the model's top decile of each market held
    # 23% of the multibagger month-ends (the 33 rule archetypes 50%; united
    # 57%); its lift is 3.1x / 2.6x inside the uncovered population and on
    # NOT-fallen names, only 1.5x on fallen ones (the rules own that ground).
    _rule_mb = [c for c in df.columns if c.startswith('arch_mb_') and c != 'arch_mb_model_top']
    df['mb_rule_count'] = df[_rule_mb].sum(axis=1)
    _model_rank = df['mb_model_rank_base']
    # 1. CONFLUENCE: a rule archetype member the model also ranks in the top
    #    decile of its market — the archetype names the situation, the model
    #    says the whole feature profile looks like the ones that tripled.
    df['arch_mb_model_confluence'] = ((df['mb_rule_count'] >= 1) & (_model_rank >= 0.90).fillna(False)).astype(int)
    # 2. THE MODEL'S OWN GROUND: top 5% of its market, NOT fallen (>= 60% of
    #    the 5-year high) and in no rule archetype — the screen for what the
    #    boxes cannot hold (lift 3.1x / 2.6x there; blow-up 22-30%, denoted).
    df['arch_mb_model_uncovered_not_fallen'] = (
        _mb_base & (_model_rank >= 0.95).fillna(False) & (_hi260 >= 0.60).fillna(False)
        & (df['mb_rule_count'] == 0)).astype(int)
    # 3. THE REGION RULE: the model's top decile rendered as a tree
    #    (MULTIBAGGER_MODEL.md §3); its two best leaves, in words: fell far
    #    more than its own market (bottom 12% of the distance-from-high-
    #    minus-market rank), very volatile (top 28%), and either tiny (bottom
    #    13% by size) or long in drawdown (> 73% of the last five years).
    #    Out of sample: leaf lifts 3.9x / 3.1x, blow-up 30-38% — a readable,
    #    lottery-shaped rule the boxes did not have.
    df['arch_mb_model_region_rule'] = (
        _mb_base & (_crank(_ncol('vs_mkt_dist_hi260')) <= 0.12).fillna(False)
        & (_crank(_ncol('ts_vol_1y')) >= 0.72).fillna(False)
        & ((_crank(mcap) <= 0.13).fillna(False) | (_crank(_ncol('ts_dd_time_share_260')) >= 0.73).fillna(False))).astype(int)
    _SPIRITED += ['mb_model_confluence', 'mb_model_uncovered_not_fallen', 'mb_model_region_rule']

    # ---------- Biotech Deep Value (below-cash special situation) ----------
    # A drug developer trading at/below its NET CASH: the market pays you to
    # own the cash and hands you a free option on the pipeline. Downside is
    # the balance sheet, not the binary trial. Requires a real cash cushion
    # AND enough runway not to face imminent dilution. This is the home for
    # the clinical biotechs the systematic filter removes from every other
    # fundamental value screen.
    _bdv_ncash = _num('net_cash_pct_mcap'); _bdv_cashev = _num('cash_gt_ev_flag')
    _bdv_ncav = _num('ncav_pct_mcap'); _bdv_cashpct = _num('cash_pct_mcap')
    # Cash runway (years) = net cash / annual burn; ample (99) when not
    # burning, NaN when cash or FCF data is missing.
    _bdv_cash_abs = _bdv_ncash.clip(lower=0) * mcap            # net cash (USD; better coverage than gross)
    _bdv_burn = -_num('fcf_ttm_usd')                           # (non-XR review) USD burn vs USD cash
    _bdv_runway = (_bdv_cash_abs / _bdv_burn.where(_bdv_burn > 0)).where(
        _bdv_burn > 0, 99.0).where(_bdv_burn.notna())
    # (endpoint matrix A.6, PROXY) runway measured within ONE statement set:
    # latest cash + short-term investments over the TTM free-cash burn, both
    # in the filer's reporting currency (no USD market-cap x net-cash% x USD
    # FCF chain). Primary where the quarterly panel has both; else the above.
    # Validity: cash must be positive, and the quarterly FCF must agree in
    # scale with the master's (converted with the validated currency bridge,
    # within 3x either way) — a units error in either series (PBSV: fq FCF
    # 25x its market cap) must not read as a 0.03-year runway.
    _fq_cash_b = _num('fq_cash_sti').where(_q_ok & (_num('fq_cash_sti') > 0))
    _fcf_scale = _num('fcf_ttm') / (_num('fq_fcf') * df['fq_fx_to_master'])
    _fq_fcf_b = _num('fq_fcf').where(_q_ok & (_fcf_scale.isna() | _fcf_scale.between(1 / 3, 3)))
    _bdv_runway_fq = (_fq_cash_b / (-_fq_fcf_b).where(_fq_fcf_b < 0)).where(
        _fq_fcf_b < 0, 99.0).where(_fq_cash_b.notna() & _fq_fcf_b.notna())
    _bdv_runway = _bdv_runway_fq.fillna(_bdv_runway)
    df['biotech_cash_runway_yrs'] = _bdv_runway.where(_bdv_runway >= 0).clip(upper=99).round(2)
    # The below-cash NET-CASH cushion is the margin of safety. Per the
    # docstring ("enough runway not to face imminent dilution"), require a
    # minimum runway using the ALREADY-COMPUTED column: non-burners clip to 99
    # (unaffected); only names being consumed faster than ~1x net cash/yr are
    # dropped (MBIO burning >100% mcap/yr, CDIO fcf_yield -1.34). Also drop
    # names ALREADY diluting massively (BIVI shares +227% YoY) — the balance
    # sheet is being handed to new holders, not to us.
    _bdv_not_gushing_dilution = ~(_num('shares_yoy') > 0.50)
    df['arch_biotech_deep_value'] = (
        _is_clinical_biotech                   # (tail) CLINICAL developers only — a solidly-profitable major (Otsuka/Ono/Shionogi) below "cash" is a negative-EV artifact, not a binary-option play
        & (mcap >= 2e6)
        # (tail) clamp the net-cash leg to a sane band — net_cash_pct is FX-
        # corruptible (Kalbe 2094x, Sundrug 6.8x); at/below cash is ~0.5-3x, not 2000x.
        & (((_bdv_ncash >= 0.5) & (_bdv_ncash <= 3.0)) | (_bdv_cashev > 0)
           | ((_bdv_ncav >= 0.8) & (_bdv_ncav <= 3.0)))
        & (mcap >= 10e6)                       # (audit 3) the sibling floors' investable scale
        # (audit 3) runway >= 2 years, or >= 1 year only where the raise is
        # already done (shares up <= 15%: financed, not about to dilute)
        & ((_bdv_runway >= 2.0) | ((_bdv_runway >= 1.0) & ~(_num('shares_yoy') > 0.15)))
        & _bdv_not_gushing_dilution
    ).fillna(False).astype(int)
    df['biotech_deep_value_score'] = ((
        0.35 * _ramp(_bdv_ncash, 0.5, 1.2)
        + 0.20 * (_bdv_cashev > 0).astype(float)
        + 0.20 * _ramp(_bdv_runway, 1.0, 4.0)
        + 0.15 * _ramp(_bdv_ncav, 0.8, 2.0)
        + 0.10 * (1.0 - _ramp(_num('shares_yoy'), 0.0, 0.20))
    ) * df['arch_biotech_deep_value']).round(3)

    # ---------- The Constraint: bottleneck / pricing-power chokepoint ----------
    # Master Reference domain I.B ("owns a bottleneck; a large system can't scale
    # without the small component") + the Akre AMT bottleneck-asset archetype. We
    # cannot screen "sole-source" (that is scuttlebutt), but the ECONOMIC
    # footprint of a chokepoint IS screenable: durable HIGH + non-eroding gross
    # margin (pricing power), high returns on capital (a toll road), and
    # CAPITAL-LIGHT economics (a chokepoint earns without heavy reinvestment).
    _bn_gm = _num('gross_margin'); _bn_gmd = _num('gross_margin_delta_yoy')
    _bn_capint = _num('capex_intensity')
    df['arch_bottleneck'] = (
        is_operating &
        _not_melting &
        (_num('revenue_ttm_usd') >= 5e6) &             # a real business, not a nano
        (_bn_gm >= 0.40) &                              # pricing power: fat gross margin
        ~((_ncol('tc_years') >= 5) & (_ncol('tc_min_gm') < 0.40)) &   # (audit 3) the WORST year of >= 5 on file also clears 40% (durable, not a one-year print)
        # ...not eroding (missing => pass). (endpoint matrix, EXC) a one-year
        # dip is not erosion when the WORST gross margin of >= 7 fiscal years
        # still clears 40% — the durable, non-eroding floor measured directly.
        (~(_bn_gmd < -0.03) | ((_ncol('tc_min_gm') >= 0.40) & (_ncol('tc_years') >= 7))) &
        (((s('roce', np.nan) >= 0.15) & ~_roce_oneoff_suspect)
         | (s('roic_lindy', np.nan) >= 0.15)) &  # toll-road returns (no uncorroborated one-off roce)
        (s('op_margin', np.nan) > 0.05) &               # genuinely profitable
        ~(_bn_capint > 0.10)                            # capital-light chokepoint (missing => pass)
    ).fillna(False).astype(int)
    _SPIRITED.append('bottleneck')                      # through-cycle minimum GM ranks the members

    # ---------- Flyover Stocks: high-quality, low-coverage, owner-controlled ----
    # Todd Wenning / quiet-compounder blueprint (Master Reference IV): durable
    # moat (ROIC>15%) + boring essential business + family/insider control +
    # strong FCF + LOW analyst coverage (<5, ideally 0). The low-coverage
    # discovery gap is DEFINITIONAL here — it is exactly what quiet_compounder and
    # owner_operator do not require, so this is the "undiscovered quality" lens.
    df['arch_flyover'] = (
        is_operating &
        ~(n_analysts_v >= 5) &                          # low / no coverage, < 5 (missing => undiscovered => pass)
        ~(_ncol('sent_n_analysts') > 2) &               # (audit 3) neglect OBSERVED where estimate coverage exists: <= 2 analysts
        (insider >= 0.20) &                             # family / insider control
        (((s('roce', np.nan) >= 0.15) & ~_roce_oneoff_suspect)
         | (s('roic_lindy', np.nan) >= 0.15)) &  # high ROIC (>15%) = the moat (no uncorroborated one-off roce)
        ((_num('fcf_ttm') > 0) | (s('n_yrs_positive_fcf', 0) >= 3)) &  # strong / durable FCF
        (s('op_margin', np.nan) > 0) &                  # profitable
        _not_melting                                    # (audit 4 / user rule) leverage (nde <= 2) is a weight, not a gate
    ).fillna(False).astype(int)
    # (tighten) same insider-band / revealed-alignment fix as owner_operator.
    # Exceptional: genuinely unwatched (observed <= 2 analysts) and FCF
    # positive in every fiscal year on file.
    _tier('flyover',
          insider.between(0.20, 0.60) | ((_ncol('insider_buy_flag') == 1) | (_ncol('buyback_yield') >= 0.01)),
          ~(_ncol('sent_n_analysts') > 2) & (_ncol('tc_fcf_pos') == _ncol('tc_fcf_years')),
          elite_metric=_ncol('roic_lindy'),
          measured=insider.notna() | _ncol('buyback_yield').notna())

    # ---------- Event-driven / Special-Situations sleeve (EDGAR, US filers) ----
    # The Special-Situations taxonomy (Master Reference III/VIII; Compendium
    # Part II). Each is a HARD, DATED corporate-action catalyst with a
    # structurally BOUNDED downside, paired — per the user's refinement — with
    # EXCELLENT VALUATION (a high EBIT yield, FCF yield, or earnings yield).
    # US-only: non-EDGAR filers carry no event signal (fields are NaN -> 0).
    _spin = s('spin_flag', 0); _tender = s('tender_flag', 0)
    # (endpoint matrix, REACH) a DATED spin anchor beside the EDGAR Form-10
    # flag: the spinco's own Form 10-12B/10-12G registration (fmp_events)
    # within 24 months — registration precedes distribution by a few months,
    # so this spans the post-spin forced-selling / orphan window. The filing
    # is the spinco's (ECG, SNDK, VSNT...), and a listed price proves the
    # distribution happened.
    _spin = _spin.where(_spin == 1, (_evt_age_days('evt_spin_filing_date') <= 730).astype(float))
    _merger = s('merger_flag', 0); _gopriv = s('going_private_flag', 0)
    # (endpoint matrix, REACH) DATED deal anchors from fmp_events beside the
    # EDGAR flags: a merger proxy / M&A-target announcement or a tender offer
    # within the last 9 months (a deal older than that has closed or broken).
    # The spread to the offer price is the true measure but FMP carries no
    # offer price, so freshness is the available proxy.
    _merger = _merger.where(_merger == 1, ((_evt_age_days('evt_merger_proxy_date') <= 270)
                                           | (_evt_age_days('evt_ma_target_date') <= 270)).astype(float))
    _tender = _tender.where(_tender == 1, (_evt_age_days('evt_tender_date') <= 270).astype(float))
    # (audit 3) a deal whose stock has since fallen > 20% over the quarter is
    # broken or repriced, not a spread — the panel reads it where present
    _deal_alive = ~(_ncol('ts_r13') < -0.20)
    _merger = _merger.where(_deal_alive, 0.0)
    _tender = _tender.where(_deal_alive, 0.0)
    _gopriv = _gopriv.where(_deal_alive, 0.0)
    _reorg = s('reorg_flag', 0); _nol_usd = _num('nol_usd')
    _ebit_yield = (1.0 / s('ev_ebit', 0)).where(s('ev_ebit', 0) > 0, np.nan)
    # (topcheck) DERIVE the earnings-yield leg from p_e, not the raw
    # earnings_yield field — the latter is FX-corruptible and was internally
    # INCONSISTENT with p_e on several event names (SUNB ey 0.19 vs p_e 21.8;
    # STG ey 0.91; PXLW ey 1.72 while loss-making). 1/p_e (p_e>0) is the
    # consistent, self-checking cheapness lens.
    _pe_v = s('p_e', np.nan)
    _earn_yield = (1.0 / _pe_v).where(_pe_v > 0, np.nan)
    # "Excellent valuation": cheap on ANY of the three yield lenses.
    _excellent_value = ((fcf_yield >= 0.08) | (_earn_yield >= 0.08)
                        | (_ebit_yield >= 0.10))

    # SHARED event-sleeve value helpers (used by spinoff AND post-reorg):
    # EBITDA yield is D&A-immune (survives fresh-start write-downs / carve-out
    # D&A shifts); commodity cyclicals emerging or spinning near a PEAK show
    # fat trailing earnings that will not persist -> Energy/Materials names are
    # judged on MID-CYCLE (margin-based) EBITDA where a standalone history
    # exists (excludes a peak, admits a trough).
    _ev_ebitda_ev = s('ev_ebitda', np.nan)
    _ebitda_y_ev = (1.0 / _ev_ebitda_ev).where(_ev_ebitda_ev > 0, np.nan)
    _midcyc_y_ev = (_midcyc_ebitda / _num('enterprise_value')).where(_num('enterprise_value') > 0, np.nan)
    _is_cyc_ev = sector.isin({'Energy', 'Materials'})
    _dna_ev = _ncol('da_ttm'); _cx_ev = _ncol('capex_ttm')
    _dna_ok_ev = ~((_dna_ev < 0.5 * _cx_ev) & _dna_ev.notna() & _cx_ev.notna())

    # Spin-off (Form 10 registration): forced-selling / identity-vacuum — a
    # viable operating business, cheap, not melting.
    # (diligence) a spin carries NO fresh-start discharge gain (1/p_e usable),
    # but trailing earnings are noised by carve-out allocations + separation
    # one-offs and the D&A basis can shift -> add the D&A-immune EBITDA yield;
    # commodity cyclical spins (SanDisk into a memory peak; cement) get the
    # mid-cycle lens; and guard the DIRTY SPIN (parent offloading debt: RHLD
    # emerged at net-debt/EBITDA 13.9x).
    # (user directive) Split the spin sleeve by THESIS, and drop the leverage
    # guard entirely — a levered spin can still be the opportunity, and the
    # guard was silently excluding SanDisk-class quality carve-outs and dirty-
    # balance-sheet orphans that the market misprices for exactly that reason.
    #
    # (1) VALUE spin (arch_spinoff_value): the classic forced-selling / orphan
    #     discount — a viable operating business trading cheap on an OPERATING
    #     yield. Leverage-agnostic (no balance-sheet cap): a cheap, viable,
    #     non-melting spun business qualifies whatever its debt.
    # (_op_viable — the impairment-robust operating-viability floor — is defined
    # once near _not_melting and reused here.)
    _spin_noncyc_val = (_excellent_value | (_ebitda_y_ev >= 0.10))
    _spin_cyc_val = ((_midcyc_y_ev.notna() & (_midcyc_y_ev >= 0.10))
                     | (_midcyc_y_ev.isna() & ((_ebitda_y_ev >= 0.10) | (fcf_yield >= 0.08))))
    _spin_value = ((_is_cyc_ev & _spin_cyc_val) | (~_is_cyc_ev & _spin_noncyc_val))
    # (audit 3) the forced-selling ORPHAN read on the panel: down over the
    # quarter or >= 15% off the 52w high, where the panel has the name; a spin
    # that has already re-rated (up > 50% over six months) is a template, not
    # an entry
    _spin_orphan = (((_ncol('ts_r13') <= -0.10) | (_ncol('ts_dist_hi52') <= 0.85))
                    | (_ncol('ts_r13').isna() & _ncol('ts_dist_hi52').isna())).fillna(False)
    _spin_undelivered = ~(_ncol('ts_r26') > 0.50)
    df['arch_spinoff_value'] = (
        (_spin == 1) & is_operating & _not_melting & (mcap > 0)
        & _op_viable(-0.05)                     # viable spun business (impairment-robust), not a deep loss-maker
        & _spin_value & _spin_orphan & _spin_undelivered
    ).fillna(False).astype(int)
    df['spinoff_value_watch'] = ((_spin == 1) & is_operating & _not_melting & (mcap > 0)
                                 & _op_viable(-0.05) & _spin_value).fillna(False).astype(int)
    # (audit 3) the DIRTY spin (parent offloading debt) surfaced, never gated
    df['dirty_spin_flag'] = ((_spin == 1) & (nde_real > 4.0)).fillna(False).astype(int)

    # (2) QUALITY spin (arch_spinoff_quality): a high-return FRANCHISE cast off
    #     at a fair (not-bubble) multiple. SanDisk spun with roce 0.35,
    #     op-margin 0.61, net cash, EV/EBIT 20.2 — a ~5% earnings yield, so it
    #     was NEVER deep-cheap and the value spin above cannot catch it. This
    #     thesis keys on RETURNS + MARGINS + a SOUND balance sheet + a SANE
    #     price, deliberately NOT on cheapness (a great business rarely spins
    #     cheap; the edge is the forced-selling orphan discount on quality).
    # (gate-audit) SanDisk lesson: this is an explicitly-QUALITY thesis (roce &
    # op-margin already gate quality), so the multiple ceiling should exclude
    # only egregious BUBBLES, not fairly-priced premium spins. Raised 22->35x
    # EV/EBIT (20->30x EV/EBITDA) — a franchise spun at 25x is still the trade.
    _spin_reasonable_mult = (((s('ev_ebit', np.nan) > 0) & (s('ev_ebit', np.nan) <= 35.0))
                             | ((_ev_ebitda_ev > 0) & (_ev_ebitda_ev <= 30.0)))
    _SPIRITED.append('spinoff_quality')   # (endpoint matrix, EXC) insider buying at the spinco ranks members
    df['arch_spinoff_quality'] = (
        (_spin == 1) & is_operating & _not_melting & (mcap > 0)
        & (_num('roce') >= 0.20)                 # genuine return on capital (SNDK 0.35)
        & (s('op_margin', np.nan) >= 0.15)       # fat operating margin — a real franchise (SNDK 0.61)
        & _spin_reasonable_mult                  # bought at a sane price, not a bubble (SNDK EV/EBIT 20.2)
        & ((nde <= 3.0) | (net_cash_pct_c >= 0)) # sound balance sheet (SNDK is net cash)
        & ~_roce_oneoff_suspect                  # (audit 3) the carve-out roce corroborated (no uncorroborated one-off)
        & _spin_undelivered                      # (audit 3) not already delivered (up > 50% over six months = a template, not an entry)
    ).fillna(False).astype(int)

    # (3) ASSET spin (arch_spinoff_asset): forced-selling of a spun entity can
    #     leave it priced below its ASSET backing regardless of earnings — the
    #     classic sum-of-parts / net-net / hidden-real-estate / deep-net-cash
    #     orphan (a spin often carries the parent's under-marked assets). Keys
    #     on a BALANCE-SHEET floor, NOT on yield (value spin) or returns
    #     (quality spin), but still requires a non-melting business so the asset
    #     value is not being torched. All legs are same-currency (mcap-relative
    #     levels straight from source), except the off-EV asset gap which is
    #     guarded by _fx_coherent (the hidden_assets currency-mix lesson).
    _spin_asset_floor = (
        ((pb > 0) & (pb < 1.0))                   # priced below book
        | (ncav_pct >= 0.5)                       # net-net: NCAV covers half+ of mcap
        | (net_cash_pct_c >= 0.20)                # deep net cash
        | (cash_gt_ev > 0)                        # cash exceeds enterprise value
        | (_fx_coherent & (_hidden_pct >= 0.25))  # off-EV asset pile >= 25% of mcap
    )
    df['arch_spinoff_asset'] = (
        (_spin == 1) & is_operating & _not_melting & (mcap > 0)
        & _op_viable(-0.05)                       # (audit) viability floor (impairment-robust): NVRI (op -89% impairment, fcf -68%) is a melting asset pile and still fails; a healthy impairment-hit spin is kept
        & _spin_asset_floor & _spin_orphan        # (audit 3) the forced-selling read, where the panel has the name
    ).fillna(False).astype(int)

    # Greenblatt Magic Formula: the intersection of a HIGH EARNINGS YIELD
    # (EBIT/EV) and a HIGH RETURN ON CAPITAL — cheap AND good, the two legs
    # Greenblatt ranks the universe on. We use EBIT/EV (1/ev_ebit, discharge-
    # and D&A-basis-agnostic vs 1/p_e) and roce as the return-on-capital proxy
    # (roic_after_sbc is too sparse in the universe to gate on). Operating-only
    # (EBIT/EV and roce are meaningless for banks/REITs/utilities) and not
    # melting.
    _greenblatt_ey = (1.0 / s('ev_ebit', 0)).where(s('ev_ebit', 0) > 0, np.nan)
    df['arch_greenblatt_magic'] = (
        is_operating & _not_melting & (mcap >= 50e6) & _ev_sane   # (audit 3) investable scale; the EV sanity band on the EBIT/EV leg
        & (_greenblatt_ey >= 0.10)               # cheap: EBIT/EV in the top ~quartile
        & ((_num('roce') >= 0.25)                # good: return on capital in the top ~decile-ish
           # (endpoint matrix) or TTM after-tax ROIC >= 20% (~25% pre-tax) from
           # the quarterly panel (EBIT x 0.75 / (equity + debt - cash))
           # (a > 100% ROIC is the same tiny-denominator artifact the roce
           # guard below drops, so the lens stops there)
           | _ncol('fqx_roic_ttm').between(0.20, 1.0))
        & ~_roce_oneoff_suspect                  # (audit) drop tiny-denominator ROCE artifacts (KPLT 1.05 on ~0% op-margin) — the guard sibling large_cap_quality already uses
    ).fillna(False).astype(int)
    # (audit 4) Greenblatt's own method is a COMBINED RANK of earnings yield and
    # return on capital (one pre-tax basis: ROCE, else the TTM after-tax ROIC
    # grossed up by 1/0.75), ranked within the listing market; the core is the
    # top decile of that combined rank, the absolute-cut rule is greenblatt_magic_watch
    _gb_roc = _ncol('roce').where(~_roce_oneoff_suspect).fillna(_ncol('fqx_roic_ttm').where(_ncol('fqx_roic_ttm') <= 1.0) / 0.75)
    # ranked within the listing market over the gate's own population (operating,
    # >= $50M) — _crank ranks only the liquid MB base, which left 218 illiquid
    # members unranked and passing as "unmeasured"
    _gb_pop = is_operating & (mcap >= 50e6)
    def _gb_crank(x):
        xv = pd.to_numeric(x, errors='coerce').where(_gb_pop)
        n_c = xv.notna().groupby(country).transform('sum')
        return xv.groupby(country).rank(pct=True).where(n_c >= 50, xv.rank(pct=True))
    _gb_rank = (_gb_crank(_greenblatt_ey) + _gb_crank(_gb_roc)) / 2.0
    df['greenblatt_combined_rank'] = _gb_rank.round(4)
    _tier('greenblatt_magic', _gb_crank(_gb_rank) >= 0.90, measured=_gb_rank.notna())

    # Post-reorg / fresh-start (Assembly Theory): the single most powerful screen
    # is EBIT yield > 20% at emergence (Verdad: +61% 2yr); de-levering + intact
    # moat is gating — we proxy the moat with a high EBIT yield + not-melting.
    # Assembly Theory's EBIT-yield>20% is measured AT EMERGENCE, which we can't
    # observe; on CURRENT price only ~1 of ~44 fresh-start names clears 20%.
    # CRITICAL: the value test here must NOT use the earnings-yield (1/p_e) leg.
    # A fresh-start company's trailing net income is systematically contaminated
    # by the one-off debt-discharge / reorganization gain — WeightWatchers (WW)
    # posts $1.02B "net income" on $701M revenue (mcap $180M), a p_e of 1.56 that
    # is pure discharge gain, not earnings. That fake earnings yield sailed
    # through the generic _excellent_value and only the leverage cap accidentally
    # caught it. So gate post-reorg on OPERATING yield only (EV/EBIT or FCF) — the
    # exact lens Verdad uses, and the one discharge gains cannot inflate. WW's
    # real EV/EBIT yield is 5.8% and FCF is negative, so it is now robustly
    # excluded on value, not by luck of leverage.
    # (diligence) The trailing EBIT lens is doubly contaminated at emergence:
    #  (a) fresh-start accounting writes assets to fair value (usually DOWN in
    #      bankruptcy) -> understated D&A -> INFLATED EBIT -> false cheapness;
    #  (b) CYCLICALS dominate emergences (Seadrill, Gulfport, Talen, Nine
    #      Energy, coal, shipping) and often emerge near a commodity PEAK, so
    #      trailing EBIT/EBITDA is peak-cycle earnings that will not persist
    #      (Verdad's own caution).
    # Fixes: prefer the D&A-IMMUNE EBITDA yield; trust the EBIT lens only when
    # D&A is not suspiciously low vs maintenance capex; and for commodity
    # cyclicals judge cheapness on MID-CYCLE (margin-based) EBITDA, not
    # trailing — which correctly EXCLUDES a peak emerger (fat trailing, thin
    # normalized) and ADMITS a trough emerger (thin trailing, fat normalized).
    _ebitda_y_pr = (1.0 / s('ev_ebitda', np.nan)).where(s('ev_ebitda', np.nan) > 0, np.nan)
    _midcyc_y_pr = (_midcyc_ebitda / _num('enterprise_value')).where(_num('enterprise_value') > 0, np.nan)
    _is_cyc_pr = sector.isin({'Energy', 'Materials'})
    _dna_pr = _ncol('da_ttm'); _cx_pr = _ncol('capex_ttm')
    _dna_ok_pr = ~((_dna_pr < 0.5 * _cx_pr) & _dna_pr.notna() & _cx_pr.notna())  # else EBIT write-down-inflated
    _noncyc_value = ((_ebitda_y_pr >= 0.10)
                     | ((_ebit_yield >= 0.10) & _dna_ok_pr)
                     | (fcf_yield >= 0.08))
    # commodity cyclical at re-emergence: mid-cycle yield is the honest lens;
    # fall back to the D&A-immune EBITDA yield only where no mid-cycle exists
    # (fresh entity, <3yr history).
    _cyc_value = ((_midcyc_y_pr.notna() & (_midcyc_y_pr >= 0.10))
                  | (_midcyc_y_pr.isna() & (_ebitda_y_pr >= 0.10))
                  | (fcf_yield >= 0.08))
    _reorg_value = ((_is_cyc_pr & _cyc_value) | (~_is_cyc_pr & _noncyc_value))
    # Leverage discipline is central to the post-reorg thesis (Verdad: de-
    # levering + intact moat), BUT (user) trailing net-debt/EBITDA is a CYCLE
    # ARTIFACT for a commodity emerger at a trough: depressed trough EBITDA
    # inflates the ratio even when the balance sheet is absolutely de-levered.
    # So judge a cyclical's leverage on MID-CYCLE EBITDA (rescale trailing nde
    # by trailing/mid-cycle EBITDA) — a trough name with sound mid-cycle
    # leverage passes; a genuinely over-levered one (iHeart 14x, non-cyclical,
    # no relaxation) still fails.
    _midcyc_nde = (nde * (ebitda_ttm_v / _midcyc_ebitda)).where(
        (_midcyc_ebitda > 0) & (ebitda_ttm_v > 0), np.nan)
    # (audit A2) the mid-cycle relaxation must not admit a genuinely TERMINAL
    # balance sheet: NINE at trailing nde 8.98x with negative op and a pure
    # discharge-gain p_e cleared on a generous normalized estimate. Cap the
    # relaxation at a moderate trailing leverage (<=6x — a real trough cyclical
    # is de-levered in absolute terms, not 9x) and require positive trailing
    # EBITDA (a positive margin to normalize from at all).
    # (gate-audit) a post-reorg emerger's thesis IS elevated-but-FALLING
    # leverage, so a flat nde<=3 was too tight and its mid-cycle relief was
    # limited to Energy/Materials — it excluded non-E/M operating emergers still
    # de-levering (WW, the comment's own poster child, at nde 3.44). Lift the
    # flat cap to 4.0 (a de-levering emerger runs elevated), keeping the deeper
    # mid-cycle relaxation for cyclicals.
    _reorg_lev_ok = ((nde <= 4.0) | (net_cash_pct_c >= 0)
                     | (_nde_meaningful.isna() & _bs_lev_ok)   # (audit 3) a trough emerger with EBITDA <= 0 is judged on the balance sheet (debt/assets, debt/equity), not the 99 fill
                     | (_is_cyc_pr & _midcyc_nde.notna() & (_midcyc_nde <= 3.0)
                        & (nde <= 6.0) & (ebitda_margin > 0)))
    # (gate-audit) FRESHNESS — now that reorg_date is the TRUE emergence date
    # (earliest ReorganizationValue mark), a post-reorg equity is a live special
    # situation only while the re-rate is still running. Verdad's alpha is the
    # first ~2 years, but a fresh-start equity keeps re-rating past that, so use
    # a 5-year emergence window: this correctly drops names that emerged >5yr
    # ago (WFRD 2019, EXE 2018) whose reorg_flag only lingered via recent
    # comparative-period ReorganizationItems. Missing date stays permissive.
    # NB: use the RAW column, not s() — s() coerces to numeric, which turns the
    # date STRINGS into NaN (vacuously "fresh").
    _emg_dt = (pd.to_datetime(df['reorg_date'], errors='coerce')
               if 'reorg_date' in df.columns
               else pd.Series(pd.NaT, index=df.index))
    _emg_cut = pd.Timestamp.now() - pd.Timedelta(days=1825)
    _emg_fresh = _emg_dt.isna() | (_emg_dt >= _emg_cut)
    df['arch_post_reorg'] = (
        (_reorg == 1) & is_operating & _not_melting
        & _reorg_value
        & _reorg_lev_ok
        & _emg_fresh
    ).fillna(False).astype(int)

    # Special-situation catalyst: a dated merger / tender / going-private event
    # with a bounded downside, bought cheap so value holds if the deal breaks.
    # (gate-audit) On a DEFINITIVE deal (announced merger / going-private) the
    # return is the SPREAD to the deal price — the target's trailing
    # profitability and independent cheapness are irrelevant, so the viability +
    # value floor wrongly excluded 83 event names (biotech/tech takeout targets
    # where op<0). Fire definitive deals on the EVENT alone; keep the
    # viability + value/NAV floor only on the softer TENDER path (rumored /
    # partial → the downside floor matters if the deal breaks).
    df['arch_special_situation'] = (
        (mcap > 0) &
        (((_merger == 1) | (_gopriv == 1))              # definitive/cash deal — spread capture
         | ((_tender == 1) & _not_melting
            & ((is_operating & _excellent_value)
               | ((is_financial | is_reit) & (pb > 0) & (pb < 1.0)))))
    ).fillna(False).astype(int)

    # NOL shell: a large net-operating-loss carryforward relative to market cap
    # (a monetizable tax asset — WMIH/Mr. Cooper), on a survivable balance sheet.
    # The RMB-as-USD inflation is fixed at the SOURCE (the re-scrape reads
    # USD-only NOL), so no domicile gate is needed — a US-listed foreign filer
    # that reports a genuine USD NOL is a legitimate member of the pool and is
    # kept. We only strip CORRUPTION (out-of-band ratio) and BURNERS, not assets.
    _nol_to_mcap = (_nol_usd / mcap.where(mcap > 0))
    df['arch_nol_shell'] = (
        is_operating & (mcap > 0)
        & (_nol_to_mcap >= 0.5) & (_nol_to_mcap <= 20.0)   # sane band (a >20x ratio is a currency/mcap artifact)
        & ((net_cash_pct_sane >= 0.10) | (cash_gt_ev > 0))   # (audit 3) a SHELL is cash-backed; an ordinary cheap profitable NOL user is xr_nol_shield / tax_efficient ground, not this
        & (s('op_margin', np.nan) > -0.30)                 # (topcheck) survivable, not a >100%-mcap/yr burner (ONCO/ASTC)
        & _not_melting
        & ~(fcf_yield < -0.25)   # (deep-audit) op_margin>-0.30 does NOT capture cash burn: CNTY fcf-119%/op+9.2%, NEON fcf-80% behind a 355% op artifact torched the balance sheet while passing the op gate. An NOL on a dying balance sheet is un-monetizable (missing fcf stays permissive).
    ).fillna(False).astype(int)

    _sym_nc = df['symbol'].astype(str)
    _nm_nc = df['name'].astype(str) if 'name' in df.columns else pd.Series('', index=df.index)
    _nm_key = _nm_nc.str.lower().str.replace(r'[^a-z]', '', regex=True).str[:14]
    _base_nm = dict(zip(_sym_nc, _nm_key))
    _sfx_pref_line = pd.Series([
        bool(len(sy) == 5 and sy.isalpha() and sy.isupper() and sy[4] in 'PONMLIVZ'
             and sy[:4] in _base_nm and nk and nk != 'nan' and _base_nm[sy[:4]] == nk)
        for sy, nk in zip(_sym_nc, _nm_key)], index=df.index)
    # exchange-traded funds / notes (FMP etf-list): an ETN issued by a bank
    # carries the BANK's name and sector (JPMorgan's AMJB / VYLD) and slipped
    # past the name-pattern test below into the elite lists
    _etf_syms = set()
    if os.path.exists('fmp_etf_symbols.csv'):
        _etf_syms = set(pd.read_csv('fmp_etf_symbols.csv')['symbol'].astype(str))
    _is_etf_line = df['symbol'].astype(str).isin(_etf_syms)
    _is_noncommon = _is_etf_line | (
        _sym_nc.str.match(r'^[A-Z]{1,5}-P[A-Z]?$')
        | _sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT|RI|CVR)$')
        # (audit-2) BARE 5-char SPAC derivatives — a 4-letter base + W (warrant)
        # / U (unit) / R (rights), Nasdaq's 5th-letter convention with NO
        # separator: SBCWW, COLAU, HAVAU, MBAVU, EVLVW, ANNAW, TDDWW. 29 of them
        # carried archetype flags (SBCWW fired a sub-book archetype on a
        # warrant's class market cap) because only the separator forms were
        # caught. Exactly 5 characters, so 4-char common stocks ending in
        # W/U/R (Charter CHTR, Netgear NTGR, Comscore SCOR) are NOT matched.
        | _sym_nc.str.match(r'^[A-Z]{4}[WUR]$')
        # (R7) suffixed foreign/Canadian preferred lines the anchored US
        # pattern misses — kept narrow so exchange suffixes (.PA Paris, .PR
        # never terminal here) are NOT caught: TICK.PR.G, TICK-PR-A, TICK PFD.
        | _sym_nc.str.contains(r'\.PR\.[A-Z]$', regex=True)          # GWO.PR.G (Canadian pref)
        | _sym_nc.str.contains(r'-PR[-.]?[A-Z]?$', regex=True)       # BAM-PR-A, X-PR
        # (fresh) exchange-suffixed pref line: TICKER-P<series>.TO / .V etc.
        # ($-anchored US pattern misses these — GWO-PI.TO, SLF-PC.TO leaked).
        | _sym_nc.str.contains(r'-P[A-Z]?\.[A-Z]{1,3}$', regex=True)
        | _sym_nc.str.contains(r'[-. ]PFD\b', case=False, regex=True)
        # SEPARATOR-LESS Nasdaq 5th-letter lines of a listed common: P/O/N/M/L/I
        # = preferred series (HBANL/HBANM/HBANP, FITBP/FITBO/FITBI, CCNEP,
        # TCBIO, FULTP), V = when-issued, Z = notes/misc. Only when the 4-letter
        # BASE is itself in the universe under the SAME company name, so
        # genuine share classes (LILAK / LILAB, ATROB, BKUTK) are untouched.
        | _sfx_pref_line
        | _nm_nc.str.contains(r'senior notes|notes due|% notes', case=False, regex=True)
        | _nm_nc.str.contains(r'preferred|pfd| pref |% notes|perpetual|warrant',
                              case=False, regex=True)
        # "Depositary" alone is an ADR / depositary receipt of the COMMON
        # (Woodside, Haleon, Rentokil, ABN AMRO): non-common only beside a
        # preferred-type word (depositary shares in a preferred series).
        # (audit 2026-10-02: the bare word scrubbed 71 ordinary shares)
        | _nm_nc.str.contains(r'depositary.*(?:preferred|pfd|perpetual|series|%)',
                              case=False, regex=True)
        # (surgical audit) BANKRUPTCY STUB: the old 5th-letter-Q convention
        # (OPIRQ, BLIAQ/BLIBQ) marks a security still IN Chapter 11 / delisted,
        # not an emerged post-reorg equity. Broadening reorg detection to
        # ReorganizationItems surfaced OPIRQ (a $0.31, $23M stub with $2.4B net
        # debt) — a false promotion. Scrub the 5-letter Q-suffix line when it is
        # also penny-priced (<$5), so a genuine 5-letter Q ticker is untouched.
        | (_sym_nc.str.match(r'^[A-Z]{4}Q$') & (_num('price') < 5.0))
        # (audit) GSE / agency PREFERRED-series stubs (Fannie/Freddie in
        # conservatorship): FNMAx / FMCCx / FMCKx / FREJx 5-char series lines
        # carry the common's equity_cagr and a corrupt tiny net income, firing
        # book_compounder. The 4-char commons (FNMA/FMCC) are NOT matched.
        | _sym_nc.str.match(r'^(FNMA|FMCC|FMCK|FREJ)[A-Z]$')
        # (surgical audit) COMMODITY/CRYPTO ETF & ETN wrappers: null-sector fund
        # lines (PALL/PPLT/SGOL physical-metal, FBTC bitcoin, AMJB/VYLD ETNs)
        # leak into cannibal/value gates — is_operating is True on a null sector
        # and their "buyback_yield" is a creation/redemption artifact. Match the
        # fund tell in the NAME, gated on a missing sector so real crypto/mining
        # OPERATORS (which carry a sector) are untouched.
        | (sector.str.lower().isin(['nan', 'none', ''])
           & _nm_nc.str.contains(
               r'\bETF\b|\bETN\b|ishares|\bSPDR\b|proshares|exchange.traded'
               r'|physical (gold|silver|platinum|palladium|metal)'
               r'|bitcoin|ethereum|\bether\b',
               case=False, regex=True))
    ).fillna(False)

    # ===== SENIOR SECURITIES: classified, judged on their own terms (user 2026-10-02) =====
    # Preferreds, baby bonds / exchange-traded notes, CVRs, rights, warrants and
    # units stay in the universe. They are kept OUT of the common-equity
    # archetypes (a preferred's "P/B" or "P/E" is the parent's book and
    # earnings over the preferred's price — meaningless), and the fixed-income
    # ones get their own lens below: the instrument's OWN yield against its
    # peers, and the issuer's ability to pay it.
    # Two tells catch the lines the ticker/name patterns above miss (audit
    # 2026-10-02: CHS preferreds, Comcast ZONES, AT&T / Stifel / Prudential
    # baby bonds, Liberty Broadband and NCR preferreds fired common screens):
    #  (a) a PREFERRED SERIES: two or more 5-letter tickers on the same 4-letter
    #      base and company name ending P/O/N/M/L (CHSCP..CHSCL, UEPCO/UEPCP);
    #  (b) a SENIOR TWIN: a line that shares its company name, exact share count
    #      and currency with a more-traded sibling (the master gives a preferred
    #      the parent's share count — NCRRP showed a $138.8B "market cap"), prices
    #      in the $15-30 band around a $25 par, pays a 4-15% coupon (profile
    #      lastDividend / price), and whose yield differs from the sibling's by
    #      more than 25% (an ADR yields what its ordinary share yields; a
    #      preferred or note does not).
    _price_sn = _num('price')
    _cpn = _ncol('fmp_last_dividend')
    _yld_sn = (_cpn / _price_sn.where(_price_sn > 0))
    _nm_sn = (_nm_nc.str.lower().str.replace(r'[^a-z0-9 ]', '', regex=True)
              .str.replace(r'\b(corp|corporation|inc|incorporated|company|co|ltd|limited|plc|holdings?|group|the)\b',
                           '', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip())
    _sh_sn = _num('shares_outstanding').round(-3)
    _cur_sn = df['currency'].astype(str) if 'currency' in df.columns else pd.Series('', index=df.index)
    _dv_sn = _ncol('pew_avg_dollar_volume').fillna(-1.0)
    _sn = pd.DataFrame({'nm': _nm_sn, 'sh': _sh_sn, 'cur': _cur_sn, 'dv': _dv_sn,
                        'px': _price_sn, 'y': _yld_sn, 'sym': _sym_nc}, index=df.index)
    _sn_valid = (_sn['nm'] != '') & (_sn['nm'] != 'nan') & (_sn['sh'] > 0)
    _g_sn = _sn[_sn_valid].groupby(['nm', 'sh', 'cur'])
    _n_sn = _g_sn['sym'].transform('size').reindex(df.index)
    _prim_i = _g_sn['dv'].idxmax()
    _prim_map = _sn.loc[_prim_i.values, ['nm', 'sh', 'cur', 'px', 'y', 'sym']].rename(
        columns={'px': 'ppx', 'y': 'py', 'sym': 'psym'})
    _sn_m = _sn[['nm', 'sh', 'cur']].reset_index().merge(_prim_map, on=['nm', 'sh', 'cur'], how='left').set_index('index')
    _px_ratio = (_sn['px'] / _sn_m['ppx'].where(_sn_m['ppx'] > 0))
    _y_ratio = (_sn['y'] / _sn_m['py'].where(_sn_m['py'] > 0))
    _senior_twin = ((_n_sn >= 2) & (_sn['sym'] != _sn_m['psym'])
                    & _price_sn.between(15.0, 30.0) & _yld_sn.between(0.04, 0.15)
                    & ((_px_ratio > 1.3) | (_px_ratio < 1 / 1.3))
                    & ~_y_ratio.between(0.8, 1.25)).fillna(False)
    _b4 = _sym_nc.str[:4]
    _ser5 = ((_sym_nc.str.len() == 5) & _sym_nc.str.isalpha() & _sym_nc.str[4].isin(list('PONML')))
    _ser_n = pd.Series(0, index=df.index)
    if _ser5.any():
        _ser_n.loc[_ser5] = (pd.DataFrame({'b4': _b4[_ser5], 'nm': _nm_sn[_ser5]})
                             .groupby(['b4', 'nm'])['b4'].transform('size').values)
    _pref_series = _ser5 & (_ser_n >= 2)
    _cvr_line = (_sym_nc.str.contains(r'-(?:RI|CVR)$', regex=True)
                 | _nm_nc.str.contains(r'contingent value', case=False, regex=True))
    _is_noncommon = (_is_noncommon | _senior_twin | _pref_series | _cvr_line).fillna(False)
    # security_type: one label per line (books show it; nothing is dropped)
    _st = pd.Series('common', index=df.index, dtype=object)
    _st[_is_noncommon] = 'other_non_common'
    _st[_sym_nc.str.match(r'^[A-Z]{4}Q$') & (_price_sn < 5.0)] = 'bankruptcy_stub'
    _st[_sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS)$') | _nm_nc.str.contains('warrant', case=False)
        | (_sym_nc.str.match(r'^[A-Z]{4}W$') & _is_noncommon)] = 'warrant'
    _st[_sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:U|UN)$') | (_sym_nc.str.match(r'^[A-Z]{4}U$') & _is_noncommon)] = 'unit'
    _st[_sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:R|RT)$') | (_sym_nc.str.match(r'^[A-Z]{4}R$') & _is_noncommon)] = 'right'
    _st[_cvr_line] = 'cvr'
    _st[_is_noncommon & (_nm_nc.str.contains(r'senior notes|notes due|% notes|debenture', case=False, regex=True)
                         | _senior_twin)] = 'note_or_preferred'
    _st[_is_noncommon & (_pref_series | _sfx_pref_line | _sym_nc.str.match(r'^[A-Z]{1,5}-P[A-Z]?$')
                         | _sym_nc.str.contains(r'\.PR\.[A-Z]$|-PR[-.]?[A-Z]?$|-P[A-Z]?\.[A-Z]{1,3}$', regex=True)
                         | _nm_nc.str.contains(r'preferred|pfd|perpetual', case=False, regex=True))] = 'preferred'
    _st[_is_etf_line] = 'etf_etn'
    df['security_type'] = _st.values
    # SENIOR SECURITY VALUE: a preferred / note line that is cheap on its OWN
    # yield — at least 1.25x the median yield of senior lines in the same
    # currency (a peer frame) — from an issuer that can pay it: the issuer
    # (the most-traded common line of the same company; the line's own row
    # where no common is listed, e.g. the CHS co-op) earns a profit, is not
    # melting, carries no data-quality flag, and, outside financials, covers
    # its interest at least 1.5x. Spirit ranks the yield premium, the issuer's
    # coverage and net cash, and its margin.
    _fi_line = df['security_type'].isin(['preferred', 'note_or_preferred']) & _yld_sn.between(0.005, 0.25)
    _y_med_cur = _yld_sn.where(_fi_line).groupby(_cur_sn).transform('median')
    _issuer_sym = _sn_m['psym'].where(_sn_m['psym'].notna() & (_sn_m['psym'] != _sym_nc), _sym_nc)
    _row_of = pd.Series(np.arange(len(df)), index=_sym_nc.values)
    _row_of = _row_of[~_row_of.index.duplicated()]
    _iss_i = _issuer_sym.map(_row_of)
    def _iss(col):
        v = _ncol(col).values
        out = np.full(len(df), np.nan)
        ok = _iss_i.notna().values
        out[ok] = v[_iss_i[ok].astype(int).values]
        return pd.Series(out, index=df.index)
    _iss_ni = _iss('net_income_ttm')
    _iss_ic = _iss('interest_coverage')
    _iss_opm = _iss('op_margin')
    _iss_dq = _iss('data_quality_flag')
    _iss_nc = _iss('net_cash_pct_mcap')
    _iss_fin = pd.Series(is_financial.values, index=df.index).astype(float)
    _iss_fin = pd.Series(np.where(_iss_i.notna(), _iss_fin.values[_iss_i.fillna(0).astype(int).values], np.nan),
                         index=df.index)
    _iss_melt = pd.Series(np.where(_iss_i.notna(),
                                   (~_not_melting).astype(float).values[_iss_i.fillna(0).astype(int).values], np.nan),
                          index=df.index)
    _can_pay = ((_iss_ni > 0) & ~(_iss_melt == 1) & ~(_iss_dq == 1)
                & ((_iss_fin == 1) | ~(_iss_ic < 1.5))).fillna(False)
    df['arch_senior_security_value'] = (
        _fi_line & (_yld_sn >= 1.25 * _y_med_cur) & _can_pay
    ).fillna(False).astype(int)
    df['senior_yield'] = _yld_sn.where(_fi_line).round(4)
    df['senior_yield_vs_peers'] = (_yld_sn / _y_med_cur).where(_fi_line).round(3)
    df['senior_issuer'] = _issuer_sym.where(_fi_line)
    _DEMOTED.setdefault('senior_security_value', []).extend([
        (_yld_sn / _y_med_cur, 1), (_iss_ic, 1), (_iss_nc, 1), (_iss_opm, 1), (_iss_ni, 1)])
    _SENIOR_OK = {'arch_senior_security_value'}
    _GATED_SCORES = [c for c in ['tenbagger_score', 'tenbagger_implied_return',
                     'evsales_derate_score', 'evsales_derate_gap',
                     'lynch_reward_score', 'lynch_leg_max', 'lynch_rank',
                     'lynch_exceptional_leg', 'analyst_awakening_score',
                     'seg_inflect_score', 'oneil_score', 'weinstein_score',
                     'kullamagie_score', 'cundill_score',
                     'analyst_rerating_score', 'asleep_score',
                     'inst_accum_score', 'inst_accum_accelerating',
                     'biotech_deep_value_score', 'biotech_cash_runway_yrs',
                     'coiled_base_score', 'xr_score', 'xr_family_count'] if c in df.columns]
    _scrub_cols = ([c for c in arch_cols if c not in _SENIOR_OK] + _GATED_SCORES
                   + [c for c in df.columns if c.endswith('_watch') and 'arch_' + c[:-6] not in _SENIOR_OK])
    # exported so books can drop preferred / warrant / unit lines too
    df['non_common_flag'] = _is_noncommon.fillna(False).astype(int).values
    if _is_noncommon.any():
        df.loc[_is_noncommon.values, _scrub_cols] = 0
        print(f'  scrubbed archetype flags + gated scores on '
              f'{int(_is_noncommon.sum())} non-common securities', file=sys.stderr)

    # (surgical audit) DATA-CORRUPTION scrub: EBITDA > revenue is physically
    # impossible for an operating company (EBITDA <= gross profit <= revenue).
    # SUNB fired spinoff_value on ebitda_ttm $4.49B / revenue $2.51B (179%) —
    # Ashtead parent-consolidated figures mapped onto the spun line. Scrub any
    # operating row whose EBITDA exceeds revenue by >10%.
    _eb_corrupt = (is_operating
                   & (_ncol('ebitda_ttm') > 1.10 * _ncol('revenue_ttm'))
                   & (_ncol('revenue_ttm') > 0))
    if _eb_corrupt.any():
        df.loc[_eb_corrupt.values, _scrub_cols] = 0
        print(f'  scrubbed {int(_eb_corrupt.sum())} EBITDA>revenue '
              f'data-corrupt rows', file=sys.stderr)

    # (surgical audit) CORRUPT-PRICE scrub: a company with material revenue
    # cannot have a near-zero market cap — SNBR (Sleep Number) carried a
    # $0.125 price (real ~$13) → mcap_usd $2.9M on ~$1.7B revenue, slipping past
    # the $2M micro-shell floor and firing nol_shell on a 100x-low price. Scrub
    # any row whose USD market cap is < $20M while USD revenue exceeds $200M.
    _px_corrupt = ((_ncol('market_cap_usd') < 20e6)
                   & (_ncol('revenue_ttm_usd') > 200e6))
    if _px_corrupt.any():
        df.loc[_px_corrupt.values, _scrub_cols] = 0
        print(f'  scrubbed {int(_px_corrupt.sum())} corrupt-price '
              f'(mcap<<revenue) rows', file=sys.stderr)

    # ===== MICRO-SHELL SCRUB: a sub-$2M market cap is untradeable and almost
    # always a delisted/data-corrupt shell (YYAI $0M, Zodiac Ventures $1M were
    # topping archetypes by ETA). Zero every archetype flag + gated score. =====
    _mc_scrub = pd.to_numeric(df.get('market_cap_usd'), errors='coerce')
    _is_shell = (_mc_scrub > 0) & (_mc_scrub < 2e6)
    if _is_shell.any():
        df.loc[_is_shell.values, _scrub_cols] = 0
        print(f'  scrubbed {int(_is_shell.sum())} sub-$2M micro-shells',
              file=sys.stderr)

    # ===== PRICE-GHOST DEDUP SCRUB: a duplicate line of the SAME security with
    # a WRONG (low) price — same normalized name + same EXACT shares
    # outstanding + same currency as a sibling, but a materially lower market
    # cap (its price is the corrupt-low outlier). Its price ratios (P/B, P/E,
    # P/S) are understated by the price error, so it fires fake-cheap value
    # archetypes and out-ranks the real listing in the dedup — e.g. UMBFO, a
    # ghost of UMB Financial (UMBF), showing P/B 0.26 vs the real 1.48. Zero its
    # archetype flags and mark is_price_ghost so enrich drops it from the ETA
    # ranking. Preferreds/warrants/units are EXCLUDED (real separate securities,
    # already handled by the non-common scrub); grouping is same-CURRENCY so
    # genuine cross-listings/ADRs (different currency) are never touched. =====
    _is_price_ghost = pd.Series(False, index=df.index)
    if {'shares_outstanding', 'name'}.issubset(df.columns):
        _sh_g = pd.to_numeric(df.get('shares_outstanding'), errors='coerce').round(0)
        _cur_g = df.get('currency', pd.Series('', index=df.index)).astype(str)
        _mc_g = pd.to_numeric(df.get('market_cap_usd'), errors='coerce')
        _nm_g = (df['name'].fillna('').astype(str).str.lower()
                 .str.replace(r'[^a-z0-9 ]', '', regex=True)
                 .str.replace(r'\b(corp|corporation|inc|incorporated|company|co|'
                              r'ltd|limited|plc|holdings?|group|sa|ag|nv|the|adr|'
                              r'sponsored|ordinary|shares?|class [a-z]|cl [a-z])\b',
                              '', regex=True)
                 .str.replace(r'\s+', ' ', regex=True).str.strip())
        _pr_g = pd.to_numeric(df.get('price'), errors='coerce')
        _gv = pd.DataFrame({'sym': df['symbol'].astype(str), 'nm': _nm_g,
                            'sh': _sh_g, 'cur': _cur_g, 'mc': _mc_g,
                            'pr': _pr_g, 'nc': _is_noncommon.values})
        _gv['_i'] = np.arange(len(_gv))
        _valid = (~_gv['nc']) & (_gv['nm'] != '') & (_gv['sh'] > 0) & (_gv['mc'] > 0)
        _gvv = _gv[_valid].copy()
        if len(_gvv):
            # A GHOST is a strict PREFIX-EXTENSION of a shorter sibling ticker
            # (base + 1-2 chars: UMBF->UMBFO, POWW->POWWP, WSBC->WSBCO, IMPP->
            # IMPPP) whose price DIVERGES >=1.3x from that sibling — i.e. an OTC
            # ghost or a no-dash preferred/note carrying the parent name + the
            # common's shares but a wrong (or par) price. The prefix rule is what
            # keeps this SAFE: a real large-cap whose baby-bonds trade under a
            # DIFFERENT ticker (AMG vs MGR, RGA/DTE/CUBI) is never a prefix of
            # them, so it is never scrubbed; and the 1.3x price gate spares
            # genuine same-price dual share-classes (NWS/NWSA).
            for (_nm, _sh, _cur), _grp in _gvv.groupby(['nm', 'sh', 'cur']):
                if len(_grp) < 2:
                    continue
                _rows = _grp.sort_values('sym', key=lambda s: s.str.len()).to_dict('records')
                for _ti in range(len(_rows)):
                    _T = _rows[_ti]
                    for _ki in range(_ti):
                        _K = _rows[_ki]
                        _dl = len(_T['sym']) - len(_K['sym'])
                        if 1 <= _dl <= 2 and _T['sym'].startswith(_K['sym']):
                            _pT, _pK = _T['pr'], _K['pr']
                            _div = (max(_pT, _pK) / max(min(_pT, _pK), 1e-9)
                                    if pd.notna(_pT) and pd.notna(_pK) and min(_pT, _pK) > 0
                                    else 99.0)
                            if _div >= 1.3:
                                _is_price_ghost.iloc[int(_T['_i'])] = True
                                break
    # NOTE: an earlier version ALSO scrubbed "FX-secondary" lines by a coarse
    # VENUE heuristic (Frankfurt/German-regional suffixes + Shanghai/Shenzhen
    # B-shares) whenever a same-name primary existed. REVERSED — that is exactly
    # the kind of rough rule that drops real opportunities: a China B-share
    # trades at a genuine, persistent DISCOUNT to its A/H sibling (a distinct,
    # legitimately-cheaper claim), and a foreign secondary is a real tradeable
    # line for some accounts. We keep only the TIGHT price-ghost rule above
    # (a wrong-price prefix-extension of the SAME ticker, e.g. UMBFO) — genuine
    # data corruption, not a separate security. FX ratio corruption on those
    # lines is a DATA problem to fix upstream (currency normalisation), not a
    # reason to remove the name from the pool.
    df['is_price_ghost'] = _is_price_ghost.astype(int)
    if _is_price_ghost.any():
        df.loc[_is_price_ghost.values, _scrub_cols] = 0
        print(f'  scrubbed {int(_is_price_ghost.sum())} price-ghost duplicate '
              f'lines (wrong-price duplicates of the SAME ticker)', file=sys.stderr)

    # ===== PRE-REVENUE BIOTECH SCRUB: a clinical-stage biotech's "5-year
    # durable margin / quality" is a licensing one-off, not operations (KROS
    # topped lindy_margin/tax_efficient). Zero these names' flags on every
    # archetype except the exempt set below (_biotech_ok). =====
    # ===== SYSTEMATIC BIOTECH CLASSIFIER =====
    # A drug developer (Biotechnology / Pharmaceuticals / drug manufacturer)
    # whose fundamentals are meaningless while PRE-COMMERCIAL: revenue is lumpy
    # licensing, "earnings" are one-off collaboration payments, cash flow is
    # R&D burn, outcomes are binary FDA events. A CLINICAL-stage name must not
    # populate any FUNDAMENTAL value/quality/growth/inflection archetype.
    # COMMERCIAL pharma (sustained revenue + profitability: Gilead/Vertex/
    # Novartis) is retained. Exposed as columns for downstream use.
    # (_is_drug_dev / _is_clinical_biotech computed above, before the scrubs.)
    # Exempt price-action/catalyst archetypes AND the biotech's own dedicated
    # deep-value screen; every other (fundamental) archetype is scrubbed.
    # (user) clinical-stage biotech moves on BINARY trial / regulatory events, a
    # different mechanism from every other archetype here, so the momentum /
    # perception archetypes are scrubbed too; the names they would have flagged
    # are SURFACED as biotech_momentum_watch (not lost), and the biotech's own
    # dedicated deep-value screen stays.
    _bio_mom = ['arch_analyst_awakening', 'arch_analyst_rerating_confirmed', 'arch_oneil_canslim',
                'arch_weinstein_stage2', 'arch_kullamagie_breakout']
    df['biotech_momentum_watch'] = (_is_clinical_biotech.values
                                    & (df[[c for c in _bio_mom if c in df.columns]].sum(axis=1) > 0)).astype(int)
    _biotech_ok = {'arch_biotech_deep_value', 'arch_senior_security_value',
                   'arch_special_situation',            # catalyst: a takeout spread does not depend on the pipeline
                   'arch_mb_biotech_financed_hiring'}   # gated on drug developers by construction
    _fund_arch = [c for c in arch_cols if c not in _biotech_ok]
    _fund_scrub = _fund_arch + [c for c in df.columns if c.endswith('_watch')
                                and c != 'biotech_momentum_watch'
                                and 'arch_' + c[:-6] not in _biotech_ok] + [c for c in _GATED_SCORES
                                if c not in ('biotech_deep_value_score',
                                             'biotech_cash_runway_yrs')]
    if _is_clinical_biotech.any():
        df.loc[_is_clinical_biotech.values, _fund_scrub] = 0
        print(f'  scrubbed {int(_is_clinical_biotech.sum())} clinical-stage '
              f'biotech from fundamental archetypes', file=sys.stderr)

    # ===== SEGMENT SURVIVABILITY SCRUB: a hidden-engine / segment-value
    # thesis needs a SURVIVING company. Zero the segment archetypes for double
    # cash-burners (EBITDA<0 AND FCF<0 AND CFO<=0). =====
    _srv_eb = pd.to_numeric(df.get('ebitda_ttm'), errors='coerce')
    _srv_fcf = pd.to_numeric(df.get('fcf_ttm'), errors='coerce')
    _srv_cfo = pd.to_numeric(df.get('cfo_ttm'), errors='coerce')
    _not_survivable = ((_srv_eb < 0) & (_srv_fcf < 0)
                       & ~(_srv_cfo > 0)).fillna(False)
    _segment_arch = [c for c in ['arch_geographic_global', 'arch_fastest_segment',
                     'arch_diversified_segments', 'arch_reinvest_inflect',
                     # the hidden-engine / segment-value XR theses this scrub names
                     'arch_xr_hidden_segment_compounder', 'arch_xr_segment_justifies_whole',
                     'arch_xr_margin_mixshift'] if c in df.columns]
    _segment_scrub = _segment_arch + [c for c in ('seg_inflect_score',)
                                      if c in df.columns]
    if _not_survivable.any():
        df.loc[_not_survivable.values, _segment_scrub] = 0
        print(f'  scrubbed {int(_not_survivable.sum())} cash-burners from '
              f'segment/reinvest archetypes', file=sys.stderr)

    # ===== DURABILITY BASE-EFFECT SCRUB: a >500% single-year revenue spike
    # (M&A / one-off) contradicts a multi-year DURABILITY claim — it distorts
    # the "lindy" averages. Base-effect stays fine for GROWTH archetypes; here
    # it disqualifies the durability/consistency ones only. =====
    _spike = (pd.to_numeric(df.get('rev_yoy'), errors='coerce') > 5.0).fillna(False)
    _durable_arch = [c for c in ['arch_lindy_growth', 'arch_lindy_margin',
                     'arch_lindy_fcf', 'arch_tax_efficient', 'arch_low_sbc_quality',
                     'arch_durable_reinvestment', 'arch_cash_quality',
                     'arch_double_inflect', 'arch_quiet_compounder',
                     'arch_owner_operator'] if c in df.columns]
    if _spike.any():
        df.loc[_spike.values, _durable_arch] = 0
        print(f'  scrubbed {int(_spike.sum())} recent-spike names from '
              f'durability archetypes', file=sys.stderr)

    # ---------- FORENSIC-XR ASYMMETRY SCORE (user) ----------
    # Combine the forensic hidden-value signals with valuation and NORMALIZE to
    # size so names are comparable: express each hidden/unpriced asset as a
    # fraction of MARKET CAP (a $899M LIFO reserve at Ford vs a small-cap's is
    # then apples-to-apples). Sum the asset-like signals into a single
    # "hidden forensic value as a share of price", then rank the MOST ASYMMETRIC
    # names — those carrying the most hidden value per dollar of price where the
    # VISIBLE business is ALSO cheap (the hidden value is then pure upside) and
    # not melting. All levels are USD (EDGAR) over USD-normalized mcap.
    # (audit P0-2) DATA-QUALITY FLAG — computed HERE, BEFORE the forensic and
    # truly-XR scores, so both can be gated on it. It previously ran after them
    # and was never applied: 84 names failing the balance-sheet identity gate
    # kept positive forensic scores (SPRO ranked #8 on 3.93). A row whose
    # equity exceeds assets, whose tangible equity exceeds equity, whose cash
    # exceeds assets, or whose EBITDA is 2x revenue has a broken ledger — no
    # "hidden value" read on it is trustworthy. Flag, then zero the scores.
    _dq_as = _ncol('assets'); _dq_eq = _ncol('equity'); _dq_teq = _ncol('tangible_equity')
    _dq_cash = _ncol('cash'); _dq_rev = _ncol('revenue_ttm'); _dq_eb = _ncol('ebitda_ttm')
    df['data_quality_flag'] = (
        ((_dq_eq > _dq_as * 1.02) & _dq_eq.notna() & (_dq_as > 0))      # equity > assets
        | ((_dq_teq > _dq_eq * 1.02) & (_dq_eq > 0))                      # tangible equity > equity
        | ((_dq_cash > _dq_as * 1.02) & _dq_cash.notna() & (_dq_as > 0))  # cash > assets
        # (audit-2) EBITDA > 2x revenue is a broken-ledger tell for an OPERATING
        # company only: a financial / REIT / utility books investment gains and
        # spread income outside "revenue", so the leg over-fired on 63 of 219
        # (29% financials) and falsely demoted 80 names above \$1B. The three
        # balance-sheet identity legs above are never legitimately violated and
        # stay universal.
        | ((_dq_eb > _dq_rev * 2.0) & (_dq_rev > 0) & is_operating)       # EBITDA > 2x revenue (operating only)
    ).fillna(False).astype(int)
    # (audit-2) ELIGIBILITY for the forensic / truly-XR / value-unlock family =
    # clean ledger AND a COMMON-equity line. Warrants, units, rights and
    # preferreds (NIOBW, VAL-WT, GENVR) carry a tiny CLASS market cap, so
    # dividing whole-company hidden value by it manufactures a top-250 score
    # — the very inflation the ledger audit was about. These are SCORES, not
    # arch_ flags, so the audit's "no flags on non-common lines" check never
    # covered them; gate them here at the source so every consumer inherits it.
    # single source of truth: the same _is_noncommon the archetype scrub uses
    _dq_bad = (df['data_quality_flag'] == 1) | _is_noncommon.fillna(False)
    _dq_ok = (~_dq_bad).astype(float)
    # (audit-2 P0) the VALUE-UNLOCK family was not DQ-gated — DDI, NNDM, PXLW,
    # ACON leaked into the Value-Unlock tab. Gate it at the SOURCE so every
    # consumer (tab, archetype_count, truly-XR tells) inherits it.
    if 'value_unlock_score' in df.columns:
        df['value_unlock_score'] = (df['value_unlock_score'] * _dq_ok).round(3)
    for _vc in ('value_unlock_confirmed', 'arch_xr_value_unlock'):
        if _vc in df.columns:
            df[_vc] = (df[_vc].fillna(0).astype(int) * (~_dq_bad).astype(int)).astype(int)

    _fx_mc = mcap.where(mcap > 0)
    _cap2 = lambda x: x.clip(lower=0, upper=2.0)      # floor at 0 (assets only), cap so no artifact dominates
    # (audit P0-3) RECONCILED LEDGER: count only REALIZABLE value that is NOT
    # already in book, each leg ONCE, each haircut to what an owner actually
    # receives. The old sum double-counted the equity-method stake, added a
    # pension surplus that is already recognised in book, booked a DTA
    # valuation allowance at face value, and treated RPO — future revenue that
    # still needs future performance and cost — as a balance-sheet asset. In
    # the top 250, 54 names drew >=50% of their score from DTA + RPO alone.
    #  - LIFO reserve: its reversal is TAXABLE -> tax-effect at (1 - eff. rate)
    _fx_tax     = _ncol('effective_tax_rate').clip(0, 0.5).fillna(0.25)
    _fx_lifo    = _cap2(_ncol('lifo_reserve').clip(lower=0) * (1.0 - _fx_tax) / _fx_mc).fillna(0)
    #  - DTA valuation allowance: it exists precisely because realisation is
    #    judged NOT more-likely-than-not (ASC 740) -> 50% probability haircut,
    #    and only when the company is actually earning (a perpetual loss-maker's
    #    allowance never reverses).
    _fx_profitable = ((s('op_margin', np.nan) > 0) | (_num('roce') > 0)).fillna(False)
    _fx_dta     = _cap2(0.50 * _ncol('deferred_tax_valuation_allowance') / _fx_mc).where(_fx_profitable, 0).fillna(0)
    #  - equity-method stakes: the CARRYING value is on the balance sheet and is
    #    already inside _hidden_pct (investments_associates) — adding the raw
    #    stake here DOUBLE-COUNTED it (26 of the top 250 carried the identical
    #    amount twice). The genuinely hidden part is the disclosed FAIR-VALUE
    #    gap over carrying, so count em_fv_gap and nothing else.
    _fx_emgap   = _cap2(_ncol('em_fv_gap').clip(lower=0) / _fx_mc).fillna(0)
    _fx_hidden  = _cap2(_hidden_pct.where(_fx_coherent)).fillna(0)   # associates-at-carrying + net cash (fx-guarded)
    #  - pension funded status is ALREADY RECOGNISED on the balance sheet
    #    (ASC 715) -> adding it wholesale double-counts book. DROPPED.
    #  - RPO is transaction price allocated to UNSATISFIED obligations: future
    #    revenue requiring future performance and cost. It is an operating
    #    forecast, NOT a realizable asset. DROPPED from the asset ledger (it
    #    remains a SIGNAL for the contracted-backlog / deferred-revenue
    #    archetypes, which is where a forecast belongs).
    _forensic_hidden = (_fx_lifo + _fx_dta + _fx_emgap + _fx_hidden)
    # meaningless for financials/REITs (float / deposits distort every line)
    _forensic_hidden = _forensic_hidden.where(is_operating, 0.0)
    df['forensic_hidden_pct'] = _forensic_hidden.round(4)
    # asymmetry RANKING: hidden value per $ of price, but only where it is a
    # REAL, MONETIZABLE opportunity — a tradeable size (mcap>=$50M, else
    # dividing by a collapsed distressed mcap manufactures a 400%-of-mcap
    # artifact: CTRM/FBIO-type shells) and NOT melting (a melter cannot
    # monetize the hidden value). x1.5 when the visible business is ALSO cheap.
    _fx_eligible = ((_ncol('market_cap_usd') >= 50e6) & _not_melting.fillna(False))
    _fx_cheap = np.where(_excellent_value.fillna(False).values, 1.5, 1.0)
    # (audit P0-2) gated on the data-quality flag: a broken ledger earns no rank
    # CLEAN-ACCOUNTING confirmation (quarterly forensics: Beneish safe zone,
    # low accruals, no receivable/inventory divergence) lifts a hidden-value
    # rank by 15% — the value is less likely an accounting artifact. A boost
    # only: the red tells are surfaced as flags, never subtracted.
    _clean_mult = 1.0 + 0.15 * pd.to_numeric(df.get('fq_forensic_clean_confirm'), errors='coerce').fillna(0) \
        if 'fq_forensic_clean_confirm' in df.columns else 1.0
    df['forensic_xr_score'] = (df['forensic_hidden_pct'] * _fx_cheap
                               * _fx_eligible.astype(float) * _dq_ok * _clean_mult).round(4)

    # ===== TRULY-XR: forensic CONFLUENCE (the grossest, least-arbitraged
    # mispricings). Part II thesis: the biggest re-ratings are not one gap but
    # SEVERAL independent GAAP-vs-economic gaps STACKED in one cheap name, with a
    # MECHANICAL (self-executing) catalyst. We count DISTINCT forensic tells by
    # gap-GROUP (so sibling archetypes of one thesis count once — dedup by
    # construction), upweight names whose firing tells carry self-executing
    # catalysts, and gate to a cheap, tradeable, non-melting opportunity. A
    # "truly XR" setup requires >= 3 independent tells.
    _XR_GAP_GROUPS = {
        # gap-group : (member archetypes, mechanical/self-executing catalyst?)
        'expensed_growth':   (['arch_xr_growth_capex_masked', 'arch_expensed_growth_value'], False),      # G1 (semi)
        'segment_sotp':      (['arch_xr_hidden_segment_compounder', 'arch_xr_segment_justifies_whole',
                               'arch_xr_margin_mixshift'], False),                                        # G2 (disclosure/spin)
        'hidden_assets':     (['arch_hidden_assets', 'arch_xr_owned_realestate_value',
                               'arch_overdepreciated_assets', 'arch_lifo_hidden_reserve',
                               'arch_pension_overfunded', 'arch_tangible_value'], False),                 # G3 (sale/activist)
        'look_through':      (['arch_xr_look_through_value'], False),                                     # off-BS stakes
        'da_rolloff':        (['arch_xr_depreciation_cliff', 'arch_xr_amortization_mask'], True),         # G4 MECHANICAL (rolls off)
        'deferred_backlog':  (['arch_xr_contracted_backlog', 'arch_xr_deferred_revenue_lead',
                               'arch_xr_float_compounding'], True),                                       # G5 MECHANICAL (converts)
        'oneoff_discops':    (['arch_xr_oneoff_loss_mask', 'arch_xr_bigbath_rebound',
                               'arch_xr_discops_mask'], True),                                            # G6 MECHANICAL (annualises out/divested)
        'tax_shield':        (['arch_xr_nol_shield', 'arch_dta_reversal',
                               'arch_xr_cash_tax_advantage', 'arch_nol_shell'], True),                    # G7 MECHANICAL (release/burn)
        'cyclical':          (['arch_xr_cyclical_trough', 'arch_xr_double_trough',
                               'arch_xr_latent_bath_floor'], True),                                       # G8 MECHANICAL (mean-reversion)
        'margin_leverage':   (['arch_xr_peer_margin_gap', 'arch_xr_gross_margin_lead',
                               'arch_xr_pre_scale_margin', 'arch_xr_reusable_assembler',
                               'arch_xr_leverage_detonation'], False),                                    # G9 (execution)
        'crossover_mandate': (['arch_xr_gaap_profit_crossover'], True),                                   # G10 MECHANICAL (inclusion)
        'cash_earnings_gap': (['arch_xr_cash_leads_book'], False),                                       # accruals gap (E catches up to cash)
        'cannibal_return':   (['arch_xr_cannibal_below_cash', 'arch_xr_cannibal_below_tbook',
                               'arch_self_funded_returner', 'arch_xr_paydown_yield',
                               'arch_xr_verified_deleveraging',
                               'arch_xr_harvest_distribution'], False),                                   # buyback/return compounding
        'reorg_special':     (['arch_post_reorg', 'arch_special_situation', 'arch_spinoff_value',
                               'arch_spinoff_quality', 'arch_spinoff_asset'], True),                      # event-driven MECHANICAL
        'balance_floor':     (['arch_negative_ev_value', 'arch_xr_neg_ev_growth',
                               'arch_xr_clean_net_net', 'arch_xr_triple_floor'], False),                  # asset/net-cash floor
    }
    _tell_count = pd.Series(0, index=df.index)
    _mech_count = pd.Series(0, index=df.index)
    _tells_present = {}   # group -> bool Series
    for _g, (_members, _mech) in _XR_GAP_GROUPS.items():
        _mem = [c for c in _members if c in df.columns]
        _fired = (df[_mem].sum(axis=1) > 0) if _mem else pd.Series(False, index=df.index)
        _tells_present[_g] = _fired
        _tell_count = _tell_count + _fired.astype(int)
        if _mech:
            _mech_count = _mech_count + _fired.astype(int)
    df['truly_xr_tell_count'] = _tell_count.astype(int)
    df['truly_xr_mech_count'] = _mech_count.astype(int)
    # cheapness: the visible business must ALSO be cheap (a hidden gap is only XR
    # when the market prices the whole cheaply). Broad OR of value lenses.
    _truly_cheap = (_excellent_value.fillna(False)
                    | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 10.0))
                    | (fcf_yield >= 0.05)
                    | ((pb > 0) & (pb < 1.5))).fillna(False)
    _truly_eligible = (is_operating & (_ncol('market_cap_usd') >= 50e6)
                       & _not_melting.fillna(False))
    # score = independent tells x mechanical-catalyst upweight x cheapness, only
    # where tradeable/non-melting. Ranks the confluence; the flag is the >=3 bar.
    _truly_cheap_mult = np.where(_excellent_value.fillna(False).values, 1.5, 1.0)
    # (audit P0-2) both gated on the data-quality flag (DDI survived into
    # Truly-XR despite failing the balance-sheet identity gate)
    df['truly_xr_score'] = (_tell_count
                            * (1.0 + 0.20 * _mech_count)
                            * _clean_mult
                            * _truly_cheap_mult
                            * (_truly_cheap & _truly_eligible).astype(float)
                            * _dq_ok).round(3)
    df['truly_xr_flag'] = ((_tell_count >= 3) & _truly_cheap & _truly_eligible
                           & ~_dq_bad).astype(int)
    # human-readable breakdown: which gap-groups fire (mechanical marked *).
    # Vectorised elementwise string build (per-row .iloc over 14 groups x 46k
    # rows was needlessly slow).
    _acc = pd.Series('', index=df.index)
    for _g in _XR_GAP_GROUPS:
        _lbl = _g + ('*' if _XR_GAP_GROUPS[_g][1] else '')
        _acc = _acc + pd.Series(np.where(_tells_present[_g].values, _lbl + ', ', ''),
                                index=df.index)
    df['truly_xr_tells_str'] = _acc.str.rstrip(', ')

    # DATA-QUALITY FLAG (honest "flag, don't null/use"). A row that violates a
    # hard accounting identity has an internally inconsistent balance sheet, so
    # its level-based value signals are untrusted — flag it so value screens
    # (below-book, net-nets) can DEMOTE it rather than surface a corrupt-level
    # name as cheap. We flag, never null: the ratio may still be Yahoo-correct.
    # data_quality_flag is now computed EARLIER (before the forensic / truly-XR
    # scores, so they can be gated on it — audit P0-2); nothing to recompute here.

    # HOLDCO flag (#3): material non-controlling interest means the consolidated
    # cash/assets include SUBSIDIARY value not freely distributable to the parent
    # — a holdco whose net-cash is really subsidiary cash (Ayala/Aboitiz).
    _mi = _ncol('minority_interest'); _eqh = _ncol('equity')
    df['holdco_flag'] = (((_mi / _eqh.where(_eqh > 0)) >= 0.10)).fillna(False).astype(int)
    # CHINA/VIE risk flag (#4): Chinese / HK operating companies (often held via
    # offshore VIE shells) — cash reliability / repatriation risk. Flag, don't
    # exclude. (country is empty in the master; src is the reliable key.)
    _srcu = df['src'].astype(str).str.upper() if 'src' in df.columns else pd.Series('', index=df.index)
    _nm = df['name'].astype(str).str.lower() if 'name' in df.columns else pd.Series('', index=df.index)
    df['china_vie_flag'] = (_srcu.isin(['CN', 'HK'])
                            | _nm.str.contains('china|chinese', regex=True)).fillna(False).astype(int)

    # FORENSIC ADJUSTED BOOK (#6): start from TANGIBLE equity (strip goodwill /
    # intangibles), then ADD verified hidden assets (LIFO reserve, pension
    # surplus, disclosed JV-stake fair-value gap) and net the pension DEFICIT —
    # the true P/B a naive screen misses. adjusted_pb = mcap / adjusted_book.
    _teq_ab = _ncol('tangible_equity')
    # (audit P0-3) pension funded status is ALREADY recognised in book (ASC
    # 715) — adding it again double-counted; DROPPED. LIFO reversal is taxable
    # — tax-effected. em_fv_gap is the fair-value gap OVER carrying, genuinely
    # off-book, so it stays.
    _ab_tax = _ncol('effective_tax_rate').clip(0, 0.5).fillna(0.25)
    _adj_hidden = (_ncol('lifo_reserve').clip(lower=0).fillna(0) * (1.0 - _ab_tax)
                   + _ncol('em_fv_gap').clip(lower=0).fillna(0))
    # TYPE-APPROPRIATE book (per Cundill: value each on its OWN realizable book,
    # don't discard whole sectors). For a FINANCIAL the base already IS the right
    # number — tangible common equity, the standard bank/insurer valuation base
    # (goodwill stripped; LIFO/pension/stake legs are null for them). For a
    # REIT / property company GAAP carries real estate at cost LESS accumulated
    # depreciation, but land + buildings do not economically depreciate on that
    # schedule, so book UNDERSTATES NAV. Add back the accumulated depreciation
    # (the non-economic charge) — the analyst-standard NAV proxy — so a property
    # company is measured against its true asset value, not a depreciated stub.
    # (audit-2) EQUITY REITs only: a MORTGAGE REIT's assets are MBS/loans, not
    # depreciating property, so the add-back is meaningless there (NLY/Annaly
    # was the one remaining sub-1 flip, and a false one).
    _is_re_ab = (sector.astype(str).str.contains('Real Estate', case=False, na=False)
                 & ~_ind_all.str.contains('mortgage', na=False))
    # (audit #9) full accumulated depreciation is NOT a defensible NAV substitute
    # (no NOI / cap rate / maintenance capex behind it): 8 names flipped from
    # P/B >= 1 to adjusted < 1 on this leg alone ($85B aggregate). Some
    # depreciation IS economic (obsolescence, maintenance), so add back only
    # HALF, and never more than the tangible book itself — an estimate that
    # can narrow a discount, not manufacture one.
    # (audit-2) DATA-DRIVEN guard, robust to coarse GICS labels (this master
    # labels every REIT "Equity", so a "Mortgage" exclusion can never fire):
    # the add-back is only meaningful where PROPERTY is a material share of the
    # balance sheet. Below 20% (mortgage REITs, net-lease vehicles whose
    # properties sit in lease receivables — LOAN, BMNM, VICI, GLPI) it is
    # immaterial or mis-targeted, so it is not applied.
    _re_prop_share = (_ncol('ppe_gross') / _ncol('assets').where(_ncol('assets') > 0))
    _re_navback = (0.50 * _ncol('accumulated_depreciation').clip(lower=0).fillna(0)
                   ).clip(upper=_teq_ab.clip(lower=0).fillna(0)) \
                   .where(_is_re_ab & (_re_prop_share >= 0.20), 0.0)
    df['adjusted_book'] = (_teq_ab + _adj_hidden + _re_navback).round(0)
    _adjb = df['adjusted_book']
    # adjusted_book is master-currency (EDGAR USD, or FMP converted to the
    # listing currency), so it is priced with the LISTING-currency cap; the
    # USD cap over a JPY-denominated book read ~150x off. (Identical for US.)
    _mc_ab = _ncol('market_cap').where(_ncol('market_cap') > 0)
    df['adjusted_pb'] = (_mc_ab / _adjb.where(_adjb > 0)).round(3)
    # quality-adjusted net-net: NNWC (haircut) as a multiple of market cap
    _mc_usd_nn = _ncol('market_cap_usd').fillna(mcap)
    df['nnwc_pct_mcap'] = (_ncol('nnwc') / _mc_usd_nn.where(_mc_usd_nn > 0)).round(3)

    # (user) archetype_count feeds convergence_score / archetype_asymmetry
    # (the density-ranked books), so a name that fires SEVERAL variants of ONE
    # thesis was over-credited. Collapse ONLY genuine same-thesis THRESHOLD
    # variants (a stricter refinement of the same signal) to count once —
    # deliberately NOT distinct-but-correlated lenses (net-cash vs hidden-
    # assets, the Wolf/liger/lindy facets), which are real independent
    # confirmations and stay counted separately.
    _DEDUP_CLUSTERS = [
        ['arch_tenbagger_path', 'arch_tenbagger_credible'],   # credible = stricter path
        ['arch_bab_low_beta', 'arch_bab_multibagger'],        # one betting-against-beta signal
        ['arch_asleep_at_wheel', 'arch_asleep_unrerated'],    # unrerated = refined asleep
        # (audit 3) same-thesis variants counted once
        ['arch_analyst_awakening', 'arch_analyst_rerating_confirmed'],
        ['arch_cannibal_at_discount', 'arch_xr_cannibal_below_tbook', 'arch_cluseau_buyback_accel'],
        ['arch_customer_float', 'arch_xr_float_compounding', 'arch_xr_deferred_revenue_lead'],
        ['arch_double_inflect', 'arch_roic_inflect', 'arch_kpi_threshold'],
        ['arch_dta_reversal', 'arch_nol_shell', 'arch_xr_nol_shield'],
        ['arch_durable_reinvestment', 'arch_cash_reinvest', 'arch_reinvest_inflect'],
        ['arch_exceptional_evsg', 'arch_cheap_sales_scaler'],
        ['arch_expensed_growth_value', 'arch_xr_pre_scale_margin'],
        ['arch_discounted_vehicle', 'arch_negative_ev_value', 'arch_tangible_value', 'arch_oak_asset_floor'],
        ['arch_owner_earnings_power', 'arch_overdepreciated_assets'],
        ['arch_tax_verified_earnings', 'arch_understated_earnings', 'arch_cash_quality'],
        # (audit 4) literal subsets: turn / accel each AND one fact onto fallen + deep value
        ['arch_mb_fallen_deep_value', 'arch_mb_fallen_value_turn', 'arch_mb_fallen_value_accel'],
    ]
    # (audit 3) DESCRIPTORS and MODIFIERS carry no thesis of their own and must
    # not add density: a negative risk flag (concentrated_segments), a mix
    # label (diversified_segments, geographic_global) and a modifier on other
    # members (forensic_payout_confirmed) are surfaced but not counted
    _NOT_COUNTED = {'arch_concentrated_segments', 'arch_diversified_segments',
                    'arch_geographic_global', 'arch_forensic_payout_confirmed'}
    _clustered = {c for cl in _DEDUP_CLUSTERS for c in cl if c in df.columns}
    _independent = [c for c in arch_cols if c not in _clustered and c not in _NOT_COUNTED]
    _count = df[_independent].sum(axis=1)
    for _cl in _DEDUP_CLUSTERS:
        _mem = [c for c in _cl if c in df.columns]
        if _mem:
            _count = _count + (df[_mem].sum(axis=1) > 0).astype(int)  # cluster contributes at most 1
    df['archetype_count'] = _count
    df['archetype_tags_str'] = df[arch_cols].apply(
        lambda r: ', '.join(pretty[c] for c in arch_cols if r[c] == 1),
        axis=1,
    )

    # EFFECTIVE values after the global fills, under distinct names so a book or
    # audit can read what the recipes actually used (the master's own columns
    # are pre-fill and US-only for these):
    #   roic_lindy_eff    EDGAR lindy ROIC, else the FMP statement-history one
    #   capret_yield_eff  the capital-return yield arch_capital_returner gated
    #                     on — max(capital_return_yield, dividend + buyback),
    #                     all post-fill (currency-safe decomposition)
    if 'roic_lindy' in df.columns:
        df['roic_lindy_eff'] = pd.to_numeric(df['roic_lindy'], errors='coerce')
    _cry_e = pd.to_numeric(df.get('capital_return_yield'), errors='coerce') if 'capital_return_yield' in df.columns else pd.Series(np.nan, index=df.index)
    _dy_e = pd.to_numeric(df.get('dividend_yield'), errors='coerce') if 'dividend_yield' in df.columns else pd.Series(np.nan, index=df.index)
    _by_e = pd.to_numeric(df.get('buyback_yield'), errors='coerce') if 'buyback_yield' in df.columns else pd.Series(np.nan, index=df.index)
    _tot_e = (_dy_e.fillna(0) + _by_e.fillna(0)).where(_dy_e.notna() | _by_e.notna())
    df['capret_yield_eff'] = pd.concat([_cry_e, _tot_e], axis=1).max(axis=1)

    # POST-FILL ("effective") copies of every FMP-fillable gate input, so the
    # methodology audit re-verifies FMP-filled firers on the values the gates
    # actually saw (the master columns it reads are pre-fill, which made those
    # checks pass vacuously on filled rows). _eff suffix: no collision with the
    # master's own column names when books merge the tags frame.
    # (audit) the gates read the FMP-filled tax rate (local effective_tax_rate);
    # write it back so the _eff copy and the tax_efficient spirit lens see it too
    df['effective_tax_rate'] = effective_tax_rate
    for _c in _EFF_COLS:
        if _c in df.columns:
            df[_c + '_eff'] = pd.to_numeric(df[_c], errors='coerce')

    # Multi-year fundamental data present from EITHER source (EDGAR or the FMP
    # statement / quarterly engines). enrich uses this to decide which names are
    # eligible for the full archetype taxonomy: once FMP fills the EDGAR-only
    # inputs, a non-US name with FMP history can fire those archetypes, so it
    # must also be counted against the full denominator (else its archetype
    # density would be inflated).
    _mm = pd.Series(False, index=df.index)
    for _c in ('roic_lindy', 'fmp_st_roic_lindy', 'n_yrs_positive_fcf'):
        if _c in df.columns:
            _mm |= pd.to_numeric(df[_c], errors='coerce').notna()
    if 'fmp_q_status' in df.columns:
        _mm |= (df['fmp_q_status'].astype(str) == 'ok')
    df['multi_year_data'] = _mm.astype(int)

    # Compact per-name digest of every active FMP-derived signal, so any book
    # can show the FMP layer in one readable column (country books included).
    _sig_defs = [
        ('fmp_piotroski_strong_flag', 'Piotroski>=7'), ('fmp_distress_flag', 'AltmanDistress'),
        ('fmp_insider_aligned_flag', 'InsiderAligned'),
        ('fmp_earnings_cash_backed_flag', 'CashBackedEPS'),
        ('fmp_low_earnings_quality_flag', 'LowEarnQuality'),
        ('fmp_customer_float_flag', 'CustomerFloat'), ('fmp_rd_intensive_flag', 'R&D>=10%'),
        ('fmp_levered_returns_flag', 'LeveredROE'),
        ('fmp_dyn_growth_streak_flag', 'Streak6q+'), ('fmp_dyn_accelerating_flag', 'RevAccel'),
        ('fmp_dyn_op_leverage_flag', 'OpLeverage'), ('fmp_dyn_unrerated_flag', 'Unrerated'),
        ('fmp_dyn_fwd_inflection_flag', 'FwdEBITCross'), ('fmp_dyn_forward_asleep_flag', 'FwdAsleep'),
        ('arch_institutional_accumulation', 'InstAccum'), ('inst_accum_accelerating', 'InstAccel'),
        # quarterly 3-statement forensics (red tells first, then green)
        ('fq_beneish_risk_flag', 'BeneishRisk'), ('fq_beneish_ma_distorted', 'BeneishM&A'),
        ('fq_high_accruals_flag', 'HighAccruals'),
        ('fq_receivables_divergence_flag', 'RecvDiverge'), ('fq_inventory_build_flag', 'InvBuild'),
        ('fq_sbc_heavy_flag', 'SBC>=30%CFO'),
        ('fq_cash_leads_earnings_flag', 'CashLeadsBook'), ('fq_wc_release_flag', 'WCRelease'),
        ('fq_deleveraging_flag', 'Deleveraging'), ('fq_gm_inflection_flag', 'GMInflect'),
        ('fq_defrev_build_flag', 'DefRevBuild'), ('fq_cash_tax_shield_flag', 'CashTaxShield'),
        ('fq_forensic_clean_confirm', 'ForensicClean'),
        ('segment_rot_flag', 'SegCoreRot'),
        ('arch_coiled_base', 'CoiledBase'), ('arch_base_ignition', 'BaseIgnition'),
        ('arch_coiled_fallen_angel', 'CoiledFallenAngel'), ('arch_ignition_fallen_angel', 'IgnitionFallenAngel'),
        ('sent_warming_flag', 'SentWarming'), ('sent_cooling_flag', 'SentCooling'),
        ('sent_discovery_flag', 'NewCoverage'), ('sent_skeptic_flag', 'StreetSkeptic'),
    ]
    _sig = pd.Series('', index=df.index)
    for _col, _tag in _sig_defs:
        if _col in df.columns:
            _on = pd.to_numeric(df[_col], errors='coerce').fillna(0) == 1
            _sig = _sig.where(~_on, _sig + ' · ' + _tag)
    if 'fmp_geo_em_share' in df.columns:
        _on = pd.to_numeric(df['fmp_geo_em_share'], errors='coerce') >= 0.50
        _sig = _sig.where(~_on.fillna(False), _sig + ' · EMrev>=50%')
    # ===== SPIRIT SCORES (continuous, per tiered archetype) =====
    # How strongly a core member embodies the archetype's OWN thesis, read
    # through several independent lenses so no single accounting treatment
    # decides it: each lens is ranked WITHIN the core (pct), the spirit score is
    # the mean of the available lens ranks (>= half the lenses required).
    # exceptional = spirit >= 0.75, elite = spirit >= 0.90 — absolute bars on the
    # mean lens rank (~7% / ~0.7% of spirited members, not a quartile) — "exceptional in
    # the archetype's own terms", continuous, never a bolted-on negative gate.
    _c = lambda c: pd.to_numeric(df[c], errors='coerce') if c in df.columns else pd.Series(np.nan, index=df.index)
    _SPIRIT = {
        'lindy_margin': [(_c('tc_min_opm'), 1), (_c('tc_med_opm'), 1), (_c('op_margin_lindy'), 1),
                         (_c('ebitda_margin_lindy'), 1), (_c('tc_min_gm'), 1), (_c('tc_years'), 1)],
        'lindy_fcf': [(_c('tc_fcf_pos') / _c('tc_fcf_years'), 1), (_c('tc_fcf_years'), 1),
                      (_c('tc_fcf_margin_avg'), 1), (_c('cash_roic_lindy'), 1), (_c('ts_maxdd_5y'), 1)],
        'no_dilution': [(_c('shares_growth_5y'), -1), (_c('shares_growth_3y'), -1), (_c('roic_lindy'), 1),
                        (_c('cash_roic_lindy'), 1), (_c('fqx_fcf_ps_g'), 1)],
        'capital_returner': [(_c('capret_yield_eff'), 1), (_c('tc_uncov_payout_3y'), -1),
                             (_c('evt_div_raise_streak'), 1),
                             (_c('fmp_st_financing_outflow_years') / _c('fmp_st_financing_years'), 1)],
        'weinstein_stage2': [(_c('ts_mrs'), 1), (_c('ts_ma30_slope13'), -1), (_c('ts_vol_spike4'), 1),
                             (_c('ts_dist_hi52'), 1)],
        'kullamagie_breakout': [(_c('ts_rs_raw'), 1), (_c('ts_tight5'), -1), (_c('ts_dist_hi52'), 1),
                                (_c('ts_dvol26_usd'), 1)],
        'oneil_canslim': [(_c('fqx_eps_q_yoy'), 1), (_c('fqx_eps_accel'), 1), (_c('ts_rs_pct_mkt'), 1),
                          (_c('ts_dist_hi52'), 1), (_c('fqx_eps_pos_share_8'), 1)],
        'analyst_rerating_confirmed': [(_c('ts_dist_hi260'), 1), (_c('ts_mrs'), 1),
                                       (_c('sent_buy_share_d12'), 1), (_c('sent_pt_rev_q'), 1)],
        'analyst_awakening': [(_c('sent_buy_share_d12'), 1), (_c('sent_upgrades_12m') - _c('sent_downgrades_12m'), 1),
                              (_c('sent_pt_rev_q'), 1), (_c('ts_mrs') - _c('ts_mrs_13ago'), 1),
                              (_c('evt_pt_rev_90d'), 1)],
        # all lags, longer the stronger: total lag across horizons, how long
        # it has lagged, how pervasive it is, and ignored hard evidence
        'narrative_lag': [(_c('narrative_lag_extent'), 1), (_c('narrative_lag_years'), 1),
                          (_c('narrative_lag_lenses'), 1), (_c('evt_ignored_beats_2y'), 1)],
        # grew into its valuation: how much multiple the growth absorbed, for
        # how long, how much the per-share earnings power compounded, whether
        # it grew into profitability, and how much premium is left
        'derate_through_growth': [(_c('fmp_st_sales_ps_5y_g').fillna(_c('fmp_st_sales_ps_3y_g')), 1),
                                  (_c('fmp_st_ebit_ps_5y_g').fillna(_c('fmp_st_ebit_ps_3y_g')), 1),
                                  (_c('fmp_st_fcf_ps_5y_g').fillna(_c('fmp_st_fcf_ps_3y_g')), 1),
                                  (_c('op_margin'), 1), (_c('derate_growth_share'), 1),
                                  (_c('derate_growth_absorbed'), 1),
                                  (_c('derate_growth_years'), 1),
                                  (_c('ev_sales').where(_c('ev_sales') > 0), -1)],
        'asleep_at_wheel': [(_c('evt_beat_share_8q'), 1), (_c('evt_surprise_4q'), 1),
                            (_c('avg_earnings_surprise'), 1), (_c('earnings_beat_streak'), 1),
                            (_c('evt_ignored_beats_2y'), 1)],
        'asleep_unrerated': [(_c('unrerated_gap_1y'), 1), (_c('bs_coil_rev'), 1),
                             (_c('evt_ignored_beats_2y'), 1), (_c('evt_react_beats_4q'), -1)],
        'evsales_derating': [(_c('derate_gap_1y'), 1), (_c('bs_coil_rev'), 1), (_c('fq_rev_growth'), 1),
                             (_c('fqx_inc_ebit_margin'), 1)],
        'lynch_pegy': [(_c('lynch_pegy_ttm'), -1), (_c('fqx_eps_pos_share_8'), 1), (_c('fqx_ni_ttm_g'), 1)],
        'lynch_evgy': [(_c('lynch_evgy_durable'), -1), (_c('fqx_ebit_ttm_g'), 1)],
        'owner_operator': [(_c('insider_ownership_pct'), 1), (_c('fmp_insider_alignment_ratio'), 1),
                           (_c('shares_growth_3y'), -1), (_c('roic_lindy'), 1)],
        'flyover': [(_c('roic_lindy'), 1), (_c('sent_n_analysts'), -1), (_c('insider_ownership_pct'), 1),
                    (_c('tc_fcf_pos') / _c('tc_fcf_years'), 1)],
        'blindspot': [(_c('sent_n_analysts'), -1), (_c('ts_dvol26_usd'), -1), (_c('fcf_yield'), 1),
                      (_c('ev_ebitda').where(_c('ev_ebitda') > 0), -1)],
        'liger_neglected_survivor': [(_c('fqx_ebit_ttm_g'), 1), (_c('fqx_inc_ebit_margin'), 1),
                                     (_c('sent_n_analysts'), -1), (_c('ev_sales').where(_c('ev_sales') > 0), -1)],
    }
    # (endpoint matrix) augmented archetypes: the matrix's EXCEPTIONAL measures
    # live here, as continuous lenses in the archetype's own terms, instead
    # of tightening the gate. ts_maxdd_5y is the "price-lindy" lens (a
    # shallower 5-year drawdown = the owners were never asked to sit through
    # a collapse).
    _pos = lambda x: x.where(x > 0)
    _opm_c = _c('op_margin')
    _SPIRIT.update({
        'capital_discipline': [(_c('fmp_st_financing_outflow_years') / _c('fmp_st_financing_years'), 1),
                               (_c('tc_uncov_payout_3y'), -1), (_c('shares_growth_5y'), -1), (_c('roce'), 1)],
        'dead_option': [(_c('ts_dist_hi260'), -1), (_c('ts_r13'), 1),
                        (_c('tc_fcf_pos') / _c('tc_fcf_years'), 1), (_c('fcf_yield'), 1)],
        'kpi_threshold': [(_c('fqx_inc_ebit_margin_dt'), 1), (_c('fqx_eps_pos_share_8'), 1),
                          (_c('evt_surprise_4q'), 1), (_c('ebitda_margin_delta_yoy'), 1)],
        'durable_reinvestment': [(_c('roiic_lindy'), 1), (_c('roic_lindy'), 1), (_c('ts_maxdd_5y'), 1),
                                 (_c('fqx_ebit_ttm_g'), 1)],
        'cheap_per_roiic': [(_c('cheap_per_roiic_lindy'), -1), (_c('cash_roiic_lindy'), 1),
                            (_c('asset_3y_cagr'), 1)],
        'strong_coverage': [(_c('tc_min_ic'), 1), (_c('interest_coverage'), 1), (_c('net_cash_pct_mcap'), 1),
                            (_c('tc_fcf_pos') / _c('tc_fcf_years'), 1)],
        'lindy_growth': [(_c('fq_rev_growth') - 0.5 * _c('revenue_5y_cagr'), 1), (_c('ts_maxdd_5y'), 1),
                         (_c('revenue_5y_cagr'), 1), (_c('revenue_acceleration_lindy'), 1)],
        'buyback_compounder': [(_c('shares_growth_5y'), -1), (_c('shares_growth_3y'), -1),
                               (_c('roic_lindy'), 1), (_c('buyback_yield'), 1)],
        'qarp': [(_c('roiic_lindy'), 1), (_c('ts_maxdd_5y'), 1), (_c('fqx_ebit_ttm_g'), 1),
                 (_pos(_c('ev_ebitda')), -1)],
        'cash_quality': [(_c('cash_roic_lindy') - _c('roic_lindy'), 1), (_c('ts_maxdd_5y'), 1),
                         (_c('fq_cash_leads_earnings_flag'), 1), (_c('fq_cfo_to_ni'), 1)],
        'capital_light_pivot': [(_c('roic_acceleration'), 1), (_c('fqx_roic_ttm') - _c('roic_lindy'), 1),
                                (_c('revenue_3y_cagr') - _c('asset_3y_cagr'), 1)],
        'bab_low_beta': [(_c('ts_beta_3y_rk'), -1), (_c('ts_down_capture_3y'), -1), (_c('roce'), 1),
                         (_c('fcf_margin'), 1)],
        'bab_multibagger': [(_c('ts_beta_3y_rk'), -1), (_c('ts_down_capture_3y'), -1),
                            (_c('yartseva_score'), 1), (_c('fcf_yield'), 1)],
        'bab_becoming': [(_c('ts_beta_3y_rk') - _c('ts_beta_1y_rk'), 1),
                         (1 - _c('ts_vol_1y') / _pos(_c('ts_vol_3y')), 1), (_c('ebitda_margin_delta_yoy'), 1)],
        'fixed_cost_demand_shock': [(_c('fqx_inc_ebit_margin_dt'), 1), (_c('fq_rev_growth'), 1),
                                    (_c('tc_med_opm') - _opm_c, 1), (_c('ebitda_margin_delta_yoy'), 1)],
        'regime_cyclical': [(_c('tc_med_opm') - _opm_c, 1), (_c('fqx_ebit_ttm_g'), 1), (_c('ts_dist_hi260'), -1)],
        'net_cash_returner': [(_c('tc_uncov_payout_3y'), -1), (_c('net_cash_pct_mcap'), 1),
                              (_c('capital_return_yield'), 1)],
        'wolf_compounder': [(_c('evt_beats_8q'), 1), (_c('fqx_eps_accel'), 1), (_c('fqx_inc_ebit_margin_dt'), 1),
                            (_c('rev_yoy'), 1)],
        'xr_quality_crisis': [(_c('tc_min_opm'), 1), (_c('ts_dist_hi260'), -1), (_c('fq_rev_growth'), 1),
                              (_c('roic_lindy'), 1)],
        'xr_forced_seller': [(_c('fmp_inst_own_chg_q0'), -1), (_c('ts_r52'), -1), (_c('fq_rev_growth'), 1)],
        'xr_cyclical_trough': [(_c('tc_med_opm') - _opm_c, 1), (_pos(_c('pb')), -1), (_c('ts_dist_hi260'), -1)],
        'oak_order_conversion': [(_c('fqx_inc_ebit_margin_dt'), 1), (_c('fq_rev_growth'), 1),
                                 (_c('fq_defrev_growth_minus_rev'), 1), (_c('ebitda_margin_delta_yoy'), 1)],
        'insider_conviction': [(_c('ts_dist_hi52'), -1), (_c('insider_distinct_buyers'), 1),
                               (_c('fmp_insider_alignment_ratio'), 1)],
        'xr_audited_streak_unrerated': [(_c('xr_streak_norerate_lenses'), 1), (_c('unrerated_gap_1y'), 1),
                                        (_c('fmp_dyn_unrerated_gap'), 1)],
        'templeton_pessimism': [(_c('ts_dist_hi260'), -1), (_pos(_c('ev_norm_midcyc')), -1), (_c('tc_min_opm'), 1)],
        # (event study) the measured ingredients, each its own lens: depth of
        # the prior fall, the coil, abnormal volume, relative strength turning
        'coiled_fallen_angel': [(_c('bs_prior_dd'), -1), (_c('bs_coil_rev'), 1), (_c('bs_coil_ebit'), 1),
                                (_c('bs_cp_dvol_z13'), 1), (_c('bs_rs26'), 1), (_c('sent_n_analysts'), -1)],
        'ignition_fallen_angel': [(_c('bs_prior_dd'), -1), (_c('bs_cp_dvol_z13'), 1), (_c('bs_dvol_trend'), 1),
                                  (_c('bs_updown_vol'), 1), (_c('bs_rs26'), 1), (_c('bs_coil_rev'), 1)],
        # (endpoint matrix) the measured seal: a DIP on a beat (more negative
        # reaction = better entry), the beat record, EPS acceleration
        'wolf_seal': [(_c('evt_react_last').where(_c('evt_beats_8q') >= 1), -1), (_c('evt_beats_8q'), 1),
                      (_c('fqx_eps_accel'), 1), (_c('fqx_ebit_ttm_g'), 1)],
        'self_funded_returner': [(_c('tc_uncov_payout_3y'), -1),
                                 (_c('fmp_st_financing_outflow_years') / _c('fmp_st_financing_years'), 1),
                                 (_c('fcf_yield'), 1), (_c('tc_fcf_pos') / _c('tc_fcf_years'), 1)],
        'dividend_verified_value': [(_c('evt_div_raise_streak'), 1), (_c('evt_div_cut_2y'), -1),
                                    (_c('tc_uncov_payout_3y'), -1), (_c('dividend_yield'), 1)],
        'spinoff_quality': [(_c('insider_distinct_buyers'), 1), (_c('roce'), 1), (_c('op_margin'), 1)],
        # index candidacy: US listing not yet in the S&P 500, investable float,
        # size — the mandate-unlocked buyer base
        'xr_gaap_profit_crossover': [(1 - _c('evt_sp500_member'), 1), (_c('evt_free_float'), 1),
                                     (_c('market_cap_usd'), 1), (_c('op_margin'), 1)],
        # multibagger pre-conditions: depth of the fall, depth of the value,
        # and the strength of the pattern's own trigger
        'mb_fallen_deep_value': [(_c('ts_dist_hi260'), -1), (_c('ev_ebit').where(_c('ev_ebit') > 0), -1),
                                 (_c('pb').where(_c('pb') > 0), -1), (_c('fcf_yield'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                                 (_c('rel_ind_ev_ebit'), -1), (_c('vs_ind_dist_hi260'), -1),
                                 # audit 3: the fresh low, the asset floor, and not too far gone (Wolf's reject rule)
                                 (_c('ts_wks_since_lo260'), -1), (_c('ncav_pct_mcap'), 1), (_c('fmp_altman_z'), 1)],
        'mb_fallen_value_turn': [(_c('ts_dist_hi260'), -1), (_c('ev_ebit').where(_c('ev_ebit') > 0), -1),
                                 (_c('fqx_ebit_ttm_g'), 1), (_c('fcf_yield'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                                 # audit 3: the turn the market shrugged at, and how recent it is
                                 (_c('fqx_m_since_turn_positive'), -1), (_c('evt_react_last'), -1), (_c('evt_ignored_beats_2y'), 1)],
        'mb_fallen_value_accel': [(_c('ts_dist_hi260'), -1), (_c('ev_ebit').where(_c('ev_ebit') > 0), -1),
                                  (_c('rev_accel'), 1), (_c('fq_rev_growth'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                                  (_c('ts_wks_since_lo260'), -1), (_c('fcf_yield'), 1)],
        'mb_fallen_stressed': [(_c('ts_dist_hi260'), -1), (_c('ev_sales').where(_c('ev_sales') > 0), -1),
                               (_c('fqx_ebit_ttm_g'), 1), (_c('cfo_yield'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                               # audit 3: the stress must RESOLVE — debt falling, interest covered, not too far gone
                               (_c('fq_netdebt_decline_months'), 1), (_c('fq_interest_cover'), 1),
                               (_c('fmp_st_financing_outflow_years'), 1), (_c('fmp_altman_z'), 1)],
        'mb_fallen_insider': [(_c('ts_dist_hi260'), -1), (_c('usf_ins_buy_quarters_4q'), 1),
                              (_c('insider_distinct_buyers'), 1), (_c('market_cap_usd'), -1),
                              # §1: buybacks alongside the insiders (1.7x), reinvesting (capex, 1.6x),
                              # LEVERAGE present (low debt lowered the odds to 0.4x), deep value
                              # (1.5x); §2 fresh low (1.3x vs 0.2x for a 1-2 year-old low)
                              (_c('buyback_yield'), 1), (_c('capex_intensity'), 1), (_c('debt_to_equity'), 1),
                              (_c('pb').where(_c('pb') > 0), -1), (_c('ts_wks_since_lo260'), -1)],
        'mb_fallen_trough': [(_c('ts_dist_hi260'), -1), (_c('tc_med_opm') - _c('op_margin'), 1),
                             (_c('rev_accel'), 1), (_c('tc_min_opm'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                             # audit 3: a cyclical trough is the INDUSTRY's too; survival through it
                             (_c('ind_tape_opm_d1'), -1), (_c('fq_interest_cover'), 1), (_c('tc_opinc_pos'), 1)],
        'mb_fallen_below_cycle': [(_c('ts_dist_hi260'), -1), (_c('tc_med_opm') - _c('op_margin'), 1),
                                  (_c('ev_sales_change_yoy'), -1), (_c('tc_opinc_pos'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1), (_c('ts_wks_since_lo260'), -1),
                                 # operator-study refinement: sell side unturned (2.6x), buy share LOW
                                 # (2.1x), few analysts (2.0x), R&D present, volatile (vol LOW 0.4x)
                                 (_c('mb_fund_up_unturned'), 1), (_c('sent_buy_share'), -1), (_c('sent_n_analysts'), -1),
                                 (_c('fmp_rd_to_revenue'), 1), (_c('ts_vol_1y'), 1),
                                 # audit 3: survival through the cycle; the price test moved here from the core
                                 (_c('fq_interest_cover'), 1), (_c('tc_opinc_pos'), 1), (_c('price_vs_5y_avg'), -1)],
        'mb_inflecting_operator': [(_c('op_margin_delta_yoy'), 1), (_c('fqx_ebit_ttm_g'), 1),
                                   (_c('fqx_roic_ttm') - _c('roic_lindy'), 1), (_c('fqx_inc_ebit_margin_dt'), 1),
                                 (_c('market_cap_usd'), -1), (-_evt_age_days('evt_sc13d_date'), 1),
                                   # audit 3: the perception half (FORENSICS §5: winners had the weaker tape)
                                   (_c('evt_react_last'), -1), (_c('ts_r13'), -1), (_c('sent_n_analysts'), -1),
                                   (_c('rel_ind_ev_ebit'), -1)],
        'mb_quiet_turn': [(_c('ts_r13'), -1), (_c('ts_dist_hi52'), -1), (_c('rev_accel'), 1),
                          (_c('fqx_opm_slope8'), 1), (_c('fqx_roic_slope8'), 1), (_c('nl_sales_1y'), 1),
                          (_c('ev_sales_change_yoy'), -1), (_c('market_cap_usd'), -1)],
        # the forensic lenses: weaker recent tape, deeper fall, cheaper vs own
        # history, larger sales-per-share divergence, smaller, informed buyers
        'mb_left_for_dead_value': [(_c('ts_dist_hi260'), -1), (_c('ts_dd_time_share_260'), 1),
                                   (_c('pb').where(_c('pb') > 0), -1), (_c('p_s').where(_c('p_s') > 0), -1),
                                   (_c('nl_sales_3y'), 1), (_c('market_cap_usd'), -1),
                                   # §1 refinements: FCF streak at zero (2.1x), insiders / a rising
                                   # 13D holder (1.7-2.0x), headcount growth (1.9x), a FALLING buy
                                   # share (1.9x), long since the last upgrade (1.6x); §2 fresh low
                                   (_c('fqx_fcfm_streak'), -1), (_c('usf_ins_buy_quarters_4q'), 1),
                                   (-_evt_age_days('evt_sc13d_date'), 1), (_c('usf_emp_g1'), 1),
                                   (_c('sent_buy_share_d12'), -1), (_c('sent_months_since_up'), 1),
                                   (_c('ts_wks_since_lo260'), -1), (_c('gross_margin'), -1),
                                   # operator study: the 10x names sat at their PEER GROUP'S lowest
                                   # multiple and lowest returns (industry frame, sector fallback)
                                   (_c('rel_ind_ev_ebit'), -1), (_c('rel_ind_roce'), -1), (_c('vs_ind_r52'), -1),
                                   # operator-study refinement: 13F holders increasing (2.7x), R&D present
                                   # (R&D LOW 0.32x), ROE not high (0.36x), weak 26w vs the industry
                                   (_c('fmp_inst_shares_chg_pct_q0'), 1), (_c('fmp_rd_to_revenue'), 1),
                                   (_c('roe'), -1), (_c('vs_ind_r26'), -1)],
        'mb_conviction_confluence': [(_c('mb_smart_money_legs'), 1), (_c('usf_ins_buy_quarters_4q'), 1),
                                     (_c('buyback_yield'), 1), (_c('ts_dist_hi260'), -1),
                                     (_c('ts_wks_since_lo260'), -1), (_c('market_cap_usd'), -1)],
        'mb_left_for_dead_insider': [(_c('fqx_fcfm_streak'), -1), (_c('usf_ins_buy_quarters_4q'), 1),
                                     (_c('pb').where(_c('pb') > 0), -1), (_c('ts_dist_hi260'), -1),
                                     (_c('ts_wks_since_lo260'), -1), (_c('buyback_yield'), 1)],
        'mb_fallen_ignored_believers': [(_c('ts_dist_hi260'), -1), (_c('sent_buy_share'), 1),
                                        (_c('sent_n_analysts'), -1), (_c('nl_sales_1y'), 1),
                                        (_c('ts_r13'), -1), (_c('market_cap_usd'), -1),
                                        # audit 3: the study's own refinements — target premium, institutions arriving, ratings fresh
                                        (_c('evt_pt_prem_12m'), 1), (_c('fmp_inst_shares_chg_pct_q0'), 1), (_c('sent_months_since_up'), -1)],
        'mb_smart_money_wreckage': [(_c('mb_smart_money_legs'), 1), (_c('ts_dist_hi260'), -1), (_c('sent_buy_share'), 1), (_c('fq_dio'), 1),
                                    (_c('usf_ins_buy_quarters_4q'), 1), (-_evt_age_days('evt_sc13d_date'), 1),
                                    (_c('usf_emp_g1'), 1), (_c('pb').where(_c('pb') > 0), -1),
                                    (_c('market_cap_usd'), -1),
                                    # §1: few analysts (1.35x), reinvesting (1.3x); §2 fresh low (1.35x)
                                    (_c('sent_n_analysts'), -1), (_c('capex_intensity'), 1),
                                    (_c('ts_wks_since_lo260'), -1),
                                    # operator-study refinement: leverage present (low debt/assets 0.35x),
                                    # gross-margin streak (1.8x), net cash NOT high (0.46x)
                                    (_c('debt_to_equity'), 1), (_c('fqx_gm_streak'), 1), (_c('net_cash_pct_mcap'), -1)],
        'mb_grew_into_valuation_turning': [(_c('derate_growth_absorbed'), 1), (_c('fqx_opm_slope8'), 1),
                                           (_c('fqx_opm_consist'), 1), (_c('fq_rev_growth'), 1),
                                           (_c('ts_r13'), -1), (_c('sent_n_analysts'), -1),
                                           # audit 3: the multiple now fair (Sub-B "already re-rated"), turn recent
                                           (_c('fmp_dyn_ev_sales_change_3y'), -1), (_c('ev_ebit').where(_c('ev_ebit') > 0), -1),
                                           (_c('fqx_m_since_turn_positive'), -1)],
        'mb_tree_recipe': [(_c('ts_vol_1y'), 1), (_c('market_cap_usd'), -1), (_c('ts_dist_hi260'), -1),
                           (_c('p_s').where(_c('p_s') > 0), -1), (_c('nl_sales_1y'), 1), (_c('ts_r13'), -1), (_c('ts_wks_since_lo260'), -1),
                           # operator-study refinement: buy share LOW (3.3x), few analysts (2.1x), ROIC x FCF
                           # yield (1.9x), P/B not high vs the industry (0.4x)
                           (_c('sent_buy_share'), -1), (_c('sent_n_analysts'), -1),
                           (_c('roce').clip(0, 1) * _c('fcf_yield').clip(0, 1), 1), (_c('rel_ind_pb'), -1),   # (-)x(-) must not rank high
                           (_c('fqx_fcfm_streak'), -1), (_c('fq_rev_yoy_streak_m'), 1)],
        'mb_tree_recipe_10x': [(_c('ts_vol_1y'), 1), (_c('market_cap_usd'), -1),
                               (_c('p_s').where(_c('p_s') > 0), -1),   # (audit 4) the fallen lens dropped: the 10x leaf is the cheapness axis, not the fallen one
                               (_c('nl_sales_3y'), 1), (-_evt_age_days('evt_sc13d_date'), 1), (_c('ts_wks_since_lo260'), -1),
                               (_c('net_debt_ebitda'), 1), (_c('capex_intensity'), 1), (_c('fqx_fcfm_streak'), -1)],
        'mb_sequence_preignition': [(_c('mb_sequence_signs'), 1), (_c('fqx_opm_slope8'), 1), (_c('ncav_pct_mcap'), 1), (_c('sent_upgrades_12m'), -1),
                                    (_c('fqx_roic_slope8'), 1), (_c('rev_accel'), 1), (_c('ts_r13'), -1),
                                    (_c('ts_dist_hi52'), -1), (_c('market_cap_usd'), -1),
                                    # operator-study refinement: debt falling (1.9x), net-net / fallen
                                    # (1.5-1.8x), sell side unturned (1.6x), few analysts (1.5x), off the low
                                    (_c('fq_netdebt_decline_months'), 1), (_c('ts_dist_hi260'), -1),
                                    (_c('mb_fund_up_unturned'), 1), (_c('sent_n_analysts'), -1), (_c('ts_dist_lo52'), 1)],
        # segment study: asset trough — sales/share far ahead of price, fresh
        # low, informed buyer, cheap on sales, uncovered, small, leverage
        # present (deleveraging was NEGATIVE), the 30w MA still falling
        'mb_asset_trough_informed': [(_c('nl_sales_1y'), 1), (_c('nl_sales_3y'), 1), (_c('ts_wks_since_lo260'), -1),
                                     (_c('usf_ins_buy_quarters_4q'), 1), (-_evt_age_days('evt_sc13d_date'), 1),
                                     (_c('p_s').where(_c('p_s') > 0), -1), (_c('sent_n_analysts'), -1),
                                     (_c('market_cap_usd'), -1), (_c('debt_to_equity'), 1),
                                     (_c('ts_ma30_slope13'), -1), (_c('ts_dd_time_share_260'), 1), (_c('ts_r13'), -1)],
        # pre-profit beats rewarded — beat count, positive beat reactions, R&D
        # intensity, targets far above price, revenue acceleration, sales ahead
        # of price, small (ignored beats are 0 by the gate: no lens)
        'mb_preprofit_beats_rewarded': [(_c('evt_beats_8q'), 1), (_c('evt_react_beats_4q'), 1),
                                       (_c('fmp_rd_to_revenue'), 1), (_c('evt_pt_prem_12m'), 1),
                                       (_c('rev_accel'), 1), (_c('nl_sales_1y'), 1), (_c('market_cap_usd'), -1),
                                       (_c('ts_r13'), -1)],
        # pre-profit freefall — depth and freshness of the fall, insiders / a
        # 13D holder, headcount SHRINKING, cheap on sales, targets far above
        'mb_preprofit_freefall_informed': [(_c('ts_dist_hi260'), -1), (_c('ts_wks_since_lo260'), -1),
                                           (_c('usf_ins_buy_quarters_4q'), 1), (-_evt_age_days('evt_sc13d_date'), 1),
                                           (_c('usf_emp_g1'), -1), (_c('p_s').where(_c('p_s') > 0), -1),
                                           (_c('evt_pt_prem_12m'), 1), (_c('nl_sales_1y'), 1), (_c('market_cap_usd'), -1)],
        # biotech financed and hiring — headcount growth, share issuance,
        # insiders, DOWNGRADES (positive in the 10x patterns), cash, depth of
        # the fall, small, volatile
        # operator study: the wave — deeper the market's / industry's own
        # depression, stronger the acceleration, cheaper vs peers, fewer
        # analysts, debt falling, smaller
        'mb_wave_neglected_value_accel': [(_c('mkt_tape_dist_hi260'), -1), (_c('ind_tape_dist_hi260'), -1), (_c('ts_dd_time_share_260'), 1), (_c('rel_ind_p_s'), -1), (_c('evt_react_last'), 1),
                                          (_c('rev_accel'), 1), (_c('rel_ind_ev_ebit'), -1),
                                          (_c('sent_n_analysts'), -1), (_c('fq_netdebt_decline_months'), 1),
                                          (_c('market_cap_usd'), -1), (_c('ts_dist_hi260'), -1),
                                          # refinement: fundamentals up with the sell side unturned (3.6x),
                                          # believers among the few (2.3x), off the low (1.6x), volatile (1.6x)
                                          (_c('mb_fund_up_unturned'), 1), (_c('sent_buy_share'), 1),
                                          (_c('ts_dist_lo52'), 1), (_c('ts_vol_1y'), 1)],
        'mb_compounder_insiders_at_high': [(_c('rel_ind_roce'), 1), (_c('roce'), 1), (_c('fmp_rd_to_revenue'), 1), (_c('fqx_eps_pos_share_8'), 1), (_c('fmp_st_buyback_yield_y0'), 1),
                                           (_c('usf_ins_buy_quarters_4q'), 1), (_c('insider_distinct_buyers'), 1),
                                           (_c('ts_dist_hi52'), 1), (_c('sent_upgrades_12m'), 1),
                                           (_c('evt_beat_share_8q'), -1), (_c('fcf_yield'), 1), (_c('net_cash_pct_mcap'), 1)],
        'mb_hiring_beating_uncovered': [(_c('usf_emp_g1'), 1), (_c('op_margin') - _c('tc_med_opm'), 1),
                                        (_c('evt_surprise_4q'), 1), (_c('evt_beat_share_8q'), 1),
                                        (_c('ev_sales_change_yoy'), 1), (_c('fmp_inst_shares_chg_pct_q0'), 1),
                                        (_c('sent_n_analysts'), -1), (_c('ts_vol_1y'), 1), (_c('market_cap_usd'), -1),
                                        (_c('ts_dist_hi260'), -1)],
        'mb_model_top': [(_c('mb_model_p'), 1), (_c('mb_model_pct_hist'), 1), (_c('mb_model_rank_base'), 1),
                         (_c('fmp_altman_z'), 1), (_c('net_cash_pct_mcap'), 1)],     # blow-up lenses on the high-variance tail
        'mb_model_confluence': [(_c('mb_model_p'), 1), (_c('mb_rule_count'), 1), (_c('mb_model_pct_hist'), 1),
                                (_c('ts_dist_hi260'), -1)],
        'mb_model_region_rule': [(_c('vs_mkt_dist_hi260'), -1), (_c('ts_vol_1y'), 1), (_c('market_cap_usd'), -1),
                                 (_c('ts_dd_time_share_260'), 1), (_c('mb_model_p'), 1), (_c('ts_wks_since_lo260'), -1)],
        'mb_model_uncovered_not_fallen': [(_c('mb_model_p'), 1), (_c('mb_model_pct_hist'), 1), (-_c('nl_sales_3y'), 1),   # price ahead of sales is the winning shape here
                                          (_c('fmp_rd_to_revenue'), 1), (_c('vs_ind_r26'), -1), (_c('market_cap_usd'), -1)],
        # the nine mined families: each lens is one of the family's own conditions, continuous
        'mb_industry_trough_cheapest': [(_c('p_s').where(_c('p_s') > 0), -1), (_c('ind_tape_opm_d1'), -1),
                                        (_c('ind_tape_rev_growth'), -1), (_c('ts_dist_hi260'), -1), (_c('nl_sales_3y'), 1),
                                        (_c('ts_ma30_slope13'), -1), (_c('market_cap_usd'), -1)],
        'mb_reinvesting_at_trough': [(_c('capex_intensity'), 1), (_c('p_s').where(_c('p_s') > 0), -1), (_c('fmp_dyn_ev_sales_change_3y'), -1),
                                     (_c('ev_sales_change_yoy'), -1), (_c('ts_dist_hi260'), -1), (_c('market_cap_usd'), -1)],
        'mb_stressed_not_diluting': [(_c('net_debt_ebitda'), 1), (_c('fmp_st_shares_growth_3y'), -1), (_c('ts_dist_lo52'), -1),
                                     (_c('ts_dist_hi260'), -1), (_c('fq_netdebt_decline_months'), 1), (_c('market_cap_usd'), -1)],
        'mb_growth_past_capex_peak': [(_c('fmp_st_revenue_3y_cagr'), 1), (_c('fq_capex_to_da'), 1), (_c('fqx_fcfm_slope8'), 1),
                                      (_c('fq_capex_p').abs() - _c('fq_capex').abs(), 1), (_c('fqx_roic_ttm') - _c('roic_lindy'), 1),
                                      (_c('ts_vol_1y'), 1), (_c('dividend_yield'), -1)],
        'mb_fallen_less_than_industry_financed': [(_c('vs_ind_dist_hi260'), 1), (_c('equity_cagr_5y'), 1),   # (audit 4) lens sign matches the gate: above its industry's drawdown
                                            (_c('fmp_st_shares_growth_3y'), 1), (_c('sent_n_analysts'), -1),
                                            (_c('ts_dist_hi260'), -1), (_c('ts_dd_time_share_260'), 1)],
        'mb_lean_rd_stocking_up': [(_c('ts_dist_lo52'), 1), (_c('fq_inv_vs_cogs'), 1), (_c('fmp_rd_to_revenue'), 1),
                                   (_c('fq_sga') / _c('fq_revenue').where(_c('fq_revenue') > 0), -1), (_c('fq_rev_growth'), 1)],
        'mb_divergence_cheapest_pb': [(_c('narrative_lag_extent'), 1), (_c('rel_ind_pb'), -1), (_c('ts_vol_1y'), 1),
                                      (_c('ind_tape_rev_growth'), -1), (_c('ts_dist_hi260'), -1), (_c('nl_fcfps_3y'), 1)],
        'mb_fallen_operator_industry_low': [(_c('ev_sales').where(_c('ev_sales') > 0), -1), (_c('ind_tape_dist_hi260'), -1),
                                            (_c('ts_r104'), -1), (_c('rel_ind_p_s'), -1), (_c('ts_dist_hi260'), -1),
                                            (_c('roce'), 1)],
        'mb_quality_at_distress': [(_c('roce').clip(0, 1) * _c('fcf_yield').clip(0, 1), 1), (_c('fmp_altman_z'), 1), (_c('fq_netdebt_decline_months'), 1),
                                   (_c('ev_sales').where(_c('ev_sales') > 0), -1), (_c('rel_ind_pb'), -1),
                                   (_c('ts_dist_hi260'), -1), (_c('ts_maxdd_5y'), -1)],
        'mb_rd_leader_on_volume': [(_c('ts_r104'), 1), (_c('bs_cp_dvol_z13'), 1), (_c('fmp_rd_to_revenue'), 1),
                                   (-_c('nl_eps_1y'), 1), (_c('fq_rev_growth'), 1), (_c('roce'), 1)],
        'mb_cheap_vs_sector_recovering': [(_c('ts_dist_lo52'), 1), (_c('ts_vol_1y'), 1), (_c('rel_ind_p_s'), -1),
                                          (_c('fqx_fcfm_streak'), 1), (_c('fqx_fcfm_slope8'), 1), (_c('market_cap_usd'), -1)],
        'mb_cheap_growth_targets_up': [(_c('fcf_yield') + _c('fq_rev_growth'), 1),
                                       (_c('ev_ebit').where(_c('ev_ebit') > 0), -1), (_c('rel_ind_ev_ebit'), -1),
                                       (_c('fq_rev_growth'), 1), (_c('rel_ind_rev_growth'), 1),
                                       (_c('sent_pt_rev_q'), 1), (_c('evt_pt_prem_12m'), 1), (_c('roce'), 1),
                                       (_c('market_cap_usd'), -1), (_c('ts_vol_1y'), 1)],
        # the leader — coverage, how far price leads sales, margin slope,
        # growth, R&D, the industry's breadth and return, volatility
        'mb_leader_in_wave': [(_c('sent_n_analysts'), 1), (-_c('nl_sales_3y'), 1), (_c('fqx_opm_slope8'), 1),
                              (_c('fq_rev_growth'), 1), (_c('fmp_rd_to_revenue'), 1), (_c('ind_breadth_up52'), 1),
                              (_c('ind_tape_r52'), 1), (_c('ts_vol_1y'), 1), (_c('roce'), 1)],
        # improving, unturned — the size of the improvement, how unturned
        # the sell side is, how low the gross margin, how far the tape has
        # already re-rated
        'mb_improving_unturned_sellside': [(_c('op_margin_delta_yoy'), 1), (_c('fq_rev_growth'), 1),
                                           (_c('sent_buy_share_d12'), -1), (_c('rel_ind_gross_margin'), -1),
                                           (_c('price_vs_5y_avg'), 1), (_c('ts_r52'), 1), (_c('ts_vol_1y'), 1),
                                           (_c('evt_pt_prem_12m'), 1)],
        # peer worst, cheapest — depth of the peer discount and of the
        # peer-quality gap, thin FCF, fallen, small
        'mb_peer_worst_cheapest': [(_c('rel_ind_ev_ebit'), -1), (_c('rel_ind_roce'), -1), (_c('rel_ind_p_s'), -1), (_c('fq_netdebt_decline_months'), 1),
                                   (_c('fcf_margin'), -1), (_c('ts_dist_hi260'), -1), (_c('vs_ind_r52'), -1),
                                   (_c('market_cap_usd'), -1), (_c('ts_wks_since_lo260'), -1)],
        'mb_biotech_financed_hiring': [(_c('usf_emp_g1'), 1), (_c('fmp_st_shares_growth_3y'), 1),
                                       (_c('usf_ins_buy_quarters_4q'), 1), (-_evt_age_days('evt_sc13d_date'), 1),
                                       (_c('sent_downgrades_12m'), 1), (_c('net_cash_pct_mcap'), 1),
                                       (_c('ts_dist_hi260'), -1), (_c('ts_wks_since_lo260'), -1),
                                       (_c('market_cap_usd'), -1), (_c('ts_vol_1y'), 1)],
        'bottleneck': [(_c('tc_min_gm'), 1), (_c('gross_margin'), 1), (_c('roic_lindy'), 1),
                       (_c('capex_intensity'), -1)],
    })
    _QUIET = [(_c('ts_r52'), -1), (_c('sent_n_analysts'), -1), (_c('ts_vol_1y'), -1)]
    _COMPOUND = [(_c('roic_lindy'), 1), (_c('cash_roic_lindy'), 1), (_c('equity_cagr_5y'), 1),
                 (_c('fqx_fcf_ps_g'), 1), (_c('fqx_ebit_ttm_g'), 1), (_c('revenue_5y_cagr'), 1)]

    # a lens rank is the average of the GLOBAL rank within the core and the
    # rank within the name's own COUNTRY (where the country has >= 20 core
    # members): a name must stand out in its own market, not merely sit in a
    # structurally cheap one (the elite book over-represented KR / HK ~1.9x
    # on valuation lenses alone)
    _ctry = country

    def _rank2(x):
        g = x.rank(pct=True)
        n_c = x.notna().groupby(_ctry).transform('sum')
        loc = x.groupby(_ctry).rank(pct=True).where(n_c >= 20)
        return pd.concat([g, loc], axis=1).mean(axis=1).where(x.notna())

    def _spirit(core_mask, lenses):
        ranks = []
        for ser, sign in lenses:
            x = (ser * sign).where(core_mask)
            ranks.append(_rank2(x) if x.notna().sum() >= 5 else pd.Series(np.nan, index=df.index))
        R = pd.concat(ranks, axis=1)
        need = max(1, int(np.ceil(len(lenses) / 2)))
        return R.mean(axis=1).where(R.notna().sum(axis=1) >= need)

    # EVERY OTHER ARCHETYPE: spirit lenses from docs/spirit_spec.json — each
    # grounded in the source write-ups the archetype replicates (the "source"
    # field), duration-type theses rewarding longer / multi-horizon evidence.
    # Lens expressions are column names with + - * / and the helpers pos()
    # (a negative multiple is not cheap), abs(), nz() (missing analyst count =
    # 0) and days_since(); parsed with a whitelist, never exec'd.
    import ast as _ast
    import json as _json
    _today = pd.Timestamp.today().normalize()
    _helpers = {
        'pos': lambda x: x.where(x > 0),
        'abs': lambda x: x.abs(),
        'nz': lambda x: x.fillna(0),
        'days_since': lambda x: (_today - pd.to_datetime(x, errors='coerce')).dt.days.astype(float),
    }
    _raw = lambda c: df[c] if c in df.columns else pd.Series(np.nan, index=df.index)

    def _lens(expr):
        def ev(node):
            if isinstance(node, _ast.Expression):
                return ev(node.body)
            if isinstance(node, _ast.Name):
                return _c(node.id)
            if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, _ast.UnaryOp) and isinstance(node.op, _ast.USub):
                return -ev(node.operand)
            if isinstance(node, _ast.BinOp) and isinstance(node.op, (_ast.Add, _ast.Sub, _ast.Mult, _ast.Div)):
                a, b = ev(node.left), ev(node.right)
                if isinstance(node.op, _ast.Div):
                    b = b.where(b != 0) if isinstance(b, pd.Series) else (b or np.nan)
                return {_ast.Add: lambda: a + b, _ast.Sub: lambda: a - b,
                        _ast.Mult: lambda: a * b, _ast.Div: lambda: a / b}[type(node.op)]()
            if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
                    and node.func.id in _helpers and len(node.args) == 1):
                if node.func.id == 'days_since':
                    return _helpers['days_since'](_raw(node.args[0].id))
                return _helpers[node.func.id](ev(node.args[0]))
            raise ValueError(f'spirit lens {expr!r}: unsupported syntax')
        out = ev(_ast.parse(expr, mode='eval'))
        return (pd.to_numeric(out, errors='coerce') if isinstance(out, pd.Series)
                else pd.Series(np.nan, index=df.index)).replace([np.inf, -np.inf], np.nan)

    _spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'spirit_spec.json')
    _SPEC = {}
    if os.path.exists(_spec_path):
        _SPEC = {k: v for k, v in _json.load(open(_spec_path)).items() if not k.startswith('_')}
    # (audit 4) survivor lenses on the two industry-trough siblings; through-cycle per-share quality on the fallen family
    for _a in ('mb_industry_trough_cheapest', 'mb_fallen_operator_industry_low'):
        _DEMOTED.setdefault(_a, []).extend([(_ncol('fq_interest_cover'), 1), (_ncol('fmp_altman_z'), 1)])
    for _a in ('mb_fallen_deep_value', 'mb_fallen_below_cycle', 'mb_fallen_trough', 'mb_fallen_stressed'):
        _DEMOTED.setdefault(_a, []).extend([(_ncol('fg_ocf_ps_5y_min5'), 1), (_ncol('fg_rev_ps_5y_min5'), 1)])
    _DEMOTED.setdefault('mb_compounder_insiders_at_high', []).append((_ncol('fg_ni_ps_3y_cagr'), 1))
    # (user) an IMPORTANT weight: the demoted block carries half of the trough
    # archetypes' spirit score; the net-cash cushion (x2) and debt / assets are 3
    # of its 5 lenses (nde and interest cover are added below), i.e. ~30% of the
    # score, and nothing where fewer than 3 of the 5 are measured
    for _a in ('xr_double_trough', 'xr_cyclical_trough'):
        _DEMOTED.setdefault(_a, []).extend([(_ncol('net_cash_pct_mcap'), 1), (_ncol('net_cash_pct_mcap'), 1), (_bs_d2a, -1)])
        _DEMOTED_W[_a] = 0.50
    for _a in ('mb_smart_money_wreckage', 'mb_conviction_confluence'):
        _DEMOTED.setdefault(_a, []).append((_corp_conviction.astype(float), 1))
    # (audit 4) facts the de-gating left without a weight, and the leftover caps
    _DEMOTED.setdefault('buyback_compounder', []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('flyover', []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('fixed_cost_demand_shock', []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('regime_cyclical', []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('dta_reversal', []).append((_ncol('shares_yoy'), -1))
    _DEMOTED.setdefault('double_inflect', []).append(((_ncol('op_margin_delta_yoy') > 0.30).astype(float).where(_ncol('op_margin_delta_yoy').notna()), -1))
    _DEMOTED.setdefault('financials_value', []).append((_ncol('fq_equity') / _ncol('fq_total_assets').where(_ncol('fq_total_assets') > 0), 1))
    _DEMOTED.setdefault('xr_monetization_trifecta', []).append((_ncol('net_income_ttm'), 1))
    # (audit 4, sources slice) demoted legs kept as weights
    for _a in ('bab_low_beta', 'bab_multibagger', 'bab_becoming'):
        _DEMOTED.setdefault(_a, []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('capital_discipline', []).extend([(_ncol('yartseva_score'), 1)])
    _DEMOTED.setdefault('oak_nav_discount', []).append((_ncol('debt_to_equity'), -1))
    _DEMOTED.setdefault('templeton_pessimism', []).append((_ncol('revenue_ttm') / _ncol('normalized_revenue').where(_ncol('normalized_revenue') > 0), -1))
    _DEMOTED.setdefault('liger_asset_backed', []).append((_ncol('net_debt_ebitda'), -1))
    _DEMOTED.setdefault('wolf_emerging', []).append((_ncol('shares_yoy'), -1))
    # (Fannie Mae chapter) ranking weights on lynch_reward: the reward-to-price
    # ("earn back the price in one year": normalised EBIT over EV), the market
    # still skeptical (ignored beats, price targets cut, thin coverage), a
    # buyback into weakness (the 1987 repurchase), and per-share progress size
    _DEMOTED.setdefault('lynch_reward', []).extend([
        (_ncol('normalized_ebit') / _ncol('enterprise_value').where(_ncol('enterprise_value') > 0), 1),
        (_ncol('evt_ignored_beats_2y'), 1), (_ncol('evt_pt_rev_90d'), -1), (_ncol('sent_n_analysts'), -1),
        (_ncol('fmp_st_buyback_yield_y0'), 1), (_ncol('fg_ni_ps_3y_cagr'), 1)])
    # (audit 4 / user rule) the XR leverage caps demoted to weights
    _DEMOTED.setdefault('xr_asset_owner_catalyst', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_baron_compounder', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_cannibal_below_tbook', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1), (_ncol('roce'), 1)])
    _DEMOTED.setdefault('xr_cyclical_trough', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_discops_mask', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_double_trough', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_forced_seller', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_insider_capitulation', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_look_through_value', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    _DEMOTED.setdefault('xr_reusable_assembler', []).extend([(_ncol('net_debt_ebitda'), -1), (_ncol('interest_coverage'), 1)])
    # One list: the tiered archetypes, the matrix-augmented ones (_SPIRITED)
    # and every archetype in the source-grounded spec. The original tiered
    # archetypes keep their own lenses; for the others the spec's lenses and
    # the augmentation's EXCEPTIONAL lenses (e.g. the 5y max-drawdown
    # "price-lindy") are UNIONED — independent angles on the same thesis —
    # except where the spec defines a two-group blend, which is kept as is.
    _SPIRIT_ALL = list(dict.fromkeys(
        list(_TIERED) + list(_SPIRITED)
        + [n for n in _SPEC if 'arch_' + n in df.columns]
        + [n for n in _DEMOTED if 'arch_' + n in df.columns]))
    # a qualitative exceptional set upstream (e.g. micro_activist_inflect's
    # recent SC 13D) is kept alongside the spirit tier
    _pre_exc = {n: df[n + '_exceptional'].copy() for n in _SPIRIT_ALL
                if n + '_exceptional' in df.columns}

    for _n in _SPIRIT_ALL:
        _core = df['arch_' + _n] == 1
        if _n == 'quiet_compounder':
            sc = 0.6 * _spirit(_core, _COMPOUND) + 0.4 * _spirit(_core, _QUIET)
        elif _n in _TIERED and _n in _SPIRIT:
            sc = _spirit(_core, _SPIRIT[_n])
        elif _n in _SPEC and _SPEC[_n].get('lenses'):
            _sp = _SPEC[_n]
            _L = {e: (_lens(e), s) for e, s in _sp['lenses']}
            _bl = _sp.get('blend')
            if _bl:
                (wa, wb) = _bl['weights']
                sc = (wa * _spirit(_core, [_L[e] for e in _bl['groupA']])
                      + wb * _spirit(_core, [_L[e] for e in _bl['groupB']]))
            else:
                sc = _spirit(_core, list(_L.values()) + list(_SPIRIT.get(_n, [])))
        elif _n in _SPIRIT:
            sc = _spirit(_core, _SPIRIT[_n])
        elif _n in _DEMOTED:
            sc = _spirit(_core, _DEMOTED[_n])
        else:
            continue
        # (user) the demoted former gates weigh 25% of the spirit score where measured
        if _n in _DEMOTED and not (_n not in _TIERED and _n not in _SPEC and _n not in _SPIRIT):
            _w = _spirit(_core, _DEMOTED[_n])
            _sh = _DEMOTED_W.get(_n, 0.25)
            sc = ((1 - _sh) * sc + _sh * _w).fillna(sc)
        df[_n + '_spirit'] = sc.where(_core).round(3)
        df[_n + '_exceptional'] = (_core & (sc >= 0.75)).fillna(False).astype(int)
        if _n in _pre_exc:
            df[_n + '_exceptional'] = (df[_n + '_exceptional'].astype(bool)
                                       | ((_pre_exc[_n] == 1) & _core)).astype(int)
        df[_n + '_elite'] = (_core & (sc >= 0.90)).fillna(False).astype(int)
    _TIERED_ALL = [n for n in _SPIRIT_ALL if n + '_spirit' in df.columns]

    # EXCEPTIONAL tiers (core/watch/exceptional split): tag + count
    _exc_cols = [n + '_exceptional' for n in _TIERED_ALL if n + '_exceptional' in df.columns]
    for _c in _exc_cols:
        _on = pd.to_numeric(df[_c], errors='coerce').fillna(0) == 1
        _sig = _sig.where(~_on, _sig + ' · EXC-' + _c[:-len('_exceptional')])
    df['exceptional_count'] = df[_exc_cols].sum(axis=1).astype(int) if _exc_cols else 0
    _eli_cols = [n + '_elite' for n in _TIERED_ALL if n + '_elite' in df.columns]
    for _c in _eli_cols:
        _on = pd.to_numeric(df[_c], errors='coerce').fillna(0) == 1
        _sig = _sig.where(~_on, _sig + ' · ELITE-' + _c[:-len('_elite')])
    df['elite_count'] = df[_eli_cols].sum(axis=1).astype(int) if _eli_cols else 0
    df['fmp_signals'] = _sig.str.lstrip(' ·')

    out = df[['symbol'] + arch_cols + ['archetype_count','archetype_tags_str','bab_score','oper_leverage_score','buyback_score','inflection_confirm_score','rev_growth_score','cheapness_score','quality_score','confirm_overall','alignment_score','governance_score','governance_tier','insider_distinct_buyers','insider_net_buy_value','insider_officer_buy_flag','insider_buy_flag','insider_cluster_buy_flag','insider_10pct_buy_flag','tenbagger_score','tenbagger_implied_return','evsales_derate_score','evsales_derate_gap','lynch_reward_score','lynch_leg_max','lynch_exceptional_leg','lynch_rank','high_52w_abs','high_52w_rel','high_52w_both','analyst_awakening_score','analyst_rerating_score','asleep_score','seg_inflect_score','oneil_score','weinstein_score','kullamagie_score','cundill_score','biotech_deep_value_score','biotech_cash_runway_yrs','is_drug_developer','is_clinical_biotech','financing_fragile_flag','sbc_polluted_flag','earnings_oneoff_flag','segment_rot_flag','data_quality_flag','holdco_flag','china_vie_flag','cash_squatter_flag','capex_treadmill_flag','earnings_variability_flag','cluseau_sizing_tier','adjusted_book','adjusted_pb','nnwc','nnwc_pct_mcap','nnwc_asset_mix','xr_family_count','xr_confidence','xr_score','forensic_hidden_pct','forensic_xr_score','value_unlock_score','value_unlock_confirmed','pre_rerating_quality','pre_rerating_score','pre_rerating_flag','truly_xr_score','truly_xr_flag','truly_xr_tell_count','truly_xr_mech_count','truly_xr_tells_str','spin_date','reorg_date']
             + [c for c in ['asym_m','asym_q','sr_m_release','roc_3_5y','roc_accel_3_5y','roc_12m','stale_tape','gaap_masked','pct_52w_high','rel_pct_52w_high','base_depth_12m','segment_count','fastest_segment_yoy','is_price_ghost','security_type','senior_yield','senior_yield_vs_peers','senior_issuer','is_cannabis'] if c in df.columns]
             # FMP secondary-source signals + fill provenance (all optional).
             + [c for c in ['fmp_piotroski','fmp_altman_z','fmp_distress_flag',
                            'fmp_piotroski_strong_flag','fmp_insider_alignment_ratio',
                            'fmp_insider_aligned_flag','fmp_insider_net_usd_12m',
                            'fmp_insider_buyers_12m','fmp_exec_comp_total',
                            'fmp_earnings_beat_rate','fmp_avg_earnings_surprise',
                            'fmp_earnings_surprise_cv',
                            # nuanced second-order signals + surfaced flags
                            'fmp_income_quality','fmp_earnings_cash_backed_flag',
                            'fmp_low_earnings_quality_flag','fmp_capex_to_depreciation',
                            'fmp_asset_harvester_flag','fmp_growth_capex_masked_flag',
                            'fmp_cash_conversion_cycle','fmp_customer_float_flag',
                            'fmp_rd_to_revenue','fmp_rd_intensive_flag',
                            'fmp_sbc_to_revenue','fmp_interest_burden','fmp_levered_returns_flag',
                            'fmp_price_to_fair_value','fmp_graham_net_net','fmp_ncav'] if c in df.columns]
             # dynamic (multi-period) trajectory columns + confirming flags
             + [c for c in ['fmp_dyn_rev_streak_q','fmp_dyn_ni_streak_q','fmp_dyn_rev_accel',
                            'fmp_dyn_rev_yoy','fmp_dyn_incremental_ebit_margin',
                            'fmp_dyn_ebitda_turned_positive','fmp_dyn_gross_margin_trend',
                            'fmp_dyn_rev_cagr_3y','fmp_dyn_ev_sales_change_3y','fmp_dyn_unrerated_gap',
                            'fmp_dyn_fwd_ebit_crossing','fmp_dyn_fwd_rev_growth_1y',
                            'fmp_dyn_fwd_underestimate_gap','fmp_dyn_unrerated_flag',
                            'fmp_dyn_accelerating_flag','fmp_dyn_op_leverage_flag',
                            'fmp_dyn_growth_streak_flag','fmp_dyn_fwd_inflection_flag',
                            'fmp_dyn_forward_asleep_flag'] if c in df.columns]
             # global statement-history reach columns
             + [c for c in ['fmp_st_roic_lindy','fmp_st_roiic_lindy','fmp_st_roce_lindy',
                            'fmp_st_op_margin_lindy','fmp_st_ebitda_margin_lindy',
                            'fmp_st_revenue_cagr','fmp_st_equity_cagr','fmp_st_shares_growth_3y',
                            'fmp_st_capital_return_yield','fmp_st_buyback_yield',
                            'fmp_st_owner_earnings_yield','fmp_st_years_of_history'] if c in df.columns]
             # institutional accumulation + FMP segmentation + digest
             + [c for c in ['inst_accum_score','inst_accum_accelerating','inst_own_excess_q0','inst_buy_excess_q0','fmp_signals',
                            'roic_lindy_eff','capret_yield_eff','multi_year_data','non_common_flag',
                            'controlled_sub_flag',
                            'narrative_lag_lenses','narrative_lag_extent','narrative_lag_years','narrative_lag_max_gap','narrative_lag_outrun','derate_growth_extent','derate_growth_years','derate_growth_horizons','derate_growth_froth','derate_growth_share','derate_growth_absorbed','mb_smart_money_legs','mb_sequence_signs','nl_sales_1y','nl_ebit_1y','nl_eps_1y','nl_fcfps_1y','nl_sales_5y','nl_ebit_3y','nl_fcfps_3y','nl_ebit_5y','nl_fcfps_5y',
                            'nl_sales_2y','nl_ebit_2y','nl_sales_3y',
                            'ts_dvol26_usd','ts_r52','ts_rs_pct_mkt','ts_weinstein_stage','ts_maxdd_5y',
                            'ts_dist_hi52','ts_mrs',
                            'fmp_inst_quarter','fmp_inst_holders','fmp_inst_own_pct',
                            'fmp_inst_own_chg_q0','fmp_inst_own_chg_q1','fmp_inst_own_chg_q2',
                            'fmp_inst_shares_chg_pct_q0','fmp_inst_shares_chg_pct_q1',
                            'fmp_inst_buy_ratio_q0','fmp_inst_buy_ratio_q1','fmp_inst_accum_quarters',
                            'fmp_seg_count','fmp_seg_hhi','fmp_seg_largest_name','fmp_seg_largest_share',
                            'fmp_seg_fastest_name','fmp_seg_fastest_yoy','fmp_seg_fastest_share_delta',
                            'fmp_geo_count','fmp_geo_largest_name','fmp_geo_largest_share',
                            'fmp_geo_em_share','fmp_geo_china_share',
                            'fmp_seg_coverage','fmp_geo_coverage','fmp_seg_fastest_yoy_q',
                            'fmp_seg_fastest_q_accel','fmp_seg_fastest_consec_growth_q',
                            'fmp_seg_fastest_accel_fy','fmp_seg_fastest_cagr_3y',
                            'fmp_seg_share_gainer_3y_name','fmp_seg_share_gainer_3y_delta',
                            'fmp_seg_hhi_delta','fmp_seg_hhi_delta_3y','fmp_seg_core_declining',
                            'fmp_geo_core_declining','fmp_geo_em_share_delta',
                            'fmp_geo_china_share_delta'] if c in df.columns]
             # quarterly 3-statement forensic layer (fmp_quarterly) + flags
             + [c for c in ['fmp_q_status','fmp_q_ccy','fmp_q_latest','fmp_q_periods_per_year',
                            'fq_cf_basis','fq_fx_to_master',
                            # reporting-currency levels (x fq_fx_to_master = master ccy)
                            'fq_revenue','fq_ni','fq_ni_cf','fq_cfo','fq_cfo_p','fq_ni_cf_p',
                            'fq_capex','fq_da','fq_sbc','fq_chg_wc','fq_financing_cf',
                            'fq_retained_earnings','fq_equity','fq_total_assets','fq_ppe_net',
                            'fq_total_debt','fq_cash_sti','fq_defrev',
                            'fq_beneish_m','fq_beneish_dsri','fq_beneish_tata','fq_sloan_accruals',
                            'fq_cfo_to_ni','fq_cfo_growth_minus_ni_growth','fq_sbc_to_cfo',
                            'fq_dso','fq_dso_p','fq_dio','fq_dio_p','fq_dpo','fq_ccc','fq_ccc_p',
                            'fq_rec_vs_rev','fq_inv_vs_cogs','fq_op_nwc_to_rev','fq_defrev_to_rev',
                            'fq_defrev_growth_minus_rev','fq_capex_to_da','fq_da_to_ppe',
                            'fq_cash_tax_rate','fq_book_tax_rate_fy','fq_cash_tax_wedge_med',
                            'fq_disc_ops_share','fq_acq_pct_assets','fq_rev_growth','fq_shares_yoy',
                            'fq_rev_yoy_streak_m','fq_ni_yoy_streak_m','fq_rev_yoy_pos_share',
                            'fq_gm_yoy_streak_m','fq_netdebt_decline_months','fq_netdebt_change_pct_assets',
                            'fq_beneish_risk_flag','fq_beneish_ma_distorted','fq_high_accruals_flag',
                            'fq_receivables_divergence_flag','fq_inventory_build_flag','fq_sbc_heavy_flag',
                            'fq_cash_leads_earnings_flag','fq_wc_release_flag','fq_deleveraging_flag',
                            'fq_gm_inflection_flag','fq_defrev_build_flag','fq_cash_tax_shield_flag',
                            'fq_forensic_clean_confirm','fq_forensic_red_count','fq_forensic_green_count',
                            # base / coil + sentiment layer
                            'coiled_base_score','coiled_base_legs','bs_is_base','bs_r104','bs_range104',
                            'bs_r26','bs_rs26','bs_pos_in_range','bs_dvol_trend','bs_updown_vol',
                            'bs_prior_dd','bs_rev_g_2y','bs_coil_rev','bs_coil_ebit','bs_ebit_turned',
                            'sent_n_analysts','sent_buy_share','sent_buy_share_d12','sent_upgrades_12m',
                            'sent_downgrades_12m','sent_initiations_12m','sent_months_since_up',
                            'sent_pt_rev_q','sent_warming_flag','sent_cooling_flag','sent_discovery_flag',
                            'sent_neglected_flag','sent_skeptic_flag',
                            ] if c in df.columns]
             + [c + '_eff' for c in _EFF_COLS if c + '_eff' in df.columns]
             + [c for c in df.columns if c.endswith(('_watch', '_exceptional', '_elite', '_spirit'))]
             + [c for c in ['lynch_pegy_ttm', 'lynch_evgy_durable', 'derate_gap_1y', 'unrerated_gap_1y',
                            'micro_activist_13d_flag', 'xr_streak_norerate_lenses', 'ev_norm_midcyc',
                            # (audit 3) surfaced flags, tiers and measures
                            'lynch_reward_gap3', 'levered_stub_tier', 'value_up_reform_flag',
                            'per_share_compounder_flag', 'lynch_transformed_flag', 'lynch_reinvented_flag', 'lynch_pandemic_recovery_flag',
                            'esb_beat_share_8q', 'esb_surprise_4q', 'esb_beat_streak', 'esb_react_last', 'esb_ignored_beats_2y',
                            'fg_rev_ps_5y_cagr', 'fg_ni_ps_3y_cagr', 'fg_ocf_ps_5y_cagr', 'fg_eq_ps_5y_cagr',
                            'fg_shares_dil_g1', 'fg_rev_ps_5y_min5', 'fg_ocf_ps_5y_min5',
                            'evh_ev_sales_now', 'evh_evs_log_chg_1y', 'evh_evs_log_chg_3y', 'evh_evs_vs_med_3y',
                            'special_return_event_flag', 'dirty_spin_flag', 'discounted_vehicle_catalyst_flag',
                            'discounted_vehicle_governance_trap_flag', 'wolf_value_catalyst_dated_flag'] if c in df.columns]
             + ['exceptional_count', 'elite_count']
             + [c for c in df.columns if c.startswith('fmp_filled_')]]
    from master_versions import versioned_replace
    # TIERS in their own file: the per-archetype continuous spirit score and
    # its watch / exceptional / elite flags (~535 columns for 166 archetypes)
    # are read by the elite book only; kept beside the flags they would push
    # archetype_tags.csv past GitHub's 100 MB hard file limit (131 MB).
    # archetype_tiers.csv is keyed by symbol; the elite book merges it back.
    _tier_cols = [c for c in out.columns if c.endswith(('_spirit', '_exceptional', '_elite', '_watch'))]
    _tiers_path = os.path.join(os.path.dirname(os.path.abspath(out_path)), 'archetype_tiers.csv')
    out[['symbol'] + _tier_cols].to_csv(_tiers_path + '.tmp', index=False, float_format='%.4g')
    os.replace(_tiers_path + '.tmp', _tiers_path)
    # 8 significant digits: exact for every ratio / flag / score and to one
    # part in 10^8 on levels (a $1bn market cap to the nearest $10).
    out.drop(columns=_tier_cols).to_csv(out_path + '.tmp', index=False, float_format='%.8g')
    versioned_replace(out_path + '.tmp', out_path)   # atomic + pre-image snapshot


    # Summary to stderr
    print(f'wrote {out_path}: {len(out)} rows', file=sys.stderr)
    for c in arch_cols:
        n = int(df[c].sum())
        print(f'  {pretty[c]:24s} {n:5d}', file=sys.stderr)
    print(f'  multi-archetype (>=2) {int((df["archetype_count"] >= 2).sum())}', file=sys.stderr)

    # ---------- Fail-safe sanity report ------------------------------------
    # Every silent-zero bug this file has had (n_analysts merge-shadowing,
    # the 52w-flag freeze, the upside units bug) would have been flagged
    # here. WARN loudly on: (a) columns the gates asked for that do not
    # exist in the frame, (b) requested columns with <2% coverage, (c)
    # archetypes firing on nobody, (d) archetypes firing on >40% of the
    # universe (identity lost). Also persisted to archetype_sanity_report.txt
    # so drivers/CI can grep it.
    _report = []
    if _absent_cols:
        _report.append('ABSENT COLUMNS (requested by gates, not in frame — '
                       'gate legs read all-NaN):')
        for c in sorted(_absent_cols):
            _report.append(f'  MISSING  {c}')
    if _sparse_cols:
        _report.append('NEAR-EMPTY COLUMNS (<2% coverage — legs almost never fire):')
        for c, cov in sorted(_sparse_cols.items(), key=lambda kv: kv[1]):
            _report.append(f'  SPARSE   {c:36s} {cov*100:5.2f}%')
    _n_rows = len(df)
    for col in arch_cols:
        _n_fire = int(pd.to_numeric(df[col], errors='coerce').fillna(0).sum())
        if _n_fire == 0:
            _report.append(f'  ZERO     {col} fires on NOBODY — investigate')
        elif _n_fire > 0.40 * _n_rows:
            _report.append(f'  BLOATED  {col} fires on {_n_fire:,}/{_n_rows:,} '
                           f'({_n_fire/_n_rows*100:.0f}%) — identity diluted')
    with open('archetype_sanity_report.txt', 'w') as fh:
        fh.write('\n'.join(_report) + ('\n' if _report else 'CLEAN\n'))
    if _report:
        print('\n  SANITY WARNINGS (archetype_sanity_report.txt):', file=sys.stderr)
        for line in _report[:40]:
            print('  ' + line, file=sys.stderr)
        if len(_report) > 40:
            print(f'  ... {len(_report)-40} more lines in the report file',
                  file=sys.stderr)
    else:
        print('  sanity: CLEAN', file=sys.stderr)
    return out


if __name__ == '__main__':
    compute()
