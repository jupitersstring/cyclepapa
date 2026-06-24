"""Core screening logic — v3.

Changes vs screen_v2:

  * Recovery-rate matrix per NAV class (params.RECOVERY_RATE) feeds
    upside directly. Closure assumption removed.
        expected_total_return = recovery / (1 - discount) - 1
    With LISTED_CLEAN @ 0.97 this is barely different from the old
    closure math; with PRIVATE_EQUITY @ 0.70 it cuts the upside on a
    50% discount from 100% to ~40% (the SUPP.L correction the user
    pushed hardest on, now encoded).

  * Catalyst duration -> IRR. We rank on annualised expected return,
    not total. A wind-down at 80% over 30 months ranks alongside an
    activist at 20% over 9 months.

  * Catalyst weighting only enters once, multiplicatively at the end
    (expected_irr × setup_score). Removed from compute_score's
    inner product so we don't double-count.

  * Windowed directional volume — for each of the last 8 weekly bars
    compute signed vol_z weighted by where the close sat in its range:
        bar_signal = vol_z × (2 × (close-low)/(high-low) - 1)
    sum these for an 8-week accumulation/distribution scalar. The
    last-bar-only vol_z that previously drove BASE_ABSORBING missed
    the multi-week patterns we kept finding by hand (SEIT.L's
    1.85/0.94/1.95 across four weeks, GCP's 3.5 in March).

  * Base detection uses 5th/95th-percentile range instead of max/min
    so a single bad print or outlier candle doesn't terminate the
    backward walk. Min-length fake-base fallback removed — short
    bases are now flagged NO_BASE.

  * RECENT_SELLOFF replaces DISTRIBUTION_DRIVEN. With auto_adjust=True
    a -8% weekly bar is real selling, not a cap return. Keep the
    flag but stop hard-excluding — combined with a vol spike and
    washed MFI it's the CAPITULATION phase (the CHRY.L entry pattern).

  * POST_RERATING now tapers — a name up 16% with 80% closure left
    loses ~20% of the prize, not 100%.

  * Investability gates (market cap, daily traded value, gearing,
    ongoing charge) applied as a hard pre-score filter from
    params.INVESTABILITY_GATES.

  * Discount sanity-clamped to params.DISCOUNT_MIN/MAX.

  * Metadata pulled from metadata.load_universe() (single source of
    truth, validated, no duplicate-key bugs).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd

import metadata
import params


# ---------------------------------------------------------------------------
# Money flow index — kept here so screen_core is self-contained.

def money_flow_index(df: pd.DataFrame, period: int = 18) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    rmf = tp * df["Volume"]
    delta = tp.diff()
    pos = rmf.where(delta > 0, 0.0)
    neg = rmf.where(delta < 0, 0.0)
    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - 100 / (1 + ratio)


# ---------------------------------------------------------------------------

@dataclass
class ScreenResult:
    ticker: str
    error: str | None = None
    name: str | None = None
    isin: str | None = None

    # Catalyst / NAV / qualitative
    catalyst: str | None = None
    nav_quality: str | None = None

    # Prices
    last_close: float | None = None
    chg_13w_pct: float | None = None
    chg_26w_pct: float | None = None

    # Base
    base_start: pd.Timestamp | None = None
    base_length_weeks: int | None = None
    base_range_pct: float | None = None
    base_low: float | None = None
    base_high: float | None = None
    base_quantile_range_pct: float | None = None  # 5-95 pct range

    # Volume profile
    poc: float | None = None
    poc_distance_pct: float | None = None

    # Volume features (NEW)
    vol_z_last: float | None = None
    vol_z_8w_max: float | None = None
    vol_z_8w_bars_over_1p5: int | None = None
    directional_vol_8w: float | None = None  # signed sum, accumulation > 0
    # Daily-volume spike (intra-week signal that weekly bars smooth over)
    daily_vol_z_max_30d: float | None = None
    daily_vol_z_max_30d_date: str | None = None
    daily_vol_spike_directional: float | None = None  # signed by close-in-range
    has_daily_spike: bool = False

    # Distribution / sell-off (renamed)
    recent_selloff: bool = False
    selloff_max_drop_pct: float | None = None

    # MFI
    mfi: float | None = None
    mfi_rising: bool | None = None
    mfi_low_8w: float | None = None

    # Phase
    phase: str = "UNKNOWN"
    in_base: bool = False

    # Discount + recovery
    nav_discount_est: float | None = None
    discount_source: str | None = None
    recovery_rate: float | None = None
    expected_total_return: float | None = None

    # Catalyst probability + signal
    catalyst_prob_base: float | None = None
    catalyst_prob_signal_adj: float | None = None
    signal_score: float | None = None
    news_score: float | None = None
    rns_score: float | None = None
    rns_tr1: int | None = None
    rns_pdmr: int | None = None
    rns_winddown: int | None = None
    rns_tender: int | None = None
    rns_buyback: int | None = None
    # PDMR direction enrichment (body-fetched)
    rns_pdmr_buys: int | None = None
    rns_pdmr_sells: int | None = None
    pdmr_buy_gbp: float | None = None
    # TR-1 direction enrichment — material institutional adds + activist
    # holder identification (Saba / AVI / Boaz / etc.)
    rns_tr1_buys: int | None = None
    rns_tr1_sells: int | None = None
    rns_tr1_material_adds: int | None = None
    rns_tr1_activist_buys: int | None = None
    tr1_buy_total_pp: float | None = None
    activist_holders: str | None = None    # pipe-separated for CSV
    # Resolution composite — fresh-only "corporate-action imminent"
    resolution_score: float | None = None

    # Upside / IRR
    expected_duration_months: float | None = None
    expected_upside: float | None = None       # total return × prob
    expected_irr: float | None = None          # annualised

    # Setup score
    phase_score: float | None = None
    setup_score: float | None = None

    # Final
    composite_score: float | None = None

    # Investability gates
    gate_market_cap: bool | None = None
    gate_daily_value: bool | None = None
    gate_gearing: bool | None = None
    gate_ongoing_charge: bool | None = None
    investable: bool = True
    investability_reasons: list[str] = field(default_factory=list)

    # Historical discount context (informational)
    discount_3y_avg: float | None = None
    discount_52w_high: float | None = None
    discount_52w_low: float | None = None

    # NAV trajectory (informational + recovery-rate factor — two-sided)
    nav_tr_1y: float | None = None
    nav_tr_3y: float | None = None
    nav_penalty_applied: float | None = None   # multiplier (1.00 = none, >1.0 = growth bonus)

    # Peer-relative discount — sourced from AIC's sector aggregates
    discount_vs_sector_pp: float | None = None  # current - sector median, in pp
    aic_sector_code: str | None = None

    # Activist intelligence
    saba_ukit_member: bool = False    # in Saba's UK Investment Trusts ETF holdings

    # Time-since-announcement (committed wind-downs only)
    catalyst_age_months: float | None = None

    # Ranking sleeve tags
    in_setup_sleeve: bool = False        # passes setup gates + score
    in_fundamentals_sleeve: bool = False  # event catalyst + IRR alone
    in_micro_sleeve: bool = False         # gate-failed but catalyst alive
    micro_position_size_pct: float | None = None  # suggested cap


# ---------------------------------------------------------------------------
# Base detection (improved)

def detect_base(
    df: pd.DataFrame,
    max_lookback: int = 208,
    range_threshold: float = 0.30,
    min_length: int = 13,
    quantile_low: float = 0.25,
    quantile_high: float = 0.75,
) -> pd.DataFrame | None:
    """Walk backwards from the latest bar, growing the window while
    the IQR (25th-75th percentile) of closes divided by the median
    stays below threshold. IQR is robust to single outlier bars
    (one bar in five doesn't move 25/75 percentiles); we also
    require the trailing-edge bar's deviation from the running
    median to be within 2x threshold, so a fresh extreme bar still
    terminates the base. Returns None if no base ≥ min_length
    forms (no min-length fallback that fakes a base from trend data)."""
    n = len(df)
    if n < min_length:
        return None
    closes = df["Close"].to_numpy()
    end = n
    start = end - 1
    upper = max(0, n - max_lookback)
    while start > upper:
        candidate = start - 1
        window = closes[candidate:end]
        if len(window) < 3:
            start = candidate
            continue
        med = float(np.median(window))
        if med <= 0:
            break
        lo = float(np.quantile(window, quantile_low))
        hi = float(np.quantile(window, quantile_high))
        rng = (hi - lo) / med
        # IQR catches volatile rangebound bases. Old-vs-new mean check
        # catches slow trends that the IQR misses (a 50% decline over
        # 200 bars keeps the IQR moderate at every step). Take the
        # mean of the oldest 20% vs the newest 20% — if they differ
        # by more than threshold the base has shifted.
        n_w = len(window)
        if n_w >= 20:
            tile = max(3, n_w // 5)
            old_mean = float(np.mean(window[:tile]))
            new_mean = float(np.mean(window[-tile:]))
            drift = abs(new_mean - old_mean) / max(med, 1e-9)
        else:
            drift = 0.0
        if rng > range_threshold or drift > range_threshold:
            break
        start = candidate
    if end - start < min_length:
        return None
    return df.iloc[start:end]


def base_volume_profile(base: pd.DataFrame, bins: int = 60) -> float | None:
    if base.empty:
        return None
    lo = float(base["Low"].min())
    hi = float(base["High"].max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vols = np.zeros(bins)
    for low, high, vol in zip(base["Low"].to_numpy(), base["High"].to_numpy(),
                              base["Volume"].to_numpy()):
        if not (np.isfinite(low) and np.isfinite(high) and np.isfinite(vol)):
            continue
        if high <= low or vol <= 0:
            continue
        lo_idx = max(0, int(np.searchsorted(edges, low, side="right") - 1))
        hi_idx = min(bins - 1, int(np.searchsorted(edges, high, side="right") - 1))
        if hi_idx < lo_idx:
            continue
        nn = hi_idx - lo_idx + 1
        vols[lo_idx:hi_idx + 1] += vol / nn
    if vols.sum() <= 0:
        return None
    return float(centers[int(np.argmax(vols))])


# ---------------------------------------------------------------------------
# Volume features

def daily_vol_spike_features(
    daily: pd.DataFrame,
    *,
    lookback_days: int = 30,
    base_window: int = 90,
) -> tuple[float, str | None, float, bool]:
    """Scan daily bars for a single-bar volume spike inside the lookback
    window. Volume z-score is computed against the previous `base_window`
    daily bars. A daily vol_z >= 3.0 (or 2.0 with a strong directional
    close) counts as a spike.

    Returns (max_z, max_z_date_iso, signed_by_close_position, has_spike).
    """
    if daily is None or len(daily) < base_window + 5:
        return 0.0, None, 0.0, False
    vol = daily["Volume"].astype(float)
    high = daily["High"].astype(float)
    low = daily["Low"].astype(float)
    close = daily["Close"].astype(float)
    # Compute rolling stats up to the bar *before* each lookback bar
    tail = daily.tail(lookback_days)
    base_v = vol.iloc[-(lookback_days + base_window):-lookback_days]
    if len(base_v) < base_window // 2 or base_v.std() == 0:
        return 0.0, None, 0.0, False
    mean_v, std_v = float(base_v.mean()), float(base_v.std())
    max_z = 0.0
    max_z_dt = None
    signed = 0.0
    has_spike = False
    for ts, bar in tail.iterrows():
        v = float(bar["Volume"]); h = float(bar["High"]); l = float(bar["Low"]); c = float(bar["Close"])
        if not (v > 0 and h > l):
            continue
        z = (v - mean_v) / std_v
        pos = (c - l) / (h - l)
        direction = 2 * pos - 1
        if abs(z) > max_z:
            max_z = abs(z)
            max_z_dt = str(ts.date()) if hasattr(ts, "date") else str(ts)
            signed = z * direction
        # Spike criterion: vol_z >= 3 OR (vol_z >= 2 AND closing high half)
        if z >= 3.0:
            has_spike = True
        elif z >= 2.0 and direction > 0.2:
            has_spike = True
    return max_z, max_z_dt, signed, has_spike


def directional_vol_score(
    data: pd.DataFrame,
    base: pd.DataFrame,
    window: int = 8,
) -> tuple[float, int, float]:
    """For each of the last `window` bars compute signed vol_z weighted
    by where the close sat in its bar range. Returns
        (signed_sum, count_bars_with_abs_z_ge_1p5, max_abs_z).
    Positive sum = volume on up-closes (accumulation pattern).
    Negative sum = volume on down-closes (distribution pattern).
    """
    if len(data) < window or base.empty:
        return 0.0, 0, 0.0
    bv = base["Volume"].astype(float)
    if len(bv) < 5 or bv.std() == 0:
        return 0.0, 0, 0.0
    mean_v, std_v = bv.mean(), bv.std()
    tail = data.tail(window)
    signed_sum = 0.0
    count = 0
    max_abs = 0.0
    for _, bar in tail.iterrows():
        v = float(bar["Volume"])
        z = (v - mean_v) / std_v
        h = float(bar["High"])
        l = float(bar["Low"])
        c = float(bar["Close"])
        if h <= l:
            pos_in_range = 0.5
        else:
            pos_in_range = (c - l) / (h - l)
        direction = 2.0 * pos_in_range - 1.0  # -1 = close at low, +1 = close at high
        bar_signal = z * direction
        signed_sum += bar_signal
        if abs(z) >= 1.5:
            count += 1
        if abs(z) > max_abs:
            max_abs = abs(z)
    return signed_sum, count, max_abs


# ---------------------------------------------------------------------------
# Phase classifier (rewritten)

def classify_phase(
    *,
    in_base: bool,
    base_length_weeks: int | None,
    vol_z_last: float | None,
    vol_z_8w_max: float | None,
    directional_8w: float | None,
    chg_13w: float | None,
    last_close: float,
    base_high: float | None,
    base_low: float | None,
    recent_selloff: bool,
    mfi_low_8w: float | None,
    daily_vol_z_max_30d: float | None = None,
    daily_vol_spike_directional: float | None = None,
) -> str:
    # Hard-rerated names — but tapered, not zeroed
    if chg_13w is not None and chg_13w > 0.15:
        return "POST_RERATING"
    # No usable base
    if not in_base or base_length_weeks is None or base_length_weeks < 13:
        if chg_13w is not None and chg_13w < -0.15:
            return "DOWNTREND"
        return "NO_BASE"
    # CAPITULATION — selloff + vol spike + washed MFI = the CHRY pattern
    if (recent_selloff
        and (vol_z_8w_max or 0) >= 1.5
        and (mfi_low_8w or 100) <= 30):
        return "CAPITULATION"
    # Breakout — above base high on volume
    if (base_high
        and last_close > base_high * 1.03
        and (vol_z_last or 0) >= 2.0):
        return "BASE_BREAKOUT"
    # Absorption — three triggers, ANY one is enough:
    #   (i)  weekly directional sum >= 1.8 AND any 8-bar vol_z >= 1.5
    #        (the multi-week pattern: SEIT 1.85/0.94/1.95)
    #   (ii) a single daily-bar vol_z >= 3.0 in the last 30 days
    #        (the intra-week signature that weekly bars smooth over —
    #         a tender, block trade, or news-day surge)
    #   (iii) daily vol_z >= 2.0 with strong directional close
    weekly_abs = (directional_8w or 0) >= 1.8 and (vol_z_8w_max or 0) >= 1.5
    daily_spike = (
        (daily_vol_z_max_30d or 0) >= 3.0
        or ((daily_vol_z_max_30d or 0) >= 2.0
            and (daily_vol_spike_directional or 0) > 0.5)
    )
    if weekly_abs or daily_spike:
        return "BASE_ABSORBING"
    # Recent selloff in the base
    if recent_selloff:
        return "RECENT_SELLOFF"
    # Drifting down
    if chg_13w is not None and chg_13w < -0.08:
        return "BASE_DECLINING"
    return "BASE_QUIET"


# ---------------------------------------------------------------------------
# Scoring — decomposed

def _post_rerating_taper(chg_13w: float, target_total_return: float) -> float:
    """A name up X% has already realised some of the closure return.
    Return remaining-return fraction (0..1)."""
    if target_total_return <= 0:
        return 0.0
    realised = chg_13w / target_total_return
    return max(0.0, 1.0 - realised)


def compute_setup_score(r: ScreenResult) -> float:
    """Setup score = pure technicals (phase × POC × base length).
    Catalyst/NAV are NOT in here — they multiply at the end via
    expected_irr.

    POC-distance scaling uses the *full* base range (max-min) rather
    than the IQR (which is only ever a broken-base check). Using IQR
    as the edge in the previous version zeroed legitimate names where
    the price sat outside the middle 50% but still inside the base
    (SUPP.L, RMII.L, IEM.L all returned setup_score=0 on the live run
    because IQR < POC-distance).

    Phases where price moving off POC is the point (CAPITULATION, the
    just-broken-out BREAKOUT) bypass the POC penalty entirely — those
    phases are defined by the close being away from the centre."""
    if r.error or r.poc is None or r.last_close is None or r.base_length_weeks is None:
        return 0.0
    # Broken-base reject uses IQR — robust to single outlier bars
    iqr_range = r.base_quantile_range_pct
    if iqr_range is not None and iqr_range > 0.40:
        return 0.0
    phase_w = params.PHASE_WEIGHT.get(r.phase, 0.10)
    # POC weight depends on phase:
    if r.phase in ("CAPITULATION", "BASE_BREAKOUT"):
        # Price moving away from POC IS the signal — don't penalise.
        poc_w = 1.0
    else:
        pd_pct = r.poc_distance_pct or 1.0
        # Edge = full base width (max-min). Cap at 50% so a base with
        # a single outlier high doesn't get unreasonably generous
        # credit. Floor at 10% so very-tight bases aren't impossible
        # to score on.
        edge = max(min(r.base_range_pct or 0.10, 0.50), 0.10)
        poc_w = max(0.0, 1.0 - (pd_pct / edge))
    base_w = min(1.0, r.base_length_weeks / 52.0)
    return phase_w * poc_w * base_w


def nav_trajectory_penalty(navtr_1y: float | None) -> float:
    """Multiplier on recovery_rate based on 1-year NAV total return.
    A declining NAV means the discount-anchored upside is partly
    illusory — the NAV target is itself moving down."""
    if navtr_1y is None:
        return 1.0
    # NAVTR1Y from AIC is in percent (e.g. -15.5 means -15.5%)
    tr = navtr_1y / 100.0 if abs(navtr_1y) > 1.5 else navtr_1y
    # Interpolate the penalty table
    items = sorted(params.NAV_DECLINE_PENALTY.items())
    if tr >= items[-1][0]:
        return items[-1][1]
    for i in range(len(items) - 1):
        lo, lo_v = items[i]
        hi, hi_v = items[i + 1]
        if lo <= tr <= hi:
            if hi == lo:
                return lo_v
            f = (tr - lo) / (hi - lo)
            return lo_v + f * (hi_v - lo_v)
    return items[0][1]


def compute_recovery_upside(
    discount: float | None,
    nav_quality: str | None,
    navtr_1y: float | None = None,
) -> tuple[float, float, float]:
    """Returns (recovery_rate, expected_total_return, nav_penalty_applied).
    NAV trajectory adjusts the recovery rate downward when NAV is in
    decline (asset sales below book, ongoing write-downs)."""
    base_recovery = params.RECOVERY_RATE.get(nav_quality or "", params.DEFAULT_RECOVERY)
    penalty = nav_trajectory_penalty(navtr_1y)
    recovery = base_recovery * penalty
    if discount is None or discount >= 1.0:
        return recovery, 0.0, penalty
    target_per_unit_price = recovery / (1.0 - discount)
    expected_return = target_per_unit_price - 1.0
    return recovery, expected_return, penalty


def wind_down_age_adjustment(months_since_announcement: float | None,
                             catalyst: str | None) -> tuple[float, float]:
    """Returns (prob_multiplier, duration_multiplier) given how many
    months ago the wind-down / strategic-review was announced."""
    if (months_since_announcement is None
        or catalyst not in ("WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY",
                            "RETURN_OF_CAPITAL_LIVE")):
        return 1.0, 1.0
    curve = sorted(params.WIND_DOWN_AGE_CURVE.items())
    m = max(0.0, float(months_since_announcement))
    if m >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        lo, (lo_p, lo_d) = curve[i]
        hi, (hi_p, hi_d) = curve[i + 1]
        if lo <= m <= hi:
            if hi == lo:
                return lo_p, lo_d
            f = (m - lo) / (hi - lo)
            return lo_p + f * (hi_p - lo_p), lo_d + f * (hi_d - lo_d)
    return curve[0][1]


def annualise(total_return: float, months: float) -> float:
    """Convert a total return over `months` to an annualised IRR."""
    if months <= 0:
        return 0.0
    if 1.0 + total_return <= 0:
        return -1.0
    return (1.0 + total_return) ** (12.0 / months) - 1.0


# ---------------------------------------------------------------------------
# Investability gates

def check_micro_investability(
    aic_record: dict | None,
    catalyst: str | None,
) -> bool:
    """Micro-sleeve gate — even more permissive than the wind-down
    relaxed gates. Only applies to committed event catalysts."""
    if aic_record is None:
        return True   # non-UK: no constraint
    if catalyst not in (
        "WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY",
        "RETURN_OF_CAPITAL_LIVE", "STRATEGIC_REVIEW",
    ):
        return False
    g = params.MICRO_GATES
    mc = _as_float(aic_record.get("MarketCap")) or 0.0
    dv = _as_float(aic_record.get("AvgValTrd1M")) or 0.0
    ng = _as_float(aic_record.get("NetGearCum")) or 0.0
    oc = _as_float(aic_record.get("OngoingCharge"))
    if mc < g["min_market_cap_gbp_m"]:
        return False
    if dv < g["min_daily_value_gbp_m"]:
        return False
    if ng > g["max_net_gearing_pct"]:
        return False
    if oc is not None and oc > g["max_ongoing_charge"]:
        return False
    return True


def _as_float(v) -> float | None:
    """Coerce AIC field to float; return None on garbage. AIC's JSON
    occasionally returns strings ('—', 'n/a') for missing values; the
    naive `or 0` fallback then leaves the string in place and the
    downstream `<` comparison throws TypeError (the HOME.L bug)."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    import math
    if math.isnan(f):
        return None
    return f


def check_investability(
    ticker: str,
    aic_record: dict | None,
    catalyst: str | None = None,
) -> tuple[bool, list[str]]:
    """Apply hard gates from params.INVESTABILITY_GATES, with relaxed
    thresholds for committed-wind-down / return-of-capital classes
    (these are *meant* to be illiquid stubs — applying the default
    daily-value floor screens them out by construction)."""
    reasons: list[str] = []
    if aic_record is None:
        return True, reasons
    # Pick gate set based on catalyst class
    gates = dict(params.INVESTABILITY_GATES)
    if catalyst and catalyst in params.INVESTABILITY_GATES_BY_CATALYST:
        gates.update(params.INVESTABILITY_GATES_BY_CATALYST[catalyst])
    mc = _as_float(aic_record.get("MarketCap")) or 0.0
    if mc < gates["min_market_cap_gbp_m"]:
        reasons.append(f"market cap £{mc:.0f}m < £{gates['min_market_cap_gbp_m']:.0f}m")
    dv = _as_float(aic_record.get("AvgValTrd1M")) or 0.0
    if dv < gates["min_daily_value_gbp_m"]:
        reasons.append(f"daily value £{dv:.2f}m < £{gates['min_daily_value_gbp_m']:.2f}m")
    ng = _as_float(aic_record.get("NetGearCum"))
    if ng is not None and ng > gates["max_net_gearing_pct"]:
        reasons.append(f"net gearing {ng:.0f}% > {gates['max_net_gearing_pct']:.0f}%")
    oc = _as_float(aic_record.get("OngoingCharge"))
    if oc is not None and oc > gates["max_ongoing_charge"]:
        reasons.append(f"ongoing charge {oc:.2f}% > {gates['max_ongoing_charge']:.2f}%")
    return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# Discount sanity

def clamp_discount(d: float | None) -> float | None:
    if d is None:
        return None
    if d < params.DISCOUNT_MIN or d > params.DISCOUNT_MAX:
        # Out of band — likely data error; return None and let caller
        # fall back to estimate.
        return None
    return d
