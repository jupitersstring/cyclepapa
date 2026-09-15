# Incentive-Analysis Audit — screening, sourcing, and regex assessment

Date: 2026-08-13. Scope: the PSU/governance incentive-strength machinery —
`proxy_scan.py` → `psu_scoring.py` / `psu_forensics.py` / `psu_forensics_v2.py`
/ `forensic_asymmetry.py` → `psu_step_change.py` → consensus layers and the
Incentive Improvers sheet. Every finding below was verified empirically
against the live scan data (4,410 proxies, 2,970 PSU names) or by direct
regex probe; fire-rates quoted are measured, not estimated.

Severity: HIGH = materially distorts scores today; MED = distorts a
meaningful subset; LOW = noise within tolerance; INFO = deliberate
tradeoff worth documenting.

---

## A. Sourcing

**S1 (MED). Single-filing, single-form sourcing.** `proxy_scan.py` reads
only the *most recent DEF 14A within 450 days* per ticker. Fresh PSU
adoptions disclosed in 8-Ks (inducement grants — the PLBY/Penguin
archetype), DEFA14A amendments, and 10-K comp sections are invisible
between proxy seasons. The 8-K inducement channel exists only as
`induce_detail.json`, a frozen one-off scan.

**S2 (MED). Say-on-pay coverage is 39%.** `say_on_pay_pct` extracts for
only 1,173 of 2,970 PSU names. Every SOP-conditioned signal (forced-response
+8 in Incentive Improvers, dissent −8 in gov score and step-change) silently
skips 61% of the population. Median extracted value is 94%, so the extracted
subset also skews toward companies that brag about their vote.

**S3 (MED). `psu_step_change.py` runs on ten frozen detail JSONs**
(`v2_detail.json`, `wide180_detail.json`, `induce_detail.json`, …) that
have no generator in `rebuild_all.sh` — they are one-off scan artifacts
recovered from git. The step-change layer therefore ages silently.
`yfinance_enrichment.json` is missing entirely, so the forensics overlay's
price-dependent pieces are skipped.

---

## B. Regex defects — confirmed by probe

**R1 (HIGH). Comma-grouped and million-suffixed dollars truncate into
phantom hurdles.** Every hurdle regex captures `\$([0-9]+(\.[0-9]+)?)`
with no thousands-separator or scale-word guard:

- `"target bonus is $1,250,000 … maximum award value is $2,500,000"`
  → extracted hurdles **[1.0, 2.0]** (probe-verified).
- `"threshold of $2.4 million EBITDA"` → hurdle **2.4**.

In live data: 7,039 captured hurdles, of which **407 are exactly $1.00**
and **33.5% are ≤ $10** — a mixture of genuine penny-stock hurdles and
this artifact. Phantom low-side values inflate the ladder-count credit
(5+ distinct → +18 step-change points) and, for low-priced stocks, the
upside kicker. The existing 8× plausibility cap only trims the *high*
side; junk below spot passes freely.

**R2 (HIGH). `single_trigger` fires on negation boilerplate.** The regex
matches the literal phrase "single-trigger" with no negation window.
`"We do not provide single-trigger acceleration"` and `"What we don't
do: single-trigger vesting"` both fire (probe-verified) — and this
"what we don't do" table is standard proxy furniture. Fire rate is
**34% of all PSU names (1,011)**, far above the real-world prevalence of
single-trigger plans; each takes −8 and loses the +8 "double-trigger
only" credit. Companies are being penalized for *bragging about not
having* the bad feature. (The Voss CIC layer was fixed for exactly this
failure mode in a prior audit; this sibling was not.)

**R3 (HIGH). `RETIREMENT` flags 401(k) boilerplate — 63.8% fire rate.**
The pattern `retire|retirement|…` inside the PSU window catches
"401(k) retirement savings plan" and "retirement eligibility" prose
(probe-verified). A penalty that fires on **2/3 of the population**
(1,894 names) is not a discriminator. It costs −6 step-change, enables
the −15 milk-and-exit combo, and is one of three gates that block
`transformation_signal` — which consequently fires on only **23 of
2,970** names.

**R4 (MED). `DISCRETIONARY` conflates plan administration with payout
override — 44.8% fire rate.** "The Committee administers the plan in
its sole discretion" (universal plan-document boilerplate) fires the
same flag (probe-verified) as a genuine formula override. At −18 it is
the single largest alignment penalty, firing on 1,332 names, and a
second `transformation_signal` gate.

**R5 (MED). Say-on-pay extraction: `\d{1,2}` cannot capture 100%**
(probe: returns None), and taking `max()` across all percentage mentions
biases toward the *historical high* — a proxy that says "received 78%
this year, versus 92% in the prior year" near a second keyword mention
reports 92 and masks the dissent that the forced-response signal exists
to catch.

**R6 (MED). Dead patterns.** `APPRECIATION_LADDER`, `APPRECIATION_PCT`,
and `TRAILING_AVG_HURDLE` are compiled in `psu_scoring.py` and never
referenced. The %-appreciation ladder case they were written for
(documented in-file: Penguin Solutions "25%/50%/75%/100% appreciation")
is not actually extracted anywhere.

**R7 (MED). Rarity-weight circularity in Incentive Improvers.** Delta
occurrence counts drive the weights (psu_weight_increased 12/4,410 →
+25; new_metric_added 2/4,410 → +15), but the counts partly measure
*regex narrowness*, not real-world rarity: `psu_weight_increased`
requires the exact verb-object sequence "increased … the PSU
weight/allocation/portion/mix" and misses "increased the portion of
equity awarded as PSUs"; `new_metric_added` requires an
"effective/beginning FY20XX … added" sequence within 80 chars. The
narrower the regex, the rarer the hit, the higher the weight — the
calibration rewards its own blind spots. Weights should be sanity-checked
against a hand-labeled sample before being treated as rarity.

**R8 (LOW). `HURDLE_TABLE_TRIGGER` harvests every $-amount in a
4,000-char window** after phrases like "vesting in tranches" — sweeping
in target-bonus and ownership-guideline dollars from adjacent comp
tables. Mitigated by the 8× cap; residual junk feeds R1.

**R9 (LOW). `REPRICING` includes `adjust(ed)? targets?`** which catches
routine annual target-setting prose ("adjusted targets to reflect the
divestiture") — 19.2% fire rate, −12 alignment, third
`transformation_signal` gate.

**R10 (INFO). Aggregate-metric detection scans the full comp text** —
peer-group and covenant EBITDA mentions flag `absolute_ebitda` even when
the LTI is purely TSR-based. Deliberate (metric tables often sit outside
the PSU window) but it means the −10/metric aggregate penalty over-fires
in a way not quantified here.

---

## C. Scoring-shape consequences

**C1. Penalty saturation.** With R2/R3/R4/R9 firing at 34–64%, the
penalty terms are close to a constant offset for most of the population
rather than a discriminator — and the composite's *relative* ranking is
driven mostly by the positive terms. The names most hurt are the honest
ones whose proxies discuss governance thoroughly.

**C2. `transformation_signal` starvation: 23/2,970 (0.8%).** The flag
requires per-share metrics AND ≥1.5× hurdles AND none of
discretionary/retirement/repricing. Given three over-firing gates, the
framework's marquee archetype almost never triggers; several of the 23
survivors are simply proxies whose PSU windows happened to dodge the
boilerplate.

**C3. Say-on-pay double treatment.** SOP < 70 penalizes twice (gov −8,
step-change −8) while SOP < 80 *rewards* +8 in Incentive Improvers as
forced-response context. Directionally defensible (dissent is bad;
responding to dissent is good) but the thresholds are uncoordinated and
all three run on 39% coverage (S2).

**C4. 703 of 2,970 PSU names carry a negative gov_score**, largely
downstream of R2's negation false-positive.

---

## D. What is working

- The PSU-keyword window (`_psu_windows`) is the right architecture —
  flags evaluated near PSU text, not across the whole proxy.
- The 8× hurdle plausibility cap (prior audit) removed the high-side
  junk; ladder ranges quoted in reasons are now sane.
- The metric taxonomy (per-share vs aggregate, with the per-share
  carve-outs like "EBITDA per share") is well-designed; ROIIC detection
  as a capital-allocator tell is a genuine edge.
- Rarity-weighting the improver deltas is directionally correct (R7's
  caveat notwithstanding) — clawback boilerplate at +4 vs PSU-weight
  increase at +25 is the right shape.
- Freshness weighting and the 450-day fetch window are consistent
  (0 names with freshness = 0 in live data).

---

## E. Recommended fixes, in order of measured impact

1. **R1**: extend dollar captures to `\$[0-9][0-9,]*(?:\.[0-9]+)?` with
   a thousands-strip, and reject any capture followed within ~12 chars
   by `million|billion|thousand`. Re-scan is not needed — re-running
   `analyze_proxy` over cached HTML (`CACHE_HTML`) suffices.
2. **R2**: require a non-negated context: fire only when "single-trigger"
   is NOT preceded within ~60 chars by `no|not|do not|don't|without|
   eliminated|removed` and not inside a "what we do not do" block.
   Mirror the fix already applied to Voss CIC.
3. **R3**: narrow to genuine carveout context — `retire\w*` within N
   chars of `vest|acceler|continue|eligib` — and explicitly exclude
   `401(k)|savings plan|retirement plan`.
4. **R4**: split the flag: `admin_discretion` (ignore) vs
   `payout_discretion` (`discretion\w* [^.]{0,60}(increase|decrease|
   adjust|modify|override) [^.]{0,40}(payout|award|vesting|result)`).
   Re-tune the −18 once fire rate is credible.
5. **R5**: `\d{1,3}` + take the percentage nearest the most recent year
   mention (or `min` within the SOP sentence), not `max` across the file.
6. **R6**: wire the appreciation-ladder patterns into
   `extract_features` (convert % ladders to implied $ via current price,
   as the in-file comment already specifies) or delete them.
7. **R7**: hand-label ~50 proxies for the two narrowest deltas; widen
   regexes until recall is credible; recompute weights from the widened
   counts.
8. **S1**: add an 8-K comp-plan poller (Items 5.02/1.01 + "inducement")
   as a generator for `induce_detail.json` so the freshest adoptions
   re-enter the step-change layer.
9. **S3**: either add generators for the frozen detail JSONs to
   `rebuild_all.sh --scans` or mark them explicitly as archival inputs
   with dates in `layer_freshness.json`.

Fixing R2+R3+R4 changes scores for a large fraction of the 2,970 PSU
names (directionally: fewer false penalties, more transformation
signals) — regenerate consensus + workbook and expect material re-ranking
inside the PSU-heavy tabs after applying.

---

## F. Fixes applied (2026-08-13, same branch)

| Finding | Status | Where |
|---|---|---|
| R1 comma/million phantom hurdles | **FIXED** | `psu_scoring.py`: `_NUM` captures full comma-grouped numbers (parse to real magnitude, die at the 1..10000 filter); `_collect_dollars` rejects million/billion/thousand-suffixed amounts. Applied to every hurdle pattern incl. the table-trigger harvest and ladder inner scan. |
| R2 single-trigger negation | **FIXED** | `psu_forensics.py` + `event_signals.py` (same bug, second site): a mention counts only when no negation token appears in the preceding 60 chars. |
| R3 retirement boilerplate | **FIXED** | `psu_scoring.py`: flag requires retirement coupled to award treatment (vest/acceler/continu/eligib/pro-rat) or explicit departure phrasings; 401(k)/savings/pension prose stripped first. |
| R4 admin vs payout discretion | **FIXED** | `psu_scoring.py`: fires only on discretion coupled to changing an outcome, discretionary bonus, or notwithstanding-the-formula. |
| R5 say-on-pay | **FIXED** | `psu_forensics_v2.py`: `\d{1,3}` (100% capturable); year-context selection — latest-year value wins, else minimum (conservative toward dissent). |
| R6 dead patterns | **FIXED** | `TRAILING_AVG_HURDLE` wired into the pattern loop; `APPRECIATION_*` extracted into `appreciation_pcts` and converted to implied $ hurdles in `score()` (also feeds `transformation_signal`). |
| R7 narrow deltas | **WIDENED** | `forensic_asymmetry.py`: `psu_weight_increased` (verb-gap + reversed order), `new_metric_added` (date prefix optional, metric-noun anchored). Re-check occurrence counts after next scan before trusting the rarity weights. |
| R9 adjust-targets | **FIXED** | `psu_scoring.py`: alternative removed; genuine resets still fire via reprice/reset/recalibrate/lowered-hurdles. |
| R8 table harvest | mitigated | R1's guards remove the dominant junk class (comp-table dollars); window unchanged. |
| R10 aggregate over-fire | **FIXED** | `psu_scoring.py`: aggregate metric counts only if a mention sits OUTSIDE peer-group / covenant / definition context (`_AGG_NEGATIVE_CTX`). |
| C3 say-on-pay thresholds | **FIXED** | Unified 80/70 graduated dissent across `proxy_scan.py` gov and `psu_step_change.py` (was a bare <70 cliff in each, <80 in improvers). |
| S2 SOP coverage (39%) | **WIDENED** | `psu_forensics_v2.py`: result group now matches support / in favour / endorsed / shares voted; reverse 'support of X%' pattern added. |
| S1 8-K inducement grants | **FIXED** | New `inducement_grant_poll.py` sweeps recent 8-Ks for price-hurdle inducement/transformation grants between proxy seasons (the PLBY/Penguin gap) and emits detail records. |
| S3 frozen detail JSONs | **FIXED** | `psu_step_change.py` now also ingests the LIVE `proxy_scan*.json` shards + `induce_live_detail.json` (a real generator), not only the frozen one-off JSONs; handles dict + list sources. |

All behaviors locked in `tests/test_incentive_fixes.py` (each FP probe
paired with a genuine-positive probe). **Data note:** the stored
`proxy_scan.json` fields were extracted with the OLD regexes; scores
re-materialize at the next `--base` proxy rescan (no cached HTML in this
sandbox — the cache archive commits are ~2.6 GB and exceed the disk
allowance).
