"""Regression tests for Form 144 parsing, buyback verification, and
the SQLite state store."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from form144_scan import parse_144_xml, summarize, score_144
from buyback_verify import classify_buyback
import state


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(
            f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


# ---------------------------------------------------------------------------
# Form 144 XML parsing (real NVDA fixture structure)
# ---------------------------------------------------------------------------

NVDA_144_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/ownership"
 xmlns:com="http://www.sec.gov/edgar/common">
  <formData>
    <issuerInfo>
      <issuerCik>0001045810</issuerCik>
      <issuerName>NVIDIA CORP</issuerName>
      <nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Neal Stephen C</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
      <relationshipsToIssuer>
        <relationshipToIssuer>Director</relationshipToIssuer>
      </relationshipsToIssuer>
    </issuerInfo>
    <securitiesInformation>
      <noOfUnitsSold>15500</noOfUnitsSold>
      <aggregateMarketValue>3343863.05</aggregateMarketValue>
      <approxSaleDate>06/03/2026</approxSaleDate>
    </securitiesInformation>
  </formData>
</edgarSubmission>"""


def test_parse_144_real_schema():
    out = parse_144_xml(NVDA_144_FIXTURE)
    assert_eq(out.get("shares"), 15500, "shares")
    assert_eq(out.get("value_usd"), 3343863.05, "value")
    assert_eq(out.get("person"), "Neal Stephen C", "person")
    assert_eq(out.get("relationship"), "Director", "relationship")
    assert_eq(out.get("approx_sale_date"), "06/03/2026", "sale date")


def test_parse_144_malformed_returns_empty():
    out = parse_144_xml("<not-xml")
    assert_eq(out, {}, "malformed XML")


# ---------------------------------------------------------------------------
# Form 144 scoring
# ---------------------------------------------------------------------------

def test_144_acceleration_needs_baseline():
    # Two filings in a quiet year must NOT read as acceleration
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc)
              - timedelta(days=10)).strftime("%Y-%m-%d")
    s = summarize([{"filing_date": recent, "value_usd": 1e6},
                   {"filing_date": recent, "value_usd": 1e6}])
    assert_eq(s["accel_ratio"], None, "accel needs n365 >= 4")


def test_144_materiality_vs_mcap():
    summary = {"n_90d": 4, "value_90d_usd": 50_000_000,
               "accel_ratio": 3.0, "n_30d": 2, "n_180d": 5, "n_365d": 6,
               "value_180d_usd": 60_000_000}
    score, reasons = score_144(summary, mcap=1_000_000_000)  # 5% of mcap
    assert_true(score <= -12, f"material acceleration scores <= -12, got {score}")
    assert_true(score >= -20, "capped at -20")


def test_144_no_signal_when_quiet():
    summary = {"n_90d": 0, "value_90d_usd": 0, "accel_ratio": None,
               "n_30d": 0, "n_180d": 0, "n_365d": 1, "value_180d_usd": 0}
    score, reasons = score_144(summary, mcap=1_000_000_000)
    assert_eq(score, 0.0, "quiet ticker scores 0")


# ---------------------------------------------------------------------------
# Buyback classification (split-adjusted)
# ---------------------------------------------------------------------------

def test_buyback_executing():
    chg = {"change_pct": -5.0, "large_residual": False}
    status, pts = classify_buyback(chg, has_auth=True)
    assert_eq(status, "EXECUTING")
    assert_true(pts > 0)


def test_buyback_diluting():
    chg = {"change_pct": 4.0, "large_residual": False}
    status, pts = classify_buyback(chg, has_auth=True)
    assert_eq(status, "DILUTING")
    assert_true(pts < 0)


def test_buyback_split_anomaly_neutral():
    # TPL-style +197% split artifact must score 0, not -10
    chg = {"change_pct": 197.0, "large_residual": True}
    status, pts = classify_buyback(chg, has_auth=True)
    assert_eq(status, "ANOMALY_REVIEW")
    assert_eq(pts, 0)


def test_buyback_unknown():
    status, pts = classify_buyback(None, has_auth=True)
    assert_eq(status, "UNKNOWN")
    assert_eq(pts, 0)


# ---------------------------------------------------------------------------
# SQLite state store
# ---------------------------------------------------------------------------

def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = state.connect(db)
        with conn:
            state.record_filing(conn, "TEST", "0001-26-000001",
                                "10-Q", "2026-01-15")
            state.record_filing(conn, "TEST", "0001-26-000002",
                                "10-K", "2026-03-01")
            state.insert_events(conn, "TEST", [
                {"accession": "0001-26-000001", "filing_date": "2026-01-15",
                 "action": "TERMINATE", "plan_type": "sell",
                 "neo": "Jane Doe", "role": "CFO", "shares": 100000},
            ], "v-test")
            state.upsert_score(conn, "TEST", "v-test", 24.0,
                               {"term_sell": 1}, ["test"], True)
        # Incremental-fetch helpers
        assert_eq(state.last_scanned_date(conn, "TEST"), "2026-03-01",
                  "last_scanned_date")
        assert_eq(state.known_accessions(conn, "TEST"),
                  {"0001-26-000001", "0001-26-000002"}, "known_accessions")
        # Events round-trip
        evs = state.events_for(conn, "TEST", "v-test")
        assert_eq(len(evs), 1, "one event")
        assert_eq(evs[0]["neo"], "Jane Doe", "event neo")
        assert_eq(evs[0]["shares"], 100000, "event shares")
        # Scores round-trip
        scores = state.all_scores(conn, "v-test")
        assert_eq(scores["TEST"]["score"], 24.0, "score")
        assert_true(scores["TEST"]["data_available"], "data_available")
        conn.close()


def test_state_filing_idempotent():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = state.connect(db)
        with conn:
            state.record_filing(conn, "T2", "acc-1", "10-Q", "2026-01-01")
            state.record_filing(conn, "T2", "acc-1", "10-Q", "2026-01-01")
        n = conn.execute(
            "SELECT COUNT(*) FROM filings WHERE ticker='T2'").fetchone()[0]
        assert_eq(n, 1, "duplicate filing ignored")
        conn.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in globals().items()
             if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
