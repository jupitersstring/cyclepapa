"""Put the VALIDATED values into the legacy quote store every module reads.

66 modules read yfinance_quick.json directly. Rather than edit each one, this step
rewrites that file from the data store after the validated financials are built:

  * p_b, p_e_trailing, ev_ebitda, fcf_yield, earnings_yield  <- name_financials
    (validated FMP: share-basis checked, rejected values become None instead of
    a misleading number)
  * mcap_usd, security_type, issuer_id, kind, cik            <- security master
  * the value each field had before is kept under "_raw" so any change is auditable
  * "_validated" records the date of the sync

Run right after fmp_universe.py (so every layer reads validated values) and again
before the books. Idempotent.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import store

ROOT = Path("/home/user/cyclepapa")
YQ = ROOT / "yfinance_quick.json"
MAP = {"p_b": "p_b", "p_e_trailing": "pe", "ev_ebitda": "ev_ebitda", "fcf_yield": "fcf_yield",
       "earnings_yield": "earn_yield"}
BAD_BASIS = ("mcap_suspect", "implausible", "inconsistent", "neg_equity")


def main() -> int:
    yq = json.loads(YQ.read_text())
    fin = json.loads((ROOT / "name_financials.json").read_text())
    con = store.connect(readonly=True)
    sec = {r["security_id"]: dict(r) for r in con.execute(
        "SELECT security_id, issuer_id, sec_type FROM securities")}
    iss = {r["issuer_id"]: dict(r) for r in con.execute("SELECT issuer_id, cik, kind FROM issuers")}
    today = date.today().isoformat()
    changed = {k: 0 for k in MAP}
    n = 0
    for t, v in yq.items():
        if not isinstance(v, dict):
            continue
        raw = v.get("_raw") or {}
        # restore the raw values first so repeated syncs stay idempotent
        for k in MAP:
            if k in raw:
                v[k] = raw[k]
        f = fin.get(t)
        sid = store.resolve(t)
        s = sec.get(sid) or {}
        if s:
            v["security_type"] = s.get("sec_type")
            v["issuer_id"] = s.get("issuer_id")
            i = iss.get(s.get("issuer_id")) or {}
            if not v.get("cik") and i.get("cik"):
                v["cik"] = i["cik"].zfill(10)
            if i.get("kind"):
                v["kind"] = i["kind"]
        if f:
            n += 1
            for k, fk in MAP.items():
                new = f.get(fk)                  # validated view is authoritative: a None is a deliberate rejection
                old = v.get(k)
                if old != new:
                    raw.setdefault(k, old)
                    v[k] = new
                    changed[k] += 1
            if f.get("mcap_usd"):
                v["mcap_usd"] = f["mcap_usd"]
            if f.get("not_common"):
                v["not_common"] = True
        if raw:
            v["_raw"] = raw
        v["_validated"] = today
    tmp = YQ.with_suffix(".tmp")
    tmp.write_text(json.dumps(yq))
    tmp.replace(YQ)
    print(f"quotes_sync: {len(yq):,} quotes, {n:,} with validated financials; fields changed: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
