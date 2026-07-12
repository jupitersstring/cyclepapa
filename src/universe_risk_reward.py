#!/usr/bin/env python3
"""
universe_risk_reward.py — quantitative reward/risk ranking across the FULL universe.

Closes the gap the prior workbook had: it ranked only the 21 hand-built
Tier 1+2 YAMLs, which were chosen for archetype coverage / prior research
/ user requests, not as a quantitative top-21 sample of the universe.

This script ranks across the entire universe (universe_screened.md's
per-region top-15 tables — currently 13 T0 + 33 T1 + 47 T2 = 93 named
candidates pre-filter) on a transparent formula:

For each name:
  bear_loss = max(0.10, 0.65 - 0.30 * score)
    * archetype tilt: A1 / A2 → *0.75 (sovereign-anchored floor)
                      E / C   → *0.85 (court / LME floor)
  bull       = 1.50 + 1.50 * min(score, 1.5)
    * archetype tilt: F → *1.15, H → *1.10
  base       = 1 + 0.5*(bull - 1) + 0.5*(1 - bear_loss)
  EV         = 0.30 * (1 - bear_loss) + 0.45 * base + 0.25 * bull
  RR ratio   = (EV - 1) / bear_loss

Where a hand-built YAML exists (matched by ticker), its real waterfall
numbers override the proxy. Each output row is tagged REAL or PROXY so
the verification gap is visible.

Filters:
- status must be OK or PRE_RECAP (drops PASS_FALSE_FRIEND, ACQUIRED,
  ARC_DONE, REPEAT_RX)
- ticker must be a real exchange:code (drops "(state)", "(private)",
  "(delisted)" placeholders)
- score must be >= 0.15 (soft threshold; prefer surfacing over cliff-drop)

Output:
  output/universe_risk_reward.md   (ranked markdown)
  output/universe_risk_reward.csv  (for the workbook)
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


def clean_display_name(n: str) -> str:
    """Sanitize a name pulled from a universe.md row for institutional-
    clean display: strip stringified-list wrappers (['NAME'] -> NAME),
    the embedded "(TICKER) (CIK NNNN)" EDGAR suffix, and collapse
    whitespace. Legacy rows promoted before the parser fixes carry these
    artifacts; cleaning at render keeps the deliverable clean without
    rewriting universe.md."""
    if not n:
        return ""
    s = str(n).strip()
    # ['FOO BAR'] or ["FOO"] -> FOO BAR
    m = re.match(r"^\[\s*['\"](.+?)['\"]\s*(?:,.*)?\]$", s)
    if m:
        s = m.group(1)
    # strip trailing "(TICKER) (CIK NNNN)" or bare "(CIK NNNN)"
    s = re.sub(r"\s*(?:\([A-Z0-9.,\-\s]+\)\s*)?\(CIK\s*\d+\).*$", "", s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip(" '\"[]")
    return s or str(n).strip()

try:
    import yaml
except ImportError:
    print("Install PyYAML", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_SCREENED = REPO / "output" / "universe_screened.md"
CANDIDATES = REPO / "data" / "candidates"
OUT_MD = REPO / "output" / "universe_risk_reward.md"
OUT_CSV = REPO / "output" / "universe_risk_reward.csv"

# Standard waterfall probabilities. Bear-heavy because the universe
# is, by selection, restructuring names — failure mode is real.
P_BEAR, P_BASE, P_BULL = 0.30, 0.45, 0.25


@dataclass
class UniverseRow:
    region: str
    score: float
    name: str
    ticker: str
    conf: str
    bucket: str
    archetype: str
    status: str
    vintage: str
    size: str
    bear_loss: float = 0.0
    bull_r: float = 0.0
    base_r: float = 0.0
    ev: float = 0.0
    rr: float = 0.0
    source: str = "PROXY"      # PROXY or REAL
    yaml_ticker: str = ""


def parse_universe_screened() -> list[UniverseRow]:
    """Pull every named row from each region's top-15 table.

    universe_screened.md has multiple table types; we only want the
    per-region top-N tables whose canonical header is:
        | Score | Name | Ticker | Conf | Bucket | Archetype | Status | Vintage | Size |
    Other aggregation tables in the same file use different column
    orders (rank-first, name-bolded). Skip anything with ** bold and
    only accept lines after a `## ... — top N` section header that's
    followed by the exact 9-column data header above.
    """
    text = UNIVERSE_SCREENED.read_text()
    rows: list[UniverseRow] = []
    region = ""
    in_per_region_section = False
    saw_correct_header = False
    rgx = re.compile(
        r"^\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)"
        r"\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)"
        r"\s*\|\s*([^|]+?)\s*\|"
    )
    CANONICAL_HEADER = re.compile(
        r"^\|\s*Score\s*\|\s*Name\s*\|\s*Ticker\s*\|\s*Conf\s*\|"
        r"\s*Bucket\s*\|\s*Archetype\s*\|\s*Status\s*\|\s*Vintage\s*\|"
        r"\s*Size\s*\|", re.I)
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s+—\s+top\s+\d+", line)
        if m:
            region = m.group(1).strip()
            in_per_region_section = True
            saw_correct_header = False
            continue
        if line.startswith("## "):
            # any other ## heading closes the per-region section
            in_per_region_section = False
            continue
        if not in_per_region_section:
            continue
        if CANONICAL_HEADER.match(line):
            saw_correct_header = True
            continue
        if not saw_correct_header:
            continue
        if "**" in line:
            # bolded rows belong to other table types
            continue
        if not line.strip().startswith("|"):
            saw_correct_header = False
            continue
        if line.strip().startswith("|---"):
            continue
        mm = rgx.match(line)
        if not mm:
            continue
        rows.append(UniverseRow(
            region=region,
            score=float(mm.group(1)),
            name=clean_display_name(mm.group(2)),
            ticker=mm.group(3).strip(),
            conf=mm.group(4).strip(),
            bucket=mm.group(5).strip(),
            archetype=mm.group(6).strip(),
            status=mm.group(7).strip(),
            vintage=mm.group(8).strip(),
            size=mm.group(9).strip(),
        ))
    return rows


def proxy_reward_risk(row: UniverseRow) -> None:
    """Populate bear_loss / bull_r / base_r / ev / rr on the row using
    the transparent proxy formula. Overridden by load_real_yaml() if
    a hand-built YAML exists for this ticker."""
    s = max(0.0, min(1.5, row.score))
    bear_loss = max(0.10, 0.65 - 0.30 * s)
    bull = 1.50 + 1.50 * s
    arch = (row.archetype or "").upper()
    if "A1" in arch or "A2" in arch:
        bear_loss *= 0.75
    elif "E" in arch.split("+") or arch == "E" or "C" in arch.split("+"):
        bear_loss *= 0.85
    if "F" in arch.split("+") or arch == "F":
        bull *= 1.15
    if "H" in arch.split("+") or arch == "H":
        bull *= 1.10
    base = 1.0 + 0.5 * (bull - 1.0) + 0.5 * (1.0 - bear_loss)
    ev = P_BEAR * (1 - bear_loss) + P_BASE * base + P_BULL * bull
    row.bear_loss = round(bear_loss, 3)
    row.bull_r = round(bull, 2)
    row.base_r = round(base, 2)
    row.ev = round(ev, 2)
    row.rr = round((ev - 1) / max(0.001, bear_loss), 1)
    row.source = "PROXY"


def load_real_yamls() -> dict[str, dict]:
    """Map ticker stem → YAML dict for Tier 1+2 candidates."""
    out: dict[str, dict] = {}
    for path in CANDIDATES.glob("*.yaml"):
        with path.open() as f:
            d = yaml.safe_load(f) or {}
        if not isinstance(d, dict):
            continue
        if d.get("tier") not in (1, 2):
            continue
        if d.get("state") == "pass":
            continue
        t = d.get("ticker")
        if t is None:
            continue
        # Match by stem (last segment after : or .)
        stem = re.sub(r"[^A-Za-z0-9-]", "", str(t).split(":")[-1]).upper()
        if stem:
            out[stem] = d
    return out


def overlay_real(row: UniverseRow, yamls: dict[str, dict]) -> None:
    """If a hand-built YAML matches this row's ticker, override the proxy
    with the YAML's bottom-up waterfall numbers."""
    if not row.ticker:
        return
    tstem = re.sub(r"[^A-Za-z0-9-]", "", row.ticker.split(":")[-1]).upper()
    d = yamls.get(tstem)
    if d is None:
        return
    w = d.get("waterfall") or {}
    bear = w.get("bear") or {}
    base = w.get("base") or {}
    bull = w.get("bull") or {}
    bp = float(bear.get("p", 0) or 0)
    br = float(bear.get("return_multiple", 0) or 0)
    np_ = float(base.get("p", 0) or 0)
    nr = float(base.get("return_multiple", 0) or 0)
    up = float(bull.get("p", 0) or 0)
    ur = float(bull.get("return_multiple", 0) or 0)
    if bp + np_ + up < 0.5:        # malformed
        return
    ev = bp * br + np_ * nr + up * ur
    bear_loss = max(0.01, 1.0 - br)
    row.bear_loss = round(bear_loss, 3)
    row.bull_r = round(ur, 2)
    row.base_r = round(nr, 2)
    row.ev = round(ev, 2)
    row.rr = round((ev - 1) / bear_loss, 1)
    row.source = "REAL"
    row.yaml_ticker = d.get("ticker", "")


# Status terms that bin a name OUT of the active universe
STATUS_DROP = {"PASS_FALSE_FRIEND", "ACQUIRED", "ARC_DONE", "REPEAT_RX"}
# Ticker placeholders that mean the name is genuinely not investable in
# listed-equity form (private / delisted / state-held). A bare "—" or
# empty ticker is NOT in this set: many real listed issuers arrive
# without a ticker (e.g. Brazilian CVM records that don't expose the B3
# symbol), and dropping them silently loses whole source legs.
TICKER_NOT_INVESTABLE = re.compile(
    r"^\(.*\)$|^\(state\)|^\(private|delisted|taken private|"
    r"^Hitachi 40%", re.I)
# Name-column placeholders (the name itself isn't a real company).
NAME_NOT_INVESTABLE = re.compile(
    r"^\(|^—$|^-$|^\?+$|census$|^various\b", re.I)


def is_investable(row: UniverseRow) -> bool:
    if row.status.upper() in STATUS_DROP:
        return False
    if row.score < 0.15:
        return False
    tkr = (row.ticker or "").strip()
    if tkr and TICKER_NOT_INVESTABLE.match(tkr):
        return False
    # Tickerless rows are kept IF the name is a real company (not a
    # placeholder) — ranked/deduped by name. Only drop when BOTH the
    # ticker is missing AND the name is unusable.
    if (not tkr or tkr in ("—", "-")):
        nm = (row.name or "").strip()
        if not nm or NAME_NOT_INVESTABLE.match(nm) or len(nm) < 4:
            return False
    return True


JUR_TO_REGION = {
    "US": "United States/Canada", "CA": "United States/Canada",
    "GB": "United Kingdom", "UK": "United Kingdom",
    "FR": "Continental Europe", "DE": "Continental Europe",
    "ES": "Continental Europe", "IT": "Continental Europe",
    "NL": "Continental Europe", "BE": "Continental Europe",
    "AT": "Continental Europe", "PT": "Continental Europe",
    "CH": "Continental Europe", "SE": "Continental Europe",
    "EU": "Continental Europe",
    "AR": "Latin America", "BR": "Latin America", "MX": "Latin America",
    "CL": "Latin America", "CO": "Latin America", "PE": "Latin America",
    "AE": "MEA / Frontier", "SA": "MEA / Frontier", "ZA": "MEA / Frontier",
    "NG": "MEA / Frontier", "TR": "MEA / Frontier",
    "JP": "Japan", "KR": "Korea",
    "HK": "Greater China / HK", "CN": "Greater China / HK",
    "ID": "SE Asia / Pacific", "NZ": "SE Asia / Pacific",
    "AU": "SE Asia / Pacific", "TH": "SE Asia / Pacific",
    "SG": "SE Asia / Pacific",
}


def add_yamls_not_in_universe_top(rows: list[UniverseRow],
                                  yamls: dict[str, dict]) -> list[UniverseRow]:
    """Hand-built YAMLs that don't appear in the per-region top-N tables
    should still rank in the universe-wide list. Synthesize a row for
    each, using the YAML jurisdiction to map region. Score is set to
    NaN-style 0.0 since the universe screener didn't surface it — the
    REAL waterfall override produces the actual RR ranking."""
    existing_stems = {
        re.sub(r"[^A-Za-z0-9-]", "", r.ticker.split(":")[-1]).upper()
        for r in rows if r.ticker
    }
    added: list[UniverseRow] = []
    for stem, d in yamls.items():
        if stem in existing_stems:
            continue
        region = JUR_TO_REGION.get(d.get("jurisdiction", "").upper(),
                                   "Unspecified")
        ticker_full = (f"{d.get('exchange', '')}:{d.get('ticker', '')}"
                       if d.get("exchange") else str(d.get("ticker", "")))
        archetype = d.get("archetype") or []
        if isinstance(archetype, list):
            archetype = "+".join(str(a) for a in archetype)
        added.append(UniverseRow(
            region=region,
            # Surrogate score 1.00 so the row clears the 0.20 filter; the
            # REAL waterfall override drives the actual RR ranking so the
            # surrogate doesn't bias the math.
            score=1.00,
            name=d.get("name", "") or stem,
            ticker=ticker_full,
            conf="★",
            bucket=str(d.get("bucket", "A")),
            archetype=str(archetype),
            status="OK",
            vintage=str((d.get("deal") or {}).get("date", "")),
            size="—",
        ))
    return rows + added


def main() -> int:
    if not UNIVERSE_SCREENED.exists():
        print("Run `make universe` first.", file=sys.stderr)
        return 1
    rows = parse_universe_screened()
    print(f"Parsed {len(rows)} rows from {len(set(r.region for r in rows))} regions")
    yamls = load_real_yamls()
    print(f"Found {len(yamls)} hand-built Tier 1+2 YAMLs")

    rows = add_yamls_not_in_universe_top(rows, yamls)
    print(f"After adding unrepresented YAMLs: {len(rows)} candidate rows")

    keep: list[UniverseRow] = []
    dropped = 0
    for r in rows:
        if not is_investable(r):
            dropped += 1
            continue
        proxy_reward_risk(r)
        overlay_real(r, yamls)
        keep.append(r)
    print(f"Investable: {len(keep)} ({dropped} dropped on status/ticker/score)")
    real_n = sum(1 for r in keep if r.source == "REAL")
    print(f"  REAL waterfalls (YAML): {real_n}    PROXY: {len(keep) - real_n}")

    # Dedup: same ticker can appear in multiple per-region tables.
    # Keep the highest-score occurrence (or REAL if any).
    by_ticker: dict[str, UniverseRow] = {}
    for r in keep:
        key = re.sub(r"[^A-Za-z0-9-]", "", r.ticker.split(":")[-1]).upper()
        if not key:
            # tickerless (e.g. Brazilian CVM) — key by name stem so they
            # don't all collapse into one empty-key bucket.
            key = "NAME:" + re.sub(r"[^A-Za-z0-9]", "",
                                   (r.name or "")).upper()[:24]
        if key not in by_ticker:
            by_ticker[key] = r
            continue
        prev = by_ticker[key]
        # Prefer REAL over PROXY; among ties prefer higher score
        if (r.source == "REAL" and prev.source != "REAL") or \
           (r.source == prev.source and r.score > prev.score):
            by_ticker[key] = r
    keep = list(by_ticker.values())
    print(f"After ticker dedup: {len(keep)}")

    # Rank by reward/risk ratio descending
    keep.sort(key=lambda r: -r.rr)

    # Write markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MD.open("w") as f:
        f.write("# Universe-wide quantitative reward/risk ranking\n\n")
        f.write("Auto-generated by `src/universe_risk_reward.py`. "
                "Computed across every named candidate in "
                "`output/universe_screened.md` whose status is OK or "
                "PRE_RECAP and whose ticker is a real exchange code.\n\n")
        f.write(f"- **{len(keep)} investable names ranked** "
                f"({real_n} with hand-built YAML waterfalls = REAL; "
                f"{len(keep) - real_n} with formula proxy = PROXY).\n")
        f.write("- Reward/Risk = (EV× − 1) ÷ Bear loss.\n")
        f.write("- Proxy formula (transparent): "
                "`bear_loss = max(0.10, 0.65 − 0.30·score)` "
                "tilted ×0.75 for A1/A2 archetypes; "
                "`bull = 1.50 + 1.50·score` tilted ×1.10 for H, "
                "×1.15 for F.\n\n")
        f.write("## Top 60\n\n")
        f.write("| Rank | Source | Ticker | Name | Region | Score | "
                "Bucket | Archetype | Bear loss | Base R | Bull R | "
                "EV× | Reward/Risk |\n")
        f.write("|---:|---|---|---|---|---:|---|---|---:|---:|---:|"
                "---:|---:|\n")
        for i, r in enumerate(keep[:60]):
            f.write(f"| {i+1} | {r.source} | {r.ticker} | "
                    f"{r.name[:35]} | {r.region[:22]} | "
                    f"{r.score:.2f} | {r.bucket} | "
                    f"{r.archetype[:10]} | "
                    f"{r.bear_loss*100:.0f}% | "
                    f"{r.base_r:.2f}× | {r.bull_r:.2f}× | "
                    f"{r.ev:.2f}× | **{r.rr:.1f}×** |\n")
        f.write("\n## Coverage gap: top 10 quant picks WITHOUT a YAML\n\n")
        gaps = [r for r in keep[:60] if r.source == "PROXY"][:10]
        f.write("These are the highest-RR names by quant proxy that "
                "don't yet have a hand-built YAML. Building these "
                "closes the comprehensiveness gap.\n\n")
        f.write("| Rank | Ticker | Name | Region | Score | "
                "Archetype | Quant RR |\n")
        f.write("|---:|---|---|---|---:|---|---:|\n")
        for r in gaps:
            rank = keep.index(r) + 1
            f.write(f"| {rank} | {r.ticker} | {r.name[:40]} | "
                    f"{r.region[:22]} | {r.score:.2f} | "
                    f"{r.archetype} | {r.rr:.1f}× |\n")

    # Write CSV for the workbook
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "source", "ticker", "name", "region",
                    "score", "bucket", "archetype", "status", "size",
                    "bear_loss", "base_r", "bull_r", "ev", "rr"])
        for i, r in enumerate(keep):
            w.writerow([i + 1, r.source, r.ticker, r.name, r.region,
                        r.score, r.bucket, r.archetype, r.status, r.size,
                        r.bear_loss, r.base_r, r.bull_r, r.ev, r.rr])

    print(f"\nWrote {OUT_MD}")
    print(f"Wrote {OUT_CSV}")
    print(f"\nTop 10 universe-wide:")
    for i, r in enumerate(keep[:10]):
        print(f"  {i+1:2d}. {r.rr:5.1f}×  [{r.source}]  "
              f"{r.ticker:18s} {r.name[:38]:38s} "
              f"({r.region[:18]:18s})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
