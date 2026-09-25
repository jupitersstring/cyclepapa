"""Distress / caution layer: filings that say 'this may be a value trap'.

Per name (US filers via EDGAR; scores for every FMP symbol):
  8-K Item 4.02   non-reliance on previously issued financial statements
  8-K Item 3.01   delisting notice / failure to meet a listing standard
  8-K Item 1.03   bankruptcy or receivership
  8-K Item 2.06   material impairment
  NT 10-K / NT 10-Q   late filing
  going concern   'substantial doubt ... going concern' in a 10-K / 10-Q
                  (EDGAR full-text search, last 12 months)
  reverse split   FMP split history (ratio < 1) in the last 18 months
  Altman Z / Piotroski   FMP scores bulk (Z < 1.1 = distress zone; F <= 2 = weak)

Used as a CAUTION signal (sizing cuts, no book floor, flags on every tab), not
as a ranking input, after the event study in distress_validate (DISTRESS_VALIDATION.md)
shows what each flag has meant for subsequent returns.

Output: distress_flags.json  {ticker: {"flags": [{kind, date, detail}], "altman_z", "piotroski", "severity"}}
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import edgar_doc
import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "distress_flags.json"
GC_CACHE = ROOT / "fmp_cache" / "going_concern.json"

ITEMS = {"4.02": ("non_reliance", "8-K 4.02: prior financial statements can no longer be relied on"),
         "3.01": ("delisting_notice", "8-K 3.01: delisting notice / listing-standard failure"),
         "1.03": ("bankruptcy", "8-K 1.03: bankruptcy or receivership"),
         "2.06": ("impairment", "8-K 2.06: material impairment")}
SEVERITY = {"bankruptcy": 5, "non_reliance": 3, "going_concern": 3, "delisting_notice": 2, "late_filing": 2,
            "reverse_split": 1, "impairment": 1, "altman_distress": 1}


def going_concern(days=365):
    """{cik: [(date, form)]} for 10-K / 10-Q filings with going-concern language (EDGAR FTS)."""
    if GC_CACHE.exists() and time.time() - GC_CACHE.stat().st_mtime < 3 * 86400:
        return json.loads(GC_CACHE.read_text())
    end = date.today()
    out = {}
    # EDGAR full-text search caps at 10,000 hits per query: walk it in monthly windows
    for k in range(0, days, 30):
        d1, d0 = end - timedelta(days=k), end - timedelta(days=k + 30)
        for page in range(0, 2000, 100):
            url = ("https://efts.sec.gov/LATEST/search-index?q=%22raise%20substantial%20doubt%22%20%22going%20concern%22"
                   f"&forms=10-K,10-Q&dateRange=custom&startdt={d0}&enddt={d1}&from={page}")
            try:
                j = edgar_doc._get(url).json()
            except Exception:
                break
            hits = (j.get("hits") or {}).get("hits") or []
            for h in hits:
                s = h.get("_source") or {}
                for c in s.get("ciks") or []:
                    out.setdefault(str(int(c)), []).append((s.get("file_date"), s.get("form")))
            if len(hits) < 100:
                break
    GC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GC_CACHE.write_text(json.dumps(out))
    return out


def reverse_splits(months=18):
    """{symbol: [(date, 'n-for-m')]} from the FMP split calendar (reverse = numerator < denominator)."""
    out = {}
    end = date.today()
    for k in range(0, months * 31, 90):
        d1, d0 = end - timedelta(days=k), end - timedelta(days=k + 90)
        try:
            rows = fmp.get_json("splits-calendar", **{"from": d0.isoformat(), "to": d1.isoformat()})
        except Exception:
            rows = []
        for r in rows or []:
            n, d = r.get("numerator") or 0, r.get("denominator") or 0
            if n and d and n < d:
                out.setdefault(r["symbol"], []).append((r.get("date"), f"1-for-{d / n:g}"))
    return out


def scores():
    rows = fmp.get_bulk_csv("scores-bulk", "scores-bulk.csv", max_age_hours=72)
    out = {}
    for r in rows:
        try:
            z = float(r.get("altmanZScore")) if r.get("altmanZScore") not in (None, "") else None
            f = int(float(r.get("piotroskiScore"))) if r.get("piotroskiScore") not in (None, "") else None
        except ValueError:
            continue
        out[r["symbol"]] = (z, f)
    return out


def edgar_flags(args):
    tk, cik, days = args
    cut = (date.today() - timedelta(days=days)).isoformat()
    flags = []
    try:
        fs = edgar_doc.filings(cik, forms=("8-K", "8-K/A", "NT 10-K", "NT 10-Q", "NT 10-K/A", "NT 10-Q/A"))
    except Exception:
        fs = []
    for form, acc, d, items in fs:
        if d < cut:
            continue
        if form.startswith("NT "):
            flags.append({"kind": "late_filing", "date": d, "detail": f"{form}: late periodic report",
                          "url": edgar_doc.url(cik, acc)})
            continue
        for it in str(items or "").split(","):
            it = it.strip()
            if it in ITEMS:
                k, txt = ITEMS[it]
                flags.append({"kind": k, "date": d, "detail": txt, "url": edgar_doc.url(cik, acc)})
    return tk, flags


def cik_map():
    """ticker -> CIK: FMP profiles first (complete), quote store as the fallback."""
    import csv, glob
    m = {}
    for fn in glob.glob(str(ROOT / "fmp_cache" / "profile-bulk_part*.csv")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            if r.get("cik"):
                m[r["symbol"]] = r["cik"]
    for t, v in json.loads((ROOT / "yfinance_quick.json").read_text()).items():
        if (v or {}).get("cik") and t not in m:
            m[t] = v["cik"]
    return m


def build(tickers, days=365):
    yq = {t: {"cik": c} for t, c in cik_map().items()}
    fin = json.loads((ROOT / "name_financials.json").read_text())
    gc = going_concern(days)
    rs = reverse_splits()
    sc = scores()
    jobs = [(t, (yq.get(t) or {}).get("cik"), days) for t in tickers if (yq.get(t) or {}).get("cik")]
    with ThreadPoolExecutor(6) as ex:
        ed = dict(ex.map(edgar_flags, jobs))
    out = {}
    for t in tickers:
        flags = list(ed.get(t) or [])
        cik = (yq.get(t) or {}).get("cik")
        if cik and str(int(cik)) in gc:
            ds = sorted(d for d, _ in gc[str(int(cik))] if d)
            flags.append({"kind": "going_concern", "date": ds[-1], "detail":
                          f"going-concern doubt in {len(ds)} 10-K/10-Q filing(s) in 12m (latest {ds[-1]})"})
        for d, r in rs.get(t) or []:
            flags.append({"kind": "reverse_split", "date": d, "detail": f"reverse split {r}"})
        z, f = sc.get(t, (None, None))
        kind = (fin.get(t) or {}).get("kind")
        if z is not None and z < 1.1 and kind in ("operating", "ep", None):   # Z is not defined for banks / insurers
            flags.append({"kind": "altman_distress", "date": None, "detail": f"Altman Z {z:.2f} (distress zone < 1.1)"})
        if not flags and z is None and f is None:
            continue
        sev = sum(SEVERITY.get(x["kind"], 0) for x in {x["kind"]: x for x in flags}.values())
        out[t] = {"flags": sorted(flags, key=lambda x: x.get("date") or "", reverse=True), "altman_z": z,
                  "piotroski": f, "severity": sev}
    return out


def line(r):
    """One short caution line for the tabs."""
    if not r or not r.get("flags"):
        return ""
    seen, bits = set(), []
    for x in sorted(r["flags"], key=lambda x: -SEVERITY.get(x["kind"], 0)):
        if x["kind"] in seen:
            continue
        seen.add(x["kind"])
        bits.append(x["detail"].split(":")[0] if x["kind"] not in ("going_concern", "altman_distress", "reverse_split")
                    else x["detail"])
    return "⚠ " + "; ".join(bits[:3])


def main() -> int:
    import sys
    if sys.argv[1:]:
        tickers = sys.argv[1:]
    else:
        import ownership_layer
        tickers = ownership_layer.universe()
    print(f"distress flags: {len(tickers)} names")
    out = build(tickers)
    OUT.write_text(json.dumps(out, indent=1))
    from collections import Counter
    c = Counter(x["kind"] for r in out.values() for x in {y["kind"]: y for y in r["flags"]}.values())
    print(f"wrote {OUT.name}: {len(out)} names; flags by kind {dict(c)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
