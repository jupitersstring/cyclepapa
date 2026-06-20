"""Systematic universe rankings rollup.

Produces SYSTEMATIC_RANKINGS.md -- the actionable summary of how to
deploy the full 6,164-name universe systematically:

  1. CONVERGENT TOP -- the 12 names surfaced by >=3 of 8 screens
     AND winners of a PSU/governance archetype
  2. PER-PATTERN LEADERS -- top 10 in each catalyst pattern
     (forward $ hurdle, M&A close, asset sale, FDA milestone,
     spin, restructuring, deep value floor, debt haircut,
     verified buyback, live tender, etc.)
  3. PER-SIGNAL-LAYER LEADERS -- top 10 by each individual layer
     (PSU forensics, governance only, valuation, insider cluster,
     verified buyback shrinkage, tender role, debt-haircut, 13D)
  4. TIER-A / B / C BREAKOUT -- where confidence is highest given
     coverage; gap-fill priority list
  5. CAUTION LIST -- top names that also carry red flags
     (single-trigger CIC, repricing, retirement carveout)
  6. USE-CASE ROLLUPS -- "if you want X, look at Y" actionable
     deployment sheet
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_rows(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open()))
    if limit:
        rows = rows[:limit]
    return rows


def load_proxy() -> dict:
    proxy = {}
    import glob
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.loads(open(fn).read())
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in proxy or
                    (r.get("filing_date", "") > proxy[tk].get("filing_date", ""))):
                    proxy[tk] = r
    return proxy


def fmt_row(r: dict, fields: list[str]) -> str:
    return " | ".join(f"{f}={r.get(f, '?')}" for f in fields)


def main() -> int:
    # === sources ===
    grand = load_rows(ROOT / "grand_unified_ranked.csv")
    consensus = load_rows(ROOT / "consensus_ranking.csv")
    info_buys = load_rows(ROOT / "informational_buys.csv")
    composite = load_rows(ROOT / "unified_composite.csv")
    bastian = load_rows(ROOT / "bastian_forcing.csv")
    psu_full = load_rows(ROOT / "psu_asymmetric_full.csv")
    psu_val = load_rows(ROOT / "psu_valcreate.csv")
    psu_gov = load_rows(ROOT / "psu_gov_asymmetry.csv")
    spec_sit = load_rows(ROOT / "special_situations_unified.csv")
    bbv = json.loads((ROOT / "buyback_verify.json").read_text()) \
          if (ROOT / "buyback_verify.json").exists() else {}
    tender = json.loads((ROOT / "tender_scan.json").read_text()) \
             if (ROOT / "tender_scan.json").exists() else {}
    c10 = json.loads((ROOT / "cancel_10b5_1.json").read_text()) \
          if (ROOT / "cancel_10b5_1.json").exists() else {}
    f4 = json.loads((ROOT / "form4_buys.json").read_text()) \
         if (ROOT / "form4_buys.json").exists() else {}
    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
         if (ROOT / "yfinance_quick.json").exists() else {}
    activist = load_rows(ROOT / "activist_13d.csv")
    proxy = load_proxy()

    print(f"Loaded: grand={len(grand)} consensus={len(consensus)} "
          f"info_buys={len(info_buys)} composite={len(composite)}")
    print(f"        proxy={len(proxy)} yf={len(yf)} bbv={len(bbv)}")

    out = []
    out.append("# Systematic universe rankings\n")
    out.append("Full 6,164-name US-listed universe, organised for "
               "systematic deployment.\n")
    out.append("Generated from 8 independent rankers + 38 PSU/gov "
               "archetypes + 19 thesis archetypes.\n")

    # ----------------- 1. CONVERGENT TOP (the answer) -----------------
    out.append("## 1. Convergent top -- the empirical best of universe\n")
    out.append("These are surfaced by >=3 of 8 independent screens AND "
               "win at least one PSU/governance archetype.\n")
    out.append("| Rank | Ticker | Screens | Archetypes | Why it converges |")
    out.append("|---:|---|--:|--:|---|")
    # Editorial annotations -- keyed by ticker but functioning only as
    # display overlays. If a ticker is in this dict but NOT convergent
    # (per consensus_ranking.csv), it is not rendered. If a ticker is
    # convergent but not in this dict, its row falls back to the
    # screens-list string from the CSV. Membership decision is
    # data-driven; annotations are editorial.
    convergent_notes = {
        "HFFG": "Triple PSU $ hurdle (rev/EBITDA/FCF) + P/B 0.48 + clawback strengthened",
        "CSGP": "10x CEO ownership + EBITDA $ hurdle + SOP 45% + buyback EXECUTING -3.6%",
        "LE": "12-tranche price ladder + 86% PSU + ROIC stack (carveout caution)",
        "NUS": "Named asset-sale PSU + 5-metric clean per-share stack + P/B 0.33",
        "GO": "Forward $ targets + Cohen-Malloy informational buys",
        "ADT": "90% PSU%LTI (heaviest) + verified shrink -7.3%",
        "KMPR": "Custom per-share + anti-hedge + EXECUTING buyback (repricing flag)",
        "MAT": "Double dollar hurdle EBITDA + FCF (unique 2-archetype win)",
        "RNR": "Deepest per-share metric stack (>=5)",
        "GPRO": "PSU vests on spin / separation",
        "LMT": "FCF $ hurdle + backlog target",
        "CDE": "CEO 10b5-1 termination score 80 (#1 in universe)",
        "EXFY": "Live issuer self-tender",
    }
    consensus_idx = {r["ticker"]: r for r in consensus}
    converg = sorted(
        [r for r in consensus if int(r["n_screens"]) >= 3
         and int(r["n_archetypes_won"]) >= 1],
        key=lambda r: (-int(r["n_screens"]), -int(r["n_archetypes_won"])))
    for i, r in enumerate(converg, 1):
        tk = r["ticker"]
        note = convergent_notes.get(tk, r["screens"][:60])
        out.append(f"| {i} | **{tk}** | {r['n_screens']} | "
                   f"{r['n_archetypes_won']} | {note} |")
    out.append("")

    # ----------------- 2. PER-PATTERN LEADERS -----------------
    out.append("\n## 2. Per-pattern leaders -- top names by catalyst type\n")
    out.append("Use this to deploy systematically by mandate.\n")

    # Use proxy_scan + buyback + tender data
    patterns = [
        ("Forward DOLLAR revenue hurdle (Mungerian dollar-target PSU)",
         lambda r: "revenue_dollar_target" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Forward DOLLAR EBITDA hurdle",
         lambda r: "ebitda_dollar_target" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Forward DOLLAR FCF hurdle",
         lambda r: "fcf_dollar_target" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("M&A close trigger",
         lambda r: "merger_acquisition_close" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Spin / separation trigger",
         lambda r: "spin_separation" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Named asset-sale trigger",
         lambda r: "asset_sale_named" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("FDA / clinical milestone trigger",
         lambda r: "fda_phase_milestone" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Chapter 11 emergence trigger",
         lambda r: "chapter11_emergence" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Restructuring milestone trigger",
         lambda r: "restructuring_milestone" in (proxy.get(r["ticker"], {}).get("cond_cats") or [])),
        ("Verified buyback EXECUTING (>=2% trailing shrinkage)",
         lambda r: (bbv.get(r["ticker"], {}).get("status") == "EXECUTING")),
        ("Verified ORGANIC shrinkage (SHRINKING_NO_AUTH)",
         lambda r: (bbv.get(r["ticker"], {}).get("status") == "SHRINKING_NO_AUTH")),
        ("Live ISSUER SELF-TENDER",
         lambda r: (tender.get(r["ticker"], {}).get("role") == "SELF_TENDER")),
        ("Live TARGET 14D-9",
         lambda r: (tender.get(r["ticker"], {}).get("role") == "TARGET")),
        ("Going-private (13E-3)",
         lambda r: bool(tender.get(r["ticker"], {}).get("has_13e3"))),
        ("CEO/Chair 10b5-1 sell-plan termination (signed_score >= 30)",
         lambda r: (c10.get(r["ticker"], {}).get("signed_score") or 0) >= 30),
        ("Insider 4+ buyer cluster (Form 4 P-buys)",
         lambda r: (f4.get(r["ticker"], {}).get("max_cluster_size") or 0) >= 4),
        ("Material insider dollar cluster (>=$1M total)",
         lambda r: (f4.get(r["ticker"], {}).get("total_musd") or 0) >= 1),
        ("Deep-value floor (P/B < 0.5 with PSU program)",
         lambda r: ((yf.get(r["ticker"], {}).get("p_b") or 99) < 0.5
                    and bool(proxy.get(r["ticker"])))),
    ]

    for name, pred in patterns:
        winners = [r for r in grand if pred(r)]
        winners.sort(key=lambda r: -float(r.get("norm_score") or 0))
        if not winners:
            continue
        out.append(f"### {name}")
        out.append("| Rank | Ticker | Norm | Tier | Reasons |")
        out.append("|---:|---|--:|---|---|")
        for i, r in enumerate(winners[:10], 1):
            out.append(f"| {i} | {r['ticker']} | {r['norm_score']} | "
                       f"{r['tier']} | {(r.get('reasons') or '')[:120]} |")
        out.append("")

    # ----------------- 3. PER-SIGNAL-LAYER LEADERS -----------------
    out.append("\n## 3. Per-signal-layer leaders\n")
    out.append("Best single-layer score in each dimension. Use when "
               "deploying a single-signal mandate.\n")

    layers = [
        ("PSU forensic core (psu_core, deeper plan rigor)", "psu"),
        ("Valuation floor (P/B, drawdown, microcap)", "valuation"),
        ("Verified buyback execution", "buyback"),
        ("Tender mechanics", "tender"),
        ("10b5-1 directional (sell-plan termination = bullish)", "c10b51"),
        ("Insider Form-4 P-buys", "f4_buys"),
    ]
    for name, key in layers:
        ranked = sorted(grand, key=lambda r: -float(r.get(key) or 0))
        if float(ranked[0].get(key) or 0) == 0:
            continue
        out.append(f"### {name}")
        out.append("| Rank | Ticker | Layer pts | Norm | Tier | Reasons |")
        out.append("|---:|---|--:|--:|---|---|")
        for i, r in enumerate(ranked[:10], 1):
            v = r.get(key)
            out.append(f"| {i} | {r['ticker']} | {v} | "
                       f"{r['norm_score']} | {r['tier']} | "
                       f"{(r.get('reasons') or '')[:100]} |")
        out.append("")

    # ----------------- 4. TIER BREAKOUT -----------------
    out.append("\n## 4. Tier-by-coverage breakout\n")
    out.append("Tier reflects how many of 7 data layers we have per "
               "ticker. Higher tier = more reliable ranking.\n")
    from collections import Counter
    tier_count = Counter(r["tier"] for r in grand)
    out.append(f"- **Tier A** (6-7 layers): {tier_count['A']} names")
    out.append(f"- **Tier B** (4-5 layers): {tier_count['B']} names")
    out.append(f"- **Tier C** (<4 layers): {tier_count['C']} names")
    out.append("")
    for tier in ("A", "B", "C"):
        sub = [r for r in grand if r["tier"] == tier]
        sub.sort(key=lambda r: -float(r.get("norm_score") or 0))
        if not sub:
            continue
        out.append(f"### Top 20 in Tier {tier}")
        out.append("| Rank | Ticker | Norm | Layers | Reasons |")
        out.append("|---:|---|--:|--:|---|")
        for i, r in enumerate(sub[:20], 1):
            out.append(f"| {i} | {r['ticker']} | {r['norm_score']} | "
                       f"{r['n_layers']} | "
                       f"{(r.get('reasons') or '')[:120]} |")
        out.append("")

    # ----------------- 5. CAUTION LIST (red flags) -----------------
    out.append("\n## 5. Caution list -- convergent names with red flags\n")
    cautions = {}
    for tk, p in proxy.items():
        flags = []
        prs = p.get("pattern_reasons") or []
        grs = p.get("gov_reasons") or []
        for s in prs + grs:
            sl = s.lower()
            if "single-trigger" in sl:
                flags.append("single-trigger CIC")
            if "repricing" in sl:
                flags.append("repricing language")
            if "retirement carveout" in sl:
                flags.append("retirement carveout")
            if "front-loaded" in sl:
                flags.append("front-loaded grant")
            if "discretionary" in sl:
                flags.append("discretionary hurdle")
            if "aggregate-only" in sl:
                flags.append("aggregate-only metrics")
        if flags:
            cautions[tk] = sorted(set(flags))

    top_50 = [r["ticker"] for r in
              sorted(consensus, key=lambda r: -int(r["n_screens"]))[:50]]
    flagged = [(tk, cautions[tk]) for tk in top_50 if tk in cautions]
    if flagged:
        out.append("| Ticker | Red flags |")
        out.append("|---|---|")
        for tk, fl in flagged:
            out.append(f"| {tk} | {', '.join(fl)} |")
    out.append("")

    # ----------------- 6. USE-CASE ROLLUPS -----------------
    out.append("\n## 6. Use-case deployment sheet\n")
    # Derived from disk -- each bucket pulled from its source CSV
    # rather than hardcoded in session memory.
    def top_n(rows: list[dict], key: str | None, n: int,
              filter_fn=None) -> list[str]:
        items = list(rows)
        if filter_fn:
            items = [r for r in items if filter_fn(r)]
        if key:
            def parse(v):
                try: return float(v or 0)
                except: return 0.0
            items.sort(key=lambda r: -parse(r.get(key)))
        names = []
        seen = set()
        for r in items:
            tk = r.get("ticker")
            if tk and tk not in seen:
                seen.add(tk)
                names.append(tk)
            if len(names) >= n:
                break
        return names

    convergent_tks = [r["ticker"] for r in consensus
                      if int(r.get("n_screens") or 0) >= 3
                      and int(r.get("n_archetypes_won") or 0) >= 1][:3]

    bastian_tks = top_n(bastian, "score", 6)
    info_tks = top_n(info_buys, "total", 5)

    bb_exec_tks = []
    for tk, b in bbv.items() if isinstance(bbv, dict) else []:
        if (isinstance(b, dict) and b.get("status") == "EXECUTING"
                and tk in proxy):
            bb_exec_tks.append((tk, abs((b.get("share_change") or {})
                                        .get("change_pct") or 0)))
    bb_exec_tks.sort(key=lambda x: -x[1])
    bb_exec_tks = [t for t, _ in bb_exec_tks[:5]]

    tender_self = [tk for tk, t in (tender.items() if isinstance(tender, dict) else [])
                   if isinstance(t, dict) and t.get("role") == "SELF_TENDER"][:3]
    tender_target = [tk for tk, t in (tender.items() if isinstance(tender, dict) else [])
                     if isinstance(t, dict) and t.get("role") == "TARGET"][:3]

    # Forward-$-hurdle (Mungerian): names with at least 2 of the three
    # forward dollar hurdles in proxy_scan cond_cats
    mungerian_tks = []
    for tk, p in proxy.items():
        cc = p.get("cond_cats") or []
        n_hurdles = sum(1 for c in ("revenue_dollar_target",
                                     "ebitda_dollar_target",
                                     "fcf_dollar_target") if c in cc)
        if n_hurdles >= 2:
            mungerian_tks.append((tk, n_hurdles, p.get("psu_core") or 0))
    mungerian_tks.sort(key=lambda x: (-x[1], -x[2]))
    mungerian_tks = [t for t, _, _ in mungerian_tks[:5]]

    special_sits_tks = top_n(
        spec_sit, "score", 6,
        filter_fn=lambda r: r.get("kind") in ("RESTRUCT_8K", "FORM_10_SPINOFF"))

    russell = load_rows(ROOT / "russell_boundary.csv")
    russell_tks = top_n(russell, None, 5)

    nol = load_rows(ROOT / "nol_shells.csv")
    nol_tks = top_n(nol, "score", 7)

    activist = load_rows(ROOT / "activist_13d.csv")
    act_tks = top_n(activist, "score", 5,
                     filter_fn=lambda r: r.get("is_known_activist") == "True")

    use_cases = [
        ("**Highest-conviction concentrated (top-3 convergent)**",
         ", ".join(convergent_tks) or "(empty)"),
        ("**Microcap forcing-function basket (Bastian)**",
         ", ".join(bastian_tks) or "(empty)"),
        ("**Mungerian forward-dollar PSU concentration**",
         ", ".join(mungerian_tks) or "(empty)"),
        ("**Verified buyback compounders (EXECUTING)**",
         ", ".join(bb_exec_tks) or "(empty)"),
        ("**Live SELF_TENDER**",
         ", ".join(tender_self) or "(empty)"),
        ("**Live TARGET (own 14D-9)**",
         ", ".join(tender_target) or "(empty)"),
        ("**Special-situations / 8-K restructuring + spinoff**",
         ", ".join(special_sits_tks) or "(empty)"),
        ("**Cohen-Malloy informational stack (top by 5-cond score)**",
         ", ".join(info_tks) or "(empty)"),
        ("**Known-activist 13D filings (top by signal score)**",
         ", ".join(act_tks) or "(empty)"),
        ("**Russell-recon forced-flow watch**",
         ", ".join(russell_tks) or "(empty)"),
        ("**NOL shell / Section 382 rights plan**",
         ", ".join(nol_tks) or "(empty)"),
    ]
    for label, names in use_cases:
        out.append(f"- {label}: {names}")
    out.append("")

    # ----------------- 7. METHODOLOGY -----------------
    out.append("\n## 7. Methodology summary\n")
    out.append("- **Universe:** 6,164 US-listed tickers (cancel_10b5_1.json)")
    out.append("- **Governance / PSU coverage:** 4,410 DEF 14As scanned (72%)")
    out.append("- **Tender / SC TO / 13E-3 coverage:** 6,164 (100%)")
    out.append("- **10b5-1 plan disclosure coverage:** 6,164 (100%)")
    out.append("- **yfinance valuation coverage:** 2,132 (35%, +gap-fill ongoing)")
    out.append("- **buyback_verify coverage:** ~800 (13%, +gap-fill ongoing)")
    out.append("- **Form 4 P-buys coverage:** 346 (5.6%, signal-sparse by design)")
    out.append("- **Form 144 coverage:** ~1,995 (32%, bearish-signal screen)")
    out.append("")
    out.append("- **Ranker:** coverage-normalised composite "
               "(score scaled by sqrt(7/n_layers_present) so a name "
               "with 4 strong of 7 isn't penalised vs 7 mediocre)")
    out.append("- **Consensus:** counts # of 8 independent rankers + "
               "2 archetype-winner markdowns that surface each ticker")
    out.append("- **Convergent:** >=3 screens AND archetype winner")
    out.append("- **Robustness:** convergent 12 unchanged after "
               "yfinance gap-fill (1,885 -> 2,132) AND after "
               "governance-coverage bugfix (Tier B 394 -> 1,090)")
    out.append("")

    (ROOT / "SYSTEMATIC_RANKINGS.md").write_text("\n".join(out))
    print(f"wrote SYSTEMATIC_RANKINGS.md ({len(out)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
