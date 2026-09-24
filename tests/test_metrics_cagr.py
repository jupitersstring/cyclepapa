"""cagr() must annualize over the CALENDAR span between the first and last present
positive value, not the count of present points — so interior gaps (common in
EDGAR's reconstructed EBITDA) don't overstate per-year growth.
"""
import math

from earnings_model.metrics import cagr


def test_cagr_uses_calendar_span_over_gaps():
    # 100 at position 0, gap, gap, 200 at position 3 -> span 3 -> (2)^(1/3)-1
    g = cagr([100.0, float("nan"), float("nan"), 200.0])
    assert abs(g - (2.0 ** (1.0 / 3.0) - 1.0)) < 1e-9


def test_cagr_contiguous_unchanged():
    assert abs(cagr([100.0, 200.0]) - 1.0) < 1e-9               # one period, doubling
    assert abs(cagr([100.0, 110.0, 121.0]) - 0.10) < 1e-9       # two periods, 10%/yr


def test_cagr_nonpositive_in_window_is_nan():
    assert math.isnan(cagr([100.0, -5.0, 200.0]))
    assert math.isnan(cagr([float("nan")]))
