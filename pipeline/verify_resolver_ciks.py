"""Verify the CIK resolvers' matches against EDGAR entity names.

fund_resolution_state.best_cik came from several generations of name
resolvers, and some matched the wrong EDGAR entity outright: Muddy Waters ->
Burger King Worldwide, Lawndale -> a Lehman Brothers capital trust, 1 Main
Capital -> DiamondRock Hospitality, Avenue Capital -> Third Avenue Management.
refresh_13d_efts reads best_cik as a 13D/G HOLDER CIK, and EDGAR full-text
search matches a CIK as filer OR subject, so a company's CIK pulled in the
13D/Gs filed ABOUT that company, booked as our fund ("Muddy Waters, 69% of
Burger King").

A match stands when the fund name and the EDGAR entity (current or any former
name) share two distinctive tokens, or the entity's leading word appears in the fund
name (not "Avenue Capital" vs "Third Avenue"), or one is the other's acronym (FPA = First
Pacific Advisors), or an all-generic name matches outright (Value Partners).
Hand-verified seeds (status manual_seed) are trusted.
Otherwise best_cik is cleared, status records the rejected entity, and the
13D/G rows booked under that CIK for that fund are deleted. The roster's own
13F CIKs get the same check, reported only: a mismatch there means a wrong book.

Usage: verify_resolver_ciks.py            (dry run: prints decisions)
       verify_resolver_ciks.py --apply
       verify_resolver_ciks.py --roster     (also name-check every roster 13F CIK)
"""
import json, os, re, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB
GENERIC = {"capital", "management", "mgmt", "mgt", "partners", "partner", "partnership", "fund", "funds",
    "asset", "assets", "advisors", "advisers", "advisory", "adviser", "advisor", "group", "holdings",
    "holding", "investment", "investments", "investors", "investor", "global", "value", "master",
    "offshore", "gp", "co", "company", "cos", "the", "opportunities", "opportunity", "lp", "llc", "llp",
    "ltd", "limited", "inc", "corp", "corporation", "trust", "associates", "sa", "ag", "plc", "pty", "et",
    "al", "de", "la", "ii", "iii", "iv", "of", "and", "international", "intl", "equity", "equities",
    "securities", "research", "financial", "strategies", "strategy", "ventures", "venture", "family",
    "office", "invt", "cap", "new", "york", "london", "uk", "us", "usa", "na", "adv"}
SUFFIX = {"lp", "llc", "llp", "ltd", "limited", "inc", "corp", "corporation", "co", "plc", "sa", "ag",
          "adv", "et", "al", "the", "of", "and"}

def _words(s):
    return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]

def toks(s):
    return {t for t in _words(s) if len(t) > 1 and t not in GENERIC}

def acronym(s):
    return "".join(w[0] for w in _words(s) if w not in SUFFIX)

def firm(fund):
    """The firm part of a roster name: no parenthetical PM, no "  Manager" tail."""
    f = re.sub(r"\(.*?(\)|$)", "", fund or "")
    return re.split(r"\s{2,}", f)[0].strip()

def _lead(s):
    return next((t for t in _words(s) if len(t) > 1 and t not in GENERIC), None)

def same_entity(fund, names):
    ft = toks(fund)
    for n in names:
        nt = toks(n)
        common = ft & nt
        # the entity's LEADING word must be in the fund name: "Avenue Capital"
        # is not "Third Avenue Management", but Pabrai's "(Dalal" is Dalal
        # Street LLC and "M3F Inc M3 Partners" is M3 Partners LP
        if len(common) >= 2 or (common and _lead(n) in ft):
            return True
        a_f, a_n = acronym(firm(fund)), acronym(n)
        if (len(a_n) >= 3 and a_n in ft) or (len(a_f) >= 3 and a_f in nt):
            return True
        sq_f = re.sub(r"[^a-z0-9]", "", firm(fund).lower())
        sq_n = re.sub(r"[^a-z0-9]", "", n.lower())
        if (not ft or not nt) and sq_f and (sq_f in sq_n or sq_n in sq_f):
            return True
    return False

_NAMES = {}

def edgar_names(cik):
    """[current name, former names...] for a CIK; None when the fetch failed."""
    k = str(int(cik))
    if k not in _NAMES:
        body = m.curl(f"https://data.sec.gov/submissions/CIK{k.zfill(10)}.json")
        try:
            d = json.loads(body) if body else None
        except json.JSONDecodeError:
            d = None
        if d is None:
            return None
        _NAMES[k] = [d.get("name") or ""] + [x.get("name") or "" for x in d.get("formerNames") or []]
        time.sleep(0.15)
    return _NAMES[k]

def run(apply=False, roster_check=False):
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    rows = conn.execute("""SELECT fund, best_cik, status FROM fund_resolution_state
                           WHERE best_cik IS NOT NULL AND best_cik != ''""").fetchall()
    rejected, failed = [], 0
    for fund, cik, status in rows:
        if status == "manual_seed":
            continue       # a hand-verified match (Greenlight -> DME Capital, Einhorn's rename)
        names = edgar_names(cik)
        if names is None:
            failed += 1; continue
        if not same_entity(fund, names):
            rejected.append((fund, str(int(cik)), names[0]))
    print(f"{len(rows)} resolver matches checked; {len(rejected)} point at a different entity"
          f"{f'; {failed} could not be fetched (kept)' if failed else ''}")
    n13d = 0
    for fund, cik, ent in rejected:
        k13 = conn.execute("""SELECT COUNT(*) FROM holder_13d WHERE holder = ?
                              AND holder_cik IN (?, ?)""", (fund[:60], cik, cik.zfill(10))).fetchone()[0]
        print(f"  ✗ {fund[:40]:40s} CIK {cik:>8s} is {ent[:40]!r}  ({k13} 13D/G rows booked under it)")
        if apply:
            conn.execute("UPDATE fund_resolution_state SET best_cik = NULL, status = ? WHERE fund = ?",
                         (f"rejected: CIK {cik} is {ent[:60]}", fund))
            n13d += conn.execute("DELETE FROM holder_13d WHERE holder = ? AND holder_cik IN (?, ?)",
                                 (fund[:60], cik, cik.zfill(10))).rowcount
    # the roster's 13F CIKs: report only (a wrong one means a wrong book)
    roster = {f: str(k) for f, k in conn.execute("SELECT fund, cik FROM fund_13f_state WHERE cik IS NOT NULL")}
    roster.update({f: str(k) for f, k in m.FUND_CIK.items() if k})
    odd = []
    for fund, cik in (sorted(roster.items()) if roster_check else []):
        names = edgar_names(cik)
        if names is not None and not same_entity(fund, names):
            odd.append((fund, cik, names[0]))
    if roster_check:
        print(f"{len(roster)} roster 13F CIKs checked; {len(odd)} filer names do not resemble the fund:")
    for fund, cik, ent in odd:
        print(f"  ? {fund[:40]:40s} CIK {cik:>8s} files as {ent[:48]!r}")
    if apply:
        conn.commit()
        print(f"applied: {len(rejected)} resolver CIKs cleared, {n13d} 13D/G rows deleted")
    else:
        print("dry run: nothing changed (--apply to clear them)")
    conn.close()
    return len(odd)

if __name__ == "__main__":
    sys.exit(1 if run(apply="--apply" in sys.argv[1:], roster_check="--roster" in sys.argv[1:]) else 0)
