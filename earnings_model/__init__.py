"""UK earnings-modelling toolkit.

A headless library + CLI for building an equity universe by industry and
market-cap size bucket, monitoring revenue / EBITDA / earnings growth,
acceleration and inflection, clustering similar-behaving names with K-means,
and flagging industries where earnings are inflecting while valuations lag.

The heavy data fetch (yfinance) is cached to disk so the analytics layer
(metrics, aggregation, clustering, valuation-gap) runs fast and offline.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
