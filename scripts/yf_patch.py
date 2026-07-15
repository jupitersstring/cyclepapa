"""Shared yfinance session helper. Bypasses the curl_cffi TLS bug in restricted
network environments by using a plain requests.Session with the agent-proxy CA
bundle. Import this BEFORE using yfinance and use the global session via
`yf_session()` or pass it explicitly to yf.Ticker / yf.download.
"""
import os
import requests
import yfinance as yf

_CA_BUNDLE = '/root/.ccr/ca-bundle.crt' if os.path.exists('/root/.ccr/ca-bundle.crt') else True

_session = None

def yf_session():
    global _session
    if _session is None:
        s = requests.Session()
        s.verify = _CA_BUNDLE
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        })
        _session = s
    return _session

# Monkey-patch yfinance to default to requests session unless caller overrides
_orig_ticker_init = yf.Ticker.__init__
def _patched_ticker_init(self, ticker, session=None, **kwargs):
    if session is None: session = yf_session()
    return _orig_ticker_init(self, ticker, session=session, **kwargs)
yf.Ticker.__init__ = _patched_ticker_init

# Patch yf.download similarly
_orig_download = yf.download
def _patched_download(*args, **kwargs):
    if 'session' not in kwargs or kwargs.get('session') is None:
        kwargs['session'] = yf_session()
    return _orig_download(*args, **kwargs)
yf.download = _patched_download
