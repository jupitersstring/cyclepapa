"""Join the special-situations fundamentals shortlist onto a momentum_rank CSV.

Usage:
  python3 fundamentals_overlay.py momentum_rank_us-all_20260527.csv

Computes the user's composite per the methodology:
  composite = 0.30 * norm_fcf_yield_rank
            + 0.25 * buyback_yield_rank
            + 0.25 * transience
            + 0.20 * cap_structure_reset

For tickers not present in the momentum CSV, prints them with reason
(not cached / cached but unflagged).
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

FUND_CSV = Path(__file__).with_name("fundamentals_special_situations.csv")

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 240)
pd.set_option("display.float_format", "{:.2f}".format)


def composite_score(fund: pd.DataFrame) -> pd.Series:
    fcf = pd.to_numeric(fund["fcf_yield_pct"], errors="coerce")
    fcf_rank = fcf.rank(pct=True)  # higher fcf = higher rank
    # buyback rank: parse status text. "Suspended"/"None" = 0; active = 1.
    bb_active = (
        fund["buyback_status"].str.contains(r"(?i)prog|yr|bn|active|s/h yield|done", regex=True, na=False)
        & ~fund["buyback_status"].str.contains(r"(?i)suspended|none|^\s*$", regex=True, na=False)
    )
    bb_rank = bb_active.astype(float)
    return (0.30 * fcf_rank.fillna(0)
            + 0.25 * bb_rank
            + 0.25 * fund["transience"].astype(float)
            + 0.20 * fund["cap_reset"].astype(float))


def main():
    fund = pd.read_csv(FUND_CSV)
    fund["composite"] = composite_score(fund)
    fund = fund.sort_values("composite", ascending=False)

    if len(sys.argv) > 1:
        mom = pd.read_csv(sys.argv[1], index_col=0)
        in_csv = fund["Ticker"].isin(mom.index)
        cols = ["name", "sector", "last_close", "td_mtf_composite",
                "td_mtf_net_setup", "td_mtf_net_cd", "td_mtf_net_perfect",
                "rs_rank_max", "mom_3m", "mom_6m", "roque_score",
                "box_length_weeks", "pos_in_box_pct",
                "td_w_buy_setup", "td_w_buy_cd", "td_m_buy_setup", "td_m_buy_cd"]
        cols = [c for c in cols if c in mom.columns]

        print("=== Fundamentals shortlist composite ranking ===")
        print(fund[["Ticker", "tier", "name", "region", "transience", "cap_reset",
                    "fcf_yield_pct", "buyback_status", "composite"]].to_string(index=False))

        if cols:
            print("\n=== Cross-ref against technical scan ===")
            joined = fund.set_index("Ticker").join(
                mom[cols].rename(columns={"name": "scan_name", "sector": "scan_sector"}),
                how="left",
            )
            joined["in_scan"] = joined["last_close"].notna()
            display_cols = ["tier", "region", "composite", "in_scan"] + [
                c if c not in ("name", "sector") else f"scan_{c}" for c in cols
            ]
            display_cols = [c for c in display_cols if c in joined.columns]
            print(joined[display_cols].to_string())
    else:
        print(fund.to_string(index=False))


if __name__ == "__main__":
    main()
