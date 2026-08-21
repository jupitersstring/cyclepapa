"""What worked among the 2026-07-15 global-best picks, 07-15 -> latest close.

Joins each pick's forward return to its selection-time attributes and
cross-tabulates: by sector, region, momentum/RS/extension bucket, and by
individual setup flag (mean return when the flag was on vs off). Universe =
union of the liquid cuts (Tradeable / Institutional / Balanced).
"""
import concurrent.futures as cf
import numpy as np
import pandas as pd
from yahoo_fetch import fetch_ohlcv

SEL = pd.Timestamp("2026-07-15")
WB = "global_best_full.xlsx"
CONS = "global_equities_consolidated.csv"
LIQUID_SHEETS = ["Tradeable 20M+ ADV", "Institutional 100M+ ADV",
                 "Balanced Best 5+cats, not run, "]
FLAGS = ["darvas2_breakout", "mv_power_trend", "mv_high_tight_flag", "vol_drying",
         "base_ready", "q_method_pass", "extended_w", "mv_at_ath",
         "td_bullish_exhaustion", "breakout_squeeze", "mv_vcp_with_volume",
         "mv_buyable_gap_up", "harmonic_bullish_w_or_m"]
EU = {"de-all","fr-all","ch-all","it-all","es-all","nl-all","se-all","be-all","no-all",
      "dk-all","fi-all","ie-all","pt-all","at-all","gr-all","eu-smid","eu-large",
      "eu-micro","eu-nano"}
ASIA = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all","id-all",
        "th-all","my-all","ph-all","vn-all"}


def region(u):
    if u in EU: return "EU"
    if u in ASIA: return "ASIA"
    if u in {"us-all"} or str(u).startswith("wiki"): return "US"
    if u in {"gb-all","uk-all"}: return "UK"
    if u in {"ca-all"}: return "CA"
    if u in {"au-all","nz-all"}: return "OCEANIA"
    return "OTHER"


def ret(tkr):
    d = fetch_ohlcv(tkr, "6mo", "1d")
    if d is None or len(d) < 5: return None
    c = pd.to_numeric(d["Close"], errors="coerce").dropna()
    pre = c[c.index <= SEL]
    if pre.empty or pre.iloc[-1] <= 0: return None
    return 100.0 * (c.iloc[-1] / pre.iloc[-1] - 1.0)


def bucket(s, edges, labels):
    return pd.cut(s, bins=edges, labels=labels)


def tab(df, by, col="ret"):
    g = df.groupby(by, observed=True)[col]
    out = pd.DataFrame({"n": g.size(), "mean%": g.mean().round(2),
                        "median%": g.median().round(2),
                        "hit%": (g.apply(lambda x: 100*(x > 0).mean())).round(0)})
    return out


def main():
    xl = pd.ExcelFile(WB)
    sm = {s.replace("$","").replace("(","").replace(")","")[:31].strip(): s
          for s in xl.sheet_names}
    tickers = set()
    for want in LIQUID_SHEETS:
        s = sm.get(want.strip()[:31].strip())
        if s:
            tickers |= set(pd.read_excel(WB, sheet_name=s)["Ticker"].dropna().astype(str))
    tickers = sorted(tickers)
    print(f"Union of liquid cuts: {len(tickers)} unique picks\n")

    rets = {}
    with cf.ThreadPoolExecutor(8) as ex:
        fut = {ex.submit(ret, t): t for t in tickers + ["SPY"]}
        for f in cf.as_completed(fut):
            r = f.result()
            if r is not None: rets[fut[f]] = r
    spy = rets.pop("SPY", float("nan"))

    cons = pd.read_csv(CONS, index_col=0, low_memory=False)
    cons = cons[~cons.index.duplicated(keep="first")]
    rows = []
    for t in tickers:
        if t not in rets or t not in cons.index: continue
        r = cons.loc[t]
        rows.append({"ticker": t, "ret": rets[t], "sector": r.get("sector"),
                     "region": region(r.get("_universe")),
                     "mom_6m": pd.to_numeric(r.get("mom_6m"), errors="coerce"),
                     "rs": pd.to_numeric(r.get("rs_rank_max"), errors="coerce"),
                     "dist_ath": pd.to_numeric(r.get("mv_dist_from_ath_pct"), errors="coerce"),
                     **{fl: str(r.get(fl)).lower() in ("true","1","yes") for fl in FLAGS}})
    df = pd.DataFrame(rows)
    print(f"Analyzable: {len(df)} picks   |   SPY benchmark: {spy:+.2f}%")
    print(f"Overall picks: mean {df['ret'].mean():+.2f}%  median {df['ret'].median():+.2f}%  "
          f"hit {100*(df['ret']>0).mean():.0f}%\n")

    print("="*64, "\nBY SECTOR (>=4 names)\n"+"="*64)
    t = tab(df, "sector"); print(t[t["n"] >= 4].sort_values("mean%", ascending=False).to_string())

    print("\n"+"="*64, "\nBY REGION\n"+"="*64)
    print(tab(df, "region").sort_values("mean%", ascending=False).to_string())

    print("\n"+"="*64, "\nBY 6-MONTH MOMENTUM AT SELECTION\n"+"="*64)
    df["mom_bkt"] = bucket(df["mom_6m"], [0,1.0,1.1,1.2,1.5,99],
                           ["<0%","0-10%","10-20%","20-50%",">50%"])
    print(tab(df, "mom_bkt").to_string())

    print("\n"+"="*64, "\nBY RS-RANK (lower=stronger)\n"+"="*64)
    df["rs_bkt"] = bucket(df["rs"], [0,30,50,70,85,101],
                          ["top(<=30)","30-50","50-70","70-85","laggard(>85)"])
    print(tab(df, "rs_bkt").to_string())

    print("\n"+"="*64, "\nBY DISTANCE FROM ATH\n"+"="*64)
    df["ath_bkt"] = bucket(df["dist_ath"], [-1,3,10,20,100],
                           ["at ATH(<3%)","3-10%","10-20%",">20% below"])
    print(tab(df, "ath_bkt").to_string())

    print("\n"+"="*64, "\nBY SETUP FLAG (mean return: flag ON vs OFF)\n"+"="*64)
    print(f"{'flag':26s} {'nON':>4s} {'ON%':>8s} {'nOFF':>5s} {'OFF%':>8s} {'edge':>8s}")
    fr = []
    for fl in FLAGS:
        on, off = df[df[fl]]["ret"], df[~df[fl]]["ret"]
        if len(on) >= 4:
            fr.append((fl, len(on), on.mean(), len(off), off.mean(), on.mean()-off.mean()))
    for fl, n1, m1, n0, m0, e in sorted(fr, key=lambda x: -x[5]):
        print(f"{fl:26s} {n1:>4d} {m1:>+8.2f} {n0:>5d} {m0:>+8.2f} {e:>+8.2f}")


if __name__ == "__main__":
    main()
