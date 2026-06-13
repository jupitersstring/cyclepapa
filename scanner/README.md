# Godley Bull-Market Scanner

A stock-flow-consistent (Godley / SFC) framework for detecting bull and bear
**regimes** in capital markets *before* they translate into asset prices —
expressed in unit-free terms so there's no size or currency bias.

## Thesis

Godley's insight: asset-price appreciation is fuelled by incremental purchasing
power entering private balance sheets. The sectoral identity always holds:

```
(G - T)  ==  (S - I)  +  (M - X)
fiscal   ==  private    +  external (foreign) net lending
```

Markets turn **bullish** where net new financing into the private sector is
expanding and accelerating; **bearish** where the private sector is forced back
toward surplus while credit decelerates. The fuel has two legs:

- **External**: cross-border bank credit (BIS LBS), portfolio flows, FDI.
- **Internal**: domestic credit creation (inside money).

## What makes it an *opportunity*, not just a flow

Fuel that's already been priced isn't an edge. The composite adds three
dimensions that convert a flow into a tradable setup, two of them with
**negative** weights:

```
Opportunity = +0.25 * CreditImpulse_z     external + internal fuel
            + 0.20 * Institutional         dated legislative catalyst (IRS / 5)
            + 0.20 * ValuationGap_z         cheap re-rates; expensive snaps
            + 0.15 * CarryCushion_z         FX-adjusted real-rate buffer
            - 0.15 * Crowding_z             consensus OW has no marginal buyer
            - 0.05 * SuddenStopRisk_z       FX-mismatch / rollover fragility
```

The negative terms are what stop the model buying the top of a consensus trade
(the India / Japan trap of mid-2026).

## Archetypes

Countries are grouped into nine Godley archetypes (+ a sanctioned residual)
because the *same* indicator means opposite things in different sectoral
configurations. A rising household saving rate is healing in a frontier economy
(I) but a fading consumption engine in an Anglo-mimic (B). `composite.py`
applies archetype-conditional tilts to each factor.

| Tag | Archetype | Example |
|-----|-----------|---------|
| A | Reserve-currency deficit absorber | US |
| B | Anglo-mimic deficit economy | UK, Australia |
| C | Mercantilist saver | Germany, Japan |
| D | Entrepot / MNC-distorted | Ireland, Singapore |
| E | EMU constraint trap | Italy, Greece |
| F | Directed-credit managed-FX | China, Vietnam |
| G | Commodity rent surplus | Saudi, Norway, Chile |
| H | Convergence capital-importer | Poland, Mexico, Brazil |
| I | Frontier dollar-dependent | Turkey, Egypt, Argentina |
| X | Sanctioned / closed | Russia, Iran |

## Run

```bash
# CLI (no extra deps beyond pandas/numpy)
python3 -m scanner.app

# Dashboard
pip install streamlit
streamlit run scanner/app.py
```

## Current call (June 2026 dataset)

Top setups: **Brazil** (cheapest CAPE + highest real carry + Selic easing cycle
+ 33% of EMDE cross-border credit), **Saudi Arabia** (mechanical forced-buyer
from QFI abolition + 49% cap review), **Germany** (light positioning into a
generational fiscal regime change). Avoid: **India / Japan / broad EM** — the
fuel is already priced and positioning is crowded.

## Going live

`data.py::default_panel()` ships a June 2026 snapshot (live figures + calibrated
estimates flagged `estimated=True`). Replace it with loaders pulling:

| Factor | Source |
|--------|--------|
| credit_impulse | BIS LBS cross-border credit, YoY %, by borrower country |
| institutional | `scanner.institutional` regime-event registry (planned) |
| valuation_gap | CAPE / forward-PE vs own 10–20y history |
| carry_cushion | (policy rate − inflation), FX-vol adjusted — FRED / IMF IFS |
| crowding | fund-manager-survey net overweight, z-scored |
| suddenstop_risk | FX-mismatch + external-debt-service / reserves |

Then backtest the composite's forward-return information coefficient against the
MSCI country ETFs in `archetypes.py` (EWZ, KSA, EWG, EWW, EPOL, EWJ, INDA, …),
grouped by archetype.
```
```
