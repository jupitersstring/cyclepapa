"""Gap-fill price-only fetcher using yf.download() bulk endpoint.

yfinance's per-ticker Ticker(t).history() goes through one HTTP call per
ticker and aggressively triggers throttling. yf.download(['T1','T2',...])
batches them into a single request against the chart endpoint, which has
a much higher rate-limit ceiling and works on names where the per-ticker
path returns empty.

Targets the specific gap: tickers that have ANY cached data
(info / eps_history / income / cashflow) but no price. These are names
the per-ticker path failed for; bulk fetch often succeeds.

Run:
    python gap_fill_prices.py
    python gap_fill_prices.py --chunk-size 200 --chunk-pause 5
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

CACHE = Path('.cache/yf')

# yfinance exchange suffixes seen in cache (reverse-map _XX -> .XX)
_YF_SUFFIXES = {
    'L','DE','F','SW','TO','V','CN','PA','MI','AS','BR','MC','LS','OL','ST','HE',
    'CO','VI','IR','WA','PR','BD','IL','HK','T','KS','KQ','TW','TWO','AX','NZ',
    'SA','BA','MX','SN','CL','JO','QA','DU','HM','BE','MU','SG','HA','NS','BO',
}


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _to_yf(safe: str) -> str:
    """Reverse _safe() for the exchange-suffix case. ZZE-H_V -> ZZE-H.V"""
    if '_' not in safe:
        return safe
    base, sfx = safe.rsplit('_', 1)
    if sfx in _YF_SUFFIXES and base:
        return f'{base}.{sfx}'
    return safe


def find_price_gaps() -> list[str]:
    """Tickers with any cached data but no non-empty price file."""
    # Build set of all tickers that have at least one cached slot
    all_t = set()
    for kind in ('info_metrics', 'eps_history', 'income', 'cashflow'):
        for f in CACHE.glob(f'*__{kind}.parquet'):
            all_t.add(f.name.split('__')[0])

    # Build set of tickers with non-empty price file
    have_price = set()
    for f in CACHE.glob('*__price.parquet'):
        try:
            df = pd.read_parquet(f)
            if not df.empty and 'Close' in df.columns:
                have_price.add(f.name.split('__')[0])
        except Exception: pass

    gaps = sorted(all_t - have_price)
    # Convert safe names back to ticker form (underscores are share-class or
    # special chars; the original may have used '-' so try both forms)
    return gaps


def chunk_fetch(safe_tickers: list[str], chunk_size: int, sleep_sec: float):
    """Bulk-download via yf.download(); save each ticker's Close to cache.

    `safe_tickers` are the safe-name (underscore) forms. We convert to yfinance
    form (dot-suffix) for the API call but persist using the safe name so the
    files line up with the rest of the cache.
    """
    n = len(safe_tickers)
    saved = 0; empty = 0; failed = 0
    zero_streak = 0
    t0 = time.time()
    n_chunks = (n + chunk_size - 1) // chunk_size
    for i in range(0, n, chunk_size):
        safe_batch = safe_tickers[i:i+chunk_size]
        yf_batch = [_to_yf(s) for s in safe_batch]
        # map yf-name -> safe-name for cache write
        yf2safe = dict(zip(yf_batch, safe_batch))

        try:
            df = yf.download(
                tickers=yf_batch,
                period='5y',
                interval='1d',
                group_by='ticker',
                auto_adjust=True,
                threads=False,
                progress=False,
            )
        except Exception as exc:
            print(f"  [batch err] {exc}")
            df = None

        batch_saved = 0
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                top_levels = set(df.columns.get_level_values(0).unique())
                for yf_tkr in yf_batch:
                    if yf_tkr not in top_levels:
                        empty += 1
                        continue
                    try:
                        sub = df[yf_tkr]
                        if not isinstance(sub, pd.DataFrame) or sub.empty or 'Close' not in sub.columns:
                            empty += 1; continue
                        keep = [c for c in ('Close','Volume') if c in sub.columns]
                        out = sub[keep].dropna(subset=['Close'])
                        if out.empty:
                            empty += 1; continue
                        idx = pd.to_datetime(out.index)
                        if getattr(idx, 'tz', None) is not None:
                            idx = idx.tz_localize(None)
                        out.index = idx
                        out.to_parquet(CACHE / f'{yf2safe[yf_tkr]}__price.parquet')
                        saved += 1; batch_saved += 1
                    except Exception:
                        failed += 1
            else:
                # single-ticker flat-columns case
                if len(yf_batch) == 1 and 'Close' in df.columns and not df['Close'].dropna().empty:
                    yf_tkr = yf_batch[0]
                    keep = [c for c in ('Close','Volume') if c in df.columns]
                    out = df[keep].dropna(subset=['Close'])
                    idx = pd.to_datetime(out.index)
                    if getattr(idx, 'tz', None) is not None:
                        idx = idx.tz_localize(None)
                    out.index = idx
                    out.to_parquet(CACHE / f'{yf2safe[yf_tkr]}__price.parquet')
                    saved += 1; batch_saved += 1
        else:
            failed += len(yf_batch)

        done = min(i + chunk_size, n)
        el = time.time() - t0
        rate = done/el if el>0 else 0
        eta = (n - done) / rate / 60 if rate>0 else 0
        hit = batch_saved / len(safe_batch) * 100 if safe_batch else 0
        print(f"  chunk {i//chunk_size + 1}/{n_chunks}: "
              f"{done}/{n}  +{batch_saved} (hit={hit:.0f}%)  total_saved={saved}  "
              f"rate={rate:.0f}/s  eta={eta:.0f}min", flush=True)

        # Throttle backoff: if a batch returns nothing, Yahoo's rate-limit has
        # tripped. Pause progressively longer until productive batches resume.
        if batch_saved == 0:
            zero_streak += 1
            backoff = min(60 * 2**(zero_streak-1), 600)   # 60s, 120s, 240s, 480s, 600s cap
            print(f"  [throttle] zero-hit streak={zero_streak}; sleeping {backoff}s", flush=True)
            time.sleep(backoff)
        else:
            zero_streak = 0
            time.sleep(sleep_sec)

    print(f"\nDone: saved={saved}, empty={empty}, failed={failed}, total={n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chunk-size', type=int, default=200,
                    help='tickers per yf.download call')
    ap.add_argument('--chunk-pause', type=float, default=5.0,
                    help='seconds between chunks')
    ap.add_argument('--max', type=int, default=None)
    args = ap.parse_args()

    gaps = find_price_gaps()
    print(f"Found {len(gaps)} tickers with cached data but no price")
    if args.max:
        gaps = gaps[:args.max]
        print(f"  capped to {len(gaps)} for testing")
    if not gaps:
        return
    chunk_fetch(gaps, args.chunk_size, args.chunk_pause)


if __name__ == '__main__':
    main()
