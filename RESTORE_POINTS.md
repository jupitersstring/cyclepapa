# Restore points

| Name | Commit | Date | What it is |
|---|---|---|---|
| pre-datastore-2026-09-25 | 96150ce6 | 2026-09-25 | Books, data and code as delivered before the security master / fact store / event store refactor (all three books, ownership, red flags, expectations, survivorship backtest). |

To go back to a restore point without losing later history:

    git checkout 96150ce6 -- .          # restore every file as it was at the checkpoint
    git commit -m "Restore pre-datastore-2026-09-25"

To inspect it without touching the branch:

    git worktree add ../cyclepapa-checkpoint 96150ce6
