"""Export per-country time series for the interactive charts HTML."""

from __future__ import annotations

import json
import sys

from . import backtest as BT
from . import highfreq as HF
from .sources import prices as PX
from .archetypes import lookup

# Long-history countries worth charting interactively.
CHART_ISOS = ["US", "DE", "JP", "GB", "KR", "FR", "AU", "CA",
              "IT", "ES", "MX", "ZA", "SE", "NL", "CH"]


def _clean(series):
    return [None if (v != v) else round(float(v), 3) for v in series]


def build() -> dict:
    out = {}
    for iso in CHART_ISOS:
        sc = BT.reconstruct_score(iso)
        px = PX.annual_prices(iso)
        if sc is None or px is None:
            continue
        yrs = [int(y) for y in sc.index if 1985 <= y <= 2024]
        ann = {
            "years": yrs,
            "gscore": _clean([sc.loc[y, "gscore"] for y in yrs]),
            "profit_fuel": _clean([sc.loc[y, "profit_fuel"] for y in yrs]),
            "external": _clean([sc.loc[y, "external"] for y in yrs]),
            "valuation": _clean([sc.loc[y, "valuation"] for y in yrs]),
            "credit": _clean([sc.loc[y, "credit"] for y in yrs]),
            "price": _clean([float(px[y]) if y in px.index else float("nan") for y in yrs]),
        }
        rec = {"country": lookup(iso).name, "annual": ann}
        # high-frequency
        rmg = HF.real_money_growth(iso)
        if rmg is not None:
            rec["money"] = {
                "t": [round(d.year + (d.month - 1) / 12, 3) for d in rmg.index],
                "v": _clean(rmg.values)}
        ci = HF.credit_impulse(iso)
        if ci is not None:
            rec["credit_impulse"] = {
                "t": [round(d.year + (d.month - 1) / 12, 3) for d in ci.index],
                "v": _clean(ci["credit_impulse"].values)}
        out[iso] = rec
    return out


if __name__ == "__main__":
    d = build()
    path = sys.argv[1] if len(sys.argv) > 1 else "scanner/timeseries_data.json"
    with open(path, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    print(f"wrote {path}: {len(d)} countries")
