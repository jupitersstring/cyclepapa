# Book QA — 2026-09-24

Automated checks over every sheet of the three books (`book_qa.py`). Counts by book and kind, then every finding.

| Book | Kind | Findings |
|---|---|---|
| MOST_ASYMMETRIC.xlsx | DEAD COLUMN | 2 |
| MOST_ASYMMETRIC.xlsx | DUPLICATE ISSUER | 2 |
| MOST_ASYMMETRIC.xlsx | NO DATA | 4 |
| cyclepapa_risk_reward_workbook.xlsx | DUPLICATE ISSUER | 6 |
| cyclepapa_risk_reward_workbook.xlsx | IMPLAUSIBLE | 16 |

## Findings

| Book | Sheet | Row | Kind | Ticker | Detail |
|---|---|---|---|---|---|
| MOST_ASYMMETRIC | Payoff Geometry | 4 | DEAD COLUMN |  | 'Down%' empty in 47/50 rows |
| MOST_ASYMMETRIC | Turnaround Signal | 4 | DEAD COLUMN |  | 'Since (vs SPY)' empty in 59/59 rows |
| MOST_ASYMMETRIC | Name Financials | 528 | DUPLICATE ISSUER | FMCQF,FMS | fresenius medical care |
| MOST_ASYMMETRIC | Name Financials | 1013 | DUPLICATE ISSUER | RACD,RACC | research alliance |
| MOST_ASYMMETRIC | Insider Filing-Time | 51 | NO DATA | GF | no FMP financial record |
| MOST_ASYMMETRIC | Insider Filing-Time | 52 | NO DATA | MXF | no FMP financial record |
| MOST_ASYMMETRIC | Turnaround Signal | 47 | NO DATA | CIK0002108121 | no FMP financial record |
| MOST_ASYMMETRIC | What's New | 79 | NO DATA | CIK0001355096 | no FMP financial record |
| cyclepapa_risk_reward_workbook | All names | 301 | DUPLICATE ISSUER | AZLUD,AZUL | azul |
| cyclepapa_risk_reward_workbook | All names | 358 | DUPLICATE ISSUER | HK:1918,HKEX:SUNAC | sunac china |
| cyclepapa_risk_reward_workbook | All names | 481 | DUPLICATE ISSUER | CIK:0001109448,AB | alliancebernstein l p |
| cyclepapa_risk_reward_workbook | All names | 968 | DUPLICATE ISSUER | HK:2202,SZSE:000002 | vanke |
| cyclepapa_risk_reward_workbook | All names | 1183 | DUPLICATE ISSUER | —,SNBR | sleep number |
| cyclepapa_risk_reward_workbook | All names | 1211 | DUPLICATE ISSUER | NRIM,— | northrim bancorp |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 56 | IMPLAUSIBLE | DRX | Window start 2026-10-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 57 | IMPLAUSIBLE | TKA | Window start 2026-12-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 58 | IMPLAUSIBLE | GTCO | Window start 2026-12-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 59 | IMPLAUSIBLE | FLG | Window start 2026-12-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 62 | IMPLAUSIBLE | LOCAL | Window start 2027-01-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 63 | IMPLAUSIBLE | WLN | Window start 2027-01-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 64 | IMPLAUSIBLE | HE | Window start 2027-01-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 65 | IMPLAUSIBLE | YPF | Window start 2027-03-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 66 | IMPLAUSIBLE | HE | Window start 2027-03-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 67 | IMPLAUSIBLE | UREE | Window start 2027-06-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 68 | IMPLAUSIBLE | LAC | Window start 2027-09-01 is in the future |
| cyclepapa_risk_reward_workbook | Catalyst timeline | 69 | IMPLAUSIBLE | LAC | Window start 2028-01-01 is in the future |
| cyclepapa_risk_reward_workbook | Name Financials | 88 | IMPLAUSIBLE | GDDY | P/B 1916.98 |
| cyclepapa_risk_reward_workbook | Name Financials | 492 | IMPLAUSIBLE | SUPV | P/B 1317.19 |
| cyclepapa_risk_reward_workbook | Name Financials | 618 | IMPLAUSIBLE | CONC | P/B 452.66 |
| cyclepapa_risk_reward_workbook | Name Financials | 877 | IMPLAUSIBLE | TLSA | P/B 1220.95 |
