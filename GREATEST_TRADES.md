# Greatest Trades — pre-rerating fingerprint & engine proposals

Event study of 525 corporate-action events. A **monster** trade = +100% or more over 12 months; 31 qualified (6% base rate).

## Headline

**The pre-rerating fingerprint of a monster is a violent, prolonged WASHOUT — not a calm base.** Before they ran, the greatest trades sat **-64%** below their 24-month high (vs -25% for the rest), in the **bottom ~2%** of their 12-month range, with pre-event monthly volatility of **0.19** (vs 0.11) — and were LESS likely to be in a tight consolidation than the losers (6% vs 17% basing). The one thing that was turning: the decline had begun to DECELERATE (decel +0.04 vs +0.00). Then the market confirmed — a >20% first-month pop is the single strongest tell (3.2× lift).

**The critical divergence: MEDIAN-best ≠ TAIL-best.** The catalysts that produce the monsters are NOT the ones with the best average outcome. Monster-rich: SALE_OF_COMPANY (19%), CH11_EMERGENCE (14%), STRATEGIC_REVIEW (11%), SPINOFF (8%) — several of these (strategic-review, uplisting, Ch11) have NEGATIVE median returns, i.e. they are LOTTERY TICKETS. Median-best: TENDER_OFFER (+11%), ASSET_SALE (+8%), EXCHANGE_OFFER (+6%). The engine currently weights catalysts by the median, which SUPPRESSES the monster-rich lottery catalysts. For tail hunting they should be weighted UP and sized DOWN (convex, small-position bets), on a separate track from the median/expected-value plays.

## What the monsters looked like BEFORE they moved

| pre-event feature | monster | the rest |
|---|---|---|
| drawdown from 12m high | -32% | -20% |
| drawdown from 24m high | -64% | -25% |
| position in 12m range | 0.025 | 0.41 |
| prior-12m return | -22% | -5% |
| pre-event monthly vol | 0.192 | 0.111 |
| basing / consolidating | +6% | +17% |
| decline decelerating (decel) | 0.041 | 0.004 |
| +1m confirmation drift | +1% | -1% |

## Strongest pre-rerating lifts (P(monster | feature) / base)

| feature = bin | lift | n |
|---|---|---|
| post_1m = up>20% | 3.32× | 51 |
| catalyst = SALE_OF_COMPANY | 3.18× | 16 |
| catalyst = CH11_EMERGENCE | 2.42× | 14 |
| sector = Healthcare | 2.2× | 54 |
| drawdown_12m = deep | 2.12× | 104 |
| drawdown_24m = deep | 2.07× | 123 |
| pre_vol = wild | 2.02× | 151 |
| catalyst = STRATEGIC_REVIEW | 1.81× | 56 |
| sector = Technology | 1.73× | 49 |
| sector = Utilities | 1.69× | 10 |
| pre_12m = down | 1.53× | 155 |
| range_pos = low | 1.47× | 219 |
| sector = Consumer Cyclical | 1.33× | 51 |
| catalyst = SPINOFF | 1.28× | 66 |
| decel = steady | 1.2× | 113 |
| decel = decelerating | 1.14× | 223 |

## Greatest trades by archetype

- **SALE_OF_COMPANY** — 3/16 monsters (19%), median -19%. Top: SNWV +396%, ALTS +339%, IRRX +185%, CREX +76%
- **CH11_EMERGENCE** — 2/14 monsters (14%), median -5%. Top: SRNE +212%, DBD +136%, NCMI +81%, OI +53%
- **STRATEGIC_REVIEW** — 6/56 monsters (11%), median -5%. Top: INRE +107259%, SYRE +975%, IRWD +496%, SVT +340%
- **SPINOFF** — 5/66 monsters (8%), median +5%. Top: MPTI +250%, LION +164%, XPO +128%, GRAL +122%
- **SEPARATION** — 1/15 monsters (7%), median +4%. Top: MODG +132%, KNF +61%, ODP +40%, WOR +32%
- **ASSET_SALE** — 4/68 monsters (6%), median +8%. Top: COMM +316%, VSTM +147%, NRG +120%, TPR +103%
- **UPLISTING** — 3/56 monsters (5%), median -23%. Top: MP +168%, ALMU +122%, BURL +105%, XYL +53%
- **EXCHANGE_OFFER** — 1/24 monsters (4%), median +6%. Top: SATS +199%, PTVE +62%, PRMW +32%, USFD +24%
- **BUYBACK_AUTH** — 3/81 monsters (4%), median +0%. Top: MYRG +150%, AKA +149%, PEV +130%, NWPX +85%
- **CAPITAL_RETURN** — 2/59 monsters (3%), median +0%. Top: MEDS +3524%, ESOA +243%, KRT +82%, LENZ +80%
- **TENDER_OFFER** — 1/47 monsters (2%), median +11%. Top: CVNA +259%, BK +82%, OBTC +80%, BFH +79%
- **GOING_PRIVATE** — 0/23 monsters (0%), median +1%. Top: GES +69%, SPHR +53%, STCN +42%, TSQ +42%

## Proposed engine improvements (data-driven)

2. **Deepen the drawdown gate on a 24-month lookback.** Monsters sat -64% below their 24m high vs -25% for the rest; the 24m drawdown separates better than the 12m. Add drawdown_24m to the geometry/tail feature set and weight the deep bucket.
3. **Add a DECELERATION filter.** Monsters' decline was decelerating pre-event (decel +0.04 vs +0.00) — the fall was stopping, not accelerating. Gate latent archetypes on decel >= 0 to avoid knives.
4. **Keep/strengthen the confirmation rule.** Monsters drifted +1% in the first month vs -1% — early confirmation remains the single cleanest separator; consider a lower confirmation threshold for the archetypes whose monsters confirmed most.
5. **Re-weight archetypes by monster rate.** Highest: SALE_OF_COMPANY (19%), CH11_EMERGENCE (14%), STRATEGIC_REVIEW (11%); lowest: GOING_PRIVATE (0%), TENDER_OFFER (2%), CAPITAL_RETURN (3%) — tilt catalyst weights toward the monster-rich types.
6. **Pre-vol / size:** see the lift table above; add the highest-lift bins as explicit tail-odds features where not already present.
