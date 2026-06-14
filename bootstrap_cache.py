"""Restore working caches from the repo-tracked durable copy.

Run after any sandbox reset (or first-time clone). It walks data/cache,
data/spy, and data/wiki, inflates the bz2 pickles back into /tmp where
momentum_rank.py expects them, and copies the wiki CSVs.

Idempotent — re-running is safe.

Usage: python3 bootstrap_cache.py
"""

import bz2
import glob
import os
import pickle
import shutil
import sys

REPO = os.path.dirname(os.path.abspath(__file__))


def inflate_pickle(src_bz2, dst_pkl):
    """Decompress data/cache/foo.pkl.bz2 -> /tmp/foo.pkl if missing or stale."""
    if os.path.exists(dst_pkl):
        # Skip if working copy newer than durable
        if os.path.getmtime(dst_pkl) >= os.path.getmtime(src_bz2):
            return False
    os.makedirs(os.path.dirname(dst_pkl), exist_ok=True)
    with bz2.open(src_bz2, "rb") as fi:
        obj = pickle.load(fi)
    tmp = dst_pkl + ".tmp"
    with open(tmp, "wb") as fo:
        pickle.dump(obj, fo)
    os.replace(tmp, dst_pkl)
    return True


def main():
    n_inflated = 0
    n_skipped = 0
    n_failed = 0

    # 1. Daily/monthly/intraday pickles
    cache_dir = os.path.join(REPO, "data", "cache")
    for src in sorted(glob.glob(os.path.join(cache_dir, "*.pkl.bz2"))):
        fname = os.path.basename(src).replace(".bz2", "")
        dst = f"/tmp/{fname}"
        try:
            if inflate_pickle(src, dst):
                sz = os.path.getsize(dst)
                print(f"  inflated {fname:60s} -> {sz/1024/1024:5.1f} MB")
                n_inflated += 1
            else:
                n_skipped += 1
        except Exception as e:
            print(f"  FAILED {fname}: {e}")
            n_failed += 1

    # 2. SPY pickles
    spy_dir = os.path.join(REPO, "data", "spy")
    for src in sorted(glob.glob(os.path.join(spy_dir, "*.pkl.bz2"))):
        fname = os.path.basename(src).replace(".bz2", "")
        dst = f"/tmp/{fname}"
        try:
            if inflate_pickle(src, dst):
                print(f"  inflated SPY {fname}")
                n_inflated += 1
            else:
                n_skipped += 1
        except Exception as e:
            print(f"  FAILED SPY {fname}: {e}")
            n_failed += 1

    # 3. Wikipedia CSVs
    wiki_src_dir = os.path.join(REPO, "data", "wiki")
    wiki_dst_dir = "/tmp/cyclepapa_wiki"
    os.makedirs(wiki_dst_dir, exist_ok=True)
    for src in sorted(glob.glob(os.path.join(wiki_src_dir, "*.csv"))):
        fname = os.path.basename(src)
        dst = os.path.join(wiki_dst_dir, fname)
        try:
            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                shutil.copy(src, dst)
                print(f"  copied wiki {fname}")
                n_inflated += 1
            else:
                n_skipped += 1
        except Exception as e:
            print(f"  FAILED wiki {fname}: {e}")
            n_failed += 1

    print()
    print(f"bootstrap_cache: inflated={n_inflated} skipped={n_skipped} failed={n_failed}")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
