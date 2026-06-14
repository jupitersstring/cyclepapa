"""Persist /tmp analysis artifacts into the repo's data/ tree so they
survive sandbox resets. Run after any expensive scan or augment.

  python persist_results.py            # copy + commit + push (default)
  python persist_results.py --no-push  # copy + commit, no push
  python persist_results.py --dry-run  # show what would copy

We keep:
  /tmp/stars_aligned_*.csv          -> data/stars_aligned/
  /tmp/mtf_psar_rank*.csv            -> data/psar/
  /tmp/master_cross_system.csv       -> data/master/
  /tmp/final_*.csv                   -> data/master/
  /tmp/best_per_leg.csv              -> data/picks/
  /tmp/*top*_named.csv, *curated*    -> data/picks/
  /tmp/mtf_psar_institutional*.csv   -> data/picks/
  /tmp/cross_leg_conviction.csv      -> data/picks/
  /tmp/master_top10_named.csv        -> data/picks/
  /tmp/pre_mega_adv_wide.csv         -> data/picks/
  /tmp/minervini_metric_eval.csv     -> data/picks/
  /tmp/cross_region_top_uncorrelated.csv -> data/picks/
  /tmp/stars_aligned_top_picks.xlsx  -> data/
  /tmp/{EWUS,IEUS,IJR,IVV,ITOT}.csv  -> data/universe/  (iShares holdings caches)

Nothing else is copied (deliberately) — raw price OHLC is multi-GB and
must be re-fetched from yfinance.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"

PATTERNS = [
    ("/tmp/stars_aligned_*.csv",                 DATA / "stars_aligned"),
    ("/tmp/mtf_psar_rank*.csv",                  DATA / "psar"),
    ("/tmp/master_cross_system.csv",             DATA / "master"),
    ("/tmp/final_*.csv",                         DATA / "master"),
    ("/tmp/best_per_leg.csv",                    DATA / "picks"),
    ("/tmp/cross_leg_conviction.csv",            DATA / "picks"),
    ("/tmp/master_top10_named.csv",              DATA / "picks"),
    ("/tmp/mtf_psar_top*_named.csv",             DATA / "picks"),
    ("/tmp/mtf_psar_top_curated.csv",            DATA / "picks"),
    ("/tmp/mtf_psar_institutional*.csv",         DATA / "picks"),
    ("/tmp/mtf_psar_full_top50_named.csv",       DATA / "picks"),
    ("/tmp/pre_mega_adv_wide.csv",               DATA / "picks"),
    ("/tmp/minervini_metric_eval.csv",           DATA / "picks"),
    ("/tmp/cross_region_top_uncorrelated.csv",   DATA / "picks"),
    ("/tmp/stars_aligned_top_picks.xlsx",        DATA),
    ("/tmp/EWUS*.csv",                           DATA / "universe"),
    ("/tmp/IEUS*.csv",                           DATA / "universe"),
    ("/tmp/IJR*.csv",                            DATA / "universe"),
    ("/tmp/IVV*.csv",                            DATA / "universe"),
    ("/tmp/ITOT*.csv",                           DATA / "universe"),
]


def sync(dry_run: bool):
    n = 0
    for pat, dest in PATTERNS:
        dest.mkdir(parents=True, exist_ok=True)
        for src in glob.glob(pat):
            tgt = dest / Path(src).name
            if dry_run:
                print(f"[dry] {src} -> {tgt}")
            else:
                shutil.copy2(src, tgt)
                print(f"  {src} -> {tgt}")
            n += 1
    print(f"\n{n} files synced.")


def commit_and_push(push: bool):
    subprocess.run(["git", "add", "data/"], cwd=REPO, check=True)
    out = subprocess.run(["git", "diff", "--cached", "--name-only"],
                          cwd=REPO, capture_output=True, text=True).stdout.strip()
    if not out:
        print("No data changes to commit.")
        return
    n = len(out.splitlines())
    subprocess.run([
        "git", "-c", "commit.gpgsign=true", "commit", "-S", "-m",
        f"data: persist {n} analysis artifacts (sandbox-safe snapshot)\n\n"
        "Refreshed via persist_results.py. These are the durable\n"
        "outputs of the screen + augment + PSAR + master-analysis pipeline.\n\n"
        "https://claude.ai/code/session_01LMs9VFsHC2fyzJ4QdzhoG6"
    ], cwd=REPO, check=True)
    if push:
        subprocess.run(["git", "push", "-u", "origin", "HEAD"], cwd=REPO, check=True)
        print("Pushed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()
    sync(dry_run=args.dry_run)
    if not args.dry_run and not args.no_commit:
        commit_and_push(push=not args.no_push)


if __name__ == "__main__":
    main()
