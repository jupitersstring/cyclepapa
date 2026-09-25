"""Regression tests for cancel_10b5_1 extractor.

Run with: python3 -m pytest tests/  OR  python3 tests/test_cancel_10b5_1.py

Locks in current behavior so future regex changes don't silently break
extraction. Each test names a real filing case observed during the
analysis."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cancel_10b5_1 import (
    classify, detect_actions, dedupe_cross_quarter,
    extract_context, is_natural_expiration, is_negative_boilerplate,
    neo_passes_sanity, score_events,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(
            f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


# ---------------------------------------------------------------------------
# Sanity-gate tests (NEO name extraction)
# ---------------------------------------------------------------------------

def test_neo_sanity_accepts_real_names():
    # Real CEO / NEO names seen in actual 10-Qs
    for n in ["Jensen Huang", "Marc Benioff", "William R. McDermott",
              "Sachin Mehra", "Carlos Abrams-Rivera", "Cristiano Amon",
              "Mr. Smith", "Chad Robins"]:
        assert_true(neo_passes_sanity(n), f"neo_sanity({n})")


def test_neo_sanity_rejects_role_tokens():
    # Captures that were straddling NEO/role boundary
    for n in ["Huang President", "Williams President", "Vice President",
              "our officers", "to time", "Senior Vice", "President"]:
        assert_true(not neo_passes_sanity(n),
                    f"neo_sanity rejects({n})")


# ---------------------------------------------------------------------------
# Boilerplate / expiration tests
# ---------------------------------------------------------------------------

def test_natural_expiration_filter():
    # Natural-expiration language should be excluded from termination hits
    cases = [
        "the plan was scheduled to terminate on December 31",
        "will terminate upon the earlier of completion",
        "expired by operation of its terms",
        "intended to terminate on April 1, 2026",
    ]
    for c in cases:
        assert_true(is_natural_expiration(c), f"natural_exp({c[:40]})")


def test_natural_expiration_passes_real():
    # Real terminations should NOT be flagged as natural expiration
    cases = [
        "Marc Benioff terminated a Rule 10b5-1 trading arrangement",
        "Jensen Huang terminated his Rule 10b5-1 trading plan",
    ]
    for c in cases:
        assert_true(not is_natural_expiration(c),
                    f"natural_exp passes({c[:40]})")


def test_negative_boilerplate_filter():
    # Standard "nothing happened this quarter" disclosure
    cases = [
        "none of our directors or officers adopted, terminated or modified",
        "no director or officer (as defined in Rule 16a-1(f)) adopted",
        "no Section 16 officer adopted or terminated",
        "no Company director or officer adopted a Rule 10b5-1",
    ]
    for c in cases:
        assert_true(is_negative_boilerplate(c),
                    f"neg_boilerplate({c[:40]})")


# ---------------------------------------------------------------------------
# Classification (scoring) tests
# ---------------------------------------------------------------------------

def test_ceo_sell_termination_scores_high():
    # Marc Benioff terminating a sell plan -- the canonical bullish signal
    e = {
        "action": "TERMINATE", "plan_type": "sell",
        "role": "Chair and Chief Executive Officer", "shares": 351607,
        "neo": "Marc Benioff",
    }
    score, label = classify(e)
    assert_eq(label, "BULLISH terminate sell")
    assert_true(score >= 30, f"score {score} >= 30")  # CEO + 250K size kicker


def test_cfo_sell_adoption_scores_negative():
    e = {
        "action": "ADOPT", "plan_type": "sell",
        "role": "Chief Financial Officer", "shares": 100000,
        "neo": "Gunnar Wiedenfels",
    }
    score, label = classify(e)
    assert_eq(label, "BEARISH adopt sell")
    assert_true(score < 0, f"score {score} < 0")


def test_modification_pair_overrides_to_zero():
    # Same-NEO same-day terminate + adopt = restructuring, not signal
    e = {
        "action": "TERMINATE", "plan_type": "sell",
        "role": "Chief Executive Officer", "shares": 100000,
        "modification_pair": True,
    }
    score, label = classify(e)
    assert_eq(label, "modification_pair")
    assert_eq(score, 0)


def test_small_adoption_weakly_bearish():
    # <10K share adoption is likely tax-management, not conviction
    e = {
        "action": "ADOPT", "plan_type": "sell",
        "role": "Director", "shares": 1359,  # ZTS Kristin Peck case
        "neo": "Kristin Peck",
    }
    score, label = classify(e)
    assert_true("small" in label.lower(),
                f"label should flag small, got {label}")
    assert_true(score >= -5, f"score {score} only weakly negative")


def test_retrospective_downweights():
    # Retrospective passages get 0.3x multiplier on score magnitude
    e = {
        "action": "ADOPT", "plan_type": "sell",
        "role": "Chief Executive Officer", "shares": 250000,
        "neo": "Some CEO", "is_retrospective": True,
    }
    score, label = classify(e)
    # Full credit would be -23 (CEO base -20 + size -3); retro = ~-7
    assert_true(abs(score) < 15,
                f"retro should reduce |score| < 15, got {score}")


# ---------------------------------------------------------------------------
# Cross-quarter dedupe
# ---------------------------------------------------------------------------

def test_cross_quarter_dedupe_keeps_oldest():
    # Same termination disclosed in 3 successive 10-Qs
    events = [
        {"action": "TERMINATE", "plan_type": "sell", "neo": "Sachin Mehra",
         "role": "Chief Financial Officer", "shares": 35079,
         "filing_date": "2025-10-31"},
        {"action": "TERMINATE", "plan_type": "sell", "neo": "Sachin Mehra",
         "role": "Chief Financial Officer", "shares": 35079,
         "filing_date": "2025-07-31"},  # earliest
        {"action": "TERMINATE", "plan_type": "sell", "neo": "Sachin Mehra",
         "role": "Chief Financial Officer", "shares": 35079,
         "filing_date": "2026-01-30"},
    ]
    deduped = dedupe_cross_quarter(events)
    assert_eq(len(deduped), 1, "single event kept")
    assert_eq(deduped[0]["filing_date"], "2025-07-31", "earliest preserved")


def test_cross_quarter_dedupe_separates_distinct_events():
    # Different shares -> different events even if same NEO+role
    events = [
        {"action": "TERMINATE", "plan_type": "sell", "neo": "Mitchell Krebs",
         "role": "Chairman", "shares": 202257,
         "filing_date": "2025-10-29"},
        {"action": "TERMINATE", "plan_type": "sell", "neo": "Mitchell Krebs",
         "role": "Chairman", "shares": 250000,
         "filing_date": "2025-08-06"},
    ]
    deduped = dedupe_cross_quarter(events)
    assert_eq(len(deduped), 2, "distinct share counts preserved")


def test_cross_quarter_dedupe_blank_neo_preserved():
    # Anonymous events (no NEO, no shares) shouldn't collapse together
    events = [
        {"action": "TERMINATE", "plan_type": "sell", "neo": "",
         "role": "director", "shares": 0, "filing_date": "2025-05-01",
         "accession": "acc1"},
        {"action": "TERMINATE", "plan_type": "sell", "neo": "",
         "role": "director", "shares": 0, "filing_date": "2025-08-01",
         "accession": "acc2"},
    ]
    deduped = dedupe_cross_quarter(events)
    assert_eq(len(deduped), 2, "anonymous events kept distinct")


# ---------------------------------------------------------------------------
# End-to-end: detect_actions on synthetic 10-Q Item 5 text
# ---------------------------------------------------------------------------

CRM_FRAGMENT = """
ITEM 5. OTHER INFORMATION
(c) Insider trading arrangements and policies. During the three months
ended April 30, 2026, none of our directors or executive officers (as
defined in Rule 16a-1(f) of the Exchange Act) informed us of the
adoption or termination of a "Rule 10b5-1 trading arrangement" or
"non-Rule 10b5-1 trading arrangement" (as defined in Item 408 of
Regulation S-K), except as follows. On March 31, 2026, Marc Benioff,
Chair and Chief Executive Officer, terminated a Rule 10b5-1 trading
arrangement that he entered into on October 10, 2025. The terminated
Rule 10b5-1 trading arrangement provided for the sale of up to 351,607
shares of the Company's common stock, subject to certain conditions,
between April 1, 2026 and February 26, 2027.
"""


def test_e2e_crm_benioff_termination():
    events = detect_actions(CRM_FRAGMENT)
    terminations = [e for e in events if e["action"] == "TERMINATE"
                    and e.get("plan_type") == "sell"]
    assert_true(len(terminations) >= 1,
                f"Benioff termination detected; got {len(events)} events")
    benioff = [e for e in terminations if e.get("neo")
               and "Benioff" in e.get("neo", "")]
    assert_true(len(benioff) >= 1, "Benioff NEO attribution")
    e = benioff[0]
    assert_eq(e["shares"], 351607, "share count")
    assert_true("Chief Executive" in e.get("role", "")
                or "Chair" in e.get("role", ""),
                f"role captured (got: {e.get('role')!r})")


CORPORATE_BUYBACK_FRAGMENT = """
ITEM 5. OTHER INFORMATION
On March 1, 2026, the Company entered into an accelerated share
repurchase (ASR Agreement) for the purchase of approximately 3,000,000
shares of the Company's common stock as part of the share repurchase
program. The ASR Agreement is intended to satisfy Rule 10b5-1.
"""


def test_e2e_corporate_buyback_excluded():
    events = detect_actions(CORPORATE_BUYBACK_FRAGMENT)
    # Corporate ASR / share repurchase should NOT score as insider buy
    insider_events = [e for e in events if not e.get("is_corporate")]
    assert_eq(len(insider_events), 0,
              f"corporate ASR should not produce insider events; got "
              f"{[(e['action'], e.get('shares')) for e in events]}")


NO_ACTIVITY_FRAGMENT = """
ITEM 5. OTHER INFORMATION
During the three months ended March 31, 2026, no director or officer
(as defined in Rule 16a-1(f)) of the Company adopted or terminated a
"Rule 10b5-1 trading arrangement" or "non-Rule 10b5-1 trading
arrangement", as each term is defined in Item 408(a) of Regulation S-K.
"""


def test_e2e_no_activity_disclosure():
    events = detect_actions(NO_ACTIVITY_FRAGMENT)
    assert_eq(len(events), 0,
              f"'no director adopted' should yield zero events; got {events}")


# ---------------------------------------------------------------------------
# Test runner
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
