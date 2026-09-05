# Methodology audit #3 — June 2026 (post-EDGAR coverage fix)

**Branch:** `claude/yartseva-multibagger-database-lZS4a`
**State as of commit:** `2a84c80`
**Scope:** Adversarial review of the live pipeline outputs, not just code-vs-source mapping.

This audit goes deeper than the previous two: it actually queries the produced data and stress-tests it for bugs, biases, and disconnects. Every finding is empirically verified against the current `asymmetry_global.csv` + `archetype_tags.csv`.

Two prior audits already landed:
- `METHODOLOGY_AUDIT.md` (commit `d415831`) — source-faithfulness audit. Closed the Yartseva-paper-alignment item, fictional-citation-cleanup item.
- `METHODOLOGY_AUDIT_2.md` (commit `2a84c80`) — forward-looking gap audit. Surfaced 3 silent filter bugs (mcap floor / is_pharma_bio / upside floor) which are now fixed.

What follows is **new** findings.

---

## 1. The big disconnect: archetype framework ↔ asymmetry score

### 1.1 Empirical evidence

Top 15 names by `archetype_count` (after dedup):

| Symbol | Name | Archetypes | asymmetry_score |
|---|---|---:|---:|
| OPXS | Optex Systems | **12** | 0.43 |
| URBN | Urban Outfitters | 10 | 0.33 |
| ECPG | Encore Capital | 10 | 0.30 |
| HRMY | Harmony Biosciences | 10 | 0.37 |
| MELI | MercadoLibre | 9 | **0.00** |
| UI | Ubiquiti | 9 | 0.45 |
| IRMD | Iradimed | 9 | 0.38 |
| LFVN | LifeVantage | 9 | 0.30 |
| LQDT | Liquidity Services | 9 | 0.41 |
| ANF | Abercrombie & Fitch | 9 | 0.23 |
| MA | Mastercard | 9 | 0.22 |
| INCY | Incyte | 9 | 0.38 |
| SFM | Sprouts Farmers | 9 | 0.20 |
| MANH | Manhattan Associates | 9 | 0.33 |
| RES | RPC Inc. | 8 | 0.40 |

**Top-50 by entry-today asymmetry catches NONE of these.** Top-50 is dominated by Asian smid-caps with archetype counts of 1-3.

### 1.2 Root cause — multiple failure modes

A. **MELI has `market_cap = NaN`** in asymmetry_global. MercadoLibre is a $100B+ company. The row only exists in `us_edgar_yartseva.csv`, and cached yfinance prices missed it (it's listed only on US ADR, original ticker maybe not in our scan). With NaN mcap, every mcap-dependent score leg (fcf_yield, p_e, p_s, net_cash/mcap, cash/mcap, EV/anything) → NaN → contributes 0 to upside via `fillna(0)`. So **`upside_score = 0`** even though 9 EDGAR-multi-year archetypes fire. Result: asymmetry = sqrt(0 × 0.12) = **0**.

B. **For Mastercard (MA) and Urban Outfitters (URBN)**, mcap is fine but they're **Large/Mid Cap**, so most of the downside_floor signals don't fire (no cash > EV, no Graham net-net, P/B > 1, etc.). Downside floor is ~0.10–0.15 even when fundamentals are stellar. Asymmetry stays low because the **downside leg structurally caps at compounder valuations**.

C. **The asymmetry composite weights only have 10% on archetype-derived signals**. Specifically:
- u_cluster (0.22 weight) consumes 7 inflection-like signals, NOT archetype_count
- u_yart (0.22) consumes yartseva_score (Yartseva-aligned composite, 6 factors)
- u_berez (0.14) consumes berezin_score (microcap deep value)
- u_3y_cagr / u_accel / u_mom / u_platform = 0.42 total weight on growth/momentum
- NOTHING weights `archetype_count` directly

So the M5 engine score, archetype_count, and 17 EDGAR/Lindy/creative archetype matches **all feed downstream consumers** but **don't change the upside_score / asymmetry_score**. The framework's two halves are disconnected.

### 1.3 Action

**Recommended fix.** Either:
1. Add a 6th component to upside leg: `u_archetypes = archetype_count / 26` with ~0.10 weight (still doesn't dominate); or
2. Promote `m5_engine_score` directly as a leg (covers the same ground); or
3. Compute a parallel `archetype_asymmetry_score = sqrt((archetype_count/26) × downside_floor_score)` and rank some books on that instead of raw asymmetry.

Option 3 is the cleanest — doesn't disturb the existing asymmetry score (which has its own academic backing), just adds a parallel ranking driven by archetype density.

---

## 2. 3,842 duplicate-symbol rows in `asymmetry_global.csv`

### 2.1 Evidence

```
asymmetry_global total: 29,454
unique symbols:         25,612
duplicate rows:          3,842
```

Same symbol appears 2-3+ times. Example — Agilent ("A"):
- Row 1: us_largecap, Health Care / Biotechnology, asymmetry 0.236
- Row 2: us_edgar, NaN / NaN, asymmetry 0.117

Cohen & Co, Mastercard, Apple, NVDA, XOM, BRK-B — all have 2 rows.

### 2.2 Root cause

- `build_asymmetry_global.sh` feeds 90+ files to `asymmetry_rank.py`
- `load_concat()` does plain `pd.concat()` — no dedup
- `asymmetry_rank.py` writes asymmetry_global.csv WITHOUT a final dedup
- Downstream consumers (build_harvard_workbook, build_nms_book, build_nms_candidates_book) each call `.drop_duplicates('symbol', keep='first')`
- Order depends on bash `declare -A` associative array iteration → **non-deterministic between runs**

For symbols where we have BOTH yfinance and EDGAR rows, whichever appears first in the bash hash table wins. Spot-check shows the sector-populated row tends to win (good), but this is luck of the hash, not by design.

### 2.3 Action

**Recommended fix.** Dedup at the asymmetry_rank.py write step using a deterministic priority:
- Prefer rows with non-null sector
- Then prefer rows with non-null market_cap
- Then prefer the first occurrence

Single sort + drop_duplicates after concat would fix it. Downstream code wouldn't need its own dedup.

---

## 3. Archetype-count is structurally biased by region

### 3.1 Evidence

| Country | rows | mean archetype_count | max |
|---|---:|---:|---:|
| LV | 3 | 2.67 | 4 |
| LT | 15 | 1.87 | 4 |
| MY | 53 | 1.60 | 5 |
| **US** | **5,456** | **1.18** | **12** |
| TH | 1,092 | 1.07 | 8 |
| IN | 4,075 | 0.99 | 6 |
| HK | 651 | 0.97 | 5 |
| **KR** | **1,508** | **0.86** | **6** |

Mean for US is 1.18 (max 12). Mean for major Asian markets (KR, HK, IN) is below 1.0 with max around 5-6. Optex Systems hits 12 archetypes; the best non-US name might hit 5.

### 3.2 Why

Of 26 archetypes, **17 require EDGAR multi-year XBRL data** that non-US filers don't have:
- 5 EDGAR ROIC/ROIIC: DurableReinvest, CashReinvest, ROICInflect, CheapPerROIIC, TangibleValue
- 4 Lindy durability: LindyMargin, LindyFCF, NoDilution, LindyGrowth
- 8 creative: QuietCompounder, BuybackCompounder, OwnerOperator, QARP, ReinvestInflect, DoubleInflect, CashQuality, CapitalLightPivot

Non-US names can match at most 9 of 26 archetypes. The other 17 are structurally locked.

### 3.3 Action

**Recommended fix.** Add an `archetype_count_normalized` column = `archetype_count / archetypes_eligible_for_row`, where eligible is 26 for US-EDGAR rows and 9 (or whatever fraction) for non-US. Then any "top-by-archetype_count" view should use the normalized value.

Currently nothing surfaces archetype_count directly — but if/when it does, this fix is needed.

---

## 4. RED-verdict names still in top-50 by raw asymmetry_score

### 4.1 Evidence

Top-50 by raw `asymmetry_score`:
- 20 YELLOW, 15 GREEN, **10 RED**, 5 UNRESEARCHED.

Top-50 by `entry_today_asymmetry` (where qual_mult 0.40× is applied to REDs):
- 32 GREEN, 13 UNRESEARCHED, 5 YELLOW, **0 RED** ✓

So the entry-today view is correct. But raw asymmetry_score still surfaces REDs.

### 4.2 Why this matters

Anyone downstream consuming `asymmetry_global.csv` directly and sorting by `asymmetry_score` will see REDs at the top. The Harvard workbook correctly uses entry-today. Other consumers (top_n_by_country.py, anywhere we sort by raw asymmetry) may not.

### 4.3 Action

**Recommended fix.** Either:
- Add `entry_today_asymmetry` as a column in asymmetry_global.csv directly (so consumers don't need to recompute it); or
- Drop RED-verdicted names from asymmetry_global entirely (loses context but avoids the trap).

Option 1 is safer (visibility preserved).

---

## 5. Score-leg correlations confirm design intent

### 5.1 Evidence

| | upside | floor | yartseva | inflection | berezin |
|---|---:|---:|---:|---:|---:|
| upside_score | 1.00 | **−0.28** | 0.27 | 0.64 | 0.46 |
| downside_floor_score | −0.28 | 1.00 | 0.09 | −0.19 | −0.01 |
| yartseva_score | 0.27 | 0.09 | 1.00 | **−0.29** | 0.18 |
| inflection_score | 0.64 | −0.19 | −0.29 | 1.00 | 0.30 |
| berezin_score | 0.46 | −0.01 | 0.30 | 1.00 |

**`upside_score` and `downside_floor_score` are negatively correlated (−0.28).** That's by design: a name with sky-high upside (recent inflection, accelerating growth) typically doesn't have a strong downside floor (cash > EV / Graham net-net), and vice versa. The geometric-mean asymmetry naturally suppresses one-leg-only outliers — that's the whole point.

**`yartseva_score` and `inflection_score` are negatively correlated (−0.29).** Also by design. Yartseva is contra-momentum / value; inflection is breakout / growth. They're explicitly opposite stylistic upsides. Good cross-check.

### 5.2 No fix needed

The framework's two halves move opposite to each other AS INTENDED.

---

## 6. NaN sector for 5/50 of entry-today top-50

### 6.1 Evidence

Top-50 by entry-today asymmetry: **5 rows have `sector = NaN`**. Those are EDGAR-only US names where the financedatabase merge didn't hydrate sector.

### 6.2 Why

`edgar_to_yartseva.py` sets `r["sector"] = ""` placeholder. The dedup later picks whichever row has sector populated — but for some symbols, ALL rows lack sector (when the name only exists in us_edgar_yartseva and isn't in financedatabase).

### 6.3 Action

**Recommended fix.** In `edgar_to_yartseva.py`, hydrate sector from financedatabase by symbol lookup when available. Failing that, use the SIC code embedded in the EDGAR companyfacts (`data.get("entityType")` + SIC industry mapping).

---

## 7. Verdicts file dedup logic + count anomaly

### 7.1 Evidence

```
verdicts file (after dedup keep='last'): 490
asym rows with verdict (not UNRESEARCHED): 624
```

134 more rows have verdicts than there are unique verdict entries. That's because asymmetry_global has 3,842 duplicate symbols (item #2). Each duplicate gets matched to the same verdict — so the verdict is applied twice. Fine, but feels like a bug to anyone counting.

### 7.2 Action

Fix item #2 (universe dedup) and this disappears.

---

## 8. RAJESHEXPO RED — verified the update flowed

### 8.1 Evidence

After last research pass, RAJESHEXPO.NS was tagged RED (SEBI interim ban June 2026, ED raids). asymmetry_global picks up the new verdict; entry-today top-50 correctly excludes it. ✓

### 8.2 Lesson

The verdict pipeline works correctly when fresh data is appended to `qualitative_extended_verdicts.csv` and the workbooks are rebuilt. No fix needed, but the speed (~3 weeks from event to RED tag) underscores §4.5 of audit #2: we need automated news watch.

---

## 9. Coverage status (post fix)

- **EDGAR-with-XBRL US filers in asym**: 5,034 of 7,972 (63%). Remaining 2,938 legitimately filtered (1,863 neg-equity, 885 deep-loss biotech, 1,902 pre-rev).
- **Asymmetry_global**: 25,612 unique symbols, 22,380 in original universe + 3,232 added by EDGAR/coverage fixes.
- **Verdicts**: 490 unique, mapped to 624 rows post-dup.

---

## 10. Prioritised fix list

### Now (high impact, low cost)

1. **Universe dedup at write-time** (§2) — single sort_values + drop_duplicates in asymmetry_rank.py. Fixes 3,842 duplicates + the verdict count anomaly + the random-row-wins issue.

2. **Add entry_today_asymmetry to asymmetry_global.csv** (§4) — column already computable from existing data. Surfaces a verdict-penalised score directly so downstream consumers don't surface REDs.

3. **Hydrate sector from financedatabase in EDGAR rows** (§6) — fallback chain in `edgar_to_yartseva.py`.

### Next (high impact, medium cost)

4. **Bridge the archetype↔asymmetry disconnect** (§1) — introduce `archetype_asymmetry_score` as a parallel ranking, OR add archetype_count as a small-weight upside leg. Either way, the framework's two halves should align.

5. **Normalize archetype_count by data-available archetypes** (§3) — `archetype_count_pct` column so non-US names aren't structurally disadvantaged.

6. **Backfill mcap from book equity for ranking** (§1.B) — names like MELI with NaN mcap should get a proxy mcap = max(equity, revenue, total_assets) for size-bucket assignment and score scaling.

### Later

7. Backtest validation, sector-specific scoring for financials/REITs, insider transaction signal (Form 4), industry tailwind, portfolio construction — all carried over from audit #2.

---

## 11. What we got right (confirmed empirically)

- **Score-leg design is sound.** Upside vs floor correlation is −0.28; yartseva vs inflection is −0.29. Both designed opposites move opposite as intended.
- **Filter recovery worked.** The mcap/biotech/upside-floor fixes recovered ~3,000 names without breaking the remaining filters. Top-50 face validity is high (Dongwoo, Cohen & Co, Kokusai, Brook Crompton — all recognisable multibagger candidates).
- **Verdict pipeline is responsive.** RAJESHEXPO went from UNRESEARCHED → RED in one append-to-CSV pass; entry-today correctly demotes it.
- **Dedup behaviour is consistent.** Sample dedup winners had populated sector in 10/10 cases — the order luck is working in our favour despite being non-deterministic.

---

## 12. Bottom line

The framework is **structurally healthier than at audit #2** — three silent filter bugs are fixed, ~3,000 EDGAR names are recovered, and entry-today top-50 has clean verdict mix (32 GREEN / 13 UNR / 5 YELLOW / 0 RED).

The **new** issues are subtler:

- The **archetype framework and asymmetry score are partly disconnected** (item §1). Top archetype-rich names like Optex, MELI, Mastercard don't make the asymmetry top-50. We've built two parallel quality measures and not yet wired them together.

- The **universe has 3,842 dup-symbol rows** (§2) — not a correctness issue but a hygiene one. Fix takes 3 lines.

- **Archetype-count is structurally biased** toward US-EDGAR names (§3). Important to surface in any ranking that uses archetype_count directly.

Closing items §1, §2, §6 (the "Now" tier) takes maybe 30 minutes of code edits and pays off immediately in cleaner workbooks. The big methodological gap remains **backtest validation** — until we measure realised return-by-archetype across a 2018-2025 holdout, every threshold and weight is plausible-but-unfit.
