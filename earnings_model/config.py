"""Central configuration for the UK earnings-modelling toolkit."""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Cache locations
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parent.parent   # anchor; independent of CWD
CACHE_DIR = Path(os.environ.get("EARNINGS_CACHE", "cache"))
UNIVERSE_PATH = CACHE_DIR / "universe.parquet"
FUNDAMENTALS_PATH = CACHE_DIR / "fundamentals.parquet"
RAW_CACHE_DIR = CACHE_DIR / "raw"          # one parquet/json per ticker

# Durable, git-tracked snapshot of the assembled analysis (survives a rollback).
DATA_DIR = REPO_ROOT / "data"
# Bump when the scored/fundamentals schema changes so a stale snapshot is detectable.
SCHEMA_VERSION = 2

# --------------------------------------------------------------------------- #
# Data-quality guardrails (earnings_model.quality)
# --------------------------------------------------------------------------- #
# Trailing returns above this magnitude in a single window are almost always a
# Yahoo split/adjustment artifact (or a penny-stock near-zero base), not a real
# move — quarantined to NaN so they don't pollute the dormancy ranking.
RETURN_SANITY_ABS = 9.0          # 900% in 12m / 24m / 36m
# Per-quarter EPS-surprise % is winsorized to this before forming the robust
# (scale-stable) surprise stat, so a single beat off a ~$0 estimate can't dominate.
SURPRISE_WINSOR = 50.0

# --------------------------------------------------------------------------- #
# Universe defaults  (UK equities complex)
# --------------------------------------------------------------------------- #
DEFAULT_COUNTRY = "United Kingdom"
DEFAULT_EXCHANGES = ("LSE",)
DEFAULT_CURRENCIES = ("GBP",)

# Main US listing venues in financedatabase (NASDAQ GS/GM/CM, NYSE, AMEX, ...).
DEFAULT_US_EXCHANGES = ("NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BATS")
US_SMALL_BUCKETS = ("Small Cap", "Micro Cap")
US_MID_BUCKETS = ("Mid Cap",)
US_LARGE_BUCKETS = ("Large Cap", "Mega Cap")
SMID_LARGE = ("Small Cap", "Micro Cap", "Mid Cap", "Large Cap", "Mega Cap")

# EU primary exchanges per country — picks the home listing and drops the heavy
# German cross-listing duplication (VIE/STU/FRA/BER/MUN/DUS/HAM carry the same
# companies many times over).
EU_PRIMARY_EXCHANGES = {
    "Germany": ("GER", "FRA"), "France": ("PAR",), "Netherlands": ("AMS",),
    "Italy": ("MIL",), "Spain": ("MCE",), "Belgium": ("BRU",),
    "Ireland": ("ISE", "DUB"), "Finland": ("HEL",), "Portugal": ("LIS",),
    "Austria": ("VIE",), "Switzerland": ("EBS", "VTX"), "Sweden": ("STO",),
    "Denmark": ("CPH",), "Norway": ("OSL",),
}

# Named universe presets for build-universe / run. Each preset is a list of
# segments; every segment is kwargs for universe.build_universe().
UNIVERSE_PRESETS = {
    "uk": [dict(region="UK", country="United Kingdom",
                exchanges=("LSE",), currencies=("GBP",))],
    "us-small": [dict(region="US", country="United States",
                      exchanges=DEFAULT_US_EXCHANGES, currencies=("USD",),
                      size_filter=US_SMALL_BUCKETS)],
    "us-mid": [dict(region="US", country="United States",
                    exchanges=DEFAULT_US_EXCHANGES, currencies=("USD",),
                    size_filter=US_MID_BUCKETS)],
    "us-large": [dict(region="US", country="United States",
                      exchanges=DEFAULT_US_EXCHANGES, currencies=("USD",),
                      size_filter=US_LARGE_BUCKETS)],
}
# US small+mid+large (one segment, all buckets).
UNIVERSE_PRESETS["us"] = [dict(region="US", country="United States",
                               exchanges=DEFAULT_US_EXCHANGES, currencies=("USD",),
                               size_filter=SMID_LARGE)]
# EU: one segment per country, restricted to its primary exchange(s), L/M/S.
UNIVERSE_PRESETS["eu"] = [
    dict(region="EU", country=ctry, exchanges=exs, currencies=None,
         size_filter=SMID_LARGE)
    for ctry, exs in EU_PRIMARY_EXCHANGES.items()
]
UNIVERSE_PRESETS["uk+us-small"] = UNIVERSE_PRESETS["uk"] + UNIVERSE_PRESETS["us-small"]
UNIVERSE_PRESETS["us-smid"] = UNIVERSE_PRESETS["us-small"] + UNIVERSE_PRESETS["us-mid"]
UNIVERSE_PRESETS["uk+us-smid"] = (
    UNIVERSE_PRESETS["uk"] + UNIVERSE_PRESETS["us-small"] + UNIVERSE_PRESETS["us-mid"]
)
# Everything: UK (all) + US (small/mid/large) + EU (L/M/S, primary listings).
UNIVERSE_PRESETS["global"] = (
    UNIVERSE_PRESETS["uk"] + UNIVERSE_PRESETS["us"] + UNIVERSE_PRESETS["eu"]
)

# Rest-of-world home markets: (region bloc, country, primary exchange(s)). Each
# country restricted to its home exchange to avoid cross-listing duplication.
# India excluded by request; Russia excluded (sanctioned / no Yahoo data);
# domicile-havens (Luxembourg/Bermuda) excluded (listings sit on other venues).
ROW_SEGMENTS = [
    ("CA", "Canada", ("TOR",)),
    ("JP", "Japan", ("JPX",)),
    ("CN", "China", ("SHH", "SHZ")),
    ("HK", "Hong Kong", ("HKG",)),
    ("ANZ", "Australia", ("ASX",)),
    ("ANZ", "New Zealand", ("NZE",)),
    ("KR", "South Korea", ("KSC", "KOE")),
    ("TW", "Taiwan", ("TAI", "TWO")),
    ("SEA", "Singapore", ("SES",)),
    ("SEA", "Thailand", ("SET",)),
    ("SEA", "Indonesia", ("JKT",)),
    ("LATAM", "Brazil", ("SAO",)),
    ("LATAM", "Mexico", ("MEX",)),
    ("LATAM", "Chile", ("SGO",)),
    ("LATAM", "Argentina", ("BUE",)),
    ("MEA", "Saudi Arabia", ("SAU",)),
    ("MEA", "Israel", ("TLV",)),
    ("MEA", "Turkey", ("IST",)),
    ("MEA", "South Africa", ("JNB",)),
    ("MEA", "Greece", ("ATH",)),
]
UNIVERSE_PRESETS["row"] = [
    dict(region=reg, country=ctry, exchanges=exs, currencies=None, size_filter=SMID_LARGE)
    for reg, ctry, exs in ROW_SEGMENTS
]
# The whole investable world we cover (ex-India, ex-Russia).
UNIVERSE_PRESETS["world"] = UNIVERSE_PRESETS["global"] + UNIVERSE_PRESETS["row"]

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
FX_TO_USD = {"GBP": 1.27, "GBp": 0.0127, "USD": 1.0, "EUR": 1.08, "PENNY": 0.0127,
             "CHF": 1.12, "SEK": 0.095, "NOK": 0.092, "DKK": 0.145,
             "JPY": 0.0064, "CAD": 0.73, "AUD": 0.65, "NZD": 0.60, "HKD": 0.128,
             "CNY": 0.139, "TWD": 0.031, "KRW": 0.00072, "SGD": 0.74, "THB": 0.029,
             "IDR": 0.000062, "BRL": 0.175, "MXN": 0.054, "CLP": 0.0011,
             "ARS": 0.001, "SAR": 0.267, "ILS": 0.27, "TRY": 0.029, "ZAR": 0.055}

# --------------------------------------------------------------------------- #
# yfinance income-statement line-item resolution (names vary by ticker)
# --------------------------------------------------------------------------- #
REVENUE_KEYS = ["Total Revenue", "TotalRevenue", "Operating Revenue", "Revenue"]
EBITDA_KEYS = ["EBITDA", "Normalized EBITDA"]
GROSS_PROFIT_KEYS = ["Gross Profit", "GrossProfit"]
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
    "trailingEps",
    "forwardEps",
    "numberOfAnalystOpinions",
]

# --------------------------------------------------------------------------- #
# Fetch resilience
# --------------------------------------------------------------------------- #
# Regions where Yahoo carries EPS-surprise history worth fetching (US strongest;
# the extra call is skipped elsewhere to avoid wasted requests).
SURPRISE_REGIONS = ("US", "UK", "EU", "CA", "ANZ")

MAX_RETRIES = 4
BACKOFF_BASE = 2.0           # seconds -> 2, 4, 8, 16
REQUEST_JITTER = (0.4, 1.2)  # random pause between tickers to ease rate limits
CACHE_TTL_DAYS = 30          # reuse cached fundamentals younger than this (a multi-day
                             # world fetch + quarterly data; 5d was far too aggressive)
FAIL_CACHE_TTL_DAYS = 1.0    # negative cache: failed fetches expire fast & auto-retry
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
    "revenue_growth", "revenue_accel",
    "ebitda_growth", "ebitda_accel",
    "earnings_growth", "earnings_accel",
    # richer behaviour so finer clusters stay meaningful (margin + recent momentum)
    "gross_margin_delta", "ebitda_margin_slope", "revenue_q_yoy",
]
KMEANS_K_RANGE = range(4, 25)  # silhouette search range when k="auto"
DEFAULT_CLUSTERS = 16          # default fixed k (silhouette favours few; we want granular behaviour)
RANDOM_STATE = 42
