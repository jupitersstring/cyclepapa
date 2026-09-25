"""Regression tests for the INCENTIVE_AUDIT.md fixes (R1-R7).

Each test pairs the audit's confirmed false-positive probe (must now be
clean) with a genuine-positive probe (must still fire) so the fixes
cannot silently over-correct.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from psu_scoring import extract_features, score
from psu_forensics import extract_forensics
from psu_forensics_v2 import extract_say_on_pay
from forensic_asymmetry import extract_plan_deltas


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


PSU = "performance share units "  # prefix so has_psu_program is True

# ---------------------------------------------------------------- R1 ---
# Comma-grouped comp dollars must not become phantom hurdles.
f = extract_features("T", PSU + "vest upon achievement of the following "
                     "stock price hurdles. The target bonus is $1,250,000 "
                     "and the maximum award value is $2,500,000.")
assert_eq(f.stock_price_hurdles, [], "R1 comma-grouped dollars rejected")

# Million-suffixed amounts must not become hurdles.
f = extract_features("T", PSU + "a threshold of $2.4 million EBITDA and "
                     "severance of $1.5 million")
assert_eq(f.stock_price_hurdles, [], "R1 $-million rejected")

# Genuine ladders still extract -- slash, comma-list, and 4-digit-with-
# comma hurdle forms.
f = extract_features("T", PSU + "vesting in tranches at stock price "
                     "hurdles of $15 / $30 / $45")
assert_true({15.0, 30.0, 45.0} <= set(f.stock_price_hurdles),
            "R1 genuine slash ladder survives")
f = extract_features("T", PSU + "stock price hurdle of $1,050")
assert_true(1050.0 in f.stock_price_hurdles, "R1 comma-grouped real hurdle kept")

# ---------------------------------------------------------------- R2 ---
neg = extract_forensics(PSU + "We do not provide single-trigger "
                        "acceleration of equity awards upon a change in control.")
assert_eq(neg.get("single_trigger"), False, "R2 negated single-trigger clean")
pos = extract_forensics(PSU + "Awards are subject to single-trigger "
                        "accelerated vesting upon a change in control.")
assert_eq(pos.get("single_trigger"), True, "R2 real single-trigger fires")

# ---------------------------------------------------------------- R3 ---
f = extract_features("T", PSU + "Employees may participate in the 401(k) "
                     "retirement savings plan sponsored by the Company.")
assert_eq(f.retirement_language, False, "R3 401(k) boilerplate clean")
f = extract_features("T", PSU + "awards continue to vest following the "
                     "executive's retirement")
assert_eq(f.retirement_language, True, "R3 genuine retirement carveout fires")

# ---------------------------------------------------------------- R4 ---
f = extract_features("T", PSU + "The Committee administers the plan in "
                     "its sole discretion.")
assert_eq(f.discretionary_language, False, "R4 admin boilerplate clean")
f = extract_features("T", PSU + "the Committee may, in its discretion, "
                     "increase or decrease the payout under the awards")
assert_eq(f.discretionary_language, True, "R4 payout override fires")
f = extract_features("T", PSU + "a discretionary bonus was paid to the CEO")
assert_eq(f.discretionary_language, True, "R4 discretionary bonus fires")

# ---------------------------------------------------------------- R5 ---
assert_eq(extract_say_on_pay(
    "advisory vote on executive compensation received 100% approval"),
    100.0, "R5 100% capturable")
sop = extract_say_on_pay(
    "In 2025 our say-on-pay proposal received 78% approval, compared "
    "with the 92% approval received at the 2024 annual meeting for "
    "say-on-pay.")
assert_eq(sop, 78.0, "R5 latest-year value wins over historical high")

# ---------------------------------------------------------------- R6 ---
f = extract_features("T", PSU + "vesting upon 25%, 50%, 75% and 100% "
                     "share price appreciation")
assert_true(len(f.appreciation_pcts) >= 4, "R6 appreciation ladder extracted")
s = score(f, current_price=10.0)
assert_true(s.upside_kicker > 0, "R6 implied hurdles drive upside kicker")

# ---------------------------------------------------------------- R7 ---
d = extract_plan_deltas("this year we increased the portion of the "
                        "annual equity mix awarded as PSUs to 70%")
assert_true(d.get("psu_weight_increased"), "R7 widened psu_weight fires")
d = extract_plan_deltas("the Committee added a ROIC metric to the PSU design")
assert_true(d.get("new_metric_added"), "R7 widened new_metric fires")

# ---------------------------------------------------------------- R9 ---
f = extract_features("T", PSU + "the Committee adjusted targets to "
                     "reflect the divestiture of the consumer segment")
assert_eq(f.repricing_language, False, "R9 routine target-setting clean")
f = extract_features("T", PSU + "the Board approved the repricing of "
                     "outstanding awards")
assert_eq(f.repricing_language, True, "R9 real repricing fires")

# --------------------------------------------------------------- R10 ---
# aggregate EBITDA in covenant / peer-group context must NOT flag
f = extract_features("T", PSU + "PSUs vest on relative TSR. EBITDA as "
                     "defined in the credit agreement is used only for the "
                     "leverage ratio covenant.")
assert_eq(f.aggregate_metrics, [], "R10 covenant EBITDA not an LTI metric")
# but EBITDA as a real LTI metric still counts
f = extract_features("T", PSU + "the PSU payout is based 50% on adjusted "
                     "EBITDA and 50% on TSR")
assert_true("absolute_ebitda" in f.aggregate_metrics, "R10 real LTI EBITDA fires")

# ---------------------------------------------------------------- S2 ---
# widened say-on-pay phrasings now extract (were missed -> 39% coverage)
assert_eq(extract_say_on_pay(
    "our say-on-pay proposal received the support of 94% of the votes cast"),
    94.0, "S2 'support of X%'")
assert_eq(extract_say_on_pay(
    "the advisory vote on executive compensation was approved by 88% in favour"),
    88.0, "S2 British 'in favour'")
assert_eq(extract_say_on_pay(
    "say-on-pay received support of approximately 72%"),
    72.0, "S2 reverse 'support of X%'")

print("test_incentive_fixes: all assertions passed")
