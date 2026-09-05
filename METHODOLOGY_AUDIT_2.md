# Methodology audit — June 2026 (post-EDGAR rebuild)

**Branch:** `claude/yartseva-multibagger-database-lZS4a`
**State as of commit:** `38b709e`
**Universe:** 22,380 in asymmetry_global / 31,831 in raw yartseva CSVs
**Coverage layer:** SEC EDGAR XBRL (10,433 US filers, multi-year) + financedatabase global universe + yfinance fundamentals
**Scoring legs:** yartseva (Yartseva-paper-aligned), inflection (the dropped factors + 52w-high), berezin (internal microcap), upside (renorm composite), downside_floor (Graham-style), asymmetry = sqrt(upside × floor), inflection_asymmetry = sqrt(inflection × floor), m5_engine (Lindy ROIIC PEG), alta_fox (rebalanced)
**Archetypes:** 26 (9 original + 5 EDGAR ROIIC + 4 Lindy durability + 8 creative)
**Verdicts:** 175 GREEN, 278 YELLOW, 159 RED, ~21,768 UNRESEARCHED

This audit follows up on `METHODOLOGY_AUDIT.md` (commit `d415831`), which closed out the source-faithfulness of the Yartseva and Alta Fox legs. Most of those recommendations are now landed. What follows is **what's left or new**.

---

## 1. Coverage gaps still material

### 1.1 EV/EBIT and P/E remain 45% NaN universe-wide

Even after the yfinance-info fallback (`fill_fundamentals_gaps.py`) and the EDGAR layer:

| field | NaN % | reason |
|---|---:|---|
| `ev_ebit` | 45.6 | EBIT negative or zero for nearly half the universe; ratio undefined |
| `p_e` | 45.7 | trailing EPS negative or missing; forwardPE backstop only catches some |
| `ev_ebitda` | 27.1 | EBITDA negative for early-stage names |
| `net_debt_ebitda` | 26.0 | same root cause |
| `roce` | 22.7 | invested capital or EBIT missing |

**Implication.** Composite scores that reference these fields drop those legs and re-normalise — *not wrong*, but it means a name with negative EBIT effectively scores on fewer signals. The `Q` (QARP) and `arch_cheap_per_roiic` archetypes only fire when `ev_ebitda > 0`, so loss-making names structurally can't match those — that's correct.

**Action.** Acceptable as-is. The NaN rate is a property of the universe, not a bug.

### 1.2 ~2,461 US tickers have no XBRL data (concept_count = 0)

The SEC ticker map has 10,433 entries; only 7,972 have any us-gaap XBRL data. The other 2,461 are typically:
- ETFs and closed-end funds (no operating company facts)
- Recently-IPO'd names that haven't filed yet
- Trusts and partnerships using non-standard taxonomies
- OTC / pink-sheet shells

Those are correctly excluded from `edgar_universe_facts.csv`. No fix needed.

### 1.3 Foreign issuers (40-F/20-F) — currency not normalised

EDGAR's XBRL is mostly USD, but Canadian (40-F) and foreign (20-F) filers can submit elements in their reporting currency. We extract via the `USD` unit only, so a CAD-reporting issuer's revenue might come back zero. The downside is conservative (we under-report rather than over-report).

**Action.** Low-priority. Add CAD / GBP / EUR unit chains in `_facts_unit_iter` if a specific name surfaces with broken EDGAR data.

### 1.4 Sector handling for Financials / REITs / Biotech is uneven

Top-100 has 8 financials (Cohen & Co, Astrum, AAME, Cocoon, Sequoia, Tong Hua + 2 others). For these:
- EV/EBITDA is meaningless (interest income = operating)
- ROIC framework breaks (leverage IS the business)
- FCF is irrelevant (regulatory capital matters)

We **DO** exclude Energy/Materials/Financials in `alta_fox_score.py` (neutral 0.5 score per the audit), but the **archetype_tags.py + asymmetry_rank.py** legs don't sector-condition.

**REITs**: We never compute P/FFO or P/AFFO; we'd under-weight quality REITs at high P/E and over-weight on net-cash trash.

**Action — recommended fix.** Add a per-sector adjustment in `archetype_tags.py`:
- Financials: use P/B + P/E + dividend yield as the value triplet, skip cheap_per_roiic
- REITs: skip everything cash-flow-based; lean on P/B and asset_5y_cagr
- Biotech / pharma early-stage: already excluded by `is_pharma_bio` filter — works.

### 1.5 18 of 26 archetypes are EDGAR-only

Non-US names are at a structural disadvantage in `archetype_count` because they can't match: DurableReinvest, CashReinvest, ROICInflect, CheapPerROIIC, TangibleValue, LindyMargin, LindyFCF, NoDilution, LindyGrowth, QuietCompounder, BuybackCompounder, OwnerOperator, QARP, ReinvestInflect, DoubleInflect, CashQuality, CapitalLightPivot.

That biases archetype_count rankings toward US names regardless of underlying quality.

**Action — recommended fix.** Add a per-region archetype_count percentile or normalise by "archetypes available given coverage." A simple fix: `archetype_count_pct = archetype_count / archetypes_available_for_this_name`.

---

## 2. Methodology gaps (untested assumptions)

### 2.1 No backtest / validation

We've never confirmed that a name matching `QuietCompounder` actually outperformed over 2018–2025, or that the M5 engine score predicts the realised cumulative return. Our thresholds (Lindy ROIIC ≥ 15%, asset 3y CAGR ≥ 5%, etc.) are eyeballed from the literature, not fitted.

**This is the single biggest gap in the framework.**

**Action — recommended.** Build `backtest_archetypes.py`:
1. Re-extract EDGAR XBRL for **fiscal years ending 2017–2019** ("entry" cohort) — XBRL goes back that far for most US filers
2. Re-compute every archetype on the *2018-vintage* universe
3. Pull total-return data 2018-2025 from yfinance
4. Compare mean / median 7y total return by archetype match (with proper survivorship adjustment for delistings)
5. Report which archetypes have realised excess vs market and which don't

This validates the framework empirically.

### 2.2 Survivorship bias is real

Our universe is *today's* listed names. Companies that 5x'd from 2018 lows and are now overextended sit in our top-50; companies that went to zero have been delisted and don't appear. A 7-year backtest would have to use the **historical** ticker map, not today's.

For now, the bias inflates the *apparent* hit rate of the framework. Real predictive power is lower than what a backtest on the current universe would suggest.

### 2.3 Composite weights are still subjective

The Yartseva composite weights (0.30 FCF yield + 0.15 B/M + 0.10 size + 0.15 profit level + 0.15 asset gate + 0.15 contra-momentum) were chosen to match her paper's emphasis, not fit to data. Similarly the M5 engine score's 4 legs are equal-weight.

**Action — defensible.** A backtest would let us re-fit. Until then, equal-leg composites are the honest default.

### 2.4 Tier cutoffs in `nms_multibagger_candidates` are arbitrary

`archetype_count ≥ 3 + cluster_n ≥ 3 + asymmetry ≥ 0.40 = STRICT`. No reason 3/3/0.40 vs 2/4/0.45.

**Action.** Run a percentile-based STRICT (top 5% by archetype_count) and see if the list materially changes. If it doesn't, the cutoffs are fine.

### 2.5 The post-rally factor may overcorrect compounders

Names like Constellation Software / Topicus that have rallied 100%+ over 12 months but are still legitimate compounders get demoted by `post_rally_factor`. Yartseva's contra-momentum applies to *entry*; for an ongoing thesis it can be wrong.

**Action — partly addressed.** We already added `inflection_score` (which positively weights momentum) as a parallel composite. Names like that DO show up in the inflection top-N. The asymmetry top-N just doesn't lead with them.

---

## 3. Implementation issues

### 3.1 Price freshness varies — top names may have stale mcap

Cached yfinance prices come from runs of June 9, 20, 23. Median balance-sheet date is 85 days old, but momentum and mcap are tied to whatever date the last yfinance scrape ran. A name that's moved 30% since then has an off-by-30% mcap.

**Action — recommended fix.** Add a `refresh_top_n_prices.py` that hits yfinance.download for just the top-500 by asymmetry. Bounded request count, less likely to rate-limit.

### 3.2 The candidate tier definition doesn't use the EDGAR M5 score

`tier()` in the candidates pipeline still uses only `archetype_count`, `cluster_n`, `asymmetry_score`. With 17 EDGAR-driven archetypes, the M5 engine score is structurally informative but isn't directly in the tier logic.

**Action — recommended fix.** Promote names with `m5_engine_score ≥ 0.5` even if archetype_count is one short of the STRICT threshold (and demote names with `m5_engine_score < 0.2` even if they hit the count).

### 3.3 Tangible equity going negative isn't a fault for high-ROIC platforms

We compute `tangible_equity = equity − goodwill − intangibles`. For acquisition-roll-up compounders (Constellation Software, Lifco, Halma, Watsco etc.), tangible_equity is often negative — by design — because they paid premium for great businesses. Our `arch_tangible_value` requires P/TB < 0.7 AND tangible_equity_pct > 0.50, which correctly **doesn't fire** on these names. So far so good.

But: `tangible_equity` is **a key feature**, not a flag for "weak balance sheet." We need to be careful not to penalise it elsewhere. Currently `arch_tangible_value` is the only place it lives, so this is fine.

### 3.4 Insider transaction data not used

We score insider ownership LEVEL but not RECENT BUYING. SEC Form 4 filings would tell us when management is putting cash in vs taking it out. This is one of the strongest single signals in the multibagger lit.

**Action — recommended fix.** New extractor `edgar_form4.py` that pulls insider transactions from EDGAR's Form 4 endpoint. Add archetype `arch_insider_buying` for names with net insider purchases > 0 in the last 90 days.

### 3.5 No FFO/AFFO for REITs

Already noted in §1.4.

### 3.6 No dividend/buyback policy signal

We score `shares_growth_3y / 5y` (dilution check) but not the **policy**: dividends announced, buyback authorisations, debt paydown commitments. EDGAR has all this in 8-K filings.

**Action — medium-priority.** New extractor `edgar_capital_returns.py` that summarises dividends declared YoY + buyback announcements + debt paydown rates.

---

## 4. Conceptual gaps

### 4.1 No industry tailwind overlay

A name with Lindy ROIC 20% in a declining industry (cable TV, fixed-line telecom, gold-mining-with-no-find) has different multibagger odds than the same metrics in a growing industry. We don't capture industry growth or competitive set.

**Action — hard but valuable.** Pull industry-level revenue growth from FRED / S&P / IBISWorld, attach a 1.0 / 0.85 / 0.70 multiplier to the asymmetry score depending on whether the industry's 5y trend is up / flat / down.

### 4.2 No macro overlay

Yartseva's #7 factor is "stable or declining interest rates." We don't factor in macro (rate cycle, USD trend, regional credit conditions, sector rotation). Implicit assumption: macro neutral.

**Action — low-priority.** Add a `macro_overlay_multiplier` based on 10y Treasury direction, USD index, and credit spreads. Apply uniformly to entry_today_asymmetry.

### 4.3 No portfolio construction layer

We deliver ranked lists. No correlation matrix, no sizing model, no "you already have 5 cash-rich HK names, this 6th is correlated." The user has to do portfolio construction in their head.

**Action — large project.** Build `portfolio_construct.py` that takes a target capital, max position size, max sector / region / archetype exposure, and proposes weights via mean-variance or risk parity.

### 4.4 Time-horizon mismatch

A QuietCompounder is a 5-7 year thesis. A DeadOption is a 1-2 year mean-reversion. Our framework treats them identically. Realised returns will compound very differently — and the asymmetry score doesn't time-discount.

**Action — medium.** Tag each archetype with an expected horizon. Surface in the per-name pages.

### 4.5 Qualitative thesis decay

A verdict from January 2026 may be stale by June. The Rajesh Exports case (RED in Jun-2026 after being UNRESEARCHED for months) shows how fast theses can break. We have static verdicts and no automatic news-watch.

**Action — recommended.** Add a `verdict_date` column and an automated `news_watch.py` that flags any verdict-bearing name that's had a material news event (earnings miss, regulator action, CEO change) since the verdict date.

---

## 5. Quality / governance issues

### 5.1 No unit tests on the scoring functions

`compute_yartseva_score`, `composite_engine_score`, `lindy_aggregates` etc. have no tests. A refactor could silently break the pipeline.

**Action — recommended.** Add `tests/test_scoring.py` with golden-row examples.

### 5.2 Methodology not versioned

We've changed the Yartseva composite weights twice. There's no record of which version of the methodology produced which version of the workbook.

**Action — recommended.** Stamp each workbook's cover with a methodology version (e.g. v3.0 post-EDGAR), and keep a `CHANGELOG.md`.

### 5.3 Archetype match strength is binary

A name with `arch_quiet_compounder = 1` matching at the threshold edge (ROIC 0.151) scores the same as one matching strongly (ROIC 0.300). All archetypes are 0/1.

**Action — medium.** Add `_score` variants of each archetype that report match strength on [0, 1]. Surface alongside the binary flag.

### 5.4 No conviction probability

We have scores but no probabilistic interpretation. "Asymmetry 0.65" doesn't tell you "there's a 70% chance of 3x in 5 years."

**Action — depends on backtest** (§2.1). A historical hit-rate by archetype would give us a clean probability.

---

## 6. Prioritised fix list

### Immediate (low cost, high value)

1. **Sector-conditional archetype scoring** (§1.4) — branch in archetype_tags.py for Financials, REITs.
2. **Promote M5 into the candidate tier definition** (§3.2) — already have the score; just use it.
3. **Refresh prices for top-500 names** (§3.1) — fixes stale mcap on the deliverables.
4. **Normalise archetype_count for EDGAR availability** (§1.5) — non-US names stop being penalised.

### Next (medium cost, high value)

5. **Backtest the archetypes against 2018–2025 returns** (§2.1) — single biggest credibility uplift.
6. **EDGAR Form 4 insider transaction signal** (§3.4) — strongest single multibagger signal we're missing.
7. **Methodology versioning + CHANGELOG.md** (§5.2) — cheap governance.
8. **Per-archetype expected holding horizon** (§4.4) — surfaces on per-name pages.

### Later (high cost, high value)

9. **Industry-tailwind overlay** (§4.1) — needs external industry-growth data.
10. **Portfolio construction layer** (§4.3) — meaningful project.
11. **REIT-specific scoring (P/FFO, P/AFFO)** (§1.4) — extends coverage.

### Defer / accept

- Field NaN rates (§1.1) — universe property, not a bug.
- ETFs / non-XBRL US (§1.2) — correctly excluded.
- Macro overlay (§4.2) — speculative until backtest done.

---

## 7. What we got right

To balance the gap list:

- **Source attribution** (post `d415831`): real Anna Yartseva CAFE WP 33 cited, internal frameworks honestly labelled, no fictional Pew/Berezin/Yellowbrick references in deliverables.
- **EDGAR XBRL extraction** is solid: 7,972 US filers with audited multi-year fundamentals, no rate-limit hangs after the initial pass.
- **ROIC / ROIIC / Lindy framework** is mathematically clean: clipped denominators, multi-window medians, cash-on-cash variants.
- **Geometric-mean asymmetry** correctly forces both upside and downside floor.
- **Renormalised-weight scoring** doesn't penalise sparse-data names.
- **Harvard formatting spec**: numbers are real numbers, formats applied at the cell layer, em-dash on missing, parens on negatives.
- **18 EDGAR/Lindy/creative archetypes** capture patterns single-period data couldn't.
- **Coverage**: 22,380 names ranked, 448 verdicts on file, no architectural blockers to adding more.

---

## 8. Bottom line

The framework is **methodologically defensible** (source-faithful, mathematically clean, honestly labelled) and **practically useful** (delivers ranked candidate lists with diligence verdicts). Its biggest weakness is **no backtest** — every threshold and weight is plausible but unfit. Closing that gap (item #5) is the highest-leverage next step.

Secondary gaps cluster around **sector handling** (financials/REITs need specific scoring), **insider-transaction signal** (highest-known unused multibagger predictor), and **archetype-count normalisation** (so non-US names aren't structurally disadvantaged).

None of these undermine the current deliverables — they're improvements, not corrections.
