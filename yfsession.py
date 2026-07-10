"""
Shared yfinance HTTP session.

yfinance defaults to curl_cffi, whose bundled BoringSSL can break against the
agent proxy's CA interception ("TLS connect error / invalid library"). A plain
requests.Session pointed at the proxy CA bundle works reliably, so every fetcher
passes session=SESSION to yf.download / yf.Ticker.
"""
import os

import requests

_CA = (os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
       or "/root/.ccr/ca-bundle.crt")


def make_session() -> requests.Session:
    s = requests.Session()
    if os.path.exists(_CA):
        s.verify = _CA
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return s


SESSION = make_session()
