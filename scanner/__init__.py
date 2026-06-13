"""
Godley Bull-Market Scanner
==========================

A stock-flow-consistent (Godley/SFC) framework for detecting bull and bear
*regimes* in capital markets before they translate into asset prices.

The core thesis (Godley): asset-price appreciation is fuelled by incremental
purchasing power entering private balance sheets. That fuel has two legs --
external (cross-border bank credit, portfolio flows, FDI) and internal
(domestic credit creation) -- and is modulated by who is trying to net-save
(the sectoral balances identity).

This package turns that thesis into a scored, unit-free, archetype-conditional
country panel and ranks tradable opportunities.

Modules
-------
archetypes   : country -> Godley sectoral archetype taxonomy
transforms   : unit-bias removal pipeline (%GDP -> annualised change -> z -> pct)
data         : default dataset (live figures, June 2026) + loader hooks
composite     : the six-factor Opportunity score + regime classifier
app          : Streamlit dashboard
"""

__version__ = "0.1.0"
