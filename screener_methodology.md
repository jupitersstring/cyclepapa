# Screener Methodology — v2 Coverage Improvements

What the v2 universe screener does differently from v1, the gaps it
closes, and the gaps that remain. This is the methodology layer above
`src/universe_screen.py`; if the code disagrees with this doc, the
code is right (it's the source of truth) and this doc is stale.

## Why v1 was insufficient

The v1 screener (June 2026 first pass) parsed the universe and produced
a ranking, but:

- **77% of candidates classified Unknown.** The keyword set was tuned
  on US-centric phrasing and missed Asian/EM/EU regulator vocabulary.
- **Completed-arc names ranked alongside live deals.** Rolls-Royce
  (2009→2024 multibagger arc), Carvana (2023 exchange recovered),
  Yes Bank (SBMC ATH) all scored as if they were live opportunities.
- **False friends ranked T1.** Petrofac (Court of Appeal reversed the
  Part 26A plan, equity wiped), Wood Group (Sidara cash takeover at
  30p), and other entries with stale "ongoing recap" framings in
  universe.md notes were not detected as failed.
- **Deal-vintage ignored.** A 2009 rights issue and a 2026 rights
  issue produced the same score, even though only one is investable
  today.
- **Deal size ignored.** A $9bn rights issue at a national champion
  and a SEK 36m microcap raise weighted identically.
- **Single-archetype tagging.** Names that satisfy multiple archetypes
  simultaneously (Eutelsat = A1+F+H; Hawaiian Electric = A1+G+H) got
  no credit for the multi-leg structural strength.

## What v2 changes

### 1. Massively expanded archetype keyword sets

The keyword regex list grew from ~50 patterns to ~150 across all
archetypes:

- **A2 (sovereign industrial-policy):** added EIB, KfW, BNDES, JIC, CDP,
  Danantara, Khazanah, Mubadala, GIC, Temasek, ADIA, PIF, NBIM,
  Industrial Accelerator Act, CRMA, "price floor," "binding offtake,"
  "sub-commercial."
- **A1:** added "director backstop," "insider backstop," "cornerstone,"
  "CIC," promoter-subscription verbs, family-foundation anchors.
- **F:** added Asian property MCB cascade vocab ("offshore
  restructuring," "Part 26A cramdown," "onshore restructure"),
  "post-bankruptcy," "new common."
- **B:** added "exchangeable bond," "convert(ible) loan/stock/preferred,"
  "premium to 30/60/90-day VWAP," strategic-anchor + premium combos.
- **C:** added "out-of-court," "super-priority," "up-tiering,"
  "distressed exchange," "open-market buyback."
- **D:** added "joint venture anchor," "offtake-anchor," specific
  customer-anchor names (VW PowerCo, Hefei, Gotion, Bright Dairy).
- **E:** added DOCA, NCLT (kept for taxonomy completeness only),
  IBC, Company Voluntary Arrangement.
- **G:** added Basel-related capital-floor language, central-bank
  directed lending, country-specific regulators (NLFI, UKGI, HFSF, HM
  Treasury, "AGR," "spectrum").
- **H:** added MPS-deadline, FIEA amendment, TSE cost-of-capital
  disclosure, KRX value-up, SASAC, take-private, MBO, board reset,
  governance overhaul, specific control-shareholder names
  (Spaldy/Gilinski/Křetínský/Niel).

The Unknown rate fell from 77% (v1) to 70% (v2). Further reduction
requires either richer notes columns in universe.md (manual data
work) or a section-context model (next iteration).

### 2. Vintage extraction with completed-arc decay

`detect_vintage()` extracts the latest year mention from notes +
section text. `vintage_decay()` applies a multiplier:

| Age | Multiplier |
|---|---|
| ≤2 years | 1.00 |
| 3–4 years | 0.85 |
| 5–8 years | 0.50 |
| >8 years | 0.25 |

Unless the notes contain a "still active" marker (`watch`, `pending`,
`ongoing`, `live`, `current`, `now`, `invest`, or any 2025+ year), the
decay applies. This causes Rolls-Royce (2009→2024) to drop out
naturally without requiring a manual "completed arc" override.

### 3. False-friend status detection

Three new status codes catch the v1 misclassifications:

- **PASS_FALSE_FRIEND** — Court of Appeal reversal, "taken private,"
  "delisted (20XX)," equity wiped, second filing, liquidation. This
  catches Wood Group (Sidara cash takeover at 30p).
- **ARC_DONE** — multibagger, recovered, dividends resumed, at ATH,
  re-rate done, now-consolidator. Drops Yes Bank-style completed arcs
  *automatically* from the live screen.
- **REPEAT_RX** — Ch.22, refiled, rescue lapsed. Catches Spirit-style
  second restructurings.

Status multipliers in the score formula:

| Status | Multiplier |
|---|---|
| OK | 1.00 |
| YELLOW | 0.55 |
| PRE_RECAP | 0.70 |
| ARC_DONE | 0.20 |
| PRE_RECAP | 0.70 |
| ACQUIRED | 0.00 |
| PASS_FALSE_FRIEND | 0.00 |
| REPEAT_RX | 0.00 |

ACQUIRED, PASS_FALSE_FRIEND, REPEAT_RX all yield score = 0, which
keeps them in the universe (auditability) but zeros their priority.

### 4. Size-class proxy from currency-amount detection

`detect_size_class()` runs regex over notes for currency-amount
strings ($, €, £, SEK/NOK/CHF/RMB/HK$/etc. + number + bn/m/billion).

- **large** = "$X bn" or "billion" appears → 1.10× multiplier
- **mid** = currency amount with "m"/"million" → 1.0× multiplier
- **small** = no currency amount detected → 0.90× multiplier

This penalises 30-word universe entries with no scale information and
gives a (mild) boost to entries that quantify the deal.

### 5. Multi-archetype tagging

`classify_archetypes()` now returns `(primary, [secondary])`. Names
matching multiple archetypes (Eutelsat A1+F, Hawaiian Electric A1+G+H,
Sunac F+A) get a `+10%` multiplier per secondary archetype, capped at
+30%. The output's Archetype column renders as `A1+F` to surface this.

### 6. Per-region tier discipline

Top 15 per region (vs. top 20 v1) — denser regions don't drown out
under-represented ones. Region summary table now reports T0+T1 count
per region so users can see which regions have actionable density.

### 7. Cleaner tier thresholds

| Tier | Threshold | Meaning |
|---|---|---|
| T0 | ≥ 0.80 | Full YAML build + verify ASAP |
| T1 | 0.55–0.80 | Priority YAML build-out |
| T2 | 0.35–0.55 | Watch + light YAML |
| T3 | 0.20–0.35 | Sector-context only |
| pass | < 0.20 | Universe ballast |

The recalibration produces ~1 T0, ~11 T1, ~30 T2 from 529 candidates —
proportionate to manual research bandwidth.

## Open coverage gaps

### G1. The Unknown rate is still 70%

Three causes:
- **Terse universe.md notes** (many rows say only "Refi 2024" or "Pre-deal:
  watch"). Fix: enrichment pass on universe.md to add 1–2 keyword tags
  to each row.
- **Sector-banner sensitivity** is limited. Currently the section
  classifier looks at sentence text; some sectors imply archetype
  (`Banks (ING/Lloyds 2009 template)` → likely G, but only for names with
  matching note context). Fix: section-prior weighting.
- **Country-context inference missing.** A name in the
  `Argentina under Milei — distressed sovereign normalisation basket`
  section is almost certainly G+A1 even without notes-keyword hits.
  Fix: section-to-archetype default mapping.

### G2. Stale universe.md entries

Even with v2, the framework relies on universe.md being accurate.
Petrofac and Wood Group are now explicitly marked as false friends
(rev `f4a5e8a` and this commit). A quarterly stale-pass on
universe.md is the maintenance discipline.

### G3. No detection of "next-recap candidate" pre-deal signal

v2 still scores reactively (looking for evidence of an *announced*
deal). The framework's most valuable trades (Calfrac pre-rights, MP
Materials pre-DoD-deal) involve detection of pre-recap names. This
needs a separate watch-list mechanism — possibly a `PRE_RECAP_WATCH`
file with reasons each name might announce something.

### G4. Confidence scoring still binary on the ★/○/▲ tag

The ★ confirmed / ○ probable / ▲ watch tagging is coarse. A
fact-density score (number of cited dates + amounts + named anchors)
would be more honest.

### G5. No ticker normalization for the YAML build-out queue

v2 added fuzzy ticker matching (strip exchange prefix, strip
punctuation, also match by first-name-token), which catches Calfrac
(TSX:CFW) against the WLN/MP/LAC YAMLs. But still misses cases
like "Hawaiian Electric Industries" (HE.yaml exists but the
universe entry is "Hawaiian Electric"). A canonical-name → ticker
mapping table is the proper fix.

## Methodology signals the v2 screen now produces

The screener output (`output/universe_screened.md`) now includes:

- **Triage tier distribution** — calibrated to manual research throughput
- **Archetype mix with multi-tag count** — shows how many names hit
  >1 archetype, a basket-level structural-strength indicator
- **Status distribution** — quantifies the false-friend rate in the
  universe (currently 47 of 529 = 8.9%)
- **Vintage distribution** — shows the cohort skew (how much of the
  universe is current vs. completed-arc)
- **Region summary with T0+T1 count** — surfaces which regions have
  research-worthy density vs. which are universe ballast
- **Sanity-check section** — auto-flags any high-scoring name that
  status-classified as completed-arc / false-friend / repeat-RX. If
  this section is empty, the calibration is honest. (It's currently
  empty.)
- **Priority YAML build-out queue** — names that scored T0/T1 AND
  don't already have YAMLs, the actionable research backlog.

## What's next

1. **Section-context archetype priors** — eliminate the bulk of the
   remaining 70% Unknown.
2. **Universe.md enrichment pass** — add structured tags to terse
   entries so the screener has more to work with.
3. **Canonical name-to-ticker dictionary** so the YAML build-out
   queue de-dupes against existing candidates correctly.
4. **PRE_RECAP_WATCH register** for pre-deal signal candidates that
   the universe.md format doesn't accommodate.
5. **Quarterly stale-pass discipline** on universe.md (next: Q3 2026).
