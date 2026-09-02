"""Per-region benchmark mapping for DSR + PSAR relative calculations.

The original DSR/PSAR-relative compared every ticker to ^GSPC, which
produced massive cross-region bias (US median DSR 22, JP-small 99)
because of timezone misalignment between SPY's end-of-NY-day bar and
non-US end-of-day bars.

Fix: each suffix maps to a US-listed ETF tracking that region's
benchmark. ETFs trade in NY hours so the timestamp aligns with SPY,
removing the lag artifact. ETFs are also far more yfinance-reliable
than the underlying indices (^FTSE, ^STOXX, etc).

Tickers with no exchange suffix (US-listed) get SPY directly.
"""

# yfinance ticker for a US-listed ETF tracking the region's broad market.
SUFFIX_TO_BENCHMARK = {
    'US':   'SPY',     # US: S&P 500

    # Europe
    '.L':   'EWU',     # UK: iShares UK
    '.PA':  'EWQ',     # France: iShares France
    '.AS':  'EWN',     # Netherlands: iShares Netherlands
    '.BR':  'EWK',     # Belgium: iShares Belgium
    '.IR':  'EIRL',    # Ireland: iShares MSCI Ireland
    '.LS':  'PGAL',    # Portugal
    '.MI':  'EWI',     # Italy
    '.MC':  'EWP',     # Spain
    '.SW':  'EWL',     # Switzerland
    '.VI':  'EWO',     # Austria
    '.DE':  'EWG',     # Germany: iShares Germany
    '.F':   'EWG',     # Frankfurt secondary listings (mostly German)
    '.MU':  'EWG',     # Munich
    '.HA':  'EWG',     # Hannover
    '.DU':  'EWG',     # Dusseldorf
    '.HM':  'EWG',     # Hamburg
    '.ST':  'EWD',     # Sweden
    '.OL':  'NORW',    # Norway
    '.CO':  'EDEN',    # Denmark
    '.HE':  'EFNL',    # Finland
    '.AT':  'GREK',    # Greece (Athens Stock Exchange)

    # Asia-Pacific
    '.T':   'EWJ',     # Japan: iShares Japan
    '.JP':  'EWJ',
    '.HK':  'EWH',     # Hong Kong
    '.SI':  'EWS',     # Singapore
    '.KS':  'EWY',     # South Korea
    '.KQ':  'EWY',     # KOSDAQ -> same Korea ETF
    '.TW':  'EWT',     # Taiwan
    '.TWO': 'EWT',     # Taiwan OTC
    '.NS':  'INDA',    # India NSE
    '.BO':  'INDA',    # India BSE
    '.SS':  'FXI',     # Shanghai: iShares China Large-Cap
    '.SZ':  'FXI',     # Shenzhen
    '.AX':  'EWA',     # Australia
    '.NZ':  'ENZL',    # New Zealand
}


def benchmark_for_ticker(ticker: str) -> str:
    """Return the yfinance ticker of the appropriate benchmark ETF."""
    if not isinstance(ticker, str):
        return 'SPY'
    if '.' not in ticker:
        return SUFFIX_TO_BENCHMARK['US']
    suf = '.' + ticker.rsplit('.', 1)[1]
    return SUFFIX_TO_BENCHMARK.get(suf, 'SPY')


def unique_benchmarks() -> set:
    """All distinct benchmark ETFs used by the mapping."""
    return set(SUFFIX_TO_BENCHMARK.values())
