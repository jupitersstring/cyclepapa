"""Buyback run-rate: the anti-one-off guard is the whole point."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timezone, timedelta
import buyback_analysis as bb


def _mk(epic, dates, shares=100000, isc=100000000, tmp=None):
    """Write a fake per-EPIC investegate file + prime detail cache."""
    items = []
    for i, d in enumerate(dates):
        url = f"https://x/{epic}/own-shares/{i}"
        items.append({"date": d, "category": "buyback",
                      "title": "Transaction in Own Shares",
                      "raw_slug": "transaction-in-own-shares", "url": url})
        cp = bb._cache_path(url)
        cp.write_text(json.dumps({"shares": shares, "isc": isc, "date": d}))
    (bb.INV_DIR / f"{epic}.json").write_text(json.dumps(items))


def test_single_filing_is_one_off_not_annualised(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "INV_DIR", tmp_path)
    monkeypatch.setattr(bb, "BUYBACK_DIR", tmp_path / "bb")
    today = datetime.now(timezone.utc)
    _mk("ONE", [(today - timedelta(days=5)).strftime("%Y-%m-%d")])
    r = bb.analyse_ticker("ONE")
    assert r["one_off"] is True
    assert r["buyback_yield_annualised"] is None   # never annualise a one-off


def test_two_filings_close_together_is_one_off(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "INV_DIR", tmp_path)
    monkeypatch.setattr(bb, "BUYBACK_DIR", tmp_path / "bb")
    today = datetime.now(timezone.utc)
    _mk("TWO", [(today - timedelta(days=d)).strftime("%Y-%m-%d")
                for d in (3, 6)])
    r = bb.analyse_ticker("TWO")
    assert r["one_off"] is True         # <4 filings, <60d span, <3 months
    assert r["buyback_yield_annualised"] is None


def test_sustained_programme_is_annualised(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "INV_DIR", tmp_path)
    monkeypatch.setattr(bb, "BUYBACK_DIR", tmp_path / "bb")
    today = datetime.now(timezone.utc)
    # 6 filings across ~150 days, 5 distinct months
    dates = [(today - timedelta(days=d)).strftime("%Y-%m-%d")
             for d in (10, 40, 70, 100, 130, 150)]
    _mk("SUS", dates, shares=1_000_000, isc=100_000_000)
    r = bb.analyse_ticker("SUS")
    assert r["sustained"] is True
    assert r["buyback_yield_annualised"] is not None
    assert 0 < r["buyback_yield_annualised"] <= bb.MAX_ANNUAL_YIELD


def test_annual_yield_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "INV_DIR", tmp_path)
    monkeypatch.setattr(bb, "BUYBACK_DIR", tmp_path / "bb")
    today = datetime.now(timezone.utc)
    # Huge retirement in a short-ish window -> must cap
    dates = [(today - timedelta(days=d)).strftime("%Y-%m-%d")
             for d in (5, 25, 45, 65)]
    _mk("CAP", dates, shares=10_000_000, isc=100_000_000)
    r = bb.analyse_ticker("CAP")
    if r["buyback_yield_annualised"] is not None:
        assert r["buyback_yield_annualised"] <= bb.MAX_ANNUAL_YIELD


def test_nav_accretion_formula():
    # 8%/yr buyback at 30% discount: 0.08*0.30/(1-0.08) = 2.6%
    acc = bb.nav_accretion(0.08, 0.30)
    assert abs(acc - 0.0261) < 0.001


def test_nav_accretion_none_for_one_off():
    assert bb.nav_accretion(None, 0.30) is None
    assert bb.nav_accretion(0.08, None) is None
