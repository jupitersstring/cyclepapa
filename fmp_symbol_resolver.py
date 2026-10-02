"""Resolve master symbols FMP does not answer for to FMP's OWN symbol for the
same company -> fmp_symbol_map.csv.

The master's symbols came from Yahoo. FMP often carries the same company under
a different listing: VNAA.F (Frankfurt) is Vonovia = VNA.DE; H3D.F is Sonnet
= SONN; MBECL.BO = MBECL.NS; 1X8.F (Creso Pharma) = CPH.AX; 26Y.SG (Yatra) =
YTRA. Treating "no rows for this symbol" as "FMP has no data" silently dropped
those companies from every FMP layer (prices, statements, quarterly, events,
sentiment). This resolver closes that: for every master symbol lacking FMP
prices or statements it asks FMP's own search endpoints (search-symbol on the
base ticker, search-name on the company name; search-isin / search-cusip where
the master carries them), verifies the candidate is the SAME company by name,
prefers the primary listing, and records FMP's symbol, exchange and currency.

fmp_client.get_json substitutes the resolved symbol automatically (the alias
hook), so every engine reaches the company's data under its master symbol.

Two permissions per row:
  use_for_fundamentals  the same company: statements / ratios / events /
                        sentiment always apply (a B-share's issuer is the
                        A-share's issuer)
  use_for_prices        only when the resolved line is the SAME SECURITY:
                        not a different share class (B-share 9xxxxx.SS /
                        2xxxxx.SZ, preferred / hybrid lines) and not an OTC
                        pink line standing in for a primary listing
"""
from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_symbol_map.csv"
COLS = ["symbol", "fmp_symbol", "method", "score", "fmp_exchange", "fmp_currency", "use_for_prices",
        "use_for_fundamentals", "note"]
_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|ag|se|sa|nv|bv|ab|as|asa|oyj|"
                     r"spa|srl|kgaa|gmbh|holdings?|group|the|class [abc]|ordinary|shares?|common|stock|kk|kabushiki|"
                     r"kaisha|tbk|pt|bhd|berhad|sdn|public|jsc|pjsc|ojsc|ao|pao)\b")
PRIMARY = {"NASDAQ", "NYSE", "AMEX", "XETRA", "TSX", "TSXV", "ASX", "LSE", "NSE", "BSE", "SHH", "SHZ", "HKSE", "KSC",
           "KOE", "JPX", "TYO", "EURONEXT", "PAR", "AMS", "BRU", "MIL", "SIX", "STO", "OSL", "CPH", "HEL", "WSE", "SES",
           "SGX", "TAI", "TWO", "JKT", "SET", "KLS", "SAO", "MEX", "BUE", "SAU", "TLV", "IST", "JNB", "NZE", "VIE",
           "PRA", "ATH", "LIS", "DUB", "BUD", "WAR"}
SECONDARY = {"FSX", "STU", "MUN", "DUS", "HAM", "BER", "XFRA"}
B_SHARE = re.compile(r"^(9\d{5}\.SS|2\d{5}\.SZ)$")
NONCOMMON = re.compile(r"[-.]P[A-Z]?$|[-.](?:WT|WS|W|U|UN|R|RT)$|^[A-Z]{4}[WUR]$")


def _norm(s) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower())
    s = _SUFFIX.sub(" ", s)
    return " ".join(s.split())


def _sim(a, b) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    return max(jac, SequenceMatcher(None, a, b).ratio())


def _get(ep, params):
    for attempt in range(8):
        try:
            return fc.get_json(ep, params, ttl=fc.TTL_SLOW) or []
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(20 * (attempt + 1))
                continue
            return []
    return []


def resolve(sym: str, name: str, isin=None, cusip=None) -> dict:
    rec = {"symbol": sym, "fmp_symbol": None, "method": None, "score": np.nan, "fmp_exchange": None,
           "fmp_currency": None, "use_for_prices": 0, "use_for_fundamentals": 0, "note": ""}
    cands = []
    if isinstance(isin, str) and len(isin) == 12:
        for d in _get("search-isin", {"isin": isin}):
            cands.append(("isin", d))
    if isinstance(cusip, str) and len(cusip) >= 8:
        for d in _get("search-cusip", {"cusip": cusip}):
            cands.append(("cusip", d))
    base = sym.split(".")[0].split("-")[0]
    if len(base) >= 2:
        for d in _get("search-symbol", {"query": base, "limit": 10}):
            cands.append(("symbol", d))
    if name and len(str(name)) >= 4:
        for d in _get("search-name", {"query": str(name)[:40], "limit": 10}):
            cands.append(("name", d))
    best = None
    for method, d in cands:
        fs = str(d.get("symbol") or "")
        if not fs or fs == sym:
            continue
        exch = str(d.get("exchangeShortName") or d.get("exchange") or "").upper()
        nm = d.get("name") or d.get("companyName") or ""
        s = 1.0 if method in ("isin", "cusip") else _sim(name, nm)
        if s < 0.75:
            continue
        # prefer: identifier match > primary exchange > secondary (German
        # regional) > OTC; then name similarity
        tier = 3 if method in ("isin", "cusip") else (2 if exch in PRIMARY else (1 if exch in SECONDARY else 0))
        key = (tier, s)
        if best is None or key > best[0]:
            best = (key, method, fs, exch, nm, s)
    if best is None:
        rec["note"] = "no FMP match"
        return rec
    _, method, fs, exch, nm, s = best
    # verify: does FMP actually serve data under this symbol?
    prof = _get("profile", {"symbol": fs})
    p0 = prof[0] if prof else {}
    if str(p0.get("isEtf")).lower() == "true" or str(p0.get("isFund")).lower() == "true":
        rec["note"] = f"match {fs} is a fund"
        return rec
    px = _get("historical-price-eod/light", {"symbol": fs, "from": "2024-01-01"})
    st = _get("income-statement", {"symbol": fs, "period": "annual", "limit": 1})
    has_px, has_st = bool(px), bool(st)
    rec.update({"fmp_symbol": fs, "method": method, "score": round(float(s), 3), "fmp_exchange": exch,
                "fmp_currency": p0.get("currency"), "use_for_fundamentals": int(has_st or has_px)})
    core = re.sub(r"\.[A-Z]{1,3}$", "", sym)             # test the line itself, not its exchange suffix
    same_security = not (B_SHARE.match(sym) or NONCOMMON.search(core)) and exch not in ("OTC", "PNK")
    rec["use_for_prices"] = int(has_px and same_security)
    rec["note"] = ("prices+fundamentals" if rec["use_for_prices"] and has_st else
                   "fundamentals only" if has_st else "prices only" if rec["use_for_prices"] else "no data under match")
    if not (has_px or has_st):
        rec["fmp_symbol"] = None
    return rec


def targets() -> pd.DataFrame:
    g = pd.read_csv("asymmetry_global.csv", low_memory=False).drop_duplicates("symbol")
    cols = ["symbol", "name"] + [c for c in ("isin", "cusip") if c in g.columns]
    g = g[cols].copy()
    g["symbol"] = g["symbol"].astype(str)
    # symbols FMP gave no prices for, or no statements for
    no_px = set()
    if os.path.exists("fmp_price_universe.csv"):
        u = pd.read_csv("fmp_price_universe.csv")
        no_px = set(u.loc[u["status"] != "ok", "symbol"].astype(str))
        no_px |= set(g["symbol"]) - set(u["symbol"].astype(str))
    no_st = set()
    if os.path.exists("fmp_statements.csv"):
        s = pd.read_csv("fmp_statements.csv", usecols=["symbol", "fmp_st_years_of_history"])
        no_st = set(s.loc[s["fmp_st_years_of_history"].isna(), "symbol"].astype(str))
        no_st |= set(g["symbol"]) - set(s["symbol"].astype(str))
    t = g[g["symbol"].isin(no_px | no_st)].copy()
    t["needs_prices"] = t["symbol"].isin(no_px).astype(int)
    t["needs_statements"] = t["symbol"].isin(no_st).astype(int)
    return t


def main(workers: int = 4) -> None:
    t = targets()
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = t[~t["symbol"].isin(done)]
    print(f"resolver: {len(t)} symbols lack FMP prices ({int(t['needs_prices'].sum())}) or statements "
          f"({int(t['needs_statements'].sum())}); {len(done)} done, {len(todo)} to resolve", flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        it = ex.map(lambda r: resolve(r.symbol, r.name, getattr(r, "isin", None), getattr(r, "cusip", None)),
                    todo.itertuples(index=False))
        for i, rec in enumerate(it, 1):
            rows.append(rec)
            if i % 500 == 0 or i == len(todo):
                pd.DataFrame(rows).reindex(columns=COLS).to_csv(OUT, mode="a", header=not os.path.exists(OUT),
                                                                index=False)
                rows = []
                print(f"  {i}/{len(todo)} | hit_rate={fc.cache_stats()['hit_rate']}", flush=True)
    m = pd.read_csv(OUT)
    ok = m["fmp_symbol"].notna()
    print(f"resolved {int(ok.sum())} of {len(m)}: prices {int(m['use_for_prices'].sum())}, "
          f"fundamentals {int(m['use_for_fundamentals'].sum())}", flush=True)
    print("RESOLVER_DONE", flush=True)


if __name__ == "__main__":
    main()
