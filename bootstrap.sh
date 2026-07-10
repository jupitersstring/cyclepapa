#!/usr/bin/env bash
# SessionStart / on-demand recovery. A fresh sandbox may (a) lack our deps and
# (b) check out a stale ref with an empty working tree. This makes it self-heal:
# sync to the remote branch tip, install the FULL dep set, then rehydrate the
# expensive caches from the git-tracked durable snapshot in data/.
set +e
cd "$(dirname "$0")"

# 1) if the working tree is behind the remote branch tip, fast-forward to it
BR=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -n "$BR" ] && git rev-parse --verify "origin/$BR" >/dev/null 2>&1; then
  git fetch origin "$BR" -q 2>/dev/null
  LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse "origin/$BR")
  if [ "$LOCAL" != "$REMOTE" ] && git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
    git reset --hard "origin/$BR" -q 2>/dev/null
  fi
fi

# 2) install the full dependency set (check EACH import, not just pandas)
python3 - <<'PY' 2>/dev/null || pip install -q pandas numpy pyarrow yfinance financedatabase scikit-learn openpyxl requests lxml beautifulsoup4 2>/dev/null
import pandas, numpy, pyarrow, yfinance, financedatabase, sklearn, openpyxl, requests  # noqa
PY

# 3) rehydrate caches from the durable snapshot
[ -d data/ohlcv ] && python3 persist.py restore || echo "[bootstrap] no data/ snapshot yet"
