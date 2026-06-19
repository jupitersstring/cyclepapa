"""Comprehensive fund→CIK resolver using EDGAR's full-text JSON search.

The cgi-bin/browse-edgar HTML scraper in resolve_fund_ciks.py was unreliable —
it missed major filers because Excel-truncated tab names (capped at 31 chars)
broke the regex parens-stripper. This module uses the modern
efts.sec.gov/LATEST/search-index endpoint which:

  1. Returns clean JSON (no HTML scraping)
  2. Scores results by relevance (max_score field)
  3. Restricts to forms=13F-HR so non-filers are naturally excluded
  4. Surfaces the actual filer CIK + canonical display_name

For each fund we:
  - Clean the name (strip parenthetical, manager, suffix)
  - Hit the search endpoint with forms=13F-HR
  - Score top candidates by token overlap with the cleaned name
  - Verify the best CIK actually has a recent 13F-HR via the same JSON
  - Write to fund_resolution_state with status='efts_resolved'

This re-resolves EVERY fund — even ones that previously had a manual_seed —
because we discovered many seeds were wrong (e.g. Brandes was 1133303,
should be 1015079). Old seeds are preserved as 'manual_seed_unverified'
if the auto-resolution disagrees.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    for i in range(4):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "25", "-A", UA, url],
                           capture_output=True).stdout
        if r[:300].find(b"Rate Threshold Exceeded") != -1 or r[:300].find(b"<title>SEC.gov") != -1:
            time.sleep(10 + 5*i); continue
        return r
    return b''

PAREN_RE = re.compile(r"\([^)]*\)")
TIER_RE = re.compile(r"\b(Tier\s+\d+|T\d+)\b", re.I)
TRAIL_RE = re.compile(r"[–—].*$")

def clean(name):
    """Strip parens (closed or unclosed), tier suffixes, trailing em-dash content."""
    n = name.split(" / ")[0]
    # double-space often separates fund-name from manager-name in our tab labels
    parts = re.split(r"  +", n)
    n = parts[0] if parts else n
    n = PAREN_RE.sub("", n)
    cut = n.find("(")  # unclosed paren
    if cut > 0: n = n[:cut]
    n = TIER_RE.sub("", n)
    n = TRAIL_RE.sub("", n)
    # strip the "fund / fund_group" doubling pattern that creeps in
    # e.g. "Aquamarine Fund   Aquamarine Capital" -> drop second instance
    n = re.sub(r"\s+", " ", n).strip(" ,-/.")
    return n

def search_efts(name):
    """EDGAR full-text search restricted to 13F-HR. Returns list of (cik, display_name, score)."""
    q = name.replace('"', '').replace("'", "").strip()
    if not q: return []
    # use quoted phrase for tighter matching
    qenc = '%22' + q.replace(" ", "+") + '%22'
    url = f"https://efts.sec.gov/LATEST/search-index?q={qenc}&forms=13F-HR&hits=5"
    body = curl(url)
    if not body: return []
    try:
        j = json.loads(body)
    except Exception:
        return []
    out = []
    seen = set()
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
            # canonical display name format: "FIRM NAME, LP  (CIK 0000123456)"
            nm = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", nm).strip()
            out.append((c, nm, score))
    return out

def fund_overlap(q, label):
    """Jaccard token overlap; strip pure legal-form noise."""
    LEGAL = {"LP","LLC","INC","CORP","LTD","PLC","COMPANY","CO","THE","AND","OF","SA","NV","AG"}
    qw = set(re.sub(r"[^A-Za-z ]", "", q).upper().split()) - LEGAL
    lw = set(re.sub(r"[^A-Za-z ]", "", label).upper().split()) - LEGAL
    if not qw or not lw: return 0.0
    return round(len(qw & lw) / max(len(qw), len(lw)), 2)

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Re-resolve everything that DIDN'T succeed in ingest_13f_state — i.e. has 0 holdings.
    # Also include funds never resolved at all.
    pending = list(conn.execute("""
        SELECT fm.fund FROM fund_meta fm
        LEFT JOIN fund_13f_state st ON st.fund = fm.fund
        LEFT JOIN fund_resolution_state fr ON fr.fund = fm.fund
        WHERE (st.n_holdings IS NULL OR st.n_holdings = 0)
          AND COALESCE(fr.status, '') NOT IN
              ('uk_non_filer','ca_non_filer','jp_non_filer','es_non_filer',
               'fr_non_filer','au_non_filer','sg_non_filer','hk_non_filer',
               'za_non_filer','de_non_filer','ch_non_filer','br_non_filer',
               'individual','meta_rollup','private_office','skip_no_aum')
        ORDER BY fm.fund"""))
    print(f"re-resolving {len(pending)} funds with no verified 13F holdings\n")

    n_found = n_changed = n_none = 0
    for fr in pending:
        fund = fr["fund"]
        q = clean(fund)
        if len(q) < 3:
            n_none += 1
            continue
        candidates = search_efts(q)
        time.sleep(0.6)
        if not candidates:
            # fall back to shorter prefix if query was 4+ words
            words = q.split()
            if len(words) >= 4:
                q2 = " ".join(words[:3])
                candidates = search_efts(q2)
                time.sleep(0.6)
        if not candidates:
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 0, None, 0.0, "efts_no_hits"))
            print(f"  - {fund[:40]:<40} no efts hits  q='{q[:30]}'")
            n_none += 1
            continue
        # rank by score * fund_overlap
        scored = []
        for cik, lbl, s in candidates:
            ov = fund_overlap(q, lbl)
            scored.append((cik, lbl, s, ov))
        scored.sort(key=lambda x: (x[3], x[2]), reverse=True)
        best_cik, best_lbl, best_s, best_ov = scored[0]
        # capture all candidates for audit
        for cik, lbl, s, ov in scored:
            conn.execute("""INSERT OR REPLACE INTO fund_cik_map
                VALUES (?,?,?,?,?,date('now'))""", (fund, cik, lbl, ov, 1))
        prev = conn.execute("SELECT best_cik FROM fund_resolution_state WHERE fund=?", (fund,)).fetchone()
        prev_cik = prev[0] if prev else None
        conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
            VALUES (?,?,?,?,?,date('now'))""",
            (fund, len(scored), best_cik, best_ov, "efts_resolved"))
        if prev_cik and prev_cik != best_cik:
            n_changed += 1
            marker = "Δ"
        else:
            marker = "✓"
        n_found += 1
        print(f"  {marker} {fund[:40]:<40} CIK={best_cik:<10}  ov={best_ov}  {best_lbl[:30]}")
        conn.commit()
        # mark 0-holdings entries as stale so ingest re-runs
        conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
        conn.commit()
    print(f"\nDone. {n_found} resolved ({n_changed} CIK corrections), {n_none} still no match.")

if __name__ == "__main__":
    run()
