"""Earnings/fundamental growth -> price responsiveness analysis.

For a universe of stocks (default: US small caps via financedatabase), this
script measures how a stock's price responds to fundamental growth on the
margin and flags names where that responsiveness has recently inflected
positively.

Two growth signals are computed:

  1. EPS-only:  trailing N-quarter EPS growth.
  2. Composite: z-scored blend of trailing N-Q revenue, EBITDA, FCF growth.

Two price-side dependent variables are tested (Sharpe is inherently a
lookback measure, just like the rolling regression, so we include it as a
risk-adjusted complement to raw forward returns):

  A. Forward 1Q smoothed log return.
  B. Forward annualized Sharpe over the next ~W trading days.

Each (growth x dependent variable) pair is run in two modes:

  i.  absolute (stock-only).
  ii. relative to ^GSPC (return spread, or Sharpe-of-excess-returns).

= 8 variants per ticker:

   eps_return_absolute        eps_sharpe_absolute
   eps_return_vs_spx          eps_sharpe_vs_spx
   composite_return_absolute  composite_sharpe_absolute
   composite_return_vs_spx    composite_sharpe_vs_spx

Methodology
-----------
For each ticker on a per-quarter grid (aligned to fiscal quarter-ends):

  g_t   = TrailingSumLastN(metric_t) / TrailingSumPriorN(metric_t) - 1
  dg_t  = g_t - g_{t-1}
  r_t   = log(P_smooth_{t+1}) - log(P_smooth_t)   (forward 1Q return)
  s_t   = mean(daily_ret) / std(daily_ret) * sqrt(252) over (t, t+W days]
  *_rel = same, but on excess-vs-^GSPC series

Then on a rolling window of W_q quarters we run OLS of the chosen dependent
variable on dg and store the slope beta_t (the marginal sensitivity).
Inflection is:

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
        --sharpe-window-days 252 \\
        --max-tickers 500 \\
        --workers 8 \\
        --output-dir results/

Outputs one CSV per variant (8 total) plus a combined ranked.csv.

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
    sharpe_window_days: int = 252   # forward window (trading days) for Sharpe
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
    exchanges: Optional[tuple[str, ...]] = None
    # EDGAR (SEC XBRL) opt-in for deep quarterly history (revenue/EBITDA/FCF).
    # yfinance is hard-capped at 5-7 quarters by Yahoo's backend; EDGAR gives
    # 20+ years for any XBRL-filing US issuer. Requires a real contact email
    # for the SEC-mandated User-Agent.
    use_edgar: bool = False
    edgar_ua: str = "earnings-price-analysis researcher@example.com"
    edgar_cache_dir: Path = field(default_factory=lambda: Path(".cache/edgar"))


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

    # CSV escape hatch: if cfg.universe points to an existing CSV file, load
    # tickers from its index (first column). Lets us run on a pre-filtered list.
    csv_path = Path(cfg.universe)
    if csv_path.is_file() and csv_path.suffix.lower() == ".csv":
        df = pd.read_csv(csv_path, index_col=0)
        tickers = [str(t).upper().strip() for t in df.index.tolist() if pd.notna(t)]
        tickers = [t for t in tickers if t and " " not in t]
        log.info("loaded %d tickers from %s", len(tickers), csv_path)
        if cfg.max_tickers:
            tickers = tickers[: cfg.max_tickers]
        return tickers

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
    """Return cached DataFrame or None.

    Empty DataFrames are returned for 'price' (the file structure encodes
    success) but treated as cache-miss for 'income'/'cashflow'/'eps_history',
    so a transient rate-limit doesn't permanently poison the cache.
    """
    path = _cache_path(cfg, ticker, kind)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age_days * 86400:
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:                # corrupt cache file
        log.debug("cache read failed for %s/%s: %s", ticker, kind, exc)
        return None
    if kind in ("income", "cashflow", "eps_history") and df.empty:
        return None  # retry — empty very likely means rate-limited
    return df


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
    """Return dict with 'income', 'cashflow', and 'eps_history' DataFrames.

    Source:
      - If cfg.use_edgar is True, pulls from SEC EDGAR XBRL Company Facts
        (20+ years of quarterly history for any US issuer; ~10 req/sec).
        EPS history is still augmented with yfinance get_earnings_dates so
        we keep the older pre-XBRL EPS observations for long-history names.
      - Otherwise yfinance is the source: 'income'/'cashflow' are limited to
        ~5-7 quarters server-side; 'eps_history' uses get_earnings_dates
        (decades of reported EPS, single endpoint that isn't capped).
    """
    if cfg.use_edgar:
        from edgar_fetcher import fetch_fundamentals_edgar
        edgar = fetch_fundamentals_edgar(cfg.edgar_cache_dir, ticker, cfg.edgar_ua)
        if edgar is not None:
            # Augment EDGAR EPS with yfinance get_earnings_dates so we don't
            # lose pre-XBRL observations (pre-~2009 for many issuers).
            yf_eps = _fetch_eps_history_yf(cfg, ticker)
            if not yf_eps.empty:
                cur = edgar.get("eps_history", pd.DataFrame())
                if cur.empty:
                    edgar["eps_history"] = yf_eps
                else:
                    merged = (
                        pd.concat([cur, yf_eps])
                        .sort_index()
                    )
                    merged = merged[~merged.index.duplicated(keep="first")]
                    edgar["eps_history"] = merged
            return edgar
        log.debug("EDGAR returned no data for %s; falling back to yfinance", ticker)
    return _fetch_fundamentals_yf(cfg, ticker)


def _fetch_eps_history_yf(cfg: Config, ticker: str) -> pd.DataFrame:
    """Just the EPS-history slice of the yfinance fetch (used to augment EDGAR)."""
    cached = _read_cache(cfg, ticker, "eps_history")
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        ed = _with_retries(t.get_earnings_dates, limit=80)
    except Exception as exc:
        log.debug("fetch eps_history failed for %s: %s", ticker, exc)
        return pd.DataFrame()
    if ed is None or ed.empty or "Reported EPS" not in ed.columns:
        return pd.DataFrame()
    df = ed[["Reported EPS"]].copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    df = df.sort_index().dropna(subset=["Reported EPS"])
    _write_cache(cfg, ticker, "eps_history", df)
    time.sleep(cfg.request_sleep)
    return df


def _fetch_fundamentals_yf(cfg: Config, ticker: str) -> dict[str, pd.DataFrame]:
    """yfinance backend (legacy; capped at 5-7 quarters for income/cashflow)."""
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
                df = df.T
                df.index = pd.to_datetime(df.index, errors="coerce")
                df = df[~df.index.isna()].sort_index()
            out[kind] = df
            _write_cache(cfg, ticker, kind, df)
        except Exception as exc:
            log.debug("fetch %s failed for %s: %s", kind, ticker, exc)
            out[kind] = pd.DataFrame()
        time.sleep(cfg.request_sleep)

    # Long EPS history via get_earnings_dates (gives ~20+ years for many names).
    cached = _read_cache(cfg, ticker, "eps_history")
    if cached is not None:
        out["eps_history"] = cached
    else:
        try:
            t = yf.Ticker(ticker)
            ed = _with_retries(t.get_earnings_dates, limit=80)
            if ed is None or ed.empty or "Reported EPS" not in ed.columns:
                ed_df = pd.DataFrame()
            else:
                ed_df = ed[["Reported EPS"]].copy()
                idx = pd.to_datetime(ed_df.index)
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_localize(None)
                ed_df.index = idx
                ed_df = ed_df.sort_index().dropna(subset=["Reported EPS"])
            out["eps_history"] = ed_df
            _write_cache(cfg, ticker, "eps_history", ed_df)
        except Exception as exc:
            log.debug("fetch eps_history failed for %s: %s", ticker, exc)
            out["eps_history"] = pd.DataFrame()
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

    EPS preferentially uses the long historical earnings-dates feed (decades
    of quarters); falls back to the income statement's short window.
    """
    inc = funds.get("income", pd.DataFrame())
    cf = funds.get("cashflow", pd.DataFrame())
    eps_hist = funds.get("eps_history", pd.DataFrame())

    eps = None
    if not eps_hist.empty and "Reported EPS" in eps_hist.columns:
        eps = pd.to_numeric(eps_hist["Reported EPS"], errors="coerce").dropna()
    if eps is None or eps.empty:
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
    # Dedup each component series on its index before concat -- yfinance and
    # EDGAR both occasionally emit two rows for the same period_end (restated
    # quarters, corporate-action ticks). Without this the outer concat
    # explodes into a many-row cartesian product and later reindex calls
    # raise "cannot reindex on an axis with duplicate labels".
    parts = []
    for name, s in cols.items():
        if s is None:
            continue
        s = s.copy()
        if s.index.has_duplicates:
            s = s[~s.index.duplicated(keep="last")]
        parts.append(s.rename(name))
    if not parts:
        return pd.DataFrame(columns=["eps", "revenue", "ebitda", "fcf"])

    out = pd.concat(parts, axis=1).sort_index()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    if out.index.has_duplicates:
        out = out[~out.index.duplicated(keep="last")]
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
    # Drop duplicate dates (rare yfinance corporate-action quirk) -- otherwise
    # reindex below blows up with "cannot reindex on an axis with duplicate labels".
    if p.index.has_duplicates:
        p = p[~p.index.duplicated(keep="last")]
    if smooth_days and smooth_days > 1:
        p = p.rolling(window=smooth_days, min_periods=max(2, smooth_days // 2), center=False).mean()
    # Align by asof: for each fiscal date, take the most recent price. Dedup
    # `dates` too -- fiscal date dupes occur when a name re-reported a quarter.
    dates_unique = pd.DatetimeIndex(dates).drop_duplicates()
    p_at = p.reindex(p.index.union(dates_unique)).ffill().reindex(dates_unique)
    log_p = np.log(p_at.replace(0, np.nan))
    return log_p.diff().shift(-1)  # forward return


def forward_sharpe_at(
    prices: pd.Series,
    dates: pd.DatetimeIndex,
    window_trading_days: int = 252,
    periods_per_year: int = 252,
    benchmark_prices: Optional[pd.Series] = None,
) -> pd.Series:
    """At each fiscal date t, annualized Sharpe of forward daily log returns.

    Returns over (t, t + ~window calendar days] are used; we take the first
    `window_trading_days` actual observations within that window. If
    `benchmark_prices` is provided, Sharpe is computed on excess returns
    (stock daily - benchmark daily) -- the information-ratio analog.

    Sharpe is inherently a lookback measure, so this gives a smoother, risk-
    adjusted dependent variable for the growth-responsiveness regression in
    addition to raw forward returns.
    """
    if prices is None or prices.empty or len(dates) < 2:
        return pd.Series(dtype=float)

    p = prices.sort_index().copy()
    if getattr(p.index, "tz", None) is not None:
        p.index = p.index.tz_localize(None)
    if p.index.has_duplicates:
        p = p[~p.index.duplicated(keep="last")]
    daily_ret = np.log(p.replace(0, np.nan)).diff()

    if benchmark_prices is not None and not benchmark_prices.empty:
        b = benchmark_prices.sort_index().copy()
        if getattr(b.index, "tz", None) is not None:
            b.index = b.index.tz_localize(None)
        if b.index.has_duplicates:
            b = b[~b.index.duplicated(keep="last")]
        bench_ret = np.log(b.replace(0, np.nan)).diff()
        daily_ret = daily_ret - bench_ret      # NaN-aligned on union of indices

    daily_ret = daily_ret.dropna()
    if daily_ret.empty:
        return pd.Series(dtype=float)

    # Calendar-day budget covering the requested trading-day window plus slack.
    calendar_days = int(round(window_trading_days * 365 / 252)) + 14
    min_obs = max(20, int(window_trading_days * 0.6))

    rows: list[tuple] = []
    for t in dates:
        t_end = t + pd.Timedelta(days=calendar_days)
        sub = daily_ret.loc[(daily_ret.index > t) & (daily_ret.index <= t_end)]
        if len(sub) < min_obs:
            continue
        sub = sub.iloc[:window_trading_days]
        mu = float(sub.mean())
        sd = float(sub.std(ddof=0))
        if sd > 0:
            rows.append((t, (mu / sd) * np.sqrt(periods_per_year)))

    if not rows:
        return pd.Series(dtype=float)
    idx, vals = zip(*rows)
    return pd.Series(list(vals), index=pd.DatetimeIndex(list(idx)))


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
    """Per-ticker rolling-beta inflection summary.

    Fields beyond `inflection_z` capture the raw (non-normalized) signals so
    downstream filters can pick names by absolute beta improvement, by
    sign-flip from negative to positive, or by an acceleration check on the
    rolling-correlation series.

    Glossary:
      recent_mean_beta : mean of last K rolling betas
      prior_mean_beta  : mean of the K betas before that
      beta_delta_raw   : recent - prior (numerator of inflection_z, pre-z)
      beta_roc         : second-difference proxy: (latest - recent_mean)
                         - (recent_mean - prior_mean). >0 means beta is
                         accelerating upward.
      recent_mean_corr / prior_mean_corr / corr_delta_raw : same on the
                         rolling correlation series.
      is_inflected     : z-score >= threshold AND latest_beta > 0.
      is_regime_flip   : prior_mean_beta <= 0 AND latest_beta > 0
                         (the literal "underreaction -> appreciation"
                         transition: market wasn't responding, now is).
      is_corr_inflected: corr_delta_raw > 0 AND latest_corr > 0
                         (correlation has improved and is now positive).
    """
    latest_growth: float
    latest_delta_growth: float
    latest_beta: float
    latest_corr: float
    inflection_z: float
    n_quarters: int
    beta_history: pd.Series = field(repr=False)
    recent_mean_beta: float = float("nan")
    prior_mean_beta: float = float("nan")
    beta_delta_raw: float = float("nan")
    beta_roc: float = float("nan")
    recent_mean_corr: float = float("nan")
    prior_mean_corr: float = float("nan")
    corr_delta_raw: float = float("nan")
    is_inflected: bool = False
    is_regime_flip: bool = False
    is_corr_inflected: bool = False

    def to_row(self) -> dict[str, float | int | bool]:
        return {
            "latest_growth": self.latest_growth,
            "latest_delta_growth": self.latest_delta_growth,
            "latest_beta": self.latest_beta,
            "latest_corr": self.latest_corr,
            "inflection_z": self.inflection_z,
            "recent_mean_beta": self.recent_mean_beta,
            "prior_mean_beta": self.prior_mean_beta,
            "beta_delta_raw": self.beta_delta_raw,
            "beta_roc": self.beta_roc,
            "recent_mean_corr": self.recent_mean_corr,
            "prior_mean_corr": self.prior_mean_corr,
            "corr_delta_raw": self.corr_delta_raw,
            "n_quarters": self.n_quarters,
            "is_inflected": self.is_inflected,
            "is_regime_flip": self.is_regime_flip,
            "is_corr_inflected": self.is_corr_inflected,
        }


def compute_responsiveness(
    growth: pd.Series,
    fwd_return: pd.Series,
    beta_window: int,
    lookback: int,
    inflection_threshold: float,
) -> Optional[Responsiveness]:
    """Run the rolling-beta + inflection pipeline for one (growth, return) pair.

    Produces three independent inflection flags:
      is_inflected      — z-score-based (current behavior, threshold-driven)
      is_regime_flip    — prior_mean_beta <= 0 AND latest_beta > 0 (sign flip)
      is_corr_inflected — corr_delta_raw > 0 AND latest_corr > 0
                          (correlation improving and now positive)
    """
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
    corr_clean = corr.dropna()
    if len(beta_clean) < 2 * lookback:
        return None

    recent_b = float(beta_clean.iloc[-lookback:].mean())
    prior_b = float(beta_clean.iloc[-2 * lookback : -lookback].mean())
    std_full = float(beta_clean.std(ddof=0))
    z = (recent_b - prior_b) / std_full if std_full and not np.isnan(std_full) and std_full > 0 else np.nan
    beta_delta_raw = recent_b - prior_b
    latest_beta = float(beta_clean.iloc[-1])
    # Second-difference style ROC: change in change. >0 => beta accelerating up.
    beta_roc = (latest_beta - recent_b) - (recent_b - prior_b)

    # Same recent/prior decomposition on the correlation series so we can
    # detect correlation inflections independently from beta-magnitude moves.
    if len(corr_clean) >= 2 * lookback:
        recent_c = float(corr_clean.iloc[-lookback:].mean())
        prior_c = float(corr_clean.iloc[-2 * lookback : -lookback].mean())
        latest_corr = float(corr_clean.iloc[-1])
    else:
        recent_c = prior_c = float("nan")
        latest_corr = float(corr_clean.iloc[-1]) if not corr_clean.empty else float("nan")
    corr_delta_raw = recent_c - prior_c

    latest_growth = float(df["g"].iloc[-1])
    latest_dg = float(df["dg"].iloc[-1])

    return Responsiveness(
        latest_growth=latest_growth,
        latest_delta_growth=latest_dg,
        latest_beta=latest_beta,
        latest_corr=latest_corr if pd.notna(latest_corr) else np.nan,
        inflection_z=float(z) if pd.notna(z) else np.nan,
        n_quarters=int(len(df)),
        beta_history=beta_clean,
        recent_mean_beta=recent_b,
        prior_mean_beta=prior_b,
        beta_delta_raw=float(beta_delta_raw),
        beta_roc=float(beta_roc),
        recent_mean_corr=recent_c,
        prior_mean_corr=prior_c,
        corr_delta_raw=float(corr_delta_raw) if pd.notna(corr_delta_raw) else float("nan"),
        is_inflected=bool(pd.notna(z) and z >= inflection_threshold and latest_beta > 0),
        is_regime_flip=bool(pd.notna(prior_b) and prior_b <= 0 and latest_beta > 0),
        is_corr_inflected=bool(
            pd.notna(corr_delta_raw) and corr_delta_raw > 0
            and pd.notna(latest_corr) and latest_corr > 0
        ),
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


def latest_shallow_growth(series: pd.Series) -> tuple[float, str]:
    """Most recent point-in-time growth observation from a short series.

    yfinance's 5-7 quarter cap on quarterly statements is not enough for a
    rolling-beta pipeline on revenue/EBITDA/FCF, but it IS enough for a
    single growth observation per name. We try, in order of preference:

      1. YoY (latest Q vs Q-4): cleanest, no seasonality risk.
         Requires >= 5 quarters.
      2. Trailing 2Q vs prior 2Q: smoother than single-quarter; useful when
         only 4 quarters available.
         Requires >= 4 quarters.
      3. Sequential (latest Q vs Q-1): noisiest, last-resort.
         Requires >= 2 quarters. Has seasonality risk.

    Returns (growth_value, method_used). NaN growth + 'none' if no data.

    All methods use the symmetric formula 2*(last - prior) / (|last| + |prior|)
    so a negative-to-positive flip doesn't blow up the denominator -- important
    for small-cap names where revenue/EBITDA/FCF often straddle zero.
    """
    if series is None or series.empty:
        return (float("nan"), "none")
    s = series.dropna().astype(float).sort_index()
    n = len(s)

    def _sym(a: float, b: float) -> float:
        denom = abs(a) + abs(b)
        if denom == 0:
            return float("nan")
        return 2.0 * (a - b) / denom

    if n >= 5:
        return (_sym(float(s.iloc[-1]), float(s.iloc[-5])), "yoy")
    if n >= 4:
        last2 = float(s.iloc[-2:].sum())
        prior2 = float(s.iloc[-4:-2].sum())
        return (_sym(last2, prior2), "ttm2")
    if n >= 2:
        return (_sym(float(s.iloc[-1]), float(s.iloc[-2])), "seq")
    return (float("nan"), "none")


def extract_shallow_momentum(funds: dict[str, pd.DataFrame]) -> dict[str, float | str]:
    """Per-ticker shallow-history fundamental momentum, suitable for the 5-7
    quarter cap on yfinance quarterly statements.

    Returns a flat dict with the latest revenue/EBITDA/FCF/NetIncome growth
    plus the method used for each. Caller z-scores cross-sectionally.
    """
    inc = funds.get("income", pd.DataFrame())
    cf = funds.get("cashflow", pd.DataFrame())

    revenue = _first_existing(inc, REVENUE_FIELDS)
    ebitda = _first_existing(inc, EBITDA_FIELDS)
    if ebitda is None:
        op_inc = _first_existing(inc, OP_INCOME_FIELDS)
        da = _first_existing(inc, DA_FIELDS)
        if op_inc is not None and da is not None:
            ebitda = (op_inc.add(da.abs(), fill_value=np.nan)).dropna()
    fcf = _first_existing(cf, FCF_FIELDS)
    if fcf is None:
        ocf = _first_existing(cf, OCF_FIELDS)
        capex = _first_existing(cf, CAPEX_FIELDS)
        if ocf is not None and capex is not None:
            fcf = (ocf - capex.abs()).dropna()
    net_inc = _first_existing(inc, NET_INCOME_FIELDS)

    out: dict[str, float | str] = {}
    for label, series in (("revenue", revenue), ("ebitda", ebitda),
                          ("fcf", fcf), ("net_income", net_inc)):
        g, method = latest_shallow_growth(series if series is not None else pd.Series(dtype=float))
        out[f"{label}_growth_latest"] = g
        out[f"{label}_growth_method"] = method
        out[f"{label}_n_quarters"] = len(series.dropna()) if series is not None else 0
    return out


# --------------------------------------------------------------------------- #
# Per-ticker analysis orchestration                                           #
# --------------------------------------------------------------------------- #


@dataclass
class TickerResult:
    ticker: str
    # Forward 1Q log-return dependent variable
    eps_ret_abs: Optional[Responsiveness] = None
    eps_ret_rel: Optional[Responsiveness] = None
    comp_ret_abs: Optional[Responsiveness] = None
    comp_ret_rel: Optional[Responsiveness] = None
    # Forward annualized Sharpe dependent variable (Sharpe is itself a lookback)
    eps_shp_abs: Optional[Responsiveness] = None
    eps_shp_rel: Optional[Responsiveness] = None
    comp_shp_abs: Optional[Responsiveness] = None
    comp_shp_rel: Optional[Responsiveness] = None
    # Shallow-history composite momentum (works within the 5-7 quarter yfinance cap):
    # single point-in-time growth observation per fundamental, blended cross-
    # sectionally in post-processing.
    shallow_momentum: dict[str, float | str] = field(default_factory=dict)
    error: Optional[str] = None


def analyze_ticker(
    cfg: Config,
    ticker: str,
    bench_prices: pd.Series,
) -> TickerResult:
    res = TickerResult(ticker=ticker)
    try:
        funds = fetch_fundamentals(cfg, ticker)
        # Shallow momentum is cheap and uses whatever income/cashflow we got,
        # even if it's too short for the rolling-beta pipeline. Compute it
        # before the min_quarters guard so we still emit it for short-history
        # names that don't qualify for the responsiveness analysis.
        res.shallow_momentum = extract_shallow_momentum(funds)

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

        # ---- Dependent variables ----
        # Forward 1Q smoothed log returns at fiscal dates (absolute + vs SPX).
        r_abs = smoothed_log_returns_at(prices, q_dates, cfg.price_smooth_days)
        r_bench = smoothed_log_returns_at(bench_prices, q_dates, cfg.price_smooth_days)
        r_rel = (r_abs - r_bench).dropna()

        # Forward annualized Sharpe (absolute) and Sharpe-of-excess-returns (vs SPX).
        s_abs = forward_sharpe_at(prices, q_dates, cfg.sharpe_window_days)
        s_rel = forward_sharpe_at(prices, q_dates, cfg.sharpe_window_days,
                                  benchmark_prices=bench_prices)

        # ---- EPS variant ----
        g_eps = trailing_n_growth(metrics["eps"], cfg.growth_window)
        if not g_eps.empty:
            res.eps_ret_abs = compute_responsiveness(
                g_eps, r_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.eps_ret_rel = compute_responsiveness(
                g_eps, r_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.eps_shp_abs = compute_responsiveness(
                g_eps, s_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.eps_shp_rel = compute_responsiveness(
                g_eps, s_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )

        # ---- Composite variant ----
        g_comp = composite_growth(metrics, cfg.growth_window)
        if not g_comp.empty:
            res.comp_ret_abs = compute_responsiveness(
                g_comp, r_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.comp_ret_rel = compute_responsiveness(
                g_comp, r_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.comp_shp_abs = compute_responsiveness(
                g_comp, s_abs, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
            res.comp_shp_rel = compute_responsiveness(
                g_comp, s_rel, cfg.beta_window, cfg.inflection_lookback, cfg.inflection_threshold
            )
    except Exception as exc:                                  # one bad ticker shouldn't kill the run
        res.error = f"{type(exc).__name__}: {exc}"
        log.debug("analyze_ticker(%s) failed: %s", ticker, exc)
    return res


# --------------------------------------------------------------------------- #
# Output assembly                                                             #
# --------------------------------------------------------------------------- #


VARIANT_FIELDS = (
    "eps_ret_abs", "eps_ret_rel", "comp_ret_abs", "comp_ret_rel",
    "eps_shp_abs", "eps_shp_rel", "comp_shp_abs", "comp_shp_rel",
)


def results_to_frame(results: list[TickerResult]) -> pd.DataFrame:
    """Wide table: one row per ticker, one column block per variant."""
    rows: list[dict] = []
    for r in results:
        row: dict[str, object] = {"ticker": r.ticker, "error": r.error}
        for var in VARIANT_FIELDS:
            sub = getattr(r, var)
            if sub is None:
                # Stub all columns the Responsiveness.to_row() would produce.
                for k in (
                    "latest_growth", "latest_delta_growth", "latest_beta", "latest_corr",
                    "inflection_z", "recent_mean_beta", "prior_mean_beta",
                    "beta_delta_raw", "beta_roc", "recent_mean_corr", "prior_mean_corr",
                    "corr_delta_raw", "n_quarters", "is_inflected",
                    "is_regime_flip", "is_corr_inflected",
                ):
                    row[f"{var}_{k}"] = np.nan
            else:
                for k, v in sub.to_row().items():
                    row[f"{var}_{k}"] = v
        # Shallow-history fundamental momentum (works even when the responsiveness
        # pipeline can't run because we have <20 quarters).
        for k, v in (r.shallow_momentum or {}).items():
            row[f"shallow_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")


def _xs_rank_columns(sub: pd.DataFrame, value_cols: tuple[str, ...]) -> pd.DataFrame:
    """Add cross-sectional rank/percentile/z-score columns for each value col.

    For each value column V:
      V_rank        — 1 = highest in universe; ties broken by first-seen
      V_pct         — percentile [0, 100], where 100 = top of universe
      V_xs_z        — cross-sectional z-score: (V - mean(V_universe)) / std(V_universe)

    NaN inputs stay NaN in the output columns. Universe = rows where the value
    is not NaN.
    """
    out = sub.copy()
    for col in value_cols:
        if col not in out.columns:
            continue
        s = pd.to_numeric(out[col], errors="coerce")
        # Rank descending (1 = best). pandas pct=True gives 0..1; flip so
        # high V => high percentile.
        rk = s.rank(ascending=False, method="min", na_option="keep")
        pct = s.rank(ascending=True, method="average", pct=True, na_option="keep") * 100
        mu = s.mean(skipna=True)
        sd = s.std(ddof=0, skipna=True)
        xs_z = (s - mu) / sd if sd and not pd.isna(sd) and sd > 0 else pd.Series(np.nan, index=s.index)
        out[f"{col}_rank"] = rk
        out[f"{col}_pct"] = pct
        out[f"{col}_xs_z"] = xs_z
    return out


def write_per_variant_csvs(df: pd.DataFrame, outdir: Path) -> None:
    """Emit one CSV per variant.

    Each CSV includes:
      - the per-ticker time-series metrics (latest_growth, latest_beta,
        inflection_z, etc.)
      - cross-sectional rank/percentile/z-score for the headline values
        (latest_beta, inflection_z, latest_growth, latest_corr)

    Time-series inflection_z is "this ticker's recent beta vs its own prior
    beta, scaled by its own beta std." Cross-sectional inflection_z_xs_z is
    "this ticker's inflection_z vs the universe of tickers' inflection_z."
    Both are useful; cross-sectional surfaces the standouts in the sample.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    variant_to_name = {
        "eps_ret_abs": "eps_return_absolute",
        "eps_ret_rel": "eps_return_vs_spx",
        "comp_ret_abs": "composite_return_absolute",
        "comp_ret_rel": "composite_return_vs_spx",
        "eps_shp_abs": "eps_sharpe_absolute",
        "eps_shp_rel": "eps_sharpe_vs_spx",
        "comp_shp_abs": "composite_sharpe_absolute",
        "comp_shp_rel": "composite_sharpe_vs_spx",
    }
    # Cross-section all the headline signals (z-based and raw) so the CSV
    # carries percentile/rank/xs-z for each. Raw deltas matter alongside the
    # z because a name with a small std-of-beta can have a giant z-score off
    # a tiny absolute move.
    headline_cols = (
        "inflection_z", "latest_beta", "latest_growth", "latest_corr",
        "recent_mean_beta", "prior_mean_beta",
        "beta_delta_raw", "beta_roc", "corr_delta_raw",
    )
    for var, label in variant_to_name.items():
        cols = [c for c in df.columns if c.startswith(f"{var}_")]
        if not cols:
            continue
        sub = df[cols].copy()
        sub.columns = [c[len(var) + 1 :] for c in cols]
        # Cross-sectional ranks computed across all tickers in this variant.
        xs_targets = tuple(c for c in headline_cols if c in sub.columns)
        sub = _xs_rank_columns(sub, xs_targets)
        sub = sub.sort_values("inflection_z", ascending=False)
        sub.to_csv(outdir / f"{label}.csv")
        log.info("wrote %s.csv (%d rows)", label, len(sub))


def write_composite_momentum(df: pd.DataFrame, outdir: Path) -> None:
    """Cross-sectional shallow-history composite-momentum CSV.

    For each ticker we have a single recent growth observation per fundamental
    (revenue / EBITDA / FCF / net income) -- whatever the 5-7 quarter yfinance
    cap permits. This function:

      1. Cross-sectionally z-scores each fundamental's latest growth.
      2. Blends the four fundamentals equally into composite_momentum_z.
      3. Adds cross-sectional rank and percentile.

    The composite_momentum_z is the cross-sectional analog of what the
    composite *responsiveness* variants would have produced if Yahoo gave us
    24+ quarters of history. It says "this name's fundamentals are improving
    fast relative to the universe right now," which usefully confirms or
    contradicts the EPS-based rolling-beta inflection.
    """
    fields = ["revenue_growth_latest", "ebitda_growth_latest",
              "fcf_growth_latest", "net_income_growth_latest"]
    base_cols = [f"shallow_{f}" for f in fields]
    have = [c for c in base_cols if c in df.columns]
    if not have:
        log.info("composite_momentum: no shallow_* columns found, skipping")
        return

    sub = df[have].copy().apply(pd.to_numeric, errors="coerce")

    z_cols: list[str] = []
    for c in have:
        s = sub[c]
        mu = s.mean(skipna=True)
        sd = s.std(ddof=0, skipna=True)
        if sd and not pd.isna(sd) and sd > 0:
            sub[f"{c}_xs_z"] = (s - mu) / sd
        else:
            sub[f"{c}_xs_z"] = np.nan
        z_cols.append(f"{c}_xs_z")
        sub[f"{c}_pct"] = s.rank(ascending=True, method="average", pct=True, na_option="keep") * 100

    sub["composite_momentum_z"] = sub[z_cols].mean(axis=1, skipna=True)
    sub["composite_momentum_pct"] = (
        sub["composite_momentum_z"]
        .rank(ascending=True, method="average", pct=True, na_option="keep")
        * 100
    )
    sub["composite_momentum_rank"] = sub["composite_momentum_z"].rank(
        ascending=False, method="min", na_option="keep"
    )

    sub = sub.sort_values("composite_momentum_z", ascending=False)
    sub.to_csv(outdir / "composite_momentum.csv")
    nz = sub["composite_momentum_z"].dropna()
    log.info("composite_momentum.csv written; %d tickers with valid score (mean=%.2f)",
             len(nz), nz.mean() if not nz.empty else 0.0)
    if not nz.empty:
        top = sub.dropna(subset=["composite_momentum_z"]).head(15)
        log.info("top 15 by composite_momentum_z (shallow-history blend):")
        for tkr, row in top.iterrows():
            log.info("  %-8s  z=%+.2f  pct=%.0f  rev=%+.2f  ebitda=%+.2f  fcf=%+.2f  ni=%+.2f",
                     tkr,
                     float(row["composite_momentum_z"]),
                     float(row["composite_momentum_pct"]),
                     float(row.get("shallow_revenue_growth_latest", np.nan)),
                     float(row.get("shallow_ebitda_growth_latest", np.nan)),
                     float(row.get("shallow_fcf_growth_latest", np.nan)),
                     float(row.get("shallow_net_income_growth_latest", np.nan)))


def write_ranked(df: pd.DataFrame, outdir: Path, threshold: float) -> None:
    """Combined ranking: avg inflection_z across all variants, with the count
    of variants where the inflection was flagged.

    With 8 variants (ret/shp x abs/rel x eps/comp), being inflected in 3+ is a
    strong signal -- the two dependent variables (return vs Sharpe) are
    correlated, so confirmation across both indicates a robust regime shift.
    """
    z_cols = [f"{v}_inflection_z" for v in VARIANT_FIELDS]
    flag_cols = [f"{v}_is_inflected" for v in VARIANT_FIELDS]
    avail = df[z_cols + flag_cols].copy()
    avail["avg_inflection_z"] = df[z_cols].mean(axis=1, skipna=True)
    avail["n_variants_inflected"] = df[flag_cols].fillna(False).astype(bool).sum(axis=1)
    # Decompose into return-side and Sharpe-side counts for diagnostic clarity.
    ret_flags = [f"{v}_is_inflected" for v in VARIANT_FIELDS if "_ret_" in v]
    shp_flags = [f"{v}_is_inflected" for v in VARIANT_FIELDS if "_shp_" in v]
    avail["n_inflected_returns"] = df[ret_flags].fillna(False).astype(bool).sum(axis=1)
    avail["n_inflected_sharpe"] = df[shp_flags].fillna(False).astype(bool).sum(axis=1)

    ranked = avail.sort_values(
        ["n_variants_inflected", "avg_inflection_z"], ascending=[False, False]
    )
    ranked.to_csv(outdir / "ranked.csv")

    min_flags = max(3, len(VARIANT_FIELDS) // 3)
    qualified = ranked[ranked["n_variants_inflected"] >= min_flags]
    log.info("ranked.csv written; %d names inflected in >= %d of %d variants",
             len(qualified), min_flags, len(VARIANT_FIELDS))
    if not qualified.empty:
        log.info("top inflecting names (n_variants_inflected >= %d):", min_flags)
        for tkr, row in qualified.head(40).iterrows():
            log.info(
                "  %-8s  n_var=%d  (ret=%d shp=%d)  avg_z=%.2f",
                tkr,
                int(row["n_variants_inflected"]),
                int(row["n_inflected_returns"]),
                int(row["n_inflected_sharpe"]),
                float(row["avg_inflection_z"]),
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
    p.add_argument("--sharpe-window-days", type=int, default=252,
                   help="forward trading-day window for the Sharpe dependent variable")
    p.add_argument("--min-quarters", type=int, default=16)
    p.add_argument("--benchmark", default="^GSPC")
    p.add_argument("--max-tickers", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--request-sleep", type=float, default=0.10)
    p.add_argument("--output-dir", type=Path, default=Path("results"))
    p.add_argument("--cache-dir", type=Path, default=Path(".cache/yf"))
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--use-edgar", action="store_true",
                   help="pull quarterly fundamentals from SEC EDGAR XBRL "
                        "(deep history) instead of yfinance (5-7 quarter cap). "
                        "Requires --edgar-ua to identify you per SEC fair-use rules.")
    p.add_argument("--edgar-ua",
                   default="earnings-price-analysis researcher@example.com",
                   help='SEC-required User-Agent: "<Name or Org> <email>"')
    p.add_argument("--edgar-cache-dir", type=Path, default=Path(".cache/edgar"))
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
        sharpe_window_days=args.sharpe_window_days,
        min_quarters=args.min_quarters,
        benchmark=args.benchmark,
        max_tickers=args.max_tickers,
        workers=max(1, args.workers),
        request_sleep=max(0.0, args.request_sleep),
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        log_level=args.log_level,
        use_edgar=args.use_edgar,
        edgar_ua=args.edgar_ua,
        edgar_cache_dir=args.edgar_cache_dir,
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
    write_composite_momentum(df, cfg.output_dir)
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
