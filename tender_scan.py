"""Tender-offer scanner: SC TO-I / SC TO-T / SC 13E-3 coverage.

THE GAP THIS CLOSES: Expensify (EXFY) ran a live issuer self-tender
(SC TO-I filed 2026-05-13, amended through 2026-06-12) and no layer
saw it. Buyback detection keyed on authorization language in 8-K/proxy
text plus realized share-count change -- but tender offers are filed
under their own dedicated form family that nothing requested:

  SC TO-I    issuer self-tender (fixed-price or Dutch auction).
             The most aggressive, time-boxed repurchase structure;
             the strongest-signal bucket in Peyer-Vermaelen.
  SC TO-I/A  amendments (extensions, price bumps -- still-live signal)
  SC 13E-3   going-private transaction statement
  SC TO-T    third-party tender (M&A in flight; informational)
  SC 14D9    target board's response to a tender

Scoring (issuer-centric, freshness-weighted like step_change):
  SC TO-I  <=30d +20, <=90d +14, <=180d +8; size kicker when the
           parsed tender cap >= 5% / >= 10% of mcap (+4 / +8)
  SC 13E-3 <=90d +15, <=180d +10
  SC TO-T  <=90d +12 (target of a live bid)
  Premium parse: Dutch range or fixed price vs current price noted.

Per-ticker cost: one submissions-JSON request (reuses the cached doc
fetch machinery only when a TO-I primary doc needs parsing).
Resumable; mirrors filings into pipeline.db.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "tender_scan.json"
EXTRACT_VERSION = "tender-v1"

TENDER_FORMS = {"SC TO-I", "SC TO-I/A", "SC 13E3", "SC 13E-3",
                "SC 13E3/A", "SC 13E-3/A", "SC TO-T", "SC TO-T/A",
                "SC 14D9", "SC 14D9/A"}

# Tender economics out of the TO-I primary doc
DOLLAR_CAP = re.compile(
    r"(?:purchase|repurchase|buy)\s+(?:for\s+cash\s+)?up\s+to\s+"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion)?", re.I)
SHARE_CAP = re.compile(
    r"up\s+to\s+([\d,]+)\s+shares", re.I)
DUTCH_RANGE = re.compile(
    r"not\s+(?:less|lower)\s+than\s+\$\s*([\d.]+)\s+(?:per\s+share\s+)?"
    r"(?:and|nor|or)\s+not\s+(?:greater|more|higher)\s+than\s+\$\s*([\d.]+)",
    re.I)
FIXED_PRICE = re.compile(
    r"(?:purchase\s+price\s+of|at\s+a\s+price\s+of)\s+\$\s*([\d.]+)\s+per\s+share",
    re.I)


def days_ago(d: str | None) -> int | None:
    if not d:
        return None
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


def fetch_tender_filings(ticker: str, days: int = 400) -> list[dict]:
    from edgar import cik_for, _get, SEC_DATA
    cik = cik_for(ticker)
    if not cik:
        return []
    sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    recent = sub.get("filings", {}).get("recent", {})
    out = []
    for form, acc, doc, dt in zip(recent.get("form", []),
                                  recent.get("accessionNumber", []),
                                  recent.get("primaryDocument", []),
                                  recent.get("filingDate", [])):
        if form not in TENDER_FORMS:
            continue
        da = days_ago(dt)
        if da is None or da > days:
            continue
        out.append({"cik": cik, "form": form, "accession": acc,
                    "primary_doc": doc, "filing_date": dt,
                    "days_ago": da})
    return out


def parse_tender_doc(cik: str, accession: str, primary_doc: str) -> dict:
    """Pull size + price terms from the TO-I/13E-3 primary document."""
    from edgar import _get
    cik_n = str(int(cik))
    acc_clean = accession.replace("-", "")
    doc = primary_doc.split("/")[-1]
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{cik_n}/{acc_clean}/{doc}")
    try:
        raw = _get(url).text
    except Exception:
        return {}
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
    out = {}
    m = DOLLAR_CAP.search(plain)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            unit = (m.group(2) or "").lower()
            if unit == "billion":
                v *= 1e9
            elif unit == "million":
                v *= 1e6
            if v >= 1e6:
                out["cap_usd"] = v
        except ValueError:
            pass
    m = SHARE_CAP.search(plain)
    if m:
        try:
            out["cap_shares"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    m = DUTCH_RANGE.search(plain)
    if m:
        try:
            out["dutch_low"] = float(m.group(1))
            out["dutch_high"] = float(m.group(2))
        except ValueError:
            pass
    else:
        m = FIXED_PRICE.search(plain)
        if m:
            try:
                out["fixed_price"] = float(m.group(1))
            except ValueError:
                pass
    return out


def score_tender(filings: list[dict], terms: dict,
                 mcap: float | None, price: float | None
                 ) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    # Most-recent ORIGINAL per family; amendments refresh liveness
    selfs = [f for f in filings if f["form"].startswith("SC TO-I")]
    e3s = [f for f in filings if "13E" in f["form"]]
    tots = [f for f in filings if f["form"].startswith("SC TO-T")
            or f["form"].startswith("SC 14D9")]

    if selfs:
        d = min(f["days_ago"] for f in selfs)   # latest activity
        base = 20 if d <= 30 else (14 if d <= 90 else 8 if d <= 180 else 0)
        if base:
            score += base
            reasons.append(f"issuer SELF-TENDER live, latest filing {d}d ago")
            cap = terms.get("cap_usd")
            if cap and mcap and mcap > 0:
                pct = cap / mcap * 100
                if pct >= 10:
                    score += 8
                    reasons.append(f"tender cap ${cap/1e6:.0f}M = {pct:.0f}% of mcap")
                elif pct >= 5:
                    score += 4
                    reasons.append(f"tender cap ${cap/1e6:.0f}M = {pct:.0f}% of mcap")
            lo, hi = terms.get("dutch_low"), terms.get("dutch_high")
            fp = terms.get("fixed_price")
            if price and price > 0:
                if hi:
                    prem = (hi / price - 1) * 100
                    reasons.append(f"Dutch ${lo}-${hi} (top {prem:+.0f}% vs px)")
                elif fp:
                    prem = (fp / price - 1) * 100
                    reasons.append(f"fixed ${fp} ({prem:+.0f}% vs px)")
    if e3s:
        d = min(f["days_ago"] for f in e3s)
        base = 15 if d <= 90 else (10 if d <= 180 else 0)
        if base:
            score += base
            reasons.append(f"SC 13E-3 going-private, {d}d ago")
    if tots and not selfs:
        d = min(f["days_ago"] for f in tots)
        if d <= 90:
            score += 12
            reasons.append(f"third-party tender / 14D-9, {d}d ago")
    return min(35.0, score), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-file", default=str(ROOT / "full_universe.txt"))
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--json", default=str(OUT_JSON))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in
               Path(args.tickers_file).read_text().splitlines() if t.strip()]
    out_path = Path(args.json)
    out: dict = json.loads(out_path.read_text()) if out_path.exists() else {}

    yq_p = ROOT / "yfinance_quick.json"
    yq = json.loads(yq_p.read_text()) if yq_p.exists() else {}

    import state
    conn = state.connect()

    n_done = n_hits = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in out and out[tk].get("_complete"):
            if out[tk].get("score"):
                n_hits += 1
            continue
        try:
            filings = fetch_tender_filings(tk)
        except Exception as e:
            # BUGFIX (silent-drop audit): transient fetch failure must
            # not be marked _complete or the resume guard skips it
            # forever. Omit _complete -> retried next run.
            out[tk] = {"_error": str(e)[:120]}
            continue
        time.sleep(args.sleep)

        terms = {}
        if filings:
            orig = [f for f in filings if f["form"] == "SC TO-I"]
            target = orig[0] if orig else filings[0]
            terms = parse_tender_doc(target["cik"], target["accession"],
                                     target["primary_doc"])
            time.sleep(args.sleep)

        q = yq.get(tk) or {}
        sc, reasons = score_tender(filings, terms,
                                   q.get("mcap"), q.get("price"))
        # BUGFIX (silent-drop audit): has_13e3 was read by 9 downstream
        # consumers but never produced here, so the going-private signal
        # was silently absent everywhere. Derive it from the filing set.
        has_13e3 = any("13E" in (f.get("form") or "") for f in filings)
        out[tk] = {
            "ticker": tk, "filings": filings, "terms": terms,
            "score": sc, "reasons": reasons, "has_13e3": has_13e3,
            "_complete": True, "_version": EXTRACT_VERSION,
        }
        if filings:
            n_hits += 1
            with conn:
                for f in filings:
                    state.record_filing(conn, tk, f["accession"],
                                        f["form"], f["filing_date"])
            print(f"  HIT {tk}: {len(filings)} tender filings, "
                  f"score {sc:.0f} -- {' | '.join(reasons)[:90]}",
                  flush=True)
        n_done += 1
        if n_done % 50 == 0:
            tmp = out_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2, default=str))
            tmp.replace(out_path)
            print(f"  [{i}/{len(tickers)}] processed={n_done} hits={n_hits}",
                  flush=True)

    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str))
    tmp.replace(out_path)
    conn.close()

    live = sorted([(tk, v) for tk, v in out.items() if v.get("score")],
                  key=lambda kv: -kv[1]["score"])
    print(f"\nDone. {n_done} processed; {len(live)} tickers with "
          f"tender activity\n")
    print(f"{'TKR':<8}{'SCR':>5}  REASONS")
    print("-" * 110)
    for tk, v in live[:30]:
        print(f"{tk:<8}{v['score']:>5.0f}  {' | '.join(v['reasons'])[:95]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
