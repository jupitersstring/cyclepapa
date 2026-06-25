"""Run the full post-gap-closure pipeline in one go.

Sequence:
  1. Broader Form 4 scan (more tickers)
  2. 8-K catalysts ingest
  3. Fundamentals enrichment (P/E, FCF, debt)
  4. Re-run unified_score with all new data
  5. Re-render both workbooks
  6. Snapshot
"""
import os, subprocess, sys, time

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_step(cmd, label):
    print(f"\n{'='*70}")
    print(f"STEP: {label}")
    print(f"  $ {' '.join(cmd)}")
    print('='*70, flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=os.path.dirname(PIPELINE_DIR))
    dt = time.time() - t0
    print(f"  [{label} done in {dt:.0f}s, exit={result.returncode}]")
    return result.returncode == 0

def run():
    steps = [
        (["python3", "pipeline/scan_insider_batch.py"], "Form 4 batch scan (expanded)"),
        (["python3", "pipeline/ingest_8k.py", "600"], "8-K ingest"),
        (["python3", "pipeline/unified_score.py"], "Re-run unified_score"),
        (["python3", "pipeline/render_universe_sheet.py"], "Render universe workbook"),
        (["python3", "pipeline/render_style_workbook.py"], "Render style workbook"),
        (["python3", "pipeline/snapshot.py", "dump"], "Snapshot to CSV"),
    ]
    for cmd, label in steps:
        ok = run_step(cmd, label)
        if not ok:
            print(f"FAILED at {label}; continuing anyway.")

    print(f"\n{'='*70}")
    print("post_gap_pipeline COMPLETE")
    print('='*70)

if __name__ == "__main__":
    run()
