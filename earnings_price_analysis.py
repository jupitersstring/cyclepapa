"""Earnings/fundamental growth -> price responsiveness analysis.

For a universe of stocks (default: US small caps via financedatabase), this
script measures how a stock's price responds to fundamental growth on the
margin and flags names where that responsiveness has recently inflected
positively.

Two flavors are computed in parallel:

  1. EPS-only:  trailing N-quarter EPS growth vs price.
  2. Composite: z-scored blend of trailing N-Q revenue, EBITDA, FCF growth
                vs price.

Each is computed against both absolute price (log) returns and price relative
to ^GSPC (log return spread). Optional smoothing on the price series.

Methodology
-----------
For each ticker on a per-quarter grid (aligned to fiscal quarter-ends):

  g_t   = TrailingSumLastN(metric_t) / TrailingSumPriorN(metric_t) - 1
  dg_t  = g_t - g_{t-1}
  r_t   = log(P_smooth_{t+1}) - log(P_smooth_t)   (forward 1Q return)
  r^*_t = r_t - r_spx_t                            (relative to SPX)

Then on a rolling window of W quarters we run OLS of r on dg and store the
slope beta_t (the marginal price-response sensitivity). Inflection is:

  inflection_z = mean(beta_{t-K+1..t}) - mean(beta_{t-2K+1..t-K})
                 ----------------------------------------------------
                                std(beta over full history)

Names where inflection_z is high AND the most recent beta is positive are
flagged.

Usage
-----
    python earnings_price_analysis.py \\
        --universe us_small_cap \\
        --growth-window 4 \\
        --beta-window 12 \\
        --inflection-lookback 4 \\
        --price-smooth-days 21 \\
        --max-tickers 500 \\
        --workers 8 \\
        --output-dir results/

Outputs CSVs per analysis variant (eps_absolute, eps_relative,
composite_absolute, composite_relative) and a combined ranked.csv.

Caches yfinance pulls to .cache/yf/<ticker>.parquet to avoid re-fetching on
re-runs. Delete .cache/ to force refresh.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

# yfinance + financedatabase imported lazily so import-time errors surface
# inside run() with a clearer message than at module load.
yf = None
fd = None


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class Config:
    """All tunable knobs for one run."""

    universe: str = "us_small_cap"
    growth_window: int = 4          # N: trailing N-Q sum used for growth base
    beta_window: int = 12           # W: rolling regression window (quarters)
    inflection_lookback: int = 4    # K: half-window for recent vs prior beta
    price_smooth_days: int = 21     # rolling mean applied to daily close
    min_quarters: int = 16          # require >= this many quarters of data
    benchmark: str = "^GSPC"
    history_period: str = "max"     # passed to yfinance for prices
    max_tickers: Optional[int] = None
    workers: int = 8
    request_sleep: float = 0.10     # pause between yfinance calls (per worker)
    output_dir: Path = field(default_factory=lambda: Path("results"))
    cache_dir: Path = field(default_factory=lambda: Path(".cache/yf"))
    log_level: str = "INFO"
    inflection_threshold: float = 1.0   # min z-score to flag as inflected
    market_cap_buckets: tuple[str, ...] = ("Small Cap",)
    countries: tuple[str, ...] = ("United States",)
    exchanges: Optional[tuple[str, ...]] = None  # e.g. ("NASDAQ","NYSE")


log = logging.getLogger("earnings_price")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)


def lazy_imports() -> None:
    """Import heavy deps lazily so --help works without them."""
    global yf, fd
    import yfinance as _yf
    import financedatabase as _fd
    yf = _yf
    fd = _fd


# --------------------------------------------------------------------------- #
# Universe loading                                                            #
# --------------------------------------------------------------------------- #


def load_universe(cfg: Config) -> list[str]:
    """Return list of tickers for the requested universe."""
    log.info("loading universe: %s", cfg.universe)

    equities = fd.Equities()
    selectors: dict[str, object] = {}
    if cfg.countries:
        selectors["country"] = list(cfg.countries) if len(cfg.countries) > 1 else cfg.countries[0]
    if cfg.market_cap_buckets:
        selectors["market_cap"] = (
            list(cfg.market_cap_buckets)
            if len(cfg.market_cap_buckets) > 1
            else cfg.market_cap_buckets[0]
        )
    if cfg.exchanges:
        selectors["exchange"] = list(cfg.exchanges) if len(cfg.exchanges) > 1 else cfg.exchanges[0]

    df = equities.select(**selectors)
    # financedatabase returns a DataFrame indexed by symbol
    tickers = [t for t in df.index.tolist() if isinstance(t, str) and t]
    # Drop obvious junk: tickers with spaces, dots used for share classes are
    # generally fine on yfinance (BRK.B becomes BRK-B). Convert "." to "-".
    cleaned: list[str] = []
    seen: set[str] = set()
    for t in tickers:
        t2 = t.replace(".", "-").upper().strip()
        if not t2 or " " in t2 or t2 in seen:
            continue
        seen.add(t2)
        cleaned.append(t2)

    log.info("universe size: %d tickers", len(cleaned))
    if cfg.max_tickers:
        cleaned = cleaned[: cfg.max_tickers]
        log.info("truncated to first %d tickers", len(cleaned))
    return cleaned


# --------------------------------------------------------------------------- #
# yfinance fetch (with on-disk cache)                                         #
# --------------------------------------------------------------------------- #


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _cache_path(cfg: Config, ticker: str, kind: str) -> Path:
    return cfg.cache_dir / f"{_safe_filename(ticker)}__{kind}.parquet"


def _read_cache(cfg: Config, ticker: str, kind: str, max_age_days: int = 7) -> Optional[pd.DataFrame]:
    path = _cache_path(cfg, ticker, kind)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age_days * 86400:
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:                # corrupt cache file
        log.debug("cache read failed for %s/%s: %s", ticker, kind, exc)
        return None


def _write_cache(cfg: Config, ticker: str, kind: str, df: pd.DataFrame) -> None:
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(_cache_path(cfg, ticker, kind))
    except Exception as exc:
        log.debug("cache write failed for %s/%s: %s", ticker, kind, exc)


def _with_retries(fn, *args, attempts: int = 3, base_sleep: float = 1.0, **kwargs):
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            time.sleep(base_sleep * (2 ** i))
    raise last_exc  # type: ignore[misc]


def fetch_fundamentals(cfg: Config, ticker: str) -> dict[str, pd.DataFrame]:
    """Return dict with 'income', 'cashflow' quarterly DataFrames.

    Each DataFrame has dates as the index (most recent at bottom) and metric
    names as columns. Empty DataFrame on failure rather than raising.
    """
    out: dict[str, pd.DataFrame] = {}
    for kind, attr in (("income", "quarterly_income_stmt"), ("cashflow", "quarterly_cashflow")):
        cached = _read_cache(cfg, ticker, kind)
        if cached is not None:
            out[kind] = cached
            continue
        try:
            t = yf.Ticker(ticker)
            df = _with_retries(getattr, t, attr)
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                df = pd.DataFrame()
            else:
                # yfinance returns rows=metric, cols=date. Transpose to dates-index.
                df = df.T
                df.index = pd.to_datetime(df.index, errors="coerce")
                df = df[~df.index.isna()].sort_index()
            out[kind] = df
            _write_cache(cfg, ticker, kind, df)
        except Exception as exc:
            log.debug("fetch %s failed for %s: %s", kind, ticker, exc)
            out[kind] = pd.DataFrame()
        time.sleep(cfg.request_sleep)
    return out


def fetch_prices(cfg: Config, ticker: str) -> pd.Series:
    """Return adjusted close as a Series indexed by date."""
    cached = _read_cache(cfg, ticker, "price")
    if cached is not None and "Close" in cached.columns:
        s = cached["Close"]
        return s.dropna()
    try:
        t = yf.Ticker(ticker)
        hist = _with_retries(t.history, period=cfg.history_period, auto_adjust=True)
    except Exception as exc:
        log.debug("price fetch failed for %s: %s", ticker, exc)
        return pd.Series(dtype=float)
    if hist is None or hist.empty:
        return pd.Series(dtype=float)
    idx = pd.to_datetime(hist.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    hist.index = idx
    _write_cache(cfg, ticker, "price", hist[["Close"]])
    time.sleep(cfg.request_sleep)
    return hist["Close"].dropna()


def fetch_benchmark(cfg: Config) -> pd.Series:
    """Benchmark close series (e.g., ^GSPC)."""
    return fetch_prices(cfg, cfg.benchmark)


# --------------------------------------------------------------------------- #
# Metric extraction                                                           #
# --------------------------------------------------------------------------- #


def _first_existing(df: pd.DataFrame, names: Iterable[str]) -> Optional[pd.Series]:
    """Return the first column in `df` whose name matches one of `names`."""
    if df.empty:
        return None
    for name in names:
        if name in df.columns:
            s = pd.to_numeric(df[name], errors="coerce").dropna()
            if not s.empty:
                return s
    return None


EPS_FIELDS = ("Diluted EPS", "Basic EPS")
NET_INCOME_FIELDS = ("Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations")
DILUTED_SHARES_FIELDS = ("Diluted Average Shares", "Basic Average Shares")
REVENUE_FIELDS = ("Total Revenue", "Operating Revenue", "Revenue")
EBITDA_FIELDS = ("EBITDA", "Normalized EBITDA")
OP_INCOME_FIELDS = ("Operating Income", "Total Operating Income As Reported", "Operating Income Loss")
DA_FIELDS = ("Reconciled Depreciation", "Depreciation Amortization Depletion", "Depreciation And Amortization", "Depreciation")
FCF_FIELDS = ("Free Cash Flow",)
OCF_FIELDS = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Total Cash From Operating Activities")
CAPEX_FIELDS = ("Capital Expenditure", "Capital Expenditures")


def extract_metrics(funds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pull EPS, Revenue, EBITDA, FCF into one quarterly DataFrame.

    Columns: ['eps', 'revenue', 'ebitda', 'fcf'].
    Missing metrics result in NaN columns (caller handles).
    """
    inc = funds.get("income", pd.DataFrame())
    cf = funds.get("cashflow", pd.DataFrame())

    eps = _first_existing(inc, EPS_FIELDS)
    if eps is None:
        ni = _first_existing(inc, NET_INCOME_FIELDS)
        shares = _first_existing(inc, DILUTED_SHARES_FIELDS)
        if ni is not None and shares is not None:
            eps = (ni / shares.replace(0, np.nan)).dropna()

    revenue = _first_existing(inc, REVENUE_FIELDS)

    ebitda = _first_existing(inc, EBITDA_FIELDS)
    if ebitda is None:
        op_inc = _first_existing(inc, OP_INCOME_FIELDS)
        da = _first_existing(inc, DA_FIELDS)
        if op_inc is not None and da is not None:
            # CapEx and D&A are stored positive in yfinance; D&A adds back.
            ebitda = (op_inc.add(da.abs(), fill_value=np.nan)).dropna()

    fcf = _first_existing(cf, FCF_FIELDS)
    if fcf is None:
        ocf = _first_existing(cf, OCF_FIELDS)
        capex = _first_existing(cf, CAPEX_FIELDS)
        if ocf is not None and capex is not None:
            # yfinance stores CapEx as negative; OCF + CapEx = FCF.
            fcf = ocf.add(capex, fill_value=np.nan).dropna()

    cols = {"eps": eps, "revenue": revenue, "ebitda": ebitda, "fcf": fcf}
    parts = [s.rename(name) for name, s in cols.items() if s is not None]
    if not parts:
        return pd.DataFrame(columns=["eps", "revenue", "ebitda", "fcf"])

    out = pd.concat(parts, axis=1).sort_index()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    # Add missing columns so downstream always has the schema.
    for c in ("eps", "revenue", "ebitda", "fcf"):
        if c not in out.columns:
            out[c] = np.nan
    return out[["eps", "revenue", "ebitda", "fcf"]]


# --------------------------------------------------------------------------- #
# Growth and price prep                                                       #
# --------------------------------------------------------------------------- #


def trailing_n_growth(series: pd.Series, n: int) -> pd.Series:
    """Trailing N-quarter sum divided by prior N-quarter sum minus 1.

    For N=4 this is exactly TTM YoY growth. Resistant to a single bad quarter
    relative to single-quarter YoY since both halves are sums.

    For EPS where the level can be negative, growth from negative to positive
    (or vice versa) is computed but flagged via sign — we just return the raw
    ratio-1; consumers should be aware.
    """
    if series is None or series.empty:
        return pd.Series(dtype=float)
    s = series.dropna().astype(float)
    if len(s) < 2 * n:
        return pd.Series(dtype=float)
    last = s.rolling(n).sum()
    prior = last.shift(n)
    # Avoid div-by-zero; use absolute denominator so sign of growth still
    # reflects direction relative to prior magnitude.
    denom = prior.replace(0, np.nan).abs()
    growth = (last - prior) / denom
    return growth.dropna()


def smoothed_log_returns_at(prices: pd.Series, dates: pd.DatetimeIndex, smooth_days: int) -> pd.Series:
    """Forward 1-period log return on smoothed price, sampled at `dates`.

    "Forward 1-period" means r_t = log(P_{t+1}) - log(P_t) where t indexes
    `dates`. Smoothing is a centered rolling mean over `smooth_days`.
    """
    if prices is None or prices.empty or len(dates) < 2:
        return pd.Series(dtype=float)
    p = prices.sort_index().copy()
    # Normalize tz to align with fiscal dates (which arrive tz-naive).
    if getattr(p.index, "tz", None) is not None:
        p.index = p.index.tz_localize(None)
    if smooth_days and smooth_days > 1:
        p = p.rolling(window=smooth_days, min_periods=max(2, smooth_days // 2), center=False).mean()
    # Align by asof: for each fiscal date, take the most recent price.
    p_at = p.reindex(p.index.union(dates)).ffill().reindex(dates)
    log_p = np.log(p_at.replace(0, np.nan))
    return log_p.diff().shift(-1)  # forward return


# --------------------------------------------------------------------------- #
# Responsiveness + inflection                                                 #
# --------------------------------------------------------------------------- #


def _rolling_ols_slope(y: pd.Series, x: pd.Series, window: int) -> pd.Series:
    """Rolling OLS slope of y on x over `window` observations.

    Returns a Series aligned to y/x's index with NaN until window is full.
    Uses the closed-form cov(x,y) / var(x).
    """
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(df) < window:
        return pd.Series(index=y.index, dtype=float)
    cov_xy = df["x"].rolling(window).cov(df["y"])
    var_x = df["x"].rolling(window).var()
    slope = cov_xy / var_x.replace(0, np.nan)
    return slope.reindex(y.index)


def _rolling_corr(y: pd.Series, x: pd.Series, window: int) -> pd.Series:
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(df) < window:
        return pd.Series(index=y.index, dtype=float)
    return df["x"].rolling(window).corr(df["y"]).reindex(y.index)


@dataclass
class Responsiveness:
    latest_growth: float
    latest_delta_growth: float
    latest_beta: float
    latest_corr: float
    inflection_z: float
    n_quarters: int
    beta_history: pd.Series = field(repr=False)
    is_inflected: bool = False

    def to_row(self) -> dict[str, float | int | bool]:
        return {
            "latest_growth": self.latest_growth,
            "latest_delta_growth": self.latest_delta_growth,
            "latest_beta": self.latest_beta,
            "latest_corr": self.latest_corr,
            "inflection_z": self.inflection_z,
            "n_quarters": self.n_quarters,
            "is_inflected": self.is_inflected,
        }


def compute_responsiveness(
    growth: pd.Series,
    fwd_return: pd.Series,
    beta_window: int,
    lookback: int,
    inflection_threshold: float,
) -> Optional[Responsiveness]:
    """Run the rolling-beta + inflection pipeline for one (growth, return) pair."""
    if growth is None or fwd_return is None or growth.empty or fwd_return.empty:
        return None
    df = pd.concat([growth.rename("g"), fwd_return.rename("r")], axis=1).dropna()
    df["dg"] = df["g"].diff()
    df = df.dropna()
    if len(df) < beta_window + 2 * lookback:
        return None

    beta = _rolling_ols_slope(df["r"], df["dg"], beta_window)
    corr = _rolling_corr(df["r"], df["dg"], beta_window)

    beta_clean = beta.dropna()
    if len(beta_clean) < 2 * lookback:
        return None

    recent = beta_clean.iloc[-lookback:].mean()
    prior = beta_clean.iloc[-2 * lookback : -lookback].mean()
    std_full = beta_clean.std(ddof=0)
    z = (recent - prior) / std_full if std_full and not np.isnan(std_full) and std_full > 0 else np.nan

    latest_beta = beta_clean.iloc[-1]
    latest_corr = corr.dropna().iloc[-1] if not corr.dropna().empty else np.nan
    latest_growth = df["g"].iloc[-1]
    latest_dg = df["dg"].iloc[-1]

    return Responsiveness(
        latest_growth=float(latest_growth),
        latest_delta_growth=float(latest_dg),
        latest_beta=float(latest_beta),
        latest_corr=float(latest_corr) if pd.notna(latest_corr) else np.nan,
        inflection_z=float(z) if pd.notna(z) else np.nan,
        n_quarters=int(len(df)),
        beta_history=beta_clean,
        is_inflected=bool(pd.notna(z) and z >= inflection_threshold and latest_beta > 0),
    )


# --------------------------------------------------------------------------- #
# Composite (sales + EBITDA + FCF) growth                                     #
# --------------------------------------------------------------------------- #


def composite_growth(metrics: pd.DataFrame, n: int) -> pd.Series:
    """Z-scored equal-weight blend of revenue, EBITDA, FCF trailing N-Q growth.

    Each component is z-scored using its own full-sample mean/std before
    averaging so a high-vol component (FCF) doesn't dominate.
    """
    parts = []
    for col in ("revenue", "ebitda", "fcf"):
        g = trailing_n_growth(metrics[col], n)
        if g.empty:
            continue
        mu, sd = g.mean(), g.std(ddof=0)
        if not sd or np.isnan(sd) or sd == 0:
            continue
        parts.append(((g - mu) / sd).rename(col))
    if not parts:
        return pd.Series(dtype=float)
    blend = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    return blend.dropna()


# --------------------------------------------------------------------------- #
# Per-ticker analysis orchestration                                           #
# --------------------------------------------------------------------------- #


@dataclass
class TickerResult:
    ticker: str
    eps_abs: Optional[Responsiveness] = None
    eps_rel: Optional[Responsiveness] = None
    comp_abs: Optional[Responsiveness] = None
    comp_rel: Optional[Responsiveness] = None
    error: Optional[str] = None


def analyze_ticker(
    cfg: Config,
    ticker: str,
    bench_prices: pd.Series,
) -> TickerResult:
    res = TickerResult(ticker=ticker)
    try:
        funds = fetch_fundamentals(cfg, ticker)
        metrics = extract_metrics(funds)
        if metrics.empty or len(metrics) < cfg.min_quarters:
            res.error = f"insufficient fundamentals (have {len(metrics)})"
            return res

        prices = fetch_prices(cfg, ticker)
        if prices.empty:
            res.error = "no prices"
            return res

        # Fiscal-quarter dates (alignment grid).
        q_dates = pd.DatetimeIndex(sorted(metrics.index.unique()))

        # Absolute forward returns at fiscal dates.
        r_abs = smoothed_log_returns_at(prices, q_dates, cfg.price_smooth_days)
        # Benchmark return on same dates.
        r_bench = smoothed_log_returns_at(bench_prices, q_dates, cfg.price_smooth_days)
        r_rel = (r_abs - r_bench).dropna()

        # ---- EPS variant ----
        g_eps = trailing_n_growth(metrics["eps"], cfg.growth_window)
        if not g_eps.empty:
            res.eps_abs = compute_responsiveness(
                g_eps, r_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.eps_rel = compute_responsiveness(
                g_eps, r_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )

        # ---- Composite variant ----
        g_comp = composite_growth(metrics, cfg.growth_window)
        if not g_comp.empty:
            res.comp_abs = compute_responsiveness(
                g_comp, r_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.comp_rel = compute_responsiveness(
                g_comp, r_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
    except Exception as exc:                                  # one bad ticker shouldn't kill the run
        res.error = f"{type(exc).__name__}: {exc}"
        log.debug("analyze_ticker(%s) failed: %s", ticker, exc)
    return res


# --------------------------------------------------------------------------- #
# Output assembly                                                             #
# --------------------------------------------------------------------------- #


VARIANT_FIELDS = ("eps_abs", "eps_rel", "comp_abs", "comp_rel")


def results_to_frame(results: list[TickerResult]) -> pd.DataFrame:
    """Wide table: one row per ticker, one column block per variant."""
    rows: list[dict] = []
    for r in results:
        row: dict[str, object] = {"ticker": r.ticker, "error": r.error}
        for var in VARIANT_FIELDS:
            sub = getattr(r, var)
            if sub is None:
                for k in ("latest_growth", "latest_delta_growth", "latest_beta", "latest_corr", "inflection_z", "n_quarters", "is_inflected"):
                    row[f"{var}_{k}"] = np.nan
            else:
                for k, v in sub.to_row().items():
                    row[f"{var}_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")


def write_per_variant_csvs(df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    variant_to_name = {
        "eps_abs": "eps_absolute",
        "eps_rel": "eps_vs_spx",
        "comp_abs": "composite_absolute",
        "comp_rel": "composite_vs_spx",
    }
    for var, label in variant_to_name.items():
        cols = [c for c in df.columns if c.startswith(f"{var}_")]
        if not cols:
            continue
        sub = df[cols].copy()
        sub.columns = [c[len(var) + 1 :] for c in cols]
        sub = sub.sort_values("inflection_z", ascending=False)
        sub.to_csv(outdir / f"{label}.csv")
        log.info("wrote %s.csv (%d rows)", label, len(sub))


def write_ranked(df: pd.DataFrame, outdir: Path, threshold: float) -> None:
    """Combined ranking: avg inflection_z across the four variants for names
    flagged as inflected in >= 2 of them."""
    z_cols = [f"{v}_inflection_z" for v in VARIANT_FIELDS]
    flag_cols = [f"{v}_is_inflected" for v in VARIANT_FIELDS]
    avail = df[z_cols + flag_cols].copy()
    avail["avg_inflection_z"] = df[z_cols].mean(axis=1, skipna=True)
    avail["n_variants_inflected"] = df[flag_cols].fillna(False).astype(bool).sum(axis=1)
    ranked = avail.sort_values(
        ["n_variants_inflected", "avg_inflection_z"], ascending=[False, False]
    )
    ranked.to_csv(outdir / "ranked.csv")
    top = ranked[ranked["n_variants_inflected"] >= 2].head(40)
    log.info("ranked.csv written; %d names inflected in >= 2 variants", (ranked["n_variants_inflected"] >= 2).sum())
    if not top.empty:
        log.info("top inflecting names (n_variants_inflected >= 2):")
        for tkr, row in top.iterrows():
            log.info(
                "  %-8s  n_var=%d  avg_z=%.2f",
                tkr, int(row["n_variants_inflected"]), float(row["avg_inflection_z"]),
            )


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: Optional[list[str]] = None) -> Config:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="us_small_cap",
                   help="label for the run (used in logs only)")
    p.add_argument("--market-cap", nargs="+", default=["Small Cap"],
                   help="financedatabase market_cap buckets (Nano Cap, Micro Cap, Small Cap, Mid Cap, Large Cap, Mega Cap)")
    p.add_argument("--country", nargs="+", default=["United States"])
    p.add_argument("--exchange", nargs="+", default=None)
    p.add_argument("--growth-window", type=int, default=4)
    p.add_argument("--beta-window", type=int, default=12)
    p.add_argument("--inflection-lookback", type=int, default=4)
    p.add_argument("--inflection-threshold", type=float, default=1.0)
    p.add_argument("--price-smooth-days", type=int, default=21)
    p.add_argument("--min-quarters", type=int, default=16)
    p.add_argument("--benchmark", default="^GSPC")
    p.add_argument("--max-tickers", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--request-sleep", type=float, default=0.10)
    p.add_argument("--output-dir", type=Path, default=Path("results"))
    p.add_argument("--cache-dir", type=Path, default=Path(".cache/yf"))
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)
    return Config(
        universe=args.universe,
        market_cap_buckets=tuple(args.market_cap),
        countries=tuple(args.country),
        exchanges=tuple(args.exchange) if args.exchange else None,
        growth_window=args.growth_window,
        beta_window=args.beta_window,
        inflection_lookback=args.inflection_lookback,
        inflection_threshold=args.inflection_threshold,
        price_smooth_days=args.price_smooth_days,
        min_quarters=args.min_quarters,
        benchmark=args.benchmark,
        max_tickers=args.max_tickers,
        workers=max(1, args.workers),
        request_sleep=max(0.0, args.request_sleep),
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        log_level=args.log_level,
    )


def run(cfg: Config) -> pd.DataFrame:
    lazy_imports()
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    tickers = load_universe(cfg)
    if not tickers:
        log.error("empty universe; aborting")
        return pd.DataFrame()

    log.info("fetching benchmark %s", cfg.benchmark)
    bench_prices = fetch_benchmark(cfg)
    if bench_prices.empty:
        log.error("benchmark prices unavailable; aborting")
        return pd.DataFrame()

    log.info("analyzing %d tickers with %d workers", len(tickers), cfg.workers)
    results: list[TickerResult] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {pool.submit(analyze_ticker, cfg, t, bench_prices): t for t in tickers}
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            if i % 25 == 0 or i == len(futures):
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                log.info("  %d/%d  (%.1f/s)  last=%s err=%s",
                         i, len(futures), rate, r.ticker, r.error or "ok")

    df = results_to_frame(results)
    write_per_variant_csvs(df, cfg.output_dir)
    write_ranked(df, cfg.output_dir, cfg.inflection_threshold)
    log.info("done in %.1fs", time.time() - t0)
    return df


def main(argv: Optional[list[str]] = None) -> int:
    cfg = parse_args(argv)
    configure_logging(cfg.log_level)
    try:
        run(cfg)
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
