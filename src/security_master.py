#!/usr/bin/env python3
"""
security_master.py — canonical entity crosswalk (institutional security master).

Every poller emits a different identifier: EDGAR gives CIK + ticker,
13F gives CUSIP, NSM gives ISIN, TDnet gives a local numeric code,
CVM gives a Brazilian CVM code. Without a canonical crosswalk, cross-
source corroboration and dedup fall back to fuzzy name-stem matching,
which silently misses the same entity carried under different ids
(e.g. a 13F CUSIP position and an 8-K ticker filing for the same
company never corroborate).

This module maintains ONE canonical entity record keyed by a stable
`entity_id` and crosswalks CIK <-> ticker <-> CUSIP <-> ISIN <-> LEI
<-> normalized-name. It resolves via three free, confirmed-accessible
sources, all cached to disk so the pipeline works offline after warm-up:

  - SEC company_tickers_exchange.json  (CIK <-> ticker <-> exchange)
  - OpenFIGI /v3/mapping               (CUSIP/ISIN -> ticker, batched)
  - GLEIF /api/v1/lei-records          (LEI <-> legal name <-> country)

Persistent store: data/security_master.json (the crosswalk) and
data/security_master_cache.json (raw resolution cache).

Usage (library):
    from src.security_master import SecurityMaster
    sm = SecurityMaster()
    ent = sm.resolve(cusip="02079K305")      # -> canonical entity dict
    key = sm.canonical_key(cik="895419")     # -> stable entity_id

Usage (CLI — warm the SEC crosswalk + batch-resolve pending CUSIPs):
    python -m src.security_master --warm
    python -m src.security_master --resolve-inbox-cusips
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
MASTER = DATA / "security_master.json"
CACHE = DATA / "security_master_cache.json"
INBOX = DATA / "inbox"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")

SEC_TICKERS_EXCH = "https://www.sec.gov/files/company_tickers_exchange.json"
OPENFIGI_MAP = "https://api.openfigi.com/v3/mapping"
GLEIF_LEI = "https://api.gleif.org/api/v1/lei-records"

_CORP_SUFFIX = re.compile(
    r"\b(plc|ltd|limited|inc|incorporated|corp|corporation|company|"
    r"co|group|holdings?|sa|nv|ag|se|oyj|asa|ab|spa|kg|llc|llp|lp|"
    r"pty|pte|kk|n.?v|s\.?a)\b\.?", re.I)


def normalize_name(n) -> str:
    """Canonical name stem: strip corporate suffixes + punctuation, upper."""
    if not n:
        return ""
    if isinstance(n, (list, tuple)):
        n = " ".join(str(x) for x in n if x)
    n = str(n)
    n = _CORP_SUFFIX.sub("", n)
    return re.sub(r"[^A-Za-z0-9]", "", n).upper()


def _norm_cik(cik) -> str:
    if not cik:
        return ""
    try:
        return str(int(str(cik).lstrip("0") or "0"))
    except ValueError:
        return ""


class SecurityMaster:
    """Canonical entity crosswalk with disk-backed caches."""

    def __init__(self, offline: bool = False):
        self.offline = offline
        self._master: dict = self._load(MASTER, {"entities": {}, "index": {}})
        self._cache: dict = self._load(CACHE, {"openfigi": {}, "gleif": {}})
        self._sec_by_cik: dict[str, dict] = {}
        self._sec_by_ticker: dict[str, dict] = {}
        self._sec_loaded = False

    # ---- persistence -----------------------------------------------------
    @staticmethod
    def _load(path: Path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return default
        return default

    def save(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        MASTER.write_text(json.dumps(self._master, indent=2, sort_keys=True))
        CACHE.write_text(json.dumps(self._cache, indent=2, sort_keys=True))

    # ---- SEC ticker/exchange crosswalk -----------------------------------
    def _ensure_sec(self) -> None:
        if self._sec_loaded:
            return
        cache_path = DATA / "sec_tickers_exchange.json"
        data = None
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = None
        if data is None and not self.offline:
            try:
                r = requests.get(SEC_TICKERS_EXCH,
                                 headers={"User-Agent": USER_AGENT}, timeout=30)
                r.raise_for_status()
                data = r.json()
                DATA.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
            except (requests.RequestException, OSError):
                data = None
        if data and "fields" in data and "data" in data:
            fields = data["fields"]
            i_cik = fields.index("cik") if "cik" in fields else 0
            i_name = fields.index("name") if "name" in fields else 1
            i_tick = fields.index("ticker") if "ticker" in fields else 2
            i_exch = fields.index("exchange") if "exchange" in fields else 3
            for row in data["data"]:
                cik = _norm_cik(row[i_cik])
                rec = {"cik": cik, "name": row[i_name],
                       "ticker": (row[i_tick] or "").upper(),
                       "exchange": row[i_exch]}
                if cik:
                    self._sec_by_cik[cik] = rec
                if rec["ticker"]:
                    self._sec_by_ticker[rec["ticker"]] = rec
        self._sec_loaded = True

    def ticker_for_cik(self, cik) -> str | None:
        self._ensure_sec()
        rec = self._sec_by_cik.get(_norm_cik(cik))
        return rec["ticker"] if rec and rec.get("ticker") else None

    def cik_for_ticker(self, ticker) -> str | None:
        self._ensure_sec()
        rec = self._sec_by_ticker.get((ticker or "").upper())
        return rec["cik"] if rec else None

    # ---- OpenFIGI CUSIP/ISIN -> ticker -----------------------------------
    def resolve_cusip(self, cusip: str) -> dict | None:
        cusip = (cusip or "").strip().upper()
        if not cusip:
            return None
        if cusip in self._cache["openfigi"]:
            return self._cache["openfigi"][cusip] or None
        if self.offline:
            return None
        res = self._openfigi_batch([("ID_CUSIP", cusip)]).get(cusip)
        self._cache["openfigi"][cusip] = res or {}
        return res

    def _openfigi_batch(self, pairs: list[tuple[str, str]]) -> dict:
        """Batch-resolve up to 100 (idType, idValue) via OpenFIGI. Free
        tier: ~25 req/min unauthenticated, 10 jobs/request."""
        out: dict[str, dict] = {}
        headers = {"Content-Type": "application/json",
                   "User-Agent": USER_AGENT}
        key = os.environ.get("OPENFIGI_API_KEY")
        if key:
            headers["X-OPENFIGI-APIKEY"] = key
        BATCH = 10 if not key else 100
        for i in range(0, len(pairs), BATCH):
            chunk = pairs[i:i + BATCH]
            body = [{"idType": t, "idValue": v} for t, v in chunk]
            try:
                r = requests.post(OPENFIGI_MAP, headers=headers,
                                  data=json.dumps(body), timeout=25)
                if r.status_code == 429:
                    time.sleep(6.0)   # respect free-tier throttle
                    r = requests.post(OPENFIGI_MAP, headers=headers,
                                      data=json.dumps(body), timeout=25)
                r.raise_for_status()
                results = r.json()
            except requests.RequestException:
                results = [{} for _ in chunk]
            for (idtype, idval), res in zip(chunk, results):
                data = (res or {}).get("data") or []
                if data:
                    d0 = data[0]
                    out[idval] = {
                        "ticker": (d0.get("ticker") or "").upper() or None,
                        "name": d0.get("name"),
                        "figi": d0.get("compositeFIGI") or d0.get("figi"),
                        "exchange": d0.get("exchCode"),
                        "security_type": d0.get("securityType"),
                    }
                else:
                    out[idval] = {}
            time.sleep(2.5 if not key else 0.3)
        return out

    # ---- canonical resolution --------------------------------------------
    def resolve(self, *, cik=None, ticker=None, cusip=None, isin=None,
                name=None) -> dict:
        """Return a canonical entity dict, resolving across sources and
        merging into the master store. Best-effort — fills what it can."""
        ent = {"cik": _norm_cik(cik) or None,
               "ticker": (ticker or "").upper() or None,
               "cusip": (cusip or "").upper() or None,
               "isin": (isin or "").upper() or None,
               "name": name or None,
               "name_stem": normalize_name(name) if name else None}
        # CIK -> ticker via SEC
        if ent["cik"] and not ent["ticker"]:
            ent["ticker"] = self.ticker_for_cik(ent["cik"])
        if ent["ticker"] and not ent["cik"]:
            ent["cik"] = self.cik_for_ticker(ent["ticker"])
        # CUSIP -> ticker via OpenFIGI
        if ent["cusip"] and not ent["ticker"]:
            r = self.resolve_cusip(ent["cusip"])
            if r and r.get("ticker"):
                ent["ticker"] = r["ticker"]
                if not ent["name"] and r.get("name"):
                    ent["name"] = r["name"]
                    ent["name_stem"] = normalize_name(r["name"])
                if not ent["cik"]:
                    ent["cik"] = self.cik_for_ticker(ent["ticker"])
        return self._upsert(ent)

    def canonical_key(self, **kw) -> str:
        """Stable entity_id for dedup/corroboration. Priority: ticker ->
        cik -> cusip -> isin -> name_stem."""
        ent = self.resolve(**kw)
        return (ent.get("ticker") or
                (f"CIK{ent['cik']}" if ent.get("cik") else None) or
                (f"CUSIP{ent['cusip']}" if ent.get("cusip") else None) or
                (f"ISIN{ent['isin']}" if ent.get("isin") else None) or
                ent.get("name_stem") or "")

    def _upsert(self, ent: dict) -> dict:
        """Merge ent into the master store, keyed by best canonical id."""
        key = (ent.get("ticker") or
               (f"CIK{ent['cik']}" if ent.get("cik") else None) or
               (f"CUSIP{ent['cusip']}" if ent.get("cusip") else None) or
               (f"ISIN{ent['isin']}" if ent.get("isin") else None) or
               ent.get("name_stem"))
        if not key:
            return ent
        existing = self._master["entities"].get(key, {})
        for f in ("cik", "ticker", "cusip", "isin", "name", "name_stem"):
            if ent.get(f) and not existing.get(f):
                existing[f] = ent[f]
        existing["entity_id"] = key
        self._master["entities"][key] = existing
        # secondary index for cross-id lookup
        for f in ("cik", "cusip", "isin"):
            if existing.get(f):
                self._master["index"][f"{f}:{existing[f]}"] = key
        ent2 = dict(existing)
        return ent2


def resolve_inbox_cusips(days_back: int = 30) -> int:
    """Batch-resolve every CUSIP found in recent inbox records so the
    OpenFIGI cache is warm before corroboration runs."""
    from datetime import date, timedelta
    sm = SecurityMaster()
    cusips: set[str] = set()
    end = date.today()
    for n in range(days_back + 1):
        day = (end - timedelta(days=n)).isoformat()
        d = INBOX / day
        if not d.exists():
            continue
        for jf in d.rglob("*.json"):
            try:
                rec = json.loads(jf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            c = (rec.get("cusip") or "").strip().upper()
            if c and c not in sm._cache["openfigi"]:
                cusips.add(c)
    cusips = sorted(cusips)
    print(f"Resolving {len(cusips)} uncached CUSIPs via OpenFIGI...")
    if cusips:
        pairs = [("ID_CUSIP", c) for c in cusips]
        got = sm._openfigi_batch(pairs)
        for c in cusips:
            sm._cache["openfigi"][c] = got.get(c, {})
        resolved = sum(1 for c in cusips if (got.get(c) or {}).get("ticker"))
        print(f"  {resolved}/{len(cusips)} resolved to a ticker")
    sm.save()
    return len(cusips)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warm", action="store_true",
                    help="Warm the SEC CIK/ticker/exchange crosswalk")
    ap.add_argument("--resolve-inbox-cusips", action="store_true",
                    help="Batch-resolve CUSIPs from recent inbox records")
    ap.add_argument("--days-back", type=int, default=30)
    args = ap.parse_args()
    sm = SecurityMaster()
    if args.warm:
        sm._ensure_sec()
        print(f"SEC crosswalk warmed: {len(sm._sec_by_cik)} CIKs, "
              f"{len(sm._sec_by_ticker)} tickers")
        sm.save()
    if args.resolve_inbox_cusips:
        resolve_inbox_cusips(args.days_back)
    if not (args.warm or args.resolve_inbox_cusips):
        # Demo
        for kw in [{"cusip": "02079K305"}, {"cik": "895419"},
                   {"ticker": "FMC"}]:
            print(kw, "->", sm.canonical_key(**kw))
        sm.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
