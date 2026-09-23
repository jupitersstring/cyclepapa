"""Empirically test which Minervini measures separate winners from losers.

Approach:
  1. Pick a known panel of ~30 'winners' (highest best_rank, label=C across TFs)
     and ~30 'losers' (low best_rank, weekly_label=Reject).
  2. For each, fetch 36mo daily bars and compute all minervini metrics.
  3. Compute the t-stat / mean-diff for each metric between winners & losers.
  4. Compute the pairwise correlation matrix of metrics to find redundancy.
  5. Report keepers (high signal, low redundancy).

Output:
  /tmp/minervini_metric_eval.csv — per-metric: winner_mean, loser_mean,
    mean_diff, t_stat, redundancy_score.
"""

import sys
import warnings
import glob

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import all_minervini_metrics

warnings.filterwarnings("ignore")


def load_pool():
    dfs = []
    for p in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        df = pd.read_csv(p)
        df["region"] = p.split("stars_aligned_")[-1].replace(".csv", "")
        dfs.append(df)
    big = pd.concat(dfs, ignore_index=True)

    def native(t):
        if "." not in t:
            return True
        return "." + t.rsplit(".", 1)[1] in {
            ".L", ".PA", ".AS", ".BR", ".LS", ".IR", ".MI", ".MC", ".SW", ".VI",
            ".DE", ".ST", ".OL", ".CO", ".HE", ".AT",
            ".T", ".HK", ".SI", ".KS", ".KQ", ".TW", ".NS", ".BO",
            ".SS", ".SZ", ".AX", ".NZ",
        }

    big = big[big.ticker.apply(native)].copy()
    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    return big


def main():
    big = load_pool()
    # Winners: top 30 by best_rank AND not rejected on any TF
    winners = big[(big.daily_label != "Reject") &
                  (big.weekly_label != "Reject") &
                  (big.monthly_label != "Reject")].copy()
    winners = winners.sort_values("best_rank", ascending=False).drop_duplicates("ticker").head(30)

    # Losers: rejected weekly + low best_rank, but still have data
    losers = big[(big.weekly_label == "Reject") & (big.best_rank < 40)].copy()
    losers = losers.sort_values("best_rank").drop_duplicates("ticker").head(30)

    panel = pd.concat([
        winners.assign(group="winner"),
        losers.assign(group="loser"),
    ])
    print(f"Panel: {len(winners)} winners + {len(losers)} losers = {len(panel)}", file=sys.stderr)

    tickers = panel["ticker"].tolist()
    daily = fetch_ohlc(tickers, period="36mo",
                       chunk=30, retries=5, pause_between_chunks=3.0)
    closes = daily.get("Close")
    if closes is None:
        print("no Close column")
        return
    have = [t for t in tickers if t in closes.columns]
    print(f"Fetched data for {len(have)}/{len(tickers)}", file=sys.stderr)

    rows = []
    for i, t in enumerate(have):
        sub = pd.DataFrame({
            "Open":   daily["Open"][t],
            "High":   daily["High"][t],
            "Low":    daily["Low"][t],
            "Close":  daily["Close"][t],
            "Volume": daily["Volume"][t] if "Volume" in daily.columns.get_level_values(0) else np.nan,
        }).dropna(subset=["Close"])
        m = all_minervini_metrics(sub, ticker=t)
        if m:
            m["group"] = panel.loc[panel.ticker == t, "group"].iloc[0]
            rows.append(m)
        if (i + 1) % 10 == 0:
            print(f"  computed {i+1}/{len(have)}", file=sys.stderr)

    df = pd.DataFrame(rows)
    print(f"\nComputed metrics for {len(df)} tickers", file=sys.stderr)

    # Per-metric t-test
    metric_cols = [c for c in df.columns if c not in ("ticker", "group")]
    eval_rows = []
    for c in metric_cols:
        w = df[df.group == "winner"][c].dropna()
        l = df[df.group == "loser"][c].dropna()
        if len(w) < 10 or len(l) < 10:
            continue
        mean_w = float(w.mean()); mean_l = float(l.mean())
        sd_w = float(w.std()); sd_l = float(l.std())
        if sd_w == 0 and sd_l == 0:
            continue
        # Welch's t-stat
        denom = np.sqrt(sd_w**2 / len(w) + sd_l**2 / len(l))
        t = (mean_w - mean_l) / max(1e-9, denom)
        eval_rows.append({
            "metric": c,
            "winner_mean": mean_w,
            "loser_mean": mean_l,
            "mean_diff": mean_w - mean_l,
            "t_stat": float(t),
            "n_winners": len(w),
            "n_losers": len(l),
        })

    edf = pd.DataFrame(eval_rows).sort_values("t_stat", key=lambda x: x.abs(), ascending=False)

    # Pairwise correlations (within winners) to find redundancy
    valid_metrics = [r["metric"] for r in eval_rows]
    corr = df[df.group == "winner"][valid_metrics].corr().abs()

    # For each metric, find max correlation with another metric ranked higher in t_stat
    rank_order = edf["metric"].tolist()
    redundancy = {}
    for i, m in enumerate(rank_order):
        higher = rank_order[:i]
        if not higher:
            redundancy[m] = 0.0
            continue
        max_corr_to_higher = corr.loc[m, higher].max()
        redundancy[m] = float(max_corr_to_higher) if not np.isnan(max_corr_to_higher) else 0.0
    edf["redundancy_with_higher"] = edf["metric"].map(redundancy)

    # Keepers: |t_stat| >= 1.0 AND redundancy < 0.7
    edf["keep"] = (edf["t_stat"].abs() >= 1.0) & (edf["redundancy_with_higher"] < 0.7)

    edf.to_csv("/tmp/minervini_metric_eval.csv", index=False)
    print("\n=== Top 30 by |t_stat| ===")
    print(edf.head(30)[["metric", "winner_mean", "loser_mean", "mean_diff",
                         "t_stat", "redundancy_with_higher", "keep"]]
          .to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    keepers = edf[edf.keep]
    print(f"\n=== {len(keepers)} keepers (|t| >= 1.0, redundancy < 0.7) ===")
    print(keepers[["metric", "winner_mean", "loser_mean", "t_stat",
                    "redundancy_with_higher"]]
          .to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
