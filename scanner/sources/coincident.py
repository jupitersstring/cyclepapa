"""
Coincident quarterly fiscal balance -- Godley's own data cadence.

Godley built his Levy Strategic Analyses on the FLOW OF FUNDS and quarterly
sector accounts -- coincident net-lending data, not annual proxies. Annual
national accounts lag ~a year (the reconstructed score's frontier is 2024);
this module fetches the CURRENT quarterly government net-lending balance, which
Eurostat publishes to ~the latest quarter (2026-Q1 at time of writing), keyless:

    Eurostat gov_10q_ggnfa -- general government (S13) net lending/borrowing
    (B9) as % of GDP, quarterly, seasonally adjusted. Verified current to
    2026-Q1 (e.g. Germany 2026-Q1 = -3.6% of GDP).

This is the coincident GOVERNMENT leg of the three-balance identity -- the
Kalecki fiscal fuel at quarterly frequency. The full private/foreign split at
this cadence requires the sector-accounts (nasq_10_nf_tr, household + corporate
B9) and quarterly current account, documented as the next wire; the Fed Z.1
Financial Accounts is the canonical US equivalent (BOGZ1FA*5000005Q).

Use: a current read on whether the government is injecting or withdrawing
demand -- the fastest-moving, most current leg of Godley's identity.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

_CACHE = Path(__file__).resolve().parent.parent / "_cache" / "coincident.json"
_ES = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

EU_ISOS = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "FI", "PT", "GR", "IE",
           "SE", "DK", "PL", "CZ", "HU", "NO"]


def _get(url: str, tries: int = 4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "godley-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def _gov_b9(geo: str) -> dict:
    """Quarterly general-government net lending, % GDP, seasonally adjusted."""
    d = _get(f"{_ES}/gov_10q_ggnfa?format=JSON&na_item=B9&sector=S13"
             f"&unit=PC_GDP&s_adj=SCA&geo={geo}&sinceTimePeriod=2019-Q1")
    if not d or not d.get("value"):
        return {}
    inv = {v: k for k, v in d["dimension"]["time"]["category"]["index"].items()}
    return {inv[int(k)]: round(float(v), 2) for k, v in d["value"].items()
            if int(k) in inv}


def refresh(isos: list[str] | None = None, polite: float = 0.5) -> dict:
    _CACHE.parent.mkdir(exist_ok=True)
    store = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    for geo in (isos or EU_ISOS):
        if geo in store:
            continue
        s = _gov_b9(geo)
        if s:
            store[geo] = s
            _CACHE.write_text(json.dumps(store))
        time.sleep(polite)
    return store


def load() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def latest_gov_balance(iso: str) -> tuple[float, str] | None:
    """Most-recent quarterly government net lending (%GDP) + the quarter."""
    rec = load().get(iso, {})
    if not rec:
        return None
    q = sorted(rec)[-1]
    return rec[q], q
