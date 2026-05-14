"""PEW archetype screener.

Hunts global clones of the "PEW setup":
  1. Negative EV, or trading below net cash
  2. Core business structurally outgrowing its industry
  3. Breakeven-to-profitable, so no cash burn
  4. High insider ownership
  5. Nascent high-margin platform / logistics / SaaS line as multi-bagger
     optionality
  6. Forgotten by the market (low analyst coverage, low volume, illiquid)

Backend: financedatabase for the universe + yfinance for fundamentals,
ownership and the business summary (used to keyword-detect the nascent
high-margin segment hint).

Usage:
    python pew_archetype.py --country Italy --max 0 --workers 3 \
        --out italian_pew.csv

Caveats:
  * "Outgrowing industry" is approximated as 3y revenue CAGR vs the
    universe median (industry-level peer sets are not reliably available
    via yfinance).
  * "Nascent platform/SaaS" is a keyword scan over the longBusinessSummary
    field. False positives are common; use the column as a starting point,
    not a verdict.
  * EV from yfinance can be wrong for tickers with stale share counts;
    we recompute net-cash position from the balance sheet directly.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd

# Reuse universe loader and helpers from the Yartseva script
from yartseva_db import (
    get_universe,
    INCOME_ALIASES,
    CASHFLOW_ALIASES,
    BALANCE_ALIASES,
    first_row,
    safe_div,
)


PLATFORM_KEYWORDS = [
    r"\bplatform\b", r"\bSaaS\b", r"\bsoftware as a service\b",
    r"\bmarketplace\b", r"\bcloud\b", r"\bsubscription\b",
    r"\bRecurring revenue\b", r"\brecurring revenue\b",
    r"\bAPI\b", r"\bdigital platform\b", r"\bnetwork effect\b",
    r"\b3PL\b", r"\bfulfillment\b", r"\bfulfilment\b",
    r"\blast[\- ]mile\b", r"\bdata platform\b",
    r"\bmonetiz", r"\bmonetis",
]

PLATFORM_PATTERN = re.compile("|".join(PLATFORM_KEYWORDS), re.IGNORECASE)


@dataclass
class PewRow:
    symbol: str
    name: str
    sector: str
    industry: str
    country: str
    currency: str
    market_cap: float
    enterprise_value: float
    cash_and_equivalents: float
    total_debt: float
    net_cash: float
    # Cheapness on net-cash basis
    net_cash_pct_mcap: float
    cash_pct_mcap: float
    cash_pct_ev: float
    ev_to_mcap: float
    negative_ev_flag: int
    below_net_cash_flag: int
    cash_gt_ev_flag: int
    balance_sheet_date: str
    # Graham
    ncav: float
    ncav_pct_mcap: float
    mcap_to_ncav: float
    graham_net_net_flag: int
    # Quality / health
    revenue_ttm: float
    ebitda_ttm: float
    ebitda_margin: float
    net_income_ttm: float
    is_breakeven_or_profitable: int
    fcf_ttm: float
    cash_runway_years: float    # cash / (-FCF) when burning, else inf
    # Growth
    rev_3y_cagr: float
    rev_5y_cagr: float
    outgrowing_universe: int    # 3y CAGR > universe median
    # Ownership
    insider_ownership_pct: float
    institution_ownership_pct: float
    # Forgotten-ness
    avg_daily_volume: float
    avg_dollar_volume: float
    n_analysts: float
    forgotten_score: float
    # Nascent platform / SaaS hint
    summary_excerpt: str
    platform_hits: int
    has_platform_hint: int
    # Composite
    pew_score: float
    notes: str


def _trailing_sum(series: Optional[pd.Series], n: int = 4) -> Optional[float]:
    if series is None or len(series) < n:
        return None
    vals = series.iloc[:n].astype(float)
    if vals.isna().any():
        return None
    return float(vals.sum())


def _annual_or_ttm(qseries, aseries):
    if qseries is not None and len(qseries) >= 4:
        v = _trailing_sum(qseries, 4)
        if v is not None:
            return v
    if aseries is not None and len(aseries) >= 1:
        v = aseries.iloc[0]
        if pd.notna(v):
            return float(v)
    return None


def _cagr(latest: Optional[float], earliest: Optional[float], periods: int) -> float:
    if latest is None or earliest is None or pd.isna(latest) or pd.isna(earliest):
        return np.nan
    if earliest <= 0 or latest <= 0:
        return np.nan
    if periods <= 0:
        return np.nan
    return (latest / earliest) ** (1.0 / periods) - 1.0


def fetch_pew(symbol: str, info_meta: dict) -> Optional[PewRow]:
    import yfinance as yf

    # Retry handful of times on transient yfinance rate-limit noise
    for attempt in range(4):
        try:
            t = yf.Ticker(symbol)
            qis = t.quarterly_income_stmt
            qcf = t.quarterly_cashflow
            qbs = t.quarterly_balance_sheet
            ais = t.income_stmt
            acf = t.cashflow
            abs_ = t.balance_sheet
            info = t.info or {}
            break
        except Exception as e:
            msg = str(e)
            transient = (
                "401" in msg or "429" in msg or "Crumb" in msg
                or "Too Many Requests" in msg or "Rate limit" in msg
                or "rate limit" in msg or "YFRateLimitError" in msg
            )
            if transient and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            return None
    else:
        return None

    if (qis is None or qis.empty) and (ais is None or ais.empty):
        return None

    def sort_cols(df):
        if df is None or df.empty:
            return df
        return df.reindex(sorted(df.columns, reverse=True), axis=1)

    qis, qcf, qbs = sort_cols(qis), sort_cols(qcf), sort_cols(qbs)
    ais, acf, abs_ = sort_cols(ais), sort_cols(acf), sort_cols(abs_)

    # Income / cashflow rows
    rev_q = first_row(qis, INCOME_ALIASES["revenue"])
    rev_a = first_row(ais, INCOME_ALIASES["revenue"])
    ebitda_q = first_row(qis, INCOME_ALIASES["ebitda"])
    ebitda_a = first_row(ais, INCOME_ALIASES["ebitda"])
    ni_q = first_row(qis, INCOME_ALIASES["net_income"])
    ni_a = first_row(ais, INCOME_ALIASES["net_income"])
    cfo_q = first_row(qcf, CASHFLOW_ALIASES["cfo"])
    cfo_a = first_row(acf, CASHFLOW_ALIASES["cfo"])
    fcf_q = first_row(qcf, CASHFLOW_ALIASES["fcf"])
    fcf_a = first_row(acf, CASHFLOW_ALIASES["fcf"])
    capex_q = first_row(qcf, CASHFLOW_ALIASES["capex"])
    capex_a = first_row(acf, CASHFLOW_ALIASES["capex"])

    if fcf_q is None and cfo_q is not None and capex_q is not None:
        idx = cfo_q.index.intersection(capex_q.index)
        fcf_q = cfo_q.reindex(idx).astype(float) + capex_q.reindex(idx).astype(float)
    if fcf_a is None and cfo_a is not None and capex_a is not None:
        idx = cfo_a.index.intersection(capex_a.index)
        fcf_a = cfo_a.reindex(idx).astype(float) + capex_a.reindex(idx).astype(float)

    rev_ttm = _annual_or_ttm(rev_q, rev_a)
    ebitda_ttm = _annual_or_ttm(ebitda_q, ebitda_a)
    ni_ttm = _annual_or_ttm(ni_q, ni_a)
    fcf_ttm = _annual_or_ttm(fcf_q, fcf_a)

    if rev_ttm is None or rev_ttm <= 0:
        return None

    # Multi-year revenue series for CAGR (annual)
    rev_3y_cagr = np.nan
    rev_5y_cagr = np.nan
    if rev_a is not None and len(rev_a) >= 4:
        latest, earliest = rev_a.iloc[0], rev_a.iloc[3]
        rev_3y_cagr = _cagr(float(latest) if pd.notna(latest) else None,
                            float(earliest) if pd.notna(earliest) else None, 3)
    if rev_a is not None and len(rev_a) >= 6:
        latest, earliest = rev_a.iloc[0], rev_a.iloc[5]
        rev_5y_cagr = _cagr(float(latest) if pd.notna(latest) else None,
                            float(earliest) if pd.notna(earliest) else None, 5)

    # Balance sheet: prefer quarterly for freshness, fall back to annual
    def first_with_fallback(qdf, adf, names):
        s = first_row(qdf, names) if qdf is not None else None
        if s is None or s.empty:
            s = first_row(adf, names) if adf is not None else None
        return s

    cash_row = first_with_fallback(qbs, abs_, BALANCE_ALIASES["cash"])
    debt_row = first_with_fallback(qbs, abs_, BALANCE_ALIASES["total_debt"])
    nd_row = first_with_fallback(qbs, abs_, BALANCE_ALIASES["net_debt"])

    cash_v = float(cash_row.iloc[0]) if (cash_row is not None and pd.notna(cash_row.iloc[0])) else np.nan
    debt_v = float(debt_row.iloc[0]) if (debt_row is not None and pd.notna(debt_row.iloc[0])) else np.nan
    nd_v = float(nd_row.iloc[0]) if (nd_row is not None and pd.notna(nd_row.iloc[0])) else np.nan
    if pd.isna(nd_v) and pd.notna(debt_v) and pd.notna(cash_v):
        nd_v = debt_v - cash_v
    net_cash = -nd_v if pd.notna(nd_v) else np.nan

    # Record latest BS as-of date for transparency
    bs_src = qbs if (qbs is not None and not qbs.empty) else abs_
    try:
        balance_sheet_date = str(bs_src.columns[0].date()) if (bs_src is not None and len(bs_src.columns)) else ""
    except Exception:
        balance_sheet_date = ""

    # Market cap / EV with recompute when yfinance info is stale or zero
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    market_cap = float(info.get("marketCap") or 0)
    if not market_cap and shares and price:
        try:
            market_cap = float(shares) * float(price)
        except Exception:
            market_cap = 0.0
    market_cap = market_cap if market_cap > 0 else np.nan

    yf_ev = info.get("enterpriseValue")
    if yf_ev and float(yf_ev) > 0:
        enterprise_value = float(yf_ev)
    elif pd.notna(market_cap) and pd.notna(nd_v):
        enterprise_value = float(market_cap) + float(nd_v)
    elif pd.notna(market_cap):
        enterprise_value = float(market_cap)
    else:
        enterprise_value = np.nan

    net_cash_pct_mcap = safe_div(net_cash, market_cap)
    cash_pct_mcap = safe_div(cash_v, market_cap)
    cash_pct_ev = safe_div(cash_v, enterprise_value) if (pd.notna(cash_v) and pd.notna(enterprise_value) and enterprise_value > 0) else np.nan
    ev_to_mcap = safe_div(enterprise_value, market_cap)
    negative_ev_flag = int(pd.notna(enterprise_value) and enterprise_value < 0)
    below_net_cash_flag = int(pd.notna(net_cash) and pd.notna(market_cap) and net_cash > market_cap)
    cash_gt_ev_flag = int(
        pd.notna(cash_pct_ev) and cash_pct_ev > 1.0
        and pd.notna(net_cash) and net_cash > 0
    )

    # NCAV: current assets - total liabilities (Graham)
    cur_assets = first_with_fallback(qbs, abs_, ["Current Assets", "Total Current Assets"])
    total_liab = first_with_fallback(qbs, abs_, ["Total Liabilities Net Minority Interest",
                                                  "Total Liab", "Total Liabilities"])
    ca_v = float(cur_assets.iloc[0]) if (cur_assets is not None and pd.notna(cur_assets.iloc[0])) else np.nan
    tl_v = float(total_liab.iloc[0]) if (total_liab is not None and pd.notna(total_liab.iloc[0])) else np.nan
    ncav = (ca_v - tl_v) if (pd.notna(ca_v) and pd.notna(tl_v)) else np.nan
    ncav_pct_mcap = safe_div(ncav, market_cap) if (pd.notna(ncav) and market_cap) else np.nan
    mcap_to_ncav = safe_div(market_cap, ncav) if (pd.notna(ncav) and ncav > 0 and market_cap) else np.nan
    graham_net_net_flag = int(
        pd.notna(mcap_to_ncav) and mcap_to_ncav > 0 and mcap_to_ncav < (2.0 / 3.0)
    )

    # Quality: breakeven-to-profitable. Accept positive EBITDA or NI within
    # a small loss band (NI/revenue > -3%).
    ebitda_margin = safe_div(ebitda_ttm, rev_ttm)
    if ebitda_ttm is not None and ebitda_ttm > 0:
        is_breakeven_or_profitable = 1
    elif ni_ttm is not None and rev_ttm is not None:
        is_breakeven_or_profitable = int((ni_ttm / rev_ttm) > -0.03)
    else:
        is_breakeven_or_profitable = 0

    # Cash runway: only meaningful when burning FCF
    cash_runway_years = np.inf
    if pd.notna(fcf_ttm) and fcf_ttm < 0 and pd.notna(cash_v) and cash_v > 0:
        cash_runway_years = float(cash_v / (-fcf_ttm))

    # Ownership
    insider = info.get("heldPercentInsiders")
    inst = info.get("heldPercentInstitutions")
    insider_ownership_pct = float(insider) if insider is not None else np.nan
    institution_ownership_pct = float(inst) if inst is not None else np.nan

    # Forgotten-ness
    avg_vol = info.get("averageVolume10days") or info.get("averageDailyVolume10Day") or info.get("averageVolume")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    avg_daily_volume = float(avg_vol) if avg_vol is not None else np.nan
    avg_dollar_volume = (avg_daily_volume * float(price)) if (pd.notna(avg_daily_volume) and price) else np.nan
    n_analysts = float(info.get("numberOfAnalystOpinions") or 0)
    # Forgotten score: high when low volume + few analysts. Cap inputs to avoid
    # blowups for super-illiquid micro caps.
    vol_term = 1.0 / (1.0 + (avg_dollar_volume or 0) / 1e6)  # decays as $/day rises
    cov_term = 1.0 / (1.0 + n_analysts)
    forgotten_score = 0.6 * vol_term + 0.4 * cov_term

    # Nascent platform/SaaS keyword scan
    summary = info.get("longBusinessSummary") or info.get("shortBusinessSummary") or ""
    matches = PLATFORM_PATTERN.findall(summary)
    platform_hits = len(matches)
    has_platform_hint = int(platform_hits >= 1)
    summary_excerpt = (summary[:300] + "...") if len(summary) > 300 else summary

    return PewRow(
        symbol=symbol,
        name=info_meta.get("name", info.get("shortName", "")),
        sector=info_meta.get("sector", info.get("sector", "")),
        industry=info_meta.get("industry", info.get("industry", "")),
        country=info_meta.get("country", info.get("country", "")),
        currency=info_meta.get("currency", info.get("currency", "")),
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        cash_and_equivalents=cash_v,
        total_debt=debt_v,
        net_cash=net_cash,
        net_cash_pct_mcap=net_cash_pct_mcap,
        cash_pct_mcap=cash_pct_mcap,
        cash_pct_ev=cash_pct_ev,
        ev_to_mcap=ev_to_mcap,
        negative_ev_flag=negative_ev_flag,
        below_net_cash_flag=below_net_cash_flag,
        cash_gt_ev_flag=cash_gt_ev_flag,
        balance_sheet_date=balance_sheet_date,
        ncav=ncav,
        ncav_pct_mcap=ncav_pct_mcap,
        mcap_to_ncav=mcap_to_ncav,
        graham_net_net_flag=graham_net_net_flag,
        revenue_ttm=rev_ttm if rev_ttm else np.nan,
        ebitda_ttm=ebitda_ttm if ebitda_ttm is not None else np.nan,
        ebitda_margin=ebitda_margin,
        net_income_ttm=ni_ttm if ni_ttm is not None else np.nan,
        is_breakeven_or_profitable=is_breakeven_or_profitable,
        fcf_ttm=fcf_ttm if fcf_ttm is not None else np.nan,
        cash_runway_years=cash_runway_years,
        rev_3y_cagr=rev_3y_cagr,
        rev_5y_cagr=rev_5y_cagr,
        outgrowing_universe=0,  # filled in after universe scan
        insider_ownership_pct=insider_ownership_pct,
        institution_ownership_pct=institution_ownership_pct,
        avg_daily_volume=avg_daily_volume,
        avg_dollar_volume=avg_dollar_volume,
        n_analysts=n_analysts,
        forgotten_score=forgotten_score,
        summary_excerpt=summary_excerpt,
        platform_hits=platform_hits,
        has_platform_hint=has_platform_hint,
        pew_score=np.nan,  # filled in after universe scan
        notes="",
    )


def _composite(row: PewRow, median_3y_cagr: float) -> tuple[float, str]:
    """Compute the PEW composite score and a notes string for a row."""

    # Each sub-score in [0,1]. Missing sub-scores are simply skipped.
    parts: dict[str, float] = {}

    # Cheapness: heavy reward for negative EV / below-net-cash; gradient via net cash %
    if pd.notna(row.net_cash_pct_mcap):
        # 0 at 0%, 1.0 at 100% net cash / mcap, capped
        parts["cheapness_net_cash"] = max(0.0, min(1.0, row.net_cash_pct_mcap))
    if row.negative_ev_flag:
        parts["negative_ev"] = 1.0
    if row.below_net_cash_flag:
        parts["below_net_cash"] = 1.0
    if getattr(row, "graham_net_net_flag", 0):
        parts["graham_net_net"] = 1.0

    # Quality
    parts["breakeven"] = float(row.is_breakeven_or_profitable)

    # Growth (outgrowing universe)
    if pd.notna(row.rev_3y_cagr) and pd.notna(median_3y_cagr):
        # Reward growth above median; cap at +30pp
        excess = max(-0.10, min(0.30, row.rev_3y_cagr - median_3y_cagr))
        parts["outgrowing"] = max(0.0, (excess + 0.10) / 0.40)

    # Insider alignment: reward >=10%, full credit at 30%+
    if pd.notna(row.insider_ownership_pct):
        parts["insider"] = max(0.0, min(1.0, (row.insider_ownership_pct - 0.05) / 0.25))

    # Forgotten / illiquid (forgotten_score is already 0..1)
    parts["forgotten"] = float(row.forgotten_score)

    # Platform / SaaS optionality (binary hint, weight modest because it's a
    # keyword scan, not a verdict)
    parts["platform_optionality"] = float(row.has_platform_hint)

    weights = {
        "cheapness_net_cash":   0.16,
        "negative_ev":          0.10,
        "below_net_cash":       0.10,
        "graham_net_net":       0.08,
        "breakeven":            0.13,
        "outgrowing":           0.13,
        "insider":              0.11,
        "forgotten":            0.10,
        "platform_optionality": 0.09,
    }

    total_w = sum(weights[k] for k in parts)
    score = (sum(weights[k] * v for k, v in parts.items()) / total_w) if total_w > 0 else np.nan

    note_parts = []
    if row.negative_ev_flag:
        note_parts.append("negative EV")
    if row.below_net_cash_flag:
        note_parts.append("below net cash")
    elif pd.notna(row.net_cash_pct_mcap) and row.net_cash_pct_mcap > 0.30:
        note_parts.append(f"net cash {row.net_cash_pct_mcap:.0%}")
    if row.is_breakeven_or_profitable:
        note_parts.append("profitable/breakeven")
    if row.outgrowing_universe:
        note_parts.append(f"outgrowing ({row.rev_3y_cagr:.0%})")
    if pd.notna(row.insider_ownership_pct) and row.insider_ownership_pct >= 0.20:
        note_parts.append(f"insider {row.insider_ownership_pct:.0%}")
    if row.forgotten_score > 0.6:
        note_parts.append("forgotten")
    if row.has_platform_hint:
        note_parts.append(f"platform/SaaS hint x{row.platform_hits}")
    if getattr(row, "graham_net_net_flag", 0):
        note_parts.append(f"Graham net-net (mcap {row.mcap_to_ncav:.2f}x NCAV)")
    if getattr(row, "cash_gt_ev_flag", 0):
        note_parts.append(
            f"cash > EV ({row.cash_pct_ev:.2f}x, net cash {row.net_cash_pct_mcap:.0%} mcap)"
        )

    return score, "; ".join(note_parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default="Italy",
                        help="comma-separated list of countries "
                             "(e.g. 'United States,United Kingdom,Germany,Italy')")
    parser.add_argument("--max", type=int, default=0, help="0 = all")
    parser.add_argument("--min-bucket", default="Nano Cap")
    parser.add_argument("--max-bucket", default="Mid Cap",
                        help="cap at smid by default — PEW setups are below the radar")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", default="pew_archetype.csv")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--min-pew-score", type=float, default=0.45,
                        help="filter when printing the shortlist")
    args = parser.parse_args()

    countries = [c.strip() for c in args.country.split(",") if c.strip()]
    print(f"[1/3] Loading {countries} universe (min={args.min_bucket}, max={args.max_bucket}) ...",
          file=sys.stderr)
    pieces = []
    for c in countries:
        sub = get_universe(country=c,
                           min_bucket=args.min_bucket,
                           max_bucket=args.max_bucket)
        sub = sub.copy()
        sub["_country"] = c
        pieces.append(sub)
        print(f"      {c}: {len(sub)}", file=sys.stderr)
    universe = pd.concat(pieces) if pieces else pd.DataFrame()
    print(f"      total universe = {len(universe)}", file=sys.stderr)
    if args.max > 0:
        universe = universe.head(args.max)
        print(f"      truncated to {len(universe)}", file=sys.stderr)

    rows: list[PewRow] = []
    start = time.time()
    partial = args.out + ".partial"
    csv_writer = None
    csv_file = None
    import csv as _csv
    try:
        csv_file = open(partial, "w", newline="")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(fetch_pew, sym, meta.to_dict()): sym
                for sym, meta in universe.iterrows()
            }
            done = 0
            for fut in as_completed(futures):
                sym = futures[fut]
                done += 1
                try:
                    row = fut.result()
                except Exception as e:
                    print(f"   {sym}: {e}", file=sys.stderr)
                    row = None
                if row is not None:
                    d = asdict(row)
                    if csv_writer is None:
                        csv_writer = _csv.DictWriter(csv_file, fieldnames=list(d.keys()))
                        csv_writer.writeheader()
                    csv_writer.writerow(d)
                    csv_file.flush()
                    rows.append(row)
                if done % 25 == 0:
                    print(f"      {done}/{len(universe)} done ({len(rows)} kept) "
                          f"elapsed {time.time()-start:.0f}s", file=sys.stderr)
    finally:
        if csv_file is not None:
            csv_file.close()

    if not rows:
        print("No rows produced.", file=sys.stderr)
        sys.exit(1)

    # Universe-relative growth: median 3y CAGR
    cagrs = [r.rev_3y_cagr for r in rows if pd.notna(r.rev_3y_cagr)]
    median_3y_cagr = float(np.median(cagrs)) if cagrs else np.nan

    # Compute outgrowing flag, score, notes
    for r in rows:
        if pd.notna(r.rev_3y_cagr) and pd.notna(median_3y_cagr):
            r.outgrowing_universe = int(r.rev_3y_cagr > median_3y_cagr)
        score, note = _composite(r, median_3y_cagr)
        r.pew_score = score
        r.notes = note

    df = pd.DataFrame([asdict(r) for r in rows])
    df = df.sort_values("pew_score", ascending=False, na_position="last")
    df.to_csv(args.out, index=False)
    print(f"\n[2/3] wrote {len(df)} rows -> {args.out}", file=sys.stderr)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 14)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    print(f"\nUniverse 3y revenue CAGR median: {median_3y_cagr:.1%}\n")

    print("=== TOP BY PEW COMPOSITE ===")
    cols = ["symbol", "name", "sector", "pew_score", "net_cash_pct_mcap",
            "negative_ev_flag", "below_net_cash_flag", "is_breakeven_or_profitable",
            "rev_3y_cagr", "insider_ownership_pct", "n_analysts",
            "forgotten_score", "has_platform_hint"]
    print(df.head(args.top)[cols].to_string(index=False))

    print("\n=== NEGATIVE EV / BELOW NET CASH ===")
    sub = df[(df["negative_ev_flag"] == 1) | (df["below_net_cash_flag"] == 1)]
    cols = ["symbol", "name", "sector", "market_cap", "enterprise_value",
            "net_cash", "net_cash_pct_mcap", "is_breakeven_or_profitable",
            "rev_3y_cagr", "pew_score", "notes"]
    print(sub.head(args.top)[cols].to_string(index=False) if len(sub) else "  (none)")

    print(f"\n=== PEW SHORTLIST (score >= {args.min_pew_score}) ===")
    short = df[df["pew_score"] >= args.min_pew_score]
    cols = ["symbol", "name", "sector", "pew_score", "net_cash_pct_mcap",
            "rev_3y_cagr", "insider_ownership_pct", "ebitda_margin",
            "has_platform_hint", "notes"]
    print(short.head(args.top)[cols].to_string(index=False) if len(short) else "  (none)")

    print("\n=== PLATFORM / SAAS HINTS (top platform_hits) ===")
    plat = df[df["has_platform_hint"] == 1].sort_values(
        ["platform_hits", "pew_score"], ascending=[False, False]
    )
    cols = ["symbol", "name", "sector", "platform_hits", "pew_score",
            "net_cash_pct_mcap", "rev_3y_cagr", "summary_excerpt"]
    print(plat.head(args.top)[cols].to_string(index=False) if len(plat) else "  (none)")

    print("\n=== GRAHAM NET-NETS (market_cap < 2/3 x NCAV) ===")
    nn = df[df["graham_net_net_flag"] == 1].sort_values("mcap_to_ncav")
    cols = ["symbol", "name", "sector", "market_cap", "ncav", "mcap_to_ncav",
            "cash_pct_mcap", "cash_pct_ev", "rev_3y_cagr",
            "is_breakeven_or_profitable", "pew_score", "notes"]
    print(nn.head(args.top)[cols].to_string(index=False) if len(nn) else "  (none)")

    print("\n=== CASH-RICH vs MARKET CAP (cash_pct_mcap > 0.3, sorted) ===")
    cash_sub = df[df["cash_pct_mcap"].fillna(0) > 0.3].sort_values("cash_pct_mcap", ascending=False)
    cols = ["symbol", "name", "sector", "market_cap", "cash_pct_mcap",
            "cash_pct_ev", "ncav_pct_mcap", "mcap_to_ncav",
            "is_breakeven_or_profitable", "pew_score"]
    print(cash_sub.head(args.top)[cols].to_string(index=False) if len(cash_sub) else "  (none)")

    print("\n=== CASH > EV (genuine: net cash > 0 AND cash > EV) ===")
    cev = df[df["cash_gt_ev_flag"] == 1].sort_values("cash_pct_ev", ascending=False)
    cols = ["symbol", "name", "sector", "balance_sheet_date", "market_cap",
            "enterprise_value", "net_cash", "cash_pct_ev", "net_cash_pct_mcap",
            "is_breakeven_or_profitable", "rev_3y_cagr", "pew_score", "notes"]
    print(cev.head(args.top)[cols].to_string(index=False) if len(cev) else "  (none)")

    print(f"\n[3/3] done in {time.time()-start:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
