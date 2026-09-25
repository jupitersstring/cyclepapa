"""Premium Capital Injection Scanner (revealed preference).

The highest-value revealed-preference signal: a sophisticated investor
knowingly subscribes for NEWLY ISSUED shares ABOVE the quoted market
price. If the screen says 80 and a specialist fund pays 100 direct from
the company, it has chosen to pay 25% more than it could have paid in the
market -- which is only rational if it believes intrinsic value is higher
still, or it obtained something not visible in the premium.

Almost every US placement is at a DISCOUNT to market. So the filter that
isolates the rare, information-rich class is simply: an equity-issuance
event AND an explicit premium statement in the filing. That combination
is unusual by construction.

Revealed-Preference Score (spec §9), with side-consideration penalties:
  RPS = premium x stake x investor-quality x lockup x governance
        - penalties for warrants / preferred / anti-dilution that make
          the apparent premium illusory.

Output: premium_injection_scan.json {ticker: {premium_pct, rps, ...}}.
US/EDGAR implementation; recipe phrases structured for global extension.
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
OUT = ROOT / "premium_injection_scan.json"

# Event phrases (spec §2 core dictionary; US subset).
EVENT_PHRASES = [
    "securities purchase agreement", "private placement",
    "registered direct offering", "strategic investment",
    "subscription agreement", "share subscription",
    "cornerstone investor", "anchor investor", "PIPE",
]
# An explicit premium statement -- the rare, decisive marker.
PREMIUM_RX = re.compile(
    r"(premium (?:to|over|of)\b|above the (?:closing|market) price|"
    r"above market price|represents? a premium|premium to (?:the )?"
    r"(?:closing price|previous close|last close|VWAP|"
    r"\d+[- ]day (?:average|VWAP)))", re.I)
PREMIUM_PCT_RX = re.compile(
    r"premium of (?:approximately )?(\d{1,3}(?:\.\d+)?)\s*%|"
    r"(\d{1,3}(?:\.\d+)?)\s*%\s+premium", re.I)
PRICE_PER_SHARE_RX = re.compile(
    r"(?:purchase price|subscription price|price)\s+of\s+"
    r"\$?(\d+(?:\.\d+)?)\s+per\s+(?:share|unit)", re.I)

# Governance commitments (spec §9 bonus).
GOV_RX = re.compile(
    r"\b(board seat|board of directors|observer rights?|nomination rights?|"
    r"standstill|voting agreement|registration rights|lock[- ]?up|"
    r"strategic cooperation|supply agreement)\b", re.I)
LOCKUP_RX = re.compile(r"lock[- ]?up[^.\n]{0,40}?(\d{1,3})\s*(month|day|year)", re.I)
# Side-consideration penalties (spec §9): make the premium possibly fake.
SIDE_RX = re.compile(
    r"\b(warrants?|convertible (?:note|preferred|debenture)|"
    r"liquidation preference|anti-dilution|price protection|"
    r"most favored nation|ratchet|redemption right)\b", re.I)

_DISPLAY_TICKER = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TICKER_RX = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TICKER_RX.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, cap=50):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?forms=8-K&dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}")
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
            m = _DISPLAY_TICKER.search(nm)
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
        return re.sub(r"\s+", " ", txt)
    except Exception:
        return ""


def score(premium_pct, gov, lockup_m, side, yf_price, sub_price):
    """RPS-lite (spec §9). Premium is the core; governance and lockup add;
    side considerations subtract because they can make the premium fake."""
    s = 0.0
    reasons = []
    # explicit premium % (best) or computed vs current price (proxy)
    prem = premium_pct
    if prem is None and yf_price and sub_price and yf_price > 0:
        prem = (sub_price / yf_price - 1) * 100
    if prem is not None:
        if prem >= 25:
            s += 25; reasons.append(f"{prem:.0f}% premium (large)")
        elif prem >= 10:
            s += 15; reasons.append(f"{prem:.0f}% premium")
        elif prem >= 2:
            s += 6; reasons.append(f"{prem:.0f}% premium (modest)")
        elif prem <= -5:
            s -= 5; reasons.append(f"{prem:.0f}% (discount)")
    if gov:
        s += 6; reasons.append("governance rights")
    if lockup_m:
        s += min(8, lockup_m / 3.0); reasons.append(f"{lockup_m}mo lock-up")
    if side:
        s -= 10; reasons.append("side consideration (premium may be illusory)")
    return round(s, 1), (prem if prem is not None else None), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    from datetime import datetime, timezone, timedelta
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Premium-injection sweep {start}..{end}", file=sys.stderr)

    yf = {}
    if (ROOT / "yfinance_quick.json").exists():
        yf = json.loads((ROOT / "yfinance_quick.json").read_text())

    # collect candidate filings
    cand = {}
    for phrase in EVENT_PHRASES:
        for h in efts(phrase, start, end):
            tk = (h["ticker"] or "").upper()
            if not _valid(tk):
                continue
            cand.setdefault((tk, h["accession"]), h)
        time.sleep(args.sleep)
    print(f"  {len(cand)} candidate issuance filings; scanning for premiums",
          file=sys.stderr)

    out = {}
    for (tk, acc), h in cand.items():
        txt = fetch_text(h["cik"], acc)
        time.sleep(args.sleep)
        if not txt or not PREMIUM_RX.search(txt):
            continue                      # only the rare explicit-premium class
        m = PREMIUM_PCT_RX.search(txt)
        premium_pct = None
        if m:
            premium_pct = float(m.group(1) or m.group(2))
        mp = PRICE_PER_SHARE_RX.search(txt)
        sub_price = float(mp.group(1)) if mp else None
        gov = bool(GOV_RX.search(txt))
        lm = LOCKUP_RX.search(txt)
        lockup_m = None
        if lm:
            n = int(lm.group(1)); unit = lm.group(2).lower()
            lockup_m = n * (12 if "year" in unit else (1 / 30 if "day" in unit else 1))
        side = bool(SIDE_RX.search(txt))
        yprice = (yf.get(tk, {}) or {}).get("price")
        sc, prem, reasons = score(premium_pct, gov, lockup_m, side, yprice, sub_price)
        if sc <= 0:
            continue
        prev = out.get(tk)
        if not prev or sc > prev["score"]:
            out[tk] = {"ticker": tk, "score": sc, "premium_pct": prem,
                       "subscription_price": sub_price, "governance": gov,
                       "lockup_months": lockup_m, "side_consideration": side,
                       "date": h["date"], "accession": acc, "reasons": reasons}
    io_util.write_json(OUT, out)
    print(f"wrote {OUT} ({len(out)} premium injections)")
    for tk, v in sorted(out.items(), key=lambda x: -x[1]["score"])[:20]:
        print(f"  {tk:<7}{v['score']:>6.1f}  {'; '.join(v['reasons'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
