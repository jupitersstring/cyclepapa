"""Regression tests for the merge-preserving statements refresh: appending fresh
Yahoo periods must never truncate deep cached history, and EDGAR annual depth is
left untouched while the quarterly block still grows."""
import math

from earnings_model import yahoo


def _annual(dates, revenue):
    """A minimal annual block in the stored parallel-list shape."""
    n = len(dates)
    return {"dates": list(dates), "revenue": list(revenue),
            "gross": [math.nan] * n, "ebitda": [math.nan] * n,
            "earnings": [math.nan] * n, "eps": [math.nan] * n}


def test_merge_appends_new_period_without_truncating():
    base = _annual(["2018-12-31", "2019-12-31", "2020-12-31"], [100.0, 110.0, 120.0])
    new = _annual(["2020-12-31", "2021-12-31"], [120.0, 130.0])   # 1 overlap, 1 new
    merged = yahoo.merge_statement_blocks(base, new)
    assert merged["dates"] == ["2018-12-31", "2019-12-31", "2020-12-31", "2021-12-31"]
    assert merged["revenue"] == [100.0, 110.0, 120.0, 130.0]      # deep history kept


def test_merge_new_wins_on_restatement():
    base = _annual(["2020-12-31"], [120.0])
    new = _annual(["2020-12-31"], [125.0])                        # restated upward
    merged = yahoo.merge_statement_blocks(base, new)
    assert merged["revenue"] == [125.0]


def test_merge_keeps_base_where_new_missing_that_item():
    base = _annual(["2019-12-31", "2020-12-31"], [110.0, 120.0])
    # new carries the dates but NaN revenue (item absent this fetch)
    new = _annual(["2020-12-31", "2021-12-31"], [math.nan, math.nan])
    merged = yahoo.merge_statement_blocks(base, new)
    # 2020 base revenue survives (new had NaN); 2021 has no revenue anywhere
    assert merged["revenue"][merged["dates"].index("2020-12-31")] == 120.0


def test_merge_quarterly_regrids_and_fills_gaps():
    base = {"dates": ["2024-03-31", "2024-06-30"], "revenue": [10.0, 11.0],
            "gross": [math.nan] * 2, "ebitda": [math.nan] * 2,
            "earnings": [math.nan] * 2, "eps": [math.nan] * 2}
    # skips 2024-09 (gap), adds 2024-12
    new = {"dates": ["2024-12-31"], "revenue": [13.0], "gross": [math.nan],
           "ebitda": [math.nan], "earnings": [math.nan], "eps": [math.nan]}
    merged = yahoo.merge_statement_blocks(base, new, quarterly=True)
    assert merged["dates"] == ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]
    assert merged["revenue"][0] == 10.0 and merged["revenue"][3] == 13.0
    assert math.isnan(merged["revenue"][2])                       # gap -> explicit NaN row


# --------------------------------------------------------------------------- #
# refresh_statements: source-aware annual handling + preservation of market blocks
# --------------------------------------------------------------------------- #
class _Client:
    """Serves one new annual year (2025) and one new quarter (2025-03)."""

    def get_json(self, path, params, retries=3):
        assert "timeseries" in path
        def pt(d, v):
            return {"asOfDate": d, "reportedValue": {"raw": v}}
        return {"timeseries": {"result": [
            {"meta": {"type": ["annualTotalRevenue"]},
             "annualTotalRevenue": [pt("2024-12-31", 120.0), pt("2025-12-31", 130.0)]},
            {"meta": {"type": ["quarterlyTotalRevenue"]},
             "quarterlyTotalRevenue": [pt("2024-12-31", 30.0), pt("2025-03-31", 33.0)]},
        ]}}


def _base_edgar():
    return {"symbol": "DEEP", "statement_source": "edgar-annual",
            "annual": _annual(["2012-12-31", "2013-12-31", "2024-12-31"],
                              [50.0, 55.0, 120.0]),          # 13y EDGAR depth
            "quarterly": {"dates": ["2024-12-31"], "revenue": [30.0], "gross": [math.nan],
                          "ebitda": [math.nan], "earnings": [math.nan], "eps": [math.nan]},
            "valuation": {"marketCap": 9e9, "trailingPE": 20.0},
            "prices": {"monthly": {"dates": ["2026-08-01"], "close": [50.0]}},
            "surprises": [{"date": "2025-03-01", "surprise_pct": 4.0}],
            "fetch_ok": True}


def test_refresh_statements_preserves_edgar_annual_but_grows_quarterly():
    out = yahoo.refresh_statements("DEEP", _Client(), _base_edgar())
    assert out is not None
    # EDGAR annual is authoritative: untouched, so NO 2025 year injected by Yahoo
    assert out["annual"]["dates"] == ["2012-12-31", "2013-12-31", "2024-12-31"]
    # quarterly grew with the freshly reported quarter
    assert out["quarterly"]["dates"][-1] == "2025-03-31"
    assert out["quarterly"]["revenue"][-1] == 33.0
    # market blocks are refresh_market's job — carried through verbatim
    assert out["valuation"]["marketCap"] == 9e9
    assert out["prices"]["monthly"]["dates"] == ["2026-08-01"]
    assert out["surprises"] == [{"date": "2025-03-01", "surprise_pct": 4.0}]
    assert out["statements_refreshed"] == out["asof"]


def test_refresh_statements_merges_annual_for_yahoo_names():
    base = _base_edgar()
    base["statement_source"] = "yahoo-urllib"          # not EDGAR: annual is Yahoo's
    out = yahoo.refresh_statements("DEEP", _Client(), base)
    assert out["annual"]["dates"][-1] == "2025-12-31"  # new fiscal year appended
    assert out["annual"]["revenue"][-1] == 130.0
    assert out["annual"]["dates"][0] == "2012-12-31"   # deep history still intact


def test_refresh_statements_none_when_no_data():
    class _Empty:
        def get_json(self, path, params, retries=3):
            raise RuntimeError("network down")
    assert yahoo.refresh_statements("X", _Empty(), _base_edgar()) is None
