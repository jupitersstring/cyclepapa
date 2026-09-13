# Top-Ticker Verification Sweep — Group 3 (29 archetypes)

Post-regeneration check (event sleeve added, wrong-price ghosts removed). Method: `scratch_diligence_dump.py` top-10 per archetype vs the measure in `archetype_tags.py`; six newest (bottleneck, flyover, spinoff, post_reorg, special_situation, nol_shell) scrutinized hardest, including event-flag genuineness against `edgar_event_signals.csv` / `.py`.

## Verdict table

| Archetype | Verdict | Worst offender (top-10) |
|---|---|---|
| arch_bottleneck | PASS | — (note: WEBJF gross_margin = exactly 1.0, agency net-revenue accounting) |
| arch_flyover | PASS* | note: JAMESWARREN.BO roce 100% / ebitda-margin 75% (one-off-distorted) fires the ROIC moat leg |
| arch_spinoff | **FLAG** | SUNB — corrupt earnings_yield satisfies value leg; spin flag is a re-listing Form 10 |
| arch_post_reorg | **FLAG** | STG (rank 1) spurious reorg flag; PPC/LEA 2009 emergences (no recency window) |
| arch_special_situation | **FLAG** | PXLW — value leg passes on corrupt earnings_yield 1.72 while burning 56%/yr |
| arch_nol_shell | **FLAG** | HERE (rank 1) NOL in RMB counted as USD; ONCO/ASTC melting burners via NaN op_margin; NEON corrupt op_margin |
| arch_liger_neglected_survivor | **FLAG** | TTEC (rank 3) — corrupt net-cash sign (EV says 12.6x mcap net DEBT) |
| arch_oak_resource_leverage | **FLAG** | AGPPF (rank 3) — ZAR fundamentals labeled USD; Monument & Thor dual-line double-counts |
| arch_oak_deleveraging | PASS | — |
| arch_oak_deep_value | **FLAG** | 11C.SG (rank 5) — EUR quote / PLN fundamentals mixed row |
| arch_oak_nav_discount | **FLAG** | COHN (rank 3) + 0111.HK — operating broker-dealers through the NAV-vehicle name filter |
| arch_oak_asset_floor | PASS | — |
| arch_oak_order_conversion | PASS* | note: ghost row 042420.KQ at rank 8 |
| arch_weschler_levered_equity | PASS | — |
| arch_cheap_sales_scaler | PASS* | note: ghost row 042420.KQ at rank 4 |
| arch_exceptional_evsg | **FLAG** | B9A.F (rank 7) — SEK/EUR mixed row fakes "exceptional" EV/S (true 27.7x, shown 0.52x) |
| arch_negative_ev_value | PASS | — |
| arch_growth_algo | **FLAG** | 042420.KQ (rank 1) — identity/ghost row ("Z Holdings" name on Korean ticker, self-contradictory net cash) |
| arch_asleep_at_wheel | PASS (by design) | notes: MDX.BK op −78% / $11M rev; CORALFINAC.BO — beats branch has no validity gate |
| arch_templeton_pessimism | PASS* | notes: 042420.KQ rank 3 ghost; 1V5.F Frankfurt-line FX mixing |
| arch_asymmetric_assembly | PASS* | notes: C44.F Frankfurt line corrupt EV path; DWS.V/DWWEF dup pair across siblings |
| arch_levered_inflection | PASS | — |
| arch_insider_conviction | **FLAG** | ONCO (rank 2) melting shell; FXNC/PCB banks >1x book via fcf_yield leg |
| arch_tenbagger_path | PASS* | note: 042420.KQ rank 1 ghost |
| arch_tenbagger_credible | PASS* | note: same ghost rank 1 |
| arch_evsales_derating | **FLAG** | 042420.KQ (rank 1) ghost + B9A.F (rank 8) FX row |
| arch_lynch_reward | PASS* | notes: 900920.SS B-share FX ratios; 131090.KQ shares_yoy +389% |
| arch_analyst_awakening | PASS* | notes: 0K2P.IL (Momo IOB line) net_cash 695% corrupt + dup vs MOMO; ZEAL.CO rev_yoy +14,640% display |
| arch_analyst_rerating_confirmed | **FLAG (soft)** | INMB (rank 4) — clinical biotech burner ($50K revenue, P/S 824) at a 52w high; no operating guard in this archetype |

**Counts: 17 PASS (8 with notes), 12 FLAG (1 soft).**

---

## FLAG details

### Six newest (event sleeve)

**arch_spinoff — SUNB (Sunbelt Rentals Holdings, rank 3).**
`_excellent_value` passed via `earnings_yield` = 0.190 while `p_e` = 21.77 on the same row (true earnings yield ~4.6%; fcf 6.3% < 8%, EV/EBIT 18.2 → 5.5% < 10%). None of the three yield lenses genuinely clears — the leg fires only on the contradicted earnings_yield field (Form-10 new entity, CIK 2083785, likely stale/mismatched EPS base). Responsible leg: `_excellent_value` / `earnings_yield` corruption. Spirit note: the Form 10 (2026-02-13) is Ashtead's US re-domiciliation vehicle, not a forced-selling spin. VSNT and VGNT are genuine, cheap Form-10 spins (VSNT = Comcast cable-nets spin, fcf 30.7% — the model citizen). NVRI note: spin flag genuine but attaches to the parent (spinco CIK 2104052 mapped to parent ticker); its displayed nde 46.3 is a corrupt ratio.

**arch_post_reorg — STG (rank 1) + staleness.**
Root cause in `edgar_event_signals.py`: `reorg_flag` = mere presence of the `ReorganizationValue` XBRL concept via `_concept_latest`, which has **no date cutoff** (unlike the 730-day window on the form flags). Consequences in the top 5:
- STG (Sunlands): a China ADR whose "reorganization" is a pre-IPO/VIE corporate reorg tag, not a Chapter 11 fresh-start. Rank 1 on a spurious event.
- PPC and LEA carry fresh-start values from their **2009** emergences; VTOL 2019. 4 of 5 top names are not live post-reorg situations. Only GPOR (2021) is arguably recent.
Responsible leg: `_reorg == 1` (source-data recency + tag-semantics gap).

**arch_special_situation — PXLW (rank 9).**
merger_flag genuine (DEFM14A), but `_excellent_value` passed on `earnings_yield` = 1.716 (171%!) while p_e is NaN, op_margin −106%, fcf_yield −55.9%, EBITDA −$23M on $24.6M revenue — a one-off-gain-corrupted earnings_yield admits a cash incinerator into a "bounded downside, bought cheap" sleeve. Responsible leg: `_excellent_value` / corrupt `earnings_yield` (same field failure as SUNB). Softer notes: BILI (rank 5) tender_flag is a convertible-notes (debt) tender — no equity-catalyst bound; BGY/BOE are CEF discount-management tenders whose "earnings yield" is fund NAV gains (no is_operating gate here by design, but their fund ratios — p_s 35, rev_yoy 605% — are noise); EXFY displays nde 29.2 (corrupt tiny-EBITDA denominator).

**arch_nol_shell — FX-mislabeled NOLs + melting shells.**
1. *FX mislabel (structural):* `_concept_latest` in `edgar_event_signals.py` does `units.get("USD") or first-unit-fallback` — for foreign filers the OperatingLossCarryforwards value comes back in reporting currency but is stored as `nol_usd`, and `_nol_to_mcap` divides by USD mcap. In the top 10: **HERE** (rank 1, RMB 210M ≈ $29M → true ratio 0.28, fails the 0.5 gate), **YOUL** (0.13), **GHG** (0.09) would NOT fire with correct FX; WIMI is borderline (~0.50) and additionally carries corrupt p_e 0.51 / ev_sales −44. Responsible leg: `_nol_to_mcap >= 0.5` on unconverted `nol_usd`.
2. *Melting shells through NaN:* **ONCO** (rank 2) burns $9.7M/yr FCF and −$13.3M EBITDA on $815K revenue (momentum −98.8%, distress_flag=1, NT filer) but `_not_melting` requires op_margin AND fcf both known-negative — op_margin is NaN, so it passes; the $5.4M "net cash" covers ~6 months of burn, violating the stated "survivable balance sheet". **ASTC** (rank 3) same NaN path (−$14.9M FCF on $1.2M revenue; its cash+NOL story is at least genuine). **NEON** (rank 9) passes both `_not_melting` and `_excellent_value` via one-off-litigation-corrupted fields (op_margin +355%, P/E 1.9, EBITDA +$7.7M on $2.2M revenue) while fcf_yield is −80%. Responsible legs: `_not_melting` NaN-permissiveness; no burn/runway gate in nol_shell.
Genuine passes for contrast: SIRI ($7.8B USD NOL, real), BOSC, JETMF.

### Remaining 23

**arch_liger_neglected_survivor — TTEC (rank 3).**
net_cash_pct_mcap = +0.744 and nde = −93.7 both read "net cash", but the same row's enterprise_value is $926M vs mcap $68M — ~$858M net DEBT (12.6x mcap; TTEC is in fact heavily levered). The `_netcash_not_contradicted` guard cross-checks nde, which is corrupt with the same wrong sign, so the net-cash survivability leg fires on a balance sheet that is the exact opposite of the thesis. Responsible leg: `net_cash_pct_c >= 0.15 & _netcash_not_contradicted` — the contradiction check needs an EV-based corroborator. (MKTW note, rank 10: fcf_yield 0.73 vs fcf_ttm −$15.5M contradiction; it passes on op_margin regardless.)

**arch_oak_resource_leverage — AGPPF (rank 3) + dual-line dupes.**
AGPPF row: currency labeled USD but fundamentals are ZAR — ebitda_ttm "USD 31.7B", fcf "USD 11.5B", EV −$1.9B against a $22.7B USD mcap → EV/EBITDA 0.22, fcf_yield 64%, net_cash 61% are all ~17x-inflated artifacts; Amplats is nowhere near these. Cheapness, cash-floor and cash-yield legs all pass on the corruption. Responsible leg: OTC-line currency mislabel upstream of every ratio. Also: **Monument Mining twice (MMY.V rank 4 + MMTMF rank 8)** and **Thor Explorations twice (THXPF rank 7 + THX.V rank 9)** — cross-listing double-counts occupying 4 of 10 slots (and MMY.V shows rev_yoy 10.99 vs 1.89 on its twin — per-line enrichment inconsistency).

**arch_oak_deep_value — 11C.SG (rank 5).**
11 bit studios EUR-quoted line with PLN fundamentals: EV €5.4M vs EBITDA "73.3M" (PLN), giving ev_ebitda 0.074 alongside p_e 29.5 on the same row; pb 0.28 and net_cash 93% are PLN-book/EUR-mcap artifacts (11 bit actually trades ~3x book with ~10% net cash). Cheapness legs fire entirely on the mixed-currency row. Note (rank 6): RFT.AX passes `ebitda_ttm > 0` on a stale positive print while ebitda_margin −49% / op −55% — the survivability legs are satisfied by mutually contradictory periods.

**arch_oak_nav_discount — COHN (rank 3), 0111.HK (rank 6).**
The (tail/fresh) fix excludes securities houses by industry token AND name token — but "Cohen & Company Inc." and "Cinda International Holdings" contain neither `securit` nor `broker`, so two operating broker-dealer/investment banks pass `_nav_vehicle` on industry "Capital Markets". COHN: fcf_yield −182%, div yield shown 18.3% (suspect) — an operating IB at 0.47x book, not a covered NAV discount. Responsible leg: `_nav_vehicle` name/industry heuristic. (BAM.BK rank 5 — leveraged NPL purchaser, nde 17.6 — is a borderline by-design "asset manager"; noting only.)

**arch_exceptional_evsg / arch_evsales_derating — B9A.F (ranks 7 / 8).**
BioArctic Frankfurt line: EUR mcap €2.73B with SEK fundamentals — revenue_ttm 1,147M **SEK** stored so that revenue_ttm_usd = $1.32B (the correctly-converted BIOA-B.ST line shows $121M), EV €600M vs the Stockholm line's SEK 27.7B (€2.5B). Result: ev_sales 0.52 vs true 27.7 — the entire "exceptionally cheap per unit of growth" signal is the FX error, compounded by rev_yoy +346% (real but one-off Leqembi milestone). Responsible leg: `evsg`/`ev_sales`/`revenue_ttm_usd` on a mixed-currency cross-list; also a duplicate of BIOA-B.ST (which correctly does NOT fire).

**arch_growth_algo / arch_evsales_derating (rank 1), and top-4 of cheap_sales_scaler, exceptional_evsg, tenbagger_path/credible, templeton, order_conversion — 042420.KQ "Z Holdings Corporation".**
Residual identity-ghost row: a KOSDAQ ticker carrying the name/industry of Japan's Z Holdings ("Internet & Direct Marketing Retail", src JP), gross_margin exactly 1.0, and a self-contradictory balance sheet — net_cash_pct +2.77 while EV (1.76e11) > mcap (1.48e11) implies net debt. It sits at rank 1–8 in SEVEN of this group's tops (archetype_count 26). One bad row is polluting the whole growth/value family's headline ranks. Root cause: symbol→profile mismatch + net-cash/EV contradiction unchecked.

**arch_insider_conviction — ONCO (rank 2); FXNC (rank 3) / PCB (rank 5).**
- ONCO: same melting nano shell as in nol_shell — `_not_melting` passes on NaN op_margin/roce while EBITDA is −$13.3M on $815K revenue; the "value-oriented" leg passes on pb 0.29. An insider buy on a husk burning 2x its mcap per year is not conviction-with-value. Responsible legs: `_not_melting` NaN path + pb leg on a broken book.
- FXNC (pb 1.48) and PCB (pb 1.19): the growth-audit fix capped financials at pb < 1.0, but the value-leg OR still admits any financial with `fcf_yield >= 0.03` — bank "FCF" (deposit-flow CFO) is exactly the meaningless quantity the fix was meant to bypass, so "insider bought a bank near/above 1.2–1.5x book" is back. Responsible leg: `fcf_yield >= 0.03` alternative not sector-restricted. (FXNC also shares_yoy +29% merger issuance.)

**arch_analyst_rerating_confirmed — INMB (rank 4), soft flag.**
INmune Bio: $50K revenue, P/S 824, ev_sales 427, ebitda_margin −616x, fcf −57%, shares +24% YoY — a clinical-stage burner printing a 52w high with 4 analysts. The measure as written is honored (conviction + 52w high + not blown off), but this archetype carries no is_operating/profitability/clinical-biotech guard at all, so the invariant-guarded clinical-biotech class leaks into a top-5 slot here. Flagging per the "unless you see one actually leaking" instruction; whether to add the guard is a design call.

---

## Residual ghost / corrupt / duplicate notes (tops only)

- **Frankfurt/IOB/OTC cross-list FX-mixed rows** are the dominant residual corruption class: B9A.F (SEK/EUR), 11C.SG (PLN/EUR), AGPPF (ZAR/USD), 1V5.F (PLN/EUR, templeton rank 8), C44.F (HKD/EUR, assembly rank 9 — heavy-debt EV path inflated), 0K2P.IL (Momo, net_cash 695%), 900920.SS (B-share USD quote / CNY fundamentals: p_e 0.79, net_cash 767%, lynch rank 5).
- **Cross-listing double-counts in one top-10:** Monument Mining (MMY.V + MMTMF) and Thor Explorations (THXPF + THX.V) in oak_resource_leverage; DWS.V/DWWEF (Diamond Estates) split across assembly/levered_inflection; B9A.F duplicates BIOA-B.ST; 0K2P.IL duplicates MOMO.
- **Contradictory-field rows:** TTEC (net cash vs EV), MKTW (fcf_yield +73% vs fcf_ttm −$15.5M), RFT.AX (ebitda_ttm > 0 vs ebitda_margin −49%), SUNB/PXLW (earnings_yield vs p_e), EXFY/NVRI (nde 29/46 tiny-denominator), 042420.KQ (net cash vs EV).
- **One-off-earnings distortions passing quality legs:** JAMESWARREN.BO (roce 100%, ebitda margin 75% — flyover/asset_floor), NEON (litigation gain), ZEAL.CO (Roche milestone: p_e 7.8, rev_yoy +14,640% display), JUSTDIAL roce −0.98 display.
- **Metadata oddities (benign?):** `src` mislabels (5843.KL and 7692.KL tagged src JP); Secuve 131090.KQ shares_yoy +389% (likely split artifact); WEBJF/WEB.AX gross_margin exactly 1.0 (agency net-revenue accounting).

## Recurring root causes (fix once, clears many flags)

1. `edgar_event_signals.py::_concept_latest` — (a) first-unit fallback stores non-USD NOLs as `nol_usd` (nol_shell FX flag); (b) no date window on `ReorganizationValue` (post_reorg staleness) or NOL facts.
2. `earnings_yield` corruption/contradiction vs p_e (SUNB, PXLW, NEON, WIMI) — `_excellent_value` should cross-check p_e or clamp.
3. Net-cash vs enterprise-value contradiction unchecked (TTEC, 042420.KQ) — the existing nde-based guard fails when nde shares the corruption.
4. Cross-list quote-currency vs reporting-currency mixing (B9A.F, 11C.SG, AGPPF, C44.F, 1V5.F, 0K2P.IL, 900920.SS) + no primary-line dedup within an archetype's ranking.
5. `_not_melting` NaN-permissiveness lets known-EBITDA-negative burners with missing op_margin through (ONCO, ASTC).
