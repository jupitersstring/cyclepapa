# Book QA — 2026-09-25

Automated checks over every sheet of the three books (`book_qa.py`). Counts by book and kind, then every finding.

| Book | Kind | Findings |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | DEAD COLUMN | 1 |
| MOST_ASYMMETRIC.xlsx | DUPLICATE ISSUER | 1 |
| MOST_ASYMMETRIC.xlsx | NO DATA | 2 |
| OTC_BOOK.xlsx | DEAD COLUMN | 1 |
| cyclepapa_risk_reward_workbook.xlsx | BAD SECURITY | 3 |
| cyclepapa_risk_reward_workbook.xlsx | DUPLICATE ISSUER | 1 |

## Findings

| Book | Sheet | Row | Kind | Ticker | Detail |
|---|---|---|---|---|---|
| MOST_ASYMMETRIC | PSU Plans | 4 | DEAD COLUMN |  | 'rTSR target' empty in 1093/1207 rows |
| MOST_ASYMMETRIC | What's New | 104 | DUPLICATE ISSUER | AANNF,AT1.DE | aroundtown s a |
| MOST_ASYMMETRIC | What's New | 59 | NO DATA | ALB-PA | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 87 | NO DATA | NOTEW | no FMP financial record |
| OTC_BOOK | Going Dark | 4 | DEAD COLUMN |  | 'Insider %' empty in 49/54 rows |
| cyclepapa_risk_reward_workbook | All names | 32 | BAD SECURITY | XETR:VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | Call intent | 111 | BAD SECURITY | VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | Executive Summary | 34 | BAD SECURITY | XETR:VOW3 | Volkswagen Preferred |
| cyclepapa_risk_reward_workbook | All names | 791 | DUPLICATE ISSUER | HK:2202,SZSE:000002 | vanke |
