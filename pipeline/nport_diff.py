"""Each N-PORT position against the fund's previous public report.

Shared by the N-PORT sheets and the Revealed Preference ranking. Share counts
are split-adjusted (nport_split_factor, from ingest_splits); added / trimmed
means shares up / down by more than 10%.
"""
import sqlite3

def nport_diff(conn):
    """Each N-PORT position against the fund's previous public report, on
    split-adjusted share counts (added / trimmed = more than 10% either way).
      pos[(series_id, key)] -> (status, delta %): new / added / trimmed / held,
                               '' when the fund has no earlier report on file
      exits[series_id]      -> [(name, prior $, country)]
      mgr[(manager, key)]   -> the same status across all of a manager's funds
    key = ISIN (else ticker, else issuer): stable across a ticker change."""
    try:
        cur = conn.execute("""SELECT series_id, manager, COALESCE(isin, ticker, issuer), ticker, shares
            FROM nport_holdings""").fetchall()
        pri = conn.execute("""SELECT p.series_id, COALESCE(p.isin, p.ticker, p.issuer), p.ticker, p.shares,
                p.val_usd, COALESCE(y.long_name, p.issuer), p.country
            FROM nport_prior p LEFT JOIN ticker_yf y ON y.ticker = p.ticker""").fetchall()
    except sqlite3.OperationalError:
        return {}, {}, {}
    try:
        split = {(sid, tk): f for sid, tk, f in conn.execute(
            "SELECT series_id, ticker, factor FROM nport_split_factor")}
    except sqlite3.OperationalError:
        split = {}
    has_prior = {r[0] for r in pri}
    mg_of = {sid: mg for sid, mg, *_ in cur}
    cur_by, pri_by = {}, {}
    for sid, mg, key, tk, sh in cur:
        a = cur_by.setdefault((sid, key), [0.0, True])
        if sh is None:
            a[1] = False
        else:
            a[0] += sh
    for sid, key, tk, sh, val, name, co in pri:
        a = pri_by.setdefault((sid, key), [0.0, True, 0.0, name, co])
        if sh is None:
            a[1] = False
        else:
            a[0] += sh * split.get((sid, tk), 1.0)
        a[2] += val or 0.0

    def classify(c_sh, p_sh, known):
        if not known or not p_sh:
            return "held", None
        r = c_sh / p_sh
        return ("added" if r > 1.10 else "trimmed" if r < 0.90 else "held"), (r - 1) * 100

    pos = {}
    for (sid, key), (c_sh, c_known) in cur_by.items():
        p = pri_by.get((sid, key))
        if sid not in has_prior:
            pos[(sid, key)] = ("", None)
        elif p is None:
            pos[(sid, key)] = ("new", None)
        else:
            pos[(sid, key)] = classify(c_sh, p[0], c_known and p[1])
    exits = {}
    for (sid, key), p in pri_by.items():
        if (sid, key) not in cur_by and sid in mg_of:
            exits.setdefault(sid, []).append((p[3], p[2], p[4]))
    agg = {}
    for (sid, key), (c_sh, c_known) in cur_by.items():
        if sid in has_prior:
            a = agg.setdefault((mg_of[sid], key), {"c": 0.0, "p": 0.0, "cin": False, "pin": False, "ok": True})
            a["c"] += c_sh; a["cin"] = True; a["ok"] &= c_known
    for (sid, key), p in pri_by.items():
        if sid in mg_of:
            a = agg.setdefault((mg_of[sid], key), {"c": 0.0, "p": 0.0, "cin": False, "pin": False, "ok": True})
            a["p"] += p[0]; a["pin"] = True; a["ok"] &= p[1]
    mgr = {}
    for k, a in agg.items():
        if a["cin"] and not a["pin"]:
            mgr[k] = "new"
        elif a["pin"] and not a["cin"]:
            mgr[k] = "exited"
        else:
            mgr[k] = classify(a["c"], a["p"], a["ok"])[0]
    return pos, exits, mgr
