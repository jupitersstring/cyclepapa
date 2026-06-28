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


def test_revenue_junk_negative_tag_does_not_override_real_tag():
    """A stray NEGATIVE Revenues series (contra/adjustment) ranked above the real
    SalesRevenueNet must NOT win the gap-fill (the PLXS -$229M-for-4-years bug)."""
    usd = lambda arr: {"units": {"USD": arr}}
    facts = {"facts": {"us-gaap": {
        "Revenues": usd([
            _fact("2012-01-01", "2012-12-31", -150_000_000, "2013-02-01"),
            _fact("2013-01-01", "2013-12-31", -100_000_000, "2014-02-01"),
        ]),
        "SalesRevenueNet": usd([
            _fact("2012-01-01", "2012-12-31", 2_300_000_000, "2013-02-01"),
            _fact("2013-01-01", "2013-12-31", 2_228_000_000, "2014-02-01"),
        ]),
        "NetIncomeLoss": usd([_fact("2012-01-01", "2012-12-31", 50_000_000, "2013-02-01")]),
    }}}
    a = edgar.build_statements(facts)["annual"]
    by = dict(zip(a["dates"], a["revenue"]))
    assert by["2012-12-31"] == 2_300_000_000     # real positive, not -150M
    assert by["2013-12-31"] == 2_228_000_000
    assert all((v is None) or (isinstance(v, float) and v != v) or v >= 0 for v in a["revenue"])


def test_axis_includes_all_line_items_not_just_revenue_earnings():
    """A gross/EBITDA/EPS value at a period-end that revenue & earnings don't anchor
    must survive (axis = union of ALL items), not be silently dropped."""
    usd = lambda arr: {"units": {"USD": arr}}
    facts = {"facts": {"us-gaap": {
        "Revenues": usd([_fact("2022-01-01", "2022-12-31", 100, "2023-02-01")]),
        "NetIncomeLoss": usd([_fact("2022-01-01", "2022-12-31", 12, "2023-02-01")]),
        "GrossProfit": usd([_fact("2021-01-01", "2021-12-31", 40, "2022-02-01"),
                            _fact("2022-01-01", "2022-12-31", 45, "2023-02-01")]),
    }}}
    a = edgar.build_statements(facts)["annual"]
    assert "2021-12-31" in a["dates"]            # the revenue-less year is kept
    assert dict(zip(a["dates"], a["gross"]))["2021-12-31"] == 40


def test_despike_strips_spike_and_dip_keeps_ramp_and_onset():
    from earnings_model.edgar import _despike
    s = _despike([100.0, 5000.0, 110.0])          # spike-and-revert -> NaN the spike
    assert math.isnan(s[1]) and s[0] == 100.0 and s[2] == 110.0
    d = _despike([800.0, 10.0, 880.0])            # dip-and-revert -> NaN the dip
    assert math.isnan(d[1])
    assert _despike([100.0, 200.0, 300.0]) == [100.0, 200.0, 300.0]   # ramp survives
    assert _despike([0.0, 174.0, 11.0]) == [0.0, 174.0, 11.0]         # onset survives


def test_quarterly_combined_da_not_discarded_when_annual_combined_absent():
    usd = lambda arr: {"units": {"USD": arr}}
    q = lambda v: _fact("2022-01-01", "2022-03-31", v, "2022-05-01", form="10-Q", fp="Q1")
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [q(100)]}},
        "NetIncomeLoss": {"units": {"USD": [q(12)]}},
        "OperatingIncomeLoss": {"units": {"USD": [q(15)]}},
        "DepreciationDepletionAndAmortization": {"units": {"USD": [q(5)]}},  # quarterly only
    }}}
    qb = edgar.build_statements(facts)["quarterly"]
    assert dict(zip(qb["dates"], qb["ebitda"]))["2022-03-31"] == 15 + 5


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
