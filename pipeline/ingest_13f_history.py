"""Earlier 13F books: the four quarters before the prior, for track records.

The books hold two quarters (current and prior), enough for last quarter's
moves but not for asking how a manager's earlier new buys have done since.
This loads each live filer's 13F-HR for the four quarters before its prior
(June 2025 - December 2025 books for a June 2026 current book, March 2025 too)
into fund_13f_history, through the same ingest path as the prior book:
options dropped, whole-dollar vs thousands detected, CUSIPs mapped by the same
authority. One reading per filing (a book held under two roster names is
loaded once). Already-loaded quarters are skipped; a failed read is left
unrecorded and retried next run.

Source: FMP's copy of the 13F information tables (its institutional-ownership
"extract": EDGAR's lines, each carrying the filing's accession in its link).
Checked against 40 books parsed from EDGAR's own XML: 38 identical line for
line; FMP leaves some options unflagged (dropped here by the same title test
EDGAR's lines get) and one $8K line was missing from a $4.7B book. EDGAR is
the fallback for a quarter FMP has nothing for: its archive server answers
this shared address with a 503 "slow down" page more often than not, which
made the first EDGAR-only load run for most of a day.

Tables: fund_13f_history (holdings, the fund_13f_holdings layout) and
fund_13f_history_state (fund, period -> accession, filed, positions, value).
"""
import json, os, re, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m
from enrich_fmp import API, api_key
from fund_moves import latest_due_quarter

DB = m.DB
N_BACK = 4          # quarters before the prior book
_ACC = re.compile(r"(\d{10}-\d{2}-\d{6})")

def _quick_curl(url, retries=6):
    """EDGAR fetch with short pauses: when SEC answers with its "slow down"
    page the same request often succeeds seconds later, and the roll's
    20-70 s back-off is far too slow for hundreds of filings."""
    for i in range(retries):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "30", "-A", m.UA, url], capture_output=True)
        out = r.stdout
        head = out[:8000]
        if (head.find(b"Rate Threshold Exceeded") != -1 or head.find(b"Undeclared Automated Tool") != -1
                or head.find(b"apology_objects") != -1):
            time.sleep(1.5 + i)
            continue
        return out
    return b""
m.curl = _quick_curl      # fetch_book / find_infotable call it through the module

def quarters_back(quarter, n):
    out, q = [], quarter
    for _ in range(n + 1):
        q = m.prev_quarter(q)
        out.append(q)
    return out[1:]      # skip the prior quarter itself (fund_13f_prior holds it)

def fmp_books(cik, period):
    """One filer's 13F-HR books for one quarter from FMP: {accession: [filed,
    rows]}, rows in parse_infotable's format with options and empty lines
    dropped as fetch_book drops them. {} = FMP has no filing for the quarter;
    None = FMP could not be read (retried next run). Lines FMP gives without
    an accession or for another quarter are counted, never guessed at."""
    y, q = int(period[:4]), (int(period[5:7]) - 1) // 3 + 1
    url = (f"{API}/institutional-ownership/extract?cik={str(int(cik)).zfill(10)}"
           f"&year={y}&quarter={q}&apikey={api_key()}")
    for attempt in range(5):
        body = subprocess.run(["curl", "-sS", "--max-time", "60", url], capture_output=True, text=True).stdout
        if "Limit Reach" in body:
            time.sleep(15 * (attempt + 1))
            continue
        try:
            d = json.loads(body)
        except ValueError:
            time.sleep(2)
            continue
        if not isinstance(d, list):
            return None
        out, stray = {}, 0
        for r in d:
            a = _ACC.search(r.get("link") or "") or _ACC.search(r.get("finalLink") or "")
            if not a or (r.get("date") or "")[:10] != period:
                stray += 1
                continue
            row = {"issuer": (r.get("nameOfIssuer") or "")[:80],
                   "cusip": (r.get("securityCusip") or "").upper(),
                   "value_k": int(float(r.get("value") or 0)),
                   "shares": int(float(r.get("shares") or 0)),
                   "type": r.get("sharesType") or "",
                   "title": (r.get("titleOfClass") or "")[:40],
                   "put_call": (r.get("putCallShare") or "").lower()}
            b = out.setdefault(a.group(1), [(r.get("filingDate") or "")[:10], []])
            if row["put_call"] or not (row["value_k"] or row["shares"]) \
                    or m.classify_sec_form(row["title"], row["type"]) == "option":
                continue
            b[1].append(row)
        if stray:
            out[None] = stray
        return out
    return None

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_13f_history (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
    CREATE INDEX IF NOT EXISTS idx_hist_fund ON fund_13f_history(fund);
    CREATE INDEX IF NOT EXISTS idx_hist_ticker ON fund_13f_history(ticker);
    CREATE TABLE IF NOT EXISTS fund_13f_history_state (
      fund TEXT, period TEXT, accession TEXT, filed TEXT, n_holdings INTEGER, total_value_k INTEGER,
      PRIMARY KEY (fund, period));
    """)
    name_map = m.cusip_ticker_map(conn)
    cusip_map = {c: (tk, st) for c, tk, st in conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    px_map = {t: p for t, p in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    maps = (cusip_map, name_map, px_map)
    periods = quarters_back(latest_due_quarter(), N_BACK)
    # one reading per filing: the name holding the current book's accession first
    funds = conn.execute("""SELECT MIN(s.fund), s.cik FROM fund_13f_state s
        WHERE s.cik IS NOT NULL AND s.n_holdings > 0 GROUP BY s.last_accession, s.cik""").fetchall()
    # a re-pointed fund (successor filer): its earlier books were filed under the
    # predecessor's CIK, as its prior book was (Pershing Square: the adviser's
    # book plus the successor's own HHH line) — both are read, as roll_prior does
    pred = {f: c for f, c in conn.execute("""SELECT p.fund, MIN(p.cik) FROM fund_13f_prior p
        JOIN fund_13f_state s ON s.fund = p.fund
        WHERE CAST(p.cik AS INTEGER) != CAST(s.cik AS INTEGER) GROUP BY p.fund""")}
    have = {(f, p) for f, p in conn.execute("SELECT fund, period FROM fund_13f_history_state")}
    todo = [(f, c, p) for f, c in funds for p in periods if (f, p) not in have]
    print(f"13F history: {len(funds)} filers x {len(periods)} quarters ({', '.join(periods)}); "
          f"{len(todo)} books to read, {len(funds) * len(periods) - len(todo)} already on file", flush=True)
    keys = sorted({(c, p) for f, c, p in todo} | {(pred[f], p) for f, c, p in todo if f in pred})
    with ThreadPoolExecutor(6) as ex:
        pre = dict(zip(keys, ex.map(lambda k: fmp_books(*k), keys)))
    done = {"fmp": 0, "edgar": 0}
    none = failed = stray = 0
    edgar_fails = [0]                    # EDGAR refusing us: stop asking after a run of failures

    def pick(cik, period):
        """One CIK's 13F-HR for the quarter: (accession, filed, rows, source),
        "none" (no filing) or "failed" (neither FMP nor EDGAR could be read)."""
        nonlocal stray
        cands = conn.execute("""SELECT accession, form, filed FROM sec_13f_filings
            WHERE cik = ? AND period = ? AND form LIKE '13F-HR%'
            ORDER BY (form = '13F-HR') DESC, filed DESC""", (str(int(cik)), period)).fetchall()
        fmp = pre.get((cik, period))
        if fmp:
            stray += fmp.pop(None, 0)
            for acc, form, filed in cands:              # the original 13F-HR first
                if fmp.get(acc) and fmp[acc][1]:
                    return acc, filed, fmp[acc][1], "fmp"
            best = sorted(((a, f, rs) for a, (f, rs) in fmp.items() if rs),   # a filing our index lacks:
                          key=lambda x: (-len(x[2]), x[1] or ""))              # the fullest book
            if best:
                return best[0][0], best[0][1], best[0][2], "fmp"
        if cands:                                       # FMP has nothing: EDGAR's own XML
            if edgar_fails[0] >= 3:
                return "failed"
            for acc, form, filed in cands:
                rows = m.fetch_book(cik, acc)
                if rows is None:
                    edgar_fails[0] += 1
                    return "failed"
                if rows:
                    edgar_fails[0] = 0
                    return acc, filed, rows, "edgar"
        return "failed" if fmp is None else "none"

    for i, (fund, cik, period) in enumerate(todo, 1):
        got = [(pick(c, period), c) for c in [cik] + ([pred[fund]] if fund in pred else [])]
        if any(g == "failed" for g, _ in got):
            failed += 1
            continue
        books = [(g, c) for g, c in got if g != "none"]
        if not books:
            conn.execute("INSERT OR REPLACE INTO fund_13f_history_state VALUES (?,?,?,?,?,?)",
                         (fund, period, None, None, 0, 0))
            none += 1
            continue
        state = None
        for (acc, filed, rows, src), c in books:
            conn.execute("DELETE FROM fund_13f_history WHERE fund = ? AND accession = ?", (fund, acc))
            n, total_v = m.ingest_book(conn, "fund_13f_history", fund, c, acc, filed, rows, *maps)
            if state is None or n > state[4]:           # the state row names the main book
                state = (fund, period, acc, filed, n, total_v)
            done[src] += 1
        conn.execute("INSERT OR REPLACE INTO fund_13f_history_state VALUES (?,?,?,?,?,?)", state)
        if i % 100 == 0:
            conn.commit()
            print(f"  {i}/{len(todo)} books read ({done['fmp']} from FMP, {done['edgar']} from EDGAR)", flush=True)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM fund_13f_history").fetchone()[0]
    print(f"DONE: {done['fmp'] + done['edgar']} books loaded ({done['fmp']} from FMP, {done['edgar']} from EDGAR), "
          f"{none} quarters with no 13F-HR, {failed} not readable (retried next run)"
          + (f", {stray} FMP lines without an accession or for another quarter left out" if stray else "")
          + f"; {n:,} history holdings", flush=True)
    conn.close()
    # a few unreadable quarters are retried next run; many means a source is down
    return 2 if failed > 0.05 * max(len(todo), 1) else 0

if __name__ == "__main__":
    sys.exit(run())
