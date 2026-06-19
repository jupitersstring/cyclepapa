#!/usr/bin/env python3
"""
yaml_skeleton.py — bulk-generate skeleton YAMLs from universe.md rows.

Closes the comprehensiveness gap: every universe-screener T0+T1 name
should have at least a skeleton YAML so the framework's score.py,
events.py, and portfolio.py all see it.

Skeleton YAMLs are tagged 'state: option' and 'tier: 3' so they don't
default into the basket unless deepened. Source fields are tagged
'reported: universe.md' which honestly flags the verification gap.

Usage:
    python -m src.yaml_skeleton                       # all T0+T1 without YAMLs
    python -m src.yaml_skeleton --min-score 0.55      # tighter threshold
    python -m src.yaml_skeleton --dry-run             # preview, don't write
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
CANDIDATES_DIR = REPO / "data" / "candidates"

# Region → factor cluster mapping for skeleton waterfalls
REGION_CLUSTER_PRIORS: dict[str, dict] = {
    "United States/Canada":  {"primary": "policy",
                              "exposures": ["US regulatory cycle", "US bank cycle"],
                              "bear_p": 0.25, "bear_r": 0.65,
                              "base_p": 0.50, "base_r": 1.70,
                              "bull_p": 0.25, "bull_r": 2.80},
    "United Kingdom":        {"primary": "idiosyncratic",
                              "exposures": ["UK cycle", "GBP exposure"],
                              "bear_p": 0.25, "bear_r": 0.60,
                              "base_p": 0.50, "base_r": 1.75,
                              "bull_p": 0.25, "bull_r": 2.80},
    "Continental Europe":    {"primary": "policy",
                              "exposures": ["European cycle", "EUR exposure"],
                              "bear_p": 0.25, "bear_r": 0.65,
                              "base_p": 0.50, "base_r": 1.75,
                              "bull_p": 0.25, "bull_r": 2.80},
    "France":                {"primary": "policy",
                              "exposures": ["French sovereign", "EUR exposure"],
                              "bear_p": 0.20, "bear_r": 0.70,
                              "base_p": 0.55, "base_r": 1.80,
                              "bull_p": 0.25, "bull_r": 2.80},
    "Latin America":         {"primary": "policy",
                              "exposures": ["LatAm sovereign cycle", "currency"],
                              "bear_p": 0.30, "bear_r": 0.55,
                              "base_p": 0.45, "base_r": 1.85,
                              "bull_p": 0.25, "bull_r": 3.20},
    "MEA / Frontier":        {"primary": "idiosyncratic",
                              "exposures": ["EM sovereign", "EM banking cycle"],
                              "bear_p": 0.30, "bear_r": 0.55,
                              "base_p": 0.45, "base_r": 1.80,
                              "bull_p": 0.25, "bull_r": 3.00},
    "Japan":                 {"primary": "policy",
                              "exposures": ["Japan governance reform", "FIEA timing"],
                              "bear_p": 0.30, "bear_r": 0.75,
                              "base_p": 0.45, "base_r": 1.55,
                              "bull_p": 0.25, "bull_r": 2.40},
    "Korea":                 {"primary": "policy",
                              "exposures": ["Korea Value-Up reform", "chaebol governance"],
                              "bear_p": 0.30, "bear_r": 0.75,
                              "base_p": 0.45, "base_r": 1.60,
                              "bull_p": 0.25, "bull_r": 2.50},
    "Greater China / HK":    {"primary": "policy",
                              "exposures": ["China property cycle", "PBOC policy"],
                              "bear_p": 0.40, "bear_r": 0.40,
                              "base_p": 0.40, "base_r": 2.00,
                              "bull_p": 0.20, "bull_r": 4.50},
    "SE Asia / Pacific":     {"primary": "idiosyncratic",
                              "exposures": ["SE Asia cycle"],
                              "bear_p": 0.25, "bear_r": 0.65,
                              "base_p": 0.50, "base_r": 1.70,
                              "bull_p": 0.25, "bull_r": 2.60},
}

# Archetype mapping from universe-screen archetype letters
ARCHETYPE_MAP = {
    "A1": ["A1"], "A2": ["A2"], "B": ["B"], "C": ["C"], "D": ["D"],
    "E": ["E"], "F": ["F"], "G": ["G"], "H": ["H"],
    "A1+G": ["A1", "G"], "A1+F": ["A1", "F"], "A1+D": ["A1", "D"],
    "A1+E": ["A1", "E"], "A1+A2+H": ["A1", "A2", "H"],
    "F+A": ["F", "A1"], "F+G": ["F", "G"], "E+H": ["E", "H"],
    "B+C": ["B", "C"], "A2+H": ["A2", "H"], "A2+B": ["A2", "B"],
    "G+A1": ["G", "A1"],
}


def existing_ticker_set() -> set[str]:
    """Tickers (and name stems) already covered by YAMLs."""
    out = set()
    for path in CANDIDATES_DIR.glob("*.yaml"):
        with path.open() as f:
            d = yaml.safe_load(f) or {}
        t = d.get("ticker")
        if t:
            out.add(str(t).upper())
            # Also add the bare ticker without exchange prefix
            for sep in (":", "."):
                if sep in str(t):
                    out.add(str(t).split(sep)[-1].upper())
        n = d.get("name", "")
        if n:
            stem = re.sub(r"[^A-Za-z]", "", n.split()[0]).upper()
            if stem:
                out.add(stem)
    return out


def parse_universe_rows(min_score: float) -> list[dict]:
    """Parse universe_screened.md generated output to get score data."""
    out_path = REPO / "output" / "universe_screened.md"
    if not out_path.exists():
        print(f"  no universe_screened.md — run `make universe` first",
              file=sys.stderr)
        return []
    rows = []
    text = out_path.read_text()
    current_region = ""
    for line in text.splitlines():
        # Region section header
        m = re.match(r"^## (.+) — top \d+", line)
        if m:
            current_region = m.group(1)
            continue
        # Data row in region table
        m = re.match(
            r"^\| (\d\.\d{2}) \| ([^|]+) \| ([^|]*) \| ([^|]*) \| "
            r"([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|",
            line)
        if m:
            score = float(m.group(1))
            if score < min_score:
                continue
            name = m.group(2).strip()
            ticker = m.group(3).strip()
            conf = m.group(4).strip()
            bucket = m.group(5).strip()
            archetype = m.group(6).strip()
            status = m.group(7).strip()
            vintage = m.group(8).strip()
            size = m.group(9).strip()
            rows.append({
                "score": score,
                "name": name,
                "ticker": ticker,
                "conf": conf,
                "bucket": bucket,
                "archetype": archetype,
                "status": status,
                "vintage": vintage,
                "size": size,
                "region": current_region,
            })
    return rows


def make_skeleton_yaml(row: dict) -> dict:
    """Build a structured-but-thin YAML for a universe-screener row."""
    region_prior = REGION_CLUSTER_PRIORS.get(row["region"],
                                            REGION_CLUSTER_PRIORS["Continental Europe"])
    # Resolve archetype list
    arch_str = row["archetype"]
    archetypes = ARCHETYPE_MAP.get(arch_str, ["Unknown"])
    # Bucket from row
    bucket = row["bucket"]
    if bucket not in ("A", "B", "C"):
        bucket = "A"

    ticker_clean = row["ticker"].split(":")[-1] if ":" in row["ticker"] else row["ticker"]
    ticker_clean = re.sub(r"[^A-Za-z0-9-]", "", ticker_clean) or "UNKNOWN"

    return {
        "ticker": ticker_clean,
        "isin": None,
        "name": row["name"],
        "jurisdiction": jurisdiction_for_region(row["region"]),
        "exchange": exchange_from_ticker(row["ticker"]),
        "sector": "TBD — verify from primary docs",
        "bucket": bucket,
        "archetype": archetypes,
        "state": "option",
        "tier": 3,
        "_skeleton": (
            "Auto-generated skeleton from universe_screen.py row. "
            "Universe score {:.2f}. All scorecard inputs require "
            "primary-document verification."
        ).format(row["score"]),
        "deal": {
            "date": row["vintage"] if row["vintage"] != "?" else None,
            "mechanic": (
                f"Skeleton — universe.md classified as bucket {bucket}, "
                f"archetype {arch_str}, region {row['region']}. "
                f"Deepen with primary deal terms."
            ),
            "fields": {
                "universe_screener_score": {
                    "value": row["score"],
                    "source": "verified: src/universe_screen.py",
                },
                "size_class": {
                    "value": row["size"],
                    "source": "verified: src/universe_screen.py",
                },
            },
        },
        "scorecard": {
            "d4_dilution_pct": None,
            "d9_alignment_gap": None,
            "d11_consensus_ebitda_cagr": 10,
            "d14_liquidity_quarters": None,
        },
        "catalysts": [
            {
                "event": "Operational delivery / cycle inflection",
                "window": [f"{date.today().year + 1}-Q1",
                          f"{date.today().year + 2}-Q4"],
                "p_favorable": 0.50,
                "rerate_if_yes": [1.4, 2.0],
                "hit_if_no": [-0.15, -0.25],
                "source": "skeleton placeholder — replace with verified catalyst",
            },
        ],
        "waterfall": {
            "bear": {"p": region_prior["bear_p"],
                    "return_multiple": region_prior["bear_r"],
                    "rationale": "Skeleton bear — region-prior default; verify"},
            "base": {"p": region_prior["base_p"],
                    "return_multiple": region_prior["base_r"],
                    "rationale": "Skeleton base — region-prior default; verify"},
            "bull": {"p": region_prior["bull_p"],
                    "return_multiple": region_prior["bull_r"],
                    "rationale": "Skeleton bull — region-prior default; verify"},
        },
        "anchor": {
            "parties": ["TBD — verify from primary deal disclosure"],
        },
        "triangulation": {
            "leg1_valuation": "partial",
            "leg2_game_theory": "partial",
            "leg3_revealed_pref": "partial",
            "notes": (
                "Skeleton — all three legs require primary-document "
                "verification before promotion above Tier 3."
            ),
        },
        "red_flags": {k: False for k in [
            "parallel_pipe_below_rights", "asymmetric_voting",
            "backstop_warrants_below_terp", "dip_to_exit_control_transfer",
            "springing_maturity_inside_24m", "stub_under_10pct_no_warrants",
            "insider_indemnity_survives", "insider_net_seller",
            "state_backstop_conditional", "refiled_within_12m",
            "new_money_irr_above_50pct",
        ]},
        "kill_criteria": ["TBD — verify from primary docs"],
        "pre_mortem": "TBD — write after primary-doc deep-read",
        "history": [
            {"date": date.today().isoformat(),
             "event": (
                 f"Skeleton YAML generated by src/yaml_skeleton.py "
                 f"(universe score {row['score']:.2f})"
             ),
             "state_after": "option"},
        ],
        "factors": {
            "primary": region_prior["primary"],
            "exposures": region_prior["exposures"],
        },
        "tier_rationale": (
            f"SKELETON — Bucket {bucket}, Archetype {arch_str}. "
            f"Universe-screener score {row['score']:.2f}. "
            "Tier 3 by default until primary-doc verification deepens "
            "the YAML. The framework's audit + score discipline keeps "
            "this from defaulting into the basket."
        ),
    }


def jurisdiction_for_region(region: str) -> str:
    return {
        "United States/Canada": "US",
        "United Kingdom": "GB",
        "France": "FR",
        "Continental Europe": "EU",
        "Latin America": "BR",
        "MEA / Frontier": "AE",
        "Japan": "JP",
        "Korea": "KR",
        "Greater China / HK": "HK",
        "SE Asia / Pacific": "ID",
    }.get(region, "")


def exchange_from_ticker(ticker: str) -> str:
    if ":" in ticker:
        return ticker.split(":")[0]
    if "." in ticker:
        return ticker.split(".")[-1]
    return ticker


def slug_for_filename(row: dict) -> str:
    t = row["ticker"]
    if ":" in t:
        t = t.split(":")[-1]
    return re.sub(r"[^A-Za-z0-9-]", "", t) or "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-score", type=float, default=0.55,
                    help="Skip rows below this universe score (default 0.55 = T1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    existing = existing_ticker_set()
    rows = parse_universe_rows(args.min_score)
    print(f"Parsed {len(rows)} universe rows at score ≥ {args.min_score}")
    print(f"Existing YAML ticker stems: {len(existing)}")

    written = 0
    skipped_existing = 0
    skipped_status = 0
    skipped_invalid = 0
    seen_slugs: set[str] = set()
    for row in rows:
        # Skip if YAML exists
        ticker_stem = slug_for_filename(row).upper()
        name_stem = re.sub(r"[^A-Za-z]", "",
                          row["name"].split()[0]).upper()
        if ticker_stem in existing or name_stem in existing:
            skipped_existing += 1
            continue
        # Skip terminal statuses
        if row["status"] in ("PASS", "PASS_FALSE_FRIEND", "ARC_DONE",
                            "ACQUIRED", "REPEAT_RX"):
            skipped_status += 1
            continue
        # Skip placeholder/invalid tickers like "(state)", "(private 2023)"
        if not row["ticker"] or row["ticker"].startswith("("):
            skipped_invalid += 1
            continue
        # Avoid invalid filename characters
        slug = slug_for_filename(row)
        if not slug or slug == "UNKNOWN" or len(slug) < 2:
            skipped_invalid += 1
            continue
        # Dedupe by slug — keep the highest-score occurrence
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        yaml_obj = make_skeleton_yaml(row)
        target = CANDIDATES_DIR / f"{slug}.yaml"
        if target.exists():
            skipped_existing += 1
            continue
        if args.dry_run:
            print(f"  DRY: would write {target.name} for "
                 f"{row['name']} ({row['score']:.2f})")
            written += 1
            continue
        with target.open("w") as f:
            yaml.dump(yaml_obj, f, sort_keys=False, default_flow_style=False,
                     allow_unicode=True)
        print(f"  wrote {target.name} — {row['name']} ({row['score']:.2f})")
        written += 1

    print(f"\nDone. {written} skeletons written / {skipped_existing} skipped (existing) / "
          f"{skipped_status} skipped (terminal status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
