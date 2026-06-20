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
