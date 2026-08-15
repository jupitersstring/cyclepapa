"""Deep multi-year enrichment for the FDB-expansion names.

The price/quote enrichers (ticker_yf, yahoo_chart_fill) give point-in-time
valuation but NOT the multi-year inflection / acceleration / first-positive
/ yartseva-composite fields that drive the archetypes. Those need annual +
quarterly income / cashflow / balance-sheet history.

yartseva_db.py already computes all 101 of those fields — but it fetches
via yfinance.Ticker, whose curl_cffi backend fails the agent proxy TLS.
This module fetches the SAME statements through Yahoo's
fundamentals-timeseries + quoteSummary + v8-chart endpoints over the
cookie/crumb session (urllib, proxy-safe), shims them into DataFrames in
yfinance's exact shape, then calls yartseva_db.fetch_ticker unchanged.

Reuses the proven warm-with-backoff YahooSession from ticker_yf.

Output: fdb_expansion_yartseva.csv — a per-country-style yartseva CSV that
fill_asymmetry_gaps.py merges into the master like any other. Resumable.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse

import numpy as np
import pandas as pd

from ticker_yf import YahooSession, Throttled, StaleCrumb
import yartseva_db


# timeseries metric key (without annual/quarterly prefix) -> yfinance row label
TS_METRICS = {
    "TotalRevenue": "Total Revenue",
    "EBITDA": "EBITDA",
    "OperatingIncome": "Operating Income",   # -> EBIT alias
    "NetIncome": "Net Income",
    "OperatingCashFlow": "Operating Cash Flow",
    "FreeCashFlow": "Free Cash Flow",
    "CapitalExpenditure": "Capital Expenditure",
    "GrossProfit": "Gross Profit",
    "TotalAssets": "Total Assets",
    "CurrentLiabilities": "Current Liabilities",
    "TotalDebt": "Total Debt",
    "NetDebt": "Net Debt",
    "CashAndCashEquivalents": "Cash And Cash Equivalents",
    "CashCashEquivalentsAndShortTermInvestments":
        "Cash Cash Equivalents And Short Term Investments",
    "StockholdersEquity": "Stockholders Equity",
    "InvestedCapital": "Invested Capital",
    # Tier-B: diluted-share trajectory + financing-section buybacks
    "DilutedAverageShares": "Diluted Average Shares",
    "BasicAverageShares": "Basic Average Shares",
    "RepurchaseOfCapitalStock": "Repurchase Of Capital Stock",
    "IssuanceOfCapitalStock": "Issuance Of Capital Stock",
}
# which statement each label belongs to
_INCOME = {"Total Revenue", "EBITDA", "Operating Income", "Net Income", "Gross Profit",
           "Diluted Average Shares", "Basic Average Shares"}
_CASH = {"Operating Cash Flow", "Free Cash Flow", "Capital Expenditure",
         "Repurchase Of Capital Stock", "Issuance Of Capital Stock"}
_BAL = {"Total Assets", "Current Liabilities", "Total Debt", "Net Debt",
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Stockholders Equity", "Invested Capital"}


def _fetch_timeseries(sess: YahooSession, symbol: str, prefix: str):
    """Return {label: {Timestamp: value}} for annual|quarterly prefix."""
    types = ",".join(prefix + k for k in TS_METRICS)
    host = "query2.finance.yahoo.com"
    url = (f"https://{host}/ws/fundamentals-timeseries/v1/finance/timeseries/"
           f"{urllib.parse.quote(symbol)}?symbol={urllib.parse.quote(symbol)}"
           f"&type={types}&period1=1041379200&period2=1900000000"
           f"&crumb={urllib.parse.quote(sess.crumb)}")
    try:
        r = sess.opener.open(url, timeout=15)
        d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise StaleCrumb()
        if e.code == 429:
            raise Throttled()
        return {}
    except Exception:
        return {}
    out = {}
    for item in (d.get("timeseries", {}).get("result") or []):
        tname = (item.get("meta", {}).get("type") or [None])[0]
        if not tname:
            continue
        label = TS_METRICS.get(tname[len(prefix):])
        if not label:
            continue
        series = {}
        for v in item.get(tname, []) or []:
            if not v:
                continue
            asof = v.get("asOfDate")
            raw = (v.get("reportedValue") or {}).get("raw")
            if asof and raw is not None:
                series[pd.Timestamp(asof)] = float(raw)
        if series:
            out[label] = series
    return out


def _frames_from(ts_map, labels):
    """Build a yfinance-shaped DataFrame (index=label, cols=Timestamps
    newest-first) from the {label:{ts:val}} map, restricted to labels."""
    rows = {lab: ts_map[lab] for lab in labels if lab in ts_map}
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).T          # index=label, cols=Timestamp
    df = df.reindex(sorted(df.columns, reverse=True), axis=1)  # newest first
    return df


class CrumbTicker:
    """Duck-typed stand-in for yfinance.Ticker backed by the crumb session.
    Exposes exactly the attributes yartseva_db.fetch_ticker reads."""

    def __init__(self, sess: YahooSession, symbol: str):
        a = _fetch_timeseries(sess, symbol, "annual")
        q = _fetch_timeseries(sess, symbol, "quarterly")
        self.income_stmt = _frames_from(a, _INCOME)
        self.cashflow = _frames_from(a, _CASH)
        self.balance_sheet = _frames_from(a, _BAL)
        self.quarterly_income_stmt = _frames_from(q, _INCOME)
        self.quarterly_cashflow = _frames_from(q, _CASH)
        self.quarterly_balance_sheet = _frames_from(q, _BAL)
        # info dict from quoteSummary
        self.info = _info_from_quote(sess, symbol)
        self._sess = sess
        self._symbol = symbol

    def history(self, period="2y", interval="1d", auto_adjust=True, **kw):
        """1-2y daily close via v8 chart (for momentum). yfinance shape:
        DataFrame with a 'Close' column indexed by date."""
        rng = "2y" if "2" in str(period) else "1y"
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(self._symbol)}?range={rng}&interval=1d")
        try:
            r = self._sess.opener.open(url, timeout=12)
            d = json.loads(r.read())
            res = d["chart"]["result"][0]
            ts = res["timestamp"]
            adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
            close = adj or res["indicators"]["quote"][0]["close"]
            idx = pd.to_datetime([pd.Timestamp(t, unit="s") for t in ts])
            return pd.DataFrame({"Close": close}, index=idx).dropna()
        except Exception:
            return pd.DataFrame()


_QS_MODULES = "summaryDetail,defaultKeyStatistics,financialData,price"


def _info_from_quote(sess: YahooSession, symbol: str) -> dict:
    """Assemble the yfinance-info dict fetch_ticker reads, from quoteSummary."""
    try:
        result = sess.quote_summary(symbol)
    except (Throttled, StaleCrumb):
        raise
    except Exception:
        result = None
    if not result:
        return {}
    def g(mod, key):
        v = (result.get(mod) or {}).get(key)
        return v.get("raw") if isinstance(v, dict) else v
    price = result.get("price", {})
    return {
        "currency": price.get("currency"),
        "currentPrice": g("financialData", "currentPrice"),
        "regularMarketPrice": g("price", "regularMarketPrice"),
        "marketCap": g("price", "marketCap") or g("summaryDetail", "marketCap"),
        "enterpriseValue": g("defaultKeyStatistics", "enterpriseValue"),
        "trailingPE": g("summaryDetail", "trailingPE"),
        "ebitdaMargins": g("defaultKeyStatistics", "profitMargins"),  # proxy
        "operatingMargins": g("financialData", "operatingMargins"),
        "sharesOutstanding": g("defaultKeyStatistics", "sharesOutstanding"),
        "impliedSharesOutstanding": g("defaultKeyStatistics", "impliedSharesOutstanding"),
        "heldPercentInsiders": g("defaultKeyStatistics", "heldPercentInsiders"),
        "targetMeanPrice": g("financialData", "targetMeanPrice"),
        "shortName": price.get("shortName") or price.get("longName"),
    }


def enrich_one(sess: YahooSession, symbol: str, meta: dict):
    """Fetch statements + compute the full yartseva TickerRow via
    yartseva_db.fetch_ticker with a monkeypatched Ticker."""
    import yfinance as yf
    orig = yf.Ticker
    yf.Ticker = lambda s, *a, **k: CrumbTicker(sess, s)
    try:
        row = yartseva_db.fetch_ticker(symbol, meta)
    finally:
        yf.Ticker = orig
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-from", default="fdb_expansion_universe.csv")
    ap.add_argument("--out", default="fdb_expansion_yartseva.csv")
    ap.add_argument("--rate", type=float, default=2.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--attempts", default="fdb_deep_attempts.json")
    # A name that returns HTTP 200 with empty/insufficient data is
    # deterministically dead — Yahoo has no fundamentals-timeseries for
    # it, and retrying just burns throttle budget. Soft-throttle surfaces
    # as 429 (caught as Throttled, which does NOT count an attempt), so 2
    # tries is enough to absorb a transient non-429 blip while retiring
    # the ~12k dead nano-caps fast.
    ap.add_argument("--max-attempts", type=int, default=2)
    args = ap.parse_args()

    src = pd.read_csv(args.symbols_from)
    rows_meta = {r["symbol"]: r for _, r in src.iterrows()}
    symbols = list(rows_meta.keys())

    done = set()
    if os.path.exists(args.out):
        try:
            done = set(pd.read_csv(args.out, usecols=["symbol"])["symbol"].dropna())
        except Exception:
            pass

    # Attempt tracking: many nano-cap FDB lines have no Yahoo fundamentals
    # and will never succeed. Without a cap on retries the driver loops
    # forever. We retry each name up to MAX_ATTEMPTS (transient throttle
    # gets more chances via the Throttled path, which does NOT count as an
    # attempt); after that the name retires so the run can finish.
    MAX_ATTEMPTS = args.max_attempts
    attempts = {}
    if os.path.exists(args.attempts):
        try:
            attempts = json.load(open(args.attempts))
        except Exception:
            attempts = {}

    def save_attempts():
        try:
            tmp = args.attempts + ".tmp"
            json.dump(attempts, open(tmp, "w"))
            os.replace(tmp, args.attempts)
        except Exception:
            pass

    todo = [s for s in symbols
            if s not in done and attempts.get(s, 0) < MAX_ATTEMPTS]
    retired = sum(1 for s in symbols
                  if s not in done and attempts.get(s, 0) >= MAX_ATTEMPTS)
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo):,} to deep-enrich ({len(done):,} done, "
          f"{retired:,} retired after {MAX_ATTEMPTS} attempts)", file=sys.stderr)
    if not todo:
        return

    sess = YahooSession()
    print("warming session...", file=sys.stderr)
    if not sess.warm():
        print("could not warm — re-run later (resumable)", file=sys.stderr)
        sys.exit(2)

    import dataclasses
    header_written = os.path.exists(args.out) and os.path.getsize(args.out) > 0
    fout = open(args.out, "a")
    min_int = 1.0 / args.rate if args.rate > 0 else 0
    last = 0.0
    ok = fail = consec = 0
    start = time.time()

    for i, sym in enumerate(todo, 1):
        gap = time.time() - last
        if gap < min_int:
            time.sleep(min_int - gap)
        last = time.time()
        meta = {}
        m = rows_meta.get(sym, {})
        # yartseva_db meta shape: {name, sector, industry, country, bucket}
        # yartseva_db.fetch_ticker reads info_meta["market_cap"] as the
        # FDB bucket string, plus name/sector/industry/currency.
        meta = {"name": m.get("name"), "sector": m.get("sector"),
                "industry": m.get("industry"),
                "country": m.get("country_full") or m.get("src"),
                "market_cap": m.get("market_cap_bucket")}
        try:
            row = enrich_one(sess, sym, meta)
        except StaleCrumb:
            # The crumb is genuinely invalid (401/403). This is the ONLY
            # case that warrants re-hitting getcrumb — force a real re-warm
            # (bypasses the disk cache). Does not count as an attempt.
            consec += 1
            if not sess.warm(force=True):
                time.sleep(30)
            continue
        except Throttled:
            # Rate-limited (429) — the crumb is FINE, we're just being
            # throttled. Re-warming here would hit the already-throttled
            # getcrumb endpoint and deepen the throttle (the root-cause
            # amplifier). So back off only; never re-warm on 429. Does not
            # count as an attempt — the name stays in todo.
            consec += 1
            time.sleep(min(90, 8 * (1 + consec // 3)))
            continue
        except Exception:
            row = None
        if row is not None:
            d = dataclasses.asdict(row) if dataclasses.is_dataclass(row) else dict(row)
            df1 = pd.DataFrame([d])
            df1.to_csv(fout, header=not header_written, index=False)
            header_written = True
            fout.flush()
            ok += 1
            consec = 0
        else:
            # Genuine no-data fail (fetch returned 200 but empty / insufficient
            # to compute a row). Count an attempt so dead names retire.
            fail += 1
            consec += 1
            attempts[sym] = attempts.get(sym, 0) + 1
        if i % 50 == 0:
            save_attempts()
            rate = i / max(1.0, time.time() - start)
            print(f"  {i:,}/{len(todo):,} ok={ok} fail={fail} "
                  f"({rate:.2f}/s, ETA {(len(todo)-i)/rate/60:.0f}m)", file=sys.stderr)
            sys.stderr.flush()
    save_attempts()
    fout.close()
    print(f"DONE ok={ok} fail={fail}", file=sys.stderr)


if __name__ == "__main__":
    main()
