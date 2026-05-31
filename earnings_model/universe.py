"""Build the investable universe from financedatabase.

financedatabase tags every equity with ``sector``, ``industry_group``,
``industry`` (the granular label we want — ~60 distinct values for the UK)
and a ``market_cap`` size label (Nano/Micro/Small/Mid/Large/Mega Cap).
"United Kingdom" also returns many foreign cross-listings on the LSE's
International Order Book, so we filter to genuine GBP-quoted LSE lines.
"""
from __future__ import annotations

import pandas as pd

from . import config

# Columns we carry forward from financedatabase.
_KEEP = [
    "symbol",
    "name",
    "sector",
    "industry_group",
    "industry",
    "market_cap",
    "currency",
    "exchange",
    "country",
]


def _bucket_from_market_cap_usd(market_cap_usd: float) -> str:
    """Map a USD market cap onto a nano->mega bucket (fallback only)."""
    if market_cap_usd is None or not (market_cap_usd == market_cap_usd):  # NaN check
        return config.UNCLASSIFIED
    for ceiling, label in config.SIZE_THRESHOLDS_USD:
        if market_cap_usd < ceiling:
            return label
    return config.UNCLASSIFIED


def build_universe(
    country: str = config.DEFAULT_COUNTRY,
    exchanges: tuple[str, ...] | None = config.DEFAULT_EXCHANGES,
    currencies: tuple[str, ...] | None = config.DEFAULT_CURRENCIES,
    require_industry: bool = False,
) -> pd.DataFrame:
    """Return a DataFrame of the investable universe.

    Parameters
    ----------
    country: financedatabase country name.
    exchanges: keep only these exchanges (None = no exchange filter).
    currencies: keep only these listing currencies (None = no filter).
    require_industry: drop names with no industry label.
    """
    import financedatabase as fd

    raw = fd.Equities().select(country=country)
    if raw is None or len(raw) == 0:
        raise ValueError(f"financedatabase returned no equities for country={country!r}")

    df = raw.reset_index()  # index name is 'symbol'
    if "symbol" not in df.columns and "index" in df.columns:
        df = df.rename(columns={"index": "symbol"})

    # Ensure all expected columns exist before subsetting.
    for col in _KEEP:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_KEEP].copy()

    if exchanges:
        df = df[df["exchange"].isin(exchanges)]
    if currencies:
        df = df[df["currency"].isin(currencies)]

    # Drop rows with no usable symbol.
    df = df[df["symbol"].notna() & (df["symbol"].astype(str).str.len() > 0)]

    # Size bucket straight from the financedatabase label; anything else
    # (incl. NaN) becomes "Unclassified" until optionally backfilled live.
    df["size_bucket"] = df["market_cap"].where(
        df["market_cap"].isin(config.SIZE_ORDER), config.UNCLASSIFIED
    )

    # Human-friendly fills for grouping keys.
    df["industry"] = df["industry"].fillna("Unknown")
    df["industry_group"] = df["industry_group"].fillna("Unknown")
    df["sector"] = df["sector"].fillna("Unknown")

    if require_industry:
        df = df[df["industry"] != "Unknown"]

    df = df.drop_duplicates(subset="symbol").sort_values(["industry", "size_bucket", "symbol"])
    df = df.reset_index(drop=True)
    return df


def backfill_size_buckets(universe: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    """Fill ``size_bucket == Unclassified`` rows using live market cap.

    Expects ``fundamentals`` to carry ``marketCap`` and ``currency`` columns
    (as produced by :mod:`earnings_model.fundamentals`).
    """
    out = universe.copy()
    caps = fundamentals.set_index("symbol")
    needs = out["size_bucket"].eq(config.UNCLASSIFIED) | out["size_bucket"].isna()
    for idx in out.index[needs]:
        sym = out.at[idx, "symbol"]
        if sym not in caps.index:
            continue
        mc = caps.at[sym, "marketCap"] if "marketCap" in caps.columns else None
        cur = caps.at[sym, "currency"] if "currency" in caps.columns else out.at[idx, "currency"]
        rate = config.FX_TO_USD.get(cur, 1.0)
        try:
            mc_usd = float(mc) * rate
        except (TypeError, ValueError):
            continue
        out.at[idx, "size_bucket"] = _bucket_from_market_cap_usd(mc_usd)
    return out


def size_bucket_dtype(df: pd.DataFrame, column: str = "size_bucket") -> pd.DataFrame:
    """Return a copy with ``column`` as an ordered categorical (nano->mega)."""
    out = df.copy()
    cats = config.SIZE_ORDER + [config.UNCLASSIFIED]
    out[column] = pd.Categorical(out[column], categories=cats, ordered=True)
    return out
