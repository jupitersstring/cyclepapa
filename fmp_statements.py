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
import time
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_statements.csv"
# Bumped whenever a field's DEFINITION changes: rows written under an older
# schema are recomputed (from cache) instead of being skipped as "done".
SCHEMA = 4


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
    bsa = fc.get_json("balance-sheet-statement", {"symbol": sym, "period": "annual", "limit": 8},
                      ttl=fc.TTL_FUNDAMENTAL)
    rec: dict = {"symbol": sym, "fmp_st_schema": float(SCHEMA)}

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
    fcf_y = dict(_by_year(cf, "freeCashFlow"))

    def _nopat(y):
        t = tax.get(y, np.nan)
        t = t if (math.isfinite(t) and 0 <= t < 0.6) else 0.25
        return op[y] * (1 - t)

    def _roiic(y_hi, span, num):
        """ΔX / ΔIC between fiscal years y_hi-span and y_hi (EDGAR roiic_window):
        consecutive-year span, capital actually DEPLOYED (ΔIC > 0 and >= 5% of
        the latest IC — a capital-returner shrinking IC over falling NOPAT is a
        ratio of two negatives, not great incremental returns), and outside
        [-2, 2] the ratio is a denominator artifact (EDGAR drops it too)."""
        y_lo = y_hi - span
        if y_hi not in ic or y_lo not in ic:
            return np.nan
        a, b = num(y_hi), num(y_lo)
        d_ic = ic[y_hi] - ic[y_lo]
        if not all(math.isfinite(v) for v in (a, b, d_ic)) or d_ic <= 0:
            return np.nan
        if ic[y_hi] > 0 and d_ic / ic[y_hi] < 0.05:
            return np.nan
        v = (a - b) / d_ic
        return v if -2.0 <= v <= 2.0 else np.nan

    _np = lambda y: _nopat(y) if y in op else np.nan
    _fc = lambda y: fcf_y.get(y, np.nan)
    if yrs:
        y0 = yrs[0]
        # LINDY = median of ROLLING 3-year windows (EDGAR roiic_lindy). A
        # single endpoint ratio is one noisy draw: FMP-filled firers of
        # cheap_per_roiic reached EV/EBITDA 138x on an implied 92% ROIIC.
        roll = [v for v in (_roiic(y, 3, _np) for y in yrs) if math.isfinite(v)]
        croll = [v for v in (_roiic(y, 3, _fc) for y in yrs) if math.isfinite(v)]
        if len(roll) >= 2:
            rec["fmp_st_roiic_lindy"] = float(np.median(roll))
            rec["fmp_st_roiic_windows"] = float(len(roll))
        if len(croll) >= 2:
            rec["fmp_st_cash_roiic_lindy"] = float(np.median(croll))
        r1, r3 = _roiic(y0, 1, _np), _roiic(y0, 3, _np)
        if math.isfinite(r1) and math.isfinite(r3):
            rec["fmp_st_roiic_acceleration"] = r1 - r3

    # ---- margins held over the window (lindy) ----
    opm = _by_year(ra, "operatingProfitMargin")
    ebm = _by_year(ra, "ebitdaMargin")
    if opm:
        rec["fmp_st_op_margin_lindy"] = _median([v for _, v in opm])
    if ebm:
        rec["fmp_st_ebitda_margin_lindy"] = _median([v for _, v in ebm])

    # ---- durability counts from cash-flow / income ----
    # Counted over the LATEST 5 fiscal years, exactly as EDGAR does
    # (edgar_roic_roiic.lindy_aggregates: df.tail(5)); counting over FMP's up-to-
    # 8 years made ">= 4" mean 4-of-8 for FMP rows vs 4-of-5 for EDGAR rows.
    fcf = _by_year(cf, "freeCashFlow")
    opinc = _by_year(isr, "operatingIncome")
    if fcf:
        rec["fmp_st_n_yrs_positive_fcf"] = float(sum(1 for _, v in fcf[:5] if v > 0))
    if opinc:
        rec["fmp_st_n_yrs_positive_opinc"] = float(sum(1 for _, v in opinc[:5] if v > 0))
    if roic:
        rec["fmp_st_n_yrs_positive_roic"] = float(sum(1 for _, v in roic[:5] if v > 0))

    # ---- cash ROIC (FCF / invested capital), EDGAR definition ----
    fcf_d = dict(fcf)
    croic = [(y, fcf_d[y] / ic[y]) for y in sorted(set(fcf_d) & set(ic), reverse=True)
             if math.isfinite(ic[y]) and ic[y] > 0]
    if croic:
        rec["fmp_st_cash_roic_lindy"] = _median([v for _, v in croic])
    roic_d = dict(roic)
    # inflection: prior fiscal year <= 0, latest > 0 (consecutive years only)
    def _inflect(series):
        if len(series) >= 2 and series[0][0] - series[1][0] == 1:
            return float(series[1][1] <= 0 < series[0][1])
        return np.nan
    rec["fmp_st_roic_inflection_flag"] = _inflect(roic)
    rec["fmp_st_cash_roic_inflection_flag"] = _inflect(croic)
    # acceleration: ROIC delta-of-delta over three consecutive years
    ys = sorted(roic_d, reverse=True)
    if len(ys) >= 3 and ys[0] - ys[2] == 2:
        rec["fmp_st_roic_acceleration"] = (roic_d[ys[0]] - roic_d[ys[1]]) - (roic_d[ys[1]] - roic_d[ys[2]])

    # ---- growth / dilution ----
    rec_rev = _by_year(isr, "revenue")
    if len(rec_rev) >= 2:
        rec["fmp_st_revenue_cagr"] = _cagr(rec_rev)

    def _span_cagr(series, span):
        """CAGR over EXACTLY `span` fiscal years back from the latest (EDGAR's
        revenue_3y_cagr / _5y_cagr); NaN when that year is missing."""
        d = dict(series)
        if not d:
            return np.nan
        y0 = max(d)
        v0, vN = d.get(y0, np.nan), d.get(y0 - span, np.nan)
        if not (math.isfinite(v0) and math.isfinite(vN)) or v0 <= 0 or vN <= 0:
            return np.nan
        return (v0 / vN) ** (1.0 / span) - 1.0
    rec["fmp_st_revenue_3y_cagr"] = _span_cagr(rec_rev, 3)
    rec["fmp_st_revenue_5y_cagr"] = _span_cagr(rec_rev, 5)
    if math.isfinite(rec["fmp_st_revenue_3y_cagr"]) and math.isfinite(rec["fmp_st_revenue_5y_cagr"]):
        rec["fmp_st_revenue_accel_lindy"] = rec["fmp_st_revenue_3y_cagr"] - rec["fmp_st_revenue_5y_cagr"]
    assets = _by_year(bsa, "totalAssets")
    rec["fmp_st_asset_3y_cagr"] = _span_cagr(assets, 3)
    rec["fmp_st_asset_5y_cagr"] = _span_cagr(assets, 5)

    # ---- 5-fiscal-year averages (EDGAR _avg_over: latest 5 aligned years, >= 3) ----
    def _avg_over(series_list, n=5, min_years=3):
        ds = [dict(s) for s in series_list]
        common = set(ds[0])
        for d in ds[1:]:
            common &= set(d)
        yrs = sorted(common, reverse=True)[:n]
        if len(yrs) < min_years:
            return np.nan, len(yrs)
        return float(np.mean([sum(d[y] for d in ds) for y in yrs])), len(yrs)
    ni_s = _by_year(isr, "netIncome")
    da_s = _by_year(cf, "depreciationAndAmortization")
    # capex positive (spend). A year whose capex AND D&A are both exactly 0 is an
    # FMP zero-fill, not a capital-free year: drop it from both series.
    _cx_raw = dict(_by_year(cf, "capitalExpenditure"))
    _da_raw = dict(da_s)
    _blank = {y for y in _cx_raw if _cx_raw[y] == 0 and _da_raw.get(y, 0) == 0}
    cx_s = [(y, abs(v)) for y, v in _cx_raw.items() if y not in _blank]
    da_s = [(y, v) for y, v in da_s if y not in _blank]
    rec["fmp_st_ni_avg"], rec["fmp_st_ni_avg_years"] = _avg_over([ni_s])
    rec["fmp_st_capex_avg"], rec["fmp_st_capex_avg_years"] = _avg_over([cx_s])
    oe_parts = [ni_s, da_s, [(y, -v) for y, v in cx_s]]
    rec["fmp_st_oe_avg"], rec["fmp_st_oe_avg_years"] = _avg_over(oe_parts)
    eq = _by_year(ra, "bookValuePerShare")
    if len(eq) >= 2:
        rec["fmp_st_equity_cagr"] = _cagr(eq)
    sh = _by_year(isr, "weightedAverageShsOutDil")
    if sh:
        from unit_scale import normalize_shares
        sh = list(zip([y for y, _ in sh], normalize_shares([v for _, v in sh])))
    if len(sh) >= 2:
        # newest-first; growth over up to 3 and 5 year spans
        def _sh_growth(n):
            s = [(y, v) for y, v in sh if math.isfinite(v) and v > 0]
            if len(s) <= n:
                return np.nan
            return s[0][1] / s[n][1] - 1.0
        rec["fmp_st_shares_growth_3y"] = _sh_growth(3)
        rec["fmp_st_shares_growth_5y"] = _sh_growth(min(5, len(sh) - 1))

    # ---- multi-year PER-SHARE earnings-power growth over EXACT spans ----
    # (the long-horizon narrative-lag lenses: the price is per share, so the
    # advance must be too). Each endpoint is the 2-fiscal-year AVERAGE (latest
    # two vs the two ending `span` years earlier) so one lumpy year — a write-
    # down, a working-capital swing, a timing shift between policies — cannot
    # make or break a multi-year trend. Both endpoints must be positive (a
    # growth rate off a loss is undefined). Operating margin change is on the
    # same averaged endpoints: sales growth that came with a falling margin is
    # volume, not earnings power.
    _sh_d = {y: v for y, v in sh if math.isfinite(v) and v > 0} if sh else {}

    def _ps_avg(series, y0):
        d = dict(series)
        vals = [d[y] / _sh_d[y] for y in (y0, y0 - 1) if y in d and y in _sh_d]
        return float(np.mean(vals)) if len(vals) == 2 else np.nan

    def _ps_growth(series, span):
        d = dict(series)
        if not d:
            return np.nan
        y0 = max(d)
        a, b = _ps_avg(series, y0), _ps_avg(series, y0 - span)
        return a / b - 1.0 if (math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0) else np.nan

    def _opm_avg(y0):
        vals = [opd[y] / revd[y] for y in (y0, y0 - 1) if y in opd and y in revd and revd[y] > 0]
        return float(np.mean(vals)) if len(vals) == 2 else np.nan

    opd, revd = dict(opinc), dict(rec_rev)
    for span in (3, 5):
        rec[f"fmp_st_ebit_ps_{span}y_g"] = _ps_growth(opinc, span)
        rec[f"fmp_st_fcf_ps_{span}y_g"] = _ps_growth(fcf, span)
        rec[f"fmp_st_sales_ps_{span}y_g"] = _ps_growth(rec_rev, span)
        if revd:
            y0 = max(revd)
            a, b = _opm_avg(y0), _opm_avg(y0 - span)
            if math.isfinite(a) and math.isfinite(b):
                rec[f"fmp_st_opm_chg_{span}y"] = a - b

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
    # exactly 0 = not disclosed (every JP filer reads 0.0), not SBC-free
    if sbc and sbc[0][1] != 0:
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
    ap.add_argument("--gc-max-mb", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
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
            _d = pd.read_csv(OUT, low_memory=False)
            _cur = pd.to_numeric(_d.get("fmp_st_schema"), errors="coerce") == SCHEMA \
                if "fmp_st_schema" in _d.columns else pd.Series(False, index=_d.index)
            done = set(_d.loc[_cur, "symbol"].astype(str))
        except Exception:
            done = set()
    todo = [s for s in syms if s not in done]
    print(f"  {len(done)} done, {len(todo)} to fetch", flush=True)
    def _one(sym):
        # rate limit = wait and retry the same symbol; never record it as an
        # empty (would-be "done") row
        for attempt in range(12):
            try:
                return enrich_symbol(sym)
            except fc.FMPError as exc:
                if "Limit Reach" in str(exc) or "429" in str(exc):
                    time.sleep(30 * (attempt + 1))
                    continue
                return {"symbol": sym}
        raise fc.FMPError(f"{sym}: still rate limited after 12 waits")

    # Parallel over symbols (I/O-bound; the client's cache and backoff are
    # thread-safe), flushed in checkpoint-sized chunks so a kill loses little.
    from concurrent.futures import ThreadPoolExecutor
    step = args.checkpoint_every
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for i in range(0, len(todo), step):
            rows = list(ex.map(_one, todo[i:i + step]))
            _flush(rows)
            st = fc.cache_stats()
            print(f"  statements {min(i + step, len(todo))}/{len(todo)} | hit_rate={st['hit_rate']} "
                  f"| cache {st['disk_mb']}MB", flush=True)
            if gc_bytes:
                fc.cache_gc(gc_bytes)
    fin = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    print(f"\nwrote {OUT}: {len(fin)} rows, {len(fin.columns)} cols", flush=True)


if __name__ == "__main__":
    main()
