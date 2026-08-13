# PSU engine snapshot (cross-feed)

Read-only snapshot of the 31-layer PSU/governance engine outputs from
branch `claude/discretionary-insider-conviction`, used by
`src/build_workbook.py` to annotate the risk-reward workbook.

- `full_universe_consensus.csv` — per-ticker layer points + consensus
  meta-ranking (n_layers_firing, consensus_score) over 6,166 US names.
- `discretionary_insider_conviction.json` — discretionary open-market
  insider-buying clusters (Form 4 code P only, role-weighted,
  dollar-gated).

Refresh by copying the regenerated files from that branch; the workbook
builder degrades gracefully when these files are absent.

Snapshot taken: 2026-08-13 (pipeline run of the same date).
