"""
Silas single-equity nuances — the two publicly-documented mechanisms our
engine lacked:

(1) ECLIPSE-DEGREE REACTIVATION ("be prepared knowing when astrology
    transits come"): an eclipse that hit the IPO chart leaves its DEGREE
    sensitive; the price event often fires later, when a transiting
    planet (esp. Mars/Jupiter/Saturn) crosses that eclipse degree.
    -> eclipse_reactivations(natal, eclipse_db, y, m): eclipses within
       lookback that hit natal points, whose degree is being transited
       within orb THIS month.

(2) ECLIPSE AS EXIT TIMER: eclipses time exits as well as entries. A
    fresh eclipse hitting the chart while a position is at/near its
    predicted peak is an exit trigger, not an accumulation signal.
    -> eclipse_exit_flag(natal, eclipse_db, y, m, in_rally=True)

Orb notes: Silas does not publish orbs. We keep our engine's <=3° for
eclipse-to-natal (inside the community's 1-5° range) and use <=2° for
transit-to-eclipse-degree reactivation (tighter, since a degree point is
a single sensitive point, not a body).
"""
import swisseph as swe
from bti_test import jd_of

PIDS = {"Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")

def _orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def _hard_orb(a, b):
    best = 99
    for asp in (0, 90, 180):
        for s in (+1, -1):
            o = _orb(a, b + s*asp)
            if o < best: best = o
    return best

def eclipse_hits(natal, eclipse_db, jd_now, months_back=24, natal_orb=3.0):
    """Eclipses in the past `months_back` months whose degree fell within
    `natal_orb` (conj/sq/opp) of a natal Sun/Moon/ASC/MC. Returns
    [{'jd','lon','type','natal_pt','orb'}]."""
    out = []
    lookback_jd = jd_now - months_back * 30.44
    for e in eclipse_db:
        if not (lookback_jd <= e["jd"] <= jd_now):
            continue
        for pt in NATAL_PTS:
            if pt not in natal: continue
            o = _hard_orb(e["lon"], natal[pt]["lon"])
            if o <= natal_orb:
                out.append({"jd": e["jd"], "lon": e["lon"],
                            "type": e.get("type", e.get("eclipse_type","")),
                            "natal_pt": pt, "orb": o})
    return out

def eclipse_reactivations(natal, eclipse_db, y, m, months_back=24,
                          natal_orb=3.0, react_orb=2.0):
    """Silas nuance (1): past eclipses that hit the chart AND whose degree
    is being crossed by a transiting Mars/Jupiter/Saturn (or outer) THIS
    month. These are the months the deferred eclipse-event tends to fire.
    Returns [{'eclipse':..., 'transiter':name, 'react_orb':deg}]."""
    jd_now = jd_of(y, m, 15, 12.0)
    hits = eclipse_hits(natal, eclipse_db, jd_now, months_back, natal_orb)
    if not hits:
        return []
    lons = {p: swe.calc_ut(jd_now, pid)[0][0] % 360 for p, pid in PIDS.items()}
    out = []
    for h in hits:
        for p, lon in lons.items():
            o = _orb(lon, h["lon"])  # conjunction to the eclipse DEGREE
            if o <= react_orb:
                out.append({"eclipse": h, "transiter": p, "react_orb": o})
    return out

def eclipse_exit_flag(natal, eclipse_db, y, m, fresh_months=2, natal_orb=3.0):
    """Silas nuance (2): a FRESH eclipse (within the last `fresh_months`
    months, or the current month) hitting the chart = exit-timing flag
    when already in a rally. Returns list of fresh hits (empty = no flag)."""
    jd_now = jd_of(y, m, 15, 12.0)
    fresh = []
    for h in eclipse_hits(natal, eclipse_db, jd_now + 45,  # include current month's eclipse
                          months_back=fresh_months, natal_orb=natal_orb):
        fresh.append(h)
    return fresh

def silas_bonus(natal, eclipse_db, y, m):
    """Composite scoring hook: +1.0 per reactivation (capped 2.0) as a
    bottom/ignition bonus; returns (bonus, exit_flag_count)."""
    reacts = eclipse_reactivations(natal, eclipse_db, y, m)
    bonus = min(2.0, 1.0 * len(reacts))
    exits = eclipse_exit_flag(natal, eclipse_db, y, m)
    return bonus, len(exits)

if __name__ == "__main__":
    from eclipse_database import build_eclipse_database
    from bti_test import compute_natal
    db = build_eclipse_database(2020, 2030)
    # normalize db entries to dicts with jd/lon/type if needed
    sample = db[0] if db else None
    print(f"eclipse db entries: {len(db)}; sample keys: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}")
    natal = compute_natal("2024-03-21")  # RDDT
    reacts = eclipse_reactivations(natal, db, 2026, 7)
    print(f"RDDT reactivations Jul 2026: {len(reacts)}")
    for r in reacts[:5]:
        print(f"  {r['transiter']} crossing eclipse deg {r['eclipse']['lon']:.1f} "
              f"(hit natal {r['eclipse']['natal_pt']} orb {r['eclipse']['orb']:.1f}°), react orb {r['react_orb']:.1f}°")
