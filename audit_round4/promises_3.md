# Promise sweep 3: comments vs code, archetype_tags.py (brief's lines 5300-8000)

## Scope and method

- **The file changed while I worked.** At 16:08 it grew from 10,533 to 10,613 lines: 33 lines were inserted near line 1129, which makes `data_quality_flag` available early. A later edit added senior-security code after line 8280. Nothing inside the reviewed block changed. **Line numbers below are for the current file.** The brief's 5300-8000 is now about 5333-8033. A snapshot is at `scratchpad/ps3_snapshot_1608.py`.
- **How impact was measured.** I never ran `compute()`. Gate legs were rebuilt from `asymmetry_global.csv`, the published `archetype_tags.csv` and the overlay files, read with usecols. The scripts are `ps3_load.py`, `ps3_mb.py`, `ps3_misc.py`, `ps3_more.py` and `ps3_vu.py`.
  - "Fires" are the published `arch_` flags, taken after the scrubs.
  - Where a leg needed `_mb_base` / `_crank`, I rebuilt it. The rebuild matches every published fire, plus 5-10% extra rows that the later scrubs remove. Additions are therefore given as pre-scrub upper bounds.
- **Validation.** All 26 patch strings occur exactly once in the current file. Applied together to a scratch copy, the file compiles with `py_compile`. The scratch copy has been deleted, and the patches are kept in `scratchpad/ps3_patches.py`.
- **Process slip.** I ran one read-only `git log -1` by mistake; its output was discarded. Nothing in the repo was written.

---

## A. Promise not implemented (code changes)

### F1. L7570-7572 / 7585: `arch_mb_fallen_value_accel`, `_accel_now` not used
- **Promise (L7570):** "acceleration date-matched where the quarterly shape exists (audit 3: rev_accel's annual fallback is a different horizon)".
- **Code:** `_accel_now` is built at L7571, but it is only used in `_mb_trough`. `_mb_accel` (L7572) still reads the annual `rev_accel >= 0.10`.
- **Impact:** 51 of the 114 fires have `fqx_rev_accel_now == 0`, so the date-matched series says they are decelerating; all 51 would drop. About 118 names would be added (pre-scrub) where the quarterly shape says accelerating but annual `rev_accel` is below 0.10. If you prefer a veto-only variant, keep the annual threshold and veto `fqx == 0`: 70 fires remain (-51, no additions).
- **Patch:**
```
old:    _mb_accel = ((rev_accel >= 0.10) & (_ncol('fq_rev_growth') >= 0)).fillna(False)   # accelerating AND not shrinking
new:    _mb_accel = ((((_ncol('fqx_rev_accel_now') == 1)                                   # date-matched where the quarterly shape exists,
                       | (_ncol('fqx_rev_accel_now').isna() & (rev_accel >= 0.10)))         # the annual >= 10pp only where it does not
                      & (_ncol('fq_rev_growth') >= 0)).fillna(False))                       # accelerating AND not shrinking
```

### F2. L6752-6761: `arch_tenbagger_path` terminal margin
- **Promise:** "floor 10%, cap 22%", and "a name below the old 12% floor is modelled at its own (after-tax) margin plus a modest expansion, so the arithmetic can actually fail".
- **Code:** `max(op*0.75, ebitda*0.4875, 0.06).clip(0.06, 0.22)`.
  - Every name below 8% op margin, loss-makers included, gets a flat 6%.
  - The 6% floor also contradicts the comment's "10%".
- **Impact:** 673 of the 1,202 core fires sit on the 6% floor, 30 of them loss-makers. With own margin + 3pp (cap 12%, floor 0), `tenbagger_implied_return` falls below 10x for 37 core fires (-37), and `tenbagger_credible` loses 8. NaN margins keep 6%.
- **Caveat:** with this patch the pre-profit route (gross margin >= 40% plus an FCF inflection, L6787-6789) can only fire on names whose own margin is positive.
- **Patch:** also change the comment's "floor 10%" to "floor: own margin + 3pp below 12%".
```
old:    term_margin = pd.concat([
            _num('op_margin') * 0.75,
            _ebm * 0.65 * 0.75,                             # EBITDA scaled to a net proxy, after tax
            pd.Series(0.06, index=df.index),
        ], axis=1).max(axis=1).clip(0.06, 0.22)
new:    _own_nm = pd.concat([
            _num('op_margin') * 0.75,
            _ebm * 0.65 * 0.75,                             # EBITDA scaled to a net proxy, after tax
        ], axis=1).max(axis=1)
        term_margin = (_own_nm.where(_own_nm >= 0.12,                      # at/above the old 12% floor: own margin (cap 22%)
                                     (_own_nm + 0.03).clip(0.0, 0.12))     # below it: own margin + 3pp expansion, never above 12%
                       .clip(upper=0.22).fillna(0.06))                     # margin unmeasured: the 6% placeholder as before
```

### F3. L7807-7818: `arch_mb_compounder_insiders_at_high`, "recent quarters NOT beating" missing
- **Promise:** "insiders buying — and the recent quarters NOT beating (expectations not yet set)". The study's leaves use `beats_4q LOW` (MULTIBAGGER_OPERATORS.md L1159-1277).
- **Code:** has no beat leg.
- **Impact:**
  - 28 of 39 fires are beating: beat share over 8 quarters >= 0.6 or 4-quarter surprise >= 5%. Examples are QLYS, PCTY, PAYC, DXCM, NTAP, GILD, ASML.AS and ROK. Result: **-28**.
  - Separately, 37 of 39 fires pass on `_corp_conviction` (buybacks), not `_ins_2q` (insiders). The (audit 4) inline comment endorses that, but the header says "insiders buying".
- **Column choice:** `evt_beats_4q` does not exist. The closest columns are `evt_beat_share_8q` and `evt_surprise_4q`, which fall back to `esb_*`. NaN reads as not beating.
```
old:        & _rd_heavy & (_ins_2q | _corp_conviction)).astype(int)
new:        & _rd_heavy & (_ins_2q | _corp_conviction)
            & ~((_ncol('evt_beat_share_8q') >= 0.6) | (_ncol('evt_surprise_4q') >= 0.05)).fillna(False)).astype(int)
```

### F4. L7755-7776: `arch_mb_leader_in_wave`, "margins and returns rising, R&D-heavy"
- **Promise:** "heavily covered, volatile, the PRICE AHEAD of sales…, margins and returns rising, R&D-heavy, in an industry whose own tape is up … Core adds the industry-relative position and acceleration".
- **Code:** gates margins, coverage, volatility, price-ahead, growth, acceleration and industry tape. There is no returns leg and no R&D leg.
- **Impact:** 28 of 35 fires fail R&D-heavy (R&D/revenue >= 8% or the FMP R&D-intensive flag); 2 fail returns rising. Either leg, or both: **-28**.
- **Decision:** this is large enough that you may prefer to reword the comment, e.g. "R&D-heavy is a rank lens".
```
old:        & (df['rel_ind_dist_hi260'] >= 0.70).fillna(False)).astype(int)
new:        & (df['rel_ind_dist_hi260'] >= 0.70).fillna(False)
            & _mb_roic_up                                                                   # returns rising
            & ((_ncol('fmp_rd_to_revenue') >= 0.08) | (_ncol('fmp_rd_intensive_flag') == 1)).fillna(False)).astype(int)   # R&D-heavy
```

### F5. L7819-7831: `arch_mb_hiring_beating_uncovered`, "EV/sales already rising, new 13F holders"
- **Code:** neither leg is present.
- **Impact:**
  - **EV/sales:** 15 of 49 fires have EV/S falling in the dated series (`evh_evs_log_chg_1y < 0`); 5 have no data. Result: -15.
  - **13F:** 44 of 49 fires have no 13F data, because 13F covers US listings only. Gating on it would remove almost all fires, so only the EV/S leg is proposed.
```
old:        & _hi260.between(0.35, 0.80).fillna(False)).astype(int)
new:        & _hi260.between(0.35, 0.80).fillna(False)
            & ~(_ncol('evh_evs_log_chg_1y') < 0)).astype(int)   # EV/sales already rising (not falling where the dated series measures it)
```

### F6. L7736 / 7747: `arch_mb_wave_neglected_value_accel`, frame read from the country
- **Promise:** "The condition is the peer group's tape, not the country."
- **Code:** `(mkt_tape_dist_hi260 <= 0.65) | (ind_tape_dist_hi260 <= 0.65)`, which is the country OR the industry.
- **Impact:** 14 of 470 fires pass only through the country leg, so **-14**. Note that the industry leg alone still passes 95% of the base; prior audit batch 1 flagged this leg as close to a no-op.
```
old:    _depressed_frame = ((df['mkt_tape_dist_hi260'] <= 0.65) | (df['ind_tape_dist_hi260'] <= 0.65)).fillna(False)
new:    _depressed_frame = (df['ind_tape_dist_hi260'] <= 0.65).fillna(False)   # the PEER group's tape, not the country's
```

### F7. L7590-7595: `_ins_2q` fallback (`mb_fallen_insider`; also used in smart_money and compounder)
- **Promise:** "SEC quarterly statistics where they exist, the EDGAR cluster-buy / distinct-buyer flags otherwise".
- **Code:** the fallback is distinct buyers OR `fmp_insider_net_usd_12m > 0`, i.e. one net purchase. The cluster flag is not used.
- **Conflict:** the (audit 4) comment at L7818 calls the net-dollar record intended, so the two comments disagree. Resolve one way or the other.
- **Impact:** **-1 / +0** (`fmp_insider_net_usd_12m` is 99.5% NaN).
```
old:                  & ((_ncol('insider_distinct_buyers') >= 2) | (_ncol('fmp_insider_net_usd_12m') > 0)))).fillna(False)
new:                  & ((_ncol('insider_distinct_buyers') >= 2) | (_ncol('insider_cluster_buy_flag') > 0)))).fillna(False)
```

### F8. L7174-7211: `arch_analyst_awakening` and `arch_analyst_rerating_confirmed`, conviction from one lens
- **Promise:** "fire needs rating AND one other" (L7176-7178), and "fire on ANY 2-of-available conviction lenses" (L7189-7190).
- **Code:** after audit 3 removed the coverage lens, `_confirm` has 2 lenses and `conv_score >= 0.5`. That means 1 of 2 suffices: rating <= 2.2 alone, or upside >= 25% alone. `_rating_present` (<= 3.0) does not restore the "AND".
- **Impact:**
  - Awakening: **755 of 1,656** fires rest on a single lens (650 rating only, 105 upside only) without two sentiment-turn lenses. All would drop.
  - Re-rating confirmed: **56 of 76** would drop.
- **Decision:** if the 1-of-2 behaviour is intended after audit 3, fix both comments instead.
```
old:    _conviction = (conv_any & (conv_score >= 0.5)) | (_sent_turn_n >= 2)
new:    _conviction = (conv_any & (conv_score >= 1.0)) | (_sent_turn_n >= 2)   # every OBSERVED level lens agrees (rating AND upside where both exist)
```

### F9. L6497-6498 / 6535-6537: `_not_rich_au` (`asleep_unrerated`, `xr_audited_streak_unrerated`), "missing = permissive" is dead (BUG)
- **Promise:** "missing = permissive, per breadth doctrine — richness unknown is not richness".
- **Code:** `ev_ebitda_v = s('ev_ebitda', 99.0)` is never NaN, so `(_pe_au.isna() & ev_ebitda_v.isna())` is always False. A name with no P/E and no EV/EBITDA fails as "rich".
- **Impact:** 338 `asleep_at_wheel` fires have both missing; 157 of them also show >= 2 no-rerate lenses. That is **up to +157** for `asleep_unrerated`, before `_not_melting` and `_tier`. `xr_audited_streak_unrerated` also gains some, not counted.
```
old:                    | (_pe_au.isna() & ev_ebitda_v.isna()))
new:                    | (_pe_au.isna() & _num('ev_ebitda').isna()))   # ev_ebitda_v is 99-filled and never NaN
```

### F10. L5917 and L5945: `arch_xr_value_unlock` / `value_unlock_confirmed`, the forensic-hidden-value leg is dead (BUG)
- **Promise:** a "hidden forensic value" leg in the cheapness test (`_vu_cheap`), and "large hidden value" as forensic confirmation (`_vu_forensic`).
- **Code:** `s('forensic_hidden_pct', 0)` reads a column that is first created at L9608 and is not in the master. It is 0 everywhere, so both legs never fire.
- **Impact:**
  - 32 of the 199 value-unlock members have published `forensic_hidden_pct >= 0.25` and are not confirmed: **+32 confirmed**.
  - Up to **+117 members** through the cheap leg (upper bound, before `_fx_coherent` / `_not_melting`).
- **Column choice:** `forensic_hidden_pct` does not exist yet at this point. The closest available measure is `_hidden_pct` (associates at carrying value plus net cash), the main term of the later ledger. Alternatively, move the ledger block (around L9560-9608) above L5899.
```
old:        | (s('forensic_hidden_pct', 0) >= 0.20)                       # hidden forensic value
new:        | (_hidden_pct.where(_fx_coherent) >= 0.20)                   # hidden forensic value (forensic_hidden_pct is built only after this block)
old:        | (s('forensic_hidden_pct', 0) >= 0.25)                        # large hidden value
new:        | (_hidden_pct.where(_fx_coherent) >= 0.25)                    # large hidden value (forensic_hidden_pct is built only after this block)
```

### F11. L5829, 6292, 6323, 6668, 6889: wrong column, the sparse `rev_3y_cagr` (BUG)
- **Promises:**
  - L5829 (`xr_peer_margin_gap`): "not in secular decline".
  - L6889 (`evsales_derating`): "HARD positive top-line floor".
  - L6292 / 6323 (`cheap_sales_scaler`, `exceptional_evsg`): a >100% YoY "must be corroborated by a durable 3y CAGR".
  - L6668: the A5 secular-decline downweight.
- **Code:** reads `rev_3y_cagr`, which has 2,311 non-NaN rows (5%). The filled `revenue_3y_cagr` has 33,708 rows on the same scale (identical where both exist, median absolute difference 4e-9). For 95% of names the floors therefore pass vacuously and the corroboration route is unavailable.
- **Impact:**
  - `evsales_derating`: **-64** of 1,015.
  - `xr_peer_margin_gap`: **-232** of 993.
  - Scaler / EVSG: 584 rows have rev_yoy > 1 and a filled 3y CAGR >= 15%. Adds are bounded by those 584; most fail other legs.
  - `xr_confidence`: score only.
- **Outside the range:** the same bug sits at L4183, 4311, 5049 and 5104.
```
old:        & ~(_ncol('rev_3y_cagr') < -0.05)                    # not in secular decline
new:        & ~(_ncol('revenue_3y_cagr') < -0.05)                # not in secular decline
old:        ((rev_yoy_c <= 1.0) | (_ncol('rev_3y_cagr') >= 0.15)) &  # (non-XR review)
new:        ((rev_yoy_c <= 1.0) | (_ncol('revenue_3y_cagr') >= 0.15)) &  # (non-XR review)
old:        ((_ncol('fq_rev_growth').fillna(rev_yoy_c) <= 1.0) | (_ncol('rev_3y_cagr') >= 0.15)) &  # (deep-audit)
new:        ((_ncol('fq_rev_growth').fillna(rev_yoy_c) <= 1.0) | (_ncol('revenue_3y_cagr') >= 0.15)) &  # (deep-audit)
old:    _secular_decline = (_ncol('rev_3y_cagr') < -0.03)
new:    _secular_decline = (_ncol('revenue_3y_cagr') < -0.03)
old:        (rev_yoy_c >= 0.15) & ~(_ncol('rev_3y_cagr') < 0) &  # (deep-audit) HARD positive top-line floor.
new:        (rev_yoy_c >= 0.15) & ~(_ncol('revenue_3y_cagr') < 0) &  # (deep-audit) HARD positive top-line floor.
```

### F12. L5473-5501: `arch_xr_hidden_segment_compounder`, "a genuinely PROFITABLE engine" not checked
- **Code:** the inflection legs test only a margin delta, a flag or operating leverage. Nothing checks the segment's margin level.
- **Impact:** 5 of 38 fires have `fastest_seg_opmargin <= 0` (column from `edgar_segment_signals`); 3 have no data. Result: **-5**.
```
old:        & (_ncol('fastest_segment_share') <= 0.60)          # still HIDDEN — not yet the whole (consolidated masks it)
new:        & (_ncol('fastest_segment_share') <= 0.60)          # still HIDDEN — not yet the whole (consolidated masks it)
            & ~(_ncol('fastest_seg_opmargin') <= 0)             # a PROFITABLE engine where the segment margin is disclosed
```

### F13. L5329-5337: `arch_xr_growth_capex_masked`, Greenwald growth capex
- **Promise:** "the capex attributable to the revenue INCREASE (prior capex-intensity x revenue growth)".
- **Code:** current intensity × g × current revenue. That overstates the increase by a factor of (1+g), and uses the current, not the prior, intensity.
- **Column note:** a TTM prior capex intensity does not exist. `fq_capex_p` is quarterly only, so the patch keeps the current intensity.
- **Impact:** **-1** of 24 (22 rebuilt on the level path).
```
old:    _growth_cx31 = (_cap_int31 * (rev_yoy_c.clip(lower=0) * _rev_loc)).where(_cap_int31.notna())
new:    _growth_cx31 = (_cap_int31 * (_rev_loc - _rev_loc / (1.0 + rev_yoy_c.clip(lower=0)))).where(_cap_int31.notna())   # x the revenue INCREASE (not g x current revenue)
```

### F14. L7894-7906: `arch_mb_growth_past_capex_peak`, "two-year revenue growth"
- **Code:** uses the 3y CAGR (`fmp_st_revenue_3y_cagr`) with a fallback to an up-to-8-year CAGR. The panel's two-year growth, `bs_rev_g_2y`, exists and covers 79% of the base.
- **Impact:** **-11 / +9**, pre-scrub (rebuild 91 vs 81 published).
```
old:    _g2 = _ncol('fmp_st_revenue_3y_cagr').where(_ncol('fmp_st_revenue_3y_cagr').notna(), _ncol('fmp_st_revenue_cagr'))
new:    _g2 = _ncol('bs_rev_g_2y').fillna((1.0 + _ncol('fmp_st_revenue_3y_cagr').where(_ncol('fmp_st_revenue_3y_cagr').notna(),
                                                                                        _ncol('fmp_st_revenue_cagr'))) ** 2 - 1.0)   # TWO-year growth (panel), CAGR-implied 2y as fallback
```

### F15. L7493-7496: `arch_coiled_base` (and ignition / fallen angels), "clean data"
- **Code:** `_cb_valid` has no data-quality leg. `data_quality_flag` is now built early (L1134), so the leg can be added.
- **Impact:** **0** today (no current fire has the flag set); this is a latent gap.
```
old:    _cb_valid = (is_operating & (_num('bs_med_dvol26') >= 250_000)
                     & (_num('revenue_ttm_usd') >= 10e6)).fillna(False)
new:    _cb_valid = (is_operating & (_num('bs_med_dvol26') >= 250_000)
                     & (_num('revenue_ttm_usd') >= 10e6)
                     & ~(_ncol('data_quality_flag') == 1)).fillna(False)
```

## B. Comment disagrees with code where the code is the intended rule (comment patches, 0 fires)

### F16. L6025-6030: `arch_forensic_payout_confirmed`, "earns an EXTRA archetype count … native ranking boost"
- **Code:** the flag is in `_NOT_COUNTED` (L9813-9814), so it adds nothing to `archetype_count`. It fires on 3,579 names.
- **Options:** fix the comment (below), or drop it from `_NOT_COUNTED`. The second would add +1 count to 3,579 names.
```
old:    # or paying a dividend — earns an EXTRA archetype count, which is this
        # system's native ranking boost (archetype density feeds ETA and the
        # convergence score). Revealed preference: management monetising the
new:    # or paying a dividend — is flagged as a SURFACED confirmation. It is in
        # _NOT_COUNTED, so it adds NO archetype count / density (it would double-
        # count its forensic parent). Revealed preference: management monetising the
```

### F17. L6067-6071: `arch_oak_order_conversion`, "> 20% of revenue" vs the flag's ">= 10%"
- **Comment:** "signed orders / deposits > 20% of revenue", yet the same comment then says "prepayments >= 10%".
- **Code:** `fq_defrev_build_flag` uses `fq_defrev_to_rev >= 0.10` (L810-812).
- **Impact:** 62 of 122 fires are in the 10-20% band.
- **Options:** the comment patch below (0 fires), or enforce 20% with `& (_ncol('fq_defrev_to_rev') >= 0.20)` (-62).
```
old:    # (audit 3) the FORWARD BOOK is the thesis (signed orders / deposits > 20%
        # of revenue): the core requires the deferred-revenue build (prepayments
new:    # (audit 3) the FORWARD BOOK is the thesis (signed orders / deposits >= 10%
        # of revenue): the core requires the deferred-revenue build (prepayments
```

### F18. L5432 vs L5446: `arch_xr_monetization_trifecta`, NOL size
- **Header:** "NOL tax shield >= 30% of market cap".
- **Code:** NOL/mcap >= 0.50, about 10.5% in tax value. The inline comment matches the code.
```
old:    #  (b) a monetizable NOL tax shield >= 30% of market cap (future earnings
new:    #  (b) a monetizable NOL >= 50% of market cap (~10% in tax value; future earnings
```

### F19. L5798-5799 vs L5819-5820: `arch_xr_peer_margin_gap`, turn signal
- **Header:** promises "or a fresh capital-return / insider-buy corroboration".
- **Code:** since audit 3, `_turn_x46` is margin-only, with no capital-return or insider leg.
```
old:    # mix, pre-self-help). We admit it only WITH a turn signal (margin delta up,
        # or a fresh capital-return / insider-buy corroboration) and a cheap multiple,
new:    # mix, pre-self-help). We admit it only WITH an observed margin turn (op or
        # gross margin up >= 1pp, TTM EBIT growing, or a dated inflection) and a cheap multiple,
```

### F20. L6230-6231: `levered_stub_tier`, "2 = 4-8 (core)"
- **Conflict:** this contradicts `_tier("levered_inflection", nde 1.5-3)` at L6229, whose (audit 4) comment says the 1.5-3x band is the core. The tier column only.
```
old:    # zero: 1 = nde <= 4, 2 = 4-8 (core), 3 = 8-30 (speculative, not core)
new:    # zero: 1 = nde <= 4, 2 = 4-8, 3 = 8-30 (speculative); the levered_inflection
        # CORE is nde 1.5-3x (the _tier above), not tier 2
```

### F21. L7991-7992 / 7996-7998: `coiled_base_score`, "counts over their leg totals"
- **Code:** divides by 3, 2 and 3, but each family has 5 legs, so the counts saturate. This affects ranking only.
```
old:    # 0.30x). Components are unit-scaled to [0, 1] by construction (counts
        # over their leg totals, depth over a 3x coil).
new:    # 0.30x). Components are clipped to [0, 1]: counts SATURATE (coil 3 of 5
        # legs, perception 2 of 5, ignition 3 of 5), depth over a 3x coil.
```

## C. Checked and not reported

These match their comments, or the gap has no live effect:

- **No live units mix:** XR32/XR44/XR45 divide EDGAR levels by the USD mcap, but all EDGAR rows carrying these columns are USD-listed (0 non-USD rows). A latent risk only.
- **Match their comments:** XR41/42/43/47/48, Weschler, asymmetric assembly, the NOL band, pre_rerating, the F6 payout guard, insider_conviction, scaler/EVSG/growth_algo guards, Templeton, the Lynch gates, institutional accumulation, the sentiment flags, the `_ign_n` family count, `_fallen_ctx`, tree recipe thresholds, U1-U3, U5-U6, C7-C9 ("covered" means covered by the archetype population, not by analysts) and the user archetypes.
- **Dead or minor, left out:**
  - `asleep_score` assigned twice (L6466, overwritten at L6483): dead but harmless.
  - `_nc_q` uses `fq_total_debt.fillna(0)`: 0 rows affected (see batch 1).
- **Stale history comments where the code matches the "now":** L6413-6414 asleep "EITHER … EPS" and L6370-6371 growth_algo "soft bonus". Not reported.

## Summary

| line | archetype | promise | status | est. fires changed |
|---|---|---|---|---|
| 7570-7572 | mb_fallen_value_accel | date-matched acceleration (`_accel_now`) | not wired | -51 / +~110 |
| 6752-6761 | tenbagger_path | own margin + modest expansion; floor 10% | flat 6% floor | -37 core (-8 credible) |
| 7812-7818 | mb_compounder_insiders_at_high | recent quarters NOT beating | missing | -28 of 39 |
| 7758-7776 | mb_leader_in_wave | returns rising, R&D-heavy | missing | -28 of 35 (or reword) |
| 7822-7831 | mb_hiring_beating_uncovered | EV/S rising, new 13F | missing | -15 (EV/S leg only) |
| 7736-7747 | mb_wave_neglected_value_accel | peer tape, not country | country leg kept | -14 |
| 7590-7595 | mb_fallen_insider (`_ins_2q`) | cluster-buy fallback | net-USD instead | -1 |
| 7176-7211 | analyst_awakening / rerating_confirmed | rating AND another lens | 1-of-2 | -755 / -56 |
| 6497, 6537 | asleep_unrerated | missing = permissive | dead leg (BUG) | up to +157 |
| 5917, 5945 | xr_value_unlock / confirmed | hidden forensic value legs | dead column (BUG) | up to +117 / +32 |
| 5829, 6292, 6323, 6668, 6889 | peer_margin_gap, evsales_derating, scaler, evsg, xr_conf | 3y CAGR floors and guards | 5%-covered column (BUG) | -232, -64, adds ≤584 |
| 5475-5501 | xr_hidden_segment_compounder | profitable engine | margin level unchecked | -5 |
| 5329-5337 | xr_growth_capex_masked | capex × revenue INCREASE | g × current revenue | -1 |
| 7894-7906 | mb_growth_past_capex_peak | two-year growth | 3y CAGR | -11 / +9 |
| 7493-7496 | coiled_base family | clean data | no DQ leg | 0 (latent) |
| 6025-6030 | forensic_payout_confirmed | extra archetype count | in `_NOT_COUNTED` | 0 (comment) |
| 6067-6071 | oak_order_conversion | deposits > 20% | flag uses 10% | 0 (comment) or -62 |
| 5432 | xr_monetization_trifecta | NOL >= 30% | code 50% | 0 (comment) |
| 5798-5799 | xr_peer_margin_gap | capital-return / insider turn | margin-only | 0 (comment) |
| 6230-6231 | levered_stub_tier | tier 2 = core | core is 1.5-3x | 0 (comment) |
| 7991-7992 | coiled_base_score | counts over leg totals | saturating /3, /2, /3 | 0 (rank only) |
