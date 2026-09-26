"""Granular three-statement engine (quarterly / half-yearly) -> fmp_quarterly.csv
                                                         + fmp_quarterly_panel.parquet

Why: the forensic / XR archetypes read balance-sheet and cash-flow detail
(working capital, deferred revenue, retained earnings, PP&E, goodwill, cash
taxes paid, discontinued ops, assets, equity) that today comes from EDGAR only:
0% coverage outside the US, 20-40% inside it. FMP's periodic statements carry
all of it globally, and at quarterly granularity they also allow the classic
forensic-accounting tests we could not run: Beneish M-score, Sloan accruals,
receivables / inventory vs sales divergence, cash vs book tax, and trajectories
(net-debt paydown, gross-margin streaks) rather than point snapshots.

ROBUSTNESS RULES (each guards a known failure mode)
  * Point-in-time: a period counts only if its filingDate is on or before
    today (no restated-in-the-future or pre-announced periods).
  * One currency: every period used must share the latest period's
    reportedCurrency; a currency change mid-series breaks the comparison.
  * Cadence detected, not assumed: quarterly filers (~91-day spacing) sum
    4 periods for TTM, half-yearly filers (~182-day spacing, common in
    Europe/Australia/HK) sum 2. Anything else -> no TTM.
  * Contiguity: a TTM window must cover ~12 months with no missing period
    (period gaps within cadence +/- 45 days); year-ago windows must end
    ~12 months before the latest one. Otherwise the metric is NaN, never
    guessed.
  * Staleness: the latest period must be <= 9 months old (quarterly) or
    <= 12 months (half-yearly), else the name is marked stale and emits
    nothing forensic.
  * Dimensionless outputs: forensic metrics are ratios of statement items to
    each other, so currency cancels. Levels are emitted in the reporting
    currency with the currency code, and the archetype layer converts them
    to the master's currency via a revenue anchor before any comparison
    with market cap.
  * Beneish inputs are winsorised to [0.25, 4.0] (standard practice: a ratio
    of two tiny bases is not information) and M is emitted only when the
    five core variables are present.

Resumable: symbols already in fmp_quarterly.csv are skipped.
"""
from __future__ import annotations

import argparse
import time
import datetime as dt
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_quarterly.csv"
PANEL = "fmp_quarterly_panel.parquet"
_PANEL_PART_DIR = "fmp_quarterly_panel_parts"
TODAY = dt.date.today()

# flow fields (summed over a TTM window)
IS_FLOWS = {"revenue": "revenue", "costOfRevenue": "cogs", "grossProfit": "gp",
            "operatingIncome": "opinc", "ebitda": "ebitda", "netIncome": "ni",
            "netIncomeFromContinuingOperations": "ni_cont",
            "netIncomeFromDiscontinuedOperations": "ni_disc",
            "incomeBeforeTax": "pretax", "incomeTaxExpense": "tax_exp",
            "interestExpense": "int_exp",
            "sellingGeneralAndAdministrativeExpenses": "sga",
            "researchAndDevelopmentExpenses": "rnd"}
CF_FLOWS = {"operatingCashFlow": "cfo", "capitalExpenditure": "capex",
            "freeCashFlow": "fcf", "depreciationAndAmortization": "da",
            "stockBasedCompensation": "sbc", "incomeTaxesPaid": "taxes_paid",
            "commonStockRepurchased": "buyback", "commonDividendsPaid": "dividends",
            "acquisitionsNet": "acquisitions", "changeInWorkingCapital": "chg_wc",
            "netCashProvidedByFinancingActivities": "financing_cf"}
# stock fields (point-in-time balance)
BS_STOCKS = {"netReceivables": "receivables", "inventory": "inventory",
             "accountPayables": "payables", "totalCurrentAssets": "cur_assets",
             "totalCurrentLiabilities": "cur_liab", "totalAssets": "total_assets",
             "propertyPlantEquipmentNet": "ppe_net",
             "goodwillAndIntangibleAssets": "gw_intang",
             "deferredRevenue": "defrev_cur", "deferredRevenueNonCurrent": "defrev_nc",
             "longTermDebt": "lt_debt", "totalDebt": "total_debt",
             "cashAndShortTermInvestments": "cash_sti",
             "totalStockholdersEquity": "equity", "retainedEarnings": "retained_earnings",
             "totalLiabilities": "total_liab", "minorityInterest": "minority",
             "treasuryStock": "treasury"}


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _clean(rows, ccy=None):
    """Newest-first, point-in-time, single-currency, de-duplicated periods."""
    out, seen = [], set()
    for r in rows or []:
        d = _d(r.get("date"))
        fd = _d(r.get("filingDate") or r.get("acceptedDate") or r.get("date"))
        if d is None or d in seen or d > TODAY or (fd and fd > TODAY):
            continue
        seen.add(d)
        out.append((d, r))
    out.sort(key=lambda t: t[0], reverse=True)
    if not out:
        return [], None
    ccy = ccy or out[0][1].get("reportedCurrency")
    out = [(d, r) for d, r in out if r.get("reportedCurrency") in (ccy, None)]
    return out, ccy


# A period whose defining lines are ALL exactly zero is an unreported
# placeholder, not a real zero: FMP zero-fills quarters a filer never
# published (Japanese filers publish cash flow semi-annually or annually, so
# every quarterly CF row reads 0 while the annual CFO is Y100M-Y4.5B). Such a
# row is blanked (dates kept, values dropped) so any TTM that touches it is
# NaN rather than a false 0 — which would otherwise read as "earnings with no
# cash behind them" and fire accrual / Beneish alarms on clean names.
_PLACEHOLDER_KEYS = {
    "is": ("revenue", "netIncome", "grossProfit", "operatingIncome"),
    "bs": ("totalAssets", "totalLiabilities", "totalStockholdersEquity"),
    # NOT netIncome: FMP copies it into placeholder CF rows from the income
    # statement and balances it with an equal-and-opposite otherNonCashItems
    # plug, so CFO still reads 0 (6580.T Q1: NI 4.0M, otherNonCash -4.0M).
    "cf": ("operatingCashFlow", "capitalExpenditure", "depreciationAndAmortization",
           "netCashProvidedByInvestingActivities", "netChangeInCash"),
}


def _blank_placeholders(periods, kind):
    keys = _PLACEHOLDER_KEYS[kind]
    out = []
    for d, r in periods:
        vals = [_f(r.get(k)) for k in keys]
        if all((not math.isfinite(v)) or v == 0 for v in vals):
            r = {k: r.get(k) for k in ("date", "period", "reportedCurrency", "filingDate")}
        out.append((d, r))
    return out


def _cadence(periods):
    if len(periods) < 3:
        return None
    gaps = [(periods[i][0] - periods[i + 1][0]).days for i in range(min(6, len(periods) - 1))]
    g = float(np.median(gaps))
    if 70 <= g <= 120:
        return 4, g
    if 150 <= g <= 215:
        return 2, g
    return None


def _window(periods, n, start, spacing):
    """n contiguous periods starting at index `start`, else None."""
    w = periods[start:start + n]
    if len(w) < n:
        return None
    for a, b in zip(w, w[1:]):
        if abs((a[0] - b[0]).days - spacing) > 45:
            return None
    return w


def _ttm(periods, n, spacing, field, year_ago=False):
    if not periods:
        return np.nan
    start = 0
    if year_ago:
        target = periods[0][0] - dt.timedelta(days=365)
        idx = [i for i, (d, _) in enumerate(periods) if abs((d - target).days) <= 45]
        if not idx:
            return np.nan
        start = idx[0]
    w = _window(periods, n, start, spacing)
    if w is None:
        return np.nan
    vals = [_f(r.get(field)) for _, r in w]
    return float(sum(vals)) if all(math.isfinite(v) for v in vals) else np.nan


def _snap(periods, field, year_ago=False):
    if not periods:
        return np.nan
    if not year_ago:
        return _f(periods[0][1].get(field))
    target = periods[0][0] - dt.timedelta(days=365)
    for d, r in periods:
        if abs((d - target).days) <= 45:
            return _f(r.get(field))
    return np.nan


def _div(a, b):
    return a / b if (math.isfinite(a) and math.isfinite(b) and b != 0) else np.nan


def _wins(x, lo=0.25, hi=4.0):
    return min(max(x, lo), hi) if math.isfinite(x) else np.nan


def enrich_symbol(sym: str):
    isr = fc.get_json("income-statement", {"symbol": sym, "period": "quarter", "limit": 13},
                      ttl=fc.TTL_FUNDAMENTAL)
    bs = fc.get_json("balance-sheet-statement", {"symbol": sym, "period": "quarter", "limit": 9},
                     ttl=fc.TTL_FUNDAMENTAL)
    cf = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "quarter", "limit": 9},
                     ttl=fc.TTL_FUNDAMENTAL)
    rec = {"symbol": sym}
    # FY-in-Q4 substitution: restore the true Q4 = FY - (Q1+Q2+Q3) (fy_q4.py)
    import fy_q4
    isr, _q4 = fy_q4.restore(isr, "is")
    cf, _ = fy_q4.restore(cf, "cf", _q4)
    ip, ccy = _clean(isr)
    if not ip:
        return rec, []
    ip = _blank_placeholders(ip, "is")
    bp, _ = _clean(bs, ccy)
    bp = _blank_placeholders(bp, "bs")
    cp, _ = _clean(cf, ccy)
    cp = _blank_placeholders(cp, "cf")
    cad = _cadence(ip)
    rec["fmp_q_ccy"] = ccy
    rec["fmp_q_latest"] = ip[0][0].isoformat()
    if cad is None:
        rec["fmp_q_status"] = "irregular_cadence"
        return rec, []
    n, spacing = cad
    age = (TODAY - ip[0][0]).days
    if age > (275 if n == 4 else 370):
        rec["fmp_q_status"] = "stale"
        return rec, []
    rec["fmp_q_status"] = "ok"
    rec["fmp_q_periods_per_year"] = float(n)

    L = {}   # levels: current TTM / snapshot, and year-ago
    for src, key in IS_FLOWS.items():
        L[key] = _ttm(ip, n, spacing, src)
        L[key + "_p"] = _ttm(ip, n, spacing, src, year_ago=True)
    for src, key in CF_FLOWS.items():
        L[key] = _ttm(cp, n, spacing, src)
        L[key + "_p"] = _ttm(cp, n, spacing, src, year_ago=True)
    # Quarterly incomeTaxesPaid is unusable in FMP: zero-filled for many
    # filers (KO, NESN every period), sporadic for others, and corrupted in
    # fourth quarters that FMP derives as annual minus nine-month YTD (AAPL
    # read -$37B). The ANNUAL cash-flow figure is reliable (AAPL $43.4B), so
    # cash taxes and the matching annual pretax come from the latest fiscal
    # year (same cached call the statements engine uses).
    L["taxes_paid"] = np.nan
    L["pretax_fy"] = np.nan
    L["tax_exp_fy"] = np.nan
    # SBC / D&A reading exactly 0 in EVERY quarter of the window is "not
    # disclosed" (most non-US filers fold SBC into opex, and some never break
    # out D&A quarterly), not a true zero — a true 0 would certify the name as
    # SBC-clean or asset-light. Buybacks / dividends / acquisitions can
    # legitimately be zero, so they are left as reported.
    for key in ("sbc", "da", "sbc_p", "da_p"):
        if L.get(key) == 0:
            L[key] = np.nan
    # SBC is an expense: a NEGATIVE TTM is FMP's sign-flipped add-back for
    # some IFRS filers (CNY / HKD / EUR rows), not a disclosure
    for key in ("sbc", "sbc_p"):
        if math.isfinite(L.get(key, np.nan)) and L[key] < 0:
            L[key] = np.nan
    # CF basis: quarterly TTM by default. When the quarterly cash-flow TTM is
    # unavailable (placeholder quarters, semi-annual cash-flow filers), fall
    # back to the latest ANNUAL cash-flow statement, paired with that same
    # fiscal year's annual net income so accrual ratios compare like periods.
    rec["fq_cf_basis"] = "quarterly" if math.isfinite(L["cfo"]) else None
    L["ni_cf"], L["ni_cf_p"] = L["ni"], L["ni_p"]
    try:
        cfa = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
        isa = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
        cfa = [(d, r) for d, r in _blank_placeholders(_clean(cfa, ccy)[0], "cf")]
        isa = {d: r for d, r in _clean(isa, ccy)[0]}
        if cfa:
            ld, latest = cfa[0]
            fy_age = (TODAY - ld).days
            # Quarterly incomeTaxesPaid is unusable in FMP: zero-filled for many
            # filers (KO, NESN every period), sporadic for others, and corrupted
            # in fourth quarters that FMP derives as annual minus nine-month YTD
            # (AAPL read -$37B). The ANNUAL figure is reliable (AAPL $43.4B), so
            # cash taxes and the matching annual pretax come from the latest FY.
            tp = _f(latest.get("incomeTaxesPaid"))
            pt = _f((isa.get(ld) or {}).get("incomeBeforeTax"))
            te = _f((isa.get(ld) or {}).get("incomeTaxExpense"))
            if math.isfinite(tp) and tp > 0 and math.isfinite(pt) and fy_age <= 550:
                L["taxes_paid"], L["pretax_fy"] = tp, pt
                # book tax on the SAME fiscal year, so the cash-vs-book wedge
                # compares like periods (a TTM book tax against an annual cash
                # tax up to 18 months older is a window mismatch)
                L["tax_exp_fy"] = te
            # multi-year cash-tax wedge (median of up to 3 fiscal years):
            # single-year cash tax carries payment-timing noise
            wedges = []
            for d, r in cfa[:3]:
                if (ld - d).days > 3 * 365 + 60:
                    break
                ir = isa.get(d) or {}
                tp_y, pt_y, te_y = _f(r.get("incomeTaxesPaid")), _f(ir.get("incomeBeforeTax")), _f(ir.get("incomeTaxExpense"))
                if all(math.isfinite(v) for v in (tp_y, pt_y, te_y)) and tp_y > 0 and pt_y > 0 and te_y > 0:
                    wedges.append((te_y - tp_y) / te_y)
            if len(wedges) >= 2 and fy_age <= 550:
                rec["fq_cash_tax_wedge_med"] = float(np.median(wedges))
                rec["fq_cash_tax_wedge_years"] = float(len(wedges))
            a_cfo = _f(latest.get("operatingCashFlow"))
            a_ni = _f((isa.get(ld) or {}).get("netIncome"))
            if (rec["fq_cf_basis"] is None and fy_age <= 550
                    and math.isfinite(a_cfo) and math.isfinite(a_ni)):
                rec["fq_cf_basis"] = "annual"
                prior = [(d, r) for d, r in cfa[1:] if abs((ld - d).days - 365) <= 45]
                for src, key in CF_FLOWS.items():
                    if key == "taxes_paid":
                        continue
                    L[key] = _f(latest.get(src))
                    L[key + "_p"] = _f(prior[0][1].get(src)) if prior else np.nan
                for key in ("sbc", "da", "sbc_p", "da_p"):
                    if L.get(key) == 0:
                        L[key] = np.nan
                L["ni_cf"] = a_ni
                L["ni_cf_p"] = _f((isa.get(prior[0][0]) or {}).get("netIncome")) if prior else np.nan
    except fc.FMPError:
        pass
    for src, key in BS_STOCKS.items():
        L[key] = _snap(bp, src)
        L[key + "_p"] = _snap(bp, src, year_ago=True)
    # Retained earnings of EXACTLY 0 is FMP's zero-fill for filers whose
    # reserves it does not map (CNY / INR / HKD reporters: 14% of rows), not a
    # company with no accumulated earnings.
    for k in ("retained_earnings", "retained_earnings_p"):
        if L.get(k) == 0:
            L[k] = np.nan
    for k in ("defrev", ):
        for sfx in ("", "_p"):
            a, b = L.get(f"defrev_cur{sfx}", np.nan), L.get(f"defrev_nc{sfx}", np.nan)
            L[f"defrev{sfx}"] = (0 if not math.isfinite(a) else a) + (0 if not math.isfinite(b) else b) \
                if (math.isfinite(a) or math.isfinite(b)) else np.nan
    from unit_scale import normalize_shares
    # one scale for the share series (FMP carried AMCCF's latest quarter as
    # 464.6 against 463,800,000): unit restoration, not a bound
    shares = normalize_shares([_f(r.get("weightedAverageShsOutDil")) for _, r in ip])

    # ---- levels emitted (reporting currency; archetype layer converts) ----
    for k in ("revenue", "gp", "opinc", "ni", "ni_cont", "ni_disc", "pretax", "tax_exp",
              "int_exp", "cfo", "capex", "fcf", "da", "sbc", "taxes_paid", "buyback",
              "dividends", "receivables", "inventory", "payables", "cur_assets", "cur_liab",
              "total_assets", "ppe_net", "gw_intang", "defrev", "total_debt", "cash_sti",
              "equity", "retained_earnings", "total_liab", "minority", "revenue_p", "ni_p",
              "cfo_p", "equity_p", "defrev_p", "financing_cf", "chg_wc", "acquisitions",
              "cogs", "sga", "lt_debt", "treasury", "capex_p", "da_p", "ni_cf", "ni_cf_p",
              "tax_exp_fy", "pretax_fy"):
        rec[f"fq_{k}"] = L.get(k, np.nan)

    rev, rev_p = L["revenue"], L["revenue_p"]
    # ---- working-capital forensics ----
    cogs = L["cogs"] if math.isfinite(L["cogs"]) else (rev - L["gp"] if math.isfinite(L["gp"]) else np.nan)
    cogs_p = L["cogs_p"] if math.isfinite(L["cogs_p"]) else (rev_p - L["gp_p"] if math.isfinite(L["gp_p"]) else np.nan)
    rec["fq_dso"] = _div(L["receivables"], rev) * 365
    rec["fq_dso_p"] = _div(L["receivables_p"], rev_p) * 365
    rec["fq_dio"] = _div(L["inventory"], cogs) * 365
    rec["fq_dio_p"] = _div(L["inventory_p"], cogs_p) * 365
    rec["fq_dpo"] = _div(L["payables"], cogs) * 365
    rec["fq_dpo_p"] = _div(L["payables_p"], cogs_p) * 365
    ccc = [rec["fq_dso"], rec["fq_dio"], rec["fq_dpo"]]
    ccc_p = [rec["fq_dso_p"], rec["fq_dio_p"], rec["fq_dpo_p"]]
    if all(math.isfinite(v) for v in ccc):
        rec["fq_ccc"] = ccc[0] + ccc[1] - ccc[2]
    if all(math.isfinite(v) for v in ccc_p):
        rec["fq_ccc_p"] = ccc_p[0] + ccc_p[1] - ccc_p[2]
    rev_g = _div(rev, rev_p) - 1
    rec["fq_rev_growth"] = rev_g
    # receivables / inventory growing faster than sales = channel stuffing /
    # unsold build. Only meaningful off a MATERIAL base (>= 5% of prior-year
    # sales / COGS): at 2% the tail reached 31x off rounding-error balances.
    if math.isfinite(L["receivables_p"]) and L["receivables_p"] > 0.05 * (rev_p or np.inf):
        rec["fq_rec_vs_rev"] = _div(L["receivables"], L["receivables_p"]) - 1 - rev_g
    if math.isfinite(L["inventory_p"]) and math.isfinite(cogs_p) and L["inventory_p"] > 0.05 * cogs_p:
        rec["fq_inv_vs_cogs"] = _div(L["inventory"], L["inventory_p"]) - _div(cogs, cogs_p)
    # NWC needs a CLASSIFIED balance sheet: an unclassified one (banks,
    # insurers, some IFRS filers) reports current assets as 0/absent and
    # would read as a large negative NWC — a false "customer float".
    ca, cl = L["cur_assets"], L["cur_liab"]
    rec["fq_nwc"] = ca - cl if (math.isfinite(ca) and math.isfinite(cl) and ca > 0 and cl > 0) else np.nan
    # OPERATING working capital (excludes cash, which hides float in a
    # cash-rich company) as a share of sales: receivables + inventory -
    # payables - deferred revenue.
    if math.isfinite(rev) and rev > 0 and math.isfinite(L["receivables"]) and math.isfinite(L["payables"]):
        onwc = (L["receivables"] + (L["inventory"] if math.isfinite(L["inventory"]) else 0)
                - L["payables"] - (L["defrev"] if math.isfinite(L["defrev"]) else 0))
        rec["fq_op_nwc_to_rev"] = onwc / rev

    # ---- accrual quality ----
    avg_ta = np.nanmean([L["total_assets"], L["total_assets_p"]]) if (
        math.isfinite(L["total_assets"]) or math.isfinite(L["total_assets_p"])) else np.nan
    # net income on the SAME basis as the cash flow (TTM, or annual fallback)
    ni_cf, ni_cf_p = L["ni_cf"], L["ni_cf_p"]
    rec["fq_sloan_accruals"] = _div(ni_cf - L["cfo"], avg_ta)
    rec["fq_cfo_to_ni"] = _div(L["cfo"], ni_cf) if (math.isfinite(ni_cf) and ni_cf > 0) else np.nan
    rec["fq_cfo_growth_minus_ni_growth"] = (
        (_div(L["cfo"], L["cfo_p"]) - _div(ni_cf, ni_cf_p))
        if all(math.isfinite(v) and v > 0 for v in (L["cfo"], L["cfo_p"], ni_cf, ni_cf_p)) else np.nan)
    rec["fq_sbc_to_cfo"] = _div(L["sbc"], L["cfo"]) if (math.isfinite(L["cfo"]) and L["cfo"] > 0) else np.nan

    # ---- capex / depreciation / asset life ----
    rec["fq_capex_to_da"] = _div(abs(L["capex"]) if math.isfinite(L["capex"]) else np.nan, L["da"])
    rec["fq_da_to_ppe"] = _div(L["da"], L["ppe_net"])
    rec["fq_gw_pct_assets"] = _div(L["gw_intang"], L["total_assets"])

    # ---- tax / one-offs / deferred revenue ----
    if math.isfinite(L["pretax"]) and L["pretax"] > 0:
        rec["fq_book_tax_rate"] = _div(L["tax_exp"], L["pretax"])
    if math.isfinite(L["pretax_fy"]) and L["pretax_fy"] > 0:
        rec["fq_cash_tax_rate"] = _div(L["taxes_paid"], L["pretax_fy"])   # annual basis
        rec["fq_book_tax_rate_fy"] = _div(L["tax_exp_fy"], L["pretax_fy"])  # same FY
    # discontinued share of CONTINUING earnings, and only off a material
    # continuing base (>= 1% of sales): |NI| near zero made NI-scaled shares explode
    nc = L["ni_cont"]
    if math.isfinite(nc) and math.isfinite(rev) and rev > 0 and abs(nc) >= 0.01 * rev:
        rec["fq_disc_ops_share"] = _div(L["ni_disc"], abs(nc))
    rec["fq_defrev_to_rev"] = _div(L["defrev"], rev)
    # M&A intensity: acquisitions mechanically inflate Beneish SGI / AQI
    if math.isfinite(L["acquisitions"]) and math.isfinite(L["total_assets"]) and L["total_assets"] > 0:
        rec["fq_acq_pct_assets"] = abs(L["acquisitions"]) / L["total_assets"]
    if math.isfinite(L["defrev_p"]) and L["defrev_p"] > 0.05 * (rev_p or np.inf):
        rec["fq_defrev_growth_minus_rev"] = _div(L["defrev"], L["defrev_p"]) - 1 - rev_g
    rec["fq_interest_cover"] = _div(L["opinc"], L["int_exp"]) if (math.isfinite(L["int_exp"]) and L["int_exp"] > 0) else np.nan
    rec["fq_equity_growth"] = _div(L["equity"], L["equity_p"]) - 1 if (
        math.isfinite(L["equity_p"]) and L["equity_p"] > 0) else np.nan

    # ---- Beneish M-score (TTM vs prior TTM; balance now vs year-ago) ----
    gm, gm_p = _div(L["gp"], rev), _div(L["gp_p"], rev_p)
    dsri = _div(_div(L["receivables"], rev), _div(L["receivables_p"], rev_p))
    gmi = _div(gm_p, gm) if (math.isfinite(gm) and gm > 0 and math.isfinite(gm_p) and gm_p > 0) else np.nan
    def _aq(ca, ppe, ta):
        return 1 - (ca + ppe) / ta if all(math.isfinite(v) for v in (ca, ppe, ta)) and ta > 0 else np.nan
    aqi = _div(_aq(L["cur_assets"], L["ppe_net"], L["total_assets"]),
               _aq(L["cur_assets_p"], L["ppe_net_p"], L["total_assets_p"]))
    sgi = _div(rev, rev_p)
    def _dep(da, ppe):
        return da / (da + ppe) if math.isfinite(da) and math.isfinite(ppe) and da + ppe > 0 else np.nan
    depi = _div(_dep(L["da_p"], L["ppe_net_p"]), _dep(L["da"], L["ppe_net"]))
    sgai = _div(_div(L["sga"], rev), _div(L["sga_p"], rev_p))
    def _lev(cl, ltd, ta):
        return (cl + (ltd if math.isfinite(ltd) else 0)) / ta if math.isfinite(cl) and math.isfinite(ta) and ta > 0 else np.nan
    lvgi = _div(_lev(L["cur_liab"], L["lt_debt"], L["total_assets"]),
                _lev(L["cur_liab_p"], L["lt_debt_p"], L["total_assets_p"]))
    _ni_t = (L["ni_cont"] if (rec["fq_cf_basis"] == "quarterly" and math.isfinite(L["ni_cont"]))
             else ni_cf)
    tata = _div(_ni_t - L["cfo"], L["total_assets"])
    core = [dsri, gmi, aqi, sgi, tata]
    if all(math.isfinite(v) for v in core):
        dsri, gmi, aqi, sgi = (_wins(v) for v in (dsri, gmi, aqi, sgi))
        depi = _wins(depi) if math.isfinite(depi) else 1.0
        sgai = _wins(sgai) if math.isfinite(sgai) else 1.0
        lvgi = _wins(lvgi) if math.isfinite(lvgi) else 1.0
        tata = min(max(tata, -0.5), 0.5)
        rec["fq_beneish_m"] = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
                               + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
        rec["fq_beneish_dsri"], rec["fq_beneish_tata"] = dsri, tata

    # ---- trajectories from the raw periods ----
    # gross-margin YoY streak: consecutive latest periods whose GM beats the
    # same period a year earlier
    gms = []
    for d, r in ip:
        rv, g = _f(r.get("revenue")), _f(r.get("grossProfit"))
        gms.append((d, g / rv if math.isfinite(rv) and rv > 0 and math.isfinite(g) else np.nan))
    streak = 0
    for i, (d, g) in enumerate(gms):
        ya = [gg for dd, gg in gms if abs((d - dt.timedelta(days=365) - dd).days) <= 45]
        if not ya or not math.isfinite(g) or not math.isfinite(ya[0]) or g <= ya[0]:
            break
        streak += 1
    rec["fq_gm_yoy_streak"] = float(streak)
    # All trajectory counts are also emitted in MONTHS: a period is 3 months
    # for a quarterly filer and 6 for a half-yearly one, so "3 periods" meant
    # 9 months for one and 18 for the other.
    mpp = 12.0 / n
    rec["fq_gm_yoy_streak_m"] = streak * mpp

    # Date-matched YoY streaks / hit-rate for revenue and net income (the
    # year-ago comparator is found by DATE, 365 +/- 45 days, never by a
    # positional lag that becomes a 2-year comparison for half-yearly filers).
    def _yoy_series(field):
        vals = [(d, _f(r.get(field))) for d, r in ip]
        out = []
        for d, v in vals:
            ya = [vv for dd, vv in vals if abs((d - dt.timedelta(days=365) - dd).days) <= 45]
            out.append((v, ya[0] if ya else np.nan))
        return out
    for field, key, need_pos_base in (("revenue", "rev", False), ("netIncome", "ni", True)):
        pairs = _yoy_series(field)
        run, hits, ncmp = 0, 0, 0
        counting = True
        for v, p in pairs:
            ok = math.isfinite(v) and math.isfinite(p) and (p > 0 if need_pos_base else p != 0)
            if not ok:
                counting = False
                continue
            ncmp += 1
            up = v > p
            hits += up
            if counting and up and v > 0:
                run += 1
            else:
                counting = False
        rec[f"fq_{key}_yoy_streak_m"] = run * mpp
        if ncmp:
            rec[f"fq_{key}_yoy_pos_share"] = hits / ncmp
            rec[f"fq_{key}_yoy_n_cmp"] = float(ncmp)
    # net-debt path over the balance snapshots (newest first)
    nd = []
    for d, r in bp[:5]:
        td, c = _f(r.get("totalDebt")), _f(r.get("cashAndShortTermInvestments"))
        if not (math.isfinite(td) and math.isfinite(c)):
            break   # keep the path contiguous (no skipping a blanked period)
        nd.append(td - c)
    if len(nd) >= 3:
        dec = 0
        for a, b in zip(nd, nd[1:]):
            if a < b:
                dec += 1
            else:
                break
        rec["fq_netdebt_decline_periods"] = float(dec)
        rec["fq_netdebt_decline_months"] = dec * mpp
        # scaled by total assets: a near-zero starting net debt made a
        # percent-of-net-debt change explode (CRM read 834%)
        rec["fq_netdebt_change_pct_assets"] = _div(nd[0] - nd[-1], L["total_assets"])
        rec["fq_netdebt_span_periods"] = float(len(nd) - 1)
    # diluted share count, year over year
    ya_sh = [s for (d, _), s in zip(ip, shares) if abs((ip[0][0] - dt.timedelta(days=365) - d).days) <= 45]
    if shares and math.isfinite(shares[0]) and ya_sh and math.isfinite(ya_sh[0]) and ya_sh[0] > 0:
        rec["fq_shares_yoy"] = shares[0] / ya_sh[0] - 1

    # ---- compact panel rows (kept for future recipe work, no re-pull) ----
    panel = []
    bmap = {d: r for d, r in bp}
    cmap = {d: r for d, r in cp}
    for d, r in ip:
        row = {"symbol": sym, "date": d.isoformat(), "period": r.get("period"), "ccy": ccy}
        for src, key in IS_FLOWS.items():
            row[key] = _f(r.get(src))
        c = cmap.get(d, {})
        for src, key in CF_FLOWS.items():
            row[key] = _f(c.get(src))
        b = bmap.get(d, {})
        for src, key in BS_STOCKS.items():
            row[key] = _f(b.get(src))
        row["shares_dil"] = _f(r.get("weightedAverageShsOutDil"))
        panel.append(row)
    if panel:
        for row, v in zip(panel, normalize_shares([row["shares_dil"] for row in panel])):
            row["shares_dil"] = v
    return rec, panel


def _flush(recs, panel, part_no):
    if recs:
        new = pd.DataFrame(recs)
        if os.path.exists(OUT):
            new = pd.concat([pd.read_csv(OUT, low_memory=False), new], ignore_index=True)\
                    .drop_duplicates("symbol", keep="last")
        new.to_csv(OUT + ".tmp", index=False)
        os.replace(OUT + ".tmp", OUT)
    if panel:
        os.makedirs(_PANEL_PART_DIR, exist_ok=True)
        pd.DataFrame(panel).to_parquet(os.path.join(_PANEL_PART_DIR, f"part_{part_no:05d}.parquet"),
                                       index=False)


def consolidate_panel():
    """Merge panel parts into one parquet (last write per symbol/date wins)."""
    if not os.path.isdir(_PANEL_PART_DIR):
        return 0
    parts = sorted(os.listdir(_PANEL_PART_DIR))
    frames = [pd.read_parquet(os.path.join(_PANEL_PART_DIR, p)) for p in parts]
    if os.path.exists(PANEL):
        frames.insert(0, pd.read_parquet(PANEL))
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="last")
    df.to_parquet(PANEL + ".tmp", index=False, compression="zstd")
    os.replace(PANEL + ".tmp", PANEL)
    for p in parts:
        os.remove(os.path.join(_PANEL_PART_DIR, p))
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--checkpoint-every", type=int, default=250)
    ap.add_argument("--gc-max-mb", type=int, default=3000)
    ap.add_argument("--consolidate", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.consolidate:
        print("panel rows:", consolidate_panel())
        return
    t = pd.read_csv("archetype_tags.csv", usecols=lambda c: c in {"symbol", "archetype_count"},
                    low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    t["archetype_count"] = pd.to_numeric(t["archetype_count"], errors="coerce").fillna(0)
    syms = t.sort_values("archetype_count", ascending=False)["symbol"].tolist()
    if args.max:
        syms = syms[: args.max]
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    part = len(os.listdir(_PANEL_PART_DIR)) if os.path.isdir(_PANEL_PART_DIR) else 0
    print(f"quarterly: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    from concurrent.futures import ThreadPoolExecutor

    def _one(sym):
        # A rate limit is a pause, not a failure: wait it out and retry the
        # SAME symbol (the client already backed off 5x). Stopping the run
        # (or recording the symbol as done) would leave a hole in the universe.
        for attempt in range(12):
            try:
                return enrich_symbol(sym)
            except fc.FMPError as exc:
                if "Limit Reach" in str(exc) or "429" in str(exc):
                    time.sleep(30 * (attempt + 1))
                    continue
                return {"symbol": sym, "fmp_q_status": "error"}, []
        raise fc.FMPError(f"{sym}: still rate limited after 12 waits")

    recs, panel = [], []
    step = args.checkpoint_every
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for b0 in range(0, len(todo), step):
            batch = todo[b0:b0 + step]
            try:
                for r, p in ex.map(_one, batch):
                    recs.append(r); panel.extend(p)
            except fc.FMPError as exc:
                print(f"  rate limited near {b0}: {exc}; checkpointing", flush=True)
                break
            part += 1
            _flush(recs, panel, part); recs, panel = [], []
            st = fc.cache_stats()
            print(f"  quarterly {b0 + len(batch)}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb and (b0 // step) % 20 == 0:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    part += 1
    _flush(recs, panel, part)
    print(f"\nwrote {OUT}: {len(pd.read_csv(OUT)) if os.path.exists(OUT) else 0} rows; "
          f"panel rows {consolidate_panel()}", flush=True)


if __name__ == "__main__":
    main()
