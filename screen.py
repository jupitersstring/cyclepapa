"""
Three-screen SMID stock picker.

Screen 1 - Relative-strength breakout: log(stock/index) at a new 52-week
           AND 12-month high.
Screen 2 - Qullamaggie-style volatility asymmetry (port of the Pine Script):
             monthly asymmetry near 50 (balanced base, coiled spring),
             weekly asymmetry rising AND above its EMA AND still "low"
             (i.e. just lifting off, not yet euphoric).
Screen 3 - Max-independent-set on the |weekly corr| > eps graph among
           survivors, greedy by composite RS-breakout score.
"""

import io
import sys
import urllib.request
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

INDEX = "IJR"

IJR_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IJR_holdings&dataType=fund"
)

# Asymmetry tuning (matches Pine defaults).
ASYM_PERIOD = 14
ASYM_SMOOTH = 7
MONTHLY_ASYM_BAND = (45.0, 55.0)   # "near 50"
WEEKLY_ASYM_LOW_MAX = 60.0         # "preferably low"
WEEKLY_ASYM_RISING_BARS = 2        # last N bars all rising

CORR_EPS = 0.5
RS_LOOKBACK_W = 52
RS_LOOKBACK_M = 12


def fetch_sp600_universe() -> list[str]:
    req = urllib.request.Request(IJR_HOLDINGS_URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig")
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Ticker,Name"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df = df[df["Asset Class"].astype(str).str.lower() == "equity"]
    tickers = df["Ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
    tickers = sorted({t for t in tickers if t and t.isascii() and t.replace("-", "").isalnum()})
    return tickers


def fetch_ohlc(tickers: list[str], period: str = "24mo") -> pd.DataFrame:
    print(f"Downloading OHLC for {len(tickers)} tickers ({period})...", file=sys.stderr)
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    return raw  # MultiIndex columns: (field, ticker)


def resample_ohlc(daily: pd.DataFrame, ticker: str, freq: str) -> pd.DataFrame:
    """Build resampled OHLC bars for one ticker on the given freq."""
    try:
        sub = pd.DataFrame({
            "High":  daily["High"][ticker],
            "Low":   daily["Low"][ticker],
            "Close": daily["Close"][ticker],
        }).dropna()
    except KeyError:
        return pd.DataFrame()
    return sub.resample(freq).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()


def asymmetry(bars: pd.DataFrame, period: int = ASYM_PERIOD, smooth: int = ASYM_SMOOTH) -> pd.DataFrame:
    """Port of the Pine Volatility Asymmetry indicator.
    Returns columns: asym (0-100, 50 = balanced), asym_ma."""
    prev_close = bars["Close"].shift(1)
    up = (bars["High"] - prev_close).clip(lower=0)
    dn = (prev_close - bars["Low"]).clip(lower=0)
    up_atr = up.ewm(span=period, adjust=False).mean()
    dn_atr = dn.ewm(span=period, adjust=False).mean()
    ratio = up_atr / (up_atr + dn_atr + 1e-9)
    asym = (ratio * 100).ewm(span=smooth, adjust=False).mean()
    asym_ma = asym.ewm(span=period, adjust=False).mean()
    return pd.DataFrame({"asym": asym, "asym_ma": asym_ma}).dropna()


def rs_breakout(stock_close: pd.Series, idx_close: pd.Series, freq: str, lookback: int) -> tuple[bool, float]:
    s = stock_close.resample(freq).last().dropna()
    i = idx_close.resample(freq).last().dropna()
    df = pd.concat([s, i], axis=1, join="inner").dropna()
    if len(df) < lookback + 2:
        return False, np.nan
    rs = np.log(df.iloc[:, 0] / df.iloc[:, 1])
    prior_max = rs.iloc[-(lookback + 1):-1].max()
    current = rs.iloc[-1]
    return bool(current > prior_max), float(current - prior_max)


def prior_relative_return(close: pd.Series, idx_close: pd.Series, weeks: int = 26) -> float:
    """Log-RS gain over the prior `weeks` weeks vs the most recent week."""
    s = close.resample("W-FRI").last().dropna()
    i = idx_close.resample("W-FRI").last().dropna()
    df = pd.concat([s, i], axis=1, join="inner").dropna()
    if len(df) < weeks + 2:
        return np.nan
    rs = np.log(df.iloc[:, 0] / df.iloc[:, 1])
    return float(rs.iloc[-1] - rs.iloc[-weeks])


def screen_rs_and_asymmetry(daily: pd.DataFrame, idx_close: pd.Series, tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            close = daily["Close"][t].dropna()
        except KeyError:
            continue
        if len(close) < 260:
            continue

        ok_w, mw = rs_breakout(close, idx_close, "W-FRI", RS_LOOKBACK_W)
        ok_m, mm = rs_breakout(close, idx_close, "ME",    RS_LOOKBACK_M)
        prior_rs_26w = prior_relative_return(close, idx_close, weeks=26)

        # Screen 2: volatility asymmetry on weekly + monthly bars
        wbars = resample_ohlc(daily, t, "W-FRI")
        mbars = resample_ohlc(daily, t, "ME")
        if len(wbars) < ASYM_PERIOD + ASYM_SMOOTH + 5 or len(mbars) < ASYM_PERIOD + 2:
            continue
        wa = asymmetry(wbars)
        ma = asymmetry(mbars)
        if wa.empty or ma.empty:
            continue
        w_now, w_ma_now = wa["asym"].iloc[-1], wa["asym_ma"].iloc[-1]
        m_now = ma["asym"].iloc[-1]
        # Rising: last N bars strictly higher than prior bar
        recent = wa["asym"].iloc[-(WEEKLY_ASYM_RISING_BARS + 1):]
        weekly_rising = bool((recent.diff().dropna() > 0).all())
        weekly_above_ma = bool(w_now > w_ma_now)
        weekly_low = bool(w_now <= WEEKLY_ASYM_LOW_MAX)
        monthly_balanced = bool(MONTHLY_ASYM_BAND[0] <= m_now <= MONTHLY_ASYM_BAND[1])

        rows.append(dict(
            ticker=t,
            rs_w=ok_w, rs_m=ok_m, w_margin=mw, m_margin=mm,
            prior_rs_26w=prior_rs_26w,
            asym_w=float(w_now), asym_w_ma=float(w_ma_now),
            asym_m=float(m_now),
            w_rising=weekly_rising, w_above_ma=weekly_above_ma,
            w_low=weekly_low, m_balanced=monthly_balanced,
            score=(mw if not np.isnan(mw) else 0) + (mm if not np.isnan(mm) else 0),
        ))

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["pass_rs"] = df.rs_w & df.rs_m
    # Qullamaggie pre-breakout setup: prior strong RS run, then a tight base
    # (monthly asym near 50, weekly rising/above MA/low). Requires positive
    # 26-week relative return so we only see "consolidation after uptrend",
    # not "stopped declining."
    prior_uptrend = df.prior_rs_26w > 0.10
    df["pass_setup"] = (
        df.w_rising & df.w_above_ma & df.w_low & df.m_balanced & prior_uptrend
    )
    # Aligned breakout: weekly RS breakout, monthly asym still in 40-60 band,
    # weekly asym rising and above its MA (drop "low" since RS breakout implies
    # asym is already lifting).
    m_band = (df.asym_m >= 40) & (df.asym_m <= 60)
    df["pass_aligned"] = df.rs_w & df.w_rising & df.w_above_ma & m_band
    df["pass_strict"] = df.pass_rs & df.pass_setup
    return df.sort_values("score", ascending=False)


def max_independent_set(survivors: pd.DataFrame, daily: pd.DataFrame, eps: float = CORR_EPS) -> pd.DataFrame:
    tickers = survivors.ticker.tolist()
    if len(tickers) <= 1:
        return survivors.assign(selected=True)
    closes = daily["Close"][tickers]
    weekly_ret = closes.resample("W-FRI").last().pct_change().dropna()
    corr = weekly_ret.corr().abs()
    survivors = survivors.set_index("ticker")
    chosen: list[str] = []
    for t in survivors.sort_values("score", ascending=False).index:
        if all(corr.loc[t, c] <= eps for c in chosen):
            chosen.append(t)
    survivors["selected"] = survivors.index.isin(chosen)
    return survivors.reset_index()


def diagnostics(selected: list[str], daily: pd.DataFrame) -> dict:
    if len(selected) < 2:
        return {"n": len(selected)}
    weekly_ret = daily["Close"][selected].resample("W-FRI").last().pct_change().dropna()
    cov = weekly_ret.cov().values
    eig = np.linalg.eigvalsh(cov)
    n_eff = (np.trace(cov) ** 2) / np.trace(cov @ cov)
    corr = weekly_ret.corr().values
    iu = np.triu_indices_from(corr, k=1)
    return {
        "n": len(selected),
        "mean_|corr|": float(np.mean(np.abs(corr[iu]))),
        "max_|corr|":  float(np.max(np.abs(corr[iu]))),
        "N_eff_bets":  float(n_eff),
        "top_eigenvalue_share": float(eig.max() / eig.sum()),
    }


def main() -> None:
    try:
        universe = fetch_sp600_universe()
        print(f"Fetched {len(universe)} tickers from IJR holdings.", file=sys.stderr)
    except Exception as e:
        print(f"IJR fetch failed ({e}); aborting.", file=sys.stderr)
        sys.exit(1)

    daily = fetch_ohlc(universe + [INDEX], period="24mo")
    if INDEX not in daily["Close"].columns:
        raise SystemExit(f"Index {INDEX} missing from data.")
    idx_close = daily["Close"][INDEX]
    tickers = [t for t in universe if t in daily["Close"].columns]

    df = screen_rs_and_asymmetry(daily, idx_close, tickers)
    print(f"\nUniverse evaluated: {len(df)}")
    print(f"  Pass weekly+monthly RS breakout:       {int(df.pass_rs.sum())}")
    print(f"  Pass Qullamaggie setup (asym only):    {int(df.pass_setup.sum())}")
    print(f"  Pass strict (RS + setup):              {int(df.pass_strict.sum())}")
    print(f"  Pass aligned breakout (RS_w + bal asym): {int(df.pass_aligned.sum())}")

    cols = ["ticker", "w_margin", "m_margin", "prior_rs_26w", "asym_w", "asym_w_ma", "asym_m", "score"]

    for label, key in [
        ("Mode A: pre-breakout setup (asym only)", "pass_setup"),
        ("Mode B: aligned breakout (weekly RS + balanced monthly asym)", "pass_aligned"),
        ("Mode C: strict (both RS TFs + full asym pattern)", "pass_strict"),
    ]:
        survivors = df[df[key]].copy()
        print(f"\n=== {label} — {len(survivors)} survivors ===")
        if survivors.empty:
            print("(none)")
            continue
        print(survivors[cols].head(40).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

        final = max_independent_set(survivors, daily, eps=CORR_EPS)
        selected = final[final.selected].ticker.tolist()
        print(f"\n  Uncorrelated portfolio (|weekly corr| <= {CORR_EPS}): {len(selected)} names")
        print(final[final.selected][cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

        diag = diagnostics(selected, daily)
        print("  Diagnostics:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in diag.items()})


if __name__ == "__main__":
    main()
