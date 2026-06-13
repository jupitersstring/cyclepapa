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

## The live opportunity set (verified June 2026) — non-India focus

India is excluded from the active opportunity set at user direction;
the Indian H1/H2 mechanisms (IDBI Bank privatization, PSB MPS-forced
dilution by Aug 1, 2026) remain documented in
`psu_governance_india_archive.md` as historical template cases and
base-rate inputs only, not as investable names.

### H3 — European state-exit overhangs (the cleanest live set)

The mechanic: a non-economic seller (sovereign or post-crisis state
holding vehicle) has telegraphed a sell-down. The overhang discount
mechanically closes as the seller crosses below blocking thresholds.
NatWest 2025 is the template: the stock re-rated ~50% into and after
HM Treasury's final placement.

- **ABN AMRO (AMS: ABN)** — Dutch NLFI sell-down continues; each
  placement compresses the overhang discount. Watch NLFI press
  releases. Liquid mid-cap; no Bucket-A purity issue, no
  national-service drag (the bank operates commercially).
- **Permanent TSB (Euronext Dublin: PTSB)** — Irish state exit
  pending; smaller, less liquid, materially bigger discount; closing
  cleanly behind ABN AMRO in size but ahead in re-rate distance.
- **Raiffeisen International (VIE: RBI)** — *adjacent* H3: not a
  state exit but the identical shape — a single non-economic overhang
  (Russia exposure, OFAC/sanctions optics) at a deep discount with a
  datable resolution (Strabag swap, court rulings, eventual orderly
  exit). The discount is the overhang; the catalyst is its removal.
- **NatWest (LSE: NWG)** — *completed-arc reference*; do not chase.

### H4 — Korea value-up tax-penalty laggards

Broad Korea has re-rated (KOSPI through 5,500, Value-Up index +130%
since Sept 2024, ~51% of market cap has filed plans). The broad
governance trade is late-cycle — completed-arc territory. The residual
asymmetry is in the laggards now facing the **February 2026 corporate
tax-credit rule**: high-dividend-capacity issuers that have NOT filed
value-up plans lose tax benefits.

Screen recipe (built from regulator outputs, no scraping needed):

- KRX non-filer list (regulator publishes monthly)
- ∩ payout capacity > 40% (issuers structurally capable of qualifying)
- ∩ NAV discount > 50% for holdcos, or PBR < 0.8 for opcos
- ∩ no national-service risk (dimension 18 ≥ 1)

The chaebol holdco discount sub-screen is the densest sub-basket.
Cross-shareholding unwinds (treasury-share cancellation requirement,
introduced July 2025) accelerate the catalyst calendar.

### H5 — Regulator-forced board / management resets (watch only)

The strongest historical setups in this archetype (Yes Bank 2020
RBI-forced, Serco 2015 post-scandal, NYCB/Mnuchin 2024) all required
*an event to seed them*: a regulator using its supervisory authority
to install a new board, a scandal forcing CEO departure, or a
central-bank-mandated capital plan.

Watch (not investable today):
- Bangladesh post-Hasina central-bank board resets at S Alam-linked
  banks (Islami Bank et al.); EM-frontier H5, option-sized only;
  litigation overhang plus dollar-shortage tail risk
- Türkiye: any post-Şimşek removal scenario would force a CBRT-led
  bank-recap cohort
- US regional banks under FDIC consent orders — sectoral candidate
  pool, no current name yet

### H6 — Japan parent-child takeouts (live and dense)

Disclosure mechanic dominant for the past two years. The trade has now
moved from "who will disclose" to *who will get taken out* — listed
subsidiaries with majority-owner parents facing the independence
rules, where the rational parent response is a tender offer (TOB).

The **May 1, 2026 FIEA amendment** drops the mandatory-TOB threshold
to 30% of voting rights from 33⅓%. Effects:

- Lowers the squeeze-out trigger across the entire Prime Market
- Forces parents at 30–33% holdings to either step back or commit to a
  full takeout
- Accelerates the takeout calendar for any majority-owned subsidiary
  with PBR < 1

Screen recipe (built from EDINET + TSE monthly disclosure list):

- Prime/Standard listed subsidiaries with >50% parent ownership
- ∩ PBR < 1.0
- ∩ parent with cash-on-hand > target market cap × 1.2
- ∩ no value-up plan filed by parent or sub (worst position to defend)

Recent template TOBs (post-disclosure-regime, pre-FIEA-30%) — useful
priors for sizing the base rate: NTT/NTT Data ¥2.37tn (May 2025);
Hitachi-subsidiary roll-ups across the post-2022 cycle.

### H3 candidates — adjacent sovereign / strategic-anchor variants

These are not state *exits* but the mirror — *state entries* at terms
that protect minority common while shifting governance to a credible
operator:

- **Eutelsat (EPA: ETL)** — A1+F+H hybrid: French State APE,
  Bharti Space, UK Government, CMA CGM all entered at €4.00 reserved
  while rights cleared at €1.35 (covered separately in `final.md`);
  governance is now multi-sovereign-anchored
- **Worldline (EPA: WLN)** — A1+H: Bpifrance + CASA + BNP + BFCM bloc
  with 9.6% Bpifrance ending stake; French sovereign-strategic
  governance reset (covered separately)
- **Hawaiian Electric (NYSE: HE)** — A1+G+H: Hawaii Act 258 + Maui
  settlement structure imposes a quasi-statutory governance regime
  on a private utility

These already sit in Tier 1 of the generated screen; the H tag here
just makes the governance leg explicit.

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
