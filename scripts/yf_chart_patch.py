"""Monkey-patch yfinance.download to use the v8 chart endpoint directly.

Yahoo's v7/quote and v10/quoteSummary endpoints are aggressively rate-limited
(HTTP 429), but query1.finance.yahoo.com/v8/finance/chart/{sym} remains open.
This patch lets every existing screener (Qullamaggie, Episodic Pivot, weekly +
monthly compression) keep using `yf.download(...)` while we fetch via direct
JSON instead of the broken yfinance internal path.

Import this BEFORE importing yfinance:
    import yf_chart_patch
    import yfinance as yf
"""
import os, time, sys
import pandas as pd
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure CA bundle is set for the proxy environment
if os.path.exists('/root/.ccr/ca-bundle.crt'):
    os.environ.setdefault('REQUESTS_CA_BUNDLE', '/root/.ccr/ca-bundle.crt')
    os.environ.setdefault('SSL_CERT_FILE', '/root/.ccr/ca-bundle.crt')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/121.0 Safari/537.36')
_HEADERS = {'User-Agent': _UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'}

# Period → range param map matching yfinance's accepted strings
_PERIOD_MAP = {
    '1d':'1d','5d':'5d','1mo':'1mo','3mo':'3mo','6mo':'6mo',
    '1y':'1y','2y':'2y','5y':'5y','7y':'10y','10y':'10y','ytd':'ytd','max':'max',
}
_INTERVAL_MAP = {
    '1d':'1d','1wk':'1wk','1mo':'1mo','5d':'5d','1m':'1m','5m':'5m','15m':'15m','30m':'30m','60m':'60m','1h':'60m',
}


def _fetch_one(symbol, period, interval, session):
    """Fetch one symbol from chart API. Returns a DataFrame with OHLCV columns or None."""
    try:
        r = session.get(
            f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',
            params={'range': _PERIOD_MAP.get(period, period),
                    'interval': _INTERVAL_MAP.get(interval, interval)},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        j = r.json()
        result = j.get('chart', {}).get('result')
        if not result: return None
        result = result[0]
        ts = result.get('timestamp') or []
        if not ts: return None
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        adj = result.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [None]*len(ts)) if result.get('indicators', {}).get('adjclose') else [None]*len(ts)
        df = pd.DataFrame({
            'Open':      quote.get('open',  [np.nan]*len(ts)),
            'High':      quote.get('high',  [np.nan]*len(ts)),
            'Low':       quote.get('low',   [np.nan]*len(ts)),
            'Close':     quote.get('close', [np.nan]*len(ts)),
            'Adj Close': adj if adj else quote.get('close', [np.nan]*len(ts)),
            'Volume':    quote.get('volume',[np.nan]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s').tz_localize('UTC').tz_convert(None).normalize())
        df.index.name = 'Date'
        return df
    except Exception:
        return None


def chart_download(tickers, period='1y', interval='1d', threads=8, **_kw):
    """Drop-in replacement for yf.download() — returns the same MultiIndex-column DataFrame.

    Single ticker → flat OHLCV; multiple → top-level columns = ('Open','High','Low','Close','Adj Close','Volume'),
    second-level = tickers, matching yfinance's group_by='column' default."""
    if isinstance(tickers, str):
        tickers = tickers.split()
    tickers = [t for t in tickers if t]
    if not tickers:
        return pd.DataFrame()

    session = requests.Session()
    session.headers.update(_HEADERS)

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        futs = {ex.submit(_fetch_one, t, period, interval, session): t for t in tickers}
        for f in as_completed(futs):
            t = futs[f]
            r = f.result()
            if r is not None and len(r):
                results[t] = r

    if not results:
        return pd.DataFrame()

    if len(tickers) == 1:
        return results.get(tickers[0], pd.DataFrame())

    # Build MultiIndex matching yfinance's (column, ticker) format
    fields = ['Open','High','Low','Close','Adj Close','Volume']
    all_index = sorted(set().union(*[df.index for df in results.values()]))
    pieces = {}
    for f_ in fields:
        col_data = {}
        for t in tickers:
            d = results.get(t)
            if d is None or f_ not in d.columns:
                col_data[t] = pd.Series(np.nan, index=all_index)
            else:
                col_data[t] = d[f_].reindex(all_index)
        pieces[f_] = pd.DataFrame(col_data, index=all_index)
    out = pd.concat(pieces, axis=1)
    out.index.name = 'Date'
    return out


# ─── Install the monkey-patch ───
import yfinance as yf
yf.download = chart_download
# Also patch Ticker.history when imports go that way
_orig_history = yf.Ticker.history
def _history(self, period='1mo', interval='1d', **kw):
    sym = getattr(self, 'ticker', None) or getattr(self, '_ticker', None)
    if not sym:
        return _orig_history(self, period=period, interval=interval, **kw)
    df = chart_download(sym, period=period, interval=interval, threads=1)
    return df if df is not None else pd.DataFrame()
yf.Ticker.history = _history

if __name__ == '__main__':
    # Self-test
    print("── self-test: single ticker AAPL 5d ──")
    d = chart_download('AAPL', period='5d', interval='1d')
    print(f"  rows: {len(d)}, cols: {list(d.columns)}")
    print(d.tail(2).to_string()[:300] if len(d) else "  empty")

    print("\n── self-test: 3 tickers AAPL MSFT NVDA 1mo ──")
    d = chart_download('AAPL MSFT NVDA', period='1mo', interval='1d')
    print(f"  shape: {d.shape}")
    print(f"  columns: {list(d.columns)[:6]}")
    if len(d):
        print(f"  last close MSFT: {d[('Close','MSFT')].iloc[-1] if ('Close','MSFT') in d.columns else 'missing'}")
