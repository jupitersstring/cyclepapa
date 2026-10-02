# Provenance ledger — every gate-consumed financial variable

Scope: the 121 master columns consumed by archetype gates (parsed from
archetype_tags.py, the same enumeration the figure-coverage audit gate
uses), plus the book-scoring inputs. For each: SOURCE hierarchy,
CONSTRUCTION, GUARDS (bands / evidence rules / qc flags), and the AUDIT
GATE that keeps it honest. Refreshed 2026-09-11 after the repair-first
overhaul; verify any claim against the cited file.

Trust hierarchy (applies to every level):
  0. Audited EDGAR company-facts (US filers), fresh-gated <=135d for TTM
     items, sign-flip superseded by fresher Yahoo, absence-of-evidence
     guard on balance items (EDGAR cash/debt only wins when >= half of
     Yahoo's). Multi-year audited fields (averages, equity CAGR, payout
     levels) merge ungated — a 5yr average is not invalidated by a
     missed quarter.
  1. Yahoo quote data (price/mcap/EV-quote-side) — authoritative, no one
     else carries prices.
  2. Yahoo statement-grade fundamentals-timeseries (trailing CFO/FCF/
     capex — validated == audited on AAPL/MSFT).
  3. Yahoo snapshot (quoteSummary) levels and pre-computed ratios,
     band-guarded, reconciled.
  4. NOTHING is identity-derived where an alternative exists (user
     directive); documented same-source definitional constructions only
     (EBITDA = EBIT + D&A within one filing; UFCF unlevering).

Cross-currency regime (applies to every level and ratio on secondary
listings): declared financialCurrency (PASS 0, authoritative, being
fetched universe-wide) > name-twin home-line bridge > pb-anchored
fx-snap; restated rows get levels in quote currency, ccy_bridge stored,
EV/price ratios rebuilt from restated components EVERY run (Yahoo's own
EV family is mixed-currency on those lines); unresolvable satellites
nulled+flagged ccy_mismatch_suspect, principals never nulled.

## 1. Market data (Yahoo quote, authoritative)
| variable | source & construction | guards / gates |
|---|---|---|
| price | Yahoo price.regularMarketPrice, overwrite each pull | >0 band |
| market_cap | Yahoo price.marketCap (fallback summaryDetail) | >0 band; audit: mcap = price x shares (pence-aware, >10% dev fails) |
| shares_outstanding | Yahoo; snapped to mcap/price when >10% off (GBp .L uses price/100) | pence-mint audit gate |
| market_cap_usd | mcap x fx_to_usd (quote ccy — correct side for mcap) | audit fx checks |
| price_52w_high | Yahoo, lifted to current price when below it (running max is definitional) | recon counter |
| pct_off_52w_high | derive: 1 - price/price_52w_high | bounded by construction |
| price_yoy / momentum_12m (alias) | yartseva_db build from price history | EVIDENCE BOUND (new): nulled where (1+yoy) > 3x the 52w high/low span or yoy < -1 (1841.T's +14,413,000% redenomination artifact; 95 nulled) |
| price_vs_5y_avg, price_pct_of_5y_range | build, price history | consumed as bounded ratios |
| yf_beta, yf_recommendation_mean, n_analysts, analyst_target_upside_pct | Yahoo snapshot, opinion data (not financials) | soft legs only |

## 2. Income-statement levels
| variable | source & construction | guards |
|---|---|---|
| revenue_ttm | EDGAR fresh-gated -> Yahoo (reconcile >1.4x) -> build | de-minimis $2M nulls sales ratios; fx-twin; restatement |
| ebitda_ttm | EDGAR -> Yahoo -> build | EDGAR-grounding audit >=95% agreement; restatement |
| net_income_ttm | direct netIncomeToCommon -> net_margin x revenue (fill only) | mcap/p_e identity derivation REMOVED; restatement |
| gross_margin, op_margin, ebitda_margin, net_margin | Yahoo margins, EDGAR op_margin preferred where audited | ordering reconcile (graded: >10pts flagged, >15pts extreme nulled); op_margin > 100% impossible -> nulled; de-minimis |
| effective_tax_rate | EDGAR only (audited) | gates use soft legs; missing = permissive |
| normalized_ebitda / normalized_ebit / normalized_revenue | 5yr averages of annual series, ONE BASIS per year (EBITDA := EBIT + Reconciled D&A when Yahoo's EBITDA row is missing/incoherent — the RNO.PA mixed-basis root cause), same year set for the pair | inversion (EBIT avg > EBITDA avg) impossible -> audit gate at zero; 2,990 repaired by refetch |

## 3. Cash-flow levels
| variable | source & construction | guards |
|---|---|---|
| cfo_ttm | EDGAR audited -> Yahoo statement trailing -> snapshot | reconcile; restatement |
| fcf_ttm | EDGAR audited -> Yahoo statement trailingFreeCashFlow (validated vs audited; financialData.freeCashflow RETIRED — third-party levered figure, MSFT 0.23x audited) -> snapshot. NO identity fallback | fcf_gt_cfo qc flag; |fcf/mcap|>1 nulls yield AND stored |
| capex_ttm | EDGAR audited -> Yahoo statement trailingCapitalExpenditure -> honestly absent. IDENTITY (cfo-fcf) DELETED — it manufactured negative capex from mixed vintages | rebuilt from primaries EVERY run, no relic survives |
| financing_cf_ttm | EDGAR only (audited) | multi-year merge, structural |
| capital_return_ttm / dividends_ttm / buybacks_ttm | EDGAR audited flow LEVELS (new — were yield-only) | levels merged structurally |
| net_buyback_ttm | build: |repurchases| - |issuance| from financing section | restatement |

## 4. Balance-sheet levels
| variable | source & construction | guards |
|---|---|---|
| cash | Yahoo broad-cash basis (investments included, documented) vs EDGAR (absence guard: EDGAR wins only when >= half Yahoo); DIRECTIONAL master-under-half repaired | ev_comp_gap qc flag; financials exempt from 20x band |
| total_debt | reconcile (lease-inclusive fresher wins); zeros repairable (hollow-zero immortality fixed) | ccy band |
| equity | audited EDGAR StockholdersEquity fresh-gated (2,543 adopted) -> build balance sheet | pb identity audit gate |
| ncav | build: current assets - total liabilities (correct aliases verified) | ncav_pct recomputed vs CURRENT mcap every run (vintage disease fixed); NCAV>1.5x equity flagged ncav_gt_equity, silent violation fails audit |
| net_working_capital | EDGAR: current assets - current liabilities | multi-year merge |
| assets | EDGAR total assets | — |
| interest_coverage | EDGAR only (audited) | soft legs; near-zero interest -> huge values are REAL (no false band) |
| net_debt_ebitda | derived from reconciled debt/cash/ebitda | recompute family |

## 5. Valuation ratios (constructed or adopted-with-guards)
| variable | rule |
|---|---|
| pb | CONSTRUCTED: (A) mcap/equity where audited equity exists; (B) price_major/bookValue (fetched primitives; cents-normalized; valid where quote==financial ccy); (C) Yahoo priceToBook ONLY behind per-row evidence guards — pence (NI/ROE discriminator: Hunting 94.8->0.95, Games Workshop untouched at ratio 1.0000; bookValue adjudication file for the evidence-less; 172 repaired), cross-ccy recompute. Audit: pb == mcap/equity where audited equity exists (>25% fails) |
| p_e | Yahoo trailingPE band-guarded; recomputed mcap/NI on restated lines every run | audit identity >25% |
| p_s | Yahoo/derive mcap/revenue; rebuilt on restated lines | de-minimis |
| ev_ebitda / ev_sales / ev_ebit | Yahoo enterpriseToEbitda/Revenue authoritative in-band ((-150,150)/(-100,100)); negative-EV multiples KEPT (real: negative EV over positive denominator); non-positive denominator -> NaN; REBUILT from restated components on cross-ccy lines every run (Yahoo's EV is mixed-currency there — T3O.F proof); ev_ebit null-guard now conditioned on KNOWN denominators only (the EDGAR-only opinc guard wiped 14,442 non-US rows — fixed) | unit-sanity level repair; implied-multiple fill only where no level exists |
| enterprise_value | Yahoo EV; row-consistency vs mcap+debt-cash (ev_comp_gap flagged >25% — broad-cash basis documented); REBUILT on restated lines | neg_ev qc flag |
| ev_gross_profit | EV/GP — the CHEAPNESS face (distinct from gross_profitability) | den>0 |
| p_tb | price/tangible book (EDGAR tangible_book_per_share where audited) | pence-aware |
| pegy, evsg, ev_ebitda_gy, psg | growth-adjusted composites from the above | inherit component guards |

## 6. Yields (LEVERED over MCAP / UNLEVERED over EV — user rule)
| variable | construction |
|---|---|
| fcf_yield | fcf_ttm/mcap, band ±100% both signs; stored value nulled when components prove impossibility (WIMI rule) |
| owner_earnings_yield | TRUE Buffett OE = NI + implied D&A (EBITDA - op_margin x rev, same row) - capex(primary), over mcap; REBUILT WHOLESALE each run AFTER margin sanitation (KTTA irreproducibility fixed); absent without capex. Audit: matches own construction; never exists without capex |
| cfo_yield / earnings_yield | cfo/mcap, NI/mcap, recomputed each run | audit identity |
| robust_cash_yield | row median of (fcf/mcap, cfo/mcap, NI/mcap) — FCF under its OWN name (the owner_earnings alias double-count is dead) |
| cash_return_ev | UNLEVERED: (CFO + backed-out interest x (1-tax))/EV; CFO/EV only when leverage immaterial |
| ufcf_yield | unlevered FCF / EV (EV-paired sibling of fcf_yield) |
| dividend_yield | Yahoo (0-50% band) / EDGAR dividends_ttm | freshness lag noted |
| capital_return_yield / buyback_yield | EDGAR audited LEVELS / CURRENT mcap, recomputed every run (map-time-mcap freeze fixed) |
| oe_avg_yield, avg_earnings_yield, fcf_avg_yield | Graham/Templeton 5yr-average levels over mcap |
| net_cash_pct_mcap / cash_pct_mcap / cash_pct_ev / ncav_pct_mcap | levels over CURRENT mcap, recomputed every run; 20x impossibility band (ccy class, financials exempt); no-anchor satellites nulled |
| gross_profitability | Novy-Marx GP/ASSETS (was GP/EV — a cheapness yield wearing a quality label; fixed, EV face lives in ev_gross_profit) |
| capex_intensity / fcf_conversion / fcf_margin / cash_conversion | capex/rev, fcf/EBITDA+, fcf/rev, CFO/EBITDA (±50 base-effect band) |

## 7. Quality / returns
| variable | source |
|---|---|
| roce | build: EBIT/invested capital (falls back to roe when IC absent — documented) |
| roe / roa | Yahoo (bands ±10/±5); roe is currency-free (NI/equity same ccy) — used as pence-immune discriminator |
| roic_after_sbc, sbc_pct_revenue | EDGAR only (audited) |
| eps streaks (eps_positive_streak_q etc.), earnings_beat_* | build: quarterly diluted-EPS actuals / earnings surprise history |
| equity_cagr_5y | EDGAR audited equity series |
| oe_avg / ni_avg / fcf_avg / capex_avg | EDGAR per-FY aligned averages (<=5yr, >=3yr); STRUCTURAL merge each run (one-off-merge death fixed) |

## 8. Growth / inflection family (build-time, quarterly series)
rev/ebitda/cfo/fcf yoy, qoq_ttm, seq, accel, inflection, first_positive,
margin deltas, rev_3y_cagr, shares_yoy, shares_3y_cagr, fcf_per_share_yoy,
gross_profit_yoy, ebit_growth_yoy, operating_leverage_ratio,
incremental_ebitda_margin.
  Provenance: yartseva_db build from Yahoo quarterly statements; WEAKEST
  family (not re-reconciled between builds; base effects possible).
  Guards: NPI consumes them only through the guarded construction
  (>1000% components dropped, ±300pp clip); operating_leverage_ratio
  requires |rev_yoy| > 1e-6; shares_yoy corroborates cannibal legs
  (~(shares_yoy > 0)). KNOWN LIMITATION, logged: full re-derivation of
  the growth family from refreshed statements is future work.

## 9. Scores / flags
| variable | construction |
|---|---|
| yartseva_score | build composite of the 7 Yartseva predictors (paper-aligned) |
| not_priced_in_score | mean of (growth - price return) differentials, base-effect-guarded, clipped; bounded [-3,3] BY CONSTRUCTION; audit gate |
| cash_gt_ev_flag, graham_net_net_flag, cheapness_under_7x_flag | boolean derivations of guarded inputs |
| melt_demotion | enrich: cash-on-cash-aware, improvement-lenient (x0.40 hard / x0.65 soft, never bars) |
| qc_flags | per-row anomaly markers (op_gt_ebitda_margin, gross_lt_op_margin, fcf_gt_cfo, ev_comp_gap, fx_twin_dev, neg_ev, edgar_grounded, edgar_currency_arbitration, unit_repaired, fcf_yf_adopted, ccy_restated, ccy_mismatch_suspect, pence_pb_repaired, ncav_gt_equity) — NOTHING is silent |

## 10. Ownership / other
insider_ownership_pct (Yahoo, 0-1 band), dividend/dividends data,
avg_earnings_surprise, sector/country/currency (Yahoo profile; country
drives the home-line currency anchor), fx_to_usd (quote-currency rate —
the mcap-correct side; statement levels cross via ccy_bridge).

## Known weak-provenance items (open, logged)
1. Growth/inflection family: build-time only (Section 8).
2. XP-class singletons: quote-ccy line, foreign financial ccy, no twin,
   no declared currency until the running fetch reaches them — then
   PASS 0 repairs automatically.
3. dividend_yield freshness (~1.5x lag observed on 2 names).
4. price_vs_5y_avg / price_pct_of_5y_range: build-time price history.
