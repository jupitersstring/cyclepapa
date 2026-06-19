"""Grand-unified ranker across the entire 6,164-name universe.

The problem: we have 8+ separate rankers (unified_composite,
informational_buys, bastian_forcing, PSU_ARCHETYPES, special_situations
_unified, psu_asymmetric_full, psu_valcreate, ASYMMETRIC_BY_ARCHETYPE)
and 6 data layers. Only 80 of 6,164 tickers have all 6 layers
populated, so the existing rankings are biased toward well-enriched
names rather than truly asymmetric ones.

This module:
  1. Walks the full universe (cancel_10b5_1.json = 6,164 tickers, the
     authoritative US-listed set).
  2. Joins every signal layer per ticker, recording WHICH layers have
     real data and which are missing.
  3. Computes a COVERAGE-NORMALISED score so a name with strong signals
     on 4 layers isn't penalised for missing 2.
  4. Tiers the universe (A: all six layers; B: 4-5; C: <4).
  5. Outputs three artifacts:
       grand_unified_ranked.csv       full ranking with coverage flags
       coverage_matrix.csv            per-ticker layer-presence matrix
       gap_fill_priority.csv          Tier-C names where score-so-far
                                      already suggests asymmetry --
                                      these are the most-worth-enriching
                                      tickers (highest expected lift
                                      from running buyback_verify /
                                      yfinance / form4 on them).

Compares top-50 grand_unified vs existing rankers and reports
disagreements -- the "what was previously hidden by data sparsity"
diff.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


# ----------------------------------------------------------------------
# Layer loaders -- each returns ticker -> raw signal value
# ----------------------------------------------------------------------

def load_proxy() -> dict:
    out: dict = {}
    for fn in sorted(ROOT.glob("proxy_scan*.json")):
        try:
            d = json.loads(fn.read_text())
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if not isinstance(r, dict):
                continue
            tk = r.get("ticker")
            if tk and (tk not in out
                       or r.get("filing_date", "") > out[tk].get("filing_date", "")):
                out[tk] = r
    return out


def load_overlays() -> dict:
    return {
        "proxy": load_proxy(),
        "yf": json.loads((ROOT / "yfinance_quick.json").read_text())
              if (ROOT / "yfinance_quick.json").exists() else {},
        "bb": json.loads((ROOT / "buyback_verify.json").read_text())
              if (ROOT / "buyback_verify.json").exists() else {},
        "tender": json.loads((ROOT / "tender_scan.json").read_text())
                  if (ROOT / "tender_scan.json").exists() else {},
        "c10": json.loads((ROOT / "cancel_10b5_1.json").read_text())
               if (ROOT / "cancel_10b5_1.json").exists() else {},
        "f4": json.loads((ROOT / "form4_buys.json").read_text())
              if (ROOT / "form4_buys.json").exists() else {},
        "f144": json.loads((ROOT / "form144_scan.json").read_text())
                if (ROOT / "form144_scan.json").exists() else {},
    }


# ----------------------------------------------------------------------
# Per-layer scoring -- each returns (points, has_data_bool, reason str)
# ----------------------------------------------------------------------

def score_psu(p: dict) -> tuple[float, bool, str]:
    """Governance + PSU scoring.

    Crucially: has_data is True whenever we have a proxy row at all
    (i.e. we scraped the DEF 14A), NOT only when psu_core > 0. A
    company can legitimately have zero PSU program but still be
    governance-scored (clawback, anti-hedge, vesting, CIC). Earlier
    bug penalised ~1,989 no-PSU companies as "no governance data."
    """
    if not p:
        return 0.0, False, ""
    # Any proxy row at all = we scored the DEF 14A
    has_data = bool(p.get("accession") or p.get("filing_date")
                    or p.get("gov_score") is not None
                    or p.get("psu_core") is not None
                    or p.get("has_psu_program") is not None)
    s = 0.0
    reasons = []
    core = p.get("psu_core") or 0
    s += min(core * 0.4, 25)  # cap at 25
    if core >= 50: reasons.append(f"PSU core {core:.0f}")
    cc = p.get("cond_cats") or []
    fwd_event = {
        "revenue_dollar_target": 12, "ebitda_dollar_target": 12,
        "fcf_dollar_target": 12, "operating_margin_target": 10,
        "fda_phase_milestone": 10, "merger_acquisition_close": 12,
        "spin_separation": 10, "asset_sale_named": 12,
        "debt_leverage_target": 10, "restructuring_milestone": 12,
        "chapter11_emergence": 15, "backlog_target": 8,
        "subscriber_arr_target": 8,
    }
    for cat in cc:
        if cat in fwd_event:
            s += fwd_event[cat]
            reasons.append(f"+{fwd_event[cat]} PSU.{cat}")
    pct = p.get("psu_pct_lti") or 0
    if pct >= 80: s += 8; reasons.append(f"PSU%LTI={pct}")
    elif pct >= 60: s += 4
    gov = p.get("gov_score") or 0
    s += min(gov * 0.5, 12)
    if gov >= 15: reasons.append(f"gov {gov:.0f}")
    return round(s, 1), has_data, "; ".join(reasons)


def score_yf(y: dict) -> tuple[float, bool, str]:
    if not y or not y.get("price"):
        return 0.0, False, ""
    s = 0.0; reasons = []
    pb = y.get("p_b")
    if pb is not None and 0 < pb < 0.5:
        s += 20; reasons.append(f"P/B {pb:.2f}")
    elif pb is not None and 0 < pb < 1.0:
        s += 12; reasons.append(f"P/B {pb:.2f}")
    elif pb is not None and 0 < pb < 1.5:
        s += 5
    px, hi = y.get("price"), y.get("fwk_high")
    if px and hi and hi > 0:
        dd = (1 - px / hi) * 100
        if dd > 80: s += 8; reasons.append(f"DD {dd:.0f}%")
        elif dd > 60: s += 4
    mcap = y.get("mcap")
    if mcap and mcap < 100e6:
        s += 5; reasons.append("microcap")
    return round(s, 1), True, "; ".join(reasons)


def score_bb(b: dict) -> tuple[float, bool, str]:
    if not b or b.get("status") in (None, "UNKNOWN"):
        return 0.0, False, ""
    pts = b.get("points") or 0
    status = b.get("status")
    chg = (b.get("share_change") or {}).get("change_pct")
    reason = f"buyback {status}" + (f" {chg:+.1f}%" if chg is not None else "")
    return float(pts), True, reason


def score_tender(t: dict) -> tuple[float, bool, str]:
    if not isinstance(t, dict):
        return 0.0, False, ""
    role = t.get("role")
    if role not in ("SELF_TENDER", "TARGET", "BIDDER"):
        if t.get("has_13e3"):
            return 15.0, True, "13E-3 going-private"
        return 0.0, False, ""
    role_pts = {"SELF_TENDER": 25, "TARGET": 25, "BIDDER": 8}[role]
    extra = 15 if t.get("has_13e3") else 0
    return float(role_pts + extra), True, f"tender {role}" + (" +13E-3" if extra else "")


def score_c10(c: dict) -> tuple[float, bool, str]:
    if not isinstance(c, dict):
        return 0.0, False, ""
    signed = c.get("signed_score")
    if signed is None:
        return 0.0, False, ""
    # cap absolute contribution at 25 (matches composite weighting)
    if signed > 0:
        return min(signed, 25), True, f"10b5-1 term_sell +{signed:.0f}"
    elif signed < 0:
        return max(signed * 0.6, -15), True, f"10b5-1 adopt_sell {signed:.0f}"
    return 0.0, True, ""


def score_f4(f: dict) -> tuple[float, bool, str]:
    if not isinstance(f, dict):
        return 0.0, False, ""
    cluster = f.get("max_cluster_size") or 0
    musd = f.get("total_musd") or 0
    if cluster == 0 and musd == 0:
        return 0.0, True, ""
    s = min(cluster * 4, 20)
    if musd >= 5: s += 8
    elif musd >= 1: s += 4
    reason = f"F4 cluster {cluster}" + (f" / ${musd:.1f}M" if musd else "")
    return round(s, 1), True, reason


def score_f144(f: dict) -> tuple[float, bool, str]:
    """Form 144 (proposed sales) is BEARISH -- negative contribution."""
    if not isinstance(f, dict):
        return 0.0, False, ""
    pts = f.get("points")
    if pts is None:
        return 0.0, False, ""
    return float(pts), True, f"Form144 {pts:+.0f}"


# ----------------------------------------------------------------------
# Main ranker
# ----------------------------------------------------------------------

def rank() -> tuple[list[dict], list[dict]]:
    ov = load_overlays()
    universe = set()
    for k in ("c10", "tender"):
        universe.update(ov[k].keys())
    # also any from proxy/yf/f4 (in case of disjoint tickers)
    for k in ("proxy", "yf", "bb", "f4", "f144"):
        universe.update(ov[k].keys())
    universe = {tk for tk in universe if tk and not tk.startswith("CIK")}
    print(f"universe size: {len(universe)}")

    rows = []
    for tk in universe:
        p = ov["proxy"].get(tk, {})
        y = ov["yf"].get(tk, {})
        b = ov["bb"].get(tk, {})
        t = ov["tender"].get(tk, {})
        c = ov["c10"].get(tk, {})
        f = ov["f4"].get(tk, {})
        f144 = ov["f144"].get(tk, {})

        psu_pts, psu_has, psu_r = score_psu(p)
        yf_pts, yf_has, yf_r = score_yf(y)
        bb_pts, bb_has, bb_r = score_bb(b)
        td_pts, td_has, td_r = score_tender(t)
        c10_pts, c10_has, c10_r = score_c10(c)
        f4_pts, f4_has, f4_r = score_f4(f)
        f144_pts, f144_has, f144_r = score_f144(f144)

        has_flags = [psu_has, yf_has, bb_has, td_has, c10_has, f4_has, f144_has]
        n_has = sum(has_flags)

        raw_total = (psu_pts + yf_pts + bb_pts + td_pts
                     + c10_pts + f4_pts + f144_pts)

        # Coverage-normalised score: rescale by 7/n_has if at least 3
        # layers have data, so a name with strong 4-of-7 isn't drowned
        # out by a name with mediocre 7-of-7. Names with <3 layers get
        # raw score only (insufficient evidence to normalise).
        if n_has >= 3:
            norm_total = round(raw_total * (7.0 / n_has) ** 0.5, 1)
        else:
            norm_total = round(raw_total, 1)

        tier = "A" if n_has >= 6 else ("B" if n_has >= 4 else "C")

        reasons = [r for r in (psu_r, yf_r, bb_r, td_r, c10_r, f4_r, f144_r) if r]

        rows.append({
            "ticker": tk,
            "tier": tier,
            "n_layers": n_has,
            "raw_score": round(raw_total, 1),
            "norm_score": norm_total,
            "psu": round(psu_pts, 1),
            "valuation": round(yf_pts, 1),
            "buyback": round(bb_pts, 1),
            "tender": round(td_pts, 1),
            "c10b51": round(c10_pts, 1),
            "f4_buys": round(f4_pts, 1),
            "f144": round(f144_pts, 1),
            "has_psu": int(psu_has),
            "has_yf": int(yf_has),
            "has_bb": int(bb_has),
            "has_tender": int(td_has),
            "has_c10": int(c10_has),
            "has_f4": int(f4_has),
            "has_f144": int(f144_has),
            "reasons": " | ".join(reasons),
        })

    rows.sort(key=lambda r: -r["norm_score"])

    # Tier-C gap-fill priority: names with raw_score > median where
    # adding 1-2 missing layers could materially change the rank.
    median_raw = sorted([r["raw_score"] for r in rows])[len(rows) // 2]
    gap_fill = [r for r in rows if r["tier"] == "C"
                and r["raw_score"] >= max(median_raw, 15)]
    # rank gap-fills by raw_score so the most-asymmetric-already names
    # are surfaced first for enrichment
    gap_fill.sort(key=lambda r: -r["raw_score"])

    return rows, gap_fill


def main() -> int:
    rows, gap_fill = rank()

    # Full ranked output
    out = ROOT / "grand_unified_ranked.csv"
    fieldnames = ["ticker", "tier", "n_layers", "raw_score", "norm_score",
                  "psu", "valuation", "buyback", "tender", "c10b51",
                  "f4_buys", "f144",
                  "has_psu", "has_yf", "has_bb", "has_tender",
                  "has_c10", "has_f4", "has_f144", "reasons"]
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")

    # Coverage matrix (compact, just the has_* flags + tier)
    cov = ROOT / "coverage_matrix.csv"
    with cov.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "ticker", "tier", "n_layers",
            "has_psu", "has_yf", "has_bb", "has_tender",
            "has_c10", "has_f4", "has_f144"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in [
                "ticker", "tier", "n_layers",
                "has_psu", "has_yf", "has_bb", "has_tender",
                "has_c10", "has_f4", "has_f144"]})
    print(f"wrote {cov} ({len(rows)} rows)")

    # Gap-fill priority list
    gf = ROOT / "gap_fill_priority.csv"
    with gf.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(gap_fill)
    print(f"wrote {gf} ({len(gap_fill)} Tier-C names worth enriching)")

    # Tier distribution
    from collections import Counter
    tiers = Counter(r["tier"] for r in rows)
    print(f"\nTier distribution: A={tiers['A']}  B={tiers['B']}  C={tiers['C']}")
    print(f"Layer-coverage histogram:")
    nl = Counter(r["n_layers"] for r in rows)
    for n in sorted(nl):
        print(f"  {n} layers: {nl[n]} names")

    # Top 25 from grand_unified (norm score)
    print(f"\n=== TOP 25 grand_unified (norm score) ===")
    print(f"{'TKR':<8}{'TIER':<5}{'NL':<3}{'NORM':<7}{'RAW':<6}{'REASONS'}")
    for r in rows[:25]:
        print(f"{r['ticker']:<8}{r['tier']:<5}{r['n_layers']:<3}"
              f"{r['norm_score']:<7}{r['raw_score']:<6}"
              f"{r['reasons'][:120]}")

    # Compare against unified_composite top-50
    try:
        uc = ROOT / "unified_composite.csv"
        if uc.exists():
            comp_top = []
            for r in csv.DictReader(uc.open()):
                comp_top.append(r["ticker"])
                if len(comp_top) >= 50:
                    break
            grand_top = [r["ticker"] for r in rows[:50]]
            in_both = set(comp_top) & set(grand_top)
            only_grand = [tk for tk in grand_top if tk not in set(comp_top)]
            only_comp = [tk for tk in comp_top if tk not in set(grand_top)]
            print(f"\n=== Top-50 disagreement ===")
            print(f"  in both:        {len(in_both)}")
            print(f"  only grand:     {len(only_grand)}  {only_grand[:15]}")
            print(f"  only composite: {len(only_comp)}  {only_comp[:15]}")
    except Exception as e:
        print(f"comparison skipped: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
