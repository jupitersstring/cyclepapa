"""MD&A language scan -- management's own words as a revealed-intent signal.

Item 7 (10-K) / Item 2 (10-Q) MD&A is where management describes, in its
own narrative, what it is DOING and INTENDS to do. Event-based layers here
(tender, spinoff, buyback, activist) catch the ACTION once filed; this
layer catches the STATED INTENT earlier, from the company's own
discussion, across five families of high-signal language:

  * VALUE_UNLOCK      -- strategic review, monetize non-core, sum-of-the-
                         parts, unlock shareholder value, realize value
  * TRANSFORMATIVE    -- transformative/transformational transaction,
                         inflection point, step change, pivotal
  * CAPITAL_POLICY    -- return capital, initiate dividend, accelerate
                         buyback, deleverage / reduce leverage
  * GOVERNANCE_ACTION -- board refresh, cooperation agreement, declassify,
                         split chair/CEO, enhanced governance
  * STRATEGIC_ACTION  -- separation / spin-off, sale of the company, exit
                         non-core, restructuring / cost-reduction program

Method (mirrors credit_agreement_mine.py): each phrase is one EFTS exact-
phrase query restricted to 10-K / 10-Q, so a single call returns every
filer using it. Phrases are RARITY-weighted -- distinctive intent language
scores high; generic language scores low and leans on CONVERGENCE (several
families firing on one name is the real tell). Top candidates are text-
verified to strip NEGATED / safe-harbour uses ("we may NOT be able to
unlock value", "no assurance", risk-factor hypotheticals).

Additive and orthogonal: it scores narrative INTENT, not a filed event, so
it leads the event layers rather than duplicating them; the correlation
stage reports any overlap honestly.

Output: mda_scan.json keyed by ticker -> {score, categories, phrases,
n_categories, small_cap}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import io_util
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "mda_scan.json"

# (phrase, category, points). Points encode rarity/optionality: a phrase
# that names a specific, uncommon intent scores high; broad language scores
# low and must converge with others to matter.
PHRASES: list[tuple[str, str, int]] = [
    # --- VALUE_UNLOCK ---
    ("review of strategic alternatives", "value_unlock", 10),
    ("exploring strategic alternatives", "value_unlock", 10),
    ("unlock shareholder value", "value_unlock", 9),
    ("unlock the value", "value_unlock", 8),
    ("sum-of-the-parts", "value_unlock", 9),
    ("monetize non-core", "value_unlock", 8),
    ("monetization of", "value_unlock", 4),
    ("realize the value", "value_unlock", 5),
    ("maximize shareholder value", "value_unlock", 4),
    # --- TRANSFORMATIVE ---
    ("transformative acquisition", "transformative", 9),
    ("transformational transaction", "transformative", 9),
    ("transformative transaction", "transformative", 9),
    ("inflection point", "transformative", 6),
    ("step change", "transformative", 5),
    ("pivotal year", "transformative", 5),
    # --- CAPITAL_POLICY ---
    ("return capital to shareholders", "capital_policy", 7),
    ("return of capital to", "capital_policy", 6),
    ("initiate a dividend", "capital_policy", 8),
    ("initiated a quarterly dividend", "capital_policy", 8),
    ("accelerate our share repurchase", "capital_policy", 7),
    ("reduce our leverage", "capital_policy", 5),
    ("reduce our net leverage", "capital_policy", 6),
    ("deleveraging", "capital_policy", 4),
    ("capital allocation priorities", "capital_policy", 4),
    # --- GOVERNANCE_ACTION ---
    ("cooperation agreement", "governance_action", 8),
    ("refreshed our board", "governance_action", 8),
    ("enhanced our corporate governance", "governance_action", 6),
    ("separated the roles", "governance_action", 6),
    ("declassify our board", "governance_action", 8),
    # --- STRATEGIC_ACTION ---
    ("pursue a spin-off", "strategic_action", 9),
    ("planned separation", "strategic_action", 8),
    ("separation into two", "strategic_action", 9),
    ("sale of the company", "strategic_action", 7),
    ("exit non-core", "strategic_action", 7),
    ("wind down", "strategic_action", 4),
    ("restructuring plan", "strategic_action", 4),
    ("cost reduction program", "strategic_action", 4),
    ("portfolio optimization", "strategic_action", 5),
]

# A phrase counts as a genuine intent only when it is NOT negated and NOT a
# safe-harbour / risk-factor hypothetical. These tokens, appearing just
# before the phrase, disqualify that occurrence.
NEG_BEFORE = re.compile(
    r"(?:\bnot\b|\bno\b|\bnever\b|\bunable to\b|\bcannot\b|\bfailed to\b|"
    r"\bdo(?:es)? not\b|\bdid not\b|\bwill not\b|\bwould not\b|\bno assurance\b|"
    r"\bno plans?\b|\bnot expect\b|\bnot intend\b|\bno longer\b)"
    r"[^.\n]{0,60}$", re.I)

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TK.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, forms="10-K,10-Q", cap=60):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}"
           f"&forms={requests_quote(forms)}")
    for _ in range(3):
        try:
            d = _get(url).json(); break
        except Exception:
            time.sleep(1.5); d = None
    if not d:
        return []
    out = []
    for h in (d.get("hits", {}).get("hits", []) or [])[:cap]:
        src = h.get("_source", {}) or {}
        ciks = src.get("ciks") or []
        tk = None
        for nm in (src.get("display_names") or []):
            m = _DT.search(nm)
            if m:
                tk = m.group(1); break
        out.append({"ticker": tk,
                    "cik": f"{int(ciks[0]):010d}" if ciks else None,
                    "accession": src.get("adsh"), "date": src.get("file_date")})
    return out


def fetch_text(cik, acc):
    from recent import _get
    if not cik or not acc:
        return ""
    accn = acc.replace("-", "")
    try:
        idx = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/index.json").json()
        docs = [i["name"] for i in idx["directory"]["item"]
                if i["name"].endswith((".htm", ".html")) and "index" not in i["name"]
                and not i["name"].startswith("R")]
        txt = ""
        for d in docs[:2]:
            txt += re.sub(r"<[^>]+>", " ",
                          _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{d}").text)
        return re.sub(r"\s+", " ", txt)[:600000]
    except Exception:
        return ""


def _phrase_is_affirmative(text_lc: str, phrase: str) -> bool:
    """True if the phrase appears at least once NOT immediately preceded by a
    negation token. Returns False only if EVERY occurrence is negated."""
    p = phrase.lower()
    start = 0
    while True:
        i = text_lc.find(p, start)
        if i < 0:
            return False
        pre = text_lc[max(0, i - 60):i]
        if not NEG_BEFORE.search(pre):
            return True
        start = i + len(p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180,
                    help="Look-back window for 10-K/10-Q MD&A (default 180).")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--verify-top", type=int, default=40,
                    help="Text-verify (negation strip) the top-N candidates.")
    ap.add_argument("--cap", type=int, default=60,
                    help="Max filers per phrase (EFTS truncation guard).")
    args = ap.parse_args()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"MD&A language sweep {start}..{end} "
          f"({len(PHRASES)} phrases)", file=sys.stderr)

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}

    # 1) EFTS phrase sweep -> per-ticker category hits.
    per: dict[str, dict] = {}
    for phrase, cat, pts in PHRASES:
        hits = efts(phrase, start, end, cap=args.cap)
        time.sleep(args.sleep)
        # a truncated (cap-filling) generic phrase is low-signal; damp it.
        damp = 0.5 if len(hits) >= args.cap else 1.0
        seen_tk = set()
        for h in hits:
            tk = (h.get("ticker") or "").upper()
            if not _valid(tk) or tk in seen_tk:
                continue
            seen_tk.add(tk)
            bad, _ = is_excluded(tk)
            if bad:
                continue
            rec = per.setdefault(tk, {
                "ticker": tk, "score": 0.0, "categories": {},
                "phrases": [], "hits": {}, "n_categories": 0})
            # dedup within a category with diminishing returns.
            cat_seen = rec["categories"].get(cat, 0)
            add = (pts if cat_seen == 0 else max(1, pts // 3)) * damp
            rec["categories"][cat] = round(rec["categories"].get(cat, 0) + add, 1)
            rec["score"] += add
            rec["phrases"].append(phrase)
            rec["hits"][phrase] = {"accession": h.get("accession"),
                                   "cik": h.get("cik"), "date": h.get("date")}
        print(f"  '{phrase}': {len(hits)} filers"
              f"{' (capped)' if len(hits) >= args.cap else ''}",
              file=sys.stderr)

    # 2) convergence bonus: several DIFFERENT families on one name is the
    #    real signal (management describing a coordinated agenda).
    for rec in per.values():
        rec["n_categories"] = len(rec["categories"])
        if rec["n_categories"] >= 3:
            rec["score"] += 8
        elif rec["n_categories"] == 2:
            rec["score"] += 4

    # 3) cheapness torque + small-cap (value-unlock language matters more in
    #    a small, cheap, ignored name than a mega-cap boilerplate MD&A).
    for tk, rec in per.items():
        y = yf.get(tk) or {}
        mcap = y.get("mcap") or 0
        pb = y.get("p_b")
        if mcap and mcap < 2e9:
            rec["score"] += 3; rec["small_cap"] = True
        if pb is not None and 0 < pb < 1.5:
            rec["score"] += 3; rec["cheap_pb"] = True

    # 4) NEGATION verify: for the top-N by score, fetch the filing text and
    #    strip phrases that appear only in negated / safe-harbour context.
    ranked = sorted(per.values(), key=lambda r: -r["score"])
    for rec in ranked[:args.verify_top]:
        # verify the single highest-value phrase hit for this name.
        best = max(rec["phrases"],
                   key=lambda p: next((pt for ph, c, pt in PHRASES if ph == p), 0),
                   default=None)
        if not best:
            continue
        h = rec["hits"].get(best) or {}
        txt = fetch_text(h.get("cik"), h.get("accession"))
        time.sleep(args.sleep)
        rec["verified"] = True
        if txt and not _phrase_is_affirmative(txt.lower(), best):
            # every occurrence negated -> heavy discount (likely risk-factor).
            rec["score"] = round(rec["score"] * 0.4, 1)
            rec["negation_flag"] = best

    for rec in per.values():
        rec["score"] = round(rec["score"], 1)

    out = {tk: rec for tk, rec in per.items() if rec["score"] > 0}
    io_util.write_json(OUT, out)

    scored = sorted(out.values(), key=lambda r: -r["score"])
    print(f"\nwrote {OUT} ({len(out)} names with MD&A intent language)",
          file=sys.stderr)
    print(f"{'TKR':<8}{'SCORE':>6}{'CATS':>5}  TOP FAMILIES")
    for r in scored[:30]:
        cats = ", ".join(sorted(r["categories"], key=lambda c: -r["categories"][c])[:3])
        flag = " [neg]" if r.get("negation_flag") else ""
        print(f"{r['ticker']:<8}{r['score']:>6.1f}{r['n_categories']:>5}  {cats}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
