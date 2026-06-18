# Event Taxonomy & Practitioner Patterns

Bridges the special-situations playbook (the prose document at
`docs/event_playbook.md`) to the YAML-driven framework. Adds two
dimensions the framework was missing:

- **Event type** — the specific catalyst (one of the 23 canonical
  event types from the playbook). Different from `archetype` (deal
  mechanic A1/A2/B/C/D/E/F/G/H) because the same archetype can produce
  different events. E.g. a sovereign A2 deal can be `definitive_ma`
  (DoD partnership) or `regulatory_approval` (state aid).
- **Practitioner pattern** — the historical activist/sponsor style
  the deal most resembles. Provides a hit-rate prior and a sizing
  template.

## The 23 canonical event types

From the playbook §3 ranking model:

| Code | Description | Filing equivalents | Typical archetype overlap |
|---|---|---|---|
| `activist_stake` | New 5%+ activist beneficial-ownership filing | 13D, 13G, TR-1, PSC | F, G, H |
| `activist_escalation` | Amendment to existing stake with public agenda | 13D/A, RNS letter | F, G |
| `proxy_fight` | Nominee slate or consent solicitation | DEFC14A, RNS notice of GM | H |
| `cooperation_settlement` | Board-seat / cooperation agreement closing fight | 8-K Item 5.02 + 8.01 | H |
| `strategic_review` | Board announces review of alternatives | 8-K Item 8.01, RNS strategic-review notice | A1, A2, B, C, H |
| `definitive_ma` | Signed merger agreement | DEFM14A, S-4, 8-K Item 1.01, RNS 2.7 | A1, B, F |
| `tender_offer` | 3rd-party cash tender | SC TO-T, 14D-9 | C, F |
| `issuer_tender` | Company tendering own shares | SC TO-I | C |
| `spin_off` | Separation announcement | Form 10, 8-K Item 2.01 | F (post-spin) |
| `asset_sale` | Material disposition | 8-K Item 2.01, RNS Cat-1 | C, E |
| `special_dividend` | Material capital return | 8-K Item 8.01 | C |
| `buyback` | Buyback authorization | 8-K Item 8.01, RNS | C |
| `board_change` | Director resignation / appointment | 8-K Item 5.02 | H |
| `ceo_change` | CEO/CFO change | 8-K Item 5.02 | H |
| `bankruptcy` | Ch.11 / receivership filing | 8-K Item 1.03 | F |
| `restructuring` | Out-of-court LME or scheme | T-3, 8-K Item 2.04, RNS scheme circular | C, E, F |
| `litigation` | Material litigation event | 8-K Item 8.01 | F |
| `regulatory_approval` | Sovereign state-aid or framework approval | 8-K Item 8.01, EU Commission decision | A2, G |
| `regulatory_block` | Regulator blocks deal | 8-K Item 8.01 | n/a (kill event) |
| `cross_holding_reduction` | Disposal of cross-shareholdings or MCB conversion | RNS, scheme effective notice | F, H |
| `delisting` | Going-private / delisting | 8-K Item 3.01, 15-12B | C, F |
| `rights_issue` | Underwritten rights offering | S-1, prospectus, RNS | A1, G |
| `pre_recap_watch` | Pre-event watch with named trigger | n/a — internal tag | n/a |
| `spinoff` | Tax-free parent distribution of subsidiary stock; includes partial spinoffs / carve-outs, reverse spinoffs, Reverse Morris Trust | **Form 10-12B**, 10-12B/A, S-1 (spinco IPO), 8-K Item 2.01, DEF 14A separation vote | F (post-spin), C (parent reset) |
| `nol_shell` | Section 382 NOL preservation + monetisation; tax-benefits-preservation rights plan | 8-K Item 8.01 NOL rights plan, S-4 with §382 disclosure | F (post-bankruptcy shell), C (M&A vehicle) |
| `spac_trust_arb` | Buying at/below SPAC trust NAV for T-bill yield + redemption + deal optionality | SPAC S-1, S-4 deal disclosure, proxy with redemption mechanics | C (option-shaped) |
| `odd_lot_tender` | Tender offer with odd-lot (<100 share) provision — bought without proration | SC TO-I / SC TO-T with odd-lot section, SC 14D-9 | C |
| `mlp_buyin` | General partner buys in MLP units; conflicts committee bumps lowball | 13D from GP, SC 13E-3, special committee disclosure | C |
| `index_reconstitution` | Forced selling/buying on Russell/MSCI/S&P add or delete | n/a — public reconstitution schedule | n/a (technical flow) |
| `dark_company` | Form 15 deregistration / "going dark"; non-reporting OTC | Form 15-12B / 15-12G | F (post-deregistration orphan) |
| `holdco_discount` | Listed parent vs look-through NAV gap; dual-class voting-premium arb | 10-Q segment notes, 13D simplification proposals | C |
| `scheme_of_arrangement` | UK/AU/CA court-sanctioned bid structure; 75% value + majority number vote | RNS Rule 2.7, scheme circular, ASX scheme booklet, SEDAR+ plan of arrangement | C (binding takeover) |
| `spruchverfahren` | German judicial appraisal post-squeeze-out / domination-and-profit-transfer agreement | German court filings; not in EDGAR | C (post-deal top-up arb) |
| `post_bankruptcy_orphan` | Newly emerged Ch.11 equity, indiscriminately ignored | Plan of Reorganization confirmation, ASC 852-10 fresh-start | F |

## Practitioner patterns

Six patterns drawn from the playbook §2. Each has a *fingerprint*
that identifies it in our framework and a *historical-prior* on
risk/reward.

### Pattern 1 — Pershing pattern (high-quality + governance unlock)

**Fingerprint:** Cash-generative business + identifiable governance
or structural discount + minimal capital-markets dependency.
Historical comp: Canadian Pacific 2011 (proxy + Hunter Harrison
CEO swap = $2.6bn realised profit). GGP 2010 (bankruptcy + spin
of Howard Hughes).

**Maps to framework:**
- Bucket: A (listed common is the trade)
- Archetype: H (governance reset) most often; H+G when regulatory
- Sizing template: medium (4–8% for high-conviction)
- Risk profile: moderate downside if business sound; high upside
  if reset works

**Active in framework today:** HE (Hawaii Act 258 = quasi-statutory
governance unlock on a regulated cash-generative utility).

### Pattern 2 — Icahn pattern (cheap assets + pressure)

**Fingerprint:** Trading well below SOTP / asset value + identifiable
pressure lever (board, sale, dividend, spin). Historical comp: eBay/
PayPal break-up 2014–15.

**Maps to framework:**
- Bucket: A or C → B (depending on whether legacy survives)
- Archetype: C (asset sale) or F (post-spin)
- Sizing template: medium (3–6%)
- Risk profile: bounded downside when underlying assets concrete

**Active in framework today:** None. The closest would be Salzgitter
(SZG) hidden Aurubis stake, but that's sovereign-anchor not
shareholder-pressure.

### Pattern 3 — Elliott pattern (process engineering)

**Fingerprint:** Strategic-review activism with PE buyer universe
identifiable; complex situations requiring negotiation engineering.
Historical comp: Citrix 2021–22 ($104/share $16.5bn close); Japan
cross-shareholding letters.

**Maps to framework:**
- Bucket: A or B (depending on take-private outcome)
- Archetype: H most often (governance); event type
  `strategic_review` or `definitive_ma`
- Sizing template: medium (3–6%)
- Risk profile: high upside if review converts; meaningful
  downside if review formally ends

**Active in framework today:** None at the activist-led stage. Could
add: Banco Sabadell (resisting BBVA; April 2026 EGM); Mediobanca
(Caltagirone/Delfin board fight).

### Pattern 4 — Third Point pattern (catalyst-rich flexibility)

**Fingerprint:** Mix of activist, risk-arb, distressed credit
across one issuer's cap stack. Historical comp: Sony 2013
(entertainment carve-out proposal — rejected but surfaced hidden
asset).

**Maps to framework:**
- Bucket: cross-tranche (debt + equity simultaneously)
- Archetype: multi (any of F, H, C)
- Sizing template: depends on tranche
- Risk profile: depends on tranche selected

**Active in framework today:** None. Framework currently runs
equity-only.

### Pattern 5 — TCI / Hohn pattern (PE-style + patient engagement)

**Fingerprint:** Deep fundamental underwriting + long-duration
constructive engagement + governance / capital-allocation focus.
Historical comp: ABN AMRO 2007 (sale activism); Japan
cross-shareholding pressure.

**Maps to framework:**
- Bucket: A (listed common is the trade)
- Archetype: A1 or H (sovereign-strategic or governance)
- Sizing template: large (5–10%)
- Risk profile: lower drawdown but longer time to convexity

**Active in framework today:** LOCAL (Niel/Lévy patient
microcap engagement), ELUX-B (Wallenberg multi-decade pattern).

### Pattern 6 — Bastian pattern (micro-cap special-situations)

**Fingerprint:** Underfollowed micro-cap + concentrated position +
self-help / asset sale / liquidation / explicit planned exit.

**Maps to framework:**
- Bucket: A (listed common)
- Archetype: E (national bankruptcy framework) or C (asset sale)
- Sizing template: large per-name within micro-cap allocation
- Risk profile: high dispersion; explicit catalyst date required

**Active in framework today:** LOCAL fits this pattern almost
exactly — micro-cap French stub, net cash floor, explicit FY2027
plan.

### Pattern 7 — Sovereign-anchor pattern (framework-native, not in playbook)

**Fingerprint:** State or sovereign-aligned entity takes equity +
debt + offtake / price floor. Multi-decade contractual support.
*Not covered by the playbook because it's a 2024–26 vintage
innovation*; framework labels it Archetype A2.

**Maps to framework:**
- Bucket: A
- Archetype: A2
- Sizing template: medium-large (5–8%)
- Risk profile: lower left tail (sovereign floor), upside on
  operational ramp

**Active in framework today:** LAC, UREE, MP, TMQ (pending), DRX
(pre-anchor), SZG (pre-anchor).

### Pattern 9 — Greenblatt 4-form spinoff specialist

**Fingerprint:** Systematic SEC filing monitoring of **8-K + Form 10/10-12B
+ 13D + S-4**, then deep-read information statements for insider-incentive
clues (stock options / restricted stock in the SpinCo prospectus reveal
where management's interest sits).

**Maps to framework:**
- Bucket: A (spin equity is the trade) or B (post-spin parent stub)
- Archetype: F (post-spin) most often; C (parent recap)
- Event type: `spinoff`
- Sizing template: medium (3–6%) per name; concentrated portfolio
- Risk profile: spinoffs +10% / yr above S&P 500 in first 3 yrs per
  Penn State 25-yr study cited in Lynch's *Stock Market Genius* foreword

**Active in framework today:** None — framework has no spinoff candidate
YAMLs. `src/spinoff_radar.py` exists to surface them but no YAML has
been built yet.

### Pattern 10 — Tauraitis repeat-pattern micro arbitrageur

**Fingerprint:** Weekly run through regulatory filings + datasets +
blogs + forums + FinTwit + hedge-fund letters. Two-question filter:
"Why does the setup/spread exist?" + "What's the downside?" — demands
heads-I-win-tails-I-don't-lose-much. Specialises in **odd-lot tenders +
MLP buy-ins + small/microcap mergers in unloved sectors**. Reported
+640% since 2017 / 100+ ideas/year.

**Maps to framework:**
- Bucket: A
- Archetype: C (LME / tender) most often; F (spin-off)
- Event types: `odd_lot_tender`, `mlp_buyin`, `definitive_ma`
- Sizing template: small (0.5–2% per name, basket of 50+ names)
- Risk profile: tiny capacity; doesn't scale; "few hundred to few
  thousand dollars per account" per Dalius

**Active in framework today:** None. Framework runs concentrated
position sizing; Tauraitis pattern is diversified small-arb.

### Pattern 11 — Klarman counter-cyclical distressed

**Fingerprint:** Large cash position (30–50%) as option value; deploys
aggressively in dislocations (Feb 2008 post-Peloton; post-Lehman ~$100m/day).
Targets bankrupt debt, financially-distressed credit, post-emergence
orphans. Distressed-debt examples: Lehman, Icelandic banks (Kaupthing/
Glitnir/Landsbanki), Puerto Rico, CIT bonds at 65¢. Holds 30–50 positions.

**Maps to framework:**
- Bucket: B (fulcrum debt) or C (post-emergence common)
- Archetype: F (post-bankruptcy orphan); credit-class
- Event types: `bankruptcy`, `restructuring`, `post_bankruptcy_orphan`
- Sizing template: cash-now + concentrate-into-dislocation
- Risk profile: relies on macro / credit-spread leading indicator

**Active in framework today:** None — framework runs equity-only. Could
add: Klarman's HY-spread + CDS leading-indicator overlay to the macro
filter.

### Pattern 12 — Horizon Kinetics index-orphan + spinoff specialist

**Fingerprint:** Targets **index orphans** — "equities that, due to
liquidity characteristics or industry categorization, have not benefitted
from the influx of assets into passive vehicles." Theory rooted in Stahl/
Bregman 1996 "Spin-offs Revisited" paper. Publishes **Spin-Off Report**
since 1996 + European / Global Spin-Off and Restructuring Report. Runs
Kinetics Spin-Off and Corporate Restructuring Fund (LSHUX).

**Maps to framework:**
- Bucket: A
- Archetype: F (post-spin orphan), C (post-rights orphan)
- Event types: `spinoff`, `index_reconstitution`
- Sizing template: medium-large basket
- Risk profile: structural pricing anomaly; long-duration

**Active in framework today:** None directly. Framework's
universe_screen identifies index-orphan-shaped names (small-cap
post-recap) but doesn't tag them as such.

### Pattern 13 — DeMuth busted-deal / antitrust binary specialist

**Fingerprint:** Be as knowledgeable as possible on all public filings,
then talk to "everyone described — board, management, competitors,
vendors, customers." Prices binary outcomes by finding true odds vs
market-implied probability. **Specialises in broken deals, antitrust-
blocked mergers, busted biotechs, SPACs** with deep-pocketed sponsors.

**Maps to framework:**
- Bucket: A (target equity) or C (downside floor)
- Archetype: C (LME), F (busted biotech), B (SPAC trust)
- Event types: `definitive_ma`, `regulatory_block`, `spac_trust_arb`,
  `tender_offer`
- Sizing template: small-medium with explicit downside floor
- Risk profile: binary by construction; "correlations go to one" in
  crisis

**Active in framework today:** None. Would require event-by-event
antitrust / regulator tracking.

### Pattern 14 — Walker tender-radar / repeat-name follower

**Fingerprint:** "Subscribes to all activist filings and all tender
offering filings through the SEC." Screens microcaps, reads 10-K
sections 1/1A/7 then balance sheet + 5 yrs financials. Edge from
**following companies for years** (Discovery, IAC/Match, Angie's List)
+ externally-sourced ideas. Deep SPAC coverage (PSTH/UMG).

**Maps to framework:**
- Bucket: A
- Archetype: C (tender) or B (SPAC)
- Event types: `tender_offer`, `odd_lot_tender`, `spac_trust_arb`,
  `activist_stake`
- Sizing template: small-medium, repeat-name concentrated
- Risk profile: needs years of context per name

**Active in framework today:** None. Closest is the YAML history-block
discipline which preserves multi-year context per name.

### Pattern 8 — MCB-cascade pattern (framework-native)

**Fingerprint:** Mandatory convertible bond restructuring with
founder participation + multi-year lockup. Equity is residual claim
post-conversion. *Specific to 2024–26 Chinese property cycle*.

**Maps to framework:**
- Bucket: B (new post-MCB common is the trade)
- Archetype: F + A (post-emergence + sovereign-adjacent if SOE)
- Sizing template: small (2–4% per name; basket-size 5–10%)
- Risk profile: binary on policy axis

**Active in framework today:** SUNAC (founder 23% MCB + 6yr lock).

## Mapping the 13 YAMLs to event types + practitioner patterns

| Ticker | Event type | Practitioner pattern | Sizing band |
|---|---|---|---|
| LOCAL | `restructuring` + `cross_holding_reduction` | Bastian + TCI | 3–6% |
| LAC | `regulatory_approval` (DOE restructuring) | Sovereign-anchor | 4–6% |
| UREE | `definitive_ma` (DoC LOI → finalisation) | Sovereign-anchor | 4–6% |
| WLN | `rights_issue` + `definitive_ma` (reserved cap inc) | Sovereign-anchor + TCI | 4–6% |
| ETL | `rights_issue` + `definitive_ma` | Sovereign-anchor | 3–5% |
| ELUX-B | `rights_issue` | TCI | 4–6% |
| HE | `restructuring` (settlement) + `regulatory_approval` | Pershing | 4–6% |
| MP | `definitive_ma` (DoD partnership) | Sovereign-anchor | 3–5% (already 5x) |
| TMQ | `definitive_ma` (Pentagon pending) | Sovereign-anchor | 1–3% (pre-close) |
| DRX | `pre_recap_watch` (BECCS) | Sovereign-anchor | 1–3% (pre-commit) |
| SZG | `regulatory_approval` (EU SA) + `pre_recap_watch` (KfW) | Sovereign-anchor | 2–4% |
| SUNAC | `restructuring` + `cross_holding_reduction` (MCB conv) | MCB-cascade | 2–4% |
| MPVD | (PASS — `bankruptcy` watch) | — | 0% |

## How the playbook's 5-axis ranking interacts with my scorecard

The playbook proposes a 100-point score across 5 axes:

- Catalyst certainty: 25
- Valuation gap / SOTP discount: 20
- Balance-sheet survivability: 15
- Quality of sponsor / activist / bidder: 15
- Governance / incentive alignment: 10
- Procedural clarity and timetable: 10
- Liquidity / borrow / tradeability: 5

My existing 14-dimension scorecard maps to this as follows:

| 5-axis | My dims that contribute |
|---|---|
| Catalyst certainty | #11 (operating catalyst), C7 status, vintage |
| Valuation gap | #9 (alignment gap), Leg 1 (PF valuation) |
| Survivability | #14 (liquidity), #13 (second-RX risk), #5 (maturity wall) |
| Sponsor quality | #9 (anchor identity), #1 (who funds new money) |
| Governance | #8 (MIP), #12 (governance reset), #18 (national-service risk) |
| Procedural clarity | #2 (issue price discount), #3 (backstop), #6 (cap stack) |
| Liquidity | universe.md size_class field |

The 5-axis model is more weighted toward catalyst + valuation gap;
my scorecard weights more toward alignment + structure. The two are
complementary: use the 5-axis to surface candidates from the
event-driven universe; use my scorecard to underwrite them once
surfaced.

## Bucket-specific elevation thresholds

From the playbook §3, applied to the framework's tier discipline:

| Bucket | Elevate to T1 when | Currently in T1 |
|---|---|---|
| Activism | score ≥ 75 + stake >5% + agenda | none |
| Strategic review / sale | score ≥ 80 + formal review + plausible buyer set | none |
| Merger arb | score ≥ 85 + signed deal + spread sized | none |
| Spin-off / break-up | score ≥ 75 + terms knowable | none |
| Distressed / bankruptcy | score ≥ 80 + fulcrum identified | none |
| Sovereign-anchor (framework-native) | EV ≥ 2.30× + 3/3 triangulation + dated C7 | LAC, UREE, WLN, ETL, ELUX-B, HE, MP, LOCAL |
| MCB-cascade (framework-native) | founder lock + state-aligned co-anchor + EV ≥ 2.0× | SUNAC |

The framework's existing tier discipline is *implicitly* applying
sovereign-anchor and MCB-cascade rules but not the activism /
arb / spin / distressed rules. That's why my T1 currently has zero
activist names — the universe.md doesn't surface them because no
event-extraction layer exists.

## Concrete next step (highest leverage)

Build `src/events.py` — an event-type extractor over universe.md
notes and (eventually) primary filings, using the 23-event regex
set from the playbook §appendix. This would:

1. Tag every universe.md row with one or more event types
2. Enable the per-bucket elevation thresholds (which require event
   type, not just archetype)
3. Surface activist patterns the framework currently misses
4. Generate the event-funnel + signal-frequency dashboards the
   playbook recommends

Until that exists, the practitioner pattern + event-type fields are
manually tagged on YAMLs (this doc). Building the extractor is the
next iteration.
