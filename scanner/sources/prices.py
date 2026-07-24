"""
Historical equity-price loader -- OECD national share-price indices via the
keyless DBnomics API (aggregator of OECD MEI; one request returns many
countries, monthly, back to the 1950s-1980s).

Broader and longer than country ETFs: the OECD share-price index
(SPASTT01.IXOB.M) is the whole national equity market, ~40 economies including
the big EMs -- the "broad and integral" source the backtest needs to align
against decades of World Bank + IMF sectoral history.

    https://api.db.nomics.world/v22/series/OECD/MEI/USA+DEU+...SPASTT01.IXOB.M
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "prices.json"

# Panel ISO2 -> OECD ISO3. Only economies OECD MEI share prices cover.
ISO2_TO_OECD = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "JP": "JPN", "KR": "KOR", "CN": "CHN",
    "BR": "BRA", "MX": "MEX", "IN": "IND", "ID": "IDN", "PL": "POL", "HU": "HUN",
    "CZ": "CZE", "TR": "TUR", "SA": "SAU", "ZA": "ZAF", "AU": "AUS", "CA": "CAN",
    "NZ": "NZL", "FR": "FRA", "IT": "ITA", "ES": "ESP", "PT": "PRT", "GR": "GRC",
    "NL": "NLD", "BE": "BEL", "AT": "AUT", "FI": "FIN", "DK": "DNK", "SE": "SWE",
    "CH": "CHE", "IE": "IRL", "LU": "LUX", "NO": "NOR", "RU": "RUS", "CL": "CHL",
    "CO": "COL",
}
_OECD_TO_ISO2 = {v: k for k, v in ISO2_TO_OECD.items()}


def _dbnomics_batch(iso3s: list[str], tries: int = 3) -> dict:
    """Fetch many national share-price indices in one DBnomics call."""
    codes = "+".join(iso3s)
    url = (f"https://api.db.nomics.world/v22/series/OECD/MEI/"
           f"{codes}.SPASTT01.IXOB.M?observations=1&limit=300")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "godley-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.load(r)
            out = {}
            for s in d["series"]["docs"]:
                iso3 = s["series_code"].split(".")[0]
                per, val = s["period"], s["value"]
                out[iso3] = {p[:7]: round(float(v), 4)
                             for p, v in zip(per, val)
                             if v is not None and v == v}
            return out
        except Exception:
            time.sleep(2.0 * (i + 1))
    return {}


def refresh(isos: list[str], polite: float = 1.2) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    want = [ISO2_TO_OECD[i] for i in isos if i in ISO2_TO_OECD and i not in store]
    for j in range(0, len(want), 10):
        grp = want[j:j + 10]
        res = _dbnomics_batch(grp)
        for iso3, series in res.items():
            iso2 = _OECD_TO_ISO2.get(iso3)
            if iso2 and series:
                store[iso2] = series
        _CACHE.write_text(json.dumps(store))  # incremental
        time.sleep(polite)
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def annual_prices(iso2: str) -> pd.Series | None:
    """Year-end share-price index as an annual series indexed by int year."""
    store = load()
    if iso2 not in store:
        return None
    s = pd.Series(store[iso2])
    s.index = pd.to_datetime(s.index + "-01")
    s = s.sort_index()
    yr = s.groupby(s.index.year).last()
    yr.index = yr.index.astype(int)
    return yr
