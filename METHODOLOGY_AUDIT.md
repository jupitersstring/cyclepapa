# Methodology Audit — Sourcing, Parsing, Scoring

Second-order audit. The prior sweep (AUDIT.md + the pipeline error
sweep) covered mechanics: syntax, JSON integrity, sorting, universe
hygiene. This audit interrogates the *semantics*: do the scanners find
what they claim, do the parsers extract the right values, and do the
scoring functions mean what they say?

Every finding below was verified against the artifacts on disk before
being declared, and every confirmed defect was fixed in the same pass.
Fix commits reference the finding IDs (A1–A11).

---

## Confirmed defects (fixed)

### A3 — Voss CIC layer over-fired on universal boilerplate  [HIGH]

**Evidence.** 968 of 1,982 scored names had ONLY the CIC-language
pillar. Change-in-control language appears in virtually every proxy;
it is not the Voss signal — the *triangulation* (CIC + insider ≥30% +
short ≥20%) is. Because the consensus counts any positive layer score
as "firing," ~1,300 names had a phantom layer inflating
`n_layers_firing`.

**Fix.** CIC-language points awarded only when at least one behavioral
pillar fires (insider ≥15% or short ≥10%). CIC-only rows remain in the
output with score 0 and an explanatory reason.
**Effect.** 1,982 → 668 non-zero scores (−1,314 phantom firings). All
11 full-triangulation names unchanged.

### A1 — Bumpitrage classified FLAT series as declining  [HIGH for the layer]

**Evidence.** Both prior "declining" hits were flat same-date
duplicates: KALV 77.8 → 77.8 (both 2026-06-11), LE 95.2 → 95.2 (both
2026-04-01). The comparison used `>=`, so equality passed; same-day
amendment pairs produced duplicated readings. **The layer's entire
positive set was false.**

**Fix.** Decline now requires (a) readings on distinct dates and
(b) a material drop (≥1.0pp on the pct series, ≥2% on shares).

### A2 — 13F deltas could come from ancient filings; no provenance  [HIGH for the layer]

**Evidence.** Name→CIK resolution can land on stale/renamed entities;
observed filings from 2008 (ValueAct CIK), 2011 (Icahn CIK), and 2023
(JANA) being treated as the "current quarter." The output JSON stored
no filing dates, so staleness was unauditable downstream.

**Fix.** Recency gates (current filing ≤200d old, pair gap ≤200d,
else the filer is skipped with a printed reason) + a
`_META_FILINGS_USED` provenance block recording exactly which filings
fed each delta.

### N-PORT series mixing  [HIGH for the layer]

**Evidence (code-confirmed).** Trust-level CIKs (e.g. Dodge & Cox
Funds) file one N-PORT-P per fund *series*; the module diffed
`filings[0]` vs `filings[1]`, which under a multi-series trust
compares two *different funds* — garbage deltas.

**Fix.** `parse_nport` now extracts the S000 `seriesId`; the pairing
loop walks up to 10 recent filings until it finds a prior with the
*same* series, with the same ≤200-day recency gates as 13F.

### A5 — Odd-lot edge scored on dead tenders  [MEDIUM]

**Evidence.** LEN carried the full +25 odd-lot edge from a 198-day-old
*completed* exchange (the snippet is past-tense results language:
"who have validly tendered … were not subject to proration"). The
odd-lot edge only exists while a tender is live.

**Fix.** Liveness gate on the latest filing age: ≤60d full score,
61–120d half, older → 0 with `liveness: STALE_OR_COMPLETED`.

### A6 — Coval proxy saturated by >100% institutional ownership  [MEDIUM]

**Evidence.** 456 of 1,180 rows had `inst_pct` > 100% (yfinance
share-class double counting; observed up to 152%). The "very high"
scoring bucket was saturated by the artifact.

**Fix.** Cap at 100% for scoring; raw value preserved as
`inst_pct_raw`.

### A7 — Spinoff timer used Form 10 filing date as distribution date  [MEDIUM]

**Evidence.** All 7 tracked SpinCos carried `distribution_date` equal
to the registration filing date. Distribution follows registration by
3–6 months; pre-listing names were mislabeled EARLY_FORCED_SELLING.

**Fix.** True first-trade date derived from the first session with
non-zero volume; names with no volume yet are `PRE_DISTRIBUTION`
(score 0). `registration_date` and `first_trade_date` now both stored.

### A9 — Activist feed silently queried only ~15 of 37 firms  [MEDIUM]

**Evidence.** `queries[:30]` with two queries per firm truncated the
8-K path after the first ~15 activists (alphabetically-early firms
only).

**Fix.** One combined OR-query per firm — full coverage of all 37
firms at roughly the same request budget.

### A4 — PDUFA day contaminated by nearby digits  [LOW-MEDIUM]

**Evidence.** 2 of 71 parsed dates wrong: the day was taken as the
first 1–2-digit number anywhere in the matched block, so "Q1" and
"Cohort 1" produced day = 1 (HRMY, CYTK).

**Fix.** Day captured inside the month-day-year group itself. Stored
rows re-parsed locally: 2 dates corrected; 2 rows whose stored text no
longer parses under the stricter pattern (SRRK, LNTH) were zeroed with
an explanatory reason rather than silently kept.

### A11 — Activist name matching lacked word boundaries  [MEDIUM]

**Evidence.** Found during post-fix re-verification: "Winklevoss
Capital Fund, LLC" was flagged as a Voss Capital 13D because the
substring alternation matched "voss capital" inside "winklevoss
capital." A family office was being scored as a known activist.

**Fix.** `\b` word boundaries wrap the alternation; unit-verified
that "Voss Capital, LP" matches and "Winklevoss Capital Fund" does
not.

### A10 — 10-Q equity captured on only 33/164 filings  [LOW]

**Evidence.** The regex accepted only "stockholders equity"; the
"shareholders" spelling was missed. (Equity is informational, not
scored, so no score impact.)

**Fix.** Pattern accepts both spellings.

---

## Verified clean (no action needed)

- **10-Q core parse quality:** `current_assets`, `total_liab`,
  `current_liab` captured on 164/164 parsed filings; **zero** cases of
  the classic "Total liabilities and stockholders' equity" mis-grab
  (checked via total_liab > total_assets sentinel).
- **10-Q unit detection:** thousands/millions multiplier detection
  verified on sampled filings.
- **Tender mechanism classifier:** Dutch-auction detection cross-
  confirmed by the `terms.dutch_low/high` fields where present.
- **All division sites** (mcap, shares, NCAV denominators) confirmed
  guarded upstream.
- **Consensus loader** ignores the new `_META_FILINGS_USED` provenance
  key by construction (universe-membership check runs first).

## Systemic lessons

1. **Presence-of-language is not a signal.** Voss (CIC boilerplate)
   and, previously, the LEN odd-lot hit both scored on text that
   *exists* rather than text that *matters now*. Every text-presence
   layer now carries either a behavioral-pillar conjunction or a
   liveness gate.
2. **`>=` vs `>` in trend detection.** Flat-as-declining survived
   because the false positives looked plausible. Trend claims now
   require material deltas, not non-increase.
3. **Filed-by identity ≠ economic identity.** Both 13F (stale CIKs)
   and N-PORT (multi-series trusts) taught the same lesson: an EDGAR
   filer identifier does not pin down *which economic entity, when*.
   Both layers now verify recency and series identity explicitly and
   record provenance.
4. **Date fields must name what they actually are.** "distribution_
   date" holding a registration date propagated a wrong mental model
   into the status labels.
5. **Name matching needs word boundaries.** Substring alternations
   over entity names will eventually match inside longer names
   (Voss / Winklevoss). Every curated-list matcher now uses \b.

## Residual known limitations (documented, not fixed here)

- PDUFA drug-name extraction remains best-effort; day/month/year is
  now strict but the drug identifier can still be missed.
- Odd-lot liveness uses filing age as a proxy for tender-open status;
  parsing explicit expiration dates from the SC TO body would be
  stricter (candidate future refinement).
- The Cohen-Malloy routine classifier still awaits the 3-year Form 4
  backfill (task S2.1) — unchanged disclosure from the prior audit.
- 13F/N-PORT curated filer lists are small by design; coverage is a
  choice, not an oversight.
