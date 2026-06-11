# Empirical Tier 1 — June 11, 2026

Replaces the prior `VERIFIED_TIER1.md`. This ranking is driven by the **backtested base rate of each name's factor tag** (12mo excess vs SPY across 22 historical setups, 2018-2024), not by my subjective confidence weights. **A live insider-cluster signal in the EDGAR Form-4 data adds +30pp to the prior.**

The numbers below are the *historical base rate*, not a price target. They are the bar each name must clear; a single name can do far better or worse than its bucket.

## Tier 1 — empirical ER ≥ +30% vs SPY

| Ticker | Mcap $M | ER vs SPY | Driver | Live cluster evidence |
|---|---|---|---|---|
| **WGS** | 1,673 | **+72%** | insider_cluster | **Casdin $32.6M** across 5 buys May 18–Jun 5, prices $42.55→$56.44 |
| **KBR** | 4,488 | **+70%** | insider_cluster | **4 insiders / $0.94M** May 13–20: CFO Evans, Directors Moore, Sabater, Von Thaer at $30.60–$32.47 |
| **ROCK** | 1,164 | **+66%** | insider_cluster | **3 insiders / $0.82M** May 20–26: CEO Bosway, CFO Lovechio, GC Bolanowski at $34.62–$37.44 |
| **NSP** | 1,420 | **+36%** | founder_buy | **Sarvadi $7.93M single-buy** Jun 3 at $34.05 |

These four are the only names where the backtested signal historically delivered double-digit excess returns *and* the signal is confirmed live in primary EDGAR data, not an aggregator.

## Tier 2 — empirical ER 0–30%

| Ticker | ER | Driver | Status notes |
|---|---|---|---|
| INMD | +10% | smart_money_uw | Founder $10.7M buy confirmed via 13D/A, but no Form-4 cluster (foreign filer; EDGAR omitted) |
| HHH | +7% | sponsor_anchor (proxied) | Vantage closed; Ackman -32% to cost; no recent insider Form 4 |
| NRP | +7% | family_anchor (proxied) | Family 31.75% intact; Sisecam JV impaired |
| SONO | +6% | activist_form4_cluster | Coliseum's $35M buys are >120 days old, fell outside the 60-day cluster window |
| UA | +5% | founder_buy | Fairfax accumulation real but it's an anchor not an open-market founder buy; weakest of the +ER set |

## Tier 3 — negative empirical ER unless an override exists

| Ticker | ER | Driver | What would justify owning it |
|---|---|---|---|
| **CDRE** | -9% | activist_13d (-26%) | Specific evidence Wynnefield is forcing a sale or buyback that breaks the activist-13d base rate |
| **MNRO** | -15% | sale_process (-46%) | A live binding bidder at a specific premium; mere "strategic review" is the bucket that lost 46% on n=2 |
| **RPAY** | -29% | bid_rejected (-61%) | A higher bid above $4.80, or a definitive AGM outcome forcing the board out |

These three sit in archetypes that historically have **catastrophic** failure rates. They can still work, but they need a specific positive surprise that overrides the base rate; otherwise the math says don't size them.

## What changed vs my prior list

- **WGS promoted to #1** by data (was Tier 2). Largest dollar insider cluster in the entire universe.
- **KBR, ROCK, NSP** confirmed as Tier 1 by both EDGAR Form-4 evidence AND the strongest backtest bucket.
- **RPAY, MNRO, SEER** demoted from Tier 1 because their dominant factor tag has a **negative** empirical track record. SEER drops off entirely as it's biotech-adjacent + bid_rejected (worst-of-both).
- **INMD** drops to Tier 2 because EDGAR didn't surface a US Form-4 cluster (Israeli filer); thesis still rests on the prior 13D/A trail, which is fine but weaker than a confirmed live cluster.
- **UA** drops to Tier 2: Fairfax accumulation is real but it's an anchor pattern, not the open-market founder-buy signal the backtest measures.

## What's still missing

1. **Sample sizes are small** — n=2 for insider_cluster, n=5 for founder_buy. A live cluster name is the strongest empirical signal but the confidence interval is wide.
2. **EDGAR pull is partial** — the system pulled the 12 main names; broader sweep of the activist 13D universe would likely surface more clusters.
3. **No options overlay** has been built yet — KBR's Jan 2027 spin and HHH's NAV close are both excellent candidates for call spreads rather than common.
4. **INMD foreign-filer gap** — Israel doesn't file Form 4 to EDGAR; need a separate ingestion path.

## How to use this list

- **Anchor positions** (largest sizing): WGS, KBR, ROCK, NSP — Tier 1 names with both backtested edge and verified live signal.
- **Smaller / opportunistic**: INMD, HHH, NRP, SONO, UA — positive ER but no live cluster confirmation; size at half-conviction.
- **Special situation only**: CDRE, MNRO, RPAY — only own if you have a specific reason to believe the base rate is wrong for *this* setup.

Pipeline: `make refresh` rebuilds every column from primary sources.
