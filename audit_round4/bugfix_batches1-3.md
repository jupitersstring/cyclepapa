# BUG patches: audit round 4, batches 1-3 (2026-10-02)

Patches: `bugfix_b1.py` (`P`, 13 entries). Each `old` occurs exactly once in the current `/home/user/cyclepapa/archetype_tags.py` (mtime 16:28, byte-identical to the copy tested). The patches apply together and the result parses. The patches were NOT applied to the repo.

Method: the unpatched copy was run in `scratchpad/bf1` with the inputs symlinked. It reproduces the published `archetype_tags.csv` exactly: all 17 columns match, 0 differences. The patched copy was then run the same way. Fire counts are final, after every scrub. Examples are ordered by USD market cap.

## Already fixed in the current code (no patch)

| archetype | evidence |
|---|---|
| mb_fallen_value_accel (169) | `_mb_accel` is now date-matched: `fqx_rev_accel_now == 1`, with the annual >= 10pp only where the quarterly read is NaN. 0 current fires are decelerating. The audit's extra `~(rev_accel > 1)` guard is not added, because the 3 remaining fires with rev_accel > 1 (FIEE, ALCRB.PA, AZEV4.SA) pass on the quarterly path. That is a LOOSE base-effect issue, not this BUG. |
| tenbagger_path (1,258) | The terminal margin is now own margin + 3pp below 12%, with the 6% only for NaN margins. The comment still says "floor 10%" (cosmetic). The g10 50% cap was graded LOOSE and is untouched. |
| wolf_emerging (7) | The `_is_cannabis` classifier is in place and cannabis names are exempt from the clinical scrub. |
| financials_value (141) | The banks / insurers / thrifts industry requirement removed the closed-end funds. Of the current fires, only HUW.L, UTGN and WDH have equity/assets above 0.5, and all three are insurers. No funds or trusts remain. |
| gayner_missed_it (183) | The per-share growth is annualised (`_g_ann5`), and the drawdown leg requires r52 <= 0.20. |
| tax_efficient (1,952) | The FMP-filled ETR is written back to `df` (L10013), so 1,845 fires carry a spirit score. The loss-history/NOL guard was graded LOOSE and is not patched. |
| evsales_derating (957) | The floor reads `revenue_3y_cagr`. Two LOOSE issues remain: a measured EV/S rise of 0-20% still passes, and EV-history artefacts are not clipped. |

## Patched

| archetype | change | fires | removed (examples) | added |
|---|---|---|---|---|
| oak_nav_discount | Excludes `reit` industries ("investment trust" matched Equity REITs). Adds `_book_twin_bad`: a line whose P/B is < 1/3 of the most-traded same-name line's P/B. Ignores p_tb below 0.98 x pb, which is impossible. | 95 → 62 | BXDIF (pb 0.15 vs BAM 10.0), PRS / SFB / MGR / MGRB / MGRE (notes), INL.JO (p_tb 0.03 on pb 1.01), TRGYO.IS, Fibra Danhos, ARI (REITs) | none |
| xr_look_through_value | Adds the same `~_book_twin_bad` | 34 → 33 | CCZ (Comcast ZONES, pb 0.17 vs CMCSA 1.0) | none |
| xr_segment_justifies_whole | The best segment is scaled by group EBIT (op margin x USD revenue) / segment total, capped at 1. Group EBIT must be > 0. | 70 → 16 | ELV, INTU, DAL, HPQ, GIS (12x fails once overhead is charged), CRC and XRAY (group EBIT < 0) | none. Kept: LULU, EDU, PPC, GNTX, TRN, DXC |
| bab_becoming | Requires `ts_beta_1y > 0`, 1-year rank `_b1 <= 0.50` (below the market median) and `_bab_liquid` | 2,770 → 821 | NVDA (1y rank 0.83), AAPL (0.65), TSFA.F, TSLA, CVX (1y beta -0.78) | none. Kept: LLY, WMT, COST, TMUS, UNP |
| cannibal_at_discount | Veto when any present count lens shows growth: `~(fq_shares_yoy > 0) & ~(shares_yoy > 0)`, NaN neutral. The noisy FY-diluted lens is not used. | 681 → 531 | DNZOF (shares_yoy 941), POSCO (quarterly +9.4%), BCE, Renault (+10%), Sainsbury, ODTech 080520.KQ (+6.2%) | none. Mercedes and KHC are kept. |
| expensed_growth_value | The spend is measured directly: (fq SG&A + R&D) / revenue, required to be present and at or above its industry median among operating names | 217 → 99 | SAIL.NS, Babcock, JD Sports (3 lines), Leroy Seafood; POLYSPIN / ZUC / NPI / MUL (cash cows, no spend read) | none. Kept: Liberty Global, Amorepacific, Resorttrust |
| xr_floor_inflection | The hidden leg counts only where `investments_associates > 0`. The acceleration route requires `rev_yoy > 0`. | 698 → 505 | JD Health, Tsingtao (2 lines), Vipshop, 3SBio (net cash 43-48% via the hidden fallback) | none |
| xr_growth_capex_masked | capex/D&A = min(panel, level) where both exist. The level maintenance yield is used only where the panel is missing, the level D&A is missing, or the two ratios agree within 2x; otherwise the currency-free panel yield is used. The FCF yield is NaN-preserving. | 23 → 23 | MELI.BA, 1742.HK, 9998.HK, 5OC.SI | ASEHN.MX, TNABF, RJET, SKLT.JK. These pass on the currency-free yield: their level yield was negative while the panel ratio disagreed more than 2x. Worth a look after the D&A currency fix. |
| liger_asset_backed | Both net-cash legs use `net_cash_pct_sane`, so net cash above 100% of mcap no longer counts. | 1,277 → 954 | All 323 removed are > 100% net cash: ATPC, Z Holdings 042420.KQ, BOE Varitronix (2 lines), Cross-Harbour | none |
| negative_ev_value | No gate change. Net cash / mcap is added as a demoted spirit weight. Leverage is a weight under the house rule, so the audit's "net cash >= 0 on the P/B branch" is not used. | 4,691 → 4,691 | none | none (ranking only; the top 5 barely move) |

Knock-on effects:
- forensic_payout_confirmed 3,514 → 3,500 (-14). These names drop alongside the expensed_growth_value removals (Leroy Seafood, SES, istyle).
- xr_confluence 898 → 892 (-6), from the floor_inflection removals.
- No other column changed.

## Dependencies on the pending data-layer fixes

- negative_ev_value: the BUG half is the stale `cash_gt_ev_flag` (471 contradicted rows). It is left to the data-layer fix.
- xr_growth_capex_masked: the D&A currency fix will change the level lens and may retire the 4 additions.
- `_book_twin_bad` is an archetype-local guard. The shared senior-security scrub still misses CCZ, SFB, PRS, TBB, NCRRP and MGR*, whose share count differs from the common's. A data-layer fix there would make the guard redundant.
- Duplicate lines (secondary-listing dedupe) remain in every count above.
