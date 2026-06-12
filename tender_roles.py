"""Disambiguate tender-offer roles: target vs bidder.

SC TO-T filings appear in the SUBMISSIONS feed of BOTH the bidder and
the target, so tender_scan.py's raw hit list conflates "company is
being acquired via tender" (deal-arb signal, the stock pins to the
offer) with "company is acquiring someone" (capital-deployment
signal). SC 14D9 is filed by the target's board, but it also shows up
under the bidder when jointly filed.

The TO-T / 14D-9 cover page always carries:

    "Name of Subject Company: <TARGET NAME>"
    (and usually) "(Name of Filing Persons -- Offeror)" etc.

So: fetch the primary doc once per tender-active ticker, extract the
subject-company name, fuzzy-match it against the scanned ticker's own
company name (universe_meta.json). Match -> role=TARGET; no match ->
role=BIDDER.

Re-scores tender_scan.json in place:
  TARGET of live tender (<=90d):   keep/boost +12 -> +15
  BIDDER (live):                   +4 informational (deal in flight)
  SELF-TENDER (SC TO-I):           untouched (already correct)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")

SUBJECT_RE = re.compile(
    r"Name\s+of\s+Subject\s+Company[^A-Za-z0-9]{0,40}"
    r"([A-Z][A-Za-z0-9 .,&'\-]{2,80}?)\s*(?:\(|Name|Commission|\d|$)",
    re.I)


def norm(name: str) -> set[str]:
    """Significant tokens of a company name for fuzzy overlap."""
    stop = {"inc", "corp", "corporation", "company", "co", "ltd", "plc",
            "holdings", "holding", "group", "the", "of", "and", "&",
            "technologies", "technology", "pharmaceuticals", "pharma",
            "therapeutics", "international", "incorporated", "sa", "nv"}
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {t for t in toks if t not in stop and len(t) > 1}


def subject_company(cik: str, accession: str, primary_doc: str) -> str | None:
    from edgar import _get
    cik_n = str(int(cik))
    acc_clean = accession.replace("-", "")
    doc = primary_doc.split("/")[-1]
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{cik_n}/{acc_clean}/{doc}")
    try:
        raw = _get(url).text
    except Exception:
        return None
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))[:30000]
    m = SUBJECT_RE.search(plain)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "tender_scan.json"))
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text())
    meta = json.loads((ROOT / "universe_meta.json").read_text()) \
        if (ROOT / "universe_meta.json").exists() else {}

    n_target = n_bidder = n_self = 0
    for tk, v in data.items():
        filings = v.get("filings") or []
        if not filings or v.get("_role_resolved"):
            continue
        tots = [f for f in filings if f["form"].startswith("SC TO-T")
                or f["form"].startswith("SC 14D9")]
        selfs = [f for f in filings if f["form"].startswith("SC TO-I")]
        if selfs:
            v["role"] = "SELF_TENDER"
            v["_role_resolved"] = True
            n_self += 1
            continue
        if not tots:
            v["_role_resolved"] = True
            continue
        own_name = (meta.get(tk) or {}).get("name") or ""
        own_toks = norm(own_name)

        # PRECEDENCE 1: an SC 14D9 in the company's own feed is filed
        # by the TARGET's board -- definitive regardless of doc parse.
        has_14d9 = any(f["form"].startswith("SC 14D9") for f in tots)

        subj = None
        is_target = None
        if has_14d9:
            is_target = True
        else:
            # PRECEDENCE 2: parse "Name of Subject Company" from the
            # freshest TO-T and fuzzy-match against own name.
            f = sorted(tots, key=lambda x: x["filing_date"],
                       reverse=True)[0]
            subj = subject_company(f["cik"], f["accession"],
                                   f["primary_doc"])
            time.sleep(args.sleep)
            v["subject_company"] = subj
            if subj:
                subj_toks = norm(subj)
                is_target = bool(own_toks and subj_toks and
                                 len(own_toks & subj_toks) >= 1)
            # PRECEDENCE 3: parse failed -> UNKNOWN; keep the original
            # generic +12 rather than guessing a side.

        live = any(f2["days_ago"] <= 90 for f2 in tots)
        d_min = min(f2["days_ago"] for f2 in tots)
        old = v.get("score") or 0
        if is_target is True:
            v["role"] = "TARGET"
            if live:
                v["score"] = max(old, 15.0)
                v["reasons"] = [r for r in (v.get("reasons") or [])
                                if "third-party" not in r]
                v["reasons"].append(
                    f"TARGET of live tender"
                    f"{' (14D-9 filed)' if has_14d9 else ''}, {d_min}d ago")
                n_target += 1
        elif is_target is False:
            v["role"] = "BIDDER"
            if live:
                v["score"] = 4.0
                v["reasons"] = [
                    f"BIDDER in live tender for {subj or '?'} "
                    f"({d_min}d ago)"]
                n_bidder += 1
        else:
            v["role"] = "UNKNOWN"
        v["_role_resolved"] = True

    tmp = Path(args.json).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(args.json)
    print(f"Resolved: {n_self} self-tenders, {n_target} targets, "
          f"{n_bidder} bidders")
    for tk, v in sorted(data.items(),
                        key=lambda kv: -(kv[1].get("score") or 0)):
        if v.get("score"):
            print(f"  {tk:<6}{v['score']:>5.0f}  {v.get('role','?'):<12}"
                  f"{' | '.join(v.get('reasons') or [])[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
