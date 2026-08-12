"""Regression tests for the discretionary insider-conviction leg.

Covers role classification, cluster-window / same-day detection, the
dollar conviction gate that neutralises trivial-dollar 'clusters', and
end-to-end scoring on a synthetic same-day C-suite cluster.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from discretionary_insider_conviction import (
    classify_role,
    role_from_buyer,
    cluster_metrics,
    conviction_gate,
    holdings_anomaly,
    is_valid_ticker,
    score_ticker,
)


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(f"FAIL {label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label=""):
    if not cond:
        raise AssertionError(f"FAIL {label}: condition false")


# --- role classification ----------------------------------------------
assert_eq(classify_role("Chief Executive Officer"), "c_suite", "CEO")
assert_eq(classify_role("President and CEO"), "c_suite", "Pres+CEO")
assert_eq(classify_role("EVP & Chief Financial Officer"), "c_suite", "EVP-CFO")
assert_eq(classify_role("Chairman"), "chair_founder", "chair")
assert_eq(classify_role("Director"), "director", "director")
assert_eq(classify_role("10%"), "ten_pct", "tenpct")
assert_eq(classify_role("VP"), "other_vp", "vp")
assert_eq(classify_role(""), "unknown", "empty")

# NOTE: "Executive Chairman" contains no CEO/CFO/President token but does
# match CHIEF? no -- it should fall to chair_founder. Verify explicitly:
assert_eq(classify_role("Executive Chairman"), "chair_founder", "exec-chairman")

# buyer_set entry split
p, r = role_from_buyer("Allemann David Michael | Executive Officer & Co-CEO")
assert_eq(p, "ALLEMANN DAVID MICHAEL", "person parse")
assert_eq(r, "c_suite", "co-CEO role")


# --- cluster metrics ---------------------------------------------------
# three distinct insiders, all same day -> same_day=3, cluster_size=3
same_day = [
    {"date": "2026-05-15", "person": "A"},
    {"date": "2026-05-15", "person": "B"},
    {"date": "2026-05-15", "person": "C"},
]
cs, sd, span = cluster_metrics(same_day)
assert_eq(cs, 3, "same-day cluster size")
assert_eq(sd, 3, "same-day count")
assert_eq(span, 0, "same-day span")

# spread beyond the 45d window should NOT count as one cluster
spread = [
    {"date": "2026-01-01", "person": "A"},
    {"date": "2026-06-01", "person": "B"},   # ~150d later
]
cs2, sd2, span2 = cluster_metrics(spread)
assert_eq(cs2, 1, "out-of-window cluster stays 1")
assert_eq(sd2, 1, "no same-day")

# two insiders 10 days apart -> window cluster of 2
near = [
    {"date": "2026-03-01", "person": "A"},
    {"date": "2026-03-11", "person": "B"},
]
cs3, sd3, span3 = cluster_metrics(near)
assert_eq(cs3, 2, "in-window cluster of 2")
assert_eq(span3, 10, "window span 10d")

# same person buying repeatedly is NOT a cluster of many
repeat = [
    {"date": "2026-03-01", "person": "A"},
    {"date": "2026-03-05", "person": "A"},
    {"date": "2026-03-09", "person": "A"},
]
cs4, _, _ = cluster_metrics(repeat)
assert_eq(cs4, 1, "one person != cluster")


# --- conviction gate ---------------------------------------------------
assert_eq(conviction_gate(1e6), 1.0, "gate full")
assert_true(conviction_gate(1e4) < 0.5, "trivial dollars dampened")
assert_true(conviction_gate(5e4) < 1.0, "small dollars partial")


# --- holdings anomaly (enriched fields) --------------------------------
# insider grew stake from 100 -> 200 shares = +100% -> strong tell
big = [{"shares": 100, "post_shares": 200}]
assert_true(holdings_anomaly(big) >= 10.0, "doubling stake scores high")
# token add: 10000 -> 10010 = +0.1% -> nothing
tiny = [{"shares": 10, "post_shares": 10010}]
assert_eq(holdings_anomaly(tiny), 0.0, "token add scores 0")
# legacy record without post_shares -> graceful 0
assert_eq(holdings_anomaly([{"shares": 5}]), 0.0, "missing field -> 0")


# --- ticker validity ---------------------------------------------------
assert_true(is_valid_ticker("AAPL"), "AAPL valid")
assert_true(not is_valid_ticker("NONE"), "NONE invalid")
assert_true(not is_valid_ticker("N/A"), "N/A invalid")
assert_true(not is_valid_ticker("CIK0001234"), "CIK invalid")


# --- end-to-end: ONON-style same-day 3-exec cluster -------------------
rec = {
    "buyer_set": [
        "Allemann David Michael | Executive Officer & Co-CEO",
        "Bernhard Olivier | Executive Officer",
        "Coppetti Caspar Felix | Executive Officer & Co-CEO",
    ],
    "total_dollar": 6594299.0,
    "filings": [
        {"date": "2026-05-15", "person": "Allemann David Michael", "dollar": 2198098.0, "shares": 60000},
        {"date": "2026-05-15", "person": "Bernhard Olivier", "dollar": 2198098.0, "shares": 60000},
        {"date": "2026-05-15", "person": "Coppetti Caspar Felix", "dollar": 2198102.0, "shares": 60000},
    ],
}
out = score_ticker(rec)
assert_eq(out["n_insiders"], 3, "3 insiders")
assert_eq(out["same_day_cluster"], 3, "same-day 3")
assert_true(out["csuite_buyers"] >= 2, "multiple C-suite")
assert_true(out["score"] >= 40, "high-conviction cluster scores high")
# a lone director buying $30k should score far lower
low = {
    "buyer_set": ["Graves Gregory B | Director"],
    "total_dollar": 22697.0,
    "filings": [{"date": "2026-05-15", "person": "Graves Gregory B", "dollar": 22697.0, "shares": 475}],
}
lo = score_ticker(low)
assert_true(lo["score"] < out["score"], "lone small director < exec cluster")
assert_true(lo["score"] < 15, "lone small buy is modest")


print("test_discretionary_conviction: all assertions passed")
