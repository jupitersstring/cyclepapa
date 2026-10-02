# Data-layer root-cause patches (METHODOLOGY_AUDIT_4, causes 1, 3, 4, 5, 6)

`bugfix_data.py` holds `P = [(id, file, old, new), ...]`: 14 patches across 5 files. Each `old` occurs exactly once in the current repo file. Apply them in list order.

**Verification.** `dl/apply_patches.py` applies the patches to pristine copies in `dl/orig/`, writes the results to `dl/p/` and parses every file. It asserts that each `old` occurs once in the repo file and once in the copy as it evolves. The patched copies were then run against the live master (read-only), with every output going to `dl/`:

- `apply_ticker_yf.py` produced `asym_base.csv.gz` (original code) and `asym_p.csv.gz` (patched). Each run took about 40 s.
- `archetype_tags.compute()` ran three times with CWD=`dl/`, about 76 s each:
  - T0: original code on the base master.
  - T1: original code on the patched master. T0 to T1 isolates patches 1 and 2.
  - T2: patched code on the patched master. T1 to T2 isolates patches 3 and 4.
- `build_archetype_book.py` and `build_country_archetype_book.py` ran in both the original and patched versions, writing `--out` into `dl/`.

The repo itself was never written. Before the T0, T1 and T2 runs `archetype_tags.ASYM_PATH` was pointed at the scratch master; that is a harness change only and is not part of P.

---

## 1. D&A and financing CF in the home currency on ADR/OTC lines: `apply_ticker_yf.py`

**Root cause, as found.** `da_ttm` is already registered in `_LEVEL_COLS`. However, the restatement passes skip every row that already carries a `ccy_bridge`; those rows rely on the source-frame bridge, which converts the `y` frame once at load. That bridge listed `yf_capex_stmt`, `yf_cfo_stmt` and `yf_fcf_stmt` but not `yf_da_stmt`, `yf_financing_cf_stmt`, `yf_net_debt_issuance_stmt` or `yf_buyback_stmt`. The D&A and financing gap-fill therefore wrote raw financial-currency figures onto bridged USD lines. Because the fill is gap-fill-only, those values then stayed frozen.

- Before the patch, 4,458 bridged rows carried exactly the raw Yahoo D&A and 1,957 the raw financing CF.
- EDGAR is not part of the bug. On the 86 bridged rows where both exist, EDGAR's 20-F levels sit in the quote currency: the median of EDGAR divided by bridged Yahoo is 1.00.
- `fix_pipeline.fx_convert` and `derive_missing_columns.py` do not touch these columns.
- `capex_avg`, `oe_avg` and `ni_avg` are already converted. In the master they are EDGAR-only, in USD and in `_LEVEL_COLS`. In `archetype_tags`, the FMP fill multiplies them by `fq_fx_to_master` (L572).

| id | change |
|---|---|
| DA1_source_bridge | Adds the four Yahoo statement columns (D&A, financing CF, debt issuance, buyback) to the source-frame bridge. |
| DA2/DA3_edgar_cov_* | Records which rows the audited EDGAR merge set this run (`_edavg_has`). |
| DA4/5/6_readopt_* | On bridged rows, re-adopts the bridged statement D&A and financing CF every run, except where EDGAR supplied the value. This repairs the frozen values. The directive never to override EDGAR is kept. |
| DA7_backstop | In the late sanitation, nulls `da_ttm` and adds the qc flag `da_incoherent` in three cases: D&A < 0; D&A > revenue on a positive-EBITDA row; D&A > 2× EBITDA while the operating margin is positive. Pre-revenue burners, whose D&A legitimately exceeds a tiny revenue, keep theirs. 417 rows are nulled: 91 negative, 59 above revenue and 270 above 2× EBITDA; 109 of the 417 are bridged rows. |

**Measured on the master (base → patched).**

| metric | base | patched (DA1-6 only) | patched (+DA7) |
|---|---|---|---|
| da_ttm > ebitda_ttm (EBITDA > 0) | 3,203 | 2,185 | 1,895 |
| audit metric: EBITDA > 0, op margin > 0, D&A > 1.05× EBITDA | 1,770 (1,029 bridged) | 893 (152 bridged) | 622 (110 bridged) |
| da_ttm > revenue_ttm (revenue > 0) | 1,154 | 400 | 341 |

- The 1,895 remaining rows with D&A above EBITDA are mostly loss-makers with EBIT < 0, which is legitimate. The 622 remaining on the audit metric fall in the 1.05-2× window-drift band.
- The 341 remaining rows with D&A above revenue are negative-EBITDA, pre-revenue names; they are kept by design.

**Named rows (patched master).**

| line | before | after |
|---|---|---|
| TOELY / TOELF | da_ttm 8.13e10 (JPY 81.3B) | **$507M** (EBITDA $6.27B, NI $5.0B) |
| ASEKY | da_ttm 2.65e11 | **$1.65B** (EBITDA $3.0B, revenue $32.5B) |
| TLK | financing_cf_ttm −2.018e13 (IDR) | **−$1.11B**: paydown about 7.5% of the $14.7B market cap, where the audit expected 7.9% (it had read 1,370×) |
| KAIKY | 5.24e10 | $327M |
| TCMFF | 2.08e12 | $1.44B |

**Archetype impact (T0 → T1), fires before → after (removed / added).**

| archetype | before → after | removed / added |
|---|---|---|
| xr_forensic_multiple_gap | 359 → 223 | −152 / +16 |
| overdepreciated_assets | 470 → 304 | −173 / +7 |
| xr_forensic_floor_growth | 822 → 672 | −160 / +10 |
| owner_earnings_power | 340 → 303 | −55 / +18 |
| xr_harvest_distribution | 153 → 111 | −44 / +2 |
| xr_paydown_yield | 446 → 434 | −14 / +2 |
| xr_amortization_mask | 95 → 90 | −12 / +7 |
| xr_growth_capex_masked | 23 → 21 | −2 / +0 |

Patches 1 and 2 together change 1,659 archetype flags.

## 2. Stale `cash_gt_ev_flag`: `apply_ticker_yf.py` (CEV1_recompute_flag)

The flag was set once by the per-country builders (`yartseva_db` and `edgar_to_yartseva`). The harmonizer moves cash, debt, market cap and EV but never touched the flag.

The patch recomputes it just before the USD-twin block, from the final quote-currency levels. It uses the builder's own definition:

- EV > 0
- cash > EV
- known net cash > 0
- cash ≤ 3× market cap

The flag is NaN where cash or EV is missing. The patch also recomputes `cash_pct_ev`, except on rows where cash exceeds 20× market cap, which stay nulled as the currency-mismatch class.

| | base | patched |
|---|---|---|
| flags = 1 | 1,733 | 2,091 |
| flag = 1 with cash ≤ EV | 471 | 0 |
| flag = 1 with cash or EV missing | 72 | 0 |
| flag = 1 with net debt | 114 | 0 |

- Transitions: 681 rows go from 1 to 0, 72 go from 1 to NaN, and 1,111 go from 0/NaN to 1. The last group are true cash > EV names the stale flag had missed.
- Archetypes (T0 → T1): discounted_vehicle 1,191 → 1,183 (−30 / +22); negative_ev_value 4,772 → 4,899 (−115 / +242); balance_sheet_return 1,746 → 1,909 (−87 / +250); biotech_deep_value 121 → 114 (−19 / +12); nol_shell 20 → 20 (−1 / +1); oak_asset_floor unchanged.
- **Decision for you.** Builder parity excludes EV ≤ 0, because every reader ORs a separate `EV < 0` leg. If the flag included negative EV, the count would be 2,989.

## 3. Dead / delisted listings: `archetype_tags.py` (DEAD1_scrub)

This is one shared scrub, placed after the micro-shell scrub. It zeroes `_scrub_cols`: every common-equity archetype, the gated scores and the `_watch` columns, with `arch_senior_security_value` exempt. It also sets `dead_listing_flag`, which is in `df` only and is not added to the export list.

```
dead = ((market_cap_usd <= 0 or NaN) or (price <= 0 or NaN)) and not (price_age_days <= 30)
       or price_age_days > 90
```

The rule deliberately does not rely on `stale_price` alone: of its 1,029 rows, the median `price_age_days` is 1, because the flag comes from a stale lynch tape. "Price but no age" is not dead either: that group of 835 rows includes live names such as NSR.AX, EKSO and Nilfisk.

**Effect.**

- 7,213 dead rows (`price_age_days` NaN for 7,209 of them). 684 of these fired 1,386 flags across 45 archetypes. The rule catches two groups:
  - 4,684 rows with no market cap and no price age.
  - 2,525 rows with a market cap but no price and no age: SWMAY, VIAC, FLT, SMFKY, Uniper, Rosneft.
- Flags removed, top: cash_quality 256, lindy_fcf 200, no_dilution 141, capital_light_pivot 137, cash_reinvest 104, asleep_at_wheel 94, durable_reinvestment 93, lindy_margin 89, buyback_compounder 87, concentrated_segments 43, reinvest_inflect 38, blindspot 23.
- Named rows go to 0 archetypes: SWMAF 7, SWMAY 8, SWMA.ST 7, FLIR 4, VIAC 2, FLT 7.
- Gates without `mcap > 0` are covered automatically, so there are no per-archetype edits.

## 4. Missing analyst count read as neglect: `archetype_tags.py` (COV1_share_coverage)

Right after all the merges in `compute()`, each line takes the maximum over its `company_key` of `n_analysts`, `n_analysts_pew` and `sent_n_analysts`. These are the coverage counts the neglect gates read; `sent_n_analysts_d12` is a delta and is left alone. The maximum fills a missing count and also raises a lower one. The patch adds `analyst_cov_shared`; 1,911 lines inherit coverage.

**Effect (T1 → T2, live rows).**

| archetype | before → after |
|---|---|
| flyover | 1,404 → 1,286 (−117 live) |
| coiled_base | 378 → 369 |
| coiled_fallen_angel | 76 → 74 |
| base_ignition | 87 → 85 |
| liger_neglected_survivor | 1,020 → 1,014 |
| mb_fallen_ignored_believers | 380 → 381 (+2 / −1; its gate needs 2-5 analysts) |

- TCTZF (Tencent F-line) and LVMHF leave flyover. Second-line flyover fires drop from 140 to 32.
- **Limit.** Of the 1,286 remaining flyover fires, 842 have no count on any line of their company. Most are ADR (`…Y`) lines, which carry their own US ISIN and so their own `company_key`, or companies no source covers. A normalised-name key would reach only 18 more. Closing the rest is flyover's own fix (treat NaN as unknown, not as neglected), not a data-layer change.

## 5. Second lines counted as separate companies (books): `otc_flag.py`, `build_archetype_book.py`, `build_country_archetype_book.py`

**Today.** `dedupe_display` collapses lines on the normalised name only, and keeps whichever line ranks highest, which is often the OTC line. Cover and section match counts are line counts; the Density tab is not deduped. `archetype_count` is a per-line count of distinct theses, so a second line does not inflate it. It needs no change, and changing it would alter enrich's ETA weights.

| id | change |
|---|---|
| DEDUP1_dedupe_display | Also collapses by `company_key`. The group keeps the rank of its best line but displays the primary listing when the primary is in the frame. It falls back to the old behaviour without `company_key`. Unit-checked: TCTZF ranked #1 is displayed as 0700.HK at #1. All six book builders and `top_n_by_country` share this function. |
| DEDUP2_archbook_cover_companies | Cover "matches" counts distinct `company_key`. |
| DEDUP3_archbook_density | The Density tab runs through `dedupe_display`. |
| DEDUP4_countrybook_counts | "N matches in country" counts distinct companies. |

**Effect.**

- Universe-wide (T2): dead_option has 2,715 line fires, 136 of them second lines, for 2,625 companies. gayner_four_lens has 554 lines, 52 second lines, for 515 companies. flyover has 1,286 lines for 1,257 companies.
- `top_by_archetype_book` (ex-OTC, at least $10M): Dead Option 2,417 → 2,413 and Flyover 1,180 → 1,179. The book's ex-OTC filter already removes most second lines.
- Both patched book copies ran to completion. The patched country book wrote 52 sheets. The original country-book run was stopped for time; its section counts are the line counts in the table above.
- The extra cost of the patched `dedupe_display` is about 1-3 ms per call (16 → 19 ms on 3,000 rows).

## Not changed / follow-ups

- `fix_pipeline.fx_convert` is correct for the columns it handles. The defect was the harmonizer's source bridge.
- After applying the patches, run `apply_ticker_yf.py`, then the retag, then enrich, then the audit gate. The D&A and cash > EV repairs only reach the master through the harmonizer.
- The FMP fill already converts `financing_cf_ttm` with `fq_fx_to_master` in `archetype_tags`, but only where the master is NaN. The master value now arrives correct.
