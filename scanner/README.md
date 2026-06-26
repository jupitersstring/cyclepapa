# Godley Bull-Market Scanner

A stock-flow-consistent (Godley / SFC) framework for detecting bull and bear
**regimes** in capital markets *before* they translate into asset prices —
in unit-free, archetype-conditional terms.

## Thesis

Godley's sectoral identity always holds:

```
(G - T)  ==  (S - I)  +  (M - X)
fiscal   ==  private    +  external (foreign) net lending
```

Asset prices rise where net new financing into the private sector is expanding
and accelerating, and where that fuel translates into actual corporate profits.
The Kalecki-Levy profits identity (Jerome Levy 1908; Kalecki 1935; unified by
Minsky 1960s; contemporary application by the Levy Forecasting Center) makes
that translation explicit:

```
Profits = + Investment
          + Government Deficit              ( = -Government Saving )
          + Net Exports                     ( = -Foreign Saving    )
          + Dividends paid
          - Household Saving
```

This is a national-accounts identity, not a model estimate. Every term on the
right contributes purchasing power to the corporate sector — and every term
maps cleanly to a public-data series.

## What's modelled

| Layer | What it does |
|------|--------------|
| **Archetypes** | 9 Godley sectoral configurations (+ sanctioned residual) covering 56 countries — the *same indicator means opposite things* in different sectoral configurations, so factor weights tilt by archetype |
| **Kalecki-Levy profit leg** | Per-country trajectory of the 5 profit sources + a named-policy registry mapping each fiscal/legislative event to the lever it pulls (the **qualitative+quantitative leg**) |
| **Opportunity composite** | 7-factor cross-sectional score; profit-fuel is now the highest-weighted term (the mechanical bridge to EPS) |
| **Seven Unsustainable Processes** | Godley's actual 1999 screen as a live diagnostic — flags lit per country, with `godley_warning = flags_lit >= 4` |

## The composite

```
Opportunity = +0.25 * ProfitFuel_z           Kalecki-Levy (NEW)  *** dominant ***
            + 0.20 * CreditImpulse_z
            + 0.15 * Institutional            (IRS / 5, status-weighted)
            + 0.15 * ValuationGap_z
            + 0.10 * CarryCushion_z
            - 0.15 * Crowding_z
            - 0.05 * SuddenStopRisk_z
```

The two negative terms keep the model from buying crowded-and-priced consensus
trades. Archetype-conditional tilts (e.g., `profit_fuel *= 1.3` for mercantilist
savers; `*= 0.5` for MNC-distorted entrepôts) live in `composite.ARCHETYPE_TILTS`.

## File layout

| File | Role |
|------|------|
| `archetypes.py` | The 9 Godley archetypes + 56-country mapping + ETF tickers for backtesting |
| `transforms.py` | Unit-bias removal pipeline (%GDP → annualised Δ → z-score → percentile → diffusion) |
| `data.py` | June 2026 factor panel (BIS LBS / IMF FM / ECB / ONS / PBoC / IIF prints + calibrated estimates flagged `estimated=True`) |
| `kalecki_levy.py` | Profit-equation components + named-policy registry (the new leg) |
| `composite.py` | Opportunity score, archetype tilts, regime classifier |
| `seven_processes.py` | Godley's 1999 diagnostic as a live country-level flag count |
| `regime.py` | Practitioner overlay: Keen accelerator + Dalio debt-cycle stage + Marathon capex-squeeze + Napier financial-repression + NBFI continuous-leverage score |
| `godley_projection.py` | Godley 1999 Appendix 2 stock-projection method, automated — endogenous NII feedback, 5y NIIP trajectory, one-sided unsustainability score |
| `tobin_q.py` | Endogenous Tobin's q per Godley-Lavoie ch.11; closes the equity-prices-validate-investment loop |
| `sfc_integrity.py` | Quadruple-bookkeeping consistency check + per-country tolerance band + data-confidence label |
| `sources/` | Stub data adapters documenting the live-wiring path for BIS / FRED-Z.1 / Eurostat / IMF — calibrated fallback values today |
| `app.py` | Streamlit dashboard + CLI fallback |

## Run

```bash
python3 -m scanner.app                  # CLI
pip install streamlit && streamlit run scanner/app.py
```

## Current call (June 2026 dataset)

After adding the Kalecki-Levy leg, the ranking shifts:

| Rank | Country | Why |
|------|---------|-----|
| 1 | Brazil | Cheapest CAPE + highest real carry + Selic easing cycle + 33% of EMDE Q4 cross-border credit |
| 2 | **Germany** ↑ | €500bn debt-brake fund → profit-fuel 4.1 (Investment + Govt Deficit); still light positioning |
| 3 | **South Korea** ↑ | Lee's KRW150tn AI fund + **Value-Up 2.0 mandatory treasury-share cancellation** → profit-fuel 4.3 (Dividends leg) |
| 4 | Saudi Arabia ↓ | Tadawul opening intact but **PIF capex cut −$41bn (NEOM down)** weighs on profit-fuel via Investment leg |
| 5 | Mexico | Plan México 41-91% capex deduction; USMCA overhang on net exports |
| Avoid | UK | Reeves consolidation + household-saving surge 2.5%→9.9% → **profit-fuel −1.1** (textbook Godley trap) |
| Avoid | US | Levy Forecasting Center (Jun 2025) flagged tariff-driven profit contraction; SCOTUS Feb 2026 only partial reprieve |
| Avoid | China | 4% deficit + RMB12tn support **offset by household-saving surge** → profit-fuel 0.0 |
| Avoid | India | SWAGAT-FI catalyst real but 75% valuation premium + $26bn FPI outflows still in train |
| Avoid | Japan | Profit-fuel highest on board (5.8) but TOPIX >1σ rich, short-yen $10.1bn crowded |

Of countries with `flags_lit >= 3` (Godley warning territory):
**Brazil (4), Poland (3), Turkey (3)** — all H/I archetypes running on external-credit fuel.

## Going live

`data.py::default_panel()` and `kalecki_levy.py::_COMPONENTS` ship June 2026
snapshots. Replace with loaders pulling:

| Component | Source / FRED mnemonic |
|-----------|------------------------|
| Investment | BEA NIPA T 1.1.5 L7 (`GPDI`) for US; OECD QNA equiv for others |
| Government deficit | T 3.1 L26 net gov saving (`NGSAVE`, flip sign) |
| Net exports | T 1.1.5 L15 (`NETEXP`); broader CA via T 4.1 L29 (`NETFI`) |
| Dividends | T 1.14 L14 (`DIVIDEND`) |
| Household saving | T 2.1 L34 (`PMSAVE`) |
| Corporate profits w/ IVA+CCAdj (LHS validation) | T 1.14 L11 (`CPROFIT` / `A445RC1`) |
| Credit impulse | BIS LBS cross-border credit, YoY %, by borrower country |
| Carry cushion | (policy rate − inflation), FX-vol adjusted — FRED / IMF IFS |
| Crowding | Fund-manager survey net OW, z-scored |
| Sudden-stop risk | FX-mismatch + external-debt-service / reserves |

NAFA decomposition is constructed from US Z.1 sector tables (F.101 households,
F.103 nonfin corp, F.104 nonfin noncorp, F.106 federal, F.107 state-and-local,
F.133 RoW); identity `NAFA - NIL ≈ S - I` holds up to statistical discrepancy.

## Foundational references

- Wynne Godley, *Seven Unsustainable Processes*, Levy Strategic Analysis, Jan 1999.
  https://www.levyinstitute.org/pubs/sr/sevenproc.pdf
- David A. Levy, Martin P. Farnham, Samira Rajan, *Where Profits Come From*,
  Jerome Levy Forecasting Center, 2008. https://www.levyforecast.com/assets/Profits.pdf
- S. Jay Levy, *Profits: The Views of Jerome Levy and Michał Kalecki*,
  Levy Institute WP 309, 2000. https://www.levyinstitute.org/pubs/wp309.pdf
- Marc Lavoie & Wynne Godley, *Kaleckian Models of Growth in a Coherent SFC
  Framework*, JPKE 24(2), 2001–02.
  https://www.levyinstitute.org/pubs/Lavoie%20Godley_2001-02.pdf
- Robert Parenteau, *US Household Deficit Spending*, Levy PPB 88, 2006.
- Francesco Zezza, *OPENSIMPLEST: The Smallest SFC Open Economy Model*,
  Levy WP 1105, Jan 2026. https://www.levyinstitute.org/wp-content/uploads/2026/01/wp_1105.pdf
- Levy Forecasting Center, *How High Tariffs, Trade War, and Uncertainty Will
  Impact Profits*, June 2025 (current bearish profit-cycle call).

### Godley corpus references (added in the deep-dive pass)

- Wynne Godley, *Seven Unsustainable Processes: Medium-Term Prospects and
  Policies for the United States and the World*, Levy Strategic Analysis,
  January 1999 (updated October 1999), incl. Appendix 2 "Note on the Models
  Employed" — the forward-projection methodology that `godley_projection.py`
  automates. https://www.levyinstitute.org/pubs/sr/sevenproc.pdf
- Wynne Godley, *Maastricht and All That*, London Review of Books, 8 October
  1992 — the load-bearing critique of monetary-union-without-fiscal-union,
  which motivates the EZ MacDougall/RRF policy entries in
  `kalecki_levy.POLICIES`. https://www.lrb.co.uk/the-paper/v14/n19/wynne-godley/maastricht-and-all-that
- Wynne Godley & Marc Lavoie, *Monetary Economics: An Integrated Approach to
  Credit, Money, Income, Production and Wealth* (Palgrave Macmillan, 2007) —
  chapters 3 (V*/YD wealth-target consumption), 5 (Brainard-Tobin portfolio
  choice), 11 (Tobin's q investment closure). Drives `tobin_q.py` and the
  V*/YD diagnostic in `kalecki_levy.wealth_norm_saving_pressure`.
- Marc Lavoie & Wynne Godley, *Kaleckian Models of Growth in a Coherent
  Stock-Flow Monetary Framework*, JPKE 24(2), 2001–02.
  https://www.levyinstitute.org/pubs/Lavoie%20Godley_2001-02.pdf
- Levy Institute Strategic Analysis series 1996–2010 (Godley, Papadimitriou,
  Zezza, Hannsgen, Nikiforos, Yajima) — the multi-country SFC tradition the
  scanner inherits.

### Practitioner overlay sources (regime.py)

- Steve Keen, *How He Saw It Coming, and Others Did Not* (INET, 2025);
  "Gaslighting us on private debt" (Substack, Nov 2025) — credit accelerator
  is the load-bearing 2nd-derivative variable, not the impulse.
- Ray Dalio, *Principles for Navigating Big Debt Crises* (2018) — six-stage
  long-term debt cycle, 48 historical case studies; stage determines the
  meaning of the same Opportunity score.
- Edward Chancellor (ed.), *Capital Returns: Investing Through the Capital
  Cycle* (Marathon Asset Management, 2002–15) — multi-year capex
  contraction is the contrarian bull signal for incumbents (oil 2014→2020,
  mining 2010→2020, semis equipment 2018→2022 case studies).
- Russell Napier, *We Are Headed Towards a System of National Capitalism*
  (themarket.ch interview); Hidden Forces podcast 2024–2025 — 15–20 year
  leitmotif of governments directing captive savings to defense / energy /
  reshoring; real-deposit-rate compression is the actionable proxy.
- Lyn Alden, June 2026 newsletter *The Wild West*; March 2026 *A Flywheel
  of Chaos* — fiscal-dominance lens, three-pillar portfolio mapping to
  inflation regime quadrants.
- Brad Setser, *Follow the Money* (CFR), Feb 2026 China backdoor
  intervention $100bn; *China's Data Still Doesn't Add Up* — F-archetype
  BoP data needs a credibility haircut (~$500bn hidden surplus).
- Bank of England staff WP, *An Anatomy of the 2022 Gilt Market Crisis*
  (2023) — LDI/pension sub-sector concentration was the under-tracked
  variable; motivates the NBFI flag.
