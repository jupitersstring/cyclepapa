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


CONSUMER_SECTORS = frozenset({
    "Consumer Cyclical", "Consumer Defensive",       # yfinance taxonomy
    "Consumer Discretionary", "Consumer Staples",    # financedatabase / GICS
    "Communication Services",
})


def filter_consumer_focused(equities: pd.DataFrame) -> pd.DataFrame:
    """Camillo's universe is heavily consumer-cyclical and consumer-defensive."""
    if equities.empty or "sector" not in equities.columns:
        return equities
    mask = equities["sector"].isin(CONSUMER_SECTORS)
    return equities[mask].reset_index(drop=True)


# Yahoo Finance exchange codes for the primary US listings.
US_EXCHANGE_CODES = frozenset({"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BATS"})


def filter_us_liquid(equities: pd.DataFrame) -> pd.DataFrame:
    """US-listed equities with a known sector (proxy for "investable").

    Drops OTC / pink / international ADRs. Strips suffixes like `.L`, `.TO`,
    `.SA` that financedatabase tags onto foreign cross-listings -- we want
    the primary US symbol that yfinance will recognize.
    """
    if equities.empty:
        return equities
    df = equities.copy()
    # Drop any symbol containing a dot (cross-listings, share classes
    # already present as `BRK-B` etc don't carry dots in Yahoo's catalog).
    df = df[~df["symbol"].astype(str).str.contains(r"\.", na=False)]
    if "exchange" in df.columns:
        df = df[df["exchange"].isin(US_EXCHANGE_CODES) | df["exchange"].isna()]
    if "country" in df.columns:
        df = df[df["country"].isin(["United States"]) | df["country"].isna()]
    if "sector" in df.columns:
        df = df[df["sector"].notna()]
    # Keep length-1..5 alphanumeric tickers; reject anything with non-letters.
    df = df[df["symbol"].astype(str).str.fullmatch(r"[A-Z]{1,5}", na=False)]
    # Drop common SPAC/unit/warrant patterns: tickers ending in U or W,
    # and names matching "unit"/"warrant"/"acquisition".
    sym = df["symbol"].astype(str)
    name = df["name"].astype(str).str.lower()
    junk_name = name.str.contains(r"\b(?:unit|warrant|acquisition corp|spac)\b", regex=True, na=False)
    df = df.loc[~junk_name]
    # SPAC units/warrants tend to end in 'U' or 'W' AND be 5-char tickers.
    sym2 = df["symbol"].astype(str)
    spac_suffix = sym2.str.len().eq(5) & sym2.str.endswith(("U", "W"))
    df = df.loc[~spac_suffix]
    return df.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


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
