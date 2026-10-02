# Dividend Yield ("Div %") Column Rollout — Progress Log

Task: add a "Div %" column (from `dividend_yield` fraction, via `_write_pct` helper)
to every book that carries the mandated P/S + P/B columns. Placed right after
"FCF yld %" wherever that column exists, else next to P/B.

Files in scope:
1. build_country_archetype_book.py
2. build_country_archetype_inflection_book.py
3. build_archetype_book.py
4. top_n_by_country.py
5. build_otc_archetype_book.py
6. build_segment_detail_book.py
7. build_harvard_workbook.py
8. build_nms_book.py
9. build_country_workbook.py

Files explicitly NOT touched: archetype_tags.py, edgar_*.py, lynch_reward_enrich.py,
run_*.sh, methodology_audit.py

---

## 1. build_country_archetype_book.py — DONE
- Inserted `'Div %'` into `HEADERS` right after `'FCF yld %'` (was col 14, Div % now
  col 15). Shifted `WIDTHS` keys 15-20 -> 16-21 (new key 15 width 7 for Div %).
  N_COLS auto-derives from HEADERS (now 21).
- In `_write_country_sheet`: added `_write_pct(ws, row, 15 + o, r.get('dividend_yield'), font=f_text)`
  and bumped every subsequent `_write_*` column index by +1 (roce 15->16,
  net_debt_ebitda 16->17, momentum_12m 17->18, archetype_count 18->19, p_s 19->20,
  pb 20->21).
- Smoke test: `python3 build_country_archetype_book.py --out <scratch>/test_cab.xlsx`
  -> exit 0, no traceback, 51 sheets written. Verified via openpyxl on GLOBAL sheet:
  header row shows `... 'FCF yld %', 'Div %', 'ROCE %', ...` and data rows show sane
  fractional-percent values (2.42, 3.28, 6.79, 2.77, ...) or '–' for missing.

## 2. build_country_archetype_inflection_book.py — DONE
- Identical structure/edits as file 1 (same HEADERS/WIDTHS pattern, same
  `_write_country_sheet` column shift, `dividend_yield` inserted at col 15+o).
- Smoke test: `python3 build_country_archetype_inflection_book.py --out <scratch>/test_caib.xlsx`
  -> exit 0, no traceback, 51 sheets written (Cover + GLOBAL/DM/EM/regions(11) +
  39 countries). Spot-checked header/columns match file 1's pattern (same code path).

## 3. build_archetype_book.py — DONE
- `_write_archetype_table`: headers list already had P/S(14)/P/B(13) before FCF
  yld%(15); inserted `'Div %'` after `'FCF yld %'` (new col 16), shifted ROIC%
  16->17, ND/EBITDA 17->18, EBITDA m% 18->19, Mom 12m% 19->20, Arch# 20->21.
  - Bumped `merge_cells end_column=20->21`, all `range(1, 21)`->`range(1, 22)`
    border loops (3 occurrences), `_section_rule(... span_cols=19)` -> `20`.
  - `widths` dict: added key 16 (width 7) for Div %, shifted old 16-20 -> 17-21.
  - Added `_write_pct(ws, r_idx, 16, r.get('dividend_yield'), font=f_text)`.
- Smoke test: `python3 build_archetype_book.py --out <scratch>/test_ab.xlsx` -> exit 0
  (pre-existing PerformanceWarning about DataFrame fragmentation, unrelated to this
  change), 71 sheets (Cover + Density + 69 archetypes). Verified via openpyxl:
  header row `... 'P/S', 'FCF yld %', 'Div %', 'ROIC %', ...` with sane percent
  values (2.42, 3.28, 6.79, 2.77) in the Div % column.

## 4. top_n_by_country.py — DONE
- 21-col layout -> 22-col. Updated the layout comment block, `N_COLS = 21 -> 22`,
  headers list (inserted `'Div %'` after `'FCF yld %'`), `_write_table_row`
  (added `_put_pct(ws, row, 14, r.get('dividend_yield'), font=f_text)`, shifted
  roce 14->15, net_debt_ebitda 15->16, ebitda_margin 16->17, momentum_12m 17->18,
  yartseva_score 18->19, cluster_n 19->20, confirm_overall 20->21, p_s 21->22),
  and `_common_col_widths` (new key 14 width 7, shifted 14-21 -> 15-22).
  All masthead/border/section-rule spans already used the `N_COLS` variable (no
  literal `range(1, 22)` existed), so they picked up the change automatically —
  verified no leftover hardcoded 21/22 literals via grep.
- Confirmed `dividend_yield` is a native column of `asymmetry_global.csv` (the
  frame this script reads directly), so no change needed to `load_quant()`'s
  `extra_cols` allowlist.
- Smoke test: `python3 top_n_by_country.py --out-csv <scratch>/test_tnbc.csv
  --out-xlsx <scratch>/test_tnbc.xlsx` -> exit 0 (pre-existing fragmentation
  PerformanceWarnings, unrelated), 53 sheets (Cover + 52 countries). Verified via
  openpyxl: header row shows `... 'FCF yld %', 'Div %', 'ROIC %', ...` and P/S
  still present as the last column; data rows show '–' for missing dividend
  yield (sane — many GREEN small-caps here pay no dividend).

## 5. build_otc_archetype_book.py — DONE (no code change needed)
- Verified this module has no local table-layout code of its own: it imports
  and calls `_write_archetype_table` directly from `build_archetype_book.py`,
  so the Div % column added there (file 3) is inherited automatically.
- Smoke test: `python3 build_otc_archetype_book.py --out /tmp/otc_test.xlsx`
  -> exit 0, 70 sheets (Cover + 69 archetypes). Verified via openpyxl: header
  row `... 'P/S', 'FCF yld %', 'Div %', 'ROIC %', ...` with a real value
  (4.48) on one row and '–' on another — correctly rendered.

## 6. build_segment_detail_book.py — DONE
- `_write_segment_table`: `NCOLS = 23 -> 24`. Headers list: inserted `'Div %'`
  after `'FCF yld %'` (new col 13), shifted ROIC% 13->14, EBITDA m% 14->15,
  ND/EBITDA 15->16, Mom 12m% 16->17, Segs 17->18, HHI 18->19, Largest segment
  19->20, Top 3 segments 20->21, Regs 21->22, Top regions 22->23, Fastest
  segment YoY 23->24. Updated `text_cols` {2,3,4,5,19,20,22,23} ->
  {2,3,4,5,20,21,23,24} and `center_cols` {7,17} -> {7,18} (Segs count moved).
  Added `_write_pct(ws, r_idx, 13, r.get('dividend_yield'), font=f_text)` and
  bumped all subsequent `_write_*`/`ws.cell` column indices by +1 through the
  row-writer. `widths` dict: new key 13 (width 7), shifted old 13-23 -> 14-24.
  All border/span loops already used the `NCOLS` variable, so they picked up
  the change automatically.
- Confirmed `dividend_yield` reaches this sheet natively via `asymmetry_global.csv`
  (loaded first in `load_data()`), so no change needed to the `val_cols`
  allowlist used for the per-country CSV valuation-ratio merge.
- Only one table-writer (`_write_segment_table`) is used for every tab (All
  Segments master + per-archetype tabs) — single point of change.
- Smoke test: `python3 build_segment_detail_book.py --out /tmp/seg_test.xlsx`
  -> exit 0, 6 sheets, "3,054 segment-covered rows". Verified via openpyxl on
  the "All Segments" tab: header row `... 'P/S', 'FCF yld %', 'Div %', 'ROIC %'
  ...` with sane values (10.42, 0, '–') in the Div % column.

## 7. build_harvard_workbook.py — DONE (index sheet); per-name pages: NOT touched, dividend yield absent there (see deviation note)
- Index sheet (`build_index`) has no 'FCF yld %' column, only P/B (col 9) and
  P/S (col 10) — per the placement rule this means Div % goes "next to P/B":
  inserted it directly after P/B, before P/S. New layout: col9 P/B, col10
  Div %, col11 P/S (was col10 P/S, now col11); trailing spacer column shifted
  10->12. Updated `_set_col_widths` (new key 10 width 7, old 10/11 -> 11/12),
  `_crimson_banner(... span_cols=11->12)`, `hdrs` list (inserted `'Div %'`),
  header alignment set `(9,10)->(9,10,11)` for right-align, added
  `_write_pct(ws, row, 10, r.get('dividend_yield'), font=...)`, moved the P/S
  write to column 11, and widened the row-rule border loop `range(2,11)->range(2,12)`.
- `dividend_yield` reaches `top_df` natively via `asymmetry_global.csv` (the
  base frame in `load_quant()`), same as the other books — no allowlist change
  needed.
- DEVIATION (informational, no code change): per-name pages
  (`build_name_sheet`'s "Valuation & balance sheet" panel, ~line 689-711) do
  **not** currently show dividend yield — grepped the whole file for
  `dividend_yield` before editing and found zero hits outside this new Index
  edit. The task said to verify and "note it" rather than mandating an add
  here (only the index sheet was in scope), so left the per-name page
  unchanged. Flagging in case the intent was actually to add it there too.
- Smoke test: `python3 build_harvard_workbook.py --out /tmp/hv_test.xlsx
  --top-n 20` -> exit 0 (pre-existing fragmentation PerformanceWarnings,
  unrelated), "top-20 verdicts: GREEN 16, YELLOW 0, RED 0, UNRESEARCHED 4".
  Verified via openpyxl on the Index sheet: header row
  `'#','Ticker','Company','Cntry','Sector','Verdict','Score','P/B','Div %','P/S'`
  with sane values (2.42, 3.28, 6.79, 2.77, '–') in the Div % column and P/B/P/S
  values unshifted/correct on either side.

## 8. build_nms_book.py — DONE (index + region sheets)
- Neither `build_nms_index` nor `build_region_sheet` has a 'FCF yld %' column
  (only P/B then P/S), so per the placement rule Div % goes next to P/B in
  both — inserted right after P/B, before P/S.
- `build_nms_index`: `_set_col_widths` gained key 13 (Div %, width 7), shifted
  old 13 (P/S, width8)->14 and old 14 (spacer, width4)->15;
  `_crimson_banner(..., span_cols=13->14)`; `hdrs` list: inserted `'Div %'`
  after `'P/B'` (alignment logic already used a catch-all `elif i >= 9: right`
  so it needed no change); row writer: added
  `_write_pct(ws, row, 13, r.get('dividend_yield'), font=mono)`, moved P/S
  write to column 14; border loop `range(2, 14) -> range(2, 15)`.
- `build_region_sheet`: same shape — `_set_col_widths` key 12 (Div %, width 7)
  inserted, old 12 (P/B stays 12), old 13 (P/S width4) -> 13... concretely:
  new layout col12=P/B (unchanged), col13=Div % (new, width7), col14=P/S
  (was col13); `_crimson_banner(..., span_cols=12->13)`; `hdrs` list updated
  (alignment used a catch-all `else: right`, no change needed); row writer:
  added `_write_pct(ws, row, 13, r.get('dividend_yield'), font=mono)`, moved
  P/S write to column 14; border loop `range(2, 14) -> range(2, 15)`.
- Confirmed this module reuses `build_harvard_workbook.load_quant()` for its
  data (imports `build_harvard_workbook as bhw`), so `dividend_yield` is
  already present natively — no extra plumbing needed.
- Smoke test: `python3 build_nms_book.py --out /tmp/nms_test.xlsx --top-n 20
  --per-region-n 5` -> exit 0 (pre-existing fragmentation warnings, unrelated),
  "universe: 36,197, NMS sub-universe: 19,015", 34 sheets. Verified via
  openpyxl on both `Global_Top_100` (index) and `R_NorthAmerica` (region)
  sheets: header row `... 'Confirm', 'P/B', 'Div %', 'P/S'` with sane values
  (2.42, 3.28, 6.79, '–', 0) in the Div % column.

## 9. build_country_workbook.py — DONE
- This file writes sheets via raw `df[cols].to_excel(...)`, so the column
  lists are literal DataFrame column names (headers = the raw field name,
  e.g. `dividend_yield`, not a display label like "Div %") — confirmed this
  is expected/intentional per the task's own note on this file. None of the
  six mandated lists carry `fcf_yield`, so `dividend_yield` was inserted
  "next to P/B" in every one — immediately after `'pb'` (before `'p_s'`
  where present):
  - `master_cols` (~line 403)
  - `gem_cols_show` (~line 428)
  - `archetype_cols_show` (~line 513)
  - `per_country_cols` (~line 665)
  - `af_show` (~line 558) — note this list's order is `'p_s','pb',...`
    (P/S before P/B); inserted `dividend_yield` right after `'pb'` per the
    literal rule, giving `'p_s','pb','dividend_yield','ev_ebitda',...`.
  - `Per_Country_Top3` is NOT a named list but an inline per-row dict
    (~line 634-654); added `'dividend_yield': r.get('dividend_yield', 0),`
    right after the `'pb'` entry, before `'p_s'`.
  - Left `garp_show` (~line 464) untouched — it carries `fcf_yield` but
    neither `pb` nor `p_s`, so it is not one of "the mandated P/S + P/B"
    tables and was correctly out of scope (also not in the task's named
    list for this file).
- Confirmed `dividend_yield` is native to `asymmetry_global.csv` (the base
  frame `load_quant()` reads), so it reaches `df` with no extra plumbing.
- Verified the post-write `harvard_style.apply_harvard_style()` pass (called
  at the end of `main()`) auto-formats any column whose header contains
  "yield" as a percent (`_PCT_HINTS` in harvard_style.py includes `"yield"`),
  so `dividend_yield` cells get the same `0.0%;(0.0%);"–"` number format as
  `fcf_yield` — no extra formatting code needed here.
- Smoke test: `python3 build_country_workbook.py --out /tmp/cw_test.xlsx
  --per-country-n 5 --top-master 20` -> exit 0 (pre-existing fragmentation
  warnings, unrelated), 75 sheets, "applied Harvard style". Verified via
  openpyxl/pandas across `Master_By_Asymmetry`, `Gems`,
  `ArchC_FixedCostDemandShock`, `AltaFox_Top60`, `Per_Country_Top3`, and
  `USA_US`: every one now carries a `dividend_yield` column positioned right
  after `pb` with sane values (0.0242, 0.0307, None-for-missing), and on
  `Master_By_Asymmetry` confirmed the cell number_format is
  `0.0%;(0.0%);"–"` (percent, dash for missing) — matching `fcf_yield`'s
  treatment.

---

## SUMMARY — all 9 files complete, no outstanding work.

Deviations from a literal reading of the brief:
1. **build_harvard_workbook.py per-name pages** do not show dividend yield
   and were left unchanged — only the Index sheet was in the task's explicit
   scope for this file; the per-name "Valuation & balance sheet" panel could
   have a `("Div yield (%)", r.get('dividend_yield'), "pct")` row added to
   `vals` (~line 693-710) trivially if that's actually wanted.
2. **build_country_workbook.py** column-list files use raw field names as
   Excel headers (`dividend_yield`, not "Div %") because they're written via
   direct `df[cols].to_excel()` — this matches the task's own framing for
   this file ("check how headers map") rather than a deviation.
3. **garp_show** in build_country_workbook.py was intentionally left alone
   (has `fcf_yield` but no `pb`/`p_s`, so it doesn't carry "the mandated P/S
   + P/B columns" and wasn't named in the task's list for this file).
4. In every book with no 'FCF yld %' column, Div % was placed immediately
   after P/B (before P/S) per the "else next to P/B" instruction.

No files outside the approved list were modified. All 9 smoke tests passed
with exit 0 and no tracebacks (pre-existing pandas `PerformanceWarning`s
about DataFrame fragmentation appear in several builders and are unrelated
to this change — they predate it).
