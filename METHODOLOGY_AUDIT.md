# Methodology audit — Yartseva, Alta Fox, and the broader multibagger literature

**Date:** 2026-06-20. Auditing `yartseva_db.py`, `alta_fox_score.py`,
`pew_archetype.py`, and `asymmetry_rank.py` against primary sources.

---

## 1. Yartseva — substantially mis-attributed

### Source identified

Anna Yartseva, Lecturer at Birmingham City Business School, *"The Alchemy
of Multibagger Stocks: An empirical investigation of factors that drive
outperformance in the stock market,"* CAFE Working Paper 33 (Feb 2025).
Real person, real paper.

Sample: 464 US stocks delivering ≥1,000% returns 2009–2024; 11,600
company-year observations; 150+ variables; dynamic panel GMM + Fama-French
factor regressions.

Sources: [BCU open access](https://www.open-access.bcu.ac.uk/16180/),
[RePEc](https://ideas.repec.org/p/akf/cafewp/33.html),
[Multibagger Ideas Substack](https://multibaggerideas.substack.com/p/the-blueprint-for-1000-returns-part),
[StableBread summary](https://stablebread.com/464-10-baggers-research/).

### What Yartseva actually finds (7 statistically significant predictors)

| # | Factor | Threshold / direction |
|---|---|---|
| 1 | **Small size** | Median starting EV ~$348M; small-caps 37.7% annual excess vs. 9.7% large-cap |
| 2 | **High book-to-market** | B/M > 0.40 → 34.7% excess; **avoid negative-equity firms** (−7 to −18% annually) |
| 3 | **FCF yield** | **Strongest single predictor** — regression coefficients 46–82 |
| 4 | **Positive operating profitability** | Modest positive margins suffice — level matters more than growth |
| 5 | **Asset growth ≤ EBITDA growth** | **100% hit rate** in her sample; mismatched expansion shows −4.7 to −22.8 coefficients |
| 6 | **Near 52-week low / negative 3–6m momentum** | Contra-momentum entry; coefficient −0.67 to −0.92 |
| 7 | **Stable / declining interest rates** | Rising rates cost 8–12% |

### Factors Yartseva explicitly finds NON-predictive

Revenue growth, EBITDA growth, EPS growth, FCF growth, dividends, debt
levels, buybacks, R&D, analyst coverage, Altman Z, standard operating
profitability.

### Audit of `yartseva_db.py` (lines 57–68 weights)

| Our weight | Our factor | Reality |
|---:|---|---|
| 0.20 | Revenue YoY growth | **Non-predictive** per Yartseva — should drop |
| 0.15 | Revenue acceleration | **Non-predictive** — should drop |
| 0.15 | EBITDA margin expansion | Level matters, *expansion* specifically not tested |
| 0.15 | ROCE | She uses ROA — close cousin, defensible |
| 0.10 | CFO / EBITDA | Not in her framework |
| 0.10 | EV/Sales vs growth | Not her metric |
| 0.10 | **FCF yield** | **Her #1 factor — massively underweight; should be 0.25–0.30** |
| 0.05 | Leverage | Correct to deprioritize |

### "First-positive print" / inflection / acceleration cluster

Our code's signature concepts — "first-positive print," "inflection,"
"acceleration" — are **not in Yartseva at all**. They look closer to
O'Shaughnessy / CANSLIM earnings-turn signals or Jegadeesh-Titman price
momentum. She finds growth-rate signals non-predictive in her multivariate
models.

### What's missing entirely from our "Yartseva" leg

- **Book-to-market** factor
- **Hard size filter** at EV < $250M (we have soft bucket bins via Alta Fox, not Yartseva)
- **Asset-growth ≤ EBITDA-growth** gate — her only 100%-hit-rate signal
- **Near-52w-low / negative 6m momentum** contra-entry signal (we have the opposite — `momentum_12m` *positively* weighted in upside leg)
- **Negative-equity guard**

---

## 2. Alta Fox — three docstring errors, weights miss the spirit

### Errors in `alta_fox_score.py:1-35` docstring

1. **Initial screen was $150M–$10B, not "<$2B"**. The <$2B finding is
   post-hoc — 84% of the sample ended below $2B. Our size_score bins are
   reasonable; the docstring is wrong.
2. **Moat numbers are flipped**: 91% had moats (any), 80% had moderate-to-high
   *barriers to entry* (42% high + 38% medium). Our text reads "80%
   barriers, 91% advantages" — close but mis-orders.
3. **TSR decomposition missing entirely**: average TSR = 59.8% from EBITDA
   growth + 44.8% from multiple expansion + 1.6% from dividends. Median
   = 33.65 / 65.71 / 0%. **Multiple expansion is more than half of
   median TSR** — our docstring takeaway #4 ("don't rely on multiples")
   misreads this. Alta Fox said *don't demand a cheap starting multiple*,
   not that multiples don't matter.

### Coverage of Alta Fox's 5 takeaways

| Takeaway | Captured? | Weight |
|---|---|---:|
| 1 — Moat / positioning (91% had moats) | **MISSED** — no moat / barriers / gross-margin-stability proxy | 0% |
| 2 — Financial health (88% started healthy) | Captured weakly via `net_debt/EBITDA` | 5% |
| 3 — Accretive M&A (56% used acquisitions) | **MISSED** — no goodwill growth, no serial-acquirer flag | 0% |
| 4 — Don't over-rely on multiples | **INVERTED** — we give cheapness the *highest* weight | 20% |
| 5 — International universe | Captured well | 20% |

### Fields loaded but unused in `alta_fox_score.py`

Lines 58–64: `roce`, `insider_ownership_pct`, `fcf_yield`, `cash_pct_ev`,
`gross_margin` all sit in the dataframe and never contribute to the
score. Mayer (100 Baggers), Greenblatt (magic formula), Russo (capacity
to suffer), Huber (Saber Capital reinvestment moat) all emphasize ROIC
and insider ownership. We've loaded them and ignored them.

Sources verified:
[Alta Fox PDF](https://static1.squarespace.com/static/5aaacb57506fbe4636414126/t/651dc6626edc551193e83dfe/1696450148005/Makings+of+a+MultiBagger.pdf),
[Behind the Balance Sheet recap](https://behindthebalancesheet.substack.com/p/what-makes-for-a-multi-bagger),
[Multibagger Ideas masterclass](https://multibaggerideas.substack.com/p/a-masterclass-in-what-actually-drives),
[Compounding Quality](https://www.compoundingquality.net/p/-how-to-find-multibaggers).

---

## 3. Broader literature cross-check

| Source | Core idea | Captured? |
|---|---|---|
| Mayer, *100 Baggers* (2015) | High ROIC (>20%), owner-operator (≥10–20% insider), long runway, retained-earnings reinvestment | ROIC and insider both **loaded but unscored** |
| Phelps, *100 to 1* (1972) | Long holding period; reinvestment runway / TAM | Snapshot screens can't price horizon; no TAM proxy |
| Dorsey, *Little Book That Builds Wealth* | Moats: switching costs, network effects, intangibles, cost advantage | **Not captured** |
| Greenblatt, *Magic Formula* | ROIC + earnings yield | Earnings yield captured (`p_e`, `fcf_yield`); ROIC unused |
| Russo, *Capacity to Suffer* | Family/insider-controlled, reinvestment runway | Insider field loaded, unused |
| Saber Capital / John Huber | Reinvestment moat = high ROIC + long runway | **Not captured** |

---

## 4. Naming / attribution issues

- **Yartseva**: real published source, but our module's signature signals
  ("first-positive print," inflection, acceleration, heavy revenue-growth
  weights) **contradict** her findings. Either rename the module or
  realign the weights — currently we're crediting her with the opposite
  of what her paper concludes.
- **Alta Fox**: real published source. Docstring errors are fixable;
  weights need rebalancing.
- **"Berezin / Stockcoach" methodology** (`yartseva_db.py:149`): no
  identifiable public investor by this name surfaces in search. The
  scoring leg is a hand-rolled deep-value composite (P/S, P/E, gross
  profit / mcap, insider, debt/equity). Defensible, but the attribution
  is fictional or internal.
- **"PEW setup"** (`pew_archetype.py:1-10`): no identifiable public
  investor by this name. The 6-criterion checklist (negative EV +
  outgrowing + breakeven + insider + nascent platform + forgotten) reads
  as a sensible Ian Cassel / MicroCapClub-style hand-rolled checklist,
  not a published framework. Same attribution gap.
- **"Yellowbrick" archetype taxonomy** (referenced in
  `build_harvard_workbook.py:570`): there is a real platform at
  joinyellowbrick.com hosting a "Multibagger Monitor" investor profile,
  but no formally published archetype taxonomy A–G. Our `archetype_tags`
  appear to be internal.

---

## 5. Concrete fix list

### `yartseva_db.py`

- Drop the 0.20 revenue-YoY weight and 0.15 revenue-acceleration weight
  (non-predictive per source).
- Raise FCF-yield weight to 0.25–0.30 (her dominant factor).
- Add a **book-to-market** component at ~0.15, with a hard negative-equity
  exclusion.
- Add a **size component** at ~0.10 favouring EV < $250M.
- Add an **asset-growth ≤ EBITDA-growth** filter (her only 100%-hit-rate
  signal; can be a hard penalty or a binary gate).
- Add a **near-52-week-low / negative 6m momentum** signal (~0.10).
- Either drop the "first-positive print" / "inflection" / "acceleration"
  cluster from the Yartseva composite or **rename them as house
  additions**, not Yartseva. They may still have predictive value (CANSLIM
  / Jegadeesh-Titman) but should be honestly labeled.
- Swap ROCE for ROA, or expose both.

### `alta_fox_score.py`

- **Fix docstring**: $150M–$10B initial screen; 91% moats vs 80% barriers;
  add TSR decomposition (59.8% EBITDA growth + 44.8% multiple expansion).
- **Add ROIC component** (10%) using already-loaded `roce`: ≥20% → 1.0,
  15–20% → 0.6, 10–15% → 0.3.
- **Add insider-ownership component** (5%): ≥10% → 1.0, 5–10% → 0.6.
- **Add serial-acquirer flag**: detect goodwill / total-assets growth, or
  use revenue growth exceeding organic norms.
- **Rebalance weights**: valuation 20→10, geo 20→10, health 5→10,
  ROIC 10, insider 5, M&A flag 5, sector 15, size 15, growth 15, margin 10.
- **Stop penalising EBITDA margin > 25%** (`margin_score = 0.6` band): high
  margins indicate the moat 91% of Alta Fox names had.
- Rename `val_score` to make clear it's a *not-extreme* filter, not a
  positive cheapness signal — that's what Alta Fox takeaway #4 actually
  means.

### `pew_archetype.py` / `asymmetry_rank.py` / `build_harvard_workbook.py`

- Either find a real public source for "PEW", "Berezin", "Yellowbrick"
  archetypes — or relabel them honestly as house frameworks.
- In the Harvard workbook References sheet, replace the fictional Yartseva
  citation ("(2024) Yartseva Capital") with the real BCU CAFE WP 33 entry.

### `asymmetry_rank.py`

- The 12-month momentum factor (`u_mom`, line 152) is **positively
  weighted** in the upside leg with weight 0.10. Yartseva finds the
  opposite signal predictive (contra-momentum / near 52w low). Either
  invert the sign for the Yartseva-aligned portion or split into two
  legs: "momentum continuation" (Jegadeesh-Titman) vs "contra-entry"
  (Yartseva). Currently they fight each other.

---

## 6. What we got right

- **Geometric-mean asymmetry** (sqrt(upside × downside_floor)) is a sound
  way to require both legs to fire — avoids the false-positive of high
  upside on a thin floor or thick floor with no upside.
- **Cash > EV / Graham net-net / sub-book downside floor** is well-grounded
  Graham heritage; correctly attributed.
- **Renormalised-weight scoring** (only-present components contribute,
  `_weighted_renormalised`) is the right answer for sparse non-US data.
- **Post-rally factor** is a sensible defence against picking already-run
  stocks — it's adjacent to Yartseva's contra-momentum finding even if
  we didn't derive it from her paper.
- **Alta Fox PDF URL** points to the right document; the 5 country list
  (UK/SE/DE/NO/AU), sector exclusions (Energy/Materials/Financials), and
  valuation thresholds (3x P/S, 20x EV/EBITDA, 30x P/E) are correct.

---

## Bottom line

Our `yartseva_db.py` implements a *plausible* multibagger composite, but
**most of its signature signals are not Yartseva's**. We're crediting her
with growth-and-inflection ideas that her own paper finds non-predictive,
and severely under-weighting her actual #1 factor (FCF yield).

`alta_fox_score.py` is closer to source, but **misses Alta Fox's two
biggest takeaways** (moats at 91% prevalence; M&A at 56% prevalence) and
**inverts the "don't rely on multiples" finding** by giving cheapness the
highest weight.

The fixes are mechanical and don't require redesigning the asymmetry
framework — they require honest source-attribution, weight
rebalancing, and adding the ROIC / insider / B/M / asset-growth-gate
signals that the literature actually emphasizes.
