# Archetype Robustness — Implementation Log

Implemented against `MASTER_consolidated.md` in `archetype_tags.py`. Only
EXISTING-archetype guards (G1, G2, G3, G5, G6, G7, G8, G9, G10) were touched;
the three new measures (G4 base floors etc.) were left to the caller.

Shared helpers used (pre-existing, defined before any archetype):
`is_operating`, `is_financial`/`is_reit`/`is_utility`, `net_cash_pct_sane`,
`ebitda_margin_sane`. One new local presence mask was added next to
`n_analysts_v`: `n_analysts_present` (raw n_analysts, before the `fillna(0)`).

`python3 archetype_tags.py` runs clean (exit 0) and writes `archetype_tags.csv`.
The file `ast.parse`s and executes after every edit. 27 archetypes changed;
no unedited archetype's count moved; none went to ~0 or exploded.

## Before → after firer counts (universe N = 46,526)

| Archetype | Before | After | Guards / groups |
|---|---:|---:|---|
| arch_negative_ev_value | 7048 | 4922 | G1 `& is_operating`; G2 `net_cash_pct`→`net_cash_pct_sane` (both the 0.75 value leg and the 0.5 survivability leg) |
| arch_oak_asset_floor | 2958 | 1396 | G1 `& is_operating`; G6 survivability `& ((fcf_ttm_v>0)|(cfo_ttm_v>0))` (matches oak_deep_value) |
| arch_oak_order_conversion | 7208 | 6299 | G1 `& is_operating` |
| arch_balance_sheet_return | 5906 | 5099 | G1 on the neg-EV leg only: `_neg_ev = ((ev<0)|(cash_gt_ev>0)) & is_operating` |
| arch_discounted_vehicle | 2324 | 1291 | G1 `& is_operating`; G2 `net_cash_pct>0.20`→`net_cash_pct_sane>0.20` |
| arch_tangible_value | 247 | 119 | G1 `& is_operating` |
| arch_liger_asset_backed | 2987 | 306 | G1 `& is_operating`; G5 `(n_analysts_v<=4)`→`(n_analysts_present & (n_analysts_v<=4))` |
| arch_liger_lagging_inflect | 5172 | 1261 | G1 `& is_operating`; G5 `(n_analysts_v<=4)`→`(n_analysts_present & (n_analysts_v<=4))` |
| arch_liger_neglected_survivor | 3940 | 716 | G1 `& is_operating`; G5 `(n_analysts_v<=3)`→`(n_analysts_present & (n_analysts_v<=3))` |
| arch_strong_coverage | 8856 | 6015 | G6 restructure: `& is_operating & (mcap>=50e6)`, net-cash leg → `net_cash_pct_sane>=0.20`, added `& (ebitda_margin_sane>0)`; interest_coverage>=8 kept as the real coverage leg |
| arch_capital_returner | 4119 | 2529 | G1 `& is_operating` (drops REIT/BDC mandatory payouts) |
| arch_capital_discipline | 3667 | 2783 | G1 `& is_operating`; G2 `ebitda_margin>=0.05`→`ebitda_margin_sane>=0.05`; G6 own-aligned restructured to require an ACTION leg (shares_growth_3y<=-0.01 OR buyback_yield>=0.02) OR insider>=0.20 paired with a return gate (roic_after_sbc>=0.10 OR fcf_yield>0) |
| arch_large_cap_quality | 890 | 749 | G1 `& is_operating`; G2 `ebitda_margin>=0.15`→`ebitda_margin_sane>=0.15` |
| arch_tax_efficient | 649 | 404 | G1 `& is_operating` |
| arch_durable_reinvestment | 504 | 184 | G3 `& (roic_lindy>=0.10) & (n_yrs_positive_roic>=4)`; ROIIC leg capped to `[0.15, 1.0]` |
| arch_cash_reinvest | 633 | 171 | G3 `& (cash_roic_lindy>=0.10) & (n_yrs_positive_roic>=4)`; cash-ROIIC leg capped to `[0.12, 1.0]` (kept its lower bar) |
| arch_kpi_threshold | 6046 | 3898 | G6 `& (mcap>=50e6)` (restored investable-scale floor) |
| arch_narrative_lag | 13630 | 13058 | G5+G9 tape gate `flat_or_down`→`_lag_tape=((price_yoy<0)|(momentum_12m<0))` — present AND genuinely down (a literal 0.0/0.0 stale/flat tape no longer qualifies). `flat_or_down` left untouched for its other consumers. |
| arch_fixed_cost_demand_shock | 4549 | 3462 | G8 `& (rev_yoy>0)` (demand shock = rising revenue); direct margin leg capped `[0.02, 0.20]` so a one-off >20pp jump can't alone qualify |
| arch_regime_cyclical | 2638 | 1597 | G8 `& (rev_yoy>0)`; direct margin leg capped `[0.02, 0.20]` |
| arch_bab_low_beta | 4739 | 3133 | G7 `& (beta_raw>=0.20)` (raw yf_beta present & >=0.2, before shrinkage) `& (adv>=1e5)` liquidity floor |
| arch_bab_multibagger | 5683 | 4078 | G7 `& (beta_raw>=0.20) & (adv>=1e5)` |
| arch_lynch_evgy | 10913 | 9099 | G9 EBITDA-yield path `& (ebitda_ttm>0)`; sales (psg/evsg) fallback also `& (ebitda_ttm>0)` (drops negative-EBITDA) `& (ev_sales>=0.05)` (guards the near-zero-EV denominator) |
| arch_evsales_derating | 4070 | 2600 | G6 size floor `(mcap>0)`→`(mcap>=50e6)`; cash sanity `& ~((ebitda_ttm_v<0)&(fcf_ttm_v<0))` |
| arch_analyst_awakening | 4058 | 2491 | G6 `& _rating_present` where `_rating_present = yf_recommendation_mean present & in (0,3.0]` — cannot fire on price-target optimism alone |
| arch_no_dilution | 814 | 803 | G10 reverse-split guard: a share drop < -30% (3y or yoy) counts only if `buyback_yield>0` corroborates |
| arch_buyback_compounder | 273 | 263 | G10 same reverse-split guard on the shares_growth_5y / shares_growth_3y legs (direct `buyback_yield>=0.03` leg untouched) |

## Items NOT cleanly implemented / partial

- **G6 arch_dead_option — LEFT AS-IS (noted, per instruction).** Its definition
  is `beaten_down_any(0.40) & _cash_yield_any & (ebitda_margin>0) & (nde<=3.0)`
  — purely a beaten-down cheap-FCF / cash-yield cow. It carries NO dedicated
  optionality / catalyst signal; the "option" is only implicit in the cash
  floor + depressed price. No clean optionality field is wired into it, so per
  the task ("leave as-is if no clean signal exists") it was not modified.
  Candidate signals exist if the caller wants to add one later
  (`inflection_print`, `not_priced_in_score`, the asym near-50-rising
  oscillators), but adding them would change the archetype's character and
  overlap the inflection family, so it was deliberately left untouched.

- **G8 oper-lev tightening (`oper_lev_any`→`oper_lev_score>=0.3`) — N/A for the
  two named archetypes.** Neither `arch_fixed_cost_demand_shock` nor
  `arch_regime_cyclical` uses `oper_lev_any`; their operating-leverage leg is
  `margin_shock_any` / `ebitda_margin_delta`. The positive-rev_yoy requirement
  and the +20pp margin cap were applied instead (see table). `margin_shock_any`
  is a SHARED helper consumed by several archetypes, so it was not modified in
  place; the demand-shock rules are now gated on rising revenue, so a margin
  swing can no longer qualify a name on its own.

- **G2 net-cash swap on the liger / oak `net_cash_pct_c` legs — not swapped.**
  Those legs use `net_cash_pct_c` (a distinct, already-clamped `±2.0` series),
  not the literal `net_cash_pct` / `net_cash_pct_mcap` the G2 instruction names,
  so they were left as-is to stay surgical. G1 `is_operating` was still added to
  every listed liger/oak archetype.

- **G2 arch_cash_quality — no change needed.** It is listed under G2 for the
  `ebitda_margin`→`ebitda_margin_sane` swap, but its current definition does not
  reference `ebitda_margin` at all (it gates on `cash_roic_lindy` / `roic_lindy`
  / `n_yrs_positive_fcf`), so there was nothing to swap.

- **G9 arch_narrative_lag — tightened but still broad (28.1% of universe).**
  The stale/flat-tape false positives (G5) and the flat-but-not-down names were
  removed by requiring a genuinely DOWN present tape, but narrative_lag is a
  breadth modifier by design and remains large. A harder cheapness gate was not
  added because the audit gives no clean threshold and the instruction favored
  minimal surgical edits; flagged here for possible future tightening.
