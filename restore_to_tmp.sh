#!/bin/bash
# Restore persisted artifacts back into /tmp so existing scripts that read
# from /tmp continue to work after a sandbox reset.
#
# Run this once at the start of a session, or wire it into a SessionStart
# hook in .claude/settings.json.

set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$REPO/data" ]; then
  echo "$REPO/data not found — nothing to restore." >&2
  exit 0
fi

n=0
for dir in stars_aligned psar master picks universe; do
  if [ -d "$REPO/data/$dir" ]; then
    for f in "$REPO/data/$dir"/*; do
      [ -f "$f" ] || continue
      cp -n "$f" "/tmp/$(basename "$f")"
      n=$((n + 1))
    done
  fi
done

# Top-level artifacts (e.g. Excel workbook)
for f in "$REPO/data"/*.csv "$REPO/data"/*.xlsx; do
  [ -f "$f" ] || continue
  cp -n "$f" "/tmp/$(basename "$f")"
  n=$((n + 1))
done

echo "restore_to_tmp: $n artifacts restored into /tmp/" >&2
