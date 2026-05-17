"""Universe construction via `financedatabase`.

financedatabase is a free, no-key package maintained by Jeroen Bouma that
ships curated metadata for equities, ETFs, funds, crypto, indices, currencies,
and money markets. We use it to bootstrap a point-in-time-agnostic universe
plus a brand/alias mapping that downstream entity resolution consumes.

Falls back to a tiny hard-coded universe if financedatabase isn't installed,
so the pipeline still works in restricted environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)

_FALLBACK_ROWS: list[dict] = [
    {"symbol": "MAT", "name": "Mattel, Inc.", "sector": "Consumer Cyclical", "industry": "Leisure", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "CROX", "name": "Crocs, Inc.", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "CELH", "name": "Celsius Holdings, Inc.", "sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "TPR", "name": "Tapestry, Inc.", "sector": "Consumer Cyclical", "industry": "Luxury Goods", "country": "United States", "exchange": "NYSE"},
    {"symbol": "NWL", "name": "Newell Brands Inc.", "sector": "Consumer Defensive", "industry": "Household & Personal Products", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "GME", "name": "GameStop Corp.", "sector": "Consumer Cyclical", "industry": "Specialty Retail", "country": "United States", "exchange": "NYSE"},
    {"symbol": "LULU", "name": "Lululemon Athletica Inc.", "sector": "Consumer Cyclical", "industry": "Apparel Manufacturing", "country": "United States", "exchange": "NASDAQ"},
    {"symbol": "UAA", "name": "Under Armour, Inc.", "sector": "Consumer Cyclical", "industry": "Apparel Manufacturing", "country": "United States", "exchange": "NYSE"},
    {"symbol": "DECK", "name": "Deckers Outdoor Corporation", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories", "country": "United States", "exchange": "NYSE"},
]


def load_equities_from_financedatabase(country: str | None = "United States") -> pd.DataFrame:
    """Load equity metadata from financedatabase.

    Returns DataFrame with columns: symbol, name, sector, industry, country,
    exchange (best-effort across financedatabase versions).
    """
    try:
        import financedatabase as fd
    except ImportError:
        log.warning("financedatabase not installed; using fallback universe")
        return pd.DataFrame(_FALLBACK_ROWS)

    try:
        equities = fd.Equities()
        df = equities.select(country=country) if country else equities.select()
    except Exception as exc:  # noqa: BLE001
        log.warning("financedatabase select failed (%s); using fallback", exc)
        return pd.DataFrame(_FALLBACK_ROWS)

    if df is None or df.empty:
        return pd.DataFrame(_FALLBACK_ROWS)

    df = df.reset_index().rename(columns={"index": "symbol"})
    keep = ["symbol", "name", "sector", "industry", "country", "exchange"]
    for col in keep:
        if col not in df.columns:
            df[col] = pd.NA
    return df[keep].dropna(subset=["symbol", "name"]).reset_index(drop=True)


def load_etfs_from_financedatabase() -> pd.DataFrame:
    try:
        import financedatabase as fd
        df = fd.ETFs().select().reset_index().rename(columns={"index": "symbol"})
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["symbol", "name", "category_group", "category"])

    for col in ("symbol", "name", "category_group", "category"):
        if col not in df.columns:
            df[col] = pd.NA
    return df[["symbol", "name", "category_group", "category"]].dropna(subset=["symbol"]).reset_index(drop=True)


def filter_consumer_focused(equities: pd.DataFrame) -> pd.DataFrame:
    """Camillo's universe is heavily consumer-cyclical and consumer-defensive."""
    if equities.empty or "sector" not in equities.columns:
        return equities
    mask = equities["sector"].isin(["Consumer Cyclical", "Consumer Defensive", "Communication Services"])
    return equities[mask].reset_index(drop=True)


def build_universe(cfg: Config, country: str | None = "United States", refresh: bool = False) -> pd.DataFrame:
    """Materialize the equity universe to parquet on disk."""
    cfg.ensure_dirs()
    path = Path(cfg.universe_parquet)
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    df = load_equities_from_financedatabase(country=country)
    df.to_parquet(path, index=False)
    return df


def symbols(universe: pd.DataFrame) -> list[str]:
    return universe["symbol"].astype(str).tolist()


def search(universe: pd.DataFrame, query: str, limit: int = 25) -> pd.DataFrame:
    q = query.lower().strip()
    mask = (
        universe["symbol"].astype(str).str.lower().str.contains(q, na=False)
        | universe["name"].astype(str).str.lower().str.contains(q, na=False)
    )
    return universe[mask].head(limit).reset_index(drop=True)
