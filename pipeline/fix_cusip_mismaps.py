"""Correct 13F holdings whose ticker disagrees with the issuer name.

The name-based matcher (and some legacy maps) occasionally resolved a CUSIP's
issuer to the WRONG ticker (e.g. "NEW YORK MTG TR" -> ADAM, "EXP WORLD HLDGS" ->
AGNT). These corrupt smart-money counts for the wrong company. CUSIP is the
authoritative key, so for every holding whose issuer name shares ZERO normalized
words with the mapped ticker's known company name, we re-resolve the CUSIP via
OpenFIGI and OVERRIDE the ticker when OpenFIGI disagrees. Legit cases (ETFs
filed under a trust name, post-merger SPACs) return the same ticker -> no-op.
"""
import os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import _norm_name
from map_cusip_openfigi import figi_batch, pick_ticker

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run(batch=10, sleep_s=2.6):
    conn = sqlite3.connect(DB)
    rows = conn.execute("""SELECT DISTINCT h.cusip, h.ticker, h.issuer,
              COALESCE(tm.name, yf.long_name) known
           FROM fund_13f_holdings h
           LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
           LEFT JOIN ticker_yf  yf ON yf.ticker = h.ticker
           WHERE h.ticker IS NOT NULL AND h.cusip IS NOT NULL AND length(h.cusip)>=8
             AND COALESCE(tm.name, yf.long_name) IS NOT NULL""").fetchall()
    suspect = {}   # cusip -> current ticker
    for cusip, tk, iss, known in rows:
        a, b = set(_norm_name(iss).split()), set(_norm_name(known).split())
        if a and b and not (a & b):
            suspect.setdefault(cusip, tk)
    cusips = list(suspect)
    print(f"suspect (zero-overlap) distinct CUSIPs: {len(cusips)}")
    overridden = 0; checked = 0
    i = 0
    while i < len(cusips):
        chunk = cusips[i:i + batch]
        try:
            res = figi_batch(chunk)
            if not (isinstance(res, list) and len(res) == len(chunk)):
                raise ValueError("bad resp")
        except Exception:
            time.sleep(8); continue   # retry same chunk on rate-limit
        for cusip, entry in zip(chunk, res):
            checked += 1
            t = pick_ticker(entry)
            cur = suspect[cusip]
            if t and t != cur:
                n = conn.execute("UPDATE fund_13f_holdings SET ticker=? WHERE cusip=?", (t, cusip)).rowcount
                overridden += 1
                print(f"  fix {cusip} {cur} -> {t} ({n} rows)")
        i += batch
        if i % 100 == 0:
            conn.commit(); print(f"  [{i}/{len(cusips)}] overridden={overridden}")
        time.sleep(sleep_s)
    conn.commit()
    print(f"\ndone: checked {checked}, overrode {overridden} mis-mapped CUSIPs")

if __name__ == "__main__":
    run()
