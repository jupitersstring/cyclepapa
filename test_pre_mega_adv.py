"""Test: what does ADV (raw and turnover) look like in the 90-180 days BEFORE
a mega-winner's run starts? Now widened across mcap tiers.

Method:
  1. For each curated winner across small/mid/large/mega-cap tiers, fetch
     max-history daily bars + current mcap + shares-outstanding.
  2. Find the trough that preceded the latest big run-up (peak/trough scan).
  3. Take a 90-day pre-run window ending at the trough.
  4. Compute ADV_20 and turnover (ADV/mcap_at_trough) over that window.
  5. Report stats per cap tier: where on the ADV ladder did the pre-launch
     look like?

The question we want to answer crisply: do small-cap and mid-cap mega
winners also clear Minervini's $20M actionable / $50M preferred bar? Or
is that bar only true for the eventual large/mega cohort?
"""

import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Curated multi-baggers categorized by pre-run cap tier (rough estimate).
# Mix of obvious mega names plus small/mid winners that few people remember
# were trading at $1-3B before they ran.
TICKERS = {
    # Pre-run mcap < $2B (small/microcap that became mid/large)
    "small": [
        "CELH",   # Celsius:  ~$1B → $20B+ at peak
        "ELF",    # e.l.f. Beauty: ~$1.5B → $13B
        "WGS",    # GeneDx: micro → mid
        "RKLB",   # Rocket Lab: ~$1.7B → multi-bagger
        "TMDX",   # TransMedics: ~$700M → $5B
        "DUOL",   # Duolingo: ~$3B → much more, but borderline
        "AAOI",   # Applied Optoelectronics
        "VKTX",   # Viking Therapeutics
        "ATAT",   # Atour Lifestyle (China)
        "IREN",   # Iris Energy
        "HUT",    # Hut 8
        "MARA",   # Marathon Digital
        "RIOT",   # Riot Platforms
        "SMR",    # NuScale Power
        "OKLO",   # Oklo
        "BLDE",   # Blade Air Mobility
        "BBAI",   # BigBear.ai
    ],
    # Pre-run mcap $2B - $20B (mid-cap → mega)
    "mid": [
        "APP",    # AppLovin: $3B → $100B+
        "PLTR",   # Palantir: $14B → mega
        "HOOD",   # Robinhood: $6B → mega
        "RDDT",   # Reddit: ~$6B → $20B+
        "SOFI",   # SoFi
        "NU",     # Nu Holdings: $15B → $60B
        "AXON",   # Axon: ~$6B → $50B
        "VST",    # Vistra: ~$5B → $50B
        "CEG",    # Constellation Energy: ~$13B → $80B
        "VRT",    # Vertiv: ~$5B → $50B
        "ANET",   # Arista Networks
        "CRWD",   # CrowdStrike
        "SMCI",   # Super Micro: $4B → $60B
        "FOUR",   # Shift4 Payments
        "CVNA",   # Carvana resurrection
        "MSTR",   # MicroStrategy / Strategy: $5B → $80B
        "GEV",    # GE Vernova
        "DASH",   # DoorDash
        "ABNB",   # Airbnb
        "DELL",   # Dell revival
        "TPR",    # Tapestry
        "ANF",    # Abercrombie
        "WING",   # Wingstop
        "FICO",   # Fair Isaac
        "IBKR",   # Interactive Brokers
        "DECK",   # Deckers
        "TDG",    # TransDigm
    ],
    # Pre-run mcap > $20B (large → mega)
    "large": [
        "NVDA",
        "META",
        "AVGO",
        "TSLA",
        "NFLX",
        "ORCL",
        "AMD",
        "LLY",    # Eli Lilly: $300B → $700B+
        "NVO",    # Novo Nordisk
        "COST",
        "WMT",
        "TSM",
        "ASML",
        "BKNG",
        "MELI",
        "JPM",
        "TMUS",
        "GE",     # General Electric revival
        "IBM",    # IBM revival
        "MSFT",   # large compounder
    ],
}


def find_pre_run_window(close: pd.Series, min_run: float = 1.5,
                         window_days: int = 90) -> dict:
    """Find the trough that preceded the largest run-up, return the pre-run
    window summary."""
    if len(close) < 250:
        return {}
    arr = close.values
    n = len(arr)
    fwd_max = np.maximum.accumulate(arr[::-1])[::-1]
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


def evaluate_ticker(t: str, tier: str) -> dict | None:
    try:
        tk = yf.Ticker(t)
        bars = tk.history(period="max", auto_adjust=True)
        if bars.empty or len(bars) < 250:
            return None
        info = tk.info or {}
        shares_out = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")

        bars5 = bars.iloc[-1260:] if len(bars) > 1260 else bars
        run = find_pre_run_window(bars5["Close"])
        if not run:
            return None

        tp = run["trough_pos"]
        window = bars5.iloc[max(0, tp - 90):tp]
        dv = (window["Close"] * window["Volume"]).dropna()
        adv_pre = float(dv.mean()) if len(dv) else None

        if shares_out and shares_out > 0:
            mcap_trough = float(run["trough_price"] * shares_out)
            turnover_pre = adv_pre / mcap_trough if adv_pre else None
        else:
            mcap_trough = None
            turnover_pre = None

        return {
            "ticker":         t,
            "tier":           tier,
            "trough_date":    run["trough_date"],
            "trough_price":   run["trough_price"],
            "peak_multiple":  run["peak_multiple"],
            "days_to_peak":   run["days_to_peak"],
            "ADV_pre_run_M":  adv_pre / 1e6 if adv_pre else None,
            "mcap_trough_M":  mcap_trough / 1e6 if mcap_trough else None,
            "turnover_pre":   turnover_pre,
        }
    except Exception as e:
        print(f"{t}: {e}", file=sys.stderr)
        return None


def report_tier(df: pd.DataFrame, tier: str):
    sub = df[df["tier"] == tier]
    if sub.empty:
        return
    print(f"\n--- {tier.upper()} TIER (n={len(sub)}) ---")
    cols = ["ticker", "trough_date", "trough_price", "peak_multiple",
            "ADV_pre_run_M", "mcap_trough_M", "turnover_pre"]
    print(sub[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"  Median ADV pre-run:        ${sub['ADV_pre_run_M'].median():.1f}M")
    print(f"  Min    ADV pre-run:        ${sub['ADV_pre_run_M'].min():.1f}M")
    print(f"  Pct >= $20M ADV:           {(sub['ADV_pre_run_M'] >= 20).mean()*100:.0f}%")
    print(f"  Pct >= $50M ADV:           {(sub['ADV_pre_run_M'] >= 50).mean()*100:.0f}%")
    print(f"  Pct >= $100M ADV:          {(sub['ADV_pre_run_M'] >= 100).mean()*100:.0f}%")
    if sub["turnover_pre"].notna().sum() > 0:
        print(f"  Median turnover (ADV/mcap): {sub['turnover_pre'].median()*100:.2f}% daily")
        print(f"  Pct turnover >= 1%:        {(sub['turnover_pre'] >= 0.01).mean()*100:.0f}%")
        print(f"  Pct turnover >= 2%:        {(sub['turnover_pre'] >= 0.02).mean()*100:.0f}%")


def main():
    rows = []
    for tier, tickers in TICKERS.items():
        print(f"\nTier {tier}: {len(tickers)} tickers", file=sys.stderr)
        for t in tickers:
            r = evaluate_ticker(t, tier)
            if r:
                rows.append(r)
                print(f"  {t}: peak_mult={r['peak_multiple']:.1f}x "
                      f"ADV=${r['ADV_pre_run_M']:.1f}M",
                      file=sys.stderr)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no results")
        return

    df = df.sort_values(["tier", "peak_multiple"], ascending=[True, False])

    for tier in ["small", "mid", "large"]:
        report_tier(df, tier)

    print(f"\n=== Overall across {len(df)} winners ===")
    print(f"Median ADV pre-run:        ${df['ADV_pre_run_M'].median():.1f}M")
    print(f"Mean   ADV pre-run:        ${df['ADV_pre_run_M'].mean():.1f}M")
    print(f"Pct >= $20M ADV:           {(df['ADV_pre_run_M'] >= 20).mean()*100:.0f}%")
    print(f"Pct >= $50M ADV:           {(df['ADV_pre_run_M'] >= 50).mean()*100:.0f}%")
    print(f"Pct >= $100M ADV:          {(df['ADV_pre_run_M'] >= 100).mean()*100:.0f}%")
    if df["turnover_pre"].notna().sum() > 0:
        print(f"Median turnover (ADV/mcap): {df['turnover_pre'].median()*100:.2f}% daily")

    # Save the full table to CSV for the Excel build to consume
    out = "/tmp/pre_mega_adv_wide.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
