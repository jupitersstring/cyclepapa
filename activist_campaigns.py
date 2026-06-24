"""Cross-name activist campaign tracker.

For each known activist holder, finds the set of UK CEFs they have
filed TR-1s on within a rolling N-day window. A burst of filings on
many trusts in the same window = the activist's campaign is
escalating — a signal that any *single* trust in the burst is more
likely to see a corporate-action follow-up than the per-name score
alone implies.

Reads:  data/investegate/tr1/*.json  (per-URL TR-1 detail cache)
        data/investegate/{epic}.json  (announcement list to find date)

Writes: data/activist_campaigns.csv  (one row per activist × window
        with target tickers + count + max-stake-delta)

The output is consumed by screen_v3 to bump resolution_score on any
ticker that's part of an active campaign.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import investegate_scraper as inv

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
TR1_DETAIL_DIR = INV_DIR / "tr1"
OUT_PATH = HERE / "data" / "activist_campaigns.csv"

WINDOW_DAYS = 60        # rolling window over which we count filings
MIN_TARGETS = 2         # only emit campaigns with >= 2 unique trusts


def _norm_holder(holder: str) -> str | None:
    """Match a holder string to one of the canonical activist groups
    in data/activist_holders.csv. Returns the canonical 'name_substring'
    that matched, or None."""
    if not holder:
        return None
    lc = holder.lower()
    for a in inv._activist_holders():
        if a in lc:
            return a
    return None


def collect_filings() -> list[dict]:
    """Walk per-URL TR-1 details, join with per-EPIC announcement date.
    Returns list of dicts with (ticker, date, holder, delta_pp,
    is_activist)."""
    # Build URL -> (epic, date) index from per-EPIC files
    url_to_meta: dict[str, tuple[str, str]] = {}
    for jf in INV_DIR.glob("*.json"):
        epic = jf.stem
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for a in data:
            if a.get("category") != "tr1":
                continue
            u = a.get("url") or ""
            d = a.get("date") or ""
            if u and d:
                url_to_meta[u] = (epic, d)
    out = []
    for jf in TR1_DETAIL_DIR.glob("*.json"):
        try:
            det = json.loads(jf.read_text())
        except Exception:
            continue
        if not det.get("is_activist"):
            continue
        holder = det.get("holder") or ""
        norm = _norm_holder(holder)
        if not norm:
            continue
        # The per-URL cache doesn't know which URL it came from once we
        # only have the file; we have to find it from the URL -> meta
        # index. Filename is the slug-id; match by that.
        rns_id = jf.stem
        # Find an URL whose path ends with /{rns_id}
        match = None
        for u, (epic, d) in url_to_meta.items():
            if u.rstrip("/").endswith(f"/{rns_id}"):
                match = (epic, d)
                break
        if match is None:
            continue
        epic, d = match
        out.append({
            "ticker": f"{epic}.L",
            "date": d,
            "holder": holder,
            "holder_group": norm,
            "delta_pp": float(det.get("delta_pp") or 0.0),
            "direction": det.get("direction", "unknown"),
        })
    return out


def detect_campaigns(filings: list[dict],
                     window_days: int = WINDOW_DAYS,
                     min_targets: int = MIN_TARGETS) -> list[dict]:
    """For each activist group, group filings into rolling windows
    and emit campaign rows where >= min_targets distinct tickers
    appear within window_days."""
    by_group: dict[str, list[dict]] = defaultdict(list)
    for f in filings:
        if f["direction"] != "buy":
            continue
        try:
            f["dt"] = datetime.fromisoformat(f["date"]).replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
        by_group[f["holder_group"]].append(f)
    campaigns = []
    for group, fs in by_group.items():
        fs_sorted = sorted(fs, key=lambda x: x["dt"])
        # Sliding window across the sorted filings
        i = 0
        for j in range(len(fs_sorted)):
            while (fs_sorted[j]["dt"] - fs_sorted[i]["dt"]).days > window_days:
                i += 1
            window = fs_sorted[i:j + 1]
            tickers = {f["ticker"] for f in window}
            if len(tickers) >= min_targets:
                # Only emit at the right-edge of each maximal window
                end_dt = window[-1]["dt"]
                # Check if this window is already covered by a later one
                next_starts_within = (
                    j + 1 < len(fs_sorted)
                    and (fs_sorted[j + 1]["dt"] - fs_sorted[i]["dt"]).days
                        <= window_days
                )
                if next_starts_within:
                    continue
                campaigns.append({
                    "holder_group": group,
                    "window_start": window[0]["date"],
                    "window_end": window[-1]["date"],
                    "n_filings": len(window),
                    "n_targets": len(tickers),
                    "targets": "|".join(sorted(tickers)),
                    "total_delta_pp": round(
                        sum(f["delta_pp"] for f in window), 3),
                })
    return campaigns


def active_targets(campaigns: list[dict], today: datetime | None = None,
                   freshness_days: int = 90) -> dict[str, list[str]]:
    """Return {ticker: [holder_group, ...]} for any ticker currently
    in an active campaign (last filing within freshness_days)."""
    today = today or datetime.now(timezone.utc)
    out: dict[str, set[str]] = defaultdict(set)
    for c in campaigns:
        try:
            end = datetime.fromisoformat(c["window_end"]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if (today - end).days > freshness_days:
            continue
        for t in c["targets"].split("|"):
            out[t].add(c["holder_group"])
    return {t: sorted(groups) for t, groups in out.items()}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(OUT_PATH))
    args = p.parse_args()
    filings = collect_filings()
    print(f"Activist buy-side TR-1s found: {len(filings)}", file=sys.stderr)
    if filings:
        campaigns = detect_campaigns(filings)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="") as f:
            cols = ["holder_group", "window_start", "window_end",
                    "n_filings", "n_targets", "targets", "total_delta_pp"]
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for c in campaigns:
                w.writerow(c)
        print(f"Wrote {len(campaigns)} campaign rows to {args.out}",
              file=sys.stderr)
        active = active_targets(campaigns)
        print(f"Active targets right now: {len(active)}", file=sys.stderr)
        for t, groups in sorted(active.items()):
            print(f"  {t:<10}  {', '.join(groups)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
