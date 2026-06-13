"""Sample mentions per (source, ticker) and apply heuristic precision labels.

For each (source, ticker) cell with >= `min_rows` mentions, sample
`sample_per_cell` rows and check whether the new resolver still
attributes them to the original ticker. The ratio is the cell's
estimated precision.

Run before AND after re-resolution to demonstrate the lift.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.config import Config
from social_arb.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-per-cell", dest="sample_per_cell", type=int, default=30)
    parser.add_argument("--min-rows", dest="min_rows", type=int, default=50)
    parser.add_argument("--show-examples", dest="show_examples", type=int, default=2,
                       help="print N failing-example texts per low-precision cell")
    parser.add_argument("--top", type=int, default=30,
                       help="show the top N largest cells")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    cfg = Config()
    pipe = Pipeline.build(cfg)

    with storage.connect(cfg) as con:
        cells = con.execute(f"""
            SELECT source, ticker, COUNT(*) AS n
            FROM mentions
            GROUP BY source, ticker
            HAVING n >= {args.min_rows}
            ORDER BY n DESC
            LIMIT {args.top}
        """).df()

    print(f"sampling {args.sample_per_cell} rows from each of the top "
          f"{len(cells)} (source, ticker) cells\n")

    rows = []
    for _, c in cells.iterrows():
        src, ticker, n = c["source"], c["ticker"], int(c["n"])
        with storage.connect(cfg) as con:
            sample = con.execute(f"""
                SELECT text FROM mentions
                WHERE source = ? AND ticker = ?
                ORDER BY RANDOM()
                LIMIT {args.sample_per_cell}
            """, [src, ticker]).df()
        hits = 0
        failing = []
        for _, r in sample.iterrows():
            text = str(r["text"]) if pd.notna(r["text"]) else ""
            mentions = pipe.resolver.resolve(text)
            if any(m.ticker == ticker for m in mentions):
                hits += 1
            else:
                failing.append(text)
        precision = hits / max(1, len(sample))
        rows.append({
            "source": src,
            "ticker": ticker,
            "n": n,
            "sample": len(sample),
            "precision": round(precision, 3),
        })
        if precision < 0.5 and args.show_examples and failing:
            print(f"\n  LOW PRECISION  {src} / {ticker} -- {precision:.0%} ({hits}/{len(sample)})")
            for ex in failing[: args.show_examples]:
                print(f"    e.g.: {ex[:120]}")

    df = pd.DataFrame(rows).sort_values(["precision", "n"], ascending=[True, False])
    pd.set_option("display.width", 160)
    print()
    print("=== Per-cell precision (lowest first) ===")
    print(df.to_string(index=False))

    # Aggregate.
    overall = df.copy()
    overall["weighted_p"] = overall["precision"] * overall["n"]
    summary = (
        overall.groupby("source")
        .agg(rows=("n", "sum"), weighted_p=("weighted_p", "sum"), n_cells=("ticker", "size"))
        .assign(precision=lambda d: (d["weighted_p"] / d["rows"]).round(3))
        .drop(columns=["weighted_p"])
        .sort_values("precision")
    )
    print()
    print("=== Per-source row-weighted precision ===")
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
