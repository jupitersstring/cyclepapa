"""Shared worksheet-tab colouring for every workbook builder.

A reader navigating a 50-70 tab workbook needs the tab strip to encode
structure at a glance. Two schemes:

  * COUNTRY books  -> colour by region (region_map bucket/region), so the
    European sheets, the EM-Asia sheets, etc. cluster visually.
  * ARCHETYPE books -> colour by archetype FAMILY (the named-investor packs
    — wolf/oak/liger/lynch/lindy — plus the value/quality/inflection/growth/
    segment themes), so related strategies share a colour.

Cover / summary / density / aggregate tabs get a dark slate so the
navigation sheets stand apart from the content sheets.

All colours are 8-digit ARGB (opaque). openpyxl accepts the hex string
directly on ws.sheet_properties.tabColor.
"""
from __future__ import annotations

# ---- navigation / summary tabs -------------------------------------------
COVER = 'FF1B2430'          # near-black slate — Cover, Density, summaries
AGGREGATE = 'FF4A5568'      # mid slate — GLOBAL/DM/EM/region roll-ups

# ---- region palette (country books) --------------------------------------
# keyed by the (bucket, region) tuples region_map.classify() returns.
REGION_COLORS = {
    ('DM', 'North America'): 'FF1F4E79',   # deep blue
    ('DM', 'W Europe'):      'FF2E7D32',   # green
    ('DM', 'Nordics'):       'FF00838F',   # teal
    ('DM', 'DM Asia-Pac'):   'FF6A1B9A',   # purple
    ('DM', 'MidEast DM'):    'FF8D6E00',   # dark gold
    ('EM', 'EM Asia'):       'FFC77400',   # amber
    ('EM', 'EM EMEA'):       'FFAD1457',   # magenta
    ('EM', 'LatAm'):         'FFAD4300',   # burnt orange
    ('EM', 'Other EM'):      'FF5D6D7E',   # blue-grey
}
_BUCKET_FALLBACK = {'DM': 'FF1F4E79', 'EM': 'FFC77400'}


def region_color(country_code: str) -> str | None:
    """Tab colour for a country sheet, by its region. None if unknown."""
    try:
        from region_map import classify
        bucket, region = classify(country_code)
    except Exception:
        return None
    return REGION_COLORS.get((bucket, region)) or _BUCKET_FALLBACK.get(bucket)


# ---- archetype families (archetype books) --------------------------------
# family -> colour
FAMILY_COLORS = {
    'deep_value':   'FF1F4E79',   # blue    — asset / NAV / net-net
    'quality':      'FF2E7D32',   # green   — compounders, durable reinvest
    'inflection':   'FFC77400',   # amber   — turnaround / inflect / cyclical
    'growth':       'FF6A1B9A',   # purple  — multibagger / scaler
    'capital':      'FF00838F',   # teal    — buyback / insider / capital return
    'lynch_screen': 'FFAD1457',   # magenta — Lynch / QARP / derating screens
    'segment':      'FF3949AB',   # indigo  — hidden-engine / segment lenses
    'contrarian':   'FF5D6D7E',   # grey    — neglect / narrative-lag / dead-option
    'momentum':     'FFB71C1C',   # crimson — trend/breakout traders (O'Neil/Weinstein/Kullamagi)
}

# Explicit archetype -> family. Named-investor packs stay together; the rest
# are grouped by economic theme. Anything unlisted falls to 'contrarian'.
ARCH_FAMILY = {
    # deep value / asset floor
    'arch_oak_asset_floor': 'deep_value', 'arch_oak_deep_value': 'deep_value',
    'arch_oak_nav_discount': 'deep_value', 'arch_oak_deleveraging': 'deep_value',
    'arch_oak_resource_leverage': 'deep_value', 'arch_oak_order_conversion': 'deep_value',
    'arch_negative_ev_value': 'deep_value', 'arch_tangible_value': 'deep_value',
    'arch_discounted_vehicle': 'deep_value', 'arch_templeton_pessimism': 'deep_value',
    'arch_liger_asset_backed': 'deep_value', 'arch_asymmetric_assembly': 'deep_value',
    'arch_weschler_levered_equity': 'deep_value',
    # quality / compounder
    'arch_buyback_compounder': 'quality', 'arch_quiet_compounder': 'quality',
    'arch_wolf_compounder': 'quality', 'arch_cash_quality': 'quality',
    'arch_low_sbc_quality': 'quality', 'arch_durable_reinvestment': 'quality',
    'arch_capital_discipline': 'quality', 'arch_strong_coverage': 'quality',
    'arch_owner_operator': 'quality', 'arch_lindy_fcf': 'quality',
    'arch_lindy_growth': 'quality', 'arch_lindy_margin': 'quality',
    'arch_no_dilution': 'quality', 'arch_tax_efficient': 'quality',
    'arch_cash_reinvest': 'quality', 'arch_wolf_seal': 'quality',
    'arch_large_cap_quality': 'quality',
    'arch_midcap_garp': 'growth',
    # inflection / turnaround / cyclical
    'arch_double_inflect': 'inflection', 'arch_reinvest_inflect': 'inflection',
    'arch_roic_inflect': 'inflection', 'arch_levered_inflection': 'inflection',
    'arch_liger_lagging_inflect': 'inflection', 'arch_micro_activist_inflect': 'inflection',
    'arch_wolf_turnaround': 'inflection', 'arch_fixed_cost_demand_shock': 'inflection',
    'arch_regime_cyclical': 'inflection', 'arch_capital_light_pivot': 'inflection',
    'arch_wolf_emerging': 'inflection', 'arch_wolf_value_catalyst': 'inflection',
    # growth / multibagger
    'arch_tenbagger_credible': 'growth', 'arch_tenbagger_path': 'growth',
    'arch_growth_algo': 'growth', 'arch_bab_multibagger': 'growth',
    'arch_bab_becoming': 'growth', 'arch_bab_low_beta': 'growth',
    'arch_exceptional_evsg': 'growth', 'arch_cheap_sales_scaler': 'growth',
    'arch_cheap_per_roiic': 'growth', 'arch_wolf_trifecta': 'growth',
    # capital return / insider
    'arch_capital_returner': 'capital', 'arch_insider_conviction': 'capital',
    'arch_balance_sheet_return': 'capital',
    'arch_net_cash_returner': 'capital',
    'arch_financials_value': 'deep_value',
    'arch_sustainable_scaler': 'growth',
    'arch_oneil_canslim': 'momentum', 'arch_weinstein_stage2': 'momentum',
    'arch_kullamagie_breakout': 'momentum',
    'arch_cundill_deep_value': 'deep_value',
    'arch_biotech_deep_value': 'deep_value',
    # Lynch / screen value
    'arch_lynch_reward': 'lynch_screen', 'arch_lynch_pegy': 'lynch_screen',
    'arch_lynch_evgy': 'lynch_screen', 'arch_qarp': 'lynch_screen',
    'arch_evsales_derating': 'lynch_screen',
    # segment / hidden-engine
    'arch_fastest_segment': 'segment', 'arch_concentrated_segments': 'segment',
    'arch_diversified_segments': 'segment', 'arch_geographic_global': 'segment',
    'arch_kpi_threshold': 'segment',
    # contrarian / neglect
    'arch_narrative_lag': 'contrarian', 'arch_blindspot': 'contrarian',
    'arch_asleep_at_wheel': 'contrarian', 'arch_dead_option': 'contrarian',
    'arch_analyst_awakening': 'contrarian', 'arch_liger_neglected_survivor': 'contrarian',
    # analyst re-rating CONFIRMED by 52w-high price strength — a momentum-
    # confirmed cousin of analyst_awakening, grouped with the trend/breakout set.
    'arch_analyst_rerating_confirmed': 'momentum',
}


def arch_color(arch_col: str) -> str:
    """Tab colour for a per-archetype sheet, by family."""
    fam = ARCH_FAMILY.get(arch_col, 'contrarian')
    return FAMILY_COLORS[fam]


def set_tab(ws, color: str | None) -> None:
    """Assign a tab colour, tolerant of None and of read-only sheets."""
    if not color:
        return
    try:
        ws.sheet_properties.tabColor = color
    except Exception:
        pass


def family_legend() -> list[tuple[str, str]]:
    """(_family label, colour) rows for a Cover-sheet legend."""
    labels = {
        'deep_value': 'Deep value / asset', 'quality': 'Quality / compounder',
        'inflection': 'Inflection / turnaround', 'growth': 'Growth / multibagger',
        'capital': 'Capital return / insider', 'lynch_screen': 'Lynch / screen value',
        'segment': 'Segment / hidden-engine', 'contrarian': 'Contrarian / neglect',
        'momentum': 'Trend/breakout traders',
    }
    return [(labels[f], c) for f, c in FAMILY_COLORS.items()]


def write_legend(ws, start_row: int, start_col: int, entries, *,
                 title: str = 'Tab colours', swatch_w: float = 2.4):
    """Write a compact colour legend: a solid swatch cell + label per row.
    entries = list of (label, argb). Tolerant of missing openpyxl bits."""
    try:
        from openpyxl.styles import PatternFill, Font, Alignment
    except Exception:
        return
    try:
        tc = ws.cell(row=start_row, column=start_col, value=title)
        tc.font = Font(size=9, bold=True, color='FF6B7280', name='Calibri')
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(start_col)].width = swatch_w
        for i, (label, argb) in enumerate(entries, start=start_row + 1):
            sw = ws.cell(row=i, column=start_col)
            sw.fill = PatternFill(start_color=argb, end_color=argb,
                                  fill_type='solid')
            lab = ws.cell(row=i, column=start_col + 1, value=label)
            lab.font = Font(size=9, color='FF374151', name='Calibri')
            lab.alignment = Alignment(horizontal='left')
    except Exception:
        pass


def region_legend():
    """(region label, colour) rows for a Cover-sheet legend, DM-then-EM."""
    return [(f'{b} · {r}', REGION_COLORS[(b, r)]) for (b, r) in REGION_COLORS]
