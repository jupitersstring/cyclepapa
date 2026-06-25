"""N-PORT-P real-data Coval-Stafford forced-selling leg (S2.2).

Replaces the yfinance proxy with actual mutual-fund holdings deltas
parsed from SEC N-PORT-P filings.

N-PORT-P is the monthly fund holdings filing. Per Coval-Stafford (JFE
2007), the alpha pool is stocks getting indiscriminately dumped by
funds for non-fundamental reasons (redemption pressure). The DIRECT
measurement is "how many large funds sold meaningful positions in this
ticker in the last 60 days" -- aggregated across our curated list.

This module:
  1. Walks a curated list of ~40 large mutual fund filer CIKs.
  2. For each fund, fetches the 2 most recent N-PORT-P filings.
  3. Parses the holdings table from each (XML).
  4. Computes per-CUSIP net change (current - prior).
  5. Resolves CUSIP / issuer name -> ticker via EDGAR company_tickers
     index.
  6. Aggregates per-ticker:
       n_funds_selling   (funds with reduced position)
       n_funds_buying    (funds with increased position)
       net_value_sold_usd
  7. Scores by Coval-Stafford intensity:
       Multiple funds selling concurrently + deep drawdown = the
       real signal. Single-fund selling = noise.

ADDITIVE: separate output file (nport_forced_selling.json). Existing
coval_stafford_proxy.json layer remains intact.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "nport_forced_selling.json"


# Curated list of mutual fund filers (40 large funds across active
# and index strategies). The 13F-style CIK lookup works for these.
# We seed with names; CIKs resolved via EDGAR search.
LARGE_FUNDS = [
    # Active value / equity
    "DODGE & COX FUNDS",
    "VANGUARD WELLINGTON FUND",
    "FIDELITY CONTRAFUND",
    "FIDELITY MAGELLAN FUND",
    "T. ROWE PRICE GROWTH STOCK",
    "T. ROWE PRICE EQUITY INCOME",
    "OAKMARK FUNDS",
    "TWEEDY BROWNE FUND",
    "FIRST EAGLE GLOBAL FUND",
    "LONGLEAF PARTNERS FUND",
    "SEQUOIA FUND",
    "ROYCE FUND",
    "BAUPOST",
    "GREENBLATT GOTHAM",
    "ARTISAN PARTNERS FUND",
    "PRIMECAP ODYSSEY",
    "ARIEL FUND",
    "CALAMOS GROWTH",
    "PARNASSUS FUND",
    "JANUS HENDERSON GROWTH",

    # Large-cap balanced / income
    "AMERICAN FUNDS GROWTH",
    "AMERICAN FUNDS INVESTMENT",
    "AMERICAN FUNDS WASHINGTON",
    "AMERICAN FUNDS NEW ECONOMY",
    "BLACKROCK CAPITAL APPRECIATION",
    "INVESCO COMSTOCK",
    "MFS VALUE FUND",
    "DELAWARE VALUE",
    "JOHN HANCOCK CLASSIC VALUE",

    # Small/mid value and growth
    "ROYCE TOTAL RETURN",
    "VANGUARD EXPLORER",
    "T. ROWE PRICE SMALL-CAP",
    "FIDELITY LOW-PRICED STOCK",
    "FIDELITY SMALL CAP STOCK",
    "WASATCH SMALL CAP",
    "AMG YACKTMAN",
    "FPA CAPITAL",
    "DODGE & COX BALANCED",
]


def cik_for_fund(name: str) -> str | None:
    """Search EDGAR for filer CIK by name (best effort)."""
    try:
        from edgar import _get
        import urllib.parse
    except ImportError:
        return None
    try:
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&company={urllib.parse.quote(name[:40])}&type=NPORT-P"
               "&dateb=&owner=include&count=5&output=atom")
        r = _get(url)
        m = re.search(r"CIK=(\d{6,10})", r.text)
        if m:
            return f"{int(m.group(1)):010d}"
    except Exception:
        pass
    return None


def recent_nport_filings(cik: str, n: int = 2) -> list[dict]:
    """Return last n NPORT-P filings for a CIK."""
    try:
        from edgar import _get
    except ImportError:
        return []
    try:
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    except Exception:
        return []
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    out = []
    for form, acc, dt, doc in zip(forms, accs, dates, docs):
        if form == "NPORT-P":
            out.append({"accession": acc, "filing_date": dt,
                         "primary_doc": doc})
            if len(out) >= n:
                break
    return out


def parse_nport(cik: str, accession: str) -> dict[str, dict]:
    """Parse N-PORT-P primary XML for holdings.
    Returns {cusip: {value_usd, shares, name}}."""
    try:
        from edgar import _get
    except ImportError:
        return {}
    acc_no = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}"
    # N-PORT-P primary is typically primary_doc.xml or primarydoc.xml
    try:
        idx = _get(f"{base}/index.json").json()
    except Exception:
        return {}
    primary_xml = None
    for f in (idx.get("directory", {}).get("item") or []):
        name = f.get("name", "")
        if name.lower().endswith(".xml") and ("primary" in name.lower()
                                                or "doc1" in name.lower()):
            primary_xml = f"{base}/{name}"
            break
    if not primary_xml:
        # fallback: try common names
        for fname in ("primary_doc.xml", "primarydoc.xml"):
            try:
                r = _get(f"{base}/{fname}")
                if r.status_code == 200 and "<" in r.text[:1000]:
                    primary_xml = f"{base}/{fname}"
                    break
            except Exception:
                continue
    if not primary_xml:
        return {}
    try:
        xml_text = _get(primary_xml).text
    except Exception:
        return {}
    xml_text = re.sub(r' xmlns="[^"]+"', "", xml_text)
    xml_text = re.sub(r"<n1:", "<", xml_text)
    xml_text = re.sub(r"</n1:", "</", xml_text)
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return {}

    out = {}
    # N-PORT holdings are in invstOrSec subtree
    for entry in root.iter("invstOrSec"):
        cusip = (entry.findtext("cusip") or "").strip()
        name = (entry.findtext("name") or "").strip()
        if not cusip and not name:
            continue
        # Some holdings have no CUSIP (e.g., FX) -- skip
        if not cusip or cusip == "000000000" or cusip.startswith("9999"):
            continue
        value_text = (entry.findtext("valUSD") or "0")
        shrs_text = (entry.findtext("balance") or "0")
        try:
            value = float(value_text)
            shrs = float(shrs_text)
        except Exception:
            continue
        # Aggregate same CUSIP across share classes
        if cusip in out:
            out[cusip]["value_usd"] += value
            out[cusip]["shares"] += shrs
        else:
            out[cusip] = {"value_usd": value, "shares": shrs, "name": name}
    return out


def build_name_index() -> dict:
    """Reuse from form_13f_delta."""
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
        for sfx in (" CORP", " CORPORATION", " INC", " INCORPORATED",
                     " HOLDINGS", " LTD", " PLC", " CO", " LLC"):
            stripped = n.replace(sfx, "").strip()
            if stripped and stripped not in idx:
                idx[stripped] = tk
    return idx


def resolve_issuer(name: str, idx: dict) -> str | None:
    if not name:
        return None
    n = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    n = re.sub(r"\s+", " ", n).strip()
    if n in idx:
        return idx[n]
    # strip common holding-class suffixes
    for sfx in (" COMMON STOCK", " COMMON", " COM", " CL A", " CL B",
                 " A SHARES", " SHARES", " ORD", " ADR", " ORDINARY",
                 " ORD SHS"):
        candidate = n.replace(sfx, "").strip()
        if candidate in idx:
            return idx[candidate]
    # try first 3 words
    f3 = " ".join(n.split()[:3])
    return idx.get(f3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-funds", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    print(f"Resolving CIKs for {len(LARGE_FUNDS)} funds...",
          file=sys.stderr, flush=True)
    fund_ciks = {}
    for name in LARGE_FUNDS:
        cik = cik_for_fund(name)
        if cik:
            fund_ciks[name] = cik
            print(f"  {name:<38} CIK {cik}", file=sys.stderr)
        time.sleep(args.sleep)
        if len(fund_ciks) >= args.limit_funds:
            break
    print(f"  resolved {len(fund_ciks)}", file=sys.stderr)

    print("Building issuer name index...", file=sys.stderr)
    name_idx = build_name_index()
    print(f"  {len(name_idx)} issuer name mappings", file=sys.stderr)

    # For each fund, parse last 2 N-PORTs
    per_ticker = defaultdict(lambda: {
        "n_funds_selling": 0, "n_funds_buying": 0,
        "n_funds_exited": 0, "n_funds_new": 0,
        "net_value_change_usd": 0.0,
        "sellers": [], "buyers": [],
    })
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())

    n_parsed = 0
    for name, cik in fund_ciks.items():
        print(f"\n[{name[:32]}] CIK {cik}", file=sys.stderr, flush=True)
        filings = recent_nport_filings(cik, n=2)
        time.sleep(args.sleep)
        if len(filings) < 2:
            print(f"  only {len(filings)} filings", file=sys.stderr)
            continue
        cur = parse_nport(cik, filings[0]["accession"])
        time.sleep(args.sleep)
        prior = parse_nport(cik, filings[1]["accession"])
        time.sleep(args.sleep)
        print(f"  cur={len(cur)} prior={len(prior)}", file=sys.stderr)
        n_parsed += 1

        all_cusips = set(cur) | set(prior)
        for cusip in all_cusips:
            cv = cur.get(cusip, {}).get("value_usd", 0)
            pv = prior.get(cusip, {}).get("value_usd", 0)
            issuer = (cur.get(cusip, {}).get("name")
                      or prior.get(cusip, {}).get("name"))
            tk = resolve_issuer(issuer or "", name_idx)
            if not tk:
                continue
            dv = cv - pv
            # Filter dust (changes < $50K)
            if abs(dv) < 50_000:
                continue
            rec = per_ticker[tk]
            rec["net_value_change_usd"] += dv
            if pv == 0 and cv > 0:
                rec["n_funds_new"] += 1
                rec["buyers"].append(name[:20])
            elif cv == 0 and pv > 0:
                rec["n_funds_exited"] += 1
                rec["sellers"].append(name[:20])
            elif dv > 0:
                rec["n_funds_buying"] += 1
                rec["buyers"].append(name[:20])
            else:
                rec["n_funds_selling"] += 1
                rec["sellers"].append(name[:20])

    # Score per ticker: Coval-Stafford forced-selling intensity
    out = {}
    for tk, rec in per_ticker.items():
        n_sell = rec["n_funds_selling"] + rec["n_funds_exited"]
        n_buy = rec["n_funds_buying"] + rec["n_funds_new"]
        net = rec["net_value_change_usd"]
        score = 0.0
        reasons = []
        # Forced selling pressure: >=3 funds selling concurrently
        if n_sell >= 5:
            score += 25
            reasons.append(f"{n_sell} funds selling (forced)")
        elif n_sell >= 3:
            score += 15
            reasons.append(f"{n_sell} funds selling")
        elif n_sell >= 2:
            score += 6
        # Forced selling + drawdown = true Coval-Stafford signal
        y = yf.get(tk, {}) or {}
        try:
            px = float(y.get("price") or 0)
            hi = float(y.get("fwk_high") or 0)
            dd = (1 - px / hi) * 100 if hi > 0 else 0
        except Exception:
            dd = 0
        if dd > 50 and n_sell >= 3:
            score += 15
            reasons.append(f"DD {dd:.0f}% + sells (real Coval-Stafford)")
        elif dd > 30 and n_sell >= 2:
            score += 6
        # Net buying offsets
        if n_buy > n_sell * 2 and n_sell > 0:
            score -= 8
            reasons.append("net buyers > sellers")
        out[tk] = {
            "n_funds_selling": rec["n_funds_selling"],
            "n_funds_exited": rec["n_funds_exited"],
            "n_funds_buying": rec["n_funds_buying"],
            "n_funds_new": rec["n_funds_new"],
            "net_value_change_usd": round(rec["net_value_change_usd"], 0),
            "sellers": rec["sellers"][:8],
            "buyers": rec["buyers"][:8],
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT} ({len(out)} tickers; {n_parsed} funds parsed)")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 N-PORT forced-selling pressure ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<7} score={v['score']:<5} sell={v['n_funds_selling']} "
              f"exit={v['n_funds_exited']} buy={v['n_funds_buying']} "
              f"{v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
