#!/usr/bin/env python3
"""
run_pollers.py — fault-isolated poller orchestrator.

The `make refresh` chain runs ~20 pollers. Previously they were make
prerequisites, so ANY single failure (a schema change, a dead endpoint,
a bad record) aborted the entire chain and nothing downstream ran —
exactly what happened when a list-typed name field crashed inbox_promote.

This orchestrator runs each poller in its OWN subprocess with a timeout.
A poller that crashes, times out, or exits non-zero is logged and the
run CONTINUES to the next one. The pipeline degrades gracefully: a
broken source costs you that source's records, not the whole refresh.

Emits a run report (output/poller_run.md) and always exits 0 so the
downstream promote → screen → rank → workbook steps still execute on
whatever records the healthy pollers produced.

Usage:
    python -m src.run_pollers                  # run all pollers
    python -m src.run_pollers --only sc13d_poll,form15_poll
    python -m src.run_pollers --timeout 300
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORT = REPO / "output" / "poller_run.md"

# (module, args). Ordered roughly by geography then US-federal then
# derived. Each entry runs isolated; failure of one does not stop others.
POLLERS: list[tuple[str, list[str]]] = [
    ("src.edgar_poll",         []),
    ("src.uk_rns_poll",        ["--days-back", "1"]),
    ("src.sedarplus_poll",     []),
    ("src.jpx_tdnet_poll",     []),
    ("src.pacer_poll",         ["--days-back", "1"]),
    ("src.cvm_poll",           ["--days-back", "1"]),
    ("src.asx_poll",           ["--days-back", "1"]),
    ("src.sc13d_poll",         []),
    ("src.form15_poll",        []),
    ("src.cluster_sells",      ["--days-back", "60"]),
    ("src.ofac_poll",          ["--pages", "4"]),
    ("src.lobbying_poll",      ["--days-back", "7"]),
    ("src.credit_spread_poll", []),
    ("src.thirteenf_poll",     ["--min-value-usd", "10000000"]),
    ("src.postreorg_poll",     ["--days-back", "90"]),
    ("src.eightk_items_poll",  ["--days-back", "1"]),
    ("src.edgar_forms_poll",   ["--count", "100"]),
    ("src.hkex_poll",          ["--days-back", "30"]),
    ("src.sgx_poll",           []),
    ("src.euronext_poll",      ["--days-back", "30"]),
    ("src.jse_poll",           []),
    ("src.distressed_13d_poll", ["--days-back", "730"]),
    ("src.pacer_emergence_poll", ["--days-back", "120"]),
    ("src.going_concern_poll",  ["--days-back", "120"]),
    ("src.spinoff_radar",      []),
    ("src.cluster_buys",       []),
]

# Records-written pattern is poller-specific; we just capture the exit
# status + duration + tail of stdout for the report.


def run_one(module: str, args: list[str], timeout: int) -> dict:
    start = time.monotonic()
    cmd = [sys.executable, "-m", module, *args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True,
            timeout=timeout)
        dur = time.monotonic() - start
        tail = (proc.stdout or "").strip().splitlines()[-3:]
        # Extract a "Done. N records" style count if present
        n = ""
        for line in reversed((proc.stdout or "").splitlines()):
            low = line.lower()
            if "done." in low or "wrote" in low or "records" in low:
                n = line.strip()
                break
        return {
            "module": module,
            "status": "ok" if proc.returncode == 0 else "FAIL",
            "returncode": proc.returncode,
            "duration_s": round(dur, 1),
            "summary": n[:100],
            "stderr_tail": (proc.stderr or "").strip().splitlines()[-2:],
        }
    except subprocess.TimeoutExpired:
        return {"module": module, "status": "TIMEOUT",
                "returncode": None, "duration_s": timeout,
                "summary": f"exceeded {timeout}s", "stderr_tail": []}
    except Exception as exc:  # never let the orchestrator itself die
        return {"module": module, "status": "ERROR",
                "returncode": None,
                "duration_s": round(time.monotonic() - start, 1),
                "summary": f"{type(exc).__name__}: {exc}"[:100],
                "stderr_tail": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=int, default=600,
                    help="Per-poller timeout in seconds (default 600)")
    ap.add_argument("--only", type=str, default="",
                    help="Comma-separated module short-names to run "
                         "(e.g. sc13d_poll,form15_poll)")
    args = ap.parse_args()

    selected = POLLERS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        selected = [(m, a) for (m, a) in POLLERS
                    if m.split(".")[-1] in wanted]

    print(f"Running {len(selected)} pollers "
          f"(fault-isolated, per-poller timeout {args.timeout}s)...\n")
    results = []
    for module, pargs in selected:
        short = module.split(".")[-1]
        print(f"  ▶ {short} ...", flush=True)
        res = run_one(module, pargs, args.timeout)
        results.append(res)
        icon = {"ok": "✓", "FAIL": "✗", "TIMEOUT": "⏱", "ERROR": "✗"}.get(
            res["status"], "?")
        print(f"    {icon} {res['status']:8s} {res['duration_s']:>6.1f}s  "
              f"{res['summary']}", flush=True)
        if res["status"] != "ok" and res["stderr_tail"]:
            for l in res["stderr_tail"]:
                print(f"        {l[:100]}", flush=True)

    ok = sum(1 for r in results if r["status"] == "ok")
    bad = len(results) - ok
    print(f"\n{ok} ok / {bad} failed of {len(results)} pollers.")

    # Report
    lines = [
        f"# Poller run report ({datetime.utcnow().isoformat()}Z)",
        "",
        f"- {ok} ok / {bad} failed of {len(results)} pollers",
        "- Fault-isolated: a failing poller does not stop the refresh chain.",
        "",
        "| Poller | Status | Duration | Summary |",
        "|---|---|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['module'].split('.')[-1]} | {r['status']} | "
            f"{r['duration_s']}s | {r['summary'][:60]} |")
    if bad:
        lines += ["", "## Failures", ""]
        for r in results:
            if r["status"] != "ok":
                lines.append(f"### {r['module']}  ({r['status']})")
                lines.append(f"- {r['summary']}")
                for l in r["stderr_tail"]:
                    lines.append(f"  - `{l[:120]}`")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {REPORT}")

    # Always exit 0 — downstream promote/screen/workbook must still run
    # on whatever the healthy pollers produced.
    return 0


if __name__ == "__main__":
    sys.exit(main())
