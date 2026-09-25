"""How each manager's new buys have done since the public could see them.

A new buy: a position worth 0.5%+ of a fund's 13F book that it did not hold
the quarter before — the fund_moves rule, applied to six quarters of books
(fund_13f_history, fund_13f_prior, fund_13f_holdings), each compared with the
book for the immediately preceding quarter only (a missing quarter is a gap,
not a comparison across two). Left out, as in the Revealed Preference score:
stocks first listed during the quarter (an IPO allocation, a spin-off
received), a new CUSIP of an issuer already held (a rename or reorganisation,
not a purchase), books that jumped or collapsed in size (a partial filing),
ETFs and funds. Tickers come from today's CUSIP map, as in fund_moves.

The clock starts on the 13F's filing date — the first day anyone could have
copied the buy — at that day's close (or the next trading day's, within a
week) and runs to the stock's latest close; the S&P 500 (SPY) over the same
days is the yardstick (a stock taken over or delisted is measured to its last
close, and the S&P to that same day). Price moves only, split-adjusted, no
dividends on either side. Common sense, not a model: how often a manager's
new buys beat the market, and by how much in the middle case. Big bets (3%+
of the book) separately.

Tables: new_buy_returns (one row per new buy) and fund_track_record (per
fund; cohorts filed at least 90 days ago count, the latest shown apart as
too early to judge).
"""
import bisect, datetime as dt, os, sqlite3, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fund_moves import _quarter_before, _prev_quarter_end

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
MIN_WEIGHT, BIG = 0.5, 3.0
MATURE_DAYS = 90
EQUITY = ("h.sh_type IN ('SH','') AND substr(h.cusip,7,1) BETWEEN '0' AND '9' "
          "AND substr(h.cusip,8,1) BETWEEN '0' AND '9'")

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    period = dict(conn.execute("SELECT accession, period FROM sec_13f_filings WHERE period != ''"))
    # books read from FMP whose filing is not in this CIK's EDGAR index
    period.update({a: p for a, p in conn.execute(
        "SELECT accession, period FROM fund_13f_history_state WHERE accession IS NOT NULL") if a not in period})
    sec = dict(conn.execute("SELECT ticker, sec_type FROM unified_signal"))
    fundlike = {t for (t,) in conn.execute("SELECT ticker FROM ticker_yf WHERE is_fund = 1")}
    ipo = dict(conn.execute("SELECT ticker, ipo_date FROM ticker_yf WHERE ipo_date IS NOT NULL"))
    # books[fund][period] = [filed, {ticker: (value, cusip6)}, total, {cusip6}]
    books, src = {}, {}
    def load(table):
        for fund, acc, filed, tk, cusip, val in conn.execute(f"""SELECT h.fund, h.accession, h.filed,
                CASE WHEN cm.sec_type = 'etf' THEN NULL ELSE COALESCE(cm.ticker, h.ticker) END,
                h.cusip, h.value_k FROM {table} h LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
                WHERE {EQUITY}"""):
            # a prior filed under a predecessor CIK is not in this CIK's index:
            # its quarter is the one its filing date follows
            p = period.get(acc) or _quarter_before(filed)
            if not p:
                continue
            # a quarter held in two tables is read from the newer one only
            if src.setdefault((fund, p), table) != table:
                continue
            b = books.setdefault(fund, {}).setdefault(p, [filed, {}, 0.0, set()])
            b[0] = min(b[0] or filed, filed) if filed else b[0]
            b[2] += val or 0.0
            b[3].add((cusip or "")[:6])
            if tk:
                v, c6 = b[1].get(tk, (0.0, (cusip or "")[:6]))
                b[1][tk] = (v + (val or 0.0), c6)
    for table in ("fund_13f_holdings", "fund_13f_prior", "fund_13f_history"):
        load(table)
    # one reading per filing: a book under two roster names counts once
    seen_acc, keep = set(), {}
    acc_of = {}
    for fund, acc in conn.execute("SELECT fund, last_accession FROM fund_13f_state"):
        acc_of[fund] = acc
    for fund in sorted(books):
        a = acc_of.get(fund)
        if a and a in seen_acc:
            continue
        seen_acc.add(a)
        keep[fund] = books[fund]
    # prices
    px = {}
    for tk, d, c in conn.execute("SELECT ticker, date, close FROM prices WHERE close > 0 ORDER BY ticker, date"):
        px.setdefault(tk, ([], []))
        px[tk][0].append(d)
        px[tk][1].append(c)
    def price_on(tk, day):
        s = px.get(tk)
        if not s:
            return None, None
        i = bisect.bisect_left(s[0], day)
        if i >= len(s[0]):
            return None, None
        return s[0][i], s[1][i]
    def last(tk):
        s = px.get(tk)
        return (s[0][-1], s[1][-1]) if s else (None, None)
    def spy_upto(day):
        s = px.get("SPY")
        i = bisect.bisect_right(s[0], day) - 1 if s else -1
        return s[1][i] if i >= 0 else None
    if "SPY" not in px:
        raise SystemExit("track records: no SPY closes in prices (run ingest_prices_fmp.py)")
    today = dt.date.today()
    rows, unpriced, gaps = [], 0, 0
    for fund, per in keep.items():
        for cur in sorted(per):
            prev = _prev_quarter_end(cur)
            if prev not in per:
                if any(p < prev for p in per):
                    gaps += 1                             # a quarter missing mid-series
                continue
            _, h_prev, t_prev, c6_prev = per[prev]
            filed, h_cur, t_cur, _ = per[cur]
            if not t_cur or not t_prev or not (0.4 * t_cur <= t_prev <= 2.5 * t_cur):
                continue
            f10 = str(filed)[:10]
            for tk, (val, c6) in h_cur.items():
                w = 100.0 * val / t_cur
                if w < MIN_WEIGHT or tk in h_prev or c6 in c6_prev:
                    continue
                if (sec.get(tk) or "common") != "common" or tk in fundlike:
                    continue
                if (ipo.get(tk) or "") > prev:            # listed during the quarter
                    continue
                d0, p0 = price_on(tk, f10)
                d1, p1 = last(tk)
                # not trading within a week of the filing (taken over before the
                # 13F came out, or no price history): nothing a copier could buy
                if not (p0 and p1) or d1 <= d0 or \
                        (dt.date.fromisoformat(d0) - dt.date.fromisoformat(f10)).days > 7:
                    unpriced += 1
                    continue
                s0, s1 = spy_upto(d0), spy_upto(d1)
                if not (s0 and s1):
                    unpriced += 1
                    continue
                r = 100.0 * (p1 / p0 - 1)
                rs = 100.0 * (s1 / s0 - 1)
                rows.append((fund, cur, tk, round(w, 2), f10, d0, p0, d1, p1, round(r, 2), round(rs, 2),
                             round(r - rs, 2)))
    conn.executescript("""DROP TABLE IF EXISTS new_buy_returns;
        CREATE TABLE new_buy_returns (fund TEXT, period TEXT, ticker TEXT, pct_book REAL, filed TEXT,
          entry_date TEXT, entry_px REAL, last_date TEXT, last_px REAL, ret REAL, spy_ret REAL, excess REAL);
        DROP TABLE IF EXISTS fund_track_record;
        CREATE TABLE fund_track_record (fund TEXT PRIMARY KEY, n INTEGER, beat_pct REAL, med_excess REAL,
          avg_excess REAL, n_big INTEGER, big_beat_pct REAL, big_med_excess REAL, first_period TEXT,
          last_period TEXT, best TEXT, worst TEXT, recent_n INTEGER, recent_med_excess REAL);""")
    conn.executemany(f"INSERT INTO new_buy_returns VALUES ({','.join('?' * 12)})", rows)
    by_fund = {}
    for r in rows:
        by_fund.setdefault(r[0], []).append(r)
    out = []
    for fund, rs in by_fund.items():
        mature = [r for r in rs if (today - dt.date.fromisoformat(r[4])).days >= MATURE_DAYS]
        recent = [r for r in rs if (today - dt.date.fromisoformat(r[4])).days < MATURE_DAYS]
        if not mature and not recent:
            continue
        ex = [r[11] for r in mature]
        big = [r[11] for r in mature if r[3] >= BIG]
        best = max(mature, key=lambda r: r[11]) if mature else None
        worst = min(mature, key=lambda r: r[11]) if mature else None
        out.append((fund, len(mature),
                    round(100.0 * sum(1 for x in ex if x > 0) / len(ex), 0) if ex else None,
                    round(statistics.median(ex), 1) if ex else None,
                    round(statistics.fmean([max(-100, min(300, x)) for x in ex]), 1) if ex else None,
                    len(big), round(100.0 * sum(1 for x in big if x > 0) / len(big), 0) if big else None,
                    round(statistics.median(big), 1) if big else None,
                    min(r[1] for r in rs), max(r[1] for r in rs),
                    f"{best[2]} {best[11]:+.0f}" if best else "", f"{worst[2]} {worst[11]:+.0f}" if worst else "",
                    len(recent), round(statistics.median([r[11] for r in recent]), 1) if recent else None))
    conn.executemany(f"INSERT INTO fund_track_record VALUES ({','.join('?' * 14)})", out)
    conn.commit()
    n_mature = sum(1 for r in rows if (today - dt.date.fromisoformat(r[4])).days >= MATURE_DAYS)
    allx = [r[11] for r in rows if (today - dt.date.fromisoformat(r[4])).days >= MATURE_DAYS]
    print(f"track records: {len(rows):,} new buys across {len(by_fund)} funds ({n_mature:,} filed {MATURE_DAYS}+ days "
          f"ago); all funds together: {100.0 * sum(1 for x in allx if x > 0) / max(len(allx), 1):.0f}% beat the "
          f"S&P 500, median {statistics.median(allx) if allx else 0:+.1f} pts; {unpriced:,} new buys not trading "
          f"within a week of the filing (or unpriced) left out; {gaps} fund-quarters without the quarter "
          f"before on file", flush=True)
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(run())
