"""Consensus meta-ranker -- the empirical answer to "are these the best
across the entire universe?"

A name surfaced by exactly one ranker may be a model artifact. A name
surfaced by 4-6 independent rankers built from different evidence
(PSU forensics, governance, valuation, insider behavior, tender
mechanics, capital-structure forcing functions) is structurally
asymmetric. That convergence is what we want to maximise.

Inputs (every published ranker in the repo):
  unified_composite.csv              the original composite (top 100)
  informational_buys.csv             Cohen-Malloy-Pomorski 5-cond
  bastian_forcing.csv                debt-haircut / self-help microcap
  psu_asymmetric_full.csv            forward-conditional PSU triggers
  psu_valcreate.csv                  per-share value-creation alignment
  psu_gov_asymmetry.csv              thesis-led PSU/gov composite
  grand_unified_ranked.csv           coverage-normalised 7-layer rank
  special_situations_unified.csv     EDGAR-stream pipeline rollup
  PSU_ARCHETYPES.md (parsed)         38 PSU/gov archetype winners
  ASYMMETRIC_BY_ARCHETYPE.md (parsed) 19 thesis archetype winners

Output:
  consensus_ranking.csv              ticker, n_screens, sum_rank_z,
                                     screens_list, archetypes_won
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_csv_top(path: Path, score_field: str | None = None,
                  top_n: int = 200,
                  sort_desc: bool = True) -> list[tuple[str, float, int]]:
    """Return [(ticker, score, rank)] for top_n rows of a CSV.
    If score_field is None, uses the existing row order (assumed sorted)."""
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open()))
    if score_field:
        def parse(v):
            try: return float(v or 0)
            except: return 0.0
        rows.sort(key=lambda r: parse(r.get(score_field)),
                  reverse=sort_desc)
    out = []
    for i, r in enumerate(rows[:top_n], 1):
        tk = r.get("ticker") or r.get("symbol")
        if not tk:
            continue
        sc = 0.0
        if score_field and r.get(score_field):
            try: sc = float(r[score_field])
            except: sc = 0.0
        out.append((tk, sc, i))
    return out


def load_archetype_md(path: Path) -> dict[str, list[str]]:
    """Parse winner names from a Markdown archetype file.
    Returns {ticker: [archetype_id, ...]}."""
    if not path.exists():
        return {}
    text = path.read_text()
    winners = defaultdict(list)
    blocks = re.findall(
        r"###?\s+(\w+\d+\.?\s+[^\n]+?)\n.*?\*\*Winner:\s*([A-Z][A-Z0-9.\-]{0,10})\*\*",
        text, re.S,
    )
    for arch, tk in blocks:
        arch_id = arch.split(".")[0].strip()
        winners[tk].append(arch_id)
    return dict(winners)


def main() -> int:
    # Each entry: (label, path, score_field_or_None, top_n)
    sources = [
        ("unified_composite", ROOT / "unified_composite.csv", "score", 150),
        ("informational_buys", ROOT / "informational_buys.csv", "total", 100),
        ("bastian_forcing", ROOT / "bastian_forcing.csv", "score", 50),
        ("psu_asymmetric_full", ROOT / "psu_asymmetric_full.csv", None, 200),
        ("psu_valcreate", ROOT / "psu_valcreate.csv", "score", 150),
        ("psu_gov_asymmetry", ROOT / "psu_gov_asymmetry.csv", None, 150),
        ("grand_unified", ROOT / "grand_unified_ranked.csv", "norm_score", 150),
        ("special_situations", ROOT / "special_situations_unified.csv", "score", 200),
    ]

    in_screen: dict[str, set] = defaultdict(set)
    best_rank: dict[str, dict] = defaultdict(dict)
    score_by: dict[str, dict] = defaultdict(dict)

    for label, path, field, top_n in sources:
        rows = load_csv_top(path, field, top_n)
        print(f"  {label:<22} {len(rows)} from {path.name}")
        for tk, sc, rk in rows:
            in_screen[tk].add(label)
            best_rank[tk][label] = rk
            score_by[tk][label] = sc

    # Archetype winners from markdown
    arch_winners = {}
    for fn in ("PSU_ARCHETYPES.md", "ASYMMETRIC_BY_ARCHETYPE.md"):
        w = load_archetype_md(ROOT / fn)
        for tk, archs in w.items():
            arch_winners.setdefault(tk, []).extend(
                [f"{fn.replace('.md','').replace('_','')[:6]}:{a}" for a in archs])
        print(f"  {fn:<35} {len(w)} archetype winners")

    # Build consensus rows: union of all ticker appearances
    all_tickers = set(in_screen) | set(arch_winners)
    print(f"\nConsensus universe: {len(all_tickers)} distinct tickers across all sources\n")

    rows = []
    for tk in all_tickers:
        screens = in_screen.get(tk, set())
        n_screens = len(screens)
        archs = arch_winners.get(tk, [])
        n_archs = len(set(archs))
        # Combined consensus score: each screen contributes (1 - rank/topN)
        # so being rank 1 contributes near 1.0, rank topN contributes 0
        contrib = 0.0
        for label, path, field, top_n in sources:
            rk = best_rank[tk].get(label)
            if rk:
                contrib += max(0.0, 1.0 - (rk - 1) / top_n)
        # Archetype winner bonus
        contrib += n_archs * 0.5
        rows.append({
            "ticker": tk,
            "n_screens": n_screens,
            "n_archetypes_won": n_archs,
            "consensus_score": round(contrib, 3),
            "screens": ",".join(sorted(screens)),
            "archetypes": ",".join(sorted(set(archs))),
            "best_rank_grand_unified": best_rank[tk].get("grand_unified"),
            "best_rank_composite": best_rank[tk].get("unified_composite"),
            "best_rank_info_buys": best_rank[tk].get("informational_buys"),
            "best_rank_bastian": best_rank[tk].get("bastian_forcing"),
        })

    rows.sort(key=lambda r: (-r["n_screens"], -r["consensus_score"]))

    out = ROOT / "consensus_ranking.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")

    # Tier the consensus universe
    print(f"\nConsensus tier distribution:")
    from collections import Counter
    by_n = Counter(r["n_screens"] for r in rows)
    for n in sorted(by_n, reverse=True):
        print(f"  {n} screens: {by_n[n]} names")

    # Top by consensus
    print(f"\n=== TOP 30 by n_screens, then consensus_score ===")
    print(f"{'TKR':<8}{'NS':<3}{'NA':<3}{'CONS':<7}{'SCREENS':<60}{'ARCHETYPES'}")
    for r in rows[:30]:
        print(f"{r['ticker']:<8}{r['n_screens']:<3}{r['n_archetypes_won']:<3}"
              f"{r['consensus_score']:<7}"
              f"{r['screens'][:58]:<60}{r['archetypes'][:60]}")

    # Names that win >= 3 screens AND archetype winner
    convergent = [r for r in rows if r["n_screens"] >= 3
                   and r["n_archetypes_won"] >= 1]
    print(f"\n=== HIGH-CONVICTION CONVERGENT ({len(convergent)} names: "
          f">=3 screens AND archetype winner) ===")
    for r in convergent[:25]:
        print(f"  {r['ticker']:<8} screens={r['n_screens']} "
              f"archetypes={r['n_archetypes_won']}: {r['archetypes']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
