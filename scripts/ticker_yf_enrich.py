#!/usr/bin/env python3
"""Authoritative Yahoo valuation enricher — cookie/crumb warmed, paced, resumable.

The "Too Many Requests" on quoteSummary was a missing-cookie problem, not a hard
quota. Yahoo's throttle is a sliding ~1-minute per-IP window. We:
  • warm a finance.yahoo.com cookie + crumb session (handles EU consent redirect)
  • pace at ~3 req/s (configurable)
  • refresh the session after N consecutive failures (re-warm cookie + crumb)
  • checkpoint + resume (skip already-done tickers) so a mid-run trip loses nothing

Pulls Yahoo's authoritative: marketCap, enterpriseValue, enterpriseToEbitda,
enterpriseToRevenue, priceToBook, trailingPE, forwardPE, priceToSales,
freeCashflow, totalRevenue, returnOnEquity, profitMargins, debtToEquity.

Output: data/research/ticker_yf.csv (resumable; one row per ticker).
"""
import os, sys, time, json, argparse, threading
import requests
import pandas as pd
import numpy as np

os.environ.setdefault('REQUESTS_CA_BUNDLE', '/root/.ccr/ca-bundle.crt')
os.environ.setdefault('SSL_CERT_FILE', '/root/.ccr/ca-bundle.crt')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/121.0 Safari/537.36')

MODULES = 'price,summaryDetail,defaultKeyStatistics,financialData'


class YahooSession:
    """Cookie + crumb warmed Yahoo session with auto-refresh."""
    def __init__(self):
        self.s = None
        self.crumb = None
        self.host = 'query1'
        self.lock = threading.Lock()
        self.warm()

    def warm(self, max_crumb_tries=10):
        s = requests.Session()
        s.headers.update({'User-Agent': _UA, 'Accept': '*/*',
                          'Accept-Language': 'en-US,en;q=0.9'})
        # 1. cookie warmup — finance.yahoo.com sets A1/A3/A1S
        try:
            s.get('https://finance.yahoo.com', timeout=15)
        except Exception:
            pass
        # EU consent flow fallback (guce) — sets cookies if the first didn't
        if not any(c.name in ('A1', 'A3') for c in s.cookies):
            try:
                s.get('https://fc.yahoo.com', timeout=10)
            except Exception:
                pass
        # 2. crumb with backoff across both hosts
        crumb = None; host = 'query1'
        for attempt in range(max_crumb_tries):
            for h in ('query1', 'query2'):
                try:
                    r = s.get(f'https://{h}.finance.yahoo.com/v1/test/getcrumb', timeout=12)
                    if r.status_code == 200 and r.text.strip() and 'Too Many' not in r.text:
                        crumb = r.text.strip(); host = h; break
                except Exception:
                    continue
            if crumb: break
            time.sleep(min(3 + attempt * 2, 20))
        self.s = s; self.crumb = crumb; self.host = host
        return crumb is not None

    def fetch(self, ticker):
        if not self.crumb:
            return None
        url = f'https://{self.host}.finance.yahoo.com/v10/finance/quoteSummary/{ticker}'
        try:
            r = self.s.get(url, params={'modules': MODULES, 'crumb': self.crumb}, timeout=15)
        except Exception:
            return 'ERR'
        if r.status_code == 200:
            try:
                return r.json()['quoteSummary']['result'][0]
            except Exception:
                return None
        if r.status_code in (401, 429):
            return 'BLOCK'
        return None


def raw(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict): return None
        cur = cur.get(p)
    if isinstance(cur, dict):
        return cur.get('raw')
    return cur


def extract(ticker, j):
    if not isinstance(j, dict): return None
    pr = j.get('price', {}); sd = j.get('summaryDetail', {})
    ks = j.get('defaultKeyStatistics', {}); fd = j.get('financialData', {})
    return {
        'ticker': ticker,
        'yf_price':        raw(pr, 'regularMarketPrice'),
        'yf_mktCap':       raw(pr, 'marketCap') or raw(sd, 'marketCap'),
        'yf_ev':           raw(ks, 'enterpriseValue'),
        'yf_ev_ebitda':    raw(ks, 'enterpriseToEbitda'),
        'yf_ev_rev':       raw(ks, 'enterpriseToRevenue'),
        'yf_pb':           raw(ks, 'priceToBook'),
        'yf_pe':           raw(sd, 'trailingPE'),
        'yf_fpe':          raw(sd, 'forwardPE') or raw(ks, 'forwardPE'),
        'yf_ps':           raw(sd, 'priceToSalesTrailing12Months'),
        'yf_fcf':          raw(fd, 'freeCashflow'),
        'yf_rev':          raw(fd, 'totalRevenue'),
        'yf_roe':          raw(fd, 'returnOnEquity'),
        'yf_profit_margin':raw(fd, 'profitMargins') or raw(ks, 'profitMargins'),
        'yf_debt_equity':  raw(fd, 'debtToEquity'),
        'yf_div_yield':    raw(sd, 'dividendYield'),
        'yf_beta':         raw(ks, 'beta') or raw(sd, 'beta'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--universe', help='CSV with a ticker column; default = synthesis rows missing valuation')
    ap.add_argument('--out', default='data/research/ticker_yf.csv')
    ap.add_argument('--rate', type=float, default=3.0, help='requests per second')
    ap.add_argument('--refresh-after', type=int, default=25, help='re-warm session after N consecutive failures')
    ap.add_argument('--checkpoint', type=int, default=50)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    # Build target ticker list
    if args.universe and os.path.exists(args.universe):
        uni = pd.read_csv(args.universe)
        targets = uni['ticker'].dropna().astype(str).str.upper().unique().tolist()
    else:
        df = pd.read_csv('data/synthesis/v2_universe_ranked_full_q.csv', low_memory=False)
        df['ticker'] = df['ticker'].astype(str).str.upper()
        need = df[(df['mktCap'].isna()) | (df['pb'].isna()) | (df['ev_valuation'].isna())]
        targets = need['ticker'].dropna().unique().tolist()
    targets = [t for t in targets if t and t != 'NAN']

    # Resume
    done = set(); existing = []
    if os.path.exists(args.out) and os.path.getsize(args.out) > 50:
        prev = pd.read_csv(args.out)
        done = set(prev['ticker'].dropna().astype(str).str.upper())
        existing = prev.to_dict('records')
        print(f"[yf] resume: {len(done):,} done", file=sys.stderr)
    todo = [t for t in targets if t not in done]
    if args.limit: todo = todo[:args.limit]
    print(f"[yf] {len(todo):,} tickers to enrich · {args.rate} req/s · refresh@{args.refresh_after} fails", file=sys.stderr)

    yh = YahooSession()
    if not yh.crumb:
        print("[yf] could not obtain crumb — IP window saturated; will retry warm() periodically", file=sys.stderr)

    rows = list(existing)
    interval = 1.0 / max(args.rate, 0.1)
    consec_fail = 0; ok = 0; start = time.time()

    for i, tk in enumerate(todo):
        t0 = time.time()
        res = yh.fetch(tk)
        if res in ('BLOCK', 'ERR', None):
            consec_fail += 1
            if consec_fail >= args.refresh_after:
                print(f"[yf] {consec_fail} consecutive fails — re-warming session", file=sys.stderr)
                time.sleep(10)
                yh.warm()
                consec_fail = 0
        else:
            row = extract(tk, res)
            if row:
                rows.append(row); ok += 1
                consec_fail = 0
        if (i + 1) % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            el = time.time() - start; rate = (i + 1) / max(el, 0.1)
            eta = (len(todo) - i - 1) / max(rate, 0.001) / 60
            print(f"[yf] {i+1}/{len(todo)}  ok {ok}  fails {consec_fail}  {rate:.1f}/s  ETA {eta:.0f}m", file=sys.stderr)
        dt = interval - (time.time() - t0)
        if dt > 0: time.sleep(dt)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"[yf] DONE: {len(rows):,} rows, {ok} newly enriched", file=sys.stderr)


if __name__ == '__main__':
    main()
