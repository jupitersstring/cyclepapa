#!/usr/bin/env python3
"""
credit_spread_poll.py — FRED OAS monitor as equity-event leading indicator.

Implements keeper #9 from output/process_improvements_keepers.md.

Bond OAS (option-adjusted spread) widening preceded the SVB, BBBY,
and Wirecard equity collapses by 1-3 quarters. Same pattern at
sovereign level (Lazard 9-default 2020-25 study). FRED publishes
ICE BofA OAS series free at fred.stlouisfed.org/graph/fredgraph.csv.

This monitor tracks market-level spreads (HY master, BB, B, CCC,
plus IG master) and flags when 30-day spread widening crosses
threshold. Per-issuer monitoring requires Bloomberg / ICE Data
Indices subscription — deferred.

Outputs:
- One inbox record per series whose 30d delta exceeds threshold
- Records go to red_flag tier (broad-market signal, not auto-promoted)

Usage:
    python -m src.credit_spread_poll
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

HEADERS = {"User-Agent": "cyclepapa-screener research@example.com"}

# Series → (label, threshold-bps for 30d widening that triggers).
# Thresholds reflect each band's historical 1-sigma move; CCC is the
# most-volatile so requires a higher absolute threshold to trigger.
SERIES = {
    "BAMLH0A0HYM2":  ("HY master OAS",         100),   # 1.0% widening = signal
    "BAMLH0A1HYBB":  ("HY BB OAS",              75),
    "BAMLH0A2HYB":   ("HY B OAS",               90),
    "BAMLH0A3HYC":   ("HY CCC+ distressed OAS", 150),  # most-distressed bucket
    "BAMLC0A0CM":    ("IG master OAS",          50),
    "BAMLEM2RAAA2APUBLEUEMEAGGRR":  ("EM IG Public OAS", 100),
}


def fetch_series(series_id: str, retries: int = 3) -> list[tuple[str, float]]:
    """Fetch the last 6 months of OAS observations."""
    cosd = (date.today() - timedelta(days=180)).isoformat()
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(FRED_CSV,
                             params={"id": series_id, "cosd": cosd},
                             headers=HEADERS, timeout=20)
            r.raise_for_status()
            reader = csv.reader(io.StringIO(r.text))
            next(reader, None)        # header
            out: list[tuple[str, float]] = []
            for row in reader:
                if len(row) < 2 or row[1] in ("", "."):
                    continue
                try:
                    out.append((row[0], float(row[1])))
                except ValueError:
                    continue
            return out
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! FRED {series_id} failed: {exc}", file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def compute_30d_delta_bps(obs: list[tuple[str, float]]) -> float | None:
    """30-business-day delta in basis points (most-recent vs 30 days back)."""
    if len(obs) < 35:
        return None
    latest = obs[-1][1]
    # Find approx 30 trading-day prior point (skip weekends in CSV gaps)
    prior = obs[-31][1] if len(obs) >= 31 else obs[0][1]
    return (latest - prior) * 100   # OAS in percent; * 100 → bps


def normalize_hit(series_id: str, label: str, latest_date: str,
                  latest_val: float, delta_bps: float, threshold: int,
                  fetched_at: str) -> dict:
    direction = "widening" if delta_bps > 0 else "tightening"
    return {
        "tier":        "red_flag",
        "query_label": f"red_flag.credit_spread_{direction}",
        "query_note":  (f"{label}: 30d delta {delta_bps:+.0f}bps "
                        f"(threshold {threshold}bps); latest {latest_val:.2f}% "
                        f"on {latest_date}. Historical lead-lag: HY OAS "
                        f"widening preceded SVB / BBBY / Wirecard equity "
                        f"collapses by 1-3 quarters."),
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        label,
        "form":        "FRED ICE BofA OAS observation",
        "form_code":   series_id,
        "accession":   f"fred-{series_id}-{latest_date.replace('-','')}",
        "filed":       latest_date,
        "jurisdiction": "US-MARKET",
        "url":         f"https://fred.stlouisfed.org/series/{series_id}",
        "delta_30d_bps": round(delta_bps, 1),
        "latest_pct":  round(latest_val, 3),
        "threshold_bps": threshold,
        "source":      "FRED-ICE-BofA-OAS",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"creditspread_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll() -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print("Polling FRED ICE BofA OAS series...")
    triggered: list[dict] = []
    for series_id, (label, threshold) in SERIES.items():
        obs = fetch_series(series_id)
        if not obs:
            print(f"  {series_id:30s} (no data)")
            continue
        delta = compute_30d_delta_bps(obs)
        if delta is None:
            print(f"  {series_id:30s} {label[:25]:25s} insufficient history")
            continue
        latest_date, latest_val = obs[-1]
        flag = "⚠ TRIGGER" if abs(delta) >= threshold else ""
        print(f"  {series_id:30s} {label[:25]:25s} "
              f"latest {latest_val:5.2f}%  30d {delta:+6.0f}bps  {flag}")
        if abs(delta) >= threshold:
            triggered.append(normalize_hit(
                series_id, label, latest_date, latest_val,
                delta, threshold, fetched_at))
        time.sleep(0.20)
    if triggered:
        counts = write_inbox(triggered)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    else:
        print("\nNo OAS series crossed widening / tightening thresholds.")
    return len(triggered)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    total = poll()
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
