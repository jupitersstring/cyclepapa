# Data store — 2026-09-25

One security master, one point-in-time fact store and one event store (`store.py`, built by `store_build.py` into `data/cyclepapa.db`, rebuilt from the caches). Every run appends a dated snapshot of the facts, so values can be read as of any past run.

## Security master

- 66,858 issuers, 93,511 securities, 565,138 aliases (FMP symbol, exchange-qualified `EPA:LOCAL`, bare tickers where unambiguous, `CIK…`, old tickers).
- Security types: common 52,550, fund 21,835, bankrupt 6,216, otc_line 5,921, spac 2,716, adr 2,224, warrant_right_unit 1,041, note_pref 1,008.

## Book identifiers resolved

| Book | Resolved | Not resolved |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | 2,629 | 13 |
| OTC_BOOK.xlsx | 310 | 0 |
| cyclepapa_risk_reward_workbook.xlsx | 1,276 | 68 |

Unresolved samples (headers / non-tickers included): AAQL, ADX:EAND, AECOM, AIDIGONG, APTOF, ASOS, AZLUY, BCBA, BMV:AZTECA, BUYBACK, BXCAP, CIMG, CLBZ, CNDIF, CONOCOPHILLIPS, CONTEL, CSE:HAYL, CSE:HNB, CSE:SAMP, CUX, CVW, CWLXF, DEVSF, DSE:ISLAMIBANK, EUROEYES, FMP, FULLSHARE, GAPACK, GSE, GSE:MTNGH, GSE:RBGH, GSE:SOGEGH, GTCO, HANAFINANCIALGR, HDKSOE, HMM, IBK, IMMUNOTECH-B, KEPCO, LGCHEM

## Cross-source disagreements (validated FMP vs the old quote store, > 25% apart)

66 modules still read the old quote store; these are the names where it disagrees with the validated value.

| Field | Disagreements | of names in both |
|---|---|---|
| mcap | 16 | 5,830 |
| p_b | 0 | 4,658 |
| pe | 0 | 5,025 |

p_b examples: 

mcap examples: CRNX 9,001,981,600.00 vs 3,782,140,160.00; CXH 62,574,172.00 vs 31,280,024.00; BTAI 2,281,855.00 vs 37,053,128.00; ATAI 2,719,161,900.00 vs 1,494,756,736.00; PHGE 1,877,106.00 vs 6,133,494.00; VSCO 7,268,242,879.00 vs 4,312,813,568.00; PSTV 9,363,867.00 vs 28,912,366.00; EVTV 6,580,053.00 vs 18,749,544.00

## Source coverage of the names in each book

| Book | Names | Financials | Expectations | Ownership | Red-flag scan | 8-K events | Transcripts | PSU plan |
|---|---|---|---|---|---|---|---|---|
| MOST_ASYMMETRIC.xlsx | 2,621 | 100% | 92% | 92% | 90% | 38% | 62% | 46% |
| OTC_BOOK.xlsx | 305 | 98% | 57% | 57% | 55% | 12% | 79% | 10% |
| cyclepapa_risk_reward_workbook.xlsx | 1,094 | 73% | 41% | 41% | 41% | 14% | 78% | 19% |

## Events

| Family | Events |
|---|---|
| INSIDER | 157,786 |
| LEGACY_SCANNER | 31,363 |
| OWNERSHIP | 12,398 |
| RED_FLAG | 1,602 |
| JP_DISCLOSURE | 1,079 |
| CALL_INTENT | 512 |
| EXEC | 400 |
| CEO_CHANGE | 126 |
| BOARD_REFRESH | 119 |
| ACTIVIST_SETTLEMENT | 109 |
| ASSET_SALE | 108 |
| CAPITAL_RETURN_POLICY | 105 |
| UPLISTING | 104 |
| BUYBACK_AUTH | 86 |
| SALE_OF_COMPANY | 81 |
| TENDER_OFFER | 64 |
| STRATEGIC_REVIEW | 58 |
| VALUE_COMMITTEE | 58 |
| DECLASSIFY | 53 |
| GOING_PRIVATE | 52 |
| CAPITAL_RETURN | 43 |
| SPINOFF | 42 |
| PILL_REMOVED | 39 |
| EXCHANGE_OFFER | 33 |
| CHAIR_CEO_SPLIT | 30 |
| SEPARATION | 20 |
| CH11_EMERGENCE | 16 |

## Point-in-time history

Dated snapshots in the fact store (live runs plus snapshots recovered from git history):

| As of | Source | Rows |
|---|---|---|
| 2026-06-04 | quote_store | 119 |
| 2026-06-10 | quote_store | 1,280 |
| 2026-06-11 | quote_store | 2,993 |
| 2026-06-12 | quote_store | 2,996 |
| 2026-06-15 | quote_store | 5,651 |
| 2026-06-19 | quote_store | 6,388 |
| 2026-06-20 | quote_store | 14,237 |
| 2026-09-23 | quote_store | 30,653 |
| 2026-09-24 | fmp_validated | 105,676 |
| 2026-09-24 | quote_store | 30,042 |
| 2026-09-25 | derived | 10,812 |
| 2026-09-25 | edgar+fmp | 7,365 |
| 2026-09-25 | fmp | 12,016 |
| 2026-09-25 | fmp+finra | 21,040 |
| 2026-09-25 | fmp_validated | 505,149 |
| 2026-09-25 | quote_store | 24,093 |

Facts rows this run: 580,475.
