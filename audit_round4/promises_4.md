# Promise sweep 4: archetype_tags.py, end-of-file section (scrubs, spirit scores, sanity report)

Scope: the original lines 8000-10533, without the GAYNER block. **The file was being edited while I worked.** The Gayner block grew, and a cannabis classifier, `arch_senior_security_value` and `_SENIOR_OK` were added. The file was 10,533 lines at the start and 10,726 at 16:17 UTC. Line numbers below refer to the live file at 16:17 UTC. Every patch is an exact old/new string pair kept in `ps4_patches.py`, next to this report. Running `python3 ps4_patches.py` checks that each old string occurs exactly once in the live file and that the file still parses with every patch applied. At 16:17 all 23 patches were unique and the patched file parsed.

Method: I read the code and grepped the whole file for later uses. Impact was measured on the published outputs (`archetype_tags.csv`, `archetype_tiers.csv`) plus the raw inputs (`asymmetry_global`, `fmp_*`, `ts_snapshot`, `edgar_event_signals`, `fmp_us_filings`), read with usecols. I did not run the pipeline. Where I rebuilt a leg, I checked the rebuild against the published counts first:
- tax_efficient spirit: 199 / 22 / 3, matching exactly.
- greenblatt core: 709 vs 698.
- mb_biotech_financed_hiring: 35 of 36 commercial rebuilds are in the published set.

---

## F1. Spirit tiers: "exceptional = top quartile, elite = top 10%" is not what the code does (L10020 vs L10541/10544)
- **Promise** (L10020): "exceptional = top quartile of spirit, elite = top 10%".
- **Code:** `_core & (sc >= 0.75)` and `_core & (sc >= 0.90)`. `sc` is the mean of several percentile ranks, so these are absolute cutoffs on an average. Averages bunch up around 0.5, so the cutoffs pass far fewer names than a quartile or a decile would.
- **Measured** (archetype_tiers.csv, 212 archetypes with spirit scores):
  - Exceptional is 6.7% of members with a spirit score (median 5.3% per archetype). Elite is 0.7% (median 0.07%).
  - A real within-core quartile / decile would give 45,453 exceptional and 18,264 elite, against 12,203 and 1,291 today.
- **Patch** (P1a + P1b, code to match the comment):
```
old:        df[_n + '_exceptional'] = (_core & (sc >= 0.75)).fillna(False).astype(int)
new:        _scp = sc.where(_core).rank(pct=True)   # documented: top quartile / top 10% OF the spirit within the core
            df[_n + '_exceptional'] = (_core & (_scp >= 0.75)).fillna(False).astype(int)
old:        df[_n + '_elite'] = (_core & (sc >= 0.90)).fillna(False).astype(int)
new:        df[_n + '_elite'] = (_core & (_scp >= 0.90)).fillna(False).astype(int)
```
- **Alternative** (P1alt, fix the comment instead). Recommended if the elite book is tuned to today's scarcity: a code fix would make elite 14x larger.
```
old:    # exceptional = top quartile of spirit, elite = top 10% — "exceptional in
new:    # exceptional = spirit >= 0.75, elite = spirit >= 0.90 — absolute bars on the
        # mean lens rank (~7% / ~0.7% of spirited members, not a quartile) — "exceptional in
```

## F2. Exceptional and elite tiers passed to `_tier()` are overwritten by the spirit loop (flyover L8961-8968; mechanism L10508-10543)
- **Promises:**
  - flyover, L8962-8963: "Exceptional: genuinely unwatched (observed <= 2 analysts) and FCF positive in every fiscal year on file", passed as `_tier(..., exceptional=..., elite_metric=roic_lindy)`.
  - Spirit block, L10508: "a qualitative exceptional set upstream ... is kept alongside the spirit tier".
- **Code:** `_pre_exc` keeps only names **not** in `_TIERED`. Every tiered archetype is in `_SPIRIT_ALL`, so the loop overwrites its `_exceptional` and `_elite` with the spirit bars.
  - All 19 `_tier()` calls that pass `exceptional=` and `elite_metric=` are dead code: blindspot, lindy_margin, lindy_fcf, no_dilution, capital_returner, quiet_compounder, owner_operator, lynch_pegy, lynch_evgy, kullamagie, weinstein, oneil, liger_neglected_survivor, asleep_at_wheel, asleep_unrerated, evsales_derating, analyst_awakening, analyst_rerating_confirmed, flyover.
- **Measured (flyover):** 1,400 fires. The comment's rule gives 497 exceptional; the published count is 76 (70 overlap). Keeping both would give 503.
- **Latent:** the `_pre_exc` OR is not ANDed with the post-scrub core, so a scrubbed row could keep `_exceptional = 1`. There are 0 such rows today.
- **Patch** (P2a + P2b):
```
old:    _pre_exc = {n: df[n + '_exceptional'].copy() for n in _SPIRIT_ALL
                    if n not in _TIERED and n + '_exceptional' in df.columns}
new:    _pre_exc = {n: df[n + '_exceptional'].copy() for n in _SPIRIT_ALL
                    if n + '_exceptional' in df.columns}
old:            df[_n + '_exceptional'] = (df[_n + '_exceptional'] | (_pre_exc[_n] == 1)).astype(int)
new:            df[_n + '_exceptional'] = (df[_n + '_exceptional'].astype(bool)
                                           | ((_pre_exc[_n] == 1) & _core)).astype(int)
```
  If the spirit-only tier is intended, delete the flyover "Exceptional:" comment (L8961-8963) and the 19 dead `exceptional=` and `elite_metric=` arguments instead.

## F3. tax_efficient spirit and `effective_tax_rate_eff` read the tax rate before the fill (L9956-9963; spec lens in docs/spirit_spec.json)
- **Promises:**
  - L9956: "POST-FILL ('effective') copies of every FMP-fillable gate input, so the audit re-verifies ... on the values the gates actually saw".
  - The tax_efficient spirit lens is `effective_tax_rate` (-1).
- **Code:** the FMP fill exists only as the local variable `effective_tax_rate` (L~2106, used by the gate). `df['effective_tax_rate']` stays pre-fill, so both the `_eff` copy and the spec lens read NaN for non-EDGAR names.
- **Measured:**
  - tax_efficient: 1,947 fires. 1,748 have NaN spirit, so only 199 get a score: 22 exceptional, 3 elite.
  - With the fill (simulated with `_rank2`, reproducing 199 / 22 / 3 exactly): 1,840 scored, 191 exceptional, 28 elite.
  - `effective_tax_rate_eff` would be filled on 27,767 more rows.
  - The forensic LIFO and adjusted-book uses (L9696, L9852) run earlier, so this patch does not change them.
- **Patch** (P3):
```
old:    for _c in _EFF_COLS:
            if _c in df.columns:
                df[_c + '_eff'] = pd.to_numeric(df[_c], errors='coerce')
new:    # (audit) the gates read the FMP-filled tax rate (local effective_tax_rate);
        # write it back so the _eff copy and the tax_efficient spirit lens see it too
        df['effective_tax_rate'] = effective_tax_rate
        for _c in _EFF_COLS:
            if _c in df.columns:
                df[_c + '_eff'] = pd.to_numeric(df[_c], errors='coerce')
```

## F4. BUG: an inline comment swallowed a spirit lens (mb_fallen_less_than_industry_financed, L10329)
- **Code:** `[(_c('vs_ind_dist_hi260'), 1),   # (audit 4) lens sign ... drawdown (_c('equity_cagr_5y'), 1),`. The sign fix put the comment in front of the `equity_cagr_5y` lens, so the lens became comment text.
- Every earlier copy in the scratchpad (before_mba, before_xra, before_degate, ...) has `(_c('equity_cagr_5y'), 1)` as a live lens.
- **Impact:** the spirit score is built from 5 lenses instead of 6, for 18 core members (2 exceptional today). Fire counts do not change.
- **Patch** (P4):
```
old:        'mb_fallen_less_than_industry_financed': [(_c('vs_ind_dist_hi260'), 1),   # (audit 4) lens sign matches the gate: above its industry's drawdown (_c('equity_cagr_5y'), 1),
new:        'mb_fallen_less_than_industry_financed': [(_c('vs_ind_dist_hi260'), 1), (_c('equity_cagr_5y'), 1),   # (audit 4) lens sign matches the gate: above its industry's drawdown
```

## F5. Clinical-biotech scrub removes archetypes the comments exempt or that target these names (L9569-9600; promises at L8737-8740, L9583-9584, L9234-9236, L8809-8813)
- **Promises:**
  - "scrubbed from every FUNDAMENTAL archetype below EXCEPT price-action/catalyst ones and their own dedicated deep-value screen" (L8738, L9583).
  - special_situation: "Fire definitive deals on the EVENT alone ... biotech/tech takeout targets where op<0".
  - mb_biotech_financed_hiring is gated on `_is_drug_dev` by design. That makes the archetype contradict itself: whatever passes it is then scrubbed.
  - The scrub header (L9569): "(durable/quality archetypes only) ... their genuine inflection/growth/deep-value theses elsewhere are untouched".
- **Code:** `_biotech_ok` holds only biotech_deep_value (and the new senior_security_value). Every other archetype is zeroed. The momentum scrub is a documented user decision; the catalyst and biotech-specific ones are not.
- **Measured:**
  - special_situation: the definitive-deal path rebuilt from EDGAR flags, fmp_events dates and `ts_r13` finds 22 live deals on clinical biotechs, 18 of them not otherwise scrubbed (BGMS, WHWK, SDEV, GRTX, OVID, CRNX, PSNL, XOMA, APGE, ATAI, TELO, ANEB, RXRX, PULM, MIRA, CNTA, HSCS, ESPR).
  - mb_biotech_financed_hiring: 48 fires. The rebuild without the informed-buyer leg reproduces 35 of the 36 commercial fires it finds, and finds 68 clinical names zeroed by the scrub (a lower bound).
  - wolf_emerging (the prior finding about cannabis names) is being fixed by a concurrent edit (`_is_drug_dev &= ~is_cannabis`, L8766). I did not re-measure it.
- **Patch** (P5a, exemptions; P5b, the header):
```
old:    _biotech_ok = {'arch_biotech_deep_value', 'arch_senior_security_value'}
new:    _biotech_ok = {'arch_biotech_deep_value', 'arch_senior_security_value',
                       'arch_special_situation',            # catalyst: a takeout spread does not depend on the pipeline
                       'arch_mb_biotech_financed_hiring'}   # gated on drug developers by construction
old:    # ===== PRE-REVENUE BIOTECH SCRUB (durable/quality archetypes only): a
        # clinical-stage biotech's "5-year durable margin / quality" is a licensing
        # one-off, not operations (KROS topped lindy_margin/tax_efficient). Zero
        # these names' flags on the QUALITY/durable archetypes; their genuine
        # inflection/growth/deep-value theses elsewhere are untouched. =====
new:    # ===== PRE-REVENUE BIOTECH SCRUB: a clinical-stage biotech's "5-year
        # durable margin / quality" is a licensing one-off, not operations (KROS
        # topped lindy_margin/tax_efficient). Zero these names' flags on every
        # archetype except the exempt set below (_biotech_ok). =====
```
  Optional: spinoff_* and post_reorg are also "catalyst" archetypes. I measured no clinical fires for them, because each needs operating viability.

## F6. Scrubs say they zero EVERY archetype flag, but the `<name>_watch` flags survive (L9452, L9596; promises L8730-8733, L9487, L9583-9584)
- **Promise:** non-common scrub: "Zero EVERY archetype flag ... makes the flags and counts honest". The shell, ghost and corrupt-data scrubs use the same `_scrub_cols`.
- **Code:** `_scrub_cols` holds `arch_*` plus the gated scores. The `_watch` flags that `_tier()` and `_reframe()` set earlier (the surfaced previous rule, read by the elite book from archetype_tiers.csv) are not zeroed.
  - `_exceptional` and `_elite` are fine: the spirit loop recomputes them from the post-scrub core.
- **Measured:**
  - Non-common lines: 947 watch flags on 491 rows (asleep_at_wheel 249, weinstein 163, lynch_pegy 147, ...).
  - Price ghosts: 19 flags on 15 rows.
  - Clinical biotech: 1,492 flags on 834 rows.
- **Patch** (P6a, P6b):
```
old:    _scrub_cols = [c for c in arch_cols if c not in _SENIOR_OK] + _GATED_SCORES
new:    _scrub_cols = ([c for c in arch_cols if c not in _SENIOR_OK] + _GATED_SCORES
                       + [c for c in df.columns if c.endswith('_watch') and 'arch_' + c[:-6] not in _SENIOR_OK])
old:    _fund_scrub = _fund_arch + [c for c in _GATED_SCORES
new:    _fund_scrub = _fund_arch + [c for c in df.columns if c.endswith('_watch')
                                    and c != 'biotech_momentum_watch'
                                    and 'arch_' + c[:-6] not in _biotech_ok] + [c for c in _GATED_SCORES
```

## F7. BUG: `xr_family_count` / `xr_score` are counts of `arch_xr_*` flags made before the scrubs and are never re-zeroed (L9442-9451; built at L~6652/6681)
- **Promise** (L9487): "Zero every archetype flag + gated score". The truly-XR block's comment says scores derived from archetype flags must be gated at the source.
- **Code:** `_GATED_SCORES` leaves out `xr_score` and `xr_family_count`.
- **Measured:**
  - 539 rows have `xr_family_count > 0` but `archetype_count == 0`, and 21 of them still read `>= 3` (confluence level).
  - 472 of the stale rows are non-common, ghost, sub-$2M or clinical rows. Examples: `xr_score > 0` on 40 non-common lines and 252 shells.
  - Consumers: build_forensic_xr_book.py and build_truly_xr_book.py.
- **Patch** (P7):
```
old:                     'coiled_base_score'] if c in df.columns]
new:                     'coiled_base_score', 'xr_score', 'xr_family_count'] if c in df.columns]
```

## F8. Segment survivability scrub misses the hidden-engine / segment-value XR archetypes its header names, and zeroes a risk flag (L9604-9620)
- **Promise:** "a hidden-engine / segment-value thesis needs a SURVIVING company. Zero the segment archetypes for double cash-burners."
- **Code:**
  - `_segment_arch` leaves out arch_xr_hidden_segment_compounder (the hidden-engine thesis), arch_xr_segment_justifies_whole and arch_xr_margin_mixshift. Their own `_not_melting` guard is a different test.
  - It includes arch_concentrated_segments, which L9922-9924 calls "a negative risk flag" and not a thesis.
- **Measured:**
  - Double burners still firing: hidden_segment_compounder 1, segment_justifies_whole 3, margin_mixshift 5 (at most 9 fires).
  - concentrated_segments: the prior audit (review_r2_batch6) found 118 risk flags hidden by this scrub.
- **Patch** (P8):
```
old:    _segment_arch = [c for c in ['arch_geographic_global', 'arch_fastest_segment',
                         'arch_concentrated_segments', 'arch_diversified_segments',
                         'arch_reinvest_inflect'] if c in df.columns]
new:    _segment_arch = [c for c in ['arch_geographic_global', 'arch_fastest_segment',
                         'arch_diversified_segments', 'arch_reinvest_inflect',
                         # the hidden-engine / segment-value XR theses this scrub names
                         'arch_xr_hidden_segment_compounder', 'arch_xr_segment_justifies_whole',
                         'arch_xr_margin_mixshift'] if c in df.columns]
```

## F9. Non-common scrub promises "rights", but the `-RI` / CVR form is not matched (L9278)
- **Promise:** "Preferred shares, warrants, units and rights are NOT common equity".
- **Code:** the suffix set is `WT|WS|U|UN|R|RT`. CELG-RI (the Celgene contingent value right) is live and fires 9 archetypes: gayner_missed_it, lindy_margin, lindy_fcf, no_dilution, buyback_compounder, cash_quality, diversified_segments, xr_lookthrough_earner, asleep_at_wheel.
- **Patch** (P9):
```
old:        | _sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT)$')
new:        | _sym_nc.str.match(r'^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT|RI|CVR)$')
```
  The regex is anchored, so CVRX (CVRx Inc.) is not matched.

## F10. greenblatt_magic: "the core is the top decile of that combined rank" skips 218 members (L9128-9137)
- **Code:** `_crank` ranks only `_mb_base`, which requires weekly dollar volume of at least $250k. Greenblatt members below that get a NaN rank, `measured=_gb_rank.notna()` reads them as unmeasured, and they keep the absolute-cut rule.
  - Their EBIT yield and ROC are observed; only the liquidity filter makes them "unmeasured".
- **Measured:** 218 of the 698 core fires are illiquid and never face the decile test.
- **Rebuilt impact:** with the gate's own population (operating, at least $50M), the simulated core goes from 709 to 651 (about -50). 189 of the illiquid names stay because they rank in the top decile.
- **Patch** (P10):
```
old:    _gb_rank = (_crank(_greenblatt_ey) + _crank(_gb_roc)) / 2.0
        df['greenblatt_combined_rank'] = _gb_rank.round(4)
        _tier('greenblatt_magic', _crank(_gb_rank) >= 0.90, measured=_gb_rank.notna())
new:    # ranked within the listing market over the gate's own population (operating,
        # >= $50M) — _crank ranks only the liquid MB base, which left 218 illiquid
        # members unranked and passing as "unmeasured"
        _gb_pop = is_operating & (mcap >= 50e6)
        def _gb_crank(x):
            xv = pd.to_numeric(x, errors='coerce').where(_gb_pop)
            n_c = xv.notna().groupby(country).transform('sum')
            return xv.groupby(country).rank(pct=True).where(n_c >= 50, xv.rank(pct=True))
        _gb_rank = (_gb_crank(_greenblatt_ey) + _gb_crank(_gb_roc)) / 2.0
        df['greenblatt_combined_rank'] = _gb_rank.round(4)
        _tier('greenblatt_magic', _gb_crank(_gb_rank) >= 0.90, measured=_gb_rank.notna())
```

## F11. biotech_deep_value runway: missing FCF reads as "not burning" (99 years) (L8868-8873). Latent bug.
- **Promise:** "ample (99) when not burning, NaN when cash data is missing". The same comment also says "gross cash", while the code uses net cash.
- **Code:** `.where(_bdv_burn > 0, 99.0)` also sets 99 when the burn is NaN, which quietly passes the "requires enough runway" leg.
- **Measured:** 0 of 119 fires today, because the quarterly runway or a positive FCF covers every fire.
- **Patch** (P11): appends `.where(_bdv_burn.notna())` and changes the comment to "net cash ... NaN when cash or FCF data is missing". The full old/new text is in `ps4_patches.py`.

## F12. cheap_net_cash_steady_earner: the comment says 90%, the code uses 7/8 (L8017-8018 / L8024)
- **Promise:** "EPS positive in >= 90% of the last 8 quarters".
- **Code:** `>= 0.875`, which is 7 of 8.
- **Impact:** 0 fires. All 61 pass on the annual profit share.
- **Patch** (P12, comment): "else EPS positive in >= 7 of the last 8 quarters (87.5%)".

## F13. flyover coverage: the comment says "<5", the code allows 5 (L8952)
- **Promise:** "LOW analyst coverage (<5, ideally 0)" (L8947).
- **Code:** `~(n_analysts_v > 5)`.
- **Impact:** 1 fire has exactly 5 analysts and no estimate-feed count.
- **Patch** (P13): `~(n_analysts_v >= 5)`.

## F14. Micro-shell header: the comment says $1M, the code uses $2M (L9485)
- **Code:** `_mc_scrub < 2e6`. The print statement and the corrupt-price comment both say $2M.
- **Impact:** 0 (comment only).
- **Patch** (P14): "sub-$2M".

## F15. Trough archetypes: "net-cash cushion (and debt / assets) carries half of the spirit score" (L10455-10459)
- **Code:** `_DEMOTED_W = 0.50` applies to the whole demoted list. For both troughs, L10491/10493 append net debt/EBITDA and interest cover to that list. The cushion is therefore 3 of 5 demoted lenses (about 30% of the score).
- Also, `.fillna(sc)` drops the whole block when fewer than 3 of the 5 lenses are measured.
- **Impact:** spirit only. No fires change.
- **Patch** (P15) rewrites the comment to describe this. A code fix would need a separate blend for the cushion, which is a user decision because the leverage-cap weights are also a "user rule".

## F16. mb_preprofit_beats_rewarded spirit: the comment says "more ignored beats", the lens is sign -1, and it is constant (L10275-10277)
- **Code:** the gate requires `evt_ignored_beats_2y == 0`, so the lens has the same value for every member. It adds nothing to the ranking but still counts toward the "need half the lenses" rule (5 of 9).
- **Impact:** spirit only.
- **Patch** (P16): drop the lens and rewrite the comment.

## F17. PSIX `_still_low`: "the multiple" means EV/EBIT in context, but the code reads EV/sales history (L8056-8058)
- **Code:** `evh_evs_vs_med_3y` is an EV/sales measure. fmp_ev_history has no 3-year EV/EBIT median; the closest column is `evh_ev_ebit_log_chg_1y`.
- **Impact:** 0 (comment only).
- **Patch** (P17): make the comment say EV/sales and note that no EV/EBIT history exists.

## Bug noticed in passing (not a comment promise)
- **B1.** `biotech_momentum_watch` is written four times into archetype_tiers.csv (columns `.1`, `.2`, `.3`). It is in the explicit `out` list and also matched by `endswith('_watch')`, and `out[['symbol'] + _tier_cols]` then doubles the duplicate again.
- **Patch** (B1): remove `'biotech_momentum_watch',` from the explicit list at L10596. The column still reaches the tiers file through the suffix match.

## Checked and not reported
- special_situation's "viability" on the tender path is `_not_melting`, which is the file's operating-viability test.
- The `spinoff_quality` and `bottleneck` spirit lenses are present.
- The Weinstein `ts_ma30_slope13` sign of -1 matches the tier rule at L3347 (an early, flat MA).
- `ts_maxdd_5y` is negative, so the +1 sign rewards a shallower drawdown, as documented.
- Truly-XR "≥3 tells", data-quality gating, the corrupt-EBITDA and corrupt-price scrubs, `_rank2`'s country minimum of 20, and "≥ half the lenses" all match their comments.
- Missing share-count or payout data passing cheap_net_cash and PSIX: 0 fires today.

## Summary

| line (16:17 UTC) | archetype / helper | promise | status | est. fires changed |
|---|---|---|---|---|
| 10020 / 10541-10544 | spirit tiers (all) | exceptional = top quartile, elite = top 10% | NOT IMPLEMENTED (absolute 0.75/0.90 bar) | exc 12,203 → 45,453; elite 1,291 → 18,264 (or comment fix: 0) |
| 8961-8968, 10508-10543 | flyover + 18 other tiered | qualitative `_tier` exceptional kept | DEAD (overwritten) | flyover exc 76 → 503; others not measured |
| 9956-9963 + spec | tax_efficient spirit, `*_eff` | post-fill values | READS PRE-FILL | spirited 199 → 1,840; exc 22 → 191; elite 3 → 28 |
| 10329 | mb_fallen_less_than_industry_financed | equity_cagr_5y lens | BUG (commented out) | spirit only (18 core) |
| 9569-9600 | clinical scrub: special_situation, mb_biotech_financed_hiring | catalyst exempt; targets drug developers | CONTRADICTED | special_sit about +18; mb_biotech at least +68 |
| 9452, 9596 | all scrubs | zero every archetype flag | PARTIAL (`_watch` survives) | -947 / -19 / -1,492 watch flags |
| 9442-9451 | xr_score, xr_family_count | gated scores zeroed | BUG (stale) | 539 rows (472 on scrubbed lines) |
| 9604-9620 | segment survivability scrub | segment-value theses need a survivor | PARTIAL / risk flag zeroed | -9 XR; concentrated about +118 |
| 9278 | non-common scrub | rights excluded | PARTIAL (`-RI` missed) | CELG-RI, -9 flags |
| 9128-9137 | greenblatt_magic | core = top decile of combined rank | PARTIAL (218 illiquid bypass) | about -50 |
| 8868-8873 | biotech_deep_value runway | NaN when data missing | LATENT BUG | 0 |
| 8017-8024 | cheap_net_cash_steady_earner | EPS ≥ 90% of 8q | NUMBER MISMATCH (0.875) | 0 |
| 8952 | flyover | < 5 analysts | NUMBER MISMATCH (≤ 5) | -1 |
| 9485 | micro-shell scrub | sub-$1M | NUMBER MISMATCH ($2M) | 0 |
| 10455-10459 | xr_double_trough, xr_cyclical_trough | cushion = half of spirit | PARTIAL (about 30%) | spirit only |
| 10275-10277 | mb_preprofit_beats_rewarded | "more ignored beats" lens | DEAD / INVERTED | spirit only |
| 8056-8058 | psix | multiple vs own 3y median | DIFFERENT COLUMN (EV/sales) | 0 |
| 10596 | output (in passing) | — | BUG: 4x duplicate column | 0 |
