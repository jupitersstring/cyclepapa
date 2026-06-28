"""Periodization correctness for the EDGAR XBRL extractor (offline, synthetic).

Guards the three subtle behaviours that broke during development:
  * dedupe a period by its END date, keeping the LATEST-filed value (restatement);
  * MERGE concept tags across eras with the modern tag winning (Revenues ->
    RevenueFromContractWithCustomer), so a tag switch keeps one continuous series;
  * reconstruct EBITDA = operating income + (Depreciation + intangible Amortization)
    when no single combined D&A tag exists.
"""
import math

from earnings_model import edgar


def _fact(start, end, val, filed, form="10-K", fp="FY"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "fp": fp}


def _synthetic_facts():
    usd = lambda arr: {"units": {"USD": arr}}
    return {"facts": {"us-gaap": {
        # deprecated tag: FY2015-2017
        "Revenues": usd([
            _fact("2015-01-01", "2015-12-31", 100, "2016-02-01"),
            _fact("2016-01-01", "2016-12-31", 110, "2017-02-01"),
            _fact("2017-01-01", "2017-12-31", 120, "2018-02-01"),
        ]),
        # modern tag: FY2017(restated)-2019 + a quarter + a later restatement of FY2019
        "RevenueFromContractWithCustomerExcludingAssessedTax": usd([
            _fact("2017-01-01", "2017-12-31", 121, "2019-02-01"),   # modern wins 2017
            _fact("2018-01-01", "2018-12-31", 130, "2019-02-01"),
            _fact("2019-01-01", "2019-12-31", 140, "2020-02-01"),   # original FY2019
            _fact("2019-01-01", "2019-03-31", 33, "2019-05-01", form="10-Q", fp="Q1"),  # quarter
            _fact("2019-01-01", "2019-12-31", 141, "2021-02-01"),   # restated FY2019 (latest filed)
        ]),
        "OperatingIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 20, "2020-02-01")]),
        "Depreciation": usd([_fact("2019-01-01", "2019-12-31", 5, "2020-02-01")]),
        "AmortizationOfIntangibleAssets": usd([_fact("2019-01-01", "2019-12-31", 3, "2020-02-01")]),
        "NetIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 12, "2020-02-01")]),
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            _fact("2019-01-01", "2019-12-31", 1.2, "2020-02-01")]}},
    }}}


def test_periodization_and_merge():
    blocks = edgar.build_statements(_synthetic_facts())
    a = blocks["annual"]
    dates, rev = a["dates"], a["revenue"]
    by_date = dict(zip(dates, rev))

    # full continuous series across the tag switch, oldest -> newest
    assert dates == sorted(dates)
    assert by_date["2015-12-31"] == 100          # deprecated tag fills history
    assert by_date["2017-12-31"] == 121          # modern tag WINS the overlap (not 120)
    assert by_date["2019-12-31"] == 141          # latest-FILED restatement wins (not 140)

    # EBITDA reconstructed = operating income + (depreciation + amortization)
    eb = dict(zip(dates, a["ebitda"]))
    assert eb["2019-12-31"] == 20 + 5 + 3
    # earlier years have no op-income/D&A -> NaN, not a bogus zero
    assert math.isnan(eb["2015-12-31"])

    # EPS read from the USD/shares unit
    assert dict(zip(dates, a["eps"]))["2019-12-31"] == 1.2

    # the ~3-month fact lands in quarterly, not annual
    q = blocks["quarterly"]
    assert 33 in [v for v in q["revenue"] if v == v]
    assert 33 not in [v for v in a["revenue"] if v == v]


def test_no_filer_returns_none():
    # an empty facts payload yields no usable revenue -> build returns empty axis
    blocks = edgar.build_statements({"facts": {"us-gaap": {}}})
    assert blocks["annual"]["dates"] == []


def test_ebitda_never_reconstructed_from_amortization_alone():
    """Depreciation buried in COGS (amortization-only) must NOT yield a tiny
    amortization-only 'EBITDA' — it should be NaN (no honest D&A add-back)."""
    usd = lambda arr: {"units": {"USD": arr}}
    facts = {"facts": {"us-gaap": {
        "Revenues": usd([_fact("2019-01-01", "2019-12-31", 100, "2020-02-01")]),
        "NetIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 12, "2020-02-01")]),
        "OperatingIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 20, "2020-02-01")]),
        "AmortizationOfIntangibleAssets": usd([_fact("2019-01-01", "2019-12-31", 3, "2020-02-01")]),
        # NO Depreciation tag and NO combined D&A tag
    }}}
    a = edgar.build_statements(facts)["annual"]
    eb = dict(zip(a["dates"], a["ebitda"]))
    assert math.isnan(eb["2019-12-31"])         # not 20+3=23


def test_ebitda_from_depreciation_plus_amortization():
    usd = lambda arr: {"units": {"USD": arr}}
    facts = {"facts": {"us-gaap": {
        "Revenues": usd([_fact("2019-01-01", "2019-12-31", 100, "2020-02-01")]),
        "NetIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 12, "2020-02-01")]),
        "OperatingIncomeLoss": usd([_fact("2019-01-01", "2019-12-31", 20, "2020-02-01")]),
        "Depreciation": usd([_fact("2019-01-01", "2019-12-31", 5, "2020-02-01")]),
        "AmortizationOfIntangibleAssets": usd([_fact("2019-01-01", "2019-12-31", 3, "2020-02-01")]),
    }}}
    a = edgar.build_statements(facts)["annual"]
    eb = dict(zip(a["dates"], a["ebitda"]))
    assert eb["2019-12-31"] == 20 + 5 + 3
