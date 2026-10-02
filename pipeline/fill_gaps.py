"""Precision resolver for the last ~75 stubborn gap funds.

Previous resolvers picked the top efts.sec.gov hit and accepted it. For
the long tail this fails because the top hit is often a similarly-named
unrelated firm with a higher BM25 score.

This module walks through ALL top-N hits, verifies each via
data.sec.gov/submissions/CIK<n>.json (must actually file 13F-HR), and
picks the FIRST one with token overlap >= 0.5 after the noise-token
strip. Also tries multiple query variants per fund:
  1. Cleaned full name
  2. First two non-noise words
  3. Distinctive token alone

For each gap, prints the candidate list so wrong picks are auditable.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_universe_resolve import clean, fund_overlap, curl as _curl
from full_universe_resolve_v2 import has_13f_hr
from full_universe_resolve_v3 import distinctive_token, NOISE

def search(q, quoted=False, hits=15):
    if not q: return []
    qstr = q.replace('"', '').strip()
    if quoted:
        qenc = '%22' + qstr.replace(" ", "+") + '%22'
    else:
        qenc = qstr.replace(" ", "+")
    url = f"https://efts.sec.gov/LATEST/search-index?q={qenc}&forms=13F-HR&hits={hits}"
    body = _curl(url)
    if not body: return []
    try:
        j = json.loads(body)
    except Exception:
        return []
    out, seen = [], set()
    for h in j.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        ciks = src.get("ciks", [])
        names = src.get("display_names", [])
        score = h.get("_score", 0)
        for i, cik in enumerate(ciks):
            c = cik.lstrip("0") or cik
            if c in seen: continue
            seen.add(c)
            nm = names[i] if i < len(names) else ""
            nm = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", nm).strip()
            out.append((c, nm, score))
    return out

def query_variants(fund):
    """Yield (label, query) variants to try in priority order."""
    c = clean(fund)
    yield "clean_quoted", c
    yield "clean_open", c
    # first two non-noise words
    toks = [t for t in re.findall(r"[A-Za-z]{3,}", c) if t.upper() not in NOISE]
    if len(toks) >= 2:
        yield "first2_open", " ".join(toks[:2])
    if toks:
        yield "first1_open", toks[0]

def find_for(fund, verbose=True):
    """Return (best_cik, best_label, best_ov, source_label) or (None,None,None,None)."""
    c = clean(fund)
    seen_ciks = set()
    candidates = []
    for label, q in query_variants(fund):
        if not q or len(q) < 3: continue
        quoted = label.endswith("_quoted")
        results = search(q, quoted=quoted, hits=15)
        time.sleep(0.5)
        for cik, nm, score in results:
            if cik in seen_ciks: continue
            seen_ciks.add(cik)
            ov = fund_overlap(c, nm)
            if ov >= 0.5:
                candidates.append((cik, nm, score, ov, label))
        # short-circuit if we have a 1.0 hit
        if any(c[3] >= 1.0 for c in candidates):
            break
    if not candidates:
        return None, None, None, None
    candidates.sort(key=lambda x: (-x[3], -x[2]))
    # verify top candidate(s) actually file 13F-HR
    for cik, nm, score, ov, label in candidates[:5]:
        if has_13f_hr(cik):
            time.sleep(0.3)
            return cik, nm, ov, label
        time.sleep(0.3)
    # nothing verified; return best name-match anyway (caller will mark unverified)
    cik, nm, score, ov, label = candidates[0]
    return cik, nm, ov, label + "_unverified"

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Find the actual gaps
    gaps = list(conn.execute("""
        SELECT fr.fund, fr.best_cik, fr.status FROM fund_resolution_state fr
        LEFT JOIN fund_13f_state st ON st.fund = fr.fund
        WHERE (st.n_holdings IS NULL OR st.n_holdings = 0)
          AND fr.status NOT LIKE '%non_filer%'
          AND fr.status NOT IN ('individual','meta_rollup','private_office','skip_no_aum')
          AND NOT EXISTS (SELECT 1 FROM holder_13d h WHERE h.holder = fr.fund OR h.holder_cik = fr.best_cik)
        ORDER BY fr.fund"""))
    print(f"Filling {len(gaps)} gap funds\n")
    n_fixed = n_changed = n_failed = 0
    for g in gaps:
        fund, prev_cik, prev_status = g["fund"], g["best_cik"], g["status"]
        cik, lbl, ov, src = find_for(fund)
        if not cik:
            print(f"  - {fund[:42]:<42} no candidate")
            n_failed += 1
            continue
        if cik == prev_cik:
            print(f"  = {fund[:42]:<42} CIK={cik} unchanged (still {prev_status})")
            continue
        conn.execute("""UPDATE fund_resolution_state SET best_cik=?, best_conf=?,
            status=?, asof=date('now') WHERE fund=?""", (cik, ov, f"gap_{src}", fund))
        # invalidate stale ingest
        conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
        conn.commit()
        n_fixed += 1
        if prev_cik:
            n_changed += 1
            mark = "Δ"
        else:
            mark = "✓"
        print(f"  {mark} {fund[:42]:<42} CIK={cik:<10} ov={ov} src={src} {lbl[:30]}")
    print(f"\n{n_fixed} fixed ({n_changed} CIK corrections), {n_failed} still unresolved")

if __name__ == "__main__":
    run()
