"""Persist / restore the raw EDGAR segment facts through git.

WHY: the 8,021-filer dimensional-XBRL harvest (hours of SEC traffic) was
lost once because both edgar_segments_cache/ and edgar_segments.csv were
gitignored — the container was reclaimed and the only copy died with it.
Derived signals survived, raw facts did not, and the segment pipeline
rewrite had to trigger a full re-harvest. Never again: after every
extract, run

    python3 persist_edgar_segments.py save    # split-gzip + stage for commit

which writes edgar_segments_parts/part_NNN.csv.gz (each < 40 MB, safely
under GitHub's limits) for committing. On a fresh container,

    python3 persist_edgar_segments.py restore # reassemble edgar_segments.csv

The per-filer JSON cache stays ignored (gigabytes, reproducible from the
CSV's accession list); the flattened facts CSV is the durable artifact.
"""
from __future__ import annotations
import glob
import gzip
import os
import shutil
import sys

PARTS_DIR = "edgar_segments_parts"
CSV = "edgar_segments.csv"
PART_MAX = 38 * 1024 * 1024      # compressed bytes per part


def save():
    if not os.path.exists(CSV):
        sys.exit(f"{CSV} not found — nothing to persist")
    os.makedirs(PARTS_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(PARTS_DIR, "part_*.csv.gz")):
        os.remove(old)
    part, n_bytes, total_in = 0, 0, 0
    out = gzip.open(os.path.join(PARTS_DIR, f"part_{part:03d}.csv.gz"),
                    "wb", compresslevel=9)
    with open(CSV, "rb") as fh:
        header = fh.readline()
        out.write(header)
        for line in fh:
            out.write(line)
            total_in += len(line)
            # check compressed size occasionally
            if total_in and total_in % (64 * 1024 * 1024) < len(line):
                out.flush()
                n_bytes = os.path.getsize(out.name)
                if n_bytes >= PART_MAX:
                    out.close()
                    part += 1
                    out = gzip.open(
                        os.path.join(PARTS_DIR, f"part_{part:03d}.csv.gz"),
                        "wb", compresslevel=9)
                    out.write(header)      # every part is a valid CSV
    out.close()
    sizes = {p: os.path.getsize(p) for p in
             sorted(glob.glob(os.path.join(PARTS_DIR, "part_*.csv.gz")))}
    for p, s in sizes.items():
        print(f"  {p}  {s/1e6:.1f} MB")
    print(f"saved {len(sizes)} part(s) — git add {PARTS_DIR} && commit")


def restore():
    parts = sorted(glob.glob(os.path.join(PARTS_DIR, "part_*.csv.gz")))
    if not parts:
        sys.exit(f"no parts in {PARTS_DIR}/ — nothing to restore")
    # a MISSING MIDDLE PART would silently truncate the restore — verify
    # the sequence is contiguous from 000
    nums = [int(os.path.basename(p)[5:8]) for p in parts]
    if nums != list(range(len(nums))):
        sys.exit(f"part sequence has gaps: {nums} — refusing a silent "
                 f"partial restore")
    with open(CSV, "wb") as out:
        for i, p in enumerate(parts):
            with gzip.open(p, "rb") as fh:
                header = fh.readline()
                if i == 0:
                    out.write(header)
                shutil.copyfileobj(fh, out)
    print(f"restored {CSV} from {len(parts)} part(s) "
          f"({os.path.getsize(CSV)/1e6:.1f} MB)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "save":
        save()
    elif mode == "restore":
        restore()
    else:
        sys.exit("usage: persist_edgar_segments.py save|restore")
