# Archetype engine upgrade audit: new data vs every `arch_*`

Date: 2026-09-26. Scope: `archetype_tags.py` (7,489 lines, 167 `arch_*` flags), outputs in `archetype_tags.csv` (46,526 rows),
master `asymmetry_global.csv`, overlays `base_snapshot.csv`, `fmp_sentiment.csv`, `fmp_quarterly.csv` / `fmp_quarterly_panel.parquet`,
`fmp_statements.csv`, `fmp_segments.csv`, `fmp_dynamics.csv`, `fmp_institutional.csv`, `fmp_enrichment.csv`, and the weekly panel
`fmp_price_parts/*.parquet`. No repo files were edited. The only compute was local and read-only: pandas checks, plus one
panel pass that derived `ts_*` measures for 27,513 live symbols. Scripts: `scratchpad/ts.py`, `p*.py`; derived measures in `scratchpad/ts_measures.parquet`.

**Denominator used throughout.** "Investable operating" (INV) means non-financial, non-REIT, non-utility, `market_cap_usd >= $10M`,
common stock only. That is 24,386 names, so 5% is about 1,220 and 10% is about 2,440. "Broad" in section B means more than 2,500
firers. The 1,500–2,500 band is treated as a watch band.

**Caveat.** Several overlays are partial runs: sentiment, dynamics, institutional, base_snapshot, and FMP earnings. Counts are
indicative. Every measured effect below is "current firers retained after the tightening", computed on the current CSVs.

---

## 0. Top findings and recommendations (ranked)

1. **Currency bug in the Coiled Base / Base Ignition validity gate (P0).** `bs_med_dvol26` and `bs_size_dvol` are in the
   listing currency. For `.L` they are in pence, because FMP quotes GBp. The gate `_cb_valid = bs_med_dvol26 >= 250_000`
   (line 6014) therefore means $1.6k/week for a JPY name and $160/week for a KRW name.
   - **Measured:** 190 of 651 `arch_coiled_base` firers and 37 of 116 `arch_base_ignition` firers fail the intended
     $250k/week in USD. 207 of the 651 firers are `.T`.
   - **Same bug upstream:** the event study's `MIN_WEEKLY_DVOL` (`event_study_base.py`) has it too, so the dry-run
     calibration of the ignition thresholds is contaminated.
   - **Fix:** in `base_snapshot.build()` and `event_study_base`, emit `bs_med_dvol26_usd = med_dvol26 * usd_per_unit(ccy) / quote_unit`.
     `quote_unit` is 100 for GBp, ZAc and ILA. Gate on the USD column. The `_small` size tilt must use the same USD value.
2. **`base_snapshot.csv` is stale and partial.** It has 14,815 names, because it was run at 14:05 while `fmp_prices.py`
   was still writing parts. The panel now holds about 27.9k live symbols.
   - A re-run (zero API calls) lifts `bs_*` coverage of INV from 58% to about 82%. It doubles the reach of Coiled Base,
     Base Ignition, the narrative-lag / Liger / institutional base legs, and the 2-year coil lens in asleep_unrerated,
     evsales_derating and xr_audited_streak.
   - Also emit the `ts_*` measures in section A.0 from the same pass.
3. **Snapshot momentum proxies are materially noisy against the panel.** Measured on INV names with both sources:
   - `price_yoy` vs panel 52-week total return: Spearman 0.69, and 55% differ by more than 15pp.
   - `momentum_12m`: 29% differ by more than 15pp.
   - `roc_12m`: 27% differ by more than 15pp.
   - `pct_off_52w_high` is fine: Spearman 0.90, and only 6% differ by more than 15pp.

   Every gate reading `price_yoy` / `momentum_12m` should read `ts_r52` first. That covers `flat_or_down`, `_lag_tape`,
   `beaten_down_any`, the momentum block, `xr_forced_seller`, `asleep_unrerated`, `evsales_derating`, `quiet_compounder`,
   `wolf_seal`, and `institutional_accumulation`.
4. **Rebuild the momentum/technical family on the weekly panel.** These setups were proxied with `momentum_12m`,
   `rel_pct_52w_high` and `price_pct_of_5y_range`.
   - **Weinstein Stage 2:** 4,307 firers, 17.7% of INV. The permissive leg is `rel_pct_52w_high >= 0.80`, which 38% of INV
     pass. A true Stage 2A core (price above a 30-week moving average that has just turned up, Mansfield RS crossing zero or
     2x volume) fires on 640 names. Only 216 of the current 4,307 qualify.
   - **O'Neil:** a genuine quarterly C (from `fmp_quarterly_panel.parquet`) plus panel N and L gives 374 INV names. Only
     101 overlap the current 334, so both precision and reach change.
   - **Kullamägi:** only 242 of 1,158 firers meet all panel legs (leader, impulse, tight, above the 10-week MA, near high).
     The leader percentile is global, which over-represents the RG / BK / BO / NS markets by 2 to 7 times. 18% of firers
     trade under $1M/week.
5. **Lynch PEGY/EVGY is broad because of its growth denominator, not its multiple.** `pegy` uses `yf_earnings_growth`, a
   single-quarter Yahoo figure (`derive_missing_columns.py:528`).
   - 59% of the 7,952 PEGY firers show at least 50% growth, and 38% hit the 100% cap. 75% of firers even clear Lynch's
     "very attractive" PEGY of 0.5.
   - Recomputed on TTM net-income growth from `fq_ni` / `fq_ni_p`, restricted to the 8–50% growth band, and requiring EPS
     durability, it fires on 1,836 names. 1,278 of those are current firers and 558 are new.
6. **Perception family: Analyst Awakening fires on levels, not change.** 2,046 of its 2,102 firers qualify through the
   level route (rating at or below 2.2, which 94% of firers meet). Requiring at least one change lens keeps 204 firers.
   Adding a price-turn escape (Mansfield RS rising and a positive 13-week return) keeps 933, which is the realistic core
   until `fmp_sentiment` completes.
7. **FMP `earnings` was fetched for only 210 names.** `fmp_earnings_beat_rate` covers 0.45% of rows, and the native
   `earnings_beat_rate` spans 4 quarters with 40% of names at or above 0.75, which is a base rate. One call per name
   (about 30k) unlocks:
   - 8–12-quarter beat history
   - revenue surprise
   - dated reports, which with the weekly panel give earnings-week reactions, post-earnings drift, and Kullamägi-style
     episodic pivots
   - a real O'Neil "C" check and Wolf "Seal" post-earnings dip
   - a Base Ignition trigger

   Asleep-at-wheel measured: 4/4 beats with more than 2% surprise and a streak of at least 3 keeps 1,445 of 3,168.
   Adding "price not rewarded" keeps 486.
8. **Several lindy/quality archetypes are broad because FMP statement fills made "4 of 5 years positive" global.** This
   is the base rate for any profitable company.
   - `lindy_fcf` has 9,356 firers. Requiring 5/5 years keeps 5,422, and 5/5 plus `roic_lindy >= 8%` keeps 3,083.
   - `no_dilution` has 7,144 firers. Enforcing its own docstring ("reinvesting at high returns", `roic_lindy >= 10%`)
     keeps 2,563.
   - `lindy_margin` has 6,752 firers. A 15% operating-margin floor plus "still at least 0.6x of the lindy margin now"
     keeps 2,774.
   - The FMP engine already holds 8 fiscal years in its cache (`limit: 8`). Emitting 7-of-8 and through-cycle minimum
     margin / coverage costs zero API calls.
9. **Price-lindy is a real new confirming leg for the compounder family.** It uses 5-year max drawdown and 3-year downside
   capture versus the name's own market.
   - Only 17% of INV names had a 5-year drawdown shallower than 40%.
   - Among quality firers, 55–76% are more resilient than their market median.
   - Use it as a core/watch split or a score term, never as a veto.
10. **Event-driven family reach is EDGAR-only.** Spin-off flags fire on 58 names universe-wide and merger flags on 300.
    Cheap FMP additions:
    - `historical-sp500-constituent`: one call, dated additions and deletions for forced-seller and inclusion catalysts.
    - `mergers-acquisitions-latest`: paged, global deal targets.
    - `sec-filings-search/symbol`: Form 10-12B/G, SC 13D, SC TO-T, DEFM14A, 8-K 5.02.

---

## A. Per-archetype upgrade table

### A.0 New measures to emit from the weekly panel

These come from one pass over `fmp_price_parts`, added to `base_snapshot.py` or a sibling `ts_snapshot.py`. Everything is
total-return (dividend-adjusted) and point-in-time at the last complete W-FRI bar. Prototype values are in
`scratchpad/ts_measures.parquet`, covering 27,513 live symbols and 20,125 INV names (versus 14,213 INV names in the
current `bs_*`).

| column | definition | feeds |
|---|---|---|
| `ts_r4/13/26/39/52/104/156/260` | close / close[t-k] − 1 | every tape gate; `ts_r52` replaces `price_yoy`/`momentum_12m` |
| `ts_ma10/30/40`, `ts_ma30_slope4/13`, `ts_above_ma30` | weekly SMAs and slope of the 30-week MA (Weinstein's 30-week MA) | Weinstein, O'Neil, Kullamägi |
| `ts_dist_hi52`, `ts_dist_lo52`, `ts_dist_hi260`, `ts_wks_since_hi52` | close / rolling-max(high); 5-year high = Cundill "former high" | beaten_down_any, 52w-high system, crisis/trough gates |
| `ts_mrs`, `ts_mrs_13ago`, `ts_rs_at_hi` | Mansfield RS: log(stock / local index) − its 52-week mean; RS line at its 52-week high | Weinstein RS, O'Neil L, rerating_confirmed rel-high |
| `ts_rs_pct_mkt`, `ts_rs_pct_glob` | IBD-style RS = 0.4·r13 + 0.2·r26 + 0.2·r39 + 0.2·r52, percentile within market / global | O'Neil L, Kullamägi leader |
| `ts_vol_spike`, `ts_vol_spike4` | last-week / max-of-4-week volume ÷ 52-week median volume | breakout volume, Stage 2A, ignition, EP |
| `ts_tight5` | (max − min of last 5 weekly closes) / close | Kullamägi / VCP tightness |
| `ts_maxdd_5y/10y`, `ts_uw_share_5y/10y` | worst peak-to-trough; share of weeks more than 20% under water | price-lindy for quality/compounders |
| `ts_beta_1y/2y/3y`, `ts_dbeta_*`, `ts_down_capture_*`, `ts_vol_1y/3y` | weekly beta / downside beta / downside capture vs local index | BAB family (beta **trend** now measurable), resilience |
| `ts_dvol26_usd` | median weekly $-volume in USD (quote-unit aware) | every tradeability validity guard (replaces the pew ADV, which is 0% present on blindspot firers) |
| `ts_ereact_*` (needs FMP `earnings` dates) | earnings-week return vs the prior week close, and 4-week drift after | asleep, Wolf Seal, EP, ignition, O'Neil C |

Index note: the prototype used an equal-weight median-return pseudo-index per market suffix, which skews betas above 1
(median 1.15). Replace it with FMP index series via `historical-price-eod` (^GSPC, ^N225, ^FTSE, ^HSI, ^NSEI, ^KS11,
^GSPTSE, ^AXJO, ^GDAXI, ^FCHI, ^TWII, ^JKSE, ^SET.BK, and so on; about 25 calls). Keep rank-within-market for beta
gates anyway. Panel beta vs Yahoo beta has a Spearman of only 0.46.

### A.1 Momentum / technical family (highest priority)

| archetype (line) | spirit | current inputs | upgrade (type) | concrete change |
|---|---|---|---|---|
| `arch_weinstein_stage2` (2463) | early Stage 2: price clears the base above a rising 30-week MA with strengthening RS and little overhead | `momentum_12m>0`, `price_pct_of_5y_range>=0.55`, `rel_pct_52w_high>=0.8`, `pct_off_52w_high>=-0.10` | **b** direct 30-week MA and Mansfield RS; **c** breakout volume | Replace `_st2_trend/_st2_rs` (2459–2461) with `ts_close>ts_ma30 & ts_ma30_slope4>0 & ts_mrs>0`. **Core = Stage 2A:** `& ts_ma30_slope13<0.03` (the MA just turned) `& (ts_mrs_13ago<=0 | ts_vol_spike4>=2)`. That is 640 INV names; 216 of the current 4,307 qualify. Emit a `weinstein_stage` label (1–4) as a surfaced column. |
| `arch_oneil_canslim` (2492) | CAN SLIM leader: accelerating current EPS, durable annual growth and ROE, new high, RS leader, sponsorship, market up | `eps_yoy_growth_streak_q`/`rev_yoy` for C, `roce` for A, `pct_off_52w_high`, RS via `_pctrank(roc_6m, momentum_12m)` | **b** true quarterly C from `fmp_quarterly_panel` (EPS = ni/shares_dil, latest-quarter YoY ≥25% and accelerating); **b** L = `ts_rs_pct_glob>=80`; **c** M = local-index above its 30-week MA; **c** I = `fmp_inst_own_chg_q0>0`; **c** S = `shares-float` | Measured: panel C+A+N+L gives 374 INV names, of which 101 overlap the current 334. Only 51% of current firers have a true quarterly C. |
| `arch_kullamagie_breakout` (2444) | liquid momentum leader after a 30%+ impulse, tight orderly base near highs | `_pctrank` global of `roc_6m`/`momentum_12m`, `sr_m_squeeze_run` (monthly), `base_depth_12m`, `pct_off_52w_high` | **b** leader = `ts_r13` or `ts_r26` top 2–5% **within market** (a global rank over-weights RG/BK/BO by 2–7x); **b** tightness = `ts_tight5<=0.10` & close > 10-week MA > 30-week MA (weekly VCP, replacing the monthly squeeze); **validity** `ts_dvol26_usd>=$1M` | All panel legs: 242 of 1,158 current firers. |
| `arch_analyst_rerating_confirmed` (5831) | analysts bullish and the price already confirms with a fresh high | `is_52w_high`/`rel_is_52w_high` (lynch tape) | **b** abs-high = `ts_dist_hi52>=0.97`; rel-high = `ts_rs_at_hi` | 345 of 390 firers pass only through the rel-high leg. Median abs distance is 0.93. Require **abs OR (rel AND ts_above_ma30)**, so a relative high in a falling tape is not a "confirmation". |
| `high_52w_*` flags (5737) | the 52-week-high system | lynch tape | **b** panel equivalents, fresh every week | `ts_dist_hi52>=0.97`, `ts_rs_at_hi`; add `ts_multi_year_high` = close at its 5-year high after a 2-year base (breakout from a long base). |
| `arch_lynch_reward` (5667) | years of fundamental progress not yet paid; coil tipping up | monthly/quarterly asym + squeeze (lynch tape); `roc_12m`, `roc_3_5y` | **b** `lr_unpaid` on `ts_r52` (total return); **c** the weekly asym/squeeze layer the code says "is deferred" (5569) can now be computed from the panel | Put `ts_r156/ts_r260` beside `roc_3_5y` in `lr_roc_setup`, and add a weekly coil lens (`bs_vol_ratio<=0.7 & bs_range_ratio<=0.4`). |
| `arch_wolf_seal` (2662) | earnings inflection bought on a post-earnings DIP | `inflection_print` (very broad), `mom12>=0.10` | **b** the dip, measured: earnings-week reaction ≤ −5% or 13-week return ≤ −5% with 52-week ≥ +10%; **b** shock-sized inflection | Proxy measured: 256 of 2,244 firers. With FMP `earnings` dates: `ts_ereact_last<=-0.05 & beat`. |

### A.2 Growth-not-rewarded / re-rating / perception family

| archetype (line) | spirit | current inputs | upgrade | concrete change |
|---|---|---|---|---|
| `arch_narrative_lag` (1152) | fundamentals advancing while the price lags | `_lag_tape`: `price_yoy<0 \| momentum_12m<0` (half the universe) OR base+coil; `_adv_breadth>=2`; loose cheapness | **b** the lag measured against the **advance**: 1-year coil = log(fq_revenue/fq_revenue_p) − log(1+ts_r52) ≥ log 1.2, OR 2-year `bs_coil_rev>=log1.2` / `bs_coil_ebit>=log1.3` | Replace the `_lag_tape` leg (1145). Coil OR form keeps 4,038 of 6,524; 1-year coil alone keeps 3,234. Only 18% of firers have `ts_r52>=0` (the tape leg is mostly real, but it is not measured against the advance). |
| `arch_asleep_at_wheel` (5171) | the street chronically under-estimates the business | 4-quarter `earnings_beat_rate>=0.75` plus 2 legs; EPS-streak branch; forward gap | **a/b** FMP `earnings` (8–12 quarters, revenue surprise) universe-wide; **c** reaction lens: beats with flat or negative earnings-week reaction | 3,107 of 3,168 fire through the 4-quarter beats branch, and 40% of covered names have `beat_rate>=0.75`. **Core:** 4/4 or ≥7/8 beats, surprise >2%, streak ≥3 (1,445). **Plus "not rewarded":** `ts_r52 <= market median` (486). |
| `arch_asleep_unrerated` (5234) | beats and still no re-rating | `ev_sales_change_yoy`, `price_yoy` vs fundamental growth, `fmp_dyn_unrerated_gap`, `bs_coil_*` | **b** `_pyw_au` → `ts_r52`; **a** re-run base_snapshot (coil lens reach) | Panel no-rerate (coil > 0) keeps 952 of 1,466. |
| `arch_xr_audited_streak_unrerated` (5267) | 8+ audited growth quarters, not re-rated | streaks, `_no_rerate_au` | same **b** | Panel no-rerate keeps 1,696 of 2,126. It is broad because `_no_rerate_au` ORs six lenses, including `_esc_au<=0.10`, which is true for any flat multiple. Require at least 2 of the lenses. |
| `arch_evsales_derating` (5535) | EV/Sales compressing while sales rip | `rev_yoy − price_yoy` (fallback momentum, roc), `roc_3_5y`, `bs_coil_rev` | **b** `_stk_ret` (5518) → `ts_r52`; 3-year leg → `ts_r156`; **c** TTM sales growth (fq) ≥15% so the derate is not one YoY print | 1,413 of 1,735 kept with panel returns; 852 with fq TTM growth too. |
| `arch_analyst_awakening` (5791) | perception **changing** toward bullish while price has only begun | `yf_recommendation_mean`, target upside, `n_analysts` (levels); `sent_*` momentum as a second route | **c** require ≥1 change lens (`sent_buy_share_d12>=0.10`, net upgrades ≥2, `sent_pt_rev_q>=0.05`, initiation), OR a price turn (`ts_mrs>ts_mrs_13ago & ts_r13>0`); **a** `price-target-news` for global target-revision momentum | 2,046 of 2,102 fire on levels only. Change-required keeps 204; change-or-turn keeps 933. |
| `arch_institutional_accumulation` (5895) | 13F adding while the tape is flat or down | 3 quarters of `symbol-positions-summary`; `roc_12m`/`momentum_12m` | **b** `_ip12` → `ts_r52`, `_ip6` → `ts_r26`; **a/c** extend to 8 quarters (5 more calls per US name) for a real persistence and acceleration base, and demean against the 8-quarter history rather than one cross-section | Coverage is 5.8k holders. |
| `arch_coiled_base` / `arch_base_ignition` (6016/6020) | flat 2 years, value accreting, nobody watching, first buyers arriving | `bs_*`, fq coil, sent, `yf_institution_pct`, 13F, insider | **P0 fix** USD dvol (section 0.1); **a** re-run snapshot; **b** perception: neglect **observed** via `numAnalystsEps` from the cached `analyst-estimates` payload (74% of firers pass `sent_neglected_flag`, but only 46% have any observed coverage field); **c** ignition leg = earnings-week reaction ≥ +8% on ≥2x volume (EP) | Ignition legs measured: `bs_updown_vol>=1.8` is met by 84% of ignition firers and `bs_dvol_trend>=1.6` by 51%. The volume legs carry it, as designed. |
| `arch_tenbagger_path` / `_credible` (5443/5487) | the 10x arithmetic closes on demonstrated growth | rev_yoy, 3y/5y CAGR, rev_qoq_ttm, P/S | **b** add fq TTM growth (`fq_revenue/fq_revenue_p`) as a lens in `_g_lenses` (5409) | The arithmetic almost always closes (median implied 33x), so breadth sits in the growth confirmation. Dropping the `rev_growth_score>=0.5` escape keeps 1,526 of 2,034. |
| `arch_cheap_sales_scaler` (5022) / `arch_exceptional_evsg` (5046) | cheap on sales relative to growth, operating leverage arriving | `psg`/`evsg` (1-year rev_yoy), `oper_lev_any` | **b** `oper_lev_any` → shock-sized margin move OR `fmp_dyn_incremental_ebit_margin>=0.15`; growth on fq TTM | cheap_sales_scaler: 1,612 of 2,529 with a shock-sized move; 472 with incremental margin as well. |
| `arch_growth_algo` (5108) | GP growth + operating leverage + shrinking count compounding FCF/share | rev_yoy, oper_lev_any, fcf_yoy | **b** FCF/share from the quarterly panel (`fcf`, `shares_dil`) TTM vs year-ago; **c** `fq_shares_yoy<=-0.02` as the DLO "−5%" leg | 527 firers; not broad. |
| `arch_liger_lagging_inflect` (2715) | a neglected microcap whose inflection the market has not processed | rev legs, `oper_lev_any`, `flat_or_down \| beaten \| bs_is_base` | **b** lag measured (1-year coil ≥ log 1.15 or 2-year coil ≥ log 1.2); **b** neglect observed (numAnalysts) | Lag measured keeps 1,418 of 2,706; shock/accel keeps 1,796. |
| `arch_liger_neglected_survivor` (2735) | neglected, survivable, cheap, early inflection | `n_analysts<=3` (missing counts as neglected), `oper_lev_any` | **b** neglect observed (only 16% of firers have any coverage field); **b** early inflection = shock-sized or first-positive | Shock/first-positive keeps 2,581 of 3,849. |
| `arch_liger_asset_backed` (2700) | neglected net-cash asset play | `n_analysts<=4` (missing permissive) | **b** observed coverage | Watch band (2,211). |

### A.3 Quality / compounder family (multi-year lindy)

| archetype (line) | spirit | current inputs | upgrade | concrete change |
|---|---|---|---|---|
| `arch_lindy_fcf` (1446) | cash-generation durability | FMP/EDGAR `n_yrs_positive_fcf/opinc` (of 5), years ≥5 | **c** 7-of-8-year window (cached FMP annuals, `limit 8`); **c** price-lindy (`ts_maxdd_5y` shallower than own-market median) as score or core | 5/5 plus 5/5 keeps 5,422 of 9,356; plus roic_lindy ≥8% keeps 3,083; price-lindy keeps 5,605. |
| `arch_lindy_margin` (1435) | durable high margin | `op_margin_lindy>=0.10` (only 28% of INV clear it, but that is still broad), years ≥5 | **c** 15% floor (the docstring says "high"); **b** through-cycle **minimum** operating margin from the 8 cached FYs; current op margin ≥0.6× the lindy margin | Both keep 2,774 of 6,752. |
| `arch_no_dilution` (1465) | reinvesting at **high** returns without tapping equity | shares 3-year ≤+2%, 4/5 FCF, 4/5 ROIC | **c** `roic_lindy>=0.10` (docstring); **b** 5-year share window; **b** date-matched `fq_shares_yoy` | ROIC ≥10% keeps 2,563 of 7,144; with 5-year shares ≤+2%, 2,235. |
| `arch_lindy_growth` (1685) | durable accelerating growth | 5y CAGR, accel, asset growth | **c** fq TTM growth still ≥ half the 5-year CAGR (not decelerating); **c** price-lindy score | 1,486. Price-lindy keeps 858. |
| `arch_durable_reinvestment` / `arch_cash_reinvest` (1360/1371) | high lindy ROIIC reinvested | FMP-filled ROIIC | **c** price-lindy (1,151 of 1,805); ROIIC sanity against the quarterly TTM EBIT path | |
| `arch_cheap_per_roiic` (1393) | cheap per unit of reinvestment return | EV/EBITDA ÷ (ROIIC×100); 92% FMP-filled ROIIC | **c** cash ROIIC corroborates (≥0.08) and real reinvestment (asset 3-year CAGR ≥5%). Rolling FMP ROIIC on small deltas is noisy. | Keeps 1,530 of 4,147 (2,402 with cash corroboration alone). |
| `arch_qarp` (1787) | high ROIIC at a reasonable price | roiic ≥0.15, multiples | **c** price-lindy score (1,450 of 2,221); growth on fq TTM | |
| `arch_quiet_compounder` (1728) | proven ROIC, **not noticed yet** | insider ≥0.10, momentum band [−10%, +50%] | **b** "quiet" = not re-rated on the panel (`bs_coil_rev>=0` or 1-year coil ≥0) and low attention (observed ≤5 analysts) | Not re-rated keeps 1,157 of 2,172; low attention keeps 1,741. |
| `arch_owner_operator` (1774) / `arch_flyover` (6483) | skin in the game plus discipline | `insider_ownership_pct>=0.20` (INV median is 0.37) | **b** Yahoo "insiders" includes corporate parents: 59–62% of firers are ≥50% held, which is typically a listed subsidiary, not an owner-operator. Core: insider 20–60% **or** revealed alignment (FMP insider buys, alignment ratio, buyback, 3-year shrink). Surface `controlled_sub_flag` for ≥60%. `shares-float` helps separate float from strategic stakes. | owner_operator: 3,716 of 5,505 kept; flyover: 20–60% keeps 1,488 of 2,631. |
| `arch_bottleneck` (6465) | chokepoint economics: durable, fat, non-eroding GM | GM ≥0.40, GM delta, roce, capex intensity | **b** 5-year **minimum** gross margin from the cached annual IS (non-eroding, not a single YoY); **c** transcripts: pricing actions, "capacity constrained", "sole source" | 1,799; price-lindy keeps 1,080. |
| `arch_capital_light_pivot` (1862) | asset-light transition, ROIC turning up | rev 3y ≥8%, asset < rev, n_yrs ROIC ≥3, `roic_accel>0 OR roic_lindy>0.10` | **c** drop the `roic_lindy>0.10` escape, which defeats the "turning up" spirit; **c** revenue/employee rising (`historical-employee-count`) | ROIC accel required keeps 1,697 of 2,234. |
| `arch_large_cap_quality` (1842) | durable large-cap franchise | margins, FCF, leverage, returns | **c** price-lindy (625 of 818) | |
| `arch_cash_quality` (1824) | cash ROIC ahead of NOPAT ROIC | lindy | **c** fq `fq_cash_leads_earnings_flag` as a quarterly confirmation; price-lindy (1,115 of 2,011) | |
| `arch_capital_discipline` (1220) | discipline evidenced by an allocation ACTION | action leg OR insider ≥20% plus a return | **c** the insider-only path (2,198 of 3,293 firers) is the thing the comment itself says is not discipline. Require action OR (insider path & `fmp_st_financing_outflow_years/years>=0.8`). | Keeps 2,078; action-only keeps 1,095. |
| `arch_capital_returner` (1506) | material, FCF-funded shareholder yield | yield 5–30%, FCF>0 | **c** FCF covers ≥80% of the payout; **c** persistence (FMP financing outflow ≥80% of FYs, or dividend-history streak) | Coverage keeps 2,882 of 3,879; with persistence, 1,641. |
| `arch_self_funded_returner` (3371) | no-Ponzi financing, cheap | fin CF <0, persistence (NaN-permissive), FCF>0, P/E ≤15 or P/B<1.5 | **c** FCF ≥ the outflow (self-funding proven) | Keeps 1,785 of 3,121. Persistence is observed for 98% already, so it is not the issue. |
| `arch_strong_coverage` (1572) | debt trivially serviceable | IC ≥8 / nde ≤0 / net cash ≥20% | **c** through-cycle: min IC over the 5 cached FYs ≥8, or net cash with FCF>0 | Net cash plus FCF keeps 4,568 of 8,385. See section B for demotion. |
| `arch_bab_low_beta` / `arch_bab_multibagger` (1920/1945) | low-beta quality (Frazzini-Pedersen) | Yahoo `yf_beta` (shrunk) | **b** panel weekly beta vs local index, rank within market (Spearman with Yahoo only 0.46); ADV via `ts_dvol26_usd` (pew ADV rarely present) | bab_low_beta: 20 of 92 current firers are bottom-35% on panel beta. **Reach:** ADV gate `adv_has` currently needs pew ADV (8% coverage), which is why this fires on only 92 names. |
| `arch_bab_becoming` (1931) | becoming BAB-like: beta compressing | the code says "No beta time-series available" and uses a margin proxy | **b** measure it: within-market rank of 1-year beta ≤ 3-year rank − 0.10, or 1-year vol < 0.85× 3-year vol | Keeps 517 of 1,702 (377 on the beta test alone). |
| `arch_midcap_garp` (2117) | reinvestment quality on a growing earnings stream | ROIIC or proxy, E/P, ebit_g | **b** growth from fq TTM EBIT (`fq_opinc` now vs `_p` in the panel) | 1,308. |
| `arch_sustainable_scaler` (2399) | real small-cap durable growth | rev 3y, FCF/share | **b** FCF/share and shares from the fq panel | 864. |
| `arch_greenblatt_magic` (6609) | high EBIT/EV and high ROC | ev_ebit, roce | **b** ROIC from fq TTM (EBIT / (equity + debt − cash)) for non-EDGAR names | 763. |

### A.4 Value / cyclical / turnaround family (panel improves "beaten down")

**Shared helper change (2 lines, affects about 20 archetypes).** In `beaten_down_any` (1029) and `not_too_deep_any` (1044),
add `ts_dist_hi52 - 1` as the PRIMARY 52-week lens. It gets the same contradiction veto as `_oh_n`: fresh, total-return,
and 82% INV coverage. Add `ts_dist_hi260` (5-year) and `ts_r52`, and use `ts_dist_hi260` for every "former high"
/ "5y range" test.

| archetype (line) | spirit | upgrade | concrete |
|---|---|---|---|
| `arch_cundill_deep_value` (2534) | Cundill 6-point checklist | **b** point 2, "price < half the former high", = `ts_dist_hi260<=0.5` exactly (not the 52-week high) | `_c2` (2519) |
| `arch_templeton_pessimism` (5371) | cheap vs mid-cycle at maximum pessimism | **b** `ts_dist_hi260<=0.65` replaces 5y-range/5y-avg proxies | 1,645 of 2,050 |
| `arch_dead_option` (1257) | option priced as dead | **b** ≥40% below the 5-year high and no longer collapsing (`ts_r13>-0.10`) | 805 of 1,617 |
| `arch_regime_cyclical` (1233) / `arch_fixed_cost_demand_shock` (1162) | heavy fixed-cost asset + regime/demand shock | **b** "heavy asset" measured, not a sector label: `fq_ppe_net/fq_total_assets>=0.30` or `fq_da/fq_revenue>=0.05` or capex intensity ≥5%; **c** incremental EBIT margin (`fmp_dyn_incremental_ebit_margin`) as the operating-leverage proof | fixed_cost: measured asset intensity keeps 1,712 of 2,975; plus ≥10% TTM growth, 1,223 |
| `arch_xr_quality_crisis` (3515) | multi-year proven quality at a crisis price | **c** ≥2 independent multi-year quality lenses (the `oe_avg>0 & ni_avg>0` leg is just "profitable on average"); **b** crisis = ≥40% below the 5-year high; business intact (fq TTM revenue ≥ −10%) | 527 of 2,676 |
| `arch_xr_double_trough` (3830), `arch_xr_forced_seller` (3849), `arch_xr_insider_capitulation` (3915), `arch_xr_floor_inflection` (3487), `arch_xr_bigbath_rebound` (3717), `arch_xr_asset_owner_catalyst` (3973), `arch_oak_resource_leverage` (2756), `arch_oak_deep_value` (2798), `arch_crisis_asset_backed_recovery` (2884), `arch_asymmetric_assembly` (4938), `arch_levered_inflection` (4964) | dislocation plus floor | **b** panel drawdown lenses; forced_seller `price_yoy<=-0.40` → `ts_r52<=-0.40`; **c** forced_seller gets an index-deletion leg (`historical-sp500-constituent` removal in the last 12 months) and a 13F exodus leg (`fmp_inst_own_chg_q0<=-5pp`) | small counts; precision gain |
| `arch_levered_inflection` / `arch_asymmetric_assembly` / `arch_weschler_levered_equity` (4964/4938/4896) | levered stub deleveraging | **c** direct deleveraging proof `fq_deleveraging_flag` / `fq_netdebt_change_pct_assets<0`. Today only oak_deleveraging uses it; these use "EBITDA rising" as the proxy (4971). | |
| `arch_kpi_threshold` (1285) | an operating KPI crosses its threshold | **b** confirm the first-positive on quarterly TTM (`fmp_dyn_opinc/ebitda/ni_turned_positive`, `bs_ebit_turned`); 52% of firers fire on FCF-first-positive, the noisiest | 1,946 of 4,123 confirmed |
| `arch_micro_activist_inflect` (1330) | microcap inflection plus a new capital-allocation board member | **c** the missing half, measurable for US: SC 13D, 8-K item 5.02 (director appointment) via `sec-filings-search/symbol` | |
| `arch_oak_order_conversion` (4823) | backlog → revenue | **c** a forward-book leg (fq defrev build, RPO, transcripts "backlog / book-to-bill"); **b** shock-sized margin plus ≥10% growth | 1,891 of 3,953 |
| `arch_wolf_trifecta` / `arch_wolf_compounder` / `arch_wolf_turnaround` (2586/2677/2602) | double-digit growth, margins up, operating leverage, cheap | **b** operating leverage = incremental EBIT margin from fq TTM (not `oper_lev_any`, which includes raw sequential moves) | |
| `arch_micro...`, `arch_wolf_value_catalyst` (2626) | catalyst | **c** press-release / 8-K dated catalyst | |
| `arch_blindspot` (1297) | under-covered small caps in blind-spot markets | **b** the ADV leg is dead (pew ADV present for 0% of firers): replace with `ts_dvol26_usd` (≤$500k/day and ≥$50k/week validity); **b** neglect observed via numAnalysts; real operating business | 707 of 3,244 (see section B) |

### A.5 Event-driven family

| archetype (line) | spirit | current | upgrade (reach **a**) | concrete |
|---|---|---|---|---|
| `arch_spinoff_value/quality/asset` (6552/6571/6595) | forced-selling orphan | EDGAR Form-10 `spin_flag` (58 names) | **a** `sec-filings-search/symbol` for 10-12B/10-12G with dates (US), plus global "new listing" detection = panel first week within 24 months with no IPO filing, parent name/CIK match (FMP `profile` `ipoDate`); **c** orphan price pattern: `ts_r13<0` in the first 3–6 months after listing | spin_date is the anchor for a freshness window (the post-spin 6–18 month drift) |
| `arch_special_situation` (6713) | dated merger/tender/take-private with spread | EDGAR merger/tender (300 / 214) | **a** `mergers-acquisitions-latest` (global targets and dates); **c** spread = offer price vs last close (from the panel) | |
| `arch_xr_value_unlock` (4689) | cheap plus a live unlock catalyst | EDGAR full-text language, event flags | **c** SC 13D / DEFA14A (activist), 8-K 1.01/2.01, M&A feed | |
| `arch_xr_gaap_profit_crossover` (4393) | first GAAP profit unlocks mandate/index demand | NI first-positive | **c** index eligibility: not in `sp500-constituent` & US & size in band; **c** `historical-sp500-constituent` for the actual addition event | |
| `arch_post_reorg` (6697), `arch_nol_shell` (6728) | fresh-start / NOL | EDGAR | **c** 8-K item 1.03 / "emergence" date via sec-filings-search (a firmer emergence date than ReorganizationValue) | |
| `arch_insider_conviction` (4994) | open-market insider buying | Form 4 (US) + FMP insider (global) | **c** buying into a panel drawdown (`ts_dist_hi52<=0.7`) as a score term | |

### A.6 Forensic / XR family (the new data is mostly already wired; small upgrades)

| archetype | upgrade |
|---|---|
| `arch_forensic_payout_confirmed` (4816) | **Tautology**: self_funded_returner, cannibal_at_discount and dividend_verified_value *are* payouts, so "payout confirmation" is automatic for them. Count only non-payout forensic members with a material (≥3% or ≥1% shrink), FCF-covered payout: 3,458 of 7,751. |
| `arch_xr_contracted_backlog` (4266) / `arch_xr_deferred_revenue_lead` (4418) | **a** RPO is EDGAR-only; the fq defrev path is global (done). Transcripts (backlog, RPO statements) extend reach to non-US filers. |
| `arch_xr_peer_margin_gap` (4596) | **b** peer set at **industry** level (the FMP profile industry is available), not sector, with a minimum of 20 peers. |
| `arch_xr_cyclical_trough` (4088) | **b** asset-heavy measured (as fixed_cost) instead of a sector set. |
| `arch_xr_float_compounding` (3696), `arch_customer_float` (3265) | fine: fq CCC / op NWC already wired. |
| `arch_xr_cash_tax_advantage` (4466), `arch_tax_efficient` (1556) | fine: fq cash-tax wedge wired. |
| `arch_biotech_deep_value` (6438) | **b** runway from fq `fq_cash_sti` / TTM `fq_fcf` (reporting currency, same basis) instead of net_cash% × USD mcap / USD FCF. |
| `arch_xr_forced_seller` (3849) | see A.4 (index deletion, 13F exodus, `ts_r52`). |

**No material upgrade from the new data** (inputs already direct or EDGAR-specific):
`discounted_vehicle`, `tangible_value`, `roic_inflect`, `double_inflect`, `reinvest_inflect`, `buyback_compounder`,
`low_sbc_quality`, `diversified/concentrated_segments`, `geographic_global`, `fastest_segment` (FMP quarterly segments
already wired), `financials_value`, `net_cash_returner`, `oak_deleveraging` (already uses fq), `oak_nav_discount`,
`oak_asset_floor`, `cluseau_*`, `hidden_assets`, `overdepreciated_assets`, `understated_earnings`,
`expensed_growth_value`, `cash_adjusted_pe`, `owner_earnings_power`, `retained_earnings_discount`, `capex_famine_harvest`,
`dividend_verified_value` (except that dividend history adds persistence), `tax_verified_earnings`,
`cannibal_at_discount`, `book_compounder_discount`, `lifo_hidden_reserve`, `pension_overfunded`, `dta_reversal`, the XR
floor/forensic gates not listed above, `xr_investment_remark`, `xr_stake_fv_gap`, `xr_lookthrough_earner`, `xr_confluence`
(meta), `wolf_emerging`.

---

## B. Breadth diagnosis and spirit-grounded tightening (measured)

Firing counts are from `archetype_tags.csv` (all rows). The share is against INV (24,386). "Kept" means current firers
that survive the proposal. All proposals tighten through the thesis. None is a quality veto. Where a proposal changes
identity, keep the old rule as a surfaced `*_watch` flag, which is the breadth-doctrine-friendly split.

### B.1 Very broad (more than 2,500)

| archetype | firers (% INV) | why broad | proposal | kept |
|---|---|---|---|---|
| lindy_fcf | 9,356 (38%) | FMP fills made "4/5 FCF+ & 4/5 op-income+" global; `years_of_history` is 8 for 20.5k INV names, so the ≥5 gate is inert. This is the base rate of profitable firms. | Core: 5/5 + 5/5 + `roic_lindy>=0.08` (cash at an economic return); later 7/8 FYs from the cached statements. Watch: the current rule. | 3,083 (33%); 5/5 only: 5,422 |
| strong_coverage | 8,385 (34%) | Three ORed legs, each ordinary (78% pass IC ≥8, 66% net cash). It describes safety rather than carrying a mispricing thesis. | Demote to a surfaced `strong_coverage_flag`, or core = net cash with FCF>0 (serviceable from own cash), with through-cycle IC later. | 4,568 (54%) |
| lynch_pegy | 7,952 | Growth = Yahoo single-quarter `yf_earnings_growth`: 38% of firers are at the 100% cap, and 75% clear PEGY 0.5. The growth is a base effect, not Lynch growth. 24% of firers are financials (fine for P/E). | Recompute with TTM NI growth (`fq_ni/fq_ni_p−1`) capped at 50%, growth band 8–50%, plus EPS durability (positive share ≥0.75 on native or fq). | 1,278 (16%) kept; +558 new; 1,836 total |
| forensic_payout_confirmed | 7,751 | The union of 14 forensic flags (9,521) times "any payout ≥0.5%"; circular for payout-defined members. | Non-payout members only, material (≥3% or ≥1% shrink) and FCF-covered payout. | 3,458 (45%) |
| no_dilution | 7,144 (29%) | Flat shares + 4/5 + 4/5 is common among mature firms; the docstring's "high returns" is not enforced. | `roic_lindy>=0.10`, plus a 5-year share window. | 2,235 (31%) |
| lynch_evgy | 6,873 | One-year EBITDA growth (median 36% among firers, 25% above 97%); PSG/EVSG fallback supplies 882. | Denominator = min(EBITDA YoY, 3-year revenue CAGR), capped at 50%. | 2,457 (36%) |
| lindy_margin | 6,752 (28%) | 10% operating-margin lindy is broad (28% of INV); no "still durable now" test. | ≥15% lindy AND current op margin ≥0.6× lindy; later the through-cycle minimum from the 8 FYs. | 2,774 (41%) |
| narrative_lag | 6,524 (27%) | `_lag_tape` = any negative 12-month print (about half the universe) + 2 common advance legs + loose cheapness. The lag is not measured against the advance. | Lag = 1-year coil (fq TTM sales vs `ts_r52`) ≥ log 1.2, OR 2-year `bs_coil_rev>=log1.2` / `bs_coil_ebit>=log1.3`. | 4,038 (62%); strict 1-year coil: 3,234. An additional `(ebitda>0\|fcf>0)` validity check gives a 1,218-name "growth-not-rewarded core" universe-wide (see C.1). |
| owner_operator | 5,505 (23%) | Insider ≥20% passes most names (INV median 0.37), and 59% of firers are ≥50% held, i.e. parent-controlled subsidiaries. | Insider 20–60% OR revealed alignment (FMP insider buys, alignment ratio, buyback, 3-year shrink); surface `controlled_sub_flag`. | 3,716 (68%); alignment-only: 1,615 |
| negative_ev_value | 4,682 (19%) | The sub-book branch (`pb<0.7`, 3,262 firers) duplicates tangible_value / cundill and is not "negative EV". | Keep only the negative/low-EV branch; move sub-book to `tangible_value`. | 1,420 (30%) |
| weinstein_stage2 | 4,307 (18%) | `rel_pct_52w_high>=0.8` (38% of INV) and 5y-range proxies; no MA or volume. | Stage 2A core on the panel (A.1); surface a `weinstein_stage` label. | 216 of current; 640 total |
| cheap_per_roiic | 4,147 (17%) | 92% of ROIIC is FMP-filled rolling incremental ratios (noisy on small deltas). | Cash ROIIC ≥0.08 and asset 3-year CAGR ≥5% (real reinvestment). | 1,530 (37%) |
| kpi_threshold | 4,123 (17%) | 52% of firers fire on FCF-first-positive (working-capital noise); annual first-positive flags. | Confirm on quarterly TTM (`fmp_dyn_*_turned_positive`, `bs_ebit_turned`). | 1,946 (47%) |
| oak_order_conversion | 3,953 (16%) | `oper_lev_any` includes raw sequential and any positive drift; rev accel >0 or >5%. | Shock-sized margin + ≥10% TTM growth; later a forward-book leg (defrev / RPO / transcripts). | 1,891 (48%); with the forward-book leg now: 145 |
| capital_returner | 3,879 (16%) | 5% total yield is common in HK/Asia; "FCF>0" is not coverage. | FCF ≥0.8× yield + persistence (financing outflow ≥80% of FYs). | 1,641 (42%); coverage only: 2,882 |
| liger_neglected_survivor | 3,849 (16%) | Missing coverage counts as neglected (84% of firers have no coverage field); `oper_lev_any` and `ev_sales<=2` are loose. | Shock/first-positive inflection now; observed neglect (numAnalysts) once extracted. | 2,581 (67%) |
| capital_discipline | 3,293 (14%) | The insider-only path (2,198) is exactly what the comment calls "not discipline". | Action OR (insider & ≥80% financing-outflow years). | 2,078 (63%) |
| balance_sheet_return | 3,287 | 48% neg-EV (duplicates negative_ev_value), the rest one-period uncovered payouts. | Uncovered branch requires ≥2 of the last 3 FYs uncovered (FMP annual CF, cached); neg-EV branch belongs to negative_ev_value. | not measured (needs an engine column) |
| blindspot | 3,244 (13%) | The ADV leg is dead (pew ADV 0% present) → "any sub-$400M in a list of countries". | Observed neglect + real operating business + USD weekly dvol ≥$50k (validity). | 707 (22%); without dvol: 1,958 |
| asleep_at_wheel | 3,168 | 4-quarter beat ≥0.75 is a base rate (40% of covered names). | 4/4 beats + surprise + streak (≥7/8 once FMP earnings is pulled); watch = current. | 1,445 (46%); +not-rewarded: 486 |
| self_funded_returner | 3,121 | Financing outflow is common; loose cheapness. | FCF ≥ the financing outflow. | 1,785 (57%) |
| fixed_cost_demand_shock | 2,975 (12%) | Sector label (Industrials + ConsDisc are 66%). | Measured asset intensity + ≥10% TTM growth. | 1,223 (41%) |
| liger_lagging_inflect | 2,706 | Lag via any down print or base. | Measured coil lag. | 1,418 (52%) |
| xr_quality_crisis | 2,676 | Quality leg `oe_avg>0 & ni_avg>0` means "profitable on average"; 5y-range proxy. | ≥2 multi-year lenses + ≥40% below the 5-year high + business intact. | 527 (20%) |
| flyover | 2,631 | As owner_operator (62% ≥50% insider). | Insider 20–60% or revealed alignment. | 1,488 (57%) |
| cheap_sales_scaler | 2,529 | `oper_lev_any`. | Shock-sized; plus incremental EBIT margin ≥0.15. | 1,612 / 472 |

### B.2 Watch band (1,500–2,500): one lever each

- `wolf_seal` 2,244: dip measured, 256.
- `capital_light_pivot` 2,234: ROIC must actually accelerate, 1,697.
- `qarp` 2,221: price-lindy score, 1,450 as core.
- `liger_asset_backed` 2,211: observed neglect.
- `quiet_compounder` 2,172: not re-rated on the panel, 1,157.
- `xr_audited_streak_unrerated` 2,126: at least 2 no-rerate lenses; panel coil, 1,696.
- `analyst_awakening` 2,102: change-or-turn, 933.
- `templeton` 2,050: 5-year panel drawdown, 1,645.
- `tenbagger_path` 2,034: no score escape, 1,526.
- `cash_quality` 2,011: price-lindy, 1,115.
- `hidden_assets` 1,995: no new-data lever.
- `oak_asset_floor` 1,973: no lever.
- `understated_earnings` 1,917: fq persistence already.
- `net_cash_returner` 1,898: FCF coverage.
- `xr_peer_margin_gap` 1,858: industry peers.
- `durable_reinvestment` 1,805: price-lindy, 1,151.
- `bottleneck` 1,799: 5-year minimum gross margin.
- `evsales_derating` 1,735: fq TTM growth, 852.
- `bab_becoming` 1,702: measured beta compression, 517.
- `dead_option` 1,617: panel, 805.

---

## C. New flags and archetypes the new data enables (not in the codebase)

1. **`arch_growth_not_rewarded_1y`**, or the strict core of narrative_lag. Rule: TTM revenue (fq, date-matched) ≥ +20%,
   `ts_r52 <= 0` (total return), profitable (EBITDA>0 or FCF>0), INV. **Measured: 1,218 INV names.** Its 2-year sibling
   already exists as the coil leg of Coiled Base.
2. **`arch_compounder_pullback`** ("lindy compounder on a rare dip"). Rule: 5/5 FCF years, `roic_lindy>=0.12`, TTM growth
   >0, 5-year max drawdown shallower than its own market's median (price-lindy), currently 18–40% below its 52-week high.
   **Measured: 369 INV names; 141 with 3-year downside capture <0.8.** Surface `ts_dd_unusual` = current drawdown ≥ 1.5×
   the name's median 5-year drawdown.
3. **`arch_earnings_episodic_pivot`** (Kullamägi EP / ignition). Needs FMP `earnings` dates. Rule: earnings-week return
   ≥ +10%, volume ≥3× the 52-week median, beat on EPS and revenue, from a flat 26-week or 2-year base (`bs_is_base`),
   liquid in USD. A weekly-only proxy (4-week volume ≥3× and 4-week return ≥ +10% out of a 2-year base) gives 56 names
   on current `bs` coverage.
4. **`arch_index_orphan`** (forced-seller, dated). Rule: removed from the S&P 500 (and optionally Nasdaq-100 / Dow via
   FMP historical constituents) in the last 12 months, business growing (fq TTM rev ≥0), not melting. Pair with
   `arch_index_candidate`: profitable (GAAP crossover), not a member, size in band, rising RS. This gives
   `xr_gaap_profit_crossover` its mechanical catalyst.
5. **`arch_rs_leader_in_correction`** (O'Neil/Minervini leadership) as a surfaced flag. Rule: RS line at its 52-week
   high, above a rising 30-week MA, `ts_r13>0`, while local-market breadth (share above 30-week MA) <35%.
   **Measured: 1,519 INV names flagged,** so it is broad by itself. Use it as a confirmation leg for O'Neil and Kullamägi,
   or intersect with quarterly C (a few hundred).
6. **Perception-lead vs perception-chase flags** from `price-target-news` (`priceWhenPosted`):
   - `pt_lead_flag`: targets raised ≥10% over 90 days while price moved <5%.
   - `pt_chase_flag`: targets raised only after price rose ≥20%, meaning late.

   These fit awakening, skeptic and coiled base. They are global where FMP carries targets, and the endpoint is already
   cached for the event-study subset.
7. **Earnings-reaction flags** (FMP `earnings` + panel):
   - `ereact_fade_flag`: beats with negative average reactions over 4 quarters. The "asleep / skeptic" tell.
   - `pead_flag`: beat plus positive reaction plus positive 4–8-week drift.
8. **`ts_beta_compressing_flag`** and **`ts_drawdown_resilient_flag`**. Beta compression is 1-year beta rank ≤ 3-year
   rank − 0.10 within market. Drawdown resilience is 3-year downside capture <0.6 with a bottom-40% beta, which flags
   3,975 INV names, so it belongs as a surfaced tag or score, not an archetype.
9. **`weinstein_stage` label** (1 base, 2 advance, 3 top, 4 decline), derived from close vs the 30-week MA, MA slope and
   MRS. Also a **`ts_multi_year_high_flag`** for a close at its 5-year high after a 2-year base, i.e. a breakout from a
   long base.
10. **`dividend_growth_streak`** from FMP `dividends` history: consecutive years of increases, and cuts. It gives
    persistence to capital_returner, dividend_verified_value and cundill point 5.
11. **`employee_leverage_flag`** from `historical-employee-count`: revenue per employee up ≥15% with headcount flat.
    Direct operating-leverage evidence for capital_light_pivot, pre_scale_margin and reusable_assembler. Mostly US
    coverage.
12. **`controlled_sub_flag`**: insider ≥60%, surfaced beside the owner-operator family, optionally corroborated by
    `shares-float` (float <30%).
13. **`attention_spike_flag`**: `news/stock` plus `news/press-releases` count over the last 30 days vs the trailing
    12-month average. This is the perception lens for non-US names where the FMP rating feed is empty.

---

## D. Data pulls required (ranked by value ÷ effort)

| # | action | endpoint / source | calls | value | unlocks |
|---|---|---|---|---|---|
| 1 | Re-run `base_snapshot.py` on the complete panel, add the `ts_*` measures (A.0), USD/pence-aware dvol | local panel, `fmp_fx_usd.csv` | **0** | very high | P0 coiled-base currency fix; bs reach from 58% to about 82% of INV; the whole momentum family; beaten_down_any; BAB beta; price-lindy |
| 2 | Extract `numAnalystsEps/Revenue` from the cached `analyst-estimates` payload; emit through-cycle columns from the cached 8-FY annuals (min op margin, min GM, min IC, 7-of-8 FCF+, FCF-margin average, uncovered-payout years) | fmp_cache (fmp_dynamics, fmp_statements) | **0** | high | observed neglect (Liger, flyover, blindspot, coiled perception); lindy tightenings; strong_coverage; bottleneck |
| 3 | Quarterly-panel features: EPS per quarter (ni/shares_dil) YoY and acceleration, TTM EBIT growth, incremental EBIT margin, FCF/share, TTM ROIC | `fmp_quarterly_panel.parquet` | **0** | high | O'Neil C/A; PEGY/EVGY durable growth; Wolf operating leverage; growth_algo; midcap_garp |
| 4 | Index price series (about 25 indices) | `historical-price-eod` (^GSPC …) | ~25 | high | Mansfield RS, O'Neil M, proper beta |
| 5 | FMP `earnings` universe-wide (limit 40) | `earnings` | ~30k | very high | asleep core; earnings reactions / PEAD / EP; Wolf Seal; ignition; O'Neil C cross-check; `earnings_variability_flag` coverage |
| 6 | Finish `fmp_sentiment` (and `fmp_dynamics`, 16k of about 30k done), then re-run tags | grades-historical, grades, price-target-summary / income-statement, EV, estimates | ~3×15k / ~4×14k | high | perception change lenses; forward-asleep; unrerated gap |
| 7 | `price-target-news` universe-wide | `price-target-news` | ~30k (cached for the event-study subset) | medium-high | pt lead/chase; global target-revision momentum for awakening |
| 8 | S&P 500 historical constituents (+ Nasdaq / Dow) | `historical-sp500-constituent`, `sp500-constituent` | 2–6 | high (cheap) | index_orphan, forced_seller leg, gaap_profit_crossover catalyst |
| 9 | US filings index | `sec-filings-search/symbol` (form types) | ~7k US | high | spin (10-12B/G) dates, 13D activist, tender/merger, 8-K 5.02, 1.03 emergence |
| 10 | Global M&A | `mergers-acquisitions-latest` (paged) | ~200–500 | medium | special_situation global reach + deal spread |
| 11 | Dividend history | `dividends` | ~15k payers | medium | dividend growth streak / cuts; capital_returner persistence |
| 12 | 13F history to 8 quarters | `institutional-ownership/symbol-positions-summary` | +5 per US name (~30k) | medium | institutional_accumulation persistence and acceleration baseline |
| 13 | Free float | `shares-float-all` (bulk) | 1–few | medium | controlled_sub_flag, O'Neil S |
| 14 | Employee history | `historical-employee-count` | ~8k (US-heavy) | medium | employee_leverage_flag |
| 15 | Earnings-call transcripts (targeted: firers of order_conversion, bottleneck, pre_scale, contracted_backlog; about 3k × 2 quarters) | `earning-call-transcript` | ~6k | medium-high but high effort (NLP) | backlog / book-to-bill / pricing / capacity legs; non-US RPO substitute |
| 16 | News / press-release counts | `news/stock`, `news/press-releases` | ~30k | low-medium | attention_spike_flag (non-US perception) |
| 17 | PIT market cap | `historical-market-capitalization` | ~30k | low-medium | exact P/S path (fmp_dyn EV history already covers most of it) |
| 18 | ETF holdings | `etf/holdings` (per ETF) | thousands | low | passive-ownership share / orphan status |

---

### Measurement appendix (reproducible)

- **Loader:** `scratchpad/load.py`. It merges tags, master, lynch tape, pew, bs, sent, `ts_measures`, and the FMP overlays.
  INV = 24,386.
- **Panel pass:** `scratchpad/ts.py` covers 14.4M weekly rows from 2015-06 and 27,908 live symbols. It uses a pseudo-index
  (per-market median weekly return), which the recommended FMP index series should replace.
- **Evaluation scripts:** `p5`–`p21`. Every "kept" figure above is the count of current `arch_*==1` rows also meeting
  the proposed condition.
