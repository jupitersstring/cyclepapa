"""Peer-ranked inflection, valuation richness and the earnings/valuation gap.

The headline output is ``gap_score``: high when a name's earnings are
inflecting/accelerating *yet* its valuation is cheap and its price hasn't
responded — i.e. exactly the "earnings inflecting, multiple not following"
setup. Ranks default to the **whole universe** (cross-sectional), which is the
right lens for "which industries are inflecting while valuations lag"; pass
``group_cols=("industry",)`` for sector-relative ranking instead.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Names that aren't ordinary operating equity (warrants, preferreds, depositary
# shares, units, rights, BDCs / closed-end vehicles) — excluded from an
# earnings screen. Catches the bulk of the US small-cap "non-stock" tail.
_NONOP_RE = re.compile(
    r"warrant|preferred|\bpfd\b|depositary|\brights?\b|\bunits?\b|\bbdc\b|%", re.I
)

# Preferred shares identified by TICKER SUFFIX rather than name: the ``-P<letter>``
# preferred-series notation (BAC-PL, JPM-PK, WFC-PY, EPR-PG, BMO-PE.TO, ...).
# yfinance labels these with the *issuer's* name ("Bank of America Corporation")
# and serves the issuer's statements, so they sail past the name filter and would
# otherwise get a phantom multiple — the parent company's EV/Sales attached to a
# preferred line. The pattern is dash-anchored (``-P`` + optional single letter +
# end-or-dot) so it matches only the preferred-series format, not ordinary tickers.
_NONOP_SYM_RE = re.compile(r"-P[A-Z]?(?:$|\.)")


def is_operating(df: pd.DataFrame, min_periods: int = 2) -> pd.Series:
    """Boolean mask: operating companies with a real income statement.

    Drops non-equity securities by name *and* by preferred-series ticker suffix,
    plus anything without >= ``min_periods`` of revenue history (closed-end funds,
    shells, most warrants/preferreds).
    """
    name = df["name"].fillna("") if "name" in df.columns else pd.Series("", index=df.index)
    sym = df["symbol"].fillna("") if "symbol" in df.columns else pd.Series("", index=df.index)
    name_ok = ~name.str.contains(_NONOP_RE)
    sym_ok = ~sym.str.upper().str.contains(_NONOP_SYM_RE)
    rev = (df["revenue_n_periods"] if "revenue_n_periods" in df.columns
           else pd.Series(0, index=df.index)).fillna(0)
    return name_ok & sym_ok & (rev >= min_periods)

# Signals where "higher = more inflecting / accelerating".
_ACCEL_SIGNALS = [
    "revenue_growth",
    "revenue_accel",
    "ebitda_accel_abs",
    "earnings_accel_abs",
    "revenue_q_yoy",
]
_INFLECTION_FLAGS = ["revenue_inflecting", "earnings_inflecting", "ebitda_inflecting"]

# Valuation multiples where "higher = more expensive". Non-positive values are
# masked (a negative P/E is not "cheap", it's not-meaningful).
_VALUATION_MULTIPLES = [
    "forwardPE",
    "trailingPE",
    "enterpriseToEbitda",
    "priceToSalesTrailing12Months",
    "priceToBook",
]


def _group_pct_rank(df: pd.DataFrame, col: str, group_cols=None, min_n: int = 3) -> pd.Series:
    """Percentile rank (0..1) of ``col``; global if ``group_cols`` is falsy.

    ``group_cols=None`` ranks across the whole universe — the right lens for the
    cross-sectional "earnings inflecting but valuation/price not responding"
    question. Pass e.g. ``("industry",)`` for sector-relative ranking instead.
    Thin samples (< ``min_n`` non-null) yield NaN so they fall back to neutral.
    """
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)

    def _rank(x: pd.Series) -> pd.Series:
        if x.notna().sum() < min_n:
            return pd.Series(np.nan, index=x.index)
        return x.rank(pct=True)

    if not group_cols or not all(c in df.columns for c in group_cols):
        return _rank(df[col])  # fall back to global if a group key is absent
    return df.groupby(list(group_cols), dropna=False)[col].transform(_rank)


def _mean_ignore_nan(frame: pd.DataFrame) -> pd.Series:
    """Row-wise mean ignoring NaN; all-NaN rows -> NaN (no warning)."""
    return frame.mean(axis=1, skipna=True)


def add_inflection_score(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``inflection_score`` (0..1): peer-ranked accel signals + flag bonus."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None

    rank_cols = []
    for sig in _ACCEL_SIGNALS:
        if sig in out.columns:
            rc = f"_rank_{sig}"
            out[rc] = _group_pct_rank(out, sig, group_cols)
            rank_cols.append(rc)
    accel_rank = _mean_ignore_nan(out[rank_cols]) if rank_cols else pd.Series(np.nan, index=out.index)

    flag_cols = [c for c in _INFLECTION_FLAGS if c in out.columns]
    if flag_cols:
        flag_bonus = out[flag_cols].astype(float).mean(axis=1, skipna=True)
    else:
        flag_bonus = pd.Series(np.nan, index=out.index)

    # 70% peer-ranked acceleration, 30% hard inflection flags.
    out["accel_rank"] = accel_rank
    out["inflection_flag_score"] = flag_bonus
    out["inflection_score"] = (
        0.7 * accel_rank.fillna(0.5) + 0.3 * flag_bonus.fillna(0.0)
    )
    out = out.drop(columns=rank_cols)
    return out


def add_valuation_richness(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``valuation_richness`` (0..1, higher = more expensive vs peers)."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None

    rank_cols = []
    for mult in _VALUATION_MULTIPLES:
        if mult not in out.columns:
            continue
        pos = out[mult].where(out[mult] > 0)  # mask non-positive multiples
        tmp = out.assign(_pos=pos)
        rc = f"_vrank_{mult}"
        out[rc] = _group_pct_rank(tmp, "_pos", group_cols)
        rank_cols.append(rc)

    out["valuation_richness"] = (
        _mean_ignore_nan(out[rank_cols]) if rank_cols else pd.Series(np.nan, index=out.index)
    )
    out["n_valuation_multiples"] = (
        out[rank_cols].notna().sum(axis=1) if rank_cols else 0
    )
    out = out.drop(columns=rank_cols)
    return out


def add_price_response(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``price_response`` (0..1): peer rank of trailing return (12m, else 6m)."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None
    base = "ret_12m" if "ret_12m" in out.columns else "ret_6m"
    out["price_response"] = _group_pct_rank(out, base, group_cols) if base in out.columns else np.nan
    return out


def add_gap_score(
    df: pd.DataFrame,
    group_cols=None,
    w_inflection: float = 0.5,
    w_cheap: float = 0.3,
    w_quiet: float = 0.2,
) -> pd.DataFrame:
    """Add the composite ``gap_score`` and its components.

    gap_score = w_inflection * inflection_score
              + w_cheap      * cheapness        (= 1 - valuation_richness)
              + w_quiet       * price_quiet      (= 1 - price_response)

    Missing cheapness / quietness fall back to a neutral 0.5 so a name is never
    rewarded or punished merely for missing valuation data.
    """
    out = df.copy()
    if "inflection_score" not in out.columns:
        out = add_inflection_score(out, group_cols)
    if "valuation_richness" not in out.columns:
        out = add_valuation_richness(out, group_cols)
    if "price_response" not in out.columns:
        out = add_price_response(out, group_cols)

    cheapness = (1.0 - out["valuation_richness"]).fillna(0.5)
    price_quiet = (1.0 - out["price_response"]).fillna(0.5)
    out["cheapness"] = cheapness
    out["price_quiet"] = price_quiet
    out["gap_score"] = (
        w_inflection * out["inflection_score"]
        + w_cheap * cheapness
        + w_quiet * price_quiet
    )
    return out


def add_growth_adjusted_value(df: pd.DataFrame, bv_weight: float = 0.2,
                              growth_cap: float = 0.50, growth_floor: float = 0.02) -> pd.DataFrame:
    """Growth-adjusted (PEG-style) valuation ratios. LOWER = cheaper per unit of
    growth. Inputs are currency-neutral (ratios / % growth) so they compare across
    markets. Defined for ~every name with a valuation multiple: growth is floored
    (below) so non-/negative-growers read *expensive* rather than NaN. The
    EBITDA-based ratios are NaN only for loss-makers (no honest EBITDA multiple);
    the sales-based ones (P/S fallback) then cover those.

    Two growth bases for each ratio:
      * ``ev_ebitda_g`` / ``ev_sales_g``         — latest **annual** (FY YoY) growth.
      * ``ev_ebitda_g_ltm`` / ``ev_sales_g_ltm`` — **LTM / near-term** (latest-quarter
        YoY) growth; sparser (~40% have quarterly data) but more current.

    Book-value tilt (``*_bv``): a gentle, bounded, *diminishing* reward for LOW
    price-to-book — ``tilt = 1 - w·(1-P/B)/(1+P/B)`` ∈ [1-w, 1+w], neutral at P/B=1.
    A low-P/B (asset-cheap) name gets a small discount that saturates as P/B→0 (so
    deep-discount names don't get unbounded credit); a high-P/B name gets a mild
    uplift. ``w`` (=``bv_weight``, default 0.2) keeps it a *minor* tilt, not the
    driver. Applied to the annual-growth ratios.

    ``ev_sales`` is reconstructed from consistent yfinance fields
    (priceToSales x enterpriseValue/marketCap) to avoid currency mismatches, then
    falls back to plain P/S and finally to a *self-computed* EV-or-marketCap /
    latest-annual-revenue for the residual names yfinance carries no pre-computed
    multiple for (the binding gap — almost every uncovered name simply lacks
    ``.info``'s priceToSales / enterpriseToEbitda). The self-computed P/S was
    validated currency-consistent against yfinance's where both exist (median ratio
    ~1.0; the residual spread is FY-vs-TTM revenue base, not currency).
    """
    out = df.copy()
    # Always an index-aligned Series (all-NaN when the column is absent) so every
    # ``.where`` below is well-defined even on a frame missing some valuation fields.
    num = lambda c: (pd.to_numeric(out[c], errors="coerce") if c in out.columns
                     else pd.Series(np.nan, index=out.index))
    ev_ebitda, psales = num("enterpriseToEbitda"), num("priceToSalesTrailing12Months")
    evv, mc, pb = num("enterpriseValue"), num("marketCap"), num("priceToBook")
    # Growth (%) in the denominator is FLOORED at growth_floor and CAPPED at
    # growth_cap. The cap stops a trough-rebound (+1000% off a near-zero base) from
    # driving the PEG to ~0; the floor means a no-/low-/negative-grower still gets a
    # (high = expensive) value instead of NaN — so the measure covers the universe,
    # not just positive growers. Missing annual growth falls back to the LTM (quarter)
    # rate before giving up.
    lo, hi = growth_floor * 100.0, growth_cap * 100.0
    clipg = lambda x: (x * 100.0).clip(lower=lo, upper=hi)
    # Primary ratios: annual growth, falling back to LTM (quarter), and finally to
    # the floor when NO growth can be measured at all — so a name with a valuation
    # multiple always gets a value (a no-growth-history name reads expensive, never
    # NaN). The _ltm variants stay strictly quarterly (sparser, genuinely near-term).
    eb_g = clipg(num("ebitda_growth").where(num("ebitda_growth").notna(), num("ebitda_q_yoy"))).fillna(lo)
    rev_g = clipg(num("revenue_growth").where(num("revenue_growth").notna(), num("revenue_q_yoy"))).fillna(lo)
    eb_gq, rev_gq = clipg(num("ebitda_q_yoy")), clipg(num("revenue_q_yoy"))
    earn_g = clipg(num("earnings_growth").where(num("earnings_growth").notna(), num("earnings_q_yoy"))).fillna(lo)
    earn_gq = clipg(num("earnings_q_yoy"))

    # Raw-statement fallback for the residual ~5%: rebuild the multiple ourselves
    # from market cap + the latest annual statement when yfinance carries no
    # pre-computed ratio. ``ev_or_mc`` uses enterpriseValue when present, else
    # market cap (the EV bridge only adds net debt — the same approximation the
    # plain-P/S fallback already makes). revenue_latest / ebitda_latest are the
    # latest *annual* FY levels, consistent with the annual growth denominators.
    rev_latest, eb_latest = num("revenue_latest"), num("ebitda_latest")
    ev_or_mc = evv.where(evv > 0, mc)
    # Currency guard. The only currency-NEUTRAL inputs are yfinance's dimensionless
    # ratios (priceToSales, enterpriseToEbitda); any reconstruction mixing
    # marketCap / EV / statement-revenue breaks when a name TRADES and REPORTS in
    # different currencies (e.g. Singapore-listed but IDR books) — and those are
    # disproportionately the names yfinance gives no pre-computed ratio for. We have
    # no per-field currency tag, so we (a) only trust the EV/mktcap leverage factor
    # when it is plausible leverage, else use plain P/S, and (b) reject an
    # implausibly *low* final multiple as a currency artifact (a 100x+ FX error
    # turns a ~1.0 ratio into ~0.001 — never a real "cheap"). Low, not high: a
    # broken-low value masquerades as the cheapest name; a broken-high one harmlessly
    # sorts to "expensive". PS_FLOOR/EV_FLOOR are well below any real operating
    # valuation (1% of sales / 0.3x EBITDA).
    PS_FLOOR, EV_FLOOR, LEV_LO, LEV_HI = 0.02, 0.3, 0.1, 10.0
    lev = (evv / mc).where((evv > 0) & (mc > 0))
    lev = lev.where((lev >= LEV_LO) & (lev <= LEV_HI))   # trust only plausible leverage

    ev_sales = (psales * lev).where(psales > 0)          # EV/Sales when leverage is sound
    # Fall back to plain P/S when the leverage factor is missing/implausible, so the
    # sales-based measure covers ~every name with a price-to-sales (plain P/S is
    # currency-neutral; the EV bridge only adds net debt — a close proxy anyway).
    ev_sales = ev_sales.where(ev_sales.notna(), psales.where(psales > 0))
    # Final fallback: self-computed EV-or-mktcap / latest annual revenue, recovering
    # names yfinance gives no priceToSales for (validated ~1.0x vs yfinance's P/S
    # where both exist).
    self_evs = (ev_or_mc / rev_latest).where((rev_latest > 0) & (ev_or_mc > 0))
    ev_sales = ev_sales.where(ev_sales.notna(), self_evs)
    ev_sales = ev_sales.where(ev_sales >= PS_FLOOR)      # drop currency artifacts
    out["ev_sales"] = ev_sales
    # EV/EBITDA: yfinance ratio when positive, else reconstruct EV-or-mktcap / latest
    # EBITDA (recovers names yfinance didn't carry the ratio for, including those
    # missing enterpriseValue; loss-making EBITDA stays NaN — there is no honest
    # EBITDA multiple for it, ev_sales_g covers those).
    eve = ev_ebitda.where(ev_ebitda > 0)
    eve = eve.where(eve.notna(), (ev_or_mc / eb_latest).where((eb_latest > 0) & (ev_or_mc > 0)))
    eve = eve.where(eve >= EV_FLOOR)                      # drop currency artifacts
    out["ev_ebitda_g"] = eve / eb_g
    out["ev_ebitda_g_ltm"] = eve / eb_gq
    out["ev_sales_g"] = ev_sales / rev_g
    out["ev_sales_g_ltm"] = ev_sales / rev_gq

    # Gentle, bounded, diminishing reward for LOW price-to-book.
    tilt = (1.0 - bv_weight * (1.0 - pb) / (1.0 + pb)).where(pb > 0)
    out["bv_tilt"] = tilt
    out["ev_ebitda_g_bv"] = out["ev_ebitda_g"] * tilt
    out["ev_sales_g_bv"] = out["ev_sales_g"] * tilt

    # Earnings-based PEG (P/E ÷ earnings-growth) — the right growth-adjusted value
    # lens for FINANCIALS (banks/insurers/capital markets), where EV/EBITDA and
    # EV/Sales are not meaningful: deposits and float distort enterprise value and
    # there is no clean operating "sales" line. Trailing P/E (fallback forward),
    # positive only; earnings growth capped/floored exactly like the EV ratios so a
    # trough-rebound can't drive it to ~0 and a non-grower reads expensive, not NaN.
    pe = num("trailingPE").where(num("trailingPE") > 0, num("forwardPE"))
    pe = pe.where(pe > 0)
    out["pe_g"] = pe / earn_g
    out["pe_g_ltm"] = pe / earn_gq
    return out


def add_all_scores(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Convenience: inflection + valuation + price + gap in one pass."""
    out = add_inflection_score(df, group_cols)
    out = add_valuation_richness(out, group_cols)
    out = add_price_response(out, group_cols)
    out = add_gap_score(out, group_cols)
    out = add_growth_adjusted_value(out)
    return out


def valuation_gap_table(df: pd.DataFrame, top: int | None = 30, min_n_periods: int = 2,
                        quality: bool = True) -> pd.DataFrame:
    """Ranked 'earnings inflecting but valuation lagging' shortlist.

    ``quality=True`` restricts to operating companies (see :func:`is_operating`).
    """
    cols = [
        "symbol", "name", "industry", "size_bucket",
        "gap_score", "inflection_score", "valuation_richness", "price_response",
        "revenue_growth", "revenue_accel", "earnings_growth", "earnings_accel_abs",
        "ebitda_accel_abs", "forwardPE", "enterpriseToEbitda",
        "priceToSalesTrailing12Months", "ret_12m", "broad_inflection",
    ]
    work = df[is_operating(df, min_n_periods)] if quality else df
    work = work.sort_values("gap_score", ascending=False)
    present = [c for c in cols if c in work.columns]
    out = work[present]
    return out.head(top) if top else out
