"""
Cross-System Asymmetry Ranker
==============================

Loads all scanner CSVs from results/, computes a unified "ultimate
asymmetry" score that blends every signal system, and outputs a single
ranked list of the best opportunities across all universes and timeframes.

Ultimate Asymmetry = f(R:R, risk tightness, signal confluence, quality)

The idea: a stock is maximally asymmetric when ALL systems agree:
  - Ord says selling dried up (OV shrinkage, shakeout)
  - Dalton says the bracket is about to break (massive score, near edge)
  - Squeeze says volatility is loaded (in squeeze, low BW)
  - RS says relative outperformance is starting (rel_brk, rs_13hi)
  - Qullamaggie says the base is tight and compressed
  - Risk/reward is excellent (high R:R, low risk_pct)
  - Regime strength says it works in all conditions (all_weather)
  - MOM says accumulation is hidden (hidden_bull, MIRAGE_BUY)

Usage:
  python cross_rank.py                      # reads from results/
  python cross_rank.py --top 30
  python cross_rank.py --out best_setups.csv
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd


def load_all_results(results_dir: str = "results") -> pd.DataFrame:
    """Load and concatenate all scanner CSVs, tagging each with its source."""
    frames = []
    for path in sorted(glob.glob(os.path.join(results_dir, "ord_scan_*.csv"))):
        fname = os.path.basename(path)
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty or "ticker" not in df.columns:
            continue
        # Parse timeframe and mode from filename
        parts = fname.replace("ord_scan_", "").replace(".csv", "").split("_")
        df["tf"] = parts[0] if len(parts) > 0 else "unknown"
        df["mode"] = parts[1] if len(parts) > 1 else "unknown"
        df["univ"] = parts[2] if len(parts) > 2 else "unknown"
        df["source"] = fname
        frames.append(df)
    if not frames:
        print(f"No CSV files found in {results_dir}/", file=sys.stderr)
        sys.exit(1)
    combined = pd.concat(frames, ignore_index=True)
    print(f"[load] {len(frames)} files, {len(combined)} total rows, "
          f"{combined['ticker'].nunique()} unique tickers")
    return combined


def compute_ultimate_asymmetry(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the unified cross-system asymmetry score for each row.
    Only scores BULLISH setups — stocks showing accumulation structure
    near the TOP of a bracket with rising lows, not breakdowns."""

    def safe(col, default=0):
        return df[col].fillna(default) if col in df.columns else pd.Series(default, index=df.index)

    ua = pd.Series(0.0, index=df.index, name="ua_score")

    # === DIRECTIONAL FILTERS (only reward bullish structure) ===
    above_ma = safe("above_ma50").astype(bool)
    close_pos = safe("close_pos", 0.5)
    brk_pos = safe("brk_pos", 0.5)
    rising = safe("rising_lows").astype(bool)

    # Is the stock near the TOP of its bracket (bullish) or bottom (bearish)?
    near_top = brk_pos >= 0.70
    near_bot = brk_pos <= 0.30
    mid_range = (brk_pos > 0.30) & (brk_pos < 0.70)

    # Bullish structure: rising lows OR above MA OR close in upper half
    bullish = (rising | above_ma | (close_pos >= 0.55))

    # === 1. RISK/REWARD (only meaningful for bullish setups) ===
    rr = safe("rr").clip(0, 50)
    ua += np.where(bullish & (rr >= 10), 15,
          np.where(bullish & (rr >= 5), 10,
          np.where(bullish & (rr >= 3), 6,
          np.where(bullish & (rr >= 2), 3, 0))))

    risk = safe("risk_pct", 1.0)
    ua += np.where(bullish & (risk <= 0.03), 10,
          np.where(bullish & (risk <= 0.05), 7,
          np.where(bullish & (risk <= 0.08), 4,
          np.where(bullish & (risk <= 0.12), 2, 0))))

    rr_dest = safe("rr_dest").clip(0, 50)
    ua += np.where(near_top & (rr_dest >= 5), 5,
          np.where(near_top & (rr_dest >= 3), 3,
          np.where(near_top & (rr_dest >= 2), 1, 0)))

    # === 2. DRAWDOWN (only rewarded if bullish structure present) ===
    dd = safe("drawdown")
    ua += np.where(bullish & (dd >= 0.15) & (dd <= 0.35), 8,
          np.where(bullish & (dd >= 0.10) & (dd < 0.15), 5,
          np.where(bullish & (dd >= 0.05) & (dd < 0.10), 2,
          np.where(dd < 0.05, -5,  # at highs = no asymmetry
          np.where(~bullish & (dd > 0.30), -5, 0)))))  # big DD without bullish = broken

    # === 3. VOLATILITY COMPRESSION (spring loading) ===
    in_sq = safe("squeeze").astype(bool)
    bw = safe("bw_pctile", 1.0)
    ua += np.where(in_sq & (bw <= 0.10), 10,
          np.where(in_sq & (bw <= 0.25), 7,
          np.where(in_sq, 5,
          np.where(bw <= 0.15, 4, 0))))

    donch = safe("donch_pct", 1.0)
    ua += np.where(donch <= 0.15, 5, np.where(donch <= 0.30, 3, 0))

    # === 4. ORD SIGNALS (volume-confirmed) ===
    ov_sig = safe("ov_sig").astype(bool)
    ov_loose = safe("ov_sig_loose").astype(bool)
    spv_sig = safe("spv_sig").astype(bool)
    ua += np.where(ov_sig, 12, np.where(ov_loose, 6, 0))
    ua += np.where(spv_sig, 8, 0)

    # === 5. RELATIVE STRENGTH (must be improving = bullish) ===
    rel_brk = safe("rel_brk").astype(bool)
    rs_13 = safe("rs_13hi").astype(bool)
    rs_26 = safe("rs_26hi").astype(bool)
    rel_sq = safe("rel_sq").astype(bool)
    rel_spv = safe("rel_spv").astype(bool)
    ua += np.where(rel_brk, 6, 0)
    ua += np.where(rs_13, 4, 0)
    ua += np.where(rs_26, 4, 0)
    ua += np.where(rel_sq, 3, 0)
    ua += np.where(rel_spv, 5, 0)

    # === 6. CONSOLIDATION near TOP (bullish cause) ===
    cause = safe("cause_bars")
    ua += np.where(near_top & (cause >= 15), 6,
          np.where(near_top & (cause >= 8), 4,
          np.where(cause >= 8, 2,
          np.where(cause >= 4, 1, 0))))

    brk_bars = safe("brk_bars")
    ua += np.where(brk_bars >= 52, 5, np.where(brk_bars >= 26, 3, 0))
    ua += np.where(near_top, 5, 0)  # only reward near TOP edge
    ua += np.where(rising & near_top, 5, 0)

    # === 7. DALTON AUCTION QUALITY (directionally aware) ===
    cib = safe("cib")
    vol_conf = safe("vol_conf")
    ua += np.where(cib >= 0.70, 5, np.where(cib >= 0.50, 3, 0))
    ua += np.where(vol_conf >= 0.70, 5, np.where(vol_conf >= 0.50, 3, 0))

    probe = safe("probe_edge").astype(bool)
    rng_exp = safe("rng_exp_v").astype(bool)
    # Probe at TOP = responsive sellers failing = bullish
    ua += np.where(probe & near_top, 4, np.where(probe & mid_range, 2, 0))
    ua += np.where(rng_exp & bullish, 4, 0)

    otf = safe("one_tf")
    ua += np.where(rising & (otf >= 6), 5, np.where(rising & (otf >= 4), 3, 0))

    # === 8. DALTON MOM SIGNALS ===
    dp = safe("dp_sig", "")
    ua += np.where(dp == "MIRAGE_BUY", 8, np.where(dp == "LOW_VOL_SELL", 5,
          np.where(dp == "CONFIRMED_UP", 3, np.where(dp == "FAILED_UP", -5, 0))))

    h_bull = safe("h_bull")
    ua += np.where(h_bull >= 3, 5, np.where(h_bull >= 2, 3, np.where(h_bull >= 1, 1, 0)))

    # === 9. QUALITY / ALL-WEATHER ===
    aw = safe("all_weather").astype(bool)
    ua += np.where(aw, 8, 0)

    # === 10. QULLAMAGGIE (tight base near highs) ===
    q_compress = safe("q_compress", 1.0)
    q_volratio = safe("q_volratio", 1.0)
    ua += np.where(bullish & (q_compress <= 0.70), 4,
          np.where(bullish & (q_compress <= 0.85), 2, 0))
    ua += np.where(bullish & (q_volratio <= 0.75), 3,
          np.where(bullish & (q_volratio <= 0.90), 1, 0))

    # === 11. MFI / CMF ZERO-CROSS (TCAP pattern) ===
    full_tcap = safe("full_tcap").astype(bool)
    mfi_x = safe("mfi_x").astype(bool)
    vol_spk_x = safe("vol_spk_x").astype(bool)
    cmf_impr = safe("cmf_impr").astype(bool)
    ua += np.where(full_tcap, 15,
          np.where(mfi_x & vol_spk_x, 10,
          np.where(mfi_x, 6,
          np.where(cmf_impr, 2, 0))))

    # === 12. ORD TRAJECTORY (early inflection detection) ===
    ord_early = safe("ord_early").astype(bool)
    ord_traj = safe("ord_traj", "")
    ord_cont = safe("ord_cont")
    ord_vel = safe("ord_vel")
    ua += np.where(ord_traj == "INFLECT_UP", 12, 0)
    ua += np.where(ord_traj == "ACCEL_BULL", 10, 0)
    ua += np.where(ord_traj == "VEL_POS", 6, 0)
    ua += np.where((ord_traj == "STRONG_UP") & bullish, 4, 0)
    ua += np.where(ord_traj == "ACCEL_BEAR", -5, 0)
    ua += np.where(ord_traj == "DECLINING", -3, 0)

    # === PENALTIES ===
    q_ret26 = safe("q_ret26")
    ua += np.where(q_ret26 > 0.40, -10, np.where(q_ret26 > 0.25, -5, 0))

    # Penalize bearish structure masquerading as "asymmetry"
    ua += np.where(near_bot & ~rising & (dd > 0.25), -10, 0)  # broken stock at bracket low
    ua += np.where(~above_ma & ~rising & (close_pos < 0.40), -5, 0)  # weak structure
    ua += np.where((dd > 0.50) & ~bullish, -8, 0)  # >50% DD without bullish signs = disaster

    df = df.copy()
    df["ua_score"] = ua.round(1)
    return df


def signal_summary(row) -> str:
    """Build a human-readable signal summary for a row."""
    signals = []
    traj = row.get("ord_traj", "")
    if traj in ("INFLECT_UP", "ACCEL_BULL", "VEL_POS", "STRONG_UP"):
        signals.append(f"★{traj}")
    if row.get("ov_sig"):
        signals.append(f"OV_{row.get('ov_str','?')}")
    elif row.get("ov_sig_loose"):
        signals.append(f"ov_loose_{row.get('ov_str','?')}")
    if row.get("spv_sig"):
        signals.append(f"SHAKEOUT({row.get('spv_ratio','')})")
    if row.get("squeeze"):
        signals.append(f"SQ(bw{row.get('bw_pctile','')})")
    if row.get("rel_brk"):
        signals.append("RS_BRK")
    if row.get("rs_13hi"):
        signals.append("RS13hi")
    if row.get("rel_sq"):
        signals.append("RS_SQ")
    if row.get("all_weather"):
        signals.append("AW")
    dp = row.get("dp_sig", "")
    if dp and dp not in ("NEUTRAL", "N/A"):
        signals.append(dp)
    if row.get("h_bull", 0) >= 2:
        signals.append(f"HidBull×{row['h_bull']}")
    if row.get("full_tcap"):
        signals.append("★TCAP")
    elif row.get("mfi_x"):
        vspk = "+VOL" if row.get("vol_spk_x") else ""
        signals.append(f"MFI_X{vspk}")
    if row.get("near_edge"):
        signals.append("EDGE")
    if row.get("rising_lows"):
        signals.append("↑LOWS")
    if row.get("probe_edge"):
        signals.append("PROBE")
    if row.get("rng_exp_v"):
        signals.append("RNG_EXP")
    return " ".join(str(s) for s in signals[:8])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-ua", type=float, default=40,
                    help="minimum ultimate asymmetry score to display")
    args = ap.parse_args()

    df = load_all_results(args.results_dir)
    df = compute_ultimate_asymmetry(df)

    # For tickers appearing in multiple CSVs (weekly+monthly, different modes),
    # take the row with the highest ua_score per ticker+tf combo
    best = df.sort_values("ua_score", ascending=False).drop_duplicates(
        subset=["ticker", "tf"], keep="first"
    )

    # Display
    view = best[best["ua_score"] >= args.min_ua].head(args.top)
    if view.empty:
        print(f"No candidates above ua_score {args.min_ua}; showing top {args.top}")
        view = best.head(args.top)

    print(f"\n{'='*120}")
    print(f"  ULTIMATE ASYMMETRY RANKING — Top {len(view)} across all systems, universes, timeframes")
    print(f"{'='*120}")
    print(f"  {'Tk':<6} {'TF':>2} {'UA':>5} {'Close':>8} {'DD%':>5} {'Risk%':>5} "
          f"{'R:R':>5} {'RRdst':>5} {'Early':>5} {'Mass':>4} {'Cause':>5} "
          f"{'BrkB':>4} {'Signals'}")
    print(f"  {'─'*6} {'─'*2} {'─'*5} {'─'*8} {'─'*5} {'─'*5} "
          f"{'─'*5} {'─'*5} {'─'*5} {'─'*4} {'─'*5} {'─'*4} {'─'*50}")

    for _, r in view.iterrows():
        sigs = signal_summary(r)
        print(f"  {r['ticker']:<6} {r.get('tf','?'):>2} {r['ua_score']:>5.0f} "
              f"{r.get('close',0):>8.2f} "
              f"{r.get('drawdown',0)*100:>4.1f}% "
              f"{r.get('risk_pct',0)*100:>4.1f}% "
              f"{r.get('rr',0):>5.1f} {r.get('rr_dest',0):>5.1f} "
              f"{r.get('early_score',0):>5.0f} {r.get('massive',0):>4.0f} "
              f"{r.get('cause_bars',0):>5.0f} {r.get('brk_bars',0):>4.0f} "
              f"{sigs}")

    if args.out:
        best.to_csv(args.out, index=False)
        print(f"\n[write] {args.out}")


if __name__ == "__main__":
    main()
