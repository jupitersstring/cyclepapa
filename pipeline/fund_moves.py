"""What each fund did in the latest quarter, position by position.

One source of truth for quarter-on-quarter 13F moves, shared by the Revealed
Preference score and the per-style "what this style bought / sold" tables. A
move is read only where it is comparable:
  * the fund's current book is the latest due quarter and its prior is an
    earlier quarter (name variants of one manager share one book);
  * both books are of comparable size (a partial prior filing fabricates
    adds and exits);
  * equity lines only (SH, common-stock CUSIPs), prior shares split-adjusted;
  * the move is worth at least MIN_WEIGHT % of the book — smaller is
    housekeeping, not preference.
Kinds: new (not held last quarter), add (shares +25% or more), trim (shares
-25% or more), exit (sold out).

A "new" line in a stock first listed during the quarter is not an open-market
purchase: an IPO allocation or a pre-IPO stake becoming reportable (D1,
Dragoneer and Atreides held SpaceX privately before its June 2026 listing)
counts half; a spin-off received from a stock the fund already held
(Honeywell Aerospace from Honeywell, FedEx Freight from FedEx) counts zero.
Both stay visible, labelled.
"""
import datetime as dt
import re

MIN_WEIGHT = 0.5          # % of book
FOCUS_CAP = 75.0          # a book of <=75 names votes fully; 600 names ~0.12

def latest_due_quarter(today=None):
    """The newest quarter end whose 13F deadline (+45 days) passed 10+ days ago."""
    today = today or dt.date.today()
    qe = [dt.date(y, m, d) for y in (today.year - 1, today.year)
          for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]
    return max(q for q in qe if q + dt.timedelta(days=55) <= today).isoformat()

_FULL = None
def _completions():
    """{31-character roster name: its full spelling} where another source
    (research notes, 13D/G filers, the roster itself) spells the name out:
    'Pershing Square Capital Managem' -> 'Pershing Square Capital Management'."""
    global _FULL
    if _FULL is None:
        _FULL = {}
        import os, sqlite3
        db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
        try:
            c = sqlite3.connect(db)
            names = set()
            for q in ("SELECT fund FROM fund_meta", "SELECT DISTINCT fund FROM fund_positions",
                      "SELECT DISTINCT holder FROM holder_13d", "SELECT DISTINCT fund FROM fund_13f_state"):
                try:
                    names |= {r[0] for r in c.execute(q) if r[0]}
                except sqlite3.OperationalError:
                    pass
            c.close()
        except Exception:
            names = set()
        for n in names:
            if len(n) == 31:
                longer = [m for m in names if len(m) > 31 and m.startswith(n.rstrip())]
                if longer:
                    _FULL[n] = min(longer, key=len)
    return _FULL

def short_fund(fund):
    """A fund's display name: 'Pabrai Investment Funds (Dalal ' -> 'Pabrai
    Investment Funds'. Roster names are cut at 31 characters, often mid-word;
    where another source spells the name out it is used ('Pershing Square
    Capital Managem' -> 'Pershing Square Capital Management')."""
    raw = fund or ""
    full = _completions().get(raw)
    if full:                                  # "... LLC / CT (Rob Citrone)": the firm is before the slash
        raw = re.split(r"\s/\s", full)[0]
    f = re.sub(r"\(.*?(\)|$)", "", raw)
    return re.split(r"\s{2,}", f)[0].strip() or raw.strip()

def eligible_funds(conn, quarter):
    """Funds whose current book is `quarter` and prior an earlier quarter,
    one per manager (name variants share a book)."""
    from _canon import canon as _cn
    period = {a: p for a, p in conn.execute(
        "SELECT accession, period FROM sec_13f_filings WHERE period != ''")}
    out, seen = [], set()
    for fund, cur_acc, pri_acc, pri_filed in conn.execute("""SELECT s.fund, s.last_accession, p.accession, p.filed
            FROM fund_13f_state s JOIN fund_13f_prior_state p ON p.fund = s.fund
            WHERE p.accession IS NOT NULL ORDER BY s.fund"""):
        # a prior filed under a predecessor CIK (Pershing Square's 2026-05-15
        # book) is not in this CIK's filings index: its quarter is the one the
        # filing date follows
        pp = period.get(pri_acc) or _quarter_before(pri_filed)
        if period.get(cur_acc) != quarter or not pp or pp >= quarter:
            continue
        # one reading per manager AND per filing: a book held under two roster
        # names ("TCI Fund Management Ltd" / "The Children's Investment Fund")
        # is one set of moves
        c = _cn(fund)
        if c not in seen and cur_acc not in seen:
            seen.add(c)
            seen.add(cur_acc)
            out.append(fund)
    return out

_EQUITY = ("h.sh_type IN ('SH','') AND substr(h.cusip,7,1) BETWEEN '0' AND '9' "
           "AND substr(h.cusip,8,1) BETWEEN '0' AND '9'")

def _books(conn, funds, table):
    ph = ",".join("?" * len(funds))
    out, tot, issuer = {}, {}, {}
    for fund, tk, iss, sh, val in conn.execute(f"""SELECT h.fund, COALESCE(cm.ticker, h.ticker),
            MAX(h.issuer), SUM(h.shares), SUM(h.value_k) FROM {table} h
            LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
            WHERE h.fund IN ({ph}) AND {_EQUITY} GROUP BY h.fund, 2""", funds):
        if tk:
            out[(fund, tk)] = (sh or 0.0, val or 0.0)
            issuer[tk] = iss
        tot[fund] = tot.get(fund, 0.0) + (val or 0.0)
    return out, tot, issuer

_NAME_STOP = {"the", "inc", "corp", "corporation", "co", "company", "companies", "holdings", "holding",
              "group", "plc", "ltd", "limited", "sa", "nv", "ag", "new", "com", "cl", "class"}

# words too common to tie a new listing to a parent ('Energy', 'Space', 'Super')
_GENERIC = set("""american america first global united national international china capital financial
    acquisition acquisitions bank bancorp trust pharmaceuticals pharma therapeutics technologies technology
    systems resources partners industries brands space digital applied future general health healthcare
    medical bio biosciences biotherapeutics software solutions data power energy gold mining metals oil gas
    royalty realty real estate properties income growth value equity fund investment investors north south
    west east pacific atlantic western eastern northern southern city community citizens peoples home homes
    auto motors air airlines water green blue silver alpha beta omega apex summit pinnacle liberty freedom
    victory star sun super ultra micro nano smart cloud cyber quantum next one two three new world""".split())

def _lead(name):
    """First distinctive word of a company name: 'HONEYWELL INTL INC' -> 'honeywell'
    ('' when the name opens with a generic word, which proves nothing)."""
    w = [x for x in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
         if x not in _NAME_STOP and len(x) > 2]
    return w[0] if w and w[0] not in _GENERIC else ""

def _is_spac(ticker, name, industry):
    return (industry == "Shell Companies" or "acquisition" in (name or "").lower()
            or bool(re.search(r"(-UN|U|-WT|W|R)$", ticker or "") and "acquisition" in (name or "").lower()))

def _quarter_before(filed):
    """The quarter end a 13F filed on `filed` covers (the last one before it)."""
    try:
        d = dt.date.fromisoformat(str(filed)[:10])
    except (TypeError, ValueError):
        return None
    ends = [dt.date(y, m, dd) for y in (d.year - 1, d.year) for m, dd in ((3, 31), (6, 30), (9, 30), (12, 31))]
    return max(e for e in ends if e < d).isoformat()

def _prev_quarter_end(quarter):
    y, m, _ = (int(x) for x in quarter.split("-"))
    return {3: f"{y - 1}-12-31", 6: f"{y}-03-31", 9: f"{y}-06-30", 12: f"{y}-09-30"}[m]

def quarter_moves(conn, quarter=None):
    """(moves, funds) — moves: one dict per material position change in
    `quarter` (default: the latest due quarter) with keys fund, ticker, kind,
    cw / pw (% of book now / last quarter), chg (% change in shares),
    focus (the fund's vote weight), pts (signed, focus-weighted % of book
    moved, capped at 10 per position), listing (None, 'listing' or
    'spin-off') and label ('new 4.1%', '+38% to 6.0%', 'exited 2.2%',
    '-50% to 1.1%', 'new 3.0% at listing'). funds: the eligible funds read."""
    quarter = quarter or latest_due_quarter()
    funds = eligible_funds(conn, quarter)
    if not funds:
        return [], []
    split = {(f, t): x for f, t, x in conn.execute("SELECT fund, ticker, factor FROM prior_split_factor")}
    cur, cur_tot, cur_issuer = _books(conn, funds, "fund_13f_holdings")
    pri, pri_tot, pri_issuer = _books(conn, funds, "fund_13f_prior")
    n_pos = {}
    for (f, _t) in cur:
        n_pos[f] = n_pos.get(f, 0) + 1
    # stocks first listed after the prior quarter end: a "new" line there is an
    # allocation, a pre-IPO stake or a spin-off, not an open-market purchase
    since = _prev_quarter_end(quarter)
    listed = {t for t, d in conn.execute("SELECT ticker, ipo_date FROM ticker_yf WHERE ipo_date IS NOT NULL")
              if d > since}
    names, industry = {}, {}
    for t, n, ind in conn.execute("SELECT ticker, long_name, industry FROM ticker_yf"):
        names[t], industry[t] = n, ind
    prior_leads = {}
    for (f, t) in pri:
        nm = pri_issuer.get(t) or names.get(t)
        if not _is_spac(t, nm, industry.get(t)):       # a sponsor's next SPAC is not a spin-off
            prior_leads.setdefault(f, set()).add(_lead(nm))
    moves, read = [], []
    for f in funds:
        ct, pt = cur_tot.get(f, 0.0), pri_tot.get(f, 0.0)
        # a pre-IPO stake becoming reportable at listing (D1's SpaceX: 62% of its
        # book) is not new money: leave it out of the like-for-like size check
        ct_like = ct - sum(v for (g, t), (sh, v) in cur.items()
                           if g == f and t in listed and pri.get((g, t), (0.0, 0.0))[0] <= 0)
        if not ct or not (0.4 * ct_like <= pt <= 2.5 * ct_like):
            continue
        read.append(f)
        focus = min(1.0, FOCUS_CAP / max(n_pos.get(f, 1), 1))
        tks = {t for (g, t) in cur if g == f} | {t for (g, t) in pri if g == f}
        for tk in tks:
            c_sh, c_val = cur.get((f, tk), (0.0, 0.0))
            p_sh, p_val = pri.get((f, tk), (0.0, 0.0))
            p_sh *= split.get((f, tk), 1.0)
            cw, pw = 100.0 * c_val / ct, (100.0 * p_val / pt if pt else 0.0)
            kind = None
            listing = None
            if c_sh > 0 and p_sh <= 0 and cw >= MIN_WEIGHT:
                kind, pts, label, chg = "new", min(cw, 10.0), f"new {cw:.1f}%", None
                if tk in listed:
                    nm = names.get(tk) or cur_issuer.get(tk)
                    lead = "" if _is_spac(tk, nm, industry.get(tk)) else _lead(nm)
                    if lead and lead in prior_leads.get(f, set()):
                        listing, pts, label = "spin-off", 0.0, f"new {cw:.1f}%, spin-off received"
                    else:
                        listing, pts, label = "listing", pts / 2, f"new {cw:.1f}% at listing"
            elif c_sh > 0 and p_sh > 0 and c_sh >= 1.25 * p_sh and cw >= MIN_WEIGHT:
                chg = 100 * (c_sh / p_sh - 1)
                kind, pts, label = "add", min(cw * (1 - p_sh / c_sh), 10.0), f"+{chg:.0f}% to {cw:.1f}%"
            elif p_sh > 0 and c_sh <= 0 and pw >= MIN_WEIGHT:
                kind, pts, label, chg = "exit", -min(pw, 10.0), f"exited {pw:.1f}%", -100.0
            elif p_sh > 0 and 0 < c_sh <= 0.75 * p_sh and pw >= MIN_WEIGHT:
                chg = -100 * (1 - c_sh / p_sh)
                kind, pts, label = "trim", -min(pw * (1 - c_sh / p_sh), 10.0), f"{chg:.0f}% to {cw:.1f}%"
            if kind:
                moves.append({"fund": f, "ticker": tk, "kind": kind, "cw": cw, "pw": pw, "chg": chg,
                              "focus": focus, "pts": focus * pts, "label": label, "listing": listing})
    return moves, read

def book_info(conn):
    """{fund: {...}} — the quarter each live 13F book is for, when it was
    filed, its equity positions, how concentrated it is (top-10 share of the
    book) and its vote weight min(1, 75 / positions)."""
    period = {a: p for a, p in conn.execute("SELECT accession, period FROM sec_13f_filings")}
    info = {}
    for fund, acc, filed in conn.execute("SELECT fund, last_accession, last_filed FROM fund_13f_state"):
        info[fund] = {"period": period.get(acc) or "", "filed": (filed or "")[:10],
                      "n": 0, "top10": None, "focus": None, "value_m": 0.0}
    vals = {}
    for fund, val in conn.execute(f"""SELECT h.fund, SUM(h.value_k) FROM fund_13f_holdings h
            WHERE {_EQUITY} AND h.ticker IS NOT NULL GROUP BY h.fund, h.cusip"""):
        vals.setdefault(fund, []).append(val or 0.0)
    for fund, v in vals.items():
        d = info.setdefault(fund, {"period": "", "filed": "", "n": 0, "top10": None,
                                   "focus": None, "value_m": 0.0})
        tot = sum(v) or 1.0
        v.sort(reverse=True)
        d.update(n=len(v), top10=100.0 * sum(v[:10]) / tot,
                 focus=min(1.0, FOCUS_CAP / len(v)), value_m=tot / 1e3)
    return info

def share_classes(conn):
    """{ticker: primary ticker} for issuers with two or more listed common
    share classes in the 13F books (same CUSIP issuer prefix): GOOG -> GOOGL,
    BRK-A -> BRK-B. The primary is the class held by the most funds. A fund
    holding both classes holds one company."""
    common, name = set(), {}
    for t, st, nm in conn.execute("""SELECT us.ticker, us.sec_type, COALESCE(y.long_name, us.name)
            FROM unified_signal us LEFT JOIN ticker_yf y ON y.ticker = us.ticker"""):
        if st == "common":
            common.add(t)
            name[t] = nm
    grp = {}
    # the issuer prefix AND the company name must agree: one filer's typo CUSIP
    # (a Visa line filed under Sotera Health's prefix) must not merge two issuers
    for c6, tk, n in conn.execute("""SELECT substr(cusip, 1, 6), ticker, COUNT(DISTINCT fund)
            FROM fund_13f_holdings WHERE ticker IS NOT NULL AND sh_type IN ('SH', '')
              AND substr(cusip, 7, 1) BETWEEN '0' AND '9' GROUP BY 1, 2"""):
        if tk in common and " " not in tk:
            key = (c6, _lead(name.get(tk)) or (name.get(tk) or "").lower()[:12])
            grp.setdefault(key, {})[tk] = max(n, grp.get(key, {}).get(tk, 0))
    out = {}
    for c6, d in grp.items():
        if len(d) < 2:
            continue
        primary = max(d, key=lambda t: (d[t], -len(t)))
        for tk in d:
            if tk != primary:
                out[tk] = primary
    return out

def section_evidence(conn, quarter=None):
    """Who stands behind each name's S1 / S3 / S4 counts, by the score's rule:
    where a fund has a current, comparable 13F book the filing supersedes the
    researcher notes — S3 new positions and S4 material adds are its moves in
    the latest quarter (spin-offs and new-at-listing lines excluded: not
    open-market decisions), and an S1 top-pick note counts only while it still
    holds the stock (any share class). Funds with no current book keep their
    notes. Other sections pass through as noted.

    Returns (evidence, stats): evidence = {ticker: {section: {manager: {'w':
    vote weight (13F: the fund's focus; notes: 1), 'src': '13F' | 'notes',
    'fund': fund name, 'label': 'new 4.1%' | 'research note'}}}}."""
    from _canon import canon
    moves, fresh_funds = quarter_moves(conn, quarter)
    # every roster name holding a book that was read is current — the research
    # notes under "The Children's Investment Fund" belong to the TCI filing read
    # as "TCI Fund Management Ltd"
    acc_of = dict(conn.execute("SELECT fund, last_accession FROM fund_13f_state"))
    read_accs = {acc_of.get(f) for f in fresh_funds} - {None}
    fresh = {canon(f) for f in fresh_funds} | {canon(f) for f, a in acc_of.items() if a in read_accs}
    cls = share_classes(conn)
    held_now, reportable = {}, set()
    for f, tk in conn.execute("SELECT DISTINCT fund, ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL"):
        held_now.setdefault(canon(f), set()).add(cls.get(tk, tk))
        reportable.add(tk)
    # a manager whose only 13F book went dormant (no filing in 200+ days:
    # closed, deregistered, below the threshold) has notes no fresher than it
    try:
        dormant = {canon(f) for (f,) in conn.execute("SELECT DISTINCT fund FROM fund_13f_dormant")} - fresh
    except Exception:
        dormant = set()
    ev = {}
    dropped = {1: 0, 3: 0, 4: 0, "dormant": 0}
    for f, tk, sec in conn.execute("""SELECT DISTINCT fund, ticker, section FROM fund_positions
            WHERE ticker IS NOT NULL"""):
        m = canon(f)
        if m in dormant and m not in held_now and sec in (1, 3, 4):
            dropped["dormant"] += 1
            continue
        if m in fresh and sec in (3, 4):
            dropped[sec] += 1
            continue
        if (m in fresh and sec == 1 and tk in reportable
                and cls.get(tk, tk) not in held_now.get(m, set())):
            dropped[1] += 1
            continue
        ev.setdefault(tk, {}).setdefault(sec, {})[m] = {"w": 1.0, "src": "notes", "fund": f,
                                                        "label": "research note"}
    n_fresh = {3: 0, 4: 0}
    for mv in moves:
        if mv["kind"] in ("new", "add") and not mv["listing"]:
            sec = 3 if mv["kind"] == "new" else 4
            m = canon(mv["fund"])
            d = ev.setdefault(mv["ticker"], {}).setdefault(sec, {})
            if m not in d or d[m]["w"] < mv["focus"]:
                d[m] = {"w": mv["focus"], "src": "13F", "fund": mv["fund"], "label": mv["label"]}
            n_fresh[sec] += 1
    return ev, {"fresh": len(fresh), "dropped": dropped, "n_fresh": n_fresh}
