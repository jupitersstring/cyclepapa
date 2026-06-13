"""Event-study calibration harness.

The Phase 3 deliverable: walk the cleaned mention history day by day,
fire each candidate signal at each historical date, measure forward
N-day cumulative-abnormal-returns vs SPY, aggregate per signal type,
and apply Benjamini-Hochberg correction across the joint test set so
we know which signals survive multiple-testing inflation.

Output: a calibration report with, per signal:
  - n_events     : number of times the signal fired in-sample
  - mean_car_Nd  : mean forward N-day cumulative abnormal return
  - hit_rate     : fraction with car > 0
  - t_stat       : mean / (std / sqrt(n))
  - p_value      : two-sided p from the t-statistic
  - bh_q         : Benjamini-Hochberg adjusted q-value
  - deflated_sr  : Lopez de Prado deflated Sharpe (correcting for
                   multiple-trials inflation across the signal sweep)
  - verdict      : KEEP if bh_q < 0.10, FADE if mean_car < 0 & bh_q < 0.10,
                   else REJECT

Walk-forward split: events from the first 60% of history train, the
last 40% holds out (default; configurable).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


@dataclass
class CalibrationConfig:
    forward_days: tuple[int, ...] = (5, 20, 60)
    benchmark: str = "SPY"
    min_events_per_signal: int = 15
    train_frac: float = 0.6
    fdr_q: float = 0.10  # Benjamini-Hochberg FDR target
    # Signal sweep:
    breadth_min: tuple[int, ...] = (1, 2, 3)
    z_thresholds: tuple[float, ...] = (1.0, 1.5, 2.0)
    window_days: int = 5
    baseline_days: int = 30
    sample_every_days: int = 5   # sweep at this stride (fewer dates, faster)


def benjamini_hochberg(p_values: np.ndarray, fdr: float = 0.10) -> np.ndarray:
    """Return BH-adjusted q-values for the input p-values.

    Implements Benjamini & Hochberg (1995). Output q-values are the
    smallest FDR at which each test would be rejected; reject H0 wherever
    q <= the desired FDR.
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranks = np.arange(1, n + 1)
    q_sorted = p[order] * n / ranks
    # Enforce monotonicity (take running min from the back).
    q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]
    q = np.empty_like(q_sorted)
    q[order] = np.clip(q_sorted, 0.0, 1.0)
    return q


def _events_for_breadth(
    weighted_daily: pd.DataFrame,
    cfg: Config,
    *,
    z_thr: float,
    min_breadth: int,
    window_days: int,
    baseline_days: int,
    dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """Walk `dates`, fire the breadth signal at each, return events frame
    (date, ticker) for every firing."""
    from .breadth import breadth_score
    out: list[dict] = []
    for d in dates:
        try:
            firings = breadth_score(
                cfg, z_threshold=z_thr, window_days=window_days,
                baseline_days=baseline_days, min_breadth=min_breadth,
                top=500, as_of=d, df=weighted_daily,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("breadth_score failed at %s: %s", d, exc)
            continue
        if firings.empty:
            continue
        for t in firings["ticker"].unique():
            out.append({"date": d, "ticker": t})
    return pd.DataFrame(out)


def _load_weighted_daily(cfg: Config) -> pd.DataFrame:
    from .breadth import _load_weighted_daily as _lwd
    return _lwd(cfg)


def _build_dates(weighted: pd.DataFrame, every: int) -> list[pd.Timestamp]:
    """Sample evaluation dates from the mention history at stride `every`."""
    if weighted.empty:
        return []
    end = pd.to_datetime(weighted["date"]).max()
    start = pd.to_datetime(weighted["date"]).min() + pd.Timedelta(days=60)
    dates = pd.date_range(start=start, end=end, freq=f"{int(every)}D")
    return [d.normalize() for d in dates]


def _forward_car(
    prices: pd.DataFrame,
    bench: pd.Series,
    ticker: str,
    event_date: pd.Timestamp,
    horizon_days: int,
) -> float | None:
    """N-trading-day forward CAR for `ticker` after `event_date`.

    Uses the *next* trading day after event_date as the entry to avoid
    look-ahead bias.
    """
    if ticker not in prices.columns or bench.empty:
        return None
    px = prices[ticker].dropna()
    bx = bench.dropna()
    idx_loc = px.index.searchsorted(event_date, side="right")
    if idx_loc + horizon_days >= len(px) or idx_loc >= len(px):
        return None
    p0 = float(px.iloc[idx_loc])
    p1 = float(px.iloc[idx_loc + horizon_days])
    asset_ret = (p1 / p0) - 1.0
    bench_idx = bx.index.searchsorted(event_date, side="right")
    if bench_idx + horizon_days >= len(bx):
        return asset_ret
    b0 = float(bx.iloc[bench_idx])
    b1 = float(bx.iloc[bench_idx + horizon_days])
    bench_ret = (b1 / b0) - 1.0
    return asset_ret - bench_ret


def evaluate_events(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    bench: pd.Series,
    *,
    forward_days: tuple[int, ...] = (5, 20, 60),
) -> dict:
    """Compute per-horizon CARs for each event row.

    Returns dict: {horizon: pd.Series of CARs}.
    """
    out: dict[int, list[float]] = {h: [] for h in forward_days}
    if events.empty:
        return {h: pd.Series(dtype=float) for h in forward_days}
    for _, ev in events.iterrows():
        for h in forward_days:
            car = _forward_car(prices, bench, ev["ticker"], pd.Timestamp(ev["date"]), h)
            if car is not None and np.isfinite(car):
                out[h].append(car)
    return {h: pd.Series(v) for h, v in out.items()}


def summarize_horizon(cars: pd.Series, *, n_trials: int = 1) -> dict:
    """Mean / hit-rate / t / p / deflated SR over one horizon."""
    if cars.empty:
        return {
            "n": 0, "mean_car": np.nan, "median_car": np.nan,
            "hit_rate": np.nan, "t_stat": np.nan, "p_value": np.nan,
            "ann_sharpe": np.nan, "deflated_sr": np.nan,
        }
    from .backtest import deflated_sharpe
    mean = float(cars.mean())
    median = float(cars.median())
    std = float(cars.std(ddof=1)) if len(cars) > 1 else np.nan
    n = int(len(cars))
    t = mean / (std / np.sqrt(n)) if (std and std > 0) else 0.0
    # Two-sided p via normal approximation (n typically >> 30).
    from math import erfc, sqrt
    p = float(erfc(abs(t) / sqrt(2)))
    # Rough annualised Sharpe using event-window CAR std as proxy.
    sharpe = mean / std * np.sqrt(252.0 / max(1, len(cars))) if std and std > 0 else 0.0
    try:
        defl = float(deflated_sharpe(sharpe, n_trials=max(1, n_trials), n_obs=n))
    except Exception:  # noqa: BLE001
        defl = float("nan")
    return {
        "n": n, "mean_car": round(mean, 4), "median_car": round(median, 4),
        "hit_rate": round(float((cars > 0).mean()), 3),
        "t_stat": round(t, 2), "p_value": round(p, 4),
        "ann_sharpe": round(sharpe, 2),
        "deflated_sr": round(defl, 2) if np.isfinite(defl) else None,
    }


def calibrate(
    cfg: Config,
    *,
    config: CalibrationConfig | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run the full event-study sweep + multiple-testing correction.

    Returns a DataFrame with one row per (signal, horizon) and a verdict:
      KEEP   : positive mean CAR, BH q <= fdr_q
      FADE   : negative mean CAR, BH q <= fdr_q
      REJECT : did not survive multiple-testing correction
    """
    cfg_ = config or CalibrationConfig()
    weighted = _load_weighted_daily(cfg)
    if weighted.empty:
        log.warning("calibration: empty mention store")
        return pd.DataFrame()
    weighted["date"] = pd.to_datetime(weighted["date"])
    dates = _build_dates(weighted, cfg_.sample_every_days)
    if not dates:
        log.warning("calibration: no eval dates")
        return pd.DataFrame()

    # Load all prices for tickers appearing in events.
    if verbose:
        print(f"calibration: {len(dates)} evaluation dates "
              f"({dates[0].date()} -> {dates[-1].date()}), "
              f"stride={cfg_.sample_every_days}d")

    # 1. Build the signal sweep -- one entry per (z_threshold, min_breadth).
    signal_specs = [
        {"name": f"breadth_z{z}_b{b}", "z": z, "breadth": b}
        for z in cfg_.z_thresholds
        for b in cfg_.breadth_min
    ]
    if verbose:
        print(f"calibration: sweeping {len(signal_specs)} signal variants "
              f"x {len(cfg_.forward_days)} horizons "
              f"= {len(signal_specs) * len(cfg_.forward_days)} hypotheses")

    # 2. Build the full event list per signal.
    all_events: dict[str, pd.DataFrame] = {}
    for spec in signal_specs:
        ev = _events_for_breadth(
            weighted, cfg,
            z_thr=spec["z"], min_breadth=spec["breadth"],
            window_days=cfg_.window_days, baseline_days=cfg_.baseline_days,
            dates=dates,
        )
        if verbose:
            print(f"  {spec['name']}: {len(ev):,} events")
        all_events[spec["name"]] = ev

    # 3. Gather the price universe.
    all_tickers: set[str] = set()
    for ev in all_events.values():
        all_tickers |= set(ev["ticker"].unique()) if not ev.empty else set()
    if not all_tickers:
        log.warning("calibration: no events fired")
        return pd.DataFrame()
    if verbose:
        print(f"calibration: pulling price history for {len(all_tickers)} tickers")
    from .prices import daily_close
    from datetime import datetime, timedelta, timezone
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int((end_dt - dates[0]).days) + max(cfg_.forward_days) + 30)
    prices = {}
    for t in sorted(all_tickers):
        s = daily_close(t, start_dt, end_dt)
        if not s.empty and len(s) >= 20:
            prices[t] = s
    if not prices:
        log.warning("calibration: no prices loaded")
        return pd.DataFrame()
    prices_df = pd.DataFrame(prices)
    bench = daily_close(cfg_.benchmark, start_dt, end_dt)
    if verbose:
        print(f"calibration: prices loaded for {prices_df.shape[1]} tickers, "
              f"benchmark {cfg_.benchmark} rows={len(bench)}")

    # 4. Walk-forward split: train on the first train_frac of dates.
    split_idx = int(len(dates) * cfg_.train_frac)
    train_cutoff = dates[split_idx]
    if verbose:
        print(f"calibration: walk-forward split at {train_cutoff.date()} "
              f"({cfg_.train_frac:.0%} train / {1 - cfg_.train_frac:.0%} test)")

    # 5. Evaluate each (signal, horizon) on TRAIN and TEST separately.
    rows: list[dict] = []
    for spec in signal_specs:
        ev = all_events[spec["name"]]
        if len(ev) < cfg_.min_events_per_signal:
            continue
        train_ev = ev[ev["date"] < train_cutoff]
        test_ev = ev[ev["date"] >= train_cutoff]
        for split_name, ev_split in (("train", train_ev), ("test", test_ev)):
            if len(ev_split) < cfg_.min_events_per_signal // 2:
                continue
            cars_per_horizon = evaluate_events(
                ev_split, prices_df, bench,
                forward_days=cfg_.forward_days,
            )
            for h in cfg_.forward_days:
                stats = summarize_horizon(
                    cars_per_horizon[h],
                    n_trials=len(signal_specs) * len(cfg_.forward_days),
                )
                rows.append({
                    "signal": spec["name"],
                    "split": split_name,
                    "horizon_d": h,
                    **stats,
                })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # 6. BH correction across all (signal, horizon, split) hypotheses.
    out = out.sort_values(["split", "signal", "horizon_d"]).reset_index(drop=True)
    # Compute BH only on TRAIN (test is for confirmation, not for selection).
    train_mask = out["split"] == "train"
    p_train = out.loc[train_mask, "p_value"].fillna(1.0).values
    q_train = benjamini_hochberg(p_train, fdr=cfg_.fdr_q)
    out["bh_q"] = np.nan
    out.loc[train_mask, "bh_q"] = q_train

    # 7. Verdict on train; report test-split CAR for confirmation.
    def _verdict(row):
        if row["split"] != "train":
            return ""
        if not np.isfinite(row.get("bh_q", np.nan)):
            return ""
        if row["bh_q"] > cfg_.fdr_q:
            return "REJECT"
        if row["mean_car"] > 0:
            return "KEEP"
        if row["mean_car"] < 0:
            return "FADE"
        return "REJECT"

    out["verdict"] = out.apply(_verdict, axis=1)
    return out
