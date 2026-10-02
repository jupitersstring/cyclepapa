#!/usr/bin/env bash
# Persistence guard: refuse to consider a pipeline run complete unless
# every data artifact it produced is tracked in git.
#
# Run after every scan / rebuild. Exits non-zero if any *.csv / *.xlsx /
# *.json file outside the ignored patterns is untracked.
#
# Prevents the failure mode of "expensive scrape lived only in the
# sandbox, sandbox was reset, scrape is gone forever."

set -u
cd "$(dirname "$0")"

untracked=$(git ls-files --others --exclude-standard | \
            grep -E '\.(csv|xlsx|json)$' || true)

if [ -n "$untracked" ]; then
    echo "ERROR: the following data files are NOT tracked in git:"
    echo "$untracked" | sed 's/^/  /'
    echo
    echo "If the sandbox is reset, these will be permanently lost."
    echo "Either commit them or add them explicitly to .gitignore."
    exit 1
fi

# Also flag .gitignore changes that would EXCLUDE existing tracked data
# (e.g. someone adds *.csv to .gitignore without thinking).
if git check-ignore -q -- *_yartseva.csv 2>/dev/null; then
    echo "ERROR: yartseva snapshot CSVs are gitignored - this is dangerous."
    exit 1
fi

echo "persistence check OK: all data artifacts are tracked."
