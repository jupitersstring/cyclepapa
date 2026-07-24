"""
Historical annual macro panel -- World Bank + IMF datamapper (keyless).

Broad, integral, long-history sources for reconstructing the Godley score
through time:

  World Bank (annual, ~1960-2024):
    FS.AST.PRVT.GD.ZS   domestic credit to private sector, %GDP
    NE.GDI.TOTL.ZS      gross capital formation (investment), %GDP
    NY.GNS.ICTR.ZS      gross savings, %GDP
    CM.MKT.LCAP.GD.ZS   stock-market capitalisation, %GDP
    NE.EXP.GNFS.ZS / NE.IMP.GNFS.ZS   exports / imports, %GDP

  IMF datamapper (annual, ~1980-2031 incl. projections):
    GGXCNL_NGDP   general government net lending (fiscal balance), %GDP
    BCA_NGDPD     current account balance, %GDP
    NGDP_RPCH     real GDP growth, %

From these we reconstruct the two dominant live-scanner factors -- the
Kalecki-Levy profit-fuel impulse and the credit impulse -- plus a valuation
term, each z-scored against the country's OWN history (which finally brings
transforms.zscore to life on real time series).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

from .live import ISO2_TO_ISO3

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "history.json"
_UA = "godley-scanner/1.0"

WB = {
    "credit": "FS.AST.PRVT.GD.ZS",
    "investment": "NE.GDI.TOTL.ZS",
    "savings": "NY.GNS.ICTR.ZS",
    "mktcap": "CM.MKT.LCAP.GD.ZS",
    "exports": "NE.EXP.GNFS.ZS",
    "imports": "NE.IMP.GNFS.ZS",
}
IMF = {
    "fiscal": "GGXCNL_NGDP",
    "ca": "BCA_NGDPD",
    "growth": "NGDP_RPCH",
}


def _get(url: str, ua: bool = True):
    req = urllib.request.Request(url, headers={"User-Agent": _UA} if ua else {})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def _wb(indicator: str, iso2: str) -> dict:
    try:
        url = (f"https://api.worldbank.org/v2/country/{iso2}/indicator/{indicator}"
               f"?format=json&date=1990:2025&per_page=100")
        d = _get(url)
        if len(d) > 1 and d[1]:
            return {int(r["date"]): float(r["value"]) for r in d[1]
                    if r.get("value") is not None}
    except Exception:
        pass
    return {}


def _imf(indicator: str, iso3: str) -> dict:
    try:
        url = f"https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}"
        d = _get(url, ua=False)  # imf 403s on custom UA via proxy
        v = d["values"][indicator][iso3]
        return {int(y): float(x) for y, x in v.items() if x is not None}
    except Exception:
        return {}


def refresh(isos: list[str], polite: float = 0.05) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    for iso2 in isos:
        iso3 = ISO2_TO_ISO3.get(iso2)
        if not iso3:
            continue
        rec = store.get(iso2, {})
        for field, ind in WB.items():
            if field not in rec or not rec[field]:
                rec[field] = {str(k): v for k, v in _wb(ind, iso2).items()}
                time.sleep(polite)
        for field, ind in IMF.items():
            if field not in rec or not rec[field]:
                rec[field] = {str(k): v for k, v in _imf(ind, iso3).items()}
                time.sleep(polite)
        store[iso2] = rec
        _CACHE.write_text(json.dumps(store))  # incremental
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def frame(iso2: str) -> pd.DataFrame | None:
    """Annual macro DataFrame for one country, indexed by int year."""
    store = load()
    if iso2 not in store:
        return None
    rec = store[iso2]
    cols = {}
    for field, series in rec.items():
        if series:
            cols[field] = {int(y): v for y, v in series.items()}
    if not cols:
        return None
    df = pd.DataFrame(cols).sort_index()
    df.index = df.index.astype(int)
    return df
