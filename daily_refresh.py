"""Daily incremental refresh orchestrator.

Designed for a cron line like:
  30 22 * * 1-5  cd /home/user/cyclepapa && python3 daily_refresh.py >> logs/daily.log 2>&1

(22:30 UTC = 6:30pm ET, after the EDGAR filing day closes.)

What it does, per ticker in full_universe.txt:
  1. INCREMENTAL FETCH -- asks the submissions JSON only for filings
     newer than the last filing_date recorded in pipeline.db (state.py).
     A quiet ticker costs exactly one submissions request and zero
     document fetches.
  2. For each NEW 10-Q/10-K/20-F/6-K: fetch+cache HTML, run
     detect_actions, append events to pipeline.db AND the JSON artifact.
  3. For each NEW Form 144: parse XML, append to pipeline.db.
  4. Re-score any ticker whose event set changed.
  5. Emit a DIFF REPORT (what changed today) to logs/diff_YYYY-MM-DD.md
     -- the "what changed this week" surface.

Idempotent: running twice in a day is a no-op for already-seen
accessions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import state
from cancel_10b5_1 import (
    detect_actions, dedupe_cross_quarter, score_events,
    load_cached, fetch_and_cache_filing,
)
from form144_scan import fetch_144_detail, parse_144_xml  # noqa: F401

ROOT = Path("/home/user/cyclepapa")
EXTRACT_VERSION = "v3-dedup-foreign-aware"
SCORE_VERSION = "v3.3"
FORMS_10B5 = ("10-Q", "10-K", "20-F", "6-K")


def new_filings_for(ticker: str, conn, days: int = 30) -> list:
    """Submissions-JSON entries newer than what pipeline.db has seen.
    `days` caps the lookback so a brand-new ticker doesn't trigger a
    full historical crawl from the daily path (use scan_10k_extend for
    backfills)."""
    from edgar import cik_for, _get, SEC_DATA
    from datetime import timedelta
    cik = cik_for(ticker)
    if not cik:
        return []
    sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    recent = sub.get("filings", {}).get("recent", {})
    known = state.known_accessions(conn, ticker)
    floor = (datetime.now(timezone.utc)
             - timedelta(days=days)).strftime("%Y-%m-%d")
    last = state.last_scanned_date(conn, ticker) or floor
    cutoff = max(floor, last)
    out = []
    for form, acc, doc, dt in zip(recent.get("form", []),
                                  recent.get("accessionNumber", []),
                                  recent.get("primaryDocument", []),
                                  recent.get("filingDate", [])):
        if form not in FORMS_10B5 and form != "144":
            continue
        if dt < cutoff or acc in known:
            continue
        out.append({"cik": cik, "form": form, "accession": acc,
                    "primary_doc": doc, "filing_date": dt})
    return out


def refresh_ticker(ticker: str, conn, json_state: dict,
                   sleep: float) -> dict | None:
    """Process new filings; return a diff record if anything changed."""
    try:
        fresh = new_filings_for(ticker, conn)
    except Exception as e:
        return {"ticker": ticker, "error": str(e)[:120]}
    if not fresh:
        return None

    new_events = []
    for fl in fresh:
        if fl["form"] == "144":
            detail = fetch_144_detail(fl["cik"], fl["accession"],
                                      fl["primary_doc"])
            time.sleep(sleep)
            ev = {
                "accession": fl["accession"],
                "filing_date": fl["filing_date"],
                "action": "PROPOSED_SALE", "plan_type": "sell",
                "neo": detail.get("person"),
                "role": detail.get("relationship"),
                "shares": detail.get("shares"),
                "value_usd": detail.get("value_usd"),
            }
            with conn:
                state.insert_events(conn, ticker, [ev], "form144-v1",
                                    source="form144")
                state.record_filing(conn, ticker, fl["accession"],
                                    fl["form"], fl["filing_date"])
            new_events.append({**ev, "source": "form144"})
        else:
            text = load_cached(fl["accession"])
            if not text:
                text = fetch_and_cache_filing(fl["cik"], fl["accession"],
                                              fl["primary_doc"])
                time.sleep(sleep)
            with conn:
                state.record_filing(conn, ticker, fl["accession"],
                                    fl["form"], fl["filing_date"])
            if not text:
                continue
            evs = detect_actions(text)
            for e in evs:
                e["accession"] = fl["accession"]
                e["filing_date"] = fl["filing_date"]
            if evs:
                with conn:
                    state.insert_events(conn, ticker, evs, EXTRACT_VERSION)
                new_events.extend(
                    {**e, "source": "10b5_1"} for e in evs)

    if not new_events:
        # Filings seen but no events -- still update JSON quarters list
        rec = json_state.get(ticker)
        if rec is not None:
            for fl in fresh:
                if fl["form"] != "144":
                    rec.setdefault("quarters_scanned", []).append({
                        "accession": fl["accession"],
                        "filing_date": fl["filing_date"],
                    })
        return {"ticker": ticker,
                "new_filings": [f["accession"] for f in fresh],
                "new_events": []}

    # Re-score from the DB event log (10b5_1 source only)
    db_events = state.events_for(conn, ticker, EXTRACT_VERSION)
    deduped = dedupe_cross_quarter(db_events)
    sc, reasons, counts = score_events(deduped)
    with conn:
        state.upsert_score(conn, ticker, SCORE_VERSION, sc, counts,
                           reasons, True)

    # Mirror to the JSON artifact
    rec = json_state.setdefault(ticker, {
        "ticker": ticker, "quarters_scanned": [], "events": [],
        "_complete": True,
    })
    old_score = rec.get("score", 0)
    for fl in fresh:
        if fl["form"] != "144":
            rec.setdefault("quarters_scanned", []).append({
                "accession": fl["accession"],
                "filing_date": fl["filing_date"],
            })
    rec["events"] = deduped
    rec["score"] = sc
    rec["reasons"] = reasons
    rec["counts"] = counts
    rec["data_available"] = True

    return {
        "ticker": ticker,
        "new_filings": [f["accession"] for f in fresh],
        "new_events": [
            {k: e.get(k) for k in ("source", "action", "plan_type",
                                    "neo", "role", "shares", "value_usd",
                                    "filing_date")}
            for e in new_events],
        "old_score": old_score,
        "new_score": sc,
    }


def write_diff_report(diffs: list[dict], out_dir: Path) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = out_dir / f"diff_{today}.md"
    lines = [f"# Daily diff — {today}", ""]
    changed = [d for d in diffs if d and d.get("new_events")]
    quiet = [d for d in diffs if d and not d.get("new_events")
             and not d.get("error")]
    errors = [d for d in diffs if d and d.get("error")]
    lines.append(f"Tickers with new events: {len(changed)}; "
                 f"new filings only: {len(quiet)}; errors: {len(errors)}")
    lines.append("")
    for d in sorted(changed,
                    key=lambda x: -abs((x.get("new_score") or 0)
                                       - (x.get("old_score") or 0))):
        delta = (d.get("new_score") or 0) - (d.get("old_score") or 0)
        lines.append(f"## {d['ticker']}  score {d.get('old_score', 0):.0f} "
                     f"→ {d.get('new_score', 0):.0f} ({delta:+.0f})")
        for e in d["new_events"]:
            val = f" ${e['value_usd']/1e6:.1f}M" if e.get("value_usd") else ""
            sh = f" {e['shares']:,}sh" if e.get("shares") else ""
            lines.append(f"- [{e['source']}] {e.get('action')} "
                         f"{e.get('plan_type') or ''} — "
                         f"{e.get('neo') or '?'} "
                         f"({e.get('role') or '?'}){sh}{val} "
                         f"filed {e.get('filing_date')}")
        lines.append("")
    p.write_text("\n".join(lines))
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-file", default=str(ROOT / "full_universe.txt"))
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--json", default=str(ROOT / "cancel_10b5_1.json"))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in
               Path(args.tickers_file).read_text().splitlines() if t.strip()]
    conn = state.connect()
    json_path = Path(args.json)
    json_state = json.loads(json_path.read_text()) if json_path.exists() else {}

    diffs = []
    n_changed = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        d = refresh_ticker(tk, conn, json_state, args.sleep)
        if d:
            diffs.append(d)
            if d.get("new_events"):
                n_changed += 1
        time.sleep(args.sleep)
        if i % 100 == 0:
            print(f"  [{i}/{len(tickers)}] changed={n_changed}", flush=True)
            tmp = json_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(json_state, indent=2, default=str))
            tmp.replace(json_path)

    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(json_state, indent=2, default=str))
    tmp.replace(json_path)
    conn.close()

    report = write_diff_report(diffs, ROOT / "logs")
    print(f"\nDone. {n_changed} tickers changed. Diff report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
