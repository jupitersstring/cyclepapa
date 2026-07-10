# Poller run report (2026-07-10T15:41:26.371817Z)

- 2 ok / 1 failed of 3 pollers
- Fault-isolated: a failing poller does not stop the refresh chain.

| Poller | Status | Duration | Summary |
|---|---|---:|---|
| sc13d_poll | ok | 5.0s | Done. 2 records. |
| nonexistent_module | FAIL | 0.0s |  |
| form15_poll | ok | 6.2s | Done. 3 records. |

## Failures

### src.nonexistent_module  (FAIL)
- 
  - `/usr/local/bin/python3: No module named src.nonexistent_module`
