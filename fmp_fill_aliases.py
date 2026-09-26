"""Re-run every FMP engine for the symbols fmp_symbol_resolver.py resolved to an
FMP alias, and replace their rows in each layer's output.

The alias hook in fmp_client makes each engine's per-symbol function fetch the
resolved company's data under the master symbol, so the outputs stay keyed by
the master symbol and every downstream reader is unchanged.

Layers: weekly prices (part file -> consolidate -> Yahoo rows re-merged for
the names FMP still lacks), annual statements, quarterly 3-statement panel,
through-cycle annuals, events, sentiment. Derived layers (fmp_quarterly_ext,
ts_snapshot, base_snapshot) are full recomputes and run after this.
"""
from __future__ import annotations

import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import fmp_client as fc


def _replace_rows(path: str, recs: list, key: str = "symbol", float_format="%.6g") -> None:
    new = pd.DataFrame(recs)
    if not len(new):
        return
    if os.path.exists(path):
        old = pd.read_csv(path, low_memory=False)
        old = old[~old[key].astype(str).isin(set(new[key].astype(str)))]
        new = pd.concat([old, new.reindex(columns=old.columns.union(new.columns, sort=False))], ignore_index=True)
    new.to_csv(path + ".tmp", index=False, float_format=float_format)
    os.replace(path + ".tmp", path)


def main(workers: int = 6) -> None:
    m = pd.read_csv("fmp_symbol_map.csv")
    m = m[m["fmp_symbol"].notna()]
    px_syms = m.loc[m["use_for_prices"] == 1, "symbol"].astype(str).tolist()
    fd_syms = m.loc[m["use_for_fundamentals"] == 1, "symbol"].astype(str).tolist()
    print(f"alias fill: prices {len(px_syms)}, fundamentals {len(fd_syms)}", flush=True)

    # ---- prices ----
    import fmp_prices as fp
    import yahoo_weekly_fill as yw
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(fp.weekly_bars, px_syms))
    frames = [r for r in res if r is not None]
    if frames:
        os.makedirs(fp.PARTS, exist_ok=True)
        part = len(glob.glob(os.path.join(fp.PARTS, "part_*.parquet"))) + 1
        pd.concat(frames, ignore_index=True).to_parquet(os.path.join(fp.PARTS, f"part_{part:05d}.parquet"),
                                                        index=False, compression="zstd")
        st = pd.DataFrame({"symbol": px_syms, "source": "alias",
                           "status": ["ok" if r is not None else "empty" for r in res]})
        st.to_csv(fp.UNIVERSE, mode="a", header=not os.path.exists(fp.UNIVERSE), index=False)
        print(f"  prices: {len(frames)} of {len(px_syms)} fetched; consolidating", flush=True)
        fp.consolidate()
        yw.merge()                                   # Yahoo rows for the names FMP still lacks
    # ---- annual statements ----
    import fmp_statements as fs
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(fs.enrich_symbol, fd_syms))
    _replace_rows(fs.OUT, recs)
    print(f"  statements: {sum(1 for r in recs if len(r) > 2)} with data", flush=True)
    # ---- quarterly panel ----
    import fmp_quarterly as fq
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(fq.enrich_symbol, fd_syms))
    recs = [r for r, _ in out]
    panel = [row for _, rows in out for row in rows]
    _replace_rows(fq.OUT, recs)
    if panel:
        os.makedirs(fq._PANEL_PART_DIR, exist_ok=True)
        pd.DataFrame(panel).to_parquet(os.path.join(fq._PANEL_PART_DIR, "part_alias.parquet"), index=False)
        fq.consolidate_panel()
    print(f"  quarterly: {sum(1 for r in recs if len(r) > 1)} with data, {len(panel)} panel rows", flush=True)
    # ---- through-cycle annuals ----
    import fmp_throughcycle as ft
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(ft.one, fd_syms))
    _replace_rows(ft.OUT, recs)
    # ---- events (need the price panel for reactions) ----
    import fmp_events as fe
    px = pd.read_parquet("fmp_weekly_prices.parquet", columns=["symbol", "week", "close"])
    px = px[px["symbol"].isin(set(fd_syms)) & (px["week"] >= "2017-01-01")]
    px_by = {k: g for k, g in px.groupby("symbol")}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(fe.one, [(s, px_by.get(s), "." not in s) for s in fd_syms]))
    _replace_rows(fe.OUT, [dict((k, r.get(k)) for k in fe.COLS) for r in recs])
    # ---- sentiment ----
    import fmp_sentiment as fsn
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(fsn.enrich_symbol, fd_syms))
    _replace_rows(fsn.OUT, [dict((k, r.get(k)) for k in fsn.COLS) for r in recs])
    print("ALIAS_FILL_DONE", flush=True)


if __name__ == "__main__":
    main()
