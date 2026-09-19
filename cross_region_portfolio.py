"""Cross-region uncorrelated portfolio from all completed Stars Aligned runs.

Loads every /tmp/stars_aligned_*.csv, picks top N candidates per region by
the best of (daily_rank, weekly_rank, monthly_rank), fetches weekly returns,
and runs max-weight independent set on |corr| > eps to surface a final
uncorrelated portfolio across regions.
"""

import glob
import sys
import warnings

import numpy as np
import pandas as pd

from screen import fetch_ohlc, fetch_fx, currency_for_ticker, usd_close

warnings.filterwarnings("ignore")


def load_all():
    rows = []
    for path in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        region = path.split("stars_aligned_")[-1].replace(".csv", "")
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        df["region"] = region
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def is_native(t: str) -> bool:
    if not isinstance(t, str):
        return False
    if "." not in t:
        return True  # US: no suffix
    suf = "." + t.rsplit(".", 1)[1]
    # US share-class hyphens are fine
    return suf in {
        ".L", ".PA", ".AS", ".BR", ".LS", ".IR", ".MI", ".MC",
        ".SW", ".VI", ".DE", ".ST", ".OL", ".CO", ".HE", ".AT",
    }


def main():
    eps = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    top_per_region = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    big = load_all()
    if big.empty:
        print("No CSVs found.")
        return
    big = big[big["ticker"].apply(is_native)].copy()
    print(f"Loaded {len(big)} rows from {big.region.nunique()} regions "
          f"(after native-exchange filter).", file=sys.stderr)

    # Composite score = max of three TF ranks, exclude Reject in any TF
    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    not_rejected = (
        (big.daily_label != "Reject") |
        (big.weekly_label != "Reject") |
        (big.monthly_label != "Reject")
    )
    big = big[not_rejected].copy()

    # Take top N per region
    pool = (
        big.sort_values("best_rank", ascending=False)
        .groupby("region", as_index=False, group_keys=False)
        .head(top_per_region)
        .sort_values("best_rank", ascending=False)
        .drop_duplicates(subset=["ticker"], keep="first")
    )
    print(f"\nCandidate pool: {len(pool)} unique tickers across "
          f"{pool.region.nunique()} regions", file=sys.stderr)

    tickers = pool["ticker"].tolist()
    daily = fetch_ohlc(tickers, period="24mo",
                       chunk=30, retries=4, pause_between_chunks=2.0)
    # Need each ticker's Close column
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print("No price data returned.")
        return
    have = [t for t in tickers if t in closes.columns]
    print(f"Got Close data for {len(have)} of {len(tickers)}", file=sys.stderr)

    # FX-normalise to USD before correlation
    ccys = {currency_for_ticker(t) for t in have}
    fx = fetch_fx(ccys, period="24mo") if any(c != "USD" for c in ccys) else {}
    usd = pd.DataFrame({t: usd_close(daily, t, fx) for t in have}).dropna(how="all")

    weekly_ret = usd.resample("W-FRI").last().pct_change().dropna(how="all")
    keep = [t for t in weekly_ret.columns if weekly_ret[t].notna().sum() >= 40]
    weekly_ret = weekly_ret[keep]
    if weekly_ret.shape[1] < 2:
        print("Not enough series for correlation.")
        return
    print(f"Weekly returns matrix: {weekly_ret.shape[1]} tickers × "
          f"{len(weekly_ret)} weeks", file=sys.stderr)

    corr = weekly_ret.corr().abs()
    pool = pool.set_index("ticker")
    available = [t for t in pool.index if t in corr.columns]
    chosen = []
    for t in available:
        if all(corr.loc[t, c] <= eps for c in chosen):
            chosen.append(t)
    print(f"\nUncorrelated portfolio (|weekly corr| <= {eps}): {len(chosen)} names\n")

    out = pool.loc[chosen, [
        "region", "best_rank", "daily_rank", "weekly_rank", "monthly_rank",
        "daily_label", "weekly_label", "monthly_label",
        "W_W", "Q_W", "D_W", "DA_W", "R_W",
    ]].sort_values("best_rank", ascending=False)
    print(out.to_string(float_format=lambda x: f"{x:.1f}"))

    # Diagnostics
    if len(chosen) >= 2:
        sub = weekly_ret[chosen]
        cov = sub.cov().values
        eig = np.linalg.eigvalsh(cov)
        n_eff = (np.trace(cov) ** 2) / np.trace(cov @ cov)
        iu = np.triu_indices_from(corr.loc[chosen, chosen].values, k=1)
        vals = corr.loc[chosen, chosen].values
        print("\nDiagnostics:")
        print(f"  mean |corr|: {float(np.mean(vals[iu])):.3f}")
        print(f"  max  |corr|: {float(np.max(vals[iu])):.3f}")
        print(f"  N_eff bets:  {n_eff:.2f} of {len(chosen)} "
              f"({n_eff/len(chosen)*100:.0f}%)")
        print(f"  top eigenvalue share: {float(eig.max()/eig.sum()):.3f}")

    out.to_csv(f"/tmp/cross_region_top_uncorrelated.csv")
    print(f"\nWrote /tmp/cross_region_top_uncorrelated.csv")


if __name__ == "__main__":
    main()
