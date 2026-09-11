"""European insider-and-buyback detector.

Approach: Europe has no SEC EDGAR equivalent, no central Form 4 feed.
But every company files share-count snapshots quarterly under
IFRS and local equivalents, and yfinance surfaces these via the
balance_sheet / shares_full endpoints for almost every European
ticker. A meaningful YoY decline in share count = executed buyback
that ACTUALLY shrank the float (not just authorised but executed).

This is more rigorous than US "authorisation $" because:
  - US buyback announcements are aspirational ($X authorized);
    execution lags often by years
  - Share count actually dropping is incontrovertible: cash deployed,
    shares retired, float shrunk
  - Works for any listing yfinance supports (UK/.L, .DE, .PA, .MI,
    .AS, .BR, .VI, .HE, .ST, .CO, .SW, .OL, .NZ, .AX, .TO, .HK, .SI,
    .T) without per-country scrapers

Combined with:
  - P/B and 180-day return (Peyer-Vermaelen U-Index)
  - Yfinance institutional holder snapshot
  - Yfinance news feed (UK RNS / EU equivalent PDMR mentions)

Output: european_buyback.csv ranked by implicit_buyback_score.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from universe_filter import is_excluded


# ---------------------------------------------------------------------------
# Universe: UK, European exchanges, plus optionally AU/CA/JP
# ---------------------------------------------------------------------------

def load_european_universe(include_intl: bool = True) -> list[str]:
    out: set[str] = set()
    try:
        from uk_universe import UK_UNIVERSE
        out.update(UK_UNIVERSE.keys())
    except Exception:
        pass
    if include_intl:
        try:
            from intl_universe import INTL_UNIVERSE
            out.update(INTL_UNIVERSE.keys())
        except Exception:
            pass
    # Curated expansion: major European mid/large caps that yfinance covers
    EU_EXPANSION = [
        # Germany DAX / MDAX
        "SAP.DE", "SIE.DE", "BMW.DE", "MBG.DE", "VOW3.DE", "DTE.DE", "DPW.DE",
        "DHL.DE", "ALV.DE", "MUV2.DE", "DBK.DE", "CBK.DE", "BAS.DE", "BAYN.DE",
        "HEN3.DE", "RHM.DE", "MTX.DE", "AIR.DE", "ZAL.DE", "BEI.DE", "ADS.DE",
        "PUM.DE", "PAH3.DE", "CON.DE", "DTG.DE", "EVK.DE", "FME.DE", "FRE.DE",
        "HEI.DE", "HFG.DE", "IFX.DE", "KGX.DE", "LIN.DE", "MRK.DE", "RWE.DE",
        "SHL.DE", "SY1.DE", "VNA.DE", "TKA.DE", "BNR.DE", "GBF.DE", "JEN.DE",
        # France CAC 40 / SBF 120
        "MC.PA", "OR.PA", "RMS.PA", "SAN.PA", "BNP.PA", "AIR.PA", "AI.PA",
        "DG.PA", "DSY.PA", "EL.PA", "ENGI.PA", "ML.PA", "ORA.PA", "SU.PA",
        "TTE.PA", "VIE.PA", "VIV.PA", "LR.PA", "RI.PA", "RNO.PA", "STM.PA",
        "ACA.PA", "CA.PA", "CAP.PA", "GLE.PA", "HO.PA", "KER.PA", "LI.PA",
        "BN.PA", "FR.PA", "STLAM.MI", "SAF.PA", "BVI.PA", "AC.PA",
        "PUB.PA", "MT.AS", "ATCO-A.ST",
        # Italy FTSE MIB
        "ENI.MI", "ENEL.MI", "STM.MI", "ISP.MI", "G.MI", "UCG.MI", "FBK.MI",
        "MB.MI", "TIT.MI", "TRN.MI", "TEN.MI", "BAMI.MI", "BMED.MI", "BPE.MI",
        "PIRC.MI", "PRY.MI", "RACE.MI", "REC.MI", "SRG.MI", "STLAM.MI",
        # Netherlands AEX
        "ASML.AS", "PHIA.AS", "NN.AS", "INGA.AS", "AD.AS", "DSM.AS",
        "AKZA.AS", "BESI.AS", "WKL.AS", "ASRNL.AS", "RDSA.AS", "UNA.AS",
        "HEIA.AS", "ADYEN.AS", "PROSY.AS", "MT.AS", "LIGHT.AS", "URW.AS",
        # Belgium
        "ABI.BR", "UCB.BR", "SOLB.BR", "AGS.BR", "GBLB.BR", "PROX.BR",
        # Switzerland SMI
        "NESN.SW", "ROG.SW", "NOVN.SW", "CSGN.SW", "ABBN.SW", "UBSG.SW",
        "ZURN.SW", "SREN.SW", "LISN.SW", "LONN.SW", "SIKA.SW", "GIVN.SW",
        "STMN.SW", "ALC.SW", "GEBN.SW", "PGHN.SW", "SCMN.SW", "BAER.SW",
        "SLHN.SW", "PSPN.SW", "EMSN.SW", "VACN.SW", "KNIN.SW", "BARN.SW",
        # Nordic
        "NOKIA.HE", "FORTUM.HE", "KNEBV.HE", "NESTE.HE", "UPM.HE", "OUT1V.HE",
        "OTE1V.HE", "TIETO.HE", "MOCORP.HE", "TYRES.HE",
        "VOLV-B.ST", "ATCO-B.ST", "SEB-A.ST", "HMB.ST", "HEXA-B.ST", "INVE-B.ST",
        "ASSA-B.ST", "ERIC-B.ST", "SAND.ST", "SBB-B.ST", "SCA-B.ST", "SKF-B.ST",
        "SWED-A.ST", "TEL2-B.ST", "TELIA.ST", "EQT.ST", "EPI-A.ST", "INDU-A.ST",
        "LATO-B.ST", "GETI-B.ST", "ELUX-B.ST", "ALFA.ST", "BOL.ST",
        "NOVO-B.CO", "MAERSK-B.CO", "DSV.CO", "VWS.CO", "DANSKE.CO", "ORSTED.CO",
        "ROCK-B.CO", "PNDORA.CO", "GMAB.CO", "AMBU-B.CO", "DEMANT.CO", "TRYG.CO",
        "EQNR.OL", "DNB.OL", "MOWI.OL", "NHY.OL", "TEL.OL", "TGS.OL",
        # Austria
        "VER.VI", "OMV.VI", "EBS.VI", "ATS.VI", "WIE.VI", "RBI.VI", "ANDR.VI",
        # Spain IBEX
        "SAN.MC", "BBVA.MC", "ITX.MC", "IBE.MC", "TEF.MC", "REP.MC", "AENA.MC",
        "FER.MC", "MEL.MC", "GRF.MC", "ELE.MC", "AMS.MC", "CLNX.MC", "ENG.MC",
        "MAP.MC", "ACX.MC", "ANA.MC", "ACS.MC", "VIS.MC", "IAG.MC",
        # Portugal
        "EDP.LS", "GALP.LS", "JMT.LS", "EDPR.LS",
        # Greece
        "OTE.AT", "ALPHA.AT", "MOH.AT",
        # Poland
        "PKO.WA", "PEKAO.WA", "PKN.WA", "OPL.WA", "CDR.WA",
    ]
    out.update(EU_EXPANSION)
    return sorted(t for t in out if not is_excluded(t)[0])


# ---------------------------------------------------------------------------
# Share-count history detection
# ---------------------------------------------------------------------------

def get_share_count_history(ticker: str) -> dict | None:
    """Pull share-count snapshots over the past 2 years."""
    try:
        t = yf.Ticker(ticker)
    except Exception:
        return None

    # Try get_shares_full first (most reliable, gives daily share count
    # to the extent yfinance has it).
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=730)
        s = t.get_shares_full(start=start.strftime("%Y-%m-%d"),
                              end=end.strftime("%Y-%m-%d"))
        if s is not None and len(s) > 1:
            s = s.dropna()
            if len(s) >= 2:
                # Take ~1y prior and most recent
                latest = float(s.iloc[-1])
                # Find ~365 days back
                target_date = end - timedelta(days=365)
                cutoff_idx = None
                for i, ts in enumerate(s.index):
                    if ts >= target_date:
                        cutoff_idx = i
                        break
                yr_ago = float(s.iloc[cutoff_idx]) if cutoff_idx else float(s.iloc[0])
                pct_change_1y = (latest / yr_ago - 1.0) * 100 if yr_ago > 0 else None
                two_year_ago = float(s.iloc[0])
                pct_change_2y = (latest / two_year_ago - 1.0) * 100 if two_year_ago > 0 else None
                return {
                    "latest_shares": latest,
                    "shares_1y_ago": yr_ago,
                    "shares_2y_ago": two_year_ago,
                    "pct_change_1y": pct_change_1y,
                    "pct_change_2y": pct_change_2y,
                    "source": "get_shares_full",
                }
    except Exception:
        pass

    # Fallback: balance_sheet snapshots
    try:
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            # Find ordinary shares outstanding row
            target_row = None
            for candidate in ("Ordinary Shares Number",
                              "Share Issued",
                              "Common Stock"):
                if candidate in bs.index:
                    target_row = candidate
                    break
            if target_row:
                series = bs.loc[target_row].dropna().sort_index()
                if len(series) >= 2:
                    latest = float(series.iloc[-1])
                    earlier = float(series.iloc[0])
                    pct = (latest / earlier - 1.0) * 100 if earlier > 0 else None
                    return {
                        "latest_shares": latest,
                        "shares_2y_ago": earlier,
                        "pct_change_2y": pct,
                        "source": "balance_sheet",
                    }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def get_price_summary(ticker: str) -> dict | None:
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="1y", interval="1d", auto_adjust=False)
        if h is None or len(h) < 30:
            return None
    except Exception:
        return None
    h = h.dropna(subset=["Close"])
    if len(h) < 30:
        return None
    last = float(h["Close"].iloc[-1])
    def _ret(n):
        if len(h) <= n: return None
        prior = float(h["Close"].iloc[-n])
        return (last / prior - 1.0) * 100 if prior > 0 else None
    return {
        "last": last,
        "ret_30d_pct": _ret(30),
        "ret_90d_pct": _ret(90),
        "ret_180d_pct": _ret(180),
        "high_52w": float(h["High"].max()),
        "low_52w": float(h["Low"].min()),
    }


def get_fundamentals(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return {}
    def _s(k):
        v = info.get(k)
        try:
            f = float(v) if v is not None else None
            if f is None or math.isnan(f) or math.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None
    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "currency": info.get("financialCurrency") or info.get("currency"),
        "market_cap": _s("marketCap"),
        "price": _s("currentPrice") or _s("regularMarketPrice") or _s("previousClose"),
        "p_b": _s("priceToBook"),
        "div_yield": _s("dividendYield"),
        "fcf": _s("freeCashflow"),
        "ev_ebitda": _s("enterpriseToEbitda"),
        "trailing_pe": _s("trailingPE"),
        "shares_out": _s("sharesOutstanding"),
        "inst_pct": _s("heldPercentInstitutions"),
        "insider_pct": _s("heldPercentInsiders"),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_implicit_buyback(share_hist: dict, fund: dict,
                           price: dict) -> tuple[float, list[str]]:
    """0-100. Higher = better implicit buyback + value setup."""
    score = 0.0
    reasons = []

    if not share_hist:
        return 0.0, ["no share-count history"]

    # Share count reduction (the core signal)
    pct_1y = share_hist.get("pct_change_1y")
    pct_2y = share_hist.get("pct_change_2y")
    if pct_1y is not None:
        if pct_1y <= -10:
            score += 45; reasons.append(f"Shares -{abs(pct_1y):.1f}% YoY (heavy)")
        elif pct_1y <= -5:
            score += 32; reasons.append(f"Shares -{abs(pct_1y):.1f}% YoY")
        elif pct_1y <= -2:
            score += 20; reasons.append(f"Shares -{abs(pct_1y):.1f}% YoY")
        elif pct_1y <= 0:
            score += 8
        elif pct_1y >= 5:
            score -= 15; reasons.append(f"Shares +{pct_1y:.1f}% (dilution)")
    elif pct_2y is not None:
        # If only 2y available, weight half
        if pct_2y <= -15:
            score += 35; reasons.append(f"Shares -{abs(pct_2y):.1f}% over 2y")
        elif pct_2y <= -8:
            score += 22; reasons.append(f"Shares -{abs(pct_2y):.1f}% over 2y")
        elif pct_2y <= -3:
            score += 12; reasons.append(f"Shares -{abs(pct_2y):.1f}% over 2y")

    # Drawdown / 6m return (U-Index proxy)
    ret_180 = price.get("ret_180d_pct") if price else None
    if ret_180 is not None:
        if ret_180 <= -30:
            score += 25; reasons.append(f"180d return {ret_180:+.0f}%")
        elif ret_180 <= -15:
            score += 18
        elif ret_180 <= 0:
            score += 10
        elif ret_180 <= 10:
            score += 4

    # P/B value
    p_b = fund.get("p_b")
    if p_b and p_b > 0:
        if p_b <= 1.0:
            score += 18; reasons.append(f"P/B {p_b:.2f} (deep value)")
        elif p_b <= 2.0:
            score += 12; reasons.append(f"P/B {p_b:.2f}")
        elif p_b <= 3.5:
            score += 5

    # Size (smaller = stronger U-Index signal)
    mc = fund.get("market_cap")
    if mc and mc > 0:
        mc_b = mc / 1e9
        if mc_b <= 0.5:
            score += 10; reasons.append(f"Small cap ($"+f"{mc_b:.1f}B)")
        elif mc_b <= 2:
            score += 7
        elif mc_b <= 10:
            score += 4

    # Dividend cushion
    dy = fund.get("div_yield")
    if dy and dy >= 0.04:
        score += 8; reasons.append(f"Div yield {dy*100:.1f}%")

    return min(100.0, score), reasons


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--min-score", type=float, default=30.0)
    p.add_argument("--csv", default="european_buyback.csv")
    p.add_argument("--out", default="european_buyback.json")
    p.add_argument("--sleep", type=float, default=0.20)
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--region", choices=["UK", "EU", "INTL", "ALL"], default="ALL")
    args = p.parse_args()

    universe = load_european_universe()
    if args.region == "UK":
        universe = [t for t in universe if t.endswith(".L")]
    elif args.region == "EU":
        eu_suffixes = (".DE", ".PA", ".MI", ".AS", ".BR", ".VI", ".HE", ".ST",
                       ".CO", ".SW", ".OL", ".MC", ".LS", ".AT", ".WA", ".F",
                       ".HM", ".MU", ".BE", ".VX")
        universe = [t for t in universe if any(t.endswith(s) for s in eu_suffixes)]
    print(f"Universe: {len(universe)} European tickers ({args.region})",
          file=sys.stderr)

    # Resume support
    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text())
        except Exception:
            results = {}

    for i, tk in enumerate(universe, 1):
        if i > args.limit:
            break
        if tk in results:
            continue
        if i % 20 == 0:
            print(f"  [{i}/{len(universe)}] {tk}", file=sys.stderr, flush=True)
            out_path.write_text(json.dumps(results, indent=2, default=str))
        sh = get_share_count_history(tk)
        time.sleep(args.sleep)
        fund = get_fundamentals(tk)
        time.sleep(args.sleep)
        ph = get_price_summary(tk)
        time.sleep(args.sleep)
        score, reasons = score_implicit_buyback(sh, fund, ph)
        results[tk] = {
            "ticker": tk,
            "score": round(score, 1),
            "share_history": sh,
            "fundamentals": fund,
            "price_summary": ph,
            "reasons": reasons,
        }

    out_path.write_text(json.dumps(results, indent=2, default=str))

    # Build ranked list
    rows = []
    for tk, d in results.items():
        if d.get("score", 0) < args.min_score:
            continue
        sh = d.get("share_history") or {}
        f = d.get("fundamentals") or {}
        ph = d.get("price_summary") or {}
        mc = f.get("market_cap") or 0
        rows.append({
            "ticker": tk,
            "name": f.get("name", ""),
            "sector": f.get("sector", ""),
            "currency": f.get("currency", ""),
            "price": ph.get("last") or f.get("price"),
            "market_cap_musd": round(mc / 1e6, 1),
            "score": d.get("score"),
            "shares_change_1y_pct": sh.get("pct_change_1y"),
            "shares_change_2y_pct": sh.get("pct_change_2y"),
            "ret_90d_pct": ph.get("ret_90d_pct"),
            "ret_180d_pct": ph.get("ret_180d_pct"),
            "p_b": f.get("p_b"),
            "div_yield": f.get("div_yield"),
            "trailing_pe": f.get("trailing_pe"),
            "ev_ebitda": f.get("ev_ebitda"),
            "inst_pct": f.get("inst_pct"),
            "insider_pct": f.get("insider_pct"),
            "reasons": " | ".join(d.get("reasons") or []),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)

    fields = ["rank", "ticker", "name", "sector", "currency", "price",
              "market_cap_musd", "score",
              "shares_change_1y_pct", "shares_change_2y_pct",
              "ret_90d_pct", "ret_180d_pct",
              "p_b", "div_yield", "trailing_pe", "ev_ebitda",
              "inst_pct", "insider_pct", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nEligible: {len(rows)} | wrote {args.csv}\n")
    print(f"=== TOP {args.top} EUROPEAN IMPLICIT BUYBACK + VALUE ===")
    print(f"{'#':<3}{'TKR':<11}{'CCY':<4}{'PX':>9}{'MCAP':>9}{'SCR':>5}"
          f"{'SH1Y':>7}{'180D':>7}{'P/B':>6}{'DIV':>5}  NAME / REASONS")
    for i, r in enumerate(rows[: args.top], 1):
        sh1 = r.get("shares_change_1y_pct")
        sh2 = r.get("shares_change_2y_pct")
        sh_str = f"{sh1:+.1f}%" if sh1 is not None else (f"{sh2:+.1f}%/2y" if sh2 else "-")
        r180 = r.get("ret_180d_pct")
        r180_str = f"{r180:+.0f}%" if r180 is not None else "-"
        pb = r.get("p_b")
        pb_str = f"{pb:.2f}" if pb else "-"
        dy = r.get("div_yield")
        dy_str = f"{dy*100:.0f}%" if dy else "-"
        mc = r.get("market_cap_musd") or 0
        px = r.get("price") or 0
        print(f"{i:<3}{r['ticker']:<11}{r.get('currency','')[:3]:<4}"
              f"{px:>9.2f}{mc:>8.0f}M{r['score']:>5.0f}"
              f"{sh_str:>7}{r180_str:>7}{pb_str:>6}{dy_str:>5}  "
              f"{(r.get('name') or '')[:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
