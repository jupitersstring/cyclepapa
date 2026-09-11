"""Cohen-Malloy-Pomorski "informationally important" insider buy pattern.

The literature: routine clip-and-buy by directors is NOISE. The signal
worth pursuing combines five conditions in the SAME ticker, in the
SAME window:

  a) FIRST-IN-A-WHILE -- buyers were absent for an extended dormant
     period before the current cluster (high-conviction, not routine).
  b) MULTIPLE INSIDERS -- distinct people, not the same buyer repeating.
     Role mix matters (CEO + CFO + independent director > 3 directors).
  c) MATERIAL SIZE -- aggregate buy is a non-trivial % of mcap, and
     average buy per person is above token threshold ($25K).
  d) FRESH BUYBACK -- company-level repurchase authorization or live
     tender opened recently (<= 120 days), running concurrently with
     the insider window. The combined firm + insider signal is what
     Bonaime-Ryngaert found predictive.
  e) MATERIAL CATALYST PROXIMATE -- a known forward event: upcoming
     earnings (proxy: PSU plan with named hurdle / merger close in
     PSU triggers / live SC TO-T / 13E-3 in flight / FDA milestone in
     PSU conditionalities).

Score each ticker on 0..20 per condition, total 0..100. Names where
ALL FIVE conditions fire are the asymmetric pattern this module is
designed to surface.

Output: informational_buys.csv ranked by total + per-condition columns.
Reads only from disk; nothing relies on memory of prior runs.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def days_ago(d: str | None) -> int | None:
    if not d:
        return None
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-condition scorers
# ---------------------------------------------------------------------------

def score_first_in_a_while(filings: list[dict]) -> tuple[float, str]:
    """a) -- All recorded buys clustered in the last 60 days, AND the
    extracted record spans >180 days back (the dormancy gap).
    Returns 0..20."""
    if not filings:
        return 0, ""
    ages = [days_ago(f.get("date")) for f in filings]
    ages = sorted(a for a in ages if a is not None)
    if not ages:
        return 0, ""
    # If the oldest buy is recent AND the data window is broader than
    # the buys, the cluster is fresh-after-quiet.
    newest, oldest = ages[0], ages[-1]
    spread = oldest - newest
    # Heuristic: spread <= 30 days = single tight cluster (good).
    # Combined with newest <= 60 = fresh.
    if newest > 90:
        return 0, ""
    if spread <= 14 and newest <= 30:
        return 20, f"single {len(filings)}-day tight cluster ({newest}d ago)"
    if spread <= 30 and newest <= 60:
        return 15, f"tight cluster within 30d (newest {newest}d ago)"
    if spread <= 60 and newest <= 90:
        return 8, f"cluster within 60d span (newest {newest}d)"
    return 3, f"buys span {spread}d"


def score_multiple_insiders(rec: dict) -> tuple[float, str]:
    """b) -- Distinct persons + role-mix bonus."""
    filings = rec.get("filings") or []
    if not filings:
        return 0, ""
    persons = {f.get("person") for f in filings if f.get("person")}
    n = len(persons)
    titles = {}
    for b in rec.get("buyer_set") or []:
        p = b.split("|")
        if len(p) >= 2:
            titles[p[0].strip()] = p[1].strip()
    # Role mix: count distinct title categories
    cats = set()
    for f in filings:
        t = (f.get("title") or titles.get((f.get("person") or "").strip(), "")).lower()
        if "ceo" in t or "chief executive" in t: cats.add("ceo")
        elif "cfo" in t or "chief financial" in t: cats.add("cfo")
        elif "chair" in t and "vice" not in t: cats.add("chair")
        elif "director" in t: cats.add("director")
        elif "president" in t: cats.add("president")
        else: cats.add("other")
    role_diversity = len(cats)
    score = 0
    notes = []
    if n >= 5: score += 12; notes.append(f"{n} distinct buyers")
    elif n >= 4: score += 10; notes.append(f"{n} distinct buyers")
    elif n >= 3: score += 7; notes.append(f"{n} distinct buyers")
    elif n >= 2: score += 3; notes.append(f"{n} distinct buyers")
    if role_diversity >= 4:
        score += 8; notes.append(f"role mix: {','.join(sorted(cats))[:30]}")
    elif role_diversity >= 3:
        score += 5; notes.append(f"role mix: {','.join(sorted(cats))[:30]}")
    elif role_diversity == 2 and "ceo" in cats and "cfo" in cats:
        score += 6; notes.append("CEO+CFO both buying")
    return min(20.0, score), " / ".join(notes)


def score_material_size(rec: dict, mcap_usd: float | None) -> tuple[float, str]:
    """c) -- Aggregate buy as % of mcap; per-buyer minimum."""
    filings = rec.get("filings") or []
    if not filings:
        return 0, ""
    total = sum(float(f.get("dollar") or 0) for f in filings)
    persons = {f.get("person") for f in filings if f.get("person")}
    if not persons:
        return 0, ""
    avg_per_buyer = total / len(persons)
    score = 0
    notes = []
    if mcap_usd and mcap_usd > 0:
        pct = total / mcap_usd * 100
        if pct >= 0.5: score += 14; notes.append(f"${total/1e6:.1f}M = {pct:.2f}% mcap")
        elif pct >= 0.15: score += 10; notes.append(f"${total/1e6:.1f}M = {pct:.2f}% mcap")
        elif pct >= 0.05: score += 5
    if avg_per_buyer >= 250_000: score += 6; notes.append(f"avg ${avg_per_buyer/1e3:.0f}K/buyer")
    elif avg_per_buyer >= 50_000: score += 4
    elif avg_per_buyer < 10_000:
        score = max(0, score - 5)
        notes.append(f"token-size avg ${avg_per_buyer/1e3:.0f}K/buyer")
    return min(20.0, score), " / ".join(notes)


def score_fresh_buyback(tk: str, v2_auth: dict, tender: dict,
                         bb_verify: dict) -> tuple[float, str]:
    """d) -- A company-level repurchase action initiated in the last
    ~120 days running concurrently with the insider window."""
    score = 0
    notes = []
    # 1) tender activity
    t = tender.get(tk) or {}
    if t.get("score", 0) >= 12:
        fr = t.get("filings") or []
        if fr:
            min_da = min((f.get("days_ago") or 999) for f in fr)
            if min_da <= 120:
                score += 16
                notes.append(f"live {t.get('role','tender')} {min_da}d ago")
    # 2) fresh buyback authorization (from v2_detail buybacks dict)
    auth = v2_auth.get(tk)
    if auth:
        amt, fd = auth
        ago = days_ago(fd)
        if ago is not None and ago <= 120:
            score += 12 if ago <= 60 else 6
            notes.append(f"${amt:.0f}M buyback {ago}d ago")
    # 3) verified executing buyback (shrinking shares)
    bb = bb_verify.get(tk) or {}
    if bb.get("status") == "EXECUTING" and not notes:
        chg = (bb.get("share_change") or {}).get("change_pct")
        if chg is not None:
            score += 8
            notes.append(f"buyback EXECUTING {chg:.1f}% shrinkage")
    return min(20.0, score), " / ".join(notes)


def score_catalyst(tk: str, proxy_row: dict, tender_row: dict,
                    cxl_row: dict) -> tuple[float, str]:
    """e) -- A known catalyst proximate: PSU plan with named hurdle,
    merger close in PSU triggers, live tender/13E-3, FDA milestone,
    or fresh 10b5-1 sell-plan termination."""
    score = 0
    notes = []
    if proxy_row and proxy_row.get("has_psu_program"):
        cats = proxy_row.get("cond_cats") or []
        if "merger_acquisition_close" in cats:
            score += 12; notes.append("PSU vests on M&A close")
        if "spin_separation" in cats:
            score += 10; notes.append("PSU vests on spin / separation")
        if "fda_phase_milestone" in cats:
            score += 12; notes.append("PSU on FDA / clinical milestone")
        if any(c in cats for c in ("ebitda_dollar_target",
                                     "revenue_dollar_target",
                                     "fcf_dollar_target")):
            score += 8; notes.append("dollar metric hurdle in PSU")
        if proxy_row.get("n_fwd_cond"):
            score += 4
    t = tender_row or {}
    if t.get("score", 0) >= 12 and "spin" not in (" ".join(notes)):
        score += 8; notes.append("live tender / 13E-3 in flight")
    cs = float((cxl_row or {}).get("score") or 0)
    if cs >= 18:
        score += 6; notes.append(f"10b5-1 termination cluster +{cs:.0f}")
    return min(20.0, score), " / ".join(notes)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    print("--- loading from disk ---", file=sys.stderr)
    f4 = json.load(open(ROOT / "form4_buys.json"))
    quick = json.load(open(ROOT / "yfinance_quick.json"))
    tender = json.load(open(ROOT / "tender_scan.json"))
    cxl = json.load(open(ROOT / "cancel_10b5_1.json"))
    bb = json.load(open(ROOT / "buyback_verify.json"))
    proxy = json.load(open(ROOT / "proxy_scan.json"))
    for sp in sorted(ROOT.glob("proxy_scan.shard_*.json")):
        for tk, v in json.loads(sp.read_text()).items():
            if v.get("_complete"):
                proxy[tk] = v
    v2 = json.load(open(ROOT / "v2_detail.json"))
    v2_auth = {}
    for r in v2:
        if r.get("buyback_authorisation_musd") and r.get("filing_date"):
            tk = r.get("ticker")
            v2_auth[tk] = (r["buyback_authorisation_musd"], r["filing_date"])

    print(f"  form4={len(f4)} proxy={len(proxy)} tender={len(tender)} "
          f"bb={len(bb)} v2_auth={len(v2_auth)}", file=sys.stderr)

    rows = []
    for tk, rec in f4.items():
        mcap = (quick.get(tk) or {}).get("mcap")
        filings = rec.get("filings") or []
        if not filings:
            continue

        a, a_note = score_first_in_a_while(filings)
        b, b_note = score_multiple_insiders(rec)
        c, c_note = score_material_size(rec, mcap)
        d, d_note = score_fresh_buyback(tk, v2_auth, tender, bb)
        e, e_note = score_catalyst(tk, proxy.get(tk) or {},
                                    tender.get(tk) or {}, cxl.get(tk) or {})
        total = a + b + c + d + e
        # Composite filter: require at least 3 of 5 conditions firing meaningfully
        firing = sum(1 for x in (a, b, c, d, e) if x >= 5)
        if firing < 2 or total < 15:
            continue
        q = quick.get(tk) or {}
        rows.append({
            "ticker": tk,
            "total": round(total, 1),
            "conditions_firing": firing,
            "a_first_in_while": round(a, 1),
            "b_multiple_insiders": round(b, 1),
            "c_material_size": round(c, 1),
            "d_fresh_buyback": round(d, 1),
            "e_catalyst_proximate": round(e, 1),
            "a_note": a_note, "b_note": b_note, "c_note": c_note,
            "d_note": d_note, "e_note": e_note,
            "mcap_musd": round((mcap or 0) / 1e6, 0) or None,
            "price": q.get("price"),
            "p_b": q.get("p_b"),
            "sector": (q.get("sector") or "")[:18],
        })

    # Rank by: conditions_firing first, total second
    rows.sort(key=lambda r: (-r["conditions_firing"], -r["total"]))

    with open(ROOT / "informational_buys.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote informational_buys.csv ({len(rows)} rows)\n")
    print(f"=== TOP 30 -- 5-condition informational insider pattern ===")
    print(f"{'#':<3}{'TKR':<7}{'MCAP':>9}{'PX':>8}{'FIR':>4}{'TOT':>5}"
          f"{'A':>4}{'B':>4}{'C':>4}{'D':>4}{'E':>4}  NOTES")
    print("-" * 220)
    for i, r in enumerate(rows[:30], 1):
        mc = f"{r['mcap_musd']:>8.0f}M" if r['mcap_musd'] else "       ?M"
        px = f"{r['price']:>8.2f}" if r['price'] else "       ?"
        bits = []
        for k in ("a_note", "b_note", "c_note", "d_note", "e_note"):
            if r[k]: bits.append(r[k])
        notes = " | ".join(bits)[:140]
        print(f"{i:<3}{r['ticker']:<7}{mc}{px}{r['conditions_firing']:>4}"
              f"{r['total']:>5.0f}{r['a_first_in_while']:>4.0f}"
              f"{r['b_multiple_insiders']:>4.0f}{r['c_material_size']:>4.0f}"
              f"{r['d_fresh_buyback']:>4.0f}{r['e_catalyst_proximate']:>4.0f}"
              f"  {notes}")
    print(f"\n4-condition firing: {sum(1 for r in rows if r['conditions_firing']>=4)}")
    print(f"5-condition firing: {sum(1 for r in rows if r['conditions_firing']>=5)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
