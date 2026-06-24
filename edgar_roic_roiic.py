"""Extract multi-year ROIC / ROIIC / cash-on-cash / Lindy metrics from
the cached EDGAR XBRL companyfacts JSONs.

No new network calls — re-reads edgar_cache/CIK########.json files
produced by edgar_universe_extract.py.

Definitions:
  NOPAT_proxy ≈ OperatingIncome × (1 − 0.25 effective tax)
  Invested Capital (IC) = Equity + TotalDebt − Cash
  ROIC          = NOPAT / IC                                    (single year)
  ROIIC_1y      = ΔNOPAT / ΔIC                                  (one-year incremental)
  ROIIC_3y      = ΔNOPAT(3y) / ΔIC(3y)                          (smooths capex lumpiness)
  ROIIC_5y      = ΔNOPAT(5y) / ΔIC(5y)                          (Lindy — survives a cycle)
  Cash ROIC     = FCF / IC                                      (sidesteps accounting EBIT)
  Cash ROIIC_Ny = ΔFCF(Ny) / ΔIC(Ny)
  Lindy ROIC    = median ROIC over the last N annual prints
  Lindy ROIIC   = median rolling-N ROIIC over the available history

Inflections / accelerations:
  *_inflection_flag : metric crossed zero from below in the latest year
  *_acceleration    : Δ(year-N) − Δ(year-N−1)                   (delta-of-delta)

Each variant addresses a specific limitation of the others:
  - ROIIC_1y is timely but noisy (lumpy capex, base effects)
  - ROIIC_3y/5y smooth noise but lag inflections by one cycle
  - Cash ROIIC ignores non-cash accounting (D&A, accruals) — useful when
    op-income is distorted by acquisitions, write-downs or aggressive policy
  - Lindy median is robust to a single bad / good year — Mauboussin-style
    durability check

Composite (M5 — Multibagger Reinvestment Engine):
  Combines per-row z-scores of:
    - Lindy ROIIC_5y                  (durable reinvestment quality)
    - Cash ROIIC_5y                   (cash-confirmation of above)
    - ROIIC acceleration               (improvement signal)
    - 1 / (EV/EBITDA / ROIIC_5y)       (cheap per unit reinvestment yield)
  Reported on [0,1] for compatibility with our other composite scores.

Output: edgar_roic_roiic.csv (keyed by symbol).
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


CACHE_DIR = Path("edgar_cache")
EFFECTIVE_TAX = 0.25  # NOPAT proxy assumption

# Same alias chains as edgar_universe_extract.py
REVENUE_ALIASES = [
    "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
    "SalesRevenueNet", "SalesRevenueGoodsNet",
]
OPINCOME_ALIASES = ["OperatingIncomeLoss"]
EQUITY_ALIASES = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
CASH_ALIASES = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash",
]
LT_DEBT_ALIASES = ["LongTermDebtNoncurrent", "LongTermDebt"]
ST_DEBT_ALIASES = ["LongTermDebtCurrent", "ShortTermBorrowings"]
CFO_ALIASES = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_ALIASES = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
    "PaymentsToAcquireProductiveAssets",
]
ASSETS_ALIASES = ["Assets"]
DA_ALIASES = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization", "Depreciation",
]


def _fy_series(facts: dict, aliases: list[str], unit: str = "USD") -> pd.Series:
    """Build an annual time series indexed by fiscal-year end date.

    For each alias, gather FY observations, dedupe to one per fiscal year
    (keeping the latest filing if duplicates), and return as a sorted
    pd.Series."""
    rows = []
    seen_years = set()
    for c in aliases:
        info = facts.get("us-gaap", {}).get(c, {}).get("units", {}).get(unit, [])
        for obs in info:
            if obs.get("fp") != "FY":
                continue
            end = obs.get("end")
            fy = obs.get("fy")
            if end is None or fy is None:
                continue
            rows.append((fy, end, obs.get("val"), obs.get("filed")))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["fy", "end", "val", "filed"])
    # Keep the latest filing for each fiscal year (handles restatements)
    df = df.sort_values(["fy", "filed"]).drop_duplicates("fy", keep="last")
    df = df.sort_values("fy")
    return pd.Series(df.val.values, index=df.fy.values, name="val")


def _point_in_time_fy(facts: dict, aliases: list[str], unit: str = "USD") -> pd.Series:
    """Balance-sheet items: latest observation that falls on each fiscal
    year-end. Returns a per-fiscal-year series."""
    rows = []
    for c in aliases:
        info = facts.get("us-gaap", {}).get(c, {}).get("units", {}).get(unit, [])
        for obs in info:
            if obs.get("fp") != "FY":
                continue
            fy = obs.get("fy")
            if fy is None:
                continue
            rows.append((fy, obs.get("end"), obs.get("val"), obs.get("filed")))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["fy", "end", "val", "filed"])
    df = df.sort_values(["fy", "filed"]).drop_duplicates("fy", keep="last")
    return pd.Series(df.val.values, index=df.fy.values, name="val")


def compute_multi_year(facts: dict, n_years: int = 6) -> pd.DataFrame:
    """Return a per-fiscal-year DataFrame of derived metrics, last N years."""
    opinc = _fy_series(facts, OPINCOME_ALIASES)
    eq = _point_in_time_fy(facts, EQUITY_ALIASES)
    cash = _point_in_time_fy(facts, CASH_ALIASES)
    lt_d = _point_in_time_fy(facts, LT_DEBT_ALIASES)
    st_d = _point_in_time_fy(facts, ST_DEBT_ALIASES)
    cfo = _fy_series(facts, CFO_ALIASES)
    capex = _fy_series(facts, CAPEX_ALIASES)
    rev = _fy_series(facts, REVENUE_ALIASES)
    da = _fy_series(facts, DA_ALIASES)
    assets = _point_in_time_fy(facts, ASSETS_ALIASES)

    # Common index = union of all years available
    years = sorted(set(opinc.index) | set(eq.index))
    if not years:
        return pd.DataFrame()
    years = years[-n_years:]
    df = pd.DataFrame(index=years)
    df["opinc"] = opinc.reindex(years)
    df["equity"] = eq.reindex(years)
    df["cash"] = cash.reindex(years)
    df["lt_debt"] = lt_d.reindex(years)
    df["st_debt"] = st_d.reindex(years)
    df["cfo"] = cfo.reindex(years)
    df["capex"] = capex.reindex(years)
    df["revenue"] = rev.reindex(years)
    df["da"] = da.reindex(years)
    df["assets"] = assets.reindex(years)

    # Derived
    df["total_debt"] = df[["lt_debt", "st_debt"]].fillna(0).sum(axis=1)
    df["ic"] = df["equity"].fillna(0) + df["total_debt"] - df["cash"].fillna(0)
    df["nopat"] = df["opinc"] * (1 - EFFECTIVE_TAX)
    df["fcf"] = df["cfo"] - df["capex"]
    df["ebitda"] = df["opinc"].fillna(0) + df["da"].fillna(0)

    # Single-year ratios
    df["roic"] = np.where(df["ic"] > 0, df["nopat"] / df["ic"], np.nan)
    df["cash_roic"] = np.where(df["ic"] > 0, df["fcf"] / df["ic"], np.nan)
    df["asset_turnover"] = np.where(df["assets"] > 0, df["revenue"] / df["assets"], np.nan)
    return df


def lindy_aggregates(df: pd.DataFrame) -> dict:
    """Compute Lindy and inflection / acceleration metrics from a multi-year frame."""
    out = {}
    if df.empty or len(df) < 2:
        return out

    # Lindy single-year (median across history) - smooths anomalies
    out["roic_lindy"] = df["roic"].median()
    out["cash_roic_lindy"] = df["cash_roic"].median()
    out["roic_latest"] = df["roic"].iloc[-1]
    out["cash_roic_latest"] = df["cash_roic"].iloc[-1]

    # ROIIC = ΔNOPAT / ΔIC across windows
    def roiic_window(years: int, num_col: str, denom_col: str) -> float:
        if len(df) < years + 1:
            return np.nan
        d_num = df[num_col].iloc[-1] - df[num_col].iloc[-(years + 1)]
        d_den = df[denom_col].iloc[-1] - df[denom_col].iloc[-(years + 1)]
        ic_latest = df[denom_col].iloc[-1]
        # Guard: denominator must be (a) absolutely meaningful AND (b) at
        # least 5% of latest IC. ΔIC < 5% of IC is structural noise — the
        # business hasn't reinvested enough to compute a clean ROIIC.
        if (d_den is None or pd.isna(d_den) or abs(d_den) < 1e6
                or (ic_latest and ic_latest > 0 and abs(d_den) / ic_latest < 0.05)):
            return np.nan
        v = d_num / d_den
        # Clip to [-2, 2] — values outside that band are denominator artifacts
        if not -2.0 <= v <= 2.0:
            return np.nan
        return v

    out["roiic_1y"] = roiic_window(1, "nopat", "ic")
    out["roiic_3y"] = roiic_window(3, "nopat", "ic")
    out["roiic_5y"] = roiic_window(5, "nopat", "ic")
    out["cash_roiic_1y"] = roiic_window(1, "fcf", "ic")
    out["cash_roiic_3y"] = roiic_window(3, "fcf", "ic")
    out["cash_roiic_5y"] = roiic_window(5, "fcf", "ic")

    # Rolling ROIIC_3y series → Lindy = median of rolling windows
    rolling_roiic = []
    rolling_cash = []
    for i in range(3, len(df)):
        d_n = df["nopat"].iloc[i] - df["nopat"].iloc[i - 3]
        d_ic = df["ic"].iloc[i] - df["ic"].iloc[i - 3]
        if pd.notna(d_n) and pd.notna(d_ic) and abs(d_ic) >= 1e6:
            rolling_roiic.append(d_n / d_ic)
        d_f = df["fcf"].iloc[i] - df["fcf"].iloc[i - 3]
        if pd.notna(d_f) and pd.notna(d_ic) and abs(d_ic) >= 1e6:
            rolling_cash.append(d_f / d_ic)
    out["roiic_lindy"] = float(np.median(rolling_roiic)) if rolling_roiic else np.nan
    out["cash_roiic_lindy"] = float(np.median(rolling_cash)) if rolling_cash else np.nan

    # Inflections: latest ROIC crossed zero from below; latest ROIIC > 0
    if len(df) >= 2:
        prev = df["roic"].iloc[-2]
        curr = df["roic"].iloc[-1]
        out["roic_inflection_flag"] = int(
            pd.notna(prev) and pd.notna(curr) and prev <= 0 and curr > 0
        )
        out["cash_roic_inflection_flag"] = int(
            pd.notna(df["cash_roic"].iloc[-2])
            and pd.notna(df["cash_roic"].iloc[-1])
            and df["cash_roic"].iloc[-2] <= 0
            and df["cash_roic"].iloc[-1] > 0
        )
    out["roiic_1y_positive_flag"] = int(pd.notna(out.get("roiic_1y")) and out["roiic_1y"] > 0.10)
    out["cash_roiic_1y_positive_flag"] = int(
        pd.notna(out.get("cash_roiic_1y")) and out["cash_roiic_1y"] > 0.10
    )

    # Accelerations: ROIC delta-of-delta
    if len(df) >= 3:
        d_now = df["roic"].iloc[-1] - df["roic"].iloc[-2]
        d_prev = df["roic"].iloc[-2] - df["roic"].iloc[-3]
        if pd.notna(d_now) and pd.notna(d_prev):
            out["roic_acceleration"] = d_now - d_prev
        d_now_c = df["cash_roic"].iloc[-1] - df["cash_roic"].iloc[-2]
        d_prev_c = df["cash_roic"].iloc[-2] - df["cash_roic"].iloc[-3]
        if pd.notna(d_now_c) and pd.notna(d_prev_c):
            out["cash_roic_acceleration"] = d_now_c - d_prev_c

    # ROIIC acceleration: roiic_1y - roiic_3y (>0 = improvement in shorter window)
    if pd.notna(out.get("roiic_1y")) and pd.notna(out.get("roiic_3y")):
        out["roiic_acceleration"] = out["roiic_1y"] - out["roiic_3y"]
    if pd.notna(out.get("cash_roiic_1y")) and pd.notna(out.get("cash_roiic_3y")):
        out["cash_roiic_acceleration"] = out["cash_roiic_1y"] - out["cash_roiic_3y"]

    # Reinvestment runway proxy: asset growth (last 3y CAGR) — multibaggers
    # need a long runway, so growing-asset-base + high ROIIC is the engine.
    if len(df) >= 4 and df["assets"].iloc[-4] and df["assets"].iloc[-1]:
        try:
            a4 = float(df["assets"].iloc[-4])
            a0 = float(df["assets"].iloc[-1])
            if a4 > 0 and a0 > 0:
                out["asset_3y_cagr"] = (a0 / a4) ** (1 / 3) - 1
        except (ValueError, TypeError):
            pass

    # Revenue growth too — useful sanity check
    if len(df) >= 4 and pd.notna(df["revenue"].iloc[-4]) and pd.notna(df["revenue"].iloc[-1]):
        r4 = float(df["revenue"].iloc[-4])
        r0 = float(df["revenue"].iloc[-1])
        if r4 > 0 and r0 > 0:
            out["revenue_3y_cagr"] = (r0 / r4) ** (1 / 3) - 1

    return out


def cheap_per_roiic(ev_ebitda: float | None, roiic: float | None) -> float | None:
    """PEG-style: lower = cheaper relative to reinvestment yield."""
    if ev_ebitda is None or roiic is None or pd.isna(ev_ebitda) or pd.isna(roiic):
        return None
    if roiic <= 0:
        return None
    return ev_ebitda / (roiic * 100)  # roiic as percent for readability


def composite_engine_score(row: dict) -> float:
    """M5 — Multibagger Reinvestment Engine score [0,1].

    Composite of:
      - Lindy ROIIC_5y (durable reinvestment quality)
      - Cash ROIIC_5y (cash-confirmation)
      - ROIIC acceleration (recent improvement)
      - 1 / cheap_per_roiic (entry valuation per unit of reinvestment yield)

    Each subscore is clipped to a sensible band, then averaged across the
    present components — names with missing legs aren't penalised vs
    names with complete data.
    """
    parts = []

    # Lindy ROIIC: 0% -> 0.0, 50% -> 1.0. Saturates higher than the prior
    # 0.30 cap to differentiate genuinely durable compounders from one-cycle
    # anomalies.
    rl = row.get("roiic_lindy")
    if pd.notna(rl):
        parts.append(max(0.0, min(1.0, rl / 0.50)))
    # Cash Lindy: 0% -> 0.0, 40% -> 1.0  (cash is harder than NOPAT after capex)
    cl = row.get("cash_roiic_lindy")
    if pd.notna(cl):
        parts.append(max(0.0, min(1.0, cl / 0.40)))
    # ROIIC acceleration: -10pp -> 0.0, +20pp -> 1.0
    ra = row.get("roiic_acceleration")
    if pd.notna(ra):
        parts.append(max(0.0, min(1.0, (ra + 0.10) / 0.30)))
    # cheap-per-roiic inverted: smaller = better. 0.50 -> 1.0, 5.0 -> 0.0
    cpr = row.get("cheap_per_roiic_lindy")
    if pd.notna(cpr) and cpr > 0:
        parts.append(max(0.0, min(1.0, (5.0 - cpr) / 4.5)))
    # Penalty: deeply-negative latest ROIC says the engine isn't actually
    # turning, regardless of historical Lindy. Cap the score if ROIC < -0.10.
    rlatest = row.get("roic_latest")
    if pd.notna(rlatest) and rlatest < -0.10 and parts:
        return float(max(0.0, np.mean(parts) - 0.30))

    if not parts:
        return float("nan")
    return float(np.mean(parts))


def process_one(cik: int, symbol: str) -> dict:
    cache_path = CACHE_DIR / f"CIK{cik:010d}.json"
    if not cache_path.exists():
        return {"symbol": symbol, "cik": cik}
    try:
        data = json.loads(cache_path.read_text())
    except json.JSONDecodeError:
        return {"symbol": symbol, "cik": cik}
    if not data.get("facts", {}).get("us-gaap"):
        return {"symbol": symbol, "cik": cik}
    df = compute_multi_year(data["facts"])
    out = {"symbol": symbol, "cik": cik, "n_years": len(df)}
    out.update(lindy_aggregates(df))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edgar-facts", default="edgar_universe_facts.csv",
                    help="primary EDGAR table — used for ticker+CIK list and ev_ebitda")
    ap.add_argument("--out", default="edgar_roic_roiic.csv")
    args = ap.parse_args()

    print("loading EDGAR facts...", file=sys.stderr)
    edgar = pd.read_csv(args.edgar_facts, usecols=["symbol", "cik"])
    print(f"  {len(edgar):,} rows", file=sys.stderr)

    rows = []
    for _, r in edgar.iterrows():
        rows.append(process_one(int(r["cik"]), r["symbol"]))
    df = pd.DataFrame(rows)

    # Merge ev_ebitda from us_edgar_yartseva if present, otherwise compute
    # cheap_per_roiic from the raw EDGAR facts
    yart_path = "us_edgar_yartseva.csv"
    if Path(yart_path).exists():
        y = pd.read_csv(yart_path, usecols=["symbol", "ev_ebitda"])
        df = df.merge(y, on="symbol", how="left")
        df["cheap_per_roiic_lindy"] = df.apply(
            lambda r: cheap_per_roiic(r.get("ev_ebitda"), r.get("roiic_lindy")), axis=1
        )
        df["cheap_per_cash_roiic_lindy"] = df.apply(
            lambda r: cheap_per_roiic(r.get("ev_ebitda"), r.get("cash_roiic_lindy")), axis=1
        )
    else:
        df["cheap_per_roiic_lindy"] = np.nan
        df["cheap_per_cash_roiic_lindy"] = np.nan

    # Composite M5 score
    df["m5_engine_score"] = df.apply(lambda r: composite_engine_score(r.to_dict()), axis=1)

    df.to_csv(args.out, index=False)
    print(f"wrote {args.out}: {len(df):,} rows", file=sys.stderr)
    for c in ["roic_lindy", "cash_roic_lindy", "roiic_lindy", "cash_roiic_lindy",
              "roiic_acceleration", "cheap_per_roiic_lindy",
              "roic_inflection_flag", "roiic_1y_positive_flag",
              "asset_3y_cagr", "m5_engine_score"]:
        if c in df.columns:
            n = df[c].notna().sum()
            print(f"  {c:32s} {n:,} / {len(df):,} ({100*n/len(df):.1f}%)",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
