# The empirical "best across the entire universe" answer

The question: across 6,164 US-listed tickers, which names are
*actually* the most asymmetric -- not just top of one model, but
top across many independent lenses.

The method: 8 independent rankers + 2 archetype-winner markdowns
joined per ticker. A name surfaced by 1 ranker may be a model
artifact. A name surfaced by 4-6 independent rankers built from
different evidence (PSU forensics, governance, insider behavior,
valuation, tender mechanics, debt-haircut forcing functions,
coverage-normalised universe rank) is empirically asymmetric.

## The 13 high-conviction convergent names

>= 3 of 8 screens AND winner of at least one PSU/governance archetype:

| Ticker | Screens | Archetypes won | Why it converges |
|---|--:|--:|---|
| **HFFG** | **6** | 4 | Triple PSU $ hurdle (revenue/EBITDA/FCF), P/B 0.48, microcap, gov 15 (clawback strengthened); 4-buyer F4 cluster; informational_buys firing |
| **CSGP** | 4 | 5 | EBITDA $ hurdle; 10x CEO ownership; shareholder-feedback responsive; lowest SOP support 45%; verified buyback EXECUTING -3.6% |
| **LE** | 4 | 4 | 12-tranche price ladder; 86% PSU LTI; ROIC stack; live TARGET tender (note: retirement carveout flag = caution) |
| **NUS** | 4 | 2 | Named asset-sale PSU + 5-metric clean per-share stack; P/B 0.33 |
| **GO** | 4 | 1 | Forward $ targets + Cohen-Malloy informational buys + insider cluster (single-trigger CIC = caution) |
| **ADT** | 4 | 2 | 90% PSU% LTI (heaviest in universe); shrinking shares -7.3%; 3-buyer F4 cluster |
| **KMPR** | 3 | 3 | Custom per-share metric + anti-hedge/pledge + verified buyback EXECUTING (repricing flag = caution) |
| **MAT** | 3 | 2 | Double dollar hurdle (EBITDA + FCF) -- only name in universe winning two A-bucket forward-trigger archetypes |
| **RNR** | 3 | 1 | Deepest per-share metric stack (>=5 per-share metrics) |
| **GPRO** | 3 | 1 | PSU vests on spin/separation |
| **LMT** | 3 | 2 | Forward $ FCF hurdle + backlog target (mega-cap defense) |
| **CDE** | 3 | 1 | CEO 10b5-1 termination score 80 (#1 in universe) |
| **EXFY** | 3 | 1 | Live issuer self-tender (Expensify -- the gap-closer name) |

## Consensus tier distribution (8 screens, 829 cumulative top-of-rank slots)

| n_screens | Count | Meaning |
|--:|--:|---|
| 6 | 1 | HFFG -- uniquely convergent |
| 4 | 19 | high cross-validation |
| 3 | 45 | meaningful cross-validation |
| 2 | 132 | corroborated but one-leg-dependent |
| 1 | 629 | single-lens; may be model artifact |

## Robustness check

Re-ran after expanding yfinance coverage from 1,885 -> 2,132 tickers
(247 new enrichments via gap-fill). **The 13-name convergent list did
not change.** New entrants to the 4-screen tier with the expanded
data: TROX, RBNE, SVRN, MLCI, WHR, ANGI. These are now corroborated
on valuation evidence; they may climb to high-conviction after the
buyback_verify gap-fill completes (currently 575 / 1,040 done).

## What grand_unified surfaces that prior composite missed

47 of the top 50 are different vs the original unified_composite.csv.
The prior composite over-weighted Form-4 cluster presence; grand_unified
surfaces PSU-forward-trigger + value-floor names that lacked insider
data:

| ticker | grand_unified rank | prior composite | reason hidden |
|---|--:|---|---|
| EHTH | 1 | not in top 50 | no insider buys; PSU triple $ hurdle invisible to composite |
| THRY | 2 | not in top 50 | same |
| HAIN | 15 | not in top 50 | same |
| MAT, LMT, ICE | top 30 | not in top 50 | mega/mid-caps with no microcap insider cluster |

## What the prior composite has that grand_unified doesn't

GETY, TONX, ACET, BRBS, FISV, HDSN, GRND, PCSA -- these have rich
Form-4 P-buy data driving the composite but score below median on
PSU/governance, so grand_unified ranks them lower. **Both views are
correct; they're scoring different things.** The consensus meta-ranker
reconciles them by demanding cross-validation.

## How to use this

- **The 13 convergent names are the empirical "best of universe."**
  Any one of them appearing on a watchlist is a defensible decision.
- **HFFG is uniquely convergent** -- the only name surfaced by 6 of 8
  screens; the only A1 PSU revenue $ hurdle winner that also fires
  insider cluster + clawback strengthening + Bastian floor.
- **CSGP** is the largest-mcap name on the list; the 5-archetype-win
  is structural (CEO 10x ownership, EBITDA $ hurdle, shareholder
  responsiveness, SOP dissent at 45% giving you forced board response).
- **LE / KMPR carry "caution flags"** -- retirement carveout and
  repricing language respectively; they're convergent but governance
  isn't clean.

## Sources joined

```
unified_composite.csv     unified_composite.py            top 150
informational_buys.csv    Cohen-Malloy-Pomorski 5-cond    top 100
bastian_forcing.csv       debt-haircut microcap           top 50
psu_asymmetric_full.csv   PSU forward triggers            top 200
psu_valcreate.csv         per-share value-creation        top 150
psu_gov_asymmetry.csv     thesis-led PSU/gov composite    top 150
grand_unified_ranked.csv  coverage-normalised 7-layer     top 150
special_situations_unified.csv  EDGAR-stream pipeline     top 200
PSU_ARCHETYPES.md         38 PSU/gov archetype winners
ASYMMETRIC_BY_ARCHETYPE.md 19 thesis archetype winners
```

Output: `consensus_ranking.csv` (full 829 names with screens list +
per-screen ranks).
