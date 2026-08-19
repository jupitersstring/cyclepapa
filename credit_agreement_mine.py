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

# Rare, under-recognised asset classes (points ~ rarity/optionality).
HIDDEN_ASSETS = [
    ("spectrum usage rights", "spectrum", 14),
    ("broadcast licenses", "broadcast_licences", 10),
    ("spectrum licenses", "spectrum", 14),
    ("mineral rights", "mineral_rights", 10),
    ("water rights", "water_rights", 12),
    ("timberland", "timberland", 8),
    ("royalty interest", "royalty", 8),
    ("air rights", "air_rights", 10),
    ("owned real estate", "real_estate", 6),
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

    # 1. find hidden-asset filers
    per: dict[str, dict] = {}
    for phrase, atype, pts in HIDDEN_ASSETS:
        for h in efts(phrase, start, end):
            tk = (h["ticker"] or "").upper()
            if not _valid(tk):
                continue
            rec = per.setdefault(tk, {"ticker": tk, "cik": h["cik"],
                                      "asset_types": {}, "score": 0.0,
                                      "mandatory_prepay": None,
                                      "latest_accession": h["accession"],
                                      "date": h["date"]})
            if atype not in rec["asset_types"]:
                rec["asset_types"][atype] = pts
                rec["score"] += pts
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
        rec["asset_types"] = list(rec["asset_types"].keys()) if isinstance(rec.get("asset_types"), dict) else rec.get("asset_types")
        out[tk] = rec
    OUT.write_text(json.dumps(out, indent=2))
    scored = [r for r in out.values() if r["score"] > 0]
    print(f"wrote {OUT} ({len(out)} names, {len(scored)} scored)")
    print("\n=== TOP HIDDEN-ASSET / INCENTIVISED-REALISATION SETUPS ===")
    print(f"{'TKR':<7}{'SCR':>6} {'PREPAY':<7}{'WATCH':<6}ASSETS")
    for r in sorted(out.values(), key=lambda x: -x["score"])[:20]:
        mp = "yes" if r.get("mandatory_prepay") else ("no" if r.get("mandatory_prepay") is False else "?")
        w = "WATCH" if r.get("watch") else ""
        assets = ",".join(r.get("asset_types") or []) or (r.get("hidden_asset", "")[:30])
        print(f"{r['ticker']:<7}{r['score']:>6.0f} {mp:<7}{w:<6}{assets[:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
