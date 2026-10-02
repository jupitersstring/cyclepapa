# Deep per-measure examination: spirit → FMP

A first-principles pass over every archetype and score: what each measure is
*trying* to detect (its spirit), why its current data is a weak proxy, and the
FMP endpoint + derived metric that serves the intent. This is the synthesis;
the per-theme detail sits below. Governing rule unchanged: FMP is a secondary,
source-tagged overlay — better data for an existing leg or a **surfaced
confirming/disqualifying flag**, never a new hard veto.

## The one architectural conclusion

The 160 measures do not have 160 independent data needs. Almost every weakness
traces to **four upstream proxy engines**, and the same FMP capability fixes
each: **FMP's multi-period statement endpoints** — `income-statement`,
`balance-sheet-statement`, `cash-flow-statement`, `financial-growth`
(annual + quarter), plus `enterprise-values`, `historical-market-capitalization`,
`dividends`, `splits`, and `revenue-*-segmentation`. These are verified live on
our key but **not yet consumed** by `fmp_enrich.py` (which today pulls only the
TTM bulks and the per-symbol governance/insider/earnings passes). That
untapped statement history is where the multi-year *evolution* the archetypes
reach for actually lives.

The four engines and their fix:

| Engine (today) | Powers | Weakness | FMP replacement |
|---|---|---|---|
| **Yahoo quarterly sequential** (`*_qoq_ttm`, `*_seq`, `*_accel`, `*_inflection`, `*_first_positive`) | ~40 inflection / operating-leverage archetypes | ≤5 quarters, seasonality-/restatement-fragile, noisy, US-and-lucky | `income-statement`/`cash-flow?period=quarter&limit=12` → clean 12-quarter TTM series; confirmed (2-quarter) inflection; true 2nd-difference acceleration |
| **EDGAR streaks** (`rev_yoy_streak_q`, `ni_yoy_streak_q`, `rev_yoy_pos_share_12q`) | audited-streak / compounder XR archetypes | US SEC filers only; synthesizes missing Q4 | `income-statement?period=quarter` → global gap-free streaks, real Q4 |
| **EDGAR ROIC/ROIIC lindy** (`roic_lindy`, `roiic_lindy`, `n_yrs_positive_*`, `equity_cagr_5y`) | the entire quality/compounder theme + forensic multi-year legs | US-only → ~29k non-US names fall to a degraded single-year ROCE fallback | `income`+`balance`+`cash-flow` (annual, multi-period) + historical `key-metrics.returnOnInvestedCapital` → same math, global |
| **Synthetic multiple** (`ev_sales_change_yoy`) | the "unrerated / coiled-spring" divergence family | one-point reconstruction from current debt + a single `price_yoy` | `enterprise-values` + `historical-market-capitalization` → real dated EV/mcap path; `divergence = revenue_cagr − ev_sales_change` |

Plus two capital-allocation-specific fixes: the **~4-5%-covered capital-return
snapshots** (`buyback_yield`, `capital_return_yield`, `dividend_yield`,
`financing_cf_ttm`) become **audited multi-year cash-flow history**
(`commonStockRepurchased`, `dividendsPaid`, `netStockIssuance`, the diluted
share-count path), and **yield snapshots** become **dividend track records**
via the `dividends` feed. And two forward capabilities the pipeline entirely
lacks today: **forward consensus** (`analyst-estimates`) turns backward
inflection screens forward-looking, and **grade/estimate-revision flow**
(`grades-historical`) is the literal "awakening" signal measured as a change,
not a static level.

## What is already shipped against this conclusion

- **`fmp_dynamics.py`** pioneers the multi-period statement spine for the
  dynamic archetypes: from `income-statement?period=quarter&limit=13` +
  `enterprise-values` + `analyst-estimates` it computes clean global streaks
  (`fmp_dyn_rev_streak_q`, `fmp_dyn_ni_streak_q`), true acceleration
  (`fmp_dyn_rev_accel`), confirmed inflection (`fmp_dyn_*_turned_positive`),
  fitted incremental operating margin (`fmp_dyn_incremental_ebit_margin`), the
  real multiple-vs-fundamental divergence (`fmp_dyn_unrerated_gap`), forward
  EBIT/EPS crossings (`fmp_dyn_fwd_ebit_crossing`), and the forward
  "asleep" underestimate gap (`fmp_dyn_fwd_underestimate_gap`). Surfaced as
  non-veto confirming flags (`fmp_dyn_unrerated_flag`,
  `fmp_dyn_accelerating_flag`, `fmp_dyn_op_leverage_flag`,
  `fmp_dyn_growth_streak_flag`, `fmp_dyn_fwd_inflection_flag`,
  `fmp_dyn_forward_asleep_flag`). Validated on NVDA (9-quarter streak, unrerated
  gap 0.95, forward-underestimate gap 0.73), RIVN (forward EBIT crossing), and
  international names (Toyota, Tencent) — so the spine already reaches ex-US.
- **`fmp_enrich.py`** already supplies the TTM half: Piotroski/Altman,
  ROIC/ROCE/margins, income quality, capex/depreciation, cash-conversion-cycle,
  DuPont burdens, Graham net-net, price-to-fair-value, plus the per-symbol
  exec-comp + insider alignment ratio and earnings beat/surprise.

## Priority roadmap (ranked, all additive / non-veto)

1. **Complete the dynamic spine (in progress):** finish the `fmp_dynamics.py`
   run over all 16k dynamic-archetype firers (US + international), then wire the
   confirming flags into the inflection / streak / unrerated / forward-crossing
   archetypes. *Largest dynamic win; already under way.*
2. **Global ROIC/ROIIC/streaks from FMP statements:** reproduce
   `edgar_roic_roiic.py` and `edgar_streaks.py` math from FMP multi-period
   statements, promoting the ~29k non-US names from the degraded single-year
   ROCE fallback to full durable-lindy treatment. *Largest reach win.*
3. **Audited capital-return history:** pull `cash-flow-statement` multi-year
   (`commonStockRepurchased`, `dividendsPaid`, `netStockIssuance`) + the diluted
   share-count path + `dividends`/`splits` → universal, track-record capital-
   return signals replacing the 4-5%-covered snapshots. Fixes the whole
   buyback/returner/cannibal family and the Cluseau realizable-book cash-trend.
4. **Real multiple history:** `enterprise-values` + `historical-market-cap`
   → true `ev_sales_change` and the coiled-spring divergence for the unrerated
   family (partly shipped in the dynamics pack).
5. **Analyst depth + revision flow:** `price-target-consensus`, `grades-consensus`,
   `grades-historical`, deep `earnings` → replace the ~11%-covered Yahoo analyst
   snapshot and 4-quarter beat cap across the analyst/sentiment family; grade
   flow is the leading "awakening" signal.
6. **Segment trajectory:** `revenue-product/geographic-segmentation` multi-year
   → global segment growth / mix-shift for the segment-mix theme (revenue only;
   segment margins remain unavailable).

## Per-theme detail

The four theme analyses (dynamic; value + capital-allocation; quality + analyst;
forensic + segment + events) each enumerate every measure with spirit →
weakness → FMP derivation. Highlights:

### Dynamic / inflection / evolution (the emphasis)
- **Confirmed inflection** replaces 2-point sign flips: require `yoy[t]>0 AND
  yoy[t-1]>0` after `yoy[t-2]<=0` from a real 12-quarter series — kills the
  single-noisy-quarter false positives in `arch_kpi_threshold`,
  `arch_micro_activist_inflect`, `arch_wolf_*`, the `*_first_positive` legs.
- **Acceleration as a true 2nd difference** (not the coarse annual fallback the
  Yahoo engine silently uses) for `rev_accel`, `oper_leverage_score`,
  `arch_wolf_compounder`, `arch_regime_cyclical`.
- **Deleveraging proof:** quarterly `balance-sheet` net-debt series gives the
  literal paydown `arch_weschler_levered_equity` / `arch_oak_deleveraging` can
  only proxy today (the code concedes there is no prior-period debt column).
- **Forward crossings:** `analyst-estimates` next-FY EBIT/EPS turning positive
  is the true "before it crosses" confirmation for `arch_xr_leverage_detonation`,
  `arch_xr_pre_scale_margin`, `arch_tenbagger_path` (forward terminal growth).
- **"Asleep, forward edition":** forward consensus lowballing the delivered
  trajectory (`fmp_dyn_forward_asleep_gap`) — the guidance-off-the-mark signal.

### Value / capital-allocation
- **Audited diluted-share-count path** is the strongest single case: it replaces
  the noisy `shares_yoy` snapshot and the buyback-yield creation/redemption
  artifacts (RVP/JVA "30% buyback_yield at 0% share change") for
  `arch_cannibal_at_discount`, `arch_buyback_compounder`, `arch_capital_discipline`.
- **Cluseau realizable-book** gets the three things its docstring flags as
  missing: the marketable-securities line (`balance-sheet` short/long-term
  investments), the multi-year cash *trend* (deployment, not a snapshot), and
  impairment history (`income-statement` repeated writedowns).
- **`priceToTangibleBookRatioTTM` / `netCurrentAssetValueTTM` / `grahamNetNetTTM`**
  globalize the EDGAR-only `p_tb` (~950 rows) and NNWC (`fmp_ncav`,
  `fmp_graham_net_net` already merged as cross-checks).
- **`revenue-geographic-segmentation`** is the only real macro/country-crisis
  signal for `arch_crisis_asset_backed_recovery`.

### Quality / compounder / analyst
- One global multi-period statement pipeline lights up every `*_lindy` /
  `n_yrs_positive_*` leg for non-US names — the dominant reach win, promoting
  ex-US quality names off the single-year ROCE fallback.
- `stockBasedCompensationToRevenueTTM` (`fmp_sbc_to_revenue`) closes the
  "missing-satisfies-<2%" hole in `arch_low_sbc_quality` globally.
- DuPont `taxBurden`/`interestBurden` separate durable operating ROE from
  levered ROE for `arch_large_cap_quality` and `quality_score`.
- `grades-historical` upgrade flow is the literal "awakening" for
  `arch_analyst_awakening` (a change, not a static 11%-covered mean);
  `profile.beta` gives BAB an independent beta vs the distrusted `yf_beta`.

### Forensic / segment / events — an explicit fillability verdict
The forensic theme is where honesty about FMP's limits matters most, because
its edge is in footnote items. Three tiers:

**Fully FMP-servable (globalizes the measure).** `arch_owner_earnings_power`
(dedicated `owner-earnings` endpoint — the single best fit),
`arch_overdepreciated_assets` / `arch_xr_depreciation_cliff` /
`arch_xr_growth_capex_masked` (`capexToDepreciation` is the exact ratio),
`arch_understated_earnings` (`incomeQuality` = CFO/NI), `arch_cash_adjusted_pe`,
`arch_retained_earnings_discount` & `arch_book_compounder_discount`
(`balance-sheet.retainedEarnings` / equity CAGR), `arch_capex_famine_harvest`,
`arch_tax_verified_earnings`, `arch_expensed_growth_value`,
`arch_xr_amortization_mask`, `arch_xr_oneoff_loss_mask`,
`arch_xr_gross_margin_lead`, `arch_xr_forensic_multiple_gap`,
`arch_xr_nol_shield` (negative retained earnings + low ETR — the FMP-native
substitute for the footnote NOL), **`nnwc`** (all Graham inputs are standardized
balance-sheet lines → the US-only net-net floor goes global), and the segment
*count/HHI/geography* measures (`arch_diversified_segments`,
`arch_concentrated_segments`, `arch_geographic_global`). FMP also *sharpens*
`arch_xr_wc_normalization` (explicit `changeInWorkingCapital`),
`arch_xr_cash_tax_advantage` (cash-flow deferred-tax), `arch_customer_float`
(negative cash-conversion-cycle), and `arch_special_situation`
(`mergers-acquisitions-latest` extends deal detection beyond the US form-type
scrape).

**Partial (revenue/pricing legs yes, margin/EBIT or associate legs no).**
`arch_hidden_assets` / `arch_xr_look_through_value` (`longTermInvestments` is a
coarse superset of associates), `arch_xr_owned_realestate_value` (net PP&E yes,
gross-PP&E/accumulated-depreciation unreliable), `arch_xr_discops_mask`
(continuing/discontinued split partial, held-for-sale no),
`arch_xr_float_compounding` / `arch_xr_deferred_revenue_lead`
(`deferredRevenue` is standardized), and the segment SOTP forensics
(`arch_fastest_segment`, `arch_xr_hidden_segment_compounder`,
`arch_xr_margin_mixshift`) — segment *revenue/growth/mix-shift* fillable,
segment *operating margin* not. Spin/post-reorg archetypes: FMP prices them
better but cannot *detect* the Form-10 / reorg event.

**FMP genuinely cannot help (footnote / filing-text moat — stays EDGAR).**
`arch_lifo_hidden_reserve` (LIFO reserve), `arch_pension_overfunded` (funded
status), `arch_dta_reversal` (DTA valuation allowance), `arch_xr_stake_fv_gap`
(disclosed equity-method fair value — the least-substitutable signal),
`arch_xr_contracted_backlog` (RPO), `arch_nol_shell` (NOL carryforward amount),
`arch_xr_segment_justifies_whole` (segment EBIT, no revenue substitute), and
the language legs of `arch_xr_value_unlock` (SEC filing-text NLP). The
aggregate `forensic_xr_score` inherits this: its three highest-signal legs
(LIFO, DTA allowance, EM-FV-gap) are footnote-only, so FMP broadens its
net-cash floor and cheapness multiplier globally but cannot reconstruct the
forensic-asset ledger that gives the score its edge.
