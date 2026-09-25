# Book QA — 2026-09-25

Automated checks over every sheet of the three books (`book_qa.py`). Counts by book and kind, then every finding.

| Book | Kind | Findings |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | DEAD COLUMN | 2 |
| MOST_ASYMMETRIC.xlsx | DUPLICATE ISSUER | 4 |
| MOST_ASYMMETRIC.xlsx | NO DATA | 7 |
| OTC_BOOK.xlsx | DEAD COLUMN | 1 |
| cyclepapa_risk_reward_workbook.xlsx | BAD SECURITY | 3 |
| cyclepapa_risk_reward_workbook.xlsx | DUPLICATE ISSUER | 2 |

## Findings

| Book | Sheet | Row | Kind | Ticker | Detail |
|---|---|---|---|---|---|
| MOST_ASYMMETRIC | Asymmetry Assembly | 4 | DEAD COLUMN |  | 'Catl' empty in 24/26 rows |
| MOST_ASYMMETRIC | PSU Plans | 4 | DEAD COLUMN |  | 'rTSR target' empty in 1074/1185 rows |
| MOST_ASYMMETRIC | Name Financials | 1109 | DUPLICATE ISSUER | FMCQF,FMS | fresenius medical care |
| MOST_ASYMMETRIC | Name Financials | 1209 | DUPLICATE ISSUER | 015760.KS,KEP | korea electric power c |
| MOST_ASYMMETRIC | Name Financials | 1416 | DUPLICATE ISSUER | RACD,RACC | research alliance |
| MOST_ASYMMETRIC | What's New | 104 | DUPLICATE ISSUER | AANNF,AT1.DE | aroundtown s a |
| MOST_ASYMMETRIC | Insider Filing-Time | 51 | NO DATA | GF | no FMP financial record |
| MOST_ASYMMETRIC | Insider Filing-Time | 52 | NO DATA | MXF | no FMP financial record |
| MOST_ASYMMETRIC | Single-Measure Best | 85 | NO DATA | GLL | no FMP financial record |
| MOST_ASYMMETRIC | Single-Measure Best | 86 | NO DATA | AGQ | no FMP financial record |
| MOST_ASYMMETRIC | Turnaround Signal | 20 | NO DATA | CIK0000859737 | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 59 | NO DATA | ALB-PA | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 87 | NO DATA | NOTEW | no FMP financial record |
| OTC_BOOK | Going Dark | 4 | DEAD COLUMN |  | 'Insider %' empty in 49/53 rows |
| cyclepapa_risk_reward_workbook | All names | 32 | BAD SECURITY | XETR:VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | Call intent | 108 | BAD SECURITY | VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | Executive Summary | 34 | BAD SECURITY | XETR:VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | All names | 256 | DUPLICATE ISSUER | AZLUY,AZUL | azul |
| cyclepapa_risk_reward_workbook | All names | 823 | DUPLICATE ISSUER | HK:2202,SZSE:000002 | vanke |
