"""Print the top 'Play Now' picks across the entire augmented universe.

Reads /tmp/stars_aligned_*.csv (which after augment_all.py contain M, E,
DSR, ADV_play_now, adv_to_mcap, adv_20). Combines them into a composite
"play now" score and reports:
  - Top 30 globally
  - Top 20 institutional-grade (>= $20M ADV, >= 0.5% turnover)
  - Top 20 small-cap flow (>= 1% turnover, regardless of raw ADV)
  - Per-region top 5
"""

import sys
import glob
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


NATIVE_SUFFIXES = {
    ".L", ".PA", ".AS", ".BR", ".LS", ".IR", ".MI", ".MC", ".SW", ".VI",
    ".DE", ".ST", ".OL", ".CO", ".HE", ".AT",
    ".T", ".JP", ".HK", ".SI", ".KS", ".KQ", ".TW", ".NS", ".BO",
    ".SS", ".SZ", ".AX", ".NZ",
}


def is_native(t: str) -> bool:
    if not isinstance(t, str):
        return False
    if "." not in t:
        return True
    suf = "." + t.rsplit(".", 1)[1]
    return suf in NATIVE_SUFFIXES


def load_all() -> pd.DataFrame:
    rows = []
    for p in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        region = p.split("stars_aligned_")[-1].replace(".csv", "")
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        df["region"] = region
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main():
    big = load_all()
    if big.empty:
        print("No CSVs found.")
        return
    big = big[big.ticker.apply(is_native)].copy()

    for col in ["E", "M", "DSR", "ADV_play_now"]:
        if col not in big.columns:
            print(f"Missing column: {col} — augment_all.py needs to finish first.")
            return

    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    big["dsr_norm"]  = big["DSR"].fillna(50)

    not_rejected = (
        (big.daily_label != "Reject") |
        (big.weekly_label != "Reject") |
        (big.monthly_label != "Reject")
    )
    base = big[not_rejected].copy()

    base["play_now_score"] = (
        0.30 * base.E.fillna(0) +
        0.20 * base.M.fillna(0) +
        0.15 * base.ADV_play_now.fillna(0) +
        0.15 * base.dsr_norm +
        0.20 * base.best_rank
    )

    cols_show = ["ticker", "region", "play_now_score",
                 "best_rank", "weekly_label",
                 "E", "M", "DSR", "ADV_play_now",
                 "adv_20", "adv_to_mcap"]
    cols_show = [c for c in cols_show if c in base.columns]

    # 1. Top 30 universal
    # E>=35 puts us in the top ~15% of entry-trigger scores (true 50+ is only
    # 5% — too rare for a watchlist).
    gated = base[
        (base.weekly_label != "Reject") &
        (base.E.fillna(0) >= 35) &
        (base.M.fillna(0) >= 55) &
        (base.ADV_play_now.fillna(0) >= 40) &
        (base.best_rank > 55)
    ].copy()
    top = gated.sort_values("play_now_score", ascending=False).drop_duplicates("ticker").head(30)
    print(f"\n=== TOP 30 PLAY-NOW (universal) — n_pool={len(gated)} ===")
    if top.empty:
        print("(no rows pass the gates)")
    else:
        print(top[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # 2. Institutional-grade
    if "adv_20" in gated.columns:
        inst = gated[gated.adv_20.fillna(0) >= 20e6]
        if "adv_to_mcap" in inst.columns:
            inst = inst[inst.adv_to_mcap.fillna(0) >= 0.005]
        inst = inst.sort_values("play_now_score", ascending=False).drop_duplicates("ticker").head(20)
        print(f"\n=== INSTITUTIONAL-GRADE (>= $20M ADV & >= 0.5% turnover) — n={len(inst)} ===")
        if inst.empty:
            print("(no rows)")
        else:
            print(inst[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # 3. Small-cap flow profile (high turnover regardless of raw ADV)
    if "adv_to_mcap" in gated.columns:
        sc = gated[gated.adv_to_mcap.fillna(0) >= 0.01]
        sc = sc.sort_values("play_now_score", ascending=False).drop_duplicates("ticker").head(20)
        print(f"\n=== SMALL-CAP FLOW (>= 1% daily turnover) — n={len(sc)} ===")
        if sc.empty:
            print("(no rows)")
        else:
            print(sc[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # 4. Per-region top 5
    print("\n=== PER-REGION TOP 5 ===")
    for region in sorted(gated.region.unique()):
        sub = gated[gated.region == region].sort_values("play_now_score", ascending=False).head(5)
        if sub.empty:
            continue
        print(f"\n-- {region} --")
        print(sub[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))


if __name__ == "__main__":
    main()
