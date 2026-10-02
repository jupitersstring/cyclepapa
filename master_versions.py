#!/usr/bin/env python3
"""Rolling version store for the master CSV.

Every writer that replaces asymmetry_global.csv goes through
versioned_replace(): the OUTGOING master is gzipped into
master_versions/ before the new file lands, so any bad rewrite
(unit bug, torn logic, over-aggressive filter) can be rolled back
locally without digging through git history. Git remains the durable
long-term store (the master is committed on every push); this guards
the window BETWEEN commits and survives only as long as the container.

CLI:
  python3 master_versions.py list
  python3 master_versions.py restore <stamp|latest>   # e.g. 20260906_164200
  python3 master_versions.py diff  <stamp|latest>     # row-count + symbol delta
"""
import glob
import gzip
import os
import shutil
import sys
from datetime import datetime, timezone

VERSIONS_DIR = 'master_versions'
KEEP = 12          # rolling window (~80MB master -> ~15-20MB gz each)
MASTER = 'asymmetry_global.csv'


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')


def snapshot(path: str = MASTER) -> str | None:
    """Gzip the CURRENT file into the version store. Returns snapshot path."""
    if not os.path.exists(path):
        return None
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    base = os.path.basename(path)
    dst = os.path.join(VERSIONS_DIR, f'{base}.{_stamp()}.gz')
    with open(path, 'rb') as fin, gzip.open(dst, 'wb', compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, length=1 << 20)
    _prune(base)
    return dst


def _prune(base: str) -> None:
    versions = sorted(glob.glob(os.path.join(VERSIONS_DIR, f'{base}.*.gz')))
    for old in versions[:-KEEP]:
        try:
            os.remove(old)
        except OSError:
            pass


def versioned_replace(tmp_path: str, path: str = MASTER) -> None:
    """Atomic replace with a pre-image snapshot: snapshot(path) then
    os.replace(tmp_path, path). Writers write to tmp_path first."""
    snapshot(path)
    os.replace(tmp_path, path)


def _resolve(stamp: str, base: str = MASTER) -> str:
    versions = sorted(glob.glob(os.path.join(VERSIONS_DIR, f'{base}.*.gz')))
    if not versions:
        sys.exit('no versions stored')
    if stamp == 'latest':
        return versions[-1]
    hits = [v for v in versions if stamp in v]
    if len(hits) != 1:
        sys.exit(f'{len(hits)} versions match {stamp!r}: '
                 + ', '.join(os.path.basename(h) for h in hits[:6]))
    return hits[0]


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if cmd == 'list':
        for v in sorted(glob.glob(os.path.join(VERSIONS_DIR, '*.gz'))):
            mb = os.path.getsize(v) / 1e6
            print(f'{os.path.basename(v)}  {mb:.1f} MB')
    elif cmd == 'restore':
        src = _resolve(sys.argv[2] if len(sys.argv) > 2 else 'latest')
        snapshot(MASTER)   # version the file being overwritten too
        tmp = MASTER + '.tmp'
        with gzip.open(src, 'rb') as fin, open(tmp, 'wb') as fout:
            shutil.copyfileobj(fin, fout, length=1 << 20)
        os.replace(tmp, MASTER)
        print(f'restored {MASTER} from {os.path.basename(src)}')
    elif cmd == 'diff':
        import pandas as pd
        src = _resolve(sys.argv[2] if len(sys.argv) > 2 else 'latest')
        old = pd.read_csv(src, usecols=['symbol'], compression='gzip')
        new = pd.read_csv(MASTER, usecols=['symbol'])
        o, n = set(old['symbol']), set(new['symbol'])
        print(f'{os.path.basename(src)}: {len(o)} rows -> current: {len(n)}')
        print(f'  added: {len(n - o)}  removed: {len(o - n)}')
        rem = sorted(o - n)[:10]
        if rem:
            print('  removed sample:', rem)
    else:
        sys.exit(f'unknown command {cmd!r} — use list/restore/diff')


if __name__ == '__main__':
    main()
