# FIP silent-drop audit

The v2 ranking reproduces cleanly against the audit CSV — all 62 rows still pass the v2 gates, sector medians match to zero, and `asym_v2_score` recomputes to float precision (max |diff| ~8e-17). The workbook rebuilds with the expected 17 tabs and 62 body rows. However, silent-drop risk in the upstream screener is **high**: five confirmed bugs are severity=high (two cache-clobber, one cache-staleness pair, one momentum-mode row-drop, one NaN→worst-rank penalty), and the price/OHLC caches are effectively unversioned — the same input on two different days can produce materially different outputs with no warning. 3 audit items were refuted and are not itemized here.

## Confirmed bugs (21)

| Dimension | File:line | Summary | Severity |
|---|---|---|---|
| universe | frog_in_pan_screener.py:197 | `drop_duplicates(subset="name")` collapses genuinely distinct entities that share a `name` string (BRK.A/BRK.B, ARR/ARR-PC, six AmTrust preferreds) | medium |
| ohlc_fip | frog_in_pan_screener.py:391 | Price cache has no staleness check — cached symbols returned regardless of age | high |
| ohlc_fip | frog_in_pan_screener.py:484 | OHLC cache has the same no-staleness bug — stale bars feed compute_qulla | high |
| ohlc_fip | frog_in_pan_screener.py:443 | `--no-cache` silently overwrites `.price_cache.pkl` with only the current run's symbols | high |
| ohlc_fip | frog_in_pan_screener.py:534 | `--no-cache` clobbers `.ohlc_cache.pkl` identically | high |
| ohlc_fip | frog_in_pan_screener.py:328 | Short-window monthly FIP unreachable for 13-24 months of history (guard nests short branch inside long-branch guard) | medium |
| ohlc_fip | frog_in_pan_screener.py:279 | Silently reports a "252-day" FIP over ~238 samples for recently-listed names (~260-273 bars) | low |
| ohlc_fip | frog_in_pan_screener.py:663 | `compute_qulla` never applies `skip_recent_days` — RS FIP/pret/asym metrics include the partial current bar | low |
| fundamentals | frog_in_pan_screener.py:1139 | Bare `except Exception: return None` swallows every non-rate-limit yfinance error with no log and no retry | medium |
| fundamentals | frog_in_pan_screener.py:1141 | `not info` guard misses truthy stub dicts; stub tickers produce all-NaN Fundamentals treated as "successfully fetched" | medium |
| fundamentals | frog_in_pan_screener.py:921 | `build_qulla_table` keeps `fu=None` rows with all-NaN fundamentals while `build_screen_table` drops them — silent mode divergence | medium |
| fundamentals | frog_in_pan_screener.py:1246 | `_pct_rank` maps NaN → 0.0, converting "missing metric" into "worst on that axis" indistinguishably | low |
| fundamentals | frog_in_pan_screener.py:1120 | `_annual_revenues` bare-excepts every yfinance failure and returns empty Series; caller then substitutes TTM YoY into the annual field | low |
| fundamentals | frog_in_pan_screener.py:1156 | Rev-growth guard requires both denominators > 0; single zero/negative print unreachable-fallbacks the 2-year branch and silently swaps to TTM | low |
| fundamentals | frog_in_pan_screener.py:1166 | On NaN annual rev_growth, code silently substitutes yfinance TTM `revenueGrowth` into the same field — semantically different metric, no flag | low |
| ranking | frog_in_pan_screener.py:1246 | NaN → 0 rank is strictly worse than the smallest non-NaN percentile (1/n); missing fundamentals score worse than the actual worst-in-cohort | high |
| ranking | frog_in_pan_screener.py:807 | `_band_score.fillna(0)` — NaN input treated as maximally-far-from-band, indistinguishable from a genuine wrong-side reading | medium |
| ranking | frog_in_pan_screener.py:1267 | `build_screen_table` silently drops FIP survivors whose fundamentals fetch returned None — no counter, no warning | high |
| ranking | frog_in_pan_screener.py:956 | `.where(pb > 0)` / `.where(ev_ebitda > 0)` collapses negative-book / negative-EBITDA companies to NaN → rank 0, indistinguishable from missing data | medium |
| ranking | frog_in_pan_screener.py:1075 | `drop_duplicates(subset="name")` after sort-by-score silently discards alternate listings and same-name-different-company rows | low |
| workbook | build_workbook.py:97 | Number format's third section is en-dash on zero, so exact 0.00 scores render identically to missing (14 rows in current audit) | medium |

## Confirmed — details

### universe · frog_in_pan_screener.py:197 — name-only dedup collapses distinct entities
**What breaks:** Docstring advertises "cross-listing" dedup but the code dedupes on the raw `name` string alone. Six AmTrust preferreds share one `longName`; ARR common and ARR-PC preferred share one; BRK.A/BRK.B collide on Mega Cap runs; SPAC common/unit/warrant triplets collapse to one. The stable sort's undocumented FD order determines which survives.
**Trigger:** `--countries='United States'` with default Small/Mid caps — ARR (Mid) and ARR-PC (Small) collide; the preferred is silently dropped.
**Fix:** Change subset to `["name", "symbol"]` or dedupe on the FD index alone; if the intent really is cross-listing collapse, key on `(name, is_primary_country)` and require the collision to be across countries.

### ohlc_fip · frog_in_pan_screener.py:391 — price cache has no staleness check
**What breaks:** `todo = [s for s in symbols if s not in cache]` uses set membership only; a symbol cached weeks ago is served with no top-up. compute_fip slices `iloc[-252:]` relative to the series' own tail, so windows anchor to whenever the cache was written, not today.
**Trigger:** Re-run today after any prior run of a few days or more without `--no-cache`.
**Fix:** After loading the cache, compute `last_index = cache[s].index[-1]` per symbol and add any symbol whose `last_index < today - staleness_days` to `todo`; then merge fresh bars into `cache[s]` rather than skipping.

### ohlc_fip · frog_in_pan_screener.py:484 — OHLC cache has the same no-staleness bug
**What breaks:** Identical mechanism — cached DataFrames pass into `compute_qulla` unchecked, so `last_price`, `rs_pret_d`, `asym_w_last`, `asym_m_last` all anchor to whenever the cache was last written.
**Trigger:** Any second `--qulla` run without `--no-cache`.
**Fix:** Apply the same last-index staleness check as the price cache; refetch if `df.index[-1]` is more than N business days behind today.

### ohlc_fip · frog_in_pan_screener.py:443 — `--no-cache` clobbers price cache
**What breaks:** With `use_cache=False`, line 387 initializes `cache = {}` instead of loading disk. The final save at line 443 unconditionally rewrites `.price_cache.pkl` with only the current run's symbols; a `--no-cache --limit 20` after a 2000-symbol full run deletes 1980 cached series.
**Trigger:** `python frog_in_pan_screener.py --no-cache --limit 20` after any larger run.
**Fix:** Guard the final `_save_price_cache(cache)` on `use_cache=True`, or read-modify-write against the on-disk pickle so the current run merges into rather than replaces existing content.

### ohlc_fip · frog_in_pan_screener.py:534 — `--no-cache` clobbers OHLC cache identically
**What breaks:** Same mechanism as line 443; the OHLC pickle is opened `"wb"` and pickled with the current-run dict only.
**Trigger:** `python frog_in_pan_screener.py --mode qulla --no-cache --limit N` after any larger prior run.
**Fix:** Same as line 443 — gate the final save on `use_cache` or merge with existing on-disk contents before writing.

### ohlc_fip · frog_in_pan_screener.py:328 — short-window monthly FIP unreachable for 13-24 months
**What breaks:** `monthly_ret` is initialized empty and only reassigned inside `if len(monthly) >= 24 + skip_m` (line 298). The short-window branch at line 328 gates on `len(monthly_ret) >= 12 + skip_m`, which stays 0 when the outer guard fails — so `fip_m_s`, `fip_m_s_prev`, `fip_m_s_inflection`, `pret_m_s` all stay NaN for stocks with 15-24 months of history despite needing only 13.
**Trigger:** Recent IPO / spin-off with ~380 trading days.
**Fix:** Compute `monthly_ret = monthly.pct_change().dropna()` unconditionally (independent of the 24-month gate) so the short-window branch can enter based on its own 12-month requirement.

### ohlc_fip · frog_in_pan_screener.py:279 — silent short-window "252-day" FIP
**What breaks:** For a stock with 260 daily bars, `daily_ret.iloc[-273:-21]` clamps to about 238 samples and `_fip`'s `min_len=20` passes. The result is stored in `fip_d`/`pret_d` and compared against full-window peers in `filter_fip_candidates` and `_pct_rank`.
**Trigger:** IPO ~13 months old with roughly 260-273 daily bars.
**Fix:** Require the slice to return at least, say, 240 non-NaN samples before returning a value in `fip_d`/`pret_d`; otherwise return NaN and let downstream filters exclude the row.

### ohlc_fip · frog_in_pan_screener.py:663 — compute_qulla ignores skip_recent_days
**What breaks:** `rs_ret.iloc[-252:]`, `rs_w_ret.iloc[-52:]`, and monthly resample all anchor at `iloc[-1]`, so today's partial daily bar, the current partial W-FRI week, and the partial ME month leak into every RS FIP / asymmetry metric. `rs_fip_w_prev` (which uses `iloc[-65:-13]`) is clean, so the inflection subtracts clean from contaminated.
**Trigger:** Any `--mode qulla` run on a day that is not month-end / Friday close.
**Fix:** Add a `skip_recent_days` parameter to `compute_qulla` matching `compute_fip`'s default of 21 and apply the same `iloc[-(N+skip):end]` slicing to all RS/asym windows.

### fundamentals · frog_in_pan_screener.py:1139 — bare-except swallows every non-rate-limit error
**What breaks:** `except Exception: return None` catches HTTPError, ConnectionError, JSONDecodeError, and yfinance internal KeyErrors and silently returns None on the first attempt, aborting the retry loop. The stderr "K ok / N" line is the only trace.
**Trigger:** A delisted ticker like BPSO.MI (404), or any transient network flake.
**Fix:** Catch specific exceptions with `logging.warning(f"{symbol}: {type(e).__name__}: {e}")`, retry on transient errors, and expose a per-symbol failure counter to the caller.

### fundamentals · frog_in_pan_screener.py:1141 — stub dicts bypass the empty-info guard
**What breaks:** `if not info: return None` treats only literal empty dicts as failures; yfinance's `{'symbol':'X','quoteType':'EQUITY'}` stubs pass through. A Fundamentals object with pb/ev_ebitda/rev_growth all NaN is returned and treated identically to a real fetch.
**Trigger:** Delisted / newly-listed / thinly-covered ticker where yfinance returns a minimal stub.
**Fix:** Require at least one of `trailingPE`, `marketCap`, `enterpriseValue`, `totalRevenue` to be present before returning; otherwise return None (or a sentinel with `data_available=False`).

### fundamentals · frog_in_pan_screener.py:921 — qulla keeps fu=None rows, momentum drops them
**What breaks:** `build_qulla_table` uses `fu.X if fu else float("nan")` and appends the row anyway; `build_screen_table` at line 1266-1267 does `if fu is None: continue`. Two modes produce different survivor counts for the same failed refetch with no warning.
**Trigger:** Any symbol whose fundamentals fetch fails (rate-limit past 4 backoffs, 404, network flake).
**Fix:** Pick one policy — either add `if fu is None: continue` to `build_qulla_table` for consistency with momentum mode, or add a `data_incomplete` boolean column so both modes surface the divergence in output.

### fundamentals · frog_in_pan_screener.py:1246 — NaN → 0 rank silently penalizes missing data
**What breaks:** `_pct_rank` uses `na_option="keep"` then `.fillna(0.0)`, so a REIT with no `priceToBook`, a negative-EBITDA firm, or a rate-limited ticker each scores 0 on that leg — indistinguishable from being genuinely worst.
**Trigger:** Any partial fundamentals payload (financials, negative-EBITDA firms, newly-listed).
**Fix:** Either fill NaN with the median non-NaN rank (0.5) so missing data is neutral, or track a per-row missing-count and expose it as a column so the user can distinguish.

### fundamentals · frog_in_pan_screener.py:1120 — `_annual_revenues` bare-excepts entire pipeline
**What breaks:** Both `tk.income_stmt` and `tk.financials` are wrapped in `except Exception: continue`; if both raise or lack the "Total Revenue" index, an empty Series is returned. Line 1165-1166 then silently substitutes yfinance's trailing 4-quarter `revenueGrowth` (TTM YoY) into the `rev_growth` field, while `rev_growth_prev` and inflection stay NaN.
**Trigger:** Non-US financials / REITs whose income_stmt endpoint 403s or lacks the standard revenue label.
**Fix:** Log the failure and return a distinguished sentinel or add a `rev_growth_source` field ("annual" / "ttm" / "missing") so downstream can weight or exclude accordingly.

### fundamentals · frog_in_pan_screener.py:1156 — zero-or-negative denominator bypasses 2-year fallback
**What breaks:** With `len(rev) >= 3` but r2 ≤ 0 (loss year, restated print), the `if r1 > 0 and r2 > 0` guard fails; the `elif len(rev) == 2` fallback does not execute because we entered the outer `if` branch. Both `rev_growth` and `rev_growth_prev` stay NaN, then get overwritten by the TTM substitute.
**Trigger:** A ticker whose oldest of 3 annual revenue prints is 0 or negative (data errata or a genuine loss with unusual line-item mapping).
**Fix:** Compute r0/r1 from any pair with both denominators > 0 (search the 3-year window rather than requiring the two adjacent oldest prints).

### fundamentals · frog_in_pan_screener.py:1166 — TTM YoY silently substituted for annual YoY
**What breaks:** When multi-year `rev_growth` is NaN, `rev_growth = rev_growth_info` overwrites the same field with a semantically different metric (trailing 4-quarter YoY vs. fiscal-year YoY). `rev_growth_prev` stays NaN, so inflection is NaN, and `_pct_rank`'s NaN→0 penalty applies on that axis.
**Trigger:** Any ticker with <3 usable annual prints or a failed `_annual_revenues` pull.
**Fix:** Store TTM into a separate `rev_growth_ttm` column and leave `rev_growth` NaN; only mix if the caller opts in.

### ranking · frog_in_pan_screener.py:1246 — NaN → 0 penalty on composite score
**What breaks:** Same code as the fundamentals finding, but the ranking-level consequence: default qulla weights sum to 0.37 across the four fundamentals ranks (pb 0.06 + ev 0.06 + rev_g 0.17 + rev_inf 0.08). A ticker with all four NaN scores 0.37 lower than a peer at rank 1.0 with no data-missing flag anywhere in the output.
**Trigger:** Fetch-failed ticker reaches `build_qulla_table` — most likely a `.KL` / `.NS` / EU-financial with rate-limit fallout.
**Fix:** Fill NaN with 0.5 (median rank) or renormalize the composite over only the non-NaN legs for each row so missing data neither penalizes nor rewards.

### ranking · frog_in_pan_screener.py:807 — `_band_score` also fillna(0)
**What breaks:** `_band_score` returns 0 for NaN input, identical to what a value many sigmas from target returns. In early mode the three band terms sum to 0.13 of the composite; a short-history stock with NaN `va_fip_d` from `_fip_change` loses that silently.
**Trigger:** Recent IPO with short asym_d series enters `shortlist_early_stage` (which only filters on `rs_pret_d` NaN).
**Fix:** Return NaN from `_band_score` on NaN input and let the composite skip / renormalize that term.

### ranking · frog_in_pan_screener.py:1267 — momentum silently drops fetch-failed rows
**What breaks:** `if fu is None: continue` in `build_screen_table` removes the row from the CSV and print output with no counter increment. On a rate-limited run this can silently halve the momentum table; the `fundamentals for {len(funds)} candidates` log at line 1423 reports dict size, not row loss.
**Trigger:** `fetch_fundamentals` returns None (rate-limit past 4 backoffs, 404, network flake).
**Fix:** Count drops and print `dropped {n} FIP survivors due to missing fundamentals`, or keep the row with NaN fields plus a `data_incomplete` boolean and let the ranker decide.

### ranking · frog_in_pan_screener.py:956 — negative book/EBITDA coerced to NaN
**What breaks:** `.where(pb > 0)` maps negative `pb` to NaN, which `_pct_rank` then maps to 0. Loss-eroded book equity and negative-EBITDA firms score identically to no-data-at-all, and both score identically to being genuinely worst on that axis.
**Trigger:** Loss-making biotech / restructuring name survives `filter_qulla_candidates` on RS grounds with pb=-0.4.
**Fix:** For P/B and EV/EBITDA, treat negative values as a distinct signal — e.g. rank on `-1/pb` so negative book gets a strongly-negative rank, or add a `pb_negative` boolean flag and route those rows to a separate stratum.

### ranking · frog_in_pan_screener.py:1075 — post-sort dedup silently drops alternate listings
**What breaks:** `sort_values("score", desc)` then `drop_duplicates(subset="name", keep="first")` discards the lower-scoring row whenever two rows share Yahoo `longName`. With `--all-listings` this collapses genuine cross-listings; two unrelated small caps with a generic name like "Investment Company plc" also collide.
**Trigger:** `python frog_in_pan_screener.py qulla --all-listings` with European dual-listed names (SHEL.L/SHEL.AS, RHM.DE/RHM.MU).
**Fix:** Dedupe on `["name", "country"]` or add a `symbol` tiebreak; log the number of rows collapsed at each dedup.

### workbook · build_workbook.py:97 — exact 0.00 renders as en-dash
**What breaks:** `NUM_FMT`'s third section (`;"–"`) is applied to zero, not just to missing. A survivor with `rs_fip_d == 0.0` shows an en-dash indistinguishable from NaN. The current audit contains 14 such rows across `rs_fip_*`; the bug generalizes to every FMT_RATIO/FMT_PP column.
**Trigger:** Any survivor whose column is exactly 0.0 (BP.L on `rs_fip_w_inflection`, 6806.T / 8331.T / 5434.TW in Asia Developed).
**Fix:** Change the format to `#,##0.00;(#,##0.00);0.00` so zeros render as `0.00`, keeping the en-dash exclusively for NaN via the existing `pd.isna(v)` branch.

## Plausibles (6)

- **frog_in_pan_screener.py:179** — Empty-check runs before index-notna and ticker-regex filters; a universe emptied by those later filters slips through and reports "got prices for 0/0" instead of raising.
- **frog_in_pan_screener.py:190** — `--include-suffix` rows with FD `country=NaN` get sentinel `__none__` and lose the name dedup to a same-name row with mapped country.
- **frog_in_pan_screener.py:189** — Suffix-extract regex is uppercase-only while the ticker-accept regex is case-insensitive; hypothetically lowercase `abc.pa` slips through non-primary.
- **build_workbook.py:57** — Unmapped countries bucket to 'Other', which is not in REGIONS, so those rows only appear in All Survivors. Zero rows affected in current data.
- **build_workbook.py:406** — Hard-coded `> -1e9` sentinel filter would drop legitimate values ≤ -1e9. Structurally-bounded metrics currently sit far above that threshold.
- **build_workbook.py:91** — `pd.to_numeric(errors='coerce')` silently NaN-fills non-numeric cells in PCT_COLS. All current source columns are already float64.

## Refuted: 3 audit items were checked and not upheld against the current code; they are omitted here.

## Reproduction bullets

- **STEP 1 — Gates:** Loaded `asymmetric_v2_universe_audit.csv` (62 rows, matches expected). Re-applying all v2 gates on the CSV's own columns: **62 / 62 pass**, no silent drops.
- **STEP 2 — Sector medians:** Recomputed `median(ev_ebitda_use)` per `sector_used` across the 62 survivors; **max |diff| = 0.000000** across all 9 sectors vs. the CSV's `sec_ev_med`.
- **STEP 3 — Fresh yfinance spot check:** 1st / 31st / 62nd survivor (`000960.SZ`, `C`, `VTRS`). Drift vs CSV: 000960.SZ pb -18.1% / ev_ebitda -15.6%; C pb -1.6% / ev_sales -11.7%; VTRS pb +8.3% / fcf_yield -0.8 pp. Material drift on the Chinese name, modest on VTRS, marginal on C — code is unchanged; the world moved.
- **STEP 4 — Rank-order:** Recomputed `asym_v2_score = sqrt(upside*floor)*(0.7+0.3*quality)*(0.8+0.2*stealth)` from CSV inputs; **max |recomp − csv| = 8.33e-17**. Formula reproduces to float precision.
- **STEP 5 — Workbook:** `build_workbook.py` exit 0. **17 tabs** in expected order; All Survivors has **62 body rows**; every populated region has at least one body row (NA 10/40, Europe 4, Asia Dev 10/13, Asia Emerg 3, MENA+Africa 2; LatAm has zero tickers in the universe).

Files:
- `/home/user/cyclepapa/scratchpad_repro.py`
- `/home/user/cyclepapa/FIP_Asymmetry_Workbook.xlsx`