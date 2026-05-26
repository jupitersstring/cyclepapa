"""
Crypto Mean Reversion (MR) Engine — TD Sequential leg.

Direct port of the Pine v5 "Enhanced MTF TD Sequential" methodology
(c) malikmck, MPL-2.0. Nothing is omitted from the original methodology:
every measure (setup, countdown, perfection, aggressive count, volume
confirmation, Fibonacci recycle, price flip, stealth, double, triple,
risk lines, composite, z-score) is computed.

Per the user-selected style ticks, only the following measures feed the
final MR rank (`net_signal`):
    - Net Setup
    - Net Countdown
    - Net Perfect
    - Net Stealth Setup
    - Net Triple Setup
The remaining nets (Composite, Composite Z-Score, Aggressive, Recycle,
Price Flip, Double Setup) are computed and exposed on the result object
for transparency, but are NOT included in the rank.

Timeframes (intraday → monthly): 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1mo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Pine inputs — defaults mirror the screenshots
# ---------------------------------------------------------------------------

TIMEFRAMES: List[Tuple[str, str]] = [
    # (label,  yfinance interval)
    ("1m",  "1m"),
    ("5m",  "5m"),
    ("15m", "15m"),
    ("1h",  "60m"),
    ("4h",  "4h"),     # resampled from 60m
    ("1d",  "1d"),
    ("1w",  "1wk"),
    ("1mo", "1mo"),    # extension to monthly
]

VOLUME_THRESHOLD = 1.5
FIB_FACTOR = 1.618
RISK_FACTOR = 1.0
Z_LENGTH = 20

# Fibonacci constants from Pine — preserved verbatim.
PHI = (math.sqrt(5) + 1) / 2
FI2 = PHI + 1
FI3 = FI2 + PHI
FI4 = FI3 + FI2
FA = PHI - 1
FB = math.sqrt(FA)
FC = math.sqrt(FB)
FD = 0.5
FE = FA ** 2
FF = FA ** 3
FG = FA ** 4

# Measures that feed the final MR rank (user-ticked in Style tab).
TICKED_MEASURES: Tuple[str, ...] = (
    "setup",
    "countdown",
    "perfect",
    "stealth",
    "triple",
)
# Full methodology measures (used for the composite / completeness).
ALL_MEASURES: Tuple[str, ...] = TICKED_MEASURES + (
    "aggressive",
    "recycle",
    "price_flip",
    "double",
)

# Per-measure max value used for normalising to a 0-100 proportion, matching
# Pine: setup count maxes at 9, countdown at 13, the rest are 0/1 booleans.
MEASURE_MAX: Dict[str, int] = {
    "setup": 9,
    "countdown": 13,
    "perfect": 1,
    "aggressive": 1,
    "recycle": 1,
    "price_flip": 1,
    "stealth": 1,
    "double": 1,
    "triple": 1,
}


# ---------------------------------------------------------------------------
# TD Sequential — per-timeframe computation
# ---------------------------------------------------------------------------


@dataclass
class TDSeqFrame:
    """All TD Sequential measures for a single timeframe."""
    index: pd.DatetimeIndex
    bull_count: pd.Series
    bear_count: pd.Series
    cd_buy: pd.Series
    cd_sell: pd.Series
    buy_perfect: pd.Series
    sell_perfect: pd.Series
    buy_aggressive: pd.Series
    sell_aggressive: pd.Series
    vol_confirmed: pd.Series
    recycle_buy: pd.Series
    recycle_sell: pd.Series
    price_flip_up: pd.Series
    price_flip_down: pd.Series
    stealth_buy: pd.Series
    stealth_sell: pd.Series
    double_buy: pd.Series
    double_sell: pd.Series
    triple_buy: pd.Series
    triple_sell: pd.Series
    buy_risk: pd.Series
    sell_risk: pd.Series

    def buy(self, measure: str) -> pd.Series:
        return {
            "setup": self.bull_count,
            "countdown": self.cd_buy,
            "perfect": self.buy_perfect,
            "aggressive": self.buy_aggressive,
            "recycle": self.recycle_buy,
            "price_flip": self.price_flip_up,
            "stealth": self.stealth_buy,
            "double": self.double_buy,
            "triple": self.triple_buy,
        }[measure]

    def sell(self, measure: str) -> pd.Series:
        return {
            "setup": self.bear_count,
            "countdown": self.cd_sell,
            "perfect": self.sell_perfect,
            "aggressive": self.sell_aggressive,
            "recycle": self.recycle_sell,
            "price_flip": self.price_flip_down,
            "stealth": self.stealth_sell,
            "double": self.double_sell,
            "triple": self.triple_sell,
        }[measure]


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def td_sequential(df: pd.DataFrame) -> TDSeqFrame:
    """
    Compute the full TD Sequential family for one timeframe.

    `df` is expected to be OHLCV with lower-case columns
    (open, high, low, close, volume) and a DatetimeIndex aligned to the
    target timeframe (no resampling done here).
    """
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)

    n = len(c)
    h_arr = h.to_numpy()
    l_arr = l.to_numpy()
    c_arr = c.to_numpy()
    c4 = c.shift(4).to_numpy()

    bull = np.zeros(n)
    bear = np.zeros(n)
    cd_b = np.zeros(n, dtype=int)
    cd_s = np.zeros(n, dtype=int)
    setup_high = np.full(n, np.nan)
    setup_low = np.full(n, np.nan)

    cur_setup_high = np.nan
    cur_setup_low = np.nan

    for i in range(n):
        if i >= 4 and not np.isnan(c4[i]):
            if c_arr[i] < c4[i]:
                bull[i] = bull[i - 1] + 1 if bull[i - 1] < 9 else 1
            else:
                bull[i] = 0
            if c_arr[i] > c4[i]:
                bear[i] = bear[i - 1] + 1 if bear[i - 1] < 9 else 1
            else:
                bear[i] = 0

        if i > 0:
            cd_b[i] = cd_b[i - 1]
            cd_s[i] = cd_s[i - 1]

        if bull[i] == 9:
            cd_b[i] = 1
        elif i >= 2 and cd_b[i - 1] > 0 and cd_b[i - 1] < 13 and c_arr[i] < l_arr[i - 2]:
            cd_b[i] = cd_b[i - 1] + 1

        if bear[i] == 9:
            cd_s[i] = 1
        elif i >= 2 and cd_s[i - 1] > 0 and cd_s[i - 1] < 13 and c_arr[i] > h_arr[i - 2]:
            cd_s[i] = cd_s[i - 1] + 1

        if bull[i] == 9 and i >= 8:
            cur_setup_high = float(np.nanmax(h_arr[i - 8 : i + 1]))
        if bear[i] == 9 and i >= 8:
            cur_setup_low = float(np.nanmin(l_arr[i - 8 : i + 1]))
        setup_high[i] = cur_setup_high
        setup_low[i] = cur_setup_low

    idx = df.index
    bull_s = pd.Series(bull, index=idx)
    bear_s = pd.Series(bear, index=idx)
    cd_b_s = pd.Series(cd_b, index=idx)
    cd_s_s = pd.Series(cd_s, index=idx)
    setup_high_s = pd.Series(setup_high, index=idx)
    setup_low_s = pd.Series(setup_low, index=idx)

    l2, l3 = l.shift(2), l.shift(3)
    h2, h3 = h.shift(2), h.shift(3)
    c1, c4_s, c5 = c.shift(1), c.shift(4), c.shift(5)

    buy_perfect = ((bull_s == 9) & (l < l2) & (l < l3)).astype(int)
    sell_perfect = ((bear_s == 9) & (h > h2) & (h > h3)).astype(int)

    buy_aggressive = (c < l2).astype(int)
    sell_aggressive = (c > h2).astype(int)

    vol_confirmed = (v > v.rolling(20).mean() * VOLUME_THRESHOLD).fillna(False).astype(int)

    recycle_buy = ((setup_high_s.notna()) & (h > setup_high_s * FIB_FACTOR)).astype(int)
    recycle_sell = ((setup_low_s.notna()) & (l < setup_low_s / FIB_FACTOR)).astype(int)

    price_flip_up = ((c <= c4_s) & (c1 > c5)).astype(int)
    price_flip_down = ((c > c4_s) & (c1 < c5)).astype(int)

    stealth_buy = ((bull_s.shift(1) == 8) & (l <= c4_s) & (bull_s != 9)).astype(int)
    stealth_sell = ((bear_s.shift(1) == 8) & (h >= c4_s) & (bear_s != 9)).astype(int)

    # Pine valuewhen(bull_count[1]==9, bull_count, 1) returns 9 iff a prior
    # setup has completed; ,2 iff two priors. Equivalent: count of completions
    # strictly before the current bar must be >= 1 / >= 2.
    completes_buy = (bull_s == 9).astype(int).to_numpy()
    completes_sell = (bear_s == 9).astype(int).to_numpy()
    prior_buy = np.concatenate(([0], np.cumsum(completes_buy)[:-1]))
    prior_sell = np.concatenate(([0], np.cumsum(completes_sell)[:-1]))
    double_buy = ((bull_s == 9) & (prior_buy >= 1)).astype(int)
    double_sell = ((bear_s == 9) & (prior_sell >= 1)).astype(int)
    triple_buy = ((bull_s == 9) & (prior_buy >= 2)).astype(int)
    triple_sell = ((bear_s == 9) & (prior_sell >= 2)).astype(int)

    tr = _true_range(h, l, c)
    lowest_9 = l.rolling(9).min()
    highest_9 = h.rolling(9).max()
    buy_risk = pd.Series(np.where(bull_s == 9, lowest_9 - tr * RISK_FACTOR, np.nan), index=idx)
    sell_risk = pd.Series(np.where(bear_s == 9, highest_9 + tr * RISK_FACTOR, np.nan), index=idx)

    return TDSeqFrame(
        index=idx,
        bull_count=bull_s, bear_count=bear_s,
        cd_buy=cd_b_s, cd_sell=cd_s_s,
        buy_perfect=buy_perfect, sell_perfect=sell_perfect,
        buy_aggressive=buy_aggressive, sell_aggressive=sell_aggressive,
        vol_confirmed=vol_confirmed,
        recycle_buy=recycle_buy, recycle_sell=recycle_sell,
        price_flip_up=price_flip_up, price_flip_down=price_flip_down,
        stealth_buy=stealth_buy, stealth_sell=stealth_sell,
        double_buy=double_buy, double_sell=double_sell,
        triple_buy=triple_buy, triple_sell=triple_sell,
        buy_risk=buy_risk, sell_risk=sell_risk,
    )


# ---------------------------------------------------------------------------
# Per-timeframe rank (snapshot of latest bar)
# ---------------------------------------------------------------------------


@dataclass
class TFRank:
    """Snapshot rank for one timeframe at the latest bar."""
    tf: str
    # Per-measure buy / sell raw values (latest bar).
    buy: Dict[str, float]
    sell: Dict[str, float]
    # Per-measure buy / sell as 0..100 proportions (Pine-style).
    buy_prop: Dict[str, float]
    sell_prop: Dict[str, float]
    vol_confirmed: int
    # Net per measure (buy_prop - sell_prop).
    net: Dict[str, float]
    # Net signal restricted to ticked measures.
    net_signal: float
    # Net signal across all measures (composite, methodology-complete).
    net_composite_full: float


def per_tf_rank(tf_label: str, frame: TDSeqFrame) -> TFRank:
    last = -1
    buy_raw = {m: float(frame.buy(m).iloc[last]) for m in ALL_MEASURES}
    sell_raw = {m: float(frame.sell(m).iloc[last]) for m in ALL_MEASURES}
    buy_prop = {m: (buy_raw[m] / MEASURE_MAX[m]) * 100.0 for m in ALL_MEASURES}
    sell_prop = {m: (sell_raw[m] / MEASURE_MAX[m]) * 100.0 for m in ALL_MEASURES}
    net = {m: buy_prop[m] - sell_prop[m] for m in ALL_MEASURES}
    net_signal = float(np.mean([net[m] for m in TICKED_MEASURES]))
    net_composite_full = float(np.mean([net[m] for m in ALL_MEASURES]))
    vol_confirmed = int(frame.vol_confirmed.iloc[last]) if len(frame.vol_confirmed) else 0
    return TFRank(
        tf=tf_label,
        buy=buy_raw, sell=sell_raw,
        buy_prop=buy_prop, sell_prop=sell_prop,
        vol_confirmed=vol_confirmed,
        net=net,
        net_signal=net_signal,
        net_composite_full=net_composite_full,
    )


# ---------------------------------------------------------------------------
# Net across timeframes — Pine-style proportions
# ---------------------------------------------------------------------------


@dataclass
class MTFResult:
    """Net-across-timeframes MR rank at the latest bar."""
    timeframes: List[str]
    per_tf: Dict[str, TFRank]
    # Per-measure buy / sell proportions aggregated across TFs (Pine-style:
    # sum of measure across TFs / (n_tfs * measure_max) * 100).
    buy_prop: Dict[str, float]
    sell_prop: Dict[str, float]
    # Net per measure (buy_prop - sell_prop).
    net: Dict[str, float]
    # Top-level rolled-up signals.
    bullish_signal: float           # mean of buy_prop over TICKED_MEASURES
    bearish_signal: float
    net_signal: float               # bullish_signal - bearish_signal  (RANK)
    # Composite / z-score from the full methodology (for transparency only).
    bullish_composite: float
    bearish_composite: float
    net_composite: float
    volume_confirmed_prop: float
    # Optional historical net composite series (highest-freq grid) and its
    # z-score — kept for completeness; not part of the rank.
    net_composite_series: Optional[pd.Series] = None
    net_composite_z: Optional[pd.Series] = None


def aggregate_across_tfs(per_tf: Dict[str, TDSeqFrame]) -> MTFResult:
    """
    Aggregate per-timeframe TD Sequential frames into a single MR rank.

    Pine proportions are reproduced exactly: for each measure we sum the
    latest-bar value across timeframes and divide by `n_tfs * measure_max`,
    times 100. The final `net_signal` (the MR rank) is the mean of the net
    proportions for the ticked measures only.
    """
    tfs = list(per_tf.keys())
    n = len(tfs)
    if n == 0:
        raise ValueError("No timeframes provided")

    ranks = {tf: per_tf_rank(tf, fr) for tf, fr in per_tf.items()}

    buy_prop: Dict[str, float] = {}
    sell_prop: Dict[str, float] = {}
    for m in ALL_MEASURES:
        buy_sum = sum(ranks[tf].buy[m] for tf in tfs)
        sell_sum = sum(ranks[tf].sell[m] for tf in tfs)
        denom = n * MEASURE_MAX[m]
        buy_prop[m] = buy_sum / denom * 100.0
        sell_prop[m] = sell_sum / denom * 100.0
    net = {m: buy_prop[m] - sell_prop[m] for m in ALL_MEASURES}

    vol_confirmed_prop = (
        sum(ranks[tf].vol_confirmed for tf in tfs) / n * 100.0
    )

    bullish_signal = float(np.mean([buy_prop[m] for m in TICKED_MEASURES]))
    bearish_signal = float(np.mean([sell_prop[m] for m in TICKED_MEASURES]))
    net_signal = bullish_signal - bearish_signal

    bullish_signal_full = float(np.mean([buy_prop[m] for m in ALL_MEASURES]))
    bearish_signal_full = float(np.mean([sell_prop[m] for m in ALL_MEASURES]))
    bullish_composite = (bullish_signal_full * 2 + vol_confirmed_prop) / 3.0
    bearish_composite = (bearish_signal_full * 2 + vol_confirmed_prop) / 3.0
    net_composite = bullish_composite - bearish_composite

    return MTFResult(
        timeframes=tfs,
        per_tf=ranks,
        buy_prop=buy_prop,
        sell_prop=sell_prop,
        net=net,
        bullish_signal=bullish_signal,
        bearish_signal=bearish_signal,
        net_signal=net_signal,
        bullish_composite=bullish_composite,
        bearish_composite=bearish_composite,
        net_composite=net_composite,
        volume_confirmed_prop=vol_confirmed_prop,
    )


def aggregate_history(per_tf: Dict[str, TDSeqFrame]) -> pd.DataFrame:
    """
    Build a historical net-signal time series on the highest-frequency grid.

    Each lower-frequency timeframe is forward-filled onto the highest-freq
    index so the MTF net reflects the standing state at each high-freq bar.
    Returns a DataFrame with one column per measure plus `net_signal` and
    `net_composite` (the latter computed with `vol_confirmed_prop` per Pine).
    """
    tfs = list(per_tf.keys())
    n = len(tfs)
    if n == 0:
        raise ValueError("No timeframes provided")

    # Highest-frequency index = the TF with the most bars per unit time, which
    # in practice is the one with the densest DatetimeIndex.
    base_tf = max(tfs, key=lambda tf: len(per_tf[tf].index))
    base_idx = per_tf[base_tf].index

    def _align(series: pd.Series) -> pd.Series:
        return series.reindex(base_idx, method="ffill").fillna(0)

    sums_buy: Dict[str, pd.Series] = {
        m: sum(_align(per_tf[tf].buy(m)) for tf in tfs) for m in ALL_MEASURES
    }
    sums_sell: Dict[str, pd.Series] = {
        m: sum(_align(per_tf[tf].sell(m)) for tf in tfs) for m in ALL_MEASURES
    }
    vol_sum = sum(_align(per_tf[tf].vol_confirmed) for tf in tfs)

    out = pd.DataFrame(index=base_idx)
    for m in ALL_MEASURES:
        denom = n * MEASURE_MAX[m]
        out[f"buy_{m}_prop"] = sums_buy[m] / denom * 100.0
        out[f"sell_{m}_prop"] = sums_sell[m] / denom * 100.0
        out[f"net_{m}"] = out[f"buy_{m}_prop"] - out[f"sell_{m}_prop"]
    out["volume_confirmed_prop"] = vol_sum / n * 100.0

    out["bullish_signal"] = out[[f"buy_{m}_prop" for m in TICKED_MEASURES]].mean(axis=1)
    out["bearish_signal"] = out[[f"sell_{m}_prop" for m in TICKED_MEASURES]].mean(axis=1)
    out["net_signal"] = out["bullish_signal"] - out["bearish_signal"]

    bull_full = out[[f"buy_{m}_prop" for m in ALL_MEASURES]].mean(axis=1)
    bear_full = out[[f"sell_{m}_prop" for m in ALL_MEASURES]].mean(axis=1)
    out["bullish_composite"] = (bull_full * 2 + out["volume_confirmed_prop"]) / 3.0
    out["bearish_composite"] = (bear_full * 2 + out["volume_confirmed_prop"]) / 3.0
    out["net_composite"] = out["bullish_composite"] - out["bearish_composite"]

    ma = out["net_composite"].rolling(Z_LENGTH).mean()
    sd = out["net_composite"].rolling(Z_LENGTH).std()
    out["net_composite_z"] = (out["net_composite"] - ma) / sd
    return out


# ---------------------------------------------------------------------------
# Data fetching — multi-timeframe crypto OHLCV via yfinance
# ---------------------------------------------------------------------------


# yfinance window limits by interval (its docs / runtime errors).
_YF_PERIOD_FOR_INTERVAL = {
    "1m":  "7d",
    "2m":  "60d",
    "5m":  "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h":  "730d",
    "1d":  "max",
    "5d":  "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    cols = {"open", "high", "low", "close", "volume"}
    missing = cols - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}")
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    return df


def fetch_multitf(symbol: str, timeframes: Optional[List[Tuple[str, str]]] = None) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for `symbol` (e.g. "BTC-USD") at every configured timeframe.
    Returns a dict keyed by the human label ("1m", "5m", ...).

    4h is resampled from 60m since yfinance has no native 4h bar.
    """
    import yfinance as yf  # local import: keeps the engine import-light

    if timeframes is None:
        timeframes = TIMEFRAMES
    out: Dict[str, pd.DataFrame] = {}
    for label, interval in timeframes:
        if label == "4h":
            base = yf.download(
                symbol,
                period=_YF_PERIOD_FOR_INTERVAL.get("60m", "60d"),
                interval="60m",
                progress=False,
                auto_adjust=False,
            )
            if base is None or base.empty:
                continue
            base = _normalise_ohlcv(base)
            resampled = base.resample("4h").agg({
                "open": "first", "high": "max", "low": "min",
                "close": "last", "volume": "sum",
            }).dropna()
            out[label] = resampled
            continue

        period = _YF_PERIOD_FOR_INTERVAL.get(interval, "max")
        data = yf.download(
            symbol, period=period, interval=interval,
            progress=False, auto_adjust=False,
        )
        if data is None or data.empty:
            continue
        out[label] = _normalise_ohlcv(data)
    return out


# ---------------------------------------------------------------------------
# Top-level entry: full MR rank for a symbol
# ---------------------------------------------------------------------------


def run_mr(symbol: str, with_history: bool = False) -> Tuple[MTFResult, Optional[pd.DataFrame]]:
    """
    Run the full MR engine for `symbol`. Returns the latest-bar MTF rank and
    optionally a historical net-signal DataFrame on the highest-freq grid.
    """
    raw = fetch_multitf(symbol)
    per_tf = {label: td_sequential(df) for label, df in raw.items() if len(df) > 30}
    if not per_tf:
        raise RuntimeError(f"No usable OHLCV data fetched for {symbol}")
    snapshot = aggregate_across_tfs(per_tf)
    history = aggregate_history(per_tf) if with_history else None
    if history is not None:
        snapshot.net_composite_series = history["net_composite"]
        snapshot.net_composite_z = history["net_composite_z"]
    return snapshot, history


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------


def rank_table(result: MTFResult) -> pd.DataFrame:
    """
    Build a per-timeframe rank table whose columns are the ticked measures
    (net values per TF) plus a `net_signal` column = mean across ticked.
    Bottom row "NET" shows the across-TF Pine-style proportion nets.
    """
    rows = []
    for tf in result.timeframes:
        r = result.per_tf[tf]
        row = {"timeframe": tf}
        for m in TICKED_MEASURES:
            row[f"net_{m}"] = r.net[m]
        row["net_signal"] = r.net_signal
        row["vol_confirmed"] = r.vol_confirmed
        rows.append(row)
    df = pd.DataFrame(rows)
    net_row = {"timeframe": "NET"}
    for m in TICKED_MEASURES:
        net_row[f"net_{m}"] = result.net[m]
    net_row["net_signal"] = result.net_signal
    net_row["vol_confirmed"] = result.volume_confirmed_prop
    df = pd.concat([df, pd.DataFrame([net_row])], ignore_index=True)
    return df


def full_methodology_table(result: MTFResult) -> pd.DataFrame:
    """Diagnostic table showing every measure (ticked + unticked)."""
    rows = []
    for tf in result.timeframes:
        r = result.per_tf[tf]
        row = {"timeframe": tf}
        for m in ALL_MEASURES:
            row[f"net_{m}"] = r.net[m]
        row["net_signal_ticked"] = r.net_signal
        row["net_composite_full"] = r.net_composite_full
        row["vol_confirmed"] = r.vol_confirmed
        rows.append(row)
    net_row = {"timeframe": "NET"}
    for m in ALL_MEASURES:
        net_row[f"net_{m}"] = result.net[m]
    net_row["net_signal_ticked"] = result.net_signal
    net_row["net_composite_full"] = result.net_composite
    net_row["vol_confirmed"] = result.volume_confirmed_prop
    return pd.concat([pd.DataFrame(rows), pd.DataFrame([net_row])], ignore_index=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crypto MR engine — TD Sequential leg")
    parser.add_argument("symbol", nargs="?", default="BTC-USD")
    parser.add_argument("--full", action="store_true", help="Show full methodology table")
    args = parser.parse_args()

    snap, _ = run_mr(args.symbol)
    print(f"\n=== MR rank for {args.symbol} ===")
    print(f"net_signal (ticked-only)  : {snap.net_signal:+.2f}")
    print(f"net_composite (full)      : {snap.net_composite:+.2f}")
    print(f"vol_confirmed_prop        : {snap.volume_confirmed_prop:.1f}%\n")
    if args.full:
        print(full_methodology_table(snap).to_string(index=False))
    else:
        print(rank_table(snap).to_string(index=False))
