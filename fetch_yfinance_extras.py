"""Fetch high-value yfinance endpoints not previously cached.

Adds five new per-ticker caches (one parquet each), per the YFINANCE_REFERENCE
audit:

  *  growth_estimates         — 5-year consensus growth + peer comparisons
  *  analyst_price_targets    — current/mean/low/high target prices
  *  insider_purchases        — net insider buy/sell over the last 6 months
  *  recommendations_summary  — broker rating bucket (strongBuy/buy/hold/sell)
  *  earnings_estimate        — next-Q and next-Y consensus EPS

Each row is keyed on `<safe_ticker>__<slot>.parquet`. A `<slot>.dead` sentinel
is written when an endpoint legitimately returns nothing — so future runs
don't re-fetch known empties.

Run pattern matches fetch_all_deep.py: chunked, time-boxed, resumable. Default
chunk targets ~9 min of inline runtime, with snapshot pushes between chunks.
"""
from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_session import get_session, quote_summary_modules

CACHE = Path('.cache/yf')
CACHE.mkdir(parents=True, exist_ok=True)

# We fetch these five slots straight from Yahoo's quoteSummary modules via our
# own warmed cookie+crumb client (yahoo_session) instead of yfinance's lazy
# Ticker properties. yfinance's default curl_cffi transport fails the TLS
# handshake here ("curl: (35)"), and even with a plain session passed in, its
# INTERNAL crumb management (a 'basic'/'csrf' fallback dance, separate from the
# session's crumb) intermittently 429s under our shared IP + concurrency and
# raises YFRateLimitError. Our client is the proven path (69/s concurrent), so
# we read the raw modules and reshape them into the exact frames the downstream
# screener expects — no yfinance dependency, no fragile double crumb.
#
# Slot -> source module:
#   growth_estimates        <- earningsTrend            (per-period `growth`)
#   earnings_estimate       <- earningsTrend            (per-period earningsEstimate)
#   analyst_price_targets   <- financialData            (current + target prices)
#   insider_purchases       <- netSharePurchaseActivity (6m buy/sell/net)
#   recommendations_summary <- recommendationTrend      (rating buckets)
_EXTRAS_MODULES = ['earningsTrend', 'financialData',
                   'netSharePurchaseActivity', 'recommendationTrend']

SLOTS = (
    'growth_estimates',
    'analyst_price_targets',
    'insider_purchases',
    'recommendations_summary',
    'earnings_estimate',
)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _outpath(t: str, slot: str) -> Path:
    return CACHE / f'{_safe(t)}__{slot}.parquet'


def _deadpath(t: str, slot: str) -> Path:
    return CACHE / f'{_safe(t)}__{slot}.dead'


def _missing(cache_key: str) -> list[str]:
    """Return slots that have neither a parquet nor a .dead sentinel.
    Operates on the cache_key (on-disk name), not the live ticker symbol."""
    out = []
    for s in SLOTS:
        if _outpath(cache_key, s).exists() or _deadpath(cache_key, s).exists():
            continue
        out.append(s)
    return out


def _raw(v):
    """Unwrap Yahoo's {raw, fmt} number wrapper to the raw value."""
    return v.get('raw') if isinstance(v, dict) else v


# --- Builders: reshape a raw quoteSummary module into the exact DataFrame the
# downstream screener (analyst_extras_screener.py) reads. Each returns None
# when the module carries no usable data (→ a .dead sentinel is written).

def _build_growth_estimates(et: dict) -> pd.DataFrame | None:
    """index=period (0q/+1q/0y/+1y/LTG), col stockTrend = per-period earnings
    growth. indexTrend isn't in this module (yfinance sources it separately)
    and the screener doesn't read it, so it's left NaN. Matches yfinance's
    Ticker.growth_estimates shape (period index, stockTrend column)."""
    trend = et.get('trend') or []
    idx, stock = [], []
    for t in trend:
        p = t.get('period')
        if not p:
            continue
        idx.append('LTG' if p == '+5y' else p)
        stock.append(_raw(t.get('growth')))
    if not idx:
        return None
    df = pd.DataFrame({'stockTrend': stock, 'indexTrend': [float('nan')] * len(idx)},
                      index=idx)
    df.index.name = 'period'
    return df


def _build_earnings_estimate(et: dict) -> pd.DataFrame | None:
    """index=period, cols avg/low/high/numberOfAnalysts/yearAgoEps/growth/
    currency — from each earningsTrend period's earningsEstimate block."""
    trend = et.get('trend') or []
    rows = {}
    for t in trend:
        p = t.get('period')
        ee = t.get('earningsEstimate') or {}
        if not p or not ee:
            continue
        rows[p] = {
            'avg': _raw(ee.get('avg')), 'low': _raw(ee.get('low')),
            'high': _raw(ee.get('high')),
            'numberOfAnalysts': _raw(ee.get('numberOfAnalysts')),
            'yearAgoEps': _raw(ee.get('yearAgoEps')),
            'growth': _raw(ee.get('growth')),
            'currency': ee.get('earningsCurrency'),
        }
    if not rows:
        return None
    df = pd.DataFrame.from_dict(rows, orient='index')
    df.index.name = 'period'
    return df


def _build_analyst_price_targets(fd: dict) -> pd.DataFrame | None:
    """Single-row current/high/low/mean/median from financialData."""
    cur = _raw(fd.get('currentPrice'))
    mean = _raw(fd.get('targetMeanPrice'))
    if cur is None and mean is None:
        return None
    return pd.DataFrame([{
        'current': cur, 'high': _raw(fd.get('targetHighPrice')),
        'low': _raw(fd.get('targetLowPrice')), 'mean': mean,
        'median': _raw(fd.get('targetMedianPrice')),
    }])


def _build_insider_purchases(a: dict) -> pd.DataFrame | None:
    """Reconstruct yfinance's insider_purchases table. The screener matches the
    row whose label starts '% Net Shares Purchased' and reads its 'Shares'
    cell, so that row must be present and carry netPercentInsiderShares."""
    net_pct = _raw(a.get('netPercentInsiderShares'))
    buy_shares = _raw(a.get('buyInfoShares'))
    if net_pct is None and buy_shares is None:
        return None
    rows = [
        {'Insider Purchases Last 6m': 'Purchases',
         'Shares': buy_shares, 'Trans': _raw(a.get('buyInfoCount'))},
        {'Insider Purchases Last 6m': 'Sales',
         'Shares': _raw(a.get('sellInfoShares')), 'Trans': _raw(a.get('sellInfoCount'))},
        {'Insider Purchases Last 6m': 'Net Shares Purchased (Sold)',
         'Shares': _raw(a.get('netInfoShares')), 'Trans': _raw(a.get('netInfoCount'))},
        {'Insider Purchases Last 6m': 'Total Insider Shares Held',
         'Shares': _raw(a.get('totalInsiderShares')), 'Trans': None},
        {'Insider Purchases Last 6m': '% Net Shares Purchased (Sold)',
         'Shares': net_pct, 'Trans': None},
        {'Insider Purchases Last 6m': '% Buy Shares',
         'Shares': _raw(a.get('buyPercentInsiderShares')), 'Trans': None},
    ]
    return pd.DataFrame(rows)


def _build_recommendations_summary(rt: dict) -> pd.DataFrame | None:
    """period + strongBuy/buy/hold/sell/strongSell from recommendationTrend."""
    trend = rt.get('trend') or []
    rows = []
    for t in trend:
        rows.append({
            'period': t.get('period'),
            'strongBuy': _raw(t.get('strongBuy')), 'buy': _raw(t.get('buy')),
            'hold': _raw(t.get('hold')), 'sell': _raw(t.get('sell')),
            'strongSell': _raw(t.get('strongSell')),
        })
    if not rows:
        return None
    return pd.DataFrame(rows)


def fetch_one(cache_key: str, ticker_symbol: str | None = None) -> dict[str, str]:
    """Fetch every missing slot for one ticker via our quoteSummary client and
    reshape into the per-slot parquets. `cache_key` is the on-disk name;
    `ticker_symbol` is the real symbol (defaults to cache_key for plain US
    tickers). Returns a per-slot status: 'ok' | 'empty' | 'fetch_error'."""
    if ticker_symbol is None:
        ticker_symbol = _cache_key_to_ticker(cache_key)
    todo = _missing(cache_key)
    if not todo:
        return {s: 'cached' for s in SLOTS}
    mods = quote_summary_modules(ticker_symbol, _EXTRAS_MODULES, get_session(),
                                 timeout=8)
    if not mods:
        # No data at all (dead symbol / no coverage): mark todo slots empty so
        # we don't re-fetch. A transient network miss returns {} too, but the
        # .dead sentinel only blocks THIS slot and a genuine name reappears via
        # its info_metrics — acceptable for these secondary analytics.
        for s in todo:
            _deadpath(cache_key, s).touch()
        return {s: 'empty' for s in todo}

    builders = {
        'growth_estimates': lambda: _build_growth_estimates(mods.get('earningsTrend', {})),
        'earnings_estimate': lambda: _build_earnings_estimate(mods.get('earningsTrend', {})),
        'analyst_price_targets': lambda: _build_analyst_price_targets(mods.get('financialData', {})),
        'insider_purchases': lambda: _build_insider_purchases(mods.get('netSharePurchaseActivity', {})),
        'recommendations_summary': lambda: _build_recommendations_summary(mods.get('recommendationTrend', {})),
    }
    results: dict[str, str] = {}
    for slot in todo:
        try:
            df = builders[slot]()
        except Exception:
            results[slot] = 'fetch_error'
            continue
        if df is None or df.empty:
            _deadpath(cache_key, slot).touch()
            results[slot] = 'empty'
            continue
        try:
            df.to_parquet(_outpath(cache_key, slot), compression='snappy')
            results[slot] = 'ok'
        except Exception:
            try:
                df.astype(str).to_parquet(_outpath(cache_key, slot),
                                          compression='snappy')
                results[slot] = 'ok'
            except Exception:
                results[slot] = 'fetch_error'
    return results


# Region-suffix mapping — recovers the original ticker (e.g. 000955.SZ) from
# the on-disk cache key (000955_SZ), which encodes "." as "_". Keep in sync
# with the same map in growth_adj_value.py.
_KNOWN_SUFFIXES = {
    'T','L','DE','F','PA','TO','V','AX','SW','MI','AS','MC','ST','OL','CO','BR',
    'HE','IR','VI','LS','AT','KS','KQ','HK','TW','TWO','SI','NZ','TA','SS','SZ',
    'NS','BO','SA','MX','JO','IS','BK','JK',
}

def _cache_key_to_ticker(key: str) -> str:
    """Reverse the cache-name → symbol mapping. The on-disk name encodes
    everything that isn't [A-Za-z0-9_-] (mainly '.') as '_'. We can recover
    `<head>.<suffix>` when `<suffix>` is a known regional exchange suffix.
    Tickers without a regional suffix are returned unchanged."""
    if '_' in key:
        head, _, tail = key.rpartition('_')
        if tail in _KNOWN_SUFFIXES:
            return f'{head}.{tail}'
    return key


def universe_tickers() -> list[tuple[str, str]]:
    """Return (cache_key, ticker_symbol) pairs for every ticker that has an
    info_metrics parquet. The cache_key is the stable on-disk filename;
    the ticker_symbol is what we pass to yf.Ticker.

    Ordering: US tickers first (highest analyst-coverage payoff), then
    other markets sorted alphabetically by region suffix. Non-US analyst
    endpoints mostly return empty, so doing US first means we get all the
    actionable data within the first ~2500 fetches."""
    keys = sorted({p.name.split('__')[0]
                   for p in CACHE.glob('*__info_metrics.parquet')})
    us, other = [], []
    for k in keys:
        sym = _cache_key_to_ticker(k)
        if '.' in sym:
            other.append((k, sym))
        else:
            us.append((k, sym))
    return us + other


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-tickers', type=int, default=12000,
                    help='Cap per chunk.')
    ap.add_argument('--sleep', type=float, default=0.05,
                    help='Per-worker sleep — small since N workers in parallel.')
    ap.add_argument('--workers', type=int, default=8,
                    help='Concurrent yfinance sessions.')
    ap.add_argument('--us-only', action='store_true', default=True,
                    help='Skip non-US tickers (yfinance has no analyst data for them).')
    ap.add_argument('--include-non-us', dest='us_only', action='store_false')
    ap.add_argument('--progress-every', type=int, default=200)
    args = ap.parse_args()

    universe = universe_tickers()
    # SKIP non-US tickers — yfinance has zero analyst/insider coverage for them
    # (verified empirically: ~50% of fetch time was wasted on Chinese/Korean
    # tickers that always return empty + slow timeouts). The earlier full-
    # universe pass already wrote dead sentinels for the few that had data.
    if args.us_only:
        universe = [(k, s) for k, s in universe if '.' not in s]
    todo = [(k, s) for k, s in universe if _missing(k)]
    print(f'Universe size: {len(universe):,} tickers ({"US-only" if args.us_only else "all"})')
    print(f'Tickers with missing extras slots: {len(todo):,}')
    if not todo:
        print('All caught up.')
        return

    target = todo[: args.max_tickers]
    t0 = time.time()
    n_ok = n_empty = n_err = 0
    counter_lock = threading.Lock()
    progress_counter = [0]

    def worker(item):
        nonlocal n_ok, n_empty, n_err
        key, sym = item
        r = fetch_one(key, sym)
        with counter_lock:
            progress_counter[0] += 1
            i = progress_counter[0]
            for slot, status in r.items():
                if status == 'ok': n_ok += 1
                elif status == 'empty': n_empty += 1
                elif status == 'fetch_error': n_err += 1
            if i % args.progress_every == 0:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(target) - i) / rate / 60 if rate > 0 else float('inf')
                print(f'  {i:>5,}/{len(target):,}  ok={n_ok:,} empty={n_empty:,} '
                      f'err={n_err:,} rate={rate:.1f}/s eta={eta_min:.0f}min',
                      flush=True)
        time.sleep(args.sleep)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(worker, target))

    print(f'\nFinal: ok={n_ok:,} empty={n_empty:,} err={n_err:,} '
          f'across {len(target):,} tickers')


if __name__ == '__main__':
    main()
