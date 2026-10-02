# EDGAR XBRL harvesting audit — June 2026

**Branch:** `claude/yartseva-multibagger-database-lZS4a`
**Cache:** 8,021 CIK#.json files in `edgar_cache/` (10,433 SEC tickers attempted; 2,412 returned empty XBRL — ETFs / trusts).
**Question:** Are we extracting everything material from the cached XBRL data?

This audit samples 500 cached files and ranks the us-gaap concepts by how often they appear, then compares against what `edgar_universe_extract.py` + `edgar_roic_roiic.py` actually read.

## High-frequency concepts NOT currently extracted

| Concept | Sample freq | What it gives us |
|---|---:|---|
| NetCashProvidedByUsedInFinancingActivities | 72.6% | Total financing cash flow (dividends + buybacks + debt issuance/repayment) |
| NetCashProvidedByUsedInInvestingActivities | 70.2% | Total investing (M&A spend, divestitures) — distinct from capex |
| RetainedEarningsAccumulatedDeficit | 70.6% | Cumulative retained earnings — compounder signature |
| EarningsPerShareBasic / Diluted | 67–66% | EPS — currently we don't extract directly |
| IncomeTaxExpenseBenefit | 65.8% | Tax paid — enables REAL effective tax rate vs our 25% assumption |
| IncomeLossFromContinuingOperationsBeforeIncomeTaxes | 62% | Pre-tax income — denominator for real tax rate |
| PropertyPlantAndEquipmentNet | 61% | Net PP&E — asset turnover, depreciation context |
| InterestPaidNet | 58.6% | Cash interest — better leverage signal than B/S debt |
| ShareBasedCompensation | 58.6% | SBC — quality-of-earnings flag |
| PaymentsOfDividends | ~50% | DIRECT dividend cash paid — currently only inferred via shares-growth check |
| PaymentsForRepurchaseOfCommonStock | ~45% | Buybacks paid — currently only inferred via shares-growth |
| ProceedsFromIssuanceOfLongTermDebt / RepaymentsOfLongTermDebt | ~40% | Debt issuance / repayment — capital structure dynamics |
| AccountsReceivableNetCurrent | ~55% | A/R turnover, working-capital quality |
| InventoryNet | ~50% | Inventory dynamics |
| AccountsPayableCurrent | ~50% | A/P, working-capital position |

## Why this matters

Three archetypes were built without direct access to the underlying signal:

1. **BuybackCompounder** currently fires on `shares_growth_5y < -5%` — INFERRED from share-count series. With `PaymentsForRepurchaseOfCommonStock`, we'd know the actual cash spent on buybacks per year, the buyback yield, and whether buybacks were funded by retained earnings vs new debt.

2. **NoDilution** uses the same shares-growth proxy. With direct `PaymentsOfDividends` + buyback figures, we'd know the total capital-return yield (`(dividends + buybacks) / market_cap`).

3. **CashQuality** compares NOPAT-ROIC vs FCF-ROIC. With `ShareBasedCompensation`, we'd compute a "cash-after-SBC" ROIC that excludes a major non-cash earnings item that some SaaS / tech companies use to dress up GAAP profits.

4. **M5 engine score** uses `NOPAT = OpInc × (1 − 0.25 assumed tax)`. With direct `IncomeTaxExpenseBenefit / PreTaxIncome`, we'd compute the REAL effective rate — a high-tax-cash company looks better than a tax-shield company on this adjusted basis.

## What we DO extract (for completeness)

`edgar_universe_extract.py` alias chains cover:
- Revenue (5 aliases) ✓
- OperatingIncomeLoss ✓
- NetIncomeLoss + 2 aliases ✓
- Assets / AssetsCurrent ✓
- Liabilities / LiabilitiesCurrent ✓
- StockholdersEquity + 1 alias ✓
- Goodwill ✓
- IntangibleAssetsNetExcludingGoodwill + 1 alias ✓
- Cash + 2 aliases ✓
- Long-term debt (non-current + current) ✓
- CFO ✓
- Capex (3 aliases) ✓
- DepreciationDepletionAndAmortization + 2 aliases ✓
- CommonStockSharesOutstanding + 2 aliases (multi-year only) ✓
- GrossProfit ✓

## Fix plan

1. **Add concepts** to `edgar_universe_extract.py`:
   - PaymentsOfDividendsCommonStock + PaymentsOfDividends (alias chain)
   - PaymentsForRepurchaseOfCommonStock + PaymentsForRepurchaseOfEquity
   - ShareBasedCompensation
   - IncomeTaxExpenseBenefit
   - IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
   - RetainedEarningsAccumulatedDeficit
   - EarningsPerShareBasic + EarningsPerShareDiluted
   - PropertyPlantAndEquipmentNet
   - InterestPaidNet (and InterestExpense as fallback)
   - NetCashProvidedByUsedInFinancingActivities
   - NetCashProvidedByUsedInInvestingActivities

2. **Compute derived fields**:
   - `dividends_ttm`, `buybacks_ttm`, `sbc_ttm`
   - `capital_return_yield = (dividends_ttm + buybacks_ttm) / market_cap`
   - `real_effective_tax_rate = tax_expense / pretax_income` (with clipping)
   - `cash_ebit = opinc - sbc` (SBC-adjusted operating income)
   - `roic_after_sbc = (cash_ebit × (1 − tax_rate)) / invested_capital`
   - `eps_basic`, `eps_diluted`
   - `retained_earnings` (point-in-time + 5y growth)
   - `interest_coverage = opinc / interest_paid`

3. **Re-extract from cache** — no new network calls needed; just re-run `edgar_universe_extract.py` and the cache wins.

4. **New archetypes** that use these:
   - `arch_capital_returner` — capital_return_yield > 5%
   - `arch_low_sbc_quality` — sbc_pct_revenue < 2% AND op_margin > 5%
   - `arch_retained_compounder` — retained_earnings_5y_cagr > 8% AND no_dilution
   - `arch_tax_efficient` — real_effective_tax_rate < 0.15 with positive pretax income (real not loss-driven)

5. **M5 engine update** — use real_effective_tax_rate instead of 0.25 assumption.

This is **all derivable from cached XBRL data** — no new network calls.
