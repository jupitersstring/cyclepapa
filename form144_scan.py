"""Form 144 scanner: proposed insider sales, BEFORE they happen.

Form 144 must be filed by affiliates intending to sell restricted or
control stock -- it is the forward-looking complement to Form 4 (which
reports completed trades) and 10b5-1 Item 5 disclosures (plan-level).
Electronic filing has been mandatory since April 2023, and the filings
appear under the ISSUER's CIK in the submissions JSON with a structured
XML primary document (xsl144X01/primary_doc.xml).

Signal interpretation (issuer-level, trailing window):
  - Sudden ACCELERATION in 144 filings = insiders queueing up to sell.
  - Prolonged ABSENCE after historical activity = insiders holding.
  - 144 $ value vs market cap = materiality.

We compute per ticker:
  n_144_180d, n_144_90d, n_144_30d        filing counts by window
  value_180d, value_90d                    aggregate proposed $ value
  accel_ratio = (n_90d/90) / (n_365d/365)  filing-rate acceleration
  signal: -1 * min(20, ...) bearish points when acceleration + size

State: events stored in pipeline.db (source='form144') AND mirrored to
form144_scan.json for the git-tracked artifact. Resumable per ticker.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "form144_scan.json"
EXTRACT_VERSION = "form144-v1"


def fetch_144_index(ticker: str, days: int = 400) -> list[dict]:
    """All Form 144 entries for the issuer from submissions JSON."""
    from edgar import cik_for, _get, SEC_DATA
    cik = cik_for(ticker)
    if not cik:
        return []
    sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    recent = sub.get("filings", {}).get("recent", {})
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for form, acc, doc, dt in zip(recent.get("form", []),
                                  recent.get("accessionNumber", []),
                                  recent.get("primaryDocument", []),
                                  recent.get("filingDate", [])):
        if form != "144" or dt < cutoff:
            continue
        out.append({"cik": cik, "accession": acc,
                    "primary_doc": doc, "filing_date": dt})
    return out


def parse_144_xml(raw: str) -> dict:
    """Pull proposed-sale economics from the Form 144 XML.

    The electronic Form 144 uses the edgar/ownership namespace (same
    family as Forms 3/4/5), e.g.:
      <edgarSubmission xmlns="http://www.sec.gov/edgar/ownership" ...>
        <formData><issuerInfo>...
          <nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
          <relationshipsToIssuer><relationshipToIssuer>Director
        <securitiesInformation>
          <noOfUnitsSold>15500</noOfUnitsSold>
          <aggregateMarketValue>3343863.05</aggregateMarketValue>
          <approxSaleDate>06/03/2026</approxSaleDate>
    """
    out = {}
    try:
        # Strip ALL xmlns declarations so tag matching is namespace-free
        import re as _re
        raw = _re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", raw)
        # Also strip namespace prefixes on tags (com:street1 etc.)
        raw = _re.sub(r"<(/?)\w+:", r"<\1", raw)
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out

    def first_text(*tags):
        for tag in tags:
            el = root.find(f".//{tag}")
            if el is not None and el.text:
                return el.text.strip()
        return None

    shares = first_text("noOfUnitsSold", "amountOfSecuritiesAcquired")
    value = first_text("aggregateMarketValue")
    person = first_text("nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold")
    relationship = first_text("relationshipToIssuer")
    sale_date = first_text("approxSaleDate")
    try:
        out["shares"] = int(float(shares.replace(",", ""))) if shares else None
    except (ValueError, AttributeError):
        out["shares"] = None
    try:
        out["value_usd"] = float(value.replace(",", "")) if value else None
    except (ValueError, AttributeError):
        out["value_usd"] = None
    out["person"] = person
    out["relationship"] = relationship
    out["approx_sale_date"] = sale_date
    return out


def fetch_144_detail(cik: str, accession: str, primary_doc: str) -> dict:
    """Fetch + parse one Form 144. primary_doc is usually
    'xsl144X01/primary_doc.xml' -- the raw XML lives at the path with
    the xsl prefix stripped."""
    from edgar import _get
    cik_n = str(int(cik))
    acc_clean = accession.replace("-", "")
    doc = primary_doc.split("/")[-1]  # strip the XSL-rendering prefix
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{cik_n}/{acc_clean}/{doc}")
    try:
        raw = _get(url).text
    except Exception:
        return {}
    return parse_144_xml(raw)


def days_ago(d: str | None) -> int | None:
    if not d:
        return None
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


def summarize(filings: list[dict]) -> dict:
    n30 = n90 = n180 = n365 = 0
    v90 = v180 = 0.0
    for f in filings:
        da = days_ago(f.get("filing_date"))
        if da is None:
            continue
        v = f.get("value_usd") or 0
        if da <= 30: n30 += 1
        if da <= 90:
            n90 += 1
            v90 += v
        if da <= 180:
            n180 += 1
            v180 += v
        if da <= 365: n365 += 1
    # Acceleration: recent filing rate vs trailing-year baseline.
    # Guard against tiny baselines: require n365 >= 4 before claiming
    # acceleration so two filings in a quiet year don't read as a spike.
    accel = None
    if n365 >= 4:
        rate_90 = n90 / 90
        rate_365 = n365 / 365
        accel = round(rate_90 / rate_365, 2) if rate_365 > 0 else None
    return {"n_30d": n30, "n_90d": n90, "n_180d": n180, "n_365d": n365,
            "value_90d_usd": round(v90), "value_180d_usd": round(v180),
            "accel_ratio": accel}


def score_144(summary: dict, mcap: float | None) -> tuple[float, list[str]]:
    """Bearish points (negative) for acceleration + materiality.
    Capped at -20 so a single signal layer can't dominate the
    composite -- Form 144s are intentions, not completed sales."""
    score = 0.0
    reasons = []
    accel = summary.get("accel_ratio")
    n90 = summary.get("n_90d", 0)
    v90 = summary.get("value_90d_usd", 0)
    if accel and accel >= 2.0 and n90 >= 3:
        score -= 8
        reasons.append(f"144 filing rate {accel:.1f}x trailing-year pace")
    if mcap and mcap > 0 and v90:
        pct = v90 / mcap * 100
        if pct >= 1.0:
            score -= 12
            reasons.append(f"144 proposed sales = {pct:.2f}% of mcap in 90d")
        elif pct >= 0.25:
            score -= 6
            reasons.append(f"144 proposed sales = {pct:.2f}% of mcap in 90d")
    elif v90 >= 25_000_000:
        score -= 8
        reasons.append(f"${v90/1e6:.0f}M proposed sales in 90d")
    return max(-20.0, score), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-file", default=str(ROOT / "full_universe.txt"))
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--detail-limit", type=int, default=25,
                    help="Max 144 XMLs fetched per ticker (newest first); "
                         "counts beyond this still tallied from the index.")
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--json", default=str(OUT_JSON))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in
               Path(args.tickers_file).read_text().splitlines() if t.strip()]

    out_path = Path(args.json)
    out: dict = json.loads(out_path.read_text()) if out_path.exists() else {}

    import state
    conn = state.connect()

    mcap_map = {}
    yq = ROOT / "yfinance_quick.json"
    if yq.exists():
        for tk, v in json.loads(yq.read_text()).items():
            if v.get("mcap"):
                mcap_map[tk] = v["mcap"]

    n_done = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in out and out[tk].get("_complete"):
            continue
        try:
            index = fetch_144_index(tk)
        except Exception as e:
            print(f"  {tk}: index fail: {e}", file=sys.stderr)
            out[tk] = {"_complete": True, "_error": str(e)[:120]}
            continue
        time.sleep(args.sleep)

        filings = []
        for j, f in enumerate(index):
            detail = {}
            if j < args.detail_limit:
                detail = fetch_144_detail(f["cik"], f["accession"],
                                          f["primary_doc"])
                time.sleep(args.sleep)
            filings.append({**f, **detail})

        summary = summarize(filings)
        score, reasons = score_144(summary, mcap_map.get(tk))
        rec = {
            "ticker": tk,
            "n_filings_indexed": len(index),
            "summary": summary,
            "score": score,
            "reasons": reasons,
            "filings": filings[:50],
            "_complete": True,
            "_version": EXTRACT_VERSION,
        }
        out[tk] = rec

        # Mirror events into SQLite
        with conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM events WHERE ticker=? AND "
                "extract_version=? AND source='form144'",
                (tk, EXTRACT_VERSION)).fetchone()[0]
            if not existing:
                evs = [{
                    "accession": f.get("accession"),
                    "filing_date": f.get("filing_date"),
                    "action": "PROPOSED_SALE",
                    "plan_type": "sell",
                    "neo": f.get("person"),
                    "role": f.get("relationship"),
                    "shares": f.get("shares"),
                    "value_usd": f.get("value_usd"),
                } for f in filings]
                state.insert_events(conn, tk, evs, EXTRACT_VERSION,
                                    source="form144")

        n_done += 1
        if n_done % 20 == 0:
            tmp = out_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2, default=str))
            tmp.replace(out_path)
            print(f"  [{i}/{len(tickers)}] processed={n_done}", flush=True)

    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str))
    tmp.replace(out_path)
    conn.close()

    nz = [(tk, v) for tk, v in out.items()
          if v.get("score") and v["score"] < 0]
    nz.sort(key=lambda kv: kv[1]["score"])
    print(f"\nDone. {n_done} newly processed; "
          f"{len(nz)} tickers with bearish 144 signal\n")
    print(f"{'TKR':<8}{'N90':>5}{'V90($M)':>10}{'ACCEL':>7}{'SCR':>6}  REASONS")
    print("-" * 100)
    for tk, v in nz[:30]:
        s = v["summary"]
        print(f"{tk:<8}{s['n_90d']:>5}{s['value_90d_usd']/1e6:>10.1f}"
              f"{s['accel_ratio'] if s['accel_ratio'] else 0:>7.1f}"
              f"{v['score']:>6.0f}  {' | '.join(v['reasons'])[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
