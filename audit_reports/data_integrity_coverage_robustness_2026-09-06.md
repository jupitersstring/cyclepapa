# Data Integrity, Coverage & Measure Robustness Audit — 2026-09-06

Master at audit time: 46,526 rows × 246 cols (post FDB-expansion merge), all rows stamped 2026-09-06.
Methodology harness after this audit: **41 checks, 0 FAIL, 0 WARN** (2 checks added by this audit).

## 1. Integrity

| Check | Result |
|---|---|
| Duplicate symbols | 0 |
| Rows missing src/currency | 0 |
| Lynch signals file (26,628 rows) | 0 ragged, 0 dup |
| mcap ≈ price×shares (0.6–1.7×) | 92.6% of testable rows |
| FX conversion internal consistency | p99/p1 < 1.5× for every currency |
| Composite bounds [0,1] | 0 violations |

**Found & repaired this audit:**
- **Torn master reads (P0, systemic).** The audit itself initially read a half-written
  `asymmetry_global.csv` (26,281 of 46,526 rows) while the deep driver's enrich step was
  streaming it out — the same non-atomic-write hazard previously fixed in the fdb scripts.
  `enrich_asymmetry_global.py`, `archetype_tags.py`, and `fix_pipeline.py` now all write
  tmp+rename. Any concurrent reader (book builders, audits, drivers) previously risked
  silently processing a truncated master.
- **13 pence-minted .L market caps** re-nulled (re-introduced by the still-running enricher's
  pre-fix code image; the on-disk fix takes effect on its next restart).
- **379 impossible FCF yields (>100%) nulled** — root cause for the large-cap cases is
  a *systematic ADR currency mismatch*: F-suffix OTC listings (GELYF, TRSBF, MFRVF…)
  carry fundamentals in home currency (CNY/TRY) against USD market caps, inflating every
  yield ~7–40×. `financialCurrency` is now captured by the deep enricher so future runs
  can convert properly; until then impossible values are nulled at the source
  (`derive_missing_columns.py`) and gated by a new methodology check.
- **15 absurd dividend yields (>40%)** nulled — stale-price/preferred artifacts
  (IIPR-PA "90%", YCBD "50%"). New methodology check added.

**Known, accepted, and quantified:**
- 34 rows where mcap ≈ 100×(price×shares) — Yahoo dual-class/preferred share-count
  artifacts (Korean prefs, TEL2-A style dual class). Market caps themselves are correct.
- EV ≠ mcap+debt−cash by >20% on 15.8% of testable rows — Yahoo EV staleness vs live
  mcap; EV-based measures inherit this noise.
- 54→39 remaining div yields in 25–40% band left as-is (one-off specials can be real).

## 2. Coverage

Two clearly distinct cohorts after the expansion merge:

| Cohort | Rows | mcap_usd | revenue | fcf_yield | div yield | 52w system |
|---|---|---|---|---|---|---|
| Enriched core | ~26k | ~99.5% | ~97% | ~99% | ~46% | ~69% |
| Full master (incl. fresh expansion) | 46,526 | 74.7% | 70.4% | 69.7% | 30.8% | 49.1% |

- Lynch price-series signals: 26,628 of ~29.7k universe (drive running, ~3k left);
  100% of rows carry a lynch_reward_score (absent data scores 0, see §3).
- All 53 src countries ≥95% lynch coverage — no geographic hole.
- Segment (v2 EDGAR) signals: 4,745 US filers.
- Qualitative verdicts: 448 names (1.9%) — the thinnest layer by far.
- Dividend yield is structurally sparse in the US/CA cohort (20%/11% — most names
  simply don't pay) vs 70–80% in JP/TW/TH — a real-world pattern, not a defect.

## 3. Measure Robustness

**Missingness bias (the main finding).** On the enriched core, `confirm_overall` is
independent of data coverage (ρ=0.02). On the merged 46.5k master it correlates 0.60
with coverage — *not* because the measure rewards data, but because unenriched
expansion names default to zero legs. Any ranking across the merged master therefore
buries data-poor names on missingness, not merit. Containment: ranked books already
gate on market_cap_usd + measure presence, which excludes the unenriched cohort from
top-N lists rather than mis-ranking it; the enrichment drives are progressively filling
the gap. `lynch_reward_score` shows no such bias (ρ=0.09) since it scores only fetched
series.

**Distribution shapes** (n=46,526): confirmation composites healthy (std 0.28–0.35);
`lynch_reward_score` and `seg_inflect_score` are intentionally rare-event flags
(97.8–98.5% zero) — correct for screens, useless as general-purpose rankers, which is
how the books use them.

**Coarseness:** quality (13 distinct values), buyback (11), rev_growth (19) are
leg-count composites — ties are expected and broken by adjacent columns in the books.

**Redundancy:** `inflection_confirm_score` ~ `rev_growth_score` (ρ=0.92) and
~ `oper_leverage_score` (ρ=0.90) — by construction (they are its legs); the composite
adds gating, not information, over its parts. `confirm_overall` vs its legs sits at
0.70–0.75, appropriate for a parent composite.

**Concentration sanity:** lynch top-decile tilts small (<$50M: 32% vs 22% universe)
and toward US/JP/KR roughly in proportion to universe weight — no single-country or
penny-stock capture.
