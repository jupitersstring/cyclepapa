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
import json
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
REGION = {"US": "United States/Canada", "CA": "United States/Canada", "GB": "United Kingdom",
          "JP": "Japan", "KR": "Korea", "HK": "Greater China / HK", "CN": "Greater China / HK",
          "TW": "Greater China / HK", "AU": "SE Asia / Pacific", "NZ": "SE Asia / Pacific",
          "SG": "SE Asia / Pacific", "MY": "SE Asia / Pacific", "ID": "SE Asia / Pacific",
          "TH": "SE Asia / Pacific", "PH": "SE Asia / Pacific", "VN": "SE Asia / Pacific",
          "IN": "India", "BR": "Latin America", "MX": "Latin America", "AR": "Latin America",
          "CL": "Latin America", "CO": "Latin America", "PE": "Latin America",
          **{c: "Continental Europe" for c in ("DE", "FR", "ES", "IT", "NL", "BE", "SE", "NO", "DK",
                                                "FI", "CH", "AT", "PT", "IE", "LU", "PL", "GR")},
          **{c: "MEA / Frontier" for c in ("NG", "EG", "ZA", "AE", "SA", "QA", "KE", "MA", "TR", "IL")}}
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def load_bulk():
    prof, by_cik, by_isin = {}, {}, {}
    for fn in sorted(glob.glob(str(ROOT / "fmp_cache" / "profile-bulk_part*.csv"))):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            s = r["symbol"]
            prof[s] = r
            live = str(r.get("isActivelyTrading")).lower() == "true"
            if r.get("cik"):
                k = str(int(float(r["cik"])))
                # prefer the actively traded line (CIKs keep dead symbols too)
                if k not in by_cik or (live and str(prof[by_cik[k]].get("isActivelyTrading")).lower() != "true"):
                    by_cik[k] = s
            if r.get("isin"):
                if r["isin"] not in by_isin or (live and str(prof[by_isin[r["isin"]]].get("isActivelyTrading")).lower() != "true"):
                    by_isin[r["isin"]] = s
    rat = {r["symbol"]: r for r in fmp.get_bulk_csv("ratios-ttm-bulk")}
    km = {r["symbol"]: r for r in fmp.get_bulk_csv("key-metrics-ttm-bulk")}
    return prof, by_cik, by_isin, rat, km


import unicodedata

_STOPN = {"inc", "corp", "corporation", "company", "co", "ltd", "limited", "holdings", "holding",
          "group", "the", "plc", "sa", "ag", "nv", "se", "spa", "de", "and", "of", "asa", "ab",
          "bhd", "berhad", "tbk", "pt", "class", "series", "ordinary", "shares", "common", "stock",
          "nl", "llc", "lp", "trust", "international", "global"}


def _fold(x):
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"['’`]", "", x)


def same_company(a, b):
    """Loose name match: shared distinctive token, or a shared 5-char stem
    (Suedzucker/Südzucker, HeidelbergMaterials/HeidelbergCement, Moodys/Moody's)."""
    ta = {t for t in re.findall(r"[a-z0-9]+", _fold(a)) if t not in _STOPN and len(t) > 1}
    tb = {t for t in re.findall(r"[a-z0-9]+", _fold(b)) if t not in _STOPN and len(t) > 1}
    if ta & tb:
        return True
    ca, cb = re.sub(r"[^a-z0-9]", "", _fold(a)), re.sub(r"[^a-z0-9]", "", _fold(b))
    return bool(ca and cb) and (ca[:5] == cb[:5] or ca in cb or cb in ca)


# a bare engine ticker is ambiguous (ASX 'CMG' = Critical Minerals Group, not
# Chipotle): try these venues, keep the first whose company name matches
BARE_TRY = ["", ".AX", ".L", ".TO", ".V", ".NZ", ".SI", ".JO", ".HK", ".KL"]


def to_fmp(ticker, prof, by_cik, by_isin, name=None):
    t = ticker.strip()
    if ":" not in t:
        if t.isdigit():                              # bare Asian codes: 4-digit JP/HK, 6-digit KR/CN
            cands = [t + ".T", t.zfill(4) + ".HK"] if len(t) <= 4 else \
                    [t + ".KS", t + ".KQ", t + ".SS", t + ".SZ"]
            for c in cands:
                if c in prof and (not name or same_company(name, prof[c].get("companyName"))):
                    return c
            return None
        for suf in BARE_TRY:
            c = t + suf
            if c in prof and (not name or same_company(name, prof[c].get("companyName"))):
                return c
        return None
    ex, code = t.split(":", 1)
    ex, code = ex.upper(), code.strip()
    if code in prof and "." in code:                   # already a venue-suffixed symbol (00232.HK)
        return code
    if code.upper().endswith(".HK") and code[:-3].isdigit():
        c = code[:-3].lstrip("0").zfill(4) + ".HK"
        if c in prof:
            return c
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


def usd_mcap(r):
    """Market cap in USD (quotes are in local currency: HKD, JPY, GBP...)."""
    m = f(r.get("mcap"), 0) or 0
    ccy = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(r.get("currency"), r.get("currency"))
    if not m or not ccy or ccy == "USD":
        return m
    rate = fmp_book.fx(ccy, "USD")
    return m * rate if rate else m


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

    # rows that are not investable companies: OFAC / Treasury notice titles and
    # press-release headlines ingested as names, funds and trusts
    junk = re.compile(r"designation|issuance of|sanction|counter (?:terror|narcotic)|non-proliferation|"
                      r"general license|related (?:designations|sanctions)|\bannounces?\b|restructurati?on de|"
                      r"réalisation|\betf\b|\bfund\b|shared trust|lending (?:&|and) leasing|asset-based", re.I)
    dropped = [r for r in rows if r["source"] != "REAL" and (junk.search(r["name"] or "")
               or re.search(r"(?:-WT|-WS|\.WS|\.U)$", r["ticker"]))]   # warrants / units too
    rows = [r for r in rows if r not in dropped]
    upgraded = mapped = inactive = 0
    for r in rows:
        sym = to_fmp(r["ticker"], prof, by_cik, by_isin, r["name"])
        for k in ("fmp_symbol", "price", "currency", "mcap", "p_b", "pb_src", "floor_frac", "flag"):
            r.setdefault(k, "")
        if not sym:
            continue
        mapped += 1
        p = prof[sym]
        reg = REGION.get(p.get("country") or "")
        if reg and r["region"] in ("Unspecified", "", None) or (reg and r["region"] != reg and r["source"] != "REAL"):
            r["region"] = reg                           # engine regions are often wrong/blank
        # bankrupt / delisted equity (Ch.11 'Q' tickers, not actively trading):
        # the ordinary shares are usually cancelled -- the PROXY formula's ~35%
        # bear case is not credible
        if r["source"] != "REAL" and str(p.get("isActivelyTrading")).lower() != "true" \
                and not (len(sym) == 5 and sym.endswith("Q")):
            r["flag"] = "NOT TRADING in FMP (taken private / delisted / symbol change?) -- verify"
            continue
        if r["source"] != "REAL" and len(sym) == 5 and sym.endswith("Q"):
            r.update({"source": "FMP", "bear_loss": 0.95, "base_r": 0.3, "bull_r": round(f(r["bull_r"], 2.0), 2),
                      "ev": round(0.30 * 0.05 + 0.45 * 0.3 + 0.25 * f(r["bull_r"], 2.0), 2),
                      "flag": "INACTIVE/BANKRUPT: equity likely cancelled"})
            r["rr"] = round((f(r["ev"]) - 1) / 0.95, 1)
            r["skew"] = round((f(r["bull_r"]) - 1) / 0.95, 2)
            r["downside_prot"] = 0.05
            inactive += 1
            continue
        pb, pb_src = fmp_book.pb(sym, p.get("marketCap"), p.get("currency"),
                                 (rat.get(sym) or {}).get("priceToBookRatioTTM"), sheets,
                                 p.get("price"), str(p.get("isAdr")).lower() == "true")
        eve = f((km.get(sym) or {}).get("evToEBITDATTM"))
        r.update({"fmp_symbol": sym, "price": p.get("price"), "currency": p.get("currency"),
                  "mcap": p.get("marketCap"), "p_b": round(pb, 3) if pb is not None else "",
                  "pb_src": pb_src})
        if r["source"] != "PROXY":
            continue                                   # never override REAL rows
        bs = sheets.get(sym) or {}
        eq = f(bs.get("totalStockholdersEquity"))
        if eq is None or pb_src in ("none", "no_mcap", "implausible", "mcap_suspect"):
            continue                                   # FMP can't value it: stays PROXY
        if (f(p.get("marketCap"), 0) < 5e6
                or str(p.get("isActivelyTrading")).lower() != "true"):
            continue                                   # stale / sub-scale quote
        if pb_src == "ratio":
            continue                                   # no usable statement: stays PROXY
        fin = (p.get("sector") or "") == "Financial Services"
        burn = max(0.0, -(fcf.get(sym) or 0.0))       # one year of cash burn
        cash = f(bs.get("cashAndShortTermInvestments"), 0.0)
        debt = f(bs.get("totalDebt"), 0.0)
        ca = f(bs.get("totalCurrentAssets"), 0.0)
        tl = f(bs.get("totalLiabilities"), 0.0)
        gi = f(bs.get("goodwillAndIntangibleAssets"), 0.0)
        if eq > 0 and pb and pb > 0:
            to_mcap = 1.0 / (eq * pb)                  # 1/mcap in statement currency
            if fin:                                    # deposits aren't debt: book only (soft)
                floor, ncf = min(max(TB_HAIRCUT * (eq - gi), 0.0) * to_mcap, 0.60), None
            else:
                # a burning cash shell is only worth its cash AFTER a year of burn
                # book is only a floor if creditors don't own it first
                ta = f(bs.get("totalAssets"), 0.0)
                lev = debt / ta if ta > 0 else 1.0
                tbh = TB_HAIRCUT if lev < 0.4 else 0.20 if lev < 0.6 else 0.0
                prop = (p.get("sector") or "") == "Real Estate"
                hard = max(cash - debt - burn,
                           0.0 if prop else NCAV_HAIRCUT * (ca - tl) - burn, 0.0) * to_mcap
                # book is a SOFT floor: a stock at 0.2x book is the market saying the
                # book is impaired -- it can support at most 60% of today's price;
                # only cash / working capital can take the bear case below 40%
                soft = min(tbh * (eq - gi) * to_mcap, 0.60)
                # equity STUB: debt swamps the equity and interest isn't covered --
                # the book belongs to creditors, so it is no floor at all
                icov = f((rat.get(sym) or {}).get("interestCoverageRatioTTM"))
                if (debt - cash) * to_mcap > 2.0 and (icov is None or icov < 1.0):
                    soft = 0.0
                    r["flag"] = r.get("flag") or "equity stub: net debt > 2x mcap, interest not covered"
                floor = max(hard, soft)
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

    # an untradeable / bankrupt / tickerless row must not lead any lens
    # (the engine's "Signal conviction" lens ranks on raw conviction)
    for r in rows:
        if r["source"] != "REAL" and ((r.get("flag") or "").startswith(("NOT TRADING", "INACTIVE"))
                                      or r["ticker"].strip() in ("—", "-", "")):
            r["conviction"] = 0
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
        # investability: a name FMP can't find trading is not a position; a
        # sub-$50M micro-cap can't absorb size -- both demoted and flagged
        if r["source"] != "REAL" and r["ticker"].strip() in ("—", "-", ""):
            r["flag"] = "NO LISTED TICKER (debt issuer / unlisted?) -- not tradeable as equity"
        if (r.get("flag") or "").startswith(("NOT TRADING", "NO LISTED")):
            b *= 0.5
        elif r["source"] != "REAL" and 0 < usd_mcap(r) < 5e7:
            b *= 0.85
            r["flag"] = r.get("flag") or "micro-cap < $50M (liquidity)"
        r["composite"] = round(min(b, 1.0), 4)
    rows.sort(key=lambda r: -f(r["composite"], 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    out_fields = fields + [k for k in ("fmp_symbol", "price", "currency", "mcap", "p_b",
                                       "pb_src", "floor_frac", "flag") if k not in fields]
    (Path(args.wt) / "output" / "fmp_overlay_log.json").write_text(json.dumps({
        "dropped_not_companies": [(r["ticker"], r["name"]) for r in dropped],
        "flagged": [(r["ticker"], r["name"], r["flag"]) for r in rows if r.get("flag")]}, indent=1))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"FMP overlay: {mapped}/{len(rows)} rows mapped to FMP symbols; "
          f"{upgraded} PROXY rows upgraded to data-driven FMP rows; {inactive} inactive/bankrupt "
          f"equities marked; {len(dropped)} non-company rows dropped; "
          f"sources now {dict(Counter(r['source'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
