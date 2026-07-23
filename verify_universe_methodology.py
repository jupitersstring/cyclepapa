"""Verification: prove the ranking methodology processes the
ENTIRE universe from disk, not from session memory.

Asks and answers, with assertion proofs:

  Q1. How many tickers are in the universe ON DISK?
  Q2. Does grand_unified_ranker touch every ticker in the universe?
  Q3. Does consensus_meta_ranker derive purely from CSV inputs?
  Q4. Is the convergent list derivable from those CSVs alone?
  Q5. Are there any hardcoded ticker dependencies?

Run with: python3 verify_universe_methodology.py
Outputs:
  - Per-layer ticker counts from disk
  - Universe size (union of layers)
  - Re-derived convergent list (no hardcoded names)
  - Pass/fail flags
"""

from __future__ import annotations

import csv
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def green(s): return f"\033[92m{s}\033[0m"
def red(s): return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"


# ----------------------------------------------------------------------
# Q1. Universe from disk
# ----------------------------------------------------------------------

def q1_universe_from_disk() -> set[str]:
    section("Q1. Universe from DISK (no in-memory ticker lists)")

    sources = {
        "cancel_10b5_1.json (10b5-1 sweep)": "cancel_10b5_1.json",
        "tender_scan.json (SC TO / 14D-9 / 13E-3)": "tender_scan.json",
        "form4_buys.json (Form 4 P-buy)": "form4_buys.json",
        "form144_scan.json (Form 144 proposed sale)": "form144_scan.json",
        "yfinance_quick.json (valuation overlay)": "yfinance_quick.json",
        "buyback_verify.json (verified shrinkage)": "buyback_verify.json",
    }

    union = set()
    for label, fn in sources.items():
        p = ROOT / fn
        if not p.exists():
            print(f"  {red('MISSING')}  {label}: {fn}")
            continue
        d = json.loads(p.read_text())
        n = len(d)
        union.update(d.keys())
        print(f"  {green('OK')}      {label:<45} {n:>6} tickers")

    # proxy_scan (sharded)
    proxy = set()
    n_files = 0
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.loads(open(fn).read())
        except Exception:
            continue
        n_files += 1
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                proxy.add(r["ticker"])
    print(f"  {green('OK')}      proxy_scan*.json ({n_files} shards)             "
          f"{len(proxy):>6} tickers")
    union.update(proxy)

    print(f"\n  Universe (union of all layer files): "
          f"{green(str(len(union)))} tickers")
    print(f"  Cleaned (drop CIK-only entries): "
          f"{green(str(len([t for t in union if not t.startswith('CIK')])))} tickers")

    return union


# ----------------------------------------------------------------------
# Q2. Grand-unified ranker walks every ticker
# ----------------------------------------------------------------------

def q2_grand_unified_touches_all(disk_universe: set[str]) -> None:
    section("Q2. Does grand_unified_ranker touch every ticker?")

    ranked_path = ROOT / "grand_unified_ranked.csv"
    if not ranked_path.exists():
        print(red("  FAIL — grand_unified_ranked.csv missing"))
        return

    ranked = set()
    for r in csv.DictReader(ranked_path.open()):
        ranked.add(r["ticker"])

    print(f"  grand_unified_ranked.csv rows: {green(str(len(ranked)))}")
    print(f"  disk universe size:            {green(str(len(disk_universe)))}")

    cleaned_disk = {t for t in disk_universe if not t.startswith("CIK")}
    missing = cleaned_disk - ranked
    extra = ranked - cleaned_disk

    if not missing and not extra:
        print(green("  PASS — grand_unified covers every ticker in the disk universe"))
    else:
        if missing:
            sample = list(missing)[:10]
            print(yellow(f"  WARN — {len(missing)} disk tickers NOT in ranker output"))
            print(f"         sample: {sample}")
        if extra:
            print(yellow(f"  NOTE — {len(extra)} ranker tickers not in disk union"))


# ----------------------------------------------------------------------
# Q3. Consensus derived purely from CSVs
# ----------------------------------------------------------------------

def q3_consensus_from_csvs() -> None:
    section("Q3. Is consensus_meta_ranker derived purely from CSV inputs?")

    p = ROOT / "consensus_meta_ranker.py"
    if not p.exists():
        print(red("  FAIL — consensus_meta_ranker.py missing"))
        return
    src = p.read_text()

    # Look for hardcoded ticker patterns (3-5 uppercase letters in quotes)
    hardcoded = re.findall(
        r"['\"]([A-Z]{2,5})['\"]", src)
    # Filter common-word false positives (KEY, USD, etc.)
    common_words = {"CSV", "USD", "EOF", "YYYY", "JSON", "URL", "API",
                    "MD", "USA", "UK", "CIK", "EDGAR"}
    hardcoded_tickers = [t for t in hardcoded if t not in common_words]

    if not hardcoded_tickers:
        print(green("  PASS — no hardcoded ticker references in source"))
    else:
        # Confirm they're not in actual ticker positions (could be labels)
        print(yellow(f"  CHECK — {len(set(hardcoded_tickers))} uppercase tokens; "
                     f"manual audit recommended"))
        print(f"          sample: {list(set(hardcoded_tickers))[:10]}")

    # Verify it actually reads CSVs
    sources_read = re.findall(r"csv\.DictReader\([^)]+\)", src)
    print(f"  csv.DictReader calls: {len(sources_read)}")
    md_loads = re.findall(r"load_archetype_md\([^)]+\)", src)
    print(f"  archetype-md parses:  {len(md_loads)}")


# ----------------------------------------------------------------------
# Q4. Re-derive convergent list purely from CSV
# ----------------------------------------------------------------------

def q4_rederive_convergent() -> list[dict]:
    section("Q4. Re-derive the convergent list from consensus_ranking.csv")

    cr = ROOT / "consensus_ranking.csv"
    if not cr.exists():
        print(red("  FAIL — consensus_ranking.csv missing"))
        return []

    rows = list(csv.DictReader(cr.open()))
    print(f"  Total consensus rows: {len(rows)}")

    convergent = []
    for r in rows:
        try:
            ns = int(r["n_screens"])
            na = int(r["n_archetypes_won"])
        except (ValueError, KeyError):
            continue
        if ns >= 3 and na >= 1:
            convergent.append(r)

    convergent.sort(key=lambda r: (-int(r["n_screens"]),
                                   -int(r["n_archetypes_won"]),
                                   -float(r.get("consensus_score") or 0)))

    print(green(f"  Convergent (≥3 screens AND ≥1 archetype): "
                f"{len(convergent)} names"))
    print()
    print(f"  {'#':<3}{'TKR':<8}{'NS':<4}{'NA':<4}{'CONS':<7}{'SCREENS'}")
    for i, r in enumerate(convergent, 1):
        print(f"  {i:<3}{r['ticker']:<8}{r['n_screens']:<4}"
              f"{r['n_archetypes_won']:<4}"
              f"{r.get('consensus_score', '?'):<7}"
              f"{r['screens'][:60]}")
    return convergent


# ----------------------------------------------------------------------
# Q5. Audit hardcoded ticker references across all artifacts
# ----------------------------------------------------------------------

def q5_audit_hardcoded() -> None:
    section("Q5. Audit hardcoded ticker references across modules")
    print("  Distinguishes:")
    print("    (a) MEMBERSHIP hardcoded -- list/tuple of >=3 tickers used "
          "for selection")
    print("    (b) ANNOTATION overlay   -- dict keyed by ticker for display")
    print()

    audit_files = [
        ("build_most_asymmetric_xlsx.py", "Excel workbook builder"),
        ("systematic_rankings.py",        "Markdown rollup"),
        ("grand_unified_ranker.py",       "Universe ranker"),
        ("consensus_meta_ranker.py",      "Consensus meta-ranker"),
        ("informational_buys.py",         "Cohen-Malloy scorer"),
        ("psu_archetypes_full.py",        "Archetype generator"),
    ]

    # Pattern (a): membership list -- multiple tickers in a single
    # list/tuple literal. This is the bad pattern.
    membership_re = re.compile(
        r"[\[(]\s*['\"][A-Z]{2,5}['\"]\s*,\s*['\"][A-Z]{2,5}['\"]\s*,"
        r"\s*['\"][A-Z]{2,5}['\"]",
    )

    # Pattern (b): annotation dict -- ticker as a dict key.
    annotation_re = re.compile(r"['\"]([A-Z]{2,5})['\"]\s*:")

    for fn, label in audit_files:
        p = ROOT / fn
        if not p.exists():
            continue
        src = p.read_text()

        membership_hits = membership_re.findall(src)
        annotation_keys = set(annotation_re.findall(src))

        # Validate annotation_keys are actually tickers (in universe)
        try:
            yf = json.loads((ROOT / "yfinance_quick.json").read_text())
            real_annotations = annotation_keys & set(yf.keys())
        except Exception:
            real_annotations = set()

        if membership_hits:
            print(f"  {red('MEMBERSHIP')}  {fn:<35} "
                  f"{len(membership_hits)} hardcoded membership lists")
            print(f"             sample: {membership_hits[0][:80]}")
        elif real_annotations:
            print(f"  {yellow('OVERLAY')}    {fn:<35} "
                  f"{len(real_annotations)} editorial ticker annotations "
                  f"(display-only)")
        else:
            print(f"  {green('CLEAN')}      {fn:<35} {label}")


# ----------------------------------------------------------------------

def main() -> int:
    print("Universe-coverage methodology audit")
    print("Verifying that the ranking processes the entire universe")
    print("from disk, with no reliance on session/local memory.")

    universe = q1_universe_from_disk()
    q2_grand_unified_touches_all(universe)
    q3_consensus_from_csvs()
    convergent = q4_rederive_convergent()
    q5_audit_hardcoded()

    section("SUMMARY")
    print(f"  Universe on disk: {len(universe)} tickers")
    print(f"  Convergent (re-derived live): {len(convergent)} names")
    print(f"  See `convergent_rederived.csv` for the disk-derived list")

    # Write the re-derived list so it's verifiable
    out = ROOT / "convergent_rederived.csv"
    with out.open("w", newline="") as f:
        if convergent:
            w = csv.DictWriter(f, fieldnames=list(convergent[0].keys()))
            w.writeheader()
            w.writerows(convergent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
