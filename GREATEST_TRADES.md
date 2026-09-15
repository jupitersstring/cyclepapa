# Greatest Trades — pre-rerating fingerprint & engine proposals

Event study of 417 corporate-action events. A **monster** trade = +100% or more over 12 months; 19 qualified (5% base rate).

## Headline

**The pre-rerating fingerprint of a monster is a violent, prolonged WASHOUT — not a calm base.** Before they ran, the greatest trades sat **-52%** below their 24-month high (vs -26% for the rest), in the **bottom ~12%** of their 12-month range, with pre-event monthly volatility of **0.18** (vs 0.10) — and were LESS likely to be in a tight consolidation than the losers (0% vs 18% basing). The one thing that was turning: the decline had begun to DECELERATE (decel +0.07 vs +0.00). Then the market confirmed — a >20% first-month pop is the single strongest tell (3.2× lift).

**The critical divergence: MEDIAN-best ≠ TAIL-best.** The catalysts that produce the monsters are NOT the ones with the best average outcome. Monster-rich: CH11_EMERGENCE (9%), SPINOFF (9%), STRATEGIC_REVIEW (8%), UPLISTING (6%) — several of these (strategic-review, uplisting, Ch11) have NEGATIVE median returns, i.e. they are LOTTERY TICKETS. Median-best: ASSET_SALE (+10%), TENDER_OFFER (+9%), SPINOFF (+4%). The engine currently weights catalysts by the median, which SUPPRESSES the monster-rich lottery catalysts. For tail hunting they should be weighted UP and sized DOWN (convex, small-position bets), on a separate track from the median/expected-value plays.

## What the monsters looked like BEFORE they moved

| pre-event feature | monster | the rest |
|---|---|---|
| drawdown from 12m high | -32% | -21% |
| drawdown from 24m high | -52% | -26% |
| position in 12m range | 0.124 | 0.39 |
| prior-12m return | -20% | -8% |
| pre-event monthly vol | 0.181 | 0.105 |
| basing / consolidating | +0% | +18% |
| decline decelerating (decel) | 0.069 | 0.0 |
| +1m confirmation drift | +0% | -1% |

## Strongest pre-rerating lifts (P(monster | feature) / base)

| feature = bin | lift | n |
|---|---|---|
| post_1m = up>20% | 3.23× | 34 |
| sector = Healthcare | 2.37× | 37 |
| pre_vol = wild | 2.34× | 103 |
| sector = Utilities | 2.19× | 10 |
| catalyst = CH11_EMERGENCE | 2.0× | 11 |
| catalyst = SPINOFF | 1.96× | 56 |
| drawdown_12m = deep | 1.76× | 75 |
| drawdown_24m = deep | 1.75× | 88 |
| catalyst = STRATEGIC_REVIEW | 1.73× | 38 |
| sector = Consumer Cyclical | 1.73× | 38 |
| sector = Basic Materials | 1.46× | 15 |
| pre_12m = down | 1.44× | 122 |
| catalyst = UPLISTING | 1.43× | 46 |
| sector = Technology | 1.42× | 31 |
| size = large | 1.41× | 78 |
| range_pos = low | 1.39× | 174 |

## Greatest trades by archetype

- **CH11_EMERGENCE** — 1/11 monsters (9%), median +0%. Top: DBD +136%, NCMI +78%, OI +53%, UGI +30%
- **SPINOFF** — 5/56 monsters (9%), median +4%. Top: MPTI +250%, LION +164%, XPO +128%, GRAL +122%
- **STRATEGIC_REVIEW** — 3/38 monsters (8%), median -12%. Top: SYRE +975%, IRWD +495%, CMTL +195%, DNTH +96%
- **UPLISTING** — 3/46 monsters (6%), median -23%. Top: MP +168%, ALMU +122%, BURL +105%, XYL +51%
- **ASSET_SALE** — 3/49 monsters (6%), median +10%. Top: VSTM +147%, NRG +112%, TPR +100%, NTRP +99%
- **BUYBACK_AUTH** — 2/71 monsters (3%), median -3%. Top: MYRG +150%, AKA +149%, NWPX +85%, EML +79%
- **TENDER_OFFER** — 1/38 monsters (3%), median +9%. Top: CVNA +259%, OBTC +80%, BFH +77%, GILD +63%
- **CAPITAL_RETURN** — 1/53 monsters (2%), median -6%. Top: ESOA +238%, LENZ +80%, KRT +73%, COKE +70%
- **EXCHANGE_OFFER** — 0/19 monsters (0%), median +0%. Top: USFD +24%, WMG +17%, BHC +14%, TROX +9%
- **GOING_PRIVATE** — 0/15 monsters (0%), median -23%. Top: SPHR +53%, TSQ +34%, CHCI +14%, MSGS +5%
- **SALE_OF_COMPANY** — 0/12 monsters (0%), median -38%. Top: CREX +76%, AMPY +61%, SNWV +56%, VIASP +0%
- **SEPARATION** — 0/9 monsters (0%), median -4%. Top: KNF +61%, WOR +30%, NATL +28%, MDU +26%

## Proposed engine improvements (data-driven)

2. **Deepen the drawdown gate on a 24-month lookback.** Monsters sat -52% below their 24m high vs -26% for the rest; the 24m drawdown separates better than the 12m. Add drawdown_24m to the geometry/tail feature set and weight the deep bucket.
3. **Add a DECELERATION filter.** Monsters' decline was decelerating pre-event (decel +0.07 vs +0.00) — the fall was stopping, not accelerating. Gate latent archetypes on decel >= 0 to avoid knives.
4. **Keep/strengthen the confirmation rule.** Monsters drifted +0% in the first month vs -1% — early confirmation remains the single cleanest separator; consider a lower confirmation threshold for the archetypes whose monsters confirmed most.
5. **Re-weight archetypes by monster rate.** Highest: CH11_EMERGENCE (9%), SPINOFF (9%), STRATEGIC_REVIEW (8%); lowest: EXCHANGE_OFFER (0%), GOING_PRIVATE (0%), SALE_OF_COMPANY (0%) — tilt catalyst weights toward the monster-rich types.
6. **Pre-vol / size:** see the lift table above; add the highest-lift bins as explicit tail-odds features where not already present.
