from __future__ import annotations

import csv
import json
import math
import os
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import pandas as pd
import swisseph as swe

swe.set_ephe_path(None)

NYSE_LAT, NYSE_LON = 40.7069, -74.0113
NYSE_TZ = ZoneInfo("America/New_York")
SIGNS = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]
SAT_NEP_DEG = 0.75
BARBAULT = {y: ("RISING" if y <= 2030 else ("FALLING" if y <= 2034 else "RISING")) for y in range(2024, 2041)}

STARS_J2000 = [
    ("Algol", 56.17, 5), ("Aldebaran", 69.47, 5), ("Betelgeuse", 88.64, 4),
    ("Sirius", 103.67, 5), ("Regulus", 149.83, 5), ("Spica", 203.50, 5),
    ("Antares", 249.47, 5), ("GC", 266.57, 5), ("Vega", 285.17, 4),
    ("Fomalhaut", 303.52, 5), ("Scheat", 359.08, 4), ("Mirach", 359.92, 3),
]
PREC = 0.01397
STAR_STRENGTH = {nm: st for nm, _, st in STARS_J2000}

MEAN_SPEEDS = {
    "Sun": 1.0, "Moon": 13.0, "Mercury": 1.2, "Venus": 1.0, "Mars": 0.5,
    "Jupiter": 0.08, "Saturn": 0.03, "Uranus": 0.01, "Neptune": 0.006, "Pluto": 0.004,
}

DEFAULT_ALREADY = {
    "TSLA","PLTR","NVDA","COIN","RDDT","CRWV","FIG","CRCL","HOOD","SHOP",
    "CROX","SNAP","ROKU","UBER","LYFT","ABNB","ZM","DASH","META","GOOG",
    "AAPL","MSFT","ORCL","CRM","NOW","CSCO","NFLX","DELL","QCOM","V","MA",
    "WMT","DIS","SBUX","NKE","HD","IBM","AMZN","BABA","BIDU","SQ","BILL",
    "DDOG","NET","OKTA","MDB","TEAM","DOCU","PINS","WORK","LNKD","TWTR",
    "YHOO","PCLN","BKNG","ARM","SPOT","DBX","RIVN","LCID","NU","GTLB",
    "DUOL","TOST","BROS","IREN","ALAB","CRWD","PANW","CHWY","AI","PATH",
    "SNOW","U","CPNG","WRBY","RKLB","JOBY","ACHR","LULU","ETSY","EBAY",
    "CMG","EXPE","GM","F","INTC","MCD","BA","JNJ","PG","XOM",
    "WDAY","PTON","BYND","MANU","GPRO","TMUS","BTC","ETH","BIRK","CAVA",
    "DPZ","DNKN","CIEN","MO","GE","CHTR","ERTS","BX","ANSS"
}
SHELL_KW = [
    "acquisition", "merger corp", "spac", "capital corp", "blank check",
    "income tr", "premium", "quality mun", "bond trust", " fund ", "trust i"
]


# ----------------------------
# Astronomical utilities
# ----------------------------

def orb(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def circular_midpoint(a: float, b: float) -> float:
    diff = (b - a) % 360
    if diff > 180:
        diff -= 360
    return (a + diff / 2.0) % 360


def hard_asp(a: float, b: float, mx: float = 3.0):
    diff = orb(a, b)
    for name, deg in (("conj", 0), ("opp", 180), ("sq", 90)):
        o = abs(diff - deg)
        if o <= mx:
            return name, o
    return None


def star_positions(year: int) -> dict[str, float]:
    dy = year - 2000
    return {nm: (lon + PREC * dy) % 360 for nm, lon, _ in STARS_J2000}


def star_hit(lon: float, stars: dict[str, float], mx: float = 1.0):
    best = None
    for nm, sl in stars.items():
        o = orb(lon, sl)
        if o <= mx and (best is None or o < best[1]):
            best = (nm, o, STAR_STRENGTH.get(nm, 3))
    return best


def exchange_open_jd(date_str: str):
    d = date.fromisoformat(date_str)
    local = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NYSE_TZ)
    utc = local.astimezone(timezone.utc)
    ut = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    jd = swe.julday(utc.year, utc.month, utc.day, ut)
    return jd, d, utc


def synodic_phase(fast_lon: float, slow_lon: float):
    age = (fast_lon - slow_lon) % 360
    return ("waxing" if age < 180 else "waning"), age


def synodic_age_bucket(age: float) -> str:
    if age < 30:
        return "seed"
    if age < 90:
        return "early_waxing"
    if age < 150:
        return "late_waxing"
    if age < 210:
        return "oppositional"
    if age < 270:
        return "late_waning"
    if age < 330:
        return "terminal_waning"
    return "balsamic"


def phase_angle_at_jd(jd: float) -> float:
    sl = swe.calc_ut(jd, swe.SUN)[0][0] % 360
    ml = swe.calc_ut(jd, swe.MOON)[0][0] % 360
    return (ml - sl) % 360


def exact_last_syzygy(jd: float):
    prev_pa = None
    prev_jd = None
    for k in range(1, 40 * 24 + 1):
        test_jd = jd - (k / 24.0)
        pa = phase_angle_at_jd(test_jd)
        if prev_pa is not None and prev_pa < 20 and pa > 340:
            lo, hi = test_jd, prev_jd
            for _ in range(25):
                mid = (lo + hi) / 2.0
                pm = phase_angle_at_jd(mid)
                if pm > 180:
                    lo = mid
                else:
                    hi = mid
            syz_jd = (lo + hi) / 2.0
            sl = swe.calc_ut(syz_jd, swe.SUN)[0][0] % 360
            return sl, "NewMoon"
        prev_pa = pa
        prev_jd = test_jd
    return None, None


def phase_name(sun_lon: float, moon_lon: float) -> str:
    pa = (moon_lon - sun_lon) % 360
    for threshold, name in (
        (45, "new"), (90, "waxcres"), (135, "firstQ"), (180, "waxgib"),
        (225, "full"), (270, "wangib"), (315, "lastQ"), (360, "balsamic"),
    ):
        if pa < threshold:
            return name
    return "balsamic"


def is_shell(name: str) -> bool:
    nl = (name or "").lower()
    return any(k in nl for k in SHELL_KW)


# ----------------------------
# Chart computation
# ----------------------------

def compute_chart(date_str: str) -> dict:
    jd, d, utc = exchange_open_jd(date_str)
    c = {"_jd": jd, "_date": d, "_utc": utc.isoformat(), "_stars": star_positions(d.year)}

    planets = [
        ("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
        ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN), ("Uranus", swe.URANUS),
        ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO), ("NN", swe.MEAN_NODE),
    ]
    for nm, pid in planets:
        res = swe.calc_ut(jd, pid)
        lon = res[0][0] % 360
        speed = res[0][3]
        decl = swe.calc_ut(jd, pid, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)[0][1]
        mean_spd = MEAN_SPEEDS.get(nm, 1.0)
        c[nm] = {
            "lon": lon,
            "decl": decl,
            "speed": speed,
            "retro": speed < 0,
            "station": abs(speed) < mean_spd * 0.2,
            "sign": int(lon // 30),
        }

    for nm, pid in (("Jupiter", swe.JUPITER), ("Neptune", swe.NEPTUNE), ("Uranus", swe.URANUS)):
        try:
            hl = swe.calc_ut(jd, pid, swe.FLG_HELCTR)[0][0] % 360
            c[f"H_{nm}"] = {"lon": hl}
        except Exception:
            pass
    c["H_Earth"] = {"lon": (c["Sun"]["lon"] + 180) % 360}

    try:
        cusps, ascmc = swe.houses(jd, NYSE_LAT, NYSE_LON, b"P")
        c["ASC"] = {"lon": ascmc[0] % 360, "sign": int((ascmc[0] % 360) // 30)}
        c["MC"] = {"lon": ascmc[1] % 360, "sign": int((ascmc[1] % 360) // 30)}
    except Exception:
        c["ASC"] = {"lon": 0.0, "sign": 0}
        c["MC"] = {"lon": 0.0, "sign": 0}

    c["_is_day"] = True
    c["LOF"] = {"lon": (c["ASC"]["lon"] + c["Moon"]["lon"] - c["Sun"]["lon"]) % 360}

    c["_phase"] = phase_name(c["Sun"]["lon"], c["Moon"]["lon"])
    c["_jn_phase"], c["_jn_age"] = synodic_phase(c["Jupiter"]["lon"], c["Neptune"]["lon"])
    c["_jn_bucket"] = synodic_age_bucket(c["_jn_age"])
    c["_ju_phase"], c["_ju_age"] = synodic_phase(c["Jupiter"]["lon"], c["Uranus"]["lon"])
    c["_ju_bucket"] = synodic_age_bucket(c["_ju_age"])
    c["_equinox_solstice"] = any(orb(c["Sun"]["lon"], cp) <= 2.0 for cp in (0, 90, 180, 270))

    natal_nep = c["Neptune"]["lon"]
    best_nr = 999.0
    best_nr_date = None
    for yr in range(2026, 2037):
        for mo in range(1, 13):
            tjd = swe.julday(yr, mo, 1, 12)
            tnep = swe.calc_ut(tjd, swe.NEPTUNE)[0][0] % 360
            o = orb(tnep, natal_nep)
            if o < best_nr:
                best_nr = o
                best_nr_date = f"{yr:04d}-{mo:02d}-01"
    c["_nep_return"] = best_nr <= 2.0
    c["_nep_return_orb"] = best_nr
    c["_nep_return_date"] = best_nr_date

    pne, pne_type = exact_last_syzygy(jd)
    c["_pne"] = pne
    c["_pne_type"] = pne_type
    return c


# ----------------------------
# Structural scoring
# ----------------------------

def robust_core(c: dict):
    score = 0.0
    hits = []
    gate = False
    archetype = set()
    stars = c["_stars"]

    r = hard_asp(c["Jupiter"]["lon"], c["Neptune"]["lon"], 2.5)
    if r:
        asp, o = r
        base = 12.0
        if c["_jn_phase"] == "waxing":
            base *= 1.2
            if c["_jn_age"] < 30:
                base *= 1.05
            tag = f"WAX age{c['_jn_age']:.0f}"
        else:
            base *= 0.85
            if c["_jn_age"] > 300:
                base *= 0.92
            tag = f"WAN age{c['_jn_age']:.0f}"
        pts = base * (2.5 - o) / 2.5
        score += pts
        hits.append(f"T1 JupNep {asp} {o:.2f}° {tag} [+{pts:.1f}]")
        if o <= 2.0:
            gate = True
        archetype.add("Dionysian")
        for p in ("Jupiter", "Neptune"):
            if c[p]["station"]:
                score += 2.0
                hits.append(f"  {p} station [+2.0]")

    if "H_Jupiter" in c and "H_Neptune" in c:
        r2 = hard_asp(c["H_Jupiter"]["lon"], c["H_Neptune"]["lon"], 2.5)
        if r2:
            asp2, o2 = r2
            pts = 5.0 * (2.5 - o2) / 2.5
            score += pts
            hits.append(f"HELIO JupNep {asp2} {o2:.2f}° [+{pts:.1f}]")
            if o2 <= 1.5 and not gate:
                gate = True

    for other, label, base in (("Uranus", "SunUra", 10.0), ("Neptune", "SunNep", 8.0), ("Pluto", "SunPlu", 7.0)):
        max_orb = 3.0 if other == "Uranus" else 2.5
        r = hard_asp(c["Sun"]["lon"], c[other]["lon"], max_orb)
        if r:
            asp, o = r
            pts = base * (max_orb - o) / max_orb
            score += pts
            hits.append(f"T {label} {asp} {o:.2f}° [+{pts:.1f}]")
            if o <= (2.0 if other == "Uranus" else 1.5):
                gate = True
            archetype.add({"Uranus": "Promethean", "Neptune": "Dionysian", "Pluto": "Orphic"}[other])

    for p1, p2, label, bpts in (
        ("Mercury", "Uranus", "info-disrupt", 5.0),
        ("Mars", "Neptune", "action-fantasy", 5.0),
        ("Venus", "Neptune", "beautiful-delusion", 5.0),
        ("Jupiter", "Uranus", "spec-disrupt", 5.0),
        ("Saturn", "Neptune", "cycle-bend", 4.0),
    ):
        r = hard_asp(c[p1]["lon"], c[p2]["lon"], 2.5)
        if r:
            asp, o = r
            pts = bpts * (2.5 - o) / 2.5
            score += pts
            hits.append(f"T {p1}{p2} {asp} {o:.2f}° ERA:{label} [+{pts:.1f}]")
            if o <= 1.5:
                gate = True
            if p1 == "Mercury":
                archetype.add("Hermetic")

    sc = star_hit(c["Sun"]["lon"], stars, 1.0)
    if sc:
        nm, o, st = sc
        pts = st * 1.8 * (1.0 - o)
        score += pts
        hits.append(f"T Sun on {nm} {o:.2f}° [+{pts:.1f}]")
        if st >= 4:
            gate = True
            archetype.add("Solar/Royal")

    for cp in (0, 90, 180, 270):
        o = orb(c["Sun"]["lon"], cp)
        if o <= 2.0:
            pts = 6.0 * (2.0 - o) / 2.0
            score += pts
            hits.append(f"T Sun AP ({o:.2f}°) [+{pts:.1f}]")
            if o <= 1.5:
                gate = True
            break

    midpoint_specs = [
        ("Jupiter", "Neptune", "JuNe", 3.0),
        ("Mars", "Uranus", "MaUr", 2.5),
        ("Sun", "Uranus", "SuUr", 2.5),
        ("Mars", "Jupiter", "MaJu", 2.0),
        ("Venus", "Pluto", "VePl", 2.0),
        ("Jupiter", "Pluto", "JuPl", 2.0),
    ]
    for a, b, label, bpts in midpoint_specs:
        mp = circular_midpoint(c[a]["lon"], c[b]["lon"])
        for m in (mp, (mp + 180) % 360):
            d = orb(c["Sun"]["lon"], m)
            if d <= 1.5:
                pts = bpts * (1.5 - d) / 1.5
                if pts > 0.2:
                    score += pts
                    hits.append(f"MP {label}=Sun {d:.2f}° [+{pts:.1f}]")
                break

    sign_counts = defaultdict(list)
    for p in ("Sun", "Mercury", "Venus", "Mars", "Jupiter"):
        sign_counts[c[p]["sign"]].append(p)
    for sidx, planets in sign_counts.items():
        if len(planets) >= 3:
            pts = 4.0 if SIGNS[sidx] in ("Aqu", "Pis", "Ari", "Gem", "Leo", "Sco") else 2.0
            score += pts
            hits.append(f"Stellium {SIGNS[sidx]}:{','.join(planets)} [+{pts:.1f}]")
            if len(planets) >= 4:
                gate = True

    if c["_pne"] is not None:
        for p2 in ("Neptune", "Uranus", "Pluto"):
            r2 = hard_asp(c["_pne"], c[p2]["lon"], 2.0)
            if r2:
                asp2, o2 = r2
                pts = 2.0 * (2.0 - o2) / 2.0
                score += pts
                hits.append(f"PreNM {asp2} {p2} {o2:.1f}° [+{pts:.1f}]")

    sun_to_sn = orb(c["Sun"]["lon"], SAT_NEP_DEG)
    if sun_to_sn <= 2.0:
        pts = 4.0 * (2.0 - sun_to_sn) / 2.0
        score += pts
        hits.append(f"SatNep archetype ({sun_to_sn:.2f}°) [+{pts:.1f}]")
        archetype.add("Saturnine")

    if c["_phase"] == "balsamic":
        score *= 1.08
        hits.append("BALSAMIC (×1.08)")
    elif c["_phase"] == "new":
        score *= 1.04
        hits.append("NEW MOON (×1.04)")

    if c["_nep_return"]:
        score *= 1.12
        hits.append(f"NEPTUNE RETURN ({c['_nep_return_orb']:.2f}°) (×1.12)")

    if c["_equinox_solstice"]:
        score += 2.0
        hits.append("EQUINOX/SOLSTICE [+2.0]")

    for p in ("Jupiter", "Neptune", "Uranus", "Pluto"):
        if c[p]["station"]:
            score += 2.0
            hits.append(f"{p} station [+2.0]")

    if not archetype:
        archetype = {"Unclassified"}
    founder_flag = (score < 20 and any(a in archetype for a in ("Promethean", "Solar/Royal", "Hermetic")))
    return score, hits, gate, archetype, founder_flag


def semi_lunar_bucket(c: dict):
    score = 0.0
    hits = []
    stars = c["_stars"]

    for other, label, base in (("Neptune", "MoonNep", 8.0), ("Pluto", "MoonPlu", 7.0), ("Uranus", "MoonUra", 5.0)):
        r = hard_asp(c["Moon"]["lon"], c[other]["lon"], 2.5)
        if r:
            asp, o = r
            pts = base * (2.5 - o) / 2.5
            score += pts
            hits.append(f"L {label} {asp} {o:.2f}° [+{pts:.1f}]")

    sc = star_hit(c["Moon"]["lon"], stars, 0.8)
    if sc:
        nm, o, st = sc
        pts = st * 1.0 * (0.8 - o) / 0.8
        if pts > 0.2:
            score += pts
            hits.append(f"L Moon on {nm} {o:.2f}° [+{pts:.1f}]")

    for cp in (0, 90, 180, 270):
        o = orb(c["Moon"]["lon"], cp)
        if o <= 1.5:
            pts = 3.0 * (1.5 - o) / 1.5
            score += pts
            hits.append(f"L Moon AP ({o:.2f}°) [+{pts:.1f}]")
            break

    if abs(c["Moon"]["decl"]) > 23.45:
        score += 2.0
        hits.append(f"L MoonOOB ({c['Moon']['decl']:.1f}°) [+2.0]")

    mp = circular_midpoint(c["Moon"]["lon"], c["Pluto"]["lon"])
    for m in (mp, (mp + 180) % 360):
        d = orb(c["Moon"]["lon"], m)
        if d <= 1.5:
            pts = 2.5 * (1.5 - d) / 1.5
            if pts > 0.2:
                score += pts
                hits.append(f"L MP MoPl=Moon {d:.2f}° [+{pts:.1f}]")
            break

    return score * 0.5, hits


def speculative_bonus(c: dict):
    bonus = 0.0
    hits = []
    stars = c["_stars"]
    for body in ("ASC", "MC"):
        sc = star_hit(c[body]["lon"], stars, 1.0)
        if sc:
            nm, o, st = sc
            pts = st * 1.5 * (1.0 - o)
            bonus += pts
            hits.append(f"SPEC {body} on {nm} {o:.2f}° [+{pts:.1f}]")
    for angle in ("ASC", "MC"):
        for p in ("Uranus", "Neptune", "Pluto", "Jupiter"):
            o = orb(c[angle]["lon"], c[p]["lon"])
            if o <= 3.0:
                pts = 4.0 * (3.0 - o) / 3.0
                bonus += pts
                hits.append(f"SPEC {p}conj{angle} {o:.2f}° [+{pts:.1f}]")
    for body in ("ASC", "MC"):
        for cp in (0, 90, 180, 270):
            o = orb(c[body]["lon"], cp)
            if o <= 2.0:
                pts = 5.0 * (2.0 - o) / 2.0
                bonus += pts
                hits.append(f"SPEC {body} AP ({o:.2f}°) [+{pts:.1f}]")
                break
    sc = star_hit(c["LOF"]["lon"], stars, 1.0)
    if sc:
        nm, o, st = sc
        pts = st * 0.5 * (1.0 - o)
        if pts > 0.2:
            bonus += pts
            hits.append(f"SPEC LOF on {nm} {o:.2f}° [+{pts:.1f}]")
    return bonus * 0.5, hits


# ----------------------------
# Forward timing and classification
# ----------------------------

def july_cluster_positions(cluster_date: str = "2026-07-20") -> dict:
    jd, _, _ = exchange_open_jd(cluster_date)
    return {
        "JulJup": swe.calc_ut(jd, swe.JUPITER)[0][0] % 360,
        "JulNep": swe.calc_ut(jd, swe.NEPTUNE)[0][0] % 360,
        "JulPlu": swe.calc_ut(jd, swe.PLUTO)[0][0] % 360,
    }


def score_forward(c: dict, events: dict | None = None):
    events = events or {}
    all_hits = []
    robust_targets = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Neptune"]
    lunar_targets = ["Moon"]

    for ev in events.get("eclipses", []):
        is_scheat = "SCHEAT" in ev.get("type", "")
        star_amp = 1.8 if is_scheat else (1.5 if any(k in ev.get("type", "") for k in ("ALDEBARAN", "GREAT")) else 1.0)
        base = 10.0 if "total_solar" in ev.get("type", "") else (8.0 if "annular" in ev.get("type", "") else 5.0)
        base *= star_amp
        for pn in robust_targets + lunar_targets:
            plon = c[pn]["lon"]
            r = hard_asp(ev["lon"], plon, 2.0)
            if not r:
                continue
            asp, o = r
            pm = 1.5 if pn == "Sun" else (1.4 if pn in ("Jupiter", "Neptune") else (1.1 if pn == "Moon" else 1.0))
            pts = base * (2.0 - o) / 2.0 * pm
            if pn == "Moon":
                pts *= 0.65
            try:
                yr = int(ev["date"][:4])
                if BARBAULT.get(yr, "RISING") == "FALLING":
                    pts *= 0.85
            except Exception:
                pass
            all_hits.append({"pts": pts, "date": ev["date"], "desc": f"{ev['date']} {ev.get('type','')[:30]} {asp} {pn} {o:.2f}°"})

    for ev in events.get("outer_pair_conj_and_ingress", []):
        note = ev.get("note", "")
        is_jn = "Jupiter-Neptune" in note
        base = 10.0 if is_jn else (9.0 if any(k in note for k in ("Saturn-Uranus", "Saturn-Neptune")) else 6.0)
        for pn in robust_targets + lunar_targets:
            plon = c[pn]["lon"]
            r = hard_asp(ev["lon"], plon, 2.0)
            if not r:
                continue
            asp, o = r
            pm = 2.0 if is_jn and pn == "Sun" else (1.5 if pn == "Sun" else (1.1 if pn == "Moon" else 1.0))
            pts = base * (2.0 - o) / 2.0 * pm
            if pn == "Moon":
                pts *= 0.65
            try:
                yr = int(ev["date"][:4])
                if BARBAULT.get(yr, "RISING") == "FALLING":
                    pts *= 0.85
            except Exception:
                pass
            all_hits.append({"pts": pts, "date": ev["date"], "desc": f"{ev['date']} {note[:30]} {asp} {pn} {o:.2f}°"})

    for st in events.get("stations", []):
        parts = st["what"].rsplit("_", 1)
        pname = parts[0] if len(parts) == 2 else st["what"]
        if pname not in ("Saturn", "Uranus", "Neptune", "Pluto"):
            continue
        for pn in robust_targets + lunar_targets:
            o = orb(st["lon"], c[pn]["lon"])
            if o <= 1.0:
                pm = 1.5 if pn in ("Sun", "Moon") else 1.0
                pts = 8.0 * (1.0 - o) * pm
                if pn == "Moon":
                    pts *= 0.65
                if pts > 0.3:
                    all_hits.append({"pts": pts, "date": st["date"], "desc": f"{st['date']} {st['what']} conj {pn} {o:.2f}°"})

    jd_n = c["_jd"]
    natal_sun = c["Sun"]["lon"]
    for ty in range(2026, 2037):
        years = ty - c["_date"].year
        if years <= 0 or years > 50:
            continue
        try:
            prog_sun = swe.calc_ut(jd_n + years, swe.SUN)[0][0] % 360
            arc = (prog_sun - natal_sun) % 360
            if arc > 180:
                arc -= 360
        except Exception:
            continue
        for np in ("Sun", "Moon"):
            sa_lon = (c[np]["lon"] + arc) % 360
            for tp in ("Uranus", "Neptune", "Pluto"):
                r = hard_asp(sa_lon, c[tp]["lon"], 1.0)
                if r:
                    asp, o = r
                    pts = 3.5 * (1.0 - o)
                    if np == "Moon":
                        pts *= 0.65
                    if pts > 0.3:
                        all_hits.append({"pts": pts, "date": str(ty), "desc": f"{ty} SA {np} {asp} {tp} {o:.2f}°"})

    for ty in range(2026, 2037):
        years = ty - c["_date"].year
        if years <= 0 or years > 50:
            continue
        for mo in range(1, 13):
            prog_days = years + (mo - 0.5) / 12.0
            try:
                pmoon = swe.calc_ut(jd_n + prog_days, swe.MOON)[0][0] % 360
            except Exception:
                continue
            for pn in ("Sun", "Jupiter", "Neptune", "Uranus", "Pluto"):
                r = hard_asp(pmoon, c[pn]["lon"], 1.5)
                if r:
                    asp, o = r
                    pts = 2.5 * (1.5 - o) / 1.5
                    if pn == "Sun":
                        pts *= 0.9
                    if pts > 0.3:
                        all_hits.append({"pts": pts, "date": f"{ty}-{mo:02d}", "desc": f"{ty}-{mo:02d} pMoon {asp} {pn} {o:.1f}°"})

    all_hits.sort(key=lambda h: (-h["pts"], h["date"]))
    peak = all_hits[0] if all_hits else {"pts": 0.0, "desc": "none"}
    top3 = sum(h["pts"] for h in all_hits[:3])
    rest = sum(h["pts"] for h in all_hits[3:]) * 0.1

    cluster = july_cluster_positions("2026-07-20")
    jul_score = 0.0
    jul_hits = []
    for body in ("Sun", "Moon", "Jupiter", "Neptune"):
        nl = c[body]["lon"]
        for tn, tl in cluster.items():
            for asp, adeg in (("conj", 0), ("opp", 180), ("sq", 90), ("tri", 120)):
                ao = abs(orb(nl, tl) - adeg)
                if ao <= 2.0:
                    pts = 3.0 * (2.0 - ao) / 2.0 * (1.5 if body in ("Sun", "Moon") else 1.0)
                    if body == "Moon":
                        pts *= 0.65
                    jul_score += pts
                    jul_hits.append(f"{body} {asp} {tn} {ao:.1f}°")
    return peak["pts"], peak, top3 + rest, all_hits, jul_score, jul_hits


def era_match(c: dict) -> float:
    score = 0.0
    sun_lon = c["Sun"]["lon"]
    for center, width, pts in ((2.5, 7, 3.0), (64.5, 10, 3.0), (134.5, 10, 2.0), (305.5, 7, 2.0)):
        d = orb(sun_lon, center)
        if d <= width:
            score += pts * (width - d) / width
    if 60 <= c["Mercury"]["lon"] <= 69:
        score += 2.0
    for p in ("Sun", "Moon"):
        o = orb(c[p]["lon"], SAT_NEP_DEG)
        if o <= 3.0:
            score += 3.0 * (3.0 - o) / 3.0 * (0.8 if p == "Moon" else 1.0)
    return score


# ----------------------------
# Normalization and asymmetry
# ----------------------------

def percentile_rank(value: float, sample: list[float]) -> float:
    if not sample:
        return 0.0
    s = sorted(sample)
    pos = bisect_left(s, value)
    return 100.0 * pos / len(s)


def composite_v8_1(robust: float, semi: float, spec: float, peak: float, conc: float, era: float, jul: float, stats: dict[str, list[float]]):
    dna_raw = robust + semi + spec
    fwd_raw = peak * 0.6 + conc * 0.4
    dna_norm = percentile_rank(dna_raw, stats.get("dna", []))
    fwd_norm = percentile_rank(fwd_raw, stats.get("fwd", []))
    era_norm = percentile_rank(era, stats.get("era", []))
    jul_norm = percentile_rank(jul, stats.get("jul", []))
    return dna_norm * 0.50 + fwd_norm * 0.35 + era_norm * 0.10 + jul_norm * 0.05


def classify_window(fwd_hits: list[dict]):
    for h in sorted(fwd_hits, key=lambda x: x["date"]):
        if h["pts"] < 3:
            continue
        yr = h["date"][:4]
        if yr == "2026":
            return "IMMINENT", 2026
        if yr in ("2027", "2028"):
            return "SOONER", int(yr)
        if yr in ("2029", "2030", "2031", "2032"):
            return "MEDIUM", int(yr)
        return "PEAK", int(yr)
    return "DISTANT", 2040


def classify_rally(jn_phase: str, jn_age: float, first_year: int, dna: float, peak: float, conc: float) -> str:
    barb = BARBAULT.get(first_year, "RISING")
    score = 0
    if jn_phase == "waxing":
        score += 2
        if jn_age < 120:
            score += 1
    else:
        if jn_age > 300:
            score -= 1
    if barb == "RISING":
        score += 1
    if dna >= 20:
        score += 1
    if peak >= 8:
        score += 1
    if conc >= 24:
        score += 1
    if score >= 5:
        return "SUSTAINED"
    if score >= 4:
        return "SUSTAINED_MOD"
    if score >= 3:
        return "MODERATE"
    if jn_phase == "waning" and jn_age > 300:
        return "TERMINAL_SPIKE"
    if jn_phase == "waning":
        return "SPIKE"
    return "MODERATE_WEAK"


def pre_cult_bucket(window: str, total_dna: float, peak: float, conc: float, already_cult: bool = False) -> str:
    if already_cult:
        return "ALREADY_CULT"
    if total_dna >= 22 and window == "IMMINENT" and (peak >= 7 or conc >= 22):
        return "PRE_CULT_IMMINENT"
    if total_dna >= 20 and window in ("IMMINENT", "SOONER") and (peak >= 6 or conc >= 18):
        return "PRE_CULT_12M"
    if total_dna >= 18 and window in ("SOONER", "MEDIUM"):
        return "PRE_CULT_YEARS"
    return "PRE_CULT_LONGDATED"


def asymmetry_scores(row: dict) -> tuple[float, float, float, str]:
    timing_window = {"IMMINENT": 1.0, "SOONER": 0.8, "MEDIUM": 0.45, "PEAK": 0.25, "DISTANT": 0.1}.get(row["window"], 0.1)
    wax_bonus = 1.0 if row["jn_phase"] == "waxing" else 0.6
    is_imminent = row["window"] == "IMMINENT"
    young_wax = row["jn_phase"] == "waxing" and row["jn_age"] < 120
    age_bonus = 1.1 if young_wax else (0.8 if row["jn_phase"] == "waning" and row["jn_age"] > 300 else 1.0)
    imminent_kicker = 1.20 if is_imminent and young_wax else 1.0
    early = (row["total_dna"] * 0.9 + row["peak"] * 1.2 + row["conc"] * 0.6 + row["jul"] * 0.4) * timing_window * wax_bonus * age_bonus * imminent_kicker

    env = 1.0 if BARBAULT.get(row["first_year"], "RISING") == "RISING" else 0.78
    if is_imminent:
        endurance = 1.0
    else:
        endurance = 1.15 if row["jn_phase"] == "waxing" and row["jn_age"] < 150 else (0.7 if row["jn_phase"] == "waning" and row["jn_age"] > 300 else 0.9)
    enduring = (row["total_dna"] * 1.1 + row["peak"] * 0.8 + row["conc"] * 0.9 + row["era"] * 0.5 + row["jul"] * 0.3) * env * endurance

    total = max(early, enduring)
    if early >= enduring * 1.15:
        label = "EARLY_IMMINENT_ASYMMETRY"
    elif enduring >= early * 1.15:
        label = "ENDURING_HIGH_MAGNITUDE_ASYMMETRY"
    else:
        label = "BALANCED_ASYMMETRY"
    return early, enduring, total, label


# ----------------------------
# Universe loaders and year sweep
# ----------------------------

def load_ipos(expanded_path: str | None = None, ritter_path: str | None = None, extra_rows: list[tuple[str, str, str]] | None = None) -> list[dict]:
    rows = []
    seen = set()
    if expanded_path and Path(expanded_path).exists():
        with open(expanded_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row["ticker"]
                if t not in seen:
                    rows.append({"ticker": t, "name": row.get("name", ""), "date": row["date"]})
                    seen.add(t)
    if ritter_path and Path(ritter_path).exists():
        with open(ritter_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row["ticker"]
                if t not in seen and row["date"] >= "1980-01-01":
                    rows.append({"ticker": t, "name": row.get("name", ""), "date": row["date"]})
                    seen.add(t)
    if extra_rows:
        for t, n, d in extra_rows:
            if t not in seen:
                rows.append({"ticker": t, "name": n, "date": d})
                seen.add(t)
    return rows


def run_scoring(ipos: list[dict], events: dict | None = None, already_cult: set[str] | None = None) -> tuple[list[dict], dict[str, list[float]]]:
    already_cult = already_cult or DEFAULT_ALREADY
    preliminary = []
    for ipo in ipos:
        try:
            c = compute_chart(ipo["date"])
            robust, r_hits, gate, archetype, founder_flag = robust_core(c)
            if not gate or ipo["ticker"] in already_cult or is_shell(ipo.get("name", "")):
                continue
            semi, l_hits = semi_lunar_bucket(c)
            spec, s_hits = speculative_bonus(c)
            peak, peak_d, conc, fwd_hits, jul, jul_hits = score_forward(c, events)
            era = era_match(c)
            window, first_year = classify_window(fwd_hits)
            total_dna = robust + semi + spec
            preliminary.append({
                "ticker": ipo["ticker"], "name": (ipo.get("name") or "").strip('"'), "date": ipo["date"],
                "robust": robust, "semi": semi, "spec": spec, "total_dna": total_dna,
                "era": era, "peak": peak, "conc": conc, "jul": jul,
                "window": window, "first_year": first_year,
                "jn_phase": c["_jn_phase"], "jn_age": c["_jn_age"], "jn_bucket": c["_jn_bucket"],
                "phase": c["_phase"], "archetype": "/".join(sorted(archetype)),
                "nep_return": c["_nep_return"], "nep_orb": c["_nep_return_orb"],
                "eq_sol": c["_equinox_solstice"], "founder_flag": founder_flag,
                "r_hits": r_hits, "l_hits": l_hits, "s_hits": s_hits,
                "fwd_hits": fwd_hits[:8], "peak_d": peak_d, "jul_hits": jul_hits[:4],
            })
        except Exception:
            continue

    stats = {
        "dna": [r["total_dna"] for r in preliminary],
        "fwd": [r["peak"] * 0.6 + r["conc"] * 0.4 for r in preliminary],
        "era": [r["era"] for r in preliminary],
        "jul": [r["jul"] for r in preliminary],
    }
    for r in preliminary:
        r["comp"] = composite_v8_1(r["robust"], r["semi"], r["spec"], r["peak"], r["conc"], r["era"], r["jul"], stats)
        r["rally"] = classify_rally(r["jn_phase"], r["jn_age"], r["first_year"], r["total_dna"], r["peak"], r["conc"])
        r["pre_cult"] = pre_cult_bucket(r["window"], r["total_dna"], r["peak"], r["conc"], r["ticker"] in already_cult)
        early, enduring, asym, asym_label = asymmetry_scores(r)
        r["asym_early"] = early
        r["asym_enduring"] = enduring
        r["asym_total"] = asym
        r["asym_label"] = asym_label

    preliminary.sort(key=lambda r: (-r["asym_total"], -r["comp"], -r["total_dna"], r["date"], r["ticker"]))
    return preliminary, stats


def business_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def sweep_theoretical_dates(start: str = "1980-01-01", end: str = "2025-12-31", top_n: int = 250) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    for d in business_days(date.fromisoformat(start), date.fromisoformat(end)):
        c = compute_chart(d.isoformat())
        robust, _, gate, _, _ = robust_core(c)
        semi, _ = semi_lunar_bucket(c)
        total = robust + semi
        if gate:
            rows.append({
                "date": d.isoformat(),
                "year": d.year,
                "robust": robust,
                "semi": semi,
                "total": total,
                "jn_phase": c["_jn_phase"],
                "jn_age": c["_jn_age"],
                "phase": c["_phase"],
                "key": "",
            })
    df = pd.DataFrame(rows).sort_values(["total", "robust"], ascending=[False, False]).reset_index(drop=True)
    top = df.head(top_n).copy()
    single = df.groupby("year", as_index=False).agg(best_date=("date", "first"), best_score=("total", "max")).sort_values("best_score", ascending=False)
    density_rows = []
    for yr, grp in df.groupby("year"):
        vals = grp["total"].sort_values(ascending=False).tolist()[:5]
        density_rows.append({"year": yr, "density_score": mean(vals), "count_top5": len(vals)})
    density = pd.DataFrame(density_rows).sort_values("density_score", ascending=False)
    return top, single, density


def nearest_matches(theoretical_dates: pd.DataFrame, ipos: list[dict], max_gap_days: int = 5) -> pd.DataFrame:
    ipo_df = pd.DataFrame(ipos).copy()
    ipo_df["date_dt"] = pd.to_datetime(ipo_df["date"])
    out = []
    for _, row in theoretical_dates.iterrows():
        td = pd.to_datetime(row["date"])
        gaps = (ipo_df["date_dt"] - td).abs().dt.days
        best_idx = gaps.idxmin()
        if pd.notna(best_idx) and int(gaps.loc[best_idx]) <= max_gap_days:
            m = ipo_df.loc[best_idx]
            out.append({
                "theoretical_date": row["date"],
                "theoretical_score": row["total"],
                "ticker": m["ticker"],
                "name": m.get("name", ""),
                "ipo_date": m["date"],
                "gap_days": int(gaps.loc[best_idx]),
            })
    return pd.DataFrame(out).sort_values(["theoretical_score", "gap_days"], ascending=[False, True]).reset_index(drop=True)


# ----------------------------
# CLI / export
# ----------------------------

def load_events(path: str | None) -> dict:
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def export_results(results: list[dict], output_csv: str):
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "rank", "ticker", "name", "ipo_date", "robust_dna", "semi_lunar", "spec_bonus", "total_dna",
            "era", "jul26", "peak", "conc", "composite", "asym_early", "asym_enduring", "asym_total", "asym_label",
            "pre_cult", "window", "rally_type", "jn_phase", "jn_age", "jn_bucket", "lunar_phase", "archetype",
            "neptune_return", "nep_return_orb", "equinox_solstice", "founder_flag",
            "key_robust_hit", "key_lunar_hit", "key_spec_hit", "peak_event", "jul26_hits",
        ])
        for i, r in enumerate(results, start=1):
            peak_desc = r["peak_d"].get("desc", "") if isinstance(r["peak_d"], dict) else ""
            w.writerow([
                i, r["ticker"], r["name"], r["date"],
                f"{r['robust']:.1f}", f"{r['semi']:.1f}", f"{r['spec']:.1f}", f"{r['total_dna']:.1f}",
                f"{r['era']:.1f}", f"{r['jul']:.1f}", f"{r['peak']:.1f}", f"{r['conc']:.1f}", f"{r['comp']:.1f}",
                f"{r['asym_early']:.1f}", f"{r['asym_enduring']:.1f}", f"{r['asym_total']:.1f}", r["asym_label"],
                r["pre_cult"], r["window"], r["rally"], r["jn_phase"], f"{r['jn_age']:.0f}", r["jn_bucket"], r["phase"], r["archetype"],
                r["nep_return"], f"{r['nep_orb']:.2f}", r["eq_sol"], r["founder_flag"],
                r["r_hits"][0][:80] if r["r_hits"] else "",
                r["l_hits"][0][:80] if r["l_hits"] else "",
                r["s_hits"][0][:80] if r["s_hits"] else "",
                peak_desc[:80], "; ".join(r["jul_hits"][:4]),
            ])


def main():
    expanded = os.environ.get("RA_EXPANDED", "/home/claude/ipos_expanded.csv")
    ritter = os.environ.get("RA_RITTER", "/home/claude/ritter_full.csv")
    events_path = os.environ.get("RA_EVENTS", "/home/claude/forward_events.json")
    output_dir = Path(os.environ.get("RA_OUTDIR", "/mnt/user-data/outputs"))
    extra_ritter = [
        ("RUBI", "Rubicon Project", "2014-04-02"),
        ("EXA", "Exa Corp", "2012-06-28"),
        ("SLTN", "Solectron", "1989-11-15"),
        ("IMGN", "ImmunoGen", "1989-11-16"),
        ("CMLE", "Casual Male", "1988-09-20"),
        ("NRGN", "Neurogen", "1989-10-03"),
        ("LEND", "Accredited Home Lenders", "2003-02-14"),
    ]

    ipos = load_ipos(expanded, ritter, extra_ritter)
    events = load_events(events_path)
    results, _stats = run_scoring(ipos, events)

    export_results(results, str(output_dir / "reverse_arch_v8_1_asymmetry.csv"))

    do_sweep = os.environ.get("RA_SWEEP", "1") == "1"
    if do_sweep:
        sweep_start = os.environ.get("RA_SWEEP_START", "1980-01-01")
        sweep_end = os.environ.get("RA_SWEEP_END", "2025-12-31")
        top_theoretical, best_years_single, best_years_density = sweep_theoretical_dates(sweep_start, sweep_end, 250)
        top_theoretical.to_csv(output_dir / "reverse_arch_theoretical_dates_1980_2025_v8_1.csv", index=False)
        best_years_single.to_csv(output_dir / "reverse_arch_best_years_single_v8_1.csv", index=False)
        best_years_density.to_csv(output_dir / "reverse_arch_best_years_density_v8_1.csv", index=False)
        nearest = nearest_matches(top_theoretical.head(100), ipos)
        nearest.to_csv(output_dir / "reverse_arch_nearest_matches_v8_1.csv", index=False)

    def top_bucket(label: str, n: int = 15):
        return [r for r in results if r["asym_label"] == label][:n]

    print(f"Universe: {len(ipos)}")
    print(f"Gate-passed: {len(results)}")
    print("\nBest risk/reward asymmetry — EARLY / IMMINENT")
    for i, r in enumerate(top_bucket("EARLY_IMMINENT_ASYMMETRY"), start=1):
        print(f"{i:2d}. {r['ticker']:<8s} asym={r['asym_total']:.1f} window={r['window']:<9s} pre_cult={r['pre_cult']:<18s} dna={r['total_dna']:.1f} peak={r['peak']:.1f} conc={r['conc']:.1f} {r['date']}")

    print("\nBest risk/reward asymmetry — ENDURING / HIGH MAGNITUDE")
    for i, r in enumerate(top_bucket("ENDURING_HIGH_MAGNITUDE_ASYMMETRY"), start=1):
        print(f"{i:2d}. {r['ticker']:<8s} asym={r['asym_total']:.1f} window={r['window']:<9s} rally={r['rally']:<14s} dna={r['total_dna']:.1f} peak={r['peak']:.1f} conc={r['conc']:.1f} {r['date']}")

    if do_sweep:
        print("\nBest years by strongest single date")
        print(best_years_single.head(10).to_string(index=False))
        print("\nBest years by density of strong dates")
        print(best_years_density.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
