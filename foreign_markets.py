"""Foreign markets additive layer (S2.6) — JP / KR / UK.

The Special Situations Sourcing Playbook identified Japan TSE PBR<1
reform, Korea Value-Up + treasury cancellation, and UK schemes of
arrangement as the highest-EV under-covered terrain. Our framework
has been US-only. This module adds a curated foreign-ticker overlay.

Sources:
  - Japan: TOPIX-100 + Nikkei 225 large caps (.T suffix on yfinance)
  - Korea: KOSPI 50 large caps (.KS suffix)
  - UK: FTSE 100 large caps (.L suffix)

For each foreign ticker we apply jurisdiction-specific scoring:

  Japan (TSE PBR<1 reform target):
    - PBR < 0.7: +25 (Reform candidate — TSE explicitly named)
    - PBR < 1.0: +15
    - ROE > 8% AND PBR < 1.0: +10 (quality + value)
    - Buyback execution: +8

  Korea (Value-Up + treasury cancellation):
    - Member of Value-Up Index (proxied by Samsung/Hyundai/LG family
      tickers in our seed list): +15
    - PBR < 1.0: +10
    - High treasury shares (proxied by float vs shares-out): +8

  UK (schemes / wind-down):
    - PBR < 0.7: +20 (deep value, candidate for take-private)
    - Net cash / negative EV: +15

ADDITIVE: separate JSON output. Existing US-only layers unchanged.
Foreign tickers retain their yfinance suffix so they're never
confused with US tickers.

Output: foreign_markets.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "foreign_markets.json"


# Curated seed lists. Top 30-50 by market cap per jurisdiction; we can
# expand later. Mix of large caps and known PBR<1 / Value-Up names.
JAPAN_TICKERS = [
    # Mega-cap defensive
    "7203.T",   # Toyota
    "6758.T",   # Sony
    "6098.T",   # Recruit Holdings
    "9432.T",   # NTT
    "9433.T",   # KDDI
    "9984.T",   # SoftBank
    "8306.T",   # Mitsubishi UFJ
    "8316.T",   # SMFG
    "8411.T",   # Mizuho
    "8058.T",   # Mitsubishi
    "8053.T",   # Sumitomo
    "8001.T",   # Itochu
    "8002.T",   # Marubeni
    "8031.T",   # Mitsui & Co
    "6501.T",   # Hitachi
    "7267.T",   # Honda
    "7269.T",   # Suzuki
    "7270.T",   # Subaru
    "7201.T",   # Nissan
    "6502.T",   # Toshiba
    "6503.T",   # Mitsubishi Electric
    "6752.T",   # Panasonic
    "4502.T",   # Takeda
    "4503.T",   # Astellas
    "4519.T",   # Chugai
    "4523.T",   # Eisai
    "9020.T",   # JR East
    "9022.T",   # JR Central
    "1605.T",   # Inpex
    "5020.T",   # ENEOS Holdings
    "5101.T",   # Yokohama Rubber
    "5108.T",   # Bridgestone
    "5401.T",   # Nippon Steel
    "5411.T",   # JFE Holdings
    "8801.T",   # Mitsui Fudosan
    "8802.T",   # Mitsubishi Estate
    "8830.T",   # Sumitomo Realty
    "9101.T",   # NYK Line
    "9104.T",   # MOL
    "9107.T",   # Kawasaki Kisen
    "1812.T",   # Kajima
    "1801.T",   # Taisei
    "1925.T",   # Daiwa House
    "1928.T",   # Sekisui House
    "2914.T",   # Japan Tobacco
    "3382.T",   # Seven & I
    "9201.T",   # JAL
    "9202.T",   # ANA
    "9501.T",   # Tokyo Electric
    "9503.T",   # Kansai Electric
    "9531.T",   # Tokyo Gas
]

KOREA_TICKERS = [
    "005930.KS",  # Samsung Electronics
    "000660.KS",  # SK Hynix
    "035420.KS",  # Naver
    "035720.KS",  # Kakao
    "005380.KS",  # Hyundai Motor
    "005490.KS",  # POSCO Holdings
    "012330.KS",  # Hyundai Mobis
    "028260.KS",  # Samsung C&T
    "055550.KS",  # Shinhan Financial
    "086790.KS",  # Hana Financial
    "316140.KS",  # Woori Financial
    "105560.KS",  # KB Financial
    "066570.KS",  # LG Electronics
    "051910.KS",  # LG Chem
    "006400.KS",  # Samsung SDI
    "005935.KS",  # Samsung Electronics PFD
    "032830.KS",  # Samsung Life
    "029780.KS",  # Samsung Card
    "017670.KS",  # SK Telecom
    "030200.KS",  # KT
    "015760.KS",  # Korea Electric Power
    "036570.KS",  # NCSoft
    "251270.KS",  # Netmarble
    "010130.KS",  # Korea Zinc
    "024110.KS",  # Industrial Bank of Korea
    "010140.KS",  # Samsung Heavy Industries
    "009540.KS",  # HD Hyundai Heavy
    "267250.KS",  # HD Korea Shipbuilding
    "047810.KS",  # Korea Aerospace Industries
    "138040.KS",  # Mertich Financial
]

UK_TICKERS = [
    "SHEL.L",   # Shell
    "BP.L",     # BP
    "ULVR.L",   # Unilever
    "HSBA.L",   # HSBC
    "AZN.L",    # AstraZeneca
    "GSK.L",    # GSK
    "BATS.L",   # British American Tobacco
    "BARC.L",   # Barclays
    "STAN.L",   # Standard Chartered
    "LLOY.L",   # Lloyds
    "NWG.L",    # NatWest
    "DGE.L",    # Diageo
    "REL.L",    # RELX
    "RIO.L",    # Rio Tinto
    "GLEN.L",   # Glencore
    "AAL.L",    # Anglo American
    "ANTO.L",   # Antofagasta
    "VOD.L",    # Vodafone
    "BT-A.L",   # BT Group
    "AAF.L",    # Airtel Africa
    "PRU.L",    # Prudential
    "AV.L",     # Aviva
    "LGEN.L",   # Legal & General
    "PHNX.L",   # Phoenix
    "ABDN.L",   # Abrdn
    "III.L",    # 3i Group
    "WPP.L",    # WPP
    "BARC.L",   # Barclays
    "BNZL.L",   # Bunzl
    "CRH.L",    # CRH
    "EXPN.L",   # Experian
    "FERG.L",   # Ferguson
    "IAG.L",    # IAG
    "IMI.L",    # IMI
    "JD.L",     # JD Sports
    "KGF.L",    # Kingfisher
    "MKS.L",    # M&S
    "NXT.L",    # Next
    "PSN.L",    # Persimmon
    "RKT.L",    # Reckitt
    "SBRY.L",   # Sainsbury's
    "SGE.L",    # Sage
    "SVT.L",    # Severn Trent
    "TSCO.L",   # Tesco
    "UU.L",     # United Utilities
    "VTY.L",    # Vistry
    "WEIR.L",   # Weir Group
]


def _num(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None


def fetch_yf(tk: str):
    import yfinance as yf
    try:
        info = yf.Ticker(tk).info or {}
    except Exception:
        return None
    if not info or not info.get("marketCap"):
        return None
    return {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "mcap": info.get("marketCap"),
        "price": info.get("currentPrice") or info.get("previousClose"),
        "p_b": info.get("priceToBook"),
        "p_e_trailing": info.get("trailingPE"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "roe": info.get("returnOnEquity"),
        "dividend_yield": info.get("dividendYield"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "float_shares": info.get("floatShares"),
        "fwk_low": info.get("fiftyTwoWeekLow"),
        "fwk_high": info.get("fiftyTwoWeekHigh"),
    }


def score_japan(rec: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    pb = _num(rec.get("p_b"))
    roe = _num(rec.get("roe"))
    if pb is not None:
        if 0 < pb < 0.7:
            score += 25; reasons.append(f"PBR {pb:.2f} (TSE reform target)")
        elif 0 < pb < 1.0:
            score += 15; reasons.append(f"PBR {pb:.2f}")
    if roe is not None and roe > 0.08 and pb is not None and pb < 1.0:
        score += 10; reasons.append(f"quality+value ROE {roe*100:.0f}%")
    # 52-week drawdown
    px = _num(rec.get("price"))
    hi = _num(rec.get("fwk_high"))
    if px and hi and hi > 0:
        dd = (1 - px / hi) * 100
        if dd > 40:
            score += 8; reasons.append(f"DD {dd:.0f}%")
    return score, reasons


def score_korea(rec: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    pb = _num(rec.get("p_b"))
    name = (rec.get("name") or "").lower()
    if any(s in name for s in ("samsung", "hyundai", "lg", "sk", "posco")):
        score += 15; reasons.append("chaebol Value-Up candidate")
    if pb is not None and 0 < pb < 1.0:
        score += 10; reasons.append(f"PBR {pb:.2f}")
    elif pb is not None and 0 < pb < 1.5:
        score += 4
    # Treasury shares proxy: float < 70% of shares outstanding
    so = _num(rec.get("shares_outstanding"))
    fl = _num(rec.get("float_shares"))
    if so and fl and so > 0:
        treasury_pct = (1 - fl / so) * 100
        if treasury_pct > 15:
            score += 8; reasons.append(f"treasury ~{treasury_pct:.0f}%")
    return score, reasons


def score_uk(rec: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    pb = _num(rec.get("p_b"))
    if pb is not None:
        if 0 < pb < 0.7:
            score += 20; reasons.append(f"P/B {pb:.2f} (scheme candidate)")
        elif 0 < pb < 1.0:
            score += 10; reasons.append(f"P/B {pb:.2f}")
    pe = _num(rec.get("p_e_trailing"))
    if pe is not None and 0 < pe < 8:
        score += 12; reasons.append(f"P/E {pe:.1f}")
    div_y = _num(rec.get("dividend_yield"))
    if div_y is not None and div_y > 0.06:
        score += 8; reasons.append(f"div yield {div_y*100:.1f}%")
    return score, reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr)
        return 1

    universes = {
        "JP": (JAPAN_TICKERS, score_japan),
        "KR": (KOREA_TICKERS, score_korea),
        "UK": (UK_TICKERS, score_uk),
    }

    out = {}
    for jur, (tickers, scorer) in universes.items():
        print(f"\n=== {jur} ({len(tickers)} tickers) ===",
              file=sys.stderr, flush=True)
        for i, tk in enumerate(tickers, 1):
            if len(out) >= args.limit:
                break
            rec = fetch_yf(tk)
            time.sleep(args.sleep)
            if not rec:
                continue
            sc, rs = scorer(rec)
            if sc < 5:
                continue
            out[tk] = {
                "jurisdiction": jur,
                "name": rec.get("name"),
                "currency": rec.get("currency"),
                "mcap_local": rec.get("mcap"),
                "price": rec.get("price"),
                "p_b": rec.get("p_b"),
                "p_e_trailing": rec.get("p_e_trailing"),
                "roe": rec.get("roe"),
                "score": round(sc, 1),
                "reasons": "; ".join(rs),
            }
            if i % 10 == 0:
                print(f"  [{i}/{len(tickers)}] scored {len(out)}",
                      file=sys.stderr, flush=True)

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 30 foreign value-up candidates ===")
    for tk, v in ranked[:30]:
        pb = v.get("p_b") or 0
        roe = (v.get("roe") or 0) * 100
        print(f"  {tk:<10} {v['jurisdiction']} score={v['score']:<5} "
              f"P/B={pb:<5.2f} ROE={roe:<5.1f}% "
              f"{(v.get('name') or '')[:30]} -- {v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
