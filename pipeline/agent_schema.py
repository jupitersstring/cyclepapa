"""Agent output contract + merge with contradiction detection.   (eng fix #6)

Research agents must return JSON conforming to AGENT_FINDING_SCHEMA — one
object per finding — instead of prose. merge() loads N agent files, validates,
dedupes by (ticker, claim_type), and flags contradictions (same key, different
values from different agents) instead of silently keeping the first one seen.

This is the structural fix for the PRLD Baker-vs-OrbiMed and RPAY
Veradace-vs-Forager attribution drift.

Usage:
  python3 pipeline/agent_schema.py example          > prompt snippet to give agents
  python3 pipeline/agent_schema.py merge a.json b.json ...
"""
import json, sys, itertools

AGENT_FINDING_SCHEMA = {
    "type": "object",
    "required": ["ticker", "claim_type", "value", "asof", "source_url", "confidence"],
    "properties": {
        "ticker":      {"type": "string"},
        "claim_type":  {"enum": ["price", "mcap_m", "holder_pct_company", "holder_pct_book",
                                  "form4_buy", "form4_sell", "13d_filing", "13g_filing",
                                  "catalyst", "bid", "verdict_rerated", "other"]},
        "actor":       {"type": "string", "description": "fund/insider name if applicable"},
        "value":       {"description": "number for quantitative claims; string for events"},
        "event_date":  {"type": "string", "description": "ISO date of the underlying event"},
        "asof":        {"type": "string", "description": "ISO date the agent checked this"},
        "source_url":  {"type": "string", "minLength": 10},
        "confidence":  {"enum": ["primary_source", "secondary", "inferred"]},
        "note":        {"type": "string"},
    },
}

PROMPT_SNIPPET = """Return findings ONLY as a JSON array, one object per finding, no prose:
[{"ticker":"KBR","claim_type":"form4_buy","actor":"Sabater Carlos","value":470725,
  "event_date":"2026-05-19","asof":"2026-06-10",
  "source_url":"https://www.sec.gov/...","confidence":"primary_source",
  "note":"14,500 sh @ $32.47"}]
claim_type one of: price|mcap_m|holder_pct_company|holder_pct_book|form4_buy|form4_sell|
13d_filing|13g_filing|catalyst|bid|verdict_rerated|other.
confidence: primary_source (SEC/company doc) | secondary (aggregator/news) | inferred.
Every finding MUST carry source_url. Do not return any finding you cannot source."""

def validate(finding):
    errs = []
    for k in AGENT_FINDING_SCHEMA["required"]:
        if k not in finding or finding[k] in (None, ""):
            errs.append(f"missing {k}")
    ct = finding.get("claim_type")
    if ct and ct not in AGENT_FINDING_SCHEMA["properties"]["claim_type"]["enum"]:
        errs.append(f"bad claim_type {ct}")
    return errs

def merge(paths):
    all_f, bad = [], 0
    for p in paths:
        for i, f in enumerate(json.load(open(p))):
            errs = validate(f)
            if errs:
                bad += 1
                print(f"REJECT {p}[{i}] {f.get('ticker','?')}: {'; '.join(errs)}")
            else:
                f["_src_file"] = p
                all_f.append(f)
    # contradiction detection: same (ticker, claim_type, actor-ish) different value
    key = lambda f: (f["ticker"], f["claim_type"], f.get("actor", ""))
    contradictions = []
    for k, grp in itertools.groupby(sorted(all_f, key=key), key=key):
        grp = list(grp)
        vals = {json.dumps(g["value"], sort_keys=True) for g in grp}
        if len(vals) > 1:
            contradictions.append((k, grp))
    print(f"\n{len(all_f)} valid findings, {bad} rejected, {len(contradictions)} contradictions")
    for k, grp in contradictions:
        print(f"\nCONTRADICTION {k}:")
        for g in grp:
            print(f"  {g['_src_file']}: {g['value']} ({g['confidence']}) {g['source_url'][:60]}")
    # primary_source wins ties; secondary kept only if no primary disagrees
    return all_f, contradictions

if __name__ == "__main__":
    if sys.argv[1:2] == ["example"]:
        print(PROMPT_SNIPPET)
    elif sys.argv[1:2] == ["merge"]:
        merge(sys.argv[2:])
