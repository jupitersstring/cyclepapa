"""Tests for the FMP balance-sheet/quality overlay: attach is additive + a no-op
when absent, derived flags are correct, and the quality-value screen gates work."""
import pandas as pd

from earnings_model import fmp, screens


def _overlay(tmp_path):
    ov = pd.DataFrame({
        "symbol": ["A", "B", "C"],
        "fmp_net_debt_to_ebitda": [-1.5, 2.0, 8.0],     # net cash / normal / over-levered
        "fmp_fcf_yield": [0.08, 0.05, -0.02],
        "fmp_earnings_yield": [0.07, 0.04, -0.01],
        "fmp_roic": [0.25, 0.12, 0.03],
        "fmp_income_quality": [1.2, 0.9, 0.3],          # C: accrual-inflated
        "fmp_current_ratio": [2.5, 1.4, 0.6],
    })
    p = tmp_path / "fmp_metrics.parquet"
    ov.to_parquet(p, index=False)
    return p


def test_attach_is_noop_when_absent(tmp_path):
    df = pd.DataFrame({"symbol": ["A", "B"], "x": [1, 2]})
    out = fmp.attach(df, path=tmp_path / "does_not_exist.parquet")
    assert list(out.columns) == ["symbol", "x"]           # unchanged
    assert len(out) == 2


def test_attach_joins_and_derives_flags(tmp_path):
    p = _overlay(tmp_path)
    df = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "revenue_growth": [0.1, 0.2, 0.3, 0.4]})
    out = fmp.attach(df, path=p).set_index("symbol")
    assert len(out) == 4                                  # left join keeps D (no FMP row)
    assert out.loc["D", "fmp_roic"] != out.loc["D", "fmp_roic"]   # NaN for unmatched
    # derived flags
    assert bool(out.loc["A", "fmp_net_cash"]) is True     # neg leverage + positive earnings yield
    assert bool(out.loc["B", "fmp_net_cash"]) is False
    assert bool(out.loc["C", "fmp_over_levered"]) is True
    assert bool(out.loc["C", "fmp_low_income_quality"]) is True   # income quality 0.3 < 0.5
    assert bool(out.loc["A", "fmp_low_income_quality"]) is False


def test_attach_no_duplicate_columns_on_reattach(tmp_path):
    p = _overlay(tmp_path)
    df = pd.DataFrame({"symbol": ["A"], "revenue_growth": [0.1]})
    once = fmp.attach(df, path=p)
    twice = fmp.attach(once, path=p)                      # must not double the fmp_ cols
    assert list(twice.columns).count("fmp_roic") == 1


def test_quality_value_screen_gates(tmp_path):
    p = _overlay(tmp_path)
    # Build a frame that passes eligible(): operating, sane multiple, has industry.
    base = pd.DataFrame({
        "symbol": ["A", "B", "C"],
        "name": ["Aco", "Bco", "Cco"],
        "region": ["US", "US", "US"],
        "industry": ["Software", "Software", "Software"],
        "size_bucket": ["Large Cap"] * 3,
        "revenue_growth": [0.15, 0.10, 0.20],
        "revenue_n_periods": [5, 5, 5],
        "forwardPE": [20.0, 18.0, 12.0],                  # sane multiple
    })
    df = fmp.attach(base, path=p)
    res = screens.quality_value(df, top=None)
    syms = set(res["symbol"])
    # A (net cash, FCF+, ROIC 25%, iq 1.2) passes; C fails gates (FCF yield<0,
    # over-levered, income quality 0.3); B passes (modest but clean).
    assert "A" in syms and "C" not in syms
    assert "fmp_fcf_yield" in res.columns
    # Ranking direction: A (ROIC 25%, FCFy 8%, net cash) must outrank B (12%, 5%).
    order = list(res["symbol"])
    assert order.index("A") < order.index("B")


def test_quality_value_empty_without_overlay():
    base = pd.DataFrame({
        "symbol": ["A"], "name": ["Aco"], "region": ["US"], "industry": ["Software"],
        "size_bucket": ["Large Cap"], "revenue_growth": [0.15],
        "revenue_n_periods": [5], "forwardPE": [20.0],
    })
    res = screens.quality_value(base, top=None)            # no fmp_ columns
    assert len(res) == 0
