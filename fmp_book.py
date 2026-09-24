"""Validated book value / P/B from FMP bulk balance sheets.

FMP's `priceToBookRatioTTM` is unreliable in exactly the tail we screen
(deep below book): reverse splits leave a stale share count in book value per
share (KALA: 0.005x when the true figure is ~1.2x), and the odd filing is
scaled x1000 (PRVA Q2-26 equity $782bn vs $753m the quarter before). This
module rebuilds P/B as current market cap / latest equity, straight from the
bulk quarterly balance sheets, with two guards:

  * scale check -- if latest equity AND total assets jump or collapse >20x
    versus the prior quarter, the latest statement is rejected for the prior;
  * staleness -- statements older than ~15 months are ignored;
  * plausibility -- P/B < 0.10 is returned as None ('implausible'): in FMP
    that is nearly always a scaling error or a stale share count in the
    quote's market cap, not a real 90% discount to book.

Currency: when the statement's reportedCurrency differs from the quote
currency, market cap is converted at spot FX (FMP batch forex quotes) --
`pb_src='calc_fx'`. The ratio feed is used only when no statement exists.
Market-cap check: quote mcap vs price x latest diluted shares; a >2.5x gap
means a stale share count and returns None ('mcap_suspect').

API: load() -> {symbol: balance-sheet dict (latest good quarter)}
     pb(symbol, mcap, quote_ccy, ratio_pb, sheets) -> (p_b | None, src)
"""

from __future__ import annotations

from datetime import date, datetime

import fmp_client as fmp

_CACHE: dict | None = None
MIN_PLAUSIBLE = 0.10


def _quarters(n=5):
    """Most recent n (year, 'Qk') pairs, newest first, ending last quarter."""
    t = date.today()
    y, q = t.year, (t.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append((y, f"Q{q}"))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _consistent(r) -> bool:
    """A statement whose parts exceed its whole has a field-level scale error
    (INR Q2-26: cash $160bn inside $1.5bn of total assets)."""
    ta = _f(r.get("totalAssets"))
    if not ta or ta <= 0:
        return False
    for k in ("cashAndShortTermInvestments", "totalCurrentAssets"):
        v = _f(r.get(k))
        if v is not None and v > 1.02 * ta:
            return False
    eq = _f(r.get("totalStockholdersEquity"))
    return eq is None or abs(eq) <= 1.5 * ta


_FX: dict | None = None


def fx(src: str, dst: str):
    """Spot FX multiplier src->dst from FMP batch forex quotes (via USD if needed)."""
    global _FX
    if not src or not dst or src == dst:
        return 1.0
    if _FX is None:
        try:
            _FX = {r["symbol"]: _f(r.get("price")) for r in fmp.get_json("batch-forex-quotes") or []}
        except RuntimeError:
            _FX = {}
    def pair(a, b):
        if a == b:
            return 1.0
        v = _FX.get(a + b)
        if v:
            return v
        v = _FX.get(b + a)
        return (1.0 / v) if v else None
    d = pair(src, dst)
    if d:
        return d
    a, b = pair(src, "USD"), pair("USD", dst)
    return a * b if a and b else None


_SH: dict | None = None


def latest_shares() -> dict:
    """{symbol: latest diluted weighted shares} from cached income-statement bulks."""
    global _SH
    if _SH is not None:
        return _SH
    import csv as _csv, glob as _glob
    from pathlib import Path as _P
    best = {}
    for fn in _glob.glob(str(_P(fmp.CACHE) / "isbulk_*")):
        for r in _csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            v = _f(r.get("weightedAverageShsOutDil")) or _f(r.get("weightedAverageShsOut"))
            if v and r.get("date") and (r["symbol"] not in best or r["date"] > best[r["symbol"]][0]):
                best[r["symbol"]] = (r["date"], v)
    _SH = {k: v for k, (_, v) in best.items()}
    return _SH


def load() -> dict:
    """{symbol: latest sane quarterly balance sheet}; also annotates
    `_prior_equity`. Cached per process (bulk files cached 20h on disk)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    hist: dict[str, list] = {}
    for y, q in _quarters():
        try:
            rows = fmp.get_bulk_csv("balance-sheet-statement-bulk",
                                    f"bsbulk_{y}_{q}", max_age_hours=72,
                                    year=y, period=q)
        except RuntimeError:
            continue
        for r in rows:
            hist.setdefault(r["symbol"], []).append(r)
    cutoff = date.today().toordinal() - 460
    out = {}
    for s, lst in hist.items():
        lst = sorted({r["date"]: r for r in lst if r.get("date")}.values(),
                     key=lambda r: r["date"], reverse=True)
        lst = [r for r in lst
               if datetime.strptime(r["date"][:10], "%Y-%m-%d").toordinal() >= cutoff
               and _consistent(r)]
        if not lst:
            continue
        cur = lst[0]
        if len(lst) > 1:
            e0, e1 = _f(cur.get("totalStockholdersEquity")), _f(lst[1].get("totalStockholdersEquity"))
            a0, a1 = _f(cur.get("totalAssets")), _f(lst[1].get("totalAssets"))
            if e0 and e1 and a0 and a1 and e1 > 0 and a1 > 0:
                if (e0 / e1 > 20 and a0 / a1 > 20) or (e0 / e1 < 0.05 and a0 / a1 < 0.05):
                    cur = lst[1]                       # scale error in latest filing
            cur = dict(cur)
            cur["_prior_equity"] = lst[1].get("totalStockholdersEquity")
        out[s] = cur
    _CACHE = out
    return out


_FCF: dict | None = None


def ttm_fcf() -> dict:
    """{symbol: trailing-4-quarter free cash flow} from the bulk cash-flow
    statements (statement currency). Symbols with < 4 recent quarters are
    annualised from what exists (>= 2 quarters)."""
    global _FCF
    if _FCF is not None:
        return _FCF
    by: dict[str, dict] = {}
    for y, q in _quarters():
        try:
            rows = fmp.get_bulk_csv("cash-flow-statement-bulk", f"cfbulk_{y}_{q}",
                                    max_age_hours=72, year=y, period=q)
        except RuntimeError:
            continue
        for r in rows:
            v = _f(r.get("freeCashFlow"))
            if v is not None and r.get("date"):
                by.setdefault(r["symbol"], {})[r["date"]] = v
    out = {}
    for s, d in by.items():
        vals = [d[k] for k in sorted(d, reverse=True)[:4]]
        if len(vals) >= 2:
            out[s] = sum(vals) * 4.0 / len(vals)
    _FCF = out
    return out


def pb(symbol, mcap, quote_ccy, ratio_pb, sheets, price=None, is_adr=False):
    """Validated P/B. Returns (value or None, source tag).
    calc    -- mcap / latest equity, same currency
    calc_fx -- mcap converted to the statement currency at spot FX
    ratio   -- FMP ratio feed (only when no usable statement)
    mcap_suspect -- quote mcap disagrees with price x latest shares by >2.5x
                    (stale share count after a big issuance / reverse split)"""
    bs = sheets.get(symbol)
    mcap = _f(mcap)
    rpb = _f(ratio_pb)
    if not mcap or mcap <= 0:
        return None, "no_mcap"
    # LSE / JSE / TASE quote in minor units (GBp, ZAc, ILA) while marketCap is
    # in major units: normalise before comparing or converting
    minor = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ZAC": "ZAR", "ILA": "ILS"}
    px, sh = _f(price), latest_shares().get(symbol)
    if quote_ccy in minor:
        quote_ccy = minor[quote_ccy]
        px = px / 100 if px else px
    if px and sh and not is_adr:
        r = mcap / (px * sh)
        if r < 0.4 or r > 2.5:
            return None, "mcap_suspect"
    if bs:
        eq = _f(bs.get("totalStockholdersEquity"))
        ccy = bs.get("reportedCurrency")
        if eq is not None:
            if eq <= 0:
                return None, "neg_equity"
            conv = fx(quote_ccy, ccy) if (quote_ccy and ccy and quote_ccy != ccy) else 1.0
            if conv:
                v = mcap * conv / eq
                tag = "calc" if conv == 1.0 else "calc_fx"
                # < 0.10x is almost always a x1000 filing or a stale share count
                # in the quote (GNK, KXIN, MOVE) -- never treat it as "cheap".
                return (v, tag) if v >= MIN_PLAUSIBLE else (None, "implausible")
    if rpb is not None and rpb > 0:
        return (rpb, "ratio") if rpb >= MIN_PLAUSIBLE else (None, "implausible")
    return None, "none"
