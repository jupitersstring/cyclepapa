# 10b5-1 Plan Activity — Adoptions, Terminations, Modifications

*Generated 2026-06-02. Source: 10-Q Item 5 ("Other Information /
Trading Arrangements") for the top 80 names spanning the asymmetry
universe. Outputs: `cancel_10b5_1.{py,csv,json}`,
`asymmetric_integrated.{csv,json}`.*

## Why it matters

Rule 10b5-1 plans are pre-arranged insider trading instructions. Since
Feb 2023 the SEC requires companies to disclose **adoption,
modification, and TERMINATION** of every 10b5-1 plan in each 10-Q's
Item 5. This produces a directional signal that's stronger than ordinary
insider trade flow:

| Action | Plan type | Signal |
|---|---|---|
| TERMINATE | sell plan | **Bullish** — insider voluntarily cancelled scheduled selling |
| ADOPT | sell plan | **Bearish** — insider has committed to a calendar of sales |
| TERMINATE | buy plan | Bearish — insider no longer wants to keep buying |
| ADOPT | buy plan | Bullish (rare) |
| Modification pair | — | Neutral (terminate + re-adopt same day = restructure) |

Terminating a sell plan is a stronger signal than the absence of selling,
because the insider had previously committed to sell and then changed
their mind. They had to file the cancellation publicly — a costly,
deliberate action.

## Methodology

1. For each top asymmetric ticker, pull the most-recent 4 10-Q filings
   via SEC submissions JSON. Cache each filing's HTML permanently to
   `.cache/docs/{accession}.html`.
2. Isolate the Item 5 / Trading Arrangements section (union of windows
   around Item 5, "10b5-1 trading arrangement", "Trading Plans"
   anchors).
3. Apply three trigger patterns (TERMINATE / ADOPT / MODIFY) with
   proximity constraints to "Rule 10b5-1" or "trading plan".
4. Negative-boilerplate filter: full-paragraph scan for "no director or
   officer adopted or terminated" eliminates Item 5 entries that
   explicitly state nothing happened.
5. Natural-expiration filter: drop hits matching "scheduled to
   terminate", "expired by operation of its terms", "will terminate
   upon the earlier of".
6. NEO + role + shares attribution via tight-window regex around the
   trigger.
7. Same-filing-date terminate + adopt by the same NEO is flagged as a
   modification pair (neutral, overrides individual scores).
8. Size-conditional scoring: adoptions <10K shares are weakened (likely
   tax-management, not signal).

Scoring per event (signed, capped ±25 in composite):

| Action | Plan | CEO/Chair | CFO | Other NEO |
|---|---|---|---|---|
| TERMINATE | sell | **+30 (+8 size kicker)** | +24 | +18 |
| ADOPT | sell | -20 (-6 size kicker) | -16 | -12 |
| TERMINATE | buy | — | — | -8 |
| ADOPT | buy | — | — | +8 |

## Bullish signal — terminate sell plan

### CRM · Salesforce · $148.7B · $181.82 — composite leapt from 41 to 66

**Marc Benioff (Chair and Chief Executive Officer) terminated a
Rule 10b5-1 trading arrangement on March 31, 2026 that would have sold
up to 351,607 shares of CRM common stock between April 1, 2026 and
February 26, 2027.**

At $181.82, that's a $64M pre-arranged sale that the founder-CEO
explicitly walked back. Combined with the earlier-flagged $1M director
buy cluster (Alber + Kirk, March 18-19, 2026) and the $25B buyback +
spin + governance reset stack from the step-change layer, CRM now
ranks **#1** in the integrated composite. The founder is voting with
his own arrangement — strongest possible signal of expected upside.

The CEO also adopted a 7,000-share plan in December 2025 along with two
other officers (small standing tax-management plans, weakly bearish at
-3 each), but the size differential is overwhelming: a 50× larger
position was unwound.

## Bearish signal — adopt sell plan (downgrades to prior Tier A)

### FLUT · Flutter Entertainment · $17.5B — composite dropped from 56 to 36

Peter Jackson (Chief Executive Officer) adopted a Rule 10b5-1 trading
plan on November 12, 2025 (-20). The 7-director buy cluster on May 11-
12, 2026 (Tier A in the previous report) is partly offset by the CEO
having pre-arranged sales in place. **Note the sequence**: the CEO sell
plan was adopted *before* the buy cluster. The buys happened on top of
existing sell commitments — the bullish reading is that conviction-buy
behaviour intensified despite the prior sell plan, the bearish reading
is that the cycle of pre-arranged selling weakens the signal.

### Other 10b5-1 adopt-sell flags (insiders preparing to sell)

| TKR | 10b5 score | Detail |
|---|---|---|
| LAZ | -34 | CFO adopted 206K sh plan, Director adopted 226K sh plan |
| SOFI | -33 | EVP Keough 244K, **CTO Rishel 815K** |
| EPAM | -29 | **Executive Chair Dobkin adopted 150K** (+ Fejes mod pair) |
| NKE | -27 | EVP Alagirisamy 53K + EVP Friend 153K |
| WST | -20 | **CEO Eric Green adopted 83K plan** |
| PCG | -15 | EVP adopted 374K plan |
| EYE | -15 | Director adopted 150K plan |

These are all SELL plan adoptions in recent quarters by C-suite or
senior insiders. Material adoption volumes (>100K shares by senior
execs) signal the insider has decided to monetize.

## Mixed signal — terminate + adopt by different NEOs

### OPCH · Option Care Health · $3.2B — composite essentially flat (40 → 39)

Same filing (2026-04-30):
- COO **Luke Whitworth terminated a 60,000-share sell plan** (bullish +22)
- CEO **John Rademacher adopted a 200,000-share sell plan** (bearish -20)

Read as transition: outgoing-position COO winding down personal selling,
incoming-position CEO setting up scheduled sales. Net signal is roughly
neutral but the composition is informative: the bigger share count is on
the adopt side.

## Effect on the asymmetry rankings

| TKR | Prior asymmetry | 10b5-1 leg | Integrated | Δ rank |
|---|---|---|---|---|
| **CRM** | 41 | **+29** | 66 | 2 → 1 |
| FLUT | 56 | -20 | 36 | 1 → 26 |
| BETR | 47 | -8 | 39 | 8 → 18 |
| HDSN | 49 | 0 | 49 | unchanged |
| OPCH | 40 | -1 | 39 | unchanged |

CRM emerges as the #1 integrated pick — the founder-CEO terminated
$64M of scheduled selling, on top of the prior step-change stack and
director cluster.

FLUT, BETR drop materially. The remaining Tier A picks (TONX, AGBK,
SRAD, PATK, GO, POOL, ODTX, OI, GSHD, EVTC, HFFG, ONON) have **no
10b5-1 activity** in the last 4 quarters — their asymmetric rankings
are unchanged.

## What this analysis cannot tell you

- 10b5-1 terminations sometimes precede strategic transactions (M&A,
  spin, going-private). Cancellation could mean "I expect upside" OR
  "I have material non-public information and can't trade anyway".
- The cleanest read requires the cancellation to be **NOT** quickly
  followed by another sell plan adoption (modification pair test).
  Benioff's case passes this — no re-adoption of a comparable-sized
  plan.
- Adoption of a sell plan is sometimes purely for tax-loss-harvesting
  or option-expiration cover. Sub-10K-share adoptions are weakened
  in scoring.

## Persistence

`cancel_10b5_1.{py,csv,json}` and `asymmetric_integrated.{csv,json}`
all committed. 10-Q filings cached under `.cache/docs/{accession}.html`.
Resumable: each ticker is processed atomically, JSON written
incrementally.
