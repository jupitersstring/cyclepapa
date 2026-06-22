# The Asymmetric Equities Workbook

**A Case-Method Companion to the Universe Analysis**

*Cyclepapa Research, Module Series 1*

---

## Preface

This workbook teaches a discipline: how to surface structurally
asymmetric common-equity positions by integrating PSU forensics,
governance scoring, insider behaviour, capital-structure forcing
functions, tender mechanics, and verified buyback execution across
a universe of 6,164 US-listed companies.

It is built in the case method. Each case opens with a *situation*
— a real ticker as of mid-2026 — followed by *exhibits* drawn
from the underlying scoring data, *discussion questions* the
analyst should be able to answer before reading the *teaching note*,
and a brief *what we did* showing the decision actually taken.

**Suggested study sequence.** Cases A–E in order; Modules I–IV as
needed. Each case takes 45–60 minutes if you write out answers
before reading the teaching note.

**Notation.** Throughout: "PSU%LTI" = performance share units as a
percentage of long-term incentive value granted. "Cond_cat" = forward-
conditional vesting category coded in plan (`revenue_dollar_target`,
`spin_separation`, `asset_sale_named`, etc.). "Tier A/B/C" = data-
coverage tier per `grand_unified_ranked.csv` (A = 6+ of 7 layers,
B = 4–5, C = <4).

---

## Table of Contents

**Front matter**
- Preface
- Learning objectives
- How to read this workbook

**Cases**
- **Case A: HFFG (HF Foods Group, Inc.) — The Convergent Winner**
  Why a single name surfaces on 6 of 8 independent screens.
- **Case B: CSGP (CoStar Group) — Governance as Catalyst**
  How a 45% say-on-pay vote becomes a forced-action signal.
- **Case C: Lands' End (LE) — The Caution-Flagged Convergent**
  When archetype victories conceal retirement carveouts.
- **Case D: ODTX (Odonate Therapeutics) — The Insider-Information Trifecta**
  $75.3M of P-buys = 9.57% of float in 30 days.
- **Case E: EXFY / BBGI — The Forcing-Function Stub**
  Reading creditor covenants as catalysts.

**Modules**
- **Module I: The Universe and Its Layers**
- **Module II: The Convergence Test**
- **Module III: Caution-Flag Taxonomy**
- **Module IV: Deployment by Mandate**

**Appendices**
- Appendix A: Signal-layer methodology
- Appendix B: Per-pattern leaderboards (full)
- Appendix C: Glossary

---

## Learning Objectives

After completing this workbook the analyst should be able to:

1. Identify whether a single-signal screen result is structurally
   asymmetric or a model artifact, by checking convergence across
   independent rankers.
2. Read a DEF 14A's PSU plan as a *catalyst description* — the
   forward dollar hurdle that defines what the board has been paid
   to achieve.
3. Distinguish a "10b5-1 termination" (informational) from a
   "10b5-1 adoption" (mechanical) and weight them accordingly.
4. Recognise the BBGI forcing-function archetype in an exchange-
   offer 8-K before the asset sale closes.
5. Combine a hard floor (P/B, tender bid, verified shrinkage) with
   an outsized catalyst the market hasn't priced — the asymmetric
   common-equity structural recipe.
6. Size a position by knowability and downside, not by upside —
   the Bastian/Dalius two-question test.

## How to Read This Workbook

Each case follows a strict format:

```
SITUATION       60–120 words. Just the facts as of mid-2026.
EXHIBIT 1       The scoring stack output for the name.
EXHIBIT 2       The PSU plan structure (cond_cats, %LTI, gov_score).
EXHIBIT 3       The supporting evidence (buyback, tender, F4, 10b5-1).
QUESTIONS       4–6 questions. Write answers before reading the note.
TEACHING NOTE   The framework-level lesson.
WHAT WE DID     The actual ranking decision and where it appears.
```

---

# Case A: HFFG (HF Foods Group, Inc.) — The Convergent Winner

## Situation

HF Foods Group, Inc. (NASDAQ: HFFG) is a $98M market-cap distributor
of Asian-restaurant supplies operating ~16 distribution centers across
the US. Spot price $1.84. P/B 0.48. The stock sits 52% below its
52-week high.

The board's latest DEF 14A discloses an unusual PSU plan: three
separate forward dollar hurdles — revenue must reach $1.232B for
PSUs to vest at target, with step-up to $1.281B and $1.319B for
higher payouts. The plan strengthens the clawback policy and codes
EBITDA and FCF dollar thresholds alongside revenue.

In the trailing 90 days, four insiders — CEO, CFO, and two directors
— made open-market purchases totaling materially less than 1% of
market cap but representing role-balanced conviction.

The analyst's task is to rank HFFG against the 6,164-name universe.

## Exhibit A-1 — Consensus screen presence

| Screen | HFFG rank / top-N | Why surfaced |
|---|--:|---|
| `grand_unified_ranked` (7-layer norm score) | top 10 | PSU + value + governance |
| `informational_buys` (Cohen-Malloy 5-cond) | top 30 | 4-buyer cluster, material |
| `psu_asymmetric_full` (forward triggers) | top 50 | triple dollar hurdle |
| `psu_gov_asymmetry` (thesis composite) | #1 | core 52 + gov 15 + n_fwd 3 |
| `psu_valcreate` (per-share alignment) | top 40 | TSR core, no per-share gameable metric |
| `unified_composite` (original) | top 20 | F4 + value |
| Archetype: PSU forward $ revenue hurdle | **Winner** | Single best representative |
| Archetype: clawback strengthened | **Winner** | Top governance evolution |
| Archetype: front-loaded grant (red-flag) | **Winner** | Caution flag (see Case A note) |

**HFFG surfaces on 6 of 8 screens. It is the only name in the
universe to do so.**

## Exhibit A-2 — PSU plan structure

```
psu_core           52.0
gov_score          15.0
psu_pct_lti        50%
cond_cats          [revenue_dollar_target]
per_share_metrics  [tsr]
fwd_snippets       "vest at 100%, the Company must have achieved a
                    revenue of $1.232 billion"
                   "vest at 100%, the Company must achieve a revenue
                    of $1.281 billion"
                   "vest at 100%, the Company must achieve a revenue
                    of $1.319 billion"
pattern_reasons    [clawback strengthened, anti-hedge/pledge,
                    front-loaded grant]
```

## Exhibit A-3 — Supporting evidence

| Layer | Reading |
|---|---|
| Form 4 P-buys (90d) | 4 buyers (CEO, CFO, 2 directors), role-balanced |
| 10b5-1 plan disclosure | Quiet — no terminations, no fresh adoptions |
| Tender / 13E-3 | None live |
| Buyback verification | `NO_AUTH` — share count –0.9% trailing 200d |
| yfinance | mcap $98M, P/B 0.48, 52% off high |

## Discussion Questions

1. The plan defines a *specific dollar revenue target*, not a TSR
   percentile. Why is this structurally more informative than the
   typical relative-TSR PSU?

2. The Cohen-Malloy-Pomorski cluster has only 4 buyers and is small
   in absolute dollars. Why does it nonetheless score so highly on
   `informational_buys`?

3. The `front-loaded grant` flag appears alongside `clawback
   strengthened`. Are these contradictory? Which weighs more in
   sizing?

4. HFFG is Tier B (4–5 of 7 data layers). What gap-fill would most
   improve confidence?

5. The PSU revenue hurdle is *known*. Why does this convert
   "uncertainty" to "knowability" and improve the asymmetric
   payoff math?

## Teaching Note

**A1. Why a dollar hurdle is more informative than relative TSR.**
A relative-TSR PSU can vest with the stock down 30% if the peer
group is down 40%. The board gets paid for outperforming a basket,
not for creating absolute value. A *named dollar revenue hurdle*
($1.232B target) is unconditional: the board only vests if revenue
in fact reaches that number. The board has therefore told you,
publicly, exactly what they are working toward. You can value the
gap between current revenue (~$1.15B in the most recent quarter
annualised) and the hurdle. If they hit it, the equity must
re-rate to a different revenue regime. If they don't, the PSU
fails. There is no in-between.

**A2. Why the small cluster scores so high.** The Cohen-Malloy-
Pomorski result is that *role mix* and *clustering window* dominate
absolute dollar size in predicting abnormal return. Four buyers
across CEO/CFO/director within 30 days is a *coordination signal*:
it is unlikely to occur unless the participants share a non-public
view that the stock is mispriced. The dollars are modest because the
mcap is modest; the *coordination is large*.

**A3. Front-loaded grant vs clawback.** A front-loaded grant pays
the executive now for goals to be hit later — it shifts risk from
the executive to the shareholder. A strengthened clawback retrieves
compensation if the achievement was misrepresented or restated. They
are *not contradictory*: they are two layers of compensation hygiene
arguing in opposite directions. The net read here is mixed: HFFG's
board accepted a front-loaded grant *and* added clawback teeth in
the same plan. The grant suggests urgency (board paid the executives
upfront to act); the clawback suggests discipline (they can claw
back if action is bad). The flag is real but should not veto.

**A4. Gap-fill priority.** HFFG's missing layers are: detailed
10b5-1 disclosure parsing (signed_score absent) and full Form 144
(proposed sales) coverage. Both would either confirm or break the
"insider conviction" reading. The signed_score from a richer
cancel_10b5_1 scan would be the highest-information add.

**A5. Knowability.** The asymmetric structural recipe is: hard floor
(half book, microcap, low absolute price) + outsized catalyst the
market hasn't priced. The "catalyst the market hasn't priced" is
typically uncertain. HFFG converts it to *knowable*: the board's
own plan tells you the catalyst — $1.232B revenue. If hit, the
equity re-rates; if not, the floor is the P/B. The math of the
position has been *defined for you*.

## What We Did

- Ranked HFFG #1 on `consensus_ranking.csv` (6 of 8 screens, 4 of
  57 archetypes won).
- Surfaced as **A1** on `ASYMMETRIC_BY_ARCHETYPE.md` (PSU forward
  revenue $ hurdle winner).
- Listed first in the "highest-conviction concentrated position"
  bucket of `SYSTEMATIC_RANKINGS.md` use-case deployment sheet.
- Cautioned in section 5 of `SYSTEMATIC_RANKINGS.md` for the front-
  loaded grant flag.

---

# Case B: CSGP (CoStar Group) — Governance as Catalyst

## Situation

CoStar Group ($13.9B mcap, $33.93 spot) is the dominant commercial-
real-estate data platform. The stock is 65% off its 52-week high
following sustained capex on a land-purchase program for a
residential-portal expansion.

The board's PSU plan codes an EBITDA dollar hurdle, a 60% PSU%LTI,
a **10x CEO ownership multiple**, and a series of plan evolutions
documented as "responsive to shareholders." The most recent say-on-
pay vote received **45.0% support** — a passing vote, barely.

The company's verified share count has fallen 3.6% over the trailing
193 days (buyback EXECUTING). A special-committee disclosure
appeared in the prior quarter, with strategic advisors named.

## Exhibit B-1 — Convergence

| Screen | Position |
|---|---|
| `grand_unified` | top 25 |
| `psu_asymmetric_full` | top 50 |
| `psu_gov_asymmetry` | top 20 |
| `unified_composite` | top 30 |
| **5 archetype wins** | A2 EBITDA-$ hurdle, C1 10x CEO ownership, C6 shareholder-responsive, D1 feedback evolution, F1 lowest passing SOP |

## Exhibit B-2 — Governance plan

```
psu_core            45.0
gov_score           14.0
psu_pct_lti         60%
cond_cats           [ebitda_dollar_target]
per_share_metrics   [eps, tsr]
say_on_pay_pct      45.0
gov_reasons         [10x ownership multiple, anti-hedge/pledge,
                     responsive to shareholders, post-vest holding]
verified_buyback    EXECUTING -3.6% / 188d
```

## Discussion Questions

1. A 45% say-on-pay vote *passes* (the threshold is 50%). Why is
   it nonetheless an active catalyst rather than a benign passing
   vote?

2. The CEO is required to hold 10x base salary in company stock.
   How does this change his/her decision function on the strategic-
   alternatives committee?

3. The buyback is verified EXECUTING at –3.6% in six months.
   Compared to the "authorized but not executed" buybacks in our
   `buyback_verify.json`, what does verified shrinkage tell you
   about discount-rate alignment?

4. CSGP is a $13.9B mid/large-cap. The Bastian/Dalius/Walker
   playbook explicitly says *avoid over-analysed large-caps*. Why
   would we still include CSGP as a convergent name?

## Teaching Note

**B1. Why 45% is a catalyst.** ISS and Glass Lewis will recommend
"against" for any director up for re-election at a company with two
consecutive SOP votes below 70%. A 45% vote is the proxy advisors
saying *the board's pay program is materially out of line with
shareholder expectations*. The board has three responses available:
restructure the plan (creates new disclosure and tangible change),
ignore (faces director-removal risk at next annual), or sell the
company (eliminates the problem). Each is a catalyst path; none is
benign passing.

**B2. The 10x ownership multiple as decision shaper.** A CEO with
10x base salary in stock has personal liquidity tied to per-share
value, not headline EBITDA. The CEO's decision function when
evaluating strategic alternatives is therefore *closer to a
shareholder's* than a typical CEO's. The probability of accepting a
take-private bid that is fair to the common shareholder is
materially higher than at a typical company. This is the *Greenblatt
Sears stub* logic generalised: when management compensation is
mechanically tied to per-share value, agency cost falls.

**B3. Verified vs authorised buyback.** The market routinely
mis-prices "authorised" buybacks because they are *announcements*,
not commitments. `buyback_verify.json` measures whether the share
count actually fell. CSGP's –3.6% in 193 days is *realised* —
the company has actually retired shares, not announced an
intention to do so. Realised shrinkage of 3.6% in six months at a
50% PSU%LTI plan tied to EPS means every dollar repurchased at
current prices is *3.6x accretive* to PSU value. The board has
financial alignment to continue.

**B4. Why a large-cap belongs in convergent.** The Bastian playbook
warns against the over-analysed *index-favoured* large-cap, where
information arbitrage is unlikely. CSGP is the inverse: a large-
cap that has been *de-rated* off a temporary capex cycle, with
multiple independent structural signals (PSU EBITDA-$ hurdle, 10x
ownership, SOP dissent, verified buyback) aligning. The
information arbitrage is not "the market doesn't know about CoStar"
but "the market is discounting CoStar's capex as permanent." The
PSU plan and buyback both say the board does not agree.

## What We Did

- Convergent rank #2 (4 screens, **5 archetypes — the highest
  archetype count of any name in the universe**).
- Surfaced as A2, C1, C6, D1, and F1 winner on `PSU_ARCHETYPES.md`.
- Top-of-list in `SYSTEMATIC_RANKINGS.md` "verified buyback
  compounders" bucket.

---

# Case C: Lands' End (LE) — The Caution-Flagged Convergent

## Situation

Lands' End ($381M mcap, $12.41 spot) is a Sears Holdings spinoff
operating direct-to-consumer apparel. Long-tail post-Sears history.
86% PSU%LTI (very heavy), 5+ per-share metric stack (deepest in the
universe for retail), 12 step-tranches in the stock-price ladder
(longest ladder identified), gov score 15.

There is a live take-private bid pending: LE is the subject of a
14D-9 filing dated within 80 days.

The same proxy text contains a *retirement carveout*: an executive
who retires while a PSU is mid-cycle vests at target regardless of
goal achievement.

## Exhibit C-1 — Convergence and flags

| Screen | Rank |
|---|---|
| `grand_unified` | top 5 |
| `bastian_forcing` | #16 |
| `psu_gov_asymmetry` | top 30 |
| `unified_composite` | top 50 |
| Archetype wins | A15 longest tranche ladder, B2 70–79% PSU LTI, B5 ROIC metric, **E6 retirement carveout (red-flag winner)** |
| Caution flags | retirement carveout |

## Discussion Questions

1. LE wins four archetypes — but one of them is the *red-flag
   E6 carveout* archetype. How do you weigh a structural strength
   (heavy PSU + deep metric stack) against the carveout?

2. The live 14D-9 means a third-party bid is in flight. How does
   the carveout interact with that bid? Specifically, what happens
   to PSU value if the deal closes?

3. The ladder has 12 tranches — the longest in the universe. What
   does this say about the board's view of the equity's potential
   upside?

4. What position size adjustment, if any, does the carveout flag
   warrant?

## Teaching Note

**C1. Weighing strength against carveout.** The PSU stack at 86%
LTI on five per-share metrics with a 12-tranche price ladder is
*the most aligned LTI plan in the universe for a retail name*.
The board has structurally bet its compensation on long-term per-
share value. The retirement carveout, however, means an executive
in the final two years of their career can ride a high-tranche
PSU to retirement and vest at target regardless of business
performance. This is *not* invalidating — most senior LE executives
are mid-career. But it caps the asymmetry of compensation alignment.

**C2. Carveout interaction with the live bid.** A take-private bid
that triggers single-trigger CIC acceleration would pay the PSU at
target *regardless* of where the stock price is on the tranche
ladder. The carveout is essentially redundant with the CIC if the
deal closes. The danger is asymmetric: if the deal *breaks*, the
carveout still lets the executives walk away on retirement at
target. From the common shareholder's perspective, the cleanest
outcome is deal-close at a number above the current spot; the
worst is deal-break with executive turnover.

**C3. 12 tranches as upside signal.** A ladder going from $1 to
$8 in 12 steps is the board saying *we believe the equity has
multiple ladders of upside ahead of us*. Boards don't pay
themselves with 12-tranche ladders for static businesses. The
ladder structure encodes the board's view of how big the gap is
between current value and intrinsic value: very big.

**C4. Position sizing under flag.** The asymmetric structure
remains valid. The flag suggests *do not concentrate*. LE belongs
in a portfolio of similarly-structured names rather than as a
1-of-3 concentrated position. The basket approach — LE, NUS, ADT,
KMPR — diversifies away the single-name flag risk while preserving
the heavy-PSU exposure.

## What We Did

- Convergent rank #3 (4 screens / 4 archetypes).
- Flagged in `SYSTEMATIC_RANKINGS.md` section 5 as carveout caution.
- Listed in "live tender / 13E-3 mechanics" use-case bucket.

---

# Case D: ODTX (Odonate Therapeutics) — The Insider-Information Trifecta

## Situation

Odonate Therapeutics ($787M mcap, $16.69 spot) is a clinical-stage
oncology company. Over the trailing 30 days, seven insiders
(across CFO, director, and other-officer roles) bought stock for
a total of **$75.3M — equal to 9.57% of the entire market cap**.

The company has no PSU program disclosed in the latest DEF 14A
(it is a clinical-stage company with stock-option-only
compensation). It has no buyback authorisation. No tender. No
live activism on file.

The single signal is the insider buying.

## Exhibit D-1 — The cluster

```
Form 4 P-buy stack (last 30 days):
  Buyers (distinct):       7
  Role mix:                cfo, director, other-officer
  Total $ purchased:       $75.3M
  As % of mcap:            9.57%
  Avg per buyer:           $10,760K
  Days since latest:       33
```

## Exhibit D-2 — What's absent

| Layer | Reading |
|---|---|
| PSU forensics | No PSU program |
| Governance | gov_score not scored (clinical-stage minimal proxy) |
| Buyback verify | No authorisation |
| Tender / 13E-3 | None |
| 10b5-1 | No structured disclosure |

## Discussion Questions

1. Seven distinct insiders buying simultaneously to the tune of
   9.57% of mcap — what is the *least pessimistic* explanation
   that doesn't assume material non-public information?

2. ODTX wins three archetypes (B6 largest dollar cluster, B7
   highest % of mcap, B8 first-in-a-while cluster) but is *not* a
   convergent name in our framework. Why?

3. What would convert ODTX from a "single-signal trifecta winner"
   to a convergent name?

4. If the insider buying is the only signal, how do you size?
   Apply the Dalius "what's the downside" test.

## Teaching Note

**D1. Least pessimistic non-MNPI explanation.** Seven board
members coordinating a 9.57%-of-mcap purchase implies *agreement*
on a view. The view does not require MNPI to be informationally
asymmetric. It can be: (a) the cash on the balance sheet is
sufficient to fund another two years of trial work without dilution
and the market is discounting dilution risk; (b) a strategic process
is being run that produces a base case at a number well above
spot; (c) the clinical readout in the next 6 months has a high-
probability positive outcome the board is comfortable underwriting
publicly via personal purchase. None require Reg FD violation.

**D2. Why not convergent.** Our framework requires *3 of 8
screens* AND *archetype winner*. ODTX wins 3 archetypes but
appears on only 1 screen (`informational_buys`). The other screens
do not surface it because they require PSU forensics or governance
scoring that the company simply doesn't have to score. The
framework correctly identifies ODTX as a *single-leg high-
intensity signal* rather than a multi-leg convergence. Both are
real. They are sized differently.

**D3. What makes it convergent.** Either: (a) a PSU plan
emerging in the next proxy that codes a clinical milestone trigger
(`fda_phase_milestone` cond_cat), which would surface it on
`psu_asymmetric_full`; (b) a buyback authorisation, which would
add a verified-shrinkage path; or (c) an activist 13D filing,
which would add a forcing-function leg. Any one of these would
move it from single-leg to convergent.

**D4. Sizing under single signal.** The Dalius test: *what's the
downside?* For a clinical-stage company the downside is binary
trial failure → equity to near-zero. The insider cluster does not
hedge that. Sizing therefore must be *small enough to survive the
binary*. Concentration is wrong; participation is fine. The
framework treats ODTX as a *Cohen-Malloy stack* name, not a
concentrated-position name.

## What We Did

- Surfaced as winner of three archetypes (B6, B7, B8) on
  `ASYMMETRIC_BY_ARCHETYPE.md`.
- Top of `informational_buys.csv` 5-condition scorer (firing 3 of 5).
- Listed in `SYSTEMATIC_RANKINGS.md` "Cohen-Malloy stack" use-case
  bucket — not in the concentrated-position bucket.

---

# Case E: EXFY / BBGI — The Forcing-Function Stub

## Situation

Two situations, one archetype.

**EXFY (Expensify):** $121M mcap, $1.25 spot, P/B 0.87. Live
issuer self-tender amended today. The company is bidding for its
own equity at a defined fixed price.

**BBGI (Beasley Broadcast):** A controlled radio company that
underwent a 2025 exchange offer reducing second-lien notes to ~50%
of face. The new PIK notes have a *springing maturity* if asset
sales sufficient to repay them aren't entered by September 2027,
and an *equity-conversion feature* allowing creditors to convert
into up to 95% of common stock.

EXFY surfaces on our tender_scan. BBGI **does not** appear on our
current scanners because our scan stack doesn't yet parse 8-K
exchange-offer language.

## Exhibit E-1 — The two situations side by side

| Dimension | EXFY | BBGI |
|---|---|---|
| Forcing mechanism | Live self-tender (issuer bid) | Exchange-offer covenant |
| Catalyst hardness (0–5) | 5 (filed and live) | 4 (covenant date set) |
| Common preservation | Issuer-paid: maximal | Up to 95% creditor dilution at risk |
| Surfaced by our framework? | Yes | No — gap |
| Bastian forcing-function score | 30 | Would be ~50+ if parsed |

## Exhibit E-2 — The gap in our scanners

```
What our recent_8k_restructuring_range queries:
  "exchange offer" "senior secured"        ✓
  "PIK notes"                              ✓
  "springing maturity"                     ✓
  "strategic alternatives committee"       ✓
  "transaction support agreement"          ✓

What we don't yet do:
  Parse the cover-page numbers from a returned 8-K
  Compute: debt reduced / market cap
  Compute: equity conversion percentage
  Compute: forced-deadline value
```

## Discussion Questions

1. Why is BBGI's exchange-offer covenant a "harder" catalyst than
   a generic restructuring announcement, despite both appearing in
   8-K?

2. What is the structural risk to common equity from the 95%
   equity-conversion feature?

3. EXFY surfaces on our framework. What single quantitative
   refinement would let us distinguish a *clean* issuer self-tender
   (creates equity value) from a *dilutive* one (e.g., partial
   tender at premium funded by new equity raise)?

4. Reading the playbook's Bastian section, what is the equity
   torque formula? Compute it (qualitatively) for BBGI.

## Teaching Note

**E1. Why a covenant is harder than an announcement.** A
restructuring announcement is a *signal of intent*. A covenant
with a dated springing maturity and a defined equity-conversion
fallback is a *committed mechanism*. The party with covenant
optionality (here, the creditors) has economic incentive to act if
the covenant springs. Boards announce strategic alternatives all
the time; covenants force outcomes.

**E2. 95% equity conversion as torque and risk.** The asymmetry
is real but cuts both ways. If asset sales repay the notes, the
equity-conversion never fires and the common keeps its full
optionality. If asset sales fail, the conversion fires and
dilutes existing common to 5% of float — near-elimination.
Position sizing must reflect *both* outcomes. The risk is the
upside is only ~3x while the downside is ~95%.

**E3. Distinguishing clean from dilutive self-tender.** The
single number that disambiguates is the *concurrent equity raise*:
does the SC TO-I or 8-K disclose a planned ATM offering, rights
offering, or registration-statement amendment for new shares? If
no concurrent raise, the tender is funded from cash flow — clean.
If concurrent, the tender is a *recycling* — bullish in price but
not in equity value. The refinement is: parse SC TO-I for cross-
references to S-3 / S-1 / 424 effective filings in the prior 30
days.

**E4. Bastian equity torque for BBGI.**
```
Equity torque
  = (debt principal reduced)
  + (asset sale proceeds expected)
  + (maturity extension value)
  + (forced-control covenant value)
  - (dilution / creditor equity-conversion risk)
divided by
  pre-event market cap

For BBGI (approximate):
  debt reduced     ~$100M
  expected sales   $50–150M (range)
  market cap       ~$10M pre-event

  Torque ratio    ~15–25x pre-event mcap if successful
  Dilution risk   up to 95% if not
```

The math says BBGI is the highest-asymmetry forcing-function stub
in the playbook. Our framework cannot rank it because we don't
parse the 8-K covenant numbers — this is the documented gap.

## What We Did

- EXFY ranked on `bastian_forcing.csv` (#13), surfaced as B1 winner
  on `ASYMMETRIC_BY_ARCHETYPE.md` and in `SYSTEMATIC_RANKINGS.md`
  "live tender" use-case bucket.
- BBGI documented as **the gap** in `TRANSFORMATION_VS_BASTIAN.md`
  and `bastian_forcing.csv` reasoning: our 8-K full-text scanner
  catches the keywords but does not parse the covenant numerics.
  Listed as the next leg to build.

---

# Module I: The Universe and Its Layers

## Setup

The framework operates on a 6,164-name US-listed universe drawn
from `cancel_10b5_1.json`. This is the authoritative set —
every NYSE / Nasdaq / AMEX / CBOE common ticker that files 10b5-1
disclosures.

## The seven data layers

```
1. PSU forensics       proxy_scan*.json        4,410 names (72%)
2. Governance          (same; gov_score)       4,410 names (72%)
3. yfinance overlay    yfinance_quick.json     2,132 names (35%)
4. Buyback verify      buyback_verify.json     ~800 names (13%)
5. Tender / 13E-3      tender_scan.json        6,164 names (100%)
6. 10b5-1 directional  cancel_10b5_1.json      6,164 names (100%)
7. Form 4 P-buys       form4_buys.json         346 names (5.6%)
   + Form 144           form144_scan.json       ~1,995 names (32%)
```

Plus EDGAR-stream scanners:
- Form 10/10-12B spinoff registrations
- 8-K restructuring keyword feed (Bastian archetype)
- SC 13D / 13D-A activist filings
- Form 15 / Form 25 going-dark and delisting
- 8-K Tax Benefits Preservation Rights Plan (NOL shells)

## Coverage tiers

| Tier | Definition | Names | Use |
|---|---|--:|---|
| A | 6+ of 7 layers | 0 | Maximum confidence |
| B | 4–5 of 7 layers | 1,090 | Reliable for concentration |
| C | <4 of 7 layers | 5,079 | Requires gap-fill before concentration |

The fact that **zero names are Tier A** means there is no
universe-wide ticker for which every layer of evidence is complete.
This is the framework's honest acknowledgement of limits.

## Why each layer matters

```
PSU forensics       What is the board paid to achieve?
                    Forward dollar hurdles = knowable catalysts.

Governance          How constrained is the board?
                    Clawback, anti-hedge, vesting, ownership multiple.

Valuation           What is the floor?
                    P/B < 1 + drawdown > 60% = asymmetric setup.

Buyback verify      Does the supply curve actually shrink?
                    EXECUTING > authorisation; verified > announced.

Tender / 13E-3      Is there a mechanical bid?
                    Floor is the tender price.

10b5-1 directional  Are insiders unwinding scheduled selling?
                    Term_sell = bullish; adopt_sell = bearish.

Form 4 P-buys       Are insiders independently risking own money?
                    Cohen-Malloy: cluster + role + size = informational.

Form 144            Are insiders signalling proposed sales?
                    Negative weight; bearish-signal screen.
```

## The convergence test (formalised)

A name is *convergent* if and only if:
1. It appears in the top-N of at least 3 independent screens, AND
2. It wins at least one PSU/governance archetype.

This is a deliberately tight definition. It produces 12–13 names
across a 6,164-name universe. The intent is to *concentrate
diligence* on the few names where multiple independent lines of
evidence agree.

---

# Module II: The Convergence Test

## Why convergence

A single screen produces a ranking. A single ranking can be wrong
for any of: model bias, data sparsity (the Tier-C problem),
overfitting to a particular signal, regime change. The convergence
test corrects this by *requiring agreement across independent
evidence*.

Independence is the key word. Our eight rankers are not eight
flavors of the same calculation. They draw on:

```
PSU forensics             Plan-text parsing
Governance composite      Plan-evolution time series
Insider cluster           Form 4 transaction patterns
Valuation overlay         Market data
Tender mechanics          SC TO / 14D-9 parsing
Verified buyback          Time-series share-count regression
EDGAR keyword             8-K full-text search
Coverage-normalised rank  Multi-layer composite
```

The probability that all eight independently surface the same name
by chance is approximately 1 in (top-N / universe)^k, where k is
the number of independent rankers that agree. For HFFG appearing
on 6 of 8 with top-N=150, the chance probability is roughly
(150/6164)^6 = 2.4×10⁻¹⁰. Convergence is structurally informative,
not statistically inevitable.

## Robustness checks

Two robustness checks have been performed:

**Robustness check 1 (gap-fill expansion).** After enriching 247
new tickers with yfinance valuation overlay, the convergent list
was unchanged. This rules out the hypothesis that the convergent
list is an artifact of *which* tickers got data.

**Robustness check 2 (governance bugfix).** After expanding
governance coverage from 394 to 1,090 names in Tier B (a 2.8x
increase), the convergent list lost one name (EXFY) and otherwise
held. This rules out the hypothesis that the convergent list is
an artifact of governance-data sparsity.

Both checks suggest the convergent list is structurally informative,
not data-dependent.

## What convergence does not tell you

It does not tell you the *direction* — a convergent name with
bearish red-flag wins is convergent *toward caution*. HAIN is a
four-red-flag convergent (discretionary hurdle, front-loaded grant,
retirement carveout, single-trigger CIC). Convergence without
direction is a flag for *attention*, not for *action*.

This is why Module III (caution flag taxonomy) is necessary.

---

# Module III: Caution-Flag Taxonomy

## The eight flags

```
1. Front-loaded grant
   Executive paid upfront for future achievement.
   Shifts risk to shareholder. Real but not invalidating.

2. Discretionary hurdle / committee discretion
   Hurdle adjustable at committee's discretion.
   Disconnects pay from outcome. Devalues the PSU.

3. Repricing language
   Plan allows option / PSU repricing on stock decline.
   Removes downside discipline from grant. Devalues the PSU.

4. Single-trigger CIC
   Change-in-control accelerates PSU at target.
   Caps incentive to negotiate; favors any deal over best deal.

5. Retirement carveout
   Retiring executive vests PSU at target regardless of goal.
   Mid-cycle retirement creates pay-without-performance path.

6. Aggregate-only metrics (no per-share)
   Plan metrics are absolute, not per-share.
   Allows buyback dilution or issuance without penalty.

7. PSU with TSR only (no operating metric)
   Vesting tied purely to relative TSR.
   No accountability for absolute value creation.

8. Front-loaded grant + retirement carveout combo
   Pay-without-performance double whammy. Highest concern.
```

## Reading the flags as catalysts (counter-intuitive)

Some flags can be catalysts rather than red flags. A *repricing
language* clause becomes activated when the stock falls sharply —
which means an existing equity position has a built-in re-rate
incentive for management to reset hurdles in their favor *and yours*.
This is the FISV / Fiserv case: payments giant with a re-rate de-
risking the existing PSU stack.

## Per-name caution mapping

The convergent 12 with their flags:

```
HFFG     front-loaded grant                          (1 flag)
CSGP     (clean — no flags surface)                  (0 flags)
LE       retirement carveout                          (1 flag)
NUS      retirement carveout                          (1 flag)
GO       discretionary hurdle, single-trigger CIC     (2 flags)
ADT      retirement carveout                          (1 flag)
KMPR     repricing language, retirement carveout      (2 flags)
MAT      discretionary, repricing, carveout           (3 flags)
RNR      (clean — no flags surface)                   (0 flags)
GPRO     discretionary, retirement carveout           (2 flags)
LMT      retirement carveout                          (1 flag)
CDE      single-trigger CIC                           (1 flag)
```

CSGP and RNR are the only "clean convergent" names — convergent
without red-flag wins. They are the highest-quality structural
holdings in the universe.

---

# Module IV: Deployment by Mandate

## Mapping use cases to names

The framework produces, in `SYSTEMATIC_RANKINGS.md` section 6, a
deployment sheet. The teaching version of that sheet:

```
"Concentrated 1–3 names with maximum
 cross-signal conviction"
                       → HFFG, CSGP, RNR
                       (clean convergent + multi-archetype)

"Microcap forcing-function basket"
                       → BEEP, LGL, NUS, DXLG, WW, OSUR
                       (P/B < 0.5 + PSU trigger + tender role)

"Mungerian forward-dollar PSU"
                       → HFFG (revenue), MAT (EBITDA+FCF),
                          LMT (FCF+backlog), THRY (triple), EHTH
                       (named dollar hurdle = knowable catalyst)

"Verified buyback compounders"
                       → CSGP, KMPR, ADT, PAYC, GRND
                       (EXECUTING status with PSU alignment)

"Live tender / event-driven"
                       → EXFY, GPUS, GETY (self-tender);
                          LE, DXLG (target); CWAN (13E-3)
                       (mechanical bid as floor)

"Special-situations debt-haircut"
                       → WW (post-Ch11), LGL (post-Ch11),
                          QVCGQ, ENHA, FONR
                       (capital-structure forcing function)

"Cohen-Malloy informational basket"
                       → NSP, ODTX, FONR, MOBI, RGR
                       (insider-cluster as sole signal)

"Activist / 8-K stress"
                       → RPAY (triple), CCO, SATS
                       (13D + restructuring + boundary overlap)

"Russell-recon forced flow"
                       → EBS, BYND, CMCO, BLCO, MUR
                       (within ±20% of R2000 cutoff)

"NOL shell / §382 tax-asset"
                       → WOLF, CEG, NOTV, NINE, USGO,
                          CMLSQ, TSEOF
                       (Tax Benefits Preservation Rights Plan)
```

## Sizing principles

```
Concentrated (≥5% position):
  Clean convergent + ≥4 screens + 0 red flags
  → HFFG (front-loaded grant accepted as tolerable),
     CSGP, RNR

Material (2–5%):
  Convergent with 1 flag, or 4+ archetypes
  → LE, NUS, ADT, KMPR, MAT

Participation (0.5–2%):
  Single-archetype winner, single-screen surface
  → ODTX, EXFY, individual Bastian-forcing names

Basket (each at <1%):
  Sub-archetype baskets — Cohen-Malloy stack, R2000
  boundary, NOL shells, microcap forcing-function
```

## What to monitor

```
Weekly:  Russell boundary list (mcap shifts)
         New 13D / 8-K restructuring keyword hits
         tender_scan refresh
Quarterly: DEF 14A re-scan for plan evolutions
           buyback_verify gap-fill expansion
Annually: PSU plan amendments in proxy
```

---

# Appendix A: Signal-layer methodology

Refer to the documented modules:

```
proxy_scan.py + psu_scoring.py    PSU forensics + gov score
psu_step_change.py                Plan-evolution + price ladders
psu_forensics.py                  Plan-text parsing
forensic_asymmetry.py             Forward vs retrospective direction
form4_buys.py                     Form 4 P-buy ingestion
informational_buys.py             Cohen-Malloy 5-condition scorer
cancel_10b5_1.py                  10b5-1 signed-score scorer
form144_scan.py                   Form 144 proposed-sale screen
tender_scan.py + tender_roles.py  SC TO / 14D-9 / 13E-3 ingestion
buyback_verify.py                 Split-adjusted share-count delta
recent.py                         EDGAR full-text scanners
recent_13d_sweep.py               Schedule 13D activist sweep
grand_unified_ranker.py           Coverage-normalised universe rank
consensus_meta_ranker.py          Cross-ranker consensus joiner
systematic_rankings.py            Final rollup
```

# Appendix B: Per-pattern leaderboards (full)

See `SYSTEMATIC_RANKINGS.md` section 2 for the complete top-10 per
catalyst type. 18 patterns covered.

# Appendix C: Glossary

```
Asymmetric        Reward >> risk, with the risk well-bounded.
Convergent        Surfaced on >=3 independent screens AND
                  archetype winner.
Cond_cat          Coded forward-conditional vesting category
                  (revenue_dollar_target, spin_separation, etc.)
Forcing function  A creditor / regulatory / tender mechanism that
                  obliges value-transferring action.
Forward dollar    PSU hurdle expressed as a dollar number, not a
                  percentile. Knowable catalyst.
hurdle
PSU%LTI           PSUs as a percentage of long-term incentive value.
Per-share         PSU metric expressed per share (EPS, FCF/share,
metric            ROIC) rather than absolute (revenue, EBITDA).
                  Penalises issuance, rewards buyback.
Tier A / B / C    Data-coverage classification: A=6+ layers,
                  B=4–5, C=<4. Per ticker.
TSR               Total shareholder return — typically used as
                  the only metric in lower-quality PSU plans.
Verified buyback  Share count actually fell over trailing window
                  (split-adjusted). Distinguished from authorised.
```

---

# Historical Case Library

Single-paragraph teaching notes from verified historical event-driven
trades. Each maps to the Cyclepapa scoring leg that would have
surfaced the setup *ex ante*. Outcome claims carry URLs; where the
number could not be independently verified, the note says so.

## H1. MAR / HMT — Marriott / Host Marriott (1993) — Spinoff "orphan equity"

Stephen Bollenbach engineered the Marriott Corp. split in October 1993,
loading the parent's hotel debt onto Host Marriott (HMT) while keeping
the cash-flow-rich management contracts in Marriott International (MAR).
**Detectable signal:** Form 10 disclosed an extreme post-spin debt/EBITDA
on the SpinCo, generating the textbook "orphan equity" — index funds and
investment-grade-only mandates were forced sellers; the parent's
management explicitly took the cheap side. **Cyclepapa leg that would
fire:** the spinoff scanner (Form 10 + insider Form 4 cluster on RemainCo
*and* SpinCo) plus the "forced-seller" overlay (debt/EBITDA above
high-yield index thresholds). **Outcome:** Greenblatt documented an
HMT triple over ~24 months — see *You Can Be a Stock Market Genius*
(Joel Greenblatt, 1997), the canonical write-up. **Teaching:** SpinCo
ugliness *is* the signal — board chose ugliness on purpose.

## H2. FACT — Facet Biotech (2009-2010) — 13D + post-spin distressed

Facet Biotech was spun out of PDL BioPharma in December 2008 with cash
on the balance sheet exceeding the post-spin market cap on day one — a
classic neglected-spin floor. Baupost (Klarman) filed 13D on April 8,
2009, amended to **17.8% ownership** April 27, 2009. **Detectable signal:**
13D + cash-above-market-cap on a forced-seller spin. **Cyclepapa leg:**
13D sweep (`recent_13d_sweep.py`) cross-referenced with the spinoff
scanner — exactly our "convergent on two independent rankers" pattern.
**Outcome:** Abbott tender at $27/share announced March 9, 2010;
Baupost exited Q2 2010 at roughly **+209% from 13D filing**.
([SEC 13D/A](https://www.sec.gov/Archives/edgar/data/0001441848/000106176809000115/fact13damend1.txt),
[Market Folly](https://www.marketfolly.com/2009/04/seth-klarmans-baupost-group-starts.html))
**Teaching:** cash-above-market-cap is a *hard floor* — the leg of
the asymmetric recipe Cyclepapa codes as the P/B overlay equivalent.

## H3. GGP — General Growth Properties (2008-2010) — Ackman Ch 11 equity preserved

Pershing Square filed 13D on November 24, 2008 disclosing ~25M shares plus
total-return swaps with reference prices $0.49–$1.58, total economic
exposure ~19.9%. GGP filed Ch 11 April 2009, *emerged with equity intact*
November 2010, with shareholders also receiving the Howard Hughes
spinoff. **Detectable signal:** 13D + creditor analysis showing real
estate values > debt at any defensible cap rate (the bankruptcy was
liquidity-driven, not solvency-driven). **Cyclepapa leg:** 13D sweep
+ Bastian forcing-function archetype (capital-structure stress where
the *asset* exceeds the *claim*). **Outcome:** Ackman publicly stated
~$60M turned into ~$1.6B.
([SEC 13D](https://www.sec.gov/Archives/edgar/data/0000895648/000095012308016206/y00645sc13d.htm),
[CRE Analyst](https://www.creanalyst.com/insights/bill-ackmans-1.6-billion-ggp-win-a-masterclass-in-bankruptcy-investing))
**Teaching:** the BBGI archetype generalized — when the covenant fires
but the assets exceed the claims, equity survives.

## H4. PYPL — PayPal spin from eBay (July 2015) — Icahn-prompted separation

Carl Icahn filed 13D on eBay in January 2014 advocating separation. eBay
agreed in September 2014; PayPal spun July 17, 2015 at ~$38 per share.
**Detectable signal:** 13D advocating separation + Form 10 registration
of the higher-growth payments unit. **Cyclepapa leg:** the spinoff
scanner with the "SpinCo is the cleaner business" overlay (PSU plan
of the SpinCo was payments-growth indexed; RemainCo was retail-margin
indexed). **Outcome:** PYPL roughly doubled from spin to mid-2018,
while EBAY underperformed SPY over the same window — the spin worked,
the RemainCo did not. **Outcome verified at high level**; precise
trade-window IRRs depend on entry timing. **Teaching:** when an activist
demands separation and management *agrees*, the SpinCo is usually the
gem and the parent's compensation plan has already been reindexed to
it — the PSU forensic leg can confirm before the spin closes.

## H5. MTCH — Match Group from IAC (June-July 2020)

IAC completed full separation of Match Group on June 30, 2020, the
latest in Barry Diller's serial-spinoff machine (Expedia 2005, HSN/QVC
2008, Vimeo 2021, etc.). **Detectable signal:** Form 10 + IAC's
documented track record of spinoff-as-value-recognition. **Cyclepapa leg:**
spinoff scanner + the "Liberty/IAC archetype" — any time the parent is
a known serial spinner, the SpinCo deserves an automatic look. **Outcome:**
MTCH rallied to an all-time closing high of $169.43 on Oct 21, 2021, then
collapsed; calendar-year total returns were **–12.5% (2021) and –68.6%
(2022)** vs SPY +28.7% / –18.1%
([Match 8-K June 2020](https://www.sec.gov/Archives/edgar/data/0001575189/000157518920000086/mtch8-k20200625ex991.htm)).
The IAC-spin investor who exited within 18 months captured material alpha;
the indefinite holder did not. **Teaching:** the spinoff edge is *temporal*
— harvest the re-rate window, then re-evaluate.

## H6. WBD — Warner Bros Discovery (April 2022) — the spin that didn't work

AT&T spun WarnerMedia and merged with Discovery in a Reverse Morris
Trust transaction April 8, 2022. **Detectable signal:** the structure
itself (Reverse Morris Trust + Malone involvement) was a textbook
Greenblatt-style setup. **Cyclepapa leg:** spinoff scanner + the
"forced seller" overlay (AT&T income holders dumped WBD on receipt).
**Outcome:** WBD opened ~$24, fell to $18.15 by April 29, 2022 (–27.8%
in three weeks), and finished 2022 **~–60% vs SPY –18.1%**
([Motley Fool](https://www.fool.com/investing/2022/11/18/warner-bros-discovery-is-down-nearly-60-this-year/)).
The thesis failed because
the underlying media business was structurally declining; the spin
mechanics did not rescue a bad business. **Teaching (counter-case):**
the spin scanner surfaces both winners and losers. Spin + forced-seller
flow is necessary but not sufficient — the SpinCo's PSU plan must code
a credible *operating* hurdle, not just a TSR percentile.

## H7. GEHC / GEV / GE — General Electric three-way split (2023-2024)

GE separated GE HealthCare (Jan 4, 2023), then split the remaining
parent into GE Vernova (energy) and GE Aerospace on April 2, 2024.
**Detectable signal:** Larry Culp's multi-year deleveraging + the
explicit announcement of separation timeline gave a ~24-month window
to position. **Cyclepapa leg:** the spinoff scanner + the "remaining
parent" PSU re-indexing (Aerospace's PSU plan was re-coded to backlog
and FCF — Cyclepapa's `revenue_dollar_target` plus `fcf_dollar` cond_cats).
**Outcome:** all three sub-spins outperformed — a rare 3-for-3. GEHC
debuted ~$53.94 (Jan 4, 2023) and reached ~$93.56 by Sept 30, 2024.
GEV opened ~$142.85 on April 2, 2024 and rallied **roughly 5x** through
2025 on the AI/data-center power thesis. GE Aerospace climbed from ~$136
to ~$200 April 2024–April 2025 (**+~50% vs SPY ~+25%**)
([GE press release](https://www.ge.com/news/press-releases/ge-completes-separation-of-ge-healthcare),
[GEV completion](https://www.gevernova.com/news/press-releases/ge-vernova-completes-spin-off-begins-trading-new-york-stock-exchange)). **Teaching:** when one parent spawns three
SpinCos, the PSU plan of each post-spin entity tells you which one the
management team picked — that is the one to overweight.

## H8. NLOP — Net Lease Office Properties (November 2023) — liquidation spin

W.P. Carey spun NLOP November 1, 2023 at 1 share per 15 WPC shares,
explicitly to liquidate the office portfolio. **Detectable signal:**
Form 10 *stated* the liquidation intent. The income-mandated REIT
holders of WPC were forced sellers of a sub-1% allocation. **Cyclepapa leg:**
spinoff scanner with the "stated liquidation" flag — equivalent to a
tender's mechanical bid. **Outcome:** by March 2026 NLOP had sold 41
of 59 properties for ~$813M gross and paid ~**$22.69/share** in cumulative
special distributions against a ~$27 reference, with stock still trading
~$20.
([Seeking Alpha](https://seekingalpha.com/article/4862361-net-lease-office-properties-the-endgame-approaches),
[StockTitan](https://www.stocktitan.net/sec-filings/NLOP/8-k-net-lease-office-properties-reports-material-event-de599a474442.html))
**Teaching:** a stated-liquidation spin is the cleanest version of the
"PSU forward dollar hurdle" — the board has told you the entire equity
will be returned, you just compute the timing.

## H9. CURB — Curbline Properties (October 2024) — fortress-balance-sheet spin

SITE Centers spun Curbline on October 1, 2024 at 2 CURB per 1 SITC,
capitalized with ~$800M cash, $400M undrawn revolver, $100M delayed-draw
term loan, and **zero debt**. **Detectable signal:** Form 10 disclosed
the fortress balance sheet — a unique configuration that retail-REIT
income holders would dump. **Cyclepapa leg:** spinoff scanner + the
"net cash / no debt" overlay (analog of P/B < 1). **Outcome:** opened
$22.60; ~$30.90 mid-June 2026, ~**+22% price return** in ~20 months,
ahead of REIT index.
([Curbline IR](https://ir.curbline.com/news/news-details/2024/Curbline-Properties-Announces-Completion-of-Spin-Off-from-SITE-Centers/default.aspx),
[WallStreetZen](https://www.wallstreetzen.com/stocks/us/nyse/curb))
**Teaching:** net cash at spin is the asymmetric floor; the convenience-
retail strategy was upside optionality on top.

## H10. RGS — Regis Corporation (2024) — debt-haircut equity stub

Regis completed a 20:1 reverse split (Nov 2023), then on June 25, 2024
announced a TCW/MidCap $105M term loan that cut ~$80M of debt and
~$7M annual interest in exchange for 15% dilutive warrants struck at $7.
**Detectable signal:** the 8-K disclosed the structure on the day. **Cyclepapa
leg:** Bastian forcing-function archetype (exchange offer / restructured
debt where the haircut is large vs the equity stub) + EDGAR keyword
scanner. **Outcome:** stock soared **~120% intraday** on the announcement
and traded $27.42 by mid-June 2026 vs sub-$5 pre-refi — a multi-bagger.
([SahmCapital](https://www.sahmcapital.com/news/content/us-market-preview-nvidia-turns-up-23-pre-market-ffie-plunges-27-plans-reverse-stock-split-regis-soars-120-after-debt-refinancing-2024-06-25),
[StockTitan](https://www.stocktitan.net/news/RGS/regis-corporation-announces-new-credit-facility-to-refinance-e9h3dkolkul3.html))
**Teaching:** this is the exact archetype Cyclepapa codes in
`bastian_forcing.csv` — the BBGI gap closed. Parse the cover-page numbers
of the 8-K to compute (debt reduced)/(pre-event mcap); when the ratio
exceeds ~5x, the equity has torque.

## H11. BBGI — Beasley Broadcast Group (2025-2026) — exchange-offer covenant

BBGI exchanged ~$184M of 9.20% second-lien notes for $98.5M of 2027 PIK
notes with **springing maturity** as early as Sept 30, 2027 and a holder
option from Dec 31, 2027 to convert into up to **95% of fully diluted
equity**. **Detectable signal:** the 8-K cover-page numbers (debt reduced,
equity conversion %, springing date). **Cyclepapa leg:** the explicit
BBGI archetype documented in Case E above — *currently a gap*; the
8-K full-text scanner catches the keywords but does not parse covenant
numerics. **Outcome (interim):** post-settlement BBGI traded $19.73-$22.20
in April 2026, well above pre-deal — equity preserved so far, but the
catalyst is future-dated.
([StockTitan 8-K](https://www.stocktitan.net/sec-filings/BBGI/8-k-beasley-broadcast-group-inc-reports-material-event-2098335345ab.html))
**Teaching:** the asymmetry is binary — refinance/sell assets, or
existing equity is mostly wiped. Size accordingly; track the asset-sale
calendar.

## H12. CMG — Ackman + Chipotle (2016-2025) — clean activist win

Pershing Square took a ~$1.2B / **9.9% stake** via 13D in September 2016,
the trade following the e-coli food-safety crisis. **Detectable signal:**
13D filing on a brand with operational damage but intact franchise economics.
**Cyclepapa leg:** 13D sweep + a "post-stress operational reset" overlay
(PSU plan re-coded post-crisis to specifically targeted operating metrics).
**Outcome:** stock more than quadrupled from purchase through 2025;
Pershing fully exited Q4 2025 at reported **~16% IRR vs ~15% S&P** — a win
in absolute, only marginally above benchmark in relative.
([Fool](https://www.fool.com/investing/2026/03/11/billionaire-bill-ackman-dump-fund-stake-chipotle/))
**Teaching:** the 13D-on-damaged-brand setup works when the franchise
economics are intact. Cyclepapa's red-flag taxonomy (Module III) is
the filter — if the damage is to the business model, not just the
quarter, the activist won't rescue it.

## H13. DRI — Starboard + Darden (2014) — full board sweep

Starboard filed 13D October 2013, opposed the Red Lobster sale, then
nominated a full 12-person slate. At the October 10, 2014 annual meeting
**all 12 Starboard nominees** were elected — first full S&P 500 board
replacement in modern proxy history. **Detectable signal:** DFAN14A
solicitation with a full-slate nomination is unmistakably a forcing
vote. **Cyclepapa leg:** 13D sweep + a proxy-contest overlay (DFAN14A
keyword in EDGAR feed). **Outcome:** DRI total return materially
outperformed casual-dining peers and SPY over the subsequent 3 years.
([Bloomberg](https://www.bloomberg.com/news/articles/2014-10-10/starboard-wins-all-12-seats-on-darden-s-board-after-proxy-fight),
[Olshan](https://www.olshanlaw.com/capabilities/matters/Starboard-Victory-Board-Directors-Darden))
**Teaching:** a full-slate nomination is a Tier-1 forcing function —
higher hardness than a single-seat ask. The proxy advisor calendar
becomes the catalyst date.

## H14. TWTR — Twitter / Musk merger arb (2022) — closed-deal payoff

Musk filed 13G April 4, 2022 (9.2%, later refiled 13D); merger agreement
signed April 25, 2022 at $54.20 cash; Musk attempted termination July 8;
Delaware trial set October 17; Musk capitulated October 4; deal closed
October 27, 2022 at $54.20. **Detectable signal:** signed merger agreement
+ deteriorating spread = Cyclepapa's mechanical "tender / 13E-3" leg.
**Outcome:** merger-arb spread reached ~30-40% in July (TWTR ~$32-34),
making the closed payoff one of the highest-return liquid merger-arb
trades of the cycle for holders through the specific-performance window.
([SEC 13D/A](https://www.sec.gov/Archives/edgar/data/1418091/000110465922113051/tm2229215d1_sc13da.htm))
**Teaching:** when the spread blows out, the binary becomes pricing
the specific-performance probability. Delaware Chancery's track record
on this clause is the discount rate — read it directly.

## H15. TGNA — Tegna / Standard General (2023) — regulatory break

Deal announced February 22, 2022 at $24/share cash (~$8.6B EV). FCC Media
Bureau issued a Hearing Designation Order **February 24, 2023** — historically
deal-killing. Merger terminated May 22, 2023; break fee $136M paid.
**Detectable signal:** the FCC HDO itself is the kill signal — once an
ALJ referral happens, historical close rate collapses below 20%.
**Cyclepapa leg:** tender_scan + a "regulatory hardness" overlay that
discounts merger spreads when the FCC, DOJ Antitrust, or CFIUS shows
adverse posture. **Outcome:** TGNA fell sharply on the HDO and again on
termination — short-the-spread trade payoff.
([CNBC](https://www.cnbc.com/2023/05/22/tegna-scraps-8point6-billion-standard-general-deal-after-regulatory-pushback.html))
**Teaching:** Cyclepapa's tender leg cannot just count whether a deal
exists; it must score regulatory hardness. The FCC/DOJ overlay is the
missing module — this is the documented gap for merger-arb coverage,
analogous to BBGI's covenant-numerics gap for forcing-function coverage.

## H16. PSTH — Pershing Square Tontine Holdings (2020-2022) — SPAC liquidation floor

PSTH IPO'd July 2020 at $20/share, raised $4B (largest SPAC ever);
announced a $4B UMG transaction June 2021; SEC pushback forced
withdrawal July 19, 2021; wind-down announced July 11, 2022; redeemed
common at **~$20.05/share** July 25, 2022. Warrants expired worthless.
**Detectable signal:** the SPAC trust value itself — every dollar in
trust at NAV is a hard floor for the common until business-combination
vote. **Cyclepapa leg:** SPAC trust-arb scanner (`spac_trust_arb.csv`)
+ the timing of the deadline. **Outcome:** common holders who bought at
or below trust value collected ~+0.25% with a free option on a successful
deal — exactly the "asymmetric structural recipe" the workbook describes
(hard floor + outsized but uncertain catalyst).
([SEC](https://www.sec.gov/Archives/edgar/data/0001811882/000119312522191391/d305715dex992.htm))
**Teaching:** the SPAC trust floor is the rare *guaranteed* floor in
public equities — better than P/B because it is cash and Treasuries.
The Cyclepapa SPAC leg ranks by (trust NAV - market price) and time
to deadline.

## H17. KLG / K — WK Kellogg / Kellanova split (October 2023) — the parent was the trade

Kellogg split October 2, 2023; shareholders received 1 KLG per 4 K shares.
Classic setup: June 2021 announcement, WK Kellogg Form 10, retention
PSU grants. **Detectable signal:** Form 10 + the "neglected stub" pattern
(KLG, the cereal RemainCo, was the small-cap forced-sale piece). **Cyclepapa
leg:** spinoff scanner. **Outcome (the inversion):** the small-cap "stub"
KLG underperformed for ~21 months, but was then acquired by **Ferrero on
July 10, 2025 at $23.00/share** (~+69% from $13.58 debut). Meanwhile the
parent-side Kellanova was acquired by **Mars on Aug 14, 2024 at $83.50
cash** (~44% premium to 30-day VWAP, $35.9B EV) — the parent paid sooner
and bigger.
([Kellanova-Mars](https://investor.kellanova.com/news-events/news-details/2024/Mars-to-Acquire-Kellanova-de7e19f9d/default.aspx),
[KLG-Ferrero](https://newsroom.wkkellogg.com/2025-07-10-FERRERO-TO-ACQUIRE-WK-KELLOGG-CO))
**Teaching:** the small-cap-stub heuristic doesn't always win. When the
parent's brands are the strategic asset, the parent is the trade — the
Cyclepapa scanner must rank *both* halves and look at acquirer landscape
on each.

## H18. VLTO — Veralto from Danaher (September 2023) — pedigree didn't pay

Danaher completed Veralto separation September 30, 2023; DHR holders
received 1 VLTO per 3 DHR. Textbook Danaher: Sept 2022 announcement,
Form 10-12B, the Fortive (2016) / Envista (2019) pedigree priming
institutional bid, standalone PSUs for VLTO management. **Detectable
signal:** spinoff scanner + the "serial-spinner pedigree" overlay.
**Outcome (the counter-case):** VLTO opened ~$71.50 on Oct 2, 2023 and
reached ~$84 by mid-2026 — roughly **+18% price-only over ~32 months,
materially lagging SPY (~+50%)**.
([Danaher release](https://investors.danaher.com/2023-09-30-Danaher-Corporation-Completes-Separation-of-Veralto-Corporation))
**Teaching:** "Danaher pedigree always wins" is a heuristic, not a
structural signal. Cyclepapa must score the SpinCo's *own* PSU plan
and end-market exposure, not its parent's brand. Spinoffs from
high-quality parents are *not automatically* asymmetric.

## Library reading list

The single best companion text remains Greenblatt's *You Can Be a Stock
Market Genius* (1997) for the spinoff, restructuring, and rights-offering
archetypes. For activist case mechanics, Lazard's annual *Review of
Shareholder Activism* and the Harvard CGI corpgov blog are the data-quality
sources. For SPAC mechanics, the SPAC Research database is authoritative.
For distressed/Ch 11 equity preservation, Moyer's *Distressed Debt
Analysis* remains the structural reference.

## Cross-walks to existing cases

| Historical case | Maps to existing case | Shared leg |
|---|---|---|
| H1 MAR/HMT | (new archetype: spinoff) | Form 10 + insider cluster |
| H2 FACT | Case D ODTX | 13D as single high-intensity leg |
| H3 GGP | Case E BBGI | covenant fires, assets > claims |
| H4 PYPL | Case C LE | activist-driven separation |
| H8 NLOP | Case A HFFG | forward dollar hurdle = liquidation NAV |
| H10 RGS | Case E BBGI | exchange offer / equity stub |
| H11 BBGI | Case E BBGI | (the gap, still open) |
| H14 TWTR | Case E EXFY | mechanical bid as floor |
| H16 PSTH | (new archetype: SPAC trust) | NAV floor |
| H17 KLG/K | Case A HFFG | both halves of a split need ranking |
| H18 VLTO | Case D ODTX (no PSU/no convergence) | pedigree ≠ asymmetry |

---

## End of Workbook

*Companion artifacts: `BEST_OF_UNIVERSE.md`, `SYSTEMATIC_RANKINGS.md`,
`PSU_ARCHETYPES.md`, `ASYMMETRIC_BY_ARCHETYPE.md`,
`TRANSFORMATION_VS_BASTIAN.md`, `ASYMMETRIC_THESIS.md`,
`DURABILITY.md`.*

*Data artifacts: `consensus_ranking.csv`, `grand_unified_ranked.csv`,
`unified_composite.csv`, `informational_buys.csv`,
`bastian_forcing.csv`, `special_situations_unified.csv`,
`psu_asymmetric_full.csv`, `psu_valcreate.csv`,
`psu_gov_asymmetry.csv`.*
