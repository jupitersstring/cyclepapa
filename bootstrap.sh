#!/usr/bin/env bash
# Runs on SessionStart (fresh sandbox) and on demand: ensure deps + rehydrate the
# expensive caches from the git-tracked durable snapshot in data/.
set -e
cd "$(dirname "$0")"
python3 -c "import pandas, pyarrow, numpy" 2>/dev/null || \
  pip install -q pandas pyarrow numpy yfinance financedatabase scikit-learn 2>/dev/null || true
if [ -d data/ohlcv ]; then
  python3 persist.py restore || true
else
  echo "[bootstrap] no data/ snapshot yet"
fi
