"""Sub-13D activist public-letter feed.

Captures the PRE-13D phase of activist campaigns: when a fund
publishes a public letter calling for strategic alternatives /
board changes / sum-of-parts before crossing the 5% 13D threshold,
or as an addition to an existing position.

Two complementary sources, both EDGAR-native (no external news API):

  1. 8-K Item 7.01 / 8.01 disclosures where a target company
     INCLUDES the activist's letter as an exhibit. Filter to 8-Ks
     mentioning known activist firm names in the body.

  2. SC 13D filings where the filer name matches a known activist
     and the filing is very recent (last 60 days). High-signal-
     intensity tail.

The output flags names where activist pressure is being publicly
applied and the market may not yet have noticed.

Output: activist_letter_feed.json
  {ticker: {date, accession, source, filer, score, reasons}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "activist_letter_feed.json"


# Curated activist list -- known to file public sale-pressure letters
KNOWN_ACTIVISTS = [
    "elliott investment", "elliott management",
    "starboard value", "starboard partners",
    "trian fund", "trian partners",
    "engaged capital",
    "mantle ridge",
    "ancora advisors", "ancora holdings",
    "jana partners",
    "valueact capital",
    "third point",
    "pershing square",
    "icahn enterprises", "carl icahn",
    "donerail group",
    "engine capital",
    "land & buildings", "land and buildings",
    "politan capital",
    "voce capital",
    "blackwells capital",
    "carlson capital",
    "sachem head",
    "discovery capital",
    "ides capital",
    "scopia capital",
    "h partners",
    "shareholder vista",
    "saba capital",
    "indaba capital",
    "browning west",
    "white pine capital",
    "irenic capital",
    "kanen wealth",
    "voss capital",
]

ACTIVIST_RX = re.compile(
    "|".join(re.escape(a) for a in KNOWN_ACTIVISTS),
    re.I,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    try:
        from recent import EFTS, _get, requests_quote, _cik_to_ticker_map
    except ImportError as e:
        print(f"need recent.py: {e}", file=sys.stderr)
        return 1

    try:
        from recent_13d_sweep import pull_13d_index, KNOWN_ACTIVISTS as KA_RX
    except ImportError:
        pull_13d_index = None
        KA_RX = None

    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    cik_to_ticker = _cik_to_ticker_map()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=args.days)).strftime("%Y-%m-%d")

    out = {}

    # 1. 8-K Item 7.01 / 8.01 with activist firm name in body
    print(f"[1/2] Scanning 8-K Item 7.01/8.01 {start}..{end}",
          file=sys.stderr, flush=True)

    # METHODOLOGY FIX (audit finding A9): the old queries[:30] cap
    # silently dropped the 8-K query pair for all but the first ~15
    # activists. To bound runtime WITHOUT losing coverage, we now run
    # ONE combined query per activist (the two phrase variants OR'd)
    # and cap pagination per query instead of truncating the firm list.
    queries = []
    for a in KNOWN_ACTIVISTS:
        queries.append(
            f'"{a}" ("strategic alternatives" OR "public letter")')

    seen = set()
    for q in queries:
        offset = 0
        while len(seen) < args.limit and offset < 200:
            url = (f"{EFTS}?forms=8-K&dateRange=custom"
                   f"&startdt={start}&enddt={end}"
                   f"&from={offset}&q={requests_quote(q)}")
            try:
                data = _get(url).json()
            except Exception:
                break
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                src = h.get("_source", {}) or {}
                ciks = src.get("ciks") or []
                cik = f"{int(ciks[0]):010d}" if ciks else None
                if not cik or cik in seen:
                    continue
                tickers = src.get("tickers") or []
                ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
                if not ticker:
                    continue
                seen.add(cik)
                file_date = src.get("file_date", "")
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                accession = id_parts[0]

                # Identify which activist matched
                m = ACTIVIST_RX.search(q)
                activist = m.group(0) if m else ""

                # Recency score
                try:
                    fdt = datetime.strptime(file_date[:10], "%Y-%m-%d")
                    days_ago = (datetime.now(timezone.utc).replace(tzinfo=None)
                                - fdt).days
                except Exception:
                    days_ago = None

                score = 0.0
                reasons = [f"8-K mentions {activist}"]
                if days_ago is not None:
                    if days_ago <= 14: score += 25; reasons.append(f"{days_ago}d ago (fresh)")
                    elif days_ago <= 45: score += 18; reasons.append(f"{days_ago}d ago")
                    elif days_ago <= 90: score += 10
                # Curated activist multiplier
                if any(top in activist for top in
                       ("elliott", "starboard", "trian", "engaged",
                        "mantle ridge", "icahn", "pershing")):
                    score += 12; reasons.append("tier-1 activist filer")

                # If already recorded from another query, keep highest
                if ticker in out and out[ticker]["score"] >= score:
                    continue
                out[ticker] = {
                    "source": "8-K Item 7.01/8.01",
                    "filing_date": file_date,
                    "accession": accession,
                    "activist_match": activist,
                    "days_since": days_ago,
                    "score": round(score, 1),
                    "reasons": "; ".join(reasons),
                }
            offset += 100
            time.sleep(args.sleep)

    print(f"  [1/2] 8-K hits: {len(out)}", file=sys.stderr)

    # 2. SC 13D filings filtered to known activists (last 60 days)
    if pull_13d_index:
        print(f"[2/2] Scanning recent SC 13D filings",
              file=sys.stderr, flush=True)
        sd13d = (datetime.now(timezone.utc)
                  - timedelta(days=min(60, args.days))).strftime("%Y-%m-%d")
        try:
            hits = pull_13d_index(sd13d, end, limit=2000)
        except Exception as e:
            print(f"  13d sweep failed: {e}", file=sys.stderr)
            hits = []
        for h in hits:
            tk = (h.get("target_ticker") or "").upper()
            if not tk:
                continue
            filer = h.get("filer_name") or ""
            if not ACTIVIST_RX.search(filer):
                continue
            try:
                fdt = datetime.strptime(h.get("file_date", "")[:10], "%Y-%m-%d")
                days_ago = (datetime.now(timezone.utc).replace(tzinfo=None)
                            - fdt).days
            except Exception:
                days_ago = None
            score = 0.0
            reasons = [f"SC 13D filed by {filer[:40]}"]
            if days_ago is not None:
                if days_ago <= 14: score += 25; reasons.append(f"{days_ago}d ago (fresh)")
                elif days_ago <= 30: score += 18
                elif days_ago <= 60: score += 12
            if any(top in filer.lower() for top in
                   ("elliott", "starboard", "trian", "engaged",
                    "mantle ridge", "icahn", "pershing", "valueact")):
                score += 15
                reasons.append("tier-1 activist")
            if tk in out and out[tk]["score"] >= score:
                continue
            out[tk] = {
                "source": "SC 13D",
                "filing_date": h.get("file_date"),
                "accession": h.get("accession"),
                "activist_match": filer[:60],
                "days_since": days_ago,
                "score": round(score, 1),
                "reasons": "; ".join(reasons),
            }

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 25 activist letter / 13D feed ===")
    for tk, v in ranked[:25]:
        print(f"  {tk:<7} {v['score']:<5.0f} {v['source']:<22} "
              f"days={v.get('days_since')} {v['reasons'][:55]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
