# Measure False-Positive / Inflation Audit — 2026-09-08

Hunt: names that pass the *letter* of a measure but violate its *spirit* —
inflated by data artifacts, sign flips, one-offs, or base effects. Evidence is
empirical (counts over the live master + archetype_tags). Ranked by impact.

---

## 1. BUG — `ev_ebitda` ignores the sign of EBITDA (1,709 names)
`ev_ebitda` is **positive and small** for companies with **negative** EBITDA, so
loss-makers read as ultra-cheap. Examples: CTTMF (EV 1.75M / EBITDA −4.0M) shows
`ev_ebitda = 0.175`; 6986.T (EV 8.5B / EBITDA −1.27B) shows `1.17`. A negative
EBITDA must give a negative (meaningless) multiple; instead it's a "cheap" one.

This is not cosmetic — `ev_ebitda ≤ threshold` is a cheapness gate in **QARP,
Wolf-Compounder, Mid-Cap+ GARP (EBITDA/EV yield), EV/Sales-derating**, and it
feeds the cheapness composite. **19 of the ETA top-500** carry this flip.

**Fix (do now):** at the source, force `ev_ebitda = NaN` (or keep it negative)
whenever `ebitda_ttm ≤ 0`; and gate every EV/EBITDA cheapness leg on
`ebitda_ttm > 0`. Same treatment for the derived EBITDA/EV yield in GARP.

## 2. Capital-return funded beyond cash flow (985 / 5,186 = 19%)
Nearly a fifth of `arch_capital_returner` firers pay dividends/buybacks while
**FCF is negative** — distributing cash they don't generate (funded from the
balance sheet or debt). That is the opposite of the archetype's spirit (a
business returning the cash it earns). 18 reach the ETA top-500.

**Proposal:** require `fcf_yield > 0` for the archetype, or better, require
`capital_return_yield ≤ fcf_yield + small buffer` (returns are covered by FCF).
Add a `capital_return_covered` sub-flag so an uncovered payer is visibly demoted
rather than silently ranked.

## 3. Paper earnings yield not backed by cash (1,297 names)
Value screens reward a high E/P even when **FCF is negative** — accrual-heavy or
one-off earnings, not durable cash. `arch_lynch_pegy` 438/5,066 and
`arch_midcap_garp` 51/1,509 fire on `earnings_yield ≥ 8%` with `fcf_yield < 0`.
15 reach the ETA top-500.

**Proposal:** add a cash-backing condition to earnings-yield value legs —
`fcf_yield > 0` OR an FCF/NI conversion floor (e.g. ≥ 0.5 over the cycle). The
Mid-Cap+ GARP "good & growing earnings yield" leg should require the earnings be
cash-backed, matching its intent.

## 4. Inorganic / base-effect growth in growth archetypes
Huge single-year revenue growth is usually an **acquisition** or **recovery from
a crushed base**, not the durable organic scaling the multibagger thesis wants.
- `rev_yoy > +200%`: 740 names (rev_yoy is currently clipped only at +1000%).
- Revenue < $20M base (percentage growth ~meaningless): `tenbagger_path`
  351/4,282, `cheap_sales_scaler` 100/3,193, `exceptional_evsg` 88/1,883.
- 22 base-effect + 33 tiny-base names reach the ETA top-500.

**Proposals:** (a) tighten the rev_yoy clamp toward +100–150% for scoring;
(b) prefer **3-yr revenue CAGR** (smooths base effects and one-off M&A years)
over 1-yr YoY in the growth-scaling archetypes; (c) require a **minimum revenue
base** ($20–50M) for tenbagger/scaler/EVSG so a $5M company that doubled doesn't
qualify as a scalable grower; (d) where segment data exists, prefer organic
(same-segment) growth.

## 5. One-off margin swings in durability archetypes
A 20+ percentage-point one-year margin swing contradicts "Lindy / durable."
`arch_lindy_margin` 115/1,002 fire with `|ebitda_margin_delta| > 20pp` — almost
always restructuring, an asset sale, or an impairment reversal.
(`fixed_cost_demand_shock` 732/4,549 also, but there large swings are partly the
point — treat it more leniently than the Lindy family.)

**Proposal:** for the Lindy/durability archetypes, cap the single-year margin
contribution and require **multi-year margin stability** (low variance, positive
in ≥3 of 4 years) rather than a one-year jump.

## 6. Lynch-Reward single-leg domination (minor, 47 / 730)
One exceptional leg (`lynch_leg_max > 0.9`) carries names whose overall score is
weak (< 0.4) — a single-signal fire dressed as a multi-signal reward. Already
partly surfaced via `lynch_leg_max`.
**Proposal:** require ≥2 contributing legs for the archetype to fire, keeping the
single-leg names visible only through the explicit `lynch_exceptional_leg` column.

---

## Cross-cutting idea: a shared "cash-backing / sustainability" guard
Findings 2–3 are the same disease (a value/quality signal not backed by cash).
Rather than patch each archetype, add one reusable helper — `cash_backed(row)` =
FCF positive and covering the claimed distribution/earnings — and require it in
every leg whose spirit is "real, cash-generative" (capital-returner, GARP,
Lynch-PEGY, cash-quality). Keeps the definitions consistent and auditable, and
lets the methodology harness assert it (new checks: no uncovered capital-returner,
no negative-EBITDA "cheap" multiple).

## Suggested order
1. Fix #1 (ev_ebitda sign) — it's a bug and touches many archetypes. **Now.**
2. Add the cash-backing guard for #2 and #3.
3. Tighten growth base-effect handling (#4).
4. Lindy durability (#5), Lynch legs (#6) — tuning.
Each is measurable before/after by the counts above, and each earns a methodology
check so it can't regress.
