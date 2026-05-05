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


US_EXCHANGES = {"NYQ", "NMS", "NGM", "NCM", "ASE", "BATS"}

EU_PRIMARY_EXCHANGES = {
    "LSE",  # London .L
    "GER",  # Xetra .DE
    "PAR",  # Paris .PA
    "AMS",  # Amsterdam .AS
    "MIL",  # Milan .MI
    "MCE",  # Madrid .MC
    "STO",  # Stockholm .ST
    "HEL",  # Helsinki .HE
    "CPH",  # Copenhagen .CO
    "OSL",  # Oslo .OL
    "VIE",  # Vienna .VI
    "EBS",  # SIX Swiss .SW
    "BRU",  # Brussels .BR
    "IRE",  # Dublin .IR
    "LIS",  # Lisbon .LS
    "ATH",  # Athens .AT
    "WSE",  # Warsaw .WA
    "PRA",  # Prague .PR
}

EU_COUNTRIES = [
    "United Kingdom", "Germany", "France", "Italy", "Spain",
    "Netherlands", "Switzerland", "Sweden", "Belgium", "Norway",
    "Denmark", "Finland", "Ireland", "Austria", "Portugal",
    "Greece", "Poland", "Czech Republic", "Hungary", "Luxembourg",
]


def get_universe(name):
    import financedatabase as fd

    equities = fd.Equities()
    if name == "us-mid":
        df = equities.select(country="United States", market_cap="Mid Cap")
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-micro":
        df = equities.select(country="United States", market_cap="Micro Cap")
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-smid":
        frames = []
        for cap in ["Small Cap", "Mid Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "uk-smid":
        frames = []
        for cap in ["Small Cap", "Mid Cap"]:
            try:
                sub = equities.select(country="United Kingdom", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "LSE"]
        return df
    if name == "uk-midlarge":
        frames = []
        for cap in ["Mid Cap", "Large Cap"]:
            try:
                sub = equities.select(country="United Kingdom", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "LSE"]
        return df
    if name == "us-midlarge":
        frames = []
        for cap in ["Mid Cap", "Large Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "eu-smid":
        frames = []
        for country in EU_COUNTRIES:
            for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap"]:
                try:
                    sub = equities.select(country=country, market_cap=cap)
                    if len(sub):
                        frames.append(sub)
                except Exception:
                    continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(EU_PRIMARY_EXCHANGES)]
        return df
    raise ValueError(f"unknown universe: {name}")


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


def download_prices(tickers, timeframe, years, chunk_size=80, batch_sleep=20.0):
    interval = "1wk" if timeframe == "weekly" else "1mo"
    period = f"{years}y"
    frames = {}
    total = len(tickers)
    n_batches = (total + chunk_size - 1) // chunk_size
    for i in range(0, total, chunk_size):
        batch_idx = i // chunk_size + 1
        chunk = tickers[i : i + chunk_size]
        print(f"  batch {batch_idx}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} of {total} (kept so far: {len(frames)})")
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
            data = None
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    sub = _extract_ticker_frame(data, t)
                    if sub is not None and len(sub) >= 60:
                        frames[t] = sub
                except Exception:
                    continue
        if batch_idx < n_batches:
            time.sleep(batch_sleep)
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


def fetch_fundamentals(tickers, base_sleep_s=1.0, max_retries=3):
    rows = []
    sleep_s = base_sleep_s
    rate_limited_streak = 0
    for i, t in enumerate(tickers, 1):
        if i % 10 == 0:
            print(f"  fundamentals {i}/{len(tickers)} (sleep={sleep_s:.1f}s)")
        info = {}
        for attempt in range(max_retries):
            try:
                info = yf.Ticker(t).info or {}
                rate_limited_streak = 0
                break
            except Exception as e:
                msg = str(e).lower()
                if "rate" in msg or "too many" in msg or "429" in msg:
                    rate_limited_streak += 1
                    wait = sleep_s * (2 ** attempt) + 2
                    print(f"    rate limited on {t}, waiting {wait:.0f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                else:
                    break
        if rate_limited_streak >= 3:
            sleep_s = min(sleep_s * 1.5, 10.0)
        rows.append(
            {
                "Ticker": t,
                "priceToBook": info.get("priceToBook"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                "enterpriseValue": info.get("enterpriseValue"),
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


def rank(df, quality=False):
    pb = pd.to_numeric(df["priceToBook"], errors="coerce")
    drop_mask = pb.notna() & (pb <= 0)
    out = df[~drop_mask].copy()
    if quality and not out.empty:
        roe = pd.to_numeric(out["returnOnEquity"], errors="coerce")
        margin = pd.to_numeric(out["profitMargins"], errors="coerce")
        de = pd.to_numeric(out["debtToEquity"], errors="coerce")
        growth = pd.to_numeric(out["revenueGrowth"], errors="coerce")
        keep = (
            (roe > 0.05)
            & (margin > 0)
            & (de.notna() & (de < 200))
            & (growth.notna() & (growth > -0.10))
        )
        n_before = len(out)
        out = out[keep]
        print(f"  quality filter: {len(out)}/{n_before} survive (ROE>5%, margin>0, D/E<200, growth>-10%)")
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

    n_complete = out[["priceToBook", "returnOnEquity"]].notna().all(axis=1).sum()
    print(f"  {n_complete}/{len(out)} rows have full P/B + ROE; missing rows rank with z=0")

    return out.sort_values("score", ascending=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument("--years", type=int, default=None, help="History length for price download (default: 5y weekly, 15y monthly)")
    parser.add_argument("--lookback", type=int, default=None, help="Bars for fresh-low / support lookback (default: 10 weekly, 6 monthly)")
    parser.add_argument("--sma-short", type=int, default=None, help="Short SMA bars (default: 20 weekly, 10 monthly)")
    parser.add_argument("--sma-long", type=int, default=None, help="Long SMA bars (default: 50 weekly, 20 monthly)")
    parser.add_argument("--max-bars-to-failure", type=int, default=None, help="(default: 5 weekly, 3 monthly)")
    parser.add_argument(
        "--active-bars",
        type=int,
        default=None,
        help="Failure trigger must be within the last N bars to count as active (default: 8 weekly, 4 monthly)",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--universe", choices=["us-mid", "us-micro", "us-smid", "us-midlarge", "uk-smid", "uk-midlarge", "eu-smid"], default="us-mid")
    parser.add_argument("--quality", action="store_true",
                        help="Apply hard quality floor: ROE>5%, margin>0, D/E<200, rev_growth>-10% (drops NaN)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.timeframe == "weekly":
        defaults = dict(years=5, lookback=10, sma_short=20, sma_long=50, max_bars_to_failure=5, active_bars=8)
    else:
        defaults = dict(years=15, lookback=6, sma_short=10, sma_long=20, max_bars_to_failure=3, active_bars=4)
    for k, v in defaults.items():
        cli = getattr(args, k)
        if cli is None:
            setattr(args, k, v)
    print(
        f"Params: timeframe={args.timeframe} years={args.years} lookback={args.lookback} "
        f"sma_short={args.sma_short} sma_long={args.sma_long} "
        f"max_bars_to_failure={args.max_bars_to_failure} active_bars={args.active_bars}"
    )

    print(f"Fetching {args.universe} universe from financedatabase...")
    universe = get_universe(args.universe)
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

    sig_df = pd.DataFrame.from_dict(signals, orient="index")
    sig_df.index.name = "Ticker"

    signals_path = (
        f"failed_bearish_signals_{args.universe}_{args.timeframe}_{datetime.today():%Y%m%d}.csv"
    )
    sig_df.to_csv(signals_path)
    print(f"Saved signals-only CSV: {signals_path}")

    print("Fetching fundamentals (rate-limit aware; this is slow)...")
    fundamentals = fetch_fundamentals(list(signals.keys()))
    combined = sig_df.join(fundamentals, how="left")

    ranked = rank(combined, quality=args.quality)
    if ranked.empty:
        print("No survivors after P/B filter.")
        return

    ranked["pct_from_failure"] = (
        (ranked["latest_close"] - ranked["failure_close"]) / ranked["failure_close"] * 100
    )

    display_cols = [
        "shortName",
        "sector",
        "priceToBook",
        "enterpriseToEbitda",
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
        or f"failed_bearish_{args.universe}_{args.timeframe}_{datetime.today():%Y%m%d}.csv"
    )
    out.to_csv(out_path)
    print(f"Saved: {out_path}")

    with pd.option_context("display.max_columns", None, "display.width", 200, "display.float_format", "{:.2f}".format):
        print(f"\n=== Top {args.top} by composite score ===")
        print(out.head(args.top).to_string())

        pb = pd.to_numeric(out["priceToBook"], errors="coerce")
        by_pb = out[pb > 0].sort_values("priceToBook", ascending=True)
        print(f"\n=== Top {args.top} cheapest by P/B ===")
        print(by_pb.head(args.top).to_string())

        if "enterpriseToEbitda" in out.columns:
            ev = pd.to_numeric(out["enterpriseToEbitda"], errors="coerce")
            by_ev = out[ev > 0].sort_values("enterpriseToEbitda", ascending=True)
            print(f"\n=== Top {args.top} cheapest by EV/EBITDA ===")
            print(by_ev.head(args.top).to_string())


if __name__ == "__main__":
    main()
