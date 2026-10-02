"""Is the quarterly 13F roll due? Exit 0 (yes) or 1 (no), with the reason.

Due when the newest quarter whose 13F deadline has passed (fund_moves.
latest_due_quarter: quarter end + 55 days) is later than the quarter most
live books hold — the daily refresh would otherwise run on last quarter's
books and validate.py would stop it. run_scheduled.sh reads this.
"""
import collections, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fund_moves import latest_due_quarter
from ingest_13f import DB, DORMANT_DAYS

def run():
    conn = sqlite3.connect(DB, timeout=60)
    period = dict(conn.execute("SELECT accession, period FROM sec_13f_filings WHERE period != ''"))
    held = collections.Counter(
        period.get(acc) for acc, in conn.execute(
            "SELECT last_accession FROM fund_13f_state WHERE last_filed >= date('now', ?)",
            (f"-{DORMANT_DAYS} days",)) if period.get(acc))
    due = latest_due_quarter()
    if not held:
        print(f"roll due: no live 13F books on file (latest due quarter {due})")
        return 0
    modal, n = held.most_common(1)[0]
    if modal < due:
        print(f"roll due: most live books ({n} of {sum(held.values())}) hold {modal}; {due} is due")
        return 0
    print(f"no roll: most live books ({n} of {sum(held.values())}) hold {modal}, the latest due quarter")
    return 1

if __name__ == "__main__":
    sys.exit(run())
