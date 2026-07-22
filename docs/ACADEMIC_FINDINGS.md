# Academic literature review — post-reorg & special-situations investing

A structured review of the SSRN / academic literature on post-bankruptcy
equity, distress-risk, forced selling, and quality/value factors, mapped to
concrete improvements for the cyclepapa screener. 96 papers surveyed across
seven themes; the convergent, implementable findings are below with the
papers behind them.

## The single most important recalibration

**Eberhart, Altman & Aggarwal (1999), "The Equity Performance of Firms
Emerging from Bankruptcy" (JF)** — 131 emergers show large positive abnormal
returns concentrated in the **first ~200 trading days (~9–10 months)** after
relisting. This is the academic anchor for the whole strategy: the alpha
window is **front-loaded**, not multi-year.

→ **Our Q2 forced-seller-overhang window was 24 months — far too long.** The
literature says the live window is ~10 months. Tightening it makes "live
overhang" mean what the data says it means.

**Jiang, Wang & Yang (2023), "The Disappeared Outperformance of Post-Reorg
Equity"** — for *exchange-listed* post-reorgs the naive "post-reorg
outperforms" edge has largely **disappeared**; the residual edge is in
**cross-sectional selection** and in the window where **unnatural/forced
owners still dominate the register** (low-but-rising institutional %).

→ Don't assume a category premium; lean on selection (exactly what the
six-question screen does) and treat institutional-ownership uptake as the
timing/exit gate.

## Improvements, by module area (priority-ordered)

### P0 — Quantitative Chapter-22 veto via Altman Z″ (postreorg_score.py)
Our Chapter-22 veto was purely historical (a name re-appearing in PACER).
The literature gives a *predictive* test:
- **Altman (2013 update) & "Chapter 22 Recidivism"** — compute the
  non-manufacturer **Z″ = 3.25 + 6.56·(WC/TA) + 3.26·(RE/TA) + 6.72·(EBIT/TA)
  + 1.05·(MVE/TL)**; **Z″ < ~1.1 = distress zone → veto** (high re-filing
  risk). Base-rate of Chapter 22 is ~15–18% (Hotchkiss; LoPucki).
- **Hotchkiss (1995), "Postbankruptcy Performance and Management Turnover"**
  — >40% of emergers still report operating losses 3yrs out; ~32% re-file or
  restructure again; **retaining pre-petition management predicts worse
  outcomes.**

### P0 — Piotroski F-score quality gate (postreorg_score.py / Q6)
- **Piotroski (2000), "Value Investing: The Use of Historical Financial
  Statements"** — the 9-point F-score works **best in the distressed / low-
  price universe** (our exact set). **Require F ≥ 5 (ideally ≥ 7); veto
  F ≤ 2.** Complements, not replaces, the Verdad EBIT-yield tier.

### P0 — Recency window = ~10 months (listed_equity_screen.py / Q2)
Retune `OVERHANG_MONTHS` from 24 → ~10 (200 trading days), per Eberhart et al.
and echoed by every theme. Beyond the window a name is still a post-reorg but
the overhang has cleared — de-rate, don't flag it "live".

### P1 — Verdad EBIT-yield tiers (already implemented — confirmed)
- **Verdad / Rasmussen (2020), "Post-Reorg Equities"** — EBIT/EV **> 20% →
  +61% avg 2yr; 0–20% → neutral; < 0% → −21%.** Barbell/right-skewed outcome
  distribution. Directly validates our Q6 tiers and the skew/downside lenses.
- **Loughran & Wellman (2011), "The Enterprise Multiple Factor"** — EV/EBIT(DA)
  (which nets cash, adds debt) is the correct value multiple for levered /
  post-reorg names; cheap bucket ≈ EM < ~7×.

### P1 — Earnings-quality & investment-discipline vetoes (postreorg_score.py)
- **Sloan (1996), accruals anomaly** — require **low accruals / high cash-
  conversion** (accruals = (NI − CFO)/TA); fresh-start accounting can inflate
  reported EBIT, so gate on cash. → sharpens Q4 (overstated earnings).
- **Cooper, Gulen & Schill (2008), asset growth** — **veto top-quintile asset
  growth** (re-levering / empire-building post-emergence).
- **Novy-Marx (2013), gross profitability** — add **GP/A** as a quality axis;
  robust to fresh-start restatement (top of the income statement).

### P1 — Debt-paydown *trajectory*, not static snapshot (Q3)
- **Verdad, "Forecasting Debt Paydown Among Leveraged Equities"; Chingono &
  Rasmussen, "Leveraged Small Value Equities"** — reward **YoY debt reduction
  (balance-sheet-in-repair)**, not merely a low-but-flat net-debt. Cheap +
  small + de-levering is the winning combination.

### P1 — Forced-selling microstructure (Q2 / Q4 sizing)
- **Chen, Noronha & Singal (2004), index additions/deletions** — a recent
  **index deletion** is a decaying forced-seller overhang (~15% depression
  for S&P, ~5% Russell, decaying ~2 months) that reverts. → a discrete Q2
  entry signal / catalyst.
- **Shleifer (1986), "Do Demand Curves for Stocks Slope Down?"** — overhang
  magnitude ≈ (shares distributed to unnatural owners / float), elasticity
  ≈ 1. → sizes Q4.
- **Coval & Stafford (2007), "Asset Fire Sales"; Lou (2012), flow-induced
  trading** — buy into flow/mandate-driven forced selling; reversal horizon
  ~12–20 months. → holder-flow overhang detection (needs 13F holder base).

### P1 — Structural-origin vetoes (emergence_master.py / postreorg_score.py)
- **Kolb & Tykvová (2016) et al., de-SPAC long-run underperformance** — a
  **SPAC-origin listing is structurally negative** (the opposite of a healthy
  orphan). Add a de-SPAC veto/penalty.

### P2 — Analyst-neglect & information-uncertainty tilts (ranking)
- **Hong, Lim & Stein (2000), "Bad News Travels Slowly"** — low analyst
  coverage (≤1–2) amplifies drift; a tailwind **only when combined with
  quality**. → coverage-count input to the conviction/asymmetry lens.
- **Zhang (2006), information uncertainty** — build an info-uncertainty score
  (age since relisting, coverage, forecast dispersion) as a **multiplier** on
  positive catalysts (Q5), not a standalone signal.

### P1 — Buyback catalyst gated by value (Q5)
- **Ikenberry, Lakonishok & Vermaelen (1995)** — open-market repurchase drift
  (~4yr) accrues **only to cheap names**; ~zero drift for expensive ones. →
  weight the Q5 buyback signal by Q6/valuation.

## Cross-cutting takeaways
1. **The window is ~10 months, not 2 years** — retune the overhang clock.
2. **Make the Chapter-22 veto predictive (Z″), not just historical.**
3. **Add F-score + gross-profitability + accruals** — quality beyond EBIT/EV,
   robust to fresh-start distortion.
4. **Reward de-levering *trajectory*, veto asset-growth / re-levering.**
5. **Institutional-ownership uptake is the exit gate**; de-SPAC origin is a veto.

## Top reading (cite these)
- Eberhart, Altman & Aggarwal (1999), *J. Finance* — emergence abnormal returns, ~200-day window.
- Jiang, Wang & Yang (2023, SSRN) — disappeared outperformance; ownership-uptake gate.
- Hotchkiss (1995), *J. Finance* — postbankruptcy performance & management turnover.
- Altman (Z″) + "Chapter 22 Recidivism" — predictive re-filing veto.
- Piotroski (2000), *J. Accounting Research* — F-score in distressed value.
- Campbell, Hilscher & Szilagyi (2008), *J. Finance* — "In Search of Distress Risk" (CHS).
- Novy-Marx (2013), *JFE* — gross profitability.
- Sloan (1996), *Accounting Review* — accruals anomaly.
- Cooper, Gulen & Schill (2008), *J. Finance* — asset growth.
- Chen, Noronha & Singal (2004), *J. Finance* — index deletions / forced selling.
- Coval & Stafford (2007), *JFE* — asset fire sales.
- Verdad / Rasmussen — Post-Reorg Equities; Leveraged Small Value; Debt Paydown.

_Sourced from SSRN / academic journals via the postreorg-academic-research
workflow (96 papers, 7 themes)._
