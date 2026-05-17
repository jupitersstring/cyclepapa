"""Social arbitrage pipeline.

A retail-grade implementation of Chris Camillo's "social arbitrage" method:
detect consumer-behavior shifts on free public sources, map them to publicly
traded companies, and surface anomalies for discretionary review.

All modules degrade gracefully when optional dependencies are missing so that
the entry-level pipeline (PullPush + Apewisdom + GDELT + Stocktwits + yfinance
+ financedatabase + VADER) runs with zero API keys.
"""

from .config import Config

__all__ = ["Config"]
__version__ = "0.1.0"
