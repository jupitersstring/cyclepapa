#!/usr/bin/env python3
"""
emergence_master.py — multi-source Chapter 11 EMERGENCE triangulation.

The old methodology was single-source: only postreorg_poll's three
full-text phrases fed the emergence funnel, so coverage was whatever those
phrases happened to match. But a real emergence throws off FIVE independent
SEC signals, and catching ANY of them catches the event; how MANY corroborate
sets the confidence:

  1. 8-K describing the emergence        (postreorg prose / 8-K Item 1.03)
  2. Fresh-start accounting in next 10-K  (postreorg freshstart)
  3. OLD shares delisted: Form 25-NSE / 15 (edgar_forms / form15)
  4. NEW shares registered: Form 8-A12B/G  (relisting the reorganized common)
  5. Court plan-confirmation docket        (PACER)

This module fuses those inbox signals into one de-duplicated master list of
emergence events, keyed by CIK (falling back to a normalized name), each
scored by how many INDEPENDENT sources flagged it. It also runs a
COMPLETENESS tripwire: given a ground-truth list of known emergences (from
research / the emergence-catch audit), it flags any listed-common emergence
we FAILED to catch — turning "we're missing so much" into a measured,
auditable gap instead of an unknown.

Outputs:
  data/emergence_master.json   — the fused, confidence-scored event list
  output/emergence_master.md   — human-readable, plus the coverage-gap report

Usage:
    python -m src.emergence_master
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
GROUND_TRUTH = REPO / "data" / "emergence_ground_truth.json"
OUT_JSON = REPO / "data" / "emergence_master.json"
OUT_MD = REPO / "output" / "emergence_master.md"

try:
    from src.edgar_util import resolve_cik_to_ticker
except Exception:            # pragma: no cover
    def resolve_cik_to_ticker(_):
        return None


# --- signal taxonomy ------------------------------------------------------
# Each inbox signal maps to (source_channel, is_primary_emergence). Primary
# signals ARE an emergence on their own; corroborating signals only raise
# confidence when they coincide with a primary (or with each other).

def _norm(n) -> str:
    if isinstance(n, (list, tuple)):
        n = " ".join(map(str, n))
    return re.sub(r"[^a-z0-9]", "",
                  re.sub(r"\b(inc|corp|corporation|ltd|limited|plc|llc|lp|"
                         r"holdings?|group|co|company|the|sa|nv|ag|se)\b",
                         "", str(n or ""), flags=re.I)).lower()


def _key(rec) -> str:
    cik = rec.get("cik")
    if cik:
        try:
            return f"CIK:{int(cik)}"
        except (ValueError, TypeError):
            pass
    nm = _norm(rec.get("name", ""))
    return f"NAME:{nm}" if nm else ""


def _classify(rec) -> tuple[str, bool] | None:
    """Return (channel, is_primary) for an inbox record, or None if the
    record is not emergence-relevant."""
    lbl = (rec.get("query_label") or "").lower()
    form = (rec.get("form") or rec.get("form_code") or "").upper()
    src = (rec.get("source") or "")
    # --- primary emergence signals ---
    if "freshstart" in lbl:
        return ("fresh-start accounting (10-K/Q)", True)
    if "emerged" in lbl or "post_reorg_emerged" in lbl:
        return ("emergence 8-K prose", True)
    if "plan_effective" in lbl:
        return ("plan-effective 8-K", True)
    if "emergence" in lbl:
        return ("emergence signal", True)
    # 8-K Item 1.03 covers BOTH entry and emergence; treat as corroborating
    # (the emergence_master can't split them without the body, so it counts
    # only as a supporting court/structural signal).
    if "item_bankruptcy" in lbl or "1.03" in lbl or "bankruptcy_11" in lbl:
        return ("8-K Item 1.03 / bankruptcy docket", False)
    # --- corroborating structural signals ---
    if "form25" in lbl or form.startswith("25"):
        return ("Form 25 old-share delisting", False)
    if "form15" in lbl or form.startswith("15-") or form == "15":
        return ("Form 15 deregistration", False)
    if form.startswith("8-A"):
        return ("Form 8-A new-common registration", False)
    if "delisting" in lbl and "deficiency" not in lbl:
        return ("delisting notice", False)
    if src.startswith("CourtListener") or "pacer" in src.lower():
        return ("PACER bankruptcy docket", False)
    return None


def collect_signals() -> dict[str, dict]:
    """Fuse every emergence-relevant inbox record into per-entity events."""
    events: dict[str, dict] = {}
    for jf in INBOX.rglob("*.json"):
        try:
            rec = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(rec, dict):
            continue
        cls = _classify(rec)
        if not cls:
            continue
        channel, is_primary = cls
        k = _key(rec)
        if not k:
            continue
        ev = events.get(k)
        if ev is None:
            ev = {"key": k, "name": rec.get("name", ""),
                  "cik": rec.get("cik") or "",
                  "ticker": rec.get("ticker") or "",
                  "channels": {}, "primary": False,
                  "item_1_03": False, "pending": None,
                  "first_filed": rec.get("filed") or "",
                  "last_filed": rec.get("filed") or ""}
            events[k] = ev
        ev["channels"].setdefault(channel, 0)
        ev["channels"][channel] += 1
        ev["primary"] = ev["primary"] or is_primary
        # structured 8-K Item 1.03 = strong confirmation this is a genuine
        # bankruptcy/emergence filing (the audit's key precision filter).
        ev["item_1_03"] = ev["item_1_03"] or bool(rec.get("item_1_03"))
        # a Q-suffix ticker means STILL IN bankruptcy (pending emergence);
        # any non-Q primary signal flips it to actually-emerged.
        if rec.get("pre_emergence") and ev["pending"] is None:
            ev["pending"] = True
        if is_primary and not rec.get("pre_emergence"):
            ev["pending"] = False
        if not ev.get("ticker") and rec.get("ticker"):
            ev["ticker"] = rec["ticker"]
        # prefer the longest, most descriptive name
        if len(str(rec.get("name", ""))) > len(str(ev["name"])):
            ev["name"] = rec.get("name", "")
        f = rec.get("filed") or ""
        if f and (not ev["first_filed"] or f < ev["first_filed"]):
            ev["first_filed"] = f
        if f and f > ev["last_filed"]:
            ev["last_filed"] = f
    # resolve tickers from CIK where missing
    for ev in events.values():
        if not ev["ticker"] and ev["cik"]:
            t = resolve_cik_to_ticker(ev["cik"])
            if t:
                ev["ticker"] = t
    return events


def confidence(ev: dict) -> str:
    if ev.get("pending"):
        return "pending (Q-suffix — still in Chapter 11, not yet emerged)"
    n = len(ev["channels"])
    # a structured 8-K Item 1.03 counts as an independent corroboration
    corrob = n + (1 if ev.get("item_1_03") else 0)
    if ev["primary"] and corrob >= 2:
        return "high (primary + corroboration)"
    if ev["primary"]:
        return "medium (single primary source)"
    if corrob >= 2:
        return "medium (corroborating signals only)"
    return "low (single corroborating signal)"


# --- completeness tripwire ------------------------------------------------

def load_ground_truth() -> list[dict]:
    if GROUND_TRUTH.exists():
        try:
            data = json.loads(GROUND_TRUTH.read_text())
            return data if isinstance(data, list) else data.get("emergences", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def coverage_gap(events: dict[str, dict],
                 truth: list[dict]) -> list[dict]:
    """Known listed-common emergences NOT present in our fused corpus."""
    caught_names = {_norm(ev["name"]) for ev in events.values()}
    caught_tickers = {re.sub(r"[^A-Za-z0-9]", "",
                             (ev["ticker"] or "").split(":")[-1]).upper()
                      for ev in events.values() if ev["ticker"]}
    gaps = []
    for t in truth:
        if not t.get("listed_common", True):
            continue
        nm = _norm(t.get("name", ""))
        tk = re.sub(r"[^A-Za-z0-9]", "",
                    (t.get("ticker") or "").split(":")[-1]).upper()
        if nm in caught_names or (tk and tk in caught_tickers):
            continue
        gaps.append(t)
    return gaps


def main() -> int:
    events = collect_signals()
    truth = load_ground_truth()
    ordered = sorted(events.values(),
                     key=lambda e: (e["primary"], len(e["channels"]),
                                    e["last_filed"]), reverse=True)
    high = [e for e in ordered if confidence(e).startswith("high")]
    primary = [e for e in ordered if e["primary"]]
    pending = [e for e in ordered if e.get("pending")]
    gaps = coverage_gap(events, truth)

    # persist the fused list
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(
        [{**e, "confidence": confidence(e)} for e in ordered],
        indent=2, sort_keys=True, default=str))

    lines = [
        "# Emergence master — multi-source triangulation",
        "",
        "Every Chapter 11 emergence signal in `data/inbox/`, fused by entity "
        "and scored by how many INDEPENDENT SEC channels corroborate it. "
        "Primary channels (emergence 8-K, fresh-start accounting, "
        "plan-effective) ARE an emergence; structural channels (Form 25/15 "
        "delisting, Form 8-A relisting, PACER docket, 8-K Item 1.03) raise "
        "confidence.",
        "",
        f"- fused emergence events: **{len(ordered)}**  ·  with a primary "
        f"signal: **{len(primary)}**  ·  high-confidence (primary + "
        f"corroboration): **{len(high)}**  ·  pending (Q-suffix, still in "
        f"Chapter 11): **{len(pending)}**",
        f"- ground-truth known emergences loaded: **{len(truth)}**  ·  "
        f"**coverage gaps (known, listed, NOT caught): {len(gaps)}**",
        "",
        "## Fused events (most-corroborated first)",
        "",
        "| Entity | Ticker | Confidence | Channels | Last filing |",
        "|---|---|---|---|---|",
    ]
    for e in ordered[:200]:
        chans = "; ".join(f"{k}×{v}" if v > 1 else k
                          for k, v in e["channels"].items())
        lines.append(f"| {str(e['name'])[:36]} | {e['ticker'] or '—'} | "
                     f"{confidence(e)} | {chans[:80]} | {e['last_filed']} |")

    lines += ["", "## Coverage gaps — known emergences we FAILED to catch", ""]
    if not truth:
        lines.append("_No ground-truth list loaded "
                     "(`data/emergence_ground_truth.json`). Populate it from "
                     "the emergence-catch audit to activate the tripwire._")
    elif gaps:
        lines += ["These listed-common emergences are in the ground-truth "
                  "list but absent from our fused corpus — the poller must be "
                  "broadened to catch them.", "",
                  "| Name | Ticker | Emergence date | Note |", "|---|---|---|---|"]
        for g in gaps:
            lines.append(f"| {str(g.get('name',''))[:36]} | "
                         f"{g.get('ticker') or '—'} | "
                         f"{g.get('emergence_date','')} | "
                         f"{str(g.get('note',''))[:50]} |")
    else:
        lines.append("No coverage gaps: every known listed-common emergence "
                     "in the ground-truth list is present in our corpus. ✓")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"Fused emergence events: {len(ordered)} "
          f"(primary {len(primary)}, high-conf {len(high)})")
    print(f"Ground-truth: {len(truth)}  ·  coverage gaps: {len(gaps)}")
    print(f"Wrote {OUT_JSON} and {OUT_MD}")
    if gaps:
        print("\nCoverage gaps (known emergences NOT caught):")
        for g in gaps[:20]:
            print(f"  {(g.get('ticker') or '—'):8} {str(g.get('name',''))[:40]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
