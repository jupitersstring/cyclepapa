"""Map pb_affiliation.company -> ticker.

1. Our own universe: name match against ticker_meta / ticker_yf / 13F issuers
   (exact, then a guarded whole-word prefix match).
2. FMP's full profile list (~90k listings, the enrich step's cached bulk
   file): an EXACT normalised name match only — 90k names collide too easily
   for anything looser. This reaches the boards our funds don't hold:
   ArcelorMittal, Fortescue, Dollarama, Aston Martin, Siam Cement. Among a
   company's listings the one already in our data wins, then an exchange
   listing over OTC, then the largest.
3. A few brand names PitchBook uses in place of the listed name ("Snapchat").

ticker_src records which step mapped each row. Mapped tickers join the enrich
universe (enrich_fmp) so they carry valuations like every other name.
"""
import os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

_SUFFIX = re.compile(
    r"\b(INC|CORP|CORPORATION|LTD|LIMITED|PLC|LLC|LLP|LP|CO|COMPANY|GROUP|"
    r"HOLDINGS?|SA|AG|NV|SE|OYJ|ASA|AB|SPA|BHD|TBK|PJSC|PSC|PCL|PUBLIC|THE|"
    r"CLASS [A-C]|ADR|ADS)\b", re.I)

BRANDS = {"SNAPCHAT": "SNAP"}           # PitchBook's brand name -> listed ticker
_OTC = {"OTC", "PNK", "OTCQX", "OTCQB", "OTCMKTS", "OTC MARKETS", "GREY"}

def norm(s):
    s = (s or "").upper()
    s = re.sub(r"\([^)]*\)?$", "", s)         # drop trailing (possibly unclosed) paren tag
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    # "S A" / "N V" / "P L C" (from "S.A.", "N.V.") -> one token, so the suffix drops
    s = re.sub(r"\b([A-Z]) (?=[A-Z]\b)", r"\1", s)
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def compact(s):
    return norm(s).replace(" ", "")          # "INTER PARFUMS" == "INTERPARFUMS"

def build_index(conn):
    """{name: ticker} and {compact name: ticker}. When listings share a name
    the one funds hold wins, then the US line (ArcelorMittal -> MT, not
    MT.AS), then the first seen."""
    held = {r[0] for r in conn.execute("SELECT ticker FROM unified_signal WHERE sec_type = 'common'")}
    rank = lambda t: (t in held, "." not in t and "-R" not in t)
    idx, cidx = {}, {}
    def add(tk, nm):
        n = norm(nm)
        if n and len(n) >= 3 and (n not in idx or rank(tk) > rank(idx[n])):
            idx[n] = tk
        k = n.replace(" ", "")
        if k and len(k) >= 5 and (k not in cidx or rank(tk) > rank(cidx[k])):
            cidx[k] = tk
    for tk, nm in conn.execute("SELECT ticker, name FROM ticker_meta WHERE name IS NOT NULL"):
        add(tk, nm)
    for tk, nm in conn.execute("SELECT ticker, long_name FROM ticker_yf WHERE long_name IS NOT NULL"):
        add(tk, nm)
    for tk, iss in conn.execute("""SELECT ticker, issuer FROM fund_13f_holdings
        WHERE ticker IS NOT NULL AND issuer IS NOT NULL GROUP BY ticker"""):
        add(tk, iss)
    return idx, cidx

def fmp_index(known):
    """{compact name: best symbol} over FMP's profile list (cached; {} if absent)."""
    try:
        from enrich_fmp import load_profiles
        prof = load_profiles()
    except Exception as e:                   # offline / no key: step 2 is skipped, loudly
        print(f"  ! FMP profiles unavailable ({str(e)[:80]}): company-name step skipped")
        return {}
    def num(x):
        try:
            return float(x or 0)
        except ValueError:
            return 0.0
    groups = {}
    for sym, r in prof.items():
        if str(r.get("isEtf", "")).lower() == "true" or str(r.get("isFund", "")).lower() == "true":
            continue
        k = compact(r.get("companyName"))
        if k and len(k) >= 5:
            groups.setdefault(k, []).append(r)
    out = {}
    for k, rows in groups.items():
        live = [r for r in rows if str(r.get("isActivelyTrading", "")).lower() == "true"] or rows
        # London's international order book re-quotes foreign shares as 0XXX.L
        # (Banca Sistema 0R9H.L): the home listing is the one to value
        best = max(live, key=lambda r: (r["symbol"] in known,
                                         (r.get("exchange") or "").upper() not in _OTC,
                                         not re.match(r"^0[A-Z0-9]{3}\.L$", r["symbol"]),
                                         # Thai NVDR / foreign-board lines (SCC-R.BK) re-quote SCC.BK
                                         not re.search(r"-[RF]\.BK$", r["symbol"]),
                                         num(r.get("marketCap"))))
        out[k] = best["symbol"]
    return out

def run():
    conn = sqlite3.connect(DB)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pb_affiliation)")}
    if "ticker_src" not in cols:
        conn.execute("ALTER TABLE pb_affiliation ADD COLUMN ticker_src TEXT")
    conn.execute("UPDATE pb_affiliation SET ticker=NULL, ticker_src=NULL")   # idempotent re-map
    idx, cidx = build_index(conn)
    known = {r[0] for r in conn.execute("SELECT ticker FROM ticker_yf")}
    # longest keys first so a fuzzy contains-match prefers the most specific name
    keys_by_len = sorted(idx.keys(), key=len, reverse=True)
    fmp = None
    counts = {"exact": 0, "fuzzy": 0, "fmp-profile": 0, "brand": 0}
    rows = conn.execute("SELECT rowid, company, company_type FROM pb_affiliation").fetchall()
    for rowid, company, ctype in rows:
        n = norm(company)
        if not n:
            continue
        tk, src = idx.get(n) or cidx.get(n.replace(" ", "")), "exact"
        if not tk and len(n) >= 6:
            # fuzzy: one name is a whole-word prefix of the other. Require the
            # SHORTER (the shared stem) to be multi-word, so a generic single word
            # can't bridge two different firms — e.g. "Reliance" must not link
            # "Reliance Industries" (Ambani, India) to "Reliance, Inc." (US steel, RS).
            for k in keys_by_len:
                if n == k or n.startswith(k + " ") or k.startswith(n + " "):
                    stem = k if len(k) < len(n) else n
                    if " " in stem and abs(len(k) - len(n)) <= 12:
                        tk, src = idx[k], "fuzzy"
                        break
        if not tk and n.replace(" ", "") in BRANDS:
            tk, src = BRANDS[n.replace(" ", "")], "brand"
        if not tk and ctype == "Public Company":
            if fmp is None:
                fmp = fmp_index(known)
            tk, src = fmp.get(n.replace(" ", "")), "fmp-profile"
        if tk:
            counts[src] += 1
            conn.execute("UPDATE pb_affiliation SET ticker=?, ticker_src=? WHERE rowid=?", (tk, src, rowid))
    conn.commit()
    mapped = conn.execute("SELECT COUNT(*) FROM pb_affiliation WHERE ticker IS NOT NULL").fetchone()[0]
    dist = conn.execute("SELECT COUNT(DISTINCT ticker) FROM pb_affiliation WHERE ticker IS NOT NULL").fetchone()[0]
    left = conn.execute("""SELECT COUNT(DISTINCT company) FROM pb_affiliation WHERE ticker IS NULL
        AND company_type = 'Public Company'""").fetchone()[0]
    print(f"mapped {mapped} affiliation rows to {dist} distinct tickers "
          f"({', '.join(f'{k} {v}' for k, v in counts.items())}); {left} public companies still unmapped")
    conn.close()

if __name__ == "__main__":
    run()
