"""FMP overlay for the risk-reward engine (branch claude/risk-reward-crossfeed).

That engine ranks ~1,460 global recapitalisation / capital-structure names,
but ~98% are PROXY rows: bear/bull come from a formula on a qualitative
screener score, with no market data at all. This overlay upgrades every
PROXY row FMP can price to a data-driven FMP row, WITHOUT touching the
hand-verified REAL rows:

  * floor  = max(net cash, 2/3 x net current assets, 0.35 x tangible book),
    cash legs net of one year of free-cash-flow burn, book leg cut to 0.20x /
    0x when debt is 40-60% / >60% of assets (creditors own that book), from the
    latest validated FMP bulk balance sheet (fmp_book; banks: book only), expressed as a fraction of market cap via
    floor/book x 1/(P/B) -- the ratio is taken inside one statement, so no FX
    conversion is needed for yen / euro / won reporters.
  * bear_loss = clamp(1 - floor, 0.10, 0.90)       (negative equity -> 0.90)
  * bull      = average of the engine's thesis bull and a re-rate to book
                (1/(P/B), clamped 1.3-5.0x)
  * base / EV / RR / skew / downside_prot recomputed with the ENGINE'S OWN
    formulas; the valuation lens (net cash >= 60% of mcap, EV/EBITDA, P/B)
    is filled from FMP for rows that had none; the percentile composite is
    re-ranked exactly as the engine does (rr normalised within source, REAL
    premium unchanged).

Adds columns: fmp_symbol, price, currency, mcap, p_b, floor_frac.
Usage: python3 rr_fmp_overlay.py --wt <risk-reward worktree>
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
from pathlib import Path

import fmp_book
import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
SUF = {"TSE": [".T"], "LSE": [".L"], "XETR": [".DE"], "EPA": [".PA"],
       "BME": [".MC"], "BIT": [".MI"], "B3": [".SA"], "JSE": [".JO"],
       "TSX": [".TO"], "TSXV": [".V"], "TADAWUL": [".SR"], "VIE": [".VI"],
       "ST": [".ST"], "STO": [".ST"], "EGX": [".CA"], "HOSE": [".VN"],
       "KLSE": [".KL"], "PSE": [".PS"], "NZX": [".NZ"], "QSE": [".QA"],
       "SIX": [".SW"], "SWX": [".SW"], "BCBA": [".BA"], "AMS": [".AS"],
       "EURONEXT": [".PA", ".AS", ".BR", ".LS"], "KRX": [".KS", ".KQ"],
       "HKEX": [".HK"], "HK": [".HK"], "CSE": [".CN"], "THB": [".BK"],
       "DFM": [".AE"], "ADX": [".AE"], "NGX": [".LG"]}
NCAV_HAIRCUT, TB_HAIRCUT = 0.67, 0.35    # Graham 2/3 NCAV; liquidation value of book
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def load_bulk():
    prof, by_cik, by_isin = {}, {}, {}
    for fn in sorted(glob.glob(str(ROOT / "fmp_cache" / "profile-bulk_part*.csv"))):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            s = r["symbol"]
            prof[s] = r
            if r.get("cik"):
                by_cik.setdefault(str(int(float(r["cik"]))), s)
            if r.get("isin"):
                by_isin.setdefault(r["isin"], s)
    rat = {r["symbol"]: r for r in fmp.get_bulk_csv("ratios-ttm-bulk")}
    km = {r["symbol"]: r for r in fmp.get_bulk_csv("key-metrics-ttm-bulk")}
    return prof, by_cik, by_isin, rat, km


def to_fmp(ticker, prof, by_cik, by_isin):
    t = ticker.strip()
    if ":" not in t:
        return t if t in prof else None
    ex, code = t.split(":", 1)
    ex, code = ex.upper(), code.strip()
    if ex == "CIK":
        return by_cik.get(str(int(code))) if code.isdigit() else None
    if _ISIN.match(code):
        return by_isin.get(code)
    if ex in ("NYSE", "NASDAQ", "NYSE/TSX", "NYSEAMERICAN", "AMEX"):
        return code if code in prof else None
    cands = []
    for suf in SUF.get(ex, []):
        c = code.zfill(4) if suf == ".HK" and code.isdigit() else code
        cands.append(c + suf)
    for c in cands:
        if c in prof:
            return c
    return None


def valuation_lens(net_cash_frac, ev_ebitda, pb):
    """The engine's _valuation_lens rules, fed with FMP facts."""
    sig, notes = [], []
    if net_cash_frac is not None and net_cash_frac >= 0.6:
        sig.append(1.0); notes.append("net cash ≥60% of mkt cap")
    if ev_ebitda is not None and 0 < ev_ebitda <= 4:
        sig.append(0.9); notes.append(f"EV/EBITDA {ev_ebitda:.1f}×")
    elif ev_ebitda is not None and 0 < ev_ebitda <= 7:
        sig.append(0.6); notes.append(f"EV/EBITDA {ev_ebitda:.1f}×")
    if pb is not None and 0 < pb <= 0.7:
        sig.append(0.85); notes.append(f"P/B {pb:.2f}×")
    elif pb is not None and 0 < pb <= 1.0:
        sig.append(0.5); notes.append(f"P/B {pb:.2f}×")
    if not sig:
        return None, ""
    return round(min(1.0, max(sig) * 0.7 + 0.3 * (len(sig) >= 2)), 2), "; ".join(notes[:3]) + " (FMP)"


def pct(vals):
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    p = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            p[order[k]] = ((i + j) / 2.0) / max(1, n - 1)
        i = j + 1
    return p


def f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", required=True)
    args = ap.parse_args()
    path = Path(args.wt) / "output" / "universe_risk_reward.csv"
    rows = list(csv.DictReader(open(path)))
    fields = list(rows[0].keys())
    prof, by_cik, by_isin, rat, km = load_bulk()
    sheets = fmp_book.load()
    fcf = fmp_book.ttm_fcf()

    upgraded = mapped = 0
    for r in rows:
        sym = to_fmp(r["ticker"], prof, by_cik, by_isin)
        for k in ("fmp_symbol", "price", "currency", "mcap", "p_b", "pb_src", "floor_frac"):
            r.setdefault(k, "")
        if not sym:
            continue
        mapped += 1
        p = prof[sym]
        pb, pb_src = fmp_book.pb(sym, p.get("marketCap"), p.get("currency"),
                                 (rat.get(sym) or {}).get("priceToBookRatioTTM"), sheets)
        eve = f((km.get(sym) or {}).get("evToEBITDATTM"))
        r.update({"fmp_symbol": sym, "price": p.get("price"), "currency": p.get("currency"),
                  "mcap": p.get("marketCap"), "p_b": round(pb, 3) if pb is not None else "",
                  "pb_src": pb_src})
        if r["source"] != "PROXY":
            continue                                   # never override REAL rows
        bs = sheets.get(sym) or {}
        eq = f(bs.get("totalStockholdersEquity"))
        if eq is None or pb_src in ("none", "no_mcap", "implausible"):
            continue                                   # FMP can't value it: stays PROXY
        if (f(p.get("marketCap"), 0) < 5e6
                or str(p.get("isActivelyTrading")).lower() != "true"):
            continue                                   # stale / sub-scale quote
        if pb_src == "ratio" and pb < 0.10:
            continue                                   # ratio-feed tail is unreliable
        fin = (p.get("sector") or "") == "Financial Services"
        burn = max(0.0, -(fcf.get(sym) or 0.0))       # one year of cash burn
        cash = f(bs.get("cashAndShortTermInvestments"), 0.0)
        debt = f(bs.get("totalDebt"), 0.0)
        ca = f(bs.get("totalCurrentAssets"), 0.0)
        tl = f(bs.get("totalLiabilities"), 0.0)
        gi = f(bs.get("goodwillAndIntangibleAssets"), 0.0)
        if eq > 0 and pb and pb > 0:
            to_mcap = 1.0 / (eq * pb)                  # 1/mcap in statement currency
            if fin:                                    # deposits aren't debt: book only
                floor, ncf = max(TB_HAIRCUT * (eq - gi), 0.0) * to_mcap, None
            else:
                # a burning cash shell is only worth its cash AFTER a year of burn
                # book is only a floor if creditors don't own it first
                ta = f(bs.get("totalAssets"), 0.0)
                lev = debt / ta if ta > 0 else 1.0
                tbh = TB_HAIRCUT if lev < 0.4 else 0.20 if lev < 0.6 else 0.0
                floor = max(cash - debt - burn, NCAV_HAIRCUT * (ca - tl) - burn,
                            tbh * (eq - gi), 0.0) * to_mcap
                ncf = (cash - debt - burn) * to_mcap
        else:
            floor, ncf = 0.0, None                     # negative equity: option-like stub
        floor = min(floor, 1.0)
        bear = min(0.90, max(0.10, 1.0 - floor))
        bull_thesis = f(r["bull_r"], 2.0)
        bull_data = min(5.0, max(1.3, 1.0 / pb)) if pb else bull_thesis
        bull = 0.5 * bull_thesis + 0.5 * bull_data
        base = 1.0 + 0.5 * (bull - 1.0) + 0.5 * (1.0 - bear)
        ev = 0.30 * (1.0 - bear) + 0.45 * base + 0.25 * bull
        r.update({"source": "FMP", "bear_loss": round(bear, 3), "bull_r": round(bull, 2),
                  "base_r": round(base, 2), "ev": round(ev, 2),
                  "rr": round((ev - 1.0) / bear, 1),
                  "skew": round((bull - 1.0) / bear, 2),
                  "downside_prot": round(1.0 - bear, 3), "floor_frac": round(floor, 3)})
        if not r.get("val_score"):
            vs, note = valuation_lens(ncf, eve, pb)
            if vs is not None:
                r["val_score"], r["val_note"] = vs, note
        upgraded += 1

    # re-rank exactly as the engine does
    rr_p = [0.0] * len(rows)
    for src in {r["source"] for r in rows}:
        idx = [i for i, r in enumerate(rows) if r["source"] == src]
        sub = pct([f(rows[i]["rr"], 0) for i in idx])
        for k, i in enumerate(idx):
            rr_p[i] = sub[k]
    sk = pct([f(r["skew"], 0) for r in rows])
    dp = pct([f(r["downside_prot"], 0) for r in rows])
    cv = pct([f(r["conviction"], 0) for r in rows])
    for i, r in enumerate(rows):
        b = 0.40 * rr_p[i] + 0.25 * sk[i] + 0.20 * dp[i] + 0.15 * cv[i]
        vs = f(r.get("val_score"))
        if vs is not None:
            b = 0.85 * b + 0.15 * vs
        if r["source"] == "REAL":
            b += 0.12
        r["composite"] = round(min(b, 1.0), 4)
    rows.sort(key=lambda r: -f(r["composite"], 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    out_fields = fields + [k for k in ("fmp_symbol", "price", "currency", "mcap", "p_b",
                                       "pb_src", "floor_frac") if k not in fields]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"FMP overlay: {mapped}/{len(rows)} rows mapped to FMP symbols; "
          f"{upgraded} PROXY rows upgraded to data-driven FMP rows; "
          f"sources now {dict(Counter(r['source'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
