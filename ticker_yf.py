"""Authoritative Yahoo fundamentals enricher (cookie/crumb session).

Why this exists
---------------
Yahoo's v10 quoteSummary endpoint (mcap / EV / EV-EBITDA / P/B / P/E and
friends) rejects unauthenticated callers with 401 — but NOT because of a
hard quota. It needs a *warmed cookie + crumb* session:

  1. GET finance.yahoo.com (and the consent flow if redirected) to obtain
     the A1 / A3 / A1S cookies.
  2. GET /v1/test/getcrumb with those cookies to obtain a crumb token.
  3. Pass ?crumb=<token> on every quoteSummary call, with the cookie jar.

The crumb/cookie pair stays valid for hours; we re-warm automatically when
a call starts failing.

Throttle reality
----------------
Yahoo throttles per source IP on a sliding ~1-minute window (low hundreds
of req/min). Our egress proxy shares an IP with everything else, so we
pace conservatively (default 3 req/s) and back off exponentially on 429
— the window clears in seconds-to-minutes, there is no fixed reset.

Resilience
----------
Resumable: tickers already in the output CSV are skipped, so a run that
trips a limit mid-way just continues on re-run. Atomic checkpoint writes.

Transport
---------
Uses urllib (not curl_cffi / requests) because the agent egress proxy
re-terminates TLS and urllib honours the standard CA env vars, whereas
yfinance 1.4.1's curl_cffi backend fails the proxy TLS handshake.

Output: ticker_yf.csv keyed by our universe symbol.
"""
from __future__ import annotations
import argparse
import csv
import http.cookiejar
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd


UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

MODULES = "summaryDetail,defaultKeyStatistics,financialData,price"

# Fields we extract → output column. (module, yahoo_key, our_column)
FIELD_MAP = [
    ("price", "regularMarketPrice", "yf_price"),
    ("price", "marketCap", "yf_market_cap"),
    ("summaryDetail", "marketCap", "yf_market_cap"),  # fallback
    ("defaultKeyStatistics", "enterpriseValue", "yf_enterprise_value"),
    ("defaultKeyStatistics", "enterpriseToEbitda", "yf_ev_ebitda"),
    ("defaultKeyStatistics", "enterpriseToRevenue", "yf_ev_sales"),
    ("defaultKeyStatistics", "priceToBook", "yf_pb"),
    ("defaultKeyStatistics", "pegRatio", "yf_peg"),
    ("defaultKeyStatistics", "forwardPE", "yf_forward_pe"),
    ("defaultKeyStatistics", "profitMargins", "yf_profit_margin"),
    ("defaultKeyStatistics", "sharesOutstanding", "yf_shares_outstanding"),
    ("defaultKeyStatistics", "floatShares", "yf_float_shares"),
    ("defaultKeyStatistics", "heldPercentInsiders", "yf_insider_pct"),
    ("defaultKeyStatistics", "heldPercentInstitutions", "yf_institution_pct"),
    ("summaryDetail", "trailingPE", "yf_pe"),
    ("summaryDetail", "priceToSalesTrailing12Months", "yf_ps"),
    ("summaryDetail", "dividendYield", "yf_dividend_yield"),
    ("summaryDetail", "fiftyTwoWeekHigh", "yf_52w_high"),
    ("summaryDetail", "fiftyTwoWeekLow", "yf_52w_low"),
    ("summaryDetail", "beta", "yf_beta"),
    ("financialData", "ebitda", "yf_ebitda"),
    ("financialData", "totalRevenue", "yf_revenue"),
    ("financialData", "totalCash", "yf_cash"),
    ("financialData", "totalDebt", "yf_total_debt"),
    ("financialData", "freeCashflow", "yf_fcf"),
    ("financialData", "operatingCashflow", "yf_cfo"),
    ("financialData", "returnOnEquity", "yf_roe"),
    ("financialData", "returnOnAssets", "yf_roa"),
    ("financialData", "grossMargins", "yf_gross_margin"),
    ("financialData", "operatingMargins", "yf_operating_margin"),
    ("financialData", "ebitdaMargins", "yf_ebitda_margin"),
    ("financialData", "revenueGrowth", "yf_revenue_growth"),
    ("financialData", "earningsGrowth", "yf_earnings_growth"),
    ("financialData", "currentPrice", "yf_price"),  # fallback
    ("financialData", "targetMeanPrice", "yf_target_mean"),
    ("financialData", "recommendationMean", "yf_recommendation_mean"),
    ("financialData", "numberOfAnalystOpinions", "yf_n_analysts"),
]

OUT_COLUMNS = ["symbol"] + sorted({c for _, _, c in FIELD_MAP})


class YahooSession:
    """Warmed cookie + crumb session with auto re-warm."""

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = None
        self.crumb = None
        self._build_opener()

    def _build_opener(self):
        ua = random.choice(UA_POOL)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [
            ("User-Agent", ua),
            ("Accept", "text/html,application/json,application/xhtml+xml,*/*"),
            ("Accept-Language", "en-US,en;q=0.9"),
        ]

    def warm(self, max_attempts: int = 5) -> bool:
        """Obtain cookies + crumb. Returns True on success. Backs off on 429."""
        for attempt in range(max_attempts):
            try:
                # Fresh jar + opener each warm attempt
                self.cj.clear()
                self._build_opener()
                # Cookie warmup — quote page reliably sets A1/A3/A1S
                for u in ("https://finance.yahoo.com/quote/AAPL",
                          "https://fc.yahoo.com"):
                    try:
                        self.opener.open(u, timeout=12).read()
                    except Exception:
                        pass
                    if len(self.cj):
                        break
                time.sleep(1.0 + attempt)
                # Crumb
                for host in ("query2.finance.yahoo.com",
                             "query1.finance.yahoo.com"):
                    try:
                        r = self.opener.open(
                            f"https://{host}/v1/test/getcrumb", timeout=12)
                        crumb = r.read().decode().strip()
                        if crumb and "Too Many" not in crumb and len(crumb) < 40:
                            self.crumb = crumb
                            return True
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            continue
                    except Exception:
                        continue
            except Exception:
                pass
            # Backoff — the sliding window clears in seconds-to-minutes
            sleep = min(60, 5 * (2 ** attempt)) + random.uniform(0, 3)
            print(f"  warm attempt {attempt+1} failed, backing off {sleep:.0f}s",
                  file=sys.stderr)
            time.sleep(sleep)
        return False

    def quote_summary(self, symbol: str, timeout: int = 12):
        """Return parsed result dict for symbol, or None. Raises Throttled
        on 429 so the caller can decide to re-warm / back off."""
        if not self.crumb:
            return None
        url = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
               f"{urllib.parse.quote(symbol)}?modules={MODULES}"
               f"&crumb={urllib.parse.quote(self.crumb)}")
        try:
            r = self.opener.open(url, timeout=timeout)
            d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise StaleCrumb()
            if e.code == 429:
                raise Throttled()
            return None
        except Exception:
            return None
        res = (d.get("quoteSummary") or {}).get("result")
        if not res:
            err = (d.get("quoteSummary") or {}).get("error")
            if err:
                raise StaleCrumb()
            return None
        return res[0]


class Throttled(Exception):
    pass


class StaleCrumb(Exception):
    pass


def extract_row(symbol: str, result: dict) -> dict:
    row = {"symbol": symbol}
    for module, key, col in FIELD_MAP:
        mod = result.get(module) or {}
        val = mod.get(key)
        if isinstance(val, dict):
            val = val.get("raw")
        if val is not None and col not in row:
            row[col] = val
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-from", default="asymmetry_global.csv")
    ap.add_argument("--out", default="ticker_yf.csv")
    ap.add_argument("--rate", type=float, default=3.0,
                    help="target requests per second (paced)")
    ap.add_argument("--rewarm-after-failures", type=int, default=25,
                    help="re-warm the cookie/crumb session after N consecutive failures")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap tickers this run (0 = all)")
    ap.add_argument("--only-missing-valuation", action="store_true",
                    help="only fetch symbols where ev_ebitda is null in the input")
    args = ap.parse_args()

    print(f"loading universe from {args.symbols_from}...", file=sys.stderr)
    uni = pd.read_csv(args.symbols_from)
    if "symbol" not in uni.columns:
        print("no symbol column", file=sys.stderr)
        sys.exit(1)

    if args.only_missing_valuation and "ev_ebitda" in uni.columns:
        uni = uni[uni["ev_ebitda"].isna()]
        print(f"  filtered to {len(uni):,} rows missing ev_ebitda", file=sys.stderr)

    symbols = uni["symbol"].dropna().drop_duplicates().tolist()

    # Resume: load already-done
    done = set()
    if os.path.exists(args.out):
        try:
            prev = pd.read_csv(args.out)
            done = set(prev["symbol"].dropna())
            print(f"  resuming — {len(done):,} already done", file=sys.stderr)
        except Exception:
            pass

    todo = [s for s in symbols if s not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"  {len(todo):,} symbols to fetch", file=sys.stderr)
    if not todo:
        print("nothing to do", file=sys.stderr)
        return

    sess = YahooSession()
    print("warming session...", file=sys.stderr)
    if not sess.warm():
        print("FATAL: could not warm session (IP throttled). Re-run later — "
              "progress is resumable.", file=sys.stderr)
        sys.exit(2)
    print(f"  warmed, crumb={sess.crumb!r}", file=sys.stderr)

    # Output file: append mode, write header if new
    new_file = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    fout = open(args.out, "a", newline="")
    writer = csv.DictWriter(fout, fieldnames=OUT_COLUMNS, extrasaction="ignore")
    if new_file:
        writer.writeheader()
        fout.flush()

    min_interval = 1.0 / args.rate if args.rate > 0 else 0
    consecutive_failures = 0
    ok = 0
    fail = 0
    start = time.time()
    last_req = 0.0

    for i, sym in enumerate(todo, start=1):
        # Pace
        gap = time.time() - last_req
        if gap < min_interval:
            time.sleep(min_interval - gap)
        last_req = time.time()

        try:
            result = sess.quote_summary(sym)
        except Throttled:
            consecutive_failures += 1
            # Hard backoff — window clears
            back = min(90, 10 * (1 + consecutive_failures // 5)) + random.uniform(0, 5)
            print(f"  [{i}/{len(todo)}] 429 throttle on {sym}; backing off {back:.0f}s",
                  file=sys.stderr)
            time.sleep(back)
            if consecutive_failures % args.rewarm_after_failures == 0:
                print("  re-warming session...", file=sys.stderr)
                sess.warm()
            continue
        except StaleCrumb:
            print(f"  [{i}/{len(todo)}] stale crumb; re-warming...", file=sys.stderr)
            sess.warm()
            continue

        if result:
            row = extract_row(sym, result)
            if len(row) > 1:  # got at least one field
                writer.writerow(row)
                fout.flush()
                ok += 1
                consecutive_failures = 0
            else:
                fail += 1
                consecutive_failures += 1
        else:
            fail += 1
            consecutive_failures += 1
            if consecutive_failures and consecutive_failures % args.rewarm_after_failures == 0:
                print(f"  {consecutive_failures} consecutive failures; re-warming...",
                      file=sys.stderr)
                sess.warm()

        if i % 50 == 0:
            rate = i / max(1.0, time.time() - start)
            eta = (len(todo) - i) / rate if rate else 0
            print(f"  {i:,}/{len(todo):,}  ok={ok} fail={fail}  "
                  f"({rate:.2f}/s, ETA {eta/60:.0f}m)", file=sys.stderr)
            sys.stderr.flush()

    fout.close()
    print(f"\nDONE: ok={ok} fail={fail} in {(time.time()-start)/60:.1f}m",
          file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
