"""FMP universe + quote integration.

Why: the quote store (yfinance_quick.json) is read by 54 modules and feeds
the consensus universe, but yfinance priced only ~46% of the universe and
never carried P/E or EV/EBITDA -- so every price/valuation layer silently
skipped over half the names and part of the valuation layer was dead.

What this does (3 bulk calls + profile parts, cached under fmp_cache/):
  1. profile-bulk      -> price, market cap, 52-week range, sector, industry,
                          beta, volume, CIK, CUSIP, exchange, flags
  2. ratios-ttm-bulk   -> P/B, P/S, P/E, dividend yield, EV multiple
  3. key-metrics-ttm   -> EV/EBITDA, Graham net-net, NCAV, earnings / FCF yield

Outputs:
  * fmp_quotes.json -- the distilled FMP store for every active US-exchange
    AND OTC common stock (OTC kept here for going-dark / NOL / micro-cap
    work, but deliberately NOT merged into the main ranking universe).
  * yfinance_quick.json -- ENRICHED in place (so all 54 consumers benefit):
    FMP fills/refreshes price, mcap, range, sector/industry, P/B, P/S and
    adds P/E + EV/EBITDA; yfinance-only fields (short / inst / insider %)
    are preserved. Adds real US-listed common stocks not yet covered
    (expanding the consensus universe, which is the union of sources).
  * fmp_universe_report.json -- before/after coverage.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import io_util
import fmp_book
import fmp_client as fmp
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
YQ = ROOT / "yfinance_quick.json"
OUT_Q = ROOT / "fmp_quotes.json"
OUT_R = ROOT / "fmp_universe_report.json"

US_EXCH = {"NASDAQ", "NYSE", "AMEX", "NYSE American", "NYSEArca"}
OTC_EXCH = {"OTC", "PNK", "OTC Markets"}
_SYM_OK = re.compile(r"^[A-Z]{1,5}(-[A-C])?$")   # common + class shares only


def _truthy(x):
    return str(x).strip().lower() == "true"


def _range(r):
    try:
        lo, hi = str(r).split("-", 1)
        lo, hi = float(lo), float(hi)
        return (lo, hi) if 0 < lo <= hi else (None, None)
    except (ValueError, AttributeError):
        return (None, None)


def main() -> int:
    # 1) pull bulks (cached).
    prof = {}
    for part in range(0, 12):
        try:
            rows = fmp.get_bulk_csv("profile-bulk", cache_name=f"profile-bulk_part{part}.csv",
                                    part=part)
        except RuntimeError:
            break                                      # 400 past the last part
        if not rows:
            break
        for r in rows:
            prof[r["symbol"]] = r
    ratios = {r["symbol"]: r for r in fmp.get_bulk_csv("ratios-ttm-bulk")}
    km = {r["symbol"]: r for r in fmp.get_bulk_csv("key-metrics-ttm-bulk")}
    sheets = fmp_book.load()                         # validated book value (see fmp_book)
    print(f"FMP: {len(prof)} profiles, {len(ratios)} ratio rows, {len(km)} key-metric rows")

    # 2) distil the FMP store: active US-exchange + OTC common (no ETFs/funds).
    q = {}
    for s, p in prof.items():
        ex = p.get("exchange", "")
        if ex not in US_EXCH and ex not in OTC_EXCH:
            continue
        if not _truthy(p.get("isActivelyTrading")) or _truthy(p.get("isEtf")) \
                or _truthy(p.get("isFund")):
            continue
        if not _SYM_OK.match(s):
            continue
        lo, hi = _range(p.get("range"))
        ra, k = ratios.get(s, {}), km.get(s, {})
        q[s] = {
            "name": p.get("companyName"), "exchange": ex,
            "otc": ex in OTC_EXCH, "is_adr": _truthy(p.get("isAdr")),
            "sector": p.get("sector") or None, "industry": p.get("industry") or None,
            "country": p.get("country") or None,
            "price": fmp.num(p.get("price")), "mcap": fmp.num(p.get("marketCap")),
            "fwk_low": lo, "fwk_high": hi, "beta": fmp.num(p.get("beta")),
            "volume": fmp.num(p.get("volume")), "avg_volume": fmp.num(p.get("averageVolume")),
            "cik": p.get("cik") or None, "cusip": p.get("cusip") or None,
            "ipo_date": p.get("ipoDate") or None,
            # P/B = mcap / latest equity (the TTM ratio feed breaks on reverse
            # splits and x1000 filings); ratio feed only for cross-currency
            **dict(zip(("p_b", "pb_src"), fmp_book.pb(
                s, p.get("marketCap"), p.get("currency"),
                ra.get("priceToBookRatioTTM"), sheets))),
            "p_s": fmp.num(ra.get("priceToSalesRatioTTM")),
            "p_e_trailing": fmp.num(ra.get("priceToEarningsRatioTTM")),
            "div_yield": fmp.num(ra.get("dividendYieldTTM")),
            "ev": fmp.num(k.get("enterpriseValueTTM")),
            "ev_ebitda": fmp.num(k.get("evToEBITDATTM")),
            "graham_net_net": fmp.num(k.get("grahamNetNetTTM")),
            "ncav": fmp.num(k.get("netCurrentAssetValueTTM")),
            "earnings_yield": fmp.num(k.get("earningsYieldTTM")),
            "fcf_yield": fmp.num(k.get("freeCashFlowYieldTTM")),
        }
    io_util.write_json(OUT_Q, q)
    n_us = sum(1 for v in q.values() if not v["otc"])
    print(f"wrote {OUT_Q.name}: {len(q)} active common ({n_us} US-exchange, "
          f"{len(q) - n_us} OTC)")

    # 3) enrich the main quote store (all 54 consumers read it).
    yq = json.loads(YQ.read_text()) if YQ.exists() else {}
    from full_universe_consensus import is_valid_ticker
    universe = {r["ticker"] for r in csv.DictReader(open(ROOT / "full_universe_consensus.csv"))} \
        if (ROOT / "full_universe_consensus.csv").exists() else set()

    def priced(d):
        return {t for t, v in d.items() if v.get("price") and v.get("mcap")}
    before_priced_univ = len(priced(yq) & universe)
    before_pe = sum(1 for t in universe if (yq.get(t) or {}).get("p_e_trailing"))

    targets = set(yq) | universe
    added = 0
    for s, v in q.items():                            # expansion: US-listed only
        if v["otc"] or v["is_adr"] or s in targets:
            continue
        if not v["mcap"] or not is_valid_ticker(s):
            continue
        if is_excluded(s, v.get("name"))[0]:
            continue
        targets.add(s); added += 1

    FILL = ("price", "mcap", "fwk_low", "fwk_high", "sector", "industry",
            "p_b", "p_s", "p_e_trailing", "ev_ebitda")
    for t in targets:
        v = q.get(t)
        if not v:
            continue
        rec = yq.setdefault(t, {})
        new = not rec
        if not rec.get("name") and v.get("name"):
            rec["name"] = v["name"]
        for f in FILL:
            if v.get(f) is not None:
                rec[f] = v[f]                         # FMP is fresher / uniform
        if v.get("pb_src") in ("neg_equity", "implausible", "no_mcap"):
            rec["p_b"] = None                         # no/unreliable book: never "below book"
        rec["pb_src"] = v.get("pb_src")
        for f in ("beta", "cik", "cusip", "exchange", "graham_net_net", "ncav",
                  "earnings_yield", "fcf_yield", "avg_volume"):
            if v.get(f) is not None:
                rec[f] = v[f]
        rec["_src"] = "fmp" if new else "fmp+yf"
    io_util.write_json(YQ, yq)

    after_priced_univ = len(priced(yq) & universe)
    after_pe = sum(1 for t in universe if (yq.get(t) or {}).get("p_e_trailing"))
    rep = {
        "universe_size": len(universe),
        "universe_priced_before": before_priced_univ,
        "universe_priced_after": after_priced_univ,
        "universe_pe_before": before_pe, "universe_pe_after": after_pe,
        "quote_store_size": len(yq),
        "us_listed_added_to_universe": added,
        "fmp_store_us": n_us, "fmp_store_otc": len(q) - n_us,
    }
    io_util.write_json(OUT_R, rep)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
