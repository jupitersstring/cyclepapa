"""Cache persistence: snapshot .cache/ to a dedicated git branch on origin.

Without this, the cache lives only in the sandbox and is lost on any reset.
We tar the cache, split into <90MB chunks (under GitHub's 100MB file limit),
and commit on an orphan branch `cache-snapshot` that's force-pushed each
time. `pull` reassembles and extracts.

Usage:
    python cache_sync.py push          # snapshot cache+results -> origin/cache-snapshot
    python cache_sync.py pull          # restore latest snapshot to working tree
    python cache_sync.py status        # show what's local vs remote

Design choices:
- Orphan branch (no history) keeps repo small; we don't need cache history.
- Chunks named cache_chunks/part_NNN so reassembly order is deterministic.
- A manifest (cache_chunks/MANIFEST) records ticker counts so `status` is fast.
- We tar .cache/ AND results_peg/ AND results_forensic/ AND screener_report.xlsx
  so a re-pull rehydrates the full analytical context.
"""
from __future__ import annotations
import argparse, os, subprocess, tarfile, sys, time, shutil, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent
SNAPSHOT_BRANCH = 'cache-snapshot'
CHUNK_BYTES = 90 * 1024 * 1024
CHUNK_DIR = REPO / 'cache_chunks'

# Paths to include in the snapshot (everything that's expensive to regenerate)
PERSIST_PATHS = [
    Path('.cache'),
    Path('results_peg'),
    Path('results_forensic'),
    Path('screener_report.xlsx'),
]


def _run(cmd, **kw):
    return subprocess.run(cmd, cwd=REPO, check=False, capture_output=True, text=True, **kw)


def _existing_paths():
    return [p for p in PERSIST_PATHS if (REPO / p).exists()]


def _tar_to_chunks(out_dir: Path):
    """Tar .cache/ + results into chunked .tar.gz files, one per chunk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear old chunks
    for f in out_dir.glob('part_*'):
        f.unlink()
    paths = _existing_paths()
    if not paths:
        print('  (nothing to snapshot — no .cache/ or results)')
        return 0, 0
    # Tar into a single stream, then split into chunks
    tar_path = out_dir / 'snapshot.tar.gz'
    with tarfile.open(tar_path, 'w:gz', compresslevel=6) as tar:
        for p in paths:
            tar.add(REPO / p, arcname=str(p))
    total = tar_path.stat().st_size
    # Now split
    n_chunks = 0
    with open(tar_path, 'rb') as src:
        idx = 0
        while True:
            buf = src.read(CHUNK_BYTES)
            if not buf: break
            (out_dir / f'part_{idx:04d}').write_bytes(buf)
            idx += 1; n_chunks += 1
    tar_path.unlink()
    return total, n_chunks


def _chunks_to_tar(chunk_dir: Path, out_tar: Path):
    chunks = sorted(chunk_dir.glob('part_*'))
    if not chunks:
        raise RuntimeError(f'No chunks found in {chunk_dir}')
    with open(out_tar, 'wb') as dst:
        for c in chunks:
            dst.write(c.read_bytes())


def push():
    """Snapshot current cache+results to origin/cache-snapshot (force-push)."""
    paths = _existing_paths()
    if not paths:
        print('Nothing to push — no cache or results present.')
        return 1
    print(f'Snapshotting: {[str(p) for p in paths]}')
    # Build chunks in a temp staging dir
    staging = REPO / '.cache_snapshot_staging'
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir()
    total, n_chunks = _tar_to_chunks(staging / 'cache_chunks')
    print(f'  Snapshot: {total/1e6:.1f} MB across {n_chunks} chunks')

    # Capture manifest info while we still have the snapshot
    manifest = []
    if (REPO / '.cache' / 'yf').exists():
        n_tickers = len({p.name.split('__')[0] for p in (REPO / '.cache' / 'yf').glob('*__info_metrics.parquet')})
        manifest.append(f'cache.yf.info_metrics_tickers={n_tickers}')
    if (REPO / 'results_peg' / 'all.csv').exists():
        with open(REPO / 'results_peg' / 'all.csv') as f:
            manifest.append(f'results_peg.all.rows={sum(1 for _ in f) - 1}')
    manifest.append(f'snapshot_time={int(time.time())}')
    manifest.append(f'total_bytes={total}')
    manifest.append(f'n_chunks={n_chunks}')
    (staging / 'cache_chunks' / 'MANIFEST').write_text('\n'.join(manifest) + '\n')

    # Stash any pending changes on current branch
    r = _run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    current_branch = r.stdout.strip()
    print(f'Current branch: {current_branch}')

    # Use a worktree so we don't disturb working tree
    wt = REPO / '.snapshot_worktree'
    if wt.exists(): shutil.rmtree(wt)
    # Make an orphan branch worktree
    _run(['git', 'worktree', 'remove', '--force', str(wt)])  # cleanup any stale
    r = _run(['git', 'worktree', 'add', '--detach', str(wt)])
    if r.returncode != 0:
        print(f'worktree add failed: {r.stderr}'); return 2
    # Inside the worktree: create orphan branch, clear, copy chunks, commit
    def w(cmd): return subprocess.run(cmd, cwd=wt, check=False, capture_output=True, text=True)
    w(['git', 'checkout', '--orphan', SNAPSHOT_BRANCH])
    w(['git', 'rm', '-rf', '.'])  # clear index
    # Remove everything in worktree
    for entry in wt.iterdir():
        if entry.name == '.git': continue
        if entry.is_dir(): shutil.rmtree(entry)
        else: entry.unlink()
    # Copy chunks in
    target = wt / 'cache_chunks'
    shutil.copytree(staging / 'cache_chunks', target)
    # Write a README so the branch is self-describing
    (wt / 'README.md').write_text(
        f'# {SNAPSHOT_BRANCH}\n\n'
        f'Cache + results snapshot for the cyclepapa screener.\n'
        f'Reassemble via `python cache_sync.py pull` on the analysis branch.\n\n'
        f'See `cache_chunks/MANIFEST` for snapshot metadata.\n'
    )
    # Incremental commit+push: one chunk per commit, push after each.
    # The proxy rejects pushes >~100MB, so single-commit-all-chunks fails on
    # large caches. Each iteration commits one more chunk and pushes the
    # accumulated branch state, so each push body is bounded by the chunk
    # size (~90 MB). First push uses --force to overwrite the prior snapshot;
    # subsequent pushes are fast-forwards onto our just-pushed HEAD.
    chunk_files = sorted((target).glob('part_*'))
    # Always stage the MANIFEST + README first so the early-commit branch
    # is at least minimally valid if we crash mid-way.
    w(['git', 'add', 'README.md', f'cache_chunks/MANIFEST'])
    msg0 = f'Cache snapshot start {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())} '\
           f'({n_chunks} chunks, {total/1e6:.1f} MB)'
    r = w(['git', '-c', 'user.email=cache-sync@cyclepapa', '-c', 'user.name=cache-sync',
           'commit', '-m', msg0])
    if r.returncode != 0:
        print(f'commit failed: {r.stderr}'); return 3
    # Force-push the empty branch first (removes any prior cache-snapshot)
    r = w(['git', 'push', '--force', 'origin', f'HEAD:{SNAPSHOT_BRANCH}'])
    if r.returncode != 0:
        print(f'initial force-push failed: {r.stderr}\n{r.stdout}'); return 4
    print(f'  -- pushed snapshot scaffold')

    for i, ch in enumerate(chunk_files, 1):
        w(['git', 'add', f'cache_chunks/{ch.name}'])
        cmsg = f'Cache snapshot chunk {i}/{n_chunks}: {ch.name} ({ch.stat().st_size/1e6:.1f} MB)'
        r = w(['git', '-c', 'user.email=cache-sync@cyclepapa', '-c', 'user.name=cache-sync',
               'commit', '-m', cmsg])
        if r.returncode != 0:
            print(f'commit {i} failed: {r.stderr}'); return 3
        # Push (fast-forward) — proxy can handle a single ~90MB chunk
        r = w(['git', 'push', 'origin', f'HEAD:{SNAPSHOT_BRANCH}'])
        if r.returncode != 0:
            print(f'  push of chunk {i} failed: {r.stderr}\n{r.stdout}')
            # Retry with explicit large postBuffer + verbose for diagnostics
            w(['git', 'config', 'http.postBuffer', '209715200'])  # 200MB
            r = w(['git', 'push', 'origin', f'HEAD:{SNAPSHOT_BRANCH}'])
            if r.returncode != 0:
                print(f'  retry failed: {r.stderr}\n{r.stdout}'); return 4
        print(f'  pushed chunk {i}/{n_chunks}: {ch.name}')
    msg = f'Cache snapshot {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())} ({n_chunks} chunks, {total/1e6:.1f} MB)'
    print(f'Pushed to origin/{SNAPSHOT_BRANCH}: {msg}')
    # Cleanup worktree
    _run(['git', 'worktree', 'remove', '--force', str(wt)])
    shutil.rmtree(staging)
    return 0


def pull():
    """Restore latest snapshot from origin/cache-snapshot into working tree."""
    # Fetch the snapshot branch
    r = _run(['git', 'fetch', 'origin', f'{SNAPSHOT_BRANCH}:{SNAPSHOT_BRANCH}'])
    if r.returncode != 0:
        # Maybe branch doesn't exist yet
        if 'couldn\'t find remote ref' in (r.stderr or '').lower() or 'not found' in (r.stderr or '').lower():
            print(f'No snapshot exists yet on origin/{SNAPSHOT_BRANCH}.')
            return 1
        print(f'fetch failed: {r.stderr}'); return 2
    # Add a worktree for the snapshot branch
    wt = REPO / '.snapshot_worktree'
    if wt.exists():
        _run(['git', 'worktree', 'remove', '--force', str(wt)])
    r = _run(['git', 'worktree', 'add', str(wt), SNAPSHOT_BRANCH])
    if r.returncode != 0:
        print(f'worktree add failed: {r.stderr}'); return 3
    chunk_dir = wt / 'cache_chunks'
    if not chunk_dir.exists():
        print('Snapshot branch has no cache_chunks/ — empty snapshot.'); return 4
    # Show manifest
    manifest = chunk_dir / 'MANIFEST'
    if manifest.exists():
        print('Snapshot manifest:'); print('  ' + manifest.read_text().replace('\n', '\n  '))
    # Reassemble + extract
    tar_path = REPO / '.cache_restore.tar.gz'
    _chunks_to_tar(chunk_dir, tar_path)
    print(f'Reassembled {tar_path.stat().st_size/1e6:.1f} MB tarball; extracting...')
    with tarfile.open(tar_path, 'r:gz') as tar:
        tar.extractall(REPO)
    tar_path.unlink()
    _run(['git', 'worktree', 'remove', '--force', str(wt)])
    print('Restore complete.')
    return 0


def status():
    """Report local cache/results state and (if reachable) remote snapshot age."""
    print('=== Local ===')
    yf_dir = REPO / '.cache' / 'yf'
    if yf_dir.exists():
        n_inf = len(list(yf_dir.glob('*__info_metrics.parquet')))
        n_inc = len(list(yf_dir.glob('*__income.parquet')))
        n_prc = len(list(yf_dir.glob('*__price.parquet')))
        sz = sum(p.stat().st_size for p in yf_dir.glob('*')) / 1e6
        print(f'  .cache/yf: {sz:.1f} MB, {n_inf} info_metrics, {n_inc} income, {n_prc} price')
    else:
        print('  .cache/yf: MISSING')
    for p in [Path('results_peg/all.csv'), Path('results_peg/best_undervalued.csv'),
              Path('screener_report.xlsx')]:
        full = REPO / p
        print(f'  {p}: {"OK " + str(full.stat().st_size//1024) + " KB" if full.exists() else "MISSING"}')
    print('=== Remote (origin/cache-snapshot) ===')
    r = _run(['git', 'ls-remote', '--heads', 'origin', SNAPSHOT_BRANCH])
    if r.returncode == 0 and r.stdout.strip():
        print(f'  exists: {r.stdout.strip().split()[0][:12]}')
    else:
        print('  no snapshot yet — run `python cache_sync.py push`')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['push','pull','status'])
    args = ap.parse_args()
    if args.cmd == 'push':   sys.exit(push())
    if args.cmd == 'pull':   sys.exit(pull())
    if args.cmd == 'status': status(); sys.exit(0)


if __name__ == '__main__':
    main()
