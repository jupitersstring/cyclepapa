#!/usr/bin/env python3
"""
events.py — event-type and practitioner-pattern extractor.

Implements the playbook §appendix regex set against universe.md row
notes. Tags each candidate with one or more of the 23 canonical event
types from the special-situations playbook + the practitioner pattern
the deal most resembles.

Output: output/event_taxonomy_screen.md — event-tagged ranking that
complements the existing archetype-based ranking.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_MD = REPO / "universe.md"
OUT = REPO / "output" / "event_taxonomy_screen.md"

# Direct from playbook §appendix — regex starters keyed by event code
EVENT_PATTERNS: dict[str, list[str]] = {
    "activist_stake": [
        r"\b(schedule\s+13[dg](/a)?|sc\s*13[dg](/a)?)\b",
        r"\b(13d filing|substantial shareholder notif)",
        r"\b(early[ -]?warning report)\b",
        r"\bactivist\b.*\b(stake|disclosure|filing)\b",
    ],
    "activist_escalation": [
        r"\b13d/a\b", r"\bescalation\b.*\bletter\b",
        r"\bcaltagirone\b", r"\bcevian\b.*\bcampaign\b",
    ],
    "proxy_fight": [
        r"\b(proxy fight|proxy contest|nominate(d|s)?|consent solicitation)\b",
        r"\bnominee slate\b",
    ],
    "cooperation_settlement": [
        r"\bcooperation agreement\b", r"\bboard[ -]?seat settlement\b",
        r"\bstandstill\b",
    ],
    "strategic_review": [
        r"\b(strategic review|exploring strategic alternatives|review of alternatives)\b",
        r"\b(banker hired|advisor (hired|appointed))\b",
        r"\bsale process\b",
    ],
    "definitive_ma": [
        r"\b(entered into|signed|executed)\b.{0,80}\b(merger agreement|definitive agreement)\b",
        r"\b(agreement and plan of merger)\b",
        r"\b(definitive (cash )?(merger )?agreement)\b",
        r"\b(tender|takeover bid|hostile bid)\b.*\bagreement\b",
        r"\b(dod partnership|doc.*finalisation)\b",
    ],
    "tender_offer": [
        r"\b(tender offer|offer to purchase|dutch auction)\b",
        r"\b(sc to-?[tic])\b",
    ],
    "issuer_tender": [
        r"\b(issuer tender|share buy[- ]?back tender)\b",
        r"\b(dutch auction.*own)\b",
    ],
    "spin_off": [
        r"\b(spin[- ]?off|separation|carve[- ]?out|split[- ]?off|demerger)\b",
        r"\b(form 10|information statement)\b",
    ],
    "asset_sale": [
        r"\b(asset sale|divestiture|sale[- ]leaseback|non-core asset|monetisation)\b",
        r"\b(disposal|disposition)\b",
        r"\b(carve.?out)\b",
    ],
    "special_dividend": [
        r"\b(special dividend)\b",
        r"\b(capital return)\b",
    ],
    "buyback": [
        r"\b(share repurchase|buyback|share buyback)\b",
        r"\b(repurchase authorisation|repurchase program)\b",
    ],
    "board_change": [
        r"\b(board refresh|director (resig|appoint))\b",
        r"\b(new (independent )?director)\b",
        r"\b(board reset|board overhaul)\b",
    ],
    "ceo_change": [
        r"\b(ceo|cfo)\b.{0,20}\b(change|resign|appoint|depart|step down)\b",
        r"\bnew (chief executive|cfo)\b",
        r"\bmanagement reset\b",
    ],
    "bankruptcy": [
        r"\b(chapter 11|ch\.?\s?11|receivership|administration)\b",
        r"\b(insolven(t|cy)|liquidat(ed|ion))\b",
        r"\b(judicial recovery)\b",
    ],
    "restructuring": [
        r"\b(restructuring|liability management|amend(ed)? and extend|a\&e)\b",
        r"\b(rsa|restructuring support agreement|dip financing)\b",
        r"\b(scheme of arrangement|part 26a?)\b",
        r"\b(accelerated safeguard|sauvegarde|whoa|starug|pn17|ccaa)\b",
        r"\b(rj plan|recovery plan)\b",
    ],
    "litigation": [
        r"\b(class action|settlement|court (sanction|approval|ruling))\b",
        r"\b(tort|wildfire liab)\b",
    ],
    "regulatory_approval": [
        r"\b(state aid (approv|grant)|eu commission approv)\b",
        r"\b(chips act|atvm|doe.*loan)\b",
        r"\b(framework approved|cluster designation)\b",
        r"\b(approved by (eu|state|government))\b",
    ],
    "regulatory_block": [
        r"\b(blocked|prohibition|denied) by (eu|cma|ftc|antitrust)\b",
        r"\b(court of appeal.*set aside)\b",
    ],
    "cross_holding_reduction": [
        r"\b(cross[- ]?shareholding (disposal|reduction|unwind))\b",
        r"\b(mcb conversion|mandatory convertible bond)\b",
        r"\b(equitised|debt[ -]?for[ -]?equity|debt[ -]?to[ -]?equity)\b",
        r"\b(holding company discount|hidden asset)\b",
    ],
    "delisting": [
        r"\b(delisting|going private|take[- ]?private)\b",
        r"\b(15-12b|form 15)\b",
        r"\b(cash takeover at.*p)\b",
    ],
    "rights_issue": [
        r"\b(rights (issue|offering))\b",
        r"\b(fully underwritten|underwritten rights)\b",
        r"\b(qip|fpo|preferential allotment)\b",
    ],
    "pre_recap_watch": [
        r"\bpre[ -]?recap\b", r"\bwatch\b.*\b(refi|round|recap|deal)\b",
        r"\bstrategic alternatives\b",
        r"\bcontemplated\b",
        r"\bbridging mechanism\b",
        r"\bpipeline\b.*\b(state aid|kfw|sovereign)\b",
    ],
}

# Practitioner-pattern detection — pattern → keywords/heuristics
PATTERN_RULES = [
    # (pattern_code, required_event_types, optional_keywords)
    ("Sovereign-anchor", {"regulatory_approval", "definitive_ma"},
     [r"\b(dod|doe|kfw|eib|sovereign|state aid|atvm)\b"]),
    ("MCB-cascade", {"cross_holding_reduction", "restructuring"},
     [r"\b(mcb|founder.*(lock|restriction|partic))\b"]),
    ("TCI", {"rights_issue"},
     [r"\b(wallenberg|investor ab|niel|lévy|patient)\b"]),
    ("Pershing", {"restructuring", "litigation"},
     [r"\b(act 258|statutory|regulated utility)\b"]),
    ("Bastian", set(),  # micro-cap proxy
     [r"\b(microcap|micro[ -]?cap|net cash floor)\b"]),
    ("Elliott", {"strategic_review", "definitive_ma"},
     [r"\b(strategic review|review of alternatives|sale process)\b"]),
    ("Icahn", {"asset_sale", "spin_off"},
     [r"\b(break[ -]?up|sotp|hidden asset)\b"]),
    ("Third-Point", {"definitive_ma", "asset_sale"},
     [r"\b(entertainment carve|partial ipo|sub.{0,3}ipo)\b"]),
]


@dataclass
class Candidate:
    name: str
    ticker: str
    notes: str
    section: str
    events: list[str] = field(default_factory=list)
    practitioner: str = "Unknown"


def parse_universe() -> list[Candidate]:
    text = UNIVERSE_MD.read_text()
    section = ""
    cands: list[Candidate] = []
    in_table = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            section = line[4:].strip()
            in_table = False
            continue
        if line.startswith("## "):
            in_table = False
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.match(r"^[-:\s]+$", c) for c in cells):
            in_table = True
            continue
        if not in_table:
            continue
        if len(cells) < 4:
            continue
        name = cells[0]
        ticker = cells[1] if len(cells) > 1 else ""
        notes = cells[-1] if cells else ""
        if name.lower() == "name" or ticker.lower() == "ticker":
            continue
        if not name or name.startswith("---"):
            continue
        cands.append(Candidate(name=name, ticker=ticker,
                               notes=notes, section=section))
    return cands


def extract_events(notes: str, section: str) -> list[str]:
    text = (notes + " " + section).lower()
    events = []
    for code, patterns in EVENT_PATTERNS.items():
        for p in patterns:
            if re.search(p, text):
                events.append(code)
                break
    return events


def classify_practitioner(events: set[str], notes: str) -> str:
    text = notes.lower()
    for pattern_code, required, keywords in PATTERN_RULES:
        # Either required events overlap, OR keyword fires
        events_hit = bool(required & events) if required else False
        keyword_hit = any(re.search(p, text) for p in keywords)
        if (events_hit and keyword_hit) or (not required and keyword_hit):
            return pattern_code
    if events:
        return "Unclassified-with-event"
    return "Unknown"


def render(cands: list[Candidate]) -> str:
    by_event: dict[str, list[Candidate]] = defaultdict(list)
    by_pattern: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        for e in c.events:
            by_event[e].append(c)
        by_pattern[c.practitioner].append(c)

    lines = [
        f"# Event taxonomy screen ({date.today().isoformat()})",
        "",
        "Auto-generated by `src/events.py`. Tags each universe row with",
        "event types (playbook §appendix) and practitioner patterns",
        "(playbook §2). Complements the archetype-based screen.",
        "",
        f"**{len(cands)} candidates parsed; "
        f"{sum(1 for c in cands if c.events)} have at least one event tag "
        f"({100*sum(1 for c in cands if c.events)/len(cands):.0f}%).**",
        "",
        "## Event-type distribution",
        "",
        "| Event type | Count | Top candidate |",
        "|---|---|---|",
    ]
    for code in sorted(EVENT_PATTERNS.keys()):
        cs = by_event.get(code, [])
        top = cs[0].name if cs else "—"
        lines.append(f"| `{code}` | {len(cs)} | {top} |")
    lines.append("")

    lines.append("## Practitioner-pattern distribution")
    lines.append("")
    lines.append("| Pattern | Count | Example |")
    lines.append("|---|---|---|")
    for pattern in sorted(by_pattern.keys(),
                         key=lambda p: -len(by_pattern[p])):
        cs = by_pattern[pattern]
        ex = cs[0].name if cs else "—"
        lines.append(f"| **{pattern}** | {len(cs)} | {ex} |")
    lines.append("")

    # Per-pattern listing (top 15 each), excluding Unknown
    for pattern in ["Sovereign-anchor", "MCB-cascade", "TCI",
                   "Pershing", "Bastian", "Elliott", "Icahn",
                   "Third-Point"]:
        cs = by_pattern.get(pattern, [])
        if not cs:
            continue
        lines.append(f"## Pattern: {pattern} — top 15")
        lines.append("")
        lines.append("| Name | Ticker | Events | Section |")
        lines.append("|---|---|---|---|")
        for c in cs[:15]:
            events_str = ", ".join(sorted(c.events))[:60]
            lines.append(f"| {c.name} | {c.ticker} | "
                       f"{events_str} | {c.section[:40]} |")
        lines.append("")

    # Multi-event candidates (signal-richest names)
    multi_event = [c for c in cands if len(c.events) >= 3]
    multi_event.sort(key=lambda c: -len(c.events))
    lines.append("## Multi-event candidates (3+ event tags)")
    lines.append("")
    lines.append("Multi-event names are signal-richest in the universe —")
    lines.append("their notes contain multiple catalyst dimensions.")
    lines.append("")
    lines.append("| Name | Ticker | # Events | Events | Pattern |")
    lines.append("|---|---|---|---|---|")
    for c in multi_event[:30]:
        events_str = ", ".join(sorted(c.events))[:80]
        lines.append(f"| {c.name} | {c.ticker} | {len(c.events)} | "
                   f"{events_str} | {c.practitioner} |")
    lines.append("")

    return "\n".join(lines) + "\n"


def main():
    cands = parse_universe()
    for c in cands:
        c.events = extract_events(c.notes, c.section)
        c.practitioner = classify_practitioner(set(c.events), c.notes)
    OUT.write_text(render(cands))
    print(f"Wrote {OUT}")
    print(f"  {len(cands)} parsed")
    print(f"  {sum(1 for c in cands if c.events)} with event tags "
          f"({100*sum(1 for c in cands if c.events)/len(cands):.0f}%)")
    print(f"  Pattern distribution:")
    by_pattern = Counter(c.practitioner for c in cands)
    for p, n in by_pattern.most_common():
        print(f"    {p}: {n}")


if __name__ == "__main__":
    main()
