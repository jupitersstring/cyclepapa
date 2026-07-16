"""Daily-diff report — compare today's results to the most recent
prior run and surface what changed: new entrants/exits per sleeve,
resolution-score jumps, new PDMR/TR-1 activity, catalyst promotions.

Run after screen_v3.py to write a `diff_YYYYMMDD.md` and a CSV with
per-ticker change records.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


HERE = Path(os.path.dirname(os.path.abspath(__file__)))


def latest_results(exclude: str | None = None) -> list[Path]:
    """Most-recent-first list of results_*.csv (excluding the path
    passed as `exclude`)."""
    out = []
    for p in HERE.glob("results_*.csv"):
        if "_top30" in p.name or "_sleeves" in p.name:
            continue
        if exclude and p.name == os.path.basename(exclude):
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def compute_diff(today: pd.DataFrame, prior: pd.DataFrame) -> dict:
    """Per-ticker comparison of meaningful fields.

    Scope guard: when the two runs cover materially different ticker
    sets (e.g. a UK-only run vs a full-universe run) the added/removed
    lists are run-scope noise, not real universe changes. We flag that
    in the output so the reader doesn't misread 250 'removed' names as
    delistings."""
    fields = ["in_setup_sleeve", "in_fundamentals_sleeve", "in_micro_sleeve",
              "catalyst", "phase", "expected_irr", "composite_score",
              "resolution_score", "rns_pdmr_buys", "rns_tr1_buys",
              "rns_tr1_activist_buys"]
    today_idx = today.set_index("ticker")
    prior_idx = prior.set_index("ticker")
    common = today_idx.index.intersection(prior_idx.index)
    added = today_idx.index.difference(prior_idx.index)
    removed = prior_idx.index.difference(today_idx.index)

    sleeve_moves: list[dict] = []
    resolution_jumps: list[dict] = []
    irr_jumps: list[dict] = []
    new_insiders: list[dict] = []
    new_activists: list[dict] = []
    catalyst_promotions: list[dict] = []

    for tk in common:
        a = today_idx.loc[tk]
        b = prior_idx.loc[tk]
        for sleeve in ("in_setup_sleeve", "in_fundamentals_sleeve",
                       "in_micro_sleeve"):
            t = bool(a.get(sleeve, False))
            p = bool(b.get(sleeve, False))
            if t != p:
                sleeve_moves.append({
                    "ticker": tk, "sleeve": sleeve,
                    "from": p, "to": t,
                    "irr": round(float(a.get("expected_irr") or 0), 3),
                })
        # Resolution-score jump >= 0.10
        r_now = float(a.get("resolution_score") or 0)
        r_prior = float(b.get("resolution_score") or 0)
        if r_now - r_prior >= 0.10:
            resolution_jumps.append({
                "ticker": tk, "from": round(r_prior, 3),
                "to": round(r_now, 3),
                "delta": round(r_now - r_prior, 3),
            })
        # IRR change >= 5pp
        irr_now = float(a.get("expected_irr") or 0)
        irr_prior = float(b.get("expected_irr") or 0)
        if abs(irr_now - irr_prior) >= 0.05:
            irr_jumps.append({
                "ticker": tk, "from_pct": round(irr_prior * 100, 1),
                "to_pct": round(irr_now * 100, 1),
                "delta_pp": round((irr_now - irr_prior) * 100, 1),
            })
        # New insider activity
        ib_now = float(a.get("rns_pdmr_buys") or 0)
        ib_prior = float(b.get("rns_pdmr_buys") or 0)
        if ib_now > ib_prior:
            new_insiders.append({
                "ticker": tk, "new_buys": int(ib_now - ib_prior),
                "total_now": int(ib_now),
            })
        ab_now = float(a.get("rns_tr1_activist_buys") or 0)
        ab_prior = float(b.get("rns_tr1_activist_buys") or 0)
        if ab_now > ab_prior:
            new_activists.append({
                "ticker": tk, "new_activist_buys": int(ab_now - ab_prior),
                "total_now": int(ab_now),
                "holders": a.get("activist_holders") or "",
            })
        # Catalyst promotion
        if a.get("catalyst") != b.get("catalyst"):
            catalyst_promotions.append({
                "ticker": tk,
                "from": b.get("catalyst") or "",
                "to": a.get("catalyst") or "",
            })
    size_ratio = len(today) / max(1, len(prior))
    scope_mismatch = size_ratio < 0.8 or size_ratio > 1.25
    return {
        "scope_mismatch": scope_mismatch,
        "added": list(added),
        "removed": list(removed),
        "sleeve_moves": sleeve_moves,
        "resolution_jumps": sorted(resolution_jumps,
                                   key=lambda r: -r["delta"]),
        "irr_jumps": sorted(irr_jumps, key=lambda r: -abs(r["delta_pp"])),
        "new_insiders": sorted(new_insiders,
                               key=lambda r: -r["new_buys"]),
        "new_activists": sorted(new_activists,
                                key=lambda r: -r["new_activist_buys"]),
        "catalyst_promotions": catalyst_promotions,
    }


def render_markdown(today_path: Path, prior_path: Path, diff: dict) -> str:
    lines = [
        f"# Diff report — {today_path.name} vs {prior_path.name}",
        f"\nGenerated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if diff.get("scope_mismatch"):
        lines.append(
            "> **Scope warning:** the two runs cover materially "
            "different ticker counts — the added/removed lists below "
            "reflect run scope, not universe changes.\n")
    if diff["new_activists"]:
        lines.append("## NEW activist accumulation (highest priority)")
        for r in diff["new_activists"][:10]:
            lines.append(f"- **{r['ticker']}** — {r['new_activist_buys']} new "
                         f"activist TR-1(s); holders: {r['holders'][:80]}")
        lines.append("")
    if diff["new_insiders"]:
        lines.append("## NEW insider buys")
        for r in diff["new_insiders"][:10]:
            lines.append(f"- **{r['ticker']}** — {r['new_buys']} new PDMR "
                         f"buy(s) (total now: {r['total_now']})")
        lines.append("")
    if diff["resolution_jumps"]:
        lines.append("## Resolution-score jumps (≥0.10)")
        for r in diff["resolution_jumps"][:15]:
            lines.append(f"- **{r['ticker']}** — "
                         f"{r['from']:.2f} → {r['to']:.2f} (+{r['delta']:.2f})")
        lines.append("")
    if diff["catalyst_promotions"]:
        lines.append("## Catalyst promotions")
        for r in diff["catalyst_promotions"]:
            lines.append(f"- **{r['ticker']}** — {r['from']} → {r['to']}")
        lines.append("")
    if diff["sleeve_moves"]:
        lines.append("## Sleeve membership changes")
        for r in diff["sleeve_moves"][:30]:
            arrow = "ENTERED" if r["to"] else "exited"
            lines.append(f"- **{r['ticker']}** — {arrow} "
                         f"{r['sleeve'].replace('in_','').replace('_sleeve','')} "
                         f"(IRR {r['irr']*100:.1f}%)")
        lines.append("")
    if diff["irr_jumps"]:
        lines.append("## IRR changes ≥5pp")
        for r in diff["irr_jumps"][:15]:
            direction = "▲" if r["delta_pp"] > 0 else "▼"
            lines.append(f"- **{r['ticker']}** — "
                         f"{r['from_pct']:.1f}% → {r['to_pct']:.1f}% "
                         f"({direction} {abs(r['delta_pp']):.1f}pp)")
        lines.append("")
    if diff["added"]:
        lines.append(f"## New names in universe ({len(diff['added'])})")
        lines.append("  " + ", ".join(sorted(diff["added"])[:50]))
        lines.append("")
    if diff["removed"]:
        lines.append(f"## Names dropped from this run ({len(diff['removed'])})")
        lines.append("  " + ", ".join(sorted(diff["removed"])[:50]))
        lines.append("")
    if not any(diff[k] for k in ("new_activists", "new_insiders",
                                 "resolution_jumps", "catalyst_promotions",
                                 "sleeve_moves", "irr_jumps", "added",
                                 "removed")):
        lines.append("No material changes since last run.")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("today", nargs="?", help="results_*.csv (defaults to latest)")
    p.add_argument("--prior", help="path to prior results CSV "
                   "(defaults to second-latest)")
    args = p.parse_args()
    candidates = latest_results()
    if not candidates:
        print("No results CSV found", file=sys.stderr)
        return 1
    today_path = Path(args.today) if args.today else candidates[0]
    if args.prior:
        prior_path = Path(args.prior)
    else:
        priors = latest_results(exclude=str(today_path))
        if not priors:
            print("Need at least two results CSVs for a diff", file=sys.stderr)
            return 1
        prior_path = priors[0]
    today = pd.read_csv(today_path)
    prior = pd.read_csv(prior_path)
    diff = compute_diff(today, prior)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    out_md = HERE / f"diff_{stamp}.md"
    with open(out_md, "w") as f:
        f.write(render_markdown(today_path, prior_path, diff))
    print(f"[diff] {today_path.name} vs {prior_path.name}", file=sys.stderr)
    print(f"  new_activists:   {len(diff['new_activists'])}", file=sys.stderr)
    print(f"  new_insiders:    {len(diff['new_insiders'])}", file=sys.stderr)
    print(f"  resolution≥0.1:  {len(diff['resolution_jumps'])}",
          file=sys.stderr)
    print(f"  catalyst moves:  {len(diff['catalyst_promotions'])}",
          file=sys.stderr)
    print(f"  sleeve moves:    {len(diff['sleeve_moves'])}", file=sys.stderr)
    print(f"  written: {out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
