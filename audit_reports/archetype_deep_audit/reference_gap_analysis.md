# Reference-Gap Analysis — our 82 archetypes vs the Master Reference + Compendium

Two user-supplied canonical taxonomies (Master Archetype Reference: 87 archetypes /
7 domains; The Archetype Compendium: 9 named archetypes + 5 playbooks + 2 advanced
frameworks) mapped against our 82 live `arch_*` rules. Goal: where are we missing
NUANCE or whole MECHANISMS. Grouped by data feasibility so we can act on the
buildable ones and flag the rest.

---

## Where we are already STRONG (faithful coverage)
- **Yartseva empirical screener** — our `asymmetry_score` IS the validated screener
  (FCF/P dominant, high B/M, near 12m low, negative 6m return). Well-modelled.
- **The Surviving Thing / Capital-Discipline / Regime-Change Cyclical** →
  regime_cyclical, capital_discipline, templeton_pessimism (maximum-pessimism).
- **The Optional Thing (option mispriced as dead)** → dead_option.
- **The Unlocked Thing (discount + catalyst / NAV / KPI threshold / regional blind-spot)**
  → discounted_vehicle, oak_nav_discount, kpi_threshold, blindspot.
- **First-Time Coverage & Earnings Divergence** → analyst_awakening,
  analyst_rerating_confirmed, asleep_at_wheel, narrative_lag.
- **Flyover / Quiet Compounder core** → quiet_compounder, owner_operator, lindy_*,
  liger_neglected_survivor.
- **Microcap Multibagger core** → wolf_trifecta, tenbagger_*, micro_activist_inflect,
  sustainable_scaler, no_dilution.
- **The 52w-high vs 12m-low contradiction** — we run BOTH sides deliberately
  (oneil/weinstein/kullamagie at highs; asymmetry at lows). Good.

---

## GAP CLASS A — missing MECHANISMS, buildable with data we already have

### A1. The Constraint / Bottleneck-Asset (HIGH value, we have NOTHING)
Reference domain I.B, the Akre AMT archetype, and half the Trade-Journal signals are
all one idea: *own a non-discretionary chokepoint; a big system can't scale without a
small component.* We have zero bottleneck coverage. Proxy we CAN build: sustained
HIGH + RISING gross margin (pricing power) + high ROIC + LOW capex-intensity +
niche/low-revenue-concentration — i.e. a "toll road" quality screen distinct from the
compounder screens. Won't capture "sole-source" (needs qualitative/scuttlebutt) but
the economic footprint is screenable.

### A2. Recurring-Revenue / Subscription Compounder (Den Fujita, Harpin) — MISSING
"Boring painful recurring problem solved by a low-ticket subscription" (HomeServe) and
Fujita's "women/mouth recurring consumables + record-everything chokepoints." We have
no recurring-revenue lens. We lack a true recurring-revenue field, but a proxy exists:
high + STABLE gross margin, low revenue volatility (multi-year), steady mid-teens
growth, high FCF conversion. Partial but worth a dedicated archetype.

### A3. Flyover low-coverage gate is MISSING on the compounders
The reference defines flyover quality as moat + ROIC>15% + **low analyst coverage
(<5, ideally 0)** + family control. We gate low coverage ONLY on the liger family;
quiet_compounder and owner_operator do NOT require it — so they surface well-covered
mega-caps that are the opposite of "undiscovered." Cheap fix: add a coverage tilt
(n_analysts low = the discovery gap) to the quiet/owner/lindy compounders, as a bonus
or a soft gate.

### A4. "Level, not growth RATE" (Yartseva) — our growth rules over-index on rate
The single most-cited empirical nuance: Yartseva finds the LEVEL of profitability /
FCF drives returns and the growth RATE is statistically insignificant; every
practitioner over-weights EPS growth. Our growth family (tenbagger, growth_algo,
cheap_sales_scaler, exceptional_evsg) gates primarily on growth RATE. Nuance: add / up
weight an FCF-yield / profitability-LEVEL floor so a high grower with thin cash returns
ranks below a moderate grower with a fat FCF/P.

### A5. Per-share revenue growth + 52w-high breakout (Andreola microcap) — partial
Andreola's CAN-SLIM-for-microcaps keys on **per-SHARE** revenue growth >15% and a
52-week-high/base breakout (dilution-proof growth confirmed by price). We have
fcf_per_share signals but our microcap growth rules use aggregate revenue growth and
don't require the price-confirmation Andreola insists on. Nuance: a per-share-growth +
near-high microcap variant (bridges wolf_trifecta and kullamagie).

### A6. Rule-Breaker "Already Re-rated" (Gardner sub-B) — partial via midcap_garp
"Multiple compressed 50%+ through EARNINGS growth, not price decline — grew into and
past its valuation" (Nvidia 131→40x). This is quality-growth at a high-but-falling
multiple — distinct from our cheap-GARP. midcap_garp is the closest but it gates on
cheapness; the Rule-Breaker is expensive-getting-cheaper. Worth a dedicated lens.
(Gardner sub-A "Expensive But Right / buy the overvalued top-dog first-mover" is a
DELIBERATE philosophical exclusion for a value/asymmetry desk — flag, don't build.)

### A7. Capital-Cycle SUPPLY signals (Marathon) — we have the demand side only
regime_cyclical / templeton fire on price + margin inflection (demand side). Marathon's
edge is the SUPPLY side: falling capex/depreciation ratio, industry consolidation,
reduced equity issuance, capacity withdrawal. We have capex_intensity and shares data —
a supply-discipline leg (capex being CUT + share count not expanding + consolidation) is
buildable and would sharpen the cyclicals from "cheap + bouncing" to "cheap because
capital has left."

---

## GAP CLASS B — missing MECHANISMS that need NEW DATA (event-driven sleeve)

The entire Special-Situations taxonomy (ref domains III & VIII, Compendium Part II-A/C
and the Assembly-Theory framework) is **filing-signal driven** and we capture almost
none of it. These are the cleanest bounded-downside asymmetries in the references.

- **B1. Spin-offs** (Form 10-12B) — the single best early-warning; forced-selling
  bottoms. Needs an EDGAR Form-10 scrape. We already harvest EDGAR, so buildable as a
  new pipeline, not from current columns.
- **B2. Insider CLUSTER buys done right** — we have insider_conviction, but the
  reference is specific: ≥3 unique insiders, code P (open-market), within ~10 days,
  ≥1 independent director, at sentiment troughs (Lakonishok/Lee: power is in small
  firms + purchases; clusters ~2x lone-buy returns). We have the SEC insider harvest —
  tightening insider_conviction to the true cluster definition is partly buildable.
- **B3. Net-net / NOL shells** — we have negative_ev_value / balance_sheet_return, but
  not NOL-shell mechanics (§382, monetization catalyst) — needs tax-asset data.
- **B4. Post-reorg equities (Assembly Theory)** — EBIT-yield>20%-at-emergence is the
  single most powerful screen; de-levering + intact moat is gating. Needs
  bankruptcy-emergence / fresh-start data. Not screenable from current columns.
- **B5. Merger-arb / tender / odd-lot / index-event / forced-selling** — needs deal
  and index-membership feeds.

---

## GAP CLASS C — a DELIBERATE TENSION worth a decision: the Preferreds Sleeve
We **scrub every preferred line** (and just hardened that scrub for Canadian `.TO`
prefs). The Compendium treats preferreds as a **first-class asymmetry source** — Korean
우선주 at 50–74% discounts to common with the Commercial-Code treasury-cancellation
catalyst is called "the widest structural asymmetry in the entire universe." So our
blanket scrub is correct for *contaminating the common-stock screens* but throws away a
legitimate, separate archetype. Decision point: build a dedicated `arch_preferred_discount`
(pref-vs-common discount + yield floor + cancellation/reset catalyst) that fires ONLY on
preferred lines, instead of only ever deleting them. Needs a pref↔common linkage +
discount field we don't currently compute.

---

## GAP CLASS D — NUANCE inside archetypes we DO have
- **Hidden-asset MISMARKING (Kerrisdale/Scrapyard):** tangible_value/oak_asset_floor use
  P/TB and NCAV, but miss the reference's core signal — a cross-holding / stake / property
  carried at HISTORICAL COST worth a multiple of mcap (Keisei's Oriental Land stake ~2x
  its own cap; unrevalued property). Needs investment/associate-holdings-at-cost data.
- **The Reclassified Thing (semantic migration / thematic camouflage):** narrative_lag
  captures accounting-progress-not-yet-paid, but NOT the re-CATEGORISATION mechanism
  ("the multiple changes when the noun changes" — HDDs→AI storage). This is inherently
  narrative/NLP — hard to screen, flag as out-of-scope-without-NLP.
- **Tillinghast "certainty / life span":** our lindy_* durability captures history length;
  the "predictability of cash flows" (low variance of margins/FCF) is a distinct,
  buildable quality dimension we don't score.
- **Convergence scoring** (Compendium's organising principle: rank by archetype-COUNT ×
  asymmetry × liquidity; "highest conviction scores 3+ archetypes simultaneously"). We
  compute archetype_count and asymmetry — a `convergence_score` = count × asymmetry ×
  liquidity-tier is a trivial, high-value addition that mirrors the reference's own
  top-level ranking and would surface multi-thesis names.

---

## Recommended priority (buildable-now, highest leverage first)
1. **Convergence score** (D) — trivial, and it's the reference's own master ranking.
2. **Flyover low-coverage tilt** (A3) — one-line-ish, sharpens the compounders.
3. **"Level not rate" FCF floor** on the growth family (A4) — tuning, empirically backed.
4. **Bottleneck / pricing-power quality** archetype (A1) — new, high-value, screenable.
5. **Capital-cycle SUPPLY leg** on the cyclicals (A7) — sharpens regime/templeton.
6. **Per-share-growth + near-high microcap** variant (A5).
7. **Recurring-revenue compounder** proxy (A2).
8. **Insider cluster-buy tightening** (B2) — partly buildable from the SEC harvest.
9. **Preferred-discount archetype** (C) — needs a data decision first.
10. Event-driven sleeve (B1/B3/B4/B5) — each is a new data pipeline; scope separately.
