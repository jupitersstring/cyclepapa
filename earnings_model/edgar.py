"""Authoritative US fundamentals from SEC EDGAR XBRL (companyfacts API).

yfinance gives ~4 years of statements and market data; SEC EDGAR gives the FULL
filed history (the "backlog" — typically 10-15+ years of annual and every
discrete quarter) for US filers, straight from the 10-K/10-Q XBRL, with no rate
wall worth worrying about (SEC allows ~10 req/s with a declared User-Agent).

This module is the STATEMENT side only — SEC XBRL carries no market data, so the
merge keeps yfinance's valuation / prices / EPS-surprises and overlays EDGAR's
authoritative annual + quarterly statement blocks (revenue, gross, EBITDA,
earnings, EPS), in the exact shape :func:`earnings_model.metrics.compute_metrics`
already consumes.

Periodization (the crux of XBRL): companyfacts repeats every period across
filings (each 10-K restates the prior year's comparatives), so we DEDUPE by
period-end date, keeping the latest-filed value (captures restatements). Periods
are classified by DURATION — ~12 months => annual, ~3 months => discrete quarter
— which is robust to the ``frame`` tag being null on the newest filings. EBITDA
is reconstructed (operating income + D&A) since SEC has no EBITDA concept, mirroring
the yfinance fallback.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from . import config

NaN = float("nan")

# SEC asks for a descriptive User-Agent with contact info on every request.
_UA = {"User-Agent": "cyclepapa-research contact@cyclepapa.example"}
_BASE_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_CACHE = config.CACHE_DIR / "edgar"
_MIN_INTERVAL = 1.0 / 8.0   # <=8 req/s, comfortably under SEC's ~10/s limit
_last_call = [0.0]

# Ordered XBRL us-gaap concept candidates per line item. We pick, per company,
# the single candidate with the most populated annual history (companies report
# revenue under exactly one primary tag; choosing the richest avoids mixing
# inconsistent definitions across the candidate set).
# Candidates are listed CURRENT-TAG-FIRST and merged across eras (see
# _merge_concept): a company that switched from ``Revenues`` to
# ``RevenueFromContractWithCustomer...`` in 2018 keeps one continuous series, with
# the modern tag winning on any overlapping period.
_CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues",
                "SalesRevenueNet", "SalesRevenueGoodsNet"],
    "gross": ["GrossProfit"],
    "earnings": ["NetIncomeLoss", "ProfitLoss",
                 "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "op_income": ["OperatingIncomeLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
}
# Depreciation & amortization for the EBITDA reconstruction. Try a single combined
# tag first; otherwise sum the discrete Depreciation + intangible-Amortization
# components (the schedule-disclosure tags like ...AmortizationExpenseYearTwo are
# forward-looking and deliberately excluded).
_DA_COMBINED = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                "DepreciationAmortizationAndAccretionNet",
                "DepreciationAmortizationAndImpairment", "DepreciationAmortizationAndOther"]
_DA_DEP = ["Depreciation", "DepreciationNonproduction"]
_DA_AMORT = ["AmortizationOfIntangibleAssets"]


# --------------------------------------------------------------------------- #
# HTTP (paced, cached, SEC-compliant)
# --------------------------------------------------------------------------- #
def _throttle() -> None:
    gap = _last_call[0] + _MIN_INTERVAL - time.monotonic()
    if gap > 0:
        time.sleep(gap)
    _last_call[0] = time.monotonic()


def _get_json(url: str, retries: int = 4):
    last = None
    for attempt in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                return None                      # genuinely no filings for this CIK
            time.sleep(config.BACKOFF_BASE * (2 ** attempt))  # 429/5xx -> back off
        except Exception as e:                   # noqa: BLE001 transient network
            last = e
            time.sleep(config.BACKOFF_BASE * (2 ** attempt))
    raise RuntimeError(f"SEC fetch failed: {url}: {last}")


def ticker_cik_map(refresh: bool = False) -> dict[str, int]:
    """{TICKER -> CIK int} from SEC's official company_tickers.json (~10k US filers)."""
    path = _EDGAR_CACHE / "ticker_cik.json"
    if path.exists() and not refresh:
        try:
            return {k: int(v) for k, v in json.loads(path.read_text()).items()}
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    data = _get_json(_TICKERS_URL) or {}
    out = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper().strip()
        if t:
            out[t] = int(row["cik_str"])
    _EDGAR_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def companyfacts(cik: int, ttl_days: float = config.CACHE_TTL_DAYS,
                 refresh: bool = False) -> dict | None:
    """Raw companyfacts JSON for a CIK, cached to cache/edgar/CIK##########.json."""
    _EDGAR_CACHE.mkdir(parents=True, exist_ok=True)
    path = _EDGAR_CACHE / f"CIK{cik:010d}.json"
    if path.exists() and not refresh:
        try:
            blob = json.loads(path.read_text())
            asof = blob.get("_asof")
            if asof and ttl_days is not None:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(asof)
                if age.total_seconds() <= ttl_days * 86400:
                    return blob
            elif asof is None:
                return blob
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    data = _get_json(_BASE_FACTS.format(cik=cik))
    if data is None:
        return None
    data["_asof"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data))
    return data


# --------------------------------------------------------------------------- #
# XBRL -> aligned statement blocks
# --------------------------------------------------------------------------- #
def _dur_days(fact: dict):
    try:
        s = date.fromisoformat(fact["start"]); e = date.fromisoformat(fact["end"])
    except (KeyError, ValueError, TypeError):
        return None
    return (e - s).days


def _split_periods(unit_arr: list) -> tuple[dict, dict]:
    """Return ({end_date -> val} annual, {end_date -> val} quarterly), deduped.

    Dedupe key is the period-END date; on collision the LATEST-filed value wins
    (so a restated figure supersedes the original). Classification is by DURATION:
    ~12 months (330-400d) annual, ~3 months (80-100d) a discrete quarter.
    """
    annual: dict[str, tuple[str, float]] = {}
    quarterly: dict[str, tuple[str, float]] = {}
    for a in unit_arr:
        val = a.get("val")
        end = a.get("end")
        if val is None or end is None:
            continue
        d = _dur_days(a)
        if d is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        filed = str(a.get("filed", ""))
        if 330 <= d <= 400:
            bucket = annual
        elif 80 <= d <= 100:
            bucket = quarterly
        else:
            continue
        if end not in bucket or filed > bucket[end][0]:
            bucket[end] = (filed, fval)
    return ({k: v[1] for k, v in annual.items()},
            {k: v[1] for k, v in quarterly.items()})


def _merge_concept(gaap: dict, candidates: list[str], nonneg: bool = False) -> tuple[dict, dict]:
    """Union periods across candidate tags into (annual, quarterly) end->val dicts.

    Earlier candidate wins on a shared period-end (``setdefault``), so the modern
    tag takes precedence and older/deprecated tags only FILL the historical gap —
    giving one continuous series across a tag switch (the AAPL/KO ``Revenues`` ->
    ``RevenueFromContractWithCustomer`` transition that otherwise drops recent years).

    ``nonneg=True`` skips negative values, so a junk tag carrying contra/adjustment
    negatives (e.g. a stray ``Revenues`` of -$200M for years where the real
    ``SalesRevenueNet`` is +$2B) cannot win the gap-fill and corrupt the series.
    Used for revenue, which is never negative; earnings/EBITDA/gross legitimately can be.
    """
    ann: dict[str, float] = {}
    qtr: dict[str, float] = {}
    for tag in candidates:
        node = gaap.get(tag)
        if not node:
            continue
        units = node.get("units", {})
        # $ items live under "USD"; EPS under "USD/shares". Take the first unit key.
        unit_key = "USD" if "USD" in units else next(iter(units), None)
        if unit_key is None:
            continue
        a, q = _split_periods(units[unit_key])
        for end, v in a.items():
            if nonneg and v < 0:
                continue
            ann.setdefault(end, v)
        for end, v in q.items():
            if nonneg and v < 0:
                continue
            qtr.setdefault(end, v)
    return ann, qtr


def _dep_amort(gaap: dict) -> tuple[dict, dict]:
    """D&A end->val dicts: a single combined tag if present, else the sum of the
    discrete Depreciation + intangible-Amortization components per period-end."""
    ann, qtr = _merge_concept(gaap, _DA_COMBINED)
    if ann:
        return ann, qtr
    dep_a, dep_q = _merge_concept(gaap, _DA_DEP)
    am_a, am_q = _merge_concept(gaap, _DA_AMORT)

    # Anchor on Depreciation (the dominant add-back) and ADD intangible amortization
    # only where the SAME period reports it. Reconstructing from amortization ALONE
    # (depreciation buried in cost of sales) is definitionally not EBITDA's D&A and
    # would massively understate it; and pairing a present component with an absent
    # one as 0 would fabricate a step exactly where component coverage changes. So a
    # period with no depreciation yields NO D&A -> EBITDA stays NaN there (which the
    # metric/forensic blocks already skip) rather than a wrong-but-present value.
    def _combine(dep: dict, am: dict) -> dict:
        return {end: v + am.get(end, 0.0) for end, v in dep.items()}

    return _combine(dep_a, am_a), _combine(dep_q, am_q)


def _aligned(series_by_item: dict[str, dict], dates: list[str]) -> dict:
    """Project each line item's {end->val} dict onto a shared, sorted date axis,
    NaN where a period is missing — the position-aligned shape metrics expects."""
    out = {"dates": list(dates)}
    for item, d in series_by_item.items():
        out[item] = [d.get(dt, NaN) for dt in dates]
    return out


def build_statements(facts: dict) -> dict:
    """Annual + quarterly statement blocks (revenue/gross/ebitda/earnings/eps)
    from a companyfacts payload, in the metrics-ready shape. EBITDA is rebuilt as
    operating income + D&A (per period-end) since SEC has no EBITDA concept."""
    gaap = (facts.get("facts", {}) or {}).get("us-gaap", {}) or {}
    # Revenue is non-negative — skip negative tag values so a junk Revenues series
    # can't override the real one (the PLXS -$229M-for-4-years corruption).
    items = {k: _merge_concept(gaap, c, nonneg=(k == "revenue")) for k, c in _CONCEPTS.items()}
    items["dep_amort"] = _dep_amort(gaap)

    def reconstruct_ebitda(which: int) -> dict:
        op, da = items["op_income"][which], items["dep_amort"][which]
        out = {}
        for end, o in op.items():
            d = da.get(end)
            if d is not None:
                out[end] = o + d
        return out

    blocks = {}
    for which, name in ((0, "annual"), (1, "quarterly")):
        by_item = {
            "revenue": items["revenue"][which],
            "gross": items["gross"][which],
            "ebitda": reconstruct_ebitda(which),
            "earnings": items["earnings"][which],
            "eps": items["eps"][which],
        }
        # Date axis = union of revenue & earnings period-ends (the reliable anchors).
        axis = sorted(set(by_item["revenue"]) | set(by_item["earnings"]))
        blocks[name] = _aligned(by_item, axis)
    return blocks


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def fetch_statements(ticker: str, cik: int | None = None,
                     refresh: bool = False) -> dict | None:
    """EDGAR statement blocks for a ticker, or None if it has no SEC filings.

    Returns ``{"annual": {...}, "quarterly": {...}, "cik": int,
    "n_annual": int, "source": "edgar"}`` or None for non-filers / no data.
    """
    cmap = ticker_cik_map()
    cik = cik if cik is not None else cmap.get(ticker.upper())
    if cik is None:
        return None
    facts = companyfacts(cik, refresh=refresh)
    if facts is None:
        return None
    blocks = build_statements(facts)
    n_annual = sum(1 for v in blocks["annual"].get("revenue", []) if v == v)
    if n_annual == 0:
        return None                              # filer but no usable revenue history
    return {"cik": cik, "annual": blocks["annual"], "quarterly": blocks["quarterly"],
            "n_annual": n_annual, "source": "edgar"}


def merge_into_raw(yf_raw: dict, edgar: dict) -> dict:
    """Overlay EDGAR's authoritative statements onto a yfinance raw record,
    KEEPING yfinance's valuation / prices / surprises (SEC has none of those).

    Only overlays when EDGAR genuinely has more annual history than the yfinance
    record, so a sparse EDGAR pull never degrades a good yfinance one.
    """
    yf_annual = (yf_raw.get("annual") or {}).get("revenue", []) or []
    yf_n = sum(1 for v in yf_annual if isinstance(v, (int, float)) and v == v)
    if edgar.get("n_annual", 0) < max(yf_n, 1):
        return yf_raw
    merged = dict(yf_raw)
    merged["annual"] = edgar["annual"]          # authoritative + full filing backlog
    # Keep yfinance's QUARTERLY block: EDGAR's discrete quarters omit fiscal Q4
    # (10-Ks report the full year, not a Q4), which would break the YoY-by-4
    # indexing in metrics._q_yoy_block. yfinance gives consecutive quarters.
    merged["cik"] = edgar.get("cik")
    merged["statement_source"] = "edgar-annual"
    merged["fetch_ok"] = True
    return merged
