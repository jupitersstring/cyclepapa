"""SessionManager must auto-route to the urllib Yahoo client when curl_cffi is
broken by the proxy, and use the curl_cffi path when it is healthy — so
build_fundamentals/step_fetch/fetch_new keep working without call-site changes.
"""
from earnings_model import fundamentals as F, yahoo


def test_routes_to_urllib_when_curl_broken(monkeypatch):
    F._CURL_HEALTHY = None
    monkeypatch.setattr(F, "curl_cffi_healthy", lambda *a, **k: False)
    monkeypatch.setattr(F, "make_session", lambda warm=True: object())
    seen = {}

    class FakeClient:
        def warm(self):
            seen["warm"] = seen.get("warm", 0) + 1

    def fake_fetch(sym, client, with_surprises=False):
        seen["sym"], seen["ws"] = sym, with_surprises
        return {"fetch_ok": True, "symbol": sym, "statement_source": "yahoo-urllib"}

    monkeypatch.setattr(yahoo, "YahooClient", FakeClient)
    monkeypatch.setattr(yahoo, "fetch_raw", fake_fetch)

    mgr = F.SessionManager()
    assert mgr._yahoo is not None                     # chose urllib
    raw = mgr.fetch("AAPL", with_surprises=True, max_retries=1)   # max_retries filtered out
    assert raw["fetch_ok"] and seen["sym"] == "AAPL" and seen["ws"] is True
    mgr.refresh()
    assert seen["warm"] == 1                           # refresh re-warms the urllib client


def test_uses_curl_when_healthy(monkeypatch):
    F._CURL_HEALTHY = None
    monkeypatch.setattr(F, "curl_cffi_healthy", lambda *a, **k: True)
    monkeypatch.setattr(F, "make_session", lambda warm=True: object())
    monkeypatch.setattr(F, "fetch_raw",
                        lambda sym, session=None, **kw: {"fetch_ok": True, "used": "curl"})
    mgr = F.SessionManager()
    assert mgr._yahoo is None                          # chose curl_cffi
    assert mgr.fetch("AAPL")["used"] == "curl"


def test_explicit_urllib_transport(monkeypatch):
    F._CURL_HEALTHY = None
    monkeypatch.setattr(F, "make_session", lambda warm=True: object())
    monkeypatch.setattr(yahoo, "YahooClient", lambda: object())
    mgr = F.SessionManager(transport="urllib")         # forced, no probe
    assert mgr._yahoo is not None
