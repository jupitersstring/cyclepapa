"""Unit tests for the data-quality guardrails and the metric/screen fixes.

Runnable two ways:
    pytest tests/test_data_quality.py
    python tests/test_data_quality.py     # plain asserts, no pytest needed

These cover the bugs that actually reached the shortlists this session: duplicate
Yahoo payloads (ONT/MEG), split-artifact returns, the surprise %-sum scale blowup,
the missing-history false inflection, and the back-fill ticker-exclusion regex.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, metrics, quality


def test_payload_fingerprint_detects_shared_statements():
    a = {"revenue": [100.0, 110.0, 121.0], "ebitda": [10.0, 12.0, 14.0], "earnings": [5, 6, 7]}
    b = dict(a)                                   # same numbers, different ticker
    c = {"revenue": [200.0, 250.0, 300.0], "ebitda": [20.0, 25.0, 30.0], "earnings": [9, 9, 9]}
    assert metrics._payload_fp(a) == metrics._payload_fp(b)
    assert metrics._payload_fp(a) != metrics._payload_fp(c)


def test_payload_fingerprint_none_when_no_data():
    assert metrics._payload_fp({"revenue": []}) is None
    assert metrics._payload_fp({"revenue": [float("nan")]}) is None    # not enough real points


def test_flag_duplicate_payloads_keeps_largest_cap():
    df = pd.DataFrame({
        "symbol": ["MEG", "ONT", "AAPL"],
        "payload_fp": ["dup", "dup", "unique"],
        "marketCap": [800e6, 578e6, 3e12],
    })
    out = quality.flag_duplicate_payloads(df)
    # The larger-cap of the shared-fingerprint pair is kept; the other is flagged.
    assert out.set_index("symbol").loc["MEG", "dup_payload"] == False  # noqa: E712
    assert out.set_index("symbol").loc["ONT", "dup_payload"] == True   # noqa: E712
    assert out.set_index("symbol").loc["AAPL", "dup_payload"] == False  # noqa: E712


def test_quarantine_returns_nulls_split_artifacts():
    df = pd.DataFrame({"ret_12m": [0.2, 104.0, -0.5], "ret_24m": [-0.99, 0.1, 50.0]})
    out = quality.quarantine_returns(df)
    assert math.isnan(out["ret_12m"].iloc[1])        # 10,400% -> quarantined
    assert math.isnan(out["ret_24m"].iloc[2])        # 5,000% -> quarantined
    assert abs(out["ret_12m"].iloc[0] - 0.2) < 1e-9  # sane values untouched
    assert out.attrs["returns_quarantined"] == 2


def test_surprise_robust_is_scale_stable():
    # One monster beat off a ~$0 estimate (+800%) plus normal beats.
    raw = {"surprises": [{"surprise_pct": x} for x in [800.0, 5.0, 4.0, 6.0]]}
    out = metrics.surprise_block(raw)
    assert out["surprise_cum8"] > 700                       # raw sum is dominated by the 800
    assert abs(out["surprise_robust"]) <= config.SURPRISE_WINSOR  # winsorized -> bounded
    assert out["surprise_robust"] < 20                     # not dragged up by the outlier


def test_apply_quality_flags_combines_both():
    df = pd.DataFrame({
        "symbol": ["A", "B"], "payload_fp": ["x", "x"],
        "marketCap": [10.0, 5.0], "ret_12m": [200.0, 0.1],
    })
    out = quality.apply_quality_flags(df, verbose=False)
    assert out["dup_payload"].sum() == 1
    assert math.isnan(out["ret_12m"].iloc[0])


def test_nonop_regex_keeps_real_tickers_drops_junk():
    """The back-fill exclusion filter must not false-exclude real names."""
    NONOP = re.compile(r"(-[A-Z]{1,3}$|^[A-Z]{4}[WUPNORMQE]$)")
    for keep in ["AMZN", "PLTR", "TTWO", "CRM", "IBM", "QCOM", "MU", "UBER", "LOW", "RIVN"]:
        assert not NONOP.search(keep), f"{keep} wrongly excluded"
    for drop in ["LUNRW", "NOVTU", "POWWP", "AGNCN", "IVR-PC", "BRK-A"]:
        assert NONOP.search(drop), f"{drop} should be excluded"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"[ok] {fn.__name__}")
    print(f"ALL {len(fns)} DATA-QUALITY TESTS PASSED")


if __name__ == "__main__":
    _run_all()
