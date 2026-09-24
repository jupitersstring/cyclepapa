"""Backfill forensic trajectory fields onto an existing scored.parquet.

A fast path: rather than re-running the whole metrics pipeline over every cached
ticker, read each raw's annual block and attach only the columns produced by
``metrics.forensic_block``. Use after upgrading the toolkit so existing caches
gain the forensic fields without a full re-fetch/re-analyze.

    PYTHONPATH=. python scripts/add_forensic_fields.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from earnings_model import config, metrics

_FIELDS = ["rev_up_frac", "ebitda_margin", "margin_delta3",
           "ebitda_all_pos", "ebitda_lump", "rev_cagr_n"]


def main() -> None:
    scored_path = config.CACHE_DIR / "scored.parquet"
    df = pd.read_parquet(scored_path)
    rows = []
    for sym in df["symbol"]:
        p = config.RAW_CACHE_DIR / f"{str(sym).replace('/', '_')}.json"
        block = {f: None for f in _FIELDS}
        if p.exists():
            try:
                annual = json.loads(p.read_text()).get("annual", {}) or {}
                block = {k: v for k, v in metrics.forensic_block(annual).items()}
            except (json.JSONDecodeError, OSError):
                pass
        block["symbol"] = sym
        rows.append(block)
    add = pd.DataFrame(rows)
    df = df.drop(columns=[c for c in _FIELDS if c in df.columns], errors="ignore")
    df = df.merge(add, on="symbol", how="left")
    df.to_parquet(scored_path, index=False)
    present = [c for c in _FIELDS if c in df.columns]
    n_pass = int((df["ebitda_all_pos"].fillna(False).astype(bool)
                  & (df["margin_delta3"].fillna(-1) > 0)).sum())
    print(f"added {present} to {scored_path} ({len(df)} rows; {n_pass} margin-expanding)")


if __name__ == "__main__":
    main()
