# Archetype × FMP endpoint cross-reference

How Financial Modeling Prep's `/stable` endpoints can enrich or harden every
archetype family in `archetype_tags.py` (~160 `arch_*` screens + ~30 scoring
recipes). Built by cross-referencing the full archetype inventory against the
endpoints verified live on our key (2026-09-19).

**Governing discipline (unchanged):** FMP is a *secondary, source-tagged*
overlay. Every column it produces is `fmp_`-prefixed and merged optionally.
It never overwrites an EDGAR-primary value, and it is never fed into the
forensic / NNWC legs. A fill into a gate-feeding base column happens only
where (a) our primary is NaN and (b) that archetype's own guards still hold —
proven per-archetype against the methodology audit, not assumed.

---

## The leverage insight

The 160 archetypes do not have 160 independent data needs. A small number of
**recurring coverage gaps** each gate dozens of archetypes. Filling one gap
enriches a whole theme. Ranked by breadth × coverage-gain × safety:

| # | Gap (recurring input) | FMP endpoint(s) | Archetypes unblocked | Coverage gain | Risk |
|---|---|---|---|---|---|
| 1 | **Multi-year fundamentals, US-only today** (`roic_lindy`, `roiic_lindy`, `n_yrs_positive_*`, `equity_cagr_5y`, `capex_avg`, `oe_avg`, `ni_avg`, `retained_earnings`, `da_ttm`, `financing_cf_ttm`) | `income-statement`, `balance-sheet-statement`, `cash-flow-statement` (annual, multi-year), `financial-growth`, `owner-earnings` | **~40**: all of Quality/Compounder (§2), most Forensic (§6), the XR quality/reinvestment floor (§7) | Extends US-only lindy/streak metrics to the **~29k non-US names** | Med — must recompute our derived lindy/streak metrics from FMP statements the same way `edgar_roic_roiic.py` does, then DQ-gate |
| 2 | **Analyst estimates & sentiment, ~11%** (`earnings_beat_rate`, `avg_earnings_surprise`, `earnings_beat_streak`, `yf_recommendation_mean`, `analyst_target_upside_pct`, `n_analysts`) | `earnings`, `analyst-estimates`, `price-target-consensus`/`-summary`, `grades-consensus`, `grades-historical` | **~10**: all of Analyst/Sentiment (§9) + the neglect gates in Inflection (`arch_liger_*`, `arch_flyover`) | 11% → broad (US-centric, thinner on micro/OTC) | Low — estimate family is non-forensic; beat/surprise already shipped |
| 3 | **Revenue segments, ~10% of US filers** (`segment_count`, `segment_revenue_hhi`, `largest_segment_share`, `geographic_region_count`, `fastest_segment_yoy`, `fastest_segment_share_delta`) | `revenue-product-segmentation`, `revenue-geographic-segmentation` | **~9**: all of Segment-Mix (§11) + revenue-side of the segment SOTP forensics (§6) | 10% → global, wherever the filer discloses segments | Med — FMP gives segment **revenue only**, not segment EBIT/op-margin (see limits) |
| 4 | **Form-4 insider signals, US-only/sparse** (`insider_cluster_buy_flag`, `insider_officer_buy_flag`, `insider_10pct_buy_flag`, `insider_net_buyer_flag`, `insider_distinct_buyers`, `insider_net_buy_value`) | `insider-trading/search`, `insider-trading/statistics` | **~6**: `arch_insider_conviction`, `arch_xr_insider_capitulation`, `arch_owner_operator`, `governance_score`, `alignment_score` | Consolidates/repairs the existing `sec_insider_signals.csv` (still SEC/US) | Low — same Form-4 data, cleaner parse; alignment $ already shipped |
| 5 | **Liquidity, ~13%** (`avg_dollar_volume`) | `quote`, historical price EOD (price × volume) | `arch_blindspot`, `arch_bab_*`, PEW `forgotten`/liquidity gates | 13% → broad | Low |
| 6 | **52-week / price-range, missing ~half** (`pct_off_52w_high`, `price_pct_of_5y_range`) | `quote`, `historical-price-eod`, `historical-market-capitalization` | All Momentum/Technical (§8) + every `beaten_down_any` value gate | ~50% → broad; a more complete tape than the paused Yahoo feed | Med — must respect the existing raw-vs-adjusted-close discipline |
| 7 | **Quality / distress scores (new capability)** | `scores-bulk` (Piotroski, Altman Z) | Solvency guard usable across Value/Compounder; **shipped** as the Cluseau distress gate | Universe-wide (88–94%) | Low — additive flags |
| 8 | **Institutional sponsorship (out-of-scope today)** | `institutional-ownership/symbol-positions-summary` + `/latest` (13F) | The "I" leg of `arch_oneil_canslim`; a smart-money confirm on compounders | New signal | Low–Med — 13F is quarter-lagged |

---

## What is already shipped this session

- **Insider alignment ratio** (`fmp_insider_alignment_ratio`, `fmp_insider_aligned_flag`): trailing 12m open-market purchase $ ÷ most-recent-year total NEO compensation, from `governance-executive-compensation` + `insider-trading/search`. Fills the Cluseau lens's documented XBRL gap (gap #4 above, exec-comp half).
- **Altman-Z distress gate** (`fmp_distress_flag` from `scores-bulk`): negative gate on `arch_cluseau_realizable_book` and `arch_cluseau_buyback_accel` (dropped the near-insolvent firers a cheap-to-book screen would otherwise call bargains).
- **Piotroski** (`fmp_piotroski`, `fmp_piotroski_strong_flag`) surfaced universe-wide.
- **Earnings beat / surprise / variability** from `earnings`: fills `earnings_beat_rate` and `avg_earnings_surprise` NaNs (gap #2) and adds a surprise-dispersion leg to `earnings_variability_flag`. Per-quarter surprise winsorized to ±100%.
- **TTM returns/margins** (`fmp_roic`, `fmp_ebitda_margin`, `fmp_gross_margin`, `fmp_fcf_yield`, `fmp_ev_ebitda`, `fmp_net_debt_ebitda`, `fmp_pb`, `fmp_dividend_yield`) present universe-wide as `fmp_` columns (not yet coalesced into gate inputs — see risk note below).

---

## Per-theme opportunities

### §1 Value / Deep-Value
- `arch_oak_nav_discount`, `arch_cluseau_realizable_book`: FMP `balance-sheet` marketable-securities and cash-trend (multi-year) let the "realizable book" test read the *trend* of cash, not just the level — the article's squatter-vs-returner distinction. `owner-earnings` sharpens the profitability leg.
- `arch_cundill_deep_value`: `dividends` history confirms the dividend leg globally; `grades-consensus` is not needed.
- **Distress gate (shipped)** applies naturally to `arch_negative_ev_value`, `arch_oak_asset_floor`, `arch_tangible_value` — a net-cash screen on an Altman-distressed shell is the trap these already try to avoid.

### §2 Quality / Compounder — **highest coverage leverage**
- Every `*_lindy` / `n_yrs_positive_*` / `equity_cagr_5y` archetype (`arch_durable_reinvestment`, `arch_buyback_compounder`, `arch_no_dilution`, `arch_owner_operator`, `arch_qarp`, `arch_large_cap_quality`, `arch_flyover`, BAB family, Alta Fox) is **US-only today** because the multi-year metrics come from `edgar_roic_roiic.py`. FMP's multi-year `income-statement`/`balance-sheet`/`cash-flow` (global) let us recompute the same lindy/streak/ROIIC metrics for non-US names → the biggest single expansion available.
- `owner-earnings` endpoint is a direct source for `oe_avg` / owner-earnings power.
- `fmp_piotroski` is a ready-made quality confirm to AND into compounder gates.

### §3 Inflection / Turnaround
- The **neglect** legs (`n_analysts` in `arch_liger_lagging_inflect`, `arch_liger_neglected_survivor`) and momentum legs use analyst + tape gaps (#2, #6). FMP `grades-*` + `price-target-*` fill coverage.
- Debt-maturity-dependent names (`arch_weschler_levered_equity`) stay unscreenable (see limits).

### §4 Capital-Allocation / Buyback
- `insider-trading/*` (#4) directly powers `arch_insider_conviction`. `dividends` + `splits` history confirms capital-return legs (`arch_capital_returner`, `arch_dividend_verified_value`) globally.
- `fmp_insider_aligned_flag` (shipped) is a new conviction tag for this whole family.

### §5 Special-Situations / Event
- `mergers-acquisitions-latest` is a live M&A feed for `arch_special_situation` (today gated on EDGAR event flags, US-only) — extends deal detection beyond US filers.
- NOL / DTA / reorg / fresh-start remain EDGAR-only (footnote items FMP standardization drops — see limits).

### §6 Forensic / Hidden-Asset
- `owner-earnings` → `arch_owner_earnings_power`, `arch_xr_forensic_multiple_gap`.
- Multi-year statements (#1) → `arch_retained_earnings_discount`, `arch_book_compounder_discount`, `arch_overdepreciated_assets`, `arch_capex_famine_harvest` for non-US names.
- **Cannot fill**: `arch_lifo_hidden_reserve`, `arch_pension_overfunded`, `arch_dta_reversal`, `arch_xr_contracted_backlog` (RPO), `arch_nol_shell` — these read XBRL footnote tags FMP's standardized statements do not expose.
- Segment SOTP forensics (`arch_xr_hidden_segment_compounder` etc.): segment **revenue** fillable from FMP (#3); segment **EBIT/margin** is not — so the revenue-mix and share-shift legs enrich, the segment-margin legs do not.

### §7 XR convexity floor
- Multi-year quality legs (`arch_xr_quality_crisis`, `arch_xr_compounding_deployer`) ride on #1. Streak fields (`rev_yoy_streak_q`, `ni_yoy_streak_q`) recomputable from FMP quarterly statements.

### §8 Momentum / Technical
- `historical-price-eod` (adjusted + unadjusted) + `quote` fill `pct_off_52w_high`, `roc_*`, `momentum_12m`, base depth (#6) globally and fresh — a cleaner tape than the rate-limited Yahoo feed. Respect the existing raw-close-for-price / adjusted-close-for-momentum rule.
- `institutional-ownership` (#8) can finally supply the "I" (institutional sponsorship) leg of `arch_oneil_canslim` that is currently out of scope.

### §9 Analyst / Sentiment — **direct fills**
- `arch_asleep_at_wheel` / `arch_asleep_unrerated`: `earnings` (beat/surprise/streak — shipped) + `analyst-estimates`.
- `arch_analyst_awakening` / `arch_analyst_rerating_confirmed`: `price-target-consensus`/`-summary` → `analyst_target_upside_pct`; `grades-consensus`/`grades-historical` → `yf_recommendation_mean` and a genuine upgrade/downgrade flow (better than a static mean).

### §10 Biotech
- `arch_biotech_deep_value`: cash-runway from FMP `cash-flow` burn + `balance-sheet` cash; `key-executives` and `earnings-calendar` add catalyst timing. Pipeline/clinical-phase data is out of FMP's scope.

### §11 Segment-Mix
- Fully addressed by #3 for the revenue/HHI/geography legs; segment-margin legs limited (revenue-only).

### §12 Country / Sizing / Neglect
- `avg_dollar_volume` (#5) repairs the `arch_blindspot` ADV gate for the ~87% of names it is currently missing on.

---

## Net-new signals FMP makes possible (not in the codebase today)

- **Institutional sponsorship / 13F** (`institutional-ownership`): smart-money accumulation, the O'Neil "I".
- **Political-insider trades** (`senate-trades`, `house-trades`): a novel attention/conviction flag.
- **Analyst upgrade/downgrade *flow*** (`grades-historical`): a rerating *event* stream, not just a static consensus.
- **Employee productivity** (`employee-count`): revenue/employee and its trend — an operating-leverage tell.
- **Clean beta** (`profile.beta`): a less noisy input for the betting-against-beta family than `yf_beta`.

## What FMP cannot fill (honest limits)

- **XBRL footnote items**: LIFO reserve, pension funded status, DTA valuation allowance, RPO, deferred-revenue detail, NOL carryforwards, held-for-sale lines — FMP's standardized statements drop these. The forensic archetypes built on them stay EDGAR-only.
- **Segment EBIT / operating margin**: FMP segmentation is revenue-only.
- **Debt-maturity schedule**: no endpoint → the Weschler refinancing-wall check stays manual.
- **Point-in-time discipline**: FMP statements can silently restate. Anything feeding NNWC / forensic hidden-value must keep its EDGAR accession/filing-date provenance; FMP is fill-only there and, for those legs, not at all.
- **Backlog / board-change / sole-source / clinical-phase**: not in FMP; scuttlebutt/SEDAR territory.

## Recommended sequencing

1. **Analyst/sentiment fills** (#2) — safe, direct, and the estimate half is already in. Add `price-target-*` and `grades-*` → finishes §9 and the neglect legs.  *(next, low risk)*
2. **Liquidity + 52w tape** (#5, #6) — repairs ADV and the beaten-down gates universe-wide.
3. **Segment revenue** (#3) — unlocks §11 and the revenue-side segment forensics globally.
4. **Multi-year global fundamentals** (#1) — the big one: recompute lindy/streak/ROIIC from FMP statements to extend §2/§6/§7 to non-US names. Largest effort, largest payoff; needs its own DQ gate and audit pass, exactly like the EDGAR path.
5. **Net-new signals** (13F sponsorship, grade-flow) — additive experiments once the fills are in.

Each step is a `fmp_`-column addition validated against `methodology_audit.py` before any coalesce into a gate input, per the discipline at the top.

---

# Appendix — per-archetype enrichment

Every archetype, with the concrete FMP move. Tag legend:
**[Q]** better data quality for a signal we already use (replace a sparse/noisy/stale source);
**[+]** a genuinely new signal FMP makes available;
**[R]** reach — extend a US-only screen to global names;
**[—]** FMP cannot help (EDGAR footnote / out of scope), stated honestly.

### §1 Value / Deep-Value
- **arch_discounted_vehicle** — [Q] `net_debt_ebitda` drives the net-cash cushion and can be stale; FMP `key-metrics-ttm.netDebtToEBITDATTM` is a fresh cross-check. [+] `fmp_altman_z` solvency gate.
- **arch_dead_option** — [Q] the cash-yield legs (`fcf_yield`, `owner_earnings_yield`) from FMP `owner-earnings` (Buffett owner earnings direct) instead of derived proxies.
- **arch_tangible_value** — [R] `p_tb`/`tangible_equity` is EDGAR-only (~950 rows); FMP `ratios-ttm.tangibleBookValuePerShareTTM` + `key-metrics.tangibleAssetValueTTM` extend tangible book globally. [+] distress gate.
- **arch_cundill_deep_value** — [Q] dividend leg from FMP `dividends` (actual history, global) not a yield snapshot; [+] `fmp_piotroski`/`fmp_altman_z` are the exact "profitable + prudent debt" Cundill checks.
- **arch_negative_ev_value** — [Q] EV/net-cash from FMP `enterprise-values` fresh; [+] Altman gate stops the distressed-shell false positive.
- **arch_oak_deep_value / arch_oak_asset_floor** — [Q] `interest_coverage` (soft, ~7%) from FMP `ratios-ttm.interestCoverageRatioTTM` universe-wide; [+] Altman survivability.
- **arch_oak_nav_discount** — [Q] the "book≈NAV" proxy is weak; FMP `balance-sheet` marketable-securities split + `dividends` cover the dividend-cover leg the code flags as unseeable.
- **arch_crisis_asset_backed_recovery** — [R] `ppe_gross`/`assets` from FMP `balance-sheet` globally; [Q] fresh 52w/5y range from FMP price for the "smashed by crisis" leg.
- **arch_cluseau_realizable_book** — [+] cash *trend* from multi-year FMP `balance-sheet` (squatter vs returner); [+] exec-comp alignment (**shipped**); [+] Altman gate (**shipped**).
- **arch_cluseau_buyback_accel** — [Q] `shares_3y_cagr`/`buyback_yield` from FMP `income-statement` diluted-share history (global, audited) vs our derived; [+] Altman gate (**shipped**).
- **cash_squatter_flag / capex_treadmill_flag** — [Q] `cfo`/`capex` from FMP `cash-flow` global; capex/CFO ratio also in `key-metrics.capexToOperatingCashFlowTTM` directly.
- **earnings_variability_flag** — [+] FMP surprise-dispersion leg (**shipped**); could add EPS-actual coefficient-of-variation from `earnings`.
- **arch_financials_value** — [Q] bank ROE/PB from FMP `ratios-ttm` (financials are excluded from EDGAR ROIC harvest, so FMP is often the only multi-year source).
- **arch_greenblatt_magic** — [Q] EBIT/EV + ROCE from FMP `key-metrics.returnOnCapitalEmployedTTM` + `enterprise-values` directly, replacing the one-off-suspect ROCE proxy. [R] global.
- **arch_templeton_pessimism** — [Q] fresh 5y range + `normalized_ebitda` cross-check via FMP `income-statement` multi-year.
- **arch_lynch_pegy / arch_lynch_evgy** — [Q] growth denominators from FMP `financial-growth` (clean YoY) rather than derived; [+] `analyst-estimates` gives *forward* growth for a true PEG.
- **Graham net-net / PEW deep-value flags** — [Q] NCAV components (`Current Assets`, `Total Liabilities`) from FMP `balance-sheet` global; [Q] `n_analysts`/forgotten from FMP `grades-consensus` count instead of Yahoo `numberOfAnalystOpinions`.

### §2 Quality / Compounder — the [R] theme
- **arch_durable_reinvestment, arch_cash_reinvest, arch_roic_inflect, arch_cheap_per_roiic, arch_reinvest_inflect, arch_double_inflect, arch_cash_quality, arch_capital_light_pivot** — [R] all gate on `roic_lindy`/`roiic_lindy`/`n_yrs_positive_roic`, EDGAR-only. Recompute from FMP multi-year `income-statement`+`balance-sheet`+`cash-flow` → extend every one to ~29k non-US names.
- **arch_lindy_margin, arch_lindy_fcf, arch_no_dilution, arch_lindy_growth** — [R] multi-year margin/FCF/share-count history from FMP statements; `financial-growth` gives the CAGRs directly.
- **arch_quiet_compounder, arch_owner_operator, arch_flyover** — [R] multi-year quality globally; [Q] `insider_ownership_pct` cross-check from FMP; [Q] `n_analysts` neglect leg from FMP `grades-consensus` (arch_flyover's ~11% gap).
- **arch_qarp, arch_reinvest_inflect, arch_midcap_garp, arch_capital_light_pivot** — [Q] ROIIC + acceleration from FMP `key-metrics.returnOnInvestedCapitalTTM` history; [+] `analyst-estimates` forward EBIT for the GARP growth leg.
- **arch_large_cap_quality** — [Q] `capital_return_yield` (~4-5%) from FMP `dividends` + buyback (share-count delta) universe-wide.
- **arch_low_sbc_quality** — [R] `sbc_pct_revenue` (EDGAR ~9%); FMP `ratios-ttm.stockBasedCompensationToRevenueTTM` universe-wide — a big fill.
- **arch_tax_efficient / arch_strong_coverage** — [Q] effective tax + interest coverage from FMP `ratios-ttm` universe-wide (both are soft-gated on sparse EDGAR today).
- **arch_sustainable_scaler, arch_bottleneck** — [Q] margins/gross-margin trend from FMP `ratios-ttm` + `financial-growth`; [—] "sole-source/chokepoint" stays scuttlebutt.
- **BAB family (arch_bab_low_beta/becoming/multibagger)** — [Q] **beta**: replace noisy `yf_beta` with FMP `profile.beta`; [Q] ADV from FMP volume.
- **alta_fox_score** — [Q] every fundamental leg (P/S, EV/EBITDA, margins, ROCE, insider) has a cleaner FMP equivalent; [R] global.
- **quality_score / alignment_score / governance_score** — [Q] insider legs from FMP `insider-trading/*` (cleaner Form-4 parse); [+] `fmp_insider_alignment_ratio` (**shipped**).

### §3 Inflection / Turnaround
- **arch_narrative_lag, arch_fixed_cost_demand_shock, arch_regime_cyclical, arch_kpi_threshold** — [Q] margin-delta + inflection columns from FMP `financial-growth` (quarterly), a cleaner sequential series than the derived `*_qoq`/`*_seq`.
- **arch_micro_activist_inflect** — [+] `mergers-acquisitions` + `grades-historical` for the activist/board-change confirmation the code leaves to a SEDAR scraper (partial).
- **arch_wolf_* / arch_liger_* / arch_cheap_sales_scaler / arch_exceptional_evsg / arch_growth_algo** — [Q] revenue-growth + operating-leverage from FMP `financial-growth`; [Q] the **neglect** legs (`n_analysts`) from FMP `grades-consensus`; [+] `analyst-estimates` forward revenue turns these into forward-looking inflection screens.
- **arch_evsales_derating, arch_tenbagger_path/credible** — [Q] fresh price/tape from FMP for the EV/sales-vs-price divergence; [+] `analyst-estimates` for the forward revenue ramp the 10-bagger arithmetic needs.
- **arch_oak_order_conversion, arch_asymmetric_assembly, arch_levered_inflection, arch_weschler_levered_equity, arch_oak_deleveraging/resource_leverage** — [Q] deleveraging via FMP `cash-flow.financingCashFlow` + `net_debt_ebitda` fresh; [—] debt-maturity wall (Weschler) still unscreenable.

### §4 Capital-Allocation / Buyback
- **arch_capital_discipline, arch_buyback_compounder, arch_net_cash_returner, arch_cannibal_at_discount** — [Q] share-count history + buyback from FMP `income-statement` diluted shares (audited, global) and `cash-flow` repurchases.
- **arch_capital_returner, arch_balance_sheet_return, arch_dividend_verified_value** — [Q] actual `dividends` + `splits` history globally, not a yield snapshot.
- **arch_self_funded_returner** — [R] `financing_cf_ttm` (EDGAR) from FMP `cash-flow` global.
- **arch_insider_conviction** — [Q] Form-4 cluster/officer/10% flags from FMP `insider-trading/search`+`/statistics` (cleaner than `sec_insider_signals.csv`).
- **arch_forensic_payout_confirmed** — [Q] payout legs from FMP `dividends`/buyback.

### §5 Special-Situations / Event
- **arch_special_situation** — [+] `mergers-acquisitions-latest` live deal feed, extends beyond US EDGAR event flags.
- **arch_spinoff_* , arch_post_reorg, arch_nol_shell, arch_dta_reversal, arch_xr_monetization_trifecta** — [—] spin/reorg/NOL/DTA are EDGAR event/footnote items FMP does not carry; keep EDGAR. [Q] the *valuation* legs (EV/EBIT, FCF yield) around them can use FMP.

### §6 Forensic / Hidden-Asset
- **arch_owner_earnings_power, arch_xr_forensic_multiple_gap** — [+] FMP `owner-earnings` endpoint is a direct, audited owner-earnings source (today derived from `da_ttm`/`capex`).
- **arch_understated_earnings, arch_customer_float, arch_xr_float_compounding** — [Q] CFO vs NI and working-capital from FMP `cash-flow`+`balance-sheet`; [R] global.
- **arch_retained_earnings_discount, arch_book_compounder_discount, arch_overdepreciated_assets, arch_capex_famine_harvest, arch_expensed_growth_value, arch_cash_adjusted_pe** — [R] retained earnings / equity CAGR / D&A / capex / gross margin from FMP multi-year statements → global.
- **arch_lifo_hidden_reserve, arch_pension_overfunded, arch_dta_reversal, arch_xr_contracted_backlog (RPO), arch_xr_deferred_revenue_lead, arch_xr_cash_tax_advantage, arch_xr_discops_mask, arch_xr_owned_realestate_value, arch_xr_amortization_mask** — [—] LIFO reserve, pension status, DTA allowance, RPO, deferred-revenue detail, cash-taxes-paid, held-for-sale, gross-PPE/accumulated-depreciation, acquired-intangible amortization are XBRL footnote tags FMP's standardized statements drop. Keep EDGAR.
- **arch_xr_look_through_value, arch_xr_lookthrough_earner, arch_xr_stake_fv_gap, arch_xr_investment_remark** — [—] equity-method carrying/fair-value and remeasurement are EDGAR-cache forensics; FMP has no equivalent.
- **Segment SOTP forensics (arch_xr_hidden_segment_compounder, arch_xr_segment_justifies_whole, arch_xr_margin_mixshift, arch_xr_gross_margin_lead)** — [R] segment **revenue**/HHI/share-shift from FMP `revenue-product-segmentation`+`revenue-geographic-segmentation`; [—] segment **EBIT/margin** legs not fillable (FMP segments are revenue-only).
- **data_quality_flag** — [+] FMP `scores-bulk` balance-sheet components are an independent identity cross-check.

### §7 XR convexity floor
- **arch_xr_quality_crisis, arch_xr_compounding_deployer, arch_xr_baron_compounder, arch_xr_reusable_assembler, arch_xr_audited_streak_unrerated** — [R] multi-year quality + streak (`rev_yoy_streak_q`, `ni_yoy_streak_q`) recomputable from FMP quarterly statements → global.
- **arch_xr_neg_ev_growth, arch_xr_triple_floor, arch_xr_clean_net_net, arch_xr_cannibal_below_cash/tbook** — [Q] net-cash/NCAV/tangible-book from FMP `balance-sheet`; [+] Altman survivability.
- **arch_xr_leverage_detonation, arch_xr_pre_scale_margin, arch_xr_latent_inflection_floor** — [+] `analyst-estimates` forward revenue/EBITDA for the "before it crosses" thesis; [Q] incremental-margin from FMP `financial-growth`.

### §8 Momentum / Technical
- **arch_kullamagie_breakout, arch_weinstein_stage2, arch_oneil_canslim, arch_lynch_reward, 52w-high flags** — [Q] fill `pct_off_52w_high`/`roc_*`/`momentum_12m`/base-depth from FMP `historical-price-eod` (adjusted+unadjusted, global, fresh) — the rate-limited Yahoo tape is the current bottleneck. [+] **arch_oneil_canslim**: `institutional-ownership` finally supplies the "I" (institutional sponsorship) leg marked out-of-scope; [+] `grades-historical` gives the RS/estimate-revision confirm. [—] true intraday ORH/RVOL execution triggers stay out of scope.

### §9 Analyst / Sentiment — the [Q] theme (your "asleep at the wheel" example)
- **arch_asleep_at_wheel / arch_asleep_unrerated** — [Q] `earnings_beat_rate`, `avg_earnings_surprise`, `earnings_beat_streak`, `earnings_surprise_inflecting` today come from a ~11% Yahoo feed. FMP `earnings` (per-quarter actual vs estimate, deep history) gives all four at far higher coverage — beat_rate + surprise **shipped**; add `earnings_beat_streak` and `earnings_surprise_inflecting` from the same series next.
- **arch_analyst_awakening / arch_analyst_rerating_confirmed** — [Q] `analyst_target_upside_pct` from FMP `price-target-consensus`/`-summary`; [Q][+] `yf_recommendation_mean` from FMP `grades-consensus`, and `grades-historical` upgrades a static mean into an actual **upgrade/downgrade flow** — a rerating *event* the current mean cannot see.
- **asymmetry_score upside/downside** — [Q] analyst + liquidity inputs from FMP across the board.

### §10 Biotech
- **arch_biotech_deep_value** — [Q] cash-runway from FMP `cash-flow` burn + `balance-sheet` cash (cleaner than derived `fcf_ttm_usd`); [+] `earnings-calendar` for catalyst timing. [—] clinical-phase/pipeline not in FMP.

### §11 Segment-Mix
- **arch_diversified_segments, arch_concentrated_segments, arch_geographic_global, arch_fastest_segment, seg_inflect_score** — [R] `revenue-product-segmentation` + `revenue-geographic-segmentation` give segment count, HHI, largest-share, geography count and fastest-segment growth globally (today ~10% of US filers). [—] segment operating margin / `seg_oplev` / `seg_margin_inflect_flag` not fillable (revenue-only).

### §12 Country / Sizing / Neglect
- **arch_blindspot** — [Q] `avg_dollar_volume` from FMP volume (repairs the ~87% ADV gap).
- **pre_rerating_score** — [+] `fmp_piotroski` is a near-exact substitute for the Piotroski-style quality leg it approximates.
- **NMS candidate meta-screen** — inherits every fill above through `archetype_count`.

## Net-new signals worth prototyping (not in any archetype today)
- **Institutional sponsorship** (`institutional-ownership`): the O'Neil "I"; a smart-money accumulation confirm for compounders.
- **Analyst upgrade/downgrade flow** (`grades-historical`): a rerating-event stream feeding a new `arch_rerating_wave`.
- **Political-insider trades** (`senate-trades`/`house-trades`): a novel attention flag.
- **Employee productivity** (`employee-count`): revenue/employee trend, an operating-leverage tell for the inflection theme.

---

# Nuanced (second-order) enrichments

These are not coverage fills. Each is a specific FMP field that repairs a
*known analytical weakness* in an archetype — a place where the screen today
leans on a proxy that misfires. Field names are verified live on our key.

1. **Earnings quality as an accrual veto — `key-metrics.incomeQualityTTM` (CFO ÷ NI), universe-wide.**
   Weakness: every screen that trusts net income or P/E (`arch_asleep_at_wheel`, `arch_cash_adjusted_pe`, `arch_tax_verified_earnings`, the P/E legs of the XR value floor) can be flattered by accruals. `arch_understated_earnings` already wants exactly CFO≫NI but reads a sparse EDGAR-derived `cash_conversion`. FMP gives it universe-wide, and its inverse is a **negative gate**: a cheap "earning" name with incomeQuality < ~0.7 is an accrual trap, not a bargain — screen it out of the value archetypes.

2. **Cash-conversion cycle for the float archetypes — `key-metrics.cashConversionCycleTTM` + the day-metrics.**
   Weakness: `arch_customer_float` infers "customers fund the business" from the *sign* of net working capital; `arch_xr_wc_normalization` and `arch_xr_float_compounding` infer a WC glut/float from coarse proxies. A negative CCC (Salesforce prints −204 days) measures customer float directly, with magnitude and trend. A **rising** DSO/DIO (`daysOfSalesOutstandingTTM`, `daysOfInventoryOutstandingTTM`) is the early forensic tell that receivables/inventory are swelling and about to crush FCF — the exact `arch_xr_wc_normalization` thesis, made a leading rather than trailing signal.

3. **R&D intensity distinguishes expensed growth from SG&A waste — `key-metrics.researchAndDevelopementToRevenueTTM`.**
   Weakness: `arch_expensed_growth_value` (F3) reads a fat-gross-margin / thin-operating-margin gap and *assumes* the gap is expensed growth investment. But the same gap can be plain SG&A bloat — a value trap, not hidden value. R&D/revenue tells them apart: a 15%+ R&D load with thin operating margin is real expensed growth; a thin-margin name with ~0 R&D is just inefficient. This turns a heuristic into an evidenced screen.

4. **Capex ÷ depreciation replaces the D&A proxy for the whole depreciation family — `key-metrics.capexToDepreciationTTM`.**
   `arch_overdepreciated_assets`, `arch_capex_famine_harvest`, `arch_xr_depreciation_cliff`, `arch_xr_growth_capex_masked` all reconstruct capex-vs-D&A from EDGAR `da_ttm`/`capex_ttm`. FMP gives the ratio directly, universe-wide. The nuance it adds: ratio < 1 with **stable revenue** = a genuine harvester (good); ratio < 1 with **falling revenue** = a melting under-investor (bad) — the same number, opposite meaning, and the pairing is what the archetypes actually want.

5. **DuPont burdens separate durable returns from levered ones — `key-metrics.taxBurdenTTM`, `interestBurdenTTM`.**
   Weakness: the compounder screens (`arch_large_cap_quality`, `arch_durable_reinvestment`, `arch_midcap_garp`) gate on ROE/ROCE without seeing *where* the return comes from. A high ROE built on a low interest burden (heavy leverage) is fragile; one built on operating margin and asset turnover is durable. Gating on the operating components, not headline ROE, is a real quality upgrade — and flags the levered-ROE names that are one downturn from trouble.

6. **Estimate dispersion + forward curve for the analyst family — `analyst-estimates` (Avg/High/Low, forward years).**
   Weakness: `arch_analyst_awakening` uses a static recommendation mean and target upside. FMP carries the full estimate *distribution* and *forward* years. Dispersion `(epsHigh − epsLow)/epsAvg` measures analyst disagreement: low dispersion + rising estimates = high-conviction awakening; wide dispersion = false signal. More powerfully, forward estimates make the "before it crosses" inflection archetypes (`arch_xr_leverage_detonation`, `arch_wolf_turnaround`, `arch_tenbagger_path`) *forward-looking* — the consensus forward EBIT/EPS crossing zero is the confirmation those screens currently lack, and for `arch_asleep_at_wheel` it shows whether the market *still* underestimates the trajectory.

7. **Institutional accumulation as a contrarian confirm/veto — `institutional-ownership` (`investorsHoldingChange`, `newPositions`, `ownershipPercentChange`, `putCallRatio`).**
   Weakness: every deep-value / forced-seller / neglected-survivor screen (`arch_dead_option`, `arch_xr_forced_seller`, `arch_liger_neglected_survivor`) fires on a falling tape and cannot tell a value trap everyone is fleeing from a contrarian setup smart money is entering. QoQ 13F deltas answer it: rising `investorsHolding` + `newPositions` = accumulation into the dip (confirm); rising `closedPositions` = distribution (veto). This is also the literal "I" (institutional sponsorship) leg that `arch_oneil_canslim` marks out of scope, and `putCallRatio` adds an options-hedging sentiment read.

8. **True economic geography re-tiers the sizing logic — `revenue-geographic-segmentation`.**
   Weakness: `cluseau_sizing_tier` labels emerging-market tail-risk from `src`, the *listing* domicile. A US-listed company with 90% of revenue in China is an EM-risk name that the domicile test misses entirely. FMP's revenue-by-geography gives true economic exposure, so the starter-position sizing (and `arch_crisis_asset_backed_recovery`'s crisis-geography leg) keys on where the earnings actually come from.

9. **Dividend history exposes the yield trap — `dividends` + `ratios.dividendPayoutRatioTTM`.**
   Weakness: `arch_dividend_verified_value` and `arch_oak_nav_discount` check current yield and FCF cover but not the *path*. A high yield sitting on a recent dividend **cut** is a yield trap; a steadily rising payout is the opposite. Dividend history + payout-ratio sustainability turns a point-in-time yield into a verified track record.

10. **Reverse-split distress flag for the microcap screens — `splits`.**
    Weakness: the microcap archetypes (`arch_micro_activist_inflect`, `arch_blindspot`, `arch_liger_*`) fire in exactly the universe where a recent **reverse** split signals delisting-avoidance distress. A split-ratio < 1 in the last year is a cheap, high-precision negative screen these currently lack.

11. **SBC pollution hardens the owner-earnings screens — `key-metrics.stockBasedCompensationToRevenueTTM`, universe-wide.**
    Weakness: `arch_owner_earnings_power`, `arch_cash_quality`, `arch_understated_earnings` can be flattered when FCF is propped by a large stock-comp add-back. Today `sbc_pct_revenue` is EDGAR-only (~9%). FMP gives SBC/revenue universe-wide, letting `sbc_polluted_flag` apply globally and de-rate the owner-earnings archetypes where the "cash" is really dilution.

12. **Independent Graham/NCAV cross-check — `key-metrics.grahamNetNetTTM`, `netCurrentAssetValueTTM`.**
    Weakness: the net-net screens and `arch_xr_clean_net_net` compute NCAV from our own balance-sheet fields; a units or sign error silently mis-fires (the audit already fights pence-vs-pounds). FMP's own net-net figure is an independent second opinion — disagreement beyond a tolerance becomes a `data_quality_flag` trigger rather than a bad recommendation.

13. **Debt-service coverage is the real survivability gate for levered turnarounds — `ratios.debtServiceCoverageRatioTTM`, `interestCoverageRatioTTM`.**
    Weakness: `arch_weschler_levered_equity`, `arch_asymmetric_assembly`, `arch_xr_paydown_yield` bet on deleveraging transferring EV to equity, gated on sparse EDGAR `interest_coverage`. Debt-service coverage (principal + interest vs cash flow) universe-wide is the sharper line: below ~1 the "deleveraging" story is actually a solvency countdown.

14. **FMP fair value as a cheapness sanity line — `ratios.priceToFairValueTTM`.**
    Not a gate (it is model-dependent), but where our deep-value flags fire yet FMP's own Graham/DCF fair value says price ≥ fair value, that disagreement is worth surfacing on the value books as a "look twice" column — a cheap, independent contra-indicator.

Every item above lands as an `fmp_` column first, is validated against
`methodology_audit.py`, and only then — if it is meant to move a gate — is
coalesced, with that archetype's own guards intact.
