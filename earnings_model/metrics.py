"""Growth, acceleration and inflection metrics.

Pure functions over plain Python sequences (no network, no pandas state) so
the analytical core is deterministic and unit-testable offline.

Convention: every history sequence is ordered **oldest -> newest**.

Growth handling for loss-makers
-------------------------------
Ratio growth (vₜ/vₜ₋₁ − 1) is only meaningful when the prior value is
positive, which is often false for EBITDA / net income in small-cap and
biotech names. We therefore expose three complementary views:

* ``*_growth``  / ``*_accel``      — ratio YoY growth and its change (NaN when
  the denominator is non-positive);
* ``*_accel_abs``                  — acceleration of the *absolute* level change
  (always defined), which still captures a trough turning up;
* ``*_turned_positive``            — a loss -> profit crossing (a hard inflection).
"""
from __future__ import annotations

import math
from typing import Sequence

from . import config

NaN = float("nan")


def _isnan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _f(x) -> float:
    """Coerce to float, mapping missing/garbage to NaN."""
    if x is None:
        return NaN
    try:
        v = float(x)
    except (TypeError, ValueError):
        return NaN
    return v if not math.isnan(v) else NaN


def pct_growth(curr, prev) -> float:
    """YoY ratio growth; defined only when ``prev`` is strictly positive."""
    curr, prev = _f(curr), _f(prev)
    if _isnan(curr) or _isnan(prev) or prev <= 0:
        return NaN
    return curr / prev - 1.0


def cagr(values: Sequence[float]) -> float:
    """Compound annual growth across an all-positive series; else NaN."""
    vals = [_f(v) for v in values]
    vals = [v for v in vals if not _isnan(v)]
    if len(vals) < 2 or any(v <= 0 for v in vals):
        return NaN
    n = len(vals) - 1
    return (vals[-1] / vals[0]) ** (1.0 / n) - 1.0


def metric_block(values: Sequence[float], prefix: str) -> dict:
    """Compute the growth/acceleration/inflection block for one line item.

    ``values`` is oldest -> newest. Returns a flat dict keyed by ``prefix``.
    """
    vals = [_f(v) for v in values]
    n = len(vals)
    latest = vals[-1] if n >= 1 else NaN
    prev = vals[-2] if n >= 2 else NaN
    prev2 = vals[-3] if n >= 3 else NaN

    growth = pct_growth(latest, prev)
    prev_growth = pct_growth(prev, prev2)
    accel = (growth - prev_growth) if not (_isnan(growth) or _isnan(prev_growth)) else NaN

    # Absolute-level dynamics (robust to sign changes / losses).
    delta = (latest - prev) if not (_isnan(latest) or _isnan(prev)) else NaN
    delta_prev = (prev - prev2) if not (_isnan(prev) or _isnan(prev2)) else NaN
    accel_abs = (delta - delta_prev) if not (_isnan(delta) or _isnan(delta_prev)) else NaN

    turned_positive = (not _isnan(prev)) and (not _isnan(latest)) and prev <= 0 < latest
    improving = (not _isnan(delta)) and delta > 0
    # Absolute trough turning up: was falling, now rising.
    trough_up = (not _isnan(delta)) and (not _isnan(delta_prev)) and delta_prev < 0 < delta

    return {
        f"{prefix}_latest": latest,
        f"{prefix}_prev": prev,
        f"{prefix}_growth": growth,
        f"{prefix}_prev_growth": prev_growth,
        f"{prefix}_accel": accel,
        f"{prefix}_accel_abs": accel_abs,
        f"{prefix}_cagr": cagr(vals),
        f"{prefix}_turned_positive": turned_positive,
        f"{prefix}_improving": improving,
        f"{prefix}_trough_up": trough_up,
        f"{prefix}_n_periods": sum(1 for v in vals if not _isnan(v)),
    }


def _q_yoy_block(values: Sequence[float], prefix: str) -> dict:
    """Latest quarterly YoY growth (vₜ vs vₜ₋₄) and its acceleration."""
    vals = [_f(v) for v in values]
    n = len(vals)
    q_yoy = pct_growth(vals[-1], vals[-5]) if n >= 5 else NaN
    q_yoy_prev = pct_growth(vals[-2], vals[-6]) if n >= 6 else NaN
    q_accel = (q_yoy - q_yoy_prev) if not (_isnan(q_yoy) or _isnan(q_yoy_prev)) else NaN
    return {f"{prefix}_q_yoy": q_yoy, f"{prefix}_q_accel": q_accel}


def inflection_flags(m: dict) -> dict:
    """Per-name boolean inflection signals derived from the metric blocks.

    These are *cross-section-free* (no peer ranking) so they stay stable as the
    universe changes. The continuous inflection *score* (peer-ranked) is added
    later in :mod:`earnings_model.valuation`.
    """
    def truthy(key):
        return bool(m.get(key))

    rev_accel = m.get("revenue_accel", NaN)
    eps_accel = m.get("earnings_accel", NaN)
    ebitda_accel = m.get("ebitda_accel", NaN)

    revenue_inflecting = (
        truthy("revenue_trough_up")
        or (not _isnan(rev_accel) and rev_accel > 0 and (m.get("revenue_growth", NaN) or 0) > 0)
    )
    earnings_inflecting = (
        truthy("earnings_turned_positive")
        or truthy("earnings_trough_up")
        or (not _isnan(eps_accel) and eps_accel > 0 and (m.get("earnings_growth", NaN) or 0) > 0)
    )
    ebitda_inflecting = (
        truthy("ebitda_turned_positive")
        or truthy("ebitda_trough_up")
        or (not _isnan(ebitda_accel) and ebitda_accel > 0 and (m.get("ebitda_growth", NaN) or 0) > 0)
    )
    return {
        "revenue_inflecting": revenue_inflecting,
        "earnings_inflecting": earnings_inflecting,
        "ebitda_inflecting": ebitda_inflecting,
        # Composite: at least two of the three lines inflecting up.
        "broad_inflection": sum(
            [revenue_inflecting, earnings_inflecting, ebitda_inflecting]
        ) >= 2,
    }


def _ols_slope(ys: list) -> float:
    """Annualised linear trend (units of y per period) over an evenly-spaced series."""
    n = len(ys)
    if n < 2:
        return NaN
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else NaN


def _margin_series(rev: list, profit: list) -> list:
    """profit/revenue per period where both align and revenue is positive."""
    if len(rev) != len(profit) or not rev:
        return []
    return [profit[i] / rev[i] for i in range(len(rev)) if rev[i] > 0]


def margin_horizons(rev: list, profit: list, prefix: str) -> dict:
    """Margin level + change over short and LONG horizons (annual series).

    ``{prefix}_margin``        latest level
    ``{prefix}_margin_delta``  1-year change (pp)
    ``{prefix}_margin_delta3`` 3-year change
    ``{prefix}_margin_delta_full`` change over the whole window
    ``{prefix}_margin_slope``  annualised linear trend (pp/yr) — the robust
                               long-period expansion rate.
    """
    out = {f"{prefix}_margin": NaN, f"{prefix}_margin_delta": NaN,
           f"{prefix}_margin_delta3": NaN, f"{prefix}_margin_delta_full": NaN,
           f"{prefix}_margin_slope": NaN}
    m = _margin_series(rev, profit)
    if not m:
        return out
    out[f"{prefix}_margin"] = m[-1]
    if len(m) >= 2:
        out[f"{prefix}_margin_delta"] = m[-1] - m[-2]
        out[f"{prefix}_margin_delta_full"] = m[-1] - m[0]
    if len(m) >= 3:
        out[f"{prefix}_margin_delta3"] = m[-1] - m[-3]
        out[f"{prefix}_margin_slope"] = _ols_slope(m)
    return out


def q_margin_horizons(qrev: list, qprofit: list, prefix: str) -> dict:
    """SHORT-horizon margin from quarterly statements (catches the turn earliest).

    ``{prefix}_margin_q``       latest-quarter margin
    ``{prefix}_margin_q_delta`` QoQ change (vs previous quarter)
    ``{prefix}_margin_q_yoy``   vs the same quarter a year ago (de-seasonalised)
    """
    out = {f"{prefix}_margin_q": NaN, f"{prefix}_margin_q_delta": NaN,
           f"{prefix}_margin_q_yoy": NaN}
    m = _margin_series(qrev, qprofit)
    if not m:
        return out
    out[f"{prefix}_margin_q"] = m[-1]
    if len(m) >= 2:
        out[f"{prefix}_margin_q_delta"] = m[-1] - m[-2]
    if len(m) >= 5:
        out[f"{prefix}_margin_q_yoy"] = m[-1] - m[-5]
    return out


def forensic_block(annual: dict) -> dict:
    """Trajectory-quality + multi-horizon margin metrics from the annual series.

    Looks at the *shape* of the multi-year history, not just the latest growth
    number: revenue consistency (``rev_up_frac``), gross & EBITDA margin over
    short and long horizons (via :func:`margin_horizons`), operating leverage
    (``operating_leverage`` = degree of operating leverage, ΔEBITDA% / ΔRev%),
    and artifact guards (``ebitda_all_pos``, ``ebitda_lump``).
    """
    rev = [x for x in (_f(z) for z in (annual.get("revenue") or [])) if not _isnan(x)]
    eb = [x for x in (_f(z) for z in (annual.get("ebitda") or [])) if not _isnan(x)]
    gross = [x for x in (_f(z) for z in (annual.get("gross") or [])) if not _isnan(x)]

    out = {"rev_up_frac": NaN, "rev_cagr_n": NaN,
           "ebitda_all_pos": False, "ebitda_lump": False,
           "operating_leverage": NaN, "operating_leverage_full": NaN}
    out.update(margin_horizons(rev, gross, "gross"))
    out.update(margin_horizons(rev, eb, "ebitda"))
    # Back-compat alias used by the forensic screen.
    out["margin_delta3"] = out["ebitda_margin_delta3"]

    if len(rev) >= 3:
        diffs = [b - a for a, b in zip(rev[:-1], rev[1:])]
        out["rev_up_frac"] = sum(1 for d in diffs if d > 0) / len(diffs)
        if rev[0] > 0 and rev[-1] > 0:
            out["rev_cagr_n"] = (rev[-1] / rev[0]) ** (1 / (len(rev) - 1)) - 1

    out["ebitda_all_pos"] = len(eb) >= 3 and all(x > 0 for x in eb)
    if len(eb) >= 4:
        steps = [abs(b - a) for a, b in zip(eb[:-1], eb[1:])]
        prior = sorted(steps[:-1])
        med = prior[len(prior) // 2] if prior else 0.0
        out["ebitda_lump"] = bool(med > 0 and steps[-1] > 3 * med)

    # Operating leverage = degree of operating leverage (ΔEBITDA% / ΔRevenue%).
    # >1 means EBITDA grew faster than revenue (the cost base scaled) — positive
    # operating leverage; computed only where revenue actually moved and the
    # EBITDA base is positive (so the ratio is meaningful, not a sign artifact).
    if len(rev) >= 2 and len(eb) >= 2 and rev[-2] > 0 and eb[-2] > 0:
        rg = rev[-1] / rev[-2] - 1
        if abs(rg) > 0.02:
            out["operating_leverage"] = max(-10.0, min(10.0, (eb[-1] / eb[-2] - 1) / rg))
    if len(rev) >= 3 and len(eb) >= 3 and rev[0] > 0 and all(x > 0 for x in eb):
        rg = rev[-1] / rev[0] - 1
        if abs(rg) > 0.02:
            out["operating_leverage_full"] = max(-10.0, min(10.0, (eb[-1] / eb[0] - 1) / rg))
    return out


def compute_metrics(raw: dict) -> dict:
    """Flatten a raw fundamentals record into the per-name metric row.

    ``raw`` is the structure produced by :func:`earnings_model.fundamentals.fetch_raw`.
    """
    annual = raw.get("annual", {}) or {}
    quarterly = raw.get("quarterly", {}) or {}

    out: dict = {"symbol": raw.get("symbol")}
    out.update(metric_block(annual.get("revenue", []), "revenue"))
    out.update(metric_block(annual.get("ebitda", []), "ebitda"))
    out.update(metric_block(annual.get("earnings", []), "earnings"))
    out.update(_q_yoy_block(quarterly.get("revenue", []), "revenue"))
    out.update(_q_yoy_block(quarterly.get("earnings", []), "earnings"))
    out.update(_q_yoy_block(quarterly.get("ebitda", []), "ebitda"))
    out.update(inflection_flags(out))
    out.update(forensic_block(annual))
    # Short-horizon margins from the quarterly statement.
    qrev = [_f(x) for x in (quarterly.get("revenue") or [])]
    out.update(q_margin_horizons(qrev, [_f(x) for x in (quarterly.get("gross") or [])], "gross"))
    out.update(q_margin_horizons(qrev, [_f(x) for x in (quarterly.get("ebitda") or [])], "ebitda"))

    # Carry valuation + price + identity straight through.
    val = raw.get("valuation", {}) or {}
    for k, v in val.items():
        out[k] = v
    prices = raw.get("prices", {}) or {}
    for k in config.PRICE_FEATURE_KEYS:
        out[k] = prices.get(k, NaN)
    out["asof"] = raw.get("asof")
    return out
