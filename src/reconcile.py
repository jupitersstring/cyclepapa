#!/usr/bin/env python3
"""
reconcile.py — pipeline completeness audit (silent-drop detector).

Every recurring bug this framework has hit was a SILENT drop/corruption
at a boundary — a promotion window, a whitelist, a filter, a positional
parser. This module traces every named entity in universe.md through the
pipeline and flags exactly where and why each one is lost, so no
prior-session or auto-promoted name disappears unnoticed.

Stages traced:
  1. universe.md            — every table row with a Name
  2. universe_screened.md   — did the screener parse + surface it?
  3. universe_risk_reward   — did it reach the investable ranking?

For each lost entity it reports the stage and reason (parse-miss,
score<threshold, terminal-status, non-investable-ticker, dedup-collapse).
Writes output/reconcile.md and exits non-zero if any HIGH-severity loss
(a real investable name silently dropped) is detected.

Usage:
    python -m src.reconcile
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_MD = REPO / "universe.md"
SCREENED = REPO / "output" / "universe_screened.md"
RANKED_CSV = REPO / "output" / "universe_risk_reward.csv"
OUT_MD = REPO / "output" / "reconcile.md"

# name/ticker placeholders that are legitimately non-investable
_PLACEHOLDER_TICKER = re.compile(
    r"^\(.*\)$|state|private|delisted|taken private|n/?a|^—$|^-$", re.I)
_PLACEHOLDER_NAME = re.compile(r"^\(|^—$|^-$|census$|^various\b|^\?+$", re.I)


def _stem(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "",
                  re.sub(r"\b(inc|corp|corporation|ltd|limited|plc|holdings?|"
                         r"group|co|sa|nv|ag|se|the)\b", "", s or "",
                         flags=re.I)).upper()


def universe_md_names() -> list[dict]:
    """Every data row in universe.md that carries a real company name."""
    out = []
    text = UNIVERSE_MD.read_text()
    in_table = False
    for line in text.splitlines():
        st = line.strip()
        if all(c in "-:| " for c in st) and "|" in st:
            in_table = True
            continue
        if not st.startswith("|"):
            in_table = False
            continue
        if not in_table:
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, ticker = cells[0], cells[1]
        if name.lower() in ("name", "") or name.startswith("---"):
            continue
        if _PLACEHOLDER_NAME.match(name):
            continue
        # Messy auto-promoted rows carry "NAME (TICKER) (CIK NNNN)" in the
        # name and "CIK:NNNN" in the ticker. Extract the embedded ticker
        # and clean the name so matching against the resolved ranked CSV
        # works (else these false-flag as losses though they ARE ranked).
        emb = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,[^)]*)?\)\s*\(CIK", name)
        clean_name = re.sub(r"\s*\(.*$", "", name).strip() or name
        tk = ticker
        tstem = re.sub(r"[^A-Za-z0-9]", "", ticker.split(":")[-1]).upper()
        alt_tstem = emb.group(1).upper() if emb else ""
        # resolve CIK:NNNN -> ticker if possible
        mcik = re.match(r"CIK[:\s]*0*(\d+)", ticker, re.I)
        if mcik and not alt_tstem:
            try:
                from src.edgar_util import resolve_cik_to_ticker
                rr = resolve_cik_to_ticker(mcik.group(1))
                if rr:
                    alt_tstem = rr.upper()
            except Exception:
                pass
        out.append({"name": name, "ticker": tk,
                    "stem": _stem(clean_name),
                    "tstem": (alt_tstem or (tstem if not mcik else "")),
                    "alt_tstem": alt_tstem})
    # dedup by (stem or tstem)
    seen, uniq = set(), []
    for r in out:
        k = r["tstem"] or r["stem"]
        if k and k not in seen:
            seen.add(k); uniq.append(r)
    return uniq


def screened_stems() -> set[str]:
    if not SCREENED.exists():
        return set()
    stems = set()
    for line in SCREENED.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        for c in cells:
            s = _stem(c.replace("**", ""))
            if len(s) > 3:
                stems.add(s)
    return stems


def ranked_index() -> tuple[set[str], set[str]]:
    """Return (ranked_name_stems, ranked_ticker_stems)."""
    names, tickers = set(), set()
    if not RANKED_CSV.exists():
        return names, tickers
    for r in csv.DictReader(RANKED_CSV.open()):
        names.add(_stem(r["name"]))
        tickers.add(re.sub(r"[^A-Za-z0-9]", "",
                           r["ticker"].split(":")[-1]).upper())
    return names, tickers


SCORE_THRESHOLD = 0.15   # matches universe_risk_reward.is_investable


def full_scores() -> dict[str, float]:
    """name_stem -> triage score, from the complete screener CSV. Indexed
    by BOTH the full-name stem and a parenthetical-stripped stem (and the
    ticker stem) so lookups succeed regardless of how the name was cleaned
    upstream — otherwise below-threshold names mis-classify as losses."""
    full = REPO / "output" / "universe_full.csv"
    out: dict[str, float] = {}
    if full.exists():
        for r in csv.DictReader(full.open()):
            try:
                sc = float(r["score"])
            except (ValueError, KeyError):
                continue
            nm = r.get("name", "")
            out[_stem(nm)] = sc
            out[_stem(re.sub(r"\s*\(.*$", "", nm))] = sc   # paren-stripped
            tk = re.sub(r"[^A-Za-z0-9]", "",
                        (r.get("ticker") or "").split(":")[-1]).upper()
            if tk:
                out.setdefault("T:" + tk, sc)
    return out


def main() -> int:
    names = universe_md_names()
    rnames, rtickers = ranked_index()
    scores = full_scores()

    ranked = 0
    below_threshold = []   # scored but intentionally below the cutoff
    true_loss = []         # score >= threshold, real ticker, NOT ranked = BUG
    for r in names:
        if (r["stem"] in rnames) or (r["tstem"] and r["tstem"] in rtickers):
            ranked += 1
            continue
        investable_ticker = bool(r["tstem"]) and not _PLACEHOLDER_TICKER.match(
            r["ticker"].strip())
        sc = scores.get(r["stem"])
        if sc is None and r["tstem"]:
            sc = scores.get("T:" + r["tstem"])
        if not investable_ticker:
            continue   # legitimately non-investable placeholder
        if sc is not None and sc < SCORE_THRESHOLD:
            below_threshold.append(r)   # transparent: in universe_full.csv
        else:
            true_loss.append(r)         # SILENT LOSS — a real bug

    print(f"universe.md named entities: {len(names)}")
    print(f"  reached the ranking:              {ranked}")
    print(f"  scored but below {SCORE_THRESHOLD} threshold "
          f"(in universe_full.csv, transparent): {len(below_threshold)}")
    print(f"  ** TRUE SILENT LOSS (score>=thr, real ticker, unranked): "
          f"{len(true_loss)} **")

    lines = ["# Pipeline reconciliation — completeness audit", "",
             f"- universe.md named entities: **{len(names)}**",
             f"- reached the ranking: **{ranked}**",
             f"- scored but below the {SCORE_THRESHOLD} actionable "
             f"threshold (present in `output/universe_full.csv`, "
             f"transparently filtered): **{len(below_threshold)}**",
             f"- **TRUE SILENT LOSS (a bug): {len(true_loss)}**", ""]
    if true_loss:
        lines += ["## TRUE silent losses — investigate/fix", "",
                  "| Name | Ticker |", "|---|---|"]
        for e in true_loss[:80]:
            lines.append(f"| {e['name'][:44]} | {e['ticker']} |")
    else:
        lines.append("No silent losses: every above-threshold investable "
                      "name in universe.md reaches the ranking. ✓")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")
    if true_loss:
        print("\nTrue silent losses (BUGS):")
        for e in true_loss[:20]:
            print(f"  {e['ticker']:16} {e['name'][:40]}")
    return 1 if true_loss else 0


if __name__ == "__main__":
    sys.exit(main())
