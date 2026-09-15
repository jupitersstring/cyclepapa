# Pre-rerating patterns — the greatest trades per archetype, and how to catch them earlier

*Method: for each archetype family, take the canonical great re-ratings, isolate
what was OBSERVABLE BEFORE the move (the leading signature, not the hindsight
story), check what our engine catches today, and propose the concrete signal
that would catch it earlier. Goal: shift the engine from detecting the STATE
(cheap / hidden value) to detecting the TRANSITION (the state about to be
repriced).*

---

## 0. The universal pre-rerating sequence

Every re-rating runs through the same five stages. The engine is strong at
stage 1 and weak at 2–3 — which is exactly where the asymmetry is, because by
stage 4 the move has begun.

1. **The gap** — cheap / hidden / mispriced. The latent condition. *(engine: strong — this is most archetypes)*
2. **The turn** — the fundamental first-derivative changes sign: first positive print, margin inflection, cycle bottom, capital-return initiation, a catalyst forming. *(engine: partial)*
3. **The disbelief** — the market, analysts, and positioning still price the OLD regime: still cheap, still near lows, estimates stale/negative, low ownership, high short interest. This is the FUEL — the wider the gap between reality-turning and perception-lagging, the bigger the re-rate. *(engine: weak)*
4. **Recognition** — an analyst upgrade, index inclusion, a 52-week-high break, a beat that can't be dismissed. *(engine: `analyst_awakening`, 52w-high archetypes)*
5. **The re-rating** — the multiple expands. *(too late)*

**The single highest-value insight of this study:** the pre-rerating sweet spot
is **stage 2 × stage 3 — the TURN happening WHILE perception still prices
decline.** The engine measures the pieces separately (inflection archetypes;
cheapness; 52w-low; analyst_awakening) but does not COMBINE them into one
leading signal. That combination is proposal P1 below.

---

## 1. Per-archetype-family: greatest trades and their pre-rerating signature

### Deep value / asset floor (oak_*, net-nets, negative-EV, financials_value)
- **Great trades:** Japanese net-nets 2012–15 (Abenomics + governance reform); Korean holdcos post-2022 (Value-Up program); post-GFC European asset plays.
- **Pre-rerating signature:** the discount alone is a *value trap*. The re-rate began when a **CATALYST formed on the dormant discount** — first buyback, first/raised dividend, an activist 13D, or a country-level governance reform. The observable turn: **capital-allocation behaviour changed** (hoarding → returning).
- **Catch today:** the discount (yes); `value_unlock` catalyst (yes, new); country reform (no).
- **Improvement:** **capital-return INITIATION** detection — first buyback after none, dividend initiation, a step-change in payout — is the cleanest pre-rerating tell for a dormant net-net. (P2)

### Quality compounder (lindy_*, buyback_compounder, wolf_compounder, durable_reinvestment)
- **Great trades:** Monster, Copart, Domino's 2010s, Constellation Software, Fastenal.
- **Pre-rerating signature:** the quality was ALREADY visible (high ROIC, long clean record) but the multiple hadn't extrapolated the *durability*. The pre-tell: **ROIC/margin ACCELERATING while the multiple stays compressed** — a coiled spring, quality improving faster than the multiple.
- **Catch today:** `audited_streak_unrerated`, lindy family (state); ROIC acceleration exists as a column.
- **Improvement:** rank the quality sleeve by **(ROIC acceleration) × (multiple compression)** — improving durability the market hasn't paid up for yet. (P3)

### Inflection / turnaround (double_inflect, roic_inflect, gross_margin_lead, gaap_profit_crossover)
- **Great trades:** AMD 2016–20 (gross-margin inflection pre-dated the re-rate); Netflix post-2011; Apple 2003–06; Nvidia 2013.
- **Pre-rerating signature:** the FIRST derivative turned before the market believed it — **gross margin inflected before operating; the first good quarter was dismissed as a fluke.** The reliable pre-tell is not one print but a **STREAK of consecutive improving quarters while the tape/analysts still price decline.**
- **Catch today:** inflection flags, first-positive crossovers, `gross_margin_lead`, streak columns (`rev_yoy_streak_q`, `eps_positive_streak_q`).
- **Improvement:** a **consecutive-improvement streak** requirement (≥2–3 quarters) combined with **disbelief** (still cheap, price still near lows) — the turn the tape hasn't ratified. (P1)

### Cyclical trough (cyclical_trough, double_trough, latent_bath_floor)
- **Great trades:** steel/SD 2020–21; dry-bulk shipping 2020–22; homebuilders 2011–12; oil & gas 2020–22; fertilizer 2020–21.
- **Pre-rerating signature:** the trough LOOKS expensive (near-zero trailing earnings). The turn is a **SUPPLY-side signal that precedes the demand recovery: industry capex collapses, capacity exits, inventories destock to empty.** Cheap capex-starved supply is the leading edge; pricing follows.
- **Catch today:** normalized mid-cycle earnings (state). No supply-side signal.
- **Improvement:** a **capex-collapse / capacity-exit** signal (multi-year capex down hard, capex/D&A << 1 = under-investing, industry-wide) + **inventory destock trough** — the supply tightening that leads the cycle. (P4)

### Capital return / cannibal (cannibal_below_cash/tbook, self_funded_returner, net_cash_returner)
- **Great trades:** AutoZone, NVR, Dillard's 2020–22, Teradyne, Nu Skin at troughs.
- **Pre-rerating signature:** steady buyback compounding; the re-rate came when **per-share metrics inflected and the shrinking share count crossed into scarcity** — often with the buyback ACCELERATING into a depressed price.
- **Catch today:** cannibal family (state), buyback yield.
- **Improvement:** **buyback ACCELERATION into weakness** — buyback yield rising *and* price near lows (management leaning in hardest when cheapest) — the revealed-preference pre-tell. (P2 sibling)

### Forensic hidden value (segment SOTP, stake FV gap, owned real estate, investment remark)
- **Great trades:** Amazon/AWS disclosure; Dillard's owned real estate; LanzaTech SGLT remark; conglomerate break-ups (DuPont, GE, United Tech).
- **Pre-rerating signature:** hidden value existed; the re-rate needed the **catalyst to form** — a segment-reporting change, a held-for-sale classification, a spin filing (Form 10), an activist, a remark. The pre-tell is the **catalyst APPEARING on the filings** (held-for-sale asset, Form 10, 13D, strategic-review language).
- **Catch today:** strong — the whole forensic XR family + `value_unlock` + held-for-sale footprint (all built this session).
- **Improvement:** mostly done; add **first-time segment disclosure** (a company newly breaking out a segment often precedes a re-rate as the market values the parts). (P5)

### Value-unlock / event-driven (value_unlock, spinoff_*, post_reorg, special_situation)
- **Great trades:** post-reorg equities (GGP, Six Flags, XPO from Conway); spin stubs; activist campaigns (Icahn, Elliott, Starboard targets).
- **Pre-rerating signature:** covered by the value-unlock work — the CATALYST language + forensic confirmation + committed stage + activist. The pre-tell is a **committed process with a named advisor / 13D**, freshness-weighted.
- **Catch today:** strong (value_unlock_score with stage/credibility, this session).
- **Improvement:** track **13D → subsequent board seat / settlement** escalation; and **fresh CEO/management change** (new eyes → self-help) as an early self-help pre-tell. (P6)

---

## 2. The synthesis — what all the great pre-rerating signatures share

Boiling the above down, every early entry combined **a fundamental TURN** with
**persistent DISBELIEF**. The engine has both halves as separate signals; the
alpha is in requiring them TOGETHER and ranking by the product:

- **TURN (reality improving):** consecutive improving quarters, first-positive crossovers (NI/FCF/EBITDA/ROCE), gross-margin lead, capital-return initiation/acceleration, a value-unlock catalyst forming, supply-side capex collapse.
- **DISBELIEF (perception lagging):** still cheap (low P/E, EV/EBITDA, P/B), price still near 52w/5y lows (not yet run), analyst estimates stale or falling, low institutional ownership / high short interest, low `momentum_12m`.

A name where **reality has clearly turned but the price, the multiple, the
analysts and the tape all still price the old regime** is the pre-rerating
sweet spot — the maximum gap between what is becoming true and what is priced.

---

## 3. Proposed engine improvements (prioritised)

**P1 — `pre_rerating_score` (the headline).** A universal leading signal:
`TURN_strength × DISBELIEF_strength`, gated to not-melting and real size.
- TURN = weighted count of {≥2-qtr consecutive improvement in rev/EBITDA/margin; a first-positive crossover; gross-margin lead; capital-return initiation; a fresh value-unlock catalyst}.
- DISBELIEF = weighted count of {cheap on ≥1 multiple; price in the bottom third of its 5y range / near 52w low; `momentum_12m ≤ 0`; low institutional ownership or analyst neglect; estimates not yet rising}.
- Rank by the product. This surfaces stage-2×3 names across EVERY archetype — the single biggest lift, built entirely from columns we already have.

**P2 — Capital-return INITIATION / acceleration.** First buyback after none, dividend initiation, or buyback yield stepping up *into a depressed price*. The cleanest pre-tell for dormant deep value and cannibals. Needs a prior-period buyback/dividend series (from the EDGAR cache, like the other cache pulls).

**P3 — Quality coiled spring:** rank the quality sleeve by ROIC/margin ACCELERATION × multiple compression (improving durability not yet paid for). Existing columns.

**P4 — Cyclical supply-side signal:** multi-year capex collapse / capex-below-maintenance (capex/D&A ≪ 1) + inventory destock trough — the supply tightening that leads the demand recovery. Needs capex and D&A series (largely have) + an industry-aggregate view.

**P5 — First-time segment disclosure** (a newly broken-out segment often precedes a parts re-rate). Needs a segment-count / segment-first-appearance delta from the segment harvest.

**P6 — Fresh-management self-help** (new CEO / board change → self-help turn), via 8-K item 5.02 / proxy — a leading pre-tell for the G9 below-peer-margin turnaround. On-demand EFTS/8-K, scoped to cheap under-earners.

**Build order:** P1 first (biggest lift, no new data), then P2 (initiation, one cache pull), then P3 (free), then P4/P5/P6 as data allows.

---

*Companion to XR_RERATING_FORENSIC_RESEARCH.md (the forensic GAAP-vs-economic
gap taxonomy). That doc answers "where is the hidden value"; this one answers
"when is it about to be repriced".*

---

## 4. Deeper nuances — the patterns we still miss (forensic research pass)

Pushing past the state/turn/disbelief frame, here are the subtler signatures
that produced great re-ratings and that the engine does NOT yet capture. Each is
forensically grounded and mostly buildable from data we have or can pull.

### N1. The second-derivative-of-decline discriminator (value-trap crux)
The hardest and most valuable distinction: a cheap-AND-*bottoming* name vs a
cheap-AND-*dying* one. `_not_melting` is a level test; the real tell is the
**rate of change of the rate of change**. A melting ice cube declines with the
decline ACCELERATING and the whole complex deteriorating together (revenue ↓,
margin ↓, share ↓). A bottoming turnaround shows the **decline DECELERATING**
(second derivative positive) even before it turns positive — revenue still down
but *less* down each quarter, margins stabilising, share holding. We measure
first derivatives (deltas, inflection) but not the **deceleration of decline**.
*Build:* a `decline_decelerating` flag = YoY decline this period milder than
last, across rev/margin/FCF — the earliest bottoming tell, and the single best
value-trap filter. Existing quarterly series.

### N2. Earnings-quality inflection (Sloan, in reverse)
Reported earnings lag reality when accruals are high; the pre-rerating tell is
**accruals FALLING / cash-conversion RISING before the P&L shows it** — the
business is converting to cash, a quality upgrade the market hasn't paid for.
We have CFO and NI but never compute the accrual ratio or its trend. *Build:*
`accrual_ratio = (NI − CFO)/assets` and its improvement; low/falling accruals +
rising CFO/NI = the earnings-quality coiled spring. (N-ext-1 from the forensic
doc, still unbuilt.)

### N3. Distress-flag / going-concern REMOVAL
A binary re-rate: the survival question gets answered. A **going-concern
qualification lifted**, a **material-weakness remediated**, a **delinquent
filer becoming timely**, a **refinancing that clears the maturity wall** — each
removes a discrete discount-for-uncertainty. We flag distress (`distress_flag`,
1,365 names) but never its **REMOVAL** — the transition from distressed to
clean is the signal, not the state. *Build:* track `distress_flag` /
going-concern language / late-filing status YoY; a name that WAS flagged and
now is not is the pre-rerating. On-demand EFTS ("no longer substantial doubt",
"regained compliance") + filing-timeliness from submissions.

### N4. Refinancing / maturity-wall clearing on levered equity
Distinct from deleveraging: a levered equity trades at a going-concern discount
until the **near-term maturity wall is refinanced** — the gun leaves the head
and the equity (a call option on enterprise value) re-rates as survival
probability jumps, before any operational change. *Build:* short-term debt /
total debt (a maturity-concentration proxy) + a refinancing event (8-K item
2.03 / "entered into credit agreement" / new notes) — the discount-lift trigger.

### N5. Signal SEQUENCING — position in the re-rating chain
The engine bundles signals statically; the alpha is in their ORDER. The canonical
chain is **insider buy → decline decelerates → margin stabilises → first
positive print → estimate revisions up → 52w-high break → re-rate.** A name
EARLY in the chain (insider buy + decelerating) is pre-rerating; one LATE (52w
high, estimates already up) is mid-rerate. *Build:* a `rerating_stage` (1–6)
from which links are lit, and rank by *early stage with the most latent gap* —
buying the sequence before recognition, not after.

### N6. Operating-KPI lead (pre-financials)
Unit economics turn 1–2 quarters before the P&L: **same-store sales / comps,
subscriber or user adds, bookings/backlog, occupancy, load factor, capacity
utilisation, announced price increases.** These live in MD&A / press releases,
not XBRL. We mine backlog (narrowly) and segments; we don't mine the KPI turn.
*Build:* extend the EFTS/MD&A miner (scoped to cheap+turning candidates) for
"same-store sales increased", "raised prices", "record bookings", "utilisation
improved" — the operating lead the financials haven't caught.

### N7. Disclosure-CONFIDENCE signals (management revealing its hand)
Management changes what it discloses when it gets confident: **initiating
guidance after none, first-time breakout of a segment/KPI (ARR, RPO), a first
buyback authorisation, reinstating a dividend, hosting a first investor day.**
Each is a revealed-preference confidence signal that precedes the numbers.
*Build:* first-appearance deltas — segment count rising (segment harvest),
first RPO/deferred disclosure, first buyback (cache series), guidance initiation
(EFTS). The *newness* is the signal.

### N8. Overhang EXHAUSTION (forced-selling finishing)
A re-rate often waits for a mechanical seller to finish: **tax-loss selling
(December lows on the year's biggest losers), index deletion, post-spin dumping,
lockup expiry, a fund liquidation.** The pre-tell is the overhang *ending* — the
stock stops making new lows on higher volume. We have `forced_seller`/spin but
not the **exhaustion timing**. *Build:* a "selling-climax" tape signal (new low
on a volume spike then stabilising) + calendar awareness (Dec tax-loss names,
index-rebalance dates).

### N9. Contingent-liability / overhang RESOLUTION
A discrete discount lifts when a **litigation settles, a regulatory probe
closes, a pension is bought out / de-risked, a large customer contract renews,
or customer concentration diversifies.** The market prices the tail risk; its
resolution re-rates. *Build:* EFTS for "settled", "resolution of", "dismissed",
"pension buy-in/buy-out", scoped to names carrying the overhang (litigation
reserves, single-customer concentration flag we already have).

### N10. Repeat-unlocker base rate (pedigree)
Some management teams create value on a schedule: **serial spinners (the Liberty
/ Malone complex), disciplined serial acquirers (Constellation, Danaher,
Roper), proven activists' targets.** A base-rate prior: the same catalyst in
proven hands is worth more. *Build:* a `pedigree_flag` from a curated list +
detection of prior value-creating spins/buybacks in the filing history — a
Bayesian prior on the catalyst succeeding.

### N11. The mix-shift margin ratchet (already partly built — deepen)
Beyond segment mix (`margin_mixshift`): a company whose **incremental margin >>
average margin** for several quarters is structurally re-rating its whole-company
margin as the high-margin mix compounds — a *ratchet*, not a one-off. We have
`incremental_ebitda_margin`; we don't track its persistence. *Build:* a
multi-quarter incremental-margin streak.

### N12. Balance-sheet OPTIONALITY the market ignores
Assets that are *free options*: **NOLs about to be usable (profits returning),
a DTA valuation allowance about to reverse, land/permits/spectrum/IP carried at
zero, an equity stake pre-IPO, an overfunded pension reverting to the P&L.** We
catch several as static hidden value; the nuance is the **TRIGGER that turns the
option live** (profits returning → NOL/DTA usable; an investee filing to IPO →
stake remark, which we now catch). *Build:* pair each optionality with its
activation trigger (e.g. DTA allowance + a return to profitability = imminent
reversal, a mechanical earnings boost).

---

## 5. The meta-nuance

Two themes unify N1–N12. **First: the engine measures LEVELS and first
derivatives; the great pre-rerating tells live in SECOND derivatives (decline
decelerating, accruals improving, incremental-margin ratchet) and in
TRANSITIONS/REMOVALS (distress lifted, overhang exhausted, option activated) —
the change in the change, and the discrete disappearance of a discount.**
**Second: the sharpest signals are REVEALED PREFERENCE under asymmetric
information — management disclosing more, buying more, refinancing, initiating
returns — because insiders act on the turn before it is reportable.** An engine
that systematically watched *second derivatives*, *discount removals*, and
*revealed-preference confidence* would catch the re-rate one stage earlier than
one watching levels and single prints.
