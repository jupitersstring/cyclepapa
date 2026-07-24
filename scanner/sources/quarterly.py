"""
Quarterly credit loader -- the middle rung of Godley's frequency ladder.

BIS long series on total credit to the private non-financial sector, %GDP,
quarterly, keyless via DBnomics (BIS/WS_TC, series key Q.<CTY>.P.A.M.770.A --
private non-financial borrowers, all lenders, market value, % of GDP, break-
adjusted). History to the 1940s-60s for the majors.

From it we build the two quarterly SFC measures Godley's Seven Processes name:
  Process 2  net lending to the private sector = 4q change in credit/GDP
  credit impulse (Biggs-Mayer) = the acceleration of that flow (2nd derivative)

These fill the 1-2 year window where the monthly money signal has faded and the
annual sectoral score has not yet built.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "quarterly.json"

# Panel ISO2 -> BIS reporting code (mostly ISO2; a few differ).
ISO2_TO_BIS = {
    "US": "US", "GB": "GB", "DE": "DE", "JP": "JP", "KR": "KR", "CN": "CN",
    "BR": "BR", "MX": "MX", "IN": "IN", "ID": "ID", "PL": "PL", "HU": "HU",
    "CZ": "CZ", "TR": "TR", "SA": "SA", "ZA": "ZA", "AU": "AU", "CA": "CA",
    "NZ": "NZ", "FR": "FR", "IT": "IT", "ES": "ES", "PT": "PT", "GR": "GR",
    "NL": "NL", "BE": "BE", "AT": "AT", "FI": "FI", "DK": "DK", "SE": "SE",
    "CH": "CH", "IE": "IE", "NO": "NO", "RU": "RU", "CL": "CL", "CO": "CO",
    "IL": "IL", "TH": "TH", "MY": "MY",
}
_BIS_TO_ISO2 = {v: k for k, v in ISO2_TO_BIS.items()}


def _q_to_ts(q: str) -> pd.Timestamp:
    """'2024-Q4' -> quarter-end Timestamp."""
    y, qq = q.split("-Q")
    return pd.Timestamp(int(y), int(qq) * 3, 1) + pd.offsets.MonthEnd(1)


def _db_batch(bis_codes: list[str], tries: int = 3) -> dict:
    mask = "+".join(bis_codes)
    url = (f"https://api.db.nomics.world/v22/series/BIS/WS_TC/"
           f"Q.{mask}.P.A.M.770.A?observations=1&limit=200")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "godley-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.load(r)
            out = {}
            for s in d["series"]["docs"]:
                cty = s["series_code"].split(".")[1]
                out[cty] = {p: float(v) for p, v in zip(s["period"], s["value"])
                            if v is not None and v == v}
            return out
        except Exception:
            time.sleep(2.0 * (i + 1))
    return {}


def refresh(isos: list[str], polite: float = 1.2) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    codes = [ISO2_TO_BIS[i] for i in isos if i in ISO2_TO_BIS and i not in store]
    for j in range(0, len(codes), 10):
        res = _db_batch(codes[j:j + 10])
        for bis, series in res.items():
            iso2 = _BIS_TO_ISO2.get(bis)
            if iso2 and series:
                store[iso2] = series
        _CACHE.write_text(json.dumps(store))
        time.sleep(polite)
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def credit_gdp(iso2: str) -> pd.Series | None:
    """Private non-financial credit / GDP (%), quarterly, indexed by quarter-end."""
    store = load()
    if iso2 not in store:
        return None
    s = pd.Series(store[iso2])
    s.index = [_q_to_ts(q) for q in s.index]
    return s.sort_index()
