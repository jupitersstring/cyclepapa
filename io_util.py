"""Shared IO + source-health utilities.

Two engineering fixes from SOURCES_AND_ANALYSIS Part 3:

  E1 (atomic writes) -- 36 of 46 producers wrote output with a plain
     `path.write_text(...)`; a sandbox reset or crash mid-write left a
     truncated/corrupt JSON that every downstream consumer then failed on
     (silently, thanks to E3). write_json() writes to a temp file in the
     same directory and os.replace()s it in -- the swap is atomic on
     POSIX, so a reader sees either the old file or the new one, never a
     half-written one.

  E3 (source-health gate) -- absent/empty/malformed source files scored
     0 exactly like "no signal", which is how whole layers (spinoff,
     arquitos, the un-committed equity-committee JSON) fed zeros
     unnoticed. check_sources() distinguishes the three and is called at
     the end of rebuild_all so the failure is loud, not silent.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_json(path, obj, indent: int = 2, default=str) -> None:
    """Atomically write obj as JSON to path (tmp in same dir + replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=indent, default=default)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic on POSIX
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# --- source-health gate ------------------------------------------------
# name -> (min_records, required_keys). required_keys checked on the first
# record. A layer whose data is expected to be sparse sets min_records=1.
CONSUMED_SOURCES = {
    "yfinance_quick.json": (1000, ["price"]),
    "proxy_scan.json": (100, ["ticker"]),
    "tender_scan.json": (1000, []),
    "cancel_10b5_1.json": (1000, []),
    "form4_buys.json": (50, ["buyer_set"]),
    "form144_scan.json": (500, []),
    "buyback_verify.json": (200, []),
    "discretionary_insider_conviction.json": (50, ["score"]),
    "opportunistic_insiders.json": (50, ["score"]),
    "coval_stafford_proxy.json": (200, ["score"]),
    "voss_cic_triangulation.json": (100, []),
    "net_net_ncav.json": (50, []),
    "emergence_crossfeed.json": (50, ["score"]),
    "distressed_stub_progress.json": (10, ["score"]),
    "hidden_asset_watch.json": (1, []),
    "credit_agreement_mine.json": (20, ["score"]),
    "equity_committee_scan.json": (1, ["score"]),
    "asymmetry_assembly.json": (100, ["score"]),
    "xbrl_frames_store.json": (3000, ["equity"]),
    "net_buyback.json": (500, ["score"]),
    "full_universe_consensus.csv": (1000, None),   # csv: row-count only
}


def check_sources(root=".", strict_fail=False) -> list[str]:
    """Return a list of health problems. Distinguishes MISSING / EMPTY /
    MALFORMED / SPARSE (below expected min) so 'absent' never reads as
    'zero signal'. Prints a summary; raises if strict_fail and any hard
    problem (missing/empty/malformed) is found."""
    root = Path(root)
    problems: list[str] = []
    for name, (min_n, keys) in CONSUMED_SOURCES.items():
        p = root / name
        if not p.exists():
            problems.append(f"MISSING   {name}")
            continue
        if p.stat().st_size == 0:
            problems.append(f"EMPTY     {name}")
            continue
        if name.endswith(".csv"):
            n = sum(1 for _ in p.open()) - 1
            if n < min_n:
                problems.append(f"SPARSE    {name} ({n} rows < {min_n})")
            continue
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            problems.append(f"MALFORMED {name} ({type(e).__name__})")
            continue
        n = len(d)
        if n < min_n:
            problems.append(f"SPARSE    {name} ({n} < {min_n})")
        if keys and n:
            rec = next(iter(d.values())) if isinstance(d, dict) else d[0]
            if isinstance(rec, dict):
                missing = [k for k in keys if k not in rec]
                if missing:
                    problems.append(f"SCHEMA    {name} missing {missing}")

    hard = [x for x in problems if x.split()[0] in
            ("MISSING", "EMPTY", "MALFORMED")]
    if problems:
        print("=== SOURCE-HEALTH: %d issue(s) ===" % len(problems))
        for x in problems:
            print("  " + x)
    else:
        print("=== SOURCE-HEALTH: all %d consumed sources OK ===" %
              len(CONSUMED_SOURCES))
    if strict_fail and hard:
        raise SystemExit(f"source-health: {len(hard)} hard failure(s)")
    return problems


if __name__ == "__main__":
    import sys
    probs = check_sources(Path(__file__).parent,
                          strict_fail="--strict" in sys.argv)
    raise SystemExit(1 if probs else 0)
