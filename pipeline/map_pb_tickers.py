"""Map pb_affiliation.company -> ticker using our own universe (no external calls).

Best-effort name match against ticker_meta / ticker_yf / 13F issuers. Many
affiliations are foreign listings (Gulf/India/Europe boards) outside our US-13F
universe and stay unmapped — that is expected and surfaced separately as a
"titan-connected, not in universe" watchlist.
"""
import os, re, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

_SUFFIX = re.compile(
    r"\b(INC|CORP|CORPORATION|LTD|LIMITED|PLC|LLC|LLP|LP|CO|COMPANY|GROUP|"
    r"HOLDINGS?|SA|AG|NV|SE|OYJ|ASA|AB|SPA|BHD|TBK|PJSC|PSC|THE|"
    r"CLASS [A-C]|ADR|ADS)\b", re.I)

def norm(s):
    s = (s or "").upper()
    s = re.sub(r"\([^)]*\)?$", "", s)         # drop trailing (possibly unclosed) paren tag
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def build_index(conn):
    idx = {}
    def add(tk, nm):
        n = norm(nm)
        if n and len(n) >= 3 and n not in idx:
            idx[n] = tk
    for tk, nm in conn.execute("SELECT ticker, name FROM ticker_meta WHERE name IS NOT NULL"):
        add(tk, nm)
    for tk, nm in conn.execute("SELECT ticker, long_name FROM ticker_yf WHERE long_name IS NOT NULL"):
        add(tk, nm)
    for tk, iss in conn.execute("""SELECT ticker, issuer FROM fund_13f_holdings
        WHERE ticker IS NOT NULL AND issuer IS NOT NULL GROUP BY ticker"""):
        add(tk, iss)
    return idx

def run():
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE pb_affiliation SET ticker=NULL")   # idempotent re-map
    idx = build_index(conn)
    # longest keys first so a fuzzy contains-match prefers the most specific name
    keys_by_len = sorted(idx.keys(), key=len, reverse=True)
    exact = fuzzy = 0
    rows = conn.execute("SELECT rowid, company FROM pb_affiliation").fetchall()
    for rowid, company in rows:
        n = norm(company)
        if not n:
            continue
        tk = idx.get(n)
        if tk:
            exact += 1
        elif len(n) >= 6:
            # fuzzy: one name is a whole-word prefix of the other. Require the
            # SHORTER (the shared stem) to be multi-word, so a generic single word
            # can't bridge two different firms — e.g. "Reliance" must not link
            # "Reliance Industries" (Ambani, India) to "Reliance, Inc." (US steel, RS).
            for k in keys_by_len:
                if n == k or n.startswith(k + " ") or k.startswith(n + " "):
                    stem = k if len(k) < len(n) else n
                    if " " in stem and abs(len(k) - len(n)) <= 12:
                        tk = idx[k]; fuzzy += 1; break
        if tk:
            conn.execute("UPDATE pb_affiliation SET ticker=? WHERE rowid=?", (tk, rowid))
    conn.commit()
    mapped = conn.execute("SELECT COUNT(*) FROM pb_affiliation WHERE ticker IS NOT NULL").fetchone()[0]
    dist = conn.execute("SELECT COUNT(DISTINCT ticker) FROM pb_affiliation WHERE ticker IS NOT NULL").fetchone()[0]
    print(f"mapped {mapped} affiliation rows ({exact} exact + {fuzzy} fuzzy) to {dist} distinct tickers")
    conn.close()

if __name__ == "__main__":
    run()
