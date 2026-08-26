"""Audit-round-3 regression tests: surprise merge/ordering and the quarterly grid."""
import math

from earnings_model import yahoo


def test_merge_surprises_unions_not_replaces():
    old = [{"date": f"2024-{m:02d}-01", "surprise_pct": float(m)} for m in range(1, 13)]
    new = [{"date": "2024-12-01", "surprise_pct": 99.0},           # collision: new wins
           {"date": "2025-03-01", "surprise_pct": 13.0}]           # genuinely new
    merged = yahoo.merge_surprises(old, new)
    assert len(merged) == 12                                        # capped, not truncated to 2
    assert merged[-1]["date"] == "2025-03-01"
    assert {e["date"]: e["surprise_pct"] for e in merged}["2024-12-01"] == 99.0
    assert merged == sorted(merged, key=lambda e: e["date"])        # chronological


def test_merge_surprises_handles_none():
    assert yahoo.merge_surprises(None, None) == []
    got = yahoo.merge_surprises(None, [{"date": "2025-01-01", "surprise_pct": 1.0}])
    assert len(got) == 1


def test_quarterly_grid_fills_missing_quarters():
    """A gap in the quarterly axis must become an explicit NaN row so positional
    YoY (vals[-1] vs vals[-5]) keeps comparing the same fiscal quarter."""
    facts = {"timeseries": {"result": [
        {"meta": {"type": ["quarterlyTotalRevenue"]},
         "quarterlyTotalRevenue": [
             {"asOfDate": d, "reportedValue": {"raw": v}}
             # 2024-Q2 missing: 5 observed values across 6 quarters
             for d, v in [("2023-09-30", 10.0), ("2023-12-31", 11.0),
                          ("2024-03-31", 12.0), ("2024-09-30", 14.0),
                          ("2024-12-31", 15.0)]]},
    ]}}

    class _Stub:
        def get_json(self, path, params):
            assert "timeseries" in path
            return facts

    ann, qtr = yahoo._timeseries_blocks(_Stub(), "TEST")
    assert len(qtr["dates"]) == 6                       # grid spans all 6 quarters
    rev = qtr["revenue"]
    assert math.isnan(rev[3])                           # the missing 2024-Q2 is NaN
    assert rev[0] == 10.0 and rev[-1] == 15.0           # observed values in place
