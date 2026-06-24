"""Headless runner for the wind-down / NAV-discount setup.

Iterates the curated KNOWN_CANDIDATES list, runs screen_ticker on each,
and prints a ranked table — anything matching the setup (weekly volume
spike near volume-profile POC) is flagged. MFI(18) reported alongside.
"""

from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from nav_discount_finder import KNOWN_CANDIDATES, all_known_candidates, screen_ticker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vol-mult", type=float, default=2.0,
                        help="Volume-spike multiple vs 26w average")
    parser.add_argument("--poc-pct", type=float, default=0.10,
                        help="POC proximity as fraction of POC price")
    parser.add_argument("--profile-weeks", type=int, default=156)
    parser.add_argument("--mfi-period", type=int, default=18)
    parser.add_argument("--groups", nargs="*", default=None,
                        help="Subset of KNOWN_CANDIDATES groups to run")
    parser.add_argument("--tickers", nargs="*", default=None,
                        help="Override list of tickers to screen")
    args = parser.parse_args()

    if args.tickers:
        symbols = [t.upper() if "." in t else f"{t.upper()}.L" for t in args.tickers]
    elif args.groups:
        symbols = []
        for g in args.groups:
            for sym in KNOWN_CANDIDATES.get(g, []):
                if sym not in symbols:
                    symbols.append(sym)
    else:
        symbols = all_known_candidates()

    print(f"Screening {len(symbols)} tickers (vol_mult={args.vol_mult}, "
          f"poc_pct={args.poc_pct}, profile_weeks={args.profile_weeks}, "
          f"mfi={args.mfi_period})", file=sys.stderr)

    rows: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        res = screen_ticker(
            sym,
            profile_weeks=args.profile_weeks,
            vol_spike_mult=args.vol_mult,
            poc_proximity_pct=args.poc_pct,
            mfi_period=args.mfi_period,
        )
        rows.append(res)
        flag = "MATCH" if res.get("setup_match") else ("ERR" if "error" in res else "    ")
        print(f"  [{i:3d}/{len(symbols)}] {sym:<8} {flag}  "
              f"vol_ratio={res.get('vol_ratio')!s:<6.6} "
              f"poc_dist={res.get('poc_distance_pct')!s:<6.6} "
              f"mfi={res.get('mfi')!s:<6.6}",
              file=sys.stderr)
        time.sleep(0.15)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows", file=sys.stderr)
        return 1

    cols = ["ticker", "setup_match", "near_poc", "vol_spike", "mfi_green",
            "last_close", "poc", "poc_distance_pct", "vol_ratio", "mfi", "error"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    matches = df[df["setup_match"] == True].copy() if "setup_match" in df else df.iloc[0:0]
    print("\n=== SETUP MATCHES (volume spike + near POC) ===")
    if matches.empty:
        print("(none)")
    else:
        print(matches.sort_values("vol_ratio", ascending=False).to_string(index=False))

    print("\n=== NEAR-MISS: near POC, no vol spike yet ===")
    near = df[(df.get("near_poc") == True) & (df.get("setup_match") != True)]
    if near.empty:
        print("(none)")
    else:
        print(near.sort_values("vol_ratio", ascending=False).head(15).to_string(index=False))

    print("\n=== NEAR-MISS: volume spike, not yet at POC ===")
    spk = df[(df.get("vol_spike") == True) & (df.get("setup_match") != True)]
    if spk.empty:
        print("(none)")
    else:
        print(spk.sort_values("vol_ratio", ascending=False).head(15).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
