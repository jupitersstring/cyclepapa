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


def compute(out_path: str = 'archetype_tags.csv') -> pd.DataFrame:
    asym = pd.read_csv(ASYM_PATH).drop_duplicates('symbol')
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
    if os.path.exists('lynch_reward_signals.csv'):
        lynch_signals = pd.read_csv('lynch_reward_signals.csv').drop_duplicates('symbol')
        df = df.merge(lynch_signals, on='symbol', how='left', suffixes=('','_lr'))
    # EDGAR event-driven / special-situations signals (US filers): Form-10 spins,
    # tenders/mergers/going-private, NOL carryforwards, post-reorg fresh-start.
    if os.path.exists('edgar_event_signals.csv'):
        _evt = pd.read_csv('edgar_event_signals.csv').drop_duplicates('symbol')
        _evt_keep = ['symbol', 'spin_flag', 'tender_flag', 'merger_flag',
                     'going_private_flag', 'distress_flag', 'nol_usd', 'reorg_flag']
        _evt = _evt[[c for c in _evt_keep if c in _evt.columns]]
        df = df.merge(_evt, on='symbol', how='left', suffixes=('', '_evt'))
    # pew and asym both carry n_analysts; suffix pew's copy so downstream
    # _num('n_analysts') keeps reading the asym column instead of vanishing
    # into n_analysts_x/_y (which silently zeroed the analyst-awakening gate).
    df = df.merge(pew, on='symbol', how='left', suffixes=('', '_pew'))

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

    def beaten_down_any(depth):
        """Beaten down by >= depth through ANY available drawdown lens.
        A PRESENT primary 52w measure that clearly contradicts (drawdown
        shallower than half the claimed depth) VETOES the proxy lenses —
        a stock that crashed years ago and round-tripped to its high
        satisfies the 5y-average leg without being beaten down."""
        any_lens = ((_oh_n <= -depth) |
                    (_p5r_n <= max(0.10, 0.50 - depth)) |
                    (_pv5_n <= (1.0 - depth)) |
                    (_r12_n <= -depth) |
                    (_py_raw <= -depth) |
                    (_m12_raw <= -depth)).fillna(False)
        contradicted = (_oh_n.notna() & (_oh_n > -depth * 0.5))
        return any_lens & ~contradicted

    def not_too_deep_any(cap):
        """True unless a PRESENT tape measure shows a drawdown DEEPER than
        cap (missing data is not evidence of a shallow drawdown — the old
        `off_high >= -cap` on a 0-defaulted series admitted every name with
        no 52w-high data)."""
        return (~((_oh_n.notna() & (_oh_n < -cap)) |
                  (_r12_n.notna() & (_r12_n < -cap)) |
                  (_m12_raw.notna() & (_m12_raw < -cap))))

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
    _lag_tape = ((_py_raw < 0.0) | (_m12_raw < 0.0))
    # (audit re-check) tightened from ~28% of the universe toward the spirit
    # (price/narrative LAGS genuinely improving fundamentals): require a real
    # multi-lens advance (not a lone first-positive), investable operating
    # scale, survivability (not a double cash-burner), and a cheapness anchor
    # so the narrative is actually LAGGING a reasonable valuation.
    df['arch_narrative_lag'] = (
        _lag_tape &
        (_adv_breadth >= 2) &
        is_operating & (mcap >= 10e6) &
        _roce_now_ok &                          # (tail) lag on IMPROVING fundamentals, not a deteriorating name (UCID/ILINK)
        ((s('fcf_ttm') > 0) | (s('ebitda_ttm') > 0) | _first_pos_any) &
        (((pb > 0) & (pb < 3.0)) | (fcf_yield >= 0.03))
    ).fillna(False).astype(int)

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

    # ---------- Cluster E7: Discounted Vehicle ----------
    df['arch_discounted_vehicle'] = (
        is_operating &                                   # (G1) exclude financials/REITs/utilities
        (pb > 0) & (pb < 0.85) &
        ((cash_gt_ev > 0) | (net_cash_pct_sane > 0.20)) &  # (G2) drop >100%-of-mcap shells
        ~((nde >= 1.0) & (nde < 90)) &                   # (tail) net-cash claim not contradicted by REAL net debt (nde 99 = unknown, stays permissive; Newtree nde+2.1 excluded)
        _not_melting &                                   # (deep-audit) the net-cash claim doesn't stop an OPERATING melter sitting on cash: CHGG roce-95%, WISH roce-87%, FOM roce-98% passed on one-off working-cap FCF. Sibling dead_option carries the returns floor; add it here.
        (mcap > 0) & (mcap < 2e9)   # mcap>0: missing mcap must not auto-pass the size gate
    ).astype(int)

    # ---------- Cluster E8: Capital Discipline Re-rating ----------
    # Proxy: founder/insider-aligned, lightly levered, durable margin, not
    # already re-rated.  We don't have a direct buyback signal in fundamentals
    # so this is a "compounder-pattern" proxy.
    # (G6) require a real capital-allocation ACTION (buyback / share shrink),
    # OR pair high insider ownership with a genuine return gate — insider
    # ownership alone is not capital discipline (91% passed on it before).
    # (gate audit #4) a buyback claim is corroborated against the share
    # count — SBC out-diluting the buyback is not discipline (TTEC class)
    _action_leg = ((_ncol('shares_growth_3y') <= -0.01) |
                   ((_ncol('buyback_yield') >= 0.02)
                    & ~(_ncol('shares_yoy') > 0)))
    # (R2) roic_after_sbc is EDGAR-only (NA for all non-US filers), so the
    # returns leg used to collapse to "insider>=0.20 & any positive FCF" for
    # ex-US names. Add globally-available roce>=0.12 as the real returns leg,
    # and lift the FCF fallback to a meaningful yield (not a trivial +epsilon).
    _insider_plus_return = ((insider >= 0.20) &
                            ((_ncol('roic_after_sbc') >= 0.10) |
                             (_ncol('roce') >= 0.12) |
                             (fcf_yield >= 0.04)))
    _own_aligned = (_action_leg | _insider_plus_return)
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
        (s('op_margin', np.nan) > 0) &          # positive operating profit (Hinduja op -9.9% out)
        (nde <= 1.5) &
        (ebitda_margin_sane >= 0.05) &          # (G2) drop one-off >60% margins
        (price_yoy <= 0.30) &
        (yart_score >= 0.45)
    ).fillna(False).astype(int)

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

    # ---------- Cluster F10: Option Mispriced as Dead ----------
    _cash_yield_any = ((fcf_yield > 0.05) |
                       (_ncol('owner_earnings_yield') > 0.05) |
                       (_ncol('robust_cash_yield') > 0.05) |
                       (_ncol('cash_return_ev') > 0.05))
    df['arch_dead_option'] = (
        is_operating &                          # (R1b) exclude financials/REITs (Wanda Hotel, Shimao)
        (mcap >= 10e6) &                        # investable scale — drops one-off-FCF sub-scale ADRs (JFU, SOGP)
        beaten_down_any(0.40) &
        _cash_yield_any &
        (ebitda_margin > 0) &
        (s('op_margin', np.nan) > 0) &          # real operating cow, not a one-off/near-liquidation FCF spike
        _roce_now_ok &                          # (fresh) sibling floor — not a capital-destroyer on a one-off FCF spike (TTEC roe-101%)
        (nde <= 3.0)
    ).fillna(False).astype(int)

    # ---------- Cluster G11: Operating KPI Threshold ----------
    # TIGHTENED: require BOTH a first-positive print AND confirmation that
    # the inflection is operating-level (margin or ROCE improving sequentially),
    # AND that the company is at investable scale.  Previous version fired
    # on 37 pct of universe (too broad - signal carries no information).
    # New version requires at least one first-positive in a profitability
    # measure (EBITDA/CFO/FCF/NI/ROCE) AND positive margin delta YoY AND
    # positive ROCE today (>= 5 pct).
    first_pos_print = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0)
    )
    margin_confirming = ((ebitda_margin_delta >= 0.01) |
                         (_ncol('op_margin_delta_yoy') >= 0.01) |
                         (_ncol('gross_margin_delta_yoy') >= 0.01) |
                         (_ncol('roce_delta_yoy') > 0.01)).fillna(False)
    roce_today = s('roce') >= 0.05
    df['arch_kpi_threshold'] = (
        is_operating &                          # (R1b) exclude financials/REITs (KPI/margin lens is operating-only)
        _not_melting &                          # (tail) a loss-narrowing margin delta must not substitute for the returns floor (MKTW roce-75%)
        first_pos_print & (margin_confirming | roce_today) &
        (mcap >= 10e6)                          # (G6) restore investable-scale floor
    ).fillna(False).astype(int)

    # ---------- Cluster G12: Regional Blind-Spot ----------
    # ADV data only covers ~13% of the universe (PEW screen subset), so we
    # use ADV as a hard gate where present but fall back to mcap-only for
    # the rest of the under-covered geographies.
    adv_has = adv < 1e10  # finite ADV present
    df['arch_blindspot'] = (
        country.isin(BLINDSPOT_COUNTRIES) &
        (mcap > 0) & (mcap < 4e8) &
        ((~adv_has) | (adv < 5e5))
    ).astype(int)

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
    inflection_now = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0) |
        (ebitda_margin_delta >= 0.02) | (rev_accel >= 0.05)
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
        profitable &
        inflection_now &
        clean_balance_sheet &
        cheap_on_ebitda
    ).fillna(False).astype(int)

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
    df['arch_durable_reinvestment'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok &                               # (R4) current returns not negative
        (roic_lindy >= 0.10) &                       # (G3) positive base ROIC
        (s('n_yrs_positive_roic', 0) >= 4) &         # (G3) require ROIC history
        (roiic_lindy >= 0.15) & (roiic_lindy <= 1.0) &  # (G3) sane ROIIC band
        (asset_3y_cagr > 0.05)
    ).fillna(False).astype(int)

    # J — Cash-confirmed reinvestment: cash ROIIC lindy > 12% (lower bar than
    # NOPAT because FCF includes capex outflows).
    df['arch_cash_reinvest'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok &                               # (R4) current returns not negative
        (cash_roic_lindy >= 0.10) &                  # (G3) positive base cash ROIC
        (s('n_yrs_positive_roic', 0) >= 4) &         # (G3) require ROIC history
        (cash_roiic_lindy >= 0.12) & (cash_roiic_lindy <= 1.0) &  # (G3) sane band
        (asset_3y_cagr > 0.05)
    ).fillna(False).astype(int)

    # K — ROIC inflection: latest ROIC crossed zero from below AND cash ROIC
    # also positive (confirms the inflection is real, not accounting).
    df['arch_roic_inflect'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        ((roic_inflect == 1) | (cash_roic_inflect == 1))
        & (cash_roic_lindy.fillna(-1) > 0)
        & (rev_yoy > 0)                              # (R5) not a cost-cut blip in a shrinking co
        & (s('op_margin', np.nan) > 0)               # (R4) inflection is REAL now — positive operating result (GitLab op -6%, Azenta -33% out)
    ).fillna(False).astype(int)

    # L — Cheap per reinvestment yield (PEG analogue on ROIIC). Lower
    # cheap_per_roiic = more reinvestment yield per multiple paid. Threshold
    # 1.5 means "you're paying < 1.5x EV/EBITDA per percent of lindy ROIIC".
    df['arch_cheap_per_roiic'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        _roce_now_ok & _not_melting &           # (R4/fresh) current returns not negative + not a cash-burner (KPLT fcf-41%)
        (roic_lindy >= 0.05) &                  # (G3/topcheck) POSITIVE base ROIC — ROIIC on a negative base (KPLT roic_lindy -0.15) is loss-narrowing noise, not reinvestment
        (cheap_per_roiic > 0) & (cheap_per_roiic <= 1.5) & (roiic_lindy > 0.10)
    ).fillna(False).astype(int)

    # M — Tangible-value floor: P/TB < 0.7 with tangible equity > 50% of book
    # equity (real assets, not goodwill).
    df['arch_tangible_value'] = (
        is_operating &                          # (G1) exclude financials/REITs/utilities
        (mcap >= 10e6) &                        # investable scale (was firing on $2k shells)
        (p_tb > 0) & (p_tb < 0.7) & (tangible_equity_pct > 0.50) &
        ((s('fcf_ttm') > 0) | (s('cfo_ttm') > 0)) &   # REAL cash generation (EBITDA-alone let levered melters KSS fcf -0.60 pass)
        ~(_ncol('fcf_yield') < -0.15) &         # (fresh) not deeply FCF-negative via capex burn — the CFO fallback let cyclicals melt the floor (BATL fcf -153%, MOS, HPK)
        ~(net_cash_pct > 1.0) &                 # (deep-audit) drop >100%-of-mcap cash operating shells: HOLO (net-cash 677%, pb 0.11), MLGO (366%) are RED-verdict reverse-split ADR pumps where the sub-book print is a serial-dilution artifact, not tangible value.
        (nde <= 4.0)                            # not melting the 'floor' under a heavy debt load
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
    df['arch_lindy_fcf'] = (
        is_operating &                               # (R1b) exclude financials/REITs
        _roce_now_ok & _not_melting &                # (R4) current returns not negative; (deep-audit) _roce_now_ok is NaN-permissive, so a NaN-roce op&fcf melter (DSNY op-21.6%/fcf-0.8%/roce NaN) slipped through — _not_melting closes the leak.
        (years_of_history >= 5) &                    # (R4) real multi-cycle history, not a 1-yr shell
        (n_yrs_fcf_pos >= 4) &
        (n_yrs_opinc_pos >= 4)
    ).fillna(False).astype(int)

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
        (((shares_growth_3y <= 0.02) & _not_split_3y) |
         (_ncol('shares_growth_3y').isna() & (_ncol('shares_yoy') <= 0.01)
          & _not_split_yoy)) &
        (n_yrs_fcf_pos >= 4) &
        (n_yrs_roic_pos >= 4)
    ).fillna(False).astype(int)

    # ---------- Z-AC: Capital-allocation archetypes (audit June 2026) ---------
    # Directly extracted from EDGAR XBRL: payments of dividends + buybacks +
    # SBC + real effective tax rate. Distinct from the prior shares-growth
    # proxies in NoDilution / BuybackCompounder — these use the actual cash
    # spent rather than inferring from share count.
    capital_return_yield = s('capital_return_yield', np.nan)
    dividend_yield = s('dividend_yield', np.nan)
    buyback_yield = s('buyback_yield', np.nan)
    sbc_pct_revenue = s('sbc_pct_revenue', np.nan)
    effective_tax_rate = s('effective_tax_rate', np.nan)
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
    _covered = (_fcf_y > 0) | _fcf_y.isna()
    df['arch_capital_returner'] = (
        is_operating &                                    # (G1) exclude REIT/BDC mandatory payouts
        (((capital_return_yield >= 0.05) & (capital_return_yield <= 0.30)) |
         ((_tot_yield >= 0.05) & (_tot_yield <= 0.30)))   # >30% total yield =
                                                          # stale price / return-
                                                          # of-capital artifact
        & _covered
    ).fillna(False).astype(int)

    # Z2 — Balance-Sheet Return / Cash-Rich Runoff: a DISTINCT thesis, not an
    # operating compounder. Companies returning cash NOT generated by
    # operations (dividends/buybacks while FCF is negative — funded from the
    # balance sheet), PLUS negative-EV businesses (net cash exceeds market
    # cap). Separated out so the operating capital-returner stays FCF-covered,
    # and so these cash-rich / self-liquidating situations get their own home.
    _returns_any = ((capital_return_yield >= 0.02) |
                    (_tot_yield >= 0.02)).fillna(False)
    _uncovered = _returns_any & (_fcf_y < 0)
    # (G1) the negative-EV leg must exclude financials/REITs/utilities, whose
    # EV goes hugely negative on deposits/float (not distributable cash).
    _neg_ev = (((_ncol('enterprise_value') < 0) | (cash_gt_ev > 0))
               & is_operating).fillna(False)
    df['arch_balance_sheet_return'] = (
        is_operating & (mcap > 0) & (_uncovered | _neg_ev)
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
         ((_roic_asbc > 0.10) & ((_roce_n - _roic_asbc).abs() < 0.02))) &
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
        (pretax_pos > 0) &
        (s('op_margin', np.nan) > 0)            # real OPERATING profit, not a cash-pile interest print (WIMI op_margin -9%)
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
        ((interest_coverage >= 8.0) |        # real coverage leg
         (nde <= 0.0) |                      # outright net cash (guarded series)
         (net_cash_pct_sane >= 0.20)) &      # deep net cash, sane denominator
        (_ebitda_ttm_guard > 0) &
        (ebitda_margin_sane > 0)             # sane operating profitability
    ).fillna(False).astype(int)

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
        (_fs_yoy_q, lambda x: x >= 0.25),                    # true quarterly YoY
        (_fs_yoy_fy, lambda x: x >= 0.25),                   # annual base
        (fastest_segment_yoy, lambda x: x >= 0.25),          # legacy robust max
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
        [_fs_yoy_q, _fs_yoy_fy, fastest_segment_yoy], axis=1).max(axis=1)
    df['arch_fastest_segment'] = (
        is_operating &                          # (R8) financials/land-sale one-offs excluded
        (_ncol('revenue_ttm_usd') >= 20e6) &    # (tail) a hidden GROWTH ENGINE needs a real base, not a $0.84M shell (CKX/BYAH)
        _not_melting &                          # (tail) not a -952%-EBITDA-margin burner (BYAH)
        (_ncol('rev_yoy') > -0.10) & ~(_ncol('revenue_3y_cagr') < -0.05) &  # (deep-audit) whole-company decline guard: a "hidden growth engine" inside a company whose TOTAL revenue is collapsing (VISN rev-84%, TRS/THRY shrinking) is a divestiture/wind-down, not a hidden engine. Mix-shift requires the parent not to be melting away (missing => pass).
        (segment_count >= 2) & seg_inflect_any & (_seg_any_growth >= 0.10)
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
        (years_of_history >= 5)
    ).fillna(False).astype(int)

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
    _qc_common = (is_operating & _roce_now_ok & (insider >= 0.10)
                  & (_m12_raw.fillna(_py_raw).between(-0.10, 0.30)
                     & (_m12_raw.notna() | _py_raw.notna())))
    _qc_us = ((roic_lindy >= 0.15) & (n_yrs_roic_pos >= 4)
              & (shares_growth_3y <= 0.03) & (years_of_history >= 5))
    _qc_global = ((country != 'US') & (s('roce', np.nan) >= 0.15)
                  & ~_roce_oneoff_suspect & _not_melting
                  & ~(_ncol('shares_yoy') > 0.03))
    df['arch_quiet_compounder'] = (
        _qc_common & (_qc_us | _qc_global)
    ).fillna(False).astype(int)

    # S — Buyback Compounder: shrinking share count + durable ROIC + clean
    # balance sheet. Greenblatt / capital-allocation classic.
    # (G10) reverse-split guard: a share-count drop < -30% in one period is a
    # split / restructuring, not a buyback — such a drop counts only when a
    # real buyback yield corroborates it. A direct buyback_yield>=0.03 stays.
    _bb_yield_pos = (_ncol('buyback_yield') > 0)
    _shares_shrink = (
        ((shares_growth_5y <= -0.05) &
         ((shares_growth_5y >= -0.30) | _bb_yield_pos)) |
        ((_ncol('shares_growth_3y') <= -0.03) &
         ((_ncol('shares_growth_3y') >= -0.30) | _bb_yield_pos)) |
        (_ncol('buyback_yield') >= 0.03)
    )
    df['arch_buyback_compounder'] = (
        is_operating &                          # (R1b) exclude financials/utilities/lenders (buybacks funded by float/book)
        _roce_now_ok &                          # (R4) current returns not negative
        _shares_shrink &
        (roic_lindy >= 0.08) &
        (n_yrs_roic_pos >= 4) &
        (nde <= 1.5)
    ).fillna(False).astype(int)

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
              & (shares_growth_3y <= 0.02) & (years_of_history >= 5))
    _oo_global = ((country != 'US') & (s('roce', np.nan) >= 0.12)
                  & ~_roce_oneoff_suspect & (fcf_yield > 0)
                  & ~(_ncol('shares_yoy') > 0.02))
    df['arch_owner_operator'] = (
        _oo_common & (_oo_us | _oo_global)
    ).fillna(False).astype(int)

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
        (roiic_lindy >= 0.15) &
        _qarp_cheap &
        (n_yrs_roic_pos >= 4) &
        (shares_growth_3y <= 0.02)
    ).fillna(False).astype(int)

    # V — Reinvestment Inflection: ROIIC accelerating from a positive
    # base AND assets actually growing (not financial-engineering). The
    # signature of a compounder finding more runway.
    df['arch_reinvest_inflect'] = (
        is_operating &                          # (R1b) exclude financials/REITs (sibling durable/cash_reinvest carry this)
        _roce_now_ok &                          # (R4) current returns not negative (melting-name guard)
        (roiic_lindy >= 0.05) &
        (roiic_acceleration_v >= 0.05) &
        (asset_3y_cagr_v >= 0.05)
    ).fillna(False).astype(int)

    # W — Double Inflection: BOTH NOPAT-ROIC AND cash-ROIC crossed zero
    # from below in the latest year. Confirms the inflection is real
    # cash, not accounting-driven (D&A timing, accruals).
    df['arch_double_inflect'] = (
        is_operating &                          # (R1b) exclude financials/REITs
        (roic_inflect_v == 1) &
        (cash_roic_inflect_v == 1) &
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
        ((cash_roic_lindy - roic_lindy) >= 0.05) &
        (shares_growth_3y <= 0.05) &            # non-dilution: the cash-earnings gap must not be an SBC add-back on a serial diluter
        (n_yrs_fcf_pos >= 4)
    ).fillna(False).astype(int)

    # ---------- Large-Cap Quality (compounder at scale) ----------
    # A durable large-cap franchise: big, highly profitable, cash-generative,
    # conservatively financed, and either returning cash or compounding at a
    # high rate. The asymmetry/multibagger screen is small-cap-tilted, so
    # these quality giants never surface there — this archetype gives them a
    # home. Core gate uses GLOBALLY-available quality signals (margin / FCF /
    # leverage / payout); ROIC is a bonus qualifier where EDGAR provides it.
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
        (n_yrs_roic_pos >= 3) &
        ((roic_acceleration_v > 0) | (roic_lindy > 0.10))
    ).fillna(False).astype(int)

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
        (nde <= 2.5) &
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

    # ---------- Lynch multiples (One Up on Wall Street) ----------
    # PEGY = P/E / (earnings growth% + dividend yield%). Lynch: <=1.0 is
    # fair-or-better, growth+income you aren't paying for. The EV variant
    # applies the same idea capital-structure-neutral: EV/EBITDA /
    # (EBITDA growth% + dividend yield%) — threshold scaled to 0.6 since
    # EV/EBITDA runs ~60% of P/E for the same business. Both ratios are
    # computed in derive_missing_columns.py with growth capped at 100% so a
    # one-off doubling can't manufacture a sub-0.1 multiple.
    # Each ratio also accepts a same-family fallback so a missing upstream
    # column doesn't erase the archetype: PEGY falls back to a recompute
    # from p_e + growth + dividend; EV-GY falls back to the sales-based
    # analogues (psg / evsg), which express the identical
    # cheap-relative-to-growth fact through a different accounting measure.
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
    # (G9) require real positive EBITDA on the EBITDA-yield path (a negative
    # EBITDA makes the ratio meaningless), and drop the sales (psg/evsg)
    # fallback for negative-EBITDA names while guarding a near-zero-EV
    # denominator (ev_sales >= 0.05 rejects the EV~0 artifact that otherwise
    # passes the cheap gate spuriously).
    _ebitda_ttm_e = _ncol('ebitda_ttm')
    _ev_sales_g = s('ev_sales', 99.0)
    df['arch_lynch_evgy'] = (
        is_operating &                          # (tail) EV/EBITDA-based → meaningless for financials (TUGU/Indara insurers); P/E-based lynch_pegy correctly omits this
        (((evgy_v > 0) & (evgy_v <= 0.6) & (_ebitda_ttm_e > 0)) |
         (_evgy_missing & (_ebitda_ttm_e > 0) & (_ev_sales_g >= 0.05) &
          (((_psg_e > 0) & (_psg_e <= 0.06)) |
           ((_evsg_e > 0) & (_evsg_e <= 0.05)))))
    ).fillna(False).astype(int)

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
    # (G5) PRESENCE mask: a NaN n_analysts (unrated) must NOT read as
    # "maximally neglected". Neglect gates require the field actually present.
    n_analysts_present = (_ncol('n_analysts')
                          .fillna(_ncol('n_analysts_pew'))).notna()
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
    _ev_mcap_garp = (_ncol('enterprise_value') / mcap.where(mcap > 0))
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
        ((_ebit_g > 0) | (rev_yoy_c >= 0.08))       # ...on a growing earnings/rev stream
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
    _returning = ((_nby > 0) | (_ndy > 0.01) | (_nsh3 < -0.01)
                  | (_nbb > 0)).fillna(False)
    df['arch_net_cash_returner'] = (
        is_operating & (mcap > 0)
        & (net_cash_pct >= 0.30)
        & _returning
        & _not_melting   # (deep-audit) a company returning cash while DESTROYING capital is the anti-thesis: YXT roce-97%, DCGO roce-95% passed on net-cash + a one-off FCF print. Add the returns floor.
    ).fillna(False).astype(int)

    # Sustainable Scaler: small-cap durable growth that is REAL — a genuine
    # revenue base (>= $20M, not a base-effect pop), NOT funded by dilution
    # (share count flat/down), growth confirmed either by a durable 3y CAGR or
    # by PER-SHARE FCF growth (immune to acquisition-by-dilution), self-funding
    # unit economics, and not overpriced on EV/sales. The home for genuine
    # small-cap compounders the base-effect growth guards now exclude.
    _sr3 = _num('rev_3y_cagr'); _sry = _num('rev_yoy'); _sfps = _num('fcf_per_share_yoy')
    _sfm = _num('fcf_margin'); _ssh3 = _num('shares_3y_cagr'); _srev = _num('revenue_ttm_usd')   # (R6+FX) USD revenue, not raw local currency
    _sroic = _num('roic_after_sbc'); _sevs = _num('ev_sales')
    _durable_growth = (((_sr3 >= 0.15) & (_sr3 <= 1.0))
                       | ((_sry >= 0.15) & (_sry <= 1.0) & (_sfps > 0)))
    _self_funding = (_sfps > 0) | (_sfm > 0.03) | (_sroic >= 0.10)
    _not_pricey = ((_sevs > 0) & (_sevs <= 8)) | _sevs.isna()
    df['arch_sustainable_scaler'] = (
        is_operating & (mcap < 2e9) & (_srev >= 5e6)
        & (_ssh3.fillna(0) <= 0.05)
        & _durable_growth & _self_funding & _not_pricey
        & _profit_present                        # (reference II) profitability LEVEL present
    ).fillna(False).astype(int)

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
    _c2 = (_coff <= -0.50) | (_c5y <= 0.20)
    # (3) P/E < min(10, 1/LT-corporate-bond-rate) — the earnings yield must
    #     also clear the bond yield [C]. In a low-rate regime 10 binds; in a
    #     high-rate regime 1/rate binds (r=12% -> P/E<8.3). Rate is a research
    #     parameter [R]; set to a current LT investment-grade corporate yield.
    _LT_CORP_BOND_RATE = 0.055
    _cundill_pe_cap = min(10.0, 1.0 / _LT_CORP_BOND_RATE)
    _c3 = (_cpe > 0) & (_cpe <= _cundill_pe_cap)
    # (4) profitable; preferably no deficits over 5y  [C]
    _c4 = ((_croce > 0) | (_ceb > 0)) & ((_ceps_pos >= 0.6) | _ceps_pos.isna())
    # (5) paying dividends  [C]
    _c5 = _cdiv > 0
    # (6) debt judiciously employed, room to expand  [C] (financials exempt)
    _c6 = (((_cnde.fillna(99) < 2.5) | (_cd2e.fillna(99) < 1.0) | (_cncash > 0))
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
                            + 0.10 * _ramp(_ceps_pos, 0.6, 1.0)     # no deficits
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
    df['arch_wolf_trifecta'] = (
        is_operating &                              # (R1b) exclude financials/REITs
        (mcap >= 10e6) & (mcap <= 300e6) &
        (_num('revenue_ttm_usd') >= 10e6) &         # real revenue base (microcap-appropriate floor)
        (rev_yoy_c >= 0.15) &                       # "double-digit", not 50%
        oper_lev_any &                              # operating leverage (any of 6 angles)
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
        ((ebitda_first_pos > 0) | (cfo_first_pos > 0) |
         (fcf_first_pos > 0) | (ni_first_pos > 0) |
         (cfo_inflection > 0) | (fcf_inflection > 0) |
         ((ebitda_inflection > 0) & oper_lev_any)) &
        # a genuine TURNAROUND is a low-margin business crossing to black, NOT an
        # already-solidly-profitable compounder whose CFO merely ticked up. Cap
        # the current operating margin so established earners fall out; the LOWER
        # bound keeps it a name approaching black, not a deep loss-maker (op-65%).
        (s('op_margin', np.nan) < 0.15) & (s('op_margin', np.nan) > -0.30) &
        (emd_c >= 0.0) &
        (rev_yoy_c >= 0.0) & rev_present &          # growing (present), not shrinking
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
        ((net_cash_pct_c >= 0.20) | (cash_gt_ev > 0) | (ncav_pct >= 0.50)) &
        ((rev_yoy_c >= 0.10) | ((rev_growth_score >= 0.5) & (rev_yoy_c >= 0))) &  # a GROWING thesis is not a declining top line (TTEC rev -3.2%)
        (cfo_ttm_v > 0) &
        _not_melting &                              # (tail) survivability — cash-on-cash-aware + improvement-lenient (per user: demote melters via melt_demotion, don't bar cash-generative/inflecting names).
        ((fcf_yield >= 0.08) |
         ((ev_ebitda_v > 0) & (ev_ebitda_v < 6.0)))

        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)

    # D — Emerging-sector profitability (his cautious cannabis bets). His one
    # such pick (Simply Solventless/HASH) blew up -57% on accounting + cash
    # problems, so gate hard on POSITIVE OPERATING CASH FLOW (not just EBITDA)
    # and clean SBC — exactly what would have excluded HASH.
    # (inflection-audit) DROP 'tobacco': it dragged in mature Big Tobacco majors
    # (Gudang Garam, Sampoerna, Japan Tobacco, Scandinavian Tobacco), the exact
    # mature/declining population this "cautious cannabis bets" thesis avoids.
    _emerging = (_ind.str.contains('cannabis|hemp|marijuana|psychedelic', regex=True) |
                 _nm.str.contains('cannabis|hemp', regex=True))
    # The HASH-lesson discipline that MATTERS is the hard positive-CFO + clean-SBC
    # gate; the deep-value price cut (pe<10/EV<6) is too strict for a nascent
    # grower and left the archetype empty once mature tobacco was removed. Keep
    # the cash discipline, widen the cheapness to a reasonable-multiple band.
    df['arch_wolf_emerging'] = (
        _emerging &
        (cfo_ttm_v > 0) &
        low_sbc_wolf &
        (((pe_w > 0) & (pe_w < 20.0)) | ((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)))
    ).fillna(False).astype(int)

    # E — "Seal of Approval" fresh trigger: an earnings inflection bought on
    # a post-earnings dip. Loosened the drawdown gate (he buys before the
    # full run) and added his valuation discipline (the KITS lesson).
    df['arch_wolf_seal'] = (
        (mcap > 0) & (mcap < 500e6) &
        inflection_print &
        (mom12 >= 0.10) &
        not_too_deep_any(0.50) &
        _not_melting &   # (deep-audit) the only wolf gate with NO melting floor — inflection_print (a one-off EBITDA print) admitted confirmed op-loss+FCF-burn shells: 0128.HK op-46%/fcf-, CTO.SI op-65% on a rev+2626% base. Trims ~92 melters, keeps genuine first-positive inflections.
        (((ev_ebitda_v > 0) & (ev_ebitda_v < 15.0)) | ((pe_w > 0) & (pe_w < 25.0)))

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

    # F — NEW: Wolf Compounder — his signature winner (NCI/ZOMD/KITS-at-entry):
    # a sustained, ACCELERATING grower bought at a single-digit/low-teens
    # multiple, margins expanding, cash-positive, low dilution. Isolates the
    # multi-quarter streak the single-period trifecta gate can miss.
    df['arch_wolf_compounder'] = (
        (mcap >= 10e6) & (mcap <= 150e6) &
        (_num('revenue_ttm_usd') >= 10e6) &         # real revenue base (base-effect guard: Dong A Eltek +234%)
        (rev_yoy_c >= 0.25) & (rev_yoy_c <= 1.5) &  # accelerating streak, NOT a base-effect explosion
        (rev_accel > 0) &
        (s('op_margin', np.nan) > 0) &              # profitable compounder, not Bengal Tea op_margin -160%
        _roce_now_ok &                              # (fresh) a compounder does not destroy capital (SOGP roce-96%)
        ~(_num('shares_yoy') > 0.20) &              # low dilution — not ADESE (+400% shares)
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &
        oper_lev_any &
        (((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)) |
         ((pe_w > 0) & (pe_w < 20.0))) &
        low_sbc_wolf
        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)

    # ---------- Liger Cub / Byron Street family ----------
    # Long-only public-information arbitrage in NEGLECTED microcaps. His edge
    # is OSINT (unscreenable); these capture the financial preconditions his
    # documented longs (RCMT, VTSI) shared: neglect (<=3-4 analysts), no
    # dilution, survivable balance sheet, near-breakeven-or-better cash flow
    # (this gate correctly REJECTS the WATT cash-burner, whose edge was pure
    # OSINT), depressed/off-highs, and NOT mining/biotech/crypto.
    df['arch_liger_asset_backed'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 400e6) &
        (net_cash_pct_c >= 0.20) & _netcash_not_contradicted &  # GENUINE net cash (nde not materially positive)
        ((pb > 0) & (pb < 3.0)) &                   # "asset-backed" needs a real book anchor (WINE.L pb 75 is not asset-backed)
        (~(n_analysts_v > 4)) &                       # (twosided) MISSING coverage = MOST neglected (the thesis); mcap cap prevents mega-cap re-admit
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
        (((rev_yoy_c >= 0.10) & (rev_accel > 0)) | (rev_yoy_c >= 0.15) | oper_lev_any) &
        # (gate audit #3) cash_conversion reads falsely positive when CFO
        # and EBITDA are BOTH negative — trust it only over positive EBITDA
        (((cash_conv_w >= 0.80) & (ebitda_ttm_v > 0)) | (fcf_margin_w > 0)) &
        _clean_bs(1.5) &                            # clean b/s (nde OR net-cash)
        (~(n_analysts_v > 4)) &                       # (twosided) MISSING coverage = MOST neglected (the thesis); mcap cap prevents mega-cap re-admit
        low_sbc_liger &
        liger_sector_ok &
        (flat_or_down | beaten_down_any(0.30))    # presence-aware lag/drawdown
    ).fillna(False).astype(int)

    # NEW: Liger Neglected Survivor — the single best proxy for his edge:
    # neglected + financially survivable (no dilution) + cheap, with an early
    # inflection and room to re-rate on a material catalyst. RCMT & VTSI pass;
    # WATT is intentionally rejected by the near-breakeven gate.
    df['arch_liger_neglected_survivor'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap >= 5e6) & (mcap <= 400e6) &           # (deep-audit) floor 20e6->5e6: it was binding at exactly $20.005M, cutting the sub-$20M nano cohort this "neglected survivor, 0 analysts ideally" thesis MOST targets (RCMT/VTSI were tiny). Both siblings have no such floor; 5e6 keeps a shell guard.
        (~(n_analysts_v > 3)) &                       # (twosided) MISSING coverage = MOST neglected (the thesis)
        (((net_cash_pct_c >= 0.15) & _netcash_not_contradicted) | ((ebitda_ttm_v > 0) & (nde <= 1.5))) &
        ((fcf_margin_w >= 0.0) | (op_margin_v >= -0.02)) &
        low_sbc_liger &
        (beaten_down_any(0.30) | ((ev_sales_v > 0) & (ev_sales_v <= 2.0))) &
        ((rev_accel > 0) | oper_lev_any) &
        liger_sector_ok
    ).fillna(False).astype(int)

    # ---------- Oak Bloke special situations ----------
    # Every Oak winner pairs cheapness with a CASH-RICH, cash-generative
    # balance sheet; every trap (Belluscura -96.6%) was a cash-burner needing
    # external capital. So each screen now carries a solvency/cash gate.
    #
    # Resource leverage — low-cost producer in the bottom half of the cost
    # curve, bought NET-CASH on price weakness (Thungela: ~75% of price was
    # cash, P/E<1). Added cash floor + high-margin (cost-curve) proxy +
    # bought-on-weakness; loosened EV/EBITDA to 8 so the very cheapest qualify.
    df['arch_oak_resource_leverage'] = (
        sector.isin({'Materials', 'Energy'}) &
        (ev_ebitda_v > 0) & (ev_ebitda_v < 8.0) &
        _clean_bs(1.5) &
        (net_cash_pct_c >= 0.20) &                  # NET-cash survivability (not gross cash)
        (ebitda_margin >= 0.25) &                   # cost-curve proxy
        ((fcf_yield >= 0.08) | (_ncol('robust_cash_yield') >= 0.08) |
         (_ncol('owner_earnings_yield') >= 0.08)) &
        beaten_down_any(0.20)                       # bought on weakness (any lens)
    ).fillna(False).astype(int)

    # Deleveraging/yield — heavy FCF, moderate debt being paid down (rising
    # EBITDA mechanically cuts the ratio = his actual thesis), material
    # shareholder return. Yield floor raised to DEC-scale; solvency soft gate.
    df['arch_oak_deleveraging'] = (
        is_operating &                              # (R1b) exclude financials/REITs (mandatory-leverage biz)
        _roce_now_ok & (s('op_margin', np.nan) > 0) &  # returns floor: a deleveraging compounder earns real operating profit (NIC Autotec p/e 169 out)
        ((fcf_yield >= 0.10) | (_ncol('robust_cash_yield') >= 0.10) |
         (_ncol('owner_earnings_yield') >= 0.10)) &
        (ebitda_ttm_v > 0) & (nde >= 1.0) & (nde <= 3.0) &
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0) | oper_lev_any) &   # leverage trajectory (any angle)
        ((div_yield_v >= 0.06) | (s('capital_return_yield', 0.0) >= 0.06)) &
        _soft_ok_above('interest_coverage', 2.0)
    ).fillna(False).astype(int)

    # Distressed deep value with a hard-asset parachute — crushed price, deep
    # discount to book OR net-net, real cash, still cash-GENERATIVE (the
    # Belluscura gate: positive EBITDA alone isn't enough, require FCF/CFO>0).
    df['arch_oak_deep_value'] = (
        is_operating &                              # (R1b) RE developers (Shimao) / brokers: book & leverage not comparable
        beaten_down_any(0.50) &
        (((pb > 0) & (pb < 0.7)) | (ncav_pct >= 0.5) | (cheap_score >= 0.5)) &   # deep sub-book OR net-net OR cheap-across-multiples
        (cash_pct_mcap_v >= 0.20) &
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
    df['arch_oak_nav_discount'] = (
        sector.isin({'Financials'}) & _nav_vehicle & _nav_not_eroding &
        (((pb > 0) & (pb < 0.7)) | ((_ptb_nav > 0) & (_ptb_nav < 0.7))) &
        ((div_yield_v >= 0.05) | (_ncol('capital_return_yield') >= 0.06))
    ).fillna(False).astype(int)

    # NEW: Oak asset floor — market cap at/below cash + hard assets (CVV/PRTC).
    # Well-captured on the CASH leg (net cash or NCAV >= mcap = Graham floor);
    # does NOT see hidden real-estate-at-market or private-stake value.
    df['arch_oak_asset_floor'] = (
        is_operating &                              # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 500e6) &
        ((net_cash_pct_c >= 0.40) | (ncav_pct >= 0.80)) &
        (pb > 0) & (pb < 1.5) &
        ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &        # (G6) survivability (match oak siblings)
        _not_melting   # (deep-audit) the Graham cash floor protects the balance sheet but not against operations eating it: DCGO roce-95%, 0738.HK roce-70% passed. Add the returns floor (SOGP roce-96%/op+7% is a denominator artifact, correctly kept).
    ).fillna(False).astype(int)

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
    _hidden_pct = ((_ev_ha + _ca_ha - _mc_ha - _td_ha)
                   / _mc_ha.where(_mc_ha > 0))
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
        (pb > 0) & (pb < 1.5) &                     # the portfolio is not being paid for
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
    _dna_loc = _ncol('ebitda_ttm') - _ebit_loc
    _capex_loc = _ncol('capex_ttm')
    df['arch_overdepreciated_assets'] = (
        is_operating & (mcap > 0) &
        (_dna_loc > 0) & (_rev_loc > 0) &
        ((_dna_loc / _rev_loc) >= 0.05) &          # a real fixed-asset business (D&A >= 5% of sales)
        (_capex_loc >= 0) & (_capex_loc <= 0.6 * _dna_loc) &  # replacement FAR below depreciation
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
    _pe_ue = _ncol('p_e')
    df['arch_understated_earnings'] = (
        is_operating & (mcap > 0) &
        (_ni_loc > 0) &
        (_cfo_ni >= 1.5) & (_cfo_ni <= 4.0) &      # cash well above book earnings; sane band (beyond 4x = distortion, not conservatism)
        ((_ncol('cash_conversion') >= 1.1) | (fcf_yield >= 0.10)) &  # durability corroboration, not one working-capital swing
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
    # operating business comes free plus change. 0 < adj P/E <= 8 is the cheap
    # band. All components LOCAL currency. CAVEAT (documented): the data has no
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
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # F5 — Owner-earnings power (Buffett's adjustment as a forensic lens).
    # Owner earnings = NI + D&A - capex: when depreciation persistently
    # overstates true asset consumption (D&A >> replacement capex), accounting
    # NI UNDERSTATES the cash the owner actually keeps. Fire when owner
    # earnings run >=1.4x reported NI and the price is <=10x OWNER earnings —
    # cheap on the truer measure while the market prices the accounting one.
    _oe_loc = _ni_ca + (_dna_loc - _capex_loc)
    _oe_ratio = (_oe_loc / _ni_ca).where(_ni_ca > 0)
    df['arch_owner_earnings_power'] = (
        is_operating & (_mc_ca > 0) &
        _fx_coherent &
        (_ni_ca > 0) & (_dna_loc > 0) & (_capex_loc >= 0) &
        (_oe_ratio >= 1.4) &                        # owner earnings far above accounting earnings
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
    df['arch_customer_float'] = (
        is_operating & (_mc_f7 > 0) &
        (_nwc_f8 < 0) &                              # customers/suppliers fund operations
        (s('op_margin', np.nan) > 0.03) &
        (rev_yoy_c >= 0.0) &                         # float grows WITH the business, not a liquidation
        ((_ncol('cfo_ttm') / _ncol('net_income_ttm').where(_ncol('net_income_ttm') > 0)) >= 1.1) &
        _not_melting
    ).fillna(False).astype(int)

    # F9 — Capex-famine harvest: the investment cycle is ENDING (current capex
    # far below the audited 5-year average) while revenue holds — the FCF
    # inflection is mechanically loaded before it prints. Needs capex_avg
    # (EDGAR annual series).
    _cx_f9 = _ncol('capex_ttm')
    _cxa_f9 = _ncol('capex_avg')
    df['arch_capex_famine_harvest'] = (
        is_operating & (_mc_f7 > 0) &
        (_cxa_f9 > 0) & (_cx_f9 >= 0) &
        (_cx_f9 <= 0.6 * _cxa_f9) &                  # spending far below its own history
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
    df['arch_dividend_verified_value'] = (
        is_operating & (_mc_f7 > 0) &
        _fx_coherent &                              # (gate audit #2, completed) payout vs local NI/FCF
        (_dy_f10 >= 0.06) &                          # a fat, real payout
        (_ni_f10 > 0) & (_div_paid <= 0.70 * _ni_f10) &
        (_fcf_f10 > 0) & (_div_paid <= 0.70 * _fcf_f10) &
        (pb > 0) & (pb < 1.0) &                      # and the market still prices sub-book
        _not_melting
    ).fillna(False).astype(int)

    # F11 — Tax-verified earnings ('Forensic-TaxProof', EDGAR). You do not pay
    # real cash taxes on fake earnings: a FULL effective tax rate (18-40%) on
    # positive pretax income is the tax authority auditing the P&L for us.
    # Cheap on those verified earnings = forensic value. (Inverse cousin of
    # arch_tax_efficient, which hunts LOW structural rates.)
    _etr_f11 = _ncol('effective_tax_rate')
    _pretax_f11 = _ncol('pretax_income_ttm')
    df['arch_tax_verified_earnings'] = (
        is_operating & (mcap > 0) &
        (_pretax_f11 > 0) &
        (_etr_f11 >= 0.18) & (_etr_f11 <= 0.40) &     # really paying the state
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
                      & ~(_ncol('shares_yoy') > 0)))
    df['arch_cannibal_at_discount'] = (
        is_operating & (mcap > 0) &
        (pb > 0) & (pb < 1.0) &                       # buying below book
        _shrink_f12 &
        ~(_ncol('shares_yoy') < -0.30) &              # a -30% collapse is a restructuring, not a buyback
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
    df['arch_self_funded_returner'] = (
        is_operating & (mcap > 0) &
        (_fincf_f13 < 0) &                            # net capital OUT to providers
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
    _eqc_f14 = _ncol('equity_cagr_5y')
    df['arch_book_compounder_discount'] = (
        ~is_reit & (mcap > 0) &
        (_eqc_f14 >= 0.08) &
        (pb > 0) & (pb < 1.0) &
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)) &
        _not_melting
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
         | (_ncol('rev_yoy_streak_q') >= 8)) &
        _profit_present &
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
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)) &
        (_ncol('dividend_yield') >= 0.03) &
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
                   | ((rev_accel > 0) & oper_lev_any))
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
    # (>=40% off the high, or the bottom third of the 5-year range) and cheap
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
    _xr_crisis = ((_num('pct_off_52w_high') <= -0.40)
                  | (_num('price_pct_of_5y_range') <= 0.30))
    _xr_cheap = (((pb > 0) & (pb < 1.2))
                 | ((_ncol('p_e') > 0) & (_ncol('p_e') <= 10.0))
                 | (fcf_yield >= 0.10))
    df['arch_xr_quality_crisis'] = (
        is_operating & (mcap > 0) &
        _xr_quality & _xr_crisis & _xr_cheap &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # ---------- XR x FORENSIC crossovers (user request) ----------
    # XR5 — Forensic floor under growth ('XR-ForensicFloorGrowth'): the floor
    # is INVISIBLE to standard screens — off-EV securities (hidden-asset gap),
    # retained earnings above 1.5x the price, or an over-depreciated asset
    # base — while the business on top GROWS. Convexity nobody screens for
    # because the support is not in standard metrics.
    _xr5_floor = ((_hidden_pct >= 0.50)
                  | ((_ncol('retained_earnings') / _ncol('market_cap').where(_ncol('market_cap') > 0)) >= 1.5)
                  | ((_dna_loc > 0) & (_capex_loc >= 0)
                     & (_capex_loc <= 0.5 * _dna_loc) & ((_dna_loc / _rev_loc.where(_rev_loc > 0)) >= 0.05)))
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
        ((_pe_head >= 15.0) | _pe_head.isna()) &       # headline: dear or meaningless
        (_ncol('net_income_ttm') > 0) &                # real (not loss-masked) accounting
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
        (_dna_loc > 0) & (_capex_loc >= 0) & (_capex_loc <= 0.5 * _dna_loc) &
        (_payout_x7 >= 0.06) &
        (pb > 0) & (pb < 1.0) &
        ((_oe_loc > 0) | (_ncol('oe_avg') > 0)) &
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
        (nde >= 2.0) & (nde < 90) &
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
        ((_ncol('dividend_yield') >= 0.02) | (_ncol('buyback_yield') > 0)) &
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
        ((_ncol('rev_yoy_streak_q') >= 4) | (rev_yoy_c >= 0.10)) &
        (((_ncol('ev_ebit') > 0) & (_ncol('ev_ebit') <= 14))
         | ((_ncol('p_e') > 0) & (_ncol('p_e') <= 18))) &
        ~(_ncol('shares_yoy') > 0.02) &
        _not_melting
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
    df['arch_xr_float_compounding'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_nwc_x12 < 0) &                                   # the float exists
        ((_cfo_ni_x12 >= 1.3) | (_ncol('cash_conversion') >= 1.2)) &
        ((rev_accel > 0) | (rev_yoy_c >= 0.15)) &          # bookings engine turning
        ((_ncol('p_e') >= 20) | _ncol('p_e').isna()) &     # headline looks dear/meaningless
        ((_ncol('market_cap') / _ncol('cfo_ttm').where(_ncol('cfo_ttm') > 0)) <= 15) &
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
    _nrm_eb_x13 = _ncol('normalized_ebitda')
    _ev_nrm_x13 = (_ncol('enterprise_value') / _nrm_eb_x13.where(_nrm_eb_x13 > 0))
    df['arch_xr_bigbath_rebound'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_nrm_eb_x13 > 0) &
        ((ebitda_ttm_v < 0.6 * _nrm_eb_x13) | (_ncol('net_income_ttm') < 0)) &
        (_ncol('cfo_yield') > 0) &                          # the bath was non-cash
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
        (_capex_loc >= 0) & (_capex_loc <= 0.6 * _dna_loc) &
        (_oe_loc > 0) & ((_mc_ca / _oe_loc) <= 10.0) &      # cheap on the true cash take
        ((_ncol('p_e') >= 12) | _ncol('p_e').isna()) &      # dear/meaningless on polluted E
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
        (_num('cash_conversion') < 0.7) &                   # WC eating the cash
        (ebitda_ttm_v > 0) &
        (rev_yoy_c >= -0.05) &                              # demand intact
        (_num('gross_margin_delta_yoy') >= -0.03) &         # margins intact
        (nde < 3.0) &                                       # survives the cycle
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
        ((_ncol('buyback_yield') >= 0.02)
         | (_ncol('net_buyback_ttm') > 0)) &                # ...and they are BUYING
        ~(_ncol('shares_yoy') > 0.0) &                      # count actually not growing
        ((_ncol('net_income_ttm') > 0) | (_ncol('ni_avg') > 0)
         | (_ncol('cfo_yield') > 0)) &                      # a real business attached
        _not_melting
    ).fillna(False).astype(int)

    # XR18 — Double trough ('XR-DoubleTrough'): a TROUGH MULTIPLE on TROUGH
    # EARNINGS — price near multi-year lows, EV cheap against the MID-CYCLE
    # (normalized) base, and current earnings sitting BELOW that base (so
    # the cheapness is not peak-margin illusion), with survival assured.
    # Two discounts compound: the multiple re-rates AND earnings mean-revert.
    _nrm18 = _ncol('normalized_ebitda')
    _evn18 = (_ncol('enterprise_value') / _nrm18.where(_nrm18 > 0))
    _surv18 = ((net_cash_pct_c >= 0) | (_ncol('interest_coverage') >= 4)
               | ((nde > -90) & (nde <= 1.5)))
    df['arch_xr_double_trough'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ((_num('pct_off_52w_high') <= -0.50)
         | (_num('price_pct_of_5y_range') <= 0.15)) &
        (_evn18 > 0) & (_evn18 <= 5.0) &                    # cheap on MID-CYCLE earnings
        (ebitda_ttm_v > 0) & (ebitda_ttm_v <= 0.85 * _nrm18) &  # earnings AT the trough
        _surv18 &
        ~(_ncol('shares_yoy') > 0.05) &
        _not_melting
    ).fillna(False).astype(int)

    # XR19 — Forced-seller dislocation ('XR-ForcedSeller'): the price
    # COLLAPSED >=40% in a year in which the BUSINESS GREW on both lines
    # with no dilution — a seller-driven, not business-driven, mark
    # (index deletions, fund liquidations, spin-off orphans). Buying a
    # growing business from someone who must sell at any price.
    df['arch_xr_forced_seller'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        (_num('price_yoy') <= -0.40) &
        (rev_yoy_c >= 0.05) &
        ((ebitda_yoy_v >= 0) | (_ncol('net_income_ttm') > 0)) &
        ~(_ncol('shares_yoy') > 0.02) &
        ((nde < 3.0) | (net_cash_pct_c >= 0)) &
        _not_melting
    ).fillna(False).astype(int)

    # XR20 — Operating-leverage detonation ('XR-LeverageDetonation'): the
    # breakeven CROSSING with high drop-through — losses just flipped (or
    # are one step from flipping) while incremental margins run >=35% on
    # 20%+ growth. Historically the most violent PERCENTAGE re-ratings
    # occur exactly here: each new revenue dollar is suddenly mostly
    # profit, and trailing screens still price the loss-maker.
    df['arch_xr_leverage_detonation'] = (
        is_operating & (mcap > 0) & _fx_coherent &
        ((ebitda_first_pos > 0) | (fcf_first_pos > 0)
         | ((_num('fcf_eta_quarters') > 0) & (_num('fcf_eta_quarters') <= 2))) &
        (_num('incremental_ebitda_margin') >= 0.35) &
        (rev_yoy_c >= 0.20) & (rev_yoy_c <= 1.5) &
        ((_ncol('p_s') <= 3.0) | (_ncol('ev_sales') <= 3.0)) &
        (_ncol('revenue_ttm_usd') >= 10e6) &                # not a base-effect shell
        ~(_ncol('shares_yoy') > 0.10) &
        _not_melting
    ).fillna(False).astype(int)

    # F6 — Forensic payout confirmation (the user's BOOST leg). Any forensic /
    # hidden-value member that is ALSO returning capital — buying back shares
    # or paying a dividend — earns an EXTRA archetype count, which is this
    # system's native ranking boost (archetype density feeds ETA and the
    # convergence score). Revealed preference: management monetising the
    # hidden value for owners, not hoarding it.
    _payout_any = ((_ncol('dividend_yield') >= 0.005)
                   | (_ncol('buyback_yield') > 0)
                   | (_ncol('shares_yoy') < -0.01))
    _forensic_any = ((df['arch_hidden_assets'] == 1)
                     | (df['arch_retained_earnings_discount'] == 1)
                     | (df['arch_customer_float'] == 1)
                     | (df['arch_capex_famine_harvest'] == 1)
                     | (df['arch_dividend_verified_value'] == 1)
                     | (df['arch_tax_verified_earnings'] == 1)
                     | (df['arch_cannibal_at_discount'] == 1)
                     | (df['arch_self_funded_returner'] == 1)
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
        oper_lev_any &
        ((ebitda_inflection > 0) | (ebitda_yoy_v > 0))
    ).fillna(False).astype(int)

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
        ((ebitda_yoy_v >= 0) | (ebitda_inflection > 0) | oper_lev_any) &  # stable/rising (any angle)
        _soft_ok_above('interest_coverage', 1.0) &  # can service (soft; 8% cov)
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
        (rev_yoy_c <= 0.05) & oper_lev_any & strong_op_improvement &
        # (2) levered equity stub -> convexity (EV >> equity)
        heavy_debt &
        # (3) survivable + pledgeable income actively DELEVERAGING (EBITDA
        #     rising cuts the debt/EBITDA ratio and transfers value to equity)
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0)) &
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
    df['arch_levered_inflection'] = (
        is_operating &                           # (R1b) RE developers/REITs: structural leverage + revaluation EBITDA fakes the thesis
        (mcap > 0) & (mcap < 5e9) &
        oper_lev_any & strong_op_improvement &   # real operating improvement (any rev dir.)
        heavy_debt &                             # levered equity stub -> convexity
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &  # survivable + cash
        _not_melting &   # (deep-audit) the leakiest levered gate gains the survivability leg — now cash-on-cash-aware + improvement-lenient, so a genuine melting-ice stub with no cash and no inflection (LINK.JK op-47%/fcf-/roce-9%) fails, but a cash-generative or inflecting levered stub is kept (per user: demote, don't bar on op-margin alone).
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0)) &           # deleveraging (rising EBITDA)
        (((ev_ebitda_v > 0) & (ev_ebitda_v <= 8.0)) | (robust_cy >= 0.12)) &  # cheap
        beaten_down_any(0.25) &                  # beaten down / low expectations (any lens)
        _soft_ok_below('capex_intensity', 0.15)
    ).fillna(False).astype(int)

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
    df['arch_cheap_sales_scaler'] = (
        (mcap > 0) & (mcap < 5e9) &
        (_num('revenue_ttm_usd') >= 5e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (p_s_v >= 0.10) & (p_s_v <= 2.0) &       # cheap on revenues (lower bound kills
                                                 #   near-zero-mcap p_s artifacts)
        (rev_yoy_c >= 0.10) &                    # actually growing (double-digit)
        (((psg_v >= 0.005) & (psg_v <= 0.10)) |
         (_ncol('psg').isna() & (_ncol('evsg') >= 0.004) &
          (_ncol('evsg') <= 0.08))) &              # cheap RELATIVE to growth (PSG,
                                                 #   EVSG analog when PSG missing)
        oper_lev_any &                           # operating margins improving (any angle)
        near_profit &                            # at / near / just-crossed profitability
        _profit_present                          # (reference II) a real profitability LEVEL, not rate alone
    
        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

    # ---------- Exceptional EV/sales vs growth ----------
    # A fast grower priced at an EXCEPTIONALLY low EV/sales relative to that
    # growth (EVSG). Capital-structure-neutral (EV, not price) analog of PSG,
    # so it compares levered and unlevered growers fairly. We have no
    # organic-vs-total revenue split, so total revenue growth stands in for
    # organic. A light quality gate keeps out pre-revenue cash-burn shells.
    evsg_v = s('evsg', 99.0)
    df['arch_exceptional_evsg'] = (
        (mcap > 0) & (mcap < 20e9) &
        (_num('revenue_ttm_usd') >= 5e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (((evsg_v >= 0.002) & (evsg_v <= 0.05)) |
         (_ncol('evsg').isna() & (_ncol('psg') >= 0.0025) &
          (_ncol('psg') <= 0.06))) &               # EXCEPTIONAL EV/sales-to-growth
                                                 #   (PSG analog when EVSG missing)
        (rev_yoy_c >= 0.20) &                    # strong (organic-proxy) growth
        ((rev_yoy_c <= 1.0) | (_ncol('rev_3y_cagr') >= 0.15)) &  # (deep-audit) BASE-EFFECT guard: a huge one-year print mechanically makes EVSG (valuation/growth) look "exceptional" off a one-off denominator (B9A.F rev+346%/PE307, 088130.KQ +234%). A >100% YoY must be corroborated by a durable 3y CAGR (mirrors tenbagger's _g_confirmed discipline).
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
    df['arch_negative_ev_value'] = (
        is_operating &                                # (G1) exclude financials/REITs/utilities
        (mcap > 0) & (mcap < 5e9) &
        (neg_or_low_ev | ((pb > 0) & (pb < 0.7))) &   # cash floor OR deep sub-book
                                                      # (neg_or_low_ev already triangulates
                                                      #  the EV/cash floor the appropriate way)
        ((fcf_ttm_v > 0) | (ebitda_ttm_v > 0) | (net_cash_pct_sane >= 0.5)) &  # (G2) not a cash-burn trap
        _not_melting   # (deep-audit) the ebitda>0-alone leg was too weak: FOM roce-98%, WLN roce-99% passed while operationally melting. Cash-below-EV thesis intact; only the burning-operating subset is removed.
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
    p_fcf = mcap / fcf_ttm_v.where(fcf_ttm_v > 0)
    df['arch_growth_algo'] = (
        (mcap > 0) & (mcap < 50e9) &
        (_num('revenue_ttm_usd') >= 20e6) &      # (R6+FX) real USD revenue base — % growth is noise below this
        (rev_yoy_c >= 0.15) &                    # top-line (gross-profit) growth
        oper_lev_any &                           # operating leverage (EBIT outpaces sales)
        (fcf_ttm_v > 0) &
        ((fcf_yoy_v >= 0.20) |
         (_ncol('fcf_per_share_yoy') >= 0.20) |
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
    df['arch_asleep_at_wheel'] = (
        _asleep_beats_branch
        | _asleep_eps_branch
    ).fillna(False).astype(int)
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
    _no_rerate_au = ((_esc_au <= 0.10)
                     | ((_pyw_au <= _fund_g_au)
                        & _pyw_au.notna() & _fund_g_au.notna())
                     | (_pe_exp_au <= 0.10))
    _pe_au = _num('p_e')
    _not_rich_au = (((_pe_au > 0) & (_pe_au <= 25))
                    | ((ev_ebitda_v > 0) & (ev_ebitda_v <= 14))
                    | (_pe_au.isna() & ev_ebitda_v.isna()))
    df['arch_asleep_unrerated'] = (
        (df['arch_asleep_at_wheel'] == 1) &
        _no_rerate_au.fillna(False) &
        _not_rich_au.fillna(False) &
        _not_melting
    ).fillna(False).astype(int)

    # XR9 — Audited streak, unrerated ('XR-AuditedStreakUnrerated'):
    # (user: streaks LONGER than four quarters) 8+ CONSECUTIVE quarters of
    # FILED growth (revenue or parent NI, from ~7yr of EDGAR quarterlies
    # with the missing-Q4 synthesized — not estimates, not provider caps),
    # with an honest window (>=8 comparisons available), while the market
    # has NOT re-rated (the asleep_unrerated no-rerate evidence) and the
    # multiple is not already rich. The longest-duration told-and-ignored
    # signal the data supports.
    _stk_best = pd.concat([_ncol('ni_yoy_streak_q'),
                           _ncol('rev_yoy_streak_q')], axis=1).max(axis=1)
    df['arch_xr_audited_streak_unrerated'] = (
        is_operating & (mcap > 0) &
        (_stk_best >= 8) &
        (_ncol('streak_quarters_n') >= 8) &
        _no_rerate_au.fillna(False) &
        _not_rich_au.fillna(False) &
        _not_melting
    ).fillna(False).astype(int)

    # XR21 — Confluence ('XR-Confluence', the once-in-a-lifetime meta-gate):
    # the historic outliers were rarely ONE signal — they were CONFLUENCE:
    # a floor AND an engine AND a forensic tell AND a dislocation at once.
    # Fires when >=3 independent XR classes agree on the same name. By
    # construction the rarest flag in the book.
    _xr_cols_meta = [c for c in df.columns if c.startswith('arch_xr_')
                     and c != 'arch_xr_confluence']
    df['arch_xr_confluence'] = (
        (df[_xr_cols_meta].sum(axis=1) >= 3)
    ).astype(int)


    # ---------- Templeton "maximum pessimism" (cheap vs own history) ----------
    # Cheap against the company's OWN mid-cycle earnings (EV / normalized 5yr
    # EBITDA — the cyclical adjustment that makes a trough-earnings cyclical
    # look expensive on the spot number but cheap normalized), bought when the
    # price sits near the bottom of its 5-year range / below its 5yr average.
    # Survivability-gated so it is pessimism, not terminal decline.
    ev_norm = _num('ev_norm_ebitda')
    _ev_norm_ebit = (_num('enterprise_value')
                     / _num('normalized_ebit').where(_num('normalized_ebit') > 0))
    df['arch_templeton_pessimism'] = (
        is_operating &                                         # (tail) EV/normalized-EBITDA lens is meaningless for financials/REITs/utilities
        (((ev_norm > 0) & (ev_norm <= 8.0)) |                   # cheap vs mid-cycle
         (ev_norm.isna() & (_ev_norm_ebit > 0) & (_ev_norm_ebit <= 10.0))) &
        ((_num('price_pct_of_5y_range') <= 0.35) |              # near 5y low…
         (_num('price_vs_5y_avg') <= 0.85)) &                  # …or below 5y avg
        (_num('pct_off_52w_high') <= -0.15) &                  # MAXIMUM PESSIMISM = not near a 52w high (a recovered name isn't pessimism)
        ((fcf_ttm_v > 0) | (ebitda_ttm_v > 0) | (net_cash_pct >= 0.30)) &
        _roce_now_ok   # (deep-audit) Templeton buys TROUGH cyclicals (a negative SPOT op margin at trough is the thesis, kept), but a KNOWN-negative current roce is terminal decline not pessimism: DCGO roce-95%, 1V5.F roce-5.9%. The mild _roce_now_ok cut (not _not_melting) preserves positive-op trough cyclicals.
    ).fillna(False).astype(int)

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
    ], axis=1)
    g10 = _g_lenses.median(axis=1, skipna=True).clip(lower=0.0, upper=0.50)
    _g_confirmed = ((_g_lenses >= 0.15).sum(axis=1) >= 2)
    # Conservative terminal NET margin: reward where already profitable; floor
    # 10%, cap 22% — never assume a fatter margin than a maturing peer holds.
    term_margin = pd.concat([
        _num('op_margin'),
        _ebm * 0.65,                                    # EBITDA scaled to a net proxy
        pd.Series(0.12, index=df.index),
    ], axis=1).max(axis=1).clip(0.10, 0.22)
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
        _profit_present &                               # (reference II) profitability LEVEL present, not just a growth rate
        (implied_10x >= 10.0)                           # the 10x arithmetic closes

        & is_operating   # (G1 ext) revenue-multiple/margin meaningless for financials
    ).fillna(False).astype(int)

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
    stable_share_count = (
        _soft_ok_below('shares_yoy', 0.05) & _soft_ok_below('shares_3y_cagr', 0.10)
    )
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
    mult_compression = (rev_yoy_c - _stk_ret).clip(-11.0, 11.0)  # sales growth minus stock return
    df['evsales_derate_gap'] = mult_compression.round(3)
    _evsg_exceptional = (evsg_v > 0) & (evsg_v <= 0.08)   # cheap per unit of growth
    # The derate itself, seen through more than one base: the 1y gap, a 3y
    # version (sales CAGR outrunning annualized 3.5y price ROC), or an
    # exceptional growth-adjusted multiple with confirmed growth.
    _roc35_ann = (1.0 + _num('roc_3_5y')).clip(lower=0.0).pow(1.0 / 3.5) - 1.0
    _derate_3y = _num('revenue_3y_cagr') - _roc35_ann
    derate_any = (
        (mult_compression >= 0.15) |
        (_derate_3y >= 0.15) |
        (_evsg_exceptional & (rev_growth_score >= 0.5) &
         ((mult_compression >= 0) | (_derate_3y >= 0)))
    ).fillna(False)
    df['arch_evsales_derating'] = (
        (mcap >= 50e6) & (mcap < 20e9) &                # (G6) investable-size floor
        (rev_yoy_c >= 0.15) & ~(_ncol('rev_3y_cagr') < 0) &  # (deep-audit) HARD positive top-line floor. The old rev_growth_score>=0.6 OR-branch admitted FALLING-sales names (TTEC rev_yoy-3.2%/3y-4.4%/roce-9.7%) because that composite stays high while sales fall, and derate_any rewards a collapsing STOCK — a melting value trap, the anti-thesis. rev_growth_score stays an upweight in the score, not a gate-opener.
        derate_any &                                    # EV/Sales compressing (any base)
        (ev_sales_v > 0.10) & (ev_sales_v <= 6.0) &     # room left; lower bound drops artifacts
        ((_num('gross_margin') >= 0.20) | (ebitda_ttm_v > 0) | (fcf_ttm_v > 0)) &  # not a trap
        ~((ebitda_ttm_v < 0) & (fcf_ttm_v < 0))         # (G6) cash sanity: not burning on BOTH EBITDA & FCF
    
        & is_operating   # (G1 ext) EV-multiple meaningless for financials
    ).fillna(False).astype(int)
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
    lr_progress_any, lr_progress_score = _confirm([
        (revenue_5y_cagr,                  lambda x: x >= 0.08),   # 5y top line
        (revenue_3y_cagr_v,                lambda x: x >= 0.10),   # 3y top line
        (_num('gross_profit_yoy'),         lambda x: x >= 0.08),   # gross profit
        (_num('eps_yoy_positive_share'),   lambda x: x >= 0.6),    # EPS durability
        (n_yrs_fcf_pos,                    lambda x: x >= 4),      # FCF durability
        (n_yrs_opinc_pos,                  lambda x: x >= 4),      # op-income durability
        (roiic_lindy,                      lambda x: x >= 0.10),   # reinvestment econ
        (op_margin_lindy,                  lambda x: x >= 0.08),   # durable margins
        (inflection_confirm_score,         lambda x: x >= 0.6),    # confirmed inflection
    ])
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
    lr_unpaid = ((_r12 <= 0.35) | (_r12.isna() & (_num('momentum_12m') <= 0.35)))
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
                 (lr_coil_score >= 0.5))
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
    lr_roc_setup = (((_num('roc_3_5y') <= 0.40) & (_acc35 > 0)) |
                    ((_num('roc_10y') <= 1.00) & (_acc10 > 0)) |
                    ((_num('price_vs_5y_avg') <= 1.00) & (_acc35 > 0)))
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
        (lr_progress_score >= 0.66)
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
    conv_any, conv_score = _confirm([
        (_rec, lambda x: (x > 0) & (x <= 2.2)),   # consensus rating strong
        (_ups, lambda x: x >= 0.25),              # >=25% target upside
        (_nan_, lambda x: x >= 8),                # deep coverage still bullish-priced
    ])
    _conviction = conv_any & (conv_score >= 0.5)  # >=half the AVAILABLE lenses
    _not_extended = ((_num('roc_12m') <= 0.50) |
                     (_num('roc_12m').isna() & (_num('momentum_12m') <= 0.50)))
    # (G6) require a REAL consensus rating present and reasonable (not bearish)
    # — the awakening cannot fire on price-target optimism alone (38% did).
    _rating_present = (_rec.notna()) & (_rec > 0) & (_rec <= 3.0)
    # (R9) a genuine EARLY re-rating is not a name in freefall. Target-upside
    # mechanically inflates after a crash, so a stock >35% off its 52w high with
    # no recent momentum is a falling knife, not an awakening. Require it be
    # NOT collapsing: within 35% of the high, or showing positive recent momentum.
    _not_freefall = ((_num('pct_off_52w_high') >= -0.35) |
                     (_num('momentum_12m') > 0) | (_num('roc_6m') > 0))
    df['arch_analyst_awakening'] = (
        (mcap > 0) & (_nan_ >= 3) & _rating_present & _conviction &
        _not_extended & _not_freefall & lr_live_tape
    ).fillna(False).astype(int)
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
    df['arch_analyst_rerating_confirmed'] = (
        (mcap > 0) & (_nan_ >= 3) & _rating_present & _conviction &
        _at_52w_high & _not_blownoff & lr_live_tape
    ).fillna(False).astype(int)
    # Score: same conviction stack, but the 52w-high confirmation carries the
    # largest weight (it is the defining, market-validated signal here).
    df['analyst_rerating_score'] = (((0.20 * _rec_sc + 0.15 * _ups_sc
                                      + 0.12 * _brd_sc + 0.08 * conv_score
                                      + 0.45 * _hi_sc)
                                     .clip(0, 1))
                                    * df['arch_analyst_rerating_confirmed']).round(3)

    arch_cols = [
        'arch_narrative_lag',
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
        'arch_spinoff',
        'arch_post_reorg',
        'arch_special_situation',
        'arch_nol_shell',
    ]
    pretty = {
        'arch_narrative_lag': 'NarrativeLag',
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
        'arch_spinoff': 'SpinOff-Form10',
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
    _is_clinical_biotech = (_is_drug_dev & ~_commercial.fillna(False))
    df['is_drug_developer'] = _is_drug_dev.astype(int)
    df['is_clinical_biotech'] = _is_clinical_biotech.astype(int)

    # ---------- Biotech Deep Value (below-cash special situation) ----------
    # A drug developer trading at/below its NET CASH: the market pays you to
    # own the cash and hands you a free option on the pipeline. Downside is
    # the balance sheet, not the binary trial. Requires a real cash cushion
    # AND enough runway not to face imminent dilution. This is the home for
    # the clinical biotechs the systematic filter removes from every other
    # fundamental value screen.
    _bdv_ncash = _num('net_cash_pct_mcap'); _bdv_cashev = _num('cash_gt_ev_flag')
    _bdv_ncav = _num('ncav_pct_mcap'); _bdv_cashpct = _num('cash_pct_mcap')
    # Cash runway (years) = gross cash / annual burn; ample (99) when not
    # burning, NaN when cash data is missing.
    _bdv_cash_abs = _bdv_ncash.clip(lower=0) * mcap            # net cash (USD; better coverage than gross)
    _bdv_burn = -_num('fcf_ttm')                               # >0 = burning
    _bdv_runway = (_bdv_cash_abs / _bdv_burn.where(_bdv_burn > 0)).where(
        _bdv_burn > 0, 99.0)
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
        & (_bdv_runway >= 1.0)                 # docstring runway floor (non-burners = 99)
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
        ~(_bn_gmd < -0.03) &                            # ...not eroding (missing => pass)
        (((s('roce', np.nan) >= 0.15) & ~_roce_oneoff_suspect)
         | (s('roic_lindy', np.nan) >= 0.15)) &  # toll-road returns (no uncorroborated one-off roce)
        (s('op_margin', np.nan) > 0.05) &               # genuinely profitable
        ~(_bn_capint > 0.10)                            # capital-light chokepoint (missing => pass)
    ).fillna(False).astype(int)

    # ---------- Flyover Stocks: high-quality, low-coverage, owner-controlled ----
    # Todd Wenning / quiet-compounder blueprint (Master Reference IV): durable
    # moat (ROIC>15%) + boring essential business + family/insider control +
    # strong FCF + LOW analyst coverage (<5, ideally 0). The low-coverage
    # discovery gap is DEFINITIONAL here — it is exactly what quiet_compounder and
    # owner_operator do not require, so this is the "undiscovered quality" lens.
    df['arch_flyover'] = (
        is_operating &
        ~(n_analysts_v > 5) &                           # low / no coverage (missing => undiscovered => pass)
        (insider >= 0.20) &                             # family / insider control
        (((s('roce', np.nan) >= 0.15) & ~_roce_oneoff_suspect)
         | (s('roic_lindy', np.nan) >= 0.15)) &  # high ROIC (>15%) = the moat (no uncorroborated one-off roce)
        ((_num('fcf_ttm') > 0) | (s('n_yrs_positive_fcf', 0) >= 3)) &  # strong / durable FCF
        (s('op_margin', np.nan) > 0) &                  # profitable
        _not_melting &
        (nde <= 2.0)                                    # low leverage (strong balance sheet)
    ).fillna(False).astype(int)

    # ---------- Event-driven / Special-Situations sleeve (EDGAR, US filers) ----
    # The Special-Situations taxonomy (Master Reference III/VIII; Compendium
    # Part II). Each is a HARD, DATED corporate-action catalyst with a
    # structurally BOUNDED downside, paired — per the user's refinement — with
    # EXCELLENT VALUATION (a high EBIT yield, FCF yield, or earnings yield).
    # US-only: non-EDGAR filers carry no event signal (fields are NaN -> 0).
    _spin = s('spin_flag', 0); _tender = s('tender_flag', 0)
    _merger = s('merger_flag', 0); _gopriv = s('going_private_flag', 0)
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

    # Spin-off (Form 10 registration): forced-selling / identity-vacuum — a
    # viable operating business, cheap, not melting.
    df['arch_spinoff'] = (
        (_spin == 1) & is_operating & _not_melting & (mcap > 0)
        & (s('op_margin', np.nan) > -0.05)      # (topcheck) a viable spun business, not a deep loss-maker
        & _excellent_value
    ).fillna(False).astype(int)

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
    _reorg_value = ((_ebit_yield >= 0.10) | (fcf_yield >= 0.08))
    df['arch_post_reorg'] = (
        (_reorg == 1) & is_operating & _not_melting
        & _reorg_value
        & (nde <= 3.0)
    ).fillna(False).astype(int)

    # Special-situation catalyst: a dated merger / tender / going-private event
    # with a bounded downside, bought cheap so value holds if the deal breaks.
    df['arch_special_situation'] = (
        ((_merger == 1) | (_tender == 1) | (_gopriv == 1)) & (mcap > 0)
        & _not_melting                          # (topcheck) not a deep loss-maker (PXLW op-106%)
        # (deep-audit) right event, right value LENS. An operating special-sit is
        # cheap on yield (_excellent_value); a closed-end fund / financial under a
        # tender (43% of firers — BGY/BOE/VTN/BDJ) is cheap on DISCOUNT-TO-NAV, and
        # was wrongly validated on its pass-through "op_margin"/earnings yield.
        # Keep both — operating via yield, financials via pb<1.0 (NAV discount).
        & ((is_operating & _excellent_value)
           | ((is_financial | is_reit) & (pb > 0) & (pb < 1.0)))
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
        & ((net_cash_pct_sane >= 0.10) | _excellent_value | (cash_gt_ev > 0))
        & (s('op_margin', np.nan) > -0.30)                 # (topcheck) survivable, not a >100%-mcap/yr burner (ONCO/ASTC)
        & _not_melting
        & ~(fcf_yield < -0.25)   # (deep-audit) op_margin>-0.30 does NOT capture cash burn: CNTY fcf-119%/op+9.2%, NEON fcf-80% behind a 355% op artifact torched the balance sheet while passing the op gate. An NOL on a dying balance sheet is un-monetizable (missing fcf stays permissive).
    ).fillna(False).astype(int)

    _sym_nc = df['symbol'].astype(str)
    _nm_nc = df['name'].astype(str) if 'name' in df.columns else pd.Series('', index=df.index)
    _is_noncommon = (
        _sym_nc.str.match(r'^[A-Z]{1,5}-P[A-Z]?$')
        | _sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT)$')
        # (R7) suffixed foreign/Canadian preferred lines the anchored US
        # pattern misses — kept narrow so exchange suffixes (.PA Paris, .PR
        # never terminal here) are NOT caught: TICK.PR.G, TICK-PR-A, TICK PFD.
        | _sym_nc.str.contains(r'\.PR\.[A-Z]$', regex=True)          # GWO.PR.G (Canadian pref)
        | _sym_nc.str.contains(r'-PR[-.]?[A-Z]?$', regex=True)       # BAM-PR-A, X-PR
        # (fresh) exchange-suffixed pref line: TICKER-P<series>.TO / .V etc.
        # ($-anchored US pattern misses these — GWO-PI.TO, SLF-PC.TO leaked).
        | _sym_nc.str.contains(r'-P[A-Z]?\.[A-Z]{1,3}$', regex=True)
        | _sym_nc.str.contains(r'[-. ]PFD\b', case=False, regex=True)
        | _nm_nc.str.contains(r'preferred|pfd| pref |depositary|% notes|perpetual|warrant',
                              case=False, regex=True)
    ).fillna(False)
    _GATED_SCORES = [c for c in ['tenbagger_score', 'tenbagger_implied_return',
                     'evsales_derate_score', 'evsales_derate_gap',
                     'lynch_reward_score', 'lynch_leg_max', 'lynch_rank',
                     'lynch_exceptional_leg', 'analyst_awakening_score',
                     'seg_inflect_score', 'oneil_score', 'weinstein_score',
                     'kullamagie_score', 'cundill_score',
                     'analyst_rerating_score', 'asleep_score',
                     'biotech_deep_value_score', 'biotech_cash_runway_yrs'] if c in df.columns]
    _scrub_cols = arch_cols + _GATED_SCORES
    if _is_noncommon.any():
        df.loc[_is_noncommon.values, _scrub_cols] = 0
        print(f'  scrubbed archetype flags + gated scores on '
              f'{int(_is_noncommon.sum())} non-common securities', file=sys.stderr)

    # ===== MICRO-SHELL SCRUB: a sub-$1M market cap is untradeable and almost
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

    # ===== PRE-REVENUE BIOTECH SCRUB (durable/quality archetypes only): a
    # clinical-stage biotech's "5-year durable margin / quality" is a licensing
    # one-off, not operations (KROS topped lindy_margin/tax_efficient). Zero
    # these names' flags on the QUALITY/durable archetypes; their genuine
    # inflection/growth/deep-value theses elsewhere are untouched. =====
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
    _biotech_ok = {'arch_analyst_awakening', 'arch_analyst_rerating_confirmed',
                   'arch_oneil_canslim',
                   'arch_weinstein_stage2', 'arch_kullamagie_breakout',
                   'arch_biotech_deep_value'}
    _fund_arch = [c for c in arch_cols if c not in _biotech_ok]
    _fund_scrub = _fund_arch + [c for c in _GATED_SCORES
                                if c not in ('analyst_awakening_score',
                                             'oneil_score', 'weinstein_score',
                                             'kullamagie_score',
                                             'biotech_deep_value_score',
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
                     'arch_concentrated_segments', 'arch_diversified_segments',
                     'arch_reinvest_inflect'] if c in df.columns]
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

    df['archetype_count'] = df[arch_cols].sum(axis=1)
    df['archetype_tags_str'] = df[arch_cols].apply(
        lambda r: ', '.join(pretty[c] for c in arch_cols if r[c] == 1),
        axis=1,
    )

    out = df[['symbol'] + arch_cols + ['archetype_count','archetype_tags_str','bab_score','oper_leverage_score','buyback_score','inflection_confirm_score','rev_growth_score','cheapness_score','quality_score','confirm_overall','alignment_score','insider_buy_flag','insider_cluster_buy_flag','insider_10pct_buy_flag','tenbagger_score','tenbagger_implied_return','evsales_derate_score','evsales_derate_gap','lynch_reward_score','lynch_leg_max','lynch_exceptional_leg','lynch_rank','high_52w_abs','high_52w_rel','high_52w_both','analyst_awakening_score','analyst_rerating_score','asleep_score','seg_inflect_score','oneil_score','weinstein_score','kullamagie_score','cundill_score','biotech_deep_value_score','biotech_cash_runway_yrs','is_drug_developer','is_clinical_biotech']
             + [c for c in ['asym_m','asym_q','sr_m_release','roc_3_5y','roc_accel_3_5y','roc_12m','stale_tape','gaap_masked','pct_52w_high','rel_pct_52w_high','base_depth_12m','segment_count','fastest_segment_yoy','is_price_ghost'] if c in df.columns]]
    from master_versions import versioned_replace
    out.to_csv(out_path + '.tmp', index=False)
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
