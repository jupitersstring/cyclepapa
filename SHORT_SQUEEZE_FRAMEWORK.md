# Short-Squeeze Candidates — Metastudy & Systematic Framework

A research-grounded framework for (a) identifying genuine short-squeeze setups and
(b) — just as valuable — *disqualifying* the much larger set of heavily-shorted
names where the short side is comfortable and the stock is more likely to grind
down than to squeeze.

This document is the research half. The implementation is `short_squeeze.py`
(scoring engine + two detectors, zero third-party dependencies in the core) and
`test_short_squeeze.py` (28 stdlib tests).

---

## 0. TL;DR — the one thing that matters

> **Utilization is the signal.** Not short-interest %, not days-to-cover, not the
> borrow fee on its own. Utilization = *shares on loan ÷ shares available to lend*
> — i.e. how exhausted the lendable supply is. When utilization is low, shorts
> have room and cannot be forced; when it is near 100%, the supply that lets
> shorts stay short is gone, and any forced recall has nowhere to source stock.

This is the central result of **Paul Schultz, "Short Squeezes and Their
Consequences," *Journal of Financial and Quantitative Analysis* (JFQA) 59(1):
68–96, Feb 2024** (online Jan 2023; SSRN WP 4025226, Feb 2022; data: IHS Markit
2006–2019). Both figures cited in the brief check out (see §1).

Everything else in this framework is a refinement of, or a complement to, that
result.

---

## 1. Verdict on the seed claims

| Claim (as briefed) | Verdict | Detail |
|---|---|---|
| Schultz, JFQA, ~Feb 2024, "short squeeze" paper | **Confirmed** | Full title *"Short Squeezes and Their Consequences"*, JFQA **59(1):68–96**, print Feb 2024 / online Jan 4 2023 / SSRN Feb 2022. Notre Dame. Data: IHS Markit, 2006–2019. |
| **Utilization is the single best predictor** (beating SI%, days-to-cover, borrow rate alone) | **Confirmed** | Reported as "the single best predictor" / "number one determinant" of all-lender squeezes. Squeeze frequency rises from **~1 per 40 years at ≤25% utilization** to **~1 per 11 days at ≥90%**. |
| **Borrow-rate mean ≈ 2.67%** | **Confirmed** | Mean annual loan fee = **2.673%**. |
| **Borrow-rate 95th percentile ≈ 11.0%** | **Confirmed** | p95 = **11.0%**; median = p25 = **~0.375%** (37.5 bp — the general-collateral floor). The mean sits far above the median because a thin tail of "special" names drags it up. |
| Bearish-convergence: SI>10% + util<50% + borrow<3% = genuinely short | **Adopted, with a nuance** | Well-supported as a *squeeze disqualifier* (low utilization + cheap borrow ⇒ shorts can't be forced). As a *bearish* signal it is directionally right (shorts are informed on average) but note the academically *strongest* underperformance lives in **expensive**-to-borrow names, not cheap ones (Drechsler & Drechsler 2014). See §6. |

**Sourcing caveat (be honest about it):** the exact fee figures (2.673% / 0.375% /
11.0%) and the squeeze-frequency numbers were verified against a detailed
secondary write-up of the paper (The Evidence-Based Investor), reproduced
consistently across retrievals, **not** extracted from the publisher PDF directly
(SSRN/ResearchGate returned 403; the Cambridge PDF would not text-extract in the
research environment). They are internally coherent and match the brief exactly,
but final sign-off should be against Table 1 of the published article. No AUC /
pseudo-R² statistic was located; Schultz presents predictive power via squeeze
frequencies conditional on utilization/fee buckets and via portfolio sorts.

---

## 2. What a squeeze actually *is* (mechanics)

A short seller borrows shares, sells them, and must eventually buy them back.
A **short squeeze** is *forced or panicked buying-to-cover* that feeds on itself:
rising price → losses + margin calls / recalls → covering → more buying → higher
price. Schultz formalises the *forced* part through the lending market with two
definitions:

- **All-lender squeeze:** shares *available to lend* fall below shares *on loan*
  the previous day — the entire lendable pool can no longer support existing
  loans, so recalls must happen.
- **Current-lender squeeze:** total shares available and shares on loan fall by
  the *same amount on the same day* — a specific lender pulls supply and that
  borrower is forced out.

Two related but distinct feedback loops are usually conflated:

- **Short squeeze** — forced *covering* in the cash market (the above).
- **Gamma squeeze** — dealers who sold call options are short gamma; as the
  stock rises they must buy shares to delta-hedge, which pushes it higher. GME
  and AMC (2021) were short squeezes *amplified* by gamma. Gamma needs an
  optionable stock with concentrated near-the-money call buying.

The S3 Partners refinement is essential and often missed: **a short that is still
profitable cannot be squeezed.** No one is forced out of a winning trade. A real
squeeze requires the average short to be *under water* — net-of-financing
mark-to-market **losses**. Crowding is necessary, not sufficient; pain is the
trigger.

---

## 3. The metrics — definitions, distributions, thresholds

All percentages below are in percent units. Thresholds are the bands used in
`short_squeeze.py`.

### 3.1 Short interest % of float — `d33` (weakest of the three)
- **Def:** shares sold short ÷ free float. (Use **float**, not shares
  outstanding; insiders/strategic holders aren't really borrowable, so % of
  shares-outstanding understates the true squeeze pressure.)
- **Source/lag:** FINRA, **twice a month**, published on the **7th business day
  after** the settlement date — *stale by construction*.
- **Why weak alone:** heavily-shorted stocks *under-perform on average* (§5).
  High SI is mostly a bearish tilt; it only becomes squeeze fuel when borrow is
  scarce and dear.
- **Bands (→ 0–100):** <5 → 0 · 5–10 → 20 · 10–20 → 40 · 20–30 → 60 · 30–50 → 80
  · >50 → 100. **Weight 0.20.**

### 3.2 Utilization % — `d34` (THE signal)
- **Def:** shares on loan ÷ shares available to lend (lendable supply). 0% = none
  borrowed; 100% = the lending program is tapped out.
- **Source/lag:** securities-lending vendors, **daily**.
- **Why it dominates:** it measures the *room shorts have left*. Schultz:
  ≤25% ⇒ squeeze ~1/40yr; ≥90% ⇒ ~1/11 days — a steep, convex relationship.
- **Bands:** ≤25 → 0 · 25–50 → 15 · 50–70 → 35 · 70–85 → 60 · 85–95 → 85 · >95 →
  100. **Weight 0.50 (highest).**

### 3.3 Borrow rate / cost-to-borrow %/yr — `d35`
- **Def:** annualised loan fee a short pays to borrow (a.k.a. CTB, loan fee;
  the rebate rate is its mirror image). "General collateral" (GC) = cheap/easy;
  "special" = expensive/scarce.
- **Distribution (Schultz):** median ≈ p25 ≈ **0.375%** (the GC floor),
  **mean 2.673%**, **p95 11.0%**. ~Half of all names sit at the floor.
- **Markit DCBS:** a 1–10 "Daily Cost of Borrow Score", 1 = GC, 10 = most special.
- **The level vs the *trend*:** a *spiking* fee is an earlier and better tell than
  a high static level — it means demand is overrunning supply right now.
- **Bands:** ≤0.5 → 0 · 0.5–1 → 10 · 1–3 → 25 · 3–10 → 55 · 10–25 → 80 · >25 →
  100. **Weight 0.30.**

### 3.4 Supporting context (used by the detectors, not the core score)
- **Days to cover / short ratio** = shares short ÷ avg daily volume. >5–10 = a lot
  of covering demand relative to liquidity. Weak as a stand-alone predictor in
  Schultz, but it sizes the *fuel* once a squeeze starts.
- **Free float / low-float:** a small float makes every other metric more
  explosive (VW, KOSS).
- **Institutional ownership:** high institutional ownership ⇒ more lendable
  supply ⇒ lower utilization/fee; low/concentrated ownership ⇒ thin supply.
- **Short-side P&L proxy** (`price_vs_short_cost_basis_pct`): how far price is
  above the average short's entry; >0 = shorts under water (squeezable).
- **Utilization & fee *trends*:** acceleration is the signal.

---

## 4. Ranked predictors by evidence strength

1. **Utilization %** — *strongest.* Schultz's headline; direct measure of supply
   exhaustion. (Requires a lending feed.)
2. **Borrow fee, especially its *trend*** — strong. The price of scarcity; the
   right tail (>10%, ≈p95) is squeeze-prone. (Lending feed.)
3. **Short-side mark-to-market pain** — strong *as a gate.* No pain, no squeeze
   (S3). Hard to observe precisely; proxy via price vs estimated short cost basis.
4. **Float / liquidity (days-to-cover)** — moderate; an amplifier, not an
   initiator.
5. **Short interest % of float** — *weak alone*, despite being the headline
   number. Necessary backdrop, low incremental predictive value.
6. **Catalyst** (earnings, news, index event, activist, retail coordination) —
   necessary as a *spark*, but not screenable from lending data.

---

## 5. The academic backbone (why high SI ≠ buy)

| Finding | Source |
|---|---|
| ~91% of borrowed stock is GC at ~17 bp; ~9% "special" averaging 4.30%; specialness ↑ with divergence of opinion, ↓ with size/institutional ownership. | D'Avolio (2002), *JFE* 66(2–3):271–306 |
| Highest-SI-percentile **and** lowest-institutional-ownership stocks under-perform **−215 bp/mo equal-weighted** (significant), but only −39 bp/mo value-weighted (insignificant) — the effect is a small-cap phenomenon. Constraints are rare (~21 stocks/mo). | Asquith, Pathak & Ritter (2005), *JFE* 78(2):243–276 |
| Heavily-shorted under-perform lightly-shorted by **~1.16% over the next 20 trading days** (~15.6% annualised); institutional non-program shorts most informative (−1.43%/mo). | Boehmer, Jones & Zhang (2008), *JF* 63(2):491–527 |
| A rise in **shorting demand** predicts **−2.98%** abnormal return the next month. | Cohen, Diether & Malloy (2007), *JF* 62(5):2061–2096 |
| The **shorting premium**: predictable under-performance concentrates in **expensive-to-short** names; anomalies largely *vanish* within the ~80% of stocks that are cheap to short. | Drechsler & Drechsler (2014), NBER WP 20282 |
| **Short-selling risk** (recall / fee-spike risk) is priced; it deters arbitrage and leaves stocks less efficient. | Engelberg, Reed & Ringgenberg (2018), *JF* 73(2) |
| Concentrated/short-term ownership ⇒ lower lending supply, higher shorting costs, more mispricing. | Prado, Saffi & Sturgess (2016), *RFS* 29(12):3211–3244 |
| Supply is least available exactly when shorts most want it; anomaly short-side returns concentrate in "special" stocks. | Beneish, Lee & Nichols (2015), *JAE* 60(2):33–57 |
| Short-sale constraints sustain gross mispricing (3Com/Palm stub ≈ **−$63/share**). | Lamont & Thaler (2003), *JPE* 111(2):227–268 |
| Social-network / "fanatic"-driven model of meme-stock bubbles (applied to GameStop). | Pedersen (2022), "Game On," SSRN 3794616 |

**Net:** shorts are informed more often than not. The base case for a high-SI
stock is *under-performance*, not a squeeze. This is exactly why a squeeze
screen must be built on the *fragility of the short side* (utilization, fee,
pain), and why a separate **bearish-convergence** detector is worth as much as
the squeeze detector.

---

## 6. The bearish-convergence detector (the counterintuitive part)

**Rule:** `SI% > 10  AND  utilization < 50%  AND  borrow_fee < 3%` ⇒ `GENUINELY_SHORT`.

Read it as: *a lot of capital is short, yet borrow is ample (low utilization)
and cheap (low fee).* The short side is **uncrowded and comfortable**. There is
plenty of stock to borrow, so no one can be forced to cover. This is the
signature of **sophisticated capital that is genuinely short on fundamentals** —
and it is the *opposite* of a squeeze setup. In the framework it **overrides** the
composite score: even a 22%-of-float short like this is classified
`GENUINELY_SHORT`, not a candidate.

**The honest nuance.** The brief frames this as a *bearish* signal. Directionally
that's supported — shorts are informed (Boehmer–Jones–Zhang; Cohen–Diether–
Malloy). **But** the academically *strongest* predictable under-performance is in
**expensive**-to-borrow names (Drechsler & Drechsler: anomalies vanish among the
cheap 80%). So a cheap, low-utilization short is most reliably read as
**"low squeeze risk,"** and only secondarily as "bearish." The cleanest use of
this detector is therefore as a **squeeze disqualifier** — it tells you *not to
buy this for a squeeze* — rather than as a strong stand-alone short thesis.

**The mirror image — squeeze fuel:**
`utilization ≥ 85  AND  SI% ≥ 10  AND  (fee ≥ 10  OR fee rising)  AND  shorts not
in profit`. Scarce, expensive, crowded, *and painful*. That is where Schultz's
−2.67%/month average **gross** short return is more than two-thirds eaten by
squeeze costs — i.e. where the tail risk to shorts is real.

---

## 7. Practitioner / vendor frameworks (how desks actually screen)

- **Ortex** — "Short Squeeze" signals (Types 1/2/3) over estimated short interest,
  **utilization**, **cost-to-borrow**, price, *and their rates of change*. Also a
  per-metric historical **percentile** (100 = highest SI in the stock's history).
- **S3 Partners (Ihor Dusaniwsky)** — **Crowded Score** (short interest as a *true*
  % of tradable float, including the synthetic longs that short selling creates)
  plus a **Squeeze Score** that overlays *financing cost* and *unrealised MTM
  losses*. 70–100 = squeezable; **>90 = significantly elevated risk.** Their stated
  principle: *a profitable short, however crowded, cannot be squeezed.*
- **Fintel** — "Short Squeeze Score," **0–100, 50 = average**, ranking names by
  squeeze risk *relative to peers* using short interest, % of float,
  days-to-cover, borrow fee, float and volume.
- **Markit / FIS Astec** — **DCBS** 1–10 borrow-cost score (1 = GC, 10 = special).
- **Interactive Brokers** — daily shortable-quantity and borrow-fee feed (a
  realistic free-ish source of the otherwise-paywalled lending data).

The common thread across all of them: the **lending market** (utilization +
borrow cost + their dynamics), *not* the headline short-interest number, is the
core of the score — which is exactly Schultz's point.

---

## 8. Case studies (with the caveat that peak figures are often disputed)

| Case | Peak short | Utilization / borrow | Float | Trigger & mechanism | Move |
|---|---|---|---|---|---|
| **GameStop**, Jan 2021 | **~140% of float** (Jan 22) | ~100% util; very high fee | small, low-float | Retail coordination (WSB) + **gamma squeeze** + Melvin covering | ~$4→~$120 split-adj (≈$483 intraday) then round-trip |
| **VW / Porsche**, Oct 2008 | **~12–13%** short vs **~6% free float** | no borrow left | tiny effective float | Porsche disclosed **74.1%** (42.6% shares + **31.5% cash-settled options**); Lower Saxony 20% ⇒ float gone | **€200 → ~€1,005** intraday in 3 days; briefly world's most valuable company; shorts lost ~**$30bn** |
| **AMC**, 2021 | very high % of float | ~100% util, high fee | large but retail-held | Retail + options gamma | multi-x, partial round-trip |
| **KOSS**, Jan 2021 | very high | tapped out | micro-float | WSB spillover | ~$3→~$64 |
| **BBBY**, Aug 2022 | ~40%+ of float | high | moderate | Activist (Ryan Cohen) + options | ~$5→~$30 then collapse |

Pattern: **low/locked float + ~100% utilization + a catalyst + options gamma**.
VW is the purest "supply gone" case (no Reddit, no gamma — just float
mathematics). GME is the purest "gamma-amplified retail" case. The high-SI-%
number is the *headline*, but in every case the *operative* variable is that
**there was no stock left to borrow** — utilization at the ceiling.

**Base rate / failure mode:** Goldman noted SI **>100% of float** occurred only
~**15 times in 10 years** — squeezes of the GME magnitude are genuinely rare.
Across the broad cross-section, heavily-shorted baskets **under-perform** (§5).
Most high-SI names grind down; the squeeze is the fat tail, reachable only when
the lending market is at breaking point *and* the shorts are in pain.

---

## 9. The systematic framework (what the code does)

```
SqueezeMetrics ──► 3 SCORE_RULES ──► weighted composite (0–100)
                   d33 SI%  (w 0.20)        │
                   d34 util (w 0.50)  ◄── dominant
                   d35 fee  (w 0.30)        │
                                            ▼
        ┌───────────────── detectors ───────────────┐
        │ bearish_convergence  → GENUINELY_SHORT     │  (overrides score)
        │ squeeze_fuel         → SQUEEZE_FUEL        │
        └────────────────────────────────────────────┘
                                            ▼
   classification ∈ {GENUINELY_SHORT, SQUEEZE_FUEL, ELEVATED, WATCH,
                     LOW, INSUFFICIENT_DATA}
   confidence     ∈ {HIGH (have utilization), MEDIUM (fee only), LOW (SI% only)}
```

Design decisions, each tracing to the research:

- **Utilization carries the most weight (0.50 > 0.30 fee > 0.20 SI)** — Schultz's
  ranking, encoded directly.
- **Bands are anchored to real distributions** — the fee bands sit on the
  0.375%/2.673%/11.0% percentiles; the utilization bands on Schultz's
  25%/90% frequency cliffs.
- **Graceful degradation with confidence tiers** — the composite is
  *weight-renormalised over available rules* (a missing input lowers *coverage*,
  it never silently counts as zero). Confidence is **HIGH** with utilization,
  **MEDIUM** with borrow fee but no utilization (detectors switch to a fee proxy:
  cheap fee ⇒ ample supply), **LOW** with neither. At LOW confidence the call is
  **capped at WATCH** — high SI% alone is bearish-leaning, not squeeze fuel, so it
  is never promoted to ELEVATED/SQUEEZE_FUEL. `INSUFFICIENT_DATA` is reserved for
  when nothing is scorable at all. Wire a lending feed later and it auto-upgrades
  to strict detectors + HIGH confidence (see Appendix A).
- **Bearish convergence overrides the score** — a cheap, low-utilization short is
  disqualified as a squeeze regardless of how high SI% is.
- **Squeeze fuel requires pain** — the S3 gate: a still-profitable short is vetoed.

### Plugging into an existing `SCORE_RULES` system
`SCORE_RULES` is a dict keyed by the `dNN` id, so it merges into a larger rule
table with `your_rules.update(short_squeeze.SCORE_RULES)`. Detectors are plain
functions returning a `DetectorResult` (truthy/falsey), easy to fold into a
composite alongside `d1…d32`.

---

## 10. Data-sourcing reality (the binding constraint)

| Field | Free (yfinance) | Better source |
|---|---|---|
| Short interest, % of float, days-to-cover | ✅ (stale: bi-monthly + 7-business-day lag) | — |
| **Borrow fee / cost-to-borrow** | ❌ | IBKR public file (free), Ortex free tier, Markit/Fintel (paid) |
| **Utilization** | ❌ | IBKR *Orbisa* dashboard (GUI only — no API), Ortex free tier, Markit/Nasdaq (paid) |

The two most predictive inputs are the two you can't get from a no-account free
feed. **Current build (IBKR parked):** the engine runs *degraded* — it scores and
classifies on whatever subset of {SI%, days-to-cover, borrow fee} you have, tags
the result `confidence = MEDIUM/LOW`, and uses borrow-fee **proxy** detectors when
utilization is absent. With **only** yfinance (SI%/days-to-cover) it is best used
to **AVOID** crowded shorts, not to confirm squeezes — and squeeze calls are
**capped at WATCH**. Appendix A documents the (parked) IBKR wiring that upgrades
this to HIGH confidence for free.

---

## 11. Limitations & honest caveats

- Schultz's exact fee/frequency figures verified via a secondary reproduction,
  not the publisher PDF (§1). Confirm against Table 1 before production use.
- Thresholds/weights are **expert-anchored to the literature, not re-estimated**
  on a fresh dataset. They are a defensible prior, not a fitted model. Re-fit on
  your own lending history if you can.
- FINRA short interest is stale; utilization/fee are daily — don't mix vintages.
- "SI > 100% of float" is real (re-lending of already-borrowed shares), not a
  data error, but it inflames headline numbers; trust utilization over it.
- A squeeze needs a **catalyst** that lending data cannot see. This framework
  finds *fragility*; timing still needs a spark.
- Backtest before trusting. Heavily-shorted baskets under-perform on average —
  the edge here is in *separating* the rare fragile-short tail from the bearish
  base case, not in buying high SI%.

---

## 12. Annotated bibliography (URLs)

**Primary result**
- Schultz, P. (2024). *Short Squeezes and Their Consequences.* JFQA 59(1):68–96.
  https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/short-squeezes-and-their-consequences/63F30135D28474EEFE7AC0C47967FE98
  · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4025226

**Securities lending & short-selling literature**
- D'Avolio (2002), *The Market for Borrowing Stock.* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=305479
- Asquith, Pathak & Ritter (2005). https://site.warrington.ufl.edu/ritter/files/2015/04/Short-interest-institutional-ownership-and-stock-returns-2005-08.pdf
- Boehmer, Jones & Zhang (2008), *Which Shorts Are Informed?* https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2008.01324.x
- Cohen, Diether & Malloy (2007), *Supply and Demand Shifts in the Shorting Market.* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=672381
- Drechsler & Drechsler (2014), *The Shorting Premium and Asset-Pricing Anomalies.* https://www.nber.org/papers/w20282
- Engelberg, Reed & Ringgenberg (2018), *Short-Selling Risk.* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312625
- Prado, Saffi & Sturgess (2016), *Ownership Structure, Limits to Arbitrage…* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1787291
- Beneish, Lee & Nichols (2015), *In Short Supply.* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2362971
- Lamont & Thaler (2003), *Can the Market Add and Subtract?* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=384240
- Pedersen (2022), *Game On: Social Networks and Markets.* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3794616

**Practitioner / vendor**
- Ortex short-interest & squeeze docs. https://public.ortex.com/understanding-the-mechanics-and-metrics-of-short-selling/
- S3 Partners, *Most "Squeezable" U.S. Stocks.* https://www.s3partners.com/articles/most-squeezable-stocks
- Fintel short-squeeze screener. https://fintel.io/shortSqueeze
- FINRA short-interest reporting (bi-monthly; 7-business-day publication). https://www.finra.org/finra-data/browse-catalog/equity-short-interest

**Cases**
- GameStop short squeeze. https://en.wikipedia.org/wiki/GameStop_short_squeeze
- Volkswagen (2008). https://en.wikipedia.org/wiki/Short_squeeze · https://thehedgefundjournal.com/the-case-of-volkswagen/

*Secondary verification of Schultz's summary statistics:* The Evidence-Based
Investor, *The Consequences of Short Squeezes.*
https://www.evidenceinvestor.com/post/the-consequences-of-short-squeezes

---

## Appendix A — Wiring data sources (IBKR plan, **parked**)

We are **building without IBKR for now**; this records the plan so it can be
picked up later. The framework is already shaped for it: `SqueezeMetrics` accepts
`utilization_pct` / `borrow_fee_pct`, and `assess()` auto-upgrades to strict
detectors + HIGH confidence the moment utilization appears.

What IBKR actually exposes (researched, and it's nuanced):

| What | How | Account? | Gives |
|---|---|---|---|
| **Borrow fee + shortable availability** | Public file `ftp://shortstock@ftp3.interactivebrokers.com/usa.txt` — pipe-delimited, skip lines starting with `#`; columns ≈ `SYM\|CUR\|NAME\|CON\|ISIN\|REBATERATE\|FEERATE\|AVAILABLE`; refreshed several times/day | **No** | `borrow_fee_pct` (→ MEDIUM confidence) + a tightness proxy from `AVAILABLE` |
| **Live shortable-share quantity** | TWS API (`ib_insync`) `reqMktData(contract, genericTickList="236")` → `ticker.shortableShares` | Yes + TWS/Gateway running | real-time shortable qty |
| **Utilization + shares-on-loan** | **Orbisa** Securities Lending Dashboard in TWS / Client Portal / Mobile | Yes | **utilization (→ HIGH confidence)** — but **GUI only, no API** |

Key catch: **true utilization has no IBKR API** — it lives only in the Orbisa
dashboard GUI. So the realistic IBKR build is:

1. **Automate the fee** by parsing `usa.txt` (no account needed) → populate
   `borrow_fee_pct`. This alone moves you to MEDIUM confidence + fee-proxy
   detectors.
2. **Hand-enter utilization** (or read `Shares on Loan` and inventory off the
   Orbisa dashboard and call `utilization_from_loan(on_loan, inventory)`) when you
   want a HIGH-confidence read on a specific name.

Alternative to IBKR: **Ortex** free tier surfaces real-time CTB + utilization for
a limited set; paid ≈ $39–50/mo for full coverage — a true API path to
utilization if hand-entry is too manual.

Status: **parked.** No FTP/API code is shipped yet by design; `from_yfinance()`
+ manual injection covers the current "build without IBKR" scope.
