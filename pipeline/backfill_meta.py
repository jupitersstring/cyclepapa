"""Backfill ticker_meta descriptive fields (name / sector / industry) from the
Yahoo-sourced ticker_yf, so every table that joins ticker_meta shows a name and
industry instead of blanks.

Two passes:
  1. INSERT a ticker_meta row for any ticker that exists in ticker_yf (with a
     name) but is absent from ticker_meta — typically foreign / frontier
     listings discovered via the yfinance pass.
  2. UPDATE blank name / sector / industry / sic_description on existing rows
     from ticker_yf where we now have the value.

Purely additive — never overwrites a non-blank existing value.
"""
import os, sqlite3, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    c = sqlite3.connect(DB)
    asof = time.strftime("%Y-%m-%d")

    before_name = c.execute("SELECT COUNT(*) FROM ticker_meta WHERE name IS NOT NULL AND name!=''").fetchone()[0]
    before_rows = c.execute("SELECT COUNT(*) FROM ticker_meta").fetchone()[0]

    # 1. insert meta rows for yf tickers missing from meta
    cur = c.execute("""INSERT OR IGNORE INTO ticker_meta (ticker, name, sector, industry, mcap_m, asof)
        SELECT yf.ticker, yf.long_name, yf.sector, yf.industry, yf.mcap_m, ?
        FROM ticker_yf yf
        WHERE COALESCE(yf.long_name, yf.sector, yf.industry) IS NOT NULL
          AND yf.ticker NOT IN (SELECT ticker FROM ticker_meta)""", (asof,))
    n_ins = cur.rowcount

    # 2. backfill blank descriptive fields on existing rows
    pairs = [("name", "long_name"), ("sector", "sector"),
             ("industry", "industry"), ("sic_description", "industry")]
    n_upd = 0
    for meta_col, yf_col in pairs:
        cur = c.execute(f"""UPDATE ticker_meta
            SET {meta_col} = (SELECT yf.{yf_col} FROM ticker_yf yf WHERE yf.ticker = ticker_meta.ticker)
            WHERE ({meta_col} IS NULL OR {meta_col} = '')
              AND EXISTS (SELECT 1 FROM ticker_yf yf
                          WHERE yf.ticker = ticker_meta.ticker
                            AND yf.{yf_col} IS NOT NULL AND yf.{yf_col} != '')""")
        n_upd += cur.rowcount
    c.commit()

    after_name = c.execute("SELECT COUNT(*) FROM ticker_meta WHERE name IS NOT NULL AND name!=''").fetchone()[0]
    after_rows = c.execute("SELECT COUNT(*) FROM ticker_meta").fetchone()[0]
    print(f"inserted {n_ins} new meta rows ({before_rows} -> {after_rows})")
    print(f"backfilled {n_upd} blank descriptive fields")
    print(f"named tickers: {before_name} -> {after_name}")

if __name__ == "__main__":
    run()
