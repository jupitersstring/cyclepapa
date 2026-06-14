# Portfolio Construction — Deep Work on the Top 20

The framework has been producing per-name expected values for months. It
has never produced a *portfolio*. This document closes that gap.

The generated portfolio output lives in `output/portfolio.md`; this is
the narrative analysis layer above it. Three deliverables:

1. **Verified YAMLs** for three previously-unmodelled high-information
   names: Hawaiian Electric, MP Materials, Sunac China.
2. **Factor decomposition + correlation matrix** across the active 9
   candidates (`src/portfolio.py`).
3. **Risk-budgeted basket weights** with cluster caps, correlation
   haircuts, and an explicit cash allocation.

---

## 1. What the YAML build verified

### 1.1 Hawaiian Electric (HE) — catalyst already fired April 10, 2026

Primary-document evidence located via the HEI 8-K filing on April 10,
2026 (CIK 354707). Confirmed:

- First of **four equal annual $479m installments** authorised on
  April 10, 2026.
- Final payment condition was a **December 30, 2025 subrogation
  judgment** that became unappealable after all 200+ insurers
  stipulated dismissal of their appeals with prejudice.
- First installment was funded from the **September 2024 equity
  offering** held in a special-purpose vehicle.
- Remaining $1.99bn funding plan: $479m already insurance-reimbursed +
  $479m from 2024 equity (paid) + $479m to be funded by debt or
  convertible debt + $479m from a mix of capital sources, scheduled
  annually through April 2029.

**Framework implication:** HE is the only Tier-1 name where the main
dated catalyst is in the *past tense*. The question shifts from "will
the catalyst fire?" to "is the partial re-rate (from the Sept 2024
$9.25 equity-buyer entry to current ~$15 ≈ +62%) fully discounting the
operational re-rate the catalyst enables?" The waterfall says no:
realised ROE 6.1 vs authorised 9.5 implies ~50% EPS upside on closing
the gap alone, plus multiple normalisation from 1.6× P/B to peer 1.8–2.5×.
Base case 1.80×, bull 3.00×.

EV/DD = 1.92/0.40 = **4.80** — the second-cleanest left tail in the
basket after ELUX-B. This is *anchor-sleeve* material, not a binary.

### 1.2 MP Materials (MP) — the A2 template verified

Confirmed via WebSearch against the July 10, 2025 partnership
announcement (mpmaterials.com investor news + CNBC + Columbia CGEP +
Payne Institute + SFA Oxford):

- **$400m DoD convertible preferred + warrants → 15% as-converted,
  as-exercised stake** (Pentagon largest shareholder).
- **$150m 12-year DoD loan** + $1bn JPM/GS committed financing.
- **10-year NdPr price floor at $110/kg** (≈2× spot at deal date —
  this is the "hard backstop" that makes A2 structurally distinct
  from a normal equity injection).
- **7,000 MT/yr × 10-year magnet offtake** to DoD for defence supply
  + commercial pull-through.
- Apple $500m prepayment followed.

**Framework implication:** MP is the cluster *anchor*, not the highest
EV (LAC has the highest at 3.10×). Its information density comes from
the fact that every other A2 candidate (UREE, Trilogy, Lynas, Algoma,
Calumet, Atlantic Alumina) trades on structural analogy to this deal.
A change in DoD policy stance affects all six simultaneously — which
is exactly what the correlation matrix below picks up.

### 1.3 Sunac China (SUNAC / HKEX 1918) — strongest founder alignment in the cascade

YAML built from prior research with explicit `reported` source tags
(not `verified`) because primary HK scheme circular hasn't been
cross-checked. The framework flags this with sizing-blocked diagnostics.

The structural point worth noting: Sun Hongbin took **23% of the new
MCBs with a 6-year selling restriction**. Of the four Chinese property
names in the universe (Sunac, Kaisa, CIFI, Sino-Ocean), this is the
*strongest* founder commitment device. But the dimension that matters
more — **liquidation recovery floor 4–10%** — means surviving equity is
a genuine residual claim, not merely diluted. The waterfall reflects
this honestly: bear 40% probability × 0.30× return.

EV 2.10×, EV/DD 3.00 — lowest EV/DD in the basket, which is correct.
Chinese property is a binary option, not a compounder.

---

## 2. Factor decomposition — what the correlation matrix exposes

Cosine-similarity correlation over 16 hand-curated factors:

| | Top correlation pair | Value | Meaning |
|---|---|---|---|
| 1 | MP ↔ UREE | **0.99** | Both load on `us_critical_minerals_policy` + `ndpr_ree_cycle` + `us_china_trade_friction`; almost identical risk profile |
| 2 | LAC ↔ UREE | 0.59 | Shared US sovereign minerals policy + EV-cycle exposure |
| 3 | LAC ↔ MP | 0.53 | Shared sovereign policy; distinct on lithium vs NdPr |
| 4 | WLN ↔ ETL | 0.48 | Shared `french_sovereign_strategic` |
| 5 | TMQ ↔ UREE | 0.47 | Shared sovereign policy via Pentagon equity stake |
| 6 | All HE / SUNAC pairs | 0.00 | Genuinely uncorrelated with the rest of the basket |

**The MP↔UREE 0.99 is the most important number in the matrix.** Without
the correlation haircut, the framework would have happily sized both at
10% each (raw ¼-Kelly) — a 20% position in what is effectively one bet
on Pentagon rare-earth policy. The haircut corrects this: MP gets 3.42%
and UREE gets 3.29% after weighting for in-cluster correlation.

HE and SUNAC sit *outside* every cluster's correlation web — they are
the diversifiers. The portfolio sizes them at their full pre-cap weight
(5% each) because there is no in-cluster correlation to discount.

---

## 3. Cluster summary — where the basket concentrates

| Cluster | Names | Raw ¼-Kelly sum | After cap (50%) | Final basket weight |
|---|---|---|---|---|
| **US sovereign minerals** | LAC, MP, TMQ, UREE | 40.0% | 20.0% cap | **15.0%** (cap binds via correlation haircut alone) |
| **French sovereign** | ETL, WLN | 20.0% | 10.0% cap | **10.0%** (cap binds at exactly the post-haircut sum) |
| **Nordic consumer** | ELUX-B | 10.0% | 5.0% cap | **5.0%** |
| **US utility** | HE | 10.0% | 5.0% cap | **5.0%** |
| **China property** | SUNAC | 10.0% | 5.0% cap | **5.0%** |

Total invested: **40%**. Cash: **60%**.

The 60% cash is *not* a bug — it's the framework being honest about
parameter uncertainty. Three independent disciplines push toward it:

- **Fractional Kelly (¼ instead of full Kelly)** — accounts for the
  fact that our waterfall probabilities are estimates with wide
  confidence intervals.
- **Correlation haircut** — accounts for the fact that "10 names" with
  three correlated clusters is really 3-4 independent bets.
- **Cluster cap (50% of raw sum)** — accounts for tail risk of an
  entire cluster going wrong simultaneously (e.g. a US-China rare-
  earth deal collapses MP, UREE, LAC, TMQ together).

The cash sleeve is the option value to size up when correlations
break (one of the cluster bets fires and the others don't — that's
when you redeploy).

---

## 4. Expected portfolio performance

**Expected portfolio multiple on invested capital: 2.34×** (computed as
Σ weight × EV ÷ Σ weight).

**Expected portfolio multiple on total NAV: 0.40 × 2.34 + 0.60 × 1.00 =
1.54×** if held to terminal cash distribution and the cash earns 0%.

Per-name EV contributions (basis points to portfolio multiple):

1. **WLN** — 13.10 bps (largest contributor; gap 1.93× + dated 2027 FCF)
2. **LAC** — 12.28 bps (highest single-name EV; sub-commercial DOE financing)
3. **ETL** — 11.75 bps (partial re-rate priced; dated IRIS² programme)
4. **ELUX-B** — 11.60 bps (cleanest left tail; Wallenberg + Midea)
5. **SUNAC** — 10.50 bps (binary; sized at floor)
6. **HE** — 9.60 bps (catalyst fired; anchor sleeve)
7. **TMQ** — 9.31 bps (Pentagon close pending July 31)
8. **UREE** — 8.91 bps (newest A2 template; in-cluster haircut bit)
9. **MP** — 6.49 bps (heavy haircut due to UREE correlation 0.99)

---

## 5. What this changes in the daily workflow

- The "top 20" rankings of prior screens treated each name as an
  independent EV opportunity. The portfolio layer makes the **basket
  the unit of decision**.
- The cluster caps mean adding a *new* A2 candidate (e.g. when Trilogy
  closes July 31, or when Lynas signs the analogous DoD deal) doesn't
  add a fresh 5% slot — it forces re-allocation *within* the US
  sovereign minerals cluster's 15% combined cap.
- Cash allocation becomes a tracked metric. When 4+ catalysts fire
  within a 6-month window, cash drops as conviction concentrates;
  when none do, cash stays at 60%+.
- The MP↔UREE 0.99 correlation means at most one of them can be
  oversized at any given time. If we promote UREE's Stillwater ramp
  to Tier 1 verified, MP gets downgraded to monitor — they cannot
  both be sized aggressively.

---

## 6. What's still missing (deferred to the next pass)

1. **Source tags are mostly `reported` or `unverified`** on 8 of 10
   candidates. The score.py diagnostics enforce "sizing blocked at
   full conviction" until they're upgraded to `verified` against
   primary filings. The portfolio output here represents an
   *upper-bound* position size that the verification gates throttle.
2. **Factor loadings are hand-curated** — a 1.0 vs 0.7 NdPr loading
   on MP would meaningfully change the portfolio. A proper next step
   is to derive loadings from each YAML's `factors.exposures` field
   programmatically with explicit weights.
3. **Tail correlation is unmodelled**. The cosine similarity is a
   normal-times metric; in a stress scenario (US-China trade deal,
   Chinese property policy stimulus, French banking crisis), the
   inter-cluster correlation moves toward 1.0. A regime-switching
   correlation matrix would be more honest. For now, the cluster cap
   at 50% of raw Kelly serves as a tail-risk haircut.
4. **No options overlay yet.** Several names (HE, WLN, MP) have liquid
   listed options where 2-year call spreads dominate equity on
   risk-adjusted basis. The methodology_review.md §3.2 fix is still
   open.

---

## 7. Top-line summary table — for the chat answer

| Name | Cluster | Final weight | EV× | Contribution |
|---|---|---|---|---|
| **WLN** | French sovereign | 5.00% | 2.62 | 13.10 bps |
| **LAC** | US sovereign minerals | 3.96% | 3.10 | 12.28 bps |
| **ETL** | French sovereign | 5.00% | 2.35 | 11.75 bps |
| **ELUX-B** | Nordic consumer | 5.00% | 2.32 | 11.60 bps |
| **SUNAC** | China property | 5.00% | 2.10 | 10.50 bps |
| **HE** | US utility | 5.00% | 1.92 | 9.60 bps |
| **TMQ** | US sovereign minerals | 4.36% | 2.14 | 9.31 bps |
| **UREE** | US sovereign minerals | 3.29% | 2.71 | 8.91 bps |
| **MP** | US sovereign minerals | 3.42% | 1.90 | 6.49 bps |
| Cash | — | 60% | 1.00 | 0 |

Portfolio total: **40% invested**, expected **2.34× on invested capital
= 1.54× total NAV**.
