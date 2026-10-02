"""Restore a true fourth quarter where FMP carries the FISCAL YEAR in the Q4 slot.

Some filers publish only the full fiscal year for their fourth quarter (the
10-K has no separate Q4), and FMP's quarterly series then shows the ANNUAL
figure in the Q4 row: OpenText's 2026-06-30 "quarter" reads revenue $5.2B
against ~$1.3B for each of Q1-Q3, so any TTM through it jumps to $9.1B. ~4%
of covered companies have at least one such row (1,424 of 32,166), 148 of
them in their latest quarter.

The restoration is the analyst's identity Q4 = FY - (Q1 + Q2 + Q3), applied to
every FLOW line of the row (income statement, cash flow); balance-sheet rows
are point-in-time and unaffected. It is applied only where all of this holds:
  * the row is labelled Q4 and Q1, Q2, Q3 of the SAME fiscal year are present
  * the "Q4" revenue is > 2.5x the median of Q1-Q3 (a whole year, not a
    seasonal quarter: even strongly seasonal retailers' Q4 is < ~2x)
  * the implied true Q4 (FY - 9 months) is a normal quarter: 0.4x-2.5x the
    Q1-Q3 median
so a genuine spike quarter is never rewritten. Cash-flow rows are restored
for the SAME periods the income statement identified (the substitution is a
filing-level artifact that hits every statement of that period together).
Per-share lines and share counts are not flows and are left untouched.
"""
from __future__ import annotations

import math

import numpy as np

FLOW = {
    "is": ("revenue", "costOfRevenue", "grossProfit", "researchAndDevelopmentExpenses",
           "generalAndAdministrativeExpenses", "sellingAndMarketingExpenses",
           "sellingGeneralAndAdministrativeExpenses", "otherExpenses", "operatingExpenses",
           "costAndExpenses", "netInterestIncome", "interestIncome", "interestExpense",
           "depreciationAndAmortization", "ebitda", "ebit", "nonOperatingIncomeExcludingInterest",
           "operatingIncome", "totalOtherIncomeExpensesNet", "incomeBeforeTax", "incomeTaxExpense",
           "netIncomeFromContinuingOperations", "netIncomeFromDiscontinuedOperations",
           "otherAdjustmentsToNetIncome", "netIncome", "netIncomeDeductions", "bottomLineNetIncome"),
    "cf": ("netIncome", "depreciationAndAmortization", "deferredIncomeTax", "stockBasedCompensation",
           "changeInWorkingCapital", "accountsReceivables", "inventory", "accountsPayables",
           "otherWorkingCapital", "otherNonCashItems", "netCashProvidedByOperatingActivities",
           "investmentsInPropertyPlantAndEquipment", "acquisitionsNet", "purchasesOfInvestments",
           "salesMaturitiesOfInvestments", "otherInvestingActivities", "netCashProvidedByInvestingActivities",
           "netDebtIssuance", "longTermNetDebtIssuance", "shortTermNetDebtIssuance", "netStockIssuance",
           "netCommonStockIssuance", "commonStockIssuance", "commonStockRepurchased", "netPreferredStockIssuance",
           "netDividendsPaid", "commonDividendsPaid", "preferredDividendsPaid", "otherFinancingActivities",
           "netCashProvidedByFinancingActivities", "effectOfForexChangesOnCash", "netChangeInCash",
           "operatingCashFlow", "capitalExpenditure", "freeCashFlow", "incomeTaxesPaid", "interestPaid"),
}


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _key(r):
    return str(r.get("fiscalYear") or ""), str(r.get("period") or "").upper()


def restore(rows, kind: str, dates=None):
    """Return (rows with restored Q4 flows, set of restored period dates).

    kind 'is' detects on revenue; kind 'cf' restores the `dates` the income
    statement identified. Rows are copied, never mutated in place."""
    if not rows:
        return rows, set()
    by = {}
    for r in rows:
        fy, p = _key(r)
        if fy and p in ("Q1", "Q2", "Q3", "Q4"):
            by[(fy, p)] = r
    fixed = set()
    out = []
    for r in rows:
        fy, p = _key(r)
        prior = [by.get((fy, q)) for q in ("Q1", "Q2", "Q3")]
        if p != "Q4" or not fy or any(x is None for x in prior):
            out.append(r)
            continue
        if kind == "is":
            q4 = _f(r.get("revenue"))
            q = [_f(x.get("revenue")) for x in prior]
            if not (all(math.isfinite(v) and v > 0 for v in q) and math.isfinite(q4)):
                out.append(r)
                continue
            med = float(np.median(q))
            implied = q4 - sum(q)
            if not (q4 > 2.5 * med and 0.4 * med <= implied <= 2.5 * med):
                out.append(r)
                continue
        elif dates is None or r.get("date") not in dates:
            out.append(r)
            continue
        r2 = dict(r)
        for k in FLOW[kind]:
            v, ps = _f(r.get(k)), [_f(x.get(k)) for x in prior]
            if math.isfinite(v) and all(math.isfinite(x) for x in ps):
                r2[k] = v - sum(ps)
        r2["_fy_q4_restored"] = True
        fixed.add(r.get("date"))
        out.append(r2)
    return out, fixed
