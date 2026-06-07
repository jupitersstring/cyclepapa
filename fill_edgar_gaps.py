"""Fill EDGAR cache for US tickers that have a CIK but no fetched data.

Iterates the list of US-CIK tickers in our universe that don't yet have
a .cache/edgar/CF_{cik}.json.gz file, and fetches each via the
edgar_fetcher with rate-limited polling (SEC requires 10 req/s max,
we use ~5 req/s with backoff).
"""
from __future__ import annotations
import json, time, gzip, sys
from pathlib import Path
import urllib.request
import urllib.error

CACHE = Path('.cache/yf')
EDGAR_CACHE = Path('.cache/edgar')
EDGAR_CACHE.mkdir(exist_ok=True)
UA = 'cyclepapa screener research@example.com'

with open(EDGAR_CACHE / 'company_tickers.json') as f:
    raw = json.load(f)
cik_map = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}

have_info = {f.name.split('__')[0] for f in CACHE.glob('*__info_metrics.parquet')}
to_fetch = []
for tk in sorted(have_info):
    cik = cik_map.get(tk.upper())
    if cik is None: continue
    cf = EDGAR_CACHE / f'CF_{cik:010d}.json.gz'
    if not cf.exists():
        to_fetch.append((tk, cik))

print(f'To fetch: {len(to_fetch)}')

fail = ok = 0
t0 = time.time()
for i, (tk, cik) in enumerate(to_fetch):
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            if r.headers.get('Content-Encoding') == 'gzip':
                data = gzip.decompress(data)
            # Validate it's JSON
            parsed = json.loads(data)
            # Save gzipped
            out = EDGAR_CACHE / f'CF_{cik:010d}.json.gz'
            with gzip.open(out, 'wb') as f:
                f.write(data)
            ok += 1
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Issuer has no XBRL data — skip silently
            pass
        else:
            print(f'  {tk} (CIK {cik}): HTTP {e.code}')
        fail += 1
    except Exception as exc:
        print(f'  {tk} (CIK {cik}): {exc}')
        fail += 1
    if (i+1) % 100 == 0:
        el = time.time() - t0
        rate = (i+1) / el
        eta = (len(to_fetch) - i - 1) / rate / 60
        print(f'  {i+1}/{len(to_fetch)}  ok={ok}  fail={fail}  rate={rate:.1f}/s  eta={eta:.0f}min')
    time.sleep(0.2)  # SEC: 10 req/s max, polite delay

print(f'\nDone: ok={ok}, fail={fail}, total={len(to_fetch)}')
