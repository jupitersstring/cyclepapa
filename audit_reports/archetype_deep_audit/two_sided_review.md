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
