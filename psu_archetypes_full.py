"""Full PSU / governance archetype rollout.

The earlier ASYMMETRIC_BY_ARCHETYPE.md covered 11 structural buckets
(A1-A11) drawn from the forward-conditional cond_cats. But the proxy
scanner records far more PSU/gov dimensions; this script picks the
single best representative of EVERY scored PSU/gov archetype.

Output: PSU_ARCHETYPES.md
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_proxy() -> dict:
    """Load latest proxy row per ticker across all shards."""
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
            if not tk:
                continue
            cur = out.get(tk)
            if not cur or (r.get("filing_date", "") > cur.get("filing_date", "")):
                out[tk] = r
    return out


def load_overlay() -> dict:
    """ticker -> yfinance + composite + bb_verify + cluster overlay."""
    overlay: dict = defaultdict(dict)
    yq = ROOT / "yfinance_quick.json"
    if yq.exists():
        for tk, v in json.loads(yq.read_text()).items():
            overlay[tk]["yf"] = v
    bv = ROOT / "buyback_verify.json"
    if bv.exists():
        for tk, v in json.loads(bv.read_text()).items():
            overlay[tk]["bb"] = v
    comp = ROOT / "unified_composite.csv"
    if comp.exists():
        for r in csv.DictReader(comp.open()):
            overlay[r["ticker"]]["comp"] = r
    inf = ROOT / "informational_buys.csv"
    if inf.exists():
        for r in csv.DictReader(inf.open()):
            overlay[r["ticker"]]["info"] = r
    return overlay


def fmt(r: dict, o: dict, why: str) -> str:
    yf = o.get("yf", {}) or {}
    bb = o.get("bb", {}) or {}
    comp = o.get("comp", {}) or {}
    mcap = yf.get("mcap")
    px = yf.get("price")
    pb = yf.get("p_b")
    lo, hi = yf.get("fwk_low"), yf.get("fwk_high")
    dd = None
    if hi and px and hi > 0:
        dd = round((1 - px / hi) * 100, 0)
    ps = sorted(r.get("per_share_metrics") or [])
    ag = sorted(r.get("aggregate_metrics") or [])
    metrics = f"per_share={ps} agg={ag}"
    bb_status = bb.get("status", "?")
    bb_chg = (bb.get("share_change") or {}).get("change_pct")
    bb_str = f"{bb_status}({bb_chg:+.2f}%)" if bb_chg is not None else f"{bb_status}"
    return (
        f"  mcap=${(mcap or 0)/1e6:,.0f}M  px=${px or 0:.2f}  "
        f"P/B={pb or 0:.2f}  DD%={dd or 0:.0f}%\n"
        f"    PSU core={r.get('psu_core')}  gov={r.get('gov_score')}  "
        f"PSU%LTI={r.get('psu_pct_lti')}  {metrics}\n"
        f"    composite={comp.get('score', '?')}  "
        f"buyback={bb_str}\n"
        f"    WHY: {why}"
    )


def score_for_winner(r: dict, o: dict, bonus: float = 0.0) -> float:
    """Default ranking inside a bucket: weighted PSU core + gov + composite kicker."""
    yf = o.get("yf", {}) or {}
    comp = o.get("comp", {}) or {}
    pb = yf.get("p_b") or 99
    pb_kick = 10 if pb and pb < 1 else (5 if pb and pb < 2 else 0)
    try:
        cs = float(comp.get("score") or 0)
    except Exception:
        cs = 0
    return ((r.get("psu_core") or 0) * 0.55
            + (r.get("gov_score") or 0)
            + pb_kick + cs * 0.4 + bonus)


def pick(proxy: dict, overlay: dict, pred, name: str) -> tuple[str, dict] | None:
    """pred(r,o) -> (qualifies bool, bonus float) or False/None."""
    cands = []
    for tk, r in proxy.items():
        o = overlay.get(tk, {})
        v = pred(r, o)
        if not v:
            continue
        bonus = v if isinstance(v, (int, float)) else 0.0
        cands.append((tk, score_for_winner(r, o, bonus)))
    if not cands:
        return None
    tk = max(cands, key=lambda x: x[1])[0]
    return tk, proxy[tk]


def main() -> int:
    proxy = load_proxy()
    overlay = load_overlay()
    print(f"loaded proxy={len(proxy)} overlay={len(overlay)}")

    sections = []

    def add(slug, title, why_field, pred):
        result = pick(proxy, overlay, pred, slug)
        if not result:
            sections.append((slug, title, None, None, None))
            return
        tk, r = result
        why = (why_field(r) if callable(why_field) else why_field)
        sections.append((slug, title, tk, r, why))

    # ----------------- A. STRUCTURAL PSU ARCHETYPES -----------------

    def has_cat(cat):
        return lambda r, o: cat in (r.get("cond_cats") or [])

    add("A1", "Forward DOLLAR REVENUE hurdle",
        lambda r: "; ".join(r.get("fwd_snippets") or [])[:200] or "revenue_dollar_target in plan",
        has_cat("revenue_dollar_target"))
    add("A2", "Forward DOLLAR EBITDA hurdle",
        "ebitda_dollar_target in plan",
        has_cat("ebitda_dollar_target"))
    add("A3", "Forward DOLLAR FCF hurdle",
        "fcf_dollar_target in plan",
        has_cat("fcf_dollar_target"))
    add("A4", "Operating MARGIN target",
        "operating_margin_target in plan",
        has_cat("operating_margin_target"))
    add("A5", "Subscriber / ARR target",
        "subscriber_arr_target in plan",
        has_cat("subscriber_arr_target"))
    add("A6", "Backlog target",
        "backlog_target in plan",
        has_cat("backlog_target"))
    add("A7", "PSU vests on M&A close",
        "PSU triggers on deal close",
        has_cat("merger_acquisition_close"))
    add("A8", "PSU vests on SPIN / separation",
        "PSU triggers on spin / Form 10",
        has_cat("spin_separation"))
    add("A9", "PSU vests on FDA / clinical milestone",
        "binary regulatory catalyst",
        has_cat("fda_phase_milestone"))
    add("A10", "PSU vests on NAMED ASSET SALE",
        "segment / division divestiture",
        has_cat("asset_sale_named"))
    add("A11", "PSU vests on DEBT-PAYDOWN target",
        "leverage target coded in plan",
        has_cat("debt_leverage_target"))
    add("A12", "PSU vests on RESTRUCTURING milestone",
        "restructuring_milestone in plan",
        has_cat("restructuring_milestone"))
    add("A13", "PSU vests on CHAPTER-11 EMERGENCE",
        "post-emergence plan triggers",
        has_cat("chapter11_emergence"))

    # Stock price ladders (depth, length, top tranche)
    def deep_ladder(r, o):
        hurdles = r.get("stock_price_hurdles") or []
        yf = o.get("yf", {}) or {}
        px = yf.get("price") or 0
        if not hurdles or not px:
            return False
        top = max(hurdles)
        mult = top / px
        return mult if mult >= 5 else False
    add("A14", "DEEP stock-price ladder (>=5x spot)",
        lambda r: f"top tranche {max(r['stock_price_hurdles']):.2f} ladder",
        deep_ladder)

    def long_ladder(r, o):
        h = r.get("stock_price_hurdles") or []
        return len(h) if len(h) >= 5 else False
    add("A15", "LONGEST step-tranche ladder (>=5 steps)",
        lambda r: f"{len(r['stock_price_hurdles'])} tranches",
        long_ladder)

    # ----------------- B. PSU WEIGHT / METRIC STACK -----------------
    add("B1", "HIGHEST PSU% of LTI (>=80%)",
        lambda r: f"PSU = {r['psu_pct_lti']}% of LTI",
        lambda r, o: (r.get("psu_pct_lti") or 0) >= 80
                     and (r.get("psu_pct_lti") or 0))
    add("B2", "VERY HEAVY PSU% of LTI 70-79%",
        lambda r: f"PSU = {r['psu_pct_lti']}% of LTI",
        lambda r, o: 70 <= (r.get("psu_pct_lti") or 0) < 80)
    add("B3", "DEEPEST per-share metric stack (>=5)",
        lambda r: f"{len(r['per_share_metrics'])} per-share metrics: "
                  f"{r['per_share_metrics']}",
        lambda r, o: len(r.get("per_share_metrics") or []) >= 5)
    add("B4", "FCF / SHARE metric",
        lambda r: "FCF/share in metric stack",
        lambda r, o: "fcf_per_share" in (r.get("per_share_metrics") or []))
    add("B5", "ROIC metric (per-share return-on-capital)",
        lambda r: "ROIC in metric stack",
        lambda r, o: "roic" in (r.get("per_share_metrics") or []))
    add("B6", "OTHER per-share metric (custom)",
        lambda r: "custom per-share metric in stack",
        lambda r, o: "other_per_share" in (r.get("per_share_metrics") or []))

    # ----------------- C. GOVERNANCE / ALIGNMENT -----------------
    def has_gov(s):
        return lambda r, o: any(s in g for g in (r.get("gov_reasons") or []))

    add("C1", "10x CEO OWNERSHIP MULTIPLE (highest)",
        lambda r: "10x ownership multiple required",
        has_gov("10x ownership"))
    add("C2", "ANTI-HEDGE / ANTI-PLEDGE policy",
        "anti-hedge and anti-pledge codified",
        has_gov("anti-hedge"))
    add("C3", "CLAWBACK STRENGTHENED beyond 10D-1",
        "expanded clawback policy",
        has_gov("clawback"))
    add("C4", "POST-VEST HOLDING requirement",
        "must hold shares post-vest",
        has_gov("post-vest holding"))
    add("C5", "LONG vesting (>=5y)",
        lambda r: [g for g in r.get("gov_reasons") or [] if "vesting" in g][0],
        lambda r, o: any(("5y vesting" in g or "7y vesting" in g
                          or "10y vesting" in g)
                         for g in r.get("gov_reasons") or []))
    add("C6", "RESPONSIVE-to-shareholders plan evolution",
        "redesigned plan after pushback",
        has_gov("responsive to shareholders"))

    # ----------------- D. PLAN EVOLUTION -----------------
    def has_reason(s):
        return lambda r, o: any(s in p for p in (r.get("pattern_reasons") or []))

    add("D1", "Shareholder-FEEDBACK plan response",
        "plan evolved on shareholder feedback",
        has_reason("shareholder_feedback_response"))
    add("D2", "VEST PERIOD EXTENDED in latest filing",
        "longer vest schedule than prior plan",
        has_reason("vest_period_extended"))
    add("D3", "OWNERSHIP REQUIREMENTS ADDED",
        "ownership rules added in latest filing",
        has_reason("ownership_requirements_added"))
    add("D4", "TRANSFORMATION signal (board signaling reset)",
        "transformation language in CD&A",
        has_reason("transformation signal"))

    # ----------------- E. NEGATIVE / ADVERSARIAL (red-flag winners) -----
    add("E1", "FRONT-LOADED grant (red flag, paid now for later goals)",
        "front-loaded grant in disclosure",
        has_reason("front-loaded grant"))
    add("E2", "REPRICING language (red flag)",
        "plan allows repricing",
        has_reason("repricing"))
    add("E3", "DISCRETIONARY language / gameable hurdle (red flag)",
        "committee discretion language",
        has_reason("discretionary language"))
    add("E4", "AGGREGATE-only metrics (no per-share alignment)",
        "no per-share metrics in plan",
        has_reason("aggregate-only"))
    add("E5", "SINGLE-TRIGGER CIC (penalty)",
        "single-trigger acceleration on CIC",
        has_reason("single-trigger CIC"))
    add("E6", "Retirement carveout (vest on retire, weak)",
        "retirement carveout in plan",
        has_reason("retirement carveout"))

    # ----------------- F. SAY-ON-PAY DISSENT -----------------
    add("F1", "SAY-ON-PAY DISSENT (lowest passing vote)",
        lambda r: f"SOP {r['say_on_pay_pct']}% support",
        lambda r, o: (r.get("say_on_pay_pct") or 100) < 70
                     and -(r.get("say_on_pay_pct") or 100))

    # ----------------- WRITE MARKDOWN -----------------
    lines = ["# Best representative per PSU / governance archetype",
             "",
             "Across 6,164 proxies, the single most asymmetric name in each",
             "scored PSU/gov bucket. Ranking inside a bucket: weighted",
             "psu_core + gov_score + composite kicker + P/B bonus.",
             ""]
    cur_section = ""
    for slug, title, tk, r, why in sections:
        prefix = slug[0]
        section = {
            "A": "## A. Forward conditional PSU triggers",
            "B": "## B. PSU weight & metric stack",
            "C": "## C. Governance / alignment",
            "D": "## D. Plan evolution",
            "E": "## E. Red-flag archetypes (winner = worst offender)",
            "F": "## F. Say-on-Pay dissent",
        }.get(prefix, "## Other")
        if section != cur_section:
            lines.append("")
            lines.append(section)
            lines.append("")
            cur_section = section
        lines.append(f"### {slug}. {title}")
        if tk is None:
            lines.append("")
            lines.append("(no qualifying name)")
            lines.append("")
            continue
        lines.append("")
        lines.append(f"**Winner: {tk}**")
        lines.append("")
        lines.append("```")
        lines.append(f"  {tk}")
        lines.append(fmt(r, overlay.get(tk, {}), why))
        lines.append("```")
        lines.append("")

    out = ROOT / "PSU_ARCHETYPES.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out} ({len(sections)} archetypes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
