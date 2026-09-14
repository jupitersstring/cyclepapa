"""Value-unlock language signal via EDGAR full-text search (EFTS).

Catches securities whose recent SEC filings DISCUSS realising / crystallising /
unlocking latent value for shareholders — strategic reviews, sale processes,
sum-of-the-parts separations, activist-driven capital return. Rather than fetch
and parse thousands of filings, we query EDGAR's own full-text index once per
phrase (efts.sec.gov) — high precision, cheap, dated (so we can weight
freshness). Feeds arch_xr_value_unlock (combined downstream with a CHEAP gate).

Output: value_unlock_signals.csv
  symbol, unlock_hits, unlock_distinct_phrases, unlock_latest_date,
  unlock_days_ago, unlock_forms, unlock_phrases
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

UA = {"User-Agent": "cyclepapa-research value-unlock scan contact@example.com"}
EFTS = "https://efts.sec.gov/LATEST/search-index"

# high-precision value-unlock phrases (quoted = exact phrase match in EFTS)
PHRASES = [
    "exploring strategic alternatives",
    "review of strategic alternatives",
    "strategic alternatives to enhance",
    "unlock shareholder value",
    "unlock value for",
    "maximize shareholder value",
    "enhance shareholder value",
    "sum-of-the-parts",
    "crystallize value",
    "crystallise value",
    "monetize our",
    "sale process",
    "retained a financial advisor",
    "engaged a financial advisor",
    "return of capital to shareholders",
    "separation into two",
    "pursue a separation",
    # committed-STAGE language (a process actually underway = higher conviction)
    "entered into a definitive agreement",
    "definitive agreement to sell",
    "formed a special committee",
    "special committee of the board",
    "as its financial advisor",
    "retained as financial advisor",
    "commenced a process",
    "initiated a review of",
    # activist language
    "nominate directors",
    "director nominees",
    "withhold your vote",
]
# committed-stage / activist phrases (credibility markers)
STAGE_PHRASES = {
    "entered into a definitive agreement", "definitive agreement to sell",
    "formed a special committee", "special committee of the board",
    "as its financial advisor", "retained as financial advisor",
    "commenced a process",
}
ACTIVIST_FORMS = {"SC 13D", "DEFC14A", "PREC14A", "DFAN14A", "DEFN14A"}
# strategic-catalyst forms
FORMS = "8-K,DEF 14A,SC 13D,10-K,10-Q,6-K"
START = "2025-01-01"     # ~last 9-12 months (freshness window; today 2026-09-14)
END = "2026-09-14"
_TICK_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,\s*[A-Z0-9.\-]+)*\)\s*\(CIK")


def _fetch(phrase, frm=0):
    q = urllib.parse.quote(f'"{phrase}"')
    url = f"{EFTS}?q={q}&forms={urllib.parse.quote(FORMS)}&startdt={START}&enddt={END}&from={frm}"
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
            return json.loads(r.read())
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def main():
    per_sym = defaultdict(lambda: {"hits": 0, "phrases": set(), "dates": [], "forms": set()})
    for phrase in PHRASES:
        got = 0
        frm = 0
        total = None
        while True:
            d = _fetch(phrase, frm)
            time.sleep(0.3)
            if not d:
                break
            hits = d.get("hits", {})
            if total is None:
                total = hits.get("total", {}).get("value", 0)
            batch = hits.get("hits", [])
            if not batch:
                break
            for h in batch:
                src = h.get("_source", {})
                names = src.get("display_names") or []
                fdate = src.get("file_date")
                forms = src.get("root_forms") or ([src.get("form")] if src.get("form") else [])
                for nm in names:
                    m = _TICK_RE.search(nm)
                    if not m:
                        continue
                    sym = m.group(1)
                    rec = per_sym[sym]
                    rec["hits"] += 1
                    rec["phrases"].add(phrase)
                    if fdate:
                        rec["dates"].append(fdate)
                    for f in forms:
                        rec["forms"].add(f)
            got += len(batch)
            frm += len(batch)
            if got >= min(total or 0, 300) or got >= 300:
                break
        print(f"  '{phrase}': {total} filings", file=sys.stderr)

    today = datetime(2026, 9, 14)
    rows = []
    for sym, rec in per_sym.items():
        latest = max(rec["dates"]) if rec["dates"] else None
        days_ago = None
        if latest:
            try:
                days_ago = (today - datetime.strptime(latest, "%Y-%m-%d")).days
            except Exception:
                pass
        rows.append({
            "symbol": sym,
            "unlock_hits": rec["hits"],
            "unlock_distinct_phrases": len(rec["phrases"]),
            "unlock_stage_phrases": len(rec["phrases"] & STAGE_PHRASES),  # committed process underway
            "unlock_activist": int(bool(rec["forms"] & ACTIVIST_FORMS)),  # 13D / proxy fight
            "unlock_latest_date": latest,
            "unlock_days_ago": days_ago,
            "unlock_forms": ";".join(sorted(rec["forms"])),
            "unlock_phrases": " | ".join(sorted(rec["phrases"]))[:300],
        })
    import pandas as pd
    out = pd.DataFrame(rows).drop_duplicates("symbol")
    out.to_csv("value_unlock_signals.csv", index=False)
    print(f"symbols with value-unlock language: {len(out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
