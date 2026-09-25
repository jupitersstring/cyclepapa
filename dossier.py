"""Per-company dossier: everything the system knows about one issuer, from the data store.

One record per company in the books:
  identity   security, issuer, type, kind, every other share line of the issuer
  now        validated figures (P/B or P/TBV, P/E, EV/EBITDA, market cap $, net cash, ROE ...)
  moves      how price, market cap and P/B moved vs the snapshots ~30 and ~90 days back
             (point-in-time fact store)
  timeline   the latest events across ALL sources, newest first: 8-K events (reviewed
             verdicts), 13D/13G moves, insider buys and sells, red flags, executive
             appointments, earnings-call commitments
  changed    what is new since the previous store run: events dated after it and material
             fact moves between the last two snapshots
  context    ownership, what is priced in, red flags, floor

Tear sheets render from these records. CLI: python3 dossier.py THRY
Output: dossiers.json
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import store

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "dossiers.json"
NOW_FIELDS = ("price", "mcap_usd", "p_b", "p_tbv", "pe", "ev_ebitda", "net_cash_pct", "roe", "roa", "tce_ta",
              "div_yield", "buyback_ttm_mcap", "shares_yoy", "rev_growth", "floor_frac", "downside_pct",
              "n_analysts", "pt_upside", "short_pct_float", "days_to_cover", "severity", "altman_z",
              "insider_buy_12m_usd", "insider_sell_12m_usd", "active_13d_max_pct")
FAMILY_ORDER = {"RED_FLAG": 0, "OWNERSHIP": 1, "EXEC": 2, "INSIDER": 3, "CALL_INTENT": 4}


def _j(n):
    p = ROOT / n
    return json.loads(p.read_text()) if p.exists() else {}


def build(tickers, con=None):
    con = con or store.connect(readonly=True)
    runs = [r["started"][:10] for r in con.execute("SELECT started FROM runs ORDER BY run_id")]
    prev_run = sorted({d for d in runs if d < date.today().isoformat()} or {runs[0] if runs else "1970-01-01"})[-1]
    dates = [r[0] for r in con.execute("SELECT DISTINCT as_of FROM facts ORDER BY as_of")]
    today = dates[-1] if dates else date.today().isoformat()

    def snap_before(days):
        target = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
        c = [d for d in dates if d <= target]
        return c[-1] if c else None
    d30, d90 = snap_before(25), snap_before(80)
    prev_snap = dates[-2] if len(dates) > 1 else None
    own, exp, dist = _j("ownership.json"), _j("expectations.json"), _j("distress_flags.json")
    out = {}
    for t in tickers:
        sid = store.resolve(t)
        if not sid:
            continue
        s = con.execute("SELECT * FROM securities WHERE security_id=?", (sid,)).fetchone()
        if not s:
            continue
        iss = con.execute("SELECT * FROM issuers WHERE issuer_id=?", (s["issuer_id"],)).fetchone()
        lines = [dict(r) for r in con.execute(
            "SELECT security_id, sec_type, exchange, status, is_primary FROM securities WHERE issuer_id=? AND security_id<>?",
            (s["issuer_id"], sid))][:8]
        now = {}
        for f in NOW_FIELDS:
            r = store.latest(sid, f, con=con) or store.latest(t, f, con=con)
            if r and r.get("value") is not None:
                now[f] = r["value"]
        moves = {}
        for label, d in (("30d", d30), ("90d", d90)):
            if not d or (label == "90d" and d == d30):
                continue                       # history gap: one comparison, labelled by its real start date
            for f in ("price", "mcap", "p_b"):
                a = store.latest(sid, f, validated_only=False, as_of=d, con=con)
                b = store.latest(sid, f, validated_only=False, con=con)
                if a and b and a["value"] and b["value"]:
                    moves[f"{f}_{label}"] = b["value"] / a["value"] - 1
                    moves[f"{f}_{label}_from"] = a["as_of"]
        ev = [dict(r) for r in con.execute(
            "SELECT date, type, family, source, what, verdict, reviewed, doc_url, amount_usd, counterparty, extra "
            "FROM events WHERE issuer_id=? AND date>=? ORDER BY date DESC", (s["issuer_id"], "2024-01-01"))]
        # insiders: roll individual trades up per month so they don't swamp the timeline
        tl, ins_m = [], {}
        for e in ev:
            if e["family"] == "INSIDER":
                k = (e["date"][:7], e["type"])
                ins_m.setdefault(k, [0.0, 0, e["date"]])
                ins_m[k][0] += e["amount_usd"] or 0
                ins_m[k][1] += 1
                continue
            if e["family"] == "LEGACY_SCANNER" or e.get("verdict") in ("NOT AN EVENT",):
                continue
            tl.append({"date": e["date"], "type": e["type"], "family": e["family"], "what": (e["what"] or "")[:220],
                       "reviewed": bool(e["reviewed"]), "url": e["doc_url"]})
        for (m, typ), (v, n, d) in ins_m.items():
            if v >= 100_000:
                tl.append({"date": d, "type": typ, "family": "INSIDER",
                           "what": f"insiders {'bought' if typ == 'INSIDER_BUY' else 'sold'} ${v / 1e6:.2f}M in {n} trade(s) ({m})"})
        tl.sort(key=lambda e: (e["date"], -FAMILY_ORDER.get(e["family"], 5)), reverse=True)
        changed = [e for e in tl if e["date"] > prev_run][:8]
        if prev_snap:
            for f in ("p_b", "severity", "short_pct_float", "pt_upside"):
                a = store.latest(sid, f, as_of=prev_snap, con=con)
                b = store.latest(sid, f, con=con)
                if a and b and a["value"] is not None and b["value"] is not None and a["as_of"] != b["as_of"]:
                    if f == "severity" and b["value"] > a["value"]:
                        changed.append({"date": b["as_of"], "type": "FACT", "what": f"red-flag severity {a['value']:.0f} -> {b['value']:.0f}"})
                    elif f != "severity" and a["value"] and abs(b["value"] / a["value"] - 1) >= 0.15:
                        changed.append({"date": b["as_of"], "type": "FACT", "what": f"{f} {a['value']:.2f} -> {b['value']:.2f}"})
        out[t] = {
            "security_id": sid, "issuer_id": s["issuer_id"], "name": s["name"], "sec_type": s["sec_type"],
            "exchange": s["exchange"], "currency": s["currency"], "kind": iss["kind"] if iss else None,
            "country": iss["country"] if iss else None, "other_lines": lines, "now": now, "moves": moves,
            "timeline": tl[:14], "changed_since": {"since": prev_run, "items": changed},
            "ownership": (own.get(t) or {}).get("summary"), "priced_in": (exp.get(t) or {}).get("summary"),
            "red_flags": [x.get("detail") for x in (dist.get(t) or {}).get("flags") or []][:5],
        }
    return out


def book_tickers():
    import store_build
    return sorted({t for _, t in store_build.book_names() if store.resolve(t)})


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] != "--all":
        d = build(sys.argv[1:])
        print(json.dumps(d, indent=1, default=str)[:6000])
        return 0
    tk = book_tickers()
    d = build(tk)
    OUT.write_text(json.dumps(d, indent=1, default=str))
    ch = sum(1 for r in d.values() if r["changed_since"]["items"])
    print(f"wrote {OUT.name}: {len(d):,} dossiers; {ch:,} with something new since the previous run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
