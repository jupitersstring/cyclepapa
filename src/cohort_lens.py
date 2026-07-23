#!/usr/bin/env python3
"""
cohort_lens.py — the capacity-exit / second-vintage lens (A1 + A2).

The cohort winners (US coal 2016-22, offshore drillers 2021-23, dry-bulk
shipping) all follow one shape: an INDUSTRY-WIDE restructuring wave removes
supply, and the survivors' post-reorg equity multiplies as the cycle turns
on a cleaned-up cost base. Wilbur Ross's ISG executed it with control; the
listed-equity version is buying the emergence VINTAGE that follows the wave.
The failure shape is the mirror: the FIRST restructuring wave in a downcycle
is often too early (Seadrill 2017 → Chapter 22 2021); the vintage AFTER
capacity exit is the one that works.

This lens groups our own inbox record of bankruptcies + emergences by SIC
industry (via the SEC submissions API, cached) and time, then flags:
  WAVE            — an industry with >= --wave-min distinct restructurings
                    in a trailing window (capacity likely exiting)
  COHORT VINTAGE  — emergences occurring during/after a wave in their
                    industry (the buy-signal shape)
  SECOND VINTAGE  — a wave in an industry that ALSO had an earlier wave
                    (the strongest historical setup)

Informational report only — no score impact.

Output: output/cohort_lens.md  (SIC cache: data/sic_cache.json, tracked)

Usage:
    python -m src.cohort_lens
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EMERGENCE = REPO / "data" / "emergence_master.json"
SIC_CACHE = REPO / "data" / "sic_cache.json"
OUT_MD = REPO / "output" / "cohort_lens.md"
UA = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}


def _load_cache() -> dict:
    if SIC_CACHE.exists():
        try:
            return json.loads(SIC_CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def sic_for(cik: str, cache: dict) -> tuple[str, str]:
    """(2-digit SIC, description) for a CIK via the SEC submissions API,
    disk-cached. ('', '') when unavailable — unknown is skipped, never
    penalized."""
    key = str(int(cik)) if str(cik).isdigit() else ""
    if not key:
        return "", ""
    if key in cache:
        return cache[key].get("sic2", ""), cache[key].get("desc", "")
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{int(key):010d}.json",
                         headers=UA, timeout=15)
        j = r.json() if r.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        j = {}
    sic = str(j.get("sic") or "")
    desc = str(j.get("sicDescription") or "")
    cache[key] = {"sic2": sic[:2], "desc": desc}
    time.sleep(0.12)
    return sic[:2], desc


def collect_events() -> tuple[list[dict], list[dict]]:
    """(bankruptcy entries, emergences) with CIKs, from our own record."""
    entries: list[dict] = []
    # bankruptcy ENTRIES: 8-K Item 1.03 entry-side + PACER Chapter 11 records
    for jf in INBOX.rglob("*.json"):
        try:
            r = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(r, dict):
            continue
        lbl = (r.get("query_label") or "")
        if ("item_bankruptcy" in lbl or "bankruptcy_11" in lbl) and r.get("cik"):
            entries.append({"cik": str(r["cik"]), "name": r.get("name", ""),
                            "filed": (r.get("filed") or "")[:10]})
    emergences: list[dict] = []
    if EMERGENCE.exists():
        for ev in json.loads(EMERGENCE.read_text()):
            if ev.get("primary") and ev.get("cik") and not ev.get("pending"):
                emergences.append({"cik": str(ev["cik"]),
                                   "name": ev.get("name", ""),
                                   "ticker": ev.get("ticker", ""),
                                   "filed": (ev.get("last_filed") or "")[:10]})
    return entries, emergences


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave-min", type=int, default=3,
                    help="distinct restructurings to qualify as a wave")
    args = ap.parse_args()

    entries, emergences = collect_events()
    print(f"Events: {len(entries)} bankruptcy entries, "
          f"{len(emergences)} emergences (with CIK)")
    cache = _load_cache()

    # industry (2-digit SIC) → year → set of entity CIKs restructuring
    ind_events: dict[str, dict[int, set]] = defaultdict(lambda: defaultdict(set))
    ind_desc: dict[str, str] = {}
    all_ev = [("entry", e) for e in entries] + [("emerge", e) for e in emergences]
    for i, (kind, e) in enumerate(all_ev):
        sic2, desc = sic_for(e["cik"], cache)
        if not sic2:
            continue
        e["sic2"] = sic2
        ind_desc.setdefault(sic2, desc)
        try:
            yr = int(e["filed"][:4])
        except (ValueError, TypeError):
            continue
        ind_events[sic2][yr].add(e["cik"])
        if (i + 1) % 50 == 0:
            SIC_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
            print(f"  SIC-resolved {i+1}/{len(all_ev)}...")
    SIC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SIC_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))

    # waves: industry-years where trailing-24mo distinct entities >= wave_min
    waves: list[tuple[str, int, int]] = []
    for sic2, by_yr in ind_events.items():
        years = sorted(by_yr)
        for yr in years:
            n = len(by_yr.get(yr, set()) | by_yr.get(yr - 1, set()))
            if n >= args.wave_min:
                waves.append((sic2, yr, n))
    wave_industries = {w[0] for w in waves}
    # second vintage: an industry with waves in >= 2 separated periods
    second = set()
    by_ind_years = defaultdict(list)
    for sic2, yr, n in waves:
        by_ind_years[sic2].append(yr)
    for sic2, yrs in by_ind_years.items():
        if max(yrs) - min(yrs) >= 2:
            second.add(sic2)

    # cohort-vintage emergences: emergence in a wave industry
    cohort_em = [e for e in emergences
                 if e.get("sic2") in wave_industries]

    lines = [
        "# Cohort / capacity-exit lens",
        "",
        "Industry-wide restructuring WAVES from our own inbox record "
        "(bankruptcy entries + emergences grouped by SIC industry). The "
        "case-study shape: the emergence vintage FOLLOWING a wave is the "
        "buy (coal '16, drillers '21); the FIRST restructuring in a "
        "downcycle is often too early (Seadrill '17 → Chapter 22 '21). "
        "Informational — no score impact.",
        "",
        f"- industries with a wave (≥{args.wave_min} distinct restructurings "
        f"in 24mo): **{len(wave_industries)}**  ·  second-vintage "
        f"industries: **{len(second)}**  ·  cohort-vintage emergences: "
        f"**{len(cohort_em)}**",
        "",
        "## Waves",
        "",
        "| SIC | Industry | Year | Entities (24mo) | Second vintage? |",
        "|---|---|---|---:|:--:|",
    ]
    for sic2, yr, n in sorted(waves, key=lambda w: (-w[2], w[0], w[1])):
        lines.append(f"| {sic2} | {ind_desc.get(sic2, '')[:36]} | {yr} | "
                     f"{n} | {'★' if sic2 in second else ''} |")
    lines += ["", "## Cohort-vintage emergences (in a wave industry — the "
              "buy-signal shape)", "",
              "| Name | Ticker | Industry | Emerged |", "|---|---|---|---|"]
    for e in sorted(cohort_em, key=lambda x: x.get("filed", ""), reverse=True):
        lines.append(f"| {str(e['name'])[:32]} | "
                     f"{(e.get('ticker') or '—').split(':')[-1]} | "
                     f"{ind_desc.get(e.get('sic2', ''), '')[:30]} | "
                     f"{e.get('filed', '')} |")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")
    print(f"Waves: {len(waves)} industry-years; cohort-vintage emergences: "
          f"{len(cohort_em)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
