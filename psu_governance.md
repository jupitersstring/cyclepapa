# PSU / SOE & Governance Module — Archetype H

Governance events as the recap mechanic. This module extends the
framework with a new archetype: situations where the *catalyst is a
change in who governs* — privatization, state-exit, regulatory-forced
float, board/management reset, or a mandated value-up disclosure —
rather than a balance-sheet restructuring. The balance sheet may be
fine; the discount is a **governance discount**, and the asymmetry
comes from a dated event that compresses it.

Why this deserves its own archetype: the historical multibaggers in our
own case studies that came from this category (Yes Bank's RBI-forced
board reset, Indian Bank's recap, Greek bank HFSF exits, NYCB/Flagstar's
Mnuchin board takeover, Serco's post-scandal management reset) had the
**best base rates in the framework** — because the state/regulator acts
as a non-economic seller or a forced fixer, handing aligned buyers an
entry price no market-clearing process would produce.

---

## H-archetype definition

**Archetype H — Governance reset / state exit.** A sovereign, regulator,
or controlling shareholder executes a governance event that transfers
control, forces float, or mandates shareholder-value discipline. Equity
re-rates as the governance discount closes. Sub-types:

| Sub-type | Mechanic | Template case |
|---|---|---|
| **H1. Strategic privatization** | State sells control to a private/strategic owner | IDBI Bank (live), PIA, Aeromexico re-IPO |
| **H2. Regulatory-forced float** | MPS/free-float rules force the state/promoter to dilute below a threshold | Indian PSB MPS basket (Aug 2026 deadline) |
| **H3. State-exit overhang removal** | Government sells down crisis-era stakes; the overhang discount closes as the seller finishes | NatWest (completed 2025), ABN AMRO, Permanent TSB, HFSF Greek exits (completed) |
| **H4. Mandated value-up regime** | Exchange/regulator mandates capital-efficiency disclosure with teeth | TSE PBR directive (Japan), KRX Value-Up + Feb 2026 tax penalty (Korea), SASAC market-cap KPI (China) |
| **H5. Regulator-forced board/management reset** | PCA-type framework exit, scandal reset, or central-bank-installed management | Yes Bank 2020, Serco 2015, NYCB/Flagstar 2024 |
| **H6. Parent-child unwind** | Listed-subsidiary takeouts forced by governance rules on independence | Japan Prime Market takeout boom (live) |

H combines naturally with G (regulator-forced sector recap): G fixes the
balance sheet, H fixes the governance. The strongest historical setups
had both (Yes Bank, Greek banks).

---

## Governance scorecard dimensions (extend §2 of the methodology)

Score 0–2 like the existing dimensions:

| # | Dimension | 0 (bad) | 1 (mixed) | 2 (good) |
|---|---|---|---|---|
| 15 | **State/promoter stake trajectory** | Creeping up, or sell-down suspended | Static above 75% | Declining on a dated schedule toward a rule threshold |
| 16 | **Governance reset event** | None; incumbent board entrenched | Partial (new CEO, old board) | Full reset: outside chair/CEO + regulator framework exit + auditor upgrade |
| 17 | **Value-up mandate exposure** | No disclosure regime; or filed plan with no teeth | Plan filed; weak enforcement | Subject to a regime with penalties (KRX tax screw, TSE naming, SASAC KPI) and *not yet complied* — the forced catalyst is ahead |
| 18 | **National-service risk** | SOE routinely forced into uneconomic policy actions (fuel subsidies, directed lending, politically-priced tariffs) | Occasional policy drag | Commercial mandate protected by statute, listing covenant, or strategic-investor agreement |
| 19 | **Minority-protection regime** | Squeeze-outs at unfair value routine; weak courts | Mixed | Strong appraisal rights, mandatory-offer rules, active regulator |

**Dimension 18 is the veto.** The Petrobras/Lula fuel-subsidy reversion,
Chinese banks' directed lending, and Vanke's conditional state support
are all national-service failures that wiped otherwise-cheap SOE theses.
An SOE at 0.4× book with national-service risk is correctly priced; the
trade only exists where the governance event *removes* that risk
(privatization, strategic control transfer) or fences it (statutory
commercial mandate).

---

## Systematic feeds (extend §1 of the methodology)

The governance archetype has unusually good *official, scheduled,
machine-readable* feeds — better than the distress archetypes:

| Feed | What it gives | Cadence |
|---|---|---|
| **DIPAM** (dipam.gov.in) | Indian divestment pipeline: strategic sales, OFS announcements, asset monetisation | Ad hoc; budget-cycle heavy |
| **RBI press releases** | PCA framework entries/exits, board supersessions, amalgamation schemes | Ad hoc |
| **SEBI MPS exemption notices** | Which PSUs are exempt from 25% float and until when (current blanket: **Aug 1, 2026**) | Annual-ish |
| **TSE "Management Conscious of Cost of Capital" disclosure list** | Monthly list of which Prime/Standard companies have/haven't disclosed value-up plans — *the laggards are the screen* | **Monthly** |
| **KRX Value-Up disclosure index + corporate tax-credit rules** | Which Korean issuers filed plans; from Feb 2026, high-dividend issuers *lose tax benefits* without one | Monthly |
| **SASAC announcements** | Chinese central-SOE market-value-management KPI changes | Ad hoc |
| **UKGI / HM Treasury, Dutch NLFI, Irish DoF, HFSF/HCAP, Danantara** | State sell-down schedules and completions | Scheduled |
| **METI fair-acquisition guidelines + TOB filings (EDINET)** | Japanese tender offers incl. parent-child takeouts; 2026 FIEA amendment lowers mandatory-TOB threshold to 30% from May 1, 2026 | Daily |

These slot into `src/edgar_poll.py`'s architecture as additional pollers;
the TSE monthly list and KRX index are the two highest-value additions
because they are *enumerated laggard lists* — the screen is pre-built by
the regulator.

---

## The live opportunity set (verified June 2026)

### H1 — IDBI Bank (NSE: IDBI) — the cleanest dated privatization binary

Verified status: Fairfax, Emirates NBD, and Kotak submitted bids in
February 2026; bids came in at ₹40,000–45,000 cr versus a government
reserve valuation near ₹72,000 cr (40–45% gap); the Centre is examining
the legal route to **revive the below-reserve bids with a reserve-price
cut of up to 20%**, with Fairfax the primary counterparty. Emirates NBD
is reconsidering after winning RBL Bank. GoI sells 30.48% + LIC 30.24%
with management control transfer.

- **The asymmetry:** a control transfer to Fairfax (Prem Watsa — the
  CSB Bank playbook at 10× scale) converts a state-run bank at a
  governance discount into a private compounder. India has *never*
  completed a PSB privatization — the first one re-rates the entire
  candidate set.
- **The risk:** the deal has dragged since 2022; valuation-gap standoff
  could continue indefinitely; election-cycle politics can freeze it.
- **Framework read:** H1, Bucket A, catalyst dated (reserve-cut decision
  is live now), triangulation Leg 3 = three sophisticated bidders
  revealed their price (₹40–45k cr — *that is the floor read*).

### H2 — Indian PSB MPS-forced-dilution basket (deadline Aug 1, 2026)

Five banks above the 75% promoter cap, all forced to dilute:

| Bank | Gov stake | Implied dilution to reach 75% |
|---|---|---|
| Punjab & Sind | 98.25% | ~23% of capital |
| Indian Overseas Bank | 96.38% | ~21% |
| UCO Bank | 95.39% | ~20% |
| Central Bank of India | 93.08% | ~18% |
| Bank of Maharashtra | 86.46% | ~11% |

**The playbook nuance:** the MPS event is *supply*, not demand — the
naive trade (buy because float must rise) is wrong on timing. The
asymmetric entry is **into the QIP/OFS print itself** (the same logic
as buying the rights-issue dilution shock at T=0 in the event-timeline
playbook §5): the discount window, then the post-float re-rate from
index inclusion (MSCI/FTSE free-float methodologies) and institutional
ownership normalisation. Expect deadline extension risk — the
government has extended MPS deadlines twice before; an extension
deflates the near-term event.

### H3 — European state-exit overhangs

- **ABN AMRO** (AMS) — Dutch NLFI sell-down continuing; the overhang
  discount closes mechanically as NLFI crosses below blocking
  thresholds. NatWest 2025 completion is the template: the stock
  re-rated ~50% into and after the final placement.
- **Permanent TSB** (Euronext Dublin) — Irish state exit pending;
  small-cap, less liquid, bigger discount.
- **Raiffeisen International** (VIE) — not a state exit but the same
  shape: a single non-economic overhang (Russia exposure) at a deep
  discount with a datable resolution.

### H4 — Value-up laggards (Korea + Japan)

Korea has substantially re-rated (KOSPI through 5,500; Value-Up index
+130% since Sept 2024; ~51% of market cap has filed plans). **The broad
Korea governance trade is late-cycle — completed-arc territory.** The
residual asymmetry is in the *laggards now facing the February 2026 tax
penalty*: high-dividend-capacity issuers that have NOT filed value-up
plans lose tax benefits — a forced, dated catalyst on an enumerable
list. Screen: KRX non-filer list ∩ payout capacity >40% ∩ holdco NAV
discount >50%.

Japan: >70% of Prime Market has disclosed; the trade has moved from
"who will disclose" to **parent-child takeouts** (H6): listed
subsidiaries with majority-owner parents facing the independence rules,
where the rational parent response is a TOB. The May 2026 FIEA
amendment (mandatory TOB threshold down to 30%) accelerates this.
Screen: Prime/Standard subsidiaries >50% parent-owned ∩ PBR <1 ∩
parent with balance-sheet capacity.

### H5 — Regulator-forced resets (watch list)

- RBI PCA exits historically front-ran multi-year re-rates (IOB, UCO,
  Central Bank all exited PCA 2021–22 before the 2022–24 PSU re-rate).
  No Indian bank is currently in PCA — the next *entries* (a stress
  event) will seed the next cohort.
- Bangladesh: post-Hasina central-bank board resets at S Alam-linked
  banks (Islami Bank et al.) are the live frontier version — option-
  sized only.

---

## SOE-specific red flags (extend §2.3)

- **National-service reversion** — any history of directed lending,
  subsidised pricing, or policy-driven capex within the last two
  political cycles, without a subsequent statutory fence
- **Election within the catalyst window** — privatizations and state
  sell-downs freeze in election years (India 2029 national; state
  elections matter for PSB appetite)
- **Golden share / strategic-sector veto** retained post-privatization
- **Squeeze-out at "fair value" risk in weak-appraisal jurisdictions** —
  the H6 parent-child trade in jurisdictions with weak minority courts
  becomes a cram-out at the lowball price
- **Deadline-extension habit** — MPS deadlines have been extended
  twice; treat regulatory deadlines as soft until the QIP/OFS bankers
  are mandated
- **Valuation-gap standoffs** — IDBI's 40–45% bid-ask gap shows the
  state can simply *not sell*; a non-economic seller is also a
  non-forced seller

---

## How this integrates

1. **Methodology §3.1**: Archetype H added to the taxonomy table.
2. **Scorecard**: dimensions 15–19 above; dimension 18
   (national-service risk) is a veto gate alongside #11 and #13.
3. **Feeds**: DIPAM / RBI / SEBI-MPS / TSE-monthly / KRX / NLFI-UKGI
   pollers join §1; TSE and KRX lists are the priority builds because
   the regulator publishes the laggard screen for us.
4. **Candidates**: IDBI.yaml enters as Tier 2 (dated binary, awaiting
   reserve-cut decision). The MPS basket, ABN, PTSB, Korea laggards,
   and Japan parent-child names enter `universe.md` as enumerated
   sub-baskets pending per-name work.
5. **The completed-arc discipline applies**: broad Korea value-up and
   Greek/NatWest state exits are *done* — they are proof of the
   archetype's base rate, not current trades.
