"""
Scan US mid-cap equities for an active "failed bearish setup" and rank the
survivors by a value-tilted composite of price-to-book and fundamentals.

Bearish setup (on the chosen timeframe, weekly by default):
  1. fresh low   : close < min(close[-lookback:-1])
  2. broke 50SMA : close < SMA_short AND SMA_short < SMA_long
  3. broke support: close < min(low[-lookback:-1])

Failed setup (the bullish trigger):
  within `max_bars_to_failure` bars after the setup bar, a close prints
  above the setup bar's high -- the breakdown is reclaimed.

Active filter: only keep tickers whose failure bar is within the last
`--active-bars` bars.

Ranking: z-score composite (higher is better)
  0.35 * -z(P/B) + 0.25 * z(ROE) + 0.15 * -z(D/E)
  + 0.15 * z(profit margin) + 0.10 * z(revenue growth)
with a hard floor of priceToBook > 0 and returnOnEquity > 0.
"""

import argparse
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


def get_midcap_universe():
    import financedatabase as fd

    equities = fd.Equities()
    df = equities.select(country="United States", market_cap="Mid Cap")
    return df


def _extract_ticker_frame(data, ticker):
    if isinstance(data.columns, pd.MultiIndex):
        if ticker not in data.columns.get_level_values(0):
            return None
        sub = data[ticker].dropna(how="all")
    else:
        sub = data.dropna(how="all")
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(sub.columns):
        return None
    return sub


def download_prices(tickers, timeframe, years, chunk_size=150):
    interval = "1wk" if timeframe == "weekly" else "1mo"
    period = f"{years}y"
    frames = {}
    total = len(tickers)
    for i in range(0, total, chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"  batch {i // chunk_size + 1}: {i + 1}-{min(i + chunk_size, total)} of {total}")
        try:
            data = yf.download(
                chunk,
                period=period,
                interval=interval,
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            print(f"    batch failed: {e}")
            continue
        if data is None or data.empty:
            continue
        for t in chunk:
            sub = _extract_ticker_frame(data, t)
            if sub is not None and len(sub) >= 60:
                frames[t] = sub
    return frames


def detect_failed_bearish_setup(
    df,
    lookback=10,
    sma_short=20,
    sma_long=50,
    max_bars_to_failure=5,
):
    if len(df) < sma_long + lookback + max_bars_to_failure:
        return None

    work = df.copy()
    work["sma_s"] = work["Close"].rolling(sma_short).mean()
    work["sma_l"] = work["Close"].rolling(sma_long).mean()
    work["prior_close_min"] = work["Close"].shift(1).rolling(lookback).min()
    work["prior_low_min"] = work["Low"].shift(1).rolling(lookback).min()

    trigger_mask = (
        (work["Close"] < work["prior_close_min"])
        & (work["Close"] < work["sma_s"])
        & (work["sma_s"] < work["sma_l"])
        & (work["Close"] < work["prior_low_min"])
    )
    trigger_mask = trigger_mask.fillna(False)
    triggers = work.index[trigger_mask]
    if len(triggers) == 0:
        return None

    last_trigger = triggers[-1]
    trigger_pos = work.index.get_loc(last_trigger)
    trigger_high = float(work.loc[last_trigger, "High"])
    trigger_low = float(work.loc[last_trigger, "Low"])

    end_pos = min(trigger_pos + 1 + max_bars_to_failure, len(work))
    window = work.iloc[trigger_pos + 1 : end_pos]
    failure = window[window["Close"] > trigger_high]
    if len(failure) == 0:
        return None
    failure_date = failure.index[0]

    return {
        "trigger_date": last_trigger,
        "trigger_high": trigger_high,
        "trigger_low": trigger_low,
        "failure_date": failure_date,
        "failure_close": float(work.loc[failure_date, "Close"]),
        "latest_close": float(work["Close"].iloc[-1]),
        "latest_date": work.index[-1],
    }


def fetch_fundamentals(tickers, sleep_s=0.05):
    rows = []
    for i, t in enumerate(tickers, 1):
        if i % 25 == 0:
            print(f"  fundamentals {i}/{len(tickers)}")
        try:
            info = yf.Ticker(t).info or {}
        except Exception:
            info = {}
        rows.append(
            {
                "Ticker": t,
                "priceToBook": info.get("priceToBook"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "returnOnEquity": info.get("returnOnEquity"),
                "debtToEquity": info.get("debtToEquity"),
                "profitMargins": info.get("profitMargins"),
                "revenueGrowth": info.get("revenueGrowth"),
                "marketCap": info.get("marketCap"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "shortName": info.get("shortName") or info.get("longName"),
            }
        )
        time.sleep(sleep_s)
    return pd.DataFrame(rows).set_index("Ticker")


def rank(df):
    mask = (df["priceToBook"].astype(float) > 0) & (df["returnOnEquity"].astype(float) > 0)
    out = df[mask].copy()
    if out.empty:
        return out

    def z(series, higher_better):
        s = pd.to_numeric(series, errors="coerce").astype(float)
        std = s.std(ddof=0)
        if std == 0 or np.isnan(std):
            return pd.Series(0.0, index=s.index)
        r = (s - s.mean()) / std
        r = r.fillna(0.0)
        return r if higher_better else -r

    out["z_pb"] = z(out["priceToBook"], higher_better=False)
    out["z_roe"] = z(out["returnOnEquity"], higher_better=True)
    out["z_de"] = z(out["debtToEquity"], higher_better=False)
    out["z_margin"] = z(out["profitMargins"], higher_better=True)
    out["z_growth"] = z(out["revenueGrowth"], higher_better=True)

    out["score"] = (
        0.35 * out["z_pb"]
        + 0.25 * out["z_roe"]
        + 0.15 * out["z_de"]
        + 0.15 * out["z_margin"]
        + 0.10 * out["z_growth"]
    )

    return out.sort_values("score", ascending=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument("--years", type=int, default=5, help="History length for price download")
    parser.add_argument("--lookback", type=int, default=10, help="Bars for fresh-low / support lookback")
    parser.add_argument("--sma-short", type=int, default=20)
    parser.add_argument("--sma-long", type=int, default=50)
    parser.add_argument("--max-bars-to-failure", type=int, default=5)
    parser.add_argument(
        "--active-bars",
        type=int,
        default=8,
        help="Failure trigger must be within the last N bars to count as active",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print("Fetching US mid-cap universe from financedatabase...")
    universe = get_midcap_universe()
    tickers = [t for t in universe.index.tolist() if isinstance(t, str) and t]
    print(f"  {len(tickers)} tickers")

    print(f"Downloading {args.timeframe} bars ({args.years}y)...")
    prices = download_prices(tickers, args.timeframe, args.years)
    print(f"  {len(prices)} tickers with usable data")

    print("Detecting failed bearish setups...")
    signals = {}
    for t, df in prices.items():
        sig = detect_failed_bearish_setup(
            df,
            lookback=args.lookback,
            sma_short=args.sma_short,
            sma_long=args.sma_long,
            max_bars_to_failure=args.max_bars_to_failure,
        )
        if sig is None:
            continue
        bars_since_failure = len(df.loc[sig["failure_date"] :]) - 1
        if bars_since_failure > args.active_bars:
            continue
        signals[t] = sig
    print(f"  {len(signals)} tickers with active failed bearish setup")

    if not signals:
        print("No signals.")
        return

    print("Fetching fundamentals...")
    fundamentals = fetch_fundamentals(list(signals.keys()))

    sig_df = pd.DataFrame.from_dict(signals, orient="index")
    sig_df.index.name = "Ticker"
    combined = sig_df.join(fundamentals, how="left")

    ranked = rank(combined)
    if ranked.empty:
        print("No survivors after P/B > 0 and ROE > 0 filter.")
        return

    ranked["pct_from_failure"] = (
        (ranked["latest_close"] - ranked["failure_close"]) / ranked["failure_close"] * 100
    )

    display_cols = [
        "shortName",
        "sector",
        "priceToBook",
        "returnOnEquity",
        "debtToEquity",
        "profitMargins",
        "revenueGrowth",
        "trailingPE",
        "marketCap",
        "trigger_date",
        "failure_date",
        "pct_from_failure",
        "score",
    ]
    display_cols = [c for c in display_cols if c in ranked.columns]
    out = ranked[display_cols]

    out_path = (
        args.out
        or f"failed_bearish_midcap_{args.timeframe}_{datetime.today():%Y%m%d}.csv"
    )
    out.to_csv(out_path)
    print(f"Saved: {out_path}")

    print(f"\nTop {args.top}:")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(out.head(args.top).to_string())


if __name__ == "__main__":
    main()
