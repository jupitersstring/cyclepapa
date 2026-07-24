"""
Monthly macro loader -- the high-frequency legs of Godley's framework.

Godley's Seven Unsustainable Processes include measures that are observable
monthly, long before the annual sectoral accounts print:
  - Process 3: the growth rate of the REAL money stock
  - Process 2: the flow of net lending to the private sector

This loader pulls the monthly series that make those computable across
countries, keyless via DBnomics (OECD MEI):
    MABMM301.STSA.M   broad money (M3), seasonally adjusted, monthly
    CPALTT01.IXOB.M   consumer price index, monthly

Real money growth = money YoY% - CPI YoY%. Its acceleration is the monthly
analog of the credit impulse -- the fastest SFC-consistent lead available.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

from .prices import ISO2_TO_OECD, _OECD_TO_ISO2

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "monthly.json"
_SERIES = {"money": "MABMM301.STSA.M", "cpi": "CPALTT01.IXOB.M"}


def _db_batch(iso3s: list[str], series_code: str, tries: int = 3) -> dict:
    codes = "+".join(iso3s)
    ind = series_code.split(".")[0]
    url = (f"https://api.db.nomics.world/v22/series/OECD/MEI/"
           f"{codes}.{series_code}?observations=1&limit=300")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "godley-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.load(r)
            out = {}
            for s in d["series"]["docs"]:
                iso3 = s["series_code"].split(".")[0]
                out[iso3] = {p[:7]: float(v) for p, v in zip(s["period"], s["value"])
                             if v is not None and v == v}
            return out
        except Exception:
            time.sleep(2.0 * (i + 1))
    return {}


def refresh(isos: list[str], polite: float = 1.2) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    iso3s = [ISO2_TO_OECD[i] for i in isos if i in ISO2_TO_OECD]
    for field, code in _SERIES.items():
        for j in range(0, len(iso3s), 10):
            grp = [o for o in iso3s[j:j + 10]
                   if not store.get(_OECD_TO_ISO2.get(o, ""), {}).get(field)]
            if not grp:
                continue
            res = _db_batch(grp, code)
            for iso3, series in res.items():
                iso2 = _OECD_TO_ISO2.get(iso3)
                if iso2 and series:
                    store.setdefault(iso2, {})[field] = series
            _CACHE.write_text(json.dumps(store))
            time.sleep(polite)
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def monthly_frame(iso2: str) -> pd.DataFrame | None:
    """Monthly money + CPI for one country, indexed by month-end Timestamp."""
    store = load()
    rec = store.get(iso2, {})
    if "money" not in rec or "cpi" not in rec:
        return None
    df = pd.DataFrame({k: pd.Series(rec[k]) for k in ("money", "cpi") if k in rec})
    df.index = pd.to_datetime(df.index + "-01")
    return df.sort_index()
