# MOST_ASYMMETRIC — sheet-by-sheet hand review (2026-09-24)

Every sheet was read row by row against the source data. Each entry lists
**errors** (✔ = fixed in this pass), **missing information** and the
**questions the sheet leaves unanswered**. Cross-cutting findings come
first because they matter more than any single sheet.

## Cross-cutting findings

1. **The ranking has not beaten a random sample out of sample.** Git history
   holds 48 dated snapshots of `full_universe_consensus.csv` since 2026-06-20.
   Ranking frozen at the snapshot, return measured to 2026-09-24 against SPY:

   | Snapshot | Top 20 median | Top 100 median | Random 1,000 median | Top 20 beat SPY |
   |---|---|---|---|---|
   | 2026-06-22 (≈3 months) | −9.0% | −7.5% | −7.1% | 30% (random 31%) |
   | 2026-07-24 (≈2 months) | −13.3% | −9.7% | −5.6% | 30% (random 31%) |

   Names with 6–7 layers firing did no better (−8.7%) than one-layer names
   (−5.5%). The window is short and covers one regime, so it is not conclusive.
   But the book's central claim, that layer convergence means asymmetry, is so
   far unsupported. The book's own evidence tabs agree:
   - **Re-Rate Backtest:** every catalyst type lagged SPY at 12 months.
   - **Winners Study:** deep P/B, hard floor and payoff geometry have lift < 1.
   - **Methodology row 12:** "not yet return-validated".

2. **Net cash was wrong for 3,033 tickers ✔.** The XBRL frames store only took
   debt from the `LongTermDebt` / `LongTermDebtNoncurrent` tags. Issuers that tag
   notes, term loans, convertibles or debt-including-leases differently had
   debt = 0, so "net cash" was just gross cash. Examples:

   | Ticker | "Net cash" shown | Corrected |
   |---|---|---|
   | TTEC | +$89M (148% of mcap) | −$845M |
   | Conduent (CNDT) | +$228M | −$612M |
   | Valhi (VHI) | +$194M | −$410M |
   | Cato (CATO) | +$25M | −$113M |

   Knock-on effects (all corrected in the rebuild):
   - Payoff Geometry: the top rows showed "net-cash floor, 0% downside".
   - Mechanism Gates: "sub-cash buyback".
   - The governance-discount cash bonus.
   - The consensus payoff layer.
   - The OTC book's Cash Shells tab.

   Fix: `xbrl_frames_store.fmp_debt_check()` now keeps the larger of the XBRL
   debt and FMP's normalised `totalDebt`.

3. **FDA catalysts on non-healthcare companies ✔.** The proxy classifier's
   `fda_phase_milestone` pattern ("Phase 3", "CE mark", "marketing
   authorization") fired on 14 non-healthcare issuers, including POOL, CLW, RLI,
   RKT, ARLO, COLD and CPRI. As a result:
   - POOL showed an "FDA milestone" catalyst on Most Asymmetric;
   - the A9 "PSU vests on FDA" archetype was won by Clearwater Paper.

   Fix: `proxy_cat_hygiene.py` gates the category to Healthcare issuers before
   the archetype and consensus stages.

4. **Hand-typed narrative had gone stale ✔ (partly).** The Cover said:
   - "6,164 tickers", "8 independent rankers", "the convergent twelve";
   - "HFFG — the only ticker hitting six rankers"; "CSGP, RNR";
   - "≈ 2.4 × 10⁻¹⁰ probability by chance";
   - "12-name list unchanged after 2.8× coverage expansion".

   None of it matched the table beneath it. The probability figure assumes
   independent layers, but the Layer Correlation tab shows ρ up to 0.96. The
   cover lines are now computed from disk. Still hand-written: Reserve Baskets,
   the "Portfolio math" weights and the `TICKER_ANNOTATIONS` "why" strings (see
   below).

5. **The ranking counts correlated layers as independent votes.**
   `n_layers_firing` counts raw layers. Some pairs are nearly the same signal:
   Form 4 buys vs discretionary conviction (ρ 0.96), tender vs bumpitrage
   (0.78), opportunistic insiders vs discretionary conviction (0.69). The
   "effective independent" count is reported but not used to rank.

6. **No payoff, sizing capacity or exit on the name sheets.** "Most
   Asymmetric" has no downside, upside or EV per name. Its "Floor" column reads
   "see proxy_scan", and 13 of 20 names are labelled "Concentrated 5%+", which
   is more than 65% of NAV with no portfolio constraint. Liquidity (ADV) and
   borrow are absent. The cross book has waterfalls, but for a different set of
   names; the two books barely overlap.

## Sheet by sheet

| # | Sheet | Errors | Missing | Questions left unanswered |
|---|---|---|---|---|
| 1 | Contents | Header says "45-layer" (47 now) | — | — |
| 2 | Cover | ✔ stale hand-typed claims, invalid 2.4×10⁻¹⁰ probability, "convergent twelve" when 20 are listed | Out-of-sample record (finding 1) | Why should convergence of correlated layers predict returns? |
| 3 | Most Asymmetric | POOL "FDA milestone" ✔; Name column repeats the ticker for layer-only rows (VSNT, EPAM, GPK…); "Floor: see proxy_scan" | Downside / upside / EV per name; ADV capacity; catalyst dates (mostly "–") | What is each name's payoff and what breaks the thesis? How can 13 names all be ≥5%? |
| 4 | By Archetype | Two code systems collide: rows 1–38 "PSU Archetypes" A1–F1 and rows 39–57 "Asymmetric By" A1–B8 reuse the same codes with different meanings (A9 = FDA vs RCL). Red-flag archetypes (E1–E6) listed as "wins" (GO wins E2 "repricing"). ✔ A9 FDA winner was Clearwater Paper | Size floor ($1–6M winners: INBS, INBP) | Do E-series (red-flag) "wins" count toward a name's archetype total? They should subtract |
| 5 | Reserve Baskets | Hand-maintained lists include bankrupt / resolved names (QVCGQ, NOTV = Inotiv Ch.11, WOLF); "Portfolio math" weights and names (CSGP, RNR) are typed, not computed | Whether any basket is still live | Which baskets still have a thesis? |
| 6 | Caution List | — | What each red flag has historically meant for returns | Do these governance red flags predict anything? |
| 7 | Incentive Improvers | AGNC appears four times (AGNC + preferred lines AGNCL/M/N); P/B shown to 14 decimals | — | Does an incentive "improvement" precede out-performance? (untested) |
| 8 | Insider Conviction | — | Price paid vs current price; insider's own track record | — |
| 9 | Insider Filing-Time | $10k buys (GMRS, AXR) score the same 15 as a $13.5M buy (TXO): no size weighting | Sample size behind the "63% win-rate" claim | Is the off-hours effect robust at size? |
| 10 | MD&A Intent | Sort mixes family count and score (LEVI 17 above AVAH 22) | Date of the MD&A | Covered by Call Intent now: language predicts action, not returns |
| 11 | Payoff Geometry | ✔ net cash wrong for 3,033 tickers; many rows saturated at the caps (ratio 60, upside 300%, downside 0%) | Burn-adjusted floor date; debt maturity | How many "0% downside" rows survive the debt fix? |
| 12 | Mechanism Gates | ✔ "sub-cash buyback" on levered names (CNDT, VISN) came from the net-cash bug | — | Which gates remain after the fix? |
| 13 | Structured Distressed | — | Conversion price vs spot; dilution %; who the investor is | Are micro-cap convertible PIPEs (FNGR, STEX, TAOX) really "asset-backed", or toxic financing? No validation |
| 14 | Governance Discount | — | Price reaction since the governance event | ACTION LIKELY names: did action follow? (track forward) |
| 15 | Call Intent | — | — | Language predicts action (AUC 0.66), not the re-rating |
| 16 | Political Trades | — | — | No measured edge: shown for awareness only |
| 17 | Re-Rate Catalysts | Ranks exchange offers (BHC #1) and sale-of-company (DXLG #2) at the top, which its own backtest calls TRAPS (−22% / −46% vs SPY); ratio/upside saturated at 60/300% | Deal terms (price, spread, break risk) | Why isn't the ranking conditioned on the backtest results? |
| 18 | Re-Rate Backtest | — | Point-in-time test of the consensus ranking itself (now done, finding 1) | — |
| 19 | Tail Odds | "Confirmed monsters" include UPLISTING names (EXOZ, ADTX), which Re-Rate Backtest labels a TRAP (−23% median). SALE_OF_COMPANY tagged on USAR, YUM (asset-sale / review language) | Lift sample sizes are small (SALE_OF n = 16) | Tail vs median: is the right tail worth the median loss? |
| 20 | Winners Study | — | Point-in-time version (features measured after the move) | — |
| 21 | Asymmetry Assembly | "Cap" component never fires (always "–"): dead component | — | — |
| 22 | Distressed Stub Progress | NOTV and NOTVQ both listed (same Ch.11 company) | Recovery / waterfall per stub | — |
| 23 | Hidden Asset Realisation | Thesis column mostly "–" | Estimated asset value vs EV | How big is the hidden asset relative to the stub? |
| 24 | UK Capital Events | Only 2 events: layer barely functional | — | Is the RNS feed still parsing? |
| 25 | Without Valuation | — | — | — |
| 26 | Recent 30d | Negative P/B shown as a number (GSHD −6.7, CHPT −23.7) instead of "negative equity"; raw decimals | — | — |
| 27 | Foreign Markets | P/B / P/E / ROE to 7–8 decimals | Liquidity; FX | — |
| 28 | Turnaround Signal | Grant / Talent / Role are 0 for every row: the talent-matching half of the Bollenbach signal is not firing, so the score is just "distress + new appointment" | Who was appointed and their track record | — |
| 29 | Single-Measure Best | — | — | — |
| 30 | Layer Correlation | — | Use of the effective-layer count in the ranking (finding 5) | — |
| 31 | Coverage & Tiers | ✔ % shown to 14 decimals; ✔ universe hard-coded as 6,164. Label "yfinance valuation" (it is FMP now). Several layers are thin: 13F 0.7%, activist 0.3%, Form 4 5.6% | — | — |
| 32 | Methodology | "6,164 … from cancel_10b5_1.json" is stale | Out-of-sample result | — |

## What would most improve the book (priority order)

1. **Keep scoring the ranking out of sample.** Every rebuild commits a dated
   snapshot, so extend this test monthly. After 6–12 months it becomes
   conclusive. Weight layers by what they earn, not by headcount.
2. **Payoff per name on "Most Asymmetric".** Add floor, upside and EV (debt-correct
   payoff geometry), call intent, governance status and ADV capacity. Size from
   payoff and liquidity, not from layer count.
3. **Rank on effective-independent layers**, not raw counts.
4. **Replace hand-maintained text with computed tables:** Reserve Baskets,
   portfolio math, the "why" annotations.
5. **Condition catalyst ranking on its own backtest.** Demote TRAP types such as
   exchange offers, uplistings and sale-of-company after the 8-K.
6. **Fix the smaller defects in the table above:** the archetype code collision,
   duplicate share classes, dead components, raw decimals and the Turnaround
   talent match.
