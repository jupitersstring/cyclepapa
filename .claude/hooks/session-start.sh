#!/bin/bash
# Recreate the Python venv used by the FIP screener on each session start.
# The VM wipes /tmp between sessions, so we need to rebuild the venv every
# time. Idempotent: if the venv already has the packages installed, the
# pip install is a fast no-op.
set -euo pipefail

# Only run in Claude Code on the web — local users have their own venv setup.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

VENV_DIR=/tmp/venv

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check \
  financedatabase yfinance pandas numpy

# Sanity check the installs succeeded.
"$VENV_DIR/bin/python" -c "import financedatabase, yfinance, pandas, numpy" \
  >/dev/null 2>&1 || {
    echo "session-start: package import check failed" >&2
    exit 1
  }
