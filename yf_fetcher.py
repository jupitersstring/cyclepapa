"""
Direct Yahoo Finance price fetcher (bypassing yfinance's connectivity issues).
Fetches daily closes, computes SPX-relative strength, identifies 52-week RS lows.
"""
import json, csv, time, sys, subprocess
from datetime import datetime, timezone

def fetch_prices(ticker, start_year=2018, end_ymd=None):
    """Return list of (date_str, close) for ticker from start_year to today."""
    p1 = int(datetime(start_year, 1, 1, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026, 4, 22, tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={p1}&period2={p2}&interval=1d"
    try:
        out = subprocess.run(
            ["curl","-sL","-H","User-Agent: Mozilla/5.0 (Macintosh)","--connect-timeout","10","-m","25",url],
            capture_output=True, text=True, timeout=30
        ).stdout
        j = json.loads(out)
        result = j.get("chart", {}).get("result")
        if not result: return []
        r = result[0]
        ts = r["timestamp"]
        closes = r["indicators"]["quote"][0]["close"]
        data = []
        for t, c in zip(ts, closes):
            if c is None: continue
            d = datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            data.append((d, c))
        return data
    except Exception as e:
        return []

def rs_series(stock, spx):
    """Relative strength = stock / SPX, normalized so start=1."""
    spx_map = dict(spx)
    rs = []
    s0 = None; x0 = None
    for d, c in stock:
        if d not in spx_map: continue
        if s0 is None:
            s0 = c; x0 = spx_map[d]
        rs.append((d, (c/s0) / (spx_map[d]/x0)))
    return rs

def find_rs_low(rs_series_data, lookback_days=365):
    """Find the RS low in the series with 52-week lookback at each point."""
    lows = []
    for i, (d, r) in enumerate(rs_series_data):
        # Look back ~365 days from this date
        back = []
        cur_dt = datetime.strptime(d, "%Y-%m-%d")
        for (d2, r2) in rs_series_data[:i+1]:
            d2_dt = datetime.strptime(d2, "%Y-%m-%d")
            if (cur_dt - d2_dt).days <= lookback_days:
                back.append(r2)
        if back and r == min(back):
            lows.append((d, r))
    return lows

def compute_current_rs_status(rs_series_data):
    """Given full RS series, compute current rank in last 52 weeks."""
    if not rs_series_data: return None
    cur_d, cur_r = rs_series_data[-1]
    cur_dt = datetime.strptime(cur_d, "%Y-%m-%d")
    last_year = [(d, r) for (d, r) in rs_series_data
                 if (cur_dt - datetime.strptime(d, "%Y-%m-%d")).days <= 365]
    if not last_year: return None
    sorted_r = sorted(r for (d, r) in last_year)
    pct = sorted_r.index(cur_r) / len(sorted_r) * 100
    min_r = min(r for (d, r) in last_year)
    max_r = max(r for (d, r) in last_year)
    days_since_min = (cur_dt - max(datetime.strptime(d, "%Y-%m-%d") for (d, r) in last_year if r == min_r)).days
    return {
        "current_rs": cur_r, "min_rs_1yr": min_r, "max_rs_1yr": max_r,
        "pct_rank": pct, "days_since_low": days_since_min,
        "pct_from_low": (cur_r/min_r - 1) * 100,
        "pct_from_high": (cur_r/max_r - 1) * 100,
    }

def ticker_52wk_low_date(stock_data):
    """Find the actual price 52-week low date (most recent if multiple)."""
    if not stock_data: return None
    cur_d = stock_data[-1][0]
    cur_dt = datetime.strptime(cur_d, "%Y-%m-%d")
    last_year = [(d, c) for (d, c) in stock_data
                 if (cur_dt - datetime.strptime(d, "%Y-%m-%d")).days <= 365]
    if not last_year: return None
    min_c = min(c for (d, c) in last_year)
    low_date = [d for (d, c) in last_year if c == min_c][-1]
    cur_c = stock_data[-1][1]
    return {
        "low_date": low_date, "low_close": min_c, "cur_close": cur_c,
        "pct_from_low": (cur_c/min_c - 1) * 100,
    }

if __name__ == "__main__":
    print("Fetching SPY...", file=sys.stderr)
    spx = fetch_prices("SPY", 2018)
    print(f"  SPY: {len(spx)} days, latest {spx[-1]}", file=sys.stderr)
    # Save SPY
    with open("/home/user/cyclepapa/data/spy_prices.csv","w",newline="") as f:
        w = csv.writer(f); w.writerow(["date","close"])
        for d, c in spx: w.writerow([d, f"{c:.2f}"])
    print(f"  Saved SPY to data/spy_prices.csv", file=sys.stderr)
