# Accounting-concepts review — every concept behind every measure

Directive: "check every accounting concept we are using for our measures
to ensure it's rigorous, without error and not wrongfully calculated."
This is the CONCEPT layer (is the definition right?) above the formula
audits (is the arithmetic right?). For each concept: canonical
definition -> our construction -> verdict. CORRECTED = a defect found by
this review and fixed; CONVENTION = a defensible documented choice that
differs from one textbook variant; OK = matches the canonical
definition. Reviewed 2026-09-12.

## Income / profitability

| Concept | Canonical | Ours | Verdict |
|---|---|---|---|
| Revenue | contract revenue excl. collected taxes | XBRL Revenue*ExcludingAssessedTax preferred, IncludingAssessedTax LAST; single-concept TTM | OK (alias order carries the definition) |
| Net income (for P/E, ni_avg, margins) | PARENT-attributable income | NetIncomeLoss before NCI-inclusive ProfitLoss (was reversed — CORRECTED in the formula audit); Yahoo netIncomeToCommon direct | OK after correction |
| EBIT | operating income | OperatingIncomeLoss; Yahoo "EBIT" row REJECTED where it embeds unusual items against a Normalized pair (RNO.PA class) | OK after correction |
| EBITDA | EBIT + D&A, ONE basis | rebuilt as EBIT + Reconciled D&A whenever the provider row is incoherent with EBIT (annual AND quarterly frames) | OK after correction |
| D&A | depreciation+depletion+amortization, excl. impairments | DepreciationDepletionAndAmortization family (impairment concepts never aliased in) | OK |
| Normalized (Templeton) earnings | multi-year average, one basis, same year set | 5yr aligned averages, same-basis rebuild, inversion impossible-pair gate | OK after correction |
| Effective tax rate | tax expense / pretax income | IncomeTaxExpenseBenefit / pretax continuing-ops, clipped to a sane band | OK |
| NOPAT | EBIT x (1 - company's OWN effective tax) | WAS flat 25% for every company (zero-tax payers and 30%+ jurisdictions equally) — now per-year ETR from the filing, clipped 0-45%, 25% only as fallback | CORRECTED (this review) |
| Owner earnings (Buffett) | NI + D&A - MAINTENANCE capex | NI + implied D&A - TOTAL capex | CONVENTION (conservative: total capex >= maintenance capex, so OE is understated, never flattered; maintenance capex is not separable from filings) |
| Gross profitability (Novy-Marx) | GP / total assets | GP / assets (was GP/EV — a cheapness yield in a quality label) | OK after correction |

## Balance sheet

| Concept | Canonical | Ours | Verdict |
|---|---|---|---|
| Cash | unrestricted cash + equivalents | restricted-inclusive rollup demoted to last resort; Yahoo broad basis (incl. investments) documented + directional guard | OK after correction |
| Total debt | ST + LT borrowings, no double count | LongTermDebt/Borrowings recognized as TOTALS (never summed with an ST bucket); extended current-debt aliases; unobserved stays ABSENT (never fabricated 0) | OK after correction |
| Equity | stockholders' equity (parent) | audited StockholdersEquity preferred, parent-attributable aliases first | OK |
| Tangible equity | equity - goodwill - other intangibles | same; requires OBSERVED equity; IntangibleAssetsNetExcludingGoodwill (no goodwill double-count) | OK |
| NCAV (Graham) | current assets - TOTAL liabilities - PREFERRED - NCI (the COMMON holder's claim) | WAS current assets - liabilities only: preferred stock ranks ahead of common and NCI sits in EQUITY (so no liabilities row ever removes it) — NCAV was overstated for preferred/NCI-heavy names, the fake-net-net direction. Now deducts both (EDGAR concepts MinorityInterest/PreferredStockValue; yfinance rows) | CORRECTED (this review) |
| Net working capital | current assets - current liabilities | same | OK |
| Invested capital (for ROIC/ROCE) | debt + equity (- excess cash) | filing's own "Invested Capital" row preferred; identity equity + debt - ALL cash as fallback; requires observed equity and IC > 0 | CONVENTION (subtracting all cash rather than excess-only makes returns look BETTER for cash-heavy names — noted; the melt/quality gates never rely on IC alone) |
| "ROCE" naming | EBIT / capital employed (assets - current liab.) | EBIT / invested capital (ROIC-style denominator) | CONVENTION, documented in the ledger — the measure is internally consistent everywhere it is compared |

## Cash flow

| Concept | Canonical | Ours | Verdict |
|---|---|---|---|
| CFO | operating section total | statement CFO only (never derived) | OK |
| Capex | PP&E purchases (positive outflow) | primary concepts only; the cfo-fcf identity DELETED | OK after correction |
| FCF (levered) | CFO - capex, same window | window-matched subtraction; yields over MARKET CAP | OK after correction |
| UFCF / EV-paired yields | FCF + after-tax interest, over EV | backed-out interest x (1-ETR); unlevered-over-EV pairing enforced | OK |
| Dividends / buybacks | cash paid to COMMON holders | minority-interest dividends REMOVED from the alias set; buybacks = repurchase magnitudes; yields recomputed vs CURRENT mcap from audited LEVELS | OK after correction |
| Interest charge (coverage) | interest EXPENSE | expense concepts preferred over cash paid (capitalized/PIK gap) | OK after correction |

## Valuation

| Concept | Canonical | Ours | Verdict |
|---|---|---|---|
| Market cap | price x shares (pence-aware) | Yahoo authoritative; identity-gated | OK |
| Enterprise value | mcap + debt + PREFERRED + NCI - cash | constructed EV (EDGAR mapper) now ADDS preferred + NCI; Yahoo-sourced EV omits them by provider construction — rows where those audited claims exceed 5% of |EV| carry the ev_ex_senior_claims flag (identifiable, never silent) | CORRECTED (this review; Yahoo-side flagged) |
| P/B | mcap / common equity | constructed from primaries (audited equity; bookValue) — never the provider ratio where a primary exists | OK after correction |
| P/E | price / TRAILING diluted EPS | trailing only; forward NEVER fills a trailing label (two sites removed) | OK after correction |
| EV multiples | EV over POSITIVE denominator; negative EV is real | positive-denominator policy everywhere incl. provider fallbacks; negative-EV multiples kept | OK after correction |
| Cash-adjusted P/E | (mcap - net cash)/NI, negative-or-cheap doctrine | as specified; Graham-average OR-leg | OK |

## Growth / returns / composites

| Concept | Canonical | Ours | Verdict |
|---|---|---|---|
| YoY / TTM windows | 12 months vs prior 12, consecutive periods, one cadence | cadence-detected (quarterly vs semi-annual); consecutive-quarter checks; roll-forward start-aligned; per-share values never roll-forwarded | OK after correction |
| ROIIC | dNOPAT / dIC over DEPLOYED capital (dIC > 0) | positive-deployment guard, contiguous-fiscal-year windows, NOPAT on the company's own tax | OK after correction |
| Equity CAGR (book compounding) | growth in book value PER SHARE (buybacks shrink total equity while compounding per-share value) | TOTAL-equity CAGR — penalizes cannibals; consumers keep buyback-corroborated OR-legs so a heavy repurchaser is not excluded outright | KNOWN LIMITATION, logged: per-share series needs annual share counts (dei concept now fetched); upgrade at next extract cycle |
| Segment growth (fastest) | like-for-like FY base | FY base, Q strictly fallback; latest-quarter CONFIRMATION and consecutive-growth streak UPWEIGHT the blend (user directive) rather than replace the base | OK after correction |
| Composites | renormalize over observed legs; missing = unranked | alta-fox renormalized; enrich/rank fillna(0) removed; caps enforced in code not comments | OK after correction |

## Enforcement
Every CORRECTED row above is also guarded: the 180-check methodology
audit, the mutation test (32/0), stored-value bands (38 columns), and
the flow-through gates hold each fix in place. The two CONVENTION rows
and the one KNOWN LIMITATION are documented here and in the provenance
ledger rather than silently divergent.

## Completeness proof (are ALL measures covered?)
Mechanical enumeration of all 268 master columns -> 192 classified as
accounting measures -> name-diffed against this review + the provenance
ledger + the formula-audit scopes. The diff surfaced 89 name-mismatches;
cross-referencing showed all but six were audited at their formula sites
(the growth/inflection family under the cadence findings, cheapness
blends under M11, ROCE windows under M3, price differentials under the
evidence bounds, beat streaks under M8/L4, tenbagger_implied_return and
evsales_derate_gap verified already fully guarded in place). The six
genuinely unreviewed measures were then audited:
- fcf_run_rate_delta / fcf_eta_quarters / fcf_projected_positive_in_n
  (FCF runway family): construction sound (improving-only, one-cadence
  step) EXCEPT the quarter-unit label — at semi-annual cadence one step
  is half a year, so eta now scales by 4/periods-per-year (the
  <=4-quarters flag was twice as permissive for that cohort). Stored
  band 0-40 quarters added.
- net_debt_to_fcf: construction sound (positive-FCF denominator, signed
  net debt); stored band (-100, 200) years added (near-zero-FCF tail).
- tenbagger_implied_return, evsales_derate_gap: verified sound as built
  (clipped lenses, floored P/S, capped output; artifact-clamped stock
  return, NaN-means-no-evidence).
Every accounting measure in the master now traces to a reviewed
construction; the claims-conformance gate holds the documented ones to
their implementations on every run.
