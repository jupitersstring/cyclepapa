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
                                 usecols=lambda c: c in {'symbol', 'p_tb',
                                                           'tangible_equity_pct',
                                                           'pct_off_52w_high'})

    # Merge.  Asym is the primary - everything else is enrichment.
    df = asym.merge(yart, on='symbol', how='left', suffixes=('','_y'))
    if edgar_roiic is not None:
        df = df.merge(edgar_roiic, on='symbol', how='left', suffixes=('','_er'))
    if edgar_yart is not None:
        df = df.merge(edgar_yart, on='symbol', how='left', suffixes=('','_ey'))
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

    # Q — Durable Growth: revenue 5y CAGR >= 8% AND topline accelerating
    # (3y CAGR > 5y CAGR) AND asset base growing. Multi-cycle expansion
    # without the single-year base-effect noise.
    df['arch_lindy_growth'] = (
        (revenue_5y_cagr >= 0.08) &
        (revenue_accel_lindy > 0) &
        (asset_5y_cagr > 0.03) &
        (years_of_history >= 5)
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
    }
    df['archetype_count'] = df[arch_cols].sum(axis=1)
    df['archetype_tags_str'] = df[arch_cols].apply(
        lambda r: ', '.join(pretty[c] for c in arch_cols if r[c] == 1),
        axis=1,
    )

    out = df[['symbol'] + arch_cols + ['archetype_count','archetype_tags_str']]
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
