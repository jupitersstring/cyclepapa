# Measures Audit — 2026-09-06 (audit #6): the ETA ranking chain

Focus: `entry_today_asymmetry` (ETA) — the #1 ranking key of every top-N book —
and the scoring primitives feeding it (upside/downside legs, post-rally factor).
Method: full formula trace of asymmetry_rank.compute_asymmetry + the ETA block in
enrich, then empirical extreme-case tests on the live master.
Harness after: **41 checks, 0 FAIL, 0 WARN**.

## Finding 1 (P0): stale momentum double-corrupts ETA
`momentum_12m` correlates only **0.13** with the fresh Lynch tape (`roc_12m`) —
it freezes while the Lynch drive owns the Yahoo budget. Concrete: UTZ stored
−44% vs live **+38%**; EOLS −35% vs **+44%**; JET2.L −37% vs +15%. 37% of names
are >25pp apart, 18% are >50pp apart.

Momentum feeds ETA **twice**:
- `u_mom` — upside leg of `asymmetry_score` (computed in rebuild_scores).
- `post_rally_factor` — the anti-chasing multiplier applied in enrich.

The dangerous direction: a name that has **already run** (fresh momentum high) but
shows stale-negative momentum **escapes the rally penalty** and ranks as a fresh
"entry today" — the exact failure the measure exists to prevent.

**Fix:** momentum_12m is now refreshed from the live Lynch tape (fraction scale,
same as momentum) wherever the tape is fresh — in **rebuild_scores before
compute_asymmetry** (so u_mom is fresh in-pass) AND in **enrich before the ETA
block** (so post_rally_factor is fresh). 27,091 rows refreshed. Verified: UTZ/EOLS/
JET2 momentum now match live; ETA recomputed accordingly (EOLS correctly falls to
0 — a biotech with no downside floor should not rank).

## Finding 2 (P1): 1,592 leveraged loss-makers falsely credited "low debt"
The downside-floor `d_low_debt` leg fired on `net_debt_ebitda < 1.5`. A loss-maker
with real debt produces a **negative** ratio (negative-EBITDA denominator) that
spuriously passes `< 1.5`, so the framework credited balance-sheet safety to
exactly the names most at risk. The sign of EBITDA is the discriminator: a negative
ratio with **positive** margin is genuine net cash (JET2.L at −2.2, +13% margin —
correctly kept); a negative ratio with **negative** margin is a distressed
borrower (1,592 names — now rejected).

**Fix:** the net_debt_ebitda path now requires `ebitda_margin > 0`; the
debt/equity path stays unconditional. Verified: 0 loss-makers credited via the
nde path (was 1,592).

## Finding 3 (P2): rebuild_scores was an un-versioned master writer
The atomic + version-store sweep from audit #4 missed rebuild_scores.py — it wrote
the master with a plain `to_csv`, the same torn-read hazard. Now routed through
`versioned_replace` (atomic + pre-image snapshot) like the other four writers.

## Checked and cleared
- Negative book-equity sub-book credit: 0 rows (pb already cleaned upstream).
- insider_ownership_pct scale: fraction form, 0.1% >1.0 — sane.
- Pre-revenue/negative-EBIT biotech in ETA top-500: 4 of 500 (1%) — the
  is_pharma_bio filter holds; the 4 survivors clear the revenue/margin floor.
- Renormalised weighting (`_weighted_renormalised`): missing components correctly
  drop out of both numerator and denominator — no missing-data penalty.
- Geometric-mean asymmetry (sqrt(upside·downside)): both legs must be present,
  as designed — no-floor names score 0, confirmed on EOLS.

## Note
The quote-time `price` column itself remains stale (median ~5%) until the
price-refresh enrichers resume after the Lynch drive completes (~1.5k names left);
that lag no longer reaches momentum or the 52w display, which now come from the
live per-name tape.
