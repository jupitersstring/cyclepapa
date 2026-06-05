"""Test: what does ADV (raw and turnover) look like in the 90-180 days BEFORE
a mega-winner's run starts?

Method:
  1. For each curated mega-winner, fetch max-history daily bars + current mcap.
  2. Find the trough that preceded the latest big run-up (peak/trough scan).
  3. Take a 90-day pre-run window ending at the trough.
  4. Compute ADV_20 and turnover (ADV/mcap_at_trough) over that window.
  5. Report stats: where on the ADV-bucket ladder did the pre-launch look like?

Output also includes peak-to-trough multiplier and total return so we can
see how big the subsequent run was.
"""

import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Mega-winners with a clear large run-up in trailing ~3yrs (so we can fetch).
MEGA = [
    "NVDA", "META", "PLTR", "AVGO", "TSLA",
    "ANET", "CRWD", "SMCI", "RKLB", "NU",
    "VST",  "CEG", "GEV", "APP",  "AXON",
    "NFLX", "ORCL", "HOOD","RDDT","SOFI",
]


def find_pre_run_window(close: pd.Series, min_run: float = 1.5,
                         window_days: int = 90) -> dict:
    """Find the trough that preceded the largest run-up, return the pre-run
    window summary."""
    if len(close) < 250:
        return {}
    # Walk: at each bar t, ratio = max(close[t:]) / close[t] over remaining bars
    arr = close.values
    n = len(arr)
    fwd_max = np.maximum.accumulate(arr[::-1])[::-1]  # max from t to end
    multiples = fwd_max / arr
    best_t = int(np.argmax(multiples))
    best_mult = float(multiples[best_t])
    if best_mult < min_run or best_t < window_days + 10:
        return {}
    trough_date = close.index[best_t]
    peak_after = float(arr[best_t:].max())
    days_to_peak = int(np.argmax(arr[best_t:]))
    return {
        "trough_pos":     best_t,
        "trough_date":    str(trough_date.date()),
        "trough_price":   float(arr[best_t]),
        "peak_price":     peak_after,
        "peak_multiple":  best_mult,
        "days_to_peak":   days_to_peak,
        "window_start":   str(close.index[best_t - window_days].date()),
        "window_end":     str(trough_date.date()),
    }


def main():
    rows = []
    for t in MEGA:
        try:
            tk = yf.Ticker(t)
            bars = tk.history(period="max", auto_adjust=True)
            if bars.empty or len(bars) < 250:
                continue
            info = tk.info or {}
            shares_out = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            mcap_now = info.get("marketCap")

            # Limit to last 5 years to keep the "current cycle" relevant
            bars5 = bars.iloc[-1260:] if len(bars) > 1260 else bars
            run = find_pre_run_window(bars5["Close"])
            if not run:
                continue

            # Pre-run window
            tp = run["trough_pos"]
            window = bars5.iloc[max(0, tp - 90):tp]
            dv = (window["Close"] * window["Volume"]).dropna()
            adv_pre = float(dv.mean()) if len(dv) else None
            adv_pre_med = float(dv.median()) if len(dv) else None

            # mcap at trough (approx: close * shares_out, if we have shares)
            if shares_out and shares_out > 0:
                mcap_trough = float(run["trough_price"] * shares_out)
                turnover_pre = adv_pre / mcap_trough if adv_pre else None
            else:
                mcap_trough = None
                turnover_pre = None

            rows.append({
                "ticker":         t,
                "trough_date":    run["trough_date"],
                "trough_price":   run["trough_price"],
                "peak_multiple":  run["peak_multiple"],
                "days_to_peak":   run["days_to_peak"],
                "ADV_pre_run_M":  adv_pre / 1e6 if adv_pre else None,
                "ADV_pre_med_M":  adv_pre_med / 1e6 if adv_pre_med else None,
                "mcap_trough_M":  mcap_trough / 1e6 if mcap_trough else None,
                "turnover_pre":   turnover_pre,
            })
        except Exception as e:
            print(f"{t}: {e}", file=sys.stderr)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no results")
        return

    df = df.sort_values("peak_multiple", ascending=False)
    print(df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print(f"\n=== Stats across {len(df)} mega-winners ===")
    print(f"Median ADV pre-run:        ${df['ADV_pre_run_M'].median():.1f}M")
    print(f"Mean   ADV pre-run:        ${df['ADV_pre_run_M'].mean():.1f}M")
    print(f"Pct >  $20M ADV:           {(df['ADV_pre_run_M'] >= 20).mean()*100:.0f}%")
    print(f"Pct >  $50M ADV:           {(df['ADV_pre_run_M'] >= 50).mean()*100:.0f}%")
    print(f"Pct > $100M ADV:           {(df['ADV_pre_run_M'] >= 100).mean()*100:.0f}%")
    print(f"Pct >  $1B  ADV:           {(df['ADV_pre_run_M'] >= 1000).mean()*100:.0f}%")
    if df["turnover_pre"].notna().sum() > 0:
        print(f"Median turnover (ADV/mcap): {df['turnover_pre'].median()*100:.2f}% daily")
        print(f"Mean   turnover:           {df['turnover_pre'].mean()*100:.2f}% daily")


if __name__ == "__main__":
    main()
