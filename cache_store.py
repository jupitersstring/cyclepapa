"""Three-tier filing cache: filesystem -> git archive -> network.

Disk reality forced a redesign: 26GB of cached HTML working copies vs
1.2GB free disk, while git's delta compression holds the same corpus
at ~2.6GB inside .git packs. So:

  Tier 1  .cache/docs/<accession>.html on the filesystem (fast path,
          mostly empty after the great-space-reclamation commit).
  Tier 2  git cat-file against the archive commits listed in
          cache_archive_commits.txt (one hash per line, newest first).
          Those commits are ancestors of the branch head, so the blobs
          are GC-protected and survive any clone of the branch.
  Tier 3  the caller fetches from EDGAR (not handled here).

Writing: cache_html() honours the CACHE_HTML env var -- set CACHE_HTML=0
for large backfills where the disk can't take working copies; events
extracted from the HTML are the durable work product (pipeline.db +
JSON), and the HTML itself can be re-fetched or re-archived in batches.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
CACHE_DIR = ROOT / ".cache" / "docs"
ARCHIVE_FILE = ROOT / "cache_archive_commits.txt"

_archive_commits: list[str] | None = None


def _archives() -> list[str]:
    global _archive_commits
    if _archive_commits is None:
        if ARCHIVE_FILE.exists():
            _archive_commits = [
                h.strip() for h in ARCHIVE_FILE.read_text().splitlines()
                if h.strip()]
        else:
            _archive_commits = []
    return _archive_commits


def read_html(accession: str) -> str | None:
    """Raw filing HTML by accession, or None if not cached anywhere."""
    p = CACHE_DIR / f"{accession}.html"
    if p.exists():
        try:
            return p.read_text(errors="ignore")
        except Exception:
            pass
    rel = f".cache/docs/{accession}.html"
    for commit in _archives():
        try:
            res = subprocess.run(
                ["git", "cat-file", "-p", f"{commit}:{rel}"],
                cwd=ROOT, capture_output=True, timeout=30)
            if res.returncode == 0 and res.stdout:
                return res.stdout.decode("utf-8", errors="ignore")
        except Exception:
            continue
    return None


def cache_html(accession: str, raw: str) -> bool:
    """Persist raw HTML to the filesystem tier unless CACHE_HTML=0.
    Returns True if written."""
    if os.environ.get("CACHE_HTML", "1") == "0":
        return False
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = CACHE_DIR / f"{accession}.html"
        if not p.exists():
            p.write_text(raw, errors="ignore")
        return True
    except Exception:
        return False
