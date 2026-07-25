"""
Inflation accounting for sectoral balances -- the correction Godley insisted on
and that almost every modern user of "sectoral balances" omits.

THE ARGUMENT. Under inflation, part of a nominal deficit is not new demand at
all: it is the flow required to compensate holders for the erosion of the real
value of the debt they hold. Godley & Cripps (1983: 245) put the causation
sharply -- "the faster the rate of inflation the larger the government's cash
deficit must be in order to keep real debt constant." Godley regarded the
failure to do this as the thing that discredited New Cambridge in the 1970s
(Monetary Economics, preface): "We had a bad time in the mid-1970s because we
did not then understand inflation accounting... nobody else at that time seems
to have understood inflation accounting."

THE CORRECTION is symmetric across sectors -- the same item, opposite signs.
Godley & Lavoie (2007, p.352) for government, and (eq. 10.26) for households:

    real balance = [ nominal balance + Dp * (net monetary position, t-1) ] / p

i.e. to first order as a share of GDP:

    adjusted balance  =  nominal balance  +  pi * (net monetary liabilities/GDP)

For the government, whose net monetary position is a LIABILITY, inflation is a
gain: the adjusted deficit is SMALLER than the nominal one. For households,
who hold the matching assets, inflation is a loss: their adjusted surplus is
smaller. Because net monetary positions sum to zero across sectors, the
adjustments sum to zero and THE IDENTITY SURVIVES -- inflation accounting
changes the level and sometimes the sign of each balance, never the constraint.

MATERIALITY. It is frequently sign-flipping. US federal FY2022: nominal -5.3%
of GDP, inflation-adjusted +1.3%. The UK public sector in 1975 recorded an
inflation gain of roughly 11% of GDP, turning persistent nominal deficits into
real surpluses.

WHAT GODLEY ACTUALLY DID. He used an inflation-adjusted fiscal ratio in Seven
Unsustainable Processes (1999, note 1: "adjusted for inflation by appropriate
deflation of both stocks and flows") but the headline three-balance charts in
the Strategic Analyses are nominal -- which is why the modern convention
inherited the unadjusted version.

IMPLEMENTATION NOTE. The theoretically correct stock is each sector's NET
MONETARY POSITION at market value (instruments fixed in nominal terms --
deposits, debt securities, loans, currency -- excluding equities and real
assets), deflated by the consumption deflator. We approximate the government
leg with gross general-government debt and use CPI, which is the first-order
version; the private leg is taken as the mirror image net of the external
position. Documented as an approximation, not the Taylor-Threadgold full
treatment (Bank of England DP No. 6, 1979).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

from .sources import history as HIST
from .sources.live import ISO2_TO_ISO3

_CACHE = Path(__file__).resolve().parent / "_cache" / "debt_infl.json"


def _imf(indicator: str, iso3: str) -> dict:
    try:
        url = f"https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}"
        with urllib.request.urlopen(url, timeout=25) as r:   # no UA: imf 403s on custom
            d = json.load(r)
        v = d["values"][indicator][iso3]
        return {int(y): float(x) for y, x in v.items() if x is not None}
    except Exception:
        return {}


def refresh(isos: list[str] | None = None, polite: float = 0.03) -> dict:
    """Government gross debt (%GDP) and CPI inflation (%), annual, from IMF."""
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    for iso2 in (isos or list(ISO2_TO_ISO3)):
        if iso2 in store:
            continue
        iso3 = ISO2_TO_ISO3.get(iso2)
        if not iso3:
            continue
        debt = _imf("GGXWDG_NGDP", iso3)
        time.sleep(polite)
        infl = _imf("PCPIPCH", iso3)          # CPI inflation, % change
        time.sleep(polite)
        if debt or infl:
            store[iso2] = {"debt": {str(k): v for k, v in debt.items()},
                           "inflation": {str(k): v for k, v in infl.items()}}
            _CACHE.write_text(json.dumps(store))
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def adjusted_balances(iso: str, year: int | None = None) -> dict | None:
    """
    Inflation-adjusted three balances for one country-year.

    government_adj = government + pi * debt/GDP     (inflation gain to the debtor)
    private_adj    = private    - pi * debt_held_by_private/GDP
    foreign_adj    = foreign    - pi * debt_held_abroad/GDP

    We split the inflation gain between the private and foreign sectors in
    proportion to their shares of the (unobserved) holdings, proxied by the
    ratio of the private to external balance positions -- an approximation,
    flagged as such. The adjustments sum to zero by construction.
    """
    rec = load().get(iso, {})
    debt_s, infl_s = rec.get("debt", {}), rec.get("inflation", {})
    if not debt_s or not infl_s:
        return None
    hist = HIST.load().get(iso, {})
    f, c = hist.get("fiscal", {}), hist.get("ca", {})
    if not f or not c:
        return None
    yrs = sorted({int(y) for y in f} & {int(y) for y in c}
                 & {int(y) for y in debt_s} & {int(y) for y in infl_s})
    yrs = [y for y in yrs if y <= 2024]
    if not yrs:
        return None
    y = year if year in yrs else yrs[-1]

    fiscal, ca = float(f[str(y)]), float(c[str(y)])
    debt, pi = float(debt_s[str(y)]), float(infl_s[str(y)])
    gov, ext = fiscal, -ca
    priv = ca - fiscal

    gain = pi / 100.0 * debt                      # inflation gain to the debtor, %GDP
    # split the matching loss between domestic private and foreign holders.
    # Proxy the foreign share by the external position's share of total
    # non-government claims; fall back to 30% (a typical foreign-held share).
    denom = abs(priv) + abs(ext)
    foreign_share = (abs(ext) / denom) if denom > 0.5 else 0.30
    foreign_share = min(max(foreign_share, 0.0), 0.85)

    gov_adj = gov + gain
    priv_adj = priv - gain * (1 - foreign_share)
    ext_adj = ext - gain * foreign_share

    return {"iso": iso, "year": y, "inflation": round(pi, 1), "debt": round(debt, 1),
            "nominal": {"private": round(priv, 1), "government": round(gov, 1),
                        "foreign": round(ext, 1)},
            "adjusted": {"private": round(priv_adj, 1), "government": round(gov_adj, 1),
                         "foreign": round(ext_adj, 1)},
            "inflation_gain_pct_gdp": round(gain, 1),
            "foreign_share": round(foreign_share, 2),
            "sign_flip": (gov < 0) != (gov_adj < 0)}


def panel() -> pd.DataFrame:
    """Inflation-adjusted balances across the panel."""
    rows = []
    for iso in load():
        a = adjusted_balances(iso)
        if a:
            rows.append({"iso": iso, "year": a["year"], "pi": a["inflation"],
                         "debt": a["debt"],
                         "gov_nom": a["nominal"]["government"],
                         "gov_adj": a["adjusted"]["government"],
                         "priv_nom": a["nominal"]["private"],
                         "priv_adj": a["adjusted"]["private"],
                         "gain": a["inflation_gain_pct_gdp"],
                         "sign_flip": a["sign_flip"]})
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("gain", ascending=False) if rows else pd.DataFrame())
