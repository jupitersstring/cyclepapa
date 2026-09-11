"""Regression tests for psu_step_change + forensic_asymmetry fixes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from forensic_asymmetry import classify_direction, archetype_labels
from psu_step_change import pattern_match_score


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(
            f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


def assert_close(actual, target, tol, label=""):
    if abs(actual - target) > tol:
        raise AssertionError(
            f"FAIL {label}: expected ~{target} +/- {tol}, got {actual}")


# ---------------------------------------------------------------------------
# Direction classifier (forensic_asymmetry)
# ---------------------------------------------------------------------------

def test_direction_forward_must_have_achieved():
    # HFFG canonical forward language
    s = ("in order to vest at 100%, the Company must have achieved a "
         "revenue of $1.232 billion")
    assert_eq(classify_direction(s), "forward",
              "HFFG must-have-achieved")


def test_direction_forward_will_vest_upon():
    s = "the PRSUs will vest upon achievement of the EBITDA target"
    assert_eq(classify_direction(s), "forward", "will vest upon")


def test_direction_retrospective_we_achieved():
    # CCI canonical retrospective language
    s = ("In 2025, we achieved Adjusted EBITDA performance of "
         "$4.044 billion")
    assert_eq(classify_direction(s), "retrospective",
              "CCI we-achieved")


def test_direction_retrospective_paid_out_at():
    s = "the annual incentive paid out at 142% of target"
    assert_eq(classify_direction(s), "retrospective",
              "paid out at X%")


def test_direction_ambiguous_default():
    # No forward/retro markers -> ambiguous
    s = "Adjusted EBITDA target for 2025 of $15.2 million"
    assert_eq(classify_direction(s), "ambiguous",
              "PLBY pure target language")


# ---------------------------------------------------------------------------
# Hurdle plausibility gate (psu_step_change)
# ---------------------------------------------------------------------------

def test_plausibility_gate_filters_huge_hurdles():
    # EYE case: $26-$900 ladder where current price ~$22
    r = {
        "current_price": 22.34,
        "stock_price_hurdles": [26, 50, 100, 900],  # $900 implausible at 22.34
        "per_share_metrics": ["TSR"],
        "aggregate_metrics": [],
        "alignment": 50,
        "upside_kicker": 0,
    }
    score, reasons = pattern_match_score(r, None)
    # Should mention filtering and report top hurdle <= 8x current
    filter_reason = next((x for x in reasons
                          if "filtered" in x.lower()), None)
    assert_true(filter_reason is not None,
                f"reasons should mention 'filtered'; got {reasons}")


def test_plausibility_gate_keeps_real_ladder():
    # HFFG case: $4-$8 ladder where current price ~$1.90
    r = {
        "current_price": 1.90,
        "stock_price_hurdles": [4, 6, 8],  # all within 8x of $1.90 = $15.2
        "per_share_metrics": ["TSR"],
        "aggregate_metrics": [],
        "alignment": 50,
        "upside_kicker": 100,
    }
    score, reasons = pattern_match_score(r, None)
    # No filter mention; full credit for 3-tranche ladder
    filter_reason = next((x for x in reasons
                          if "filtered" in x.lower()), None)
    assert_true(filter_reason is None,
                f"no filter expected; got {reasons}")
    # Should credit a 3-tranche ladder
    ladder_reason = next((x for x in reasons if "tranche" in x), None)
    assert_true(ladder_reason is not None and "3-tranche" in ladder_reason,
                f"3-tranche credit expected; got {reasons}")


def test_plausibility_gate_no_current_price_keeps_all():
    # Without current_price we can't gate -- preserve all hurdles
    r = {
        "current_price": 0,
        "stock_price_hurdles": [10, 25, 100, 900],
        "per_share_metrics": ["TSR"],
        "aggregate_metrics": [],
        "alignment": 50,
        "upside_kicker": 0,
    }
    score, reasons = pattern_match_score(r, None)
    # No filter mention (we can't measure plausibility)
    filter_reason = next((x for x in reasons
                          if "filtered" in x.lower()), None)
    assert_true(filter_reason is None,
                f"no current_price -> no filtering; got {reasons}")


# ---------------------------------------------------------------------------
# Archetype labelling
# ---------------------------------------------------------------------------

def test_archetype_per_share_return():
    # 3+ per-share metrics qualifies for A
    forensics = {"performance_metrics": ["TSR", "EPS", "ROIC"]}
    ladder = {}
    labels = archetype_labels(forensics, ladder)
    assert_true("A_per_share_return" in labels,
                f"A label; got {labels}")


def test_archetype_price_ladder():
    forensics = {"performance_metrics": []}
    ladder = {"stock_price_hurdles": [4, 6, 8, 10, 15]}
    labels = archetype_labels(forensics, ladder)
    assert_true("B_price_ladder" in labels, f"B label; got {labels}")


def test_archetype_relative_tsr():
    forensics = {"performance_metrics": ["TSR"]}
    ladder = {}
    labels = archetype_labels(forensics, ladder)
    assert_true("C_relative_TSR" in labels, f"C label; got {labels}")


def test_archetype_dollar_metric():
    forensics = {"performance_metrics": []}
    ladder = {"dollar_ladder": {"target": [100.0]}}
    labels = archetype_labels(forensics, ladder)
    assert_true("D_dollar_metric_target" in labels,
                f"D label; got {labels}")


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
