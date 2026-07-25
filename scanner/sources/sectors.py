"""
Disaggregated sector balances -- households vs corporations, separately.

Lumping households and firms into one "private balance" is the New Cambridge
aggregation, and Godley himself retreated from it: Godley & Lavoie (2007) model
households and firms with SEPARATE behavioural equations and balance sheets.
The aggregate can hide opposing movements and therefore opposite mechanisms:

    Germany 2024   private +8.7 = households +6.9, corporates +1.8
                   -> a HOUSEHOLD saving glut (consumption suppressed)
    Netherlands 22 private +13.3 = households +0.4, corporates +12.9
                   -> a CORPORATE saving glut (profits not reinvested)

Same headline surplus, entirely different Godley diagnosis and entirely
different policy remedy.

Source: Eurostat annual non-financial sector accounts (nasa_10_nf_tr), B9 net
lending/borrowing by institutional sector, in national currency, divided by
nominal GDP (nama_10_gdp). Keyless, and CURRENT TO 2025 -- one year fresher
than the IMF WEO actuals.

    S14_S15  households + NPISH
    S11      non-financial corporations
    S12      financial corporations
    S13      general government
    S2       rest of world
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "sectors.json"
_ES = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

SECTORS = {"households": "S14_S15", "nonfin_corp": "S11",
           "fin_corp": "S12", "government": "S13", "foreign": "S2"}

# Eurostat covers the EU/EEA; these are the panel members it reaches.
GEOS = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "FI", "PT", "GR", "IE",
        "SE", "DK", "PL", "CZ", "HU", "NO", "RO"]


def _get(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "godley-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=35) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def _extract(d) -> dict:
    if not d or not d.get("value"):
        return {}
    inv = {v: k for k, v in d["dimension"]["time"]["category"]["index"].items()}
    return {inv[int(k)]: float(v) for k, v in d["value"].items() if int(k) in inv}


def refresh(geos: list[str] | None = None, polite: float = 0.35) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    for geo in (geos or GEOS):
        if geo in store:
            continue
        gdp = _extract(_get(f"{_ES}/nama_10_gdp?format=JSON&na_item=B1GQ"
                            f"&unit=CP_MNAC&geo={geo}&sinceTimePeriod=1999"))
        if not gdp:
            continue
        rec = {}
        for name, code in SECTORS.items():
            s = _extract(_get(f"{_ES}/nasa_10_nf_tr?format=JSON&na_item=B9&sector={code}"
                              f"&unit=CP_MNAC&direct=PAID&geo={geo}&sinceTimePeriod=1999"))
            if s:
                rec[name] = {y: round(v / gdp[y] * 100, 2)
                             for y, v in s.items() if gdp.get(y)}
            time.sleep(polite)
        if rec:
            store[geo] = rec
            _CACHE.write_text(json.dumps(store))
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def frame(geo: str) -> pd.DataFrame | None:
    """
    Sector balances (%GDP) by year for one country.

    Eurostat's nasa_10_nf_tr does not return general government (S13) for
    every member (DE, DK, CZ, PT, SE come back empty), so where it is missing
    we substitute the IMF general-government net lending from the annual
    history -- the same concept, and complete for the whole panel.
    """
    rec = load().get(geo)
    if not rec:
        return None
    rec = dict(rec)
    if "government" not in rec:
        from . import history
        f = history.load().get(geo, {}).get("fiscal", {})
        if f:
            rec["government"] = {y: float(v) for y, v in f.items()
                                 if v is not None and int(y) <= 2024}
    df = pd.DataFrame({k: pd.Series(v) for k, v in rec.items()})
    df.index = df.index.astype(int)
    return df.sort_index()


def split(geo: str) -> dict | None:
    """
    Latest household / corporate decomposition of the private balance --
    the thing the aggregate hides.
    """
    f = frame(geo)
    if f is None or f.empty:
        return None
    # Require a COMPLETE year: partial vintages publish some sectors before
    # others and would otherwise show a spurious 0.0 for the missing sector.
    need = [c for c in ("households", "nonfin_corp", "government", "foreign")
            if c in f.columns]
    complete = f.dropna(subset=need)
    if complete.empty:
        return None
    # the identity should close; drop years where it misses by >1.5pp
    tot = complete[[c for c in ("households", "nonfin_corp", "fin_corp",
                                "government", "foreign") if c in complete.columns]].sum(axis=1)
    complete = complete[tot.abs() < 1.5]
    if complete.empty:
        return None
    last = complete.iloc[-1]
    hh = float(last.get("households", 0.0))
    nfc = float(last.get("nonfin_corp", 0.0))
    fin = float(last.get("fin_corp", 0.0))
    priv = hh + nfc + fin
    driver = ("household" if abs(hh) > abs(nfc + fin) else "corporate")
    return {"geo": geo, "year": int(last.name), "households": round(hh, 1),
            "nonfin_corp": round(nfc, 1), "fin_corp": round(fin, 1),
            "private_total": round(priv, 1), "driver": driver,
            "government": round(float(last.get("government", 0.0)), 1),
            "foreign": round(float(last.get("foreign", 0.0)), 1)}
