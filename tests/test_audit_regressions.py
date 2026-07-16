"""Regression tests for the silent-drop / coverage-reduction audit
(2026-07-16). Each test pins a bug class found in the audit:

  1. Catalyst auto-promotion demoting committed wind-downs
  2. price_store returning None when a stale parquet exists
  3. TR-1 detail records missing the epic/date join keys
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest

import params
import screen_v3
import price_store
import investegate_scraper as inv


# ----- 1. Promotion-only catalyst rewriting -------------------------

def test_promotion_never_demotes_committed_wind_down():
    """WIND_DOWN_COMMITTED (0.80) must not be rewritten to
    WIND_DOWN_LIKELY (0.60) — the RMII bug."""
    assert not screen_v3.promotion_increases_probability(
        "WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY")


def test_promotion_never_demotes_roc():
    """RETURN_OF_CAPITAL_LIVE (0.70) -> WIND_DOWN_LIKELY (0.60) was
    hitting four names per run."""
    assert not screen_v3.promotion_increases_probability(
        "RETURN_OF_CAPITAL_LIVE", "WIND_DOWN_LIKELY")


def test_promotion_from_structural_allowed():
    assert screen_v3.promotion_increases_probability(
        "STRUCTURAL_DISCOUNT", "WIND_DOWN_LIKELY")
    assert screen_v3.promotion_increases_probability(
        "STRUCTURAL_DISCOUNT", "DCM_ACTIVE")


def test_promotion_from_empty_allowed():
    assert screen_v3.promotion_increases_probability(
        "", "STRATEGIC_REVIEW")
    assert screen_v3.promotion_increases_probability(
        None, "WIND_DOWN_LIKELY")


def test_promotion_from_activist_target_to_likely_allowed():
    """ACTIVIST_TARGET (0.45) -> WIND_DOWN_LIKELY (0.60) is a genuine
    upgrade and should be allowed."""
    assert screen_v3.promotion_increases_probability(
        "ACTIVIST_TARGET", "WIND_DOWN_LIKELY")


def test_promotion_equal_probability_rejected():
    """Sideways moves are noise — require strictly higher."""
    assert not screen_v3.promotion_increases_probability(
        "WIND_DOWN_LIKELY", "WIND_DOWN_LIKELY")


# ----- 2. Stale-parquet fallback ------------------------------------

def test_price_store_serves_stale_cache_on_download_failure(
        tmp_path, monkeypatch):
    """A failed refresh must fall back to the on-disk parquet rather
    than dropping the name (the '255 of 653' coverage collapse)."""
    monkeypatch.setattr(price_store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({
        "Open": [1.0], "High": [1.1], "Low": [0.9],
        "Close": [1.0], "Volume": [100.0],
    }, index=pd.to_datetime(["2026-01-05"]))
    df.to_parquet(tmp_path / "STALE.L.parquet")
    # Make the cache look ancient and the network dead
    old = pd.Timestamp("2020-01-01").timestamp()
    os.utime(tmp_path / "STALE.L.parquet", (old, old))
    monkeypatch.setattr(price_store, "_download", lambda *a, **k: None)
    out = price_store.get("STALE.L", ttl_hours=24)
    assert out is not None and len(out) == 1, \
        "stale parquet must be served when refresh fails"


def test_price_store_returns_none_when_no_cache_and_no_network(
        tmp_path, monkeypatch):
    monkeypatch.setattr(price_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(price_store, "_download", lambda *a, **k: None)
    assert price_store.get("NOPE.L") is None


# ----- 3. TR-1 detail join keys -------------------------------------

def test_tr1_detail_records_carry_epic_and_date(tmp_path, monkeypatch):
    """New TR-1 detail records must include url / epic / date so the
    campaign tracker can join them after the parent announcement ages
    off the per-EPIC page."""
    body = (
        "<html><body>"
        "Resulting situation: % of voting rights: 6.12% "
        "Previous notification: % of voting rights: 4.95% "
        "Name of the shareholder: Saba Capital Management LP "
        "</body></html>"
    )

    class FakeResp:
        def __init__(self, b): self._b = b
        def read(self): return self._b.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(inv, "TR1_DETAIL_DIR", tmp_path)
    monkeypatch.setattr(inv.urllib.request, "urlopen",
                        lambda req, timeout=20: FakeResp(body))
    url = ("https://www.investegate.co.uk/announcement/rns/"
           "some-trust--abc/holding-s-in-company/1234567")
    det = inv.fetch_tr1_detail(url, use_cache=True,
                               announce_date="2026-07-01")
    assert det["epic"] == "ABC"
    assert det["date"] == "2026-07-01"
    assert det["url"] == url
    # And it round-trips through the cache
    det2 = inv.fetch_tr1_detail(url, use_cache=True)
    assert det2["epic"] == "ABC" and det2["date"] == "2026-07-01"


def test_tr1_detail_backfills_date_on_legacy_records(tmp_path, monkeypatch):
    """Legacy cache files (pre-stamping) get the date backfilled when
    the enrichment loop revisits them with announce_date."""
    monkeypatch.setattr(inv, "TR1_DETAIL_DIR", tmp_path)
    url = "https://example.com/tr1/999"
    cp = inv._tr1_cache_path(url)
    with open(cp, "w") as f:
        json.dump({"holder": "X", "new_pct": 5.0, "prev_pct": 4.0,
                   "delta_pp": 1.0, "direction": "buy",
                   "is_activist": False}, f)
    det = inv.fetch_tr1_detail(url, use_cache=True,
                               announce_date="2026-06-30")
    assert det.get("date") == "2026-06-30"
    with open(cp) as f:
        on_disk = json.load(f)
    assert on_disk.get("date") == "2026-06-30"
