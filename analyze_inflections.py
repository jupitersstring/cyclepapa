"""Post-run analytics for the non-z inflection signals.

Reads results_edgar/*.csv from the latest pipeline run and surfaces:

  1. Sign-flip set: prior_mean_beta <= 0 AND latest_beta > 0
     -- the literal underreaction->appreciation regime change.
  2. Raw beta-delta leaders: highest absolute (recent - prior) mean beta,
     no z-score normalization. Captures names with the biggest
     in-magnitude improvement in responsiveness.
  3. Correlation inflection: corr_delta_raw > 0 AND latest_corr > 0,
     ranked by correlation improvement.
  4. Beta ROC: second-difference style. >0 means responsiveness is
     accelerating upward (the "convexity" check).

Each cut is shown with positive-growth + positive-beta gate applied for
the underreaction->appreciation interpretation; the alternative
("market starting to react sharply to bad news") gets a separate panel
since it's also useful but for short ideas, not long.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


VARIANTS = [
    "eps_return_absolute", "eps_return_vs_spx",
    "eps_sharpe_absolute", "eps_sharpe_vs_spx",
    "composite_return_absolute", "composite_return_vs_spx",
    "composite_sharpe_absolute", "composite_sharpe_vs_spx",
]


def load(results_dir: Path, name: str) -> pd.DataFrame:
    p = results_dir / f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, index_col=0)


def fmt(df: pd.DataFrame, max_rows: int = 25) -> str:
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 40)
    return df.head(max_rows).to_string()


def show_sign_flips(results_dir: Path) -> None:
    """Names where the K-quarter rolling beta went from <=0 to >0.

    This is the literal underreaction->appreciation: the market WASN'T
    responding (prior beta non-positive), and now it IS (latest > 0).
    """
    print("\n" + "=" * 78)
    print("SIGN-FLIP INFLECTION  (prior_mean_beta <= 0  AND  latest_beta > 0)")
    print("=" * 78)
    for v in VARIANTS:
        df = load(results_dir, v)
        if df.empty or "is_regime_flip" not in df.columns:
            continue
        flips = df[df["is_regime_flip"] == True].copy()
        if flips.empty:
            continue
        # For a real underreaction signal we want growth to be positive too.
        flips = flips[flips["latest_growth"] > 0]
        if flips.empty:
            continue
        flips["beta_delta_raw"] = pd.to_numeric(flips["beta_delta_raw"], errors="coerce")
        flips = flips.sort_values("beta_delta_raw", ascending=False)
        cols = ["latest_growth", "prior_mean_beta", "recent_mean_beta",
                "latest_beta", "beta_delta_raw", "latest_corr", "n_quarters"]
        cols = [c for c in cols if c in flips.columns]
        sub = flips[cols].copy()
        for c in cols[:-1]:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").round(3)
        if "n_quarters" in sub.columns:
            sub["n_quarters"] = sub["n_quarters"].astype(int)
        print(f"\n--- {v}   ({len(sub)} names) ---")
        print(fmt(sub, 20))


def show_raw_beta_delta(results_dir: Path) -> None:
    """Top names by raw recent-vs-prior beta improvement (no z normalization).

    Filtered to positive latest_growth and positive latest_beta so we're
    looking at the underreaction->appreciation set, not market punishment.
    """
    print("\n" + "=" * 78)
    print("RAW BETA DELTA (recent_mean - prior_mean), NOT z-scored")
    print("=" * 78)
    for v in VARIANTS:
        df = load(results_dir, v)
        if df.empty or "beta_delta_raw" not in df.columns:
            continue
        ok = df.dropna(subset=["beta_delta_raw"])
        ok = ok[(ok["latest_growth"] > 0) & (ok["latest_beta"] > 0)]
        if ok.empty:
            continue
        ok = ok.copy()
        ok["beta_delta_raw"] = pd.to_numeric(ok["beta_delta_raw"], errors="coerce")
        ok = ok.sort_values("beta_delta_raw", ascending=False)
        cols = ["latest_growth", "prior_mean_beta", "recent_mean_beta",
                "latest_beta", "beta_delta_raw", "latest_corr",
                "inflection_z", "n_quarters"]
        cols = [c for c in cols if c in ok.columns]
        sub = ok[cols].copy()
        for c in cols:
            if c == "n_quarters":
                sub[c] = sub[c].astype(int)
            else:
                sub[c] = pd.to_numeric(sub[c], errors="coerce").round(3)
        print(f"\n--- {v}   (top by raw beta delta) ---")
        print(fmt(sub, 15))


def show_corr_inflection(results_dir: Path) -> None:
    """Correlation ROC inflections.

    A name with rising correlation but flat beta means the relationship
    between fundamental growth changes and price returns has become
    cleaner / less noisy -- the market is "paying attention" in a more
    consistent way, even if magnitude isn't shifting.
    """
    print("\n" + "=" * 78)
    print("CORRELATION INFLECTION  (corr_delta_raw > 0  AND  latest_corr > 0)")
    print("=" * 78)
    for v in VARIANTS:
        df = load(results_dir, v)
        if df.empty or "corr_delta_raw" not in df.columns:
            continue
        ok = df[df["is_corr_inflected"] == True].copy()
        ok = ok[ok["latest_growth"] > 0]
        if ok.empty:
            continue
        ok["corr_delta_raw"] = pd.to_numeric(ok["corr_delta_raw"], errors="coerce")
        ok = ok.sort_values("corr_delta_raw", ascending=False)
        cols = ["latest_growth", "prior_mean_corr", "recent_mean_corr",
                "latest_corr", "corr_delta_raw", "latest_beta", "n_quarters"]
        cols = [c for c in cols if c in ok.columns]
        sub = ok[cols].copy()
        for c in cols:
            if c == "n_quarters":
                sub[c] = sub[c].astype(int)
            else:
                sub[c] = pd.to_numeric(sub[c], errors="coerce").round(3)
        print(f"\n--- {v}   ({len(sub)} qualifying) ---")
        print(fmt(sub, 15))


def show_beta_roc(results_dir: Path) -> None:
    """Names where beta is accelerating (positive second-difference).

    beta_roc = (latest - recent_mean) - (recent_mean - prior_mean)
    Positive => the rate of improvement is itself improving. Catches
    early-stage transitions before the level move is fully apparent.
    """
    print("\n" + "=" * 78)
    print("BETA ROC / ACCELERATION  (second-difference style)")
    print("=" * 78)
    for v in VARIANTS:
        df = load(results_dir, v)
        if df.empty or "beta_roc" not in df.columns:
            continue
        ok = df.dropna(subset=["beta_roc"])
        ok = ok[(ok["latest_growth"] > 0) & (ok["latest_beta"] > 0) & (ok["beta_roc"] > 0)]
        if ok.empty:
            continue
        ok = ok.copy()
        ok["beta_roc"] = pd.to_numeric(ok["beta_roc"], errors="coerce")
        ok = ok.sort_values("beta_roc", ascending=False)
        cols = ["latest_growth", "prior_mean_beta", "recent_mean_beta",
                "latest_beta", "beta_delta_raw", "beta_roc",
                "latest_corr", "n_quarters"]
        cols = [c for c in cols if c in ok.columns]
        sub = ok[cols].copy()
        for c in cols:
            if c == "n_quarters":
                sub[c] = sub[c].astype(int)
            else:
                sub[c] = pd.to_numeric(sub[c], errors="coerce").round(3)
        print(f"\n--- {v}   (top by beta_roc) ---")
        print(fmt(sub, 15))


def show_cross_variant_flips(results_dir: Path) -> None:
    """Count, per ticker, how many of the 8 variants show a sign flip.

    Confirmation across multiple variants is a much stronger signal than a
    single one -- if a name shows sign-flip on EPS-vs-SPX AND composite-vs-
    SPX AND something else, that's three independent windows agreeing.
    """
    print("\n" + "=" * 78)
    print("CROSS-VARIANT SIGN-FLIP CONFIRMATION")
    print("=" * 78)
    rows: dict[str, dict] = {}
    for v in VARIANTS:
        df = load(results_dir, v)
        if df.empty or "is_regime_flip" not in df.columns:
            continue
        for tkr, row in df.iterrows():
            rec = rows.setdefault(tkr, {"n_flip": 0, "growths": [], "betas": [], "deltas": []})
            if bool(row.get("is_regime_flip", False)):
                rec["n_flip"] += 1
            try:
                rec["growths"].append(float(row.get("latest_growth", np.nan)))
                rec["betas"].append(float(row.get("latest_beta", np.nan)))
                rec["deltas"].append(float(row.get("beta_delta_raw", np.nan)))
            except (TypeError, ValueError):
                pass
    if not rows:
        return
    df = pd.DataFrame.from_dict(rows, orient="index")
    df["avg_growth"] = df["growths"].apply(np.nanmean)
    df["avg_beta"] = df["betas"].apply(np.nanmean)
    df["avg_beta_delta"] = df["deltas"].apply(np.nanmean)
    df = df[df["n_flip"] >= 2]
    df = df[df["avg_growth"] > 0]
    df = df.sort_values(["n_flip", "avg_beta_delta"], ascending=[False, False])
    cols = ["n_flip", "avg_growth", "avg_beta", "avg_beta_delta"]
    sub = df[cols].copy()
    for c in cols[1:]:
        sub[c] = sub[c].astype(float).round(3)
    sub["n_flip"] = sub["n_flip"].astype(int)
    print(f"\nNames with sign-flip in >= 2 of 8 variants, growth > 0: {len(sub)}")
    print(fmt(sub, 30))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", type=Path, default=Path("results_edgar"))
    args = p.parse_args(argv)

    if not args.results_dir.exists():
        print(f"results dir not found: {args.results_dir}", file=sys.stderr)
        return 1

    show_sign_flips(args.results_dir)
    show_raw_beta_delta(args.results_dir)
    show_corr_inflection(args.results_dir)
    show_beta_roc(args.results_dir)
    show_cross_variant_flips(args.results_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
