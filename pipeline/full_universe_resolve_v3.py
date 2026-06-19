"""Third-pass resolver: aggressive single-word search for stubborn names.

v2 still missed funds whose EDGAR-registered names don't match the
generic-stripped query (e.g. "Macellum Capital Management" but EDGAR
registered as "Macellum Advisors GP, LLC"). The fix: search for ONLY
the distinctive first word of the cleaned name. If that returns any 13F
filer whose display_name contains the distinctive token, accept it.

This produces a small but important set of recoveries for funds like
Kerrisdale, Bonhoeffer, Pabrai, Royce, Sequoia, MSD Partners.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_universe_resolve import clean, fund_overlap
from full_universe_resolve_v2 import has_13f_hr, search_efts_open

NOISE = {"LP","LLC","INC","CORP","LTD","PLC","COMPANY","CO","THE","AND","OF","SA","NV","AG",
         "CAPITAL","MANAGEMENT","PARTNERS","ASSOCIATES","ASSET","FUND","FUNDS",
         "INVESTMENT","INVESTMENTS","GROUP","ADVISORS","ADVISERS","ADVISORY",
         "GLOBAL","HOLDINGS","HOLDING","TRUST","SE","AB","BV","NA","NV"}

def distinctive_token(name):
    """Return the longest non-noise token of >=4 chars from name."""
    toks = [t for t in re.findall(r"[A-Za-z]{3,}", name) if t.upper() not in NOISE]
    if not toks: return None
    # Prefer the longest, but if first token is unique-looking, prefer it
    toks.sort(key=lambda t: (-len(t), toks.index(t)))
    return toks[0]

def search_for_token(tok):
    """Search 13F-HR with just one token. Return top 5 (cik, display_name, score)."""
    if not tok: return []
    url = f"https://efts.sec.gov/LATEST/search-index?q={tok}&forms=13F-HR&hits=10"
    body = subprocess.run(["curl", "-sk", "--compressed", "-m", "25", "-A", UA, url],
                          capture_output=True).stdout
    if not body: return []
    try:
        j = json.loads(body)
    except Exception:
        return []
    out, seen = [], set()
    TOK = tok.upper()
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
            # only keep if the distinctive token actually appears in the display name
            if TOK in nm.upper():
                out.append((c, nm, score))
    return out

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    NON_FILER_STATUSES = ('uk_non_filer','ca_non_filer','jp_non_filer','es_non_filer',
                          'fr_non_filer','au_non_filer','sg_non_filer','hk_non_filer',
                          'za_non_filer','de_non_filer','ch_non_filer','br_non_filer',
                          'individual','meta_rollup','private_office','skip_no_aum')
    placeholders = ",".join("?" * len(NON_FILER_STATUSES))
    pending = list(conn.execute(f"""
        SELECT fm.fund, fr.status FROM fund_meta fm
        LEFT JOIN fund_13f_state st ON st.fund = fm.fund
        LEFT JOIN fund_resolution_state fr ON fr.fund = fm.fund
        WHERE (st.n_holdings IS NULL OR st.n_holdings = 0)
          AND COALESCE(fr.status,'') NOT IN ({placeholders})
          AND fr.status IN ('no_match','no_match_v2','weak_match_only','efts_no_hits',
                            'v2_no_13f_history')
        ORDER BY fm.fund""", NON_FILER_STATUSES))
    print(f"V3 single-token-search resolving {len(pending)} stubborn funds\n")

    n_found = n_filer = 0
    for fr in pending:
        fund = fr["fund"]
        q = clean(fund)
        tok = distinctive_token(q)
        if not tok or len(tok) < 4:
            print(f"  - {fund[:40]:<40} no distinctive token")
            continue
        cands = search_for_token(tok)
        time.sleep(0.6)
        if not cands:
            print(f"  - {fund[:40]:<40} token='{tok}' no hits")
            continue
        # Re-score with overlap of full original query
        scored = [(c, l, s, fund_overlap(q, l)) for c, l, s in cands]
        scored.sort(key=lambda x: (x[3], x[2]), reverse=True)
        best_cik, best_lbl, best_s, best_ov = scored[0]
        if best_ov < 0.34:  # weaker for v3 since we're searching one token
            print(f"  ? {fund[:40]:<40} token='{tok}' best ov={best_ov} '{best_lbl[:30]}'")
            continue
        is_filer = has_13f_hr(best_cik)
        time.sleep(0.4)
        status = "v3_verified" if is_filer else "v3_no_13f_history"
        conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
            VALUES (?,?,?,?,?,date('now'))""",
            (fund, len(scored), best_cik, best_ov, status))
        for cik, lbl, s, ov in scored[:3]:
            conn.execute("""INSERT OR REPLACE INTO fund_cik_map
                VALUES (?,?,?,?,?,date('now'))""", (fund, cik, lbl, ov, 1))
        n_found += 1
        if is_filer:
            n_filer += 1
            conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
            print(f"  ✓ {fund[:40]:<40} tok='{tok}' CIK={best_cik:<8} ov={best_ov} {best_lbl[:25]}")
        else:
            print(f"  ? {fund[:40]:<40} tok='{tok}' CIK={best_cik:<8} (no 13F)")
        conn.commit()
    print(f"\nV3 done. {n_found} matched, {n_filer} verified 13F filers.")

if __name__ == "__main__":
    run()
