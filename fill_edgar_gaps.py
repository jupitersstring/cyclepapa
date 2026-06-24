"""Fill EDGAR cache for ALL SEC-registered issuers in the ticker map.

Iterates the SEC's `company_tickers.json` (every ticker SEC tracks across
NYSE/NASDAQ/AMEX, plus 20-F / 40-F foreign filers and other US-listed
entities) and fetches `companyfacts` JSON for each unique CIK that doesn't
yet have a `.cache/edgar/CF_{cik}.json.gz` file.

Polite rate: SEC requires ≤10 req/s. We use ~5 req/s with backoff to leave
headroom for the SEC's per-IP throttle and our own overhead.

Usage:
  python fill_edgar_gaps.py [--in-universe-only]

  --in-universe-only   Restrict to CIKs that also have a yfinance
                       info_metrics parquet (the historical behaviour).
                       Default: fetch the FULL SEC universe.
"""
from __future__ import annotations
import argparse, json, time, gzip
from pathlib import Path
import urllib.request
import urllib.error

YF_CACHE = Path('.cache/yf')
EDGAR_CACHE = Path('.cache/edgar')
EDGAR_CACHE.mkdir(exist_ok=True)
UA = 'cyclepapa screener research@example.com'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in-universe-only', action='store_true',
                    help='Restrict to CIKs that also have a yfinance info_metrics parquet')
    ap.add_argument('--sleep', type=float, default=0.2,
                    help='Sleep between SEC fetches (s). Default 0.2 = ~5 req/s.')
    args = ap.parse_args()

    with open(EDGAR_CACHE / 'company_tickers.json') as f:
        raw = json.load(f)
    cik_map = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}

    have_info = {f.name.split('__')[0] for f in YF_CACHE.glob('*__info_metrics.parquet')}

    # Universe: every unique CIK in the SEC ticker map. With --in-universe-only,
    # restrict to CIKs whose ticker is also in our yfinance cache.
    if args.in_universe_only:
        candidates = []
        for tk in sorted(have_info):
            cik = cik_map.get(tk.upper())
            if cik is not None:
                candidates.append((tk, cik))
    else:
        # All SEC CIKs — pick the FIRST ticker we see per CIK as a display label
        seen_ciks = {}
        for tk_upper, cik in cik_map.items():
            seen_ciks.setdefault(cik, tk_upper)
        candidates = [(tkr, cik) for cik, tkr in sorted(seen_ciks.items(), key=lambda x: x[0])]

    to_fetch = [(tk, cik) for tk, cik in candidates
                if not (EDGAR_CACHE / f'CF_{cik:010d}.json.gz').exists()]
    print(f'Universe: {len(candidates):,} CIKs ({"in-universe only" if args.in_universe_only else "full SEC universe"})')
    print(f'Already cached: {len(candidates) - len(to_fetch):,}')
    print(f'To fetch: {len(to_fetch):,}')

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
                json.loads(data)
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
            print(f'  {i+1:>5,}/{len(to_fetch):,}  ok={ok:,}  fail={fail:,}  rate={rate:.1f}/s  eta={eta:.0f}min')
        time.sleep(args.sleep)

    print(f'\nDone: ok={ok:,}, fail={fail:,}, total={len(to_fetch):,}')


if __name__ == '__main__':
    main()
