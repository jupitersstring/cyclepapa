"""SC 13D / 13D-A sweep across the SEC universe.

SC 13D = formal disclosure when a person/entity becomes the beneficial
owner of >5% of a security AND has activist intent. The single
cleanest primary-source signal of fresh activist arrival.

Distinguished from:
  SC 13G   passive 5%+ owner (mutual funds, index trackers)
  SC 13D/A amendment to existing 13D position (size change)

This sweep:
  1. Pulls every SC 13D filing across a date window via EDGAR FTS
  2. Per filing, extracts issuer (target) + filer (activist) info
  3. Aggregates by issuer ticker: how many distinct activists, dates,
     amendments
  4. Output: sc13d_recent.json keyed by ticker
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from edgar import _get, _ticker_index, SEC_WWW
from recent import EFTS
from universe_filter import is_excluded


def pull_13d_index(start_date: str, end_date: str,
                   limit: int = 6000) -> list[dict]:
    """Walk EDGAR FTS for SC 13D / SC 13D-A in window.

    EDGAR's full-text search uses 'SCHEDULE 13D' as the form filter,
    not 'SC 13D'. Display_names embeds the ticker as '(TICK)' suffix.
    Subject company is typically display_names[0]; filer is [1].
    """
    import urllib.parse
    out: list[dict] = []
    cik_map = {f"{int(v['cik_str']):010d}": v["ticker"]
               for v in _ticker_index().values()}

    for form in ("SCHEDULE 13D", "SCHEDULE 13D/A"):
        qf = urllib.parse.quote(form)
        offset = 0
        while len(out) < limit and offset < 9900:
            url = (f"{EFTS}?forms={qf}"
                   f"&dateRange=custom&startdt={start_date}&enddt={end_date}"
                   f"&from={offset}")
            try:
                data = _get(url).json()
            except Exception:
                break
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                src = h.get("_source") or {}
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                ciks = src.get("ciks") or []
                target_cik = f"{int(ciks[0]):010d}" if ciks else None
                display_names = src.get("display_names") or []
                # Extract ticker from "(TICK)" in subject-company display name
                target_ticker = None
                if display_names:
                    m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", display_names[0])
                    if m:
                        target_ticker = m.group(1)
                if not target_ticker and target_cik:
                    target_ticker = cik_map.get(target_cik)
                # Filer is typically display_names[1]
                filer_name = display_names[1] if len(display_names) > 1 else ""
                # Strip "(CIK ...)" from filer name
                filer_clean = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", filer_name).strip()
                display = " ; ".join(display_names)
                file_date = src.get("file_date", "")
                out.append({
                    "accession": id_parts[0],
                    "primary_doc": id_parts[1],
                    "target_cik": target_cik,
                    "target_ticker": target_ticker,
                    "filer_name": filer_clean,
                    "display_names": display,
                    "form": form,
                    "file_date": file_date,
                })
                if len(out) >= limit:
                    return out
            offset += 100
    return out


# Activist filer names (known firms) -- for tagging
KNOWN_ACTIVISTS = re.compile(
    r"\b("
    r"elliott|starboard|icahn|pershing\s+square|trian|jana|ancora|"
    r"engaged\s+capital|engine\s+capital|politan|voce\s+capital|"
    r"donerail|sachem\s+head|land\s*&\s*buildings|blackwells|sandell|"
    r"standard\s+general|legion\s+partners|coliseum\s+capital|saba\s+capital|"
    r"indaba|browning\s+west|glenview|greenlight|marathon\s+partners|"
    r"engine\s+no\.?\s*1|inclusive\s+capital|valueact|coast\s+capital|"
    r"lone\s+star\s+value|riposte|crescendo|eminence\s+capital|"
    r"caligan|cohanzick|jcp\s+investment|nine\s+ten|viex|hestia|corre|"
    r"carronade|legato|atalaya|western\s+investment|discovery\s+capital|"
    r"bow\s+street|driver\s+management|pwp\s+active|third\s+point|"
    r"highfields|nelson\s+peltz|mantle\s+ridge|bluetriton|hg\s+vora|"
    r"tang\s+capital|voss\s+capital|roumell|newtyn|hudson\s+bay|"
    r"anson\s+funds|oaktree|owl\s+creek|frontfour|"
    r"land\s*&\s*buildings|crystal\s+amber|sherborne|saporta|petrus|"
    r"bluebell|asset\s+value\s+investors|kelso\s+place|polygon|"
    r"algebris|cevian|sachem"
    r")\b",
    re.I,
)


def tag_activist(display_names: str) -> str | None:
    """Extract activist firm name from display_names if known."""
    m = KNOWN_ACTIVISTS.search(display_names or "")
    if m:
        return m.group(0)
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=180,
                   help="Days back to sweep SC 13D filings.")
    p.add_argument("--limit", type=int, default=8000)
    p.add_argument("--out", default="sc13d_recent.json")
    args = p.parse_args()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Pulling SC 13D / SC 13D/A {start} .. {end} (limit {args.limit})",
          file=sys.stderr)

    idx = pull_13d_index(start, end, limit=args.limit)
    print(f"SC 13D / SC 13D/A filings: {len(idx)}", file=sys.stderr)

    # Aggregate by target ticker
    by_ticker: dict = {}
    for f in idx:
        tk = (f.get("target_ticker") or "").upper()
        if not tk:
            continue
        bad, _ = is_excluded(tk)
        if bad:
            continue
        rec = by_ticker.setdefault(tk, {
            "ticker": tk,
            "filings": [],
            "activist_tags": [],
            "latest_13d_date": None,
            "n_13d": 0,
            "n_13d_a": 0,
        })
        activist = tag_activist(f.get("display_names") or "") or tag_activist(f.get("filer_name") or "")
        rec["filings"].append({
            "form": f["form"],
            "accession": f["accession"],
            "date": f["file_date"],
            "display_names": f.get("display_names"),
            "filer_name": f.get("filer_name"),
            "activist_tag": activist,
        })
        if activist and activist.lower() not in [a.lower() for a in rec["activist_tags"]]:
            rec["activist_tags"].append(activist)
        # Track all distinct filer names for richer signal
        rec.setdefault("filer_names", [])
        if f.get("filer_name") and f["filer_name"] not in rec["filer_names"]:
            rec["filer_names"].append(f["filer_name"])
        if "/A" not in f["form"]:
            rec["n_13d"] += 1
        else:
            rec["n_13d_a"] += 1
        # Latest filing date
        if not rec["latest_13d_date"] or f["file_date"] > rec["latest_13d_date"]:
            rec["latest_13d_date"] = f["file_date"]

    Path(args.out).write_text(json.dumps(by_ticker, indent=2, default=str))
    print(f"\nWrote {args.out} ({len(by_ticker)} issuers)",
          file=sys.stderr)

    # Rank by recency + activist tag presence
    ranked = sorted(by_ticker.values(),
                    key=lambda r: (r.get("latest_13d_date") or "",
                                    len(r.get("activist_tags") or [])),
                    reverse=True)

    print(f"\n=== TOP 40 BY RECENT 13D FILINGS ===")
    print(f"{'#':<3}{'TKR':<10}{'DATE':<11}{'13D':>4}{'AMD':>4}  ACTIVIST TAGS / FILER")
    print("-" * 130)
    for i, r in enumerate(ranked[:40], 1):
        tags = ", ".join((r.get("activist_tags") or [])[:3])
        first_filing = r["filings"][0] if r["filings"] else {}
        display = (first_filing.get("display_names") or "")[:60]
        print(f"{i:<3}{r['ticker']:<10}{r.get('latest_13d_date') or '?':<11}"
              f"{r.get('n_13d', 0):>4}{r.get('n_13d_a', 0):>4}  "
              f"{tags or display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
