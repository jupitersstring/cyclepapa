"""Ingest researcher-extracted positions for funds that don't file 13F-HR.

For foreign funds (UK/EU/JP) and small US funds below the 13F threshold,
their top equity holdings come from quarterly letters / fund factsheets /
RNS announcements. This module ingests those into fund_positions with
section=5 (researcher_added) so they don't conflict with the original
XLSX-sourced sections (1-4).

Expected input CSV (one row per position):
  FUND_NAME|TICKER|COMPANY|PCT_OR_RANK|SOURCE_URL|CONFIDENCE_H_M_L

Where the fund_name must match (case-insensitive prefix) an entry in
fund_meta. Only H/M confidence rows are committed.
"""
import os, re, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
SECTION_RESEARCHER = 5

def match_fund(conn, name_in):
    """Find the canonical fund_meta name that matches the researcher's name."""
    if not name_in: return None
    n = name_in.strip()
    # exact match first
    r = conn.execute("SELECT fund FROM fund_meta WHERE LOWER(fund)=LOWER(?)", (n,)).fetchone()
    if r: return r[0]
    # prefix match (first 15 chars)
    prefix = n[:15]
    r = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ? LIMIT 1",
                     (prefix + "%",)).fetchone()
    if r: return r[0]
    # any-position contains
    for word in n.split():
        if len(word) < 5: continue
        r = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ? LIMIT 1",
                         ("%" + word + "%",)).fetchone()
        if r: return r[0]
    return None

def ingest_csv(text):
    conn = sqlite3.connect(DB)
    n_ingested = n_skipped = 0
    snap = "2026-06-20"  # session date
    seen_funds = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = line.split("|")
        if len(parts) < 4: continue
        fund_in = parts[0].strip()
        ticker  = parts[1].strip()
        company = parts[2].strip() if len(parts) > 2 else ""
        rank    = parts[3].strip() if len(parts) > 3 else ""
        src     = parts[4].strip() if len(parts) > 4 else ""
        conf    = parts[5].strip().upper() if len(parts) > 5 else "M"

        # skip NO_DATA / low-confidence / no ticker
        if ticker in ("NO_DATA", "", "0", "?", "-"): n_skipped += 1; continue
        if conf == "L": n_skipped += 1; continue
        if not re.match(r'^[A-Z0-9.\-]{1,12}$', ticker): n_skipped += 1; continue

        fund = match_fund(conn, fund_in)
        if not fund:
            print(f"  ? no fund_meta match for '{fund_in}' (ticker={ticker})")
            n_skipped += 1
            continue
        seen_funds.add(fund)
        # parse rank as integer if possible
        try:
            rank_int = int(re.search(r'\d+', rank).group()) if re.search(r'\d+', rank) else None
        except: rank_int = None
        # parse % if rank contains %
        pct = None
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', rank)
        if m: pct = float(m.group(1))

        raw_text = f"[{conf}] {fund_in} | {ticker} | {company} | rank={rank} | {src}"
        conn.execute("""INSERT INTO fund_positions
            (fund, ticker, company, section, pct_value, pct_kind, dollar_m, change_text,
             event_date, raw_text, asof) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (fund, ticker, company[:60] or None, SECTION_RESEARCHER, pct,
             "book" if pct else None, None,
             f"researcher_seed_{conf}", None, raw_text[:300], snap))
        n_ingested += 1
    conn.commit()
    print(f"\ningested {n_ingested} positions across {len(seen_funds)} funds")
    print(f"skipped {n_skipped} rows (NO_DATA / low-conf / unparseable)")
    return seen_funds

if __name__ == "__main__":
    text = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1]).read()
    ingest_csv(text)
