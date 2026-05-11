# Capital-Structure Screening for Long Conviction

A practical playbook for finding the next multibagger inside ugly recaps. Two
hard problems to solve:

1. **Discovery.** How do you systematically surface the right deals out of the
   thousand restructurings, rights issues, exchange offers, and UCC filings
   that hit the wires every week?
2. **Alignment.** Once you have a candidate, how do you tell — fast — whether
   the deal is a *rescue for legacy common* or a *creditor takeover dressed up
   as one*?

The original framework below (UCC signals, Tier-S/A/B actions, historical case
studies) sets the vocabulary. The two new sections — **Discovery Pipeline**
and **Alignment Scorecard** — turn it into a process.

---

## 1. Discovery Pipeline (RSS + form filters + keyword regex)

The goal is a daily inbox of 5–20 candidates pulled automatically from
primary sources, not a weekly trawl through PitchBook or Bloomberg headlines.

### 1.1 Primary regulatory feeds (free, RSS/Atom)

| Jurisdiction | Source | Feed | What to pull |
|---|---|---|---|
| US | SEC EDGAR | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom` | 8-K, 6-K, S-3/424B, 13D/G, T-3, 15-12B, NT-10 |
| US | SEC EDGAR full-text search | `efts.sec.gov/LATEST/search-index?q=...&forms=...` (JSON) | Keyword + form-type slice |
| Canada | SEDAR+ | `https://www.sedarplus.ca/...` (Atom per issuer) | Material change reports, rights offering circulars |
| UK | LSE RNS | `https://www.londonstockexchange.com/news?tab=news-explorer` (RSS per ticker) | Rights issues, scheme of arrangement, T+12 announcements |
| EU | OAM hubs (AMF, BaFin, AFM, FINMA, ESMA) | Per-regulator RSS | Prospectuses, ad-hoc disclosures, StaRUG/WHOA notices |
| Australia | ASX Company Announcements | RSS per ticker | Capital raisings, voluntary administration |
| India | BSE/NSE corporate announcements | RSS / API | Rights issues, QIP, FPO |
| Court dockets | CourtListener (Free Law Project) RECAP | RSS per case + bankruptcy keyword alerts | First-day declarations, DIP motions, plan/disclosure statements |
| UCC | State Secretary of State portals + commercial aggregators (UCCDirect, Capitol Services) | Per-debtor saved search | New/amended/terminated UCC-1 |

Most state SOS sites do not expose RSS. The practical workaround is a
twice-weekly scrape of saved-debtor searches for the watchlist (200–500
tickers), or a paid feed (UCCDirect, Wolters Kluwer Lien Solutions, CSC).

### 1.2 Form-type and item filters

Cast a wide net by form, then narrow by item code:

- **8-K Item 1.01** (entry into material definitive agreement) — credit
  agreements, indentures, backstop agreements
- **8-K Item 1.03** (bankruptcy or receivership)
- **8-K Item 2.03 / 2.04** (creation of / triggering events under direct
  financial obligations)
- **8-K Item 3.02 / 3.03** (unregistered equity sales; modification of rights
  of security holders)
- **8-K Item 5.07** (vote results — restructuring approvals)
- **6-K** (foreign private issuers) — usually the only window into
  Petra/Viaplay/Brait-style situations
- **13D + Schedule 13D/A amendments** — anchor investor disclosure, group
  formation
- **S-3 / 424B5** prospectus supplements — equity issuance at the moment of
  pricing
- **T-3** — new indenture qualification (often signals exchange offer
  mechanics)
- **DEF 14A** — restructuring votes, MIP approvals
- **NT-10** — late filer, often a precursor to distress

### 1.3 Keyword regex (run against feed titles + first page of filing)

Tier these so the inbox is sorted by signal strength.

```
TIER_S = r"\b(tender offer|exchange offer|consent solicitation|" \
         r"rights (offering|issue)|backstop(ped)? (commit|agreement)|" \
         r"debt[- ]for[- ]equity|loan[- ]to[- ]equity|" \
         r"capped call|convertible (senior )?notes|" \
         r"maturity extension|amend(ed)? and extend|" \
         r"scheme of arrangement|StaRUG|WHOA|" \
         r"prepackaged plan|plan of reorganization|" \
         r"UCC termination|lien release|" \
         r"DIP financing|exit financing)\b"

TIER_A = r"\b(upsized revolver|repriced term loan|" \
         r"refinanc(e|ing)|early redemption|call notice|" \
         r"capital raise|primary offering|" \
         r"strategic investor|anchor investor|" \
         r"private placement|PIPE)\b"

TIER_B = r"\b(secured (term )?loan|second[- ]lien|" \
         r"warrants? (attached|issued)|" \
         r"PIK toggle|payment in kind)\b"

RED_FLAGS = r"\b(going concern|covenant waiver|" \
            r"forbearance agreement|payment default|" \
            r"missed (coupon|interest)|" \
            r"strategic alternatives|hire(d)? (financial )?advisor)\b"
```

`RED_FLAGS` matched *before* a `TIER_S` event is the highest-value early
warning lane — those are the 3–9 month leading indicators of the deal that
matters.

### 1.4 Secondary feeds (commentary, distress press)

- Reuters tag feeds (`/business/restructuring/`, `/markets/deals/`)
- FT Alphaville RSS
- Bloomberg Terminal `NSE BANKRUPTCY` / `NSE RECAPITALIZATION` (paid)
- *Petition* (Substack RSS) — concise weekly distress digest
- Reorg / Debtwire / 9fin headlines (paid; trial APIs exist)
- Trustee / agent press release pages: Kroll Restructuring Administration,
  Epiq, Stretto, Prime Clerk, DF King
- Court docket trackers: Stretto, Kroll, BMC Group public docket pages

### 1.5 Triage cadence

- **Daily (15 min):** sort overnight feed by tier; tag candidates; queue
  filings for deep read.
- **Weekly (60 min):** run watchlist UCC search; reconcile against bond
  trustee notices; refresh maturity wall for every name on the list.
- **Monthly:** prune candidates that have not progressed (no 8-K Item 1.01,
  no anchor backstop disclosed, no maturity extension filed).

The discipline is binary: a name either advances along the deal pipeline or
falls out. No "interesting, watching" purgatory.

---

## 2. Alignment Scorecard

Most restructurings rescue the enterprise. Only a subset rescue *legacy
common*. The scorecard below is the filter — score each candidate 0–2 on each
dimension; ≥10 of 14 is investable, <7 is a "creditors-only" deal.

| # | Dimension | 0 (bad for common) | 1 (mixed) | 2 (good for common) |
|---|---|---|---|---|
| 1 | **Who funds the new money?** | Creditors via debt-for-equity, or new PE sponsor at a court-set price | New strategic with no prior position | Pro-rata rights to existing holders; insiders/promoter writing a real cheque |
| 2 | **Issue price vs. market** | At a forced/court price or with a deep discount + backstop fees + sweetener warrants | Market-discount rights (20–40% TERP discount) but pro-rata access | At or near market; old common can defend pro-rata |
| 3 | **Backstop terms** | Backstoppers take rump + fees + warrants + board seats | Fee-only backstop | Backstop by existing largest holder at cost; no warrant kicker |
| 4 | **Dilution to old common** | >80% (e.g., Atos 90.8% to creditors) | 40–80% | <40% post-money |
| 5 | **Maturity wall removed** | <18 months runway → bridge to next restructuring (Spirit) | 18–36 months | 36+ months clean, no springing maturities |
| 6 | **Post-deal cap stack simplicity** | PIK toggles, multiple secured layers, IP carve-outs, springing liens | One messy layer to clean up | Single tranche, long maturity, covenant-lite |
| 7 | **UCC / lien movement** | New priming liens stacked on top of old | Mixed (new + terminations) | UCC-1 terminations dominate; lien release filings present |
| 8 | **Management equity plan** | Cash retention bonuses only; no skin | MIP struck at pre-deal price | MIP struck at recap price; CEO writes personal cheque |
| 9 | **Sponsor/anchor identity** | Distressed fund known for loan-to-own | Generalist credit fund | Strategic operator, sovereign/state, or known long-term shareholder |
| 10 | **Warrants / CVRs** | All to creditors | Token OTM warrants to old common | Real CVRs tied to litigation, asset monetization, or upside hurdle |
| 11 | **Operating catalyst exists** | None — pure financial restructuring | Cyclical reversion plausible | Identified product/cycle/contract catalyst within 24 months |
| 12 | **Governance reset** | Board untouched or stacked with creditor designees | Mixed slate | Clean board; new independents with sector pedigree |
| 13 | **Second-restructuring risk** | History of prior recap + no operating fix (Meyer Burger, Spirit) | Single prior recap, partial fix | First recap, operating model defensible |
| 14 | **Liquidity post-deal** | <6 months of opex | 6–18 months | >18 months + revolver headroom |

### Decision tree (faster than scoring on the fly)

```
1. Did legacy common get pro-rata rights at a defendable price?
   NO  → likely creditor-economics deal; default skip unless #11 is extreme
   YES → continue
2. Is the maturity wall pushed >36 months with no springing maturities?
   NO  → bridge deal; pass unless catalyst <12 months
   YES → continue
3. Is dilution to old common <40%?
   NO  → re-underwrite at the post-money share count
   YES → continue
4. Is there a real anchor (insider, sponsor, sovereign) with cost basis
   at or near the recap price?
   NO  → no alignment; pass
   YES → buy candidate
5. Is the operating catalyst identifiable and dated?
   NO  → option, size accordingly
   YES → core position
```

### Red flags (any one is a pass by default)

- New money priced below the rights price via a separate PIPE
- Multiple classes of new equity with asymmetric voting
- Backstop warrants struck at a fraction of TERP
- DIP-to-exit conversion where the DIP lender becomes the new controlling
  shareholder
- Springing maturities or PIK-toggle defaults inside 24 months
- "Stub equity" carve-out to old common at <10% post-money with no warrants
- Indemnity / release language that protects insiders from claw-back

### Green flags (any two is a strong signal)

- Existing largest shareholder backstops the *entire* rights issue at TERP
  with no fee or warrant kicker
- UCC-1 terminations filed at close (real lien release, not just rolled)
- Management MIP struck at recap price with 3–5 year vesting
- Sovereign or strategic operator buys primary shares at market
- CVR tied to specific asset sale or litigation outcome
- Cap stack collapses from 4+ tranches to 1–2
- Post-deal net debt/EBITDA pro-forma <3.5x with explicit deleveraging path

---

## 3. Original signal taxonomy (kept, lightly edited)

**UCC filings.** A UCC-1 is public notice of a security interest in a
borrower's assets — "someone now has a lien on the stuff." New UCC-1s mean
new secured debt or fresh collateral; terminations mean liens released
(usually post-repayment). A cluster of UCC events around a transaction is a
flag to scrutinize: it tells you who controls the asset base is changing.

**Tier-S events** (radically change the equity payoff):

- **Tender offers / debt buybacks** — pulls debt forward, smooths maturities,
  improves equity convexity. Screen: "tender offer", "debt repurchase",
  "call notice", "early redemption".
- **Refinancing upgrades** — maturity extension, lower spreads, or moving
  from secured to unsecured. Petra extended bank debt 2026 → 2029 and notes
  2026 → 2030 alongside a rights issue.
- **Lien releases in refinancing** — UCC terminations bundled with new debt
  is a strong de-leveraging signal.
- **Equity-friendly convertibles** — high conversion premium, capped calls,
  modest coupons. Nvidia's 2013 $1.3B converts at ~30% premium funded
  buybacks; the stock multibagged because the conversion only triggered at
  much higher prices.
- **Exchange offers / liability consents** — swap near-term bonds for longer
  paper, sometimes with warrants. Equity-friendly if cash interest drops and
  the new paper isn't structurally senior to old stub equity.

**Tier-A** (bullish but not transformational): upsized revolvers, repeated
paydowns, repricings, repeat issuance at tighter spreads.

**Tier-B** (mixed; depends on terms): new general loans, attached warrants,
second-lien add-ons, PIPE rounds without alignment.

---

## 4. Case studies (kept; re-tagged with scorecard verdicts)

Each case is now annotated with a scorecard read (S = score / 28). These are
directional, not precise — the point is to show how the rubric separates the
multibagger setups from the look-alikes.

- **Yes Bank (India, 2020) — S ≈ 22/28.** RBI-forced rescue: SBI/private
  banks injected ~₹10,000 cr at ₹10/share; July 2020 FPO at floor ₹12 raised
  another ₹15,000 cr. Brutally dilutive, but it eliminated insolvency risk
  with a *regulated* recap backstop. Common ran ~80x off the FPO floor.
  Scorecard wins: anchor identity (sovereign-adjacent), maturity wall gone,
  operating tailwind (banking re-rate).
- **Indian Bank (India, 2024) — S ≈ 20/28.** ₹5,000 cr equity raise + ₹7,000
  cr debt. Stock roughly doubled within a year. Same template as Yes Bank
  with less distress.
- **Nvidia (US, 2013) — S ≈ 21/28.** $1.3B 5-year converts at 30% premium,
  1% coupon, capped calls; proceeds funded buybacks. "Dilution on our
  terms." Equity multibagged.
- **Coinbase (US, 2025) — S ≈ 16/28.** $2B converts, ~30–35% premium,
  capped calls. Good structure, but no operating catalyst tied to a hard
  date. Optionality, not core.
- **Petra Diamonds (UK, 2025) — S ≈ 14/28.** £18.8m fully underwritten
  rights, RCF extended to Dec 2029, notes to Mar 2030, cash-or-equity
  interest option. Textbook commodity-cycle call: high dilution, but the
  default cliff is gone. Hinges on diamond prices.
- **Baxter (US, 2025) — S ≈ 13/28.** Cash tenders for 2026/2027 bonds funded
  by new unsecured debt. Equity-positive marginally; not transformational.
- **Canopy Growth (Canada, 2026) — S ≈ 7/28.** New $162m term loan to 2031;
  C$96m of 2029 converts exchanged for C$55m new converts + C$10.5m cash +
  ~9.5m new shares + 12.7m warrants. Creditors took the upside. Pattern:
  Tier-S #4 played badly for common.
- **Country Garden (China, 2025) — S ≈ 4/28.** Controlling shareholder
  converted $1.14B of loans to equity at HK$0.60. Effective control
  transfer, massive dilution. Legacy common almost entirely impaired.
- **Arch Coal → Core Natural Resources (US, post-Ch.11) — S ≈ 18/28 (new
  common).** Old common cancelled; new post-reorg shares multibagged. The
  multibagger here was the *new* security, not the legacy stub.

**Pattern.** High scores cluster around: regulated/state-adjacent rescue
(banks), Tier-S converts with capped calls (Nvidia, Coinbase), and
cyclical-recovery rights issues with insider/anchor backing (Petra, Yes
Bank). Low scores cluster around: creditor-led equitizations (Canopy,
Country Garden) and stub equity post-Chapter 11.

---

## 5. Current analogues — re-ranked by scorecard

The table below replaces the prior subjective ranking with explicit
scorecard reads.

| Rank | Situation | Mechanism | S (est.) | Key swing factor |
|---|---|---|---|---|
| 1 | **Calfrac (Canada)** | C$35m rights, director-backstopped + C$120m TL, 2L-note cleanup | 19/28 | NA frac cycle margins; backstoppers' cost basis = aligned |
| 2 | **Viaplay (Sweden)** | SEK 4bn equity + SEK 2bn write-down + SEK 0.5bn debt-to-equity + SEK 14.6bn A&E | 18/28 | Nordic refocus producing durable EBIT |
| 3 | **Brait (South Africa)** | R1.5bn rights + bond extension to Dec 2027 + convert reset to R2.21 | 17/28 | Virgin Active monetization; NAV-discount close |
| 4 | **Worldline (France)** | ~€500m raise, 121% subscribed, French banks anchored | 17/28 | Client retention; 2027 FCF credibility |
| 5 | **Ørsted (Denmark)** | DKK60bn rights, 99.3% subscribed, Danish state holds 50.1% | 16/28 | Offshore-wind IRR trough confirmed; no further write-downs |
| 6 | **Petra Diamonds (UK)** | £18.8m rights + maturity push to 2029/2030 | 15/28 | Diamond price recovery |
| 7 | **SBB (Sweden)** | 95% participation in bond exchange, €2.78bn debt retired below par | 15/28 | Property valuations stabilizing; continued sub-par retirement |
| 8 | **Fossil (US)** | "Stapled Exchange" — UK plan + $32.5m new money, legacy equity preserved | 14/28 | Brand/licensing cash flows; cost cuts |
| 9 | **ams-OSRAM (Austria/CH)** | €2.25bn package incl. ~€800m rights | 14/28 | Auto/industrial cycle; debt stack absorption |
| 10 | **Intrum (Sweden)** | Ch.11 + Swedish reorg, 10% discount on reinstated notes | 13/28 | Capital-light shift; Cerberus monetization |
| 11 | **Core Scientific (US)** | Plan with oversubscribed ERO; old holders kept ~60% incl. warrants | 13/28 | AI/HPC datacenter pivot |
| 12 | **Exicom (India)** | ~₹259 cr rights, ₹120 cr from promoter; debt-reduction use of proceeds | 13/28 | Tritium integration; EV charger margins |
| 13 | **OXE Marine (Sweden)** | MSEK 78 rights + MSEK 155 debt-to-equity + EIB warrant swap | 11/28 | Product traction; liquidity tail |
| 14 | **Ebusco (Netherlands)** | €36m rights at €0.8209, 64.3% take-up, shareholder loans converted | 10/28 | Production normalization; customer confidence |
| 15 | **Ascot Resources (Canada)** | C$14.87m rights at C$0.01 + creditor settlement | 9/28 | Mine restart math; post-consolidation dilution |
| 16 | **Star Entertainment (Australia)** | A$300m, Bally's/Mathieson ~56% post-conversion | 8/28 | Control transfer reduces alignment with minorities |

### False friends (low scores; pass by default)

- **Atos (France)** — €2.9bn debt equitization; creditors ~90.8%. S ≈ 4/28.
- **Varta (Germany)** — StaRUG with shareholder reconstitution. S ≈ 5/28.
- **Beyond Meat (US)** — 2025 exchange could issue up to 326m new shares to
  retire >$800m debt. S ≈ 5/28.
- **Meyer Burger (Switzerland)** — CHF 200m 2024 rights didn't fix the
  business; subsequent bondholder talks confirm bridge-to-next-restructuring
  status. S ≈ 4/28.
- **Spirit Airlines (US)** — Emerged March 2025, refiled August 2025. The
  canonical "balance-sheet fix without an operating fix." S ≈ 3/28.

### Shortlist by archetype

- **Pro-rata rights with insider/anchor backstop:** Calfrac, Brait, Petra,
  Exicom.
- **Discounted-debt-retirement / NAV convexity:** SBB.
- **State / strategic-anchor mega recap:** Ørsted, Worldline.
- **Legal-structure preserves listed common:** Fossil, Viaplay.
- **Post-court recap where common kept real economics:** Core Scientific,
  Intrum.

---

## 6. Workflow summary

1. **Ingest.** RSS + EDGAR/SEDAR+/RNS form filters + UCC saved searches +
   court dockets feed a single triage inbox.
2. **Tier.** Regex sorts hits into Tier-S / Tier-A / Tier-B / Red-Flag lanes.
3. **Score.** Each candidate gets a 14-dimension alignment score on first
   read of the primary filing.
4. **Decision tree.** Pro-rata + maturity wall + dilution + anchor + catalyst
   — five gates, in order. Drop fast at the first failure.
5. **Position.** Score ≥ 18 = core; 13–17 = option; <13 = pass or short the
   stub. Re-score on every amendment.
6. **Monitor.** UCC and 8-K Item 1.01/2.04 alerts on every active name; auto
   drop if a second restructuring becomes visible (NT filings, going-concern
   language, advisor hires).

The point of the system is not to find every restructuring — it is to make
the alignment question (rescue for whom?) the first thing you answer, before
the narrative gets in the way.
