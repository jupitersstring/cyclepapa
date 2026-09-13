# Forensic anatomy of the great re-ratings — new XR detection methods

*Method: backwards induction from the largest historical re-ratings to the
accounting state that preceded them, then case studies, then a shortlist of
net-new forensic signals to add. "XR" = extreme re-rating (multiple expansion),
distinct from ordinary earnings growth.*

---

## 1. Backwards induction — the algebra of a re-rate

Decompose price: **Price = Multiple × Base** (Base = earnings, FCF, book, or
asset value; Multiple = what the market pays per unit of Base).

A *re-rating* is Multiple expansion. Ordinary compounding grows the Base; an XR
event is when the **Multiple** jumps — often 2–5× — usually alongside the Base
also being revised up. Working backwards, a large Multiple jump requires that
**before** the move, one of two things was true:

- **(A) The Base was understated.** GAAP suppressed the true economic
  earnings/asset power. When reality is forced into the reported numbers (a
  catalyst), both Base *and* Multiple correct at once — the violent kind of
  re-rate. **This is the forensic-accounting hunting ground.**
- **(B) The Multiple was mis-set.** The business was mis-classified — treated as
  low-quality/terminal/cyclical when it was durable/recurring/structural. The
  re-rate is the market re-classifying it.

Forensic accounting's entire job for XR is to find, *ex ante*, the **gap between
GAAP and economic reality**, plus evidence that a **catalyst will close it**.
The canonical GAAP-vs-economic gaps (each a re-rate precondition):

| # | GAAP-vs-economic gap | Direction | Catalyst that closes it |
|---|---|---|---|
| G1 | Growth spend expensed through the P&L (R&D, S&M, content) | Earnings understated | Growth matures; incremental margin shows |
| G2 | A high-margin segment buried inside a low-margin consolidated whole | Base mis-attributed | Segment disclosure / spin / mix shift |
| G3 | Assets carried at historical cost far below market (land, brands) | Book understated | Sale/leaseback, activist, revaluation |
| G4 | Depreciation/amortization > true economic maintenance | Earnings understated | D&A rolls off; cash earnings surface |
| G5 | Recurring revenue disguised as one-off (subscription transition) | Base understated & mis-multipled | Deferred-revenue/billings convert |
| G6 | One-off / restructuring / discontinued drag masking a viable core | Earnings understated | Charge annualises out; unit sold |
| G7 | Cash taxes << book taxes (DTL cushion) or NOL shield | Owner earnings understated | Cash-flow reality recognised |
| G8 | Cyclical trough earnings mistaken for structural | Base understated | Cycle turns to mid-cycle |
| G9 | Below-peer margins with latent self-help | Base understated | New mgmt / restructuring executes |
| G10 | Not yet GAAP-profitable → uninvestable by mandate | Multiple capped near zero | First GAAP profit unlocks passive/institutional demand |

**Coverage today:** G1 (`arch_xr_growth_capex_masked`, `expensed_growth_value`),
G2 (`arch_xr_hidden_segment_compounder`, `arch_xr_segment_justifies_whole`,
`arch_xr_margin_mixshift`), G4 (`arch_xr_depreciation_cliff`,
`arch_xr_amortization_mask`, `arch_overdepreciated_assets`), G6 partially
(`arch_xr_oneoff_loss_mask`, `arch_xr_bigbath_rebound`), G7 partially
(`arch_xr_nol_shield`), G8 (`arch_xr_cyclical_trough`, `arch_xr_double_trough`),
plus float (`arch_xr_float_compounding`), look-through (`arch_xr_look_through_value`),
LIFO/pension/DTA hidden value.

**The gaps in our net — G3, G5, G6-discops, G7-cash-tax, G9, G10 — are where the
new signals below live.**

---

## 2. Case studies (backwards-induced)

Each: the re-rate, the *ex-ante* forensic tell, whether we'd catch it now, and
the signal it implies.

### 2.1 Amazon — AWS buried in retail (G1 + G2)
For years consolidated GAAP earnings were ~nil: a profitable, negative-working-
capital retail engine plus an expensed cloud build. The 2015 segment disclosure
revealed AWS's true operating margin — the stock re-rated as the market valued
the parts. **Tell:** negative cash conversion cycle (customer float) + growth
expensed + a segment whose margin dwarfed the consolidated blend. **Caught now:**
yes — `arch_xr_segment_justifies_whole` / `hidden_segment_compounder` /
`customer_float`. *Confirms the segment SOTP build.*

### 2.2 Netflix / Adobe / Autodesk — the subscription transition (G5)
Adobe and Autodesk deliberately *depressed* GAAP revenue moving from licences to
subscriptions: cash arrived up front and sat in **deferred revenue**, recognised
over the term. Reported revenue fell while **billings (revenue + Δdeferred
revenue) rose**. The market anchored on the falling P&L; the balance sheet
already contained the growth. **Tell:** deferred revenue growing faster than
recognised revenue; billings > revenue. **Caught now:** only obliquely
(`customer_float` treats deferred revenue as a static float, not as a *growing
forward-revenue lead*; `contracted_backlog` needs the newer RPO disclosure).
**→ New signal N1: billings/deferred-revenue lead.**

### 2.3 McDonald's / Darden / Dillard's — owned real estate at 1960s cost (G3)
The classic activist SOTP. Land is **never depreciated** and buildings are carried
at decades-old historical cost; a restaurant/retail operator that *owns* its
estate holds property worth multiples of book, invisible on the balance sheet and
paying near-zero rent. Dillard's 2020–22 (~10×) is the recent textbook case:
owned stores + buyback cannibalism. **Tell:** high gross PP&E with a high
accumulated-depreciation ratio (old assets), **low rent/lease expense** (owns
rather than leases), real-estate-heavy sector, trading below reproduction value.
**Caught now:** partially (`hidden_assets`, `overdepreciated_assets` use net PP&E
and non-op assets) but we can't *see* the owned-vs-leased distinction or the
historical-cost land. **→ New signal N3: over-depreciated owned real estate.**

### 2.4 AutoZone / NVR / Copart — the buyback cannibal (G-quality/multiple)
NVR's asset-light land-option model and AutoZone's relentless repurchases drove
book equity toward (or below) zero, breaking P/B and ROE screens — the screens
said "over-levered, low quality," the reality was a fortress FCF machine
shrinking the share count. Re-rate came as per-share metrics compounded.
**Caught now:** yes — `arch_xr_cannibal_below_cash/tbook`, `self_funded_returner`.
*No new signal; confirms the cannibal family.*

### 2.5 General Growth / Six Flags / post-reorg emergers (G3 + reset)
Fresh-start accounting resets the balance sheet at emergence; a de-levered
company with cleaned-up assets and a low share count re-rates hard off the
trough. **Caught now:** yes — `arch_post_reorg` (fresh-start, EBIT-yield gate),
`arch_special_situation`. *Confirmed; the earlier reorg-date freshness work
already tuned this.*

### 2.6 Nucor / Steel Dynamics / Mosaic / CF — deep-cyclical trough (G8)
At the trough, TTM earnings are near-zero and the multiple looks infinite (or the
stock screens "expensive" on trailing); mid-cycle earnings power is a multiple of
trough. The 2020–22 commodity re-rate. **Tell:** normalized (mid-cycle) EBIT vs.
trailing, plus balance-sheet survival to the next cycle. **Caught now:** yes —
`arch_xr_cyclical_trough`, `arch_xr_double_trough`, `normalized_ebitda`.
*Confirmed.*

### 2.7 The discontinued-ops mask (G6)
A recurring pattern (conglomerates shedding a losing division, e.g. many
industrial/consumer break-ups): consolidated net income is negative *because of a
unit held for sale or in discontinued operations*, while **continuing operations**
are solidly profitable. Screens on consolidated NI/EPS reject the name; the
re-rate comes when the drag is divested and continuing-ops earnings stand alone.
**Tell:** income from continuing ops >> consolidated net income; large
assets-held-for-sale vs. market cap. **Caught now:** no — we use consolidated
figures. **→ New signal N4: discontinued-ops / held-for-sale drag mask.**

### 2.8 Fairfax / Markel — insurance float compounding
Underwriting float invested at a widening spread; book value per share compounds
while GAAP earnings are lumpy. **Caught now:** `arch_xr_float_compounding`.
*Confirmed (note: financials are excluded from operating gates by design).*

### 2.9 Apple 2005–2012 — deferred iPhone revenue + services optionality (G5 + G2)
Pre-2010, iPhone revenue was subscription-accounted (deferred and amortised),
understating reported growth; later the **Services** segment disclosure revealed a
high-margin recurring annuity the market had valued at hardware multiples. Both
G5 and G2. **Caught now:** partially (segment build); the deferred-revenue lead
would add the earlier tell. **→ reinforces N1.**

### 2.10 Tax normalisation / cash-tax advantage (G7)
Two shapes. (a) A company carrying large **deferred tax liabilities** (from
accelerated depreciation) pays far less cash tax than book tax expense implies —
its owner earnings are *understated* by the book provision (the DTL is an
interest-free government loan). (b) A serial acquirer or turnaround burning
**NOLs** pays near-zero cash tax for years — cash generation the P&L tax line
hides. **Tell:** cash taxes paid << book tax expense (and/or a big DTL, or NOLs).
**Caught now:** NOLs via `arch_xr_nol_shield`; the *cash-tax-vs-book-tax gap* is
not measured. **→ New signal N2: cash-tax advantage / DTL cushion.**

### 2.11 Below-peer margins with self-help (G9) — e.g. turnaround operators
A business earning 8% operating margin in a sector where peers earn 18% is either
structurally inferior *or* sitting on latent margin (bloated cost base, bad mix,
new-management self-help). The re-rate is the market pricing mean-reversion once
execution starts. **Tell:** operating/gross margin far below the *sector median*,
plus a turn signal (margin delta turning up, cost action, new capital return,
insider buying). This is inherently **peer/size-normalised** — exactly the
comparable lens the ranking already wants. **Caught now:** no explicit
peer-relative margin gap. **→ New signal N5: peer-relative margin gap +
self-help turn.**

### 2.12 Monster / operating-leverage coils (G1 lead)
Before the operating-margin explosion, **gross margin** inflects first (mix,
pricing, scale) while SG&A hasn't yet scaled down, so operating margin lags and
the market can't see it. Gross margin leads operating margin. **Caught now:**
partially (`arch_xr_pre_scale_margin`). **→ New signal N6: gross-margin lead /
operating-leverage coil** (sharper, explicit lead structure).

---

## 3. Proposed net-new forensic signals

Ranked by expected asymmetry × buildability. Each notes the data requirement and
whether it needs a new EDGAR concept (extraction gap) or only existing columns.

| ID | Signal | Gap | Data needed | Normalised? |
|----|--------|-----|-------------|-------------|
| **N1** | **Billings/deferred-revenue lead** — Δdeferred_revenue > 0 and material vs. revenue (billings > revenue), business cheap on trailing sales/FCF, not melting. Forward revenue is contracted in the balance sheet and unpriced. | G5 | `deferred_revenue` (HAVE, level) + need **prior-period** deferred revenue to get Δ (add to EDGAR pull) | vs. own revenue |
| **N2** | **Cash-tax advantage / DTL cushion** — cash taxes paid materially below book tax expense (owner earnings understated), or large DTL relative to earnings. | G7 | **NEW EDGAR:** `IncomeTaxesPaidNet` (cash-flow supplemental); DTL from existing DTA/pretax | ratio, size-free |
| **N3** | **Over-depreciated owned real estate** — high accumulated-depreciation ratio (old assets at historical cost) + low rent/lease expense (owns) + real-estate-heavy sector + below reproduction value. | G3 | **NEW EDGAR:** `PropertyPlantAndEquipmentGross`, `AccumulatedDepreciation`; optionally `OperatingLeaseExpense`/ROU | vs. mcap |
| **N4** | **Discontinued-ops / held-for-sale drag mask** — continuing-ops income >> consolidated NI (a losing unit masks a profitable core), or large assets-held-for-sale vs. mcap. | G6 | **NEW EDGAR:** `IncomeLossFromContinuingOperations`, `IncomeLossFromDiscontinuedOperations`, `AssetsHeldForSale` | vs. mcap / own NI |
| **N5** | **Peer-relative margin gap + self-help turn** — op/gross margin far below **sector median** AND margin delta turning up (or cost action / new capital return / insider buy). Mean-reversion re-rate. | G9 | Existing margins + a **sector-median** computation (no new EDGAR) | peer-normalised (the comparable lens) |
| **N6** | **Gross-margin lead / operating-leverage coil** — gross margin inflecting up (≥ ~2pp YoY) while operating margin still flat/negative (SG&A not yet scaled), revenue growing. Operating leverage about to surface. | G1 | Existing `gross_margin_delta_yoy`, `op_margin_delta_yoy` | vs. own history |
| **N7** | **Restructuring normalisation** — large restructuring/impairment charge in TTM depressing reported operating income, underlying business cash-viable; charge annualises out. Sharper than the generic one-off mask. | G6 | **NEW EDGAR:** `RestructuringCharges` (else approximated by `oneoff_loss_mask`) | vs. own op income |
| **N8** | **GAAP-profitability crossover (index/mandate unlock)** — about to post first full-year GAAP net profit after a loss history; passive funds and profitability-mandated institutions can then own it. Multiple was capped near zero by mandate, not economics. | G10 | Existing `net_income_first_positive` / first-positive flags — formalise as an XR archetype | size-free |

### Notes on normalisation & valuation (per the earlier directive)
- **N2, N4, N5** are naturally **size-comparable** (ratios / peer medians), which
  is what the `forensic_xr_score` and cross-company ranking want. N5 is the first
  *explicitly peer-relative* forensic signal — it answers "cheap/under-earning
  **relative to comparables**," not just in absolute terms.
- Every signal must combine with **valuation** (cheap consolidated whole) and
  **survivability** (`_not_melting`) exactly as the existing XR family does — a
  hidden asset or understated-earnings tell is only an XR *setup* when the market
  is also pricing the visible business cheaply.
- N1/N3/N4/N7 fold directly into `forensic_xr_score` as additional
  size-normalised hidden-value components once extracted.

---

## 4. Build recommendation

**Two waves.** Buildable-now vs. needs-extraction — and the extraction wave
should ride along with broadening the EDGAR universe (see the coverage note).

**Wave 1 — no new EDGAR pull (build immediately):**
- **N5** peer-relative margin gap + self-help turn *(highest value; first true
  comparable-normalised forensic lens)*
- **N6** gross-margin lead / operating-leverage coil
- **N8** GAAP-profitability crossover
- **N1** billings lead — *partial*: usable from the deferred-revenue level today;
  sharper once we pull the prior-period level for a true Δ.

**Wave 2 — add EDGAR concepts (do alongside the universe broadening):**
- **N2** cash-tax advantage → alias `IncomeTaxesPaidNet`
- **N3** owned real estate → aliases `PropertyPlantAndEquipmentGross`,
  `AccumulatedDepreciation`, `OperatingLeaseExpense`
- **N4** discontinued-ops mask → aliases `IncomeLossFromContinuingOperations`,
  `IncomeLossFromDiscontinuedOperations`, `AssetsHeldForSale`
- **N7** restructuring normalisation → alias `RestructuringCharges`
- **N1** billings lead → prior-period `deferred_revenue` for the delta

Each new alias follows the established pattern (add `*_ALIASES` + `pt()` in
`edgar_universe_extract.py`, pass through `edgar_to_yartseva.py`, add to the
`derive_missing_columns.py` keep-list, register the archetype across
`arch_cols`/`pretty`/`tab_colors`/book labels/`methodology_audit` R1). Because
`_needed_concepts()` auto-collects every `*_ALIASES` global, the cache
automatically starts trimming these new concepts on the next refresh — so Wave 2
is best done in the **same pass** as the universe broadening, when the cache is
being rebuilt anyway.

---

*Companion: the EDGAR ticker-coverage broadening is tracked separately; the Wave 2
concepts should be added in that same cache-rebuild pass.*

---
---

# Part II — Why forensic accounting unveils *gross* mispricings (first principles)

*Deeper theory, requested follow-up. Part I asked "what were the tells." Part II
asks "why do these tells exist at all, and where are they structurally largest,"
then derives further signals from the theory rather than from anecdote.*

## II.1 The anchor-number theory

The marginal price-setter — the trade that clears the market — anchors on **one or
two headline numbers**: trailing P/E, EV/EBITDA, revenue growth, or P/B. Screens,
factor models, and most analyst notes are built on those anchors. **A gross
mispricing is not possible when the true economics live in the anchor** — the
crowd competes it away. It is *only* possible when the true economics live in a
number the anchor does not see:

| If the crowd anchors on… | …the gross mispricing hides in | Forensic reconstruction |
|---|---|---|
| Trailing P/E | Earnings understated (expensed growth, D&A>maintenance, DTL, discops drag, one-offs) | Normalise earnings to owner-earnings |
| EV/EBITDA | EV overstated by non-operating claims (equity stakes, land, overfunded pension, NOLs, net cash) | Strip non-operating assets from EV |
| Revenue growth | Revenue understated (deferred/subscription recognition) | Billings = revenue + Δdeferred |
| P/B | Book meaningless (historical-cost land, contra-equity buybacks, expensed intangibles) | Reconstruct economic book |

**The forensic edge is definitionally the act of computing the NON-anchor number.**
The magnitude of available alpha in a name is the *distance* between its anchor
number and its economic-reality number — this is precisely what `forensic_xr_score`
tries to size, and the sharpening below is to always express the gap **relative to
the anchor the crowd is actually using** for that name.

## II.2 GAAP is systematically conservative — the under-practiced mirror of fraud detection

Forensic accounting is overwhelmingly taught and practised as **overstatement
detection** — finding fraud, aggressive revenue, capitalised expense, the short
side. That skill is crowded (short sellers, the SEC, auditors, activists all hunt
it). The **mirror discipline — finding systematic *understatement*** — is
under-practised, therefore its findings are less arbitraged, therefore the
mispricings are grosser and more durable. US GAAP has *structural* conservative
biases that permanently understate value and never self-correct:

1. **Historical cost, no upward revaluation** (unlike IFRS): land, buildings, and
   long-held assets are frozen at acquisition cost. Land is never depreciated *and*
   never marked up → a 1960s parcel sits at 1960s cost forever. (Signal N3.)
2. **Immediate expensing of intangible investment** (R&D, brand, software,
   customer acquisition): the invested capital and the current earnings of an
   intangible-heavy grower are both understated — no asset appears, and the P&L
   is charged for investment as if it were cost. (Signal N-ext-3 below.)
3. **Impairments are one-way**: written down on a bath or a cyclical low, never
   written back up under US GAAP even as the asset's economics recover — a
   permanent understatement after every trough. (Adjacent to `bigbath_rebound`.)
4. **Full depreciation of still-productive assets**: a plant at zero net book that
   still produces carries *no* depreciation drag and its owner defers replacement
   capex — cash earnings exceed reported. (Sharper `depreciation_cliff`; N-ext-4.)
5. **LIFO inventory**, **overfunded pensions**, **reversible DTA allowances**,
   **equity-method stakes below fair value** — already in the net.

The theoretical point: **stacking multiple independent conservative biases in one
name multiplies the gap** and is rarer than any single one, so the confluence is
where the grossest, least-arbitraged mispricings sit. This is the justification for
keeping `forensic_xr_score` as a *sum of independent size-normalised components*
and rewarding confluence — the theory says confluence is the edge, not the average.

## II.3 The cash-vs-accrual wedge (the single most powerful lens)

The most reliable forensic reconstruction is **owner earnings (cash the owner can
extract) vs. reported accrual earnings**. Sloan (1996) established the *accrual
anomaly*: high-accrual firms subsequently underperform, low/negative-accrual firms
outperform — the market over-weights the accrual component of earnings and
under-weights the cash component, because accruals are less persistent than cash
but look identical in headline EPS.

For the **long/XR side**, the tell is the inverse of the fraud tell: a firm whose
**cash earnings persistently and materially EXCEED accrual earnings** (CFO ≫ NI,
low or negative accruals) is one whose headline P/E *overstates* the price of its
true cash generation. This is a distinct, measurable, academically-grounded signal
we do not yet isolate as an XR archetype (we use `owner_earnings_yield` as a level,
not the *cash-beats-accrual persistence* as a signal). → **Signal N-ext-1.**

The wedge decomposes into the exact items forensic accounting reconstructs:
`Owner earnings ≈ NI + D&A − maintenance capex + non-cash charges (impairment,
SBC¹, deferred tax provision) ± working-capital release`. Every term is a place the
accrual number diverges from cash — and every divergence we can measure is a
component of the same score. *(¹SBC is a real economic cost; it is the one add-back
forensic rigour must NOT make — the system already expenses it via `roic_after_sbc`.)*

## II.4 The disclosure-granularity gradient

Alpha concentrates at a specific granularity of disclosure: **fine enough that a
diligent reader can reconstruct economic reality, coarse enough (or buried enough)
that a screen cannot.** Face financial statements are read by every algorithm; the
**footnotes are read by almost no automated price-setter.** So the gradient of
mispricing runs:

`face statements (fully arbitraged) → MD&A prose (semi) → footnotes (barely) →
off-balance-sheet & contractual-obligations tables (essentially unread by machines)`

This is the structural reason our **EDGAR XBRL footnote extraction is the moat**:
segment notes, tax footnotes (DTA/DTL/NOL/rate-reconciliation), pension notes, lease
notes, revenue-recognition rollforwards (deferred revenue, RPO), and related-party
notes are *tagged* in XBRL and therefore machine-readable **by us** but not consumed
by the crowd's face-statement screens. Every incremental footnote concept we tag
moves us further down the gradient into less-arbitraged territory — which is the
theoretical case for the Wave-2 concept additions (cash-tax, gross PP&E, discops,
restructuring) being *worth more per name* than adding more tickers of face data.

## II.5 Mechanical vs. discretionary catalysts (avoiding the value trap)

A hidden asset with **no catalyst is a permanent discount** — the classic value
trap. The forensic edge only becomes an XR *setup* when convergence is forced.
Catalysts are not equal; rank them by **who controls the trigger**:

- **Mechanical / self-executing (highest conviction):** DTA valuation-allowance
  release when profits return, NOL burn-through, pension surplus swinging with
  rates, D&A rolling off as assets fully depreciate, deferred revenue converting to
  P&L, a one-off/restructuring charge annualising out of the trailing window, a
  cyclical trough mean-reverting. **The clock does the work — no dependence on
  anyone's decision.**
- **Semi-mechanical:** index/mandate inclusion on first GAAP profit or crossing a
  size threshold (N8) — automatic *once* the accounting condition is met.
- **Discretionary (lower conviction, longer/uncertain):** management sale-leaseback,
  spin, buyback initiation, dividend initiation, segment-reporting change, or an
  activist forcing any of the above.

**Refinement proposal (overlay, not a new archetype):** tag every forensic-family
member by its catalyst class and **upweight self-executing over discretionary** in
the ranking. Our current forensic score is catalyst-agnostic; the theory says a
mechanically-converging gap deserves a higher rank than an identically-sized gap
that needs a boardroom to act. → **Signal N-ext-2 (a `catalyst_class` overlay).**

## II.6 Mandate blind spots — "re-rate by inclusion"

Some multiples are set not by economics but by **who is structurally forbidden from
owning the stock.** When the constraint releases, price snaps to where the newly-
eligible buyers value it — a re-rate with *no* change in fundamentals:

- **GAAP-unprofitable** → excluded from S&P index inclusion and most institutional
  profitability screens. First GAAP profit unlocks. *(N8 — built.)*
- **Sub-threshold size / liquidity** → excluded from indices and large funds.
- **Negative book equity** (buyback cannibals) → excluded by P/B value screens even
  when FCF is a fortress. *(`cannibal` family — built.)*
- **No dividend** → excluded by income mandates; initiation unlocks a buyer class.
- **OTC / no major-exchange listing** → excluded by nearly all institutions;
  uplisting unlocks. *(We already flag `is_otc`/`is_price_ghost`.)*

The unifying idea: **the multiple was a function of the eligible-buyer base, not of
cash flows.** Forensic accounting's role here is to identify names *about to* cross
an eligibility line (first profit, first dividend, size threshold) — the accounting
event that mechanically widens the buyer base.

## II.7 Further signals derived from the theory (beyond N1–N8)

These fall out of the theory above rather than from case anecdote; listed for the
research record (not built now):

- **N-ext-1 — Cash-beats-accrual persistence** (§II.3): CFO persistently and
  materially > NI with low/negative accruals, cheap on owner-earnings yield. The
  academically-grounded accrual-anomaly long. *Buildable from existing CFO/NI.*
- **N-ext-2 — Catalyst-class overlay** (§II.5): tag each forensic member
  mechanical / semi / discretionary and upweight self-executing convergence.
  *A ranking overlay over existing archetypes; no new data.*
- **N-ext-3 — Capitalised-intangible ROIC** (§II.2 bias 2): reconstruct an R&D /
  brand asset (capitalise and amortise historical R&D/S&M), revealing true invested
  capital and a true ROIC the market misses on intangible-heavy compounders.
  *Needs R&D-expense history (new EDGAR concept, Wave 2+).*
- **N-ext-4 — Fully-depreciated productive asset** (§II.2 bias 4): net PP&E near
  zero relative to gross, revenue/output stable → the asset earns with no
  depreciation drag and replacement is deferred. *Needs gross PP&E + accumulated
  depreciation (the same Wave-2 concepts as N3).*

## II.8 Synthesis — the ranking implication

The theory says the grossest, most durable, least-arbitraged mispricings are those
that are simultaneously: **(a)** off the anchor number the crowd uses, **(b)** a
product of GAAP's conservative (understatement) biases rather than aggressive ones,
**(c)** visible only in the footnotes (down the disclosure-granularity gradient),
**(d)** converging via a mechanical/self-executing catalyst, and **(e)** stacked —
multiple independent conservative biases in one name. `forensic_xr_score` already
captures (b) and (e). The highest-leverage refinements this study points to are:
express each component **relative to the crowd's actual anchor** (a), keep pushing
footnote-concept extraction (c), and add a **catalyst-class upweight** (d).
