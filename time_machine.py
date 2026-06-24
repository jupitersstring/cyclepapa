"""Time-machine mode — replay the screener as of a past date.

For full fidelity this needs three things:
  (a) Historical AIC snapshot for the target date (data/aic_snapshots/
      YYYY-MM-DD.json)
  (b) Per-EPIC investegate snapshot trimmed to announcements ≤ date
  (c) Price parquets trimmed to bars ≤ date

(c) is essentially free — the parquet has the full history.
(b) requires NO new data — we filter the existing per-EPIC JSON by date.
(a) requires snapshotting AIC raw daily; this script also provides the
    snapshot writer (run daily via cron / GitHub Action).

CLI:
  python3 time_machine.py snapshot              # snapshot today's AIC raw
  python3 time_machine.py replay 2026-04-01     # rerun screen as-of date
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


HERE = Path(os.path.dirname(os.path.abspath(__file__)))
AIC_SNAPSHOT_DIR = HERE / "data" / "aic_snapshots"
INV_DIR = HERE / "data" / "investegate"


def snapshot_today() -> Path:
    """Persist today's AIC raw snapshot to data/aic_snapshots/YYYY-MM-DD.json."""
    import aic_scraper
    raw = aic_scraper.fetch_aic_raw(use_cache=False)
    AIC_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out = AIC_SNAPSHOT_DIR / f"{today}.json"
    with open(out, "w") as f:
        json.dump(raw, f)
    print(f"Wrote {out} ({len(raw)} EPICs)", file=sys.stderr)
    return out


def _nearest_snapshot(as_of: str) -> Path | None:
    """Find the closest <= as_of AIC snapshot file."""
    if not AIC_SNAPSHOT_DIR.exists():
        return None
    cands = sorted(AIC_SNAPSHOT_DIR.glob("*.json"))
    earlier = [p for p in cands if p.stem <= as_of]
    if not earlier:
        return None
    return earlier[-1]


def _trim_investegate(as_of: str, into: Path) -> int:
    """Copy INV_DIR to `into` with each per-EPIC file filtered to
    announcements ≤ as_of. Returns number of files written."""
    into.mkdir(parents=True, exist_ok=True)
    n = 0
    for jf in INV_DIR.glob("*.json"):
        if jf.parent.name != "investegate":
            continue
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        filtered = [a for a in data if (a.get("date") or "") <= as_of]
        with open(into / jf.name, "w") as f:
            json.dump(filtered, f)
        n += 1
    return n


def replay(as_of: str, out_csv: str | None = None) -> int:
    """Run a time-travelled screen as of `as_of` (YYYY-MM-DD).

    Strategy: temporarily replace data/investegate with a date-filtered
    copy and point AIC at the nearest snapshot, then invoke screen_v3.
    Restore on exit.
    """
    snapshot = _nearest_snapshot(as_of)
    if snapshot is None:
        print(f"No AIC snapshot ≤ {as_of}. Run "
              "`python3 time_machine.py snapshot` daily first.",
              file=sys.stderr)
        return 1
    backup = HERE / "data" / "investegate_backup"
    work = HERE / "data" / "investegate_replay"
    if backup.exists():
        shutil.rmtree(backup)
    print(f"Filtering investegate to ≤ {as_of}...", file=sys.stderr)
    n = _trim_investegate(as_of, work)
    print(f"  filtered {n} EPIC file(s)", file=sys.stderr)
    # Swap directories: investegate -> investegate_backup, work -> investegate
    INV_DIR.rename(backup)
    work.rename(INV_DIR)
    # Point aic_scraper's cache to the snapshot
    aic_cache_orig = HERE / "_aic_cache_orig.pkl"
    # aic_scraper uses /tmp/aic_cache.pkl — substitute it
    import aic_scraper
    aic_cache_path = Path(aic_scraper.CACHE_PATH)
    aic_cache_backup = aic_cache_path.with_suffix(".tm.bak")
    if aic_cache_path.exists():
        shutil.copy(aic_cache_path, aic_cache_backup)
    # Write the snapshot in pickle form so aic_scraper picks it up
    import pickle
    with open(snapshot) as f:
        snap = json.load(f)
    with open(aic_cache_path, "wb") as f:
        pickle.dump(snap, f)
    rc = 1
    try:
        cmd = ["python3", "screen_v3.py", "--signals-rns-only"]
        if out_csv:
            cmd.extend(["--out", out_csv])
        print(f"Running: {' '.join(cmd)}  (as of {as_of})", file=sys.stderr)
        result = subprocess.run(cmd, cwd=HERE)
        rc = result.returncode
    finally:
        # Restore
        if INV_DIR.exists():
            shutil.rmtree(INV_DIR)
        backup.rename(INV_DIR)
        if aic_cache_backup.exists():
            shutil.move(str(aic_cache_backup), aic_cache_path)
        elif aic_cache_path.exists():
            aic_cache_path.unlink()
    return rc


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("snapshot")
    rep = sub.add_parser("replay")
    rep.add_argument("as_of", help="YYYY-MM-DD")
    rep.add_argument("--out", default=None)
    args = p.parse_args()
    if args.cmd == "snapshot":
        snapshot_today()
        return 0
    if args.cmd == "replay":
        return replay(args.as_of, args.out)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
