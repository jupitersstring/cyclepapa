# BUG fixes, audit round 4 batches 6-8 (prepared 2026-10-02, not applied)

Patches: `bugfix_b3.py` (16 `(id, old, new)` entries). Each `old` occurs exactly once in the current `/home/user/cyclepapa/archetype_tags.py`. Together they apply cleanly and the result parses.

Test: the current file was run unmodified from `scratchpad/bf3` with the read-only inputs symlinked. The instrumented copy returns before the CSV writes. All arch_* columns reproduce the published `archetype_tags.csv` exactly (0 differing rows). It was then re-run with the patches applied. The fire counts below are before -> after.

## Already fixed in the current code (no patch)

| archetype | evidence |
|---|---|
| concentrated_segments | Removed from the cash-burner `_segment_arch` scrub. Published fires 568 -> 650. |
| roic_inflect | The cash-ROIC cross is no longer a standalone path. Fires 1,079 -> 484. Nintendo, Lenovo and Transcend are out. VRTX remains because it is a genuine accounting cross after the FY24 IPR&D loss year. |
| cundill_deep_value | `_c_nodef` = tc_opinc_pos / tc_years. Fires 296 -> 455. CMCSA now fires; KEP (0.375) does not. |
| mb_biotech_financed_hiring | Now in `_biotech_ok`. Fires 48 -> 157. The relative 13F test below moves it to 146: RLAY, BCRX and EDIT lose the "committed" leg that rested on 1+ new 13F holder. |

## Fixed at source by the data-layer patch (no archetype change needed)

| archetype | note |
|---|---|
| buyback_compounder (1,162 -> 1,162) | Dead listings with no market cap (FLIR, SWMA.ST, EVTN). |
| capital_light_pivot (2,104 -> 2,104) | Dead listings (EVTN, CLCN). |
| xr_paydown_yield (446 -> 446) | Financing cash flow left in the home currency (TLK, PTGCF). `nde >= 1` was not added because the user rule says "debt exists, no fixed band". |

## Patched

| archetype | status | change | fires | named examples |
|---|---|---|---|---|
| narrative_lag | BUG, open | The relative-strength and ignored-beats lenses count only beside an anchored horizon. `_adv_shock` had already been restored. | 4,081 -> 2,841 | Out: AAPL, Samsung BC94.L, JNJ, Tencent (3 lines), KO (all extent 0). Kept: UNH, Roche, Ryanair |
| liger_neglected_survivor | BUG, open | The core uses the domain-checked `_fqx_inc` (<= 1) and requires `fq_rev_growth > 0`. NaN coverage is left to the data-layer sharing of coverage across lines. | 1,018 -> 892 | Out: 1858.HK, VSTIND.NS. Kept: Nippon Rietec 1938.T, Lanpec 601798.SS |
| pension_overfunded | BUG, open | Funded status counts only when it is the direct concept, or when plan assets and PBO share the same end date. Either must be dated <= 730 days old (dates read from `edgar_universe_facts.csv`). | 5 -> 1 | Out: WY, CAL, SCHL, MAGN. Kept: DXC |
| special_situation | BUG, partly open (biotech exemption done) | EDGAR merger/tender flags need a dated anchor inside the file's 270-day window. For tenders the anchor must be third-party (TO-T/14D9, which drops issuer TO-I). SPAC, BDC and fund vehicles are excluded. | 325 -> 190 | Out: BMY, OXY, JAZZ, RPRX, LEN, ZTO, FWONA, SPACs, FSK. Lost: NSC, EA and KVUE (genuine deals older than 270 days). Still in: MDT, GLAXF, BIIB, DVN. Full role separation needs filer-versus-subject information in `edgar_event_signals.py`. |
| xr_harvest_distribution | BUG at source + guard | `_dna_sane` (D&A <= EBITDA and <= revenue). Observed `rev_yoy >= -5%`. Buyback yield filled from `fmp_st_buyback_yield_y0`. | 153 -> 92 (-66 +5) | Out: ASEKY, KAIKY, DNZOY, ELRNF. New: DUE.DE, SIMH3.SA |
| xr_amortization_mask | BUG at source + guard | `_dna_sane`. | 95 -> 69 | Out: SNEJF, BMBOY, SCMN.SW (D&A 4.69B > EBITDA 4.32B). Kept: CARS-type acquirers, SN.L, BNZL.L |
| overdepreciated_assets | BUG at source + guard | `_dna_sane`. Reads `revenue_3y_cagr` instead of the 95%-NaN `rev_3y_cagr`. | 469 -> 196 | Out: CTM.F, VOW.DE (D&A 39.5B > EBITDA 19.3B), 1455.HK (3-year revenue -23%). Kept: 4502.T, Kingboard KGX.DE |
| discounted_vehicle | BUG at source + guard | The stale-flag leg also requires measured net cash > 0. The > 100% cap was already in place. | 1,179 -> 1,161 | Out: GEA.WA, 9923.HK, DH. Kept: 035250.KS, 1060.HK |
| hidden_assets | BUG, open (P/B <= 1 already fixed) | A disclosed stake (associates or equity-method investments) must be >= 10% of mcap. NaN no longer passes. | 1,397 -> 21 | Out: COSCO (CICOY/601919.SS), 0762.HK, plain net-cash piles. Kept: TDS, Weibo (WB/WEIBF), PPLI. The cap is TIGHT by data until a global long-term-investments fill exists. CCZ (Comcast ZONES) is a non-common leak handled by the data layer. |
| mb_smart_money_wreckage | BUG, open | `_inst_arrival` = new 13F holders as a share of all holders, top quintile of the 13F market, holders >= 15. This shares out at 19.5% of the base, against 96% before. | 235 -> 155 | Out: MOS, KD, RUN, OLN, WHR. Kept: JD, CNXC, HUN, DXC |
| mb_preprofit_freefall_informed | BUG, open | The same relative `_inst_arrival`. | 682 -> 604 | Out: EL, SMCI, U, NIO. Kept: RBLX, RIVN. The LOOSE "pre-profit = op < 0" was not changed. |
| nol_shell | BUG at source + guard | Section 382 guard `~(shares_yoy > 0.05)`, the sibling xr_monetization_trifecta's rule. | 20 -> 11 | Out: FIEE, TLRY, IZEA, BOSC (+7%). Kept: KODK, RGP, GHG, IDN |
| cheap_per_roiic | BUG, open | Cheapest fifth of the sector on cpr (1.5 kept as the ceiling). ROIIC <= 1.0. `_ev_sane`. | 3,023 -> 517 | Out: NVDA, MSFT, GOOG, META, ASML, LRCX. Kept: PetroChina, Novo Nordisk, CNOOC |
| flyover | BUG at source + guard | A count missing on every feed reads as neglect only below the 60th percentile of the market's operating caps. | 1,404 -> 988 | Out: TCTZF, LVMHF, LRLCF, Airbus, Fast Retailing, Equinor. Kept: Elbit ESLT.TA, Omega Flex-type firms |
| oak_deep_value | BUG, open | Real cash = net cash >= 20% of mcap. Gross cash is used only where net cash is unmeasured. | 588 -> 264 (-334 +10) | Out: VW (3 lines), Nissan, Casino. Kept: Anhui Conch 600585.SS, Great Wall |
| xr_discops_mask | BUG, open | Arm (a) needs a discops loss covering >= 50% of the continuing-to-NI gap. AHFS is divided by the local market cap. | 76 -> 40 | Out: F, TAP/TAP-A, LUMN, CAG, JSM. Kept: Hexagon, Carrefour |

## Side effects outside the batch

From the shared `_inst_arrival` and `_dna_sane` changes:

| archetype | change |
|---|---|
| mb_conviction_confluence | 33 -> 25 |
| mb_asset_trough_informed | 24 -> 22 |
| forensic_payout_confirmed | 3,514 -> 3,392 (D&A artefacts TYIDY and JXHLY leave) |
| xr_confluence | 898 -> 880 |
| mb_model_confluence | 916 -> 912 |

No other archetype changed.
