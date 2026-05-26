"""
Crypto universe builders used by the trend engine's screener.

Three sources:
  - Revolut's listed crypto set (hard-coded snapshot — ~95 tickers from
    Revolut's public help page, normalized to yfinance form).
  - Top-N by market cap, via CoinGecko's free /coins/markets endpoint.
  - Top-N by 24h trading volume, via the same endpoint.

All tickers are normalized to yfinance-compatible "SYMBOL-USD" form. A
small alias map handles cases where the CoinGecko ticker differs from
the yfinance ticker.
"""

from __future__ import annotations

import time
from typing import Iterable, List, Optional, Set

import requests


# Snapshot of Revolut's supported crypto list (uppercase tickers, no -USD).
# Source: globefunder.com/revolut-cryptocurrency-list/ (~95 entries).
# Revolut adds new tokens frequently; extend as needed.
REVOLUT_TICKERS: List[str] = [
    "ZRX", "1INCH", "AAVE", "ACH", "ALGO", "AMP", "FORTH", "ANKR", "APE",
    "AVAX", "AXS", "BAL", "BNT", "BAND", "BOND", "BAT", "BICO", "BTC",
    "BCH", "BLZ", "FIDA", "ADA", "CTSI", "CELO", "LINK", "CHZ", "CLV",
    "COMP", "ATOM", "COTI", "CRO", "CRV", "DASH", "MANA", "DOGE", "EGLD",
    "ENJ", "MLN", "EOS", "ETH", "ETC", "ENS", "FET", "FIL", "FLOW",
    "GALA", "GODS", "GST", "IDEX", "RLC", "IMX", "ICP", "JASMY", "KEEP",
    "KNC", "LTC", "LPT", "LRC", "MKR", "MASK", "MATIC", "MINA", "MIR",
    "NKN", "NU", "NMR", "OMG", "OXT", "OGN", "PERP", "DOT", "QNT", "RAD",
    "REN", "RNDR", "REQ", "XRP", "SHIB", "SKL", "SOL", "SPELL", "XLM",
    "GMT", "STORJ", "SUPER", "SUSHI", "SNX", "XTZ", "GRT", "SAND", "TRB",
    "UNFI", "UNI", "UMA", "YFI",
]

# CoinGecko ticker → yfinance ticker (when they differ).
# yfinance generally uses the trading symbol + "-USD". Exceptions:
_YF_TICKER_ALIASES = {
    "MIOTA": "IOTA",
    "MATIC": "POL",      # rebrand: Polygon's MATIC migrated to POL ticker
    "LUNA":  "LUNC",     # Terra Classic uses LUNC on most listings
    "FTM":   "S",        # Sonic / Fantom rebrand (best-effort fallback)
    "RNDR":  "RENDER",
}


def _yf(ticker: str) -> str:
    t = ticker.upper().replace("/", "-")
    t = _YF_TICKER_ALIASES.get(t, t)
    if t.endswith("-USD"):
        return t
    return f"{t}-USD"


def revolut_universe() -> List[str]:
    """Yfinance-formatted tickers for the Revolut crypto list."""
    return sorted({_yf(t) for t in REVOLUT_TICKERS})


# ---------------------------------------------------------------------------
# CoinGecko top-N
# ---------------------------------------------------------------------------


_COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"


def _coingecko_top(order: str, n: int, *, timeout: int = 20) -> List[dict]:
    """
    Fetch the top-N markets from CoinGecko. `order` is e.g.
    'market_cap_desc' or 'volume_desc'. Free endpoint, no key needed,
    but rate-limited — we page in 250-chunks and back off if throttled.
    """
    out: List[dict] = []
    page = 1
    per_page = 250
    while len(out) < n:
        params = {
            "vs_currency": "usd",
            "order": order,
            "per_page": min(per_page, n - len(out)),
            "page": page,
            "sparkline": "false",
        }
        for attempt in range(3):
            try:
                r = requests.get(_COINGECKO_MARKETS, params=params, timeout=timeout)
                if r.status_code == 429:
                    time.sleep(2 ** attempt * 2)
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        else:
            break
        if not data:
            break
        out.extend(data)
        if len(data) < params["per_page"]:
            break
        page += 1
    return out[:n]


def _stablecoins() -> Set[str]:
    return {"USDT", "USDC", "DAI", "TUSD", "FRAX", "USDP", "BUSD", "PYUSD",
            "USDD", "FDUSD", "GUSD", "USDE", "RLUSD"}


def top_yf_cryptos_by_mcap(n: int = 200, *, exclude_stables: bool = True) -> List[str]:
    coins = _coingecko_top("market_cap_desc", n + 30)  # over-fetch to allow stable filtering
    stables = _stablecoins() if exclude_stables else set()
    out: List[str] = []
    for c in coins:
        sym = c.get("symbol", "").upper()
        if not sym or sym in stables:
            continue
        out.append(_yf(sym))
        if len(out) >= n:
            break
    return out


def top_yf_cryptos_by_volume(n: int = 200, *, exclude_stables: bool = True) -> List[str]:
    coins = _coingecko_top("volume_desc", n + 30)
    stables = _stablecoins() if exclude_stables else set()
    out: List[str] = []
    for c in coins:
        sym = c.get("symbol", "").upper()
        if not sym or sym in stables:
            continue
        out.append(_yf(sym))
        if len(out) >= n:
            break
    return out


def combined_universe(*, n_mcap: int = 200, n_volume: int = 200,
                      include_revolut: bool = True,
                      exclude_stables: bool = True) -> List[str]:
    """Dedup'd union of Revolut + top-N by mcap + top-N by volume."""
    seen: Set[str] = set()
    out: List[str] = []
    def _add(items: Iterable[str]) -> None:
        for s in items:
            if s not in seen:
                seen.add(s)
                out.append(s)
    if include_revolut:
        _add(revolut_universe())
    try:
        _add(top_yf_cryptos_by_mcap(n_mcap, exclude_stables=exclude_stables))
    except Exception:
        pass
    try:
        _add(top_yf_cryptos_by_volume(n_volume, exclude_stables=exclude_stables))
    except Exception:
        pass
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["revolut", "mcap", "volume", "combined"], default="combined")
    p.add_argument("-n", type=int, default=50)
    args = p.parse_args()
    if args.source == "revolut":
        u = revolut_universe()
    elif args.source == "mcap":
        u = top_yf_cryptos_by_mcap(args.n)
    elif args.source == "volume":
        u = top_yf_cryptos_by_volume(args.n)
    else:
        u = combined_universe(n_mcap=args.n, n_volume=args.n)
    print(f"# {args.source}: {len(u)} tickers")
    for t in u:
        print(t)
