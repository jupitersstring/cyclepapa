"""Offline scenario tests for the 13F quarterly roll (ingest_13f.run).

EDGAR fetchers are stubbed and every scenario runs on a throwaway database,
so this never touches data/cyclepapa.db or the network:
    python3 pipeline/test_13f_roll.py
Covers the normal roll (old book -> prior), an EMPTY newest report, an empty
same-quarter re-file, an old-quarter restatement filed last, a failed fetch,
an already-current book, a successor-filer re-point (union prior), and a
dormant book surviving repeated runs.
"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

def row(cusip, shares, value, issuer="X CORP", title="COM"):
    return {"issuer": issuer, "cusip": cusip, "value_k": value, "shares": shares, "type": "SH",
            "title": title, "put_call": ""}

def hr(acc, filed, period, form="13F-HR"):
    return {"form": form, "acc": acc, "filed": filed, "period": period}

BOOKS, FILINGS = {}, {}
m.f13_filings = lambda cik, need_hr=3: FILINGS.get(str(int(cik)))
m.fetch_book = lambda cik, acc: BOOKS.get(acc)
m.cusip_ticker_map = lambda conn: {}
m.time.sleep = lambda s: None

_TEMP = []

def fresh_db():
    path = tempfile.mktemp(suffix=".db")
    _TEMP.append(path)
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE fund_meta (fund TEXT PRIMARY KEY, fund_group TEXT, source_block TEXT, total_rows INTEGER);
        CREATE TABLE cusip_map (cusip TEXT PRIMARY KEY, ticker TEXT, sec_type TEXT, source TEXT, asof TEXT);
        CREATE TABLE ticker_yf (ticker TEXT PRIMARY KEY, price REAL);""")
    c.commit(); c.close()
    m.DB = path
    return path

def state(path, fund):
    c = sqlite3.connect(path)
    s = c.execute("SELECT cik, last_accession, n_holdings FROM fund_13f_state WHERE fund=?", (fund,)).fetchone()
    p = c.execute("SELECT accession, n_holdings FROM fund_13f_prior_state WHERE fund=?", (fund,)).fetchone()
    pr = c.execute("SELECT accession, cusip, shares FROM fund_13f_prior WHERE fund=? ORDER BY accession, cusip", (fund,)).fetchall()
    cur = c.execute("SELECT accession, cusip, shares FROM fund_13f_holdings WHERE fund=? ORDER BY cusip", (fund,)).fetchall()
    c.close()
    return s, p, cur, pr

fails = 0
def check(name, cond, detail):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))
    fails += 0 if cond else 1

# ---------- 1-4: one fund, scenarios on the same CIK ----------
m.FUND_CIK = {"Test Fund": "111"}
m.FUND_STYLE_LABEL = {}; m.FUND_STYLE_LABEL_SAVED = {}

def scenario(filings, books, stored=None):
    path = fresh_db()
    FILINGS.clear(); BOOKS.clear()
    if stored:
        FILINGS["111"] = [hr(*stored[:3])]
        BOOKS[stored[0]] = stored[3]
        m.run()                                    # first ingest = stored book
    FILINGS["111"] = filings
    BOOKS.update(books)
    m.run(refresh=True)
    return path

Q1 = ("acc-q1", "2026-05-15", "2026-03-31", [row("AAA111111", 100, 1000), row("BBB222222", 50, 500)])
# 1. normal roll
p = scenario([hr("acc-q2", "2026-08-14", "2026-06-30"), hr(*Q1[:3])],
             {"acc-q2": [row("AAA111111", 150, 1600)]}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("normal roll: current is Q2", s[1] == "acc-q2" and cur == [("acc-q2", "AAA111111", 150)], (s, cur))
check("normal roll: prior is the old Q1 book", ps[0] == "acc-q1" and len(pr) == 2, (ps, pr))
# 2. empty newest report
p = scenario([hr("acc-q2e", "2026-07-06", "2026-06-30"), hr(*Q1[:3])], {"acc-q2e": []}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("empty report: current is the empty Q2", s[1] == "acc-q2e" and s[2] == 0 and cur == [], (s, cur))
check("empty report: prior is Q1", ps and ps[0] == "acc-q1", ps)
# 3. same-quarter re-file that is empty, original has rows
p = scenario([hr("acc-q2x", "2026-09-01", "2026-06-30"), hr("acc-q2", "2026-08-14", "2026-06-30"), hr(*Q1[:3])],
             {"acc-q2x": [], "acc-q2": [row("AAA111111", 150, 1600)]}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("empty same-quarter re-file falls to the real Q2", s[1] == "acc-q2", s)
# 4. old-quarter restatement filed last
p = scenario([hr("acc-q4r", "2026-09-10", "2025-12-31"), hr("acc-q2", "2026-08-14", "2026-06-30"), hr(*Q1[:3])],
             {"acc-q4r": [row("ZZZ999999", 1, 1)], "acc-q2": [row("AAA111111", 150, 1600)]}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("old-quarter restatement never becomes current", s[1] == "acc-q2", s)
# 5. fetch failure keeps the stored book
p = scenario([hr("acc-q2", "2026-08-14", "2026-06-30"), hr(*Q1[:3])], {"acc-q2": None}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("fetch failure keeps stored Q1", s[1] == "acc-q1" and len(cur) == 2, (s, cur))
# 6. already current: nothing changes
p = scenario([hr(*Q1[:3])], {}, stored=Q1)
s, ps, cur, pr = state(p, "Test Fund")
check("already current: untouched", s[1] == "acc-q1" and len(cur) == 2, (s, cur))
# 7. re-point to a successor filer; successor's own prior-quarter line joins the prior
path = fresh_db(); FILINGS.clear(); BOOKS.clear()
FILINGS["111"] = [hr(*Q1[:3])]; BOOKS["acc-q1"] = Q1[3]
m.run()
m.FUND_CIK = {"Test Fund": "222"}
FILINGS["222"] = [hr("acc-b-q2", "2026-08-14", "2026-06-30"), hr("acc-b-q1", "2026-05-15", "2026-03-31")]
BOOKS["acc-b-q2"] = [row("AAA111111", 150, 1600), row("CCC333333", 9, 90)]
BOOKS["acc-b-q1"] = [row("CCC333333", 9, 90)]
m.run()                                          # no --refresh: a CIK change alone re-ingests
s, ps, cur, pr = state(path, "Test Fund")
check("re-point: current from successor CIK", s[0] == "222" and s[1] == "acc-b-q2", s)
check("re-point: prior = old filer Q1 + successor's own Q1 line",
      sorted(a for a, _, _ in pr) == ["acc-b-q1", "acc-q1", "acc-q1"], pr)
# 8. archive survives a second run (the re-run once wiped every archived book)
path = fresh_db(); FILINGS.clear(); BOOKS.clear()
m.FUND_CIK = {"Old Fund": "333"}
FILINGS["333"] = [hr("acc-old", "2024-02-14", "2023-12-31")]; BOOKS["acc-old"] = [row("AAA111111", 5, 50)]
m.run(); m.run(refresh=True); m.run(refresh=True)
c = sqlite3.connect(path)
arch = c.execute("SELECT COUNT(*) FROM fund_13f_dormant WHERE fund='Old Fund'").fetchone()[0]
live = c.execute("SELECT COUNT(*) FROM fund_13f_holdings WHERE fund='Old Fund'").fetchone()[0]
check("dormant book archived once and kept on re-runs", arch == 1 and live == 0, (arch, live))
# 9. qkey / prev_quarter
check("prev_quarter", [m.prev_quarter(p) for p in ("2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31")]
      == ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"], "")
for t in _TEMP:
    if os.path.exists(t):
        os.remove(t)
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
