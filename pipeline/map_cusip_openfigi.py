"""Resolve unmapped 13F holdings via OpenFIGI CUSIP -> ticker.

~14% of 13F holdings (incl. blue-chips held by 20+ funds: MOODY'S, PROGRESSIVE,
DANAHER, CORNING, NEWMONT...) had no ticker because the name->ticker matcher
fails on punctuation/suffix differences ("MOODYS CORP DEL" vs "Moody's Corp").

OpenFIGI maps CUSIP -> ticker authoritatively. For each unmapped CUSIP we take
the US-exchange listing (composite), normalising dual-class slashes (BRK/B ->
BRK-B). Free tier: 25 requests/min, 10 jobs/request -> ~250 CUSIPs/min.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
FIGI_URL = "https://api.openfigi.com/v3/mapping"

def figi_batch(cusips):
    payload = json.dumps([{"idType": "ID_CUSIP", "idValue": c} for c in cusips])
    out = subprocess.run(
        ["curl", "-s", "-m", "30", "-X", "POST", FIGI_URL,
         "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True).stdout
    return json.loads(out)   # raises on rate-limit/HTML -> caller retries

def pick_ticker(entry):
    data = entry.get("data") if isinstance(entry, dict) else None
    if not data:
        return None
    # prefer the US composite listing; else first listing
    us = [d for d in data if d.get("exchCode") == "US"]
    pool = us or data
    # avoid warrants/rights/units when a plain common-stock listing exists
    common = [d for d in pool if "Common" in (d.get("securityType2") or d.get("securityType") or "")]
    d = (common or pool)[0]
    t = (d.get("ticker") or "").strip().upper()
    if not t:
        return None
    return t.replace("/", "-")

def run(batch=10, sleep_s=2.6):
    conn = sqlite3.connect(DB)
    cusips = [r[0] for r in conn.execute("""SELECT DISTINCT cusip FROM fund_13f_holdings
        WHERE ticker IS NULL AND cusip IS NOT NULL AND length(cusip) >= 8""")]
    print(f"openfigi cusip map: {len(cusips)} unmapped CUSIPs, batch {batch}")
    mapped = {}
    i = 0
    while i < len(cusips):
        chunk = cusips[i:i + batch]
        ok = False
        for attempt in range(6):
            try:
                res = figi_batch(chunk)
                if isinstance(res, list) and len(res) == len(chunk):
                    ok = True
                    break
            except Exception:
                pass
            time.sleep(5 * (attempt + 1))   # backoff on rate-limit/error
        if ok:
            for c, entry in zip(chunk, res):
                t = pick_ticker(entry)
                if t and re.match(r"^[A-Z0-9][A-Z0-9.\-]{0,13}$", t):
                    mapped[c] = t
            i += batch
        else:
            print(f"  giving up on chunk at {i} after retries")
            i += batch
        if i % 200 == 0:
            print(f"  [{i}/{len(cusips)}] mapped={len(mapped)}")
        time.sleep(sleep_s)
    # apply
    n = 0
    for c, t in mapped.items():
        n += conn.execute("UPDATE fund_13f_holdings SET ticker=? WHERE cusip=? AND ticker IS NULL",
                          (t, c)).rowcount
    conn.commit()
    print(f"\ndone: mapped {len(mapped)}/{len(cusips)} CUSIPs -> {n} holdings now have a ticker")

if __name__ == "__main__":
    run()
