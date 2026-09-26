"""Reconcile original 10 archetypes against the empirical re-rank.

For each archetype:
  - members (preserved from original ARCHETYPES dict in build_archetype_workbook.py)
  - per-member current status: LIVE-T1 / LIVE-T2 / DEMOTED / RERATED / DEAD / GRADUATED
  - best surviving member's expected_return
  - archetype-level verdict: SUPPORTED / WEAK / EMPIRICALLY-DISPROVED / EMPTIED

Writes archetype_status table + console summary.
"""
import os, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# 10 archetypes -> the behavioral factor that best maps to each
ARCH_TO_FACTOR = {
    "1. Yartseva Pure Multibagger":           "smart_money_uw",     # +17%
    "2. Activist Board Catalyst":             "activist_13d",       # -26% — empirically weak
    "3. Biotech Multi-Fund Convergence":      "EXCLUDED",            # user mandate
    "4. Sponsor-Anchored Holdco Transformation": "sponsor_anchor",  # +17% proxy
    "5. Spinoff / SoTP Arbitrage":            "spin_arb",           # +10% proxy
    "6. Deep Drawdown Mean Reversion":        "smart_money_uw",     # +17%
    "7. Hard Asset / Royalty":                "family_anchor",      # +17% proxy
    "8. Foreign / Underfollowed Value":       "deep_value",         # 0%
    "9. Quality Compounder at Trough":        "post_acquisition",   # 0%
    "10. Hedged / Special Structure":         "EXCLUDED",            # warrant-class, retired
}

def status_for(tkr, c, candidates_map, er_map):
    cand = candidates_map.get(tkr)
    if not cand:
        return "UNTRACKED"
    tier = cand["tier"] or ""
    ver = cand["verification_status"] or ""
    if "DEAD" in ver or "DEAD" in tier: return "DEAD"
    if "KILLED" in tier: return "GRADUATED"   # rerated / thesis killed
    if "DEMOTED" in tier or "WEAKENED" in tier: return "DEMOTED"
    er = er_map.get(tkr, {}).get("er")
    if er is not None and er >= 0.30: return "LIVE-T1"
    if er is not None and er >= 0.0:  return "LIVE-T2"
    if er is not None and er < 0.0:   return "LIVE-T3"
    if tier.startswith("1"): return "LIVE-T1"
    if tier.startswith("2"): return "LIVE-T2"
    if tier.startswith("3"): return "LIVE-T3"
    if "bio" in tier:        return "EXCLUDED-BIOTECH"
    return f"TIER={tier}"

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS archetype_status;
    CREATE TABLE archetype_status (
      archetype TEXT PRIMARY KEY,
      mapped_factor TEXT, base_rate_excess REAL,
      members_total INTEGER, members_live_t1 INTEGER, members_live_t2 INTEGER,
      members_live_t3 INTEGER, members_demoted INTEGER, members_graduated INTEGER,
      members_dead INTEGER, members_untracked INTEGER, members_excluded INTEGER,
      best_member TEXT, best_member_er REAL, verdict TEXT);
    CREATE TABLE IF NOT EXISTS archetype_member_status (
      archetype TEXT, ticker TEXT, status TEXT, er REAL, factor_tags TEXT,
      thesis TEXT, PRIMARY KEY (archetype, ticker));
    """)
    conn.execute("DELETE FROM archetype_status")
    conn.execute("DELETE FROM archetype_member_status")

    candidates_map = {r["ticker"]: dict(r) for r in conn.execute(
        "SELECT ticker, tier, verification_status, factor_tags FROM candidates")}
    er_map = {r["ticker"]: {"er": r["weighted_excess_12m"]} for r in conn.execute(
        "SELECT ticker, weighted_excess_12m FROM expected_return")}
    br = {r["factor"]: r["avg_excess_12m"] for r in conn.execute(
        "SELECT factor, avg_excess_12m FROM base_rates")}
    proxy = {"sponsor_anchor": 0.17, "family_anchor": 0.17, "spin_arb": 0.10,
             "deep_value": 0.0, "post_acquisition": 0.0}

    by_arch = {}
    for r in conn.execute("SELECT archetype, ticker, thesis FROM archetype_members ORDER BY archetype, ticker"):
        by_arch.setdefault(r["archetype"], []).append(dict(r))

    print(f"{'#':<3} {'archetype':<48} {'factor':<24} {'base%':<7} {'live':<6} {'demo':<6} {'grad':<6} {'dead':<6} {'untr':<6} {'verdict'}")
    for arch, members in by_arch.items():
        factor = ARCH_TO_FACTOR.get(arch, "?")
        base = br.get(factor) if factor in br else proxy.get(factor)
        cnt = {"LIVE-T1":0, "LIVE-T2":0, "LIVE-T3":0, "DEMOTED":0, "GRADUATED":0,
               "DEAD":0, "UNTRACKED":0, "EXCLUDED-BIOTECH":0}
        best = None; best_er = None
        for m in members:
            s = status_for(m["ticker"], candidates_map.get(m["ticker"], {}), candidates_map, er_map)
            cnt[s] = cnt.get(s, 0) + 1
            er = er_map.get(m["ticker"], {}).get("er")
            if er is not None and (best_er is None or er > best_er):
                best_er, best = er, m["ticker"]
            conn.execute("""INSERT INTO archetype_member_status VALUES (?,?,?,?,?,?)""",
                         (arch, m["ticker"], s, er,
                          (candidates_map.get(m["ticker"]) or {}).get("factor_tags"),
                          (m["thesis"] or "")[:200]))
        total = len(members)
        live_total = cnt["LIVE-T1"] + cnt["LIVE-T2"]
        if factor == "EXCLUDED": verdict = "EXCLUDED-BY-MANDATE"
        elif base is not None and base < -0.10: verdict = "EMPIRICALLY-WEAK"
        elif live_total == 0 and cnt["GRADUATED"] > total/2: verdict = "GRADUATED-OUT"
        elif live_total == 0: verdict = "EMPTIED"
        elif live_total / total > 0.5: verdict = "SUPPORTED"
        else: verdict = "WEAKENED"
        conn.execute("""INSERT INTO archetype_status VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (arch, factor, base, total, cnt["LIVE-T1"], cnt["LIVE-T2"],
                      cnt["LIVE-T3"], cnt["DEMOTED"], cnt["GRADUATED"], cnt["DEAD"],
                      cnt["UNTRACKED"], cnt["EXCLUDED-BIOTECH"], best, best_er, verdict))
        num = arch.split(".")[0]
        nm = arch.split(".", 1)[1].strip()[:46]
        bs = f"{base*100:+.0f}%" if base is not None else "?"
        print(f"  {num:<3} {nm:<48} {factor:<24} {bs:<7} "
              f"{live_total:<6} {cnt['DEMOTED']:<6} {cnt['GRADUATED']:<6} {cnt['DEAD']:<6} "
              f"{cnt['UNTRACKED']:<6} {verdict}  best={best} ({(best_er or 0)*100:+.0f}%)")
    conn.commit()

if __name__ == "__main__":
    run()
