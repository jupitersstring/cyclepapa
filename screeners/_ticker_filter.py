"""Shared instrument filter for all screeners.

Excludes warrants / units / rights / preferreds by NAME (financedatabase gives us
the security name), plus explicit derivative ticker suffixes. This replaces the old
blunt heuristic `endswith('U') or endswith('W')` which silently dropped legitimate
common stocks such as U (Unity), DOW, FLOW, LAW, WOW, NU, EDU, SNOW, AAWW …

Usage in a screener:
    from _ticker_filter import common_stock_tickers
    uni = pd.read_csv(args.universe)
    syms = common_stock_tickers(uni)
"""
import os, sys, re
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

# Security-name markers of a non-common instrument (word-boundary, case-insensitive).
_NONCOMMON_NAME = re.compile(
    r'\b(warrant|warrants|unit|units|right|rights|preferred|pfd|'
    r'depositary|debenture|subordinated|when[- ]issued|convertible\s+note)\b', re.I)

# Explicit derivative ticker suffixes — ONLY with a separator, so bare commons
# ending in U/W (DOW, U, FLOW, NU) are preserved.
_SUFFIX = re.compile(
    r'([.\-](WT|WTS|WS|UN|RT|R|U|W)$)'   # -WT/-UN/-U/-W/.WS/.U … (separator required)
    r'|(-P[A-Z]$)'                        # -PA .. -PZ  preferreds
    r'|(\.PR[A-Z]?$)'                     # .PR / .PRA  preferreds
    r'|(\$)',                             # any '$' (preferred convention on some feeds)
    re.I)


def is_common_stock(ticker, name=''):
    t = str(ticker)
    if not t or t.lower() == 'nan':
        return False
    if _SUFFIX.search(t):
        return False
    if name and _NONCOMMON_NAME.search(str(name)):
        return False
    return True


def common_stock_tickers(uni):
    """Return the de-duplicated list of common-stock tickers from a universe DataFrame."""
    if 'ticker' not in uni.columns:
        return []
    df = uni.dropna(subset=['ticker']).copy()
    df['ticker'] = df['ticker'].astype(str)
    names = df['name'].astype(str) if 'name' in df.columns else pd.Series('', index=df.index)
    mask = [is_common_stock(t, n) for t, n in zip(df['ticker'], names)]
    kept = df.loc[mask, 'ticker'].drop_duplicates().tolist()
    dropped = len(df) - len(kept)
    print(f"[ticker_filter] kept {len(kept)} common-stock tickers, dropped {dropped} "
          f"warrants/units/rights/preferreds", file=sys.stderr)
    return kept
