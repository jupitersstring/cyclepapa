"""Crash-safe I/O + checkpoint-commit helpers shared by the pipeline and scripts.

Everything durable in this repo (cache/raw JSONs, the parquets, data/raws.tar.gz,
the surprise store, the manifest) was historically written IN PLACE. In an
ephemeral container a kill mid-write is routine, and it could truncate the very
files the durability story depends on — worst of all the raws archive, the ONLY
durable copy of ~hours of rate-limited fetching. These helpers make every such
write write-to-tmp -> ``os.replace`` (atomic on POSIX), and put a shrink guard
in front of the archive so a half-wiped cache can't silently replace a full one.

Tmp names carry the writer's pid so two processes writing the same target (the
long-running fetch scripts overlap with rebuilds) can't stomp each other's
half-written tmp; whichever ``os.replace`` lands last wins with a COMPLETE file.
The ``*.tmp`` suffix keeps strays out of every ``*.json`` / ``*.parquet`` glob.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from . import config


def _tmp(path: Path) -> Path:
    return path.with_name(f"{path.name}.{os.getpid()}.tmp")


def atomic_write_text(path: Path | str, text: str) -> None:
    """``write_text`` via tmp+rename: readers never observe a truncated file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(path)
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_to_parquet(df, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(path)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_copy(src: Path | str, dst: Path | str) -> None:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(dst)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def archive_raws(dest: Path | str | None = None, force: bool = False,
                 shrink_floor: float = 0.9) -> int:
    """Atomically re-archive ``cache/raw/*.json`` -> ``data/raws.tar.gz``.

    Refuses (unless ``force``) to replace an existing archive with one holding
    fewer than ``shrink_floor`` of its members: after a container reset the cache
    is often partially rehydrated, and a checkpoint from that state used to
    overwrite the full durable archive with a fraction of it. A corrupt/unreadable
    existing archive never blocks — replacing it is strictly an improvement.
    Returns the number of raws archived.
    """
    dest = Path(dest or (config.DATA_DIR / "raws.tar.gz"))
    files = sorted(glob.glob(str(config.RAW_CACHE_DIR / "*.json")))
    if dest.exists() and not force:
        try:
            with tarfile.open(dest, "r:gz") as t:
                prev = sum(1 for _ in t)         # streaming member count
        except Exception:
            prev = 0
        if prev and len(files) < shrink_floor * prev:
            raise RuntimeError(
                f"refusing to shrink raws archive: cache has {len(files)} raws vs "
                f"{prev} archived — is the cache fully restored? (force=True overrides)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(dest)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for p in files:
                tar.add(p, arcname=Path(p).name)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return len(files)


# --------------------------------------------------------------------------- #
# Checkpoint commits (the fetch scripts' rollback protection)
# --------------------------------------------------------------------------- #
def _git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], capture_output=True, text=True, cwd=config.REPO_ROOT)


def _branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"


def commit_paths_and_push(msg: str, paths: list[Path | str], retries: int = 4) -> bool:
    """Commit ONLY ``paths`` and push with exponential backoff.

    The commit is pathspec-scoped, so anything a concurrent process (or a human
    mid-edit) has staged is left alone instead of being swept into a checkpoint
    commit. Nothing-to-commit is detected by comparing HEAD shas, not by parsing
    localized git messages. Returns True iff a commit was created.
    """
    strs = [str(p) for p in paths]
    _git("add", "--", *strs)
    before = _git("rev-parse", "HEAD").stdout.strip()
    _git("commit", "-m", msg, "--", *strs)
    if _git("rev-parse", "HEAD").stdout.strip() == before:
        return False
    for i in range(retries):
        if _git("push", "-u", "origin", _branch()).returncode == 0:
            return True
        time.sleep(2 ** (i + 1))
    print("  [warn] push failed (commit is safe locally)", flush=True)
    return True


def archive_and_push(msg: str) -> None:
    """The fetch scripts' shared checkpoint: shrink-guarded atomic re-archive of
    the raws, then a pathspec-scoped commit+push of just the archive. A guard
    refusal warns and skips the checkpoint rather than killing a long fetch loop.
    """
    dest = config.DATA_DIR / "raws.tar.gz"
    try:
        archive_raws(dest)
    except RuntimeError as err:
        print(f"  [warn] checkpoint skipped: {err}", flush=True)
        return
    commit_paths_and_push(msg, [dest])
