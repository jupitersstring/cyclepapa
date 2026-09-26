"""Definitive 13F value-unit normalization via shares x price.

The post-2023 raw-dollar vs $thousands ambiguity cannot be settled by absolute
thresholds: a small fund reporting raw dollars (total ~$9e8) looks identical to
a large fund reporting $thousands. The reliable discriminator is per-position:

    value_k  SHOULD ~= shares * price / 1000   (when value is in $thousands)

If a fund's holdings have value_k ~= shares * price (ratio ~1000), the filing
reports RAW DOLLARS and every value_k for that fund is 1000x too large -> /1000.
Self-calibrating and idempotent: an already-correct fund has ratio ~1 and is
left untouched. FX-safe: only US-listed (USD) holdings are used to calibrate.

Run AFTER ticker_yf has prices (enrich_yfinance); BEFORE unified_score.
"""
import os, sqlite3, statistics, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=30000")
    funds = [r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_holdings")]
    fixed = 0
    for f in funds:
        rows = conn.execute("""SELECT h.value_k, h.shares, yf.price
            FROM fund_13f_holdings h JOIN ticker_yf yf ON yf.ticker = h.ticker
            WHERE h.fund=? AND h.sh_type IN ('SH','') AND h.shares>0 AND yf.price>0
              AND (yf.currency='USD' OR yf.currency IS NULL)""", (f,)).fetchall()
        ratios = [vk / (sh * px / 1000.0) for vk, sh, px in rows if sh * px > 0]
        if len(ratios) < 3:
            continue
        med = statistics.median(ratios)
        if med > 30:    # ~1000x => raw dollars
            conn.execute("UPDATE fund_13f_holdings SET value_k=value_k/1000.0 WHERE fund=?", (f,))
            conn.execute("UPDATE fund_13f_state SET total_value_k=total_value_k/1000.0 WHERE fund=?", (f,))
            fixed += 1
    conn.commit()
    print(f"normalize_13f_byprice: {fixed} funds re-scaled (raw-dollar -> $thousands)")

if __name__ == "__main__":
    run()
