"""Fetch fundamentals from yfinance with on-disk caching and backoff.

Yahoo aggressively rate-limits cloud IPs (HTTP 429), so every ticker is
cached to ``cache/raw/<symbol>.json`` and re-used within ``CACHE_TTL_DAYS``.
Network calls retry with exponential backoff and use a curl_cffi session
impersonating a browser, which is the usual way to dodge the 429 wall.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, metrics

NaN = float("nan")


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
def make_session(warm: bool = True):
    """Return a curl_cffi browser-impersonating session, cookie/crumb-warmed.

    A *cold* session is the real cause of the immediate "Too Many Requests" on
    ``.info`` — Yahoo's quoteSummary rejects a request that carries no consent
    cookie + crumb. Hitting ``fc.yahoo.com`` (sets the A1/A3 cookies) then the
    ``getcrumb`` endpoint primes the session so the first real call succeeds.
    curl_cffi's chrome impersonation already carries us most of the way; this
    warmup hardens cold starts and shared-IP runs. Best-effort: warmup failures
    are swallowed (the session still works, just less primed). ``warm=False`` for
    the rare caller that wants a bare session.
    """
    try:
        from curl_cffi import requests as cffi_requests

        session = cffi_requests.Session(impersonate="chrome")
    except Exception:
        return None
    if warm:
        for url in ("https://fc.yahoo.com",
                    "https://query1.finance.yahoo.com/v1/test/getcrumb"):
            try:
                session.get(url, timeout=10)
            except Exception:
                pass
    return session


class RateLimiter:
    """Adaptive inter-request pacer for a shared-IP bulk run.

    Holds a target gap between requests, GROWS it multiplicatively on a 429
    (``penalize``) up to a ceiling, and DECAYS it back toward target on each
    success (``recover``). This self-tunes to Yahoo's rolling per-IP window
    without a fixed sleep that is either too slow (wastes time) or too fast
    (trips the throttle)."""

    def __init__(self, min_interval: float = config.RATE_MIN_INTERVAL,
                 max_interval: float = config.RATE_MAX_INTERVAL,
                 penalty: float = config.RATE_PENALTY,
                 recover: float = config.RATE_RECOVER):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.penalty = penalty
        self.recover_factor = recover
        self.interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        gap = self._last + self.interval - time.monotonic()
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def penalize(self) -> None:
        self.interval = min(self.max_interval, self.interval * self.penalty)

    def recover(self) -> None:
        self.interval = max(self.min_interval, self.interval * self.recover_factor)


class SessionManager:
    """Owns a warmed session + adaptive limiter for a bulk fetch loop and
    re-warms the session after a run of consecutive failures (a sign the
    cookie/crumb went stale or the IP got throttled). Drop-in replacement for
    the manual ``make_session() + fetch_raw() + sleep`` pattern: call
    ``mgr.fetch(symbol)`` per ticker and it paces, adapts, and self-heals."""

    def __init__(self, rps: float | None = None,
                 refresh_after: int = config.SESSION_REFRESH_AFTER_FAILS):
        min_interval = (1.0 / rps) if rps else config.RATE_MIN_INTERVAL
        self.limiter = RateLimiter(min_interval=min_interval)
        self.refresh_after = refresh_after
        self._session = make_session(warm=True)
        self._consec_fails = 0
        self.refreshes = 0

    @property
    def session(self):
        return self._session

    def refresh(self) -> None:
        self._session = make_session(warm=True)
        self._consec_fails = 0
        self.refreshes += 1

    def fetch(self, symbol: str, **kw) -> dict:
        self.limiter.wait()
        raw = fetch_raw(symbol, session=self._session, **kw)
        if raw.get("fetch_ok"):
            self._consec_fails = 0
            self.limiter.recover()
        else:
            self._consec_fails += 1
            if raw.get("rate_limited"):
                self.limiter.penalize()
            if self._consec_fails >= self.refresh_after:
                self.refresh()
        return raw


def _ticker(symbol: str, session):
    import yfinance as yf

    if session is not None:
        try:
            return yf.Ticker(symbol, session=session)
        except TypeError:
            pass
    return yf.Ticker(symbol)


# --------------------------------------------------------------------------- #
# Statement parsing
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _resolve_row(stmt: pd.DataFrame, keys: list[str]) -> pd.Series | None:
    """Find a statement row matching any candidate name (case/space-insensitive)."""
    if stmt is None or getattr(stmt, "empty", True):
        return None
    norm_index = {_norm(idx): idx for idx in stmt.index}
    for key in keys:
        nk = _norm(key)
        if nk in norm_index:
            return stmt.loc[norm_index[nk]]
    # Fall back to substring match (e.g. odd EBITDA variants).
    for key in keys:
        nk = _norm(key)
        for nidx, orig in norm_index.items():
            if nk and nk in nidx:
                return stmt.loc[orig]
    return None


def _series(stmt: pd.DataFrame, keys: list[str]) -> list[float]:
    """Return the line-item values oldest -> newest as plain floats."""
    row = _resolve_row(stmt, keys)
    if row is None:
        return []
    row = row.sort_index()  # columns are period-end dates -> ascending
    out = []
    for v in row.tolist():
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = NaN
        out.append(f if not math.isnan(f) else NaN)
    return out


def _ebitda_series(stmt: pd.DataFrame) -> list[float]:
    """EBITDA line, or operating income + D&A reconstruction as a fallback."""
    direct = _series(stmt, config.EBITDA_KEYS)
    opinc = _series(stmt, config.OPERATING_INCOME_KEYS)
    da = _series(stmt, config.DA_KEYS)
    recon_ok = bool(opinc) and bool(da) and len(opinc) == len(da)
    if not recon_ok:
        return direct
    # Splice rather than all-or-nothing: keep as-reported EBITDA where present and
    # backfill ONLY the NaN positions with operating income + D&A, so a partly-
    # reported EBITDA line still yields the full multi-year path (earlier years
    # were previously lost whenever any single recent year reported EBITDA).
    n = len(opinc)
    direct = (direct + [NaN] * n)[:n] if direct else [NaN] * n
    out = []
    for i in range(n):
        if not math.isnan(direct[i]):
            out.append(direct[i])
        elif not (math.isnan(opinc[i]) or math.isnan(da[i])):
            out.append(opinc[i] + da[i])
        else:
            out.append(NaN)
    return out


def _dates(stmt: pd.DataFrame) -> list[str]:
    if stmt is None or getattr(stmt, "empty", True):
        return []
    cols = sorted(stmt.columns)
    return [str(getattr(c, "date", lambda: c)()) for c in cols]


def _statement_block(stmt: pd.DataFrame) -> dict:
    return {
        "dates": _dates(stmt),
        "revenue": _series(stmt, config.REVENUE_KEYS),
        "gross": _series(stmt, config.GROSS_PROFIT_KEYS),
        "ebitda": _ebitda_series(stmt),
        "earnings": _series(stmt, config.NET_INCOME_KEYS),
        "eps": _series(stmt, config.EPS_KEYS),
    }


# --------------------------------------------------------------------------- #
# Prices -> trailing returns
# --------------------------------------------------------------------------- #
def _price_features(hist: pd.DataFrame) -> tuple[dict, dict]:
    """Multi-year price features + the monthly close series (for case studies).

    Returns (features, monthly) where features covers config.PRICE_FEATURE_KEYS
    (trailing returns out to 36m, max drawdown, position in the 3y range,
    annualised 2y log-price trend, and realised vol) and monthly is
    {"dates": [...], "close": [...]} of month-end closes.
    """
    feats = {k: NaN for k in config.PRICE_FEATURE_KEYS}
    monthly_out = {"dates": [], "close": []}
    if hist is None or getattr(hist, "empty", True) or "Close" not in hist.columns:
        return feats, monthly_out
    close = hist["Close"].dropna()
    if close.empty:
        return feats, monthly_out

    m = close.resample("ME").last().dropna()
    if m.empty:
        return feats, monthly_out
    monthly_out = {"dates": [str(d.date()) for d in m.index],
                   "close": [float(x) for x in m.to_numpy()]}

    last = float(m.iloc[-1])
    last_date = m.index[-1]
    feats["last_price"] = last
    for label, months in (("ret_1m", 1), ("ret_3m", 3), ("ret_6m", 6),
                          ("ret_12m", 12), ("ret_24m", 24), ("ret_36m", 36)):
        prior = m.loc[:last_date - pd.DateOffset(months=months)]
        if not prior.empty:
            base = float(prior.iloc[-1])
            if base > 0:
                feats[label] = last / base - 1.0

    dd = (m / m.cummax() - 1.0).min()
    feats["max_drawdown"] = float(dd) if pd.notna(dd) else NaN

    win = m.loc[last_date - pd.DateOffset(months=36):]
    lo, hi = float(win.min()), float(win.max())
    feats["range_position"] = (last - lo) / (hi - lo) if hi > lo else NaN

    win2 = m.loc[last_date - pd.DateOffset(months=24):]
    if len(win2) >= 6 and bool((win2 > 0).all()):
        y = np.log(win2.to_numpy())
        feats["trend_slope"] = float(np.polyfit(np.arange(len(y)), y, 1)[0] * 12.0)

    rets = m.pct_change().dropna().loc[last_date - pd.DateOffset(months=12):]
    if len(rets) >= 3:
        feats["realized_vol"] = float(rets.std() * np.sqrt(12))
    return feats, monthly_out


# --------------------------------------------------------------------------- #
# Cache I/O
# --------------------------------------------------------------------------- #
def _cache_path(symbol: str) -> Path:
    return config.RAW_CACHE_DIR / f"{symbol.replace('/', '_')}.json"


def load_raw(symbol: str, ttl_days: float = config.CACHE_TTL_DAYS,
             fail_ttl_days: float = config.FAIL_CACHE_TTL_DAYS) -> dict | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    # Failures expire faster than successes, so transient errors auto-retry.
    effective_ttl = ttl_days if raw.get("fetch_ok") else fail_ttl_days
    asof = raw.get("asof")
    if asof and effective_ttl is not None:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(asof)
            if age.total_seconds() > effective_ttl * 86400:
                return None
        except ValueError:
            pass
    return raw


def save_raw(symbol: str, raw: dict) -> None:
    config.RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(symbol).write_text(json.dumps(raw, default=str))


# --------------------------------------------------------------------------- #
# Earnings surprises (EPS actual vs estimate) — best coverage in the US
# --------------------------------------------------------------------------- #
def refresh_valuation(symbol: str, session=None) -> dict | None:
    """Fast path: refresh only the valuation/.info fields on an already-cached raw.

    For when new fields are added to ``config.VALUATION_FIELDS`` and you don't
    want a full statement+price+surprise re-fetch. Returns the updated raw dict
    (or None if no cache exists / the .info pull fails).
    """
    cached = load_raw(symbol, ttl_days=None, fail_ttl_days=None)
    if cached is None:
        return None
    try:
        tk = _ticker(symbol, session)
        info = tk.info or {}
    except Exception:
        return None
    val = cached.get("valuation") or {}
    for f in config.VALUATION_FIELDS:
        if info.get(f) is not None:
            val[f] = info[f]
    cached["valuation"] = val
    save_raw(symbol, cached)
    return cached


def refresh_surprises(symbol: str, session=None) -> dict | None:
    """Fast path: add/refresh only the EPS-surprise history on a cached raw.

    One get_earnings_dates call per name (no statement/price re-pull), so the
    surprise leg can be back-filled for already-fetched names cheaply. Always
    writes a ``surprises`` key (possibly empty) so a re-run won't retry it.
    """
    cached = load_raw(symbol, ttl_days=None, fail_ttl_days=None)
    if cached is None:
        return None
    try:
        cached["surprises"] = _earnings_surprises(_ticker(symbol, session))
    except Exception:
        cached.setdefault("surprises", [])
    save_raw(symbol, cached)
    return cached


def _earnings_surprises(tk) -> list:
    """Recent quarters' EPS surprise %, oldest->newest. yfinance only carries
    EPS surprises (no historical revenue/sales surprise); coverage is strong in
    the US, sparse elsewhere. Big values off a near-zero estimate are capped."""
    try:
        ed = tk.get_earnings_dates(limit=24)
    except Exception:
        try:
            eh = tk.earnings_history  # fallback: ~4 quarters
            if eh is not None:
                ed = eh.rename(columns={"surprisePercent": "Surprise(%)"})
                # quoteSummary earningsHistory delivers surprisePercent as a DECIMAL
                # FRACTION (0.0257 for a 2.57% beat), unlike get_earnings_dates which
                # yields percent (2.57). Rescale so both paths feed surprise_block on
                # the SAME percent scale (else fallback names read ~100x too small).
                if "Surprise(%)" in ed.columns:
                    ed["Surprise(%)"] = pd.to_numeric(ed["Surprise(%)"], errors="coerce") * 100.0
            else:
                ed = None
        except Exception:
            return []
    if ed is None or getattr(ed, "empty", True) or "Surprise(%)" not in ed.columns:
        return []
    df = ed.dropna(subset=["Surprise(%)"]).sort_index()  # past quarters, oldest->newest
    out = []
    for dt, row in df.iterrows():
        try:
            sp = float(row["Surprise(%)"])
        except (TypeError, ValueError):
            continue
        if sp != sp:
            continue
        out.append({"date": str(getattr(dt, "date", lambda: dt)()),
                    "surprise_pct": max(-200.0, min(200.0, sp))})
    return out[-12:]  # last 12 quarters


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def fetch_raw(symbol: str, session=None, max_retries: int = config.MAX_RETRIES,
              with_surprises: bool = False) -> dict:
    """Fetch one ticker's raw fundamentals with retry/backoff.

    Sets ``rate_limited=True`` on the returned dict when a 429/throttle was seen,
    so a :class:`SessionManager` can back its pacing off and re-warm the session.
    """
    last_err = None
    rate_limited = False
    for attempt in range(max_retries):
        try:
            tk = _ticker(symbol, session)
            try:
                info = tk.info or {}
            except Exception:
                info = {}
            annual = _statement_block(tk.income_stmt)
            quarterly = _statement_block(tk.quarterly_income_stmt)
            try:
                hist = tk.history(period=config.PRICE_LOOKBACK, auto_adjust=True)
            except Exception:
                hist = None
            feats, monthly = _price_features(hist)
            # The surprise leg parses a separate (often malformed) DataFrame; isolate
            # it so a parse error there can never discard the good statement / price /
            # valuation data for the whole ticker.
            surprises = []
            if with_surprises:
                try:
                    surprises = _earnings_surprises(tk)
                except Exception:
                    surprises = []

            valuation = {f: info.get(f) for f in config.VALUATION_FIELDS}
            has_data = any(
                any(not math.isnan(x) for x in annual.get(k, []))
                for k in ("revenue", "ebitda", "earnings")
            )
            return {
                "symbol": symbol,
                "asof": datetime.now(timezone.utc).isoformat(),
                "annual": annual,
                "quarterly": quarterly,
                "valuation": valuation,
                "prices": {**feats, "monthly": monthly},
                "surprises": surprises,
                "fetch_ok": bool(has_data or valuation.get("marketCap")),
            }
        except Exception as err:  # noqa: BLE001 — broad on purpose, then back off
            last_err = err
            msg = str(err).lower()
            hit = ("429" in msg or "too many request" in msg or "rate limit" in msg
                   or "rate-limit" in msg)
            rate_limited = rate_limited or hit
            if attempt < max_retries - 1:
                # Back off 3x harder on an explicit rate-limit signal than on a
                # generic transient error, so we yield the shared IP's window.
                time.sleep(config.BACKOFF_BASE * (2**attempt) * (3.0 if hit else 1.0))
    return {
        "symbol": symbol,
        "asof": datetime.now(timezone.utc).isoformat(),
        "annual": {},
        "quarterly": {},
        "valuation": {},
        "prices": {},
        "surprises": [],   # present-but-empty: keeps the negative cache effective
        "fetch_ok": False,
        "rate_limited": rate_limited,
        "error": str(last_err) if last_err else "unknown",
    }


def load_or_fetch(symbol: str, session=None, refresh: bool = False,
                  ttl_days: float = config.CACHE_TTL_DAYS) -> dict:
    if not refresh:
        cached = load_raw(symbol, ttl_days=ttl_days)
        if cached is not None:
            return cached
    raw = fetch_raw(symbol, session=session)
    if raw.get("fetch_ok"):
        save_raw(symbol, raw)
    return raw


# --------------------------------------------------------------------------- #
# Build the flat fundamentals + metrics table
# --------------------------------------------------------------------------- #
_ID_COLS = ["symbol", "name", "sector", "industry_group", "industry", "size_bucket", "currency", "region"]
# yfinance .info fields renamed to avoid clobbering financedatabase grouping keys.
_RENAME = {"sector": "yf_sector", "industry": "yf_industry", "currency": "yf_currency"}


def build_fundamentals(
    universe: pd.DataFrame,
    limit: int | None = None,
    symbols: list[str] | None = None,
    refresh: bool = False,
    ttl_days: float = config.CACHE_TTL_DAYS,
    fail_ttl_days: float = config.FAIL_CACHE_TTL_DAYS,
    surprise_regions: tuple[str, ...] | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Fetch + compute metrics for the universe, returning a flat table.

    ``surprise_regions`` enables the (extra, US-centric) EPS-surprise pull only
    for symbols in those regions, to avoid wasting calls on markets Yahoo has no
    surprise coverage for. Pass ``ttl_days=float('inf')`` for a PURE-CACHE rebuild
    that must never re-fetch (e.g. when the cache is older than CACHE_TTL_DAYS but
    the transport is unavailable) — otherwise stale-but-good cached raws expire and
    a failed re-fetch would overwrite them.
    """
    if symbols is not None:
        syms = list(symbols)
    else:
        syms = universe["symbol"].tolist()
        if limit:
            syms = syms[:limit]

    sym_region = (dict(zip(universe["symbol"], universe["region"]))
                  if surprise_regions and "region" in universe.columns else {})

    mgr = SessionManager()
    rows = []
    n = len(syms)
    for i, sym in enumerate(syms, 1):
        cached = None if refresh else load_raw(sym, ttl_days=ttl_days, fail_ttl_days=fail_ttl_days)
        # Accept the cached raw unless a surprise run needs a surprises key it
        # lacks — but never re-fetch a FAILED raw just for surprises (failure
        # stubs carry no surprises key; requiring one defeated the negative
        # cache and re-hammered every dead ticker on every surprise run).
        if cached is not None and (not surprise_regions
                                   or not cached.get("fetch_ok")
                                   or "surprises" in cached):
            raw = cached
        else:
            ws = bool(surprise_regions) and sym_region.get(sym) in surprise_regions
            # mgr.fetch paces adaptively, flags 429s, and re-warms the session
            # after a run of failures. Only live calls go through it (cache hits
            # above skip the limiter entirely).
            raw = mgr.fetch(sym, with_surprises=ws)
            if raw.get("fetch_ok"):
                # Cache successes long, failures briefly (negative cache).
                save_raw(sym, raw)
            else:
                # NEVER overwrite a good cached raw with a failure: when the
                # transport is broken/throttled (e.g. curl_cffi TLS-reset through
                # the agent proxy) a TTL-expired re-fetch fails and would erase
                # real data. Keep and USE the stale-but-good raw instead.
                prior = load_raw(sym, ttl_days=None, fail_ttl_days=None)
                if prior is not None and prior.get("fetch_ok"):
                    raw = prior
                else:
                    save_raw(sym, raw)   # only stamp failure over nothing/failure
        row = metrics.compute_metrics(raw)
        # Rename yfinance info fields that collide with fd grouping columns.
        for src, dst in _RENAME.items():
            if src in row:
                row[dst] = row.pop(src)
        row["fetch_ok"] = raw.get("fetch_ok", False)
        rows.append(row)
        if verbose and (i % 25 == 0 or i == n):
            ok = sum(1 for r in rows if r.get("fetch_ok"))
            extra = f", {mgr.refreshes} session refresh(es)" if mgr.refreshes else ""
            print(f"  [{i}/{n}] processed, {ok} with data{extra}", flush=True)

    metrics_df = pd.DataFrame(rows)
    id_cols = [c for c in _ID_COLS if c in universe.columns]
    out = metrics_df.merge(universe[id_cols], on="symbol", how="left")
    return _sanitize(out)


# yfinance .info occasionally returns strings ('Infinity', 'N/A') for these
# numeric fields, which makes the column object-typed and unwritable to parquet.
_NUMERIC_INFO = [
    "trailingPE", "forwardPE", "enterpriseToEbitda",
    "priceToSalesTrailing12Months", "priceToBook", "pegRatio",
    "marketCap", "enterpriseValue",
]


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric info fields and strip ±inf so the table is parquet-safe."""
    out = df.copy()
    for col in _NUMERIC_INFO:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    num = out.select_dtypes(include=["number"]).columns
    if len(num):
        out[num] = out[num].replace([np.inf, -np.inf], np.nan)
    return out


def save_fundamentals(df: pd.DataFrame, path: Path = config.FUNDAMENTALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_fundamentals(path: Path = config.FUNDAMENTALS_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)
