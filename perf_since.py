"""Forward performance of the 2026-07-15 'global best' picks through today.

The workbook global_best_full.xlsx was built on prices through 2026-07-15.
This measures how each cut has done SINCE, using live prices fetched now.

For each pick we fetch one 6-month daily series and read two points from the
SAME (consistently back-adjusted) series: the close on/just-before the
selection date, and the latest close. Return = latest/entry - 1 (local ccy).
SPY over the identical window is the benchmark.
"""
import concurrent.futures as cf
import numpy as np
import pandas as pd
from yahoo_fetch import fetch_ohlcv

SEL = pd.Timestamp("2026-07-15")   # workbook / selection date
WB = "global_best_full.xlsx"
CUTS = [
    "True Best full universe",
    "Tradeable 20M+ ADV",
    "Institutional 100M+ ADV",
    "Mega-Liquid 500M+ ADV",
    "Balanced Best 5+cats, not run, liquid",
]


def sheet_lookup():
    xl = pd.ExcelFile(WB)
    m = {}
    for want in CUTS:
        for s in xl.sheet_names:
            if s.replace("$", "").replace("(", "").replace(")", "")[:31].strip() == want[:31].strip():
                m[want] = s
                break
    return m


def load_cut(sheet):
    df = pd.read_excel(WB, sheet_name=sheet)
    df = df[df["Ticker"].notna()].copy()
    df["Ticker"] = df["Ticker"].astype(str)
    return df


def series_return(tkr):
    d = fetch_ohlcv(tkr, "6mo", "1d")
    if d is None or len(d) < 5:
        return None
    c = pd.to_numeric(d["Close"], errors="coerce").dropna()
    entry_slice = c[c.index <= SEL]
    if entry_slice.empty:
        return None
    entry = entry_slice.iloc[-1]
    last = c.iloc[-1]
    if entry <= 0:
        return None
    return {"entry": float(entry), "last": float(last),
            "entry_dt": entry_slice.index[-1], "last_dt": c.index[-1],
            "ret_pct": 100.0 * (last / entry - 1.0)}


def main():
    lk = sheet_lookup()
    cuts = {name: load_cut(sheet) for name, sheet in lk.items()}

    # unique tickers across all cuts + SPY
    tickers = sorted({t for df in cuts.values() for t in df["Ticker"]})
    print(f"Fetching live prices for {len(tickers)} unique picks + SPY ...")
    rets = {}
    with cf.ThreadPoolExecutor(8) as ex:
        fut = {ex.submit(series_return, t): t for t in tickers + ["SPY"]}
        for f in cf.as_completed(fut):
            r = f.result()
            if r:
                rets[fut[f]] = r

    spy = rets.get("SPY")
    spy_ret = spy["ret_pct"] if spy else float("nan")
    win_lo = spy["entry_dt"].date() if spy else SEL.date()
    win_hi = spy["last_dt"].date() if spy else None
    print(f"\nWindow: {win_lo} -> {win_hi}   SPY benchmark: {spy_ret:+.2f}%\n")
    print(f"{'Cut':44s} {'n':>4s} {'mean%':>8s} {'med%':>8s} {'hit%':>6s} "
          f"{'>SPY%':>6s} {'EWport%':>8s} {'best':>8s} {'worst':>8s}")
    print("-" * 108)

    summary = {}
    for name, df in cuts.items():
        r = [(t, rets[t]["ret_pct"]) for t in df["Ticker"] if t in rets]
        if not r:
            continue
        vals = np.array([x[1] for x in r])
        hit = 100.0 * (vals > 0).mean()
        beat = 100.0 * (vals > spy_ret).mean()
        best = max(r, key=lambda x: x[1])
        worst = min(r, key=lambda x: x[1])
        summary[name] = {"df": df, "rets": dict(r), "vals": vals}
        print(f"{name[:44]:44s} {len(r):>4d} {vals.mean():>+8.2f} "
              f"{np.median(vals):>+8.2f} {hit:>5.0f}% {beat:>5.0f}% "
              f"{vals.mean():>+8.2f} {best[1]:>+7.1f} {worst[1]:>+7.1f}")

    # US-only view (local ccy == USD, so directly comparable to SPY, no FX)
    print("\nUS-only (no FX; directly vs SPY):")
    print(f"{'Cut':44s} {'n':>4s} {'mean%':>8s} {'med%':>8s} {'hit%':>6s} {'>SPY%':>6s}")
    print("-" * 80)
    for name, df in cuts.items():
        if "region" not in df.columns:
            continue
        us = df[df["region"] == "US"]
        r = [rets[t]["ret_pct"] for t in us["Ticker"] if t in rets]
        if not r:
            continue
        v = np.array(r)
        print(f"{name[:44]:44s} {len(v):>4d} {v.mean():>+8.2f} {np.median(v):>+8.2f} "
              f"{100*(v>0).mean():>5.0f}% {100*(v>spy_ret).mean():>5.0f}%")

    # Detail: Tradeable cut leaders/laggards
    key = "Tradeable 20M+ ADV"
    if key in summary:
        df = summary[key]["df"].copy()
        df["ret_pct"] = df["Ticker"].map(summary[key]["rets"])
        df = df.dropna(subset=["ret_pct"])
        show = ["Ticker", "name", "region", "last_close", "n_cats_passed", "ret_pct"]
        show = [c for c in show if c in df.columns]
        print(f"\n=== {key}: best 12 since {win_lo} ===")
        print(df.sort_values("ret_pct", ascending=False).head(12)[show].to_string(index=False))
        print(f"\n=== {key}: worst 12 ===")
        print(df.sort_values("ret_pct").head(12)[show].to_string(index=False))
        df.sort_values("ret_pct", ascending=False).to_csv("global_best_perf_since.csv", index=False)
        print("\nWrote global_best_perf_since.csv")


if __name__ == "__main__":
    main()
