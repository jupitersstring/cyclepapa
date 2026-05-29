"""
Ehlers 4-bandpass filters on crypto OHLCV.

Direct port of malikmck's Pine v5 "4 Ehlers Bandpass Filters" indicator,
applied to BOTH price (close) AND volume, on the daily and 90-minute
timeframes, with per-band zero-line cross detection for "inflection"
signals.

Recurrence (per Pine):
    a1 = 5 / flen
    a2 = 5 / slen
    PB[t] = (a1 - a2) * src[t]
          + (a2*(1 - a1) - a1*(1 - a2)) * src[t-1]
          + ((1 - a1) + (1 - a2)) * PB[t-1]
          - (1 - a1) * (1 - a2) * PB[t-2]

Default (flen, slen) pairs: (40, 60), (200, 300), (600, 900), (1200, 2400).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


DEFAULT_BANDS: List[Tuple[int, int]] = [
    (40,   60),     # band 1 — short cycle
    (200,  300),    # band 2 — medium
    (600,  900),    # band 3 — long
    (1200, 2400),   # band 4 — very long
]
BAND_NAMES = ("PB1", "PB2", "PB3", "PB4")

# A zero-line cross within the last CROSS_RECENCY bars counts as a
# "recent inflection" for the snapshot rank.
CROSS_RECENCY = 5


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def ehlers_bandpass(src: pd.Series, flen: int, slen: int) -> pd.Series:
    """Pine-faithful Ehlers bandpass filter for one (flen, slen) pair."""
    if len(src) == 0:
        return pd.Series([], index=src.index, dtype=float)
    a1 = 5.0 / flen
    a2 = 5.0 / slen
    c1 = a1 - a2
    c2 = a2 * (1 - a1) - a1 * (1 - a2)
    c3 = (1 - a1) + (1 - a2)
    c4 = (1 - a1) * (1 - a2)
    s = src.fillna(0).to_numpy(dtype=float)
    n = len(s)
    out = np.zeros(n)
    for i in range(n):
        prev1 = out[i - 1] if i >= 1 else 0.0
        prev2 = out[i - 2] if i >= 2 else 0.0
        prev_s = s[i - 1] if i >= 1 else 0.0
        out[i] = c1 * s[i] + c2 * prev_s + c3 * prev1 - c4 * prev2
    return pd.Series(out, index=src.index)


def four_bandpass(src: pd.Series, bands: List[Tuple[int, int]] = None) -> pd.DataFrame:
    """Apply all configured bandpass filters to a source series."""
    if bands is None:
        bands = DEFAULT_BANDS
    cols = {}
    for name, (flen, slen) in zip(BAND_NAMES, bands):
        cols[name] = ehlers_bandpass(src, flen, slen)
    return pd.DataFrame(cols)


# ---------------------------------------------------------------------------
# Snapshot signals
# ---------------------------------------------------------------------------


@dataclass
class BandSignals:
    """Zero-line snapshot for one source (price or volume) on one TF."""
    bands_above_zero: int
    bands_below_zero: int
    bull_cross_recent: int
    bear_cross_recent: int
    bull_cross_bands: List[int] = field(default_factory=list)
    bear_cross_bands: List[int] = field(default_factory=list)
    signs: List[int] = field(default_factory=list)        # +1/0/-1 per band
    last_values: List[float] = field(default_factory=list)


def band_signals(bands_df: pd.DataFrame, recency: int = CROSS_RECENCY) -> BandSignals:
    """
    Compute the latest-bar zero-line snapshot.

    - bands_above_zero / below_zero: count of bands currently above / below
      the zero line.
    - bull_cross_recent / bear_cross_recent: count of bands that crossed
      zero (in either direction) within the last `recency` bars.
    """
    signs: List[int] = []
    last_vals: List[float] = []
    bull_bands: List[int] = []
    bear_bands: List[int] = []
    for i, col in enumerate(bands_df.columns, start=1):
        s = bands_df[col].dropna()
        if len(s) == 0:
            signs.append(0); last_vals.append(0.0); continue
        last = float(s.iloc[-1])
        last_vals.append(last)
        signs.append(1 if last > 0 else (-1 if last < 0 else 0))
        if len(s) < 2:
            continue
        recent = s.tail(recency + 1).to_numpy()
        recent_signs = np.sign(recent)
        crossed_up = crossed_dn = False
        for j in range(1, len(recent_signs)):
            if recent_signs[j - 1] <= 0 and recent_signs[j] > 0:
                crossed_up = True
            elif recent_signs[j - 1] >= 0 and recent_signs[j] < 0:
                crossed_dn = True
        if crossed_up:
            bull_bands.append(i)
        if crossed_dn:
            bear_bands.append(i)
    return BandSignals(
        bands_above_zero=sum(1 for s in signs if s > 0),
        bands_below_zero=sum(1 for s in signs if s < 0),
        bull_cross_recent=len(bull_bands),
        bear_cross_recent=len(bear_bands),
        bull_cross_bands=bull_bands,
        bear_cross_bands=bear_bands,
        signs=signs,
        last_values=last_vals,
    )


# ---------------------------------------------------------------------------
# Per-TF compound: price + volume
# ---------------------------------------------------------------------------


@dataclass
class BandpassTF:
    """Both price and volume bandpass snapshots for one TF."""
    price: BandSignals
    volume: BandSignals
    price_net: int        # (above - below) + (bull_cross - bear_cross)
    volume_net: int
    combined_net: int


def bandpass_score(df: pd.DataFrame, *,
                   bands: Optional[List[Tuple[int, int]]] = None,
                   recency: int = CROSS_RECENCY) -> BandpassTF:
    """Compute price + volume bandpass signals for one OHLCV TF frame."""
    price = band_signals(four_bandpass(df["close"], bands), recency)
    volume = band_signals(four_bandpass(df["volume"], bands), recency)
    price_net = (price.bands_above_zero - price.bands_below_zero) + (price.bull_cross_recent - price.bear_cross_recent)
    vol_net = (volume.bands_above_zero - volume.bands_below_zero) + (volume.bull_cross_recent - volume.bear_cross_recent)
    return BandpassTF(
        price=price,
        volume=volume,
        price_net=price_net,
        volume_net=vol_net,
        combined_net=price_net + vol_net,
    )
