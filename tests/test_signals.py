"""Signal-layer tests for the contamination patterns surfaced by the
forensic audit."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signals as sigmod
import params


# ----- Entity verification ----------------------------------------

def test_psh_psus_contamination_dropped():
    """The PSH.L forensic finding: 39 of 39 director-dealings headlines
    were actually PSUS / PS Inc (Ackman's new US listings)."""
    bad = ('Director Bruce Herring buys 10,000 Pershing Square USA '
           '(PSUS) shares')
    assert not sigmod._entity_match(
        bad, "PSH.L", "Pershing Square Holdings",
        params.SIGNAL_EXCLUSIONS.get("PSH.L", []))


def test_psh_genuine_holding_match():
    good = "Pershing Square Holdings, Ltd. Announces Transactions in Own Shares"
    assert sigmod._entity_match(
        good, "PSH.L", "Pershing Square Holdings",
        params.SIGNAL_EXCLUSIONS.get("PSH.L", []))


def test_oci_conduit_contamination_dropped():
    """OCI.L forensic finding: 'Conduit Holdings appoints directors'
    was wrongly counted as Oakley insider activity."""
    bad = "Conduit Holdings Appoints New Directors"
    assert not sigmod._entity_match(
        bad, "OCI.L", "Oakley Capital Investments",
        params.SIGNAL_EXCLUSIONS.get("OCI.L", []))


# ----- Direction parsing ------------------------------------------

def test_director_termination_not_classified_as_dealing():
    """SOHO.L forensic finding: 'Termination of Tracey Fletcher as
    director' was being counted as a positive director-dealings hit."""
    title = ("Social Housing REIT plc Announces Termination of "
             "Tracey Fletcher as Director")
    assert sigmod._classify(title) is None


def test_director_buying_classified_positive():
    title = ("Chrysalis director Simon Holden increases stake with "
             "£52,729 share purchase")
    assert sigmod._classify(title) == "director_dealings"


# ----- Cross-category dedupe --------------------------------------

def test_classify_picks_strongest_category():
    """'SDCL opts for wind-down after strategic review' contains both
    wind-down AND strategic-review keywords — should score once, in
    wind_down (the higher-strength category)."""
    title = "SDCL Efficiency opts for managed wind-down after strategic review"
    cat = sigmod._classify(title)
    assert cat == "wind_down"


# ----- Amount parsing ---------------------------------------------

def test_amount_parsing_million():
    assert sigmod._parse_amount_gbp("Director purchases £5 million") == 5_000_000


def test_amount_parsing_k():
    assert sigmod._parse_amount_gbp("Director buys £52,729 shares") == 52729


def test_amount_parsing_missing():
    assert sigmod._parse_amount_gbp("Director buys shares") == 0.0


def test_amount_parsing_thousand_word():
    assert sigmod._parse_amount_gbp("Insider buys £100 thousand") == 100_000


# ----- Time decay -------------------------------------------------

def test_decay_recent_close_to_one():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    assert sigmod._decay_weight(now, 30) > 0.99


def test_decay_one_halflife_ago_is_half():
    from datetime import datetime, timezone, timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=30)
    w = sigmod._decay_weight(dt, 30)
    assert 0.45 < w < 0.55


def test_decay_none_returns_one():
    assert sigmod._decay_weight(None, 30) == 1.0
