"""Unit-scale normalisation for per-period count series (shares, etc.).

Filers and data vendors sometimes switch the SCALE of a reported count mid-
series while keeping the declared unit: McDonald's tags its share counts as
732.3 (millions) from its FY2023 10-K on, after years of 741,300,000 (unit
"shares" both times); FMP carries Amcor's latest quarter as 464.6 against
463,800,000 the quarter before. A growth rate across that switch reads -99.9999%
— a data artifact, not a buyback.

normalize_scale() re-expresses a value in the series' dominant scale when it is
off from the series median by (almost exactly) a power of 1,000. This RESTORES
the true number (it is a unit conversion), it does not bound or clamp it: a
genuine 40% buyback or a 3x issuance is nowhere near a power of 1,000 and is
left untouched.
"""
from __future__ import annotations

import math

import numpy as np


SHARES_MIN = 1e5   # smallest plausible share count of a listed company


def normalize_shares(values):
    return normalize_scale(values, min_plausible=SHARES_MIN)


def normalize_scale(values, tol: float = 1.5, min_plausible: float | None = None):
    """Return a list with each positive value rescaled by 10**(3k) when that
    brings it within `tol`x of the series' reference scale (k != 0). NaN /
    non-positive values pass through.

    The reference is the median of the PLAUSIBLE values (>= min_plausible)
    when given — a listed company's share count is never below ~1e5, so values
    like 732.3 can only be counts in thousands / millions; this matters when
    half a series is in each scale (MCD), where a plain median sits between."""
    vals = [float(v) if v is not None else np.nan for v in values]
    pos = [v for v in vals if math.isfinite(v) and v > 0]
    if len(pos) < 2:
        return vals
    ref = [v for v in pos if min_plausible is None or v >= min_plausible] or pos
    lm = math.log10(float(np.median(ref)))
    out = []
    for v in vals:
        if not (math.isfinite(v) and v > 0):
            out.append(v)
            continue
        k = round((lm - math.log10(v)) / 3.0)
        if k != 0 and abs(math.log10(v) + 3 * k - lm) <= math.log10(tol):
            out.append(v * 10 ** (3 * k))
        else:
            out.append(v)
    return out
