# Book QA — 2026-09-24

Automated checks over every sheet of the three books (`book_qa.py`). Counts by book and kind, then every finding.

| Book | Kind | Findings |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | DEAD COLUMN | 1 |
| MOST_ASYMMETRIC.xlsx | DUPLICATE ISSUER | 3 |
| MOST_ASYMMETRIC.xlsx | NO DATA | 6 |
| cyclepapa_risk_reward_workbook.xlsx | DUPLICATE ISSUER | 3 |

## Findings

| Book | Sheet | Row | Kind | Ticker | Detail |
|---|---|---|---|---|---|
| MOST_ASYMMETRIC | PSU Plans | 4 | DEAD COLUMN |  | 'rTSR target' empty in 1103/1217 rows |
| MOST_ASYMMETRIC | Name Financials | 1152 | DUPLICATE ISSUER | FMCQF,FMS | fresenius medical care |
| MOST_ASYMMETRIC | Name Financials | 1291 | DUPLICATE ISSUER | CUBB,CUBI | customers bancorp |
| MOST_ASYMMETRIC | Name Financials | 1438 | DUPLICATE ISSUER | RACD,RACC | research alliance |
| MOST_ASYMMETRIC | Insider Filing-Time | 51 | NO DATA | GF | no FMP financial record |
| MOST_ASYMMETRIC | Insider Filing-Time | 52 | NO DATA | MXF | no FMP financial record |
| MOST_ASYMMETRIC | Turnaround Signal | 22 | NO DATA | CIK0000859737 | no FMP financial record |
| MOST_ASYMMETRIC | Turnaround Signal | 35 | NO DATA | ALB-PA | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 62 | NO DATA | ALB-PA | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 90 | NO DATA | NOTEW | no FMP financial record |
| cyclepapa_risk_reward_workbook | All names | 302 | DUPLICATE ISSUER | AZLUY,AZUL | azul |
| cyclepapa_risk_reward_workbook | All names | 964 | DUPLICATE ISSUER | HK:2202,SZSE:000002 | vanke |
| cyclepapa_risk_reward_workbook | All names | 1204 | DUPLICATE ISSUER | NRIM,— | northrim bancorp |
