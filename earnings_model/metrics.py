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

    # Carry valuation + price + identity straight through.
    val = raw.get("valuation", {}) or {}
    for k, v in val.items():
        out[k] = v
    prices = raw.get("prices", {}) or {}
    for k in config.PRICE_FEATURE_KEYS:
        out[k] = prices.get(k, NaN)
    out["asof"] = raw.get("asof")
    return out
