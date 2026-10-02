"""Revealed preference: what the tracked investors are BUYING now, with dated evidence.

The old ranking (2 x new + adds + 0.5 x top picks) read the research
spreadsheet's position sections, a snapshot dated May-June 2026: by September
it was a quarter stale and blind to Q2 13Fs, insider buys and new stakes. This
ranks each stock on evidence with an explicit freshness window, net of selling:

  13F, latest completed quarter only — each fund's book against its exact
    preceding quarter (split-adjusted shares). A fund's contribution is the
    share of its book it committed: a new position counts its weight, an add
    the added part, a trim / exit subtracts the weight sold — capped at 10
    points per fund and scaled by focus min(1, 75 / positions), so a 40-stock
    book outweighs a 3,000-line one. Funds whose latest book is an older
    quarter (late filers) are left out rather than read as fresh.
  Insiders, last 90 days — open-market purchases (Form 4 code P) of $25k+:
    +2 per insider (up to 5), +2 when a C-suite officer is among them.
  New 13D / 13G stakes, last 90 days — initial filings by tracked holders:
    +5 per 13D (activist), +2 per 13G.
  N-PORT, each fund's latest report — +1 per manager initiating or adding,
    -1 per manager trimming or exiting.

  Capital structure — the choices that betray a view:
    insiders exercising or converting into common and HOLDING (FMP's full
    Form 4 feed, 90 days; kept at least half rather than selling within a
    week): +1 each, up to 3;
    funds converting into common (13F, latest quarter: a warrant / note /
    preferred position shrank while the same issuer's common grew — CUSIP
    issuer prefix): +1 each, up to 3;
    issuer tender offers (SC TO-I, 90 days): +3;
    net buybacks in the last fiscal year (FMP cash flow, share of market
    cap): +1 / +2 / +3 at 3 / 6 / 10%; net issuance: -1 at 5%, -2 at 15%;
    13D/G amendments raising a stake by a point or more (90 days): +2 each.

RP score = the sum. Every row carries the date of its latest evidence.
Output: table revealed_pref (one row per stock with any evidence).
"""
import datetime as dt
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nport_diff import nport_diff

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
INSIDER_DAYS, STAKE_DAYS = 90, 90
from fund_moves import MIN_WEIGHT, latest_due_quarter, eligible_funds, quarter_moves
from fund_moves import short_fund as _short

def thirteen_f(conn, quarter):
    """{ticker: {"pts", "buy": [...], "sell": [...]}} from the funds whose
    current book is `quarter` and whose prior is the preceding quarter
    (position rules in fund_moves.quarter_moves, shared with the style book)."""
    moves, funds = quarter_moves(conn, quarter)
    res = {}
    for m in moves:
        d = res.setdefault(m["ticker"], {"pts": 0.0, "buy": [], "sell": []})
        d["pts"] += m["pts"]
        (d["buy"] if m["pts"] > 0 else d["sell"]).append(
            (abs(m["pts"]), f"{_short(m['fund'])} ({m['label']})"))
    return res, len(funds)

def insiders(conn):
    res = {}
    for tk, owner, role, usd, last in conn.execute(f"""SELECT f.ticker, COALESCE(f.owner_cik, f.owner), MAX(f.role),
            SUM(f.shares * f.price), MAX(f.trans_date)
        FROM form4_transactions f
        WHERE f.code = 'P' AND f.acquired = 1 AND f.price IS NOT NULL AND f.price < 200000
          AND f.trans_date >= date('now', '-{INSIDER_DAYS} days')
          AND NOT EXISTS (SELECT 1 FROM ticker_yf y WHERE y.ticker = f.ticker
              AND ((y.mcap_m > 0 AND f.shares * f.price / 1e6 > y.mcap_m)
                OR (y.price > 0 AND (f.price > y.price * 5 OR f.price < y.price * 0.10))))
        GROUP BY f.ticker, 2 HAVING SUM(f.shares * f.price) >= 25000"""):
        d = res.setdefault(tk, {"n": 0, "usd": 0.0, "csuite": False, "last": ""})
        d["n"] += 1
        d["usd"] += usd or 0.0
        d["last"] = max(d["last"], last or "")
        if role and any(k in role.upper() for k in ("CEO", "CFO", "CHIEF", "PRESIDENT", "CHAIR")):
            d["csuite"] = True
    return res

def stakes(conn):
    res = {}
    for tk, holder, form, filed, pct in conn.execute(f"""SELECT subject_ticker, holder, form, MAX(filed), MAX(pct_class)
        FROM holder_13d WHERE subject_ticker IS NOT NULL AND filed >= date('now', '-{STAKE_DAYS} days')
          AND (form LIKE '%13D' OR form LIKE '%13G') GROUP BY subject_ticker, holder, form"""):
        d = res.setdefault(tk, {"pts": 0.0, "who": [], "last": ""})
        is_d = form.endswith("13D")
        d["pts"] += 5.0 if is_d else 2.0
        d["who"].append(f"{_short(holder)} ({'13D' if is_d else '13G'}{f' {pct:.1f}%' if pct else ''})")
        d["last"] = max(d["last"], filed or "")
    return res

def nport(conn):
    _, _, mgr = nport_diff(conn)
    key_tk = {}
    period = {}
    for key, tk, mg, p in conn.execute("""SELECT COALESCE(isin, ticker, issuer), ticker, manager, MAX(period)
            FROM nport_holdings GROUP BY 1, 3"""):
        if tk:
            key_tk[key] = tk
        period[(mg, key)] = p
    for key, tk in conn.execute("SELECT COALESCE(isin, ticker, issuer), ticker FROM nport_prior WHERE ticker IS NOT NULL"):
        key_tk.setdefault(key, tk)
    res = {}
    for (mg, key), st in mgr.items():
        tk = key_tk.get(key)
        if not tk or st not in ("new", "added", "trimmed", "exited"):
            continue
        d = res.setdefault(tk, {"pts": 0, "buy": [], "sell": [], "last": ""})
        if st in ("new", "added"):
            d["pts"] += 1
            d["buy"].append(f"{_short(mg)} ({st})")
            d["last"] = max(d["last"], period.get((mg, key)) or "")
        else:
            d["pts"] -= 1
            d["sell"].append(f"{_short(mg)} ({st})")
    return res

_NOT_COMMON = r"option|warrant|restricted|\\brsu\\b|\\bunit|note|debenture|preferred|\\bright|phantom|performance"

def capital_structure(conn, quarter):
    """{ticker: {"pts", "notes": [...], "last": date}} — see the module note."""
    import re
    res = {}

    def add(tk, pts, note, date=""):
        d = res.setdefault(tk, {"pts": 0.0, "notes": [], "last": ""})
        d["pts"] += pts
        d["notes"].append(note)
        d["last"] = max(d["last"], date or "")

    # 1. insiders exercising / converting into common and holding it
    acq, disp = {}, {}
    for sym, cik, name, tt, ad, sh, td, sec in conn.execute(f"""SELECT symbol, reporting_cik, name, trans_type,
            acq_disp, shares, trans_date, security_name FROM insider_fmp
            WHERE trans_date >= date('now', '-{INSIDER_DAYS} days') AND shares > 0"""):
        if re.search(_NOT_COMMON, sec or "", re.I):
            continue
        k = (sym, cik)
        if ad == "A" and tt in ("M-Exempt", "X-InTheMoney", "C-Conversion"):
            acq.setdefault(k, []).append((td, sh, tt, name))
        elif ad == "D" and tt in ("S-Sale", "F-InKind"):
            disp.setdefault(k, []).append((td, sh))
    per = {}
    for (sym, cik), lots in acq.items():
        got = sum(sh for _, sh, _, _ in lots)
        days = {dt.date.fromisoformat(td) for td, *_ in lots if td}
        sold = sum(sh for td, sh in disp.get((sym, cik), []) if td and any(
            abs((dt.date.fromisoformat(td) - d).days) <= 7 for d in days))
        if got > 0 and (got - sold) >= 0.5 * got:
            conv = any(tt == "C-Conversion" for _, _, tt, _ in lots)
            per.setdefault(sym, []).append((lots[0][3], conv, max(td for td, *_ in lots)))
    for sym, owners in per.items():
        n = len(owners)
        add(sym, min(n, 3), f"{n} insider{'s' if n > 1 else ''} "
                            f"{'converted' if all(c for _, c, _ in owners) else 'exercised'} into common and held",
            max(d for _, _, d in owners))

    # 2. funds converting a warrant / note / preferred into the common
    funds = eligible_funds(conn, quarter)
    if funds:
        ph = ",".join("?" * len(funds))
        def books(table):
            out = {}
            for fund, cusip, tk, form, sh, val in conn.execute(f"""SELECT h.fund, h.cusip, h.ticker,
                    COALESCE(f.sec_form, 'common'), h.shares, h.value_k FROM {table} h
                    LEFT JOIN holding_sec_form f ON f.accession = h.accession AND f.cusip = h.cusip
                    WHERE h.fund IN ({ph}) AND h.cusip IS NOT NULL""", funds):
                d = out.setdefault((fund, cusip[:6]), {"csh": 0.0, "der": 0.0, "tk": None, "kinds": set()})
                if form in ("warrant", "note", "preferred", "right", "convertible"):
                    d["der"] += val or 0.0
                    d["kinds"].add(form)
                else:
                    d["csh"] += sh or 0.0
                    if tk and " " not in tk:
                        d["tk"] = tk
            return out
        cur, pri = books("fund_13f_holdings"), books("fund_13f_prior")
        tot = {f: v for f, v in conn.execute(f"""SELECT fund, SUM(value_k) FROM fund_13f_prior
            WHERE fund IN ({ph}) GROUP BY fund""", funds)}
        conv = {}
        for (fund, pre), p in pri.items():
            c = cur.get((fund, pre))
            if not c or not c["tk"] or not tot.get(fund):
                continue
            if (p["der"] >= 0.0025 * tot[fund] and c["der"] <= 0.5 * p["der"]
                    and c["csh"] > 0 and c["csh"] >= 1.25 * p["csh"]):
                conv.setdefault(c["tk"], []).append((_short(fund), "/".join(sorted(p["kinds"]))))
        for tk, who in conv.items():
            add(tk, min(len(who), 3), "; ".join(f"{f} converted {k} into common" for f, k in who), quarter)

    # 3. issuer tender offers
    for tk, filed in conn.execute(f"""SELECT ticker, MAX(filed) FROM corp_actions WHERE form = 'SC TO-I'
            AND ticker IS NOT NULL AND filed >= date('now', '-{STAKE_DAYS} days') GROUP BY ticker"""):
        add(tk, 3.0, f"issuer tender offer ({filed})", filed)

    # 4. net buybacks / issuance, last fiscal year
    for tk, y, fy in conn.execute("""SELECT ticker, net_buyback_yield, buyback_fy FROM ticker_yf
            WHERE net_buyback_yield IS NOT NULL"""):
        pts = (3 if y >= 0.10 else 2 if y >= 0.06 else 1 if y >= 0.03 else
               -2 if y <= -0.15 else -1 if y <= -0.05 else 0)
        if pts:
            add(tk, pts, f"net {'buyback' if y > 0 else 'issuance'} {abs(y) * 100:.1f}% of mcap (FY{fy})")

    # 5. 13D / 13G amendments raising a stake
    last = {}
    for holder, tk, filed, pct in conn.execute("""SELECT holder, subject_ticker, filed, pct_class FROM holder_13d
            WHERE subject_ticker IS NOT NULL AND pct_class IS NOT NULL ORDER BY filed"""):
        prev = last.get((holder, tk))
        cutoff = (dt.date.today() - dt.timedelta(days=STAKE_DAYS)).isoformat()
        if prev is not None and filed >= cutoff and pct >= prev + 1.0:
            add(tk, 2.0, f"{_short(holder)} raised its stake {prev:.1f}% to {pct:.1f}%", filed)
        last[(holder, tk)] = pct
    return res

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    q = latest_due_quarter()
    f13, n_funds = thirteen_f(conn, q)
    ins, stk, npt = insiders(conn), stakes(conn), nport(conn)
    cap = capital_structure(conn, q)
    conn.executescript("""DROP TABLE IF EXISTS revealed_pref;
        CREATE TABLE revealed_pref (ticker TEXT PRIMARY KEY, rp_score REAL,
          f13_points REAL, f13_buyers INTEGER, f13_sellers INTEGER, f13_buying TEXT, f13_selling TEXT,
          ins_n INTEGER, ins_usd_m REAL, ins_csuite INTEGER, ins_last TEXT,
          stake_n INTEGER, stake_holders TEXT, stake_last TEXT,
          np_buyers INTEGER, np_sellers INTEGER, np_buying TEXT, np_selling TEXT,
          evidence_date TEXT, quarter TEXT, cap_points REAL, cap_notes TEXT);""")
    rows = []
    for tk in set(f13) | set(ins) | set(stk) | set(npt) | set(cap):
        a, b, c, d, e = f13.get(tk), ins.get(tk), stk.get(tk), npt.get(tk), cap.get(tk)
        ins_pts = (2.0 * min(b["n"], 5) + (2.0 if b["csuite"] else 0.0)) if b else 0.0
        score = ((a["pts"] if a else 0.0) + ins_pts + (c["pts"] if c else 0.0) + (d["pts"] if d else 0.0)
                 + (e["pts"] if e else 0.0))
        dates = [x for x in ((q if a else ""), (b or {}).get("last", ""), (c or {}).get("last", ""),
                             (d or {}).get("last", ""), (e or {}).get("last", "")) if x]
        order = lambda xs: "; ".join(t for _, t in sorted(xs, reverse=True))
        rows.append((tk, round(score, 2),
                     round(a["pts"], 2) if a else None, len(a["buy"]) if a else 0, len(a["sell"]) if a else 0,
                     order(a["buy"]) if a else "", order(a["sell"]) if a else "",
                     b["n"] if b else 0, round(b["usd"] / 1e6, 2) if b else None, int(b["csuite"]) if b else 0,
                     b["last"] if b else None,
                     len(c["who"]) if c else 0, "; ".join(c["who"]) if c else "", c["last"] if c else None,
                     len(d["buy"]) if d else 0, len(d["sell"]) if d else 0,
                     "; ".join(d["buy"]) if d else "", "; ".join(d["sell"]) if d else "",
                     max(dates) if dates else None, q,
                     round(e["pts"], 1) if e else None, "; ".join(e["notes"]) if e else ""))
    conn.executemany(f"INSERT INTO revealed_pref VALUES ({','.join('?' * 22)})", rows)
    conn.commit()
    pos = sum(1 for r in rows if r[1] > 0)
    print(f"revealed preference: 13F {q} vs prior quarter for {n_funds} funds; {len(f13)} stocks with 13F moves, "
          f"{len(ins)} with insider buying ({INSIDER_DAYS}d), {len(stk)} with new 13D/G ({STAKE_DAYS}d), "
          f"{len(npt)} with N-PORT moves, {len(cap)} with capital-structure signals; {pos} net positive")
    kinds = {}
    for e in cap.values():
        for n in e["notes"]:
            k = ("insider exercise/convert & hold" if "insider" in n else "fund conversion" if "converted" in n
                 else "issuer tender" if "tender" in n else "buyback" if "buyback" in n
                 else "issuance" if "issuance" in n else "stake raised")
            kinds[k] = kinds.get(k, 0) + 1
    print("  capital structure:", ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])))
    for r in sorted(rows, key=lambda r: -r[1])[:12]:
        print(f"  {r[0]:8s} {r[1]:6.1f}  13F {r[3]} buy / {r[4]} sell  ins {r[7]}  stakes {r[11]}  nport {r[14]}  "
              f"{(r[5] or r[12] or r[16])[:70]}")
    conn.close()

if __name__ == "__main__":
    run()
