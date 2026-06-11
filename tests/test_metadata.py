"""Metadata loader tests — the duplicate-key bug class."""
import os, sys, tempfile, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import metadata


COLS = ["ticker", "isin", "name", "group", "catalyst", "nav_quality",
        "discount_override", "aic_sector", "market_cap_gbp_m",
        "catalyst_date", "catalyst_source_url", "notes"]


def _write(rows: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            full = {c: "" for c in COLS}
            full.update(r)
            w.writerow(full)
    return path


def test_load_normal():
    path = _write([
        {"ticker": "AAA.L", "catalyst": "STRATEGIC_REVIEW",
         "nav_quality": "LISTED_CLEAN"},
        {"ticker": "BBB.L", "catalyst": "WIND_DOWN_COMMITTED",
         "nav_quality": "PRIVATE_EQUITY"},
    ])
    metadata._cache = None
    u = metadata.load_universe(path)
    assert set(u) == {"AAA.L", "BBB.L"}
    assert u["AAA.L"].catalyst == "STRATEGIC_REVIEW"


def test_duplicate_ticker_raises():
    """The bug class that previously silently mis-tagged SEIT.L and
    NESF.L: duplicate dict keys, last one wins, no error."""
    path = _write([
        {"ticker": "SEIT.L", "catalyst": "WIND_DOWN_COMMITTED",
         "nav_quality": "RENEWABLES_DCF"},
        {"ticker": "SEIT.L", "catalyst": "STRUCTURAL_DISCOUNT",
         "nav_quality": "RENEWABLES_DCF"},   # silent override before
    ])
    metadata._cache = None
    with pytest.raises(metadata.UniverseError, match="duplicate ticker"):
        metadata.load_universe(path)


def test_unknown_catalyst_raises():
    path = _write([{"ticker": "X.L", "catalyst": "WIBBLE",
                    "nav_quality": "LISTED_CLEAN"}])
    metadata._cache = None
    with pytest.raises(metadata.UniverseError, match="unknown catalyst"):
        metadata.load_universe(path)


def test_unknown_nav_quality_raises():
    path = _write([{"ticker": "X.L", "catalyst": "STRATEGIC_REVIEW",
                    "nav_quality": "WIBBLE"}])
    metadata._cache = None
    with pytest.raises(metadata.UniverseError, match="unknown nav_quality"):
        metadata.load_universe(path)


def test_empty_catalyst_and_nav_allowed():
    path = _write([{"ticker": "X.L"}])
    metadata._cache = None
    u = metadata.load_universe(path)
    assert u["X.L"].catalyst == ""
    assert u["X.L"].nav_quality == ""


def test_loads_real_universe():
    """The production universe.csv must parse clean."""
    metadata._cache = None
    real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "universe.csv")
    u = metadata.load_universe(real)
    assert len(u) > 300
    assert "SEIT.L" in u
    # The catalyst-tag-correction must have stuck
    assert u["SEIT.L"].catalyst == "WIND_DOWN_COMMITTED"
    assert u["NESF.L"].catalyst == "STRATEGIC_REVIEW"
