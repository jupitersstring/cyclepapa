"""Regression tests for the rebuild data-loss bug: a snapshot rebuild must never
re-fetch, and ANY re-fetch must merge into an enriched cached raw rather than
replace it (EDGAR deep history, merged quarters, EPS-surprise history)."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from earnings_model import config, fundamentals as F

NaN = float("nan")
STALE = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()   # > 30d TTL
NOW = datetime.now(timezone.utc).isoformat()


def _block(dates, revenue):
    n = len(dates)
    return {"dates": dates, "revenue": revenue, "gross": [NaN] * n, "ebitda": [NaN] * n,
            "earnings": [NaN] * n, "eps": [NaN] * n}


def _enriched():
    """What the overlay jobs leave in the cache: EDGAR 18y annual, merged quarters,
    an 8-quarter surprise history, provenance stamps."""
    return {"symbol": "DEEP", "fetch_ok": True, "asof": STALE,
            "statement_source": "edgar-annual", "cik": 123,
            "statements_refreshed": "2026-08-21T00:00:00+00:00",
            "annual": _block([f"{y}-12-31" for y in range(2008, 2026)],
                             [100.0 + i for i in range(18)]),
            "quarterly": _block(["2025-09-30", "2025-12-31", "2026-03-31"], [30.0, 31.0, 32.0]),
            "surprises": [{"date": f"{y}-{m:02d}-01", "surprise_pct": 5.0}
                          for y in (2024, 2025) for m in (1, 4, 7, 10)],
            "valuation": {"marketCap": 1e10}, "prices": {"monthly": {"dates": [], "close": []}}}


def _thin():
    """A plain Yahoo re-fetch: 4y annual, a NEW quarter, no surprise history."""
    return {"symbol": "DEEP", "fetch_ok": True, "asof": NOW,
            "annual": _block([f"{y}-12-31" for y in range(2022, 2026)], [114.0, 115.0, 116.0, 117.0]),
            "quarterly": _block(["2025-12-31", "2026-03-31", "2026-06-30"], [31.0, 32.0, 33.0]),
            "surprises": [], "valuation": {"marketCap": 1.1e10},
            "prices": {"monthly": {"dates": [], "close": []}}}


class _NoFetch:
    refreshes = 0
    def __init__(self, *a, **k): pass
    def fetch(self, sym, with_surprises=False):
        raise AssertionError(f"pure-cache build must not fetch {sym}")


class _ThinFetch:
    refreshes = 0
    def __init__(self, *a, **k): pass
    def fetch(self, sym, with_surprises=False):
        return _thin()


UNI = pd.DataFrame({"symbol": ["DEEP"], "name": ["Deep Co"], "region": ["US"],
                    "industry": ["Software"]})


def test_preserve_enrichment_is_lossless():
    out = F.preserve_enrichment(_enriched(), _thin())
    assert len(out["annual"]["dates"]) == 18                   # EDGAR depth kept, not 4y
    assert out["statement_source"] == "edgar-annual" and out["cik"] == 123
    assert out["quarterly"]["dates"][-1] == "2026-06-30"        # new quarter appended
    assert out["quarterly"]["dates"][0] == "2025-09-30"         # old quarter kept
    assert len(out["surprises"]) == 8                           # history not wiped
    assert out["valuation"]["marketCap"] == 1.1e10              # fresh market data used
    assert out["statements_refreshed"] == "2026-08-21T00:00:00+00:00"


def test_pure_cache_build_never_fetches_a_stale_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.setattr(F, "SessionManager", _NoFetch)
    F.save_raw("DEEP", _enriched())
    F.build_fundamentals(UNI, symbols=["DEEP"], ttl_days=None, fail_ttl_days=None,
                         verbose=False)                         # raises if it fetches
    kept = F.load_raw("DEEP", ttl_days=None, fail_ttl_days=None)
    assert len(kept["annual"]["dates"]) == 18 and len(kept["surprises"]) == 8


def test_stale_refetch_merges_instead_of_downgrading(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.setattr(F, "SessionManager", _ThinFetch)
    F.save_raw("DEEP", _enriched())
    F.build_fundamentals(UNI, symbols=["DEEP"], verbose=False)   # default 30d TTL -> re-fetch
    saved = F.load_raw("DEEP", ttl_days=None, fail_ttl_days=None)
    assert saved["statement_source"] == "edgar-annual"
    assert len(saved["annual"]["dates"]) == 18                   # was clobbered to 4 before
    assert len(saved["surprises"]) == 8                          # was wiped to 0 before
    assert saved["quarterly"]["dates"][-1] == "2026-06-30"


def test_snapshot_rebuild_requests_pure_cache(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "snapshot_mod", Path(__file__).resolve().parent.parent / "scripts" / "snapshot.py")
    snap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(snap)
    seen = {}
    monkeypatch.setattr(snap.F, "build_fundamentals",
                        lambda *a, **k: seen.update(k) or pd.DataFrame({"fetch_ok": [True]}))
    monkeypatch.setattr(snap.F, "save_fundamentals", lambda df: None)
    monkeypatch.setattr(snap.S, "reinject_into_cache", lambda: 0)
    monkeypatch.setattr(snap, "_cached_ok_symbols", lambda: ["DEEP"])
    monkeypatch.setattr(snap.pd, "read_parquet", lambda p: UNI)
    monkeypatch.setattr(snap.pipeline, "step_analyze", lambda: None)
    snap.rebuild()
    assert "ttl_days" in seen and seen["ttl_days"] is None
    assert "fail_ttl_days" in seen and seen["fail_ttl_days"] is None
