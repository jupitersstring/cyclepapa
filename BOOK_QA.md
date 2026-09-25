# Book QA — 2026-09-25

Automated checks over every sheet of the three books (`book_qa.py`). Counts by book and kind, then every finding.

| Book | Kind | Findings |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | DEAD COLUMN | 1 |
| OTC_BOOK.xlsx | DEAD COLUMN | 1 |
| cyclepapa_risk_reward_workbook.xlsx | DUPLICATE ISSUER | 1 |

## Findings

| Book | Sheet | Row | Kind | Ticker | Detail |
|---|---|---|---|---|---|
| MOST_ASYMMETRIC | PSU Plans | 4 | DEAD COLUMN |  | 'rTSR target' empty in 1093/1207 rows |
| OTC_BOOK | Going Dark | 4 | DEAD COLUMN |  | 'Insider %' empty in 49/54 rows |
| cyclepapa_risk_reward_workbook | All names | 791 | DUPLICATE ISSUER | HK:2202,SZSE:000002 | vanke |
