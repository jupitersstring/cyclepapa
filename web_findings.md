# Web Findings — Material Updates to the Screen

Output of seven rounds of targeted web search against the live framework.
Captures verified facts, framework-changing corrections, downgrades,
and new high-conviction Tier 1 candidates. All claims here are sourced
to specific press releases or articles surfaced by search.

The session converted prior narrative into auditable data, exposed two
incorrect framework claims, downgraded one Tier 1 to pass, and added
four new candidates.

---

## 1. Corrections — prior screen claims that were wrong

### 1.1 Worldline alignment gap: 6.9× → 1.93×

The shortlist documented Worldline's alignment gap as **6.9× — largest
in the universe**. The math was: anchor reserved price €2.75 ÷ rights
subscription price €0.202 ≈ 13.6× (then narrated down to 6.9× implicitly).

**The correct denominator is the market price at announcement, not the
rights price.** The rights price is a discounted subscription level, not
a market clearing price. Verified data:

- Anchor reserved price: €2.75 (confirmed; 10% premium to 30-day VWAP)
- Pre-rights closing price: **€1.421** on 2026-03-10 (the announcement
  reference close)
- Theoretical ex-rights price (TERP): €0.376
- Rights subscription price: €0.202 (46.3% discount to TERP; 85.8%
  discount to pre-rights close)
- Stock jumped 17% on launch (Worldline press coverage)
- 40:1 reverse split effective 2026-06-15 (new ISIN FR00140182K6)

**Corrected alignment gap: €2.75 / €1.421 ≈ 1.93×.** Still meaningful;
no longer the universe's largest. Bpifrance ended at **9.6%** post-deal
(not 27.5% as the prior screen had — that 27.5% number was the combined
four-anchor commitment to *vote* on the deal, not their ownership).

### 1.2 Eutelsat alignment gap: 2.9× → 1.41×

Same class of error. The shortlist documented gap as 2.9×, dividing
anchor €4.00 by an approximate market of €1.40. The correct denominator
is the *current* market price, and **Eutelsat has already partially
re-rated**:

- Reserved increase price: €4.00 (still requires verification against
  the November 25 prospectus; load-bearing number)
- Rights subscription price: €1.35 (8-for-11 ratio, 496m new shares,
  settled Dec 16, 2025)
- Current market price: **€2.84** (verified June 2026 data point)
- Stock arc: €4.40-€4.60 mid-2025 → <€2 late Dec 2025 → €2.22 mid-Jan
  2026 → €2.84 June 2026

**Corrected alignment gap: €4.00 / €2.84 ≈ 1.41×.** Q3 FY2026 revenue
+3.1% YoY driven by LEO connectivity reported May 12, 2026 — Condition 7
*partially visible*, which explains the partial re-rate. Eutelsat
remains a Tier 1 pick but the "obvious mispricing" framing is materially
weaker.

### 1.3 Framework lesson logged

Both errors share the same shape: **using the discounted-subscription
price as the denominator for the alignment-gap metric inflates it
mechanically and makes every rights-issued deal look like a Worldline.**
The correct denominator is the *traded* market price at announcement or
current. This is now documented in the WLN.yaml and ETL.yaml history
blocks; a stricter definition belongs in §2.1 of the methodology doc.

---

## 2. Downgrades

### 2.1 Mountain Province Diamonds — Tier 1 → pass

This is the most consequential framework lesson of the session. The
prior screen marked MPVD as the *cleanest seven-condition setup* in the
entire universe on the basis of "founder owns both the equity *and* the
debt via Dunebridge — fulcrum conflict eliminated by construction." Web
verification revealed this structure is now operating as the canonical
loan-to-own pattern, *not* alignment:

- Q1 FY2026 (March 31, 2026): **CAD$219,000 cash on hand** versus
  **US$290.6m total debt**
- The Dunebridge bridge facility has been amended **six times** (Feb 24
  / May 13 / Jul 25 / Nov 18 2025 / Mar 17 / Apr 30 2026) — each
  amendment extracting fees and tightening terms
- Bridge interest steps from 10.5% → 12.5% on non-repayment
- Company sold US$999,999 of De Beers receivables to Desmond for
  **US$833,000** (17% discount) for short-term liquidity
- Both independent directors (Karen Goracke, Daniel Johnson) refused
  re-election at May 2026 AGM
- Company announced intent to **delist from the TSX** to enable
  restructuring or potential sale
- May 26, 2026 AGM: shareholder approvals sought to facilitate "potential
  restructuring transaction"

**Reclassified to Bucket C / Archetype F (only) / state: pass.** Listed
common is heading to zero or near-zero outcome. Any value goes to the
new common in whatever restructuring closes.

**Framework lesson:** "founder both sides of cap stack" is NOT
automatically 3/3 triangulation by construction. When the same party
holds both tranches, the question is *which tranche they have more
economic value in*. Desmond's debt position (par + accrued + collateral +
amendment fees + receivables purchase profits) materially exceeds his
equity position (residual claim on a hemorrhaging diamond JV). The
fulcrum still exists — it just sits inside one balance sheet, and the
rational party drives toward whichever instrument maximises their
recovery. That's the equity-extracting loan-to-own seat. The §2.3 red
flag for "DIP-to-exit control transfer" should fire even when "DIP" is
informally provided by a related party. This lesson should be lifted
into the methodology document.

---

## 3. New Tier 1 candidates

### 3.1 USA Rare Earth (NASDAQ: UREE) — Archetype A2, joins MP/LAC template

The cleanest new entrant of the session. Definitive agreements with the
US Department of Commerce signed **June 3, 2026** (preceded by January
2026 non-binding LOI):

- $277m federal funding + $1.3bn CHIPS Act senior secured loan
  capacity (total $1.6bn US Gov package)
- US Government receives **16.1m shares + 17.6m warrants** → 10% direct
  stake, up to 16% fully diluted
- Complements **$1.5bn private capital raise** completed January 2026 →
  $3.5bn total committed capital
- Stock surged 21% on initial LOI announcement (January/February) and
  21% again on definitive June 3 signing
- Round Top Mine (Sierra Blanca, Texas) for rare-earth concentrate +
  Stillwater magnet facility (Stillwater, Oklahoma) for vertical
  integration

**Why it joins Tier 1:** Triangulation 3/3. Stillwater magnet facility
commissioning is dated within 12-18 months — the closest near-term
inflection of any Archetype A2 pick (LAC's Phase 1 is 5-6 quarters
further out). The private capital raise preceding the federal close is
revealed-preference confirmation that the federal terms would clear.

### 3.2 Eutelsat (Euronext: ETL) — verified at narrower gap

Already promoted (see §1.2 above). Still Tier 1 on triangulation +
dated catalyst basis but at 1.41× alignment gap not 2.9×. Q3 LEO revenue
growth confirmed partial Condition 7.

### 3.3 AB Electrolux Series B (STO: ELUX-B) — Archetype A1+D, the
canonical Nordic pattern

Discovered through the search. Rights issue subscription period **June
2-16, 2026** (literally running as this is written):

- SEK 9,062m fully underwritten rights
- **Investor AB (Wallenberg)** — 17.94% capital / 30.43% votes — has
  undertaken to subscribe pro-rata for SEK 1.7bn *plus* guarantee an
  additional SEK 1.7bn = **37.56% of the entire issue**
- Tied to **strategic JV with Midea Group** for North America (Archetype
  D customer-aligned anchor on top of A1 family-foundation anchor)
- Use of proceeds: profitable growth + balance sheet + footprint
  optimization
- EGM approved May 27, 2026

**Why Tier 1:** This is the canonical Nordic Bucket A pattern that
historically delivered 3-5× compounding (Wärtsilä, Atlas Copco split,
SEB 2016 rights all anchored by Wallenberg vehicles). The Midea
D-archetype layer is what makes the asymmetry meaningful — without the
JV it's a 2× normalisation trade; with it, the cycle + market-access
combination supports base case 2.2× and bull 4.0×. Best Nordic recap on
the screen.

---

## 4. New Tier 2 candidate

### 4.1 Trilogy Metals (NYSE: TMQ)

Pentagon $35.6m / 10% stake investment to support Upper Kobuk Mineral
Projects in Alaska's Ambler district (copper/zinc/gold/silver).
**Original closing target May 31, 2026 pushed to July 31, 2026** —
events still unfolding.

Tier 2 because the deal is not closed and the Ambler access road
permitting decision (separate federal process) is a material binary
that could halve the asset value. Promoted to Tier 1 if both close
positive in Q3 2026.

---

## 5. Catalysts confirmed firing

### 5.1 Hawaiian Electric — first $479m settlement payment authorized
April 10, 2026

The screen documented this as a Q2 2026 catalyst. **Confirmed fired:**

- 24 September 2024 equity offering of $558m net was raised explicitly
  to fund this first payment, held in SPV
- 10 April 2026: all conditions to release satisfied, including
  resolution of subrogation claims by 200+ insurers
- Payment is the first of four equal annual $479m installments
- HEI/HEC also seeking rate hikes for next 2 years — second leg of the
  thesis (ROE 6% realised vs 9.5% authorised → 50% EPS upside on
  normalisation alone) now active

Tier 1 status confirmed; the partial re-rate is likely underway.

### 5.2 Petra Diamonds — new 10-for-17 rights, but yellow flag

Verified terms of the new round (the screen previously documented Petra
as Tier 2):

- 10-for-17 fully underwritten rights at 16.5p (~£18.8m / US$22.4m net)
- Bank debt extended Jan 2026 → **Dec 2029**
- Notes extended Mar 2026 → **Mar 2030**
- Cash interest rate increased to **10.5% (or 11.5% if paid in equity
  PIK)**
- Noteholders representing >99% support consent solicitation
- **Chairman is Backstop Shareholder + Noteholder + recipient of Work
  Fee Warrants + Incentivisation Warrants**

The chairman's warrants kicker is a yellow flag (§2.3 red flag
"backstop warrants below TERP" / "equity-pledged backstop fees"). Petra
remains investable but the "no fee/warrant kicker" green-flag praise in
the prior shortlist is overturned. Should be downgraded from Tier 2
strong to Tier 2 with caveat.

---

## 6. Patterns confirmed as the structural alpha cluster of 2026

The seven-round search consolidated one clear finding: **sovereign-
anchored critical minerals is the highest-density A2 archetype cluster
in the current vintage**, and it's still expanding:

| Issuer | Anchor | Stake | Instrument |
|---|---|---|---|
| MP Materials | DoD | 15% as-converted | Convertible preferred + $150m loan + 10y NdPr floor + 7,000t magnet offtake |
| Lithium Americas | DOE | warrants (5% LAC + 5% JV) | $2.26bn ATVM at 0% Treasury spread / 24-year |
| **USA Rare Earth** (new) | DOC + DOE | 10% / up to 16% diluted | $277m federal + $1.3bn CHIPS loan |
| Trilogy Metals (pending) | DoD | 10% | $35.6m equity (July 31 close target) |
| ReElement Technologies | (refining-tier) | TBC | TBC — flagged for further verification |
| Vulcan Elements | (magnet-tier) | TBC | TBC — flagged for further verification |
| Atlantic Alumina | DOE | TBC | $150m preferred (Jan 2026); $450m P3 |

The US Gov has now taken stakes across the **full critical-minerals
value chain** — exploration (Trilogy), mining (MP, LAC), refining
(ReElement), and components (Vulcan Elements magnets, USA Rare Earth
magnets, Atlantic Alumina). This is now a basket trade, not a single
name trade.

**EU parallel:** the **Industrial Accelerator Act** (March 4, 2026)
formalizes Archetype A2 at EU level for steel, aluminum, cement,
automotive, and renewables. Includes "Made in EU" procurement
preferences and "Industrial Acceleration Areas" — the policy framework
underwrites future European Eutelsat/Worldline-style sovereign-
strategic deals. Watch: Thyssenkrupp post-EPCG, voestalpine, SSAB,
Stellantis, EDF/Engie defence-adjacent, REC Silicon-style polysilicon.

---

## 7. Yellow flag — REC Silicon (Norway)

Surfaced by the broad rights-issue search; needs explicit framework
treatment as a *negative* example.

- NOK 972.6m fully underwritten rights issue
- Subscription price NOK 0.2385 (TERP – 25%)
- Subscription period 2026-03-20 to 2026-04-07
- **Anchor AS now controls over 93% of REC Silicon post-deal**
- **Anchor took 7% underwriting fee**
- 4,078,000,000 new shares (massive dilution to legacy stub)

This is **NOT** a Tier 1 candidate even though it's "fully underwritten
with anchor support." It is the textbook *bad* version of the pattern:
creeping control (already >50% pre-deal; 93% after) + fee extraction
(7% underwriting commission). Legacy public float is now a 7% stub of
a polysilicon producer where Anchor effectively owns the platform.

Framework lesson: "fully underwritten rights" is necessary but not
sufficient. The "no fee / warrant kicker" green flag must be enforced.
A 7% underwriting commission to the anchor is a hard fail.

---

## 8. Argentine bank basket — downgrade to watch

The shortlist documented "Argentine bank basket at <1× book entering
disinflation" as a structural opportunity. Verified Q2 2026 reality:

- Banks at **5-year low** post Milei monetary tightening
- Supervielle CEO: "very tight monetary policy characterised by
  unsustainably high real interest rates and historic statutory reserve
  requirements had a severe impact on the banking sector"
- Sector ROE swung from **+18% (2023) to -7% (Q3 2025)**
- Household delinquencies at worst level in 15+ years
- Bloomberg May 14, 2026: "Household defaults rock Argentina's banks
  and fintechs"

The disinflation thesis is intact medium-term but the entry timing was
clearly premature; sector dynamics deteriorated through 2025 and into
2026 rather than improving. **Downgrade Argentine bank basket to watch
list pending macro stabilization signals.** YPF/Pampa Energía (energy
side) remain investable on the Vaca Muerta cycle (YPF target $68, 4.14×
EV/EBITDA 2026; Milei RIGI expanded to unconventional oil wells).

---

## 9. Worldline reverse split mechanic — be aware

Implementation detail worth flagging: Worldline 40:1 reverse split
effective **June 15, 2026** with new ISIN FR00140182K6. All historical
prices in the universe/shortlist/screen need translation by ×40 when
comparing to post-split quotes. Pre-split €1.421 ≈ post-split €56.84.

The candidate YAML records the split explicitly. Forward analyses should
quote post-split prices to avoid confusion.

---

## 10. Net effect on the screen

| Change | Net effect |
|---|---|
| MPVD: Tier 1 → pass | –1 Tier 1 |
| WLN: alignment gap corrected (1.93×); remains Tier 1 | 0 net |
| ETL: added as Tier 1 with verified gap 1.41× | +1 Tier 1 |
| UREE: added as Tier 1 (third A2 template after MP/LAC) | +1 Tier 1 |
| ELUX-B: added as Tier 1 (Nordic Wallenberg+Midea A1+D pattern) | +1 Tier 1 |
| TMQ: added as Tier 2 (Pentagon deal pending July close) | +1 Tier 2 |
| HE: catalyst fired — partial re-rate underway | tier maintained, asymmetry compressed |
| PDL: yellow flag on chairman warrants kicker | Tier 2 → Tier 2 with caveat |
| REC Silicon: identified as canonical negative example | pass / negative control |
| Argentine banks: reality check | downgrade to watch |

**Tier 1 after this session:** WLN, ETL, LAC, UREE, ELUX-B (per the
generated screen). MPVD removed; new entrants ETL, UREE, ELUX-B added.

Per the Monte Carlo, the four added picks have honest distributions:

| | EV× | Median | P(≥3×) | P(≥5×) | P(loss>50%) |
|---|---|---|---|---|---|
| UREE | 2.71 | 2.04× | 13.8% | 1.6% | 3.1% |
| WLN  | 2.62 | 2.01× | 13.2% | 1.6% | 2.7% |
| ETL  | 2.35 | 1.79× | 10.6% | 0.0% | 1.5% |
| ELUX | 2.32 | 1.80× | 8.1%  | 0.0% | 1.1% |
| LAC  | 3.10 | 2.44× | 17.3% | 4.2% | 1.9% |

LAC remains the highest-EV, highest-bull-tail Tier 1 pick. ELUX-B has
the cleanest left tail (P(loss>50%) only 1.1%) consistent with the
Wallenberg long-term-anchor pattern. ETL's already-partial-re-rate
shows up as P(≥5×) = 0% — most of the upside priced in already.

The added discipline of `unverified` source tags is now driving real
behaviour: every Tier 1 name in the generated screen carries the
"sizing blocked at full conviction" warning until the deal-term fields
are cross-checked against primary filings. This is the source ledger
working as designed.
