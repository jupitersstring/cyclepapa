"""Per-name research notes loader.

Reads notes/EPIC.md per ticker. The note may contain three labeled
sections (case-insensitive headings):

  ## Thesis
  …prose…

  ## Position
  …prose…

  ## Exit
  …prose…

When present these are surfaced in screen output (top_drivers + a
dedicated notes column) so the screener doubles as a research log.

Use it from the CLI:
  python3 research_notes.py write SEIT.L --thesis "Wind-down at 35% IRR..."
  python3 research_notes.py show SEIT.L
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = HERE / "notes"

_SECTION_RE = re.compile(r"^##\s*(\w+)\s*$", re.MULTILINE | re.IGNORECASE)


def _epic(ticker: str) -> str:
    return ticker.replace(".", "_").upper()


def _path(ticker: str) -> Path:
    return NOTES_DIR / f"{_epic(ticker)}.md"


def load(ticker: str) -> dict:
    """Return {thesis, position, exit, raw} for ticker, all None
    if the note doesn't exist."""
    out = {"thesis": None, "position": None, "exit": None,
           "raw": None}
    p = _path(ticker)
    if not p.exists():
        return out
    try:
        text = p.read_text()
    except Exception:
        return out
    out["raw"] = text
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        section = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if section.startswith("thes"):
            out["thesis"] = body
        elif section.startswith("pos"):
            out["position"] = body
        elif section.startswith("exit"):
            out["exit"] = body
    return out


def write_note(ticker: str, thesis: str | None = None,
               position: str | None = None,
               exit_criteria: str | None = None) -> Path:
    """Write or update a note. If a section is omitted, preserves the
    existing content for that section."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    existing = load(ticker)
    parts = []
    parts.append(f"# {ticker.upper()}\n")
    if thesis or existing.get("thesis"):
        parts.append("## Thesis")
        parts.append(thesis or existing.get("thesis") or "")
    if position or existing.get("position"):
        parts.append("## Position")
        parts.append(position or existing.get("position") or "")
    if exit_criteria or existing.get("exit"):
        parts.append("## Exit")
        parts.append(exit_criteria or existing.get("exit") or "")
    body = "\n\n".join(p for p in parts if p) + "\n"
    p = _path(ticker)
    p.write_text(body)
    return p


def all_notes() -> dict[str, dict]:
    """Return {ticker: load(ticker)} for every note on disk."""
    out = {}
    if not NOTES_DIR.exists():
        return out
    for p in NOTES_DIR.glob("*.md"):
        # Convert filename back to ticker — replace _ with . carefully
        stem = p.stem
        if "_L" in stem:
            ticker = stem.replace("_L", ".L")
        elif "_" in stem and len(stem.split("_")[-1]) <= 4:
            parts = stem.rsplit("_", 1)
            ticker = f"{parts[0]}.{parts[1]}"
        else:
            ticker = stem
        out[ticker] = load(ticker)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    show = sub.add_parser("show")
    show.add_argument("ticker")
    write = sub.add_parser("write")
    write.add_argument("ticker")
    write.add_argument("--thesis", default=None)
    write.add_argument("--position", default=None)
    write.add_argument("--exit", default=None, dest="exit_criteria")
    lst = sub.add_parser("list")
    args = p.parse_args()
    if args.cmd == "show":
        rec = load(args.ticker)
        if not rec["raw"]:
            print(f"No note for {args.ticker}", file=sys.stderr)
            return 1
        print(rec["raw"])
        return 0
    if args.cmd == "write":
        path = write_note(args.ticker, args.thesis, args.position,
                          args.exit_criteria)
        print(f"Wrote {path}", file=sys.stderr)
        return 0
    if args.cmd == "list":
        ns = all_notes()
        print(f"{len(ns)} note(s):", file=sys.stderr)
        for t in sorted(ns):
            n = ns[t]
            head = ""
            if n.get("thesis"):
                head = n["thesis"][:60].replace("\n", " ")
            print(f"  {t:<10}  {head}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
