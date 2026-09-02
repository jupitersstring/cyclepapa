"""Latent-ownership archaeology + entity alias graph, from 13D/G filing text.

A 4.9% disclosed stake can hide a much larger economic relationship:
pre-funded warrants, convertible preferred, 9.99% blockers (with the
contractual right to raise them), board designation rights, registration
rights, anti-dilution — Item 6 of a 13D and the cover notes of PIPE 13Gs
spell these out in words even when the header percentage looks small.

One fetch per filing also yields, from the SEC-HEADER "FILED BY" blocks,
every co-filing group entity (Elliott Associates + Elliott International +
managers) → entity_alias, the identity layer cross-jurisdiction feeds can
join onto later.

Tables:
  latent_ownership(ticker, holder, accession, filed, form, flags,
                   blocker_pct, swap_counterparties, n_features)
  entity_alias(entity, canonical_holder, accession)
"""
import os, re, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB

FEATURES = [
    ("prefunded_warrant", r"PRE[- ]FUNDED WARRANT"),
    ("warrant",           r"\bWARRANTS?\b"),
    ("convertible",       r"CONVERTIBLE (?:PROMISSORY )?(?:NOTE|PREFERRED|DEBENTURE|SECURIT)"),
    ("blocker",           r"BENEFICIAL OWNERSHIP (?:LIMITATION|BLOCKER)|OWNERSHIP LIMITATION|\bBLOCKER\b"),
    ("board_rights",      r"RIGHT TO (?:DESIGNATE|NOMINATE|APPOINT)|BOARD DESIGNEE|DIRECTOR DESIGNEE|NOMINATION AGREEMENT"),
    ("registration",      r"REGISTRATION RIGHTS"),
    ("rofr",              r"RIGHT OF FIRST (?:REFUSAL|OFFER)"),
    ("anti_dilution",     r"ANTI[- ]DILUTION"),
    ("standstill",        r"\bSTANDSTILL\b"),
    ("swap",              r"TOTAL RETURN SWAP|CASH[- ]SETTLED SWAP|CASH[- ]SETTLED (?:TOTAL RETURN )?EQUITY"),
]
BLOCKER_PCT = re.compile(r"(4\.9{1,2}|9\.9{1,2}|14\.9{1,2}|19\.9{1,2})\s*%")
BANKS = ["UBS", "GOLDMAN", "MORGAN STANLEY", "JPMORGAN", "J.P. MORGAN", "BARCLAYS",
         "CITIBANK", "CITIGROUP", "BANK OF AMERICA", "MERRILL", "DEUTSCHE",
         "SOCIETE GENERALE", "BNP", "NOMURA", "JEFFERIES", "MACQUARIE", "RBC",
         "SCOTIA", "MIZUHO", "CREDIT SUISSE"]
FILED_BY = re.compile(r"FILED BY:\s*\n\s*COMPANY DATA:\s*\n\s*COMPANY CONFORMED NAME:\s*(.+)")

def doc_text(cik, acc):
    accn = acc.replace("-", "")
    body = m.curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{acc}.txt")
    if not body:
        return ""
    return body[:900_000].decode("utf-8", "ignore")

def run(lookback_months=24):
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS latent_ownership (
      ticker TEXT, holder TEXT, accession TEXT PRIMARY KEY, filed TEXT, form TEXT,
      flags TEXT, blocker_pct REAL, swap_counterparties TEXT, n_features INTEGER);
    CREATE INDEX IF NOT EXISTS idx_latent_tk ON latent_ownership(ticker);
    CREATE TABLE IF NOT EXISTS entity_alias (
      entity TEXT, canonical_holder TEXT, accession TEXT,
      PRIMARY KEY (entity, canonical_holder));
    """)
    # newest filing per (holder, ticker): 13Ds always; 13Gs only for universe names
    rows = conn.execute(f"""
        WITH ranked AS (
          SELECT holder, holder_cik, subject_ticker tk, accession, filed, form,
                 ROW_NUMBER() OVER (PARTITION BY holder, subject_ticker
                                    ORDER BY filed DESC) rn
          FROM holder_13d
          WHERE filed >= date('now','-{lookback_months} months')
            AND subject_ticker IS NOT NULL AND holder_cik IS NOT NULL)
        SELECT holder, holder_cik, tk, accession, filed, form FROM ranked
        WHERE rn = 1 AND (form LIKE '%13D%' OR tk IN (SELECT ticker FROM unified_signal WHERE score > 10))
        """).fetchall()
    print(f"latent-ownership pass: {len(rows)} filings to read", flush=True)
    n_feat = n_done = 0
    for i, (holder, hcik, tk, acc, filed, form) in enumerate(rows):
        if conn.execute("SELECT 1 FROM latent_ownership WHERE accession=?", (acc,)).fetchone():
            continue
        text = doc_text(hcik, acc)
        if not text:
            conn.execute("""INSERT OR IGNORE INTO latent_ownership
                VALUES (?,?,?,?,?,NULL,NULL,NULL,0)""", (tk, holder, acc, filed, form))
            continue
        up = text.upper()
        flags = [name for name, pat in FEATURES if re.search(pat, up)]
        bl = BLOCKER_PCT.search(up)
        blocker = float(bl.group(1)) if bl and ("blocker" in flags or "LIMITATION" in up) else None
        swaps = None
        if "swap" in flags:
            hit = [b for b in BANKS if b in up]
            swaps = ",".join(hit[:4]) or "unnamed"
        members = FILED_BY.findall(text)
        for ent in {e.strip() for e in members if e.strip()}:
            conn.execute("INSERT OR IGNORE INTO entity_alias VALUES (?,?,?)",
                         (ent[:80], holder, acc))
        conn.execute("INSERT OR REPLACE INTO latent_ownership VALUES (?,?,?,?,?,?,?,?,?)",
                     (tk, holder, acc, filed, form,
                      ",".join(flags) or None, blocker, swaps, len(flags)))
        n_done += 1
        n_feat += bool(flags)
        if i % 50 == 0:
            conn.commit()
            print(f"  ...{i}/{len(rows)} ({n_feat} with features)", flush=True)
        time.sleep(0.3)
    conn.commit()
    tot = conn.execute("SELECT COUNT(*), SUM(n_features>0) FROM latent_ownership").fetchone()
    ali = conn.execute("SELECT COUNT(*) FROM entity_alias").fetchone()[0]
    print(f"DONE: {tot[0]} filings read, {tot[1]} with latent features; {ali} alias entities", flush=True)
    print("\nrichest latent structures (features >= 4):")
    for r in conn.execute("""SELECT ticker, holder, flags, blocker_pct, swap_counterparties
        FROM latent_ownership WHERE n_features >= 4 ORDER BY n_features DESC LIMIT 20"""):
        print(f"  {r[0]:6s} {r[1][:28]:30s} {r[2][:60]}  blocker={r[3]}  swap={r[4]}")
    conn.close()

if __name__ == "__main__":
    run()
