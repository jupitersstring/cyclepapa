# Name-level spot checks — figures vs source and known reality

Method: for a diverse set (mega-caps with well-known financials, the original
DEEPINDS complaint, top-book names across JP/HK/KR/TH/IN/US), every stored
figure was compared against a JUST-FETCHED Yahoo pull and against externally
known values (scale, margins, multiples). Run 2026-09-11.

| Name | Verdict | Evidence |
|---|---|---|
| MSFT | SOUND (1 note) | mcap $3.71T, rev $318B, P/E 27.9, FCF yield 2.2% all match reality & fresh pull (px drift 1.5%). NOTE: stored ebitda_margin 63.1% vs computed 55.4% — inside the 25% repair tolerance, real value ~55%. |
| AAPL | SOUND | mcap $4.67T vs fresh $4.77T, rev $451B, EBITDA margin 34.7% (real ~34-35%), P/E 36.6. |
| KSS (Kohl's) | SOUND, flagged | rev $15.5B, P/E 8.3 fit the retailer; fcf_yield −35.8% is a genuinely bad inventory-cycle year; `ev_comp_gap` qc-flag present. Px drift −14% vs fresh (fell since last pull). |
| 7203.T (Toyota) | SOUND | mcap ¥36.7T, rev ¥50.7T, EBITDA margin 15.1% (real 15-16%), P/E 8.8. |
| GASS (StealthGas) | SOUND | mcap $350M, rev $167M, 46% EBITDA margin (LPG shipping), P/E 5.8, FCF yield 28%. |
| DEEPINDS.NS | SOUND (was the original defect) | EBITDA ₹3.84B / 43% margin / EV-EBITDA 13.5 / nde 0.02, P/E 24.3 vs fresh 24.6. |
| 0700.HK (Tencent) | SOUND | mcap HK$3.96T, rev RMB 752B, EBITDA margin 47.5%, P/E 14.8, EV/EBITDA 13.8. |
| 2230.HK (Medialink) | SOUND, flagged | 2.0B shares check out; deep net cash (EV/EBITDA 1.26), FCF yield 27%; `ev_comp_gap` = investments basis. |
| 088910.KQ (Dongwoo) | SOUND, flagged | thin 3.7% food-distribution margin, P/E 5.0, net-cash EV/EBITDA 0.88; `fcf_gt_cfo` flag = negative-capex year, identifiable. |
| 1798.T (Moriya) | SOUND, flagged | classic JP net-net: P/E 4.2, EV/EBITDA 2.8, FCF yield 26%; `ev_comp_gap` = securities holdings ≈ half of mcap. |
| ERIC | n/a | not in master (Ericsson tracked via home listing). |

Conclusions
- No corruption found in any spot-checked figure; scales, margins and
  multiples match external reality for every name checked.
- Anomalies that remain are LEGITIMATE accounting states, and every one now
  carries a per-row `qc_flags` marker (op_gt_ebitda_margin,
  gross_lt_op_margin, fcf_gt_cfo, ev_comp_gap, fx_twin_dev, neg_ev) — nothing
  is silent.
- Negative-EV multiples are kept as real, interpretable numbers (negative EV
  over a positive denominator); only non-positive denominators null a multiple.
- Every reconciliation batch is persisted to audit_reports/reconcile_log.txt.

## Round 2 — archetype-consequential figures (2026-09-11)

Method: top-5 firers of each NEW archetype (CashAdjPE, OwnerEarnings,
UnderstatedE, OverDepreciated, ExpensedGrowth, HiddenAssets) = 21 unique
names; the 9 gate-critical fields each (cash, debt, NI, CFO, EBITDA, revenue,
gross margin, shares, mcap) compared against a JUST-FETCHED source pull.
189 field-checks -> 9 disagreements, three classes, two fixed at the root:

1. total_debt stale/narrow on 5 names (4629.T carried Y5M vs the real,
   lease-inclusive Y300M). Consequential in the worst direction: stale-LOW
   debt overstates net cash and therefore CashAdjPE / HiddenAssets cheapness.
   FIX: total_debt joined the conflict reconcile (fresher, lease-inclusive
   measure wins; 3,600 names repaired) and net_cash_pct_mcap — which gates
   the entire net-cash archetype family — joined the derived recompute
   (13,881 rows refreshed).
2. cfo_ttm drift on 3 names at 1.38-1.48x: the STORED source file had aged
   past new quarters. Fresh rows folded in; the two residuals (1.38x, 1.37x)
   sit inside the deliberate 1.4x non-churn tolerance.
3. 2230.HK cash 372M vs narrow 249M: the documented broad-cash
   (investments) basis — correct by design, qc-flagged.

Post-fix: 6/8 actionable disagreements cleared exactly (ratio 1.00); gates
146 checks 0 FAIL, mutation 32/0, top-60 crosscheck 0 ERROR / 32 clean.

## Round 3 — boldest claims + unsampled markets (2026-09-11)

Targets: all 8 top NEGATIVE adjusted-P/E names (the "earnings come free"
claim — cash, debt, NI, mcap each verified against a fresh source pull) and
the top name in 8 previously-unsampled markets (BR, TR, IN, PL, ID, SE, MY,
TW). 112 field comparisons -> 2 disagreements, BOTH the known FCF-source
class, and both HEALED live by the new statement-grade hierarchy the moment
the rows merged ("fcf_ttm (Yahoo statement trailing, non-EDGAR) repaired 2"):
0057.HK (Chen Hsong) master -170M -> statement +428M (a 45% FCF yield that
fits its known cash-machine profile); 035610.KQ 1.64x -> statement value.
Every input behind the negative adjusted-P/E cohort verified CLEAN — the
free-earnings claims stand on checked figures. FPIP.ST returned no fresh
Yahoo row (source miss, noted). Post-merge sweep: 0 ERROR.

## Round 4 — live SEC end-to-end + currency arbitration (2026-09-11)

Six edgar_grounded names re-verified against LIVE companyfacts with the fixed
roll-forward: 10/12 field comparisons exact (KROS self-healed since round 2).
The 2 disagreements were ONE name — JFU/9F, a 20-F ANNUAL-only Chinese ADR
whose audited USD figures were excluded by the one-quarter gate while Yahoo
served CNY levels against a USD mcap. Fixed as a class: CURRENCY ARBITRATION —
when BOTH flow fields sit >2x above audited EDGAR (age<=500d), the audited USD
levels win regardless of the quarterly gate (stale-but-right-currency beats
fresh-but-wrong-currency). 109 rows healed; JFU now $19.2M/$29.7M, P/S 1.56.

## Round 5 — EVERY archetype sampled (2026-09-11)

valuation_crosscheck gained --per-archetype: top-ETA + seeded-random firer
from EVERY archetype (94 archetypes -> 133 unique names), full per-name suite
each. One ERROR found and fixed as a class: WIMI (CNY-ADR) held a stale
plausible-looking fcf_yield beside components proving |fcf/mcap| = 4.16 —
the band-reject left the stored value standing; now a provably-corrupt
recomputation NULLS the stored yield too (59 more nulled). Final:
0 ERROR, 76/133 fully clean, all WARNs in the established explained classes
(EV composition basis 31, roe period-basis 29, small level drifts).

## Round 6 — XR gate-critical figures (2026-09-12)

18 top XR firers x 10 gate-critical fields vs a fresh statements-mode pull:
24/155 disagreements in four classes, two fixed at the root immediately:
1. NEGATIVE CAPEX corruption (088910.KQ -16.6B vs real +1.9B) inflating FCF
   through the identity -> capex normalized to the cfo-fcf identity (118
   repaired) and 4,949 negative-no-rescue capex values nulled.
2. HOLLOW EDGAR BALANCE ITEMS adopted as truth: TTEC debt ZERO vs the real
   $933M (revolver outside the alias set), STG cash $82M vs real $858M
   (money-market instruments unseen). Fixes: (a) absence-of-evidence guard —
   EDGAR cash/debt only wins when >= half of Yahoo's figure; (b) zeros are
   VALUES and must be repairable (the reconcile's nonzero-cur guard made a
   hollow zero immortal) — 1,720 debts repaired; (c) cash's broad-basis
   defense made DIRECTIONAL (master may exceed Yahoo's narrow cash, never
   sit under half of it) — 1,969 repaired.
3. CFO/FCF staleness on non-US names — heals via the statements merge.
4. Dividend-yield freshness lag (~1.5x on two names) — accepted, noted.
Re-verified post-fix: 8 -> 1 disagreement on balance/level fields (the
survivor is the documented broad-cash basis). XR6 tightened 339 -> 174 as
capex corrections flowed through owner earnings.

## Round 7 — "nonsensical methods" hunt: root-cause and REPAIR (2026-09-11)

Directive: institutional grade; every measure must be what it is described
as; never null what can be understood and repaired. Every class below was
root-caused with named evidence before any fix.

1. owner_earnings_yield was literally fcf/mcap under a Buffett label (one
   measure under two names = silent double-count in every OR-leg and in
   robust_cash_yield). Rebuilt as TRUE OE = NI + implied D&A - capex over
   mcap, built AFTER margin sanitation (KTTA held an OE its final
   components could not reproduce), with EDGAR-audited + Yahoo-statement
   capex (~3.9k rows). Audit gates: OE matches its own same-row
   construction; no OE without a capex component. Spot-verified 6/6
   reproducible post-fix.
2. normalized_ebit > normalized_ebitda (3,008 rows, impossible: needs
   negative D&A). ROOT CAUSE proven live on RNO.PA/Renault: alias pair
   mixed BASES — Yahoo "EBITDA" INCLUDES unusual items (Renault FY2025
   carries the -11.6B Nissan writedown: EBIT -9.9B, EBITDA -5.6B) while
   fallbacks "Normalized EBITDA"/"Operating Income" EXCLUDE them
   (+5.9B/+3.6B) — plus NaN-year misalignment of the two averages.
   REPAIRED 2,990/3,008 by refetch on ONE basis (EBITDA := EBIT +
   Reconciled D&A per matched year, both averages over the same years);
   yartseva_db now constructs that way at source; 18 refused (no coherent
   series). 0 inverted pairs remain.
3. not_priced_in_score unbounded (max 1.65e6). ROOT CAUSE per name: yoy
   growth off near-zero priors — ANSC (SPAC) fcf_yoy 3.29e6 = first real
   cash year; 1841.T price_yoy +14,413,000% is its own price-history
   corruption. REPAIRED by guarded recomputation from stored components
   (drop >1000% base-effect inputs, clip differentials to ±300pp):
   3,466 refilled; score bounded [-3,3] by construction + audit gate.
4. NCAV > book equity (693 at 1.05x / 312 at 1.5x — impossible;
   equity = NCAV + non-current assets). THREE distinct causes found:
   (a) UK pence-vs-pounds pb — Yahoo priceToBook divides GBp price by
   GBP book (~100x exactly) on cents-quoted markets while p_e/p_s are
   consistent. Repaired with PER-ROW evidence, never blanket: NI/ROE
   independent equity (Hunting 94.8 -> 0.95 vs known ~0.9; Games
   Workshop 21.28 vs independent 21.29 — genuine, untouched), NCAV
   identity for loss-makers, and for the evidence-less residue a fetched
   bookValue adjudication (Yahoo's price.currency says "GBp" itself):
   Virgin Wines 0.75, Derwent London 0.59, AngloGold 6.0. 172 repaired.
   (b) vintage: ncav_pct_mcap was never recomputed against current mcap
   — joined the recompute family (7,764 refreshed).
   (c) cross-currency lines (below). Survivors are FLAGGED
   ncav_gt_equity (kept, identifiable); audit fails only SILENT ones.
5. Net cash > 20x mcap (352) => THE QUOTE-vs-FINANCIAL-CURRENCY HOLE:
   fx_to_usd is keyed off the quote currency while Yahoo serves levels
   in the financial currency, so secondary lines (.F, OTC pinksheets,
   B-shares) held every level-over-mcap ratio off by exactly the fx
   factor — T3O.F showed "74x mcap" in cash (JPY over EUR), and the
   MODERATE cases (GBP/USD 1.3x) sat inside every band. REPAIRS:
   (a) name-twin restatement — home line (quote ccy == country ccy)
   anchors the financial currency; siblings with matching raw levels
   get levels restated into their own quote ccy via the exact fx bridge
   (persisted as ccy_bridge): 900920.SS B-share P/B 0.52, Chudenko OTC
   0.96, Hokuriku OTC 0.91 (a blanket pb/b would have printed 133 —
   Yahoo is inconsistent per line, so pb/p_e are recomputed from
   restated NI, never scaled);
   (b) pb-anchored TWINLESS restatement — where the home listing is not
   in master but Yahoo's pb is converted-and-sane, the bridge
   (mcap/pb)/(NI/roe) is accepted only within ±20% of a REAL currency
   pair's rate and snapped to that exact rate: 393 more lines (SKY
   Perfect JSAT to its true 7.0x earnings, ALNPY 6.7x, OYOCF 18.3x);
   (c) no-anchor mixed groups (New China Life NWWCF/NCL.F share raw CNY
   levels across USD/EUR quotes, neither provable): quote-vs-level
   ratios nulled+flagged on SATELLITE lines only — the largest-mcap
   line is presumed home so no company goes unrepresented (the Freddie
   Mac class), and financials are exempt from the 20x band
   (conservatorship cash >20x a depressed mcap is REAL).
   ticker_yf now fetches yf_quote_currency + yf_financial_currency so
   the next full pull converts everything at source.
6. Structural finds: derive's ev_ebit guard keyed to the EDGAR-only
   opinc series wiped 14,442 non-US multiples (16,708 -> 2,266) — now
   conditioned on known denominators only; the EDGAR multi-year
   averages (oe_avg/ni_avg family) had been merged one-off and silently
   died on rebuild — now merged structurally in the harmonizer every
   run (44,465 cells); the F4 audit checks now test the BINDING leg
   (latest OR Graham-average earnings).

Verification: 178 audit checks 0 FAIL (1 known WARN class), mutation
32/0, per-archetype crosscheck across ALL archetypes (154 firers):
0 ERROR, every WARN in the established documented classes.
