"""Market classification for the book builders: DM/EM bucket + region.

`src` codes are LISTING VENUES. Classification is MSCI-style (Korea and
Taiwan sit in EM). Every code the universe currently contains is mapped;
anything new lands in ('EM', 'Other EM') and the books still render.
"""
from __future__ import annotations

# region tab order — DM first, then EM
REGION_ORDER = [
    ('DM', 'North America'),
    ('DM', 'W Europe'),
    ('DM', 'Nordics'),
    ('DM', 'DM Asia-Pac'),
    ('DM', 'MidEast DM'),
    ('EM', 'EM Asia'),
    ('EM', 'EM EMEA'),
    ('EM', 'LatAm'),
    ('EM', 'Other EM'),
]

_REGIONS = {
    'North America': ['US', 'CA'],
    'W Europe': ['UK', 'GB', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'CH',
                 'AT', 'IE', 'PT', 'LU'],
    'Nordics': ['SE', 'NO', 'DK', 'FI', 'IS'],
    'DM Asia-Pac': ['JP', 'AU', 'NZ', 'HK', 'SG'],
    'MidEast DM': ['IL'],
    'EM Asia': ['CN', 'KR', 'TW', 'IN', 'TH', 'ID', 'MY', 'PH', 'VN',
                'PK', 'BD', 'LK'],
    'EM EMEA': ['TR', 'PL', 'GR', 'HU', 'CZ', 'RO', 'ZA', 'SA', 'AE',
                'QA', 'KW', 'EG', 'NG', 'KE', 'MA', 'LT', 'EE', 'LV',
                'BG', 'SI', 'HR', 'RS', 'JO', 'OM', 'BH'],
    'LatAm': ['BR', 'MX', 'CL', 'CO', 'PE', 'AR', 'UY', 'PA'],
}

_DM_REGIONS = {'North America', 'W Europe', 'Nordics', 'DM Asia-Pac',
               'MidEast DM'}

MARKET_REGION = {}
for _region, _codes in _REGIONS.items():
    for _c in _codes:
        MARKET_REGION[_c] = _region


def classify(src: str) -> tuple[str, str]:
    """(bucket, region) for a listing-venue code — e.g. 'KR' -> ('EM','EM Asia')."""
    region = MARKET_REGION.get(str(src).upper(), 'Other EM')
    return ('DM' if region in _DM_REGIONS else 'EM', region)


def ordered_countries(countries) -> list:
    """Order country codes DM-first, grouped by region (REGION_ORDER),
    preserving the given iterable's order within each region."""
    buckets = {key: [] for key in REGION_ORDER}
    for c in countries:
        buckets.setdefault(classify(c), []).append(c)
    out = []
    for key in REGION_ORDER:
        out.extend(buckets.get(key, []))
    for key, vals in buckets.items():           # any unexpected keys last
        if key not in REGION_ORDER:
            out.extend(vals)
    return out
