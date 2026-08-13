"""13F-delta scoring leg (separate from existing layers).

Per AUDIT.md S2.2/S2.7: 13F is the quarterly filing every $100M+
institutional manager must submit. The DELTA -- quarter-over-quarter
position changes -- is the alpha:
  - Activist accumulation pre-13D (Elliott/Trian/Mantle Ridge often
    quietly accumulate below the 5% 13D trigger; 13F shows it 45-90d
    later)
  - Coval-Stafford forced selling: which stocks did a redeeming fund
    dump (replaces our proxy)
  - Smart-money baskets: Buffett/Greenblatt/Klarman/Dalio top
    holdings outperform

This module fetches recent 13F-HR filings from a curated list of
"smart money" and "known activist" firms, computes per-ticker
position deltas vs prior quarter, and produces a scoring leg.

OUTPUT: form_13f_delta.json
  {ticker: {
    net_filers_buying: int,       # how many of the watched managers added
    net_filers_selling: int,
    activist_added: int,          # how many KNOWN activists added vs trimmed
    activist_trimmed: int,
    smart_money_added: list,      # filer names that added
    smart_money_trimmed: list,
    score: float,                 # net additive bonus
    reasons: str,
  }}

ADDITIVE: separate leg, does not modify any existing 13F data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "form_13f_delta.json"

# Curated "smart money" + "known activists" -- CIKs are stable IDs
# 13F filers are identified by CIK in EDGAR. Some we know by name;
# we resolve CIK on the fly via the EDGAR search-by-name endpoint.
SMART_MONEY_NAMES = [
    # Activists (typically file with strategy)
    "elliott investment management",
    "starboard value lp",
    "trian fund management",
    "engaged capital llc",
    "mantle ridge lp",
    "ancora holdings",
    "jana partners",
    "valueact capital",
    "third point llc",
    "pershing square capital",
    "icahn capital",
    "carl c icahn",
    "engine capital",
    "land & buildings",
    "politan capital",
    "saba capital",

    # Long-term smart money (concentrated value)
    "berkshire hathaway",
    "gotham asset management",   # Greenblatt
    "baupost group",             # Klarman
    "bridgewater associates",    # Dalio
    "renaissance technologies",
    "soros fund management",
    "appaloosa lp",              # Tepper
    "greenhaven road capital",
    "tweedy browne",
    "ruane cunniff",             # Sequoia
    "pzena investment management",
    "lone pine capital",
    "viking global",
    "tiger global",
    "akre capital",
    "polen capital",
    "select equity group",
    "wedgewood partners",
    "longleaf partners",
    "mar vista",
    "voss capital",
    "kingdom capital",
    "rangeley capital",
    "bonhoeffer capital",
    "alluvial capital",
    "arquitos capital",
]


def search_cik_by_name(name: str) -> str | None:
    """Search EDGAR for filer CIK by company name."""
    try:
        from edgar import _get
        import urllib.parse
    except ImportError:
        return None
    try:
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&company={urllib.parse.quote(name)}&type=13F-HR"
               "&dateb=&owner=include&count=10&output=atom")
        r = _get(url)
        m = re.search(r"CIK=(\d{6,10})", r.text)
        if m:
            return f"{int(m.group(1)):010d}"
    except Exception:
        pass
    return None


def fetch_13f_filings(cik: str, n_recent: int = 4) -> list[dict]:
    """Return last n_recent 13F-HR filings for a CIK."""
    try:
        from edgar import _get
    except ImportError:
        return []
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        sub = _get(url).json()
    except Exception:
        return []
    recent = sub.get("filings", {}).get("recent", {})
    out = []
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    pds = recent.get("primaryDocument", [])
    for form, acc, dt, pd in zip(forms, accs, dates, pds):
        if form == "13F-HR":
            out.append({
                "accession": acc, "filing_date": dt,
                "primary_doc": pd,
            })
            if len(out) >= n_recent:
                break
    return out


def parse_13f_holdings(cik: str, accession: str) -> dict[str, dict]:
    """Parse a 13F-HR information table.
    Returns {cusip: {value_usd: int, shares: int, name: str}}."""
    try:
        from edgar import _get
    except ImportError:
        return {}
    acc_no = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}"
    # Find the information table xml/html
    try:
        idx = _get(f"{base}/index.json").json()
    except Exception:
        return {}
    table_url = None
    for f in (idx.get("directory", {}).get("item") or []):
        name = f.get("name", "")
        if "table" in name.lower() or name.lower().endswith(".xml"):
            if name.lower().endswith(".xml") and "table" in name.lower():
                table_url = f"{base}/{name}"
                break
    if not table_url:
        # fallback: try common file name patterns
        for fname in ("informationtable.xml", "infotable.xml"):
            try:
                r = _get(f"{base}/{fname}")
                if r.status_code == 200 and r.text:
                    table_url = f"{base}/{fname}"
                    break
            except Exception:
                continue
    if not table_url:
        return {}
    try:
        r = _get(table_url)
        xml_text = r.text
    except Exception:
        return {}

    # Strip namespaces for parsing
    xml_text = re.sub(r' xmlns="[^"]+"', "", xml_text)
    xml_text = re.sub(r"<n1:", "<", xml_text)
    xml_text = re.sub(r"</n1:", "</", xml_text)
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return {}

    out = {}
    for entry in root.findall(".//infoTable"):
        cusip = entry.findtext("cusip", "").strip()
        name = (entry.findtext("nameOfIssuer") or "").strip()
        if not cusip:
            continue
        value_text = (entry.findtext("value") or "0").replace(",", "")
        shrs_text = (entry.findtext(".//sshPrnamt") or "0").replace(",", "")
        try:
            value = int(value_text) * 1000   # 13F reports value in $000s
            shrs = int(shrs_text)
        except Exception:
            continue
        if cusip in out:
            out[cusip]["value_usd"] += value
            out[cusip]["shares"] += shrs
        else:
            out[cusip] = {"value_usd": value, "shares": shrs, "name": name}
    return out


def issuer_name_to_ticker(name: str, name_idx: dict) -> str | None:
    """Resolve a 13F issuer name to a ticker using a fuzzy
    name->ticker index built from EDGAR company_tickers."""
    n = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    n = re.sub(r"\s+", " ", n).strip()
    if not n:
        return None
    # Exact + prefix lookup
    if n in name_idx:
        return name_idx[n]
    # Try without common suffixes
    for sfx in (" COM", " COMMON", " CL A", " CL B", " INC",
                 " CORP", " CORPORATION", " HOLDINGS", " LTD",
                 " PLC", " NV", " SE", " AG", " ORD", " ADR"):
        candidate = n.replace(sfx, "").strip()
        if candidate in name_idx:
            return name_idx[candidate]
    # Try first 3 words
    first3 = " ".join(n.split()[:3])
    return name_idx.get(first3)


def build_name_index() -> dict:
    """Build name->ticker map from EDGAR's company_tickers.json."""
    try:
        from edgar import _get
    except ImportError:
        return {}
    try:
        data = _get("https://www.sec.gov/files/company_tickers.json").json()
    except Exception:
        return {}
    idx = {}
    for v in data.values():
        if not isinstance(v, dict):
            continue
        tk = v.get("ticker")
        name = v.get("title", "")
        if not tk or not name:
            continue
        n = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
        n = re.sub(r"\s+", " ", n).strip()
        idx[n] = tk
        # also index without common corporate suffixes
        for sfx in (" CORP", " CORPORATION", " INC", " INCORPORATED",
                     " HOLDINGS", " LTD", " PLC", " CO", " LLC"):
            stripped = n.replace(sfx, "").strip()
            if stripped and stripped not in idx:
                idx[stripped] = tk
    return idx


def cusip_ticker_map() -> dict[str, str]:
    """Build a CUSIP -> ticker map from cancel_10b5_1.json (no CUSIPs
    inside) -- fallback to yfinance ticker info on demand. For now
    we use cik_to_ticker via EDGAR's company_tickers.json and treat
    each CUSIP as opaque; downstream we resolve by ticker post-fetch.
    Returns empty -- we resolve per-issuer via EDGAR ticker lookup.
    """
    return {}


def cusip_to_ticker_via_edgar(cusip: str, cache: dict) -> str | None:
    """One-shot CUSIP -> ticker lookup via EDGAR full-text search."""
    if cusip in cache:
        return cache[cusip]
    try:
        from edgar import _get
        import urllib.parse
    except ImportError:
        return None
    try:
        url = ("https://efts.sec.gov/LATEST/search-index"
               f"?q={urllib.parse.quote(cusip)}&forms=10-K,DEF+14A"
               "&hits=1")
        r = _get(url).json()
        hits = r.get("hits", {}).get("hits", [])
        if not hits:
            cache[cusip] = None
            return None
        src = hits[0].get("_source", {})
        tickers = src.get("tickers") or []
        tk = tickers[0] if tickers else None
        cache[cusip] = tk
        return tk
    except Exception:
        cache[cusip] = None
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-filers", type=int, default=15,
                    help="max 13F filers to process")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    print(f"Resolving CIKs for {len(SMART_MONEY_NAMES)} smart-money names...",
          file=sys.stderr, flush=True)
    filer_ciks = {}
    for name in SMART_MONEY_NAMES[:args.limit_filers * 2]:
        cik = search_cik_by_name(name)
        if cik:
            filer_ciks[name] = cik
            print(f"  {name:<40} CIK {cik}", file=sys.stderr)
        time.sleep(args.sleep)
        if len(filer_ciks) >= args.limit_filers:
            break
    print(f"  resolved {len(filer_ciks)} CIKs", file=sys.stderr)

    # Build issuer name -> ticker index from EDGAR company tickers
    print("\nBuilding company_tickers name index...", file=sys.stderr)
    name_idx = build_name_index()
    print(f"  indexed {len(name_idx)} issuer names", file=sys.stderr)

    # For each filer, pull latest 2 13F-HR filings (current vs prior Q)
    cusip_cache = {}
    per_ticker_changes = defaultdict(lambda: {
        "filers_added": [], "filers_trimmed": [],
        "filers_new": [], "filers_exited": [],
        "delta_value_usd": 0, "delta_shares": 0,
    })
    n_unresolved = 0   # holdings whose issuer name didn't map to a ticker

    activist_substr = (
        "elliott", "starboard", "trian", "engaged",
        "mantle ridge", "ancora", "jana", "valueact",
        "third point", "pershing", "icahn", "engine capital",
        "land &", "politan", "saba", "voss",
    )

    from datetime import datetime, timezone
    _today = datetime.now(timezone.utc).replace(tzinfo=None)
    filer_dates_used = {}

    for name, cik in filer_ciks.items():
        print(f"\n[{name}] CIK {cik}", file=sys.stderr, flush=True)
        filings = fetch_13f_filings(cik, n_recent=2)
        if len(filings) < 2:
            print(f"  only {len(filings)} 13F filings available", file=sys.stderr)
            continue
        cur = filings[0]
        prior = filings[1]

        # METHODOLOGY FIX (audit finding A2): the name->CIK resolution
        # can land on a stale/renamed entity whose most recent 13F is
        # YEARS old (observed: 2008, 2011, 2023 filings being treated
        # as the "current quarter"). Deltas from ancient filings are
        # not current signal. Gate: current filing must be <=200 days
        # old and the pair must be adjacent quarters (<=200 days apart).
        try:
            cur_dt = datetime.strptime(cur["filing_date"][:10], "%Y-%m-%d")
            prior_dt = datetime.strptime(prior["filing_date"][:10], "%Y-%m-%d")
        except Exception:
            print("  unparseable filing dates -- skipped", file=sys.stderr)
            continue
        if (_today - cur_dt).days > 200:
            print(f"  STALE: latest 13F {cur['filing_date']} "
                  f"({(_today - cur_dt).days}d old) -- skipped",
                  file=sys.stderr)
            continue
        if (cur_dt - prior_dt).days > 200:
            print(f"  NON-ADJACENT quarters ({cur['filing_date']} vs "
                  f"{prior['filing_date']}) -- skipped", file=sys.stderr)
            continue
        filer_dates_used[name] = {"current": cur["filing_date"],
                                   "prior": prior["filing_date"]}
        print(f"  current Q: {cur['filing_date']}  prior Q: {prior['filing_date']}",
              file=sys.stderr)

        cur_h = parse_13f_holdings(cik, cur["accession"])
        time.sleep(args.sleep)
        prior_h = parse_13f_holdings(cik, prior["accession"])
        time.sleep(args.sleep)
        print(f"  parsed: {len(cur_h)} cur, {len(prior_h)} prior",
              file=sys.stderr)

        is_activist = any(s in name.lower() for s in activist_substr)

        # Compute deltas
        all_cusips = set(cur_h) | set(prior_h)
        for cusip in all_cusips:
            cv = cur_h.get(cusip, {}).get("value_usd", 0)
            pv = prior_h.get(cusip, {}).get("value_usd", 0)
            cs = cur_h.get(cusip, {}).get("shares", 0)
            ps = prior_h.get(cusip, {}).get("shares", 0)
            dv = cv - pv
            ds = cs - ps
            if abs(dv) < 100_000:   # filter dust
                continue
            # Plausibility gate: no single 13F filer moves >$25B in one
            # name in one quarter. Values beyond that are parse artifacts
            # (units confusion or a mis-attributed information-table row
            # -- see the GPGI $86B Starboard "position") and must not
            # create activist-add signals. Counted, not silently dropped.
            if abs(dv) > 25_000_000_000:
                n_unresolved += 1
                continue

            # Resolve via 13F's nameOfIssuer field (much more reliable)
            issuer = cur_h.get(cusip, {}).get("name") or prior_h.get(cusip, {}).get("name")
            if not issuer:
                n_unresolved += 1
                continue
            tk = issuer_name_to_ticker(issuer, name_idx)
            if not tk:
                # Silent-drop audit: unresolved issuer names are a real
                # coverage gap (not an error) -- count them so the drop
                # is visible rather than invisible.
                n_unresolved += 1
                continue

            rec = per_ticker_changes[tk]
            if pv == 0 and cv > 0:
                rec["filers_new"].append(name)
            elif cv == 0 and pv > 0:
                rec["filers_exited"].append(name)
            elif dv > 0:
                rec["filers_added"].append(name)
            else:
                rec["filers_trimmed"].append(name)
            rec["delta_value_usd"] += dv
            rec["delta_shares"] += ds

    # Score per ticker
    out = {}
    for tk, rec in per_ticker_changes.items():
        added = rec["filers_added"] + rec["filers_new"]
        trimmed = rec["filers_trimmed"] + rec["filers_exited"]
        n_added = len(added)
        n_trimmed = len(trimmed)
        activist_added = sum(1 for n in added if any(s in n.lower() for s in activist_substr))
        activist_trimmed = sum(1 for n in trimmed if any(s in n.lower() for s in activist_substr))
        new_pos = len(rec["filers_new"])

        score = 0.0
        reasons = []
        if n_added >= 3:
            score += 18; reasons.append(f"{n_added} smart-money added")
        elif n_added >= 2:
            score += 10
        elif n_added >= 1:
            score += 4
        if activist_added >= 1:
            score += 15; reasons.append(f"{activist_added} known activist added")
        if new_pos >= 1:
            score += 8; reasons.append(f"{new_pos} new position(s)")
        # Penalty for net exits
        if n_trimmed > n_added * 2:
            score -= 8; reasons.append("net smart-money exits")
        # Activist exits are particularly bearish
        if activist_trimmed > 0 and activist_added == 0:
            score -= 12; reasons.append(f"{activist_trimmed} activist trim")

        # Cap negative
        score = max(score, -15)

        out[tk] = {
            "n_filers_adding": n_added,
            "n_filers_trimming": n_trimmed,
            "activist_added": activist_added,
            "activist_trimmed": activist_trimmed,
            "new_positions": new_pos,
            "delta_value_usd": rec["delta_value_usd"],
            "filers_adding": added[:8],
            "filers_trimming": trimmed[:8],
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    # Provenance: record which filings fed each delta so staleness is
    # auditable downstream (audit finding A2 -- prior output had no
    # filing-date trail). Stored under a reserved meta key that the
    # consensus loader ignores (not a valid ticker).
    out["_META_FILINGS_USED"] = filer_dates_used
    out["_META_UNRESOLVED_HOLDINGS"] = n_unresolved
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT} ({len(out) - 2} tickers, "
          f"{len(filer_dates_used)} filers used, "
          f"{n_unresolved} material holdings unresolved to ticker)")

    ranked = sorted(
        ((tk, v) for tk, v in out.items() if not tk.startswith("_META")),
        key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 by 13F-delta score ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<7} score={v['score']:<5.0f} added={v['n_filers_adding']} "
              f"trim={v['n_filers_trimming']} act+={v['activist_added']} "
              f"new={v['new_positions']} {v['reasons'][:50]}")
    print(f"\n=== BOTTOM 10 (smart-money exits) ===")
    for tk, v in ranked[-10:]:
        if v["score"] < 0:
            print(f"  {tk:<7} score={v['score']:<5.0f} {v['reasons'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
