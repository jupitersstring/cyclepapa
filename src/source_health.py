#!/usr/bin/env python3
"""
source_health.py — sourcing observability / data-quality monitor.

Institutional pipelines never fly blind: you must ALWAYS know whether
each source is actually producing data. Currently, if the ASX endpoint
changed and started returning 0 records, nobody would notice — the
refresh would keep "succeeding" while a whole geography went dark.

This monitor scans data/inbox/ over a trailing window, counts records
per SOURCE per day, maintains a rolling baseline, and flags each source:

  OK       producing at/near its baseline
  STALE    no record in > staleness_days (endpoint likely dead)
  ANOMALY  today's count collapsed vs baseline (silent breakage)
  QUIET    low-volume source with a legitimately sparse cadence

Persists data/source_health.json (per-source last_seen + rolling stats)
and writes output/source_health.md (operator dashboard). Exits non-zero
if any source is STALE or ANOMALY so a cron/CI wrapper can alert.

Usage:
    python -m src.source_health                 # 30-day window
    python -m src.source_health --days-back 45 --staleness-days 4
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
HEALTH_JSON = REPO / "data" / "source_health.json"
HEALTH_MD = REPO / "output" / "source_health.md"

# Expected cadence per source: how many days between records is normal.
# Low-frequency sources (quarterly 13F, bi-monthly short interest,
# episodic OFAC) shouldn't be flagged STALE at a daily threshold.
LOW_FREQUENCY = {
    "EDGAR-13F": 95,          # quarterly
    "OFAC": 10,               # episodic
    "FRED-ICE-BofA-OAS": 5,   # only writes on threshold breach
    "LDA-Senate": 5,
    "EDGAR-postreorg": 10,
    "CVM-IPE": 8,             # weekly archive refresh
}

# The canonical `source` string every active poller SHOULD emit. Without
# this, source_health only classified sources that produced records on disk,
# so a poller that produces ZERO records (endpoint moved, auth broke, a whole
# geography went dark) was simply absent from the report — invisible, the
# exact silent-failure this module claims to catch. Any EXPECTED_SOURCE with
# no records in the window is now reported as DARK.
EXPECTED_SOURCES = {
    "ASX", "CVM-IPE", "CourtListener-RECAP", "EDGAR-13F", "EDGAR-8K-items",
    "EDGAR-Form15", "EDGAR-Form4-cluster-sells", "EDGAR-SC13D", "EDGAR-forms",
    "EDGAR-postreorg", "EDGAR-FTS", "FRED-ICE-BofA-OAS", "LDA-Senate", "NSM",
    "OFAC", "SEDAR+", "TDnet", "spinoff-radar", "HKEXnews",
    "SGX", "OAM-AMF", "JSE-SENS", "EDGAR-distressed13D",
    "CourtListener-emergence", "EDGAR-going-concern",
}


def collect_counts(days_back: int) -> dict[str, dict[str, int]]:
    """source -> {day_iso: n_records} over the trailing window."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    end = date.today()
    for n in range(days_back + 1):
        day = (end - timedelta(days=n)).isoformat()
        day_dir = INBOX / day
        if not day_dir.exists():
            continue
        for jf in day_dir.rglob("*.json"):
            try:
                rec = json.loads(jf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            src = rec.get("source") or rec.get("_tier_dir") or "unknown"
            # don't count derived corroboration records as a source
            if src == "corroboration":
                continue
            counts[src][day] += 1
    return counts


def classify(src: str, day_counts: dict[str, int], today: date,
             staleness_days: int) -> dict:
    days = sorted(day_counts)
    last_day = days[-1] if days else None
    last_n = day_counts.get(last_day, 0) if last_day else 0
    daily_vals = [v for v in day_counts.values() if v > 0]
    mean = statistics.mean(daily_vals) if daily_vals else 0.0
    stdev = statistics.pstdev(daily_vals) if len(daily_vals) > 1 else 0.0
    age = (today - date.fromisoformat(last_day)).days if last_day else 999
    tol = max(staleness_days, LOW_FREQUENCY.get(src, staleness_days))

    status = "OK"
    if age > tol:
        status = "STALE"
    elif mean >= 5 and stdev > 0 and last_n < mean - 2 * stdev:
        # today's volume collapsed vs its own baseline
        status = "ANOMALY"
    elif mean < 2:
        status = "QUIET"
    return {
        "source": src,
        "status": status,
        "last_seen": last_day,
        "age_days": age,
        "last_count": last_n,
        "active_days": len(daily_vals),
        "mean_per_active_day": round(mean, 1),
        "stdev": round(stdev, 1),
        "total_window": sum(day_counts.values()),
        "cadence_tolerance_days": tol,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=30)
    ap.add_argument("--staleness-days", type=int, default=3)
    args = ap.parse_args()

    today = date.today()
    counts = collect_counts(args.days_back)
    reports = [classify(src, dc, today, args.staleness_days)
               for src, dc in counts.items()]
    # DARK: an expected poller that produced ZERO records this window. This is
    # the silent-failure case a count-only scan can never see. Only fire when
    # the source's cadence means a record WAS due in the window — a quarterly
    # feed (13F, tol 95d) legitimately shows nothing across 30 days.
    for src in sorted(EXPECTED_SOURCES - set(counts)):
        if LOW_FREQUENCY.get(src, args.staleness_days) > args.days_back:
            continue
        reports.append({
            "source": src, "status": "DARK", "last_seen": None,
            "age_days": 999, "last_count": 0, "active_days": 0,
            "mean_per_active_day": 0.0, "stdev": 0.0, "total_window": 0,
            "cadence_tolerance_days": LOW_FREQUENCY.get(src, args.staleness_days),
        })
    reports.sort(key=lambda r: ({"DARK": 0, "STALE": 1, "ANOMALY": 2,
                                 "QUIET": 3, "OK": 4}[r["status"]],
                                -r["total_window"]))

    stale = [r for r in reports if r["status"] == "STALE"]
    anomaly = [r for r in reports if r["status"] == "ANOMALY"]
    dark = [r for r in reports if r["status"] == "DARK"]

    print(f"Source health over {args.days_back + 1} days "
          f"({len(reports)} sources):")
    for r in reports:
        icon = {"OK": "✓", "QUIET": "·", "STALE": "✗", "ANOMALY": "⚠",
                "DARK": "⬛"}[r["status"]]
        print(f"  {icon} {r['status']:8s} {r['source']:24s} "
              f"last={r['last_seen']} ({r['age_days']}d ago) "
              f"total={r['total_window']:>5d} "
              f"mean/day={r['mean_per_active_day']}")

    # Persist state + dashboard
    state = {"generated": datetime.utcnow().isoformat() + "Z",
             "sources": {r["source"]: r for r in reports}}
    HEALTH_JSON.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_JSON.write_text(json.dumps(state, indent=2, sort_keys=True))

    lines = [
        f"# Source health dashboard ({today.isoformat()})",
        "",
        "Auto-generated by `src/source_health.py`. Per-source freshness "
        "and volume-anomaly monitoring so a silently-broken endpoint "
        "(returns 0 while the refresh keeps 'succeeding') is caught.",
        "",
        f"- Window: {args.days_back + 1} days",
        f"- Sources tracked: {len(reports)}",
        f"- **DARK (expected source, zero records): {len(dark)}**  ·  "
        f"**STALE: {len(stale)}**  ·  **ANOMALY: {len(anomaly)}**  ·  "
        f"OK/QUIET: {len(reports) - len(dark) - len(stale) - len(anomaly)}",
        "",
        "| Status | Source | Last seen | Age | Last | Total | Mean/day |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in reports:
        lines.append(
            f"| {r['status']} | {r['source']} | {r['last_seen']} | "
            f"{r['age_days']}d | {r['last_count']} | {r['total_window']} | "
            f"{r['mean_per_active_day']} |")
    if dark or stale or anomaly:
        lines += ["", "## Alerts", ""]
        for r in dark:
            lines.append(f"- **DARK** `{r['source']}` — an expected poller "
                         f"produced ZERO records this window. Endpoint moved, "
                         f"auth broke, or the poller stopped running.")
        for r in stale:
            lines.append(f"- **STALE** `{r['source']}` — no record in "
                         f"{r['age_days']}d (tolerance "
                         f"{r['cadence_tolerance_days']}d). Endpoint likely "
                         f"broken or query stale.")
        for r in anomaly:
            lines.append(f"- **ANOMALY** `{r['source']}` — last count "
                         f"{r['last_count']} vs baseline "
                         f"{r['mean_per_active_day']}±{r['stdev']}. "
                         f"Possible partial breakage.")
    HEALTH_MD.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_MD.write_text("\n".join(lines) + "\n")

    print(f"\nWrote {HEALTH_JSON}")
    print(f"Wrote {HEALTH_MD}")
    if dark or stale or anomaly:
        print(f"\n⚠ {len(dark)} DARK, {len(stale)} stale, "
              f"{len(anomaly)} anomalous sources.")
        return 1
    print("\nAll sources healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
