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

## 2. arch_lynch_evgy — 10,913 firers (23.5%)  [WORST: definitional gaming via sales fallback]

**SPIRIT:** Lynch EV growth-yield — cheap on EV/EBITDA RELATIVE to EBITDA growth (+div).
Threshold: `ev_ebitda_gy <= 0.6`.
**RULE (line 1017):** `((evgy>0)&(evgy<=0.6)) | (evgy_missing & ((psg>0&psg<=0.06)|(evsg>0&evsg<=0.05)))`.

**Two problems, both admit names the spirit excludes:**
1. **Sales fallback is a different measure entirely (2,738 firers, 25% of the pool).** When
   `ev_ebitda_gy` is missing the rule substitutes a price/EV-to-SALES-growth ratio (psg/evsg). That
   has nothing to do with EBITDA growth-yield — it fires on any ultra-low-P/S name, structurally
   common for insurers/distributors/holdcos. Examples: **IKGR.MI** (Intek Group, psg 0.00048,
   ebitda_margin **-0.7%**), **RAHGF** (Roan Holdings, evsg 0.58 but ev_sales 15.9 and
   ebitda_margin **-9%**), **MPSC.F** (Muhl, psg 0.0043). A negative-EBITDA name should never carry a
   "cheap-vs-EBITDA-growth" tag.
2. **Denominator/cheapness artifact in the primary leg (2,024 firers with EV/EBITDA < 5).** A very
   low EV/EBITDA (often near-zero or net-cash EV on a distressed micro) drives evgy tiny regardless
   of growth — so the tag captures absolute cheapness/distress, not the growth-yield relationship.
   min evgy = 0.0.

**ROBUSTNESS PROPOSAL:** (a) Kill or quarantine the sales fallback — at minimum require
`ebitda_margin > 0` and `ebitda_yoy > 0` before any psg/evsg substitution is allowed, so a
loss-maker or no-growth name can't back into the tag through a sales ratio. (b) Add a growth floor
to the primary leg: require the denominator's EBITDA-growth component to be materially positive
(e.g. `ebitda_yoy >= 0.05`) so evgy reflects growth-yield, not a near-zero-EV artifact. (c) Add a
minimum EV/EBITDA floor (`ev_ebitda >= 2`) to drop distressed near-zero-EV micros.

---

## 3. arch_kpi_threshold — 6,046 firers (13.0%)  [spirit gap: comment promises a scale gate that isn't in the code]

**SPIRIT (comment lines 466-474):** operating KPI inflection "at investable scale" — first-positive
profitability print CONFIRMED by margin/ROCE improvement.
**RULE (line 475):** `first_pos_print & (margin_confirming | roce_today>=0.05)`. **There is no mcap
gate at all**, despite the comment explicitly claiming "AND that the company is at investable scale."

**False positives:** median firer $149M, but **2,080 firers < $50M and 851 < $10M**; 74 have
unknown mcap. **1,051 firers are lossmaking** (ebitda_margin <= 0) — they qualify because a
first-positive print includes `ni_first_pos`/`ebitda_first_pos` ("EPS/EBITDA improving from a loss")
and the `margin_confirming` leg accepts a 1-point YoY margin move. Examples: **SECI** (Sector 10,
$30 mcap, roce -0.2%), **MOTNF** (Clean Power Capital, $246, ebitda_margin 0), **STMH** (Stem
Holdings, $666, ebitda_margin 0). These are penny-stock shells, not KPI-threshold compounders.

**ROBUSTNESS PROPOSAL:** (a) Add the scale gate the comment already promises: `mcap >= 50e6`
(or the framework's standard investable floor). (b) Require the inflection to land on a POSITIVE
base, not a loss: `ebitda_margin > 0` OR restrict first-positive to cash measures
(cfo/fcf_first_pos) so "improving from a loss" alone can't fire. (c) Tighten `roce_today` OR
`margin_confirming` to require BOTH when the first-positive is a non-cash (NI/EBITDA) print.

---

## 4. arch_lynch_pegy — 5,066 firers (10.9%)  [moderate: bounded ratio, but no quality/cash guard]

**SPIRIT:** PEGY = P/E / (EPS growth% + div%) <= 1.0 — growth+income you aren't paying for.
**RULE (line 1014):** `(pegy>0) & (pegy<=1.0)`. Growth is capped at 100% upstream so a one-off
doubling can't manufacture a sub-0.1 ratio (good), and pegy has no sales fallback (good — the
denominator is genuinely earnings growth). Ratio distribution is sane (median 0.30, min 0.0001).

**Residual gaps:** the tag is purely the ratio — **no profitability, cash-backing, or scale guard.**
**718 firers (14%) are lossmaking** (ebitda_margin <= 0) yet carry a P/E-based growth-value tag
(these have a positive p_e on thin net income while EBITDA is negative — an accounting-vs-cash
mismatch). **323 firers < $20M.** 470 firers have p_e <= 6, where a low P/E on a value-trap does
the work rather than growth.

**ROBUSTNESS PROPOSAL:** (a) Add `ebitda_margin > 0` (or `ebitda_ttm > 0`) so the P/E-implied
earnings are cash-corroborated. (b) Add a small scale floor (`mcap >= 20e6`). (c) Require the EPS
growth in the denominator to be positive on a durable basis (reuse `eps_yoy_positive_share >= 0.5`)
so a single-year growth spike doesn't stand alone. Lower priority than 1-3.

---

## 5. arch_evsales_derating — 4,070 firers (8.7%)  [WORST guard: "not a trap" leg lets cash-burners through]

**SPIRIT:** A rapid sales grower whose EV/Sales multiple has COMPRESSED (growth outrunning the
re-rating) — a de-rated quality grower.
**RULE (line 1940):** `mcap<20e9 & (rev_yoy>=0.20 | rev_growth_score>=0.6) & derate_any &
(0.10 < ev_sales <= 6.0) & (gross_margin>=0.20 | ebitda_ttm>0 | fcf_ttm>0)`.

**False positives:**
1. **The "not a trap" leg is satisfied by `gross_margin >= 0.20` ALONE — 393 firers burn cash on
   BOTH lines** (ebitda_ttm < 0 AND fcf_ttm < 0) yet pass because a software/biotech-style gross
   margin clears the gate. Example: **BNKL** (Bionik Labs, gross_margin 0.55, ebitda_ttm -$4.8M,
   fcf -$3.4M), **ALPP** (Alpine 4, ebitda -$4.3M, fcf -$20.6M). A cash-incinerating nano is not a
   de-rated quality grower.
2. **No absolute size floor — 486 firers < $10M**, including apparent nano/artifact caps
   (**VIDE**/Video Display listed at mcap 587, **BNKL** 1248).
3. **1,537 of 4,070 fired with rev_yoy < 0.20** — i.e. via `rev_growth_score>=0.6` rather than a
   real 20% top line, loosening the "rapid sales growth" spirit.

**ROBUSTNESS PROPOSAL:** (a) Fix the trap gate: require gross_margin AND a cash/earnings floor
together (`gross_margin>=0.20 & (ebitda_ttm>0 | fcf_ttm>0)`), or at least exclude names where BOTH
ebitda_ttm<0 and fcf_ttm<0. (b) Add `mcap >= 50e6`. (c) Require the derate to be a genuine
MULTIPLE compression event (`mult_compression >= 0.15` or `derate_3y >= 0.15`) rather than the
`_evsg_exceptional & rev_growth_score>=0.5` shortcut that fires without any actual compression.

---

## 6. arch_analyst_awakening — 4,058 firers (8.7%)  [WORST data artifact: fires on optimistic price targets with NO buy rating]

**SPIRIT:** Analysts pounding the table (strong consensus rating), re-rating just STARTED.
**RULE (line 2171):** `mcap>0 & n_analysts>=3 & conviction & not_extended & live_tape`, where
`conviction` = ANY 2-of-available lenses among {rating<=2.2, target_upside>=25%, n_analysts>=8}
with `conv_score >= 0.5` (half the AVAILABLE lenses).

**False positive:** **1,551 of 4,058 firers (38%) fire with NO consensus rating at all**
(`yf_recommendation_mean` is NaN). Because conviction is "2-of-AVAILABLE," a name with rating
missing fires purely on **analyst target upside + coverage count** — and target upside is the
noisiest, most-optimism-biased analyst field. The names it selects are exactly the speculative ones
analysts slap huge targets on: **KROS** (Keros Therapeutics, upside **+102%**, 6 analysts, no
rating), **CGEN** (Compugen, +76%, 5 analysts, no rating), **LSIP.JK** (London Sumatra, +58%, 4
analysts). "Awakening" is supposed to mean a strong BUY rating with the tape just starting — a
clinical biotech with a moonshot price target and no rating is the opposite. Also `n_analysts>=3`
is a low floor and 844 firers have <5 analysts.

**ROBUSTNESS PROPOSAL:** (a) Make the consensus RATING a hard requirement (the comment says "fire
needs rating AND one other" but the code doesn't enforce it) — require `rec present & rec<=2.2`,
then one corroborating lens. (b) Down-weight or cap target-upside: an upside > ~60% should be
treated as a red flag (speculative), not conviction. (c) Raise the coverage floor to
`n_analysts >= 5`.

---

## 7. arch_dead_option — 2,036 firers (4.4%)  [spirit gap: no optionality signal]

**SPIRIT (Cluster F10):** A regime-change cyclical / hidden asset whose OPTION is mispriced as dead.
**RULE (line 451):** `beaten_down_any(0.40) & cash_yield_any & ebitda_margin>0 & nde<=3.0`.

**Gap:** the rule captures a beaten-down cheap FCF cow — it enforces NO optionality (no cyclical
sector, no regime-change/inflection print, no hidden-asset/NAV signal, no catalyst). Whatever makes
the option "mispriced as DEAD" (and about to come alive) is absent, so the tag is really "deep-value
cash generator, down 40%." Additionally **796 of 2,036 firers pass without fcf_yield>0.05**, via
alternate yield columns; some have deeply negative fcf_yield (min -1.8) yet fire on
`robust_cash_yield`/`cash_return_ev`. Median firer $182M; 295 firers < $20M.

**ROBUSTNESS PROPOSAL:** (a) Add an OPTIONALITY leg the sibling archetypes already compute: require
at least one of a heavy-asset/cyclical sector membership, a margin/EBITDA inflection print
(`ebitda_inflection>0 | margin_shock_any`), or an asset-floor signal (net_cash_pct high / NCAV) —
so "dead" has a live option behind it. (b) Require the primary `fcf_yield > 0.05` (don't let a
negative-FCF name in on a noisy alternate yield), or require 2 cash-yield lenses to agree.

---

## 8. arch_blindspot — 3,364 firers (7.2%)  [spirit gap: geography+size only, no quality]

**SPIRIT (Cluster G12):** A good business in a geography the research corpus structurally misses.
**RULE (line 484):** `country in BLINDSPOT_COUNTRIES & 0<mcap<4e8 & (no ADV | ADV<5e5)`.

**Gap:** there is **zero fundamental/quality requirement** — the tag fires on ANY small illiquid
name in a blind-spot country, including money-losers. **818 firers are lossmaking**
(ebitda_margin<=0); 836 firers < $20M. Examples: **PRGNF** (Paragon Shipping, GR, ebitda_margin
-264%), **EURI** (AgriEuro, RO, -79%), **DANR** (Dana Resources, PE, ebitda 0). This is a universe
filter masquerading as a quality archetype; nothing distinguishes a firer from a random KR/TH/ID
nanocap. (If it's intended purely as a coverage bucket that's defensible, but then it shouldn't sit
alongside thesis archetypes without a quality overlay.)

**ROBUSTNESS PROPOSAL:** Add a minimal quality/viability overlay so "blind-spot" means a business
worth spotting: `ebitda_margin > 0` OR `fcf_ttm > 0` OR net-cash balance sheet, plus optionally a
survivability/inflection lens. Keep the geography+size+illiquidity as the coverage gate but require
the name to clear a floor a random nanocap wouldn't.

---
