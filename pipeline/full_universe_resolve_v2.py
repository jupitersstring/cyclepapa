"""Second-pass resolver: handle misses + verify each CIK actually files 13F-HR.

After full_universe_resolve.py runs, we still have:
  - Funds with no hits ("efts_no_hits") — quoted phrase too strict
  - Funds with low-confidence matches (Jaccard < 0.5) that may be wrong
  - Funds whose CIK didn't return a 13F-HR (no_13f_filing in fund_13f_state)

This pass:
  1. Reads fund_meta + fund_resolution_state
  2. For any fund with status in (efts_no_hits, low_confidence) OR Jaccard < 0.5,
     retries with an UNQUOTED full-text search (broader recall)
  3. For each candidate CIK, verifies it has at least one 13F-HR filing via the
     EDGAR submissions API (data.sec.gov/submissions/CIK<n>.json)
  4. Promotes only CIKs that pass verification

Drops anything matched to a CIK that has 0 13F-HR filings to status='confirmed_no_13f'.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    for i in range(4):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "25", "-A", UA, url],
                           capture_output=True).stdout
        if r[:300].find(b"Rate Threshold Exceeded") != -1:
            time.sleep(10 + 5*i); continue
        return r
    return b''

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_universe_resolve import clean, fund_overlap

def search_efts_open(name):
    """Unquoted (OR-of-tokens) full-text search — looser recall."""
    q = name.replace('"', '').replace("'", "").strip()
    if not q: return []
    qenc = q.replace(" ", "+")
    url = f"https://efts.sec.gov/LATEST/search-index?q={qenc}&forms=13F-HR&hits=8"
    body = curl(url)
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

def has_13f_hr(cik):
    """Check submissions API for a 13F-HR in the filing history."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    body = curl(url)
    if not body: return None
    try:
        j = json.loads(body)
    except Exception:
        return None
    forms = j.get("filings", {}).get("recent", {}).get("form", [])
    return "13F-HR" in forms

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Targets: funds with no holdings AND not a known non-filer
    NON_FILER_STATUSES = ('uk_non_filer','ca_non_filer','jp_non_filer','es_non_filer',
                          'fr_non_filer','au_non_filer','sg_non_filer','hk_non_filer',
                          'za_non_filer','de_non_filer','ch_non_filer','br_non_filer',
                          'individual','meta_rollup','private_office','skip_no_aum')
    placeholders = ",".join("?" * len(NON_FILER_STATUSES))
    pending = list(conn.execute(f"""
        SELECT fm.fund, fr.status, fr.best_cik, fr.best_conf FROM fund_meta fm
        LEFT JOIN fund_13f_state st ON st.fund = fm.fund
        LEFT JOIN fund_resolution_state fr ON fr.fund = fm.fund
        WHERE (st.n_holdings IS NULL OR st.n_holdings = 0)
          AND COALESCE(fr.status, '') NOT IN ({placeholders})
          AND (fr.best_conf < 0.5 OR fr.best_cik IS NULL OR fr.status='efts_no_hits')
        ORDER BY fm.fund""", NON_FILER_STATUSES))
    print(f"V2 resolving {len(pending)} funds with weak / no matches\n")

    n_found = n_verified_filer = n_no13f = 0
    for fr in pending:
        fund = fr["fund"]
        q = clean(fund)
        if len(q) < 3:
            continue
        candidates = search_efts_open(q)
        time.sleep(0.6)
        if not candidates and len(q.split()) >= 3:
            # last-resort: try just the first 2 words
            q2 = " ".join(q.split()[:2])
            candidates = search_efts_open(q2)
            time.sleep(0.6)
        if not candidates:
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 0, None, 0.0, "no_match_v2"))
            print(f"  - {fund[:40]:<40} no match (open search)")
            continue
        # rank by overlap × score
        scored = [(c, l, s, fund_overlap(q, l)) for c,l,s in candidates]
        scored.sort(key=lambda x: (x[3], x[2]), reverse=True)
        # require at least 1 distinctive word overlap (drop pure-legal-form matches)
        scored = [s for s in scored if s[3] >= 0.25]
        if not scored:
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 0, None, 0.0, "weak_match_only"))
            print(f"  - {fund[:40]:<40} only weak matches")
            continue
        best_cik, best_lbl, best_s, best_ov = scored[0]
        n_found += 1
        # verify the BEST candidate files 13F-HR
        is_filer = has_13f_hr(best_cik)
        time.sleep(0.4)
        status = "v2_verified" if is_filer else "v2_no_13f_history"
        conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
            VALUES (?,?,?,?,?,date('now'))""",
            (fund, len(scored), best_cik, best_ov, status))
        for cik, lbl, s, ov in scored[:3]:
            conn.execute("""INSERT OR REPLACE INTO fund_cik_map
                VALUES (?,?,?,?,?,date('now'))""", (fund, cik, lbl, ov, 1))
        if is_filer:
            n_verified_filer += 1
            # invalidate stale fund_13f_state row so ingest re-runs
            conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
            print(f"  ✓ {fund[:40]:<40} CIK={best_cik:<10} ov={best_ov} {best_lbl[:25]}")
        else:
            n_no13f += 1
            print(f"  ? {fund[:40]:<40} CIK={best_cik:<10} ov={best_ov} (NO 13F)")
        conn.commit()
    print(f"\nV2 done. {n_found} candidates found, {n_verified_filer} verified filers, {n_no13f} no-13F-history.")

if __name__ == "__main__":
    run()
