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


_NAME_SUFFIX_RE = None


def _name_norm_re():
    global _NAME_SUFFIX_RE
    if _NAME_SUFFIX_RE is None:
        import re
        _NAME_SUFFIX_RE = re.compile(
            r'\b(plc|ltd|limited|inc|incorporated|corp|corporation|ag|nv|sa|'
            r'ab|se|spa|s\.a|s\.p\.a|co|company|holdings?|group|adr|'
            r'sponsored|class [ab]|cl [ab]|-[ab])\b', re.I)
    return _NAME_SUFFIX_RE


def dedupe_display(df: pd.DataFrame, name_col: str = 'name',
                   within: str | None = None) -> pd.DataFrame:
    """Collapse cross-listings / dual-class lines of the SAME business to
    one display row (the caller must have sorted best-first). ~24% of the
    universe sits in a name-collision group (ADR + home line, A/B share
    classes) — without this a top-N list double-counts one company.
    Conservative: keys on the normalized company name only; rows with no
    name are never collapsed."""
    if name_col not in df.columns or df.empty:
        return df
    # Non-common security lines are display noise for an equity multibagger
    # screen: preferred series (COF-PI ranked #2 in the US top-30 on an
    # 'asymmetry' that is really a rate artifact), warrants, units, rights.
    # Name normalization cannot collapse them into the common (their names
    # carry long depositary tails), so filter explicitly. Master keeps them.
    _sym = df.get('symbol', pd.Series('', index=df.index)).astype(str)
    _nm = df[name_col].fillna('').astype(str).str.lower()
    _noncommon = (_sym.str.match(r'^[A-Z]{1,5}-P[A-Z]?$')
                  | _sym.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT)$')
                  | _nm.str.contains(r'preferred|% notes|depositary sh|'
                                     r'perpetual pref|warrant', regex=True))
    df = df[~_noncommon]
    if df.empty:
        return df
    names = df[name_col].fillna('').astype(str).str.lower()
    names = names.str.replace(_name_norm_re(), '', regex=True)
    names = names.str.replace(r'[^a-z0-9]+', '', regex=True)
    key = names.where(names != '', df.get('symbol', names))
    if within is not None and within in df.columns:
        key = df[within].astype(str) + '|' + key
    return df[~key.duplicated(keep='first')]
