"""Central configuration for the UK earnings-modelling toolkit."""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Cache locations
# --------------------------------------------------------------------------- #
CACHE_DIR = Path(os.environ.get("EARNINGS_CACHE", "cache"))
UNIVERSE_PATH = CACHE_DIR / "universe.parquet"
FUNDAMENTALS_PATH = CACHE_DIR / "fundamentals.parquet"
RAW_CACHE_DIR = CACHE_DIR / "raw"          # one parquet/json per ticker

# --------------------------------------------------------------------------- #
# Universe defaults  (UK equities complex)
# --------------------------------------------------------------------------- #
DEFAULT_COUNTRY = "United Kingdom"
DEFAULT_EXCHANGES = ("LSE",)
DEFAULT_CURRENCIES = ("GBP",)

# Main US listing venues in financedatabase (NASDAQ GS/GM/CM, NYSE, AMEX, ...).
DEFAULT_US_EXCHANGES = ("NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BATS")
US_SMALL_BUCKETS = ("Small Cap", "Micro Cap")

# Named universe presets for build-universe / run. Each preset is a list of
# segments; every segment is kwargs for universe.build_universe().
UNIVERSE_PRESETS = {
    "uk": [dict(region="UK", country="United Kingdom",
                exchanges=("LSE",), currencies=("GBP",))],
    "us-small": [dict(region="US", country="United States",
                      exchanges=DEFAULT_US_EXCHANGES, currencies=("USD",),
                      size_filter=US_SMALL_BUCKETS)],
}
UNIVERSE_PRESETS["uk+us-small"] = UNIVERSE_PRESETS["uk"] + UNIVERSE_PRESETS["us-small"]

# --------------------------------------------------------------------------- #
# Size buckets — financedatabase market_cap labels, nano -> mega
# --------------------------------------------------------------------------- #
SIZE_ORDER = ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]
UNCLASSIFIED = "Unclassified"

# Fallback thresholds for names with no financedatabase label (opt-in via
# --backfill-size). Market cap is converted to USD with the static rates below
# purely for bucketing; this is a coarse backstop, not a valuation input.
SIZE_THRESHOLDS_USD = [
    (50e6, "Nano Cap"),
    (300e6, "Micro Cap"),
    (2e9, "Small Cap"),
    (10e9, "Mid Cap"),
    (200e9, "Large Cap"),
    (float("inf"), "Mega Cap"),
]
FX_TO_USD = {"GBP": 1.27, "GBp": 0.0127, "USD": 1.0, "EUR": 1.08, "PENNY": 0.0127}

# --------------------------------------------------------------------------- #
# yfinance income-statement line-item resolution (names vary by ticker)
# --------------------------------------------------------------------------- #
REVENUE_KEYS = ["Total Revenue", "TotalRevenue", "Operating Revenue", "Revenue"]
EBITDA_KEYS = ["EBITDA", "Normalized EBITDA"]
NET_INCOME_KEYS = [
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income Continuous Operations",
    "Net Income From Continuing Operation Net Minority Interest",
]
EPS_KEYS = ["Diluted EPS", "Basic EPS"]
OPERATING_INCOME_KEYS = ["Operating Income", "Total Operating Income As Reported"]
DA_KEYS = [
    "Reconciled Depreciation",
    "Depreciation And Amortization",
    "Depreciation Amortization Depletion",
]

# Base metrics we compute growth / acceleration / inflection on.
# (earnings == net income to common shareholders)
METRICS = ["revenue", "ebitda", "earnings"]

# --------------------------------------------------------------------------- #
# Valuation fields pulled from yfinance .info
# --------------------------------------------------------------------------- #
VALUATION_FIELDS = [
    "trailingPE",
    "forwardPE",
    "enterpriseToEbitda",
    "priceToSalesTrailing12Months",
    "priceToBook",
    "pegRatio",
    "marketCap",
    "enterpriseValue",
    "currency",
    "sector",
    "industry",
]

# --------------------------------------------------------------------------- #
# Fetch resilience
# --------------------------------------------------------------------------- #
MAX_RETRIES = 4
BACKOFF_BASE = 2.0           # seconds -> 2, 4, 8, 16
REQUEST_JITTER = (0.4, 1.2)  # random pause between tickers to ease rate limits
CACHE_TTL_DAYS = 5           # reuse cached fundamentals younger than this
PRICE_LOOKBACK = "5y"        # daily closes -> monthly; enough for multi-year dormancy

# Price-derived features carried into the flat table (computed from monthly closes).
PRICE_FEATURE_KEYS = [
    "ret_1m", "ret_3m", "ret_6m", "ret_12m", "ret_24m", "ret_36m",
    "last_price", "max_drawdown", "range_position", "trend_slope", "realized_vol",
]

# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #
CLUSTER_FEATURES = [
    "revenue_growth",
    "revenue_accel",
    "ebitda_growth",
    "ebitda_accel",
    "earnings_growth",
    "earnings_accel",
]
KMEANS_K_RANGE = range(3, 11)
RANDOM_STATE = 42
