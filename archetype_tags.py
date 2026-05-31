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

    # Merge.  Asym is the primary - everything else is enrichment.
    df = asym.merge(yart, on='symbol', how='left', suffixes=('','_y'))
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

    mcap = s('market_cap')
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
    df['arch_kpi_threshold'] = (
        (ebitda_first_pos > 0) | (cfo_first_pos > 0) | (fcf_first_pos > 0) |
        (ni_first_pos > 0) | (roce_first_pos > 0)
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

    arch_cols = [
        'arch_narrative_lag',
        'arch_fixed_cost_demand_shock',
        'arch_discounted_vehicle',
        'arch_capital_discipline',
        'arch_regime_cyclical',
        'arch_dead_option',
        'arch_kpi_threshold',
        'arch_blindspot',
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
