#!/usr/bin/env python3
"""
audit.py — durability audit.

Designed to fail loudly if this repo is silently developing the
durability hole that destroyed a prior session's work (data files
on disk but excluded from git; unpushed commits sitting only in a
sandbox).

Run via:
    make audit                 # also runs on session start

Exits non-zero on any high-severity finding so it integrates with
hooks and CI.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Paths that MUST be in git (the failure mode being defended against)
REQUIRED_TRACKED_DIRS = ["data", "output", "src"]

# Filename patterns that look like ephemeral / cached state that should
# raise concern if present untracked
SUSPICIOUS_PATTERNS = [
    re.compile(r"\.cache(/|$)"),
    re.compile(r"results.*\.csv$"),
    re.compile(r"universe_.*\.csv$"),
    re.compile(r"screener.*\.xlsx$"),
    re.compile(r"^.*_(cache|tmp|scratch)/"),
    re.compile(r"\.parquet$"),
    re.compile(r"\.sqlite3?$"),
    re.compile(r"\.feather$"),
]

# .gitignore patterns that, if added, would re-create the failure mode
DANGEROUS_GITIGNORE_ENTRIES = [
    re.compile(r"^\s*data/?\s*$"),
    re.compile(r"^\s*output/?\s*$"),
    re.compile(r"^\s*cache/?\s*$"),
    re.compile(r"^\s*\.cache/?\s*$"),
    re.compile(r"^\s*\*\.csv\s*$"),
    re.compile(r"^\s*\*\.yaml\s*$"),
    re.compile(r"^\s*\*\.json\s*$"),
]


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    return r.stdout.strip()


def errors() -> list[tuple[str, str]]:
    """Return list of (severity, message). severity ∈ {ERROR, WARN}."""
    findings: list[tuple[str, str]] = []

    # 1. Remote configured?
    remotes = run(["git", "remote"]).split()
    if "origin" not in remotes:
        findings.append(("ERROR", "no `origin` remote configured — work has nowhere to go"))

    # 2. Unpushed commits on the current branch
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream:
        findings.append(("ERROR", f"branch `{branch}` has no upstream — commits will not be pushed automatically"))
    else:
        ahead = run(["git", "rev-list", "--count", f"{upstream}..HEAD"])
        if ahead and int(ahead) > 0:
            findings.append(("WARN", f"{ahead} unpushed commit(s) on `{branch}` — push before session ends"))

    # 3. Uncommitted changes
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        findings.append(("WARN", f"uncommitted changes present:\n{dirty}"))

    # 4. Required directories all tracked
    for d in REQUIRED_TRACKED_DIRS:
        p = REPO / d
        if not p.exists():
            continue
        # Are there any files under here that are not tracked?
        tracked = set(run(["git", "ls-files", d]).splitlines())
        on_disk = {
            str(f.relative_to(REPO)) for f in p.rglob("*")
            if f.is_file() and "__pycache__" not in str(f) and not str(f).endswith(".pyc")
        }
        untracked = on_disk - tracked
        if untracked:
            findings.append((
                "ERROR",
                f"files in `{d}/` exist on disk but are NOT tracked by git "
                f"(this is the exact failure mode of the prior session):\n  "
                + "\n  ".join(sorted(untracked)[:10])
            ))

    # 5. Dangerous .gitignore additions
    gi = REPO / ".gitignore"
    if gi.exists():
        for line in gi.read_text().splitlines():
            stripped = line.split("#", 1)[0].strip()
            if not stripped:
                continue
            for pat in DANGEROUS_GITIGNORE_ENTRIES:
                if pat.match(stripped):
                    findings.append((
                        "ERROR",
                        f".gitignore contains `{stripped}` — this would silently "
                        "exclude analytical state from git. Remove and ask the "
                        "user before excluding data directories."
                    ))

    # 6. Suspicious untracked patterns anywhere in the working tree
    all_untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines()
    for f in all_untracked:
        for pat in SUSPICIOUS_PATTERNS:
            if pat.search(f):
                findings.append((
                    "ERROR",
                    f"untracked file `{f}` looks like cached analytical state. "
                    "Commit it or move it into the tracked tree."
                ))
                break

    # 7. Code paths that write to suspicious cache-y locations
    suspect_code_patterns = [
        (re.compile(r'open\(["\'](\.|/tmp/)[^"\']*\.cache'), "writes to .cache dir"),
        (re.compile(r'\.to_csv\(["\']\.?/?\.cache/'), "writes CSV to .cache dir"),
        (re.compile(r'pickle\.dump.*["\']\.?/?\.cache/'), "pickles to .cache dir"),
    ]
    for py in (REPO / "src").rglob("*.py"):
        text = py.read_text(errors="ignore")
        for pat, desc in suspect_code_patterns:
            if pat.search(text):
                findings.append((
                    "WARN",
                    f"{py.relative_to(REPO)} {desc} — verify the path is tracked"
                ))

    return findings


def main() -> int:
    findings = errors()
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    print(f"durability audit on `{branch}`:")
    if not findings:
        print("  OK — no issues found.")
        return 0

    n_err = sum(1 for s, _ in findings if s == "ERROR")
    n_warn = sum(1 for s, _ in findings if s == "WARN")

    for severity, msg in findings:
        marker = "  X " if severity == "ERROR" else "  ! "
        for i, line in enumerate(msg.split("\n")):
            print(marker + line if i == 0 else "    " + line)

    print(f"\n{n_err} error(s), {n_warn} warning(s).")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
