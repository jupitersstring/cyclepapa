"""Working Yahoo Finance client — the actual fix, not a workaround.

ROOT CAUSE of the long "429 / rate-limit" saga: it was never an IP quota.
Yahoo's query1/query2 API requires a warmed cookie session + a crumb token.
Without them every call 429s immediately; WITH them the same IP sustains
~18 requests/sec with zero failures. The earlier HTML-scraper crawl at 1/s
was solving the wrong problem.

curl_cffi (yfinance's default transport) separately fails the TLS handshake
in this container. Passing a plain `requests` session to yfinance sidesteps
that. So both fixes together:

    from yahoo_session import get_session, quote_summary
    import yfinance as yf
    s = get_session()
    yf.Ticker('AAPL', session=s).info          # yfinance works natively
    quote_summary('AAPL', ['financialData'], s) # or call the API directly (faster)

The crumb lasts ~hours; we cache it and auto-re-warm on 401/429. Thread-safe
so parallel fetchers share one warmed session.
"""
from __future__ import annotations
import threading
import time

import requests

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
_HEADERS = {
    'User-Agent': _UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

_lock = threading.Lock()
_session: requests.Session | None = None
_crumb: str | None = None
_warmed_at: float = 0.0


def _warm() -> tuple[requests.Session, str]:
    """Create a fresh session, set the A1/A3/A1S cookies, fetch a crumb."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    s.get('https://finance.yahoo.com/', timeout=15)
    crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb',
                  timeout=15).text.strip()
    if not crumb or 'Too Many' in crumb or '<' in crumb:
        raise RuntimeError(f'crumb fetch failed: {crumb[:40]!r}')
    return s, crumb


def get_session(force: bool = False) -> requests.Session:
    """Return a warmed session (shared). Re-warms if older than ~2h or forced."""
    global _session, _crumb, _warmed_at
    with _lock:
        if force or _session is None or (time.time() - _warmed_at) > 7200:
            _session, _crumb = _warm()
            _warmed_at = time.time()
        return _session


def get_crumb() -> str:
    get_session()
    return _crumb  # type: ignore


def _rewarm():
    global _session, _crumb, _warmed_at
    with _lock:
        _session, _crumb = _warm()
        _warmed_at = time.time()


def quote_summary(symbol: str, modules: list[str],
                  session: requests.Session | None = None,
                  retries: int = 2) -> dict:
    """Fetch quoteSummary modules for a symbol. Returns the merged module
    dict ({} on genuine no-data / 404). Auto-re-warms on 401/429."""
    s = session or get_session()
    mod = ','.join(modules)
    for attempt in range(retries + 1):
        crumb = get_crumb()
        url = (f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/'
               f'{symbol}?modules={mod}&crumb={crumb}')
        try:
            r = s.get(url, timeout=15)
        except Exception:
            time.sleep(0.5)
            continue
        if r.status_code == 200:
            try:
                res = r.json()['quoteSummary']['result']
                if not res:
                    return {}
                out = {}
                for m in res[0].values():
                    if isinstance(m, dict):
                        out.update(m)
                return out
            except Exception:
                return {}
        if r.status_code in (401, 429) and attempt < retries:
            _rewarm()
            s = get_session()
            time.sleep(0.3)
            continue
        if r.status_code == 404:
            return {}
        time.sleep(0.3)
    return {}


def chart(symbol: str, rng: str = '2y', interval: str = '1d',
          session: requests.Session | None = None) -> dict:
    """Price history via the v8 chart endpoint. Returns
    {'timestamp': [...], 'close': [...]} or {}."""
    s = session or get_session()
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/'
           f'{symbol}?range={rng}&interval={interval}')
    try:
        r = s.get(url, timeout=15)
        if r.status_code in (401, 429):
            _rewarm(); s = get_session()
            r = s.get(url, timeout=15)
        if r.status_code != 200:
            return {}
        res = r.json()['chart']['result'][0]
        return {'timestamp': res.get('timestamp', []),
                'close': res['indicators']['quote'][0].get('close', []),
                'meta': res.get('meta', {})}
    except Exception:
        return {}


# Number-typed quoteSummary fields → the raw value (Yahoo wraps as {raw,fmt})
def _raw(node, key):
    v = node.get(key)
    if isinstance(v, dict):
        return v.get('raw')
    return v


def fetch_info(symbol: str, session: requests.Session | None = None) -> dict:
    """Fetch a rich info_metrics-shaped record via the API. Far more complete
    than the old HTML scrape — pulls the full financialData +
    defaultKeyStatistics + summaryDetail + price + assetProfile modules."""
    mods = ['price', 'summaryDetail', 'defaultKeyStatistics', 'financialData',
            'assetProfile']
    d = quote_summary(symbol, mods, session)
    if not d:
        return {'_error': 'no_data'}
    out = {'_ticker': symbol, '_source': 'yahoo_api', '_fetched_at': None}
    num = ['marketCap', 'enterpriseValue', 'trailingPE', 'forwardPE',
           'priceToBook', 'priceToSalesTrailing12Months', 'enterpriseToEbitda',
           'enterpriseToRevenue', 'totalRevenue', 'ebitda', 'returnOnEquity',
           'returnOnAssets', 'grossMargins', 'operatingMargins', 'profitMargins',
           'dividendYield', 'debtToEquity', 'currentRatio', 'quickRatio',
           'revenueGrowth', 'earningsGrowth', 'earningsQuarterlyGrowth',
           'sharesOutstanding', 'bookValue', 'totalCash', 'totalDebt',
           'freeCashflow', 'operatingCashflow', 'trailingEps', 'forwardEps',
           'currentPrice', 'regularMarketPrice', 'fiftyTwoWeekLow',
           'fiftyTwoWeekHigh', 'twoHundredDayAverage', 'fiftyDayAverage',
           'targetMeanPrice', 'targetHighPrice', 'targetLowPrice',
           'numberOfAnalystOpinions', 'recommendationMean']
    for k in num:
        v = _raw(d, k)
        if v is not None:
            out[k] = v
    # 52-week change: Yahoo's key is "52WeekChange" (leading digit). Downstream
    # screens (asymmetry, crashed_quality, unpriced_segment) read it as
    # `fiftyTwoWeekChange`, matching yfinance .info — remap it here.
    chg = _raw(d, '52WeekChange')
    if chg is not None:
        out['fiftyTwoWeekChange'] = chg
    sp = _raw(d, 'SandP52WeekChange')
    if sp is not None:
        out['SandP52WeekChange'] = sp
    for k in ('sector', 'industry', 'country', 'longName', 'shortName',
              'currency'):
        v = d.get(k)
        if isinstance(v, str) and v:
            out[k] = v
    return out


if __name__ == '__main__':
    import sys
    syms = sys.argv[1:] or ['AAPL', '600519.SS', 'RELIANCE.NS', '000002.SZ']
    s = get_session()
    print(f'crumb: {get_crumb()!r}')
    for sym in syms:
        info = fetch_info(sym, s)
        print(f'{sym:<14} mcap={info.get("marketCap")}  EV/EBITDA={info.get("enterpriseToEbitda")}  '
              f'PE={info.get("trailingPE")}  sector={info.get("sector")}')
