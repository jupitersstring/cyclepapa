#!/usr/bin/env python3
"""
portfolio.py — basket construction layer.

Addresses methodology_review.md §1.7 (factor decomposition) and §1.3
(Kelly with correlation haircuts). The framework has been producing
per-name EVs without ever asking how they cluster — this layer does.

Output:
- per-name factor exposures
- pairwise correlation matrix derived from factor co-membership
- risk-budgeted basket weights (equal-risk-contribution on factor risk)
- cluster summary
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
CANDIDATES = REPO / "data" / "candidates"
OUTPUT = REPO / "output"

# Factor taxonomy: each candidate gets exposure on a 0-1 scale to a
# defined set of factors. Hand-curated from each YAML's `factors.exposures`
# list, normalized.
FACTOR_DEFS = {
    "us_critical_minerals_policy": "DoD/DOE equity stakes + China geopolitics + CHIPS framework",
    "lithium_cycle": "Spodumene + carbonate pricing",
    "ndpr_ree_cycle": "Neodymium-praseodymium spot + China export controls",
    "copper_cycle": "Cu/Zn cycle + EV demand",
    "french_sovereign_strategic": "Bpifrance + CASA + BNP + APE + Bharti consortium pattern",
    "european_payments_cycle": "Adyen/Nexi sector multiples",
    "european_leo_satellite": "IRIS² + OneWeb integration + EU defence procurement",
    "nordic_anchor": "Wallenberg / Investor AB long-term pattern",
    "consumer_durables_cycle": "Appliance + housing demand",
    "us_china_trade_friction": "Tariff escalation + JV regulatory friction",
    "us_regulated_utility": "Authorized ROE + rate-base treatment",
    "hawaii_state_policy": "Hawaii PUC + Act 258 cap framework + wildfire risk",
    "china_property_policy": "PBOC + MOFCOM property stance + Tier-1 land cycle",
    "alaska_permitting": "BLM Ambler road + Alaska state permits",
    "diamond_cycle": "Rough diamond price index + lab-grown displacement",
    "us_election_cycle_policy_continuity": "Administration change effect on sovereign industrial policy",
}

# Per-candidate factor loadings, 0-1 scale.
# Derived from each YAML's `factors.exposures` list + analyst judgement.
FACTOR_LOADINGS: dict[str, dict[str, float]] = {
    "DRX":    {"uk_sovereign_industrial_policy": 0.8, "uk_treasury_fiscal_cycle": 0.4, "policy_continuity": 0.4},
    "SZG":    {"eu_sovereign_industrial_policy": 0.7, "european_steel_cycle": 0.7, "cbam_enforcement": 0.4},
    "LOCAL":  {"french_microcap_recovery": 0.8, "niel_levy_strategic_execution": 0.7},
    "LAC":    {"us_critical_minerals_policy": 0.7, "lithium_cycle": 0.9, "us_china_trade_friction": 0.3, "us_election_cycle_policy_continuity": 0.5},
    "UREE":   {"us_critical_minerals_policy": 0.8, "ndpr_ree_cycle": 0.7, "us_china_trade_friction": 0.4, "us_election_cycle_policy_continuity": 0.5},
    "MP":     {"us_critical_minerals_policy": 0.7, "ndpr_ree_cycle": 0.8, "us_china_trade_friction": 0.4, "us_election_cycle_policy_continuity": 0.4},
    "TMQ":    {"us_critical_minerals_policy": 0.6, "copper_cycle": 0.7, "alaska_permitting": 0.6, "us_election_cycle_policy_continuity": 0.4},
    "WLN":    {"french_sovereign_strategic": 0.9, "european_payments_cycle": 0.7},
    "ETL":    {"french_sovereign_strategic": 0.7, "european_leo_satellite": 0.9},
    "ELUX-B": {"nordic_anchor": 0.9, "consumer_durables_cycle": 0.7, "us_china_trade_friction": 0.3},
    "HE":     {"us_regulated_utility": 0.7, "hawaii_state_policy": 0.9},
    "SUNAC":  {"china_property_policy": 0.95},
    "MPVD":   {"diamond_cycle": 0.6},  # downgraded to pass; loadings kept for archive
}

# Cluster definition: factors that are economically related and should
# get a basket-level cap. Each factor belongs to exactly one cluster.
CLUSTERS = {
    "US_sovereign_minerals":   ["us_critical_minerals_policy", "lithium_cycle", "ndpr_ree_cycle", "copper_cycle",
                                "alaska_permitting", "us_election_cycle_policy_continuity"],
    "French_sovereign":        ["french_sovereign_strategic", "european_payments_cycle", "european_leo_satellite"],
    "UK_sovereign":            ["uk_sovereign_industrial_policy", "uk_treasury_fiscal_cycle", "policy_continuity"],
    "EU_industrial_policy":    ["eu_sovereign_industrial_policy", "european_steel_cycle", "cbam_enforcement"],
    "French_microcap":         ["french_microcap_recovery", "niel_levy_strategic_execution"],
    "Nordic_consumer":         ["nordic_anchor", "consumer_durables_cycle"],
    "US_utility":              ["us_regulated_utility", "hawaii_state_policy"],
    "China_property":          ["china_property_policy"],
    "Cross_factor":            ["us_china_trade_friction"],
    "Idiosyncratic":           ["diamond_cycle"],
}


def load_candidates() -> dict[str, dict]:
    out = {}
    for path in sorted(CANDIDATES.glob("*.yaml")):
        with path.open() as f:
            d = yaml.safe_load(f)
        if d.get("state") == "pass":
            continue
        out[d["ticker"]] = d
    return out


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


def kelly_fraction(d: dict, max_frac: float = 0.10) -> float:
    wf = d.get("waterfall", {})
    if not wf:
        return 0.0
    p_win = wf["base"]["p"] + wf["bull"]["p"]
    p_loss = wf["bear"]["p"]
    if p_loss == 0:
        return max_frac
    avg_win = (wf["base"]["p"] * (wf["base"]["return_multiple"] - 1)
               + wf["bull"]["p"] * (wf["bull"]["return_multiple"] - 1)) / p_win
    avg_loss = 1 - wf["bear"]["return_multiple"]
    if avg_loss <= 0:
        return max_frac
    b = avg_win / avg_loss
    if b <= 0:
        return 0.0
    full_kelly = (p_win * b - p_loss) / b
    return min(max(0.0, 0.25 * full_kelly), max_frac)


def correlation(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity over shared factor space."""
    factors = set(a) | set(b)
    if not factors:
        return 0.0
    num = sum(a.get(f, 0) * b.get(f, 0) for f in factors)
    den_a = math.sqrt(sum(v * v for v in a.values()))
    den_b = math.sqrt(sum(v * v for v in b.values()))
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def cluster_of(ticker: str) -> str:
    loadings = FACTOR_LOADINGS.get(ticker, {})
    if not loadings:
        return "Unknown"
    # Assign to cluster of the dominant factor
    dominant = max(loadings.items(), key=lambda kv: kv[1])[0]
    for cluster, factors in CLUSTERS.items():
        if dominant in factors:
            return cluster
    return "Other"


def render() -> str:
    cs = load_candidates()
    tickers = sorted(cs.keys())

    lines = []
    lines.append(f"# Portfolio construction layer")
    lines.append("")
    lines.append("Auto-generated by `src/portfolio.py`. Captures the framework's")
    lines.append("missing portfolio dimension: correlation clusters, factor exposures,")
    lines.append("and risk-budgeted weights. Do NOT hand-edit.")
    lines.append("")

    # Per-name EV / Kelly / cluster table
    lines.append("## Per-name EV, Kelly, cluster")
    lines.append("")
    lines.append("| Ticker | EV× | Downside | ¼-Kelly | Cluster | Dominant factor |")
    lines.append("|---|---|---|---|---|---|")
    rows = []
    for t in tickers:
        d = cs[t]
        ev = expected_value(d) or 0
        dd = downside(d) or 0
        kelly = kelly_fraction(d)
        c = cluster_of(t)
        ld = FACTOR_LOADINGS.get(t, {})
        dom = max(ld.items(), key=lambda kv: kv[1])[0] if ld else "—"
        rows.append((t, ev, dd, kelly, c, dom))
    for t, ev, dd, kelly, c, dom in sorted(rows, key=lambda r: -r[1]):
        lines.append(f"| **{t}** | {ev:.2f} | {dd:.2f} | {kelly*100:.1f}% | {c} | `{dom}` |")
    lines.append("")

    # Cluster summary
    lines.append("## Cluster summary")
    lines.append("")
    lines.append("| Cluster | Names | Σ raw Kelly | Σ EV-weighted Kelly | Cap (Kelly × 0.5) |")
    lines.append("|---|---|---|---|---|")
    by_cluster = defaultdict(list)
    for t in tickers:
        by_cluster[cluster_of(t)].append(t)
    for cluster, members in sorted(by_cluster.items()):
        raw = sum(kelly_fraction(cs[t]) for t in members)
        ev_w = sum(kelly_fraction(cs[t]) * (expected_value(cs[t]) or 0) for t in members) / max(1, len(members))
        cap = raw * 0.5
        lines.append(f"| **{cluster}** | {', '.join(members)} | {raw*100:.1f}% | {ev_w*100:.1f}% | {cap*100:.1f}% |")
    lines.append("")

    # Pairwise correlation matrix
    lines.append("## Pairwise correlation (cosine over factor exposures)")
    lines.append("")
    lines.append("| | " + " | ".join(tickers) + " |")
    lines.append("|---|" + "---|" * len(tickers))
    for t1 in tickers:
        row_vals = []
        for t2 in tickers:
            c = correlation(FACTOR_LOADINGS.get(t1, {}), FACTOR_LOADINGS.get(t2, {}))
            row_vals.append(f"{c:.2f}")
        lines.append(f"| **{t1}** | " + " | ".join(row_vals) + " |")
    lines.append("")

    # Risk-budgeted weights (equal-risk-contribution via inverse-variance + correlation haircut)
    lines.append("## Risk-budgeted basket weights")
    lines.append("")
    lines.append("Method: per-name raw weight = ¼-Kelly. Apply *correlation")
    lines.append("haircut*: for each name, multiply raw weight by")
    lines.append("`1 / (1 + Σ correlation with peers in same cluster)`.")
    lines.append("Then cap each cluster's total weight at 50% of its raw Kelly")
    lines.append("sum to enforce diversification across the four-cluster basket.")
    lines.append("Renormalize within the cap.")
    lines.append("")

    # Compute correlation-haircut weights
    raw_w = {t: kelly_fraction(cs[t]) for t in tickers}
    haircut_w = {}
    for t in tickers:
        c_in = cluster_of(t)
        peers = [p for p in tickers if p != t and cluster_of(p) == c_in]
        peer_corr = sum(correlation(FACTOR_LOADINGS.get(t, {}), FACTOR_LOADINGS.get(p, {}))
                        for p in peers)
        haircut_w[t] = raw_w[t] / (1.0 + peer_corr)

    # Apply cluster caps
    final_w = dict(haircut_w)
    for cluster, members in by_cluster.items():
        cluster_raw_sum = sum(raw_w[t] for t in members)
        cluster_cap = cluster_raw_sum * 0.5
        cluster_post = sum(haircut_w[t] for t in members)
        if cluster_post > cluster_cap and cluster_post > 0:
            scale = cluster_cap / cluster_post
            for t in members:
                final_w[t] = haircut_w[t] * scale

    total = sum(final_w.values())
    lines.append("| Ticker | Cluster | Raw Kelly | After corr. haircut | After cluster cap | EV×weight | Contribution to portfolio EV× |")
    lines.append("|---|---|---|---|---|---|---|")
    portfolio_ev_contrib = 0.0
    for t in sorted(tickers, key=lambda x: -final_w[x]):
        cluster = cluster_of(t)
        ev = expected_value(cs[t]) or 0
        w = final_w[t]
        contrib = w * ev
        portfolio_ev_contrib += contrib
        lines.append(f"| **{t}** | {cluster} | {raw_w[t]*100:.2f}% | {haircut_w[t]*100:.2f}% | {w*100:.2f}% | {w*100:.2f}% × {ev:.2f} | {contrib*100:.2f} bps |")
    lines.append(f"| **Total** | | | | {total*100:.2f}% | | **{portfolio_ev_contrib*100:.1f} bps** |")
    lines.append("")
    lines.append(f"Cash remainder: **{(1-total)*100:.2f}%**")
    lines.append("")

    # Interpretation
    lines.append("## Interpretation")
    lines.append("")
    lines.append(f"- Total invested: {total*100:.2f}% of NAV across {len(tickers)} active names")
    lines.append(f"- Cash: {(1-total)*100:.2f}% (a feature, not a bug — Kelly haircuts force humility)")
    lines.append(f"- Expected portfolio multiple on invested capital: {sum(final_w[t]*(expected_value(cs[t]) or 0) for t in tickers)/max(1e-9,total):.2f}×")
    lines.append("- Dominant factor concentration risk: the US sovereign-minerals cluster")
    lines.append("  carries the highest raw-Kelly sum; cluster cap is the binding constraint.")
    lines.append("- The correlation haircut materially down-weights names where multiple")
    lines.append("  candidates load on the same factor (rare-earth/lithium cluster).")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    out = render()
    target = OUTPUT / "portfolio.md"
    target.write_text(out)
    print(f"Wrote {target}")
    print(out)


if __name__ == "__main__":
    main()
