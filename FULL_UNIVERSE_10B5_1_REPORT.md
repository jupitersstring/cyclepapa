# Full Universe 10b5-1 Scan

*Generated 2026-06-07. Scope: 1,995 US-listed equities (full union of
all signal-layer cohorts after universe-filter exclusions). Method:
each company's last 4 10-Q filings pulled via SEC submissions API,
Item 5 / Trading Arrangements section isolated, all adoption /
termination / modification events extracted, role-attributed, and
size-weighted. 4 parallel workers, ~15-20 min total runtime against
8,000 10-Q HTML fetches.*

## Headline numbers

| Bucket | Count |
|---|---:|
| Tickers scanned | 1,995 |
| Non-zero 10b5-1 signal | 395 (19.8%) |
| Bullish (score > +15) | 79 |
| Bearish (score < -30) | 86 |
| Max bullish score | +80 |
| Max bearish score | -80 |

## Tier 1 — BULLISH: highest-conviction CEO-led sell-plan cancellations

These are insiders publicly walking back scheduled selling.
Verbatim filing language confirms each. Most are large-cap names —
the signal is unusually clean because CEOs/CFOs of large companies
rarely cancel pre-arranged trading plans without conviction.

### NVDA · Nvidia · score +80
Four termination events across 4 quarters:
- **Jensen Huang** (President & CEO), **363,818-share** plan TERMINATED 2025-05-28
- Director plans terminated 2025-08-27 (387,158 sh), 2025-11-19 (97,075 sh), 2026-05-20 (37,890 sh)

Total ~885K shares of sell plans walked back by Nvidia's founder-CEO
plus three directors over a year. Strongest founder-led signal at the
largest mcap in the entire screen.

### NOW · ServiceNow · score +80
Single-day institutional cluster (2026-04-23):
- William R. McDermott (CEO) terminated 3,700-share plan
- Gina Mastantuono (President & CFO) terminated 3,700-share plan
- Nick Tzitzon (Vice Chairman) terminated two plans

CEO + CFO + Vice Chair all terminating plans on the SAME DAY is the
purest institutional signal in the dataset. Plan sizes are smaller in
share count (option-based) but the role concentration is what matters.

### WMT · Walmart · score +74
Three CEO/EVP terminations spanning a year:
- **Douglas McMillon** (President & CEO), **233,000-share** plan TERMINATED 2025-06-06
- Daniel J. Bartlett (EVP), 155,328-share plan TERMINATED 2026-05-29
- David Rainey (EVP), 40,000-share plan TERMINATED 2025-12-03

McMillon writing back a 233K share plan is the largest mega-cap
CEO-led cancellation in absolute size in the entire data set.

### PCTY · Paylocity · score +80
- Williams (President & CEO) terminated sell plan 2026-05-08
- 3 director terminations across 2025 (including a 165K share plan)

### ITRI · Itron · score +78
- **Thomas L. Deitrich** (President & CEO) — terminated 2 sell plans
  (2025-05-01 and 2025-10-30)
- John F. Marcolini (SVP) terminated 11,400-share plan 2026-04-28

CEO terminating multiple sell plans across quarters is the strongest
single-name conviction pattern.

### MA · Mastercard · score +60
- **Sachin Mehra** (Chief Financial Officer) terminated 35,079-share plan 2025-07-31
- Director (Julius Genachowski) terminated 622-share plan 2025-05-01
- Director terminated 3,977-share plan 2026-04-30

### CDE · Coeur Mining · score +56
- Chairman Mitchell J. Krebs + SVP Casey M. Nault BOTH terminated
  202,257-share plans on 2025-10-29 (same day, same exact size).
- Krebs separately terminated 250,000-share plan 2025-08-06

The same-day same-size dual termination by Chairman + SVP is the
strongest gold-mining bullish signal in the screen.

### Other large-cap bullish terminations

| TKR | Score | Detail |
|---|---|---|
| APP | +72 | AppLovin — CFO Stumpf + CLO Valenzuela terminations |
| APT | +72 | Alpha Pro Tech — 4 director terminations |
| IRON | +72 | Iron Mountain — 4 director terminations |
| EYPT | +59 | EyePoint Pharma — 3 director terminations |
| FCFS | +46 | FirstCash — CEO Wessel + COO Stuart + EVP Orr terminations |
| XEL | +46 | Xcel Energy — director terminations |
| ZLAB | +46 | Zai Lab — director terminations |
| MGRC | +38 | McGrath RentCorp — **CEO terminated 1,886,409-share plan** |
| AMD | +36 | AMD — General Counsel terminations |
| SCHW | +36 | Schwab — director terminations |
| FCN | +30 | FTI Consulting + insider cluster |
| CRM | +29 | **Marc Benioff terminated 351,607-share plan** |

## Tier 1 — BEARISH: CEOs and management adopting large sell plans

The cleanest "stay away" signals in the screen — multiple senior
officers simultaneously committing to sell programs.

### WBD · Warner Bros Discovery · score -75
2026-05-06 cluster:
- **David Zaslav** (CEO) adopted 258,691-share plan
- Gunnar Wiedenfels (CFO) adopted 290,307-share plan
- **Priya Aiyar** (Chief Legal Officer) adopted 465,338-share plan + 77,243-share plan

CEO + CFO + CLO all on the same day = institutional choreography to monetize.

### KHC · Kraft Heinz · score -74
2025-04-29 cluster:
- **Carlos Abrams-Rivera** (CEO) adopted 182,183-share plan
- Eloi Lima (EVP) adopted 177,149-share plan
- Melissa Werneck (EVP) adopted 81,438-share plan
- Cory Onell (EVP) adopted 50,000-share plan
- Plus Executive Chair Miguel Patricio modified 250,000-share arrangement

### QCOM · Qualcomm · score -74
- **Cristiano Amon** (President & CEO) adopted 150,000-share plan 2025-07-30 and 40,000 plan 2026-02-04
- EVP (CFO) adopted 30,000-share plan 2026-02-04
- EVP (General Counsel) adopted 425,224-share plan 2026-04-29

### NEE · NextEra Energy · score -80
- John W. Ketchum (Chairman) adopted multiple plans (99,603 + 132,184 shares)
- Charles E. Sieving (EVP) adopted 132,184-share plan + 88,605

### TOST · Toast · score -80
2026-05-08 cluster:
- **Aman Narang** (CEO) adopted 108,000-share plan
- Jonathan Vassil (Chief Revenue Officer) adopted 108,000-share plan
- Brian Elworthy (General Counsel) adopted 108,000-share plan

### COIN · Coinbase · score -80
Multiple director plan adoptions including 2,543,770-share termination
+ adoption pattern. Director cluster.

### CRWV · CoreWeave · score -80
Recent IPO — 8 sell-plan adoptions including 2,468,000-share director plan.

### FIG · Figma · score -80
Recent IPO — **Co-Founder President adopted 2,000,000 + 750,000-share plans**.

### Other CEO-led sell-plan adoptions

| TKR | Score | Detail |
|---|---|---|
| ADPT | -78 | **CEO Chad Robins adopted 1,150,000-share plan** + CCO + CFO + CPO |
| FUBO | -76 | **CEO adopted 3,414,889-share plan** (largest single in dataset) |
| AEVA | -70 | CEO Salehian + CTO Rezk + CFO Sinha adoptions |
| BWMN | -74 | Director adopted 560,983-share plan |
| TARS | -71 | CEO Azamian adoption + multiple |
| TSCO | -70 | EVP General Counsel + EVPs |
| OMDA | -80 | CEO Sean Duffy 750K + CFO Cook 146K |
| LXU | -80 | SVP + EVP cluster |
| QTWO | -80 | CFO + CRO + multiple EVPs |
| LITE | -80 | 9 sell-plan adoptions across the org |
| VEL | -80 | EVP + CFO cluster |
| AIP | -80 | CEO Janac + CFO Hawkins + multiple |
| ACMR | -80 | 8 senior officer adoptions |
| ANTX | -49 | CEO Easom 450K plan |
| NTRA | -69 | Executive Chairman + CFO adoptions |
| FSLY | -67 | CEO + Director |
| IBTA | -73 | Founder/CEO 477,706 + CTO 477,706 |
| SVV | -73 | CEO Walsh 445K + CFO Maher 445K |

## How this changes the asymmetric rankings

The integrated composite (`asymmetric_full_universe.csv`) blends the
10b5-1 leg (capped at ±25) with the prior asymmetry signals (insider
cluster, drawdown, step-change, forensic PSU, 13D). 461 tickers now
have a composite score >0.

**CRM** held #1 (composite 66) because Marc Benioff's termination
combined with the prior layers (direct insider buys + $25B buyback +
spin + 67% PSU).

**NVDA, NOW, WMT, MA** rise materially from their prior positions
purely because of the +25 leg from the 10b5-1 scan.

**WBD, KHC, QCOM, COIN, TOST, ADPT** join the bearish-watchlist —
material capital risk from insider monetization is now coded in the
composite.

## What this analysis cannot tell you

- Plan terminations sometimes precede MNPI-triggered windows. The
  cleanest read is when the termination is NOT immediately followed
  by a new plan adoption (modification-pair test). Many of the
  large-cap bullish hits pass this test (NVDA, WMT, NOW, MA).
- The bearish signal at large-caps (WBD, KHC, QCOM) is sometimes just
  "officer needs to diversify". Don't over-weight as a short
  recommendation — use it to time entries, not to drive shorts.
- 10b5-1 disclosures only began in Feb 2023. We have ~3 years of data.
  Older plans modified before then are not captured.
- The screen captures the FACT of an action, not the underlying
  rationale. Read the actual proxy disclosure before sizing.

## Persistence

All artefacts committed:
- `cancel_10b5_1.{py,csv,json}` — main outputs
- `cancel_10b5_1.shard_{0..3}.{json,csv}` — per-shard partials
- `shard_{0..3}.txt`, `full_universe.txt` — universe lists
- `asymmetric_full_universe.csv` — integrated composite (461 rows)
- `finalize_universe_10b5_1.py` — re-runnable integration script
- `.cache/docs/{accession}.html` — every fetched 10-Q (permanent
  cache; ~3000 filings now stored)

Reproducibility: each shard is resumable. To re-run, set
`_complete=false` on any ticker in the JSON and re-execute. The HTML
cache prevents re-fetching.
