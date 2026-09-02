"""Clean fund_positions: dedupe + correct pct_value parse errors.

Two systematic errors were found in the researcher/XLSX-sourced positions:

1. DUPLICATES — the same (fund, ticker, section) ingested more than once.

2. pct_value held the position CHANGE ("+430%", "+132%") or an OWNERSHIP stake
   ("19.7% of co.") instead of the portfolio WEIGHT. A position can't be 430%
   of a book; these polluted the concentration measure (e.g. pB Max).

This re-parses pct_value from the stored raw_text:
  - the "+N%" change goes to change_text (not the weight),
  - an "N% of company/shares" ownership figure is re-kinded to 'company',
  - the true book weight is recovered from a labeled "N% portfolio/book/NAV"
    token or a bare small % alongside the change; if none is recoverable the
    bogus value is nulled (shown as "—") rather than left wrong.

Good rows (a sensible bare weight already) are left untouched.
"""
import os, re, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def _num(x):
    """Regex matching the value x in text regardless of trailing-zero formatting
    (so 19.7 also matches '19.70')."""
    if x == int(x):
        return re.escape(str(int(x))) + r'(?:\.0+)?'
    s = f"{x:.4f}".rstrip("0")
    return re.escape(s) + r'0*'

def reparse(pv, kind, raw):
    """Return (new_pv, new_kind, change_text) or None if the row looks fine."""
    if pv is None or pv <= 0 or not raw:
        return None
    change = None
    mc = re.search(r'\(?\+\s*(\d+(?:\.\d+)?)\s*%', raw)
    if mc:
        change = f"+{mc.group(1)}%"
    # is the stored pv actually the change figure?
    is_change = pv > 100 or bool(re.search(r'\+\s*' + _num(pv) + r'\s*%', raw))
    # is the stored pv an ownership ("% of company/shares/class") figure?
    is_ownco = bool(re.search(_num(pv) + r'\s*%\s*(?:of\s+)?(?:co\b|company|the company|shares|class|outstanding)', raw, re.I))
    if not is_change and not is_ownco:
        return None  # looks like a real weight — leave it

    # try to recover the true book/portfolio weight
    weight = None
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:portfolio|book|nav|aum|fund\b)', raw, re.I)
    if not m:
        m = re.search(r'(?:portfolio|book|weight)[^0-9%]{0,15}(\d+(?:\.\d+)?)\s*%', raw, re.I)
    if m and 0 < float(m.group(1)) <= 100:
        weight = float(m.group(1))
    else:
        # bare % tokens not prefixed with '+' and not an "of co/shares" figure
        cands = []
        for mm in re.finditer(r'(\d+(?:\.\d+)?)\s*%', raw):
            val = float(mm.group(1))
            pre = raw[max(0, mm.start() - 1):mm.start()]
            post = raw[mm.end():mm.end() + 14].lower()
            if pre == "+":            # a change figure
                continue
            if val > 40:              # implausible single-name book weight here
                continue
            if re.match(r'\s*of\s+(co|company|the|shares|class|outstand)', post):
                continue
            cands.append(val)
        if cands:
            weight = min(cands)       # the weight is the small one, not the change

    if weight is not None:
        return (round(weight, 2), "book", change)
    if is_ownco and not is_change:
        return (pv, "company", change)   # keep value, fix the kind
    return (None, None, change)          # null the bogus weight

def run(apply=True):
    conn = sqlite3.connect(DB)
    # 1) dedupe (keep lowest id per fund+ticker+section)
    dups = conn.execute("""SELECT COALESCE(SUM(n-1),0) FROM
        (SELECT COUNT(*) n FROM fund_positions WHERE ticker IS NOT NULL
         GROUP BY fund, ticker, section HAVING n>1)""").fetchone()[0]
    if apply:
        conn.execute("""DELETE FROM fund_positions WHERE id NOT IN (
            SELECT MIN(id) FROM fund_positions GROUP BY fund, ticker, section, COALESCE(raw_text,''))""")
    # 2) re-parse pct_value
    rows = conn.execute("SELECT id, pct_value, pct_kind, raw_text FROM fund_positions").fetchall()
    n_fix = n_null = n_kind = 0
    for rid, pv, kind, raw in rows:
        res = reparse(pv, kind, raw)
        if res is None:
            continue
        new_pv, new_kind, change = res
        if new_pv is None:
            n_null += 1
        elif new_kind == "company":
            n_kind += 1
        else:
            n_fix += 1
        if apply:
            conn.execute("""UPDATE fund_positions
                SET pct_value=?, pct_kind=?, change_text=COALESCE(change_text, ?)
                WHERE id=?""", (new_pv, new_kind, change, rid))
    if apply:
        conn.commit()
    print(f"deduped {dups} duplicate rows")
    print(f"re-parsed pct_value: {n_fix} weights recovered, {n_kind} re-kinded to company, {n_null} bogus nulled")

if __name__ == "__main__":
    import sys
    run(apply="--dry" not in sys.argv)
