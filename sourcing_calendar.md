# Sourcing Calendar — Dated Regulatory Triggers by Region

Extracted from the special-situations sourcing playbook. Each row is a
**hard, dateable catalyst** that triggers a wave of forced-selling or
forced-action across an entire market segment. These are the cleanest
"add to watchlist" calendar events.

Update quarterly. Items past their date become base-rate evidence; new
items get added as regulators announce them.

## Active live triggers (next 12 months)

| Region | Trigger | Date | What it forces | Action |
|---|---|---|---|---|
| **Korea** | Commercial Act amendment effective | **2026-03-06** (passed Feb 25, 175/176 votes) | Treasury-share cancellation: newly acquired within 12m, existing within 18m; Bloomberg est ₩60tn ($42bn) retirements this year; cumulative voting for large companies | Screen chaebol holdcos + high-treasury-share companies; Samsung 87M-share cancellation = template |
| **Korea** | Treasury-share-cancellation deadline (newly acquired) | **2027-03-06** (12m post-effective) | All shares acquired after Mar 6 2026 must be cancelled by this date | List companies that did NOT cancel; force-action candidates |
| **Korea** | Treasury-share-cancellation deadline (existing holdings) | **2027-09-06** (18m post-effective) | All existing treasury holdings must be cancelled | Same — laggard list is the screen |
| **Russell US Index** | Russell reconstitution Rank Day | **~2026-04-30** | Preliminary deletion/addition lists published ~late May; effective late June | Front-run small-cap deletions; tax-loss selling overlay |
| **Russell US Index** | First semi-annual rebalance | **2026 H2 (Q4)** | First semi-annual cycle ever — front-running effect concentrates | Calendar both June + Dec auctions |
| **Japan TSE** | "Cost of Capital / PBR<1" monthly compliant lists | **rolling monthly** since Mar 2023 | TSE publishes who has filed value-up plans; laggards face naming-and-shaming | Screen monthly non-filer list ∩ PBR<1 ∩ payout capacity |
| **EU** | Industrial Accelerator Act effective | **2026-03-04** (in force) | KfW/EIB/EU Innovation Fund templated A2 authority for steel/aluminium/cement/auto/renewables | Track KfW commitment announcements; Salzgitter is the marquee German case |
| **US December** | Tax-loss-selling window | **annual, last 2 weeks Dec** | Year-end forced selling on losers below 12-mo high | Screen YTD losers, microcap especially, with reversal patterns |
| **UK** | Takeover Panel PUSU "put up or shut up" deadlines | rolling | Bidder must announce firm intention or step away within 28 days of Possible Offer | Track Possible Offer announcements; bid-or-walk binaries |

## Recurring quarterly / semi-annual triggers

| Region | Trigger | Frequency | Use |
|---|---|---|---|
| **US** | 13F filing deadline | quarterly (45 days post-quarter-end) | Track new positions from event-driven specialists; lag is the cost but base rate is high |
| **US** | Form 4 cluster-buy windows | continuous | Lakonishok-Lee signal; see `src/cluster_buys.py` |
| **US** | EDGAR Form 10-12B filings | continuous | Spinoff 3-6 month early warning; see `src/spinoff_radar.py` |
| **US** | Russell reconstitution | semi-annual from 2026 | Forced flow; calendar Q2 + Q4 |
| **Japan** | TSE compliance monthly list | monthly | Laggard screen |
| **Korea** | KRX value-up disclosure | monthly | Same |
| **UK** | RNS PUSU calendar | continuous | Bidder deadlines |
| **EU** | EU Commission state-aid approvals | continuous | A2 deal pipeline |

## Reform regimes (multi-year structural)

| Region | Regime | Started | Status | Implications |
|---|---|---|---|---|
| **Japan** | TSE Action to Implement Management Conscious of Cost of Capital and Stock Price | **2023-03** | rolling enforcement | 43% of Japanese cos at PBR<1 vs 5% US, 24% EU; recurring catalyst across thousands of names |
| **Korea** | Value-Up / "Kospi 5000" + Commercial Act third amendment | **2024-2026** | active, ₩60tn cancellations triggered | Multi-year force-cancellation cycle for treasury shares |
| **EU** | Industrial Accelerator Act + CBAM enforcement | **2026-03** + **2026-01** | active | A2 archetype framework for steel/aluminium/cement/auto/renewables |
| **UK** | City Code / Takeover Panel scheme regime | continuous | 71–94% of recommended bids use schemes | Court-sanctioned binaries; 75% value + majority number vote |
| **Germany** | Spruchverfahren appraisal proceedings | continuous | post-squeeze-out top-ups average ~10–30% | Specialist arb post-domination/profit-transfer agreements |
| **Australia** | Schemes of arrangement | continuous | similar to UK | Court-supervised structure for the majority of recommended bids |
| **Canada** | Plan of Arrangement + NCIB / Substantial Issuer Bid | continuous | court-supervised | Issuer-bid arb basket |

## Date-keyed historical anchors (use as evidence base, not active)

| Date | Event | Lesson |
|---|---|---|
| 2026-03-06 | Korea Commercial Act effective | Treasury-share cancellation regime forces ₩60tn flow |
| 2026-03-04 | EU Industrial Accelerator Act in force | A2 European framework now legally instantiated |
| 2025-07-10 | DoD/MP Materials partnership | A2 template — sovereign as floor+offtake+lender+equity |
| 2025-Q4 | First Russell semi-annual cycle | Front-running cohort concentrated |
| 2024-2025 | Japan TSE record buyback cohort (nearly tripled 2024) | PBR<1 reform compounds into capital-return wave |
| 2023-03 | TSE PBR<1 disclosure regime announced | Multi-year force-disclosure regime begins |
| 2018-02 | WMIH/Mr. Cooper acquisition | $6bn NOL monetisation template |
| 2013-06-17 | Allegion 10-12B filed | Spinoff early-warning 3-6 months pre-distribution |

## How this calendar plugs into the framework

1. **Daily**: `src/spinoff_radar.py` polls Form 10-12B + 8-K spinoff
   language → `data/inbox/<date>/spinoff/`
2. **Daily**: `src/edgar_poll.py` polls Tier-S/A/B/red-flag queries →
   `data/inbox/<date>/<tier>/`
3. **Weekly**: `src/cluster_buys.py` runs Lakonishok-Lee Form 4 cluster
   detection over candidate set → `output/cluster_buys.md`
4. **Quarterly**: review this calendar; promote new triggers from
   "Active" to "Date-keyed historical anchor" once date passes
5. **Per-trigger-date**: pre-position for the forced-flow event; the
   calendar tells you the *when*, the framework tells you the *who*

## What's missing

- **Form 4 XML extraction** — `src/cluster_buys.py` currently flags
  clusters by unique-filer count from EDGAR FTS metadata. Full code-P
  / role / 10b5-1 detection requires parsing each Form 4 XML. Next
  iteration.
- **OpenInsider integration** — playbook recommends OpenInsider "Latest
  Cluster Buys" as the canonical free source. Direct scraping or CSV
  ingestion is the natural complement to the Form 4 XML parser.
- **PACER docket integration** — for the bankruptcy / disclosure
  statement / confirmation order workflow. Distinct from EDGAR.
- **Trust-NAV tracker for SPACs and UK investment trusts** — discount
  to NAV is the entry signal; needs a daily NAV scrape per ticker.
- **HSR pre-13D activist flag** — HSR filings precede 13D by weeks
  when an activist crosses the size threshold. Not yet integrated.
