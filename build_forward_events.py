"""Build forward_events.json from swisseph for 2026-01-01 .. 2036-12-31.

Includes:
- solar/lunar eclipses (with star-conjunction tags)
- outer-pair conjunctions (J-S, J-U, J-N, J-P, S-U, S-N, S-P, U-N, U-P, N-P)
- outer-planet sign ingresses (Saturn, Uranus, Neptune, Pluto)
- outer-planet stations (Saturn, Uranus, Neptune, Pluto)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import swisseph as swe

swe.set_ephe_path(None)

OUT_PATH = Path("/home/claude/forward_events.json")
START = (2026, 1, 1)
END = (2036, 12, 31)

PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON,
    "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO,
}

STARS = [
    ("Algol", 56.17), ("Aldebaran", 69.47), ("Betelgeuse", 88.64),
    ("Sirius", 103.67), ("Regulus", 149.83), ("Spica", 203.50),
    ("Antares", 249.47), ("GC", 266.57), ("Vega", 285.17),
    ("Fomalhaut", 303.52), ("Scheat", 359.08),
]
PREC = 0.01397


def orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def jd_of(y, m, d, hr=12.0):
    return swe.julday(y, m, d, hr)


def date_iso(jd):
    y, m, d, _ = swe.revjul(jd)
    return f"{y:04d}-{m:02d}-{int(d):02d}"


def lon_at(jd, body):
    return swe.calc_ut(jd, body)[0][0] % 360


def speed_at(jd, body):
    return swe.calc_ut(jd, body)[0][3]


def star_label(lon: float, jd: float) -> str:
    y, _, _, _ = swe.revjul(jd)
    dy = y - 2000
    best = None
    for nm, sl in STARS:
        sl2 = (sl + PREC * dy) % 360
        o = orb(lon, sl2)
        if o <= 1.5 and (best is None or o < best[1]):
            best = (nm, o)
    return f" near {best[0].upper()}" if best else ""


def find_eclipses():
    out = []
    jd_start = swe.julday(*START, 0.0)
    jd_end = swe.julday(*END, 0.0)
    jd = jd_start
    while jd < jd_end:
        try:
            res = swe.sol_eclipse_when_glob(jd, swe.FLG_SWIEPH, 0, False)
            ecl_type, tret = res[0], res[1]
            tjd = tret[0]
        except Exception as e:
            print("sol err", e)
            break
        if tjd >= jd_end:
            break
        sun_lon = lon_at(tjd, swe.SUN)
        if ecl_type & swe.ECL_TOTAL or ecl_type & swe.ECL_ANNULAR_TOTAL:
            kind = "total_solar"
        elif ecl_type & swe.ECL_ANNULAR:
            kind = "annular_solar"
        elif ecl_type & swe.ECL_PARTIAL:
            kind = "partial_solar"
        else:
            kind = "solar"
        kind += star_label(sun_lon, tjd).replace(" near ", "_NEAR_")
        out.append({"date": date_iso(tjd), "lon": round(sun_lon, 4), "type": kind})
        jd = tjd + 1.0
    jd = jd_start
    while jd < jd_end:
        try:
            res = swe.lun_eclipse_when(jd, swe.FLG_SWIEPH, False)
            ecl_type, tret = res[0], res[1]
            tjd = tret[0]
        except Exception as e:
            print("lun err", e)
            break
        if tjd >= jd_end:
            break
        moon_lon = lon_at(tjd, swe.MOON)
        if ecl_type & swe.ECL_TOTAL:
            kind = "total_lunar"
        elif ecl_type & swe.ECL_PARTIAL:
            kind = "partial_lunar"
        elif ecl_type & swe.ECL_PENUMBRAL:
            kind = "penumbral_lunar"
        else:
            kind = "lunar"
        kind += star_label(moon_lon, tjd).replace(" near ", "_NEAR_")
        out.append({"date": date_iso(tjd), "lon": round(moon_lon, 4), "type": kind})
        jd = tjd + 1.0
    out.sort(key=lambda e: e["date"])
    return out


def find_outer_pair_events():
    out = []
    pairs = [
        ("Jupiter", "Saturn", swe.JUPITER, swe.SATURN),
        ("Jupiter", "Uranus", swe.JUPITER, swe.URANUS),
        ("Jupiter", "Neptune", swe.JUPITER, swe.NEPTUNE),
        ("Jupiter", "Pluto", swe.JUPITER, swe.PLUTO),
        ("Saturn", "Uranus", swe.SATURN, swe.URANUS),
        ("Saturn", "Neptune", swe.SATURN, swe.NEPTUNE),
        ("Saturn", "Pluto", swe.SATURN, swe.PLUTO),
        ("Uranus", "Neptune", swe.URANUS, swe.NEPTUNE),
        ("Uranus", "Pluto", swe.URANUS, swe.PLUTO),
        ("Neptune", "Pluto", swe.NEPTUNE, swe.PLUTO),
    ]
    jd_start = swe.julday(*START, 0.0)
    jd_end = swe.julday(*END, 0.0)
    for n1, n2, p1, p2 in pairs:
        prev_diff = None
        prev_jd = None
        jd = jd_start
        while jd < jd_end:
            l1 = lon_at(jd, p1)
            l2 = lon_at(jd, p2)
            diff = (l1 - l2) % 360
            if diff > 180:
                diff -= 360
            if prev_diff is not None and prev_diff * diff < 0 and abs(prev_diff - diff) < 30:
                lo, hi = prev_jd, jd
                for _ in range(40):
                    mid = (lo + hi) / 2
                    md1 = lon_at(mid, p1)
                    md2 = lon_at(mid, p2)
                    md = (md1 - md2) % 360
                    if md > 180:
                        md -= 360
                    if md * prev_diff > 0:
                        lo = mid
                    else:
                        hi = mid
                conj_jd = (lo + hi) / 2
                conj_lon = lon_at(conj_jd, p1)
                out.append({
                    "date": date_iso(conj_jd),
                    "lon": round(conj_lon, 4),
                    "note": f"{n1}-{n2} conjunction",
                })
            prev_diff = diff
            prev_jd = jd
            jd += 5
    for nm, pid in (("Saturn", swe.SATURN), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)):
        prev_sign = None
        prev_jd = None
        jd = jd_start
        while jd < jd_end:
            lon = lon_at(jd, pid)
            sign = int(lon // 30)
            if prev_sign is not None and sign != prev_sign:
                lo, hi = prev_jd, jd
                target_lon = sign * 30 if sign > prev_sign else prev_sign * 30
                target_lon = target_lon % 360
                for _ in range(40):
                    mid = (lo + hi) / 2
                    ml = lon_at(mid, pid)
                    if int(ml // 30) == prev_sign:
                        lo = mid
                    else:
                        hi = mid
                ing_jd = (lo + hi) / 2
                out.append({
                    "date": date_iso(ing_jd),
                    "lon": round(lon_at(ing_jd, pid), 4),
                    "note": f"{nm} ingress",
                })
            prev_sign = sign
            prev_jd = jd
            jd += 3
    out.sort(key=lambda e: e["date"])
    return out


def find_stations():
    out = []
    jd_start = swe.julday(*START, 0.0)
    jd_end = swe.julday(*END, 0.0)
    for nm, pid in (("Saturn", swe.SATURN), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)):
        prev_speed = None
        prev_jd = None
        jd = jd_start
        while jd < jd_end:
            sp = speed_at(jd, pid)
            if prev_speed is not None and prev_speed * sp < 0:
                lo, hi = prev_jd, jd
                for _ in range(30):
                    mid = (lo + hi) / 2
                    ms = speed_at(mid, pid)
                    if ms * prev_speed > 0:
                        lo = mid
                    else:
                        hi = mid
                stn_jd = (lo + hi) / 2
                kind = "Rx" if prev_speed > 0 else "Dx"
                out.append({
                    "date": date_iso(stn_jd),
                    "lon": round(lon_at(stn_jd, pid), 4),
                    "what": f"{nm}_{kind}",
                })
            prev_speed = sp
            prev_jd = jd
            jd += 1
    out.sort(key=lambda e: e["date"])
    return out


def main():
    eclipses = find_eclipses()
    pair = find_outer_pair_events()
    stations = find_stations()
    payload = {
        "eclipses": eclipses,
        "outer_pair_conj_and_ingress": pair,
        "stations": stations,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"eclipses={len(eclipses)} pair={len(pair)} stations={len(stations)}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
