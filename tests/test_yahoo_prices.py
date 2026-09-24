"""_price_block must use ADJUSTED closes (splits+dividends), matching yfinance
history(auto_adjust=True) — raw closes exclude dividends and understate trailing
returns for dividend payers, biasing dormancy/price-response ranks.
"""
from earnings_model import yahoo


class _StubClient:
    """Serves a canned v8/chart payload where adjclose diverges from close."""

    def __init__(self, ts, close, adjclose):
        self._payload = {"chart": {"result": [{
            "timestamp": ts,
            "indicators": {"quote": [{"close": close}],
                           "adjclose": [{"adjclose": adjclose}]},
        }]}}

    def get_json(self, path, params):
        assert "/v8/finance/chart/" in path
        return self._payload


def _monthly_ts(n):
    import calendar
    from datetime import datetime, timezone
    out = []
    y, m = 2024, 1
    for _ in range(n):
        out.append(int(datetime(y, m, calendar.monthrange(y, m)[1],
                                tzinfo=timezone.utc).timestamp()))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def test_price_block_prefers_adjclose():
    ts = _monthly_ts(14)
    close = [100.0] * 13 + [110.0]        # +10% raw
    adj = [100.0] * 13 + [120.0]          # +20% adjusted (dividends reinvested)
    feats, monthly = yahoo._price_block(_StubClient(ts, close, adj), "TEST")
    assert abs(feats["ret_12m"] - 0.20) < 1e-9        # adjusted, not 0.10
    assert monthly["close"][-1] == 120.0


def test_price_block_falls_back_to_close_when_no_adjclose():
    ts = _monthly_ts(14)
    close = [100.0] * 13 + [110.0]
    stub = _StubClient(ts, close, close)
    stub._payload["chart"]["result"][0]["indicators"].pop("adjclose")
    feats, _ = yahoo._price_block(stub, "TEST")
    assert abs(feats["ret_12m"] - 0.10) < 1e-9
