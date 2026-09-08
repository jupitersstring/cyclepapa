# Archetype Deep Audit — lynch/screen + segment + contrarian/neglect family

Universe N = 46,526 (archetype_tags.csv joined to asymmetry_global.csv on `symbol`,
plus lynch_reward_signals.csv and edgar_segment_signals.csv). All counts are real
firer queries. Worst-first within the batch.

Legend: "fires X%" = share of the 46,526-name universe tagged 1.

---

## 1. arch_narrative_lag — 13,630 firers (29.3%)  [WORST: near-noise]

**SPIRIT:** Business ADVANCING while the market ignores it (flat price on a real advance).
**RULE (line 394):** `flat_or_down & ((advance_breadth >= 2) | any_first_positive_print)`, where
`flat_or_down = (price_yoy<=0 | momentum_12m<=0)` and the advance legs are loose (rev_yoy>=0.10,
ebitda_margin_delta>=0.02, any interval-inflection twitch, or a single first-positive print).

**Why it's near-noise:** `flat_or_down` alone is **43.5% of the entire universe** — nearly half
of all names have a down year. The advance requirement then admits ~2/3 of those. What actually
distinguishes a firer from a random flat name is almost nothing: any 10% revenue print or any
"EPS improving from a loss" first-positive fires it. Concretely:
- **4,136 firers (30%) are lossmaking** (ebitda_margin <= 0) yet tagged "business advancing."
- **518 firers have price_yoy == 0.0 AND momentum_12m == 0.0 exactly** — a stale/missing tape
  filled with 0 reads as "flat" and is admitted. The `notna()` guard fails because the values are
  literal 0.0, not NaN. Examples: **WEBJF** (Web Travel, $337M), **VITOF** (Vitro SAB, $70M),
  **CPADF** (Cookpad, $70M) — all price_yoy=0.0/mom=0.0, admitted on rev_yoy alone.
- Median firer mcap is $175M and **4,665 firers are < $50M**; the single first-positive-print path
  needs only one weak leg.

**ROBUSTNESS PROPOSAL:** (a) Drop the stale-tape artifact: require a genuinely non-zero, present
tape move (`(price_yoy < 0) | (momentum_12m < 0)` with an explicit `stale_tape==0 & last_bar_age_days<=45`
guard, reusing the `lr_live_tape` already defined at line 2033). (b) Require the "advance" to be a
PROFIT advance, not a top-line twitch: gate on `ebitda_margin > 0` OR a profit-durability lens
(reuse `lr_profit_durable`), so a cash-burning nano with one 10% revenue quarter cannot fire.
(c) Raise the bar to `advance_breadth >= 2` for ALL names (drop the single-first-positive shortcut,
or require first-positive to be in a CASH measure: cfo/fcf_first_pos). This alone should cut the
pool from 29% toward <10%.

---
