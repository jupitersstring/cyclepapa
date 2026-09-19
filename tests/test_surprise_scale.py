"""The earnings_history fallback in _earnings_surprises must rescale Yahoo's
DECIMAL-FRACTION surprisePercent (0.0257) to PERCENT (2.57) so it matches the
primary get_earnings_dates path. Guards the 100x scale bug.
"""
import pandas as pd

from earnings_model import fundamentals as F


class _StubTk:
    """Forces the earnings_history fallback (get_earnings_dates raises) and serves
    surprisePercent as a fraction, the way quoteSummary earningsHistory does."""

    def __init__(self, fractions, dates):
        self._eh = pd.DataFrame({"surprisePercent": fractions},
                                index=pd.to_datetime(dates))

    def get_earnings_dates(self, limit=24):
        raise RuntimeError("force fallback to earnings_history")

    @property
    def earnings_history(self):
        return self._eh


def test_fallback_rescales_fraction_to_percent():
    tk = _StubTk([0.0257, -0.1088, 0.1606],
                 ["2025-03-31", "2025-06-30", "2025-09-30"])
    out = F._earnings_surprises(tk)
    vals = [r["surprise_pct"] for r in out]
    # fractions 0.0257 / -0.1088 / 0.1606 -> percents 2.57 / -10.88 / 16.06
    assert vals == [pytest_approx(2.57), pytest_approx(-10.88), pytest_approx(16.06)]


def pytest_approx(x, tol=1e-6):
    class _A:
        def __eq__(self, other):
            return abs(other - x) < tol
    return _A()
