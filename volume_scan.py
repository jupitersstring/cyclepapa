"""Batched resume-safe Dormeier volume-leg scan over the full native
universe. Appends to /tmp/volume_rank.csv.

Emits the composite V leg (weekly bars) plus additive weekly+monthly
RVOL volume-spike columns (vspike_w_*, vspike_m_*, vspike_wm) that do NOT
affect the V score. Weekly bars drive V and the weekly spike; monthly bars
are fetched per batch for the monthly spike (best-effort — a monthly miss
leaves those columns blank, it never drops the ticker).

Usage: python volume_scan.py [--fresh]
"""

import os
import sys
import gc
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from mtf_psar_rank import load_universe, is_native, fetch_interval_bulk
from volume_leg import volume_breakout, volume_spike

warnings.filterwarnings("ignore")

OUT = "/tmp/volume_rank.csv"
BATCH = 1500


def main():
    if "--fresh" in sys.argv and os.path.exists(OUT):
        os.remove(OUT)

    big = load_universe(include_rejected=True)
    big = big[big.ticker.apply(is_native)].drop_duplicates(subset=["ticker"])
    meta = big[["ticker", "region"]]
    tickers = big.ticker.astype(str).tolist()
    print(f"Universe: {len(tickers)}", file=sys.stderr)

    done = set()
    if os.path.exists(OUT):
        done = set(pd.read_csv(OUT, usecols=["ticker"]).ticker)
        print(f"Resume: {len(done)} done", file=sys.stderr)
    todo = [t for t in tickers if t not in done]
    print(f"To scan: {len(todo)}", file=sys.stderr)
    if not todo:
        print("Nothing to scan.")
        return

    # Fast-fail probe (rate-limit detection)
    probe = fetch_interval_bulk(todo[:40], "1wk", include_volume=True)
    if len(probe) < 8:
        print(f"ABORT: probe {len(probe)}/40 — rate limited", file=sys.stderr)
        sys.exit(2)

    n_batches = (len(todo) + BATCH - 1) // BATCH
    for b in range(n_batches):
        batch = todo[b * BATCH:(b + 1) * BATCH]
        print(f"--- batch {b+1}/{n_batches} ({len(batch)}) ---", file=sys.stderr)
        weekly = fetch_interval_bulk(batch, "1wk", include_volume=True)
        if len(weekly) < len(batch) * 0.2:
            print("ABORT: batch fetch rate-limited; exit 2", file=sys.stderr)
            sys.exit(2)
        # Monthly bars power the monthly spike columns; best-effort (a monthly
        # miss just leaves that ticker's monthly spike blank, never drops it).
        monthly = fetch_interval_bulk(batch, "1mo", include_volume=True)
        rows = []
        rej = {"no_fetch": 0, "no_volume": 0, "leg_gate": 0, "exception": 0}
        for t in batch:
            try:
                w = weekly.get(t)
                if w is None:
                    rej["no_fetch"] += 1
                    continue
                # fetch_interval_bulk returns OHLC only if Volume absent from
                # its column set; ensure Volume present
                if "Volume" not in w.columns:
                    rej["no_volume"] += 1
                    continue
                r = volume_breakout(w)
                if not r:
                    rej["leg_gate"] += 1   # <30 weekly bars / no volume / tot_w==0
                    continue
                # --- volume-spike columns (additive; do not affect V) ---
                sw = volume_spike(w, freq="W", lookback=20)
                m = monthly.get(t)
                sm = volume_spike(m, freq="M", lookback=12) if m is not None \
                    and "Volume" in getattr(m, "columns", []) else {}
                r["vspike_w_rvol"] = sw.get("rvol", np.nan)
                r["vspike_w_tier"] = sw.get("tier", 0)
                r["vspike_w_up"] = sw.get("up", np.nan)
                r["vspike_m_rvol"] = sm.get("rvol", np.nan)
                r["vspike_m_tier"] = sm.get("tier", 0)
                r["vspike_m_up"] = sm.get("up", np.nan)
                # Both timeframes spiking (>=2x) on accumulation = strongest signal
                r["vspike_wm"] = bool(sw.get("tier", 0) >= 2 and sm.get("tier", 0) >= 2
                                      and sw.get("up") and sm.get("up"))
                r["ticker"] = t
                rows.append(r)
            except Exception:
                rej["exception"] += 1
                continue
        if rows:
            out = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
            out.to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            print(f"  appended {len(out)} -> {OUT}", file=sys.stderr)
        if sum(rej.values()):
            print(f"  rejected {sum(rej.values())}/{len(batch)}: {rej}", file=sys.stderr)
        del weekly, monthly
        gc.collect()

    print(f"Volume scan complete -> {OUT}")


if __name__ == "__main__":
    main()
