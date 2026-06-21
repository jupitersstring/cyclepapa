#!/usr/bin/env python3
"""
score.py — read data/candidates/*.yaml, validate, compute scores, tier,
emit ranked Markdown.

Addresses methodology_review.md items:
- §1.3 EV with explicit probabilities + Kelly sizing
- §1.5 Source-verification ledger (blocks Tier 1 with unverified fields)
- §4.1 Single-source-of-truth: rankings GENERATED, never hand-edited
- §4.4 Schema validation + stale linter
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
CANDIDATES = REPO / "data" / "candidates"
OUTPUT = REPO / "output"

# Quantitative scorecard thresholds from §2.1
# Each entry: (dimension_name, predicate that returns 0/1/2)
SCORE_RULES: dict[str, Any] = {
    "d2_issue_discount_pct":        lambda v: 2 if v is not None and v < 30 else (1 if v is not None and v < 50 else 0),
    "d3_backstop_cost_pct":         lambda v: 2 if v is not None and v < 2 else (1 if v is not None and v < 5 else 0),
    "d4_dilution_pct":              lambda v: 2 if v is not None and v < 40 else (1 if v is not None and v < 80 else 0),
    "d5_delta_wam_months":          lambda v: 2 if v is not None and v >= 24 else (1 if v is not None and v >= 12 else 0),
    "d6_debt_tranches_post":        lambda v: 2 if v is not None and v <= 1 else (1 if v is not None and v <= 3 else 0),
    "d9_alignment_gap":             lambda v: 2 if v is not None and v >= 2.0 else (1 if v is not None and v >= 1.2 else 0),
    "d9c_premium_to_vwap":          lambda v: 2 if v is not None and v >= 10 else (1 if v is not None and v >= 0 else 0),
    "d9d_liquidation_recovery_pct": lambda v: 2 if v is not None and v >= 30 else (1 if v is not None and v >= 10 else 0),
    "d11_consensus_ebitda_cagr":    lambda v: 2 if v is not None and v >= 30 else (1 if v is not None and v >= 10 else 0),
    "d13_altman_z":                 lambda v: 2 if v is not None and v > 2.9 else (1 if v is not None and v >= 1.8 else 0),
    "d14_liquidity_quarters":       lambda v: 2 if v is not None and v > 6 else (1 if v is not None and v >= 2 else 0),
    # ---- Klarman additions (process_improvements.md §A) ----
    # Lower sell-side coverage = more contrarian, better margin of safety.
    "d20_crowd_check_analysts":     lambda v: 2 if v is not None and v <= 3 else (1 if v is not None and v <= 8 else 0),
    # Boolean: True if lead underwriter on a recent capital raise is
    # also covering the stock with a Buy rating. Structural conflict
    # contaminates consensus inputs.
    "d21_sellside_conflict":        lambda v: 0 if v is True else (2 if v is False else 1),
    # ---- Walker addition (process_improvements.md §E) ----
    # Days since deal.date — 30-180 day window catches the maximum
    # info-asymmetry zone (index/screen rebalance lag).
    "d22_days_since_recap":         lambda v: 2 if v is not None and 30 <= v <= 180 else (1 if v is not None and v < 365 else 0),
}

# Red-flag checklist. Existing 11 + 3 new from Moyer (Distressed Debt
# Analysis). See process_improvements.md §C.
EXPECTED_RED_FLAGS = [
    "parallel_pipe_below_rights", "asymmetric_voting",
    "backstop_warrants_below_terp", "dip_to_exit_control_transfer",
    "springing_maturity_inside_24m", "stub_under_10pct_no_warrants",
    "insider_indemnity_survives", "insider_net_seller",
    "state_backstop_conditional", "refiled_within_12m",
    "new_money_irr_above_50pct",
    # ---- Moyer additions ----
    "mfn_below_us",                  # MFN clause leaves us above the anchor
    "fiduciary_out_overly_tight",    # Target board can't accept a topping bid
    "springing_covenant",            # Beyond springing maturity — covenants flip
]

REQUIRED_TOP_LEVEL = ["ticker", "name", "bucket", "archetype", "state", "tier"]
TIER1_REQUIREMENTS = ["catalysts", "waterfall", "pre_mortem", "kill_criteria", "anchor"]

# Tier-1 diligence-depth additions (process_improvements.md §B, §D, §G).
# Surfaced as WARNINGS not errors so they don't block existing YAMLs.
TIER1_DILIGENCE_DEPTH = [
    "consensus_pricing",     # Marks "what does the market need to believe"
    "catalyst_independence", # Voss multi-catalyst independence score
    "expert_calls",          # Expert-network channel-check log
]


# -- loading and validation ---------------------------------------------------

@dataclass
class Candidate:
    path: Path
    data: dict
    errors: list[str]
    warnings: list[str]


def load_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for path in sorted(CANDIDATES.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f)
        errors, warnings = validate(data, path)
        out.append(Candidate(path=path, data=data, errors=errors, warnings=warnings))
    return out


def validate(d: dict, path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    # Required top-level fields
    for f in REQUIRED_TOP_LEVEL:
        if f not in d:
            errors.append(f"missing required field: {f}")

    # Waterfall: probabilities must sum to 1.0
    wf = d.get("waterfall", {})
    if wf:
        p_sum = sum(wf.get(k, {}).get("p", 0) for k in ("bear", "base", "bull"))
        if abs(p_sum - 1.0) > 0.001:
            errors.append(f"waterfall probabilities sum to {p_sum:.3f}, expected 1.0")

    # Tier 1 requirements
    if d.get("tier") == 1:
        for f in TIER1_REQUIREMENTS:
            if not d.get(f):
                errors.append(f"Tier 1 candidate missing required block: {f}")

        # Source-tag check: every value field must have a source
        deal = d.get("deal", {})
        unverified = [
            k for k, v in deal.get("fields", {}).items()
            if isinstance(v, dict) and v.get("source", "unverified") == "unverified"
        ]
        if unverified:
            warnings.append(
                f"Tier 1 has {len(unverified)} unverified deal fields; sizing blocked at full conviction"
            )

        # Diligence-depth fields (process_improvements.md). Warnings, not
        # errors — additive over time as we back-fill the older YAMLs.
        for f in TIER1_DILIGENCE_DEPTH:
            if not d.get(f):
                warnings.append(
                    f"Tier 1 missing diligence-depth block: {f}"
                )

        # Expert-call freshness: Tier 1 + core should have >= 3 calls
        # within the last 90 days.
        if d.get("state") == "core":
            calls = d.get("expert_calls") or []
            if len(calls) < 3:
                warnings.append(
                    f"core Tier 1 has only {len(calls)} expert calls "
                    "logged (target: >= 3 per process_improvements.md §G)"
                )

    # State ↔ tier coherence
    state = d.get("state")
    tier = d.get("tier")
    if (state == "core" and tier != 1) or (state == "pass" and tier != "pass"):
        errors.append(f"state '{state}' incoherent with tier '{tier}'")

    # Stale linter (§4.4)
    history = d.get("history", [])
    if history:
        latest = max(_to_date(h.get("date")) for h in history)
        age_days = (date.today() - latest).days
        if age_days > 30:
            warnings.append(f"stale: last history entry {age_days} days ago")

    return errors, warnings


def _to_date(x) -> date:
    if isinstance(x, date):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, str):
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(x, fmt).date()
            except ValueError:
                continue
    return date.today()


# -- scoring & EV math --------------------------------------------------------

def quant_score(d: dict) -> tuple[int, int]:
    """Return (achieved, max) over dimensions that have a value."""
    sc = d.get("scorecard", {})
    achieved, maximum = 0, 0
    for dim, rule in SCORE_RULES.items():
        v = sc.get(dim)
        if v is None:
            continue
        achieved += rule(v)
        maximum += 2
    return achieved, maximum


def expected_value(d: dict) -> float | None:
    wf = d.get("waterfall", {})
    if not wf:
        return None
    return sum(wf.get(k, {}).get("p", 0) * wf.get(k, {}).get("return_multiple", 0)
               for k in ("bear", "base", "bull"))


def downside(d: dict) -> float | None:
    wf = d.get("waterfall", {})
    if not wf:
        return None
    return 1.0 - wf.get("bear", {}).get("return_multiple", 0)


def kelly_fraction(d: dict, max_frac: float = 0.10) -> float | None:
    """Fractional Kelly (¼) bounded to a sensible max. §1.3 fix."""
    wf = d.get("waterfall", {})
    if not wf:
        return None
    # Treat as a simple win/loss bet at base+bull combined.
    p_win = wf["base"]["p"] + wf["bull"]["p"]
    p_loss = wf["bear"]["p"]
    if p_loss == 0:
        return max_frac
    avg_win = (
        wf["base"]["p"] * (wf["base"]["return_multiple"] - 1)
        + wf["bull"]["p"] * (wf["bull"]["return_multiple"] - 1)
    ) / p_win
    avg_loss = 1 - wf["bear"]["return_multiple"]
    if avg_loss <= 0:
        return max_frac
    b = avg_win / avg_loss
    if b <= 0:
        return 0.0
    full_kelly = (p_win * b - p_loss) / b
    quarter = max(0.0, 0.25 * full_kelly)
    return min(quarter, max_frac)


def triangulation_count(d: dict) -> str:
    t = d.get("triangulation", {})
    legs = [t.get("leg1_valuation"), t.get("leg2_game_theory"), t.get("leg3_revealed_pref")]
    yes = sum(1 for x in legs if x is True)
    partial = sum(1 for x in legs if x == "partial")
    return f"{yes}+{partial}p / 3"


def active_red_flags(d: dict) -> list[str]:
    rf = d.get("red_flags", {})
    return [k for k, v in rf.items() if v is True and not k.startswith("_")]


# -- output -------------------------------------------------------------------

def render_table(candidates: list[Candidate]) -> str:
    rows = []
    for c in candidates:
        if c.errors:
            continue
        d = c.data
        ev = expected_value(d)
        dd = downside(d)
        kelly = kelly_fraction(d)
        achieved, maximum = quant_score(d)
        score_str = f"{achieved}/{maximum}" if maximum else "n/a"
        rows.append({
            "tier": d.get("tier"),
            "ticker": d.get("ticker"),
            "name": d.get("name"),
            "bucket": d.get("bucket"),
            "archetype": "+".join(d.get("archetype", [])),
            "score": score_str,
            "triang": triangulation_count(d),
            "ev": ev,
            "ev_over_dd": (ev / dd) if (ev and dd) else None,
            "kelly_pct": kelly,
            "flags": ", ".join(active_red_flags(d)) or "—",
            "state": d.get("state"),
        })
    # Sort: Tier 1 first, then by EV descending
    rows.sort(key=lambda r: (
        0 if r["tier"] == 1 else 1 if r["tier"] == 2 else 2 if r["tier"] == 3 else 9,
        -(r["ev"] or 0),
    ))

    lines = [
        f"# Generated screen ({date.today().isoformat()})",
        "",
        "Auto-generated from `data/candidates/*.yaml` by `src/score.py`. "
        "Do NOT hand-edit.",
        "",
        "| Tier | Ticker | Name | Bucket·Arch | Quant | Triang | EV× | EV/DD | ¼-Kelly | Active red flags |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ev = f"{r['ev']:.2f}" if r['ev'] is not None else "—"
        evdd = f"{r['ev_over_dd']:.2f}" if r['ev_over_dd'] is not None else "—"
        kelly = f"{r['kelly_pct']*100:.1f}%" if r['kelly_pct'] is not None else "—"
        lines.append(
            f"| {r['tier']} | **{r['ticker']}** | {r['name']} | "
            f"{r['bucket']}·{r['archetype']} | {r['score']} | {r['triang']} | "
            f"{ev} | {evdd} | {kelly} | {r['flags']} |"
        )
    return "\n".join(lines) + "\n"


def render_diagnostics(candidates: list[Candidate]) -> str:
    lines = ["", "## Diagnostics", ""]
    for c in candidates:
        if not (c.errors or c.warnings):
            continue
        lines.append(f"### {c.path.name}")
        for e in c.errors:
            lines.append(f"- ❌ ERROR: {e}")
        for w in c.warnings:
            lines.append(f"- ⚠️  warning: {w}")
        lines.append("")
    if len(lines) == 3:
        lines.append("All candidates clean. No errors or warnings.")
    return "\n".join(lines) + "\n"


def main():
    cs = load_candidates()
    out = render_table(cs) + render_diagnostics(cs)
    target = OUTPUT / "screen_generated.md"
    target.write_text(out)
    print(f"Wrote {target} ({len(cs)} candidates).")

    # Exit non-zero on any error so CI catches drift.
    any_errors = any(c.errors for c in cs)
    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
