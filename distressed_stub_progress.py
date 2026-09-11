"""Distressed Stub Progress Engine.

A distressed stub is the small residual security left after senior claims
are deducted from enterprise value. The central warning (from the TXT
checklists): progress for the COMPANY is not necessarily progress for the
STUB. A rescue loan can avert bankruptcy while transferring value to the
rescue lender; an asset sale can cut debt while disposing of the asset
that made the equity valuable; a debt-to-equity swap can restore solvency
while diluting old holders to nothing.

So this engine does NOT alert on restructuring language. It requires:
  1. a FINALITY event (hard completion verb, not intention) -- the same
     restructuring emits ten announcements; only stage advancement counts;
  2. evidence that value reaches the RESIDUAL security (waterfall), with
     heavy penalties for priming, dilution, MIPs, toxic converts;
  3. materiality relative to the (small) stub.

Design follows the spec's stage ladder and §8 scoring. This is the
US/EDGAR implementation -- the RECIPES table carries the phrase
dictionaries and is structured so the global (RNS/HKEX/ASX/local-language)
vocab can be appended later without touching the engine.

Output: distressed_stub_progress.json {ticker: {score, class, stage,
events, counters}}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "distressed_stub_progress.json"

# ---- stage ladder ----------------------------------------------------
# 0 intention, 1 process, 2 agreement, 3 approval, 4 completion,
# 5 value-reaches-stub. Only 3+ is materially evidential.
FINALITY_VERBS = re.compile(
    r"\b(executed|entered into|obtained|approved|adopted|sanctioned|"
    r"confirmed|homologated|completed|closed|settled|received|repaid|"
    r"prepaid|redeemed|retired|cancell?ed|extinguished|released|"
    r"discharged|satisfied|distributed|reinstated|emerged|effectuated|"
    r"consummat\w+|substantially implemented)\b", re.I)
SOFT_VERBS = re.compile(
    r"\b(intends?|expects?|targets?|aims?|seeks?|explor\w+|evaluat\w+|"
    r"consider\w+|propos\w+|contemplat\w+|believes?|anticipat\w+|may|"
    r"could|in discussions|in principle|non[- ]binding|indicative|"
    r"subject to)\b", re.I)

# ---- recipe table (US phrase dictionaries; extensible) ---------------
# Each recipe: phrases already encode a high-finality event; `points`
# follows the §8 positive scale; `forms` restricts EFTS.
RECIPES = [
    {"cls": "debt_retired_below_par", "stage": 4, "points": 4, "forms": "8-K",
     "phrases": ["purchase and cancellation of notes",
                 "gain on extinguishment of debt",
                 "notes accepted for purchase",
                 "privately negotiated repurchases of"]},
    {"cls": "principal_haircut", "stage": 4, "points": 4, "forms": "8-K",
     "phrases": ["forgiveness of principal", "haircut to principal",
                 "creditors agreed to accept", "balance of the debt waived"]},
    {"cls": "lien_release", "stage": 4, "points": 2, "forms": "8-K",
     "phrases": ["deed of release", "obligations discharged",
                 "termination statement", "collateral release"]},
    {"cls": "maturity_extension", "stage": 3, "points": 1, "forms": "8-K",
     "phrases": ["extension of final maturity", "new maturity date"]},
    {"cls": "asset_sale_completed", "stage": 4, "points": 3, "forms": "8-K",
     "phrases": ["net cash proceeds", "closing of the asset sale",
                 "completion of the disposal"]},
    {"cls": "claims_disallowed", "stage": 4, "points": 4, "forms": "8-K",
     "phrases": ["order sustaining objection", "claim is hereby disallowed",
                 "disputed claims reserve", "claim withdrawn with prejudice"]},
    {"cls": "rsa_threshold", "stage": 2, "points": 2, "forms": "8-K",
     "phrases": ["restructuring support agreement",
                 "requisite consenting creditors"]},
    {"cls": "plan_effective", "stage": 5, "points": 3, "forms": "8-K",
     "phrases": ["effective date has occurred", "substantial consummation",
                 "emerged from Chapter 11", "confirmation order"]},
    {"cls": "going_concern_removed", "stage": 4, "points": 2, "forms": "8-K,10-Q,10-K",
     "phrases": ["substantial doubt", "no longer exists"]},
    {"cls": "stub_distribution", "stage": 5, "points": 4, "forms": "8-K",
     "phrases": ["liquidating distribution", "initial distribution to",
                 "return of capital to shareholders"]},
    {"cls": "listing_restored", "stage": 4, "points": 1, "forms": "8-K",
     "phrases": ["resumption of trading", "regained compliance"]},
]

# ---- counter-signals (§9): convert a positive refinancing into value
# transfer AWAY from the stub. Heavy penalties.
COUNTERS = [
    ("priming_superpriority", -4, re.compile(
        r"\b(superpriority|super-priority|priming lien|first-out|roll-up|"
        r"up-?tier|dropdown|debtor-in-possession|DIP facility)\b", re.I)),
    ("equity_wipeout", -10, re.compile(
        r"(existing (equity|shares|equity interests)[^.\n]{0,40}"
        r"(cancell?ed|extinguished|no recovery|no distribution|deemed to reject))",
        re.I)),
    ("toxic_dilution", -4, re.compile(
        r"\b(variable conversion price|discount to lowest trading price|"
        r"committed equity facility|equity purchase facility|reset provision|"
        r"full-ratchet)\b", re.I)),
    ("hidden_claim_growth", -2, re.compile(
        r"\b(PIK (interest|toggle|dividend)|make-whole|redemption premium|"
        r"exit premium|accreted principal|consent fee added to principal)\b", re.I)),
    ("new_preferred", -3, re.compile(
        r"\b(liquidation preference|new preferred)\b", re.I)),
    ("creditor_enforcement", -4, re.compile(
        r"\b(acceleration notice|notice of default|reservation of rights|"
        r"appointment of receiver|foreclosure|cash dominion)\b", re.I)),
]

_TICKER_RX = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and isinstance(tk, str) and tk not in {"NONE", "N/A"}
               and _TICKER_RX.match(tk))


_DISPLAY_TICKER = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")


def efts_hits(phrase, forms, start, end, cap=60):
    """EFTS _source has no `tickers` field -- the ticker lives inside
    display_names ('Name  (TICKER)  (CIK ...)'); accession is `adsh`."""
    from recent import EFTS, _get, requests_quote
    out = []
    url = (f"{EFTS}?forms={requests_quote(forms)}&dateRange=custom"
           f"&startdt={start}&enddt={end}&q={requests_quote(chr(34)+phrase+chr(34))}"
           f"&from=0")
    for attempt in range(3):
        try:
            d = _get(url).json()
            break
        except Exception:
            time.sleep(1.5)
            d = None
    if not d:
        return out
    for h in (d.get("hits", {}).get("hits", []) or [])[:cap]:
        src = h.get("_source", {}) or {}
        ciks = src.get("ciks") or []
        names = src.get("display_names") or []
        ticker = None
        for nm in names:
            m = _DISPLAY_TICKER.search(nm)
            if m:
                ticker = m.group(1)
                break
        acc = src.get("adsh") or (h.get("_id") or "").split(":")[0]
        out.append({"ticker": ticker,
                    "cik": (f"{int(ciks[0]):010d}" if ciks else None),
                    "accession": acc, "date": src.get("file_date")})
    return out


def fetch_text(cik, accession):
    from recent import _get
    if not cik or not accession:
        return ""
    accn = accession.replace("-", "")
    try:
        idx = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/index.json").json()
        docs = [i["name"] for i in idx["directory"]["item"]
                if i["name"].endswith((".htm", ".html")) and "index" not in i["name"]
                and not i["name"].startswith("R")]
        txt = ""
        for dname in docs[:3]:
            body = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{dname}").text
            txt += re.sub(r"<[^>]+>", " ", body)
        return re.sub(r"\s+", " ", txt)
    except Exception:
        return ""


def classify(score):
    if score >= 8:
        return "hard_value_unlock"
    if score >= 4:
        return "real_progress_conditional"
    if score >= 1:
        return "survival_or_process_only"
    return "delay_or_value_transfer_away"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--verify-top", type=int, default=40,
                    help="fetch filing text for the N highest-scoring names to score counter-signals")
    args = ap.parse_args()

    from datetime import datetime, timezone, timedelta
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Distressed-stub sweep {start}..{end}", file=sys.stderr)

    per_ticker: dict[str, dict] = {}
    for rc in RECIPES:
        for phrase in rc["phrases"]:
            for h in efts_hits(phrase, rc["forms"], start, end):
                tk = (h["ticker"] or "").upper()
                if not _valid(tk):
                    continue
                # going_concern_removed needs the removal phrase co-present;
                # a bare "substantial doubt" is the DISTRESS marker, not progress.
                rec = per_ticker.setdefault(tk, {
                    "ticker": tk, "cik": h["cik"], "score": 0.0,
                    "events": [], "max_stage": 0, "counters": []})
                # avoid double-counting the same class from multiple phrases
                if any(e["class"] == rc["cls"] for e in rec["events"]):
                    continue
                rec["events"].append({"class": rc["cls"], "stage": rc["stage"],
                                      "phrase": phrase, "date": h["date"],
                                      "accession": h["accession"]})
                rec["score"] += rc["points"]
                rec["max_stage"] = max(rec["max_stage"], rc["stage"])
                if not rec.get("cik"):
                    rec["cik"] = h["cik"]
            time.sleep(args.sleep)

    # going-concern special case: only a REMOVAL counts (needs both markers)
    for tk, rec in per_ticker.items():
        cls = {e["class"] for e in rec["events"]}
        if "going_concern_removed" in cls:
            # require the "no longer exists" phrase to have hit too
            phrases = {e["phrase"] for e in rec["events"]}
            if "no longer exists" not in phrases:
                rec["events"] = [e for e in rec["events"] if e["class"] != "going_concern_removed"]
                rec["score"] -= 2

    # verify counter-signals for the top names (bounded network cost)
    ranked = sorted(per_ticker.values(), key=lambda r: -r["score"])
    for rec in ranked[:args.verify_top]:
        latest = max(rec["events"], key=lambda e: e.get("date") or "", default=None)
        if not latest:
            continue
        txt = fetch_text(rec["cik"], latest["accession"])
        time.sleep(args.sleep)
        if not txt:
            continue
        for name, pen, rx in COUNTERS:
            if rx.search(txt):
                rec["counters"].append(name)
                rec["score"] += pen

    # ---- baseline-distress gate (spec step 1) ------------------------
    # A value-unlock event only matters for a DISTRESSED STUB. Large
    # healthy caps mention "net cash proceeds" / "lien release" for
    # unrelated reasons. Require a distress marker from local data (no
    # extra network): deep drawdown, sub-$2B and low price, post-Ch11,
    # or Coval-Stafford fire-sale pressure.
    def _load(n):
        p = ROOT / n
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except Exception:
            return {}
    yf = _load("yfinance_quick.json")
    p11 = _load("post_ch11_emergence.json")
    coval = _load("coval_stafford_proxy.json")

    def distressed(tk):
        y = yf.get(tk, {}) or {}
        price = y.get("price")
        mcap = y.get("mcap")
        hi = y.get("fwk_high")
        if mcap and mcap > 15e9:
            return False                       # a mega-cap is never a stub
        if (p11.get(tk, {}) or {}).get("score", 0) > 0:
            return True
        if (coval.get(tk, {}) or {}).get("score", 0) >= 20:
            return True
        if tk.endswith("Q"):                    # post-reorg Q-ticker stub
            return True
        try:
            if mcap and mcap < 10e9 and price and hi and hi > 0 \
                    and (1 - price / hi) > 0.55:
                return True
            if mcap and price and mcap < 2e9 and price < 15:
                return True
        except Exception:
            pass
        return False

    out = {}
    dropped = 0
    for tk, rec in per_ticker.items():
        rec["score"] = round(rec["score"], 1)
        rec["distressed"] = distressed(tk)
        if not rec["distressed"] and rec["score"] < 8:
            # keep only genuine hard-unlocks among non-distressed (rare)
            dropped += 1
            continue
        rec["classification"] = classify(rec["score"])
        out[tk] = rec
    print(f"  distress gate dropped {dropped} non-distressed names", file=sys.stderr)
    io_util.write_json(OUT, out)

    scored = [r for r in out.values() if r["score"] > 0]
    print(f"wrote {OUT} ({len(out)} names, {len(scored)} net-positive)")
    print("\n=== TOP DISTRESSED-STUB PROGRESS ===")
    print(f"{'TKR':<7}{'SCR':>5}{'STG':>4}  {'CLASS':<26}EVENTS")
    for r in sorted(out.values(), key=lambda x: -x["score"])[:25]:
        cls = ",".join(sorted({e["class"] for e in r["events"]}))[:40]
        ct = (" | COUNTER:" + ",".join(r["counters"])) if r["counters"] else ""
        print(f"{r['ticker']:<7}{r['score']:>5.0f}{r['max_stage']:>4}  "
              f"{r['classification']:<26}{cls}{ct}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
