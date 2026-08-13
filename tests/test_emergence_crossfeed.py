"""Regression tests for the emergence cross-feed layer."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from emergence_crossfeed import (
    confidence_base, recency_factor, score_entity,
)


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


TODAY = datetime(2026, 8, 13, tzinfo=timezone.utc)

# confidence grading
assert_eq(confidence_base("high (primary + corroboration)"), 20.0, "high")
assert_eq(confidence_base("medium (single primary source)"), 12.0, "med-primary")
assert_eq(confidence_base("medium (corroborating signals only)"), 8.0, "med-corr")
assert_eq(confidence_base("low (single corroborating signal)"), 4.0, "low")
assert_eq(confidence_base(None), 0.0, "none")

# recency decay
assert_eq(recency_factor("2026-07-20", TODAY), 1.0, "fresh")
assert_eq(recency_factor("2026-03-01", TODAY), 0.75, "165d")
assert_eq(recency_factor("2025-01-01", TODAY), 0.25, "stale")

# fresh, corroborated, 4-channel emergence scores near the top
strong = score_entity({
    "ticker": "GOCOQ", "name": "GoHealth",
    "confidence": "high (primary + corroboration)",
    "channels": {"a": 1, "b": 1, "c": 2, "d": 1},
    "last_filed": "2026-07-23", "pending": False,
}, TODAY)
assert_true(strong is not None and strong["score"] >= 25, "strong entity")

# pending (still in Ch11) must NOT score -- wrong instrument
pending = score_entity({
    "ticker": "XYZQ", "confidence": "high (primary + corroboration)",
    "channels": {"a": 1}, "last_filed": "2026-07-01", "pending": True,
}, TODAY)
assert_eq(pending, None, "pending excluded")

# garbage ticker never enters
bad = score_entity({
    "ticker": "NONE", "confidence": "high (primary + corroboration)",
    "channels": {"a": 1}, "last_filed": "2026-07-01", "pending": False,
}, TODAY)
assert_eq(bad, None, "invalid ticker excluded")

# stale low-confidence decays to a token score
weak = score_entity({
    "ticker": "OLD", "confidence": "low (single corroborating signal)",
    "channels": {"a": 1}, "last_filed": "2025-01-01", "pending": False,
}, TODAY)
assert_true(weak is not None and weak["score"] <= 2, "stale low is token")

print("test_emergence_crossfeed: all assertions passed")
