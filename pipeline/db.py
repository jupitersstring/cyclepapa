"""cyclepapa data store — typed SQLite, single source of truth.

Replaces string-fused CSV. Invariants enforced in validate.py.
Usage: python3 pipeline/db.py init|migrate
"""
import csv, os, re, sqlite3, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "cyclepapa.db")
CSV = os.path.join(REPO, "data", "master_candidates.csv")

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  currency TEXT NOT NULL DEFAULT 'USD',
  price REAL,
  price_asof TEXT,
  mcap_m REAL,                 -- $M, same currency as price
  shares_out_m REAL,           -- derived = mcap_m/price unless sourced
  shares_method TEXT,          -- 'sourced' | 'derived'
  tier TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  known_issues TEXT,
  kill_criteria TEXT,
  factor_tags TEXT,
  source_url TEXT NOT NULL DEFAULT '',
  CHECK (price IS NULL OR price_asof IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  signal_type TEXT NOT NULL,   -- FORM4_BUY|FORM4_SELL|13D|13G|FUND_ADD|BUYBACK|BID|SALE_PROCESS|FAMILY
  actor TEXT NOT NULL,
  pct_of_company REAL CHECK (pct_of_company IS NULL OR pct_of_company BETWEEN 0 AND 100),
  pct_of_book REAL CHECK (pct_of_book IS NULL OR pct_of_book BETWEEN 0 AND 100),
  amount_usd_m REAL,
  cost_basis REAL,
  event_date TEXT,
  asof TEXT NOT NULL,
  source_url TEXT NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS catalysts (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  description TEXT NOT NULL,
  expected_date TEXT,          -- NULL = unscheduled
  status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|HAPPENED|EXPIRED_CHECK|DEAD
  outcome TEXT,
  source_url TEXT
);
CREATE TABLE IF NOT EXISTS prices (
  ticker TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, volume REAL,
  PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS liquidity (
  ticker TEXT PRIMARY KEY,
  adv_shares REAL, adv_usd_m REAL, asof TEXT NOT NULL,
  days_to_exit_1pct_adv10 REAL  -- days to exit a position = 1% of mcap at 10% of ADV
);
CREATE TABLE IF NOT EXISTS edgar_filings (
  accession TEXT PRIMARY KEY,
  ticker TEXT, cik TEXT NOT NULL, form TEXT NOT NULL, filed TEXT NOT NULL,
  primary_doc TEXT, url TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS form4_transactions (
  id INTEGER PRIMARY KEY,
  accession TEXT NOT NULL, ticker TEXT, owner TEXT, role TEXT,
  trans_date TEXT, code TEXT, shares REAL, price REAL, acquired INTEGER,
  source_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archetype_members (
  archetype TEXT NOT NULL, ticker TEXT NOT NULL,
  thesis TEXT, valuation TEXT, catalyst TEXT, variant TEXT, smart_money TEXT,
  PRIMARY KEY (archetype, ticker)
);
CREATE TABLE IF NOT EXISTS backtest_events (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL, bucket TEXT NOT NULL, event_date TEXT NOT NULL,
  description TEXT NOT NULL, source_note TEXT
);
CREATE TABLE IF NOT EXISTS backtest_results (
  event_id INTEGER PRIMARY KEY,
  entry_date TEXT, entry_px REAL,
  ret_6m REAL, ret_12m REAL, ret_18m REAL,
  spy_6m REAL, spy_12m REAL, spy_18m REAL,
  excess_6m REAL, excess_12m REAL, excess_18m REAL
);
-- Aging computed at query time, never stored (eng fix #4)
CREATE VIEW IF NOT EXISTS v_catalysts_live AS
SELECT c.*, CAST(julianday(c.expected_date) - julianday('now') AS INTEGER) AS days_remaining,
  CASE WHEN c.status='PENDING' AND c.expected_date IS NOT NULL
            AND julianday(c.expected_date) < julianday('now')
       THEN 'EXPIRED_CHECK' ELSE c.status END AS effective_status
FROM catalysts c;
CREATE VIEW IF NOT EXISTS v_tier1 AS
SELECT cd.ticker, cd.name, cd.price, cd.price_asof, cd.mcap_m, cd.tier,
       cd.verification_status, l.adv_usd_m, l.days_to_exit_1pct_adv10,
       (SELECT MIN(days_remaining) FROM v_catalysts_live v
         WHERE v.ticker=cd.ticker AND v.effective_status='PENDING') AS next_catalyst_days
FROM candidates cd LEFT JOIN liquidity l ON l.ticker=cd.ticker
WHERE cd.tier LIKE '1%';
"""

MONEY = re.compile(r'([C€$]*)\$?([\d,.]+)\s*([MBK]?)')

def parse_money_m(s):
    """'$859M'->859.0  '$4.48B'->4480  'C$908M'->(908,'CAD')  returns (value_m, currency) or (None,None)"""
    if not s or not isinstance(s, str): return None, None
    s = s.strip()
    cur = 'USD'
    if s.startswith('C$'): cur = 'CAD'
    elif s.startswith('€'): cur = 'EUR'
    m = re.search(r'([\d,]+\.?\d*)\s*([MBK]?)', s.replace('C$', '').replace('€', '').replace('$', ''))
    if not m: return None, cur
    v = float(m.group(1).replace(',', ''))
    mult = {'B': 1000.0, 'M': 1.0, 'K': 0.001, '': 1.0}[m.group(2)]
    return v * mult, cur

def parse_price(s):
    if not s or not isinstance(s, str): return None, 'USD'
    cur = 'CAD' if s.startswith('C$') else ('EUR' if s.startswith('€') else 'USD')
    m = re.search(r'([\d,]+\.?\d*)', s)
    return (float(m.group(1).replace(',', '')) if m else None), cur

def init(conn):
    conn.executescript(SCHEMA)

def migrate(conn):
    """One-time: master_candidates.csv -> typed tables."""
    with open(CSV) as f:
        rows = list(csv.DictReader(f))
    n = 0
    for r in rows:
        t = r['ticker'].strip()
        price, cur_p = parse_price(r.get('price', ''))
        mcap, cur_m = parse_money_m(r.get('mcap', ''))
        cur = cur_p if cur_p != 'USD' else cur_m or 'USD'
        shares = round(mcap / price, 2) if (mcap and price) else None
        conn.execute("""INSERT OR REPLACE INTO candidates
          (ticker,name,sector,currency,price,price_asof,mcap_m,shares_out_m,shares_method,
           tier,verification_status,known_issues,source_url)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (t, r['name'], r.get('sector'), cur or 'USD', price,
           r.get('price_asof') if price else None, mcap, shares,
           'derived' if shares else None, r.get('tier', '?'),
           r.get('verification_status', 'UNVERIFIED'), r.get('known_issues'),
           r.get('source', '')))
        if r.get('anchor_fund') and r['anchor_fund'] not in ('n/a', 'none', 'none current'):
            conn.execute("""INSERT INTO signals
              (ticker,signal_type,actor,event_date,asof,source_url,note)
              VALUES (?,?,?,?,?,?,?)""",
              (t, 'ANCHOR', r['anchor_fund'], None, r.get('price_asof') or '2026-06-10',
               r.get('source') or 'master_candidates.csv',
               f"company%:{r.get('pct_of_company')} book%:{r.get('pct_of_book')} basis:{r.get('cost_basis')} insider:{r.get('insider_signal')}"))
        cat_date = r.get('catalyst_date', '')
        if r.get('catalyst') and r['catalyst'] not in ('NONE', 'n/a', 'NONE remaining'):
            status = 'PENDING'
            if cat_date in ('done', 'closed') or 'happened' in cat_date: status = 'HAPPENED'
            conn.execute("""INSERT INTO catalysts (ticker,description,expected_date,status,source_url)
              VALUES (?,?,?,?,?)""",
              (t, r['catalyst'],
               cat_date if re.match(r'\d{4}-\d{2}-\d{2}', cat_date) else None, status,
               r.get('source', '')))
        n += 1
    print(f"migrated {n} candidates")

def archetypes(conn):
    """Migrate ARCHETYPES dict (original thesis content) into archetype_members."""
    sys.path.insert(0, os.path.join(REPO, 'pipeline'))
    src = open(os.path.join(REPO, 'pipeline', 'build_archetype_workbook.py')).read()
    ns = {}
    exec(compile(src.split("# ================================================================\n# BUILD WORKBOOK")[0], "<a>", "exec"), ns)
    n = 0
    for arch, data in ns['ARCHETYPES'].items():
        for m in data['names']:
            conn.execute("""INSERT OR REPLACE INTO archetype_members
              (archetype,ticker,thesis,valuation,catalyst,variant,smart_money)
              VALUES (?,?,?,?,?,?,?)""",
              (arch, m['ticker'], m.get('thesis'), m.get('valuation'),
               m.get('catalyst'), m.get('variant'), m.get('smart_money')))
            n += 1
    print(f"migrated {n} archetype members")

if __name__ == '__main__':
    conn = sqlite3.connect(DB)
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'init'
    init(conn)
    if cmd == 'migrate':
        migrate(conn)
        archetypes(conn)
    conn.commit()
    print(f"db ready: {DB}")
