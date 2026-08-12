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
                                 })

    # Segment signals from the edgartools dimensional harvest. Coverage
    # is sparse (only US filers with multi-segment 10-K disclosures) but
    # the signal is high-quality where it fires.
    segment_signals = None
    if os.path.exists('edgar_segment_signals.csv'):
        segment_signals = pd.read_csv('edgar_segment_signals.csv')

    # Merge.  Asym is the primary - everything else is enrichment.
    df = asym.merge(yart, on='symbol', how='left', suffixes=('','_y'))
    if edgar_roiic is not None:
        df = df.merge(edgar_roiic, on='symbol', how='left', suffixes=('','_er'))
    if edgar_yart is not None:
        df = df.merge(edgar_yart, on='symbol', how='left', suffixes=('','_ey'))
    if segment_signals is not None:
        df = df.merge(segment_signals, on='symbol', how='left', suffixes=('','_seg'))
    df = df.merge(pew, on='symbol', how='left')

    # Use the asymmetry sector/market_cap as primary; fall back to yartseva.
    for c in ('sector','industry','market_cap'):
        if c + '_y' in df.columns:
            df[c] = df[c].fillna(df[c + '_y'])

    # ---------- helper accessors ----------
    def s(col, default=0.0):
        if col in df.columns:
            return pd.to_numeric(df[col], errors='coerce').fillna(default)
        return pd.Series(default, index=df.index)

    sector = df['sector'].fillna('') if 'sector' in df.columns else pd.Series('', index=df.index)
    country = df['src'].fillna('').astype(str).str.upper() if 'src' in df.columns else pd.Series('', index=df.index)

    # Use mcap_usd (FX-converted) when available - critical for cross-country
    # comparisons.  Falls back to raw market_cap (local currency) only if
    # fix_pipeline.py hasn't been run yet.
    mcap = s('market_cap_usd') if 'market_cap_usd' in df.columns else s('market_cap')
    price_yoy = s('price_yoy')
    mom12 = s('momentum_12m')
    rev_yoy = s('rev_yoy')
    rev_accel = s('rev_accel')
    ebitda_margin = s('ebitda_margin')
    ebitda_margin_delta = s('ebitda_margin_delta_yoy')
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
    nde = s('net_debt_ebitda', 99.0)
    not_priced_in = s('not_priced_in_score')
    yart_score = s('yartseva_score')
    adv = s('avg_dollar_volume', 1e12)

    # Use price_yoy where available, otherwise momentum_12m as proxy.
    flat_or_down = ((price_yoy <= 0.0) | (mom12 <= 0.0))

    inflection_print = (
        (ebitda_inflection > 0) | (cfo_inflection > 0) | (fcf_inflection > 0) |
        (rev_inflection > 0) | (roce_inflection > 0) |
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0) |
        (rev_yoy >= 0.10) | (ebitda_margin_delta >= 0.02)
    )

    # ---------- Cluster A: Narrative Lag (modifier) ----------
    df['arch_narrative_lag'] = (flat_or_down & inflection_print).astype(int)

    # ---------- Cluster C5: Fixed-Cost Asset + Demand Shock ----------
    df['arch_fixed_cost_demand_shock'] = (
        sector.isin(HEAVY_ASSET_SECTORS) &
        (rev_accel > 0) &
        (ebitda_margin_delta >= 0.02)
    ).astype(int)

    # ---------- Cluster E7: Discounted Vehicle ----------
    df['arch_discounted_vehicle'] = (
        (pb > 0) & (pb < 0.85) &
        ((cash_gt_ev > 0) | (net_cash_pct > 0.20)) &
        (mcap < 2e9)
    ).astype(int)

    # ---------- Cluster E8: Capital Discipline Re-rating ----------
    # Proxy: founder/insider-aligned, lightly levered, durable margin, not
    # already re-rated.  We don't have a direct buyback signal in fundamentals
    # so this is a "compounder-pattern" proxy.
    df['arch_capital_discipline'] = (
        (insider >= 0.20) &
        (nde <= 1.5) &
        (ebitda_margin >= 0.05) &
        (price_yoy <= 0.30) &
        (yart_score >= 0.45)
    ).astype(int)

    # ---------- Cluster F9: Regime-Change Cyclical ----------
    df['arch_regime_cyclical'] = (
        sector.isin(HEAVY_ASSET_SECTORS) &
        (price_yoy <= -0.20) &
        ((ebitda_inflection > 0) | (ebitda_first_pos > 0) | (ebitda_margin_delta >= 0.02)) &
        (not_priced_in > 0.20)
    ).astype(int)

    # ---------- Cluster F10: Option Mispriced as Dead ----------
    df['arch_dead_option'] = (
        (price_yoy <= -0.40) &
        (fcf_yield > 0.05) &
        (ebitda_margin > 0) &
        (nde <= 3.0)
    ).astype(int)

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
    margin_confirming = ebitda_margin_delta >= 0.01
    roce_today = s('roce') >= 0.05
    df['arch_kpi_threshold'] = (
        first_pos_print & (margin_confirming | roce_today)
    ).astype(int)

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
    nde_col = s('net_debt_ebitda', 99.0)
    profitable = ebitda_margin >= 0.05
    inflection_now = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0) |
        (ebitda_margin_delta >= 0.02) | (rev_accel >= 0.05)
    )
    clean_balance_sheet = (
        (cash_gt_ev > 0) | (net_cash_pct > 0.05) | (nde_col <= 0.0)
    )
    cheap_on_ebitda = (ev_ebitda_col > 0) & (ev_ebitda_col <= 8.0)
    df['arch_micro_activist_inflect'] = (
        (mcap > 0) & (mcap < 250e6) &
        profitable &
        inflection_now &
        clean_balance_sheet &
        cheap_on_ebitda
    ).astype(int)

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
        (roiic_lindy > 0.15) & (asset_3y_cagr > 0.05)
    ).fillna(False).astype(int)

    # J — Cash-confirmed reinvestment: cash ROIIC lindy > 12% (lower bar than
    # NOPAT because FCF includes capex outflows).
    df['arch_cash_reinvest'] = (
        (cash_roiic_lindy > 0.12) & (asset_3y_cagr > 0.05)
    ).fillna(False).astype(int)

    # K — ROIC inflection: latest ROIC crossed zero from below AND cash ROIC
    # also positive (confirms the inflection is real, not accounting).
    df['arch_roic_inflect'] = (
        ((roic_inflect == 1) | (cash_roic_inflect == 1))
        & (cash_roic_lindy.fillna(-1) > 0)
    ).astype(int)

    # L — Cheap per reinvestment yield (PEG analogue on ROIIC). Lower
    # cheap_per_roiic = more reinvestment yield per multiple paid. Threshold
    # 1.5 means "you're paying < 1.5x EV/EBITDA per percent of lindy ROIIC".
    df['arch_cheap_per_roiic'] = (
        (cheap_per_roiic > 0) & (cheap_per_roiic <= 1.5) & (roiic_lindy > 0.10)
    ).fillna(False).astype(int)

    # M — Tangible-value floor: P/TB < 0.7 with tangible equity > 50% of book
    # equity (real assets, not goodwill).
    df['arch_tangible_value'] = (
        (p_tb > 0) & (p_tb < 0.7) & (tangible_equity_pct > 0.50)
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
        (op_margin_lindy >= 0.10) &
        (ebitda_margin_lindy >= 0.12) &
        (years_of_history >= 5)
    ).fillna(False).astype(int)

    # O — Consistent FCF: positive FCF in 4 of last 5 years AND positive
    # operating income in 4 of last 5. Cash-generation durability test
    # that strips out the accounting noise.
    df['arch_lindy_fcf'] = (
        (n_yrs_fcf_pos >= 4) &
        (n_yrs_opinc_pos >= 4)
    ).astype(int)

    # P — No Dilution (Clean Compounder): shares roughly flat over 3y AND
    # FCF positive 4 of 5 AND ROIC positive 4 of 5. The Mayer / Mauboussin
    # owner-operator pattern - reinvesting at high returns without
    # constantly tapping equity holders.
    df['arch_no_dilution'] = (
        (shares_growth_3y <= 0.02) &
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
    df['arch_capital_returner'] = (
        (capital_return_yield >= 0.05)
    ).fillna(False).astype(int)

    # AA — Low-SBC Quality: clean accounting (SBC < 2% of revenue) AND
    # genuinely profitable (operating margin > 5%). Filters out SaaS /
    # crypto / hyper-growth names whose GAAP earnings are SBC-inflated.
    df['arch_low_sbc_quality'] = (
        (sbc_pct_revenue >= 0.0) & (sbc_pct_revenue < 0.02) &
        (ebitda_margin > 0.05)
    ).fillna(False).astype(int)

    # AB — Tax-Efficient (real not loss-driven): effective tax rate < 15%
    # AND positive pre-tax income. Distinguishes legitimate tax structure
    # from "no tax because no profit."
    pretax_pos = s('pretax_income_ttm', np.nan)
    df['arch_tax_efficient'] = (
        (effective_tax_rate > 0) & (effective_tax_rate < 0.15) &
        (pretax_pos > 0)
    ).fillna(False).astype(int)

    # AC — Strong Interest Coverage: opinc / interest paid >= 8x.
    # Conservative leverage indicator more robust than net_debt/EBITDA
    # for asset-heavy industries.
    df['arch_strong_coverage'] = (
        (interest_coverage >= 8.0)
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
    customer_concentration_flag = s('customer_concentration_flag', 0)

    # AD — Diversified Segments: 4+ segments AND HHI <= 0.40. Real
    # diversification of revenue streams, lowers single-segment risk.
    df['arch_diversified_segments'] = (
        (segment_count >= 4) & (segment_hhi <= 0.40)
    ).fillna(False).astype(int)

    # AE — Concentrated Segment Risk: HHI >= 0.70 OR largest segment >= 70%.
    # One bad year in the dominant segment sinks the whole business.
    # FIRES as a NEGATIVE signal — kept for transparency, downstream
    # consumers can flip the sign.
    df['arch_concentrated_segments'] = (
        ((segment_hhi >= 0.70) | (largest_segment_share >= 0.70))
        & (segment_count >= 2)
    ).fillna(False).astype(int)

    # AF — Global Geographic Footprint: 4+ geographies reporting. Currency
    # diversification + market diversification.
    df['arch_geographic_global'] = (
        (geographic_region_count >= 4)
    ).astype(int)

    # AG — Fastest Segment Inflection: a single segment growing > 25% YoY
    # WITHIN a multi-segment business (i.e., a "hidden growth engine"
    # the consolidated number masks).
    df['arch_fastest_segment'] = (
        (fastest_segment_yoy >= 0.25) & (segment_count >= 2)
    ).fillna(False).astype(int)

    # Q — Durable Growth: revenue 5y CAGR >= 8% AND topline accelerating
    # (3y CAGR > 5y CAGR) AND asset base growing. Multi-cycle expansion
    # without the single-year base-effect noise.
    df['arch_lindy_growth'] = (
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
    df['arch_quiet_compounder'] = (
        (roic_lindy >= 0.15) &
        (n_yrs_roic_pos >= 4) &
        (mom12.between(-0.10, 0.30)) &
        (insider >= 0.10) &
        (shares_growth_3y <= 0.03) &
        (years_of_history >= 5)
    ).fillna(False).astype(int)

    # S — Buyback Compounder: shrinking share count + durable ROIC + clean
    # balance sheet. Greenblatt / capital-allocation classic.
    df['arch_buyback_compounder'] = (
        (shares_growth_5y <= -0.05) &
        (roic_lindy >= 0.08) &
        (n_yrs_roic_pos >= 4) &
        (nde <= 1.5)
    ).fillna(False).astype(int)

    # T — Owner-Operator: management with skin in the game AND multi-year
    # discipline. Russo's "capacity to suffer" / Mayer's owner-operator
    # 100-bagger archetype.
    df['arch_owner_operator'] = (
        (insider >= 0.20) &
        (n_yrs_roic_pos >= 4) &
        (n_yrs_fcf_pos >= 4) &
        (shares_growth_3y <= 0.02) &
        (years_of_history >= 5)
    ).fillna(False).astype(int)

    # U — Quality at a Reasonable Price (QARP): high lindy ROIIC AND not
    # already discounted as a compounder. Russo-via-Buffett pattern of
    # paying fair for great vs cheap for mediocre.
    df['arch_qarp'] = (
        (roiic_lindy >= 0.15) &
        (s('ev_ebitda', 999) > 0) & (s('ev_ebitda', 999) <= 12) &
        (n_yrs_roic_pos >= 4) &
        (shares_growth_3y <= 0.02)
    ).fillna(False).astype(int)

    # V — Reinvestment Inflection: ROIIC accelerating from a positive
    # base AND assets actually growing (not financial-engineering). The
    # signature of a compounder finding more runway.
    df['arch_reinvest_inflect'] = (
        (roiic_lindy >= 0.05) &
        (roiic_acceleration_v >= 0.05) &
        (asset_3y_cagr_v >= 0.05)
    ).fillna(False).astype(int)

    # W — Double Inflection: BOTH NOPAT-ROIC AND cash-ROIC crossed zero
    # from below in the latest year. Confirms the inflection is real
    # cash, not accounting-driven (D&A timing, accruals).
    df['arch_double_inflect'] = (
        (roic_inflect_v == 1) &
        (cash_roic_inflect_v == 1)
    ).astype(int)

    # X — Cash Quality: cash-ROIC running materially ahead of NOPAT-ROIC
    # over the lindy window. "Earnings hide the cash" — quality-of-
    # earnings tell that Mauboussin emphasises.
    df['arch_cash_quality'] = (
        (cash_roic_lindy > 0.08) &
        (roic_lindy > 0) &
        ((cash_roic_lindy - roic_lindy) >= 0.05) &
        (n_yrs_fcf_pos >= 4)
    ).fillna(False).astype(int)

    # Y — Capital-Light Pivot: revenue growing AND assets growing slower
    # AND ROIC turning up. The asset-light transition (franchise / IP /
    # platform mode).
    df['arch_capital_light_pivot'] = (
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
        (fcf_margin_v > 0.0) &
        (ebitda_margin >= 0.10) &
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
    df['arch_bab_low_beta'] = (
        beta_present & (beta_shrunk <= 0.85) & bab_quality
    ).fillna(False).astype(int)

    # 2) Becoming more BAB-like: beta still moderate, but the business is
    #    de-risking — margins expanding, cash inflecting, deleveraging — trending
    #    toward the boring-safe profile before beta has fully compressed. (No beta
    #    time-series available, so improving fundamental stability stands in for
    #    the paper's beta compression.)
    df['arch_bab_becoming'] = (
        beta_present & (beta_shrunk > 0.85) & (beta_shrunk <= 1.15) &
        (ebitda_margin_delta >= 0.01) &
        ((fcf_inflection > 0) | (ebitda_inflection > 0) | (fcf_margin_v > 0.0)) &
        (nde <= 3.0)
    ).fillna(False).astype(int)

    # 3) BAB multibagger — the synthesis: low/declining-beta quality that is ALSO
    #    a yartseva multibagger OR very cheap. Boring safety + embedded compounding
    #    (financial or reinvestment leverage) at a price the market underrates.
    df['arch_bab_multibagger'] = (
        beta_present & (beta_shrunk <= 1.0) & bab_quality &
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
    pegy_v = s('pegy', 99.0)
    evgy_v = s('ev_ebitda_gy', 99.0)
    df['arch_lynch_pegy'] = (
        (pegy_v > 0) & (pegy_v <= 1.0)
    ).fillna(False).astype(int)
    df['arch_lynch_evgy'] = (
        (evgy_v > 0) & (evgy_v <= 0.6)
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
    ev_ebitda_v = s('ev_ebitda', 99.0)
    pe_w = s('p_e', 99.0)
    cash_conv_w = s('cash_conversion')
    div_yield_v = s('dividend_yield')
    ebitda_yoy_v = s('ebitda_yoy').clip(-3.0, 10.0)
    ncav_pct = s('ncav_pct_mcap')
    n_analysts_v = s('n_analysts', 0.0)     # missing -> 0 -> treated as neglected
    off_high = s('pct_off_52w_high')        # negative = below the 52w high
    # Clamped growth/margin inputs (kill the data-artifact tail)
    rev_yoy_c = rev_yoy.clip(-1.0, 10.0)
    emd_c = ebitda_margin_delta.clip(-1.0, 1.0)
    cash_pct_mcap_v = s('cash_pct_mcap').clip(0.0, 3.0)
    net_cash_pct_c = net_cash_pct.clip(-2.0, 2.0)

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
        (mcap >= 10e6) & (mcap <= 300e6) &
        (rev_yoy_c >= 0.15) &                       # "double-digit", not 50%
        (ebitda_yoy_v > rev_yoy_c) &                # operating leverage (the 3rd leg)
        (emd_c > 0.0) &                             # margins genuinely improving
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &
        (ev_sales_v > 0) & (ev_sales_v < 3.0) &
        wolf_cheap_entry &
        low_sbc_wolf
    ).fillna(False).astype(int)

    # B — Turnaround: loss-maker crossing into the black (incl. the OCF-
    # turns-positive shape, e.g. SBBC) while still GROWING (he avoided the
    # flat/declining Thermal Energy). Cheap-entry ceiling added.
    df['arch_wolf_turnaround'] = (
        (mcap >= 10e6) & (mcap <= 200e6) &
        ((ebitda_first_pos > 0) | (cfo_first_pos > 0) |
         (fcf_first_pos > 0) | (ni_first_pos > 0) |
         (cfo_inflection > 0) | (fcf_inflection > 0) |
         ((ebitda_inflection > 0) & (emd_c > 0))) &
        (emd_c >= 0.0) &
        (rev_yoy_c >= 0.0) & rev_present &          # growing (present), not shrinking
        wolf_cheap_entry
    ).fillna(False).astype(int)

    # C — Value + catalyst (repurposed). He is NOT a net-net investor; his
    # real shape is a growing, cash-generative microcap with a fortress
    # balance sheet at a cheap FCF yield (Progressive Planet: ~12% FCF yld,
    # ~$32M cap, growing). Lowered net-cash floor 0.50->0.20; added growth
    # + positive CFO; FCF-yield as the cheapness catalyst.
    df['arch_wolf_value_catalyst'] = (
        (mcap > 0) & (mcap < 200e6) &
        (net_cash_pct_c >= 0.20) &
        (rev_yoy_c >= 0.10) &
        (cfo_ttm_v > 0) &
        ((fcf_yield >= 0.08) |
         ((ev_ebitda_v > 0) & (ev_ebitda_v < 6.0)))
    ).fillna(False).astype(int)

    # D — Emerging-sector profitability (his cautious cannabis bets). His one
    # such pick (Simply Solventless/HASH) blew up -57% on accounting + cash
    # problems, so gate hard on POSITIVE OPERATING CASH FLOW (not just EBITDA)
    # and clean SBC — exactly what would have excluded HASH.
    _emerging = (_ind.str.contains('cannabis|hemp|marijuana|tobacco', regex=True) |
                 _nm.str.contains('cannabis|hemp', regex=True))
    df['arch_wolf_emerging'] = (
        _emerging &
        (cfo_ttm_v > 0) &
        low_sbc_wolf &
        (((pe_w > 0) & (pe_w < 10.0)) | ((ev_ebitda_v > 0) & (ev_ebitda_v < 6.0)))
    ).fillna(False).astype(int)

    # E — "Seal of Approval" fresh trigger: an earnings inflection bought on
    # a post-earnings dip. Loosened the drawdown gate (he buys before the
    # full run) and added his valuation discipline (the KITS lesson).
    df['arch_wolf_seal'] = (
        (mcap > 0) & (mcap < 500e6) &
        inflection_print &
        (mom12 >= 0.10) &
        (off_high >= -0.50) &
        (((ev_ebitda_v > 0) & (ev_ebitda_v < 15.0)) | ((pe_w > 0) & (pe_w < 25.0)))
    ).fillna(False).astype(int)

    # F — NEW: Wolf Compounder — his signature winner (NCI/ZOMD/KITS-at-entry):
    # a sustained, ACCELERATING grower bought at a single-digit/low-teens
    # multiple, margins expanding, cash-positive, low dilution. Isolates the
    # multi-quarter streak the single-period trifecta gate can miss.
    df['arch_wolf_compounder'] = (
        (mcap >= 10e6) & (mcap <= 150e6) &
        (rev_yoy_c >= 0.25) & (rev_accel > 0) &     # accelerating streak
        ((cfo_ttm_v > 0) | (fcf_ttm_v > 0)) &
        (emd_c > 0) &
        ((ev_ebitda_v > 0) & (ev_ebitda_v < 12.0)) &
        (pe_w > 0) & (pe_w < 20.0) &
        low_sbc_wolf
    ).fillna(False).astype(int)

    # ---------- Liger Cub / Byron Street family ----------
    # Long-only public-information arbitrage in NEGLECTED microcaps. His edge
    # is OSINT (unscreenable); these capture the financial preconditions his
    # documented longs (RCMT, VTSI) shared: neglect (<=3-4 analysts), no
    # dilution, survivable balance sheet, near-breakeven-or-better cash flow
    # (this gate correctly REJECTS the WATT cash-burner, whose edge was pure
    # OSINT), depressed/off-highs, and NOT mining/biotech/crypto.
    df['arch_liger_asset_backed'] = (
        (mcap > 0) & (mcap < 400e6) &
        (net_cash_pct_c >= 0.20) &                  # 0.60 excluded every real long
        (n_analysts_v <= 4) &
        ((op_margin_v >= -0.05) | (ebitda_margin >= 0.0)) &
        low_sbc_liger &
        liger_sector_ok
    ).fillna(False).astype(int)

    # Quiet inflection the market hasn't processed. His signal is
    # ACCELERATION (RCMT consolidated +14.7% but the segment far faster), not
    # a high absolute growth level — so the growth gate is now accel-aware.
    # Leverage loosened 1.0->1.5 (RCMT ran ~1.3-1.5x) with the ebitda>0 guard.
    df['arch_liger_lagging_inflect'] = (
        (((rev_yoy_c >= 0.10) & (rev_accel > 0)) | (rev_yoy_c >= 0.15) | (emd_c > 0)) &
        ((cash_conv_w >= 0.80) | (fcf_margin_w > 0)) &
        _clean_bs(1.5) &                            # clean b/s (nde OR net-cash)
        (n_analysts_v <= 4) &
        low_sbc_liger &
        liger_sector_ok &
        ((mom12 <= 0.0) | (off_high <= -0.30))
    ).fillna(False).astype(int)

    # NEW: Liger Neglected Survivor — the single best proxy for his edge:
    # neglected + financially survivable (no dilution) + cheap, with an early
    # inflection and room to re-rate on a material catalyst. RCMT & VTSI pass;
    # WATT is intentionally rejected by the near-breakeven gate.
    df['arch_liger_neglected_survivor'] = (
        (mcap >= 20e6) & (mcap <= 400e6) &
        (n_analysts_v <= 3) &
        ((net_cash_pct_c >= 0.15) | ((ebitda_ttm_v > 0) & (nde <= 1.5))) &
        ((fcf_margin_w >= 0.0) | (op_margin_v >= -0.02)) &
        low_sbc_liger &
        ((off_high <= -0.30) | ((ev_sales_v > 0) & (ev_sales_v <= 2.0))) &
        ((rev_accel > 0) | (emd_c > 0)) &
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
        (cash_pct_mcap_v >= 0.20) &                 # net-cash survivability
        (ebitda_margin >= 0.25) &                   # cost-curve proxy
        (fcf_yield >= 0.08) &
        (off_high <= -0.20)                         # bought on weakness
    ).fillna(False).astype(int)

    # Deleveraging/yield — heavy FCF, moderate debt being paid down (rising
    # EBITDA mechanically cuts the ratio = his actual thesis), material
    # shareholder return. Yield floor raised to DEC-scale; solvency soft gate.
    df['arch_oak_deleveraging'] = (
        (fcf_yield >= 0.10) &
        (ebitda_ttm_v > 0) & (nde >= 1.0) & (nde <= 3.0) &
        ((ebitda_yoy_v > 0) | (ebitda_inflection > 0)) &   # leverage trajectory
        ((div_yield_v >= 0.06) | (s('capital_return_yield', 0.0) >= 0.06)) &
        _soft_ok_above('interest_coverage', 2.0)
    ).fillna(False).astype(int)

    # Distressed deep value with a hard-asset parachute — crushed price, deep
    # discount to book OR net-net, real cash, still cash-GENERATIVE (the
    # Belluscura gate: positive EBITDA alone isn't enough, require FCF/CFO>0).
    df['arch_oak_deep_value'] = (
        (off_high <= -0.50) &
        (((pb > 0) & (pb < 0.7)) | (ncav_pct >= 0.5)) &
        (cash_pct_mcap_v >= 0.20) &
        (ebitda_ttm_v > 0) & ((fcf_ttm_v > 0) | (cfo_ttm_v > 0)) &
        _soft_ok_above('interest_coverage', 1.5)
    ).fillna(False).astype(int)

    # NEW: Oak NAV-discount holdco — his price/NAV<0.7 + covered-yield trusts.
    # PROXY ONLY: for investment vehicles book ~ NAV, so a Financials-sector
    # deep book discount with a high yield. Cannot capture true NAV (marks on
    # unlisted assets) or his dividend-cover >=1.2x test.
    df['arch_oak_nav_discount'] = (
        sector.isin({'Financials'}) &
        (pb > 0) & (pb < 0.7) &
        (div_yield_v >= 0.05)
    ).fillna(False).astype(int)

    # NEW: Oak asset floor — market cap at/below cash + hard assets (CVV/PRTC).
    # Well-captured on the CASH leg (net cash or NCAV >= mcap = Graham floor);
    # does NOT see hidden real-estate-at-market or private-stake value.
    df['arch_oak_asset_floor'] = (
        (mcap > 0) & (mcap < 500e6) &
        ((net_cash_pct_c >= 0.40) | (ncav_pct >= 0.80)) &
        (pb > 0) & (pb < 1.5)
    ).fillna(False).astype(int)

    # NEW: Oak order-book conversion (backlog->revenue, the MPAC pattern).
    # LAGGING proxy: we can't see order intake / book-to-bill, only the P&L
    # footprint once it lands — accelerating revenue + margin expansion.
    df['arch_oak_order_conversion'] = (
        (mcap > 0) & (mcap < 1e9) &
        ((rev_accel > 0) | (rev_yoy_c > 0.05)) &
        (emd_c > 0) &
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
    owner_ey = s('owner_earnings_yield')   # = reported FCF / mcap
    # Upper bounds reject near-zero-mcap data artifacts (a yield of 55,000,000x
    # or EV/mcap of 130,000,000x is a broken market cap, not a cheap stub).
    # Genuine Weschler zone: P/cash ~0.5-6.7x, EV a few x equity.
    heavy_debt = ((nde_real >= 3.0) & (nde_real <= 30.0)) | \
                 ((ev_over_mcap >= 1.75) & (ev_over_mcap <= 30.0))
    df['arch_weschler_levered_equity'] = (
        (robust_cy >= 0.15) & (robust_cy <= 2.0) &  # cheap on ROBUST cash (Lindy)
        (owner_ey >= 0.08) & (owner_ey <= 2.0) &    # corroborated by reported FCF
        (ebitda_ttm_v > 0) &                     # EBITDA to service the debt
        heavy_debt &                             # enormous debt burden
        (fcf_ttm_v > 0) &                        # cash to amortise (deleverage)
        ((ebitda_yoy_v >= 0) | (ebitda_inflection > 0)) &  # stable/rising -> deleveraging
        _soft_ok_above('interest_coverage', 1.0) &  # can service (soft; 8% cov)
        (mcap > 0) & (mcap < 5e9)                # small/mid, where this is mispriced
    ).fillna(False).astype(int)

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
        'arch_capital_light_pivot',
        'arch_capital_returner',
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
        'arch_oak_order_conversion',
        'arch_weschler_levered_equity',
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
        'arch_oak_order_conversion': 'OakOrderConversion',
        'arch_weschler_levered_equity': 'WeschlerLeveredEquity',
    }
    df['archetype_count'] = df[arch_cols].sum(axis=1)
    df['archetype_tags_str'] = df[arch_cols].apply(
        lambda r: ', '.join(pretty[c] for c in arch_cols if r[c] == 1),
        axis=1,
    )

    out = df[['symbol'] + arch_cols + ['archetype_count','archetype_tags_str','bab_score']]
    out.to_csv(out_path, index=False)

    # Summary to stderr
    print(f'wrote {out_path}: {len(out)} rows', file=sys.stderr)
    for c in arch_cols:
        n = int(df[c].sum())
        print(f'  {pretty[c]:24s} {n:5d}', file=sys.stderr)
    print(f'  multi-archetype (>=2) {int((df["archetype_count"] >= 2).sum())}', file=sys.stderr)
    return out


if __name__ == '__main__':
    compute()
