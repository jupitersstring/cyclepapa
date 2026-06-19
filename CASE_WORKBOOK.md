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
