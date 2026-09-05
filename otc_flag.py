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
    global _OTC_SET
    if _OTC_SET is None:
        _OTC_SET = set()
        if os.path.exists('otc_expansion_universe.csv'):
            try:
                _OTC_SET = set(pd.read_csv('otc_expansion_universe.csv')['symbol'].dropna())
            except Exception:
                _OTC_SET = set()
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
    ap.add_argument('--otc-mode', choices=['all', 'otc', 'ex-otc'], default='all',
                    help="all (default) | otc (OTC tradings only) | "
                         "ex-otc (genuine exchange listings only)")


def apply_otc_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == 'all':
        return df
    mask = is_otc(df['symbol'], df['src'] if 'src' in df.columns else None)
    return df[mask] if mode == 'otc' else df[~mask]
