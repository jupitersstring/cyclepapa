"""
FRED + Fed Z.1 + BEA NIPA adapter -- US Kalecki-Levy panel construction.

This module documents the exact set of FRED mnemonics needed to construct a
quarterly Kalecki-Levy decomposition for the US and an SFC-consistent panel
of sector net-lending series for Godley's Seven Processes. The mnemonics
below are verified against the BEA NIPA handbook (Table indices) and the
Z.1 statistical release.

Kalecki-Levy LHS (Profits w/ IVA + CCAdj)
    BEA Table 1.14 Line 11 -- FRED `A445RC1Q027SBEA` or `CPROFIT`

Kalecki-Levy RHS components
    Investment        BEA T 1.1.5 L7   FRED `GPDI`
        - non-residential  FRED `PNFI`
        - residential      FRED `PRFI`
        - inventories      FRED `CBI`
    Net exports       BEA T 1.1.5 L15  FRED `NETEXP`
    Government saving BEA T 3.1 L26    FRED `NGSAVE` (federal: `FGDEF`, S&L: `SLEXPND`)
    Personal saving   BEA T 2.1 L34    FRED `PMSAVE`  (rate: `PSAVERT`)
    Dividends         BEA T 1.14 L14   FRED `DIVIDEND` (`B056RC`)
    Foreign saving = -CA balance       FRED `NETFI` (BEA T 4.1 L29)

Z.1 sector net lending (quarterly, BOGZ1FA* series, 4Q rolling sum / GDP):
    Households + NPISH      F.101 line 18 -- `BOGZ1FA155000005Q`
    Nonfinancial corp       F.103 line 18 -- `BOGZ1FA105000005Q`
    Nonfinancial noncorp    F.104 line 18 -- `BOGZ1FA115000005Q`
    Financial business      F.79  line 18 -- `BOGZ1FA795000005Q`
    Federal government      F.106 line 18 -- `BOGZ1FA315000005Q`
    State + local govt      F.107 line 18 -- `BOGZ1FA215000005Q`
    Rest of the world       F.133 line 18 -- `BOGZ1FA265000005Q`

SFC consistency unit test (Godley & Lavoie ch.1):
    |sum(all seven sector NL flows)| < max(0.5%, 2*hist_5y_stdev_discrepancy)
    of GDP per quarter. The Z.1 statistical discrepancy is published at
    Table F.7; in 2020-2025 it ran ~0.5-1.0% of US GDP at quarterly frequency.
"""

from __future__ import annotations

import pandas as pd


# Mnemonic registry so the upstream caller can iterate cleanly.
US_KALECKI_LEVY_MNEMONICS: dict[str, str] = {
    "profits_iva_ccadj":     "A445RC1Q027SBEA",   # T 1.14 L11
    "gross_priv_dom_inv":    "GPDI",              # T 1.1.5 L7
    "nonres_fixed_inv":      "PNFI",
    "res_fixed_inv":         "PRFI",
    "inventory_change":      "CBI",
    "net_exports":           "NETEXP",            # T 1.1.5 L15
    "net_gov_saving":        "NGSAVE",            # T 3.1 L26
    "personal_saving":       "PMSAVE",            # T 2.1 L34
    "personal_saving_rate":  "PSAVERT",
    "net_dividends":         "DIVIDEND",          # T 1.14 L14
    "ca_balance":            "NETFI",             # T 4.1 L29
}

US_Z1_SECTOR_NL_MNEMONICS: dict[str, str] = {
    "hh_npish":         "BOGZ1FA155000005Q",
    "nonfin_corp":      "BOGZ1FA105000005Q",
    "nonfin_noncorp":   "BOGZ1FA115000005Q",
    "financial":        "BOGZ1FA795000005Q",
    "federal_gov":      "BOGZ1FA315000005Q",
    "sl_gov":           "BOGZ1FA215000005Q",
    "row":              "BOGZ1FA265000005Q",
}


def pull_us_kalecki_levy(api_key: str | None = None) -> pd.DataFrame | None:
    """
    Live US Kalecki-Levy panel. Requires `fredapi` (added in requirements).

    LIVE flow (commented stub):

        from fredapi import Fred
        fred = Fred(api_key=api_key)
        rows = {k: fred.get_series(v) for k, v in US_KALECKI_LEVY_MNEMONICS.items()}
        df = pd.DataFrame(rows).resample("QS").mean()
        gdp = fred.get_series("GDP")
        return df.div(gdp, axis=0) * 100  # %GDP

    CURRENT: returns None to signal "not wired"; downstream falls back to
    the calibrated `_COMPONENTS` row in kalecki_levy.
    """
    return None


def pull_us_sector_nl(api_key: str | None = None) -> pd.DataFrame | None:
    """Live Z.1 sector net-lending panel; same pattern as above."""
    return None
