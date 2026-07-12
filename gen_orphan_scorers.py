"""Regenerate the three prior-session scorer CSVs that had no standing
generator (bastian_forcing, psu_valcreate, psu_asymmetric_full).

These were produced inline in earlier sessions and committed as frozen
artifacts. They feed consensus_meta_ranker + grand_unified_ranker +
systematic_rankings, so if proxy_scan / yfinance refresh, they must be
regenerable to stay consistent. This module reconstructs each from
proxy_scan + the yfinance overlay + the tender/buyback/10b5-1 layers,
reproducing the committed schemas exactly.

Run: python3 gen_orphan_scorers.py   (pure-compute, no network)
Outputs: bastian_forcing.csv, psu_valcreate.csv, psu_asymmetric_full.csv
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_proxy() -> dict:
    out = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.loads(open(fn).read())
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if tk not in out or r.get("filing_date", "") > out[tk].get("filing_date", ""):
                    out[tk] = r
    return out


def load_json(fn) -> dict:
    p = ROOT / fn
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


# ----------------------------------------------------------------------
# 1. bastian_forcing.csv — microcap debt-haircut / self-help forcing
#    functions. Schema: ticker,score,mcap_M,px,p_b,psu_core,gov,reasons
# ----------------------------------------------------------------------

def gen_bastian_forcing(proxy, yf, tender, bbv):
    rows = []
    for tk in set(proxy) | set(yf) | set(tender):
        p = proxy.get(tk, {})
        y = yf.get(tk, {}) or {}
        t = tender.get(tk, {}) or {}
        b = bbv.get(tk, {}) or {}
        mcap = _num(y.get("mcap"))
        px = _num(y.get("price"))
        pb = _num(y.get("p_b"))
        if not mcap or mcap > 600e6:      # microcap gate
            continue
        if pb is None or pb > 1.5 or pb < 0:
            continue
        cc = p.get("cond_cats") or []
        score = 0.0
        reasons = []
        if "chapter11_emergence" in cc:
            score += 30; reasons.append("post-Ch11 emergence in PSU")
        if "debt_leverage_target" in cc:
            score += 25; reasons.append("debt-paydown PSU trigger")
        if "restructuring_milestone" in cc:
            score += 25; reasons.append("restructuring milestone PSU")
        if "asset_sale_named" in cc:
            score += 20; reasons.append("named asset-sale PSU")
        if "merger_acquisition_close" in cc:
            score += 15; reasons.append("M&A close trigger")
        if "spin_separation" in cc:
            score += 15; reasons.append("spin trigger")
        role = t.get("role")
        if role == "SELF_TENDER":
            score += 25; reasons.append("issuer SELF_TENDER live")
        elif role == "TARGET":
            score += 25; reasons.append("TARGET live (own 14D-9)")
        elif role == "BIDDER":
            score += 5; reasons.append("outbound bidder")
        if t.get("has_13e3"):
            score += 20; reasons.append("going-private 13E-3 in flight")
        bb_st = b.get("status")
        if bb_st == "EXECUTING":
            chg = (b.get("share_change") or {}).get("change_pct", 0)
            score += 10; reasons.append(f"EXECUTING shrinkage {chg:.1f}%")
        elif bb_st == "SHRINKING_NO_AUTH":
            chg = (b.get("share_change") or {}).get("change_pct", 0)
            score += 8; reasons.append(f"organic shrink {chg:.1f}%")
        if pb < 0.5:
            score += 15; reasons.append(f"P/B {pb:.2f}")
        elif pb < 0.7:
            score += 10; reasons.append(f"P/B {pb:.2f}")
        elif pb < 1.0:
            score += 5; reasons.append(f"P/B {pb:.2f}")
        if score < 25:
            continue
        rows.append({
            "ticker": tk, "score": int(round(score)),
            "mcap_M": round(mcap / 1e6, 0), "px": px, "p_b": pb,
            "psu_core": p.get("psu_core"), "gov": p.get("gov_score"),
            "reasons": "; ".join(reasons),
        })
    rows.sort(key=lambda r: -r["score"])
    _write(rows, "bastian_forcing.csv",
           ["ticker", "score", "mcap_M", "px", "p_b", "psu_core", "gov", "reasons"])
    return len(rows)


# ----------------------------------------------------------------------
# 2. psu_valcreate.csv — per-share value-creation alignment ranking.
# ----------------------------------------------------------------------

def gen_psu_valcreate(proxy, yf):
    RET_ON_CAP = {"roic", "roe", "roce", "cfroi", "other_per_share"}
    rows = []
    for tk, p in proxy.items():
        if not (p.get("psu_core") or p.get("cond_cats")):
            continue
        ps = set(p.get("per_share_metrics") or [])
        agg = set(p.get("aggregate_metrics") or [])
        tier1 = sorted(ps & RET_ON_CAP)
        has_eps = "eps" in ps
        has_tsr = "tsr" in ps
        # aggregate-only penalty: absolute metrics with no per-share pair
        agg_penalty = sorted(a for a in agg
                             if a.startswith("absolute") and not ps)
        gov = p.get("gov_score") or 0
        psu_core = p.get("psu_core") or 0
        pct = p.get("psu_pct_lti") or 0
        fwd = p.get("n_fwd_cond") or 0

        val = 0.0
        val += len(tier1) * 6            # return-on-capital metrics
        if has_eps: val += 5
        if has_tsr: val += 3
        val += min(gov, 21) * 0.5
        val += min(psu_core, 60) * 0.3
        if pct >= 60: val += 6
        elif pct >= 40: val += 3
        val += fwd * 4
        if agg_penalty:
            val -= 6
        if val < 25:
            continue
        notes = (f"return-on-capital: {','.join(tier1)}"
                 + (" | EPS" if has_eps else "")
                 + (" | TSR" if has_tsr else "")
                 + (f" | aggregate penalty" if agg_penalty else "")
                 + " | gov hygiene")
        y = yf.get(tk, {}) or {}
        rows.append({
            "ticker": tk, "valcreate": round(val, 1),
            "tier1_metrics": ",".join(tier1),
            "eps": "EPS" if has_eps else "",
            "tsr": "TSR" if has_tsr else "",
            "aggregate_penalty": ",".join(agg_penalty),
            "psu_pct_lti": p.get("psu_pct_lti"),
            "gov": gov, "fwd": fwd, "psu_core": psu_core,
            "mcap_musd": round((_num(y.get("mcap")) or 0) / 1e6, 0) or "",
            "price": _num(y.get("price")) or "",
            "pb": _num(y.get("p_b")) or "",
            "sector": y.get("sector") or "",
            "filing_date": p.get("filing_date", ""),
            "fwd_snippet": (p.get("fwd_snippets") or [""])[0][:120] if p.get("fwd_snippets") else "",
            "notes": notes,
        })
    rows.sort(key=lambda r: -r["valcreate"])
    _write(rows, "psu_valcreate.csv",
           ["ticker", "valcreate", "tier1_metrics", "eps", "tsr",
            "aggregate_penalty", "psu_pct_lti", "gov", "fwd", "psu_core",
            "mcap_musd", "price", "pb", "sector", "filing_date",
            "fwd_snippet", "notes"])
    return len(rows)


# ----------------------------------------------------------------------
# 3. psu_asymmetric_full.csv — forward-conditional triggers + price
#    ladders + archetype tags.
# ----------------------------------------------------------------------

def gen_psu_asymmetric_full(proxy, yf, c10):
    CAT_LABEL = {
        "revenue_dollar_target": "dollar revenue hurdle",
        "ebitda_dollar_target": "dollar EBITDA hurdle",
        "fcf_dollar_target": "dollar FCF hurdle",
        "operating_margin_target": "operating margin target",
        "merger_acquisition_close": "M&A close",
        "spin_separation": "spin / separation",
        "asset_sale_named": "named asset sale",
        "fda_phase_milestone": "FDA milestone",
        "debt_leverage_target": "debt paydown target",
        "restructuring_milestone": "restructuring milestone",
        "chapter11_emergence": "Ch11 emergence",
        "backlog_target": "backlog target",
        "subscriber_arr_target": "subscriber / ARR target",
    }
    rows = []
    for tk, p in proxy.items():
        cc = p.get("cond_cats") or []
        hurdles = p.get("stock_price_hurdles") or []
        if not cc and not hurdles:
            continue
        y = yf.get(tk, {}) or {}
        px = _num(y.get("price"))
        archetypes = []
        score = 0.0

        # price ladder — apply the documented plausibility cap
        # (MAX_PLAUSIBLE_MULTIPLE = 8.0): tranches implying >8x current
        # price are almost always pre-reverse-split artifacts, not real
        # forward hurdles, and are dropped before scoring.
        MAX_PLAUSIBLE_MULTIPLE = 8.0
        top_x = ""
        if hurdles and px and px > 0:
            plausible = [h for h in hurdles if h / px <= MAX_PLAUSIBLE_MULTIPLE]
            if plausible:
                top = max(plausible)
                mult = top / px
                top_x = round(mult, 1)
                n = len(plausible)
                archetypes.append(
                    f"price ladder {n}-tranche ${min(plausible):.0f}-${top:.0f} "
                    f"({mult:.1f}x spot)")
                if mult >= 5:
                    score += 20
                elif mult >= 3:
                    score += 12
                elif mult >= 2:
                    score += 6

        for cat in cc:
            archetypes.append(CAT_LABEL.get(cat, cat))
            score += 12

        fwd = p.get("n_fwd_cond") or 0
        if fwd:
            archetypes.append(f"{fwd} FORWARD-classified hurdle")
            score += fwd * 6

        # confirmation legs
        confirmations = []
        cd = c10.get(tk, {}) or {}
        c10_score = cd.get("score")
        if c10_score:
            confirmations.append(f"10b5-1 {c10_score:+.0f}")
            score += min(abs(c10_score), 25) * (0.3 if c10_score > 0 else -0.3)

        # Inclusive by design (matches the prior-session artifact):
        # any name carrying a forward-conditional trigger OR a stock-
        # price ladder is a candidate; the score orders them.
        if not archetypes:
            continue
        rows.append({
            "ticker": tk, "score": round(score, 1),
            "archetype_count": len(archetypes),
            "archetypes": " | ".join(archetypes),
            "top_hurdle_x_spot": top_x,
            "psu_core": p.get("psu_core"),
            "gov_score": p.get("gov_score"),
            "psu_pct_lti": p.get("psu_pct_lti"),
            "per_share_metrics": ",".join(p.get("per_share_metrics") or []),
            "mcap_musd": round((_num(y.get("mcap")) or 0) / 1e6, 0) or "",
            "price": px or "",
            "p_b": _num(y.get("p_b")) or "",
            "filing_date": p.get("filing_date", ""),
            "confirmations": "; ".join(confirmations),
            "fwd_snippet": (p.get("fwd_snippets") or [""])[0][:120] if p.get("fwd_snippets") else "",
        })
    rows.sort(key=lambda r: -r["score"])
    _write(rows, "psu_asymmetric_full.csv",
           ["ticker", "score", "archetype_count", "archetypes",
            "top_hurdle_x_spot", "psu_core", "gov_score", "psu_pct_lti",
            "per_share_metrics", "mcap_musd", "price", "p_b",
            "filing_date", "confirmations", "fwd_snippet"])
    return len(rows)


def _write(rows, fn, fieldnames):
    with (ROOT / fn).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    proxy = load_proxy()
    yf = load_json("yfinance_quick.json")
    tender = load_json("tender_scan.json")
    bbv = load_json("buyback_verify.json")
    c10 = load_json("cancel_10b5_1.json")
    print(f"loaded proxy={len(proxy)} yf={len(yf)}")
    n1 = gen_bastian_forcing(proxy, yf, tender, bbv)
    n2 = gen_psu_valcreate(proxy, yf)
    n3 = gen_psu_asymmetric_full(proxy, yf, c10)
    print(f"wrote bastian_forcing.csv ({n1}), psu_valcreate.csv ({n2}), "
          f"psu_asymmetric_full.csv ({n3})")


if __name__ == "__main__":
    main()
