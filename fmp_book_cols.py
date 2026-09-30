"""Shared FMP column block for the country books.

Every country-level book (country workbook, country archetype books, the
top-N-by-country books) appends the same FMP block so the FMP layer reads the
same way everywhere:

  Piotroski | ROIC lindy % | Inst Δown pp | Inst accum | EM rev % | FMP signals

`attach_fmp(df)` merges these columns FRESH from archetype_tags.csv. It first
drops any existing copy, so a stale value can never win a merge collision
(the master is not the source of truth for FMP columns).
"""
from __future__ import annotations

import os

import pandas as pd

FMP_SOURCE = 'archetype_tags.csv'
FMP_COLS = ['fmp_signals', 'fmp_piotroski', 'roic_lindy_eff', 'inst_accum_score',
            'fmp_inst_own_chg_q0', 'inst_own_excess_q0', 'fmp_geo_em_share',
            'fmp_seg_fastest_name', 'fmp_seg_fastest_yoy', 'cluseau_sizing_tier',
            'arch_institutional_accumulation', 'inst_accum_accelerating']

# Leledc exhaustion levels (leledc_levels.py, weekly and monthly bars): the
# last exhaustion signal and its age, and the close's distance to the latest
# exhaustion resistance (high of the last sell bar) and support (low of the
# last buy bar). + = above the level, - = below it.
LELEDC_SOURCE = 'leledc_levels.csv'
LELEDC_COLS = ['lel_w_signal', 'lel_w_bars_since', 'lel_w_res_dist', 'lel_w_sup_dist',
               'lel_m_signal', 'lel_m_bars_since', 'lel_m_res_dist', 'lel_m_sup_dist']
FMP_HEADERS = ['Piotroski', 'ROIC lindy %', 'Inst Δown pp', 'Inst accum', 'EM rev %', 'FMP signals',
               'Lel W', 'Lel W res %', 'Lel W sup %', 'Lel M', 'Lel M res %', 'Lel M sup %']
FMP_WIDTHS = [9, 11, 11, 9, 9, 58, 10, 10, 10, 10, 10, 10]


def attach_fmp(df: pd.DataFrame, source: str = FMP_SOURCE) -> pd.DataFrame:
    if not os.path.exists(source) or 'symbol' not in df.columns:
        return df
    have = pd.read_csv(source, nrows=0).columns
    cols = [c for c in FMP_COLS if c in have]
    if not cols:
        return df
    fmp = pd.read_csv(source, usecols=['symbol'] + cols, low_memory=False).drop_duplicates('symbol')
    df = df.drop(columns=[c for c in cols if c in df.columns])
    df = df.merge(fmp, on='symbol', how='left')
    if os.path.exists(LELEDC_SOURCE):
        lhave = pd.read_csv(LELEDC_SOURCE, nrows=0).columns
        lcols = [c for c in LELEDC_COLS if c in lhave]
        lel = pd.read_csv(LELEDC_SOURCE, usecols=['symbol'] + lcols, low_memory=False).drop_duplicates('symbol')
        df = df.drop(columns=[c for c in lcols if c in df.columns]).merge(lel, on='symbol', how='left')
    return df


def write_fmp_block(ws, row: int, start_col: int, r, font=None) -> None:
    """Write the six FMP cells for one row starting at `start_col`."""
    from build_harvard_workbook import _write_pct, _write_score, _TXT_ALIGN_LEFT

    def g(k):
        v = r.get(k) if hasattr(r, 'get') else None
        return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v

    _write_score(ws, row, start_col, g('fmp_piotroski'), font=font)
    _write_pct(ws, row, start_col + 1, g('roic_lindy_eff'), font=font)
    _write_score(ws, row, start_col + 2, g('fmp_inst_own_chg_q0'), font=font)
    _write_score(ws, row, start_col + 3, g('inst_accum_score'), font=font)
    _write_pct(ws, row, start_col + 4, g('fmp_geo_em_share'), font=font)
    sig = g('fmp_signals')
    c = ws.cell(row=row, column=start_col + 5, value=str(sig)[:120] if sig else '')
    if font is not None:
        c.font = font
    c.alignment = _TXT_ALIGN_LEFT
    # Leledc: "Buy 3" = the last exhaustion signal was a BUY (downside
    # exhausted) 3 bars ago; "Sell 12" = a SELL (upside exhausted) 12 bars ago
    for k, tf in enumerate(('w', 'm')):
        base = start_col + 6 + 3 * k
        s_, n_ = g(f'lel_{tf}_signal'), g(f'lel_{tf}_bars_since')
        txt = '' if s_ is None else (('Buy ' if s_ > 0 else 'Sell ') + ('' if n_ is None else str(int(n_))))
        cc = ws.cell(row=row, column=base, value=txt)
        if font is not None:
            cc.font = font
        _write_pct(ws, row, base + 1, g(f'lel_{tf}_res_dist'), font=font)
        _write_pct(ws, row, base + 2, g(f'lel_{tf}_sup_dist'), font=font)
