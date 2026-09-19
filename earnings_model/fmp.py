"""Financial Modeling Prep (FMP) balance-sheet / cash-flow / quality overlay.

The Yahoo+EDGAR pipeline gives an income statement and market multiples but NO
balance-sheet or cash-flow view — yet the manual web-validation leans on exactly
that ("net cash", "leverage <1x", "FCF yield", "cash conversion"). FMP's ULTIMATE
plan exposes ``key-metrics-ttm-bulk``: one CSV with net-debt/EBITDA, FCF yield,
ROIC/ROE, current ratio and income quality (OCF/net-income) for the whole market,
so a single call overlays ~26k of our names — no per-symbol fetch storm.

The overlay is ADDITIVE and OPTIONAL: every column is prefixed ``fmp_`` (no
collision with the Yahoo columns), and :func:`attach` is a no-op when the parquet
is absent, so the pipeline runs unchanged without FMP. The API key is read from
the ``FMP_API_KEY`` environment variable and is NEVER written to disk or git.

    export FMP_API_KEY=...            # never commit this
    python scripts/fetch_fmp.py       # bulk -> data/fmp_metrics.parquet
"""
from __future__ import annotations

import io
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from . import config, util

BASE = "https://financialmodelingprep.com/stable"
KEY_ENV = "FMP_API_KEY"
FMP_METRICS_PATH = config.DATA_DIR / "fmp_metrics.parquet"

# FMP key-metrics-ttm field -> our clean, fmp_-prefixed column. Chosen for what the
# income-statement pipeline CANNOT see: balance-sheet strength, cash-flow-based
# valuation, capital-efficiency and earnings quality.
_FIELD_MAP = {
    "netDebtToEBITDATTM": "fmp_net_debt_to_ebitda",
    "freeCashFlowYieldTTM": "fmp_fcf_yield",
    "earningsYieldTTM": "fmp_earnings_yield",
    "returnOnInvestedCapitalTTM": "fmp_roic",
    "returnOnEquityTTM": "fmp_roe",
    "returnOnAssetsTTM": "fmp_roa",
    "currentRatioTTM": "fmp_current_ratio",
    "incomeQualityTTM": "fmp_income_quality",       # operating cash flow / net income
    "evToFreeCashFlowTTM": "fmp_ev_to_fcf",
    "evToEBITDATTM": "fmp_ev_to_ebitda",            # cross-check vs Yahoo's enterpriseToEbitda
    "capexToRevenueTTM": "fmp_capex_to_revenue",
}

# Plausible bounds. FMP's TTM ratios explode on near-zero denominators (invested
# capital ~0 gives ROIC of 3,000,000%; a tiny share count gives FCF yield -571%),
# and such artifacts would dominate any ranking. Values outside these bands are
# treated as not-meaningful (-> NaN) rather than trusted — the same discipline the
# Yahoo-multiple guards already apply. Net cash / net-debt sign survives (band
# keeps negatives), so the derived flags are unaffected.
_BOUNDS = {
    "fmp_net_debt_to_ebitda": (-10.0, 30.0),
    "fmp_fcf_yield": (-0.5, 0.5),
    "fmp_earnings_yield": (-0.5, 0.5),
    "fmp_roic": (-2.0, 2.0),
    "fmp_roe": (-2.0, 2.0),
    "fmp_roa": (-1.0, 1.0),
    "fmp_current_ratio": (0.0, 50.0),
    "fmp_income_quality": (-10.0, 10.0),
    "fmp_ev_to_fcf": (-100.0, 300.0),
    "fmp_ev_to_ebitda": (-50.0, 150.0),
}


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """Null near-zero-denominator artifacts so ranks/displays reflect real ratios."""
    for c, (lo, hi) in _BOUNDS.items():
        if c in df.columns:
            v = pd.to_numeric(df[c], errors="coerce")
            df[c] = v.where((v >= lo) & (v <= hi))
    return df


# Same-security exchange-suffix aliases (our Yahoo suffix -> FMP suffix). Frankfurt
# floor (.F) and Xetra (.DE) are the same Deutsche Börse listing; FMP normalises
# Taiwan OTC (.TWO) to .TW. High confidence (identical ticker base, same market),
# so relabelling is safe. Other unmatched suffixes (Korea .KQ, Thailand .BK, Turkey
# .IS, ...) are genuine FMP coverage gaps, not aliases, so they are NOT mapped.
_SUFFIX_ALIAS = {".F": ".DE", ".TWO": ".TW"}


def _fmp_candidates(our_sym: str):
    """FMP symbols to try for one of our symbols: direct first, then a suffix alias."""
    yield our_sym
    for us, fs in _SUFFIX_ALIAS.items():
        if our_sym.endswith(us):
            yield our_sym[: -len(us)] + fs


def _key() -> str:
    k = os.environ.get(KEY_ENV)
    if not k:
        raise RuntimeError(
            f"{KEY_ENV} not set. Export the FMP API key before fetching "
            f"(it must never be committed to the repo).")
    return k


def fetch_bulk_key_metrics() -> pd.DataFrame:
    """Download the whole-market key-metrics-ttm bulk CSV (proxy-safe urllib, with
    429 backoff via :func:`_fetch_csv`)."""
    return _fetch_csv("key-metrics-ttm-bulk?")


def build_overlay(universe_symbols: set[str] | None = None) -> pd.DataFrame:
    """Fetch bulk metrics, select+rename the overlay fields, and (optionally) map
    to the symbols we actually track. Returns a compact per-symbol frame keyed on
    OUR symbols (aliased FMP rows are relabelled, so :func:`attach` joins cleanly).
    """
    km = fetch_bulk_key_metrics()
    km = km[["symbol"] + [c for c in _FIELD_MAP if c in km.columns]].copy()
    km = km.rename(columns=_FIELD_MAP)
    for c in _FIELD_MAP.values():
        if c in km.columns:
            km[c] = pd.to_numeric(km[c], errors="coerce")
    km = km.dropna(subset=["symbol"]).drop_duplicates("symbol")
    km = _sanitize(km)
    if universe_symbols is None:
        return km.reset_index(drop=True)
    # Match each of our symbols to its FMP row — direct first, then a same-security
    # exchange-suffix alias (Frankfurt .F -> Xetra .DE, Taiwan OTC .TWO -> .TW) —
    # and relabel the matched row to OUR symbol.
    km["symbol"] = km["symbol"].astype(str)
    by_sym = {s: i for i, s in enumerate(km["symbol"])}
    rows = []
    for us in universe_symbols:
        for cand in _fmp_candidates(str(us)):
            j = by_sym.get(cand)
            if j is not None:
                r = km.iloc[j].copy()
                r["symbol"] = us
                rows.append(r)
                break
    return pd.DataFrame(rows).reset_index(drop=True) if rows else km.iloc[0:0].copy()


def save_overlay(df: pd.DataFrame, path: Path = FMP_METRICS_PATH) -> None:
    util.atomic_to_parquet(df, path)


# --------------------------------------------------------------------------- #
# Earnings-surprise history + forward analyst estimates (additive fmp_* columns)
# --------------------------------------------------------------------------- #
def _fetch_csv(endpoint: str, retries: int = 4) -> pd.DataFrame:
    url = f"{BASE}/{endpoint}&apikey={_key()}"
    req = urllib.request.Request(url, headers={"User-Agent": "cyclepapa/1.0"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read().decode("utf-8", "replace")
            if raw.lstrip().startswith("{") or raw.lstrip().startswith("Query"):
                raise RuntimeError(f"FMP bulk error for {endpoint}: {raw[:160]}")
            return pd.read_csv(io.StringIO(raw))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and attempt < retries - 1:      # throttled: back off hard
                time.sleep(10 * (2 ** attempt))
                continue
            break
        except Exception as e:                                # noqa: BLE001
            last = e
            break
    raise RuntimeError(f"FMP fetch failed for {endpoint}: {last}")


def _recent_quarters(n: int = 8):
    """The last ``n`` fiscal (year, 'Q#') pairs, newest first — most recent COMPLETE
    quarter is one back from the current calendar quarter (this one isn't reported)."""
    from datetime import date
    y, q = date.today().year, (date.today().month - 1) // 3 + 1
    out = []
    q -= 1
    if q == 0:
        y, q = y - 1, 4
    for _ in range(n):
        out.append((y, f"Q{q}"))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def _surprise_metrics(hist: pd.DataFrame) -> dict:
    """Clean EPS-surprise metrics for one symbol from its (date, actual, est) rows.

    beat_rate + streak are SCALE-FREE (sign only), so a serial tiny-EPS beater
    doesn't distort them; the magnitude (avg4) uses per-quarter surprise CLAMPED to
    +/-50% so a beat off a ~$0 estimate can't explode the average (the same
    near-zero-denominator artifact the Yahoo surprise clamp guards)."""
    h = hist.dropna(subset=["epsActual", "epsEstimated"]).sort_values("date")
    if h.empty:
        return {}
    beats = (h["epsActual"] > h["epsEstimated"]).tolist()
    est = h["epsEstimated"].abs().where(h["epsEstimated"].abs() > 1e-6)
    surp = ((h["epsActual"] - h["epsEstimated"]) / est).clip(-0.5, 0.5)
    streak = 0
    for b in reversed(beats):
        if b:
            streak += 1
        else:
            break
    return {
        "fmp_eps_beat_rate": float(sum(beats)) / len(beats),
        "fmp_eps_surprise_avg4": float(surp.tail(4).mean()) if surp.tail(4).notna().any() else float("nan"),
        "fmp_eps_streak": streak,
        "fmp_eps_quarters": len(beats),
    }


def build_earnings_overlay(universe_symbols: set[str] | None = None,
                           quarters: int = 8) -> pd.DataFrame:
    """Per-symbol clean EPS-surprise metrics (last ``quarters``) + forward consensus
    growth (next-FY vs this-FY revenue/EPS avg estimates). All additive fmp_* fields.
    """
    want = set(map(str, universe_symbols)) if universe_symbols is not None else None

    # --- surprise history: one bulk CSV per fiscal quarter ------------------- #
    frames = []
    for y, p in _recent_quarters(quarters):
        try:
            df = _fetch_csv(f"earnings-surprises-bulk?year={y}&period={p}")
        except RuntimeError:
            continue
        df = df[["symbol", "date", "epsActual", "epsEstimated"]].copy()
        if want is not None:
            df = df[df["symbol"].astype(str).isin(want)]
        frames.append(df)
        time.sleep(22.0)                             # pace bulk calls (severe FMP bulk limit)
    hist = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["symbol", "date", "epsActual", "epsEstimated"])
    for c in ("epsActual", "epsEstimated"):
        hist[c] = pd.to_numeric(hist[c], errors="coerce")
    surp = (hist.groupby("symbol", group_keys=False)
                .apply(lambda g: pd.Series(_surprise_metrics(g)))
                .reset_index()) if len(hist) else pd.DataFrame(columns=["symbol"])

    # --- forward consensus growth: this-FY vs next-FY avg estimates ---------- #
    from datetime import date
    y0 = date.today().year
    est = {}
    for yr in (y0, y0 + 1):
        try:
            e = _fetch_csv(f"analyst-estimates-bulk?year={yr}&period=annual")
        except RuntimeError:
            continue
        e = e[["symbol", "revenueAvg", "epsAvg", "numAnalystsEps"]].copy()
        if want is not None:
            e = e[e["symbol"].astype(str).isin(want)]
        est[yr] = e.set_index("symbol")
        time.sleep(22.0)
    fwd = pd.DataFrame(columns=["symbol"])
    if y0 in est and (y0 + 1) in est:
        a, b = est[y0], est[y0 + 1]
        common = a.index.intersection(b.index)
        rev0, rev1 = pd.to_numeric(a.loc[common, "revenueAvg"], errors="coerce"), pd.to_numeric(b.loc[common, "revenueAvg"], errors="coerce")
        eps0, eps1 = pd.to_numeric(a.loc[common, "epsAvg"], errors="coerce"), pd.to_numeric(b.loc[common, "epsAvg"], errors="coerce")
        fwd = pd.DataFrame({
            "symbol": common,
            "fmp_fwd_rev_growth": (rev1 / rev0.where(rev0 > 0) - 1.0).values,
            "fmp_fwd_eps_growth": (eps1 / eps0.where(eps0 > 0) - 1.0).values,
            "fmp_analysts_eps": pd.to_numeric(a.loc[common, "numAnalystsEps"], errors="coerce").values,
        })

    out = surp.merge(fwd, on="symbol", how="outer") if len(surp) or len(fwd) else pd.DataFrame(columns=["symbol"])
    # forward-growth ratios can still blow up off a tiny base — bound them
    for c in ("fmp_fwd_rev_growth", "fmp_fwd_eps_growth"):
        if c in out.columns:
            v = pd.to_numeric(out[c], errors="coerce")
            out[c] = v.where((v >= -1.0) & (v <= 3.0))
    return out.reset_index(drop=True)




def load_overlay(path: Path = FMP_METRICS_PATH) -> pd.DataFrame | None:
    if not Path(path).exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Derived flags — the point of the overlay: things the income statement can't show
# --------------------------------------------------------------------------- #
def _derive(out: pd.DataFrame) -> pd.DataFrame:
    """Add boolean/quality flags from the raw FMP fields (all guarded for NaN)."""
    if "fmp_net_debt_to_ebitda" in out.columns:
        nd = out["fmp_net_debt_to_ebitda"]
        # Net cash: negative net-debt/EBITDA WITH positive earnings yield (so it is
        # cash-rich, not a negative-EBITDA sign flip). Over-levered: > 4x.
        ey = out.get("fmp_earnings_yield")
        out["fmp_net_cash"] = (nd < 0) & (ey.fillna(-1) > 0 if ey is not None else False)
        out["fmp_over_levered"] = nd > 4.0
    if "fmp_income_quality" in out.columns:
        # Accrual-inflated earnings: operating cash flow well below net income.
        # (Financials read high here from non-cash provisioning, so this is a
        # yellow flag for screening, not a verdict.)
        out["fmp_low_income_quality"] = out["fmp_income_quality"] < 0.5
    return out


def attach(scored: pd.DataFrame, path: Path = FMP_METRICS_PATH) -> pd.DataFrame:
    """Left-join the FMP overlay onto a scored frame by symbol, adding the fmp_*
    columns + derived flags. A NO-OP (returns the frame unchanged) when the overlay
    parquet is absent, so the pipeline never depends on FMP being present."""
    ov = load_overlay(path)
    if ov is None or "symbol" not in scored.columns:
        return scored
    ov = _derive(_sanitize(ov))
    dup = [c for c in ov.columns if c != "symbol" and c in scored.columns]
    scored = scored.drop(columns=dup, errors="ignore")
    return scored.merge(ov, on="symbol", how="left")
