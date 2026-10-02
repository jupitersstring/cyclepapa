# Promise sweep 1: archetype_tags.py lines 1-2700

This sweep looks for places where a comment promises behaviour that the code does not deliver. It was read-only on the repo. Nothing was run from the pipeline, and no git commands were used.

**Method**
- Every comment in lines 1-2700 was read against its code.
- A token-level scan (comments excluded) found assignments that are never read anywhere in the 10.7k-line file.
- Leg impacts were rebuilt with pandas from these inputs:
  - asymmetry_global.csv, fmp_throughcycle.csv, fmp_quarterly_ext.csv, fmp_statements.csv, fmp_enrichment.csv and fmp_quarterly.csv, read with usecols
  - published flags from archetype_tags.csv and archetype_tiers.csv (written at 15:31)
- Scripts are in `S/ps1/` (`frame.py`, `measure.py`). The 16 MB frame was deleted afterwards.

**Checks on the rebuild.** The rebuilt `_adv_shock` leg holds for every row of the published `narrative_lag_watch` (5,084 rows, 0 misses). The rebuilt nde>6 leverage cap holds for every row of the published `fixed_cost_demand_shock_watch` and `regime_cyclical_watch` (0 misses). Where a count could not be rebuilt, I cite the prior instrumented run (review_r2_batch*).

**The file changed while I was reading it.** At 16:08 it grew from 10,533 to 10,725 lines. All the changes are after line 2700, and every patch anchor below was re-checked as unique after the change (each `old` string occurs exactly once). Line numbers above 2700 refer to the 10,725-line version.

**Sign convention.** A "fires changed" count with a minus sign means the patch removes that many `arch_` fires. "0" means only a comment changes.

---

## F1: narrative_lag re-specified core drops the `_adv_shock` leg (L1384-1390, L1396-1401, L1529-1536)

**Promise.**
- L1384-1386: "(audit 3) breadth counts only beside at least one SHOCK-sized lens (a first positive or a >= 2pp margin / TTM shock) — two drift lenses are not an advance".
- L1400-1401: "No non-thesis gates: the advancing-fundamentals legs of the original rule stay; only the lag test is replaced."

**Code.** The watch rule (L1388) has `(_adv_breadth >= 2) & _adv_shock`. The core (L1529) keeps `_adv_breadth >= 2` but drops `_adv_shock`. That leaves two drift lenses enough again, which is the case audit 3 closed. `_adv_shock` is never read after L1390.

**Impact.** 1,264 of 5,317 published fires have no shock-sized lens. The rebuild is exact: 0 of 5,084 watch rows lack it.

**Patch** (L1530):
```
old:
        (df['narrative_lag_lenses'] >= 1) &
        (_adv_breadth >= 2) &
new:
        (df['narrative_lag_lenses'] >= 1) &
        (_adv_breadth >= 2) & _adv_shock &
```
**Est. fires changed:** -1,264.

## F2: fixed_cost_demand_shock reframe silently drops the leverage cap (L1609 vs L1621-1636)

**Promise.**
- L1609 (old rule): "(tail) leverage cap — exclude KNOWN 24-38x zombies (AWLCF/China Primary); nde 99 = unknown stays permissive".
- L1621-1625: the reframe only re-measures the sector proxy and adds a drop-through lens. "Old rule surfaced as fixed_cost_demand_shock_watch."

**Code.** `_reframe` replaces the column with a new rule that keeps `_not_melting` but does not carry `~((nde > 6.0) & (nde < 90))`. Nothing in the comment says the cap was retired.

**Impact.** 169 of 1,722 fires have a known nde in (6, 90): 8117.HK 24.8x, NEXS.L 15.8x, BANG.NS 15.3x, STPI.BK 8.6x. The watch rule has 0 such rows.

**Patch** (L1633):
```
old:
        (rev_accel >= 0.03) & (rev_yoy >= 0.05) &   # (audit 3) a demand SHOCK: >= 3pp acceleration on a >= 5% top line, not a 0.1pp drift
        _not_melting &
new:
        (rev_accel >= 0.03) & (rev_yoy >= 0.05) &   # (audit 3) a demand SHOCK: >= 3pp acceleration on a >= 5% top line, not a 0.1pp drift
        _not_melting &
        ~((nde > 6.0) & (nde < 90)) &   # (tail) leverage cap carried over from the old rule (KNOWN zombies; nde 99 = unknown stays permissive)
```
**Est. fires changed:** -169.

## F3: regime_cyclical reframe silently drops the leverage cap (L1723 vs L1735-1746)

**Promise.**
- L1723: "(tail) leverage cap — exclude KNOWN over-levered zombies".
- L1735-1737: the reframe only swaps the sector label for measured asset intensity and the panel drawdown.

**Code.** The reframe keeps `_not_melting` and the +20pp cap but omits `~((nde > 6.0) & (nde < 90))`.

**Impact.** 134 of 1,157 fires have nde in (6, 90): 8117.HK, NEXS.L, BANG.NS, CAPRIHANS.BO 11.6x, LGPS 11.4x. The watch rule has 0 such rows.

**Patch** (L1741, the reframe block):
```
old:
        (rev_yoy > 0) &
        _not_melting &
        ((ebitda_inflection > 0) | (ebitda_first_pos > 0) |
new:
        (rev_yoy > 0) &
        _not_melting &
        ~((nde > 6.0) & (nde < 90)) &   # (tail) leverage cap carried over from the old rule
        ((ebitda_inflection > 0) | (ebitda_first_pos > 0) |
```
**Est. fires changed:** -134.

## F4 (BUG): discounted_vehicle G2 "drop >100%-of-mcap shells" bypassed by the cash_gt_ev leg (L1642)

**Promise.** `# (G2) drop >100%-of-mcap shells`. G2 at L945-948 says "cash > 100% of mcap for an OPERATING value thesis is a shell/holdco artifact".

**Code.** `(cash_gt_ev > 0) | (net_cash_pct_sane > 0.20)`. Only the second arm is clamped. The stale `cash_gt_ev_flag` readmits every >100% shell.

**Impact.**
- 83 of 1,251 fires have net cash above 100% of market cap, e.g. 2222.HK 3.9x, WHLM 3.9x, 042420.KQ 2.8x.
- The prior review (r2 batch7) found these dominate the spirit top-50 (28 of 50).

**Patch:**
```
old:
        ((cash_gt_ev > 0) | (net_cash_pct_sane > 0.20)) &  # (G2) drop >100%-of-mcap shells
new:
        (((cash_gt_ev > 0) & ~(net_cash_pct > 1.0)) | (net_cash_pct_sane > 0.20)) &  # (G2) drop >100%-of-mcap shells (on the flag leg too)
```
`net_cash_pct` is `s()`-filled with 0, so a missing percentage stays permissive on the flag leg, as before.

**Est. fires changed:** -83.

## F5 (BUG): capital_discipline's "missing P/B passes" arm is dead (L1705)

**Promise.** The leg `... | pb.isna()` intends a missing P/B to pass the "NOT YET RE-RATED" test.

**Code.** `pb = s('pb', 99.0)` (L882) is never NaN, so the arm is always False. A missing P/B reads 99 and fails `pb < 1.5`.

**Impact.** The prior instrumented run (review_r2_batch8 L24) found this would admit 19 names. I could not rebuild the full capital_discipline leg chain here.

**Patch:**
```
old:
(s('ev_ebit', np.nan) <= 12)) | pb.isna()) &
new:
(s('ev_ebit', np.nan) <= 12)) | _ncol('pb').isna()) &
```
**Est. fires changed:** +19 (per r2 batch8).

## F6 (BUG): roic_inflect lets a cash-ROIC-only cross stand alone (L1935-1936, L1946)

**Promise.** "K — ROIC inflection: latest ROIC crossed zero from below AND cash ROIC also positive (confirms the inflection is real, not accounting)."

**Code.** `(roic_inflect == 1) | (cash_roic_inflect == 1) | _roic_turn_q`. A one-year FCF/IC dip and recovery fires on its own, with no accounting-ROIC cross and no dated TTM turn. The "cash also positive" confirmation is already `cash_roic_lindy > 0` at L1948.

**Impact.**
- 596 of 1,079 fires have neither the annual ROIC cross (`fmp_st_roic_inflection_flag`) nor the TTM turn (`bs_ebit_turned == 1 & fqx_roic_ttm > 0`). All 596 pass only on the cash flag.
- r2 batch7 lists VRTX, Nintendo, Lenovo and Bajaj Auto among them.

**Patch:**
```
old:
        ((roic_inflect == 1) | (cash_roic_inflect == 1) | _roic_turn_q)
new:
        ((roic_inflect == 1) | _roic_turn_q)          # the ACCOUNTING return crossed (annual or dated TTM); cash confirms below
```
**Est. fires changed:** -596.

## F7: quiet_compounder core omits "earnings still compounding (TTM EBIT +10%)" (L2404-2412)

**Promise.** "(tighten) 'QUIET' measured, not assumed: the price has not run (52w total return <= +20%), no deep drawdown ..., **and earnings are still compounding (TTM EBIT +10%)**. Exceptional: the street is genuinely not watching (<= 3 analysts)."

**Code.**
- Core = `ts_r52 <= 0.20 & ts_maxdd_5y > -0.45`.
- The EBIT leg was put only in the `exceptional` argument, next to the analyst count.
- That exceptional argument is also overwritten later (see F9), so the leg never reaches any output.

**Impact.**
- 314 fires, 267 of them measured.
- 153 measured fires have `fqx_ebit_ttm_g < 0.10`; 26 more have it NaN and stay, NaN-permissive.

**Patch** (L2409):
```
old:
          (_ncol('ts_r52') <= 0.20) & (_ncol('ts_maxdd_5y') > -0.45),
new:
          (_ncol('ts_r52') <= 0.20) & (_ncol('ts_maxdd_5y') > -0.45) & ~(_ncol('fqx_ebit_ttm_g') < 0.10),
```
**Est. fires changed:** -153.

## F8: lindy_fcf: comment ">= 7 fiscal years", code ">= 3" (L2048-2053)

**Promise.** "durability = FCF positive in EVERY one of >= 7 fiscal years at a real margin".

**Code.** `(_ncol('tc_fcf_years') >= 3)`.

**Impact.**
- Fire windows: 3y 11, 4y 12, 5y 21, 6y 45, 7y 88, 8y 3,361. So 89 fires sit below the stated 7.
- The 19 fallback fires (tc NaN) all have ≥7 years of FMP history.

**Which to fix.** The sibling lindy_margin (L2016-2018) states the design as "measured over the years we HAVE: the worst year of >= 3 observed (7 years remain the exceptional / spirit lens)", and `tc_fcf_years` is already a lindy_fcf spirit lens. The comment is probably the stale side.
- **Patch A (recommended, comment).** Replace `# firms; durability = FCF positive in EVERY one of >= 7 fiscal years at a real` with `# firms; durability = FCF positive in EVERY observed fiscal year (>= 3; 7+ years rank higher in the spirit score) at a real`.
- **Patch B (code, honours the comment).**
```
old:
    _fcf_all_pos = ((_ncol('tc_fcf_pos') == _ncol('tc_fcf_years')) & (_ncol('tc_fcf_years') >= 3))
new:
    _fcf_all_pos = ((_ncol('tc_fcf_pos') == _ncol('tc_fcf_years')) & (_ncol('tc_fcf_years') >= 7))
```
**Est. fires changed:** 0 (A) / -89 (B).

## F9 (cross-cutting): every `_tier()` "Exceptional: ..." definition, and the elite metric, is overwritten

**Promise.**
- The `_tier` docstring (L1054-1061) says `<name>_exceptional` marks "the genuinely exceptional subset" defined by the `exceptional` argument, and `<name>_elite` is the top (1-q) on `elite_metric`.
- Per-archetype comments spell out each test:
  - narrative_lag L1537-1538: "lagging on >= 2 independent lenses, by >= 50%; elite = top 10% by extent"
  - blindspot L1827-1828: "also profitable on EBITDA and FCF"
  - lindy_margin L2017: "7 years remain the exceptional / spirit lens, longer = better"
  - lindy_fcf L2050-2052: "the price has also been durable (5y max drawdown shallower than -40%)"
  - no_dilution L2085-2086, capital_returner L2142-2143, quiet_compounder L2406-2407
  - owner_operator L2470: "insiders buying + ROIC >= 15% + no dilution"

**Code.**
- The spirit loop (now L10509-10545) recomputes `_exceptional = core & spirit >= 0.75` and `_elite = core & spirit >= 0.90` for every name in `_TIERED`.
- `_pre_exc` keeps upstream sets only `if n not in _TIERED`. So every `exceptional=`/`elite_metric=` argument, and the hand-built narrative_lag exceptional/elite at L1540-1543, are dead.

**Evidence** (published file vs the tier definitions):

| archetype | published exceptional | tier-def exceptional | overlap |
|---|---:|---:|---:|
| blindspot | 118 | 541 | 83 |
| owner_operator | 308 | 21 | 2 |
| lindy_margin | 217 | 411 | 188 |
| lindy_fcf | 54 | 1,335 | 54 |
| quiet_compounder | 3 | 18 | 0 |
| narrative_lag | 816 | 1,924 | 815 |

narrative_lag elite: 160 published vs 532 hand-built.

Most spirit lists carry a lens close to each promise: blindspot has fcf_yield; owner_operator has roic_lindy and shares_growth_3y; capital_returner has evt_div_raise_streak. **Two promises reach no output at all:**
- lindy_margin's "longer = better" history: `tc_years` is not in its spirit list.
- lindy_fcf's price durability: `ts_maxdd_5y` is not in its spirit list.

**Patches.** The `arch_` fires do not change in any option.
- **(a) Targeted spirit lenses (recommended).**
```
old:
                         (_c('ebitda_margin_lindy'), 1), (_c('tc_min_gm'), 1)],
new:
                         (_c('ebitda_margin_lindy'), 1), (_c('tc_min_gm'), 1), (_c('tc_years'), 1)],
```
```
old:
                      (_c('tc_fcf_margin_avg'), 1), (_c('cash_roic_lindy'), 1)],
new:
                      (_c('tc_fcf_margin_avg'), 1), (_c('cash_roic_lindy'), 1), (_c('ts_maxdd_5y'), 1)],
```
- **(b) Honour every promise literally:** union the tier definitions back in.
```
old:
                if n not in _TIERED and n + '_exceptional' in df.columns}
new:
                if n + '_exceptional' in df.columns}
```
This takes exceptional counts to roughly blindspot 576, lindy_fcf 1,335 (38% of the core; too loose) and narrative_lag 1,925. Not recommended.
- **(c) Comment fix.** Re-word the `_tier` docstring: "`exceptional`/`elite_metric` are provisional; the spirit loop below replaces both for every tiered archetype". Also drop or mark each per-archetype "Exceptional: ..." sentence as a spirit-lens description.

**Est. fires changed:** 0 `arch_` fires in every option. Only the exceptional and elite columns move.

## F10: kpi_threshold header promises a ROCE >= 5% requirement that does not exist (L1770-1776, L1785)

**Promise.** "New version requires at least one first-positive ... AND positive margin delta YoY AND positive ROCE today (>= 5 pct)."

**Code.**
- `roce_today` (L1785) is never read. `first_pos_print` (L1777) and `margin_confirming` (L1781) are dead too.
- The baseline (S/archetype_tags.baseline.py L495) used ROCE only as an OR escape. The L1800-1801 note says that escape was dropped. So no ROCE floor was ever an AND leg.

**Impact if honoured as code.** 1,746 of 3,329 fires have roce < 5% (240 of them NaN). That would be a large, un-audited tightening.

**Patch (comment, recommended):**
```
old:
    # New version requires at least one first-positive in a profitability
    # measure (EBITDA/CFO/FCF/NI/ROCE) AND positive margin delta YoY AND
    # positive ROCE today (>= 5 pct).
new:
    # (superseded by the audit-3 legs below: an OPERATING-line first positive
    # AND a >= 2pp margin move or TTM drop-through; there is no ROCE-level
    # floor — survivability is _not_melting.)
```
Optionally delete the three dead assignments at L1777-1785.

**Est. fires changed:** 0.

## F11: low_sbc_quality promises an "SBC/EBITDA" lens that is not implemented (L2185-2186)

**Promise.** "SBC/EBITDA and roic_after_sbc≈roce are alternate clean-accounting lenses for names lacking the revenue-based ratio."

**Code.** Only the roic_after_sbc lens exists, and it is ORed in for all names, not only those lacking the ratio.

**Data.** No SBC/EBITDA column exists for the names the comment targets. Wherever an SBC level exists (EDGAR `sbc_ttm`, `fq_sbc`, FMP annual), `sbc_pct_revenue` has already been filled from it. The closest available column is `fmp_sbc_to_revenue` (fmp_enrichment):
- 35,028 names lack `sbc_pct_revenue`; 27,636 of those carry `fmp_sbc_to_revenue`.
- 26,380 of those values are exactly 0, a zero-fill for non-disclosers, so only strictly positive values may count.
- 587 are in (0, 2%).

**Patches.**
- **A (comment):** `# roic_after_sbc≈roce is the alternate clean-accounting lens (no SBC/EBITDA level exists where the revenue ratio is missing).`
- **B (code, closest column; the L360-369 policy allows a per-archetype adoption with its own guard):**
```
old:
        (((_ncol('sbc_pct_revenue') >= 0.0) & (_ncol('sbc_pct_revenue') < 0.02)) |
         ((_roic_asbc > 0.10) & ((_roce_n - _roic_asbc).abs() < 0.02))) &
new:
        (((_ncol('sbc_pct_revenue') >= 0.0) & (_ncol('sbc_pct_revenue') < 0.02)) |
         ((_roic_asbc > 0.10) & ((_roce_n - _roic_asbc).abs() < 0.02)) |
         # FMP TTM SBC/revenue where no primary ratio exists; DISCLOSED only
         # (> 0: FMP zero-fills non-disclosers — the trap the (fresh) note closes)
         (_ncol('sbc_pct_revenue').isna() & (_ncol('fmp_sbc_to_revenue') > 0)
          & (_ncol('fmp_sbc_to_revenue') < 0.02))) &
```
**Est. fires changed:** 0 (A) / about +218 (B). The B estimate applies the operating, EBITDA > 5%, ROCE ≥ 8% and share-growth ≤ 10% legs to the 587 reachable names.

## F12: `_clin_bio_e` claims "the same construction as is_clinical_biotech below" but lacks the 2026-10-02 cannabis carve-out (L1145-1159)

**Promise.** L1145-1147: "clinical-stage drug developer, read early ... (the same construction as is_clinical_biotech below)".

**Code.** L8765 now removes `is_cannabis` names from `_is_drug_dev`. The early copy does not. Cannabis LPs and MSOs list under "Pharmaceuticals", so they are still scrubbed from these sites:
- kullamagie_breakout (L3312), weinstein_stage2 (L3346), oneil (L3392)
- analyst_awakening (L7232, parked in biotech_awakening_watch)
- analyst_rerating_confirmed (L7286)

**Impact.**
- 47 cannabis names classify as drug developers under the early construction; 35 of them are non-commercial (CRON, TLRY, OGI.TO, WEED.TO ...).
- Measured: HITI sits in `biotech_awakening_watch` and would move to `arch_analyst_awakening`.
- The three tape archetypes need their full legs to count. Exposure is at most 35 names each.

**Patch** (L3606). This fixes every reader after the cannabis classifier: analyst_awakening and rerating_confirmed.
```
old:
    df['is_cannabis'] = _is_cannabis.astype(int)
new:
    df['is_cannabis'] = _is_cannabis.astype(int)
    _clin_bio_e = _clin_bio_e & ~_is_cannabis      # (user 2026-10-02) the same carve-out as is_clinical_biotech
```
The kullamagie, weinstein and oneil sites run before L3606. For them, the `_cann_name` / `_cann_ind_bar` / `_is_cannabis` block (L3594-3606) also needs moving above L3300. It depends only on `_ind`/`_nm`, i.e. industry and name strings.

**Est. fires changed:** about +1 measured (HITI); at most 35 names exposed per tape archetype.

## F13: fmp_distress_flag comment promises a gate the code deliberately does not apply (L653-656)

**Promise.** "Distress is used ONLY as a negative gate on the two cash-rich Cluseau value archetypes."

**Code.** No gate reads it. L3953-3956 says explicitly that Altman-Z "informs, it does not silently remove the name". The flag is surfaced, and `fmp_altman_z` is a spirit weight.

**Impact if gated.** 10 of 37 cluseau_realizable_book fires and 27 of 74 cluseau_buyback_accel fires carry the flag.

**Patch (comment):**
```
old:
    # surfaced as flags. Distress is used ONLY as a negative gate on the two
    # cash-rich Cluseau value archetypes (a deep discount to a book that a
    # near-insolvent balance sheet may not realise is a trap, not a bargain).
new:
    # surfaced as flags. Distress is a DISQUALIFIER FLAG shown beside the two
    # cash-rich Cluseau value archetypes, never a gate (see the note at
    # arch_cluseau_realizable_book); Altman Z is a spirit weight elsewhere.
```
**Est. fires changed:** 0.

## F14: "SURFACED, never gates" promises for the forensic and nuanced flag blocks (L663-666, L716-718)

**Promise.**
- L663-666: "SURFACED flags — informational, never gates ... none removes a name from any archetype".
- L716-718: "QUARTERLY FORENSIC flags — SURFACED, never gates ... not a disqualifier".

**Code.** At least 11 later gate sites read the fq_ flags as legs or vetoes:
- L3825 deleveraging
- L4900 beneish_risk and receivables_divergence vetoes
- L5767 deleveraging
- L5788 cash_leads_earnings
- L6065 and L6074 defrev_build
- L7436 gm_inflection
- L7744 deleveraging
- L8050 gm_inflection
- L8135 beneish_risk veto

`fmp_rd_intensive_flag` is read at L7815 (mb_compounder_insiders_at_high). That read has 0 impact, because `rd >= 0.08` already implies it.

These gates are deliberate later designs, so the comments are the stale side.

**Patch (comment).** Replace the three L716-718 lines with:
```
    # ---- QUARTERLY FORENSIC flags (fmp_quarterly.py) — surfaced tells ----
    # Global 3-statement forensics that were EDGAR-only (or absent) before.
    # Surfaced on every name; several archetypes below ALSO read them as legs
    # (beneish_risk / receivables_divergence vetoes; deleveraging,
    # cash_leads_earnings, defrev_build, gm_inflection as confirmations).
```
At L663, change `informational, never gates` to `informational (rd_intensive is also an mb_ lens)`.

**Est. fires changed:** 0.

## F15: fq_wc_release comment numbers disagree (L785-791)

**Promise.** "cash-conversion cycle shortened >= 15 days YoY". The same comment then says "Material: >= 30 days".

**Code.** `(_qccc_p - _qccc) >= 30`.

**Patch (comment):** `#   working-capital release: cash-conversion cycle shortened >= 15 days YoY` becomes `#   working-capital release: cash-conversion cycle shortened >= 30 days YoY`.

**Est. fires changed:** 0.

---

## Dead assignments with no promise attached (clean-up only, 0 impact)

Token scan, comments excluded; none is read anywhere in the file:

| line | variable |
|---|---|
| L866 | `price_yoy` |
| L959 | `_fcf_now` |
| L1777 | `first_pos_print` |
| L1781 | `margin_confirming` |
| L1785 | `roce_today` |
| L1853 | `profitable` (its 5% leg was dropped, per the L1872 note) |
| L1899 | `roiic_1y_pos` |
| L1900 | `cash_roiic_1y_pos` |
| L1905 | `tangible_equity_pct` (the L1973 note acknowledges it) |
| L1989 | `fcf_margin_lindy` |
| L2100 | `buyback_yield` |
| L2101 | `sbc_pct_revenue` |
| L2108 | `interest_coverage` |
| L2246 | `customer_concentration_flag` |
| L2370 | `roic_latest` |
| L2485-2490 | `_qarp_cheap` (superseded by the inline 2-of-3 vote, whose EV/FCF cap is 20, not 15) |

## Checked and found consistent (not findings)

- blindspot ADV / analyst legs. The prior review's LOOSE finding stands, but the comment does not over-promise.
- dead_option spirit: carries the promised through-cycle cash record.
- bab_becoming: the `nde <= 3.0` cap at L2664 contradicts L2627, but the final reframe drops it, so only `bab_becoming_watch` is affected.
- geographic_global vs diversified_segments `_not_melting` parity: 0 geographic_global fires melt.
- `_seg_engine_ok`: NaN EBITDA margin escape, 0 fires affected.
- capital_discipline: negative P/B passing `pb < 1.5`, 0 fires.
- Fill, coalesce and FX bridge blocks (L1-660): code matches comments.
- data_quality_flag: early and late definitions are identical.

---

## Summary table

| line | archetype | promise | status | est. fires changed |
|---|---|---|---|---|
| 1384-1401 / 1529 | narrative_lag | shock-sized advance leg kept in the re-spec | leg dropped | -1,264 |
| 1609 / 1631-1636 | fixed_cost_demand_shock | leverage cap (nde > 6) | dropped in reframe | -169 |
| 1723 / 1738-1746 | regime_cyclical | leverage cap (nde > 6) | dropped in reframe | -134 |
| 1642 | discounted_vehicle | G2 drops >100%-of-mcap shells | BUG: flag leg bypasses it | -83 |
| 1705 | capital_discipline | missing P/B passes "not re-rated" | BUG: dead (`pb` filled 99) | +19 (r2b8) |
| 1935 / 1946 | roic_inflect | accounting ROIC crossed zero | BUG: cash-only cross stands alone | -596 |
| 2404-2412 | quiet_compounder | core needs TTM EBIT >= +10% | leg only in the dead exceptional | -153 |
| 2048-2053 | lindy_fcf | >= 7 fiscal years | code >= 3 (fix comment, or code) | 0 / -89 |
| 1054-1061, 1537, 1827, 2017, 2050, 2085, 2142, 2406, 2470 | all `_tier` archetypes | exceptional / elite definitions | overwritten by spirit loop; 2 lenses missing | 0 arch (exc only) |
| 1770-1785 | kpi_threshold | ROCE today >= 5% | never an AND leg; dead var (fix comment) | 0 (-1,746 if coded) |
| 2185-2186 | low_sbc_quality | SBC/EBITDA alternate lens | absent; no such column (fix comment, or fmp_sbc_to_revenue lens) | 0 / ~+218 |
| 1145-1159 | clinical-biotech scrub (5 archetypes) | same as is_clinical_biotech | lacks cannabis carve-out | ~+1 measured (≤35 exposed) |
| 653-656 | Cluseau (2) | Altman distress is a gate | never gated by design (fix comment) | 0 (-37 if gated) |
| 663-666, 716-718 | fq_/fmp_ surfaced flags | never gates | 11 gate sites read them (fix comment) | 0 |
| 785-791 | fq_wc_release_flag | CCC shortened >= 15 days | code 30 (fix comment) | 0 |
