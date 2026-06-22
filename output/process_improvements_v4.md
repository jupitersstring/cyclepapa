# Process improvements v4 — fourth-pass meta-survey

Builds on v1 (`process_improvements.md`), v2 (`_v2.md`), v3 (`_v3.md`).
Total surfaced techniques now ~67 across the four passes. v4 deliberately
mines five corners the prior three passes did not touch:

- (A) Government dockets *beyond* SEC — DOJ / OFAC / CFIUS / ITC as
  signal sources;
- (B) Tax-driven archetypes — Section 355 NOL preservation, F-reorg,
  divisive reorganization;
- (C) Quantified short-squeeze signals — utilization vs borrow vs
  short-interest hierarchy;
- (D) The Carlisle vs Cremers-Petajisto vs AQR concentration debate;
- (E) Industry-specific event calendars our framework hasn't catalogued.

11 new techniques.

---

## (A) Non-SEC US government dockets as signal sources

### 1. DOJ FCPA enforcement reset 2025 — new fraud-detection priors

**Source:** [Gibson Dunn 2025 Year-End FCPA Update](https://www.gibsondunn.com/2025-year-end-fcpa-update/);
[Pillsbury — FCPA Enforcement After the Pause](https://www.pillsburylaw.com/en/news-and-insights/fcpa-enforcement-smartmatic-comcel-doj.html);
[Thomson Reuters PE+HF FCPA scrutiny](https://legal.thomsonreuters.com/en/insights/articles/u-s-settlement-signals-increased-scrutiny-fcpa-compliance-within-private-equity-hedge-fund-industry).

Executive Order 14209 (February 10, 2025) paused DOJ FCPA enforcement;
the revised framework under AG Bondi prioritises cases involving drug
cartels and transnational criminal organisations. Two notable post-
pause cases: the **Smartmatic** corporate indictment and the
**Comcel/Millicom** deferred prosecution agreement. The PE/HF
scrutiny commentary specifically calls out diligence gaps when funds
acquire portfolio companies with FCPA exposure.

**Why it matters:** the framework's existing red-flag checklist has
no explicit FCPA / corruption-investigation field. For EM names
particularly (our LatAm-heavy top 10), an FCPA investigation can be
a multi-year overhang that compresses re-rate. The pause-and-reset
also means: any name whose pre-2025 thesis assumed an FCPA settlement
clearing the way for a deal needs that assumption re-checked.

**Technique:** poll the DOJ FCPA enforcement RSS (Justice Department
press releases) for case captions containing universe.md issuers.

**Slot:** new `src/doj_fcpa_poll.py`. RSS-based, lightweight. Outputs
`red_flag.fcpa_open_investigation` records to inbox.

### 2. CFIUS national-security review blocks — M&A break-deal signal

**Source:** [CRS report IF10177](https://www.congress.gov/crs_external_products/IF/PDF/IF10177/IF10177.39.pdf).
Notable 2025 actions: Trump blocked two PRC acquisitions of US firms;
**reopened CFIUS review reversed Biden's prohibition on Nippon Steel's
acquisition of U.S. Steel.** That's a $14bn deal where the CFIUS
political pendulum swung. Our framework has no calendar of pending
CFIUS-reviewable deals.

**Why it matters:** for any A2-archetype name where a foreign anchor
is forming (KfW for SZG, Nippon for U.S. Steel template, BNDES for
Brazilian, etc.), the CFIUS pendulum is a binary risk *to the
anchor's stake permission*, not the deal economics. The Nippon
Steel reversal showed CFIUS can be re-opened mid-process.

**Technique:** Treasury publishes a CFIUS Annual Report listing
mitigation agreements + prohibitions. Cross-reference against
universe-screened cross-border deals.

**Slot:** new `src/cfius_calendar.py`. Manual annual update from the
[Treasury CFIUS reports page](https://home.treasury.gov/policy-issues/international/the-committee-on-foreign-investment-in-the-united-states-cfius);
add `cfius_status:` field to YAML schema for cross-border-anchor
names.

### 3. OFAC general licenses — sanctions-window event-driven setups

**Source:** [OFAC consolidated FAQs](https://ofac.treasury.gov/faqs/all-faqs).
OFAC publishes General Licenses that carve specific transactions
(humanitarian, energy stabilisation, debt restructuring) out of
otherwise-prohibited sanctions regimes. Each GL has an expiration date
and named issuer/sector scope — they're effectively dated regulatory
events. The 2024 Venezuela energy GLs, Russia sovereign-debt
wind-down GLs, and Cuba humanitarian carve-outs all created dated
re-rating windows for affected paper.

**Why it matters:** OFAC GLs are *the* regulatory calendar for
sanctioned-jurisdiction restructurings. Currently we have nothing on
this. Argentine paper, Venezuelan equity, Russian residual claims
— all have OFAC-licensing windows that drive their event chains.

**Technique:** poll OFAC's [Recent Actions](https://ofac.treasury.gov/recent-actions)
feed daily. Filter for issuer names matching universe.md.

**Slot:** new `src/ofac_poll.py`. JSON feed available; clean parse;
emit `tier_s.ofac_license_window` records.

### 4. ITC Section 337 investigations — IP-driven going-private trigger

**Source:** US International Trade Commission Section 337
investigations (patent / trade-secret import disputes). When a public
company loses a 337 investigation, the resulting exclusion order can
trigger a strategic sale or going-private transaction within 6-12
months as the cost-of-staying-public exceeds the public-market
discount. Recent examples: GoPro Section 337 vs Insta360 (2024);
Sonos vs Google (settled 2024).

**Technique:** poll the ITC's Electronic Document Information System
(EDIS) for new 337 institutions involving universe.md issuers.

**Slot:** new `src/itc_poll.py` — secondary priority. ITC EDIS has
a documented search API.

---

## (B) Tax-driven archetypes

### 5. Section 355 spinoff with NOL preservation — quantifiable tax-arb

**Source:** [The Tax Adviser — Recent developments in Sec. 355 spinoffs (March 2024)](https://www.thetaxadviser.com/issues/2024/mar/recent-developments-in-sec-355-spinoffs/);
[A&O Shearman — Proposed regulations on spinoff reorgs](https://www.aoshearman.com/en/insights/proposed-regulations-provide-guidance-regarding-certain-aspects-of-spinoffs-and-reorganizations);
[SF Tax Counsel — Section 355 tax-free corporate reorganizations](https://sftaxcounsel.com/blog/tax-free-corporate-reorganizations-of-section-355/).

Section 355 governs tax-free corporate spinoffs. Key constraint: if
the parent's ownership changes >50% within 2 years before/after the
spinoff (the "Section 382 ownership-change" test), the controlled
subsidiary's NOL carryforwards get *capped* at the issuer's adjusted
long-term tax-exempt rate × pre-change equity value. The cap can
destroy 80%+ of NOL value if mis-managed.

**Why it matters for us:** spinoffs from companies with large NOLs
(Liberty Tax / J.C. Penney / Dean Foods historical templates) have
asymmetric upside ONLY if NOLs survive the spinoff. The framework's
F-archetype has no field for NOL-preservation status.

**Technique:** add a `nol_status:` block to YAML schema for any
F-archetype name with material NOLs disclosed:
```
nol_status:
  parent_nol_usd_m: 850
  ownership_change_pct_24m: 38       # < 50% required
  section_382_limitation_usd_m: 12   # annual cap if breached
  preservation_confidence: high|medium|low
```

**Slot:** YAML schema addition. Audit script flags F-archetype names
with material NOLs but no `nol_status:` block.

### 6. F-reorganization (one-shareholder shell) tax structure

**Source:** Same Tax Adviser series. An F-reorganization is a mere
change of place of organization or form (IRC §368(a)(1)(F)) — used
to swap a foreign HQ to US (or vice versa), redomicile to a more
favourable tax jurisdiction (Ireland, Bermuda), or interpose a
holding company structure pre-IPO. The F-reorg is *invisible to
shareholders* (no taxable event) but it *is* a strong signal that a
transaction is being prepped.

**Technique:** add `f_reorg_in_last_12m:` boolean to YAML. Recent F-reorg
+ A2 sovereign anchor or H governance archetype = elevated probability
of imminent strategic action.

**Slot:** YAML schema. EDGAR 8-K Item 3.03 (Material Modification to
Rights of Security Holders) discloses F-reorgs; can be screened from
existing `edgar_poll.py`.

### 7. Butterfly transaction (Section 355(e)) — split-up archetype

**Source:** [AnswerConnect (Wolters Kluwer)](https://answerconnect.cch.com/topic/bfc473dc7c6d1000a44d90b11c18cbab08/corporate-reorganizations-sec-355-spin-offs-split-offs-and-split-ups);
[vLex — After the Spin](https://vlex.com/vid/after-spin-preserving-free-treatment-29356421).
A "butterfly transaction" (US informal term; Canadian formal term for
divisive reorg) splits the parent into two or more separately-traded
entities through reciprocal exchanges. Less common than spinoffs but
produces cleaner price discovery (each entity prices independently
from day one, no parent-subsidiary attribution noise).

**Technique:** extend our F-archetype subtaxonomy:
- F1 = pro-rata spinoff (existing)
- F2 = equity carve-out (added in v3 §6)
- F3 = butterfly / split-up (new)

**Slot:** `src/universe_screen.py` ARCHETYPE_PATTERNS — add F3
keyword patterns.

---

## (C) Short-squeeze quantitative signals — utilization hierarchy

### 8. Utilization-rate prediction of short squeeze risk

**Source:** [Paul Schultz, JFQA Feb 2024 "Short Squeezes and Their Consequences"](https://www.evidenceinvestor.com/post/the-consequences-of-short-squeezes);
[Mendel University working paper 2025](https://ideas.repec.org/p/men/wpaper/104_2025.html);
[ScienceDirect — How prevalent are short squeezes?](https://www.sciencedirect.com/science/article/pii/S0378426625000561).

Schultz tested multiple short-squeeze predictors and found the
**single best predictor is utilization — the percentage of available
shares that were on loan.** Not raw short interest %; not days-to-
cover; not the borrow rate alone. Utilization captures the *supply
exhaustion* mechanic that drives squeezes.

Distribution of borrow fees: mean 2.67%, 95th percentile 11.0% —
most stocks borrow cheaply; a few are very expensive. High short
interest is a *two-sided* signal: validates a bearish thesis OR
flags squeeze risk — and the borrow rate is the discriminator.

**Why it matters:** the framework's tier_s names (catalyst-driven
upside) frequently have moderate short interest. Without utilization
data, we can't distinguish "shorts will cover happily on the catalyst"
from "shorts will get squeezed and the post-catalyst pop will be
distorted." For sizing, the latter matters — squeeze-driven pops
mean-revert; covering-driven pops compound.

**Technique:** add three fields to YAML scorecard:
- `d33_short_interest_pct` (already commonly reported)
- `d34_utilization_pct` (best squeeze predictor)
- `d35_borrow_rate_pct` (separates valid-thesis from squeeze-risk)

Scoring rules:
- `d34_utilization`: ≥90% → squeeze risk active; ≥70% → elevated;
  <50% → not a squeeze-driver
- `d35_borrow_rate`: ≥10% → expensive, structural-imbalance
  signal; <2% → cheap, validates short thesis

**Slot:** `src/score.py` SCORE_RULES additions. Data source: S3
Partners / EquiLend / FIS Global publish per-issuer utilization +
borrow rate; not free but ~$1000/month gets full universe coverage.
Alternative: Fidelity / Interactive Brokers publish indicative borrow
rates on their broker-side feeds.

### 9. "Short interest + low utilization" = clean bearish thesis flag

**Same source as §8.** The cleanest *bearish* signal is high short
interest + LOW utilization + LOW borrow rate. That combination means
borrow is plentiful, professional shorts see no scarcity, and they're
not exiting (high SI). It's the structural opposite of the meme-stock
squeeze pattern.

**Technique:** for any Tier-1 YAML, run a "bearish convergence" check:
- short_interest_pct > 10% AND
- utilization_pct < 50% AND
- borrow_rate_pct < 3%
- → annotate as `red_flag.bearish_convergence` (sophisticated capital
  thinks the thesis is short)

**Slot:** `src/score.py`. Conditional red flag added to the audit
output.

---

## (D) The Active Share / concentration debate — resolution for our framework

### 10. Cremers-Petajisto vs AQR — concentration alone is insufficient

**Source:** [Original Cremers-Petajisto 2009 paper (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=891719);
[Petajisto Deactivating Active Share rebuttal](http://www.petajisto.net/papers/ffp_original.pdf);
[CAIA: Active Share and Portfolio Concentration — Metrics not Prescriptions](https://caia.org/blog/2024/10/12/active-share-and-portfolio-concentration-metrics-not-prescriptions);
[Occam Investing review](https://occaminvesting.co.uk/concentrating-on-active-share/).

The original Cremers-Petajisto 2009 paper found that high-Active-
Share funds significantly outperformed their benchmarks net of fees.
AQR's replication using the same data found **no statistically
significant evidence** for the effect; subsequent literature largely
agrees Active Share alone is not predictive. *Concentration is a
necessary-but-not-sufficient condition.*

**Why it matters:** our framework's existing reliance on
concentration via ¼-Kelly + cluster cap + Greenberg-style 5%/10 rule
(v2 §9) needs an explicit qualitative pair — concentration paired
with depth-of-research (Hayden 100hr rule, v3 §11) + qualitative
gates (Akre three-legged stool, v3 §10) — to avoid the AQR
critique.

**Technique:** add a `concentration_justification:` block to YAMLs
where weight > 5%. Three sub-fields:
- `research_hours_logged`: must be ≥ 100 (Hayden bar) for weight
  ≥ 5%
- `akre_legs_satisfied`: 0-3 count; must be ≥ 2 for compounding-
  thesis sizing
- `qualitative_edge`: explicit text justifying why we have edge

Without these three, weight is capped at the cluster-cap default.

**Slot:** YAML schema. `src/portfolio.py` enforces the gate — names
without justification get capped at the cluster-cap default rather
than allowed to rise to 5%+.

### 11. Tobias Carlisle Acquirer's Multiple — EV/EBIT as primary screen

**Source:** [Tobias Carlisle — The Acquirer's Multiple (book)](https://www.amazon.com/Acquirers-Multiple-Billionaire-Contrarians-Market/dp/0692928855);
[MOI Global interview](https://moiglobal.com/tobias-carlisle-the-acquirers-multiple-201907/);
[Acquirer's Multiple about page](https://acquirersmultiple.com/about-us/).
Carlisle's discipline:
- Primary screen: **EV / EBIT** (the "Acquirer's Multiple")
- Rank all candidates; concentrate in the cheapest 30 names
- **Each position must perform whether it gets a multiple re-rate or
  not** — i.e., value as if no mean reversion in multiples, then
  require a wide discount to that valuation
- Hold ~30 positions

The "no-mean-reversion" framing is the key insight: he won't *rely
on* multiple expansion for his return.

**Why it matters for us:** the framework's waterfall implicitly bakes
multiple-re-rate into base+bull cases for most YAMLs (LOCAL EV/EBITDA
0.4x → 3x; SZG 0.6x book → 1.1x; etc.). Carlisle's discipline says:
even before multiple expansion, the price-to-FCF arithmetic should
make money. That's a more defensive test than ours.

**Technique:** add an `ev_ebit_steady_state:` field per YAML:
- `ev_ebit_current`: today's multiple
- `ev_ebit_no_rerate_irr`: implied IRR over 5 years assuming
  current multiple stays flat
- If `ev_ebit_no_rerate_irr` < 8%, the position is *only* a multiple-
  re-rate trade — flag as `qualifier.multiple_rerate_dependent`

**Slot:** YAML schema. `src/score.py` validation. The qualifier
doesn't kill the position but limits it to cluster-cap weighting (no
Greenberg 5%+ promotion).

---

## Implementation queue (post-v3 sequencing)

1. **SC 13D / 13D-A poller** (v3 §1, still un-built) — highest signal-
   per-effort; reuses EDGAR infrastructure; activist signal now
   arrives 5 business days faster than pre-Feb-2024.
2. **DOJ FCPA poller** (v4 §1) — RSS-based, lightweight, surfaces
   open investigations that compress re-rate for affected names.
3. **OFAC General License poller** (v4 §3) — JSON feed; sanctions-
   regime restructuring calendar for Argentina/Venezuela/Russia
   residual exposures.
4. **Short interest + utilization + borrow rate fields** (v4 §8-9) —
   YAML schema additions; data source can defer to a feed but the
   schema discipline is immediately useful.
5. **`nol_status:` block for F-archetype YAMLs** (v4 §5) — manual
   back-fill on the ~5 F-archetype YAMLs we have; one hour of work.
6. **`ev_ebit_steady_state:` block** (v4 §11) — Carlisle no-rerate
   IRR check; gates concentration justification.
7. **`concentration_justification:` block** (v4 §10) — gate Greenberg
   5%+ sizing on (a) Hayden 100hr research + (b) Akre legs ≥ 2 +
   (c) explicit qualitative edge text.
8. **F3 butterfly archetype** (v4 §7) — `src/universe_screen.py`
   keyword extension.

Deferred (require additional research or paid feeds):

9. **CFIUS calendar** (v4 §2) — manual maintenance from Treasury
   annual reports; quarterly cadence sufficient.
10. **ITC Section 337 poller** (v4 §4) — secondary; EDIS API
    documented but lower-frequency relevance.
11. **Utilization / borrow-rate data feed** (v4 §8) — paid (S3
    Partners or EquiLend); schema-ready, data-pending.

---

## Sources

- [Gibson Dunn — 2025 Year-End FCPA Update](https://www.gibsondunn.com/2025-year-end-fcpa-update/)
- [Pillsbury — FCPA Enforcement After the Pause](https://www.pillsburylaw.com/en/news-and-insights/fcpa-enforcement-smartmatic-comcel-doj.html)
- [Thomson Reuters — FCPA scrutiny of PE/HF](https://legal.thomsonreuters.com/en/insights/articles/u-s-settlement-signals-increased-scrutiny-fcpa-compliance-within-private-equity-hedge-fund-industry)
- [CRS — CFIUS report IF10177](https://www.congress.gov/crs_external_products/IF/PDF/IF10177/IF10177.39.pdf)
- [OFAC Recent Actions feed](https://ofac.treasury.gov/recent-actions)
- [OFAC Consolidated FAQs](https://ofac.treasury.gov/faqs/all-faqs)
- [The Tax Adviser — Recent developments in Sec. 355 spinoffs](https://www.thetaxadviser.com/issues/2024/mar/recent-developments-in-sec-355-spinoffs/)
- [A&O Shearman — Proposed regulations on spinoff reorgs](https://www.aoshearman.com/en/insights/proposed-regulations-provide-guidance-regarding-certain-aspects-of-spinoffs-and-reorganizations)
- [Wolters Kluwer / AnswerConnect — corporate reorganizations](https://answerconnect.cch.com/topic/bfc473dc7c6d1000a44d90b11c18cbab08/corporate-reorganizations-sec-355-spin-offs-split-offs-and-split-ups)
- [Schultz 2024 — Short Squeezes and Their Consequences (Evidence Investor summary)](https://www.evidenceinvestor.com/post/the-consequences-of-short-squeezes)
- [ScienceDirect — How prevalent are short squeezes? US/EU evidence](https://www.sciencedirect.com/science/article/pii/S0378426625000561)
- [Cremers-Petajisto 2009 (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=891719)
- [Petajisto — Deactivating Active Share rebuttal](http://www.petajisto.net/papers/ffp_original.pdf)
- [CAIA — Active Share and Portfolio Concentration](https://caia.org/blog/2024/10/12/active-share-and-portfolio-concentration-metrics-not-prescriptions)
- [Tobias Carlisle — Acquirer's Multiple about page](https://acquirersmultiple.com/about-us/)
- [MOI Global — Tobias Carlisle interview](https://moiglobal.com/tobias-carlisle-the-acquirers-multiple-201907/)
