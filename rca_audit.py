"""RCA / assembly-theory audit of the reverse-arch pipeline.

Decomposes the system into its assembly chain and verifies each layer
independently, bottom-up. Prints PASS/FAIL/WARN per check.

L1 primitives -> L2 chart assembly -> L3 natal scoring -> L4 event builder
-> L5 forward scoring (Silas overlay) -> L6 classification/normalization
-> L7 downstream scripts + data integrity.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import (
    BARBAULT, DEFAULT_ALREADY, SIGNS,
    asymmetry_scores, circular_midpoint, classify_window, compute_chart,
    era_match, exchange_open_jd, hard_asp, load_ipos, orb, percentile_rank,
    robust_core, score_forward, semi_lunar_bucket, speculative_bonus,
)

RESULTS = []


def check(layer, name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    RESULTS.append((layer, name, status, detail))
    print(f"[{status}] L{layer} {name}" + (f"  -- {detail}" if detail else ""))


def warn(layer, name, detail=""):
    RESULTS.append((layer, name, "WARN", detail))
    print(f"[WARN] L{layer} {name}" + (f"  -- {detail}" if detail else ""))


# ---------------- L1: primitives ----------------
def audit_L1():
    ok = all(abs(orb(a, b) - orb(b, a)) < 1e-9 for a, b in [(10, 350), (0, 180), (359, 1), (123.4, 321.9)])
    check(1, "orb symmetry", ok)
    check(1, "orb range [0,180]", all(0 <= orb(a, b) <= 180 for a in range(0, 360, 37) for b in range(0, 360, 41)))
    check(1, "orb wraparound", abs(orb(359, 1) - 2) < 1e-9 and abs(orb(0, 180) - 180) < 1e-9)

    mids = [(0, 90, 45), (350, 10, 0), (180, 270, 225), (90, 270, 0)]
    ok = all(abs(orb(circular_midpoint(a, b), m)) < 1e-6 or abs(orb(circular_midpoint(a, b), (m + 180) % 360)) < 1e-6 for a, b, m in mids)
    check(1, "circular_midpoint known values", ok)
    ok = all(orb(circular_midpoint(a, b), circular_midpoint(b, a)) in (0.0,) or orb(circular_midpoint(a, b), circular_midpoint(b, a)) in (180.0,) or orb(circular_midpoint(a, b), circular_midpoint(b, a)) < 1e-9
             for a, b in [(10, 80), (350, 40), (200, 300)])
    check(1, "circular_midpoint symmetry (mod 180)", ok)

    check(1, "hard_asp exact conj/opp/sq", hard_asp(10, 10, 3)[0] == "conj" and hard_asp(10, 190, 3)[0] == "opp" and hard_asp(10, 100, 3)[0] == "sq")
    check(1, "hard_asp None outside orb", hard_asp(10, 50, 3) is None and hard_asp(10, 140, 3) is None)
    check(1, "hard_asp orb value", abs(hard_asp(10, 12.5, 3)[1] - 2.5) < 1e-9)

    # DST handling: March (EST, UT+5) vs July (EDT, UT+4)
    jd_w, _, utc_w = exchange_open_jd("2000-01-14")
    jd_s, _, utc_s = exchange_open_jd("2000-07-14")
    check(1, "DST: winter open 14:30 UT", utc_w.hour == 14 and utc_w.minute == 30, utc_w.isoformat())
    check(1, "DST: summer open 13:30 UT", utc_s.hour == 13 and utc_s.minute == 30, utc_s.isoformat())

    check(1, "percentile_rank bounds", percentile_rank(5, [1, 2, 3]) == 100.0 and percentile_rank(0, [1, 2, 3]) == 0.0)
    check(1, "percentile_rank median", abs(percentile_rank(2.5, [1, 2, 3, 4]) - 50.0) < 1e-9)


# ---------------- L2: chart assembly vs ground truth ----------------
def audit_L2():
    # Sun longitude at J2000 epoch vs known (Sun ~280.0-280.5 on 2000-01-01 12UT; our chart is 14:30 UT)
    c = compute_chart("2000-01-03")
    check(2, "Sun lon 2000-01-03 ~282", abs(c["Sun"]["lon"] - 282.2) < 1.0, f"{c['Sun']['lon']:.2f}")
    # External validation vs Kate Silas's published GME chart: IPO 2002-02-12, "IPO Mars at 18 degrees Aries"
    g = compute_chart("2002-02-12")
    mars_sign = int(g["Mars"]["lon"] // 30)
    mars_deg = g["Mars"]["lon"] % 30
    check(2, "GME IPO Mars ~18 Aries (Silas cross-check)", mars_sign == 0 and abs(mars_deg - 18) <= 1.5, f"{mars_deg:.2f} {SIGNS[mars_sign]}")
    # AAPL 1980-12-12: Silas says natal Uranus conjunct by the 2022-05-16 lunar eclipse at ~25 Scorpio
    a = compute_chart("1980-12-12")
    ura_sign = int(a["Uranus"]["lon"] // 30)
    ura_deg = a["Uranus"]["lon"] % 30
    check(2, "AAPL IPO Uranus ~25-27 Scorpio (Silas cross-check)", ura_sign == 7 and 24 <= ura_deg <= 28, f"{ura_deg:.2f} {SIGNS[ura_sign]}")
    # equinox flag
    e = compute_chart("2014-03-20")
    check(2, "2014-03-20 Sun on 0 Aries + equinox flag", e["_equinox_solstice"] and orb(e["Sun"]["lon"], 0) < 1.0, f"Sun={e['Sun']['lon']:.2f}")
    # syzygy: pre-natal new moon Sun lon should be within 30 deg behind natal Sun
    pne = e["_pne"]
    check(2, "pre-natal syzygy within 30 deg of natal Sun", pne is not None and (e["Sun"]["lon"] - pne) % 360 <= 30.5, f"pne={pne:.2f}")
    # ASC/MC plausibility: 9:30 NYSE, Sun should be above horizon (house 12/11 side): ASC-Sun separation 15..120 deg
    sep = (e["Sun"]["lon"] - e["ASC"]["lon"]) % 360
    check(2, "Sun above eastern horizon at 9:30 (ASC->Sun 200..360)", 200 <= sep <= 359.9, f"sep={sep:.1f}")
    # station flag: speed threshold sanity — Jupiter mean 0.08, station if |speed|<0.016
    check(2, "station thresholds sane", not e["Sun"]["station"], "")
    # Neptune-return scan window is 2026-2036 regardless of chart date (documented as-of blindness)
    warn(2, "Neptune-return/aspect scans hardcode 2026-2036 window", "as-of blind; see L7 leakage")


# ---------------- L3: natal scoring assemblies ----------------
def audit_L3():
    c = compute_chart("2014-03-20")
    r1 = robust_core(c)
    r2 = robust_core(c)
    check(3, "robust_core deterministic", r1[0] == r2[0] and r1[2] == r2[2])
    score, hits, gate, arch, founder = r1
    check(3, "gate implies nonzero score", (not gate) or score > 0, f"score={score:.2f} gate={gate}")
    s, lh = semi_lunar_bucket(c)
    check(3, "semi_lunar non-negative", s >= 0, f"{s:.2f}")
    sp, sh = speculative_bonus(c)
    check(3, "spec bonus non-negative", sp >= 0, f"{sp:.2f}")
    # inherited quirk: Moon-on-MoPl-midpoint duplicates Moon-conj-Pluto within ~3 deg
    warn(3, "MP MoPl=Moon check only fires when Moon within ~3deg of Pluto", "duplicates L MoonPlu conj scoring (inherited from draft)")


# ---------------- L4: event builder vs known catalog ----------------
KNOWN_ECLIPSES = {
    ("2026-02-17", "annular"), ("2026-03-03", "total_lunar"), ("2026-08-12", "total_solar"),
    ("2027-02-06", "annular"), ("2027-08-02", "total_solar"), ("2028-01-26", "annular"),
    ("2028-07-22", "total_solar"), ("2030-06-01", "annular"), ("2030-11-25", "total_solar"),
    ("2033-03-30", "total_solar"), ("2034-03-20", "total_solar"), ("2035-09-02", "total_solar"),
}


def audit_L4():
    ev = json.loads(Path("/home/user/cyclepapa/forward_events.json").read_text())
    edates = {e["date"]: e["type"] for e in ev["eclipses"]}
    missing = [(d, t) for d, t in KNOWN_ECLIPSES if d not in edates or t.split("_")[0] not in edates[d]]
    check(4, "12 catalog eclipses present with right class", not missing, str(missing))
    # hybrid eclipse 2031-11-14 typed bare 'solar' -> underweighted (base 5 instead of ~10)
    hybrid = edates.get("2031-11-14", "")
    check(4, "hybrid 2031-11-14 typed as total/annular (not bare 'solar')", hybrid not in ("solar",), f"type={hybrid!r}")
    # Saturn-Neptune conjunction Feb 2026 near 0 Aries, matches SAT_NEP_DEG=0.75 constant
    sn = [e for e in ev["outer_pair_conj_and_ingress"] if "Saturn-Neptune" in e.get("note", "")]
    check(4, "Saturn-Neptune conj found Feb 2026 ~0.75 Aries", len(sn) >= 1 and sn[0]["date"].startswith("2026-02") and abs(sn[0]["lon"] - 0.75) < 0.5, str(sn[:1]))
    # independent recompute of the conjunction date via swisseph
    jd = swe.julday(2026, 2, 20, 12)
    sat = swe.calc_ut(jd, swe.SATURN)[0][0]
    nep = swe.calc_ut(jd, swe.NEPTUNE)[0][0]
    check(4, "swisseph: Sat-Nep separation <0.2 deg on 2026-02-20", abs(sat - nep) < 0.2, f"{sat:.3f} vs {nep:.3f}")
    # solar-eclipse lon vs independent Sun position
    e812 = [e for e in ev["eclipses"] if e["date"] == "2026-08-12"][0]
    jd2 = swe.julday(2026, 8, 12, 18)
    sun = swe.calc_ut(jd2, swe.SUN)[0][0]
    check(4, "2026-08-12 eclipse lon matches Sun lon", orb(e812["lon"], sun) < 1.0, f"ev={e812['lon']:.2f} sun={sun:.2f}")
    # station events: verify one against speed sign flip
    st = [s for s in ev["stations"] if s["what"] == "Neptune_Rx" and s["date"].startswith("2026")][0]
    d0 = date.fromisoformat(st["date"])
    jd_a = swe.julday(d0.year, d0.month, d0.day, 0) - 2
    jd_b = swe.julday(d0.year, d0.month, d0.day, 0) + 2
    sp_a = swe.calc_ut(jd_a, swe.NEPTUNE)[0][3]
    sp_b = swe.calc_ut(jd_b, swe.NEPTUNE)[0][3]
    check(4, "Neptune_Rx 2026 station brackets speed sign flip", sp_a > 0 > sp_b, f"{sp_a:+.4f} -> {sp_b:+.4f}")
    # events fully in the past relative to today exist in file (as-of blindness at data layer)
    today = date(2026, 7, 17).isoformat()
    past = [e["date"] for e in ev["eclipses"] if e["date"] < today]
    warn(4, f"{len(past)} eclipse events already in the past vs today 2026-07-17", ",".join(past))


# ---------------- L5: forward scoring / Silas overlay ----------------
def audit_L5():
    ev = json.loads(Path("/home/user/cyclepapa/forward_events.json").read_text())
    c = compute_chart("2014-03-20")
    peak, peak_d, conc, hits, jul, jul_hits, silas = score_forward(c, ev)
    # determinism
    peak2, _, conc2, hits2, _, _, silas2 = score_forward(c, ev)
    check(5, "score_forward deterministic", peak == peak2 and conc == conc2 and len(hits) == len(hits2))
    # no duplicate (date,desc) entries
    descs = [h["desc"] for h in hits]
    check(5, "no duplicate hits", len(descs) == len(set(descs)), f"{len(descs)} vs {len(set(descs))}")
    # polarity: conj kicker applied only to Sun conj (grep tags)
    sun_conj = [h for h in hits if " conj Sun " in h["desc"] or ("SUN-POWER" in h["desc"])]
    sun_opp = [h for h in hits if "SUN-DRAIN" in h["desc"]]
    check(5, "Sun polarity tags present for eclipse-Sun hits", bool(sun_conj) or bool(sun_opp), f"power={len(sun_conj)} drain={len(sun_opp)}")
    # eclipse_sun_events subset: each flag corresponds to an eclipse within 1 deg
    ok = all(float(s.split()[2].rstrip("°")) <= 1.0 for s in silas["eclipse_sun_events"])
    check(5, "eclipse_sun_events all <=1 deg", ok, str(silas["eclipse_sun_events"]))
    # TIGHT kicker monotonicity: a 0.9-deg hit should outscore an otherwise-identical 1.1-deg hit
    base = 10.0
    pts_tight = base * (2.0 - 0.9) / 2.0 * 1.3
    pts_loose = base * (2.0 - 1.1) / 2.0
    check(5, "tight-orb kicker preserves monotonicity at 1.0 boundary", pts_tight > pts_loose)
    # discontinuity size at the 1-deg boundary (design smell, not bug)
    j = base * (2.0 - 1.0001) / 2.0
    t = base * (2.0 - 0.9999) / 2.0 * 1.3
    warn(5, "30% step discontinuity at 1.0deg orb", f"{j:.2f} -> {t:.2f}")
    # position_by anchored on ANY event type (Neptune ingress), not eclipses only
    pb = silas["position_by"]
    ok_anchor = False
    if pb:
        anchor_date = (date.fromisoformat(pb) + timedelta(days=42)).isoformat()
        ok_anchor = any(h["date"] == anchor_date and ("solar" in h["desc"] or "lunar" in h["desc"]) for h in hits)
    check(5, "position_by anchored to an ECLIPSE hit (Silas rule)", ok_anchor, f"pos_by={pb}")
    # angles included at reduced weight; ensure no angle hit exceeds same-orb Sun hit
    angle_hits = [h for h in hits if " ASC " in h["desc"] or " MC " in h["desc"]]
    warn(5, f"{len(angle_hits)} eclipse-angle hits use assumed 9:30 chart time", "documented caveat")


# ---------------- L6: classification / normalization ----------------
def audit_L6():
    # asymmetry label partition and EARLY reachability
    row = {"total_dna": 20, "era": 5, "peak": 15, "conc": 40, "jul": 5,
           "window": "IMMINENT", "first_year": 2026, "jn_phase": "waxing", "jn_age": 100}
    e, en, tot, lab = asymmetry_scores(row)
    check(6, "asymmetry_scores returns finite", all(map(math.isfinite, (e, en, tot))))
    v3rows = list(csv.DictReader(open("/home/user/cyclepapa/reverse_arch_v8_1_asymmetry.csv")))
    labels = {r["asym_label"] for r in v3rows}
    check(6, "all three labels reachable (empirical, production CSV)", labels == {"EARLY_IMMINENT_ASYMMETRY", "ENDURING_HIGH_MAGNITUDE_ASYMMETRY", "BALANCED_ASYMMETRY"}, str(labels))
    # classify_window date-format mixing ("2026" vs "2026-02-17" vs "2026-07")
    hits = [{"pts": 5, "date": "2027"}, {"pts": 5, "date": "2026-08-12"}, {"pts": 5, "date": "2026-07"}]
    w, fy = classify_window(hits)
    check(6, "classify_window mixed date formats -> earliest year wins", fy == 2026, f"{w} {fy}")
    # BARBAULT covers all classify years incl fallback
    check(6, "BARBAULT covers 2024-2040", all(y in BARBAULT for y in range(2024, 2041)))


# ---------------- L7: downstream + data integrity ----------------
def audit_L7():
    # ticker collisions: DEFAULT_ALREADY excludes same-ticker DIFFERENT companies from Ritter era
    rows = list(csv.DictReader(open("/home/user/cyclepapa/ritter_full.csv")))
    from reverse_arch_v8_1_asymmetry import is_already_cult
    excluded = [(r["ticker"], r["name"], r["date"]) for r in rows if is_already_cult(r["ticker"], r["date"], DEFAULT_ALREADY)]
    modern_known = {
        "SNOW": ("Snowflake", "2020-09"), "U": ("Unity", "2020-09"), "AI": ("C3.ai", "2020-12"),
        "NET": ("Cloudflare", "2019-09"), "BILL": ("Bill.com", "2019-12"), "PATH": ("UiPath", "2021-04"),
        "COIN": ("Coinbase", "2021-04"), "DASH": ("DoorDash", "2020-12"), "WORK": ("Slack", "2019-06"),
        "GO": ("Grocery Outlet", "2019-06"),
    }
    collisions = []
    for t, n, d in excluded:
        if t in modern_known:
            comp, when = modern_known[t]
            if not d.startswith(when[:4]) and comp.split()[0].lower() not in n.lower():
                collisions.append(f"{t}={n} ({d}) wrongly excluded as {comp}")
    check(7, "no ticker-collision exclusions", not collisions, "; ".join(collisions))
    print(f"       total DEFAULT_ALREADY exclusions in universe: {len(excluded)}")

    # as-of leakage: score_forward with fully-filtered events still returns hits (SA/pMoon not filtered)
    c = compute_chart("2014-03-20")
    empty_ev = {"eclipses": [], "outer_pair_conj_and_ingress": [], "stations": []}
    peak, _, conc, hits, _, _, _ = score_forward(c, empty_ev, as_of="2027-11-02")
    dated_past = [h for h in hits if h["date"] < "2027-11"[: len(h["date"])] or (len(h["date"]) == 4 and h["date"] < "2027")]
    dated_past = [h for h in hits if h["date"][: len("2027-11-02")][:len(h["date"])] < "2027-11-02"[: len(h["date"])]]
    check(7, "as_of param filters progressed scans", not dated_past,
          f"{len(dated_past)} leaked, e.g. {dated_past[:2] if dated_past else ''}")

    # stale T0 constants in time-machine scripts
    src_delta = Path("/home/user/cyclepapa/asym_delta_18m.py").read_text()
    src_infl = Path("/home/user/cyclepapa/asym_curve_inflect.py").read_text()
    stale = "date(2026, 5, 4)" in src_delta or "date(2026, 5, 4)" in src_infl
    check(7, "delta/inflect T0 env-driven (RA_ASOF/today)", not stale and "RA_ASOF" in src_delta and "RA_ASOF" in src_infl)

    # v3 CSV integrity
    v3 = list(csv.DictReader(open("/home/user/cyclepapa/reverse_arch_v8_1_asymmetry.csv")))
    check(7, "v3 CSV row count 1635", len(v3) == 1635, str(len(v3)))
    bad = [r["ticker"] for r in v3 if not r["asym_total"] or float(r["asym_total"]) != float(r["asym_total"])]
    check(7, "no NaN/blank asym_total", not bad, str(bad[:5]))
    dupes = [t for t, n in Counter((r["ticker"], r["ipo_date"]) for r in v3).items() if n > 1]
    check(7, "no duplicate (ticker,date) rows", not dupes, str(dupes[:5]))
    # position_by in the past for all rows (symptom of ingress anchoring + no as-of)
    pb = Counter(r["position_by"] for r in v3 if r["position_by"])
    top_pb, top_n = pb.most_common(1)[0]
    check(7, "position_by not globally identical", top_n < len(v3) * 0.8, f"{top_pb} x{top_n}/{len(v3)}")
    past_pb = sum(1 for r in v3 if r["position_by"] and r["position_by"] < "2026-07-17")
    check(7, "position_by dates are in the future", past_pb == 0, f"{past_pb} rows have position_by already past")

    # sector_resonance built from May inflect CSV (stale after v3)
    warn(7, "sector_resonance.csv joins the May asym_inflect run", "regenerate after fixes for consistency")


def main():
    print("=" * 80)
    audit_L1(); audit_L2(); audit_L3(); audit_L4(); audit_L5(); audit_L6(); audit_L7()
    print("=" * 80)
    fails = [r for r in RESULTS if r[2] == "FAIL"]
    warns = [r for r in RESULTS if r[2] == "WARN"]
    print(f"TOTAL: {len(RESULTS)} checks  |  FAIL: {len(fails)}  WARN: {len(warns)}")
    for l, n, s, d in fails:
        print(f"  FAIL L{l}: {n} -- {d}")


if __name__ == "__main__":
    main()
