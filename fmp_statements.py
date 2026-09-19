"""Global statement-history engine -> fmp_statements.csv.

The dominant reach win from the deep examination: the entire quality/compounder
theme and much of the forensic theme gate on multi-year metrics
(`roic_lindy`, `roiic_lindy`, `n_yrs_positive_*`, `equity_cagr_5y`,
`op_margin_lindy`, `shares_growth_3y/5y`, `capital_return_yield`,
`buyback_yield`, `sbc_pct_revenue`, `effective_tax_rate`, owner earnings) that
are computed today only from `edgar_cache/CIK*.json` — SEC filers, US only. So
~29k non-US names fall to a degraded single-year fallback.

FMP already computes the per-year primitives we need:
  * `key-metrics?period=annual`  -> returnOnInvestedCapital, investedCapital,
    incomeQuality, freeCashFlowYield, netDebtToEBITDA, stockBasedCompensationToRevenue,
    researchAndDevelopementToRevenue, returnOnCapitalEmployed per fiscal year.
  * `ratios?period=annual`       -> operatingProfitMargin, ebitdaMargin,
    effectiveTaxRate, dividendPayoutRatio, bookValuePerShare, priceToBook.
  * `income-statement?period=annual` -> revenue, operatingIncome, netIncome,
    grossProfit, weightedAverageShsOutDil (the audited diluted-share path).
  * `cash-flow-statement?period=annual` -> operatingCashFlow, freeCashFlow,
    capitalExpenditure, commonStockRepurchased, commonDividendsPaid,
    netStockIssuance, netCashProvidedByFinancingActivities, stockBasedCompensation.
  * `owner-earnings` -> ownersEarnings, maintenanceCapex (Buffett owner earnings).

So the EDGAR-only lindy/streak/capital-return columns are a straight
AGGREGATION of FMP per-year values — no NOPAT reconstruction guesswork. This
module computes the global equivalents, `fmp_st_`-prefixed, as a secondary
source. Nothing here overwrites an EDGAR-primary value; the archetype layer
decides where an `fmp_st_` column may fill a NaN (an EDGAR-only column, for
the names EDGAR does not cover) — validated against the methodology audit.

Resumable: checkpoints to CSV every N symbols; already-done symbols skipped.
"""
from __future__ import annotations

import argparse
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_statements.csv"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _by_year(rows, field):
    """{fiscalYear: value} newest-first list of (year,value), finite only."""
    out = []
    for r in rows or []:
        y = _f(r.get("fiscalYear") or (r.get("date", "")[:4] if r.get("date") else None))
        v = _f(r.get(field))
        if math.isfinite(y) and math.isfinite(v):
            out.append((int(y), v))
    out.sort(key=lambda t: -t[0])
    return out


def _median(vals):
    vals = [v for v in vals if math.isfinite(v)]
    return float(np.median(vals)) if vals else np.nan


def _cagr(series):
    """series = newest-first [(year, level)]; CAGR endpoint-to-endpoint."""
    s = [(y, v) for y, v in series if math.isfinite(v)]
    if len(s) < 2:
        return np.nan
    (y0, v0), (yN, vN) = s[0], s[-1]
    span = max(1, y0 - yN)
    if v0 <= 0 or vN <= 0:
        return np.nan
    return (v0 / vN) ** (1.0 / span) - 1.0


def enrich_symbol(sym: str) -> dict:
    km = fc.get_json("key-metrics", {"symbol": sym, "period": "annual", "limit": 8}, ttl=fc.TTL_FUNDAMENTAL)
    ra = fc.get_json("ratios", {"symbol": sym, "period": "annual", "limit": 8}, ttl=fc.TTL_FUNDAMENTAL)
    isr = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 8}, ttl=fc.TTL_FUNDAMENTAL)
    cf = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 8}, ttl=fc.TTL_FUNDAMENTAL)
    oe = fc.get_json("owner-earnings", {"symbol": sym, "limit": 6}, ttl=fc.TTL_FUNDAMENTAL)
    rec: dict = {"symbol": sym}

    # ---- multi-year returns (lindy = median of the per-year series) ----
    roic = _by_year(km, "returnOnInvestedCapital")
    roce = _by_year(km, "returnOnCapitalEmployed")
    if roic:
        rec["fmp_st_roic_lindy"] = _median([v for _, v in roic])
        rec["fmp_st_n_yrs_positive_roic"] = float(sum(1 for _, v in roic if v > 0))
        rec["fmp_st_years_of_history"] = float(len(roic))
    if roce:
        rec["fmp_st_roce_lindy"] = _median([v for _, v in roce])

    # ROIIC lindy: ΔNOPAT / ΔInvestedCapital across the window, from FMP's own
    # investedCapital and an operating-income x (1 - effective tax) NOPAT.
    ic = dict(_by_year(km, "investedCapital"))
    op = dict(_by_year(isr, "operatingIncome"))
    tax = dict(_by_year(ra, "effectiveTaxRate"))
    yrs = sorted(set(ic) & set(op), reverse=True)
    if len(yrs) >= 4:
        def _nopat(y):
            t = tax.get(y, np.nan)
            t = t if (math.isfinite(t) and 0 <= t < 0.6) else 0.25
            return op[y] * (1 - t)
        y0, yN = yrs[0], yrs[min(3, len(yrs) - 1)]
        d_ic = ic[y0] - ic[yN]
        # ROIIC only means something when capital was actually DEPLOYED: a
        # capital-returner shrinks invested capital (buybacks), so ΔIC<=0 gives
        # a spurious huge/negative ratio (AAPL endpoint ROIIC was -6.8). Require
        # meaningful positive deployment; capital-returners get NaN (correct —
        # their thesis is return, not reinvestment).
        if math.isfinite(d_ic) and d_ic > 0.05 * abs(ic[yN] or 1):
            rec["fmp_st_roiic_lindy"] = (_nopat(y0) - _nopat(yN)) / d_ic

    # ---- margins held over the window (lindy) ----
    opm = _by_year(ra, "operatingProfitMargin")
    ebm = _by_year(ra, "ebitdaMargin")
    if opm:
        rec["fmp_st_op_margin_lindy"] = _median([v for _, v in opm])
    if ebm:
        rec["fmp_st_ebitda_margin_lindy"] = _median([v for _, v in ebm])

    # ---- durability counts from cash-flow / income ----
    fcf = _by_year(cf, "freeCashFlow")
    opinc = _by_year(isr, "operatingIncome")
    if fcf:
        rec["fmp_st_n_yrs_positive_fcf"] = float(sum(1 for _, v in fcf if v > 0))
    if opinc:
        rec["fmp_st_n_yrs_positive_opinc"] = float(sum(1 for _, v in opinc if v > 0))

    # ---- growth / dilution ----
    rec_rev = _by_year(isr, "revenue")
    if len(rec_rev) >= 2:
        rec["fmp_st_revenue_cagr"] = _cagr(rec_rev)
    eq = _by_year(ra, "bookValuePerShare")
    if len(eq) >= 2:
        rec["fmp_st_equity_cagr"] = _cagr(eq)
    sh = _by_year(isr, "weightedAverageShsOutDil")
    if len(sh) >= 2:
        # newest-first; growth over up to 3 and 5 year spans
        def _sh_growth(n):
            s = [(y, v) for y, v in sh if math.isfinite(v) and v > 0]
            if len(s) <= n:
                return np.nan
            return s[0][1] / s[n][1] - 1.0
        rec["fmp_st_shares_growth_3y"] = _sh_growth(3)
        rec["fmp_st_shares_growth_5y"] = _sh_growth(min(5, len(sh) - 1))

    # ---- capital return (audited multi-year cash-flow history) ----
    # CURRENCY-CONSISTENCY GUARD. A yield divides a cash-flow amount (in the
    # statement's reportedCurrency) by market cap (key-metrics.marketCap). For
    # most names these agree, but for ADRs / cross-listings FMP sometimes carries
    # the market cap in the LISTING currency while the statements are in the
    # reporting currency (e.g. SEBNF: mcap ~$2B tagged JPY, buybacks 51B local)
    # — dividing across currencies inflates the yield ~150x and manufactures an
    # economically impossible "26x buyback yield". Market cap and revenue are
    # denominated the same way, so a mcap/revenue ratio far outside the normal
    # [0.02, 100] band signals the mismatch; we then withhold the yield columns
    # (the dimensionless ratios above are currency-invariant and stay valid).
    # Per-year market cap (key-metrics) and revenue (income), so each year's
    # capital return is measured against THAT year's market cap — currency- and
    # era-consistent. Using the current market cap for a 3-year average of
    # returns manufactures a false yield for names whose cap collapsed (e.g.
    # LNZA, a de-SPAC down ~60x: an old distribution over today's tiny cap read
    # as a 760% yield). A per-year coherence check (mcap_y/revenue_y in a normal
    # band) drops the ADR/cross-listing currency mismatches (e.g. SEBNF).
    _mc_y = dict(_by_year(km, "marketCap"))
    _rev_y = dict(_by_year(isr, "revenue"))
    _buyb_y = dict(_by_year(cf, "commonStockRepurchased"))
    _div_y = dict(_by_year(cf, "commonDividendsPaid"))

    def _coherent(y):
        m, r = _mc_y.get(y, np.nan), _rev_y.get(y, np.nan)
        return math.isfinite(m) and math.isfinite(r) and r > 0 and 0.02 <= m / r <= 100 and m > 0

    _cap_yields, _buyb_yields, _div_yields = [], [], []
    for y in sorted(set(_mc_y) & (set(_buyb_y) | set(_div_y)), reverse=True)[:3]:
        if not _coherent(y):
            continue
        m = _mc_y[y]
        b = abs(_buyb_y.get(y, 0.0) or 0.0) / m
        d = abs(_div_y.get(y, 0.0) or 0.0) / m
        _buyb_yields.append(b); _div_yields.append(d); _cap_yields.append(b + d)
    if _cap_yields:
        rec["fmp_st_buyback_yield"] = float(np.median(_buyb_yields))
        rec["fmp_st_dividend_yield_cf"] = float(np.median(_div_yields))
        rec["fmp_st_capital_return_yield"] = float(np.median(_cap_yields))

    # CURRENCY-INVARIANT capital-return signal: total capital returned as a
    # fraction of net income (both in the reporting currency), so it is immune
    # to the ADR/listing-currency market-cap mismatch that corrupts every
    # yield. This is the reliable global capital-allocation signal.
    # These are ratios to net income, so the archetype layer can recover a
    # currency-correct YIELD as payout x earnings_yield (earnings_yield coming
    # from our own FX-handled master), sidestepping FMP's listing-currency cap.
    _ni_y = dict(_by_year(isr, "netIncome"))
    _tot_payouts, _buyb_payouts, _div_payouts = [], [], []
    for y in sorted(set(_ni_y) & (set(_buyb_y) | set(_div_y)), reverse=True)[:3]:
        ni = _ni_y.get(y, np.nan)
        if math.isfinite(ni) and ni > 0:
            b = abs(_buyb_y.get(y, 0.0) or 0.0) / ni
            d = abs(_div_y.get(y, 0.0) or 0.0) / ni
            _buyb_payouts.append(b); _div_payouts.append(d); _tot_payouts.append(b + d)
    if _tot_payouts:
        rec["fmp_st_capital_return_payout"] = float(np.median(_tot_payouts))
        rec["fmp_st_buyback_payout"] = float(np.median(_buyb_payouts))
        rec["fmp_st_dividend_payout_cf"] = float(np.median(_div_payouts))

    # market cap for the (single-figure) owner-earnings yield below: the latest
    # coherent year's cap, else NaN so the yield is withheld on a mismatch.
    mcap = np.nan
    for y in sorted(_mc_y, reverse=True):
        if _coherent(y):
            mcap = _mc_y[y]; break

    fin = _by_year(cf, "netCashProvidedByFinancingActivities")
    if fin:
        rec["fmp_st_financing_outflow_years"] = float(sum(1 for _, v in fin if v < 0))
        rec["fmp_st_financing_years"] = float(len(fin))

    # ---- SBC / tax / retained earnings ----
    sbc = _by_year(km, "stockBasedCompensationToRevenue")
    if sbc:
        rec["fmp_st_sbc_pct_revenue"] = sbc[0][1]
    etr = _by_year(ra, "effectiveTaxRate")
    if etr:
        rec["fmp_st_effective_tax_rate"] = etr[0][1]

    # ---- owner earnings (Buffett, maintenance-capex adjusted) ----
    if oe:
        o = sorted(oe, key=lambda r: r.get("date", ""), reverse=True)
        rec["fmp_st_owner_earnings"] = _f(o[0].get("ownersEarnings"))
        oes = [_f(r.get("ownersEarnings")) for r in o[:5]]
        oes = [v for v in oes if math.isfinite(v)]
        if oes:
            rec["fmp_st_owner_earnings_avg"] = float(np.mean(oes))
        # yield off the AVERAGE (a single year's owner earnings swings on
        # working capital; Toyota's latest was negative, its average +255B).
        oe_for_yield = rec.get("fmp_st_owner_earnings_avg", np.nan)
        if math.isfinite(mcap) and mcap > 0 and math.isfinite(oe_for_yield):
            rec["fmp_st_owner_earnings_yield"] = oe_for_yield / mcap
    return rec


def _flush(rows):
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, low_memory=False)
        both = pd.concat([old, new], ignore_index=True).drop_duplicates("symbol", keep="last")
    else:
        both = new
    tmp = OUT + ".tmp"
    both.to_csv(tmp, index=False)
    os.replace(tmp, OUT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relevant", default="archetype_tags.csv")
    ap.add_argument("--scope", choices=["nonus_edgar_gap", "firers", "all"], default="nonus_edgar_gap")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--checkpoint-every", type=int, default=150)
    ap.add_argument("--gc-max-mb", type=int, default=300)
    args = ap.parse_args()

    t = pd.read_csv(args.relevant, low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    if args.scope == "nonus_edgar_gap":
        # names that fire (or nearly fire) a quality/compounder/forensic
        # archetype but whose EDGAR lindy metric is missing — the reach set.
        edgar_col = "roic_lindy" if "roic_lindy" in t.columns else None
        missing = t[edgar_col].isna() if edgar_col else pd.Series(True, index=t.index)
        ac = t.get("archetype_count", pd.Series(0, index=t.index)).fillna(0)
        mask = missing & (ac >= 1)
    elif args.scope == "firers":
        mask = t.get("archetype_count", pd.Series(0, index=t.index)).fillna(0) >= 1
    else:
        mask = pd.Series(True, index=t.index)
    syms = t.loc[mask, "symbol"].tolist()
    if args.max:
        syms = syms[: args.max]
    print(f"statements scope={args.scope}: {len(syms)} symbols", flush=True)

    gc_bytes = args.gc_max_mb * 1_048_576 if args.gc_max_mb else None
    done = set()
    if os.path.exists(OUT):
        try:
            done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str))
        except Exception:
            done = set()
    todo = [s for s in syms if s not in done]
    print(f"  {len(done)} done, {len(todo)} to fetch", flush=True)
    rows = []
    for i, sym in enumerate(todo, 1):
        try:
            rows.append(enrich_symbol(sym))
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                print(f"  rate limited at {i}; checkpointing", flush=True)
                break
            rows.append({"symbol": sym})
        if i % args.checkpoint_every == 0:
            _flush(rows); rows = []
            st = fc.cache_stats()
            print(f"  statements {i}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if gc_bytes:
                fc.cache_gc(gc_bytes)
    _flush(rows)
    fin = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    print(f"\nwrote {OUT}: {len(fin)} rows, {len(fin.columns)} cols", flush=True)


if __name__ == "__main__":
    main()
