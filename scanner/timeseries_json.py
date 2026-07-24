"""Export per-country time series for the interactive charts HTML."""

from __future__ import annotations

import json
import sys

import json as _json
from pathlib import Path as _Path

from . import backtest as BT
from . import highfreq as HF
from .sources import prices as PX
from .archetypes import lookup

# Current (to 2026) monthly ETF prices pulled from Yahoo, keyed by ISO.
_CURRENT = {}
_cp = _Path(__file__).resolve().parent / "_cache" / "prices_current.json"
if _cp.exists():
    _CURRENT = _json.loads(_cp.read_text())


def _annual_price_current(iso):
    """Year-end price to 2026 from current Yahoo data if available, else OECD."""
    if iso in _CURRENT:
        import pandas as pd
        s = pd.Series(_CURRENT[iso]); s.index = pd.to_datetime(s.index + "-01")
        yr = s.sort_index().groupby(s.index.year).last(); yr.index = yr.index.astype(int)
        return yr
    return PX.annual_prices(iso)

# Long-history countries worth charting interactively.
CHART_ISOS = ["US", "DE", "JP", "GB", "KR", "FR", "AU", "CA",
              "IT", "ES", "MX", "ZA", "SE", "NL", "CH"]


def _clean(series):
    return [None if (v != v) else round(float(v), 3) for v in series]


def build() -> dict:
    out = {}
    for iso in CHART_ISOS:
        sc = BT.reconstruct_score(iso)
        px = _annual_price_current(iso)   # current to 2026 via Yahoo where available
        if sc is None or px is None:
            continue
        # score frontier is 2024 (annual accounts lag); price runs to 2026
        pyears = [int(y) for y in px.index if 1985 <= y <= 2026]
        syears = [int(y) for y in sc.index if 1985 <= y <= 2024]
        yrs = sorted(set(syears) | set(pyears))
        sv = lambda y, k: sc.loc[y, k] if y in sc.index else float("nan")
        ann = {
            "years": yrs,
            "gscore": _clean([sv(y, "gscore") for y in yrs]),
            "profit_fuel": _clean([sv(y, "profit_fuel") for y in yrs]),
            "external": _clean([sv(y, "external") for y in yrs]),
            "valuation": _clean([sv(y, "valuation") for y in yrs]),
            "credit": _clean([sv(y, "credit") for y in yrs]),
            "price": _clean([float(px[y]) if y in px.index else float("nan") for y in yrs]),
            "score_frontier": 2024,
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
