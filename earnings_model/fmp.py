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


def _key() -> str:
    k = os.environ.get(KEY_ENV)
    if not k:
        raise RuntimeError(
            f"{KEY_ENV} not set. Export the FMP API key before fetching "
            f"(it must never be committed to the repo).")
    return k


def fetch_bulk_key_metrics() -> pd.DataFrame:
    """Download the whole-market key-metrics-ttm bulk CSV via the proxy-safe urllib
    transport and return it as a DataFrame (raw FMP columns)."""
    url = f"{BASE}/key-metrics-ttm-bulk?apikey={_key()}"
    req = urllib.request.Request(url, headers={"User-Agent": "cyclepapa/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode("utf-8", "replace")
    if raw.lstrip().startswith("{"):                # an error object, not CSV
        raise RuntimeError(f"FMP bulk returned non-CSV: {raw[:200]}")
    return pd.read_csv(io.StringIO(raw))


def build_overlay(universe_symbols: set[str] | None = None) -> pd.DataFrame:
    """Fetch bulk metrics, select+rename the overlay fields, and (optionally) filter
    to the symbols we actually track. Returns a compact per-symbol frame."""
    km = fetch_bulk_key_metrics()
    km = km[["symbol"] + [c for c in _FIELD_MAP if c in km.columns]].copy()
    km = km.rename(columns=_FIELD_MAP)
    for c in _FIELD_MAP.values():
        if c in km.columns:
            km[c] = pd.to_numeric(km[c], errors="coerce")
    km = km.dropna(subset=["symbol"]).drop_duplicates("symbol")
    km = _sanitize(km)
    if universe_symbols is not None:
        km = km[km["symbol"].astype(str).isin(universe_symbols)]
    return km.reset_index(drop=True)


def save_overlay(df: pd.DataFrame, path: Path = FMP_METRICS_PATH) -> None:
    util.atomic_to_parquet(df, path)


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
