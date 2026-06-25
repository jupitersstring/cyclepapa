"""Yahoo Finance HTML scraper — bypasses query1/query2.finance.yahoo.com
(IP-rate-limited on our shared egress) by hitting finance.yahoo.com/quote/{TKR}/
which serves the same quoteSummary JSON embedded in the HTML.

ROOT CAUSE CONTEXT:
* yfinance v1.2+ uses curl_cffi for TLS impersonation → curl_cffi 0.15.0
  fails OpenSSL handshake in this container (Failed to perform, curl: (35)
  TLS connect error). Affects every yfinance call.
* Even bypassing curl_cffi with plain requests, query1.finance.yahoo.com
  returns HTTP 429 across every endpoint (v8/chart, v10/quoteSummary,
  v7/quote, fc.yahoo.com crumb). Yahoo's API subdomains are blocking our
  shared egress IP (160.79.106.31).
* But finance.yahoo.com (the web frontend) returns HTTP 200. The page
  embeds the full quoteSummary JSON in HTML — same data, just a different
  URL.

The fields we extract match yfinance.Ticker.info exactly (same JSON keys
in `defaultKeyStatistics` / `financialData` / `summaryDetail` modules).
"""
from __future__ import annotations
import json, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

YF_CACHE = Path('.cache/yf')
YF_CACHE.mkdir(parents=True, exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


# Headers that look like a real browser. The User-Agent matters — Yahoo's
# anti-bot lets Chrome 120+ through.
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
}


# Yahoo embeds the field as `"fieldName\":{\"raw\":VALUE,\"fmt\":...}`. We
# extract every numeric `raw` value for the field names we care about.
# Keys map yfinance.Ticker.info name → regex.
_FIELD_PATTERNS = {
    'trailingPE':                       re.compile(r'trailingPE\\":\{\\"raw\\":([-\d.eE]+)'),
    'forwardPE':                        re.compile(r'forwardPE\\":\{\\"raw\\":([-\d.eE]+)'),
    'priceToBook':                      re.compile(r'priceToBook\\":\{\\"raw\\":([-\d.eE]+)'),
    'priceToSalesTrailing12Months':     re.compile(r'priceToSalesTrailing12Months\\":\{\\"raw\\":([-\d.eE]+)'),
    'enterpriseToEbitda':               re.compile(r'enterpriseToEbitda\\":\{\\"raw\\":([-\d.eE]+)'),
    'enterpriseToRevenue':              re.compile(r'enterpriseToRevenue\\":\{\\"raw\\":([-\d.eE]+)'),
    'enterpriseValue':                  re.compile(r'enterpriseValue\\":\{\\"raw\\":([-\d.eE]+)'),
    'marketCap':                        re.compile(r'marketCap\\":\{\\"raw\\":([-\d.eE]+)'),
    'totalRevenue':                     re.compile(r'totalRevenue\\":\{\\"raw\\":([-\d.eE]+)'),
    'ebitda':                           re.compile(r'ebitda\\":\{\\"raw\\":([-\d.eE]+)'),
    'returnOnEquity':                   re.compile(r'returnOnEquity\\":\{\\"raw\\":([-\d.eE]+)'),
    'returnOnAssets':                   re.compile(r'returnOnAssets\\":\{\\"raw\\":([-\d.eE]+)'),
    'grossMargins':                     re.compile(r'grossMargins\\":\{\\"raw\\":([-\d.eE]+)'),
    'operatingMargins':                 re.compile(r'operatingMargins\\":\{\\"raw\\":([-\d.eE]+)'),
    'profitMargins':                    re.compile(r'profitMargins\\":\{\\"raw\\":([-\d.eE]+)'),
    'dividendYield':                    re.compile(r'dividendYield\\":\{\\"raw\\":([-\d.eE]+)'),
    'debtToEquity':                     re.compile(r'debtToEquity\\":\{\\"raw\\":([-\d.eE]+)'),
    'currentRatio':                     re.compile(r'currentRatio\\":\{\\"raw\\":([-\d.eE]+)'),
    'quickRatio':                       re.compile(r'quickRatio\\":\{\\"raw\\":([-\d.eE]+)'),
    'revenueGrowth':                    re.compile(r'revenueGrowth\\":\{\\"raw\\":([-\d.eE]+)'),
    'earningsGrowth':                   re.compile(r'earningsGrowth\\":\{\\"raw\\":([-\d.eE]+)'),
    'earningsQuarterlyGrowth':          re.compile(r'earningsQuarterlyGrowth\\":\{\\"raw\\":([-\d.eE]+)'),
    'sharesOutstanding':                re.compile(r'sharesOutstanding\\":\{\\"raw\\":([-\d.eE]+)'),
    'bookValue':                        re.compile(r'bookValue\\":\{\\"raw\\":([-\d.eE]+)'),
    'totalCash':                        re.compile(r'totalCash\\":\{\\"raw\\":([-\d.eE]+)'),
    'totalDebt':                        re.compile(r'totalDebt\\":\{\\"raw\\":([-\d.eE]+)'),
    'freeCashflow':                     re.compile(r'freeCashflow\\":\{\\"raw\\":([-\d.eE]+)'),
    'operatingCashflow':                re.compile(r'operatingCashflow\\":\{\\"raw\\":([-\d.eE]+)'),
    'trailingEps':                      re.compile(r'trailingEps\\":\{\\"raw\\":([-\d.eE]+)'),
    'forwardEps':                       re.compile(r'forwardEps\\":\{\\"raw\\":([-\d.eE]+)'),
    'currentPrice':                     re.compile(r'currentPrice\\":\{\\"raw\\":([-\d.eE]+)'),
}

# Categorical fields parsed differently (string values)
_STRING_PATTERNS = {
    'sector':    re.compile(r'sector\\":\\"([^\\]+)'),
    'industry':  re.compile(r'industry\\":\\"([^\\]+)'),
    'country':   re.compile(r'country\\":\\"([^\\]+)'),
    'longName':  re.compile(r'longName\\":\\"([^\\]+)'),
    'shortName': re.compile(r'shortName\\":\\"([^\\]+)'),
    'currency':  re.compile(r'\\"currency\\":\\"([^\\]+)'),
}


def fetch_quote_html(symbol: str, session: requests.Session, timeout: int = 15) -> dict:
    """Hit finance.yahoo.com/quote/{symbol}/ and parse the embedded
    quoteSummary JSON into a dict matching yfinance.Ticker.info structure."""
    url = f'https://finance.yahoo.com/quote/{symbol}/'
    try:
        r = session.get(url, timeout=timeout, headers=_HEADERS)
    except Exception as e:
        return {'_error': f'fetch_failed: {e}'}
    if r.status_code != 200:
        return {'_error': f'http_{r.status_code}'}
    body = r.text
    out = {'_ticker': symbol, '_fetched_at': time.time(), '_source': 'yahoo_html'}
    for key, pat in _FIELD_PATTERNS.items():
        m = pat.search(body)
        if m:
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass
    for key, pat in _STRING_PATTERNS.items():
        m = pat.search(body)
        if m:
            out[key] = m.group(1)
    return out


def write_info_metrics(key: str, info: dict):
    """Write a single info_metrics parquet (same schema as yfinance.Ticker.info)."""
    if '_error' in info or not info:
        return False
    p = YF_CACHE / f'{_safe(key)}__info_metrics.parquet'
    df = pd.DataFrame([info])
    try:
        df.to_parquet(p, compression='snappy')
        return True
    except Exception:
        return False


_KNOWN_SUFFIXES = {'T','L','DE','F','PA','TO','V','AX','SW','MI','AS','MC','ST','OL','CO','BR',
                    'HE','IR','VI','LS','AT','KS','KQ','HK','TW','TWO','SI','NZ','TA','SS','SZ',
                    'NS','BO','SA','MX','JO','IS','BK','JK'}
def _cache_key_to_symbol(k):
    if '_' in k:
        head, _, tail = k.rpartition('_')
        if tail in _KNOWN_SUFFIXES: return f'{head}.{tail}'
    return k


def empty_or_stale_info_metrics(any_missing: bool = True) -> list[tuple[str, str]]:
    """Return (cache_key, symbol) pairs whose info_metrics is missing one or
    more of the key valuation fields. With any_missing=True (default), we
    refetch if ANY of EV/EBITDA / trailingPE / priceToBook is empty —
    casting a wide net so we catch tickers with partial coverage."""
    todo = []
    for p in YF_CACHE.glob('*__info_metrics.parquet'):
        key = p.name.split('__')[0]
        try:
            d = pd.read_parquet(p)
            if d.empty:
                todo.append((key, _cache_key_to_symbol(key)))
                continue
            r = d.iloc[0]
            ev = r.get('enterpriseToEbitda')
            pe = r.get('trailingPE')
            pb = r.get('priceToBook')
            empties = sum(1 for v in (ev, pe, pb) if pd.isna(v) or v is None)
            if (any_missing and empties >= 1) or (not any_missing and empties == 3):
                todo.append((key, _cache_key_to_symbol(key)))
        except Exception:
            todo.append((key, _cache_key_to_symbol(key)))
    return todo


def refetch_gap_tickers(workers: int = 4, sleep: float = 0.3, max_tickers: int = 5000):
    """Re-fetch info_metrics via HTML for tickers that are missing all
    three of EV/EBITDA, P/E, P/B."""
    todo = empty_or_stale_info_metrics()
    print(f'Tickers missing all valuation metrics: {len(todo):,}')
    if not todo:
        return
    target = todo[:max_tickers]
    sess = requests.Session()
    n_ok = n_fail = n_partial = 0
    t0 = time.time()

    def worker(item):
        nonlocal n_ok, n_fail, n_partial
        key, sym = item
        info = fetch_quote_html(sym, sess)
        if info.get('_error'):
            return ('fail', key, info.get('_error'))
        # Merge into existing (preserve existing data)
        p = YF_CACHE / f'{_safe(key)}__info_metrics.parquet'
        if p.exists():
            try:
                existing = pd.read_parquet(p).iloc[0].to_dict()
                # Only fill missing fields — don't overwrite Yahoo data we
                # already have
                for k, v in info.items():
                    if k not in existing or pd.isna(existing.get(k)) or existing.get(k) is None:
                        existing[k] = v
                info = existing
            except Exception:
                pass
        # Check we got at least one valuation metric
        got_one = any(info.get(k) is not None and not pd.isna(info.get(k)) for k in
                     ('enterpriseToEbitda','trailingPE','priceToBook','marketCap'))
        if got_one:
            pd.DataFrame([info]).to_parquet(p, compression='snappy')
            return ('ok', key, None)
        return ('partial', key, 'no_valuation_fields')

    from concurrent.futures import ThreadPoolExecutor
    import threading
    lock = threading.Lock()
    i_counter = [0]

    def report(result):
        nonlocal n_ok, n_fail, n_partial
        status, key, msg = result
        with lock:
            i_counter[0] += 1
            i = i_counter[0]
            if status == 'ok': n_ok += 1
            elif status == 'partial': n_partial += 1
            elif status == 'fail': n_fail += 1
            if i % 50 == 0:
                el = time.time() - t0
                rate = i / el if el > 0 else 0
                eta = (len(target) - i) / rate / 60 if rate > 0 else 0
                print(f'  {i:>5,}/{len(target):,}  ok={n_ok} partial={n_partial} fail={n_fail}  rate={rate:.2f}/s eta={eta:.0f}min', flush=True)
        time.sleep(sleep)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for result in ex.map(worker, target):
            report(result)

    print(f'\nFinal: ok={n_ok:,} partial={n_partial:,} fail={n_fail:,}')


if __name__ == '__main__':
    import sys
    if '--smoke' in sys.argv:
        sess = requests.Session()
        for sym in ['AAPL', 'MSFT', 'CELUW']:
            t0 = time.time()
            info = fetch_quote_html(sym, sess)
            print(f'{sym} t={time.time()-t0:.1f}s  EV/EBITDA={info.get("enterpriseToEbitda")!r}  '
                  f'P/E={info.get("trailingPE")!r}  P/B={info.get("priceToBook")!r}  '
                  f'mcap={info.get("marketCap")!r}  sector={info.get("sector")!r}')
            time.sleep(2)
    else:
        refetch_gap_tickers(workers=4, sleep=0.3)
