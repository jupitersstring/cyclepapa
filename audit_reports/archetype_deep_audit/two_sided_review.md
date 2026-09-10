# Two-Sided Methodology Review (in progress)

Goal (per user): for EVERY archetype, does the rule (a) PROMOTE poor candidates,
or (b) DEMOTE/EXCLUDE good ones? The `.F` lesson generalized — a coarse rule that
drops legitimate names is as much a defect as one that admits junk. Save as we go.

---

## Part A — hunt for other `.F`-style coarse EXCLUSION heuristics (codebase-wide)

Reviewed every hard exclusion in archetype_tags / enrich / asymmetry_rank / book
builders. Verdicts:

### A1. `is_otc` → ex-otc books drop 10,329 names (22%) — MOSTLY BENIGN, one caveat
The top-ETA OTC names are almost all **F/Y-suffix US OTC lines of FOREIGN
companies** (CTTMF Catena/SE, YHEKF Yeahka/HK, WEBJF Web Travel/AU, BVNRY
Bavarian Nordic/DK, KMNCF Kingsmen/SG, RMGOF Remgro/ZA). These are the
FX-corrupt ADR duplicates — their real PRIMARY lines (BAVA.CO etc.) are already
in the pool, and there is a dedicated OTC book as the safety valve. So ex-otc is
largely excluding corrupt duplicates, not unique opportunities.
CAVEAT: a foreign micro whose ONLY scanned line is its US OTC ticker (primary
never scanned) would be lost from the main books. Bounded, and the OTC book
still carries it. → NOT a `.F`-class over-prune, but flag: consider a
"US-OTC-with-no-scanned-primary → keep in main books" rescue later.

### A2. mcap floors — hard $5M cut removes 4,135 nanos; $10M book floor hides 1,617
The $5M asymmetry_rank floor fully drops 4,135 sub-$5M names. Sub-$5M is
genuinely mostly untradeable / shell / delisted-data-corrupt, and Cassel's
microcap range is $5–100M REVENUE, not mcap — a $5M MARKET CAP is nano. Defensible
tradeability floor, but it IS a hard cut → note as the single largest blanket
exclusion; revisit if a lower floor + a liquidity gate is preferred.

### A3. non-common scrub (preferreds/warrants) — correct for EQUITY screens, but…
Scrubbing preferreds from common-equity archetypes is right, BUT the reference
treats Korean 우선주 / preferred DISCOUNTS as a first-class asymmetry source. This
is a MISSING ARCHETYPE (preferred-discount), not an over-prune of an existing one
— already logged in reference_gap_analysis as Class C.

### A4. is_operating (financials/REITs/utilities excluded from operating legs)
Not an over-prune: financials have arch_financials_value / oak_nav_discount;
REITs and utilities have their metrics honoured elsewhere. Right-metric-for-sector.

### A5. THE systematic prior-session issue (the true `.F` cousin): CURRENCY RATIO
### CORRUPTION. USD price ÷ home-currency fundamentals corrupts pb/pe/ps/ev_sales/
fcf_yield on every cross-listing/ADR line. It spawned dozens of prior fixes (the
pb<0.05 guard, ev_ebitda sign, the whole ratio-sanitizer suite) — each a SYMPTOM
patch. The FX-secondary scrub I just REVERSED was another symptom patch that also
cut real B-shares. The root cure is upstream per-name CURRENCY NORMALISATION in
the fetch layer (normalise price and fundamentals to one currency before ratios).
Until then: keep the names (don't drop), and prefer downranking a KNOWN-corrupt
ratio over excluding the name. Highest-value structural project outstanding.

### Reversed this session (rough exclusions that cut real opportunities)
FX-secondary venue scrub (.F/regional/B-share); one-off-ROCE blunt threshold →
consistency check; nol_shell US-domicile gate; financials_value ~_known_holdco.

---

## Part B — per-archetype two-sided top-20 review
(3 agents running; findings appended below as they report.)

### Part B findings — implemented directly (review agents hit session rate limit)

EXCLUDES-GOOD fixes (the priority direction — coarse rules cutting real names):

1. **Revenue floors $20M → $5M** on the microcap-growth archetypes
   (tenbagger_path, cheap_sales_scaler, exceptional_evsg, sustainable_scaler,
   bottleneck). The Cassel/Andreola reference is explicit: the multibagger
   sweet spot is **$5–10M REVENUE** businesses that scale to $30–40M. A $20M
   floor cut exactly that cohort. $5M still excludes the sub-scale base-effect
   shells (and the existing g10/profitability legs guard base-effect).
   Counts grew: tenbagger 2271→2514, cheap_sales_scaler →2466, etc.

2. **mcap floors $50M → $10M** on the microcap-value/contrarian archetypes
   (narrative_lag, dead_option, kpi_threshold, tangible_value). The reference
   microcap range is <$100M / often <$50M; a $50M floor cut the sweet spot.
   $10M still drops untradeable shells. narrative_lag 4158→5268, kpi 2647→3411.

3. **Neglect archetypes now KEEP zero-coverage names** (liger_asset_backed,
   liger_lagging_inflect, liger_neglected_survivor): changed
   `n_analysts_present & <=4` → `~(n_analysts_v > 4)` so a name with NO coverage
   data (the MOST neglected — the reference's "0 analysts, ideally") is kept,
   not excluded. mcap caps (<$400M) prevent mega-cap re-admit. Big count rise
   (liger_neglected_survivor 678→3392) — the other legs (survivability, cheap,
   no-dilution, inflection) keep it selective.

4. **post_reorg reorg window 2yr → 5yr** (edgar_event_signals): the 2-year cut
   excluded the 2021–22 emergence cohort (Gulfport, Bristow) that is still a
   valid cheap-emerger; 5yr keeps them while dropping the ancient 2009 ones
   (Pilgrim's Pride, Lear). Targeted reorg-only re-fetch running.

Also (from the top-ticker sweep, already committed): FX-secondary venue scrub
REVERSED; one-off-ROCE blunt threshold → consistency check; nol_shell
US-domicile gate removed; financials_value ~_known_holdco removed.

### Part B — data-driven junk scan (all 87 archetypes, top-20 firers)

Scanned every archetype's top firers for red flags (deep operating loss,
extreme leverage, cash burn, sub-scale revenue, out-of-band P/B). 28/87 are
totally clean. Of the flagged rest, MOST are THESIS-CONSISTENT, not defects:

- biotech_deep_value (melt/burn): by DESIGN — the thesis is cash-rich burners
  trading below net cash. The burn IS the setup. Correct.
- levered_inflection, weschler_levered_equity, asymmetric_assembly (leverage):
  leverage is in the thesis (a levered equity stub / rollup). Correct.
- financials_value, analyst_awakening (financial names showing "melt"/"burn"):
  op_margin and fcf_yield are not meaningful lenses for banks/insurers — a
  metric artifact, not junk. The archetypes gate is_financial correctly.
- asleep_at_wheel (a melter like MDX.BK topping the ETA sort): NOT a defect.
  There is an explicit user design decision (no quality FLOOR; quality is
  UPWEIGHTED in asleep_score instead) — the melter is a real estimate-beater
  that asleep_score correctly ranks near the bottom. My scan sorted by GLOBAL
  ETA, so it over-flagged names that top the list via OTHER archetypes. Lesson:
  judge an archetype by its OWN rank score, not global ETA.

GENUINE promotes-junk found and FIXED this pass:

5. **post_reorg — gate on OPERATING yield, not p_e.** A fresh-start company's
   trailing net income is inflated by the one-off debt-discharge gain:
   WeightWatchers posts $1.02B "net income" on $701M revenue (mcap $180M) — a
   p_e of 1.56 that is pure reorg gain, not earnings. That fake earnings yield
   passed the generic _excellent_value; only the leverage cap accidentally
   caught it. Now gated on EV/EBIT or FCF yield (Verdad's lens, immune to
   discharge gains). WW is robustly excluded on value (real EV/EBIT yield 5.8%,
   FCF negative). post_reorg fires 0 today — HONEST: the reorg XBRL concept only
   marks 9 names in the 5yr window and none is operationally cheap. Not forced.

6. **diversified_segments — add the sibling's distressed-shell guard.** It was
   a bare structural label (4+ segments, HHI<=0.40) with NO survivability gate,
   while its sibling geographic_global already drops shells with
   (fcf_ttm>0)|(ebitda_margin>0.05). So CETX (fcf -131%) and AMTD (op -336%)
   wore a "diversified = resilient" label their numbers contradict. Mirrored the
   sibling's guard: 208→192 firers (dropped 16 distressed shells, kept every
   real diversified operator). A consistency fix, not a new heuristic.

Not changed (deliberate): nol_shell burn (a monetizable-NOL shell need not be
FCF-positive; _not_melting already guards it); momentum archetypes
(oneil_canslim, weinstein_stage2, kullamagie_breakout) admitting growth burners
— a momentum screen legitimately prices growth, and these carry their own
technical gates.

### Pipeline note (for reproducibility)
The canonical asymmetry_global.csv is the ENRICHED base (fcf_yield, cfo_*,
op_margin, …) built up across sessions from yfinance/EDGAR merges. Re-running
`asymmetry_rank.py` (step 1 of build_asymmetry_global.sh) REBUILDS the base from
the per-country yartseva snapshots and DROPS those enrichments (they are not in
the raw snapshots), which then breaks archetype_tags/enrich with scalar-vs-Series
errors. Correct refresh path: keep the committed asymmetry_global.csv as the
base, run archetype_tags.py then enrich_asymmetry_global.py directly (both are
idempotent w.r.t. the base fundamentals; enrich re-derives ETA + nulls 213
price-ghosts + corrects src suffixes each run). The full rebuild is only valid
after re-fetching the source enrichments.
