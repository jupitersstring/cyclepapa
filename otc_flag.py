"""Shared OTC classifier for the book builders.

`src` is the LISTING VENUE, not the domicile — foreign companies traded on US
OTC (5-letter tickers ending F = foreign ordinary, Y = ADR) carry src='US'
with country often missing, which put Japanese/Swedish/Canadian names on the
"US" sheets. A name is OTC when it is in the OTC expansion universe OR its
ticker matches the US OTC foreign pattern. The ex-OTC books therefore show
genuine domestic listings; every OTC trading (domestic pink/OTCQX included)
lives in the OTC books.
"""
from __future__ import annotations
import os

import pandas as pd

_OTC_SET = None


def _otc_universe() -> set:
    """Union of every OTC membership list we have.

    otc_expansion_universe.csv is the harvested OTC expansion set;
    otc_symbols.csv is the FinanceDatabase PNK/OQX/OQB list that the
    dedicated OTC archetype book publishes from. The ex-OTC books must
    exclude EVERYTHING the OTC book includes, so the classifier takes
    the union of both files (each if present) — otherwise thousands of
    names appear in both the ex-OTC and OTC books.
    """
    global _OTC_SET
    if _OTC_SET is None:
        _OTC_SET = set()
        for path in ('otc_expansion_universe.csv', 'otc_symbols.csv'):
            if os.path.exists(path):
                try:
                    _OTC_SET |= set(pd.read_csv(path, usecols=['symbol'])['symbol'].dropna())
                except Exception:
                    pass
    return _OTC_SET


def is_otc(symbols: pd.Series, src: pd.Series | None = None) -> pd.Series:
    """Boolean mask: True where the row is an OTC trading."""
    sym = symbols.astype(str)
    in_universe = sym.isin(_otc_universe())
    fy_pattern = sym.str.match(r'^[A-Z]{5}$') & sym.str[-1].isin(['F', 'Y'])
    if src is not None:
        fy_pattern = fy_pattern & (src.astype(str).str.upper() == 'US')
    return in_universe | fy_pattern


def add_otc_mode_arg(ap):
    ap.add_argument('--otc-mode', choices=['all', 'otc', 'ex-otc'], default='ex-otc',
                    help="ex-otc (default: genuine exchange listings) | "
                         "otc (OTC tradings only) | all")


def apply_otc_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == 'all':
        return df
    mask = is_otc(df['symbol'], df['src'] if 'src' in df.columns else None)
    return df[mask] if mode == 'otc' else df[~mask]


def add_high_filter_arg(ap):
    ap.add_argument('--high-filter', choices=['none', 'abs', 'rel', 'any', 'both'],
                    default='none',
                    help="restrict to names at 52-week highs: abs (vs itself) | "
                         "rel (vs the country index) | any | both | none")


def apply_high_filter(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == 'none':
        return df
    a = pd.to_numeric(df.get('high_52w_abs'), errors='coerce').fillna(0) > 0
    r = pd.to_numeric(df.get('high_52w_rel'), errors='coerce').fillna(0) > 0
    return df[{'abs': a, 'rel': r, 'any': a | r, 'both': a & r}[mode]]
