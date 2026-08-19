"""Credit-Agreement Mining for incentivised value realisation.

The SSP (E.W. Scripps) insight: a credit agreement that MANDATES asset-
disposition proceeds be applied to debt paydown creates a structural,
INCENTIVISED path to value realisation. On a small levered equity base,
selling a hidden/undervalued asset is stub-accretive -- $X of proceeds
retires $X of senior debt, lifting the residual equity by ~$X. The credit
agreement is the mechanism; the hidden asset is the fuel.

The mandatory-prepayment-on-disposition clause alone is common (most
credit agreements have it). What makes a HIGH-VALUE setup is the
CONJUNCTION:
  1. a rare, valuable, under-recognised asset (spectrum, licences,
     mineral/water/air rights, real estate, royalty/IP portfolio);
  2. a credit agreement sweeping ~100% of disposition proceeds to debt;
  3. a small equity base beneath meaningful leverage (so deleveraging
     moves the stub a lot).

Output: credit_agreement_mine.json {ticker: {asset_type, mandatory_
prepay, score, ...}}, merged with the curated hidden_asset_watch.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "credit_agreement_mine.json"
WATCH = ROOT / "hidden_asset_watch.json"

# Under-recognised asset classes spanning ALL industries. Each:
# (search phrase, asset_type, industry category, rarity/optionality
# points). Rarer / more-optionable assets score higher; broad classes
# (real estate, patents) score low and lean on the conjunction gates
# (small-cap + net-debt + mandatory-prepay) to avoid false positives.
# The phrase is kept specific enough to be a real balance-sheet asset,
# not incidental prose.
HIDDEN_ASSETS = [
    # --- Media / Telecom / Digital infrastructure ---
    ("spectrum usage rights", "spectrum", "telecom", 14),
    ("spectrum licenses", "spectrum", "telecom", 14),
    ("broadcast licenses", "broadcast_licences", "media", 10),
    ("fcc licenses", "fcc_licences", "telecom", 10),
    ("fiber network", "fiber", "telecom", 7),
    ("data center", "data_center", "telecom", 6),
    ("cell towers", "towers", "telecom", 8),
    # --- Natural resources / Energy ---
    ("mineral rights", "mineral_rights", "resources", 10),
    ("water rights", "water_rights", "resources", 12),
    ("oil and gas reserves", "og_reserves", "energy", 7),
    ("proved reserves", "og_reserves", "energy", 6),
    ("timberland", "timberland", "resources", 8),
    ("net royalty acres", "royalty_acres", "energy", 12),
    ("carbon credits", "carbon_credits", "resources", 9),
    # --- Real estate embedded in operating companies ---
    ("owned real estate", "real_estate", "real_estate", 6),
    ("real estate portfolio", "real_estate", "real_estate", 6),
    ("ground lease", "ground_lease", "real_estate", 9),
    ("air rights", "air_rights", "real_estate", 10),
    ("land bank", "land_bank", "real_estate", 8),
    ("owned and operated stores", "owned_stores", "retail", 6),
    # --- Financial / off-balance-sheet value ---
    ("net operating loss carryforward", "nol", "any", 8),
    ("deferred tax asset", "dta", "any", 5),
    ("equity method investment", "equity_stake", "any", 7),
    ("mortgage servicing rights", "msr", "financials", 8),
    ("overfunded pension", "pension_surplus", "any", 9),
    ("pension surplus", "pension_surplus", "any", 9),
    ("investment securities portfolio", "securities", "financials", 5),
    # --- IP / intangible / contractual ---
    ("royalty interest", "royalty", "healthcare", 8),
    ("royalty stream", "royalty", "healthcare", 8),
    ("patent portfolio", "patents", "tech", 6),
    ("milestone payments", "milestones", "healthcare", 6),
    ("contingent value right", "cvr", "any", 9),
    ("litigation claim", "litigation", "any", 7),
    ("insurance recovery", "insurance", "any", 6),
    # --- Holding-company / sum-of-parts ---
    ("equity stake", "equity_stake", "holdco", 7),
    ("minority interest in", "minority_stake", "holdco", 6),
    ("strategic investment in", "strategic_stake", "holdco", 6),
]
# Mandatory-prepayment-on-disposition structure (the mechanism).
MANDATORY_PREPAY_RX = re.compile(
    r"(net cash proceeds[^.\n]{0,120}?(mandatory prepayment|prepay|"
    r"repay the (?:term )?loans?)|"
    r"mandatory prepayment[^.\n]{0,120}?(disposition|asset sale|"
    r"net cash proceeds)|"
    r"100%\s+of\s+the\s+net\s+cash\s+proceeds|"
    r"substantially all[^.\n]{0,40}?net cash proceeds)", re.I)
REINVEST_RX = re.compile(r"reinvest\w*[^.\n]{0,60}?\$?(\d[\d,]*)\s*(million|thousand)?", re.I)

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TK.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, forms=None, cap=40):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}")
    if forms:
        url += f"&forms={requests_quote(forms)}"
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
        out.append({"ticker": tk, "cik": f"{int(ciks[0]):010d}" if ciks else None,
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
        return re.sub(r"\s+", " ", txt)[:400000]
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--verify-top", type=int, default=25)
    args = ap.parse_args()
    from datetime import datetime, timezone, timedelta
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Credit-agreement / hidden-asset sweep {start}..{end}", file=sys.stderr)

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}
    q10 = json.loads((ROOT / "quarterly_10q_data.json").read_text()) \
        if (ROOT / "quarterly_10q_data.json").exists() else {}
    watch = json.loads(WATCH.read_text()) if WATCH.exists() else {}

    # 1. find hidden-asset filers across ALL industry categories
    per: dict[str, dict] = {}
    for phrase, atype, category, pts in HIDDEN_ASSETS:
        for h in efts(phrase, start, end):
            tk = (h["ticker"] or "").upper()
            if not _valid(tk):
                continue
            rec = per.setdefault(tk, {"ticker": tk, "cik": h["cik"],
                                      "asset_types": {}, "categories": {},
                                      "score": 0.0, "mandatory_prepay": None,
                                      "latest_accession": h["accession"],
                                      "date": h["date"]})
            if atype not in rec["asset_types"]:
                rec["asset_types"][atype] = pts
                rec["categories"][category] = rec["categories"].get(category, 0) + 1
                # first asset in a category scores full; extra assets in the
                # SAME category add only a little (diminishing) so a name is
                # not over-credited for synonyms
                same_cat = rec["categories"][category]
                rec["score"] += pts if same_cat == 1 else max(2, pts // 3)
            if (h["date"] or "") > (rec.get("date") or ""):
                rec["date"] = h["date"]; rec["latest_accession"] = h["accession"]
                rec["cik"] = h["cik"] or rec["cik"]
        time.sleep(args.sleep)
    print(f"  {len(per)} hidden-asset filers; small-cap/leverage weighting + prepay check",
          file=sys.stderr)

    # 2. small-levered-equity amplifier (local data) + rank
    for tk, rec in per.items():
        y = yf.get(tk, {}) or {}
        mcap = y.get("mcap")
        q = q10.get(tk, {}) or {}
        net_cash = q.get("net_cash")
        if mcap and mcap < 2e9:
            rec["score"] += 6; rec["small_cap"] = True
        elif mcap and mcap < 5e9:
            rec["score"] += 3
        if net_cash is not None and net_cash < 0:
            rec["score"] += 4; rec["net_debt"] = True   # deleveraging has torque

    # 3. verify the mandatory-prepayment structure for the top names
    ranked = sorted(per.values(), key=lambda r: -r["score"])
    for rec in ranked[:args.verify_top]:
        txt = fetch_text(rec["cik"], rec["latest_accession"])
        time.sleep(args.sleep)
        if txt and MANDATORY_PREPAY_RX.search(txt):
            rec["mandatory_prepay"] = True
            rec["score"] += 12                       # the incentivised-realisation mechanism
        elif txt:
            rec["mandatory_prepay"] = False

    # 4. merge curated watch (SSP): baseline + catalyst triggers
    for tk, w in watch.items():
        if tk.startswith("_"):
            continue
        rec = per.setdefault(tk, {"ticker": tk, "asset_types": {}, "score": 0.0})
        rec["watch"] = True
        rec["hidden_asset"] = w.get("hidden_asset")
        rec["credit_agreement_feature"] = w.get("credit_agreement_feature")
        rec["catalyst_triggers"] = w.get("catalyst_triggers")
        rec["counter_risks"] = w.get("counter_risks")
        rec["score"] = max(rec["score"], 20.0)       # curated conviction floor
        rec["mandatory_prepay"] = True

    out = {}
    for tk, rec in per.items():
        rec["score"] = round(rec["score"], 1)
        if isinstance(rec.get("asset_types"), dict):
            rec["asset_types"] = list(rec["asset_types"].keys())
        if isinstance(rec.get("categories"), dict):
            rec["categories"] = sorted(rec["categories"].keys())
        out[tk] = rec
    OUT.write_text(json.dumps(out, indent=2))
    scored = [r for r in out.values() if r["score"] > 0]
    print(f"wrote {OUT} ({len(out)} names, {len(scored)} scored)")
    from collections import Counter
    cats = Counter(c for r in out.values() for c in (r.get("categories") or []))
    print(f"  industry categories surfaced: {dict(cats)}", file=sys.stderr)
    print("\n=== TOP HIDDEN-ASSET / INCENTIVISED-REALISATION SETUPS ===")
    print(f"{'TKR':<7}{'SCR':>6} {'PREPAY':<7}{'CAT':<12}ASSETS")
    for r in sorted(out.values(), key=lambda x: -x["score"])[:25]:
        mp = "yes" if r.get("mandatory_prepay") else ("no" if r.get("mandatory_prepay") is False else "?")
        cat = ",".join(r.get("categories") or [])[:11] or ("WATCH" if r.get("watch") else "")
        assets = ",".join(r.get("asset_types") or []) or (r.get("hidden_asset", "")[:30])
        print(f"{r['ticker']:<7}{r['score']:>6.0f} {mp:<7}{cat:<12}{assets[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
