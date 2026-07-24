# Theory-Correctness Audit

Institutional-grade verification of the scanner's application of Godley/SFC and
Kalecki-Levy theory against the primary literature (two independent research
passes, sources cited inline). Confirmed-correct items, errors found, and the
fixes applied.

## Confirmed correct (verified verbatim against sources)

- **Three-balance identity & signs.** `government = fiscal balance` (deficit −),
  `foreign = −(current account)`, `private = CA − fiscal`; sums to zero. This
  is the canonical Godley-Cripps / New-Cambridge identity (Godley & Lavoie 2007
  ch. 2 transactions-flow matrix; Dos Santos & Macedo e Silva, Levy WP 594).
  *Caveat now documented in code:* the zero-sum is a construction identity and
  does not itself validate the data.
- **Kalecki-Levy profit signs.** A rising government **deficit** adds to profits
  (+); a **net-export surplus** adds to profits (+). Verified verbatim against
  S. Jay Levy, Levy WP 309, Table 2 (Kalecki "General Case").
- **Credit-impulse horizon pattern.** Positive IC at 3–12m turning contrarian
  at 24–36m is exactly the credit-boom→bust signature expected from Mian-Sufi-
  Verner (2017, QJE) and Baron-Xiong (2017, QJE, credit expansion → crash risk).
- **Process 3 labelling.** Real money-stock growth is Godley's Seventh-Processes
  measure #3; credit/net-lending is #2. Correct.

## Errors found and fixed

1. **Credit impulse — denominator bias (FIXED).** The canonical Biggs-Mayer-Pick
   (2010) impulse is Δ(credit *flow*) ÷ GDP *level*. We held only the BIS
   credit/GDP *ratio* C = D/Y and differenced it; but Δ(D/Y) ≠ ΔD/Y — they differ
   by (D/Y)·(nominal GDP growth). In a recession, falling Y mechanically lifts C
   and manufactures a false positive impulse. **Fix** (`highfreq.credit_impulse`):
   recover the flow with `dD/Y ≈ Δ(D/Y) + (D/Y)·nominal_growth`, using nominal
   GDP growth (real + CPI) from the annual history. The corrected series keeps
   the momentum→contrarian pattern and *sharpens* the 3-year contrarian signal
   (−0.083 → −0.105), more consistent with Baron-Xiong. The uncorrected version
   is retained as `credit_impulse_raw` for reference.

2. **CAB used where NX belongs in the Kalecki leg (FIXED/documented).** The
   Kalecki foreign profit term is **net exports (X−M)**, not the current account
   (which adds primary income + transfers — material for creditors/financial
   centres: Japan, Ireland, Switzerland). `backtest.reconstruct_score` now builds
   the profit-fuel leg from real net exports where available (falling back to CA
   only when the trade series is missing), and the separate "external" factor
   continues to track the CA as the *financing* leg. Documented inline.

3. **Real money growth — use log differences (FIXED).** Changed from the
   first-order subtraction of percentage changes to the exact geometric form
   `Δlog(M) − Δlog(CPI)` (matters at high inflation). Note: OECD broad money is
   the M3 concept; US M3 was discontinued 2006, so a strictly-US operational
   series should use M2/Divisia.

## Caveats documented (not errors, but institutional-grade transparency)

- **Household-saving omission.** The profit-fuel proxy retains investment + govt
  deficit + net exports but omits household saving (a large *negative* Kalecki
  term, unavailable cross-country at annual frequency from IMF/WB). It is
  therefore biased optimistic in saving-shock years (2008–09, 2020–21).
- **Expanding-window z-score.** No look-ahead and correct for backtest integrity,
  but it is time-series standardisation: it does not neutralise a common global
  cycle and is sensitive to trends/breaks. Cross-sectional z-scoring controls the
  global factor but loses own-history extension; institutional practice often
  double-standardises. The live scanner z-scores cross-sectionally; the backtest
  z-scores time-series — each appropriate to its use.

## New measures added from the audit's framing

- **Excess liquidity (`highfreq.excess_liquidity`)** — valuation-expansion fuel:
  nominal broad-money growth − nominal GDP growth (the Marshallian-K impulse).
  Money created beyond transaction needs spills into asset prices via the
  Brainard-Tobin portfolio channel (multiple expansion, not profit growth).
  Validates: caught the 2020–21 QE surge (+24% for the US) and leads equity
  returns at IC +0.083/+0.092/+0.071 at 3/6/12 months.
