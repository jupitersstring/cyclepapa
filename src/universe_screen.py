#!/usr/bin/env python3
"""
universe_screen.py — apply the framework to the entire universe.md.

Parses every markdown table in universe.md, extracts each named
candidate, classifies the archetype from the notes column using keyword
heuristics, and emits a triage-scored ranking. Output goes to
output/universe_screened.md.

This is NOT a substitute for the YAML-based deep work in score.py — it's
the *triage* layer that picks which names deserve full YAML build-outs
from the 600+ candidate universe.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_MD = REPO / "universe.md"
OUT = REPO / "output" / "universe_screened.md"

# Archetype keyword classification (applied to the notes column).
# Order matters: first hit wins so put more specific patterns first.
ARCHETYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("A2", [
        r"\bdod\b", r"\bdoe\b", r"\bchips? act\b", r"\beib\b",
        r"\bsovereign\b.*\b(anchor|stake|equity)\b",
        r"\bgovernment\b.*\b(stake|equity|loan)\b",
        r"\bpentagon\b", r"\bcritical[ -]?mineral", r"\bsaf\b",
        r"\bdepartment of (defen[cs]e|energy|commerce)\b",
        r"\batvm\b", r"\bceefc\b",
    ]),
    ("A1", [
        r"\brights (issue|offering)\b.*\b(underwrit|backstop|anchor)",
        r"\bfully[ -]underwritten\b", r"\bbackstop(p?ed)?\b",
        r"\bsovereign[ -]strategic\b",
        r"\breserved (capital )?increase\b",
        r"\bwallenberg\b", r"\binvestor ab\b",
        r"\bbpifrance\b", r"\bcrédit agricole\b", r"\bbnp paribas\b",
        r"\bdanish state\b", r"\bfrench state\b",
    ]),
    ("F", [
        r"\bmcb\b", r"\bmandatory convert", r"\bdebt[ -]for[ -]equity\b",
        r"\bdebt[ -]to[ -]equity\b", r"\bfounder\b.*\b(stake|equity|lock)\b",
        r"\bemerged (from )?ch\.?\s?11", r"\bpost[ -]reorg\b",
        r"\bplan of reorgani[sz]ation\b", r"\bpre[ -]?pack\b",
    ]),
    ("B", [
        r"\bconvertible\b", r"\bcapped call\b", r"\bsenior notes?\b.*\bexchange\b",
        r"\bwarrant\b.*\b(strike|exercise)\b",
        r"\bstrategic (anchor|investor|partner)\b",
        r"\bpremium to (vwap|market)\b",
    ]),
    ("C", [
        r"\bexchange offer\b", r"\bliability management\b", r"\bconsent solicitation\b",
        r"\btender offer\b", r"\boout-of[ -]court\b", r"\bcovenant relief\b",
        r"\bextend(ed|s)? maturit", r"\ba&e\b", r"\bamend(ed)? and extend",
    ]),
    ("D", [
        r"\bcustomer\b.*\b(jv|partnership|anchor)\b",
        r"\bsupplier\b.*\b(jv|partnership|anchor)\b",
        r"\bmidea\b", r"\bbright dairy\b", r"\ba2 milk\b",
    ]),
    ("E", [
        r"\bsauvegarde\b", r"\bstarug\b", r"\bwhoa\b", r"\bpn17\b",
        r"\bccaa\b", r"\brecovery judicial\b", r"\bjudicial recovery\b",
        r"\brehabilitation\b", r"\bre-?ipo\b", r"\bscheme of arrangement\b",
        r"\bpart 26a?\b", r"\baccelerated safeguard\b",
    ]),
    ("G", [
        r"\bregulator(y)? (forced|mandate)\b", r"\bmrel\b",
        r"\bcentral bank\b.*\b(recap|capital|stress)\b",
        r"\bcbn\b.*\b(floor|capital|recap)\b",
        r"\bsector[ -]wide\b.*\brecap\b",
    ]),
    ("H", [
        r"\bnlfi\b", r"\bukgi\b", r"\bhfsf\b", r"\bstate[ -]exit\b",
        r"\bsell[ -]down\b", r"\bvalue[ -]up\b", r"\bparent[ -]child\b",
        r"\bmandatory tob\b", r"\bgovernance reset\b",
    ]),
]

# Status flags
STATUS_PATTERNS: list[tuple[str, list[str]]] = [
    ("ARC_DONE",  [r"\bdone\b", r"\bcompleted arc\b", r"\bre[ -]?rated\b"]),
    ("PASS",      [r"\bpass\b", r"\bequity (wiped|gone|cancelled)\b", r"\bnegative control\b",
                   r"\bch\.?\s?11(?: 20\d\d)?\b.*\bgone\b", r"\bgone\b"]),
    ("ACQUIRED",  [r"\bacquired\b"]),
    ("PRE_RECAP", [r"\bwatch\b.*\b(for|closely)\b", r"\bpre[ -]recap\b"]),
    ("REPEAT_RX", [r"\bch\.?\s?22\b", r"\bre[ -]ch\.?\s?11\b", r"\bre[ -]?file"]),
    ("YELLOW",    [r"\byellow flag\b", r"\bconditional\b.*\b(state|backstop)\b"]),
]

# Confidence tier mapping (from the universe.md ★/○/▲ tags)
CONF_SCORE = {"★": 3, "○": 2, "▲": 1}

# Bucket weights for triage scoring
BUCKET_WEIGHT = {"A": 1.0, "A (low)": 0.4, "A→B": 0.7, "C → B": 0.8, "B": 0.9,
                 "C": 0.2, "C → C": 0.0, "C → acquired": 0.0, "C → done": 0.5, "n/a": 0.5}

# Archetype scoring weights for triage
ARCH_WEIGHT = {"A1": 1.0, "A2": 1.0, "B": 0.8, "C": 0.7, "D": 0.85, "E": 0.7,
               "F": 0.65, "G": 0.85, "H": 0.7, "Unknown": 0.4}

STATUS_PENALTY = {
    "ARC_DONE": 0.3, "PASS": 0.0, "ACQUIRED": 0.0,
    "PRE_RECAP": 0.7, "REPEAT_RX": 0.0, "YELLOW": 0.5,
    "OK": 1.0,
}


@dataclass
class Candidate:
    name: str
    ticker: str
    conf: str
    bucket: str
    notes: str
    section: str
    region: str
    archetype: str = "Unknown"
    status: str = "OK"
    triage_score: float = 0.0


# Region inference from section headers
REGION_KEYWORDS = {
    "United States/Canada": ["energy", "renewables", "ev / battery", "healthcare", "retail", "real estate",
                             "banks", "telecom", "crypto", "auto parts", "shipping"],
    "United Kingdom": ["uk rights"],
    "France": ["french"],
    "Continental Europe": ["european recaps", "nordic", "baltic", "iberia", "greece", "central / eastern europe"],
    "China / Hong Kong": ["china property", "china non-property"],
    "Japan": ["japan"],
    "Korea": ["korea"],
    "SE Asia / Pacific": ["indonesia", "malaysia", "singapore", "thailand", "philippines", "vietnam",
                         "australia", "nz", "sri lanka", "pakistan", "bangladesh"],
    "Latin America": ["brazil", "mexico", "latam"],
    "MEA / Frontier": ["mea", "israel", "turkey", "egypt", "argentina", "türkiye", "gulf", "africa"],
}


def infer_region(section: str) -> str:
    s = section.lower()
    for region, keys in REGION_KEYWORDS.items():
        if any(k in s for k in keys):
            return region
    return "Unspecified"


def classify_archetype(notes: str, section: str = "") -> str:
    text = (notes + " " + section).lower()
    for code, patterns in ARCHETYPE_PATTERNS:
        for p in patterns:
            if re.search(p, text):
                return code
    # Section-based fallback inference
    s = section.lower()
    if "post-ch.11" in s or "post-bankruptcy" in s or "emerged" in s:
        return "F"
    if "convertible" in s or "convert" in s:
        return "B"
    if "exchange" in s or "liability" in s:
        return "C"
    if "rights" in s and ("issue" in s or "offering" in s):
        return "A1"
    if "ch.11" in s or "ch.22" in s:
        return "F"
    if "default" in s or "post-default" in s or "sovereign" in s:
        return "G"
    if "value-up" in s or "parent-child" in s or "state-exit" in s:
        return "H"
    # Sector-based weak inference
    if "cyclical" in s:
        return "B"
    return "Unknown"


def classify_status(notes: str, bucket: str) -> str:
    text = notes.lower()
    for code, patterns in STATUS_PATTERNS:
        for p in patterns:
            if re.search(p, text):
                return code
    # Bucket-implied status
    if bucket in ("C", "C → C", "C → acquired"):
        return "PASS"
    return "OK"


def triage_score(c: Candidate) -> float:
    bucket_clean = c.bucket.strip()
    bw = BUCKET_WEIGHT.get(bucket_clean, 0.5)
    aw = ARCH_WEIGHT.get(c.archetype, 0.4)
    sp = STATUS_PENALTY.get(c.status, 1.0)
    conf_w = CONF_SCORE.get(c.conf.strip(), 1) / 3.0
    # Notes length is a *weak* proxy for documented thesis depth
    note_w = min(1.2, 0.6 + len(c.notes) / 200.0)
    return bw * aw * sp * conf_w * note_w


def parse() -> list[Candidate]:
    text = UNIVERSE_MD.read_text()
    section = ""
    region = "Unspecified"
    candidates: list[Candidate] = []

    in_table = False
    header_count = 0
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            section = line[4:].strip()
            region = infer_region(section)
            in_table = False
            header_count = 0
            continue
        if line.startswith("## "):
            # Top-level section banner — note in region inference too
            top = line[3:].strip().lower()
            for r, keys in REGION_KEYWORDS.items():
                if any(k in top for k in keys):
                    region = r
                    break
            continue
        if not line.startswith("|"):
            in_table = False
            header_count = 0
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        # Skip table header / separator lines
        if all(re.match(r"^[-:\s]+$", c) for c in cells):
            in_table = True
            continue
        if not in_table:
            # Could be the header row
            if "Name" in cells and "Ticker" in cells:
                # Find column indices for the schema
                header_count = len(cells)
                in_table = False  # wait for separator
            continue

        # Data row inside a table. Expect ~5 columns: Name, Ticker, Conf, Bucket, Notes
        if len(cells) < 4:
            continue
        # The schema varies slightly — pull canonical fields
        name = cells[0]
        ticker = cells[1] if len(cells) > 1 else ""
        # Some tables have only 4 columns (no Notes); accept that.
        if len(cells) >= 5:
            conf, bucket, notes = cells[2], cells[3], cells[4]
        elif len(cells) == 4:
            conf, bucket, notes = "", cells[2], cells[3]
        else:
            continue

        # Skip table header rows that slipped through (cells contain literal "Name", "Ticker", ...)
        if name.lower() == "name" or ticker.lower() == "ticker":
            continue
        # Skip empty / placeholder rows
        if not name or name.startswith("---"):
            continue

        c = Candidate(name=name, ticker=ticker, conf=conf, bucket=bucket,
                      notes=notes, section=section, region=region)
        c.archetype = classify_archetype(notes, section)
        c.status = classify_status(notes, bucket)
        c.triage_score = triage_score(c)
        candidates.append(c)

    return candidates


def render(candidates: list[Candidate]) -> str:
    from datetime import date

    by_region: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_region[c.region].append(c)

    lines = [
        f"# Universe-wide screen ({date.today().isoformat()})",
        "",
        "Auto-generated by `src/universe_screen.py` from `universe.md`.",
        "Do NOT hand-edit.",
        "",
        f"**Universe size: {len(candidates)} named candidates across "
        f"{len(by_region)} regions and {len(set(c.section for c in candidates))} sectors.**",
        "",
        "Classification done by keyword heuristics over the Notes column. The",
        "score is a triage-level estimate — final tier assignment requires",
        "primary-document verification per the standard YAML build-out.",
        "",
        "## Score distribution",
        "",
    ]

    # Triage tiers recalibrated to the observed score distribution
    counts = Counter()
    for c in candidates:
        s = c.triage_score
        if s >= 0.60: counts["T1"] += 1
        elif s >= 0.40: counts["T2"] += 1
        elif s >= 0.20: counts["T3"] += 1
        else: counts["pass"] += 1
    lines.append("| Triage tier | Threshold | Count | Action |")
    lines.append("|---|---|---|---|")
    lines.append(f"| **T1** | ≥ 0.60 | {counts['T1']} | priority YAML build-out |")
    lines.append(f"| **T2** | 0.40–0.60 | {counts['T2']} | watch + light YAML |")
    lines.append(f"| **T3** | 0.20–0.40 | {counts['T3']} | sector-context only |")
    lines.append(f"| **pass** | < 0.20 | {counts['pass']} | universe ballast |")
    lines.append("")

    # Archetype mix
    arch_counts = Counter(c.archetype for c in candidates)
    lines.append("## Archetype classification (by keyword heuristic)")
    lines.append("")
    lines.append("| Archetype | Count |")
    lines.append("|---|---|")
    for a, n in arch_counts.most_common():
        lines.append(f"| {a} | {n} |")
    lines.append("")

    # Region summary
    lines.append("## Region summary")
    lines.append("")
    lines.append("| Region | Names | Mean score | Top score | Top name |")
    lines.append("|---|---|---|---|---|")
    for region in sorted(by_region):
        cs = sorted(by_region[region], key=lambda x: -x.triage_score)
        if not cs:
            continue
        mean = sum(c.triage_score for c in cs) / len(cs)
        top = cs[0]
        lines.append(f"| **{region}** | {len(cs)} | {mean:.2f} | {top.triage_score:.2f} | {top.name} ({top.ticker}) |")
    lines.append("")

    # Top 20 per region
    for region in sorted(by_region):
        cs = sorted(by_region[region], key=lambda x: -x.triage_score)[:20]
        if not cs:
            continue
        lines.append(f"## {region} — top {len(cs)} by triage score")
        lines.append("")
        lines.append("| Score | Name | Ticker | Conf | Bucket | Archetype | Status | Section |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in cs:
            lines.append(
                f"| {c.triage_score:.2f} | {c.name} | {c.ticker} | {c.conf} | "
                f"{c.bucket} | {c.archetype} | {c.status} | {c.section[:50]} |"
            )
        lines.append("")

    # Global top 50
    lines.append("## Global top 50 (triage-score ranked)")
    lines.append("")
    lines.append("| # | Score | Name | Ticker | Conf | Bucket | Archetype | Region | Status |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(sorted(candidates, key=lambda x: -x.triage_score)[:50], 1):
        lines.append(
            f"| {i} | {c.triage_score:.2f} | **{c.name}** | {c.ticker} | "
            f"{c.conf} | {c.bucket} | {c.archetype} | {c.region} | {c.status} |"
        )
    lines.append("")

    # Priority YAML build-out queue — anything T1 or T2 that doesn't already have a YAML
    have_yamls = set()
    yaml_dir = REPO / "data" / "candidates"
    if yaml_dir.exists():
        for y in yaml_dir.glob("*.yaml"):
            have_yamls.add(y.stem.upper())
    lines.append("## Priority YAML build-out queue")
    lines.append("")
    lines.append("Names scored T1 or T2 that DO NOT yet have a YAML in `data/candidates/`.")
    lines.append("These are the candidates the next research pass should verify against")
    lines.append("primary filings and promote.")
    lines.append("")
    needs_yaml = [
        c for c in candidates
        if c.triage_score >= 0.40 and c.status == "OK"
    ]
    needs_yaml.sort(key=lambda x: -x.triage_score)
    # De-dup by name and filter out names whose ticker overlaps an existing YAML
    seen_names = set()
    queue = []
    for c in needs_yaml:
        ticker_key = c.ticker.split(":")[-1].strip("() ").upper() if c.ticker else ""
        if ticker_key and ticker_key in have_yamls:
            continue
        if c.name in seen_names:
            continue
        seen_names.add(c.name)
        queue.append(c)
    lines.append("| Score | Name | Ticker | Region | Bucket | Archetype | Section |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in queue[:40]:
        lines.append(
            f"| {c.triage_score:.2f} | **{c.name}** | {c.ticker} | "
            f"{c.region} | {c.bucket} | {c.archetype} | {c.section[:50]} |"
        )
    lines.append("")
    lines.append(f"**{len(queue)} names need YAML build-out.** Top 40 shown.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main():
    candidates = parse()
    OUT.write_text(render(candidates))
    print(f"Wrote {OUT}")
    print(f"  {len(candidates)} candidates parsed")
    print(f"  {sum(1 for c in candidates if c.triage_score >= 1.5)} priority (score ≥ 1.5)")
    print(f"  {sum(1 for c in candidates if c.triage_score >= 1.0)} actionable (score ≥ 1.0)")


if __name__ == "__main__":
    main()
