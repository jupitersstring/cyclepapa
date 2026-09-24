"""Expand the universe with operating companies from FMP's live company list.

financedatabase (the original universe source) filters by DOMICILE and a coarse
size label, which structurally misses whole pockets of listed companies:

* Chinese companies listed in Hong Kong (H-shares / red chips) — domicile is CN,
  not HK, so the HK segment never saw them;
* foreign-domiciled London listings (Jersey / Guernsey / Irish) — same issue;
* micro caps everywhere (``size_filter=SMID_LARGE`` drops fd's Micro label);
* whole home markets fd only carried as cross-listings (Poland, UAE, ...);
* Canada's TSX Venture board.

This script takes FMP's ``profile-bulk`` (every listed security with live
flags), keeps ACTIVE OPERATING equities on HOME exchanges, normalises market cap
to USD, maps FMP's industry taxonomy onto the universe's GICS-style one with a
crosswalk learned from the names both sources share, and appends the missing
names to ``universe.parquet``. ``scripts/widen_fetch.py`` then fetches them.

Respects the standing exclusions: India (by request) and Russia (sanctioned).

    export FMP_API_KEY=...
    python scripts/expand_universe.py --dry-run          # report the gap only
    python scripts/expand_universe.py --min-mcap 50e6    # append to the universe
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fmp, util
from earnings_model.valuation import _NONOP_RE, _NONOP_SYM_RE

EXCLUDED_COUNTRIES = {"IN", "RU"}          # India by request; Russia sanctioned
# Listing venue -> region bloc. Only HOME/primary venues: secondary German venues,
# pan-EU MTFs, OTC, the LSE International Order Book and Canadian alt boards
# carry cross-listings of names already covered on their home exchange.
EXCHANGE_REGION = {
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US",
    "LSE": "UK",
    "XETRA": "EU", "PAR": "EU", "AMS": "EU", "BRU": "EU", "MIL": "EU", "BME": "EU",
    "LIS": "EU", "STO": "EU", "OSL": "EU", "CPH": "EU", "HEL": "EU", "SIX": "EU",
    "VIE": "EU", "WSE": "EU", "ATH": "EU", "PRA": "EU", "BUD": "EU", "ICE": "EU",
    "TAL": "EU", "RIS": "EU", "LIT": "EU", "IRL": "EU", "ISE": "EU",
    "TSX": "CA", "TSXV": "CA",
    "JPX": "JP",
    "SHH": "CN", "SHZ": "CN",
    "HKSE": "HK",
    "KSC": "KR", "KOE": "KR",
    "TAI": "TW", "TWO": "TW",
    "SES": "SEA", "SET": "SEA", "JKT": "SEA", "KLS": "SEA", "PSE": "SEA",
    "HOSE": "SEA", "HNX": "SEA",
    "ASX": "ANZ", "NZE": "ANZ",
    "SAO": "LATAM", "MEX": "LATAM", "SGO": "LATAM", "BUE": "LATAM",
    "BVC": "LATAM", "BVL": "LATAM",
    "SAU": "MEA", "TLV": "MEA", "IST": "MEA", "JNB": "MEA", "DFM": "MEA",
    "ADX": "MEA", "DOH": "MEA", "CAI": "MEA", "KUW": "MEA",
}
# Venue -> its home country (ISO-2), used only to vet listings that carry no ISIN.
EXCHANGE_COUNTRY = {
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US", "LSE": "GB",
    "XETRA": "DE", "PAR": "FR", "AMS": "NL", "BRU": "BE", "MIL": "IT", "BME": "ES",
    "LIS": "PT", "STO": "SE", "OSL": "NO", "CPH": "DK", "HEL": "FI", "SIX": "CH",
    "VIE": "AT", "WSE": "PL", "ATH": "GR", "PRA": "CZ", "BUD": "HU", "ICE": "IS",
    "TAL": "EE", "RIS": "LV", "LIT": "LT", "IRL": "IE", "ISE": "IE",
    "TSX": "CA", "TSXV": "CA", "JPX": "JP", "SHH": "CN", "SHZ": "CN", "HKSE": "HK",
    "KSC": "KR", "KOE": "KR", "TAI": "TW", "TWO": "TW", "SES": "SG", "SET": "TH",
    "JKT": "ID", "KLS": "MY", "PSE": "PH", "HOSE": "VN", "HNX": "VN",
    "ASX": "AU", "NZE": "NZ", "SAO": "BR", "MEX": "MX", "SGO": "CL", "BUE": "AR",
    "BVC": "CO", "BVL": "PE", "SAU": "SA", "TLV": "IL", "IST": "TR", "JNB": "ZA",
    "DFM": "AE", "ADX": "AE", "DOH": "QA", "CAI": "EG", "KUW": "KW",
}
# LSE "0XXX.L" codes are foreign stocks cross-traded in London, not home listings.
_LSE_FOREIGN = re.compile(r"^0[A-Z0-9]{3}\.L$")
# FMP reports sub-unit-quoted listings' market cap in the MAJOR unit (BP.L's cap is
# in GBP though the quote currency is GBp), so map sub-units to their major unit.
_SUBUNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS", "KWF": "KWD"}
# Same USD cut-offs as the size-bucket labels the universe already uses.
_BUCKETS = [(200e9, "Mega Cap"), (10e9, "Large Cap"), (2e9, "Mid Cap"),
            (300e6, "Small Cap"), (50e6, "Micro Cap"), (0, "Nano Cap")]
CROSSWALK_PATH = config.DATA_DIR / "industry_crosswalk_fmp.csv"
UNIVERSE_COLS = ["symbol", "name", "sector", "industry_group", "industry", "market_cap",
                 "currency", "exchange", "country", "size_bucket", "region"]


def fetch_profiles(src_dir: Path | None) -> pd.DataFrame:
    """FMP profile-bulk, from pre-downloaded part_*.csv files or fetched live."""
    if src_dir and any(src_dir.glob("part_*.csv")):
        parts = sorted(src_dir.glob("part_*.csv"))
        return pd.concat([pd.read_csv(p, low_memory=False) for p in parts], ignore_index=True)
    frames = []
    for part in range(20):
        try:
            df = fmp._fetch_csv(f"profile-bulk?part={part}")
        except RuntimeError:
            break                                   # past the last part (FMP 400s)
        if df.empty:
            break
        frames.append(df)
        time.sleep(22.0)                            # FMP bulk throttle
    return pd.concat(frames, ignore_index=True)


def fetch_fx() -> dict[str, float]:
    """{currency -> USD per unit} from FMP's batch forex quotes."""
    import json
    import urllib.request
    url = f"{fmp.BASE}/batch-forex-quotes?apikey={fmp._key()}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cyclepapa/1.0"}),
                                timeout=60) as r:
        quotes = json.loads(r.read())
    fx = {q["symbol"][:3]: float(q["price"]) for q in quotes
          if str(q.get("symbol", "")).endswith("USD") and len(q["symbol"]) == 6 and q.get("price")}
    fx["USD"] = 1.0
    return fx


def _truthy(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1"])


_CORP_WORDS = re.compile(
    r"\b(the|and|inc|incorporated|corp|corporation|co|company|ltd|limited|plc|sa|ag|nv|se|"
    r"spa|ab|asa|as|oyj|bhd|berhad|tbk|pcl|holdings?|group|class\s+[a-z])\b")
# Venues whose foreign-company boards are pure cross-listings (Mexico's SIC,
# Argentina's CEDEARs, Chile's international market): only DOMESTIC companies
# have a genuine primary listing there.
_DOMESTIC_ONLY = {"MEX", "BUE", "SGO"}
# ASX ordinary shares carry 3-character codes; 5-character codes are hybrids,
# capital notes and options (AN3PJ is an ANZ hybrid, not ANZ's equity).
_ASX_ORDINARY = re.compile(r"^[A-Z0-9]{3}\.AX$")
_DR_NAME = re.compile(r"\bcedear\b|\bdepositary\b|\breceipts?\b", re.I)


def _norm_name(name: str) -> str:
    """Company name reduced to its distinctive words, for cross-venue matching."""
    if not isinstance(name, str):
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    s = _CORP_WORDS.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_crosswalk(ops: pd.DataFrame, uni: pd.DataFrame) -> pd.DataFrame:
    """FMP industry -> the universe's (sector, industry_group, industry), learned as
    the MODE over names present in both sources."""
    both = ops.merge(uni[["symbol", "sector", "industry_group", "industry"]]
                     .rename(columns={"sector": "u_sector", "industry_group": "u_group",
                                      "industry": "u_industry"}), on="symbol")
    both = both[both["u_industry"].notna() &
                ~both["u_industry"].astype(str).isin(["", "Unknown", "nan"])]
    cw = (both.groupby(["industry", "u_sector", "u_group", "u_industry"]).size()
              .rename("n").reset_index().sort_values(["industry", "n"], ascending=[True, False]))
    total = cw.groupby("industry")["n"].transform("sum")
    cw["purity"] = (cw["n"] / total).round(3)
    return cw.drop_duplicates("industry").reset_index(drop=True)


def candidates(prof: pd.DataFrame, uni: pd.DataFrame, fx: dict, min_mcap: float,
               crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Missing companies, each resolved to its PRIMARY listing.

    Every venue here also lists foreign companies (NVIDIA trades on Xetra, Apple
    in Mexico, Tencent in Vienna), so a venue-only rule admits cross-listings of
    names we already hold. Instead each company is identified by ISIN and resolved
    to one primary listing: the venue in the ISIN's home country (US... ISIN ->
    NASDAQ/NYSE), or, for offshore domiciles with no home exchange (Cayman,
    Bermuda, Jersey, ...), the highest dollar-volume allowed venue (Tencent ->
    HKSE). A company is skipped if ANY of its listings is already in the universe.
    """
    ops = prof[_truthy(prof["isActivelyTrading"]) & ~_truthy(prof["isEtf"])
               & ~_truthy(prof["isFund"]) & ~_truthy(prof["isAdr"])].copy()
    ops = ops[ops["industry"].notna() & (ops["industry"].astype(str).str.strip() != "")]
    ops["symbol"] = ops["symbol"].astype(str)
    fxr = ops["currency"].map(lambda c: _SUBUNIT.get(c, c)).map(fx)
    ops["mcap_usd"] = pd.to_numeric(ops["marketCap"], errors="coerce") * fxr
    ops["dvol_usd"] = (pd.to_numeric(ops["price"], errors="coerce")
                       * pd.to_numeric(ops["averageVolume"], errors="coerce") * fxr)
    ops["region"] = ops["exchange"].map(EXCHANGE_REGION)
    ops["isin"] = ops["isin"].astype(str).where(ops["isin"].notna(), None)
    ops["isin_cty"] = ops["isin"].str[:2]

    # Companies already covered: any listing of theirs is in the universe (direct
    # symbol or a same-security suffix alias). Collect their ISINs so every OTHER
    # venue listing of the same company is skipped too.
    have = set(uni["symbol"].astype(str))
    def known(s: str) -> bool:
        return (s in have or (s.endswith(".DE") and s[:-3] + ".F" in have)
                or (s.endswith(".TW") and s[:-3] + ".TWO" in have))
    known_isins = set(ops.loc[ops["symbol"].map(known) & ops["isin"].notna(), "isin"])

    # PRIMARY listing per company = where it trades most (USD dollar volume) across
    # ALL its venues, including ones we don't cover. This one rule handles every
    # case: NVIDIA -> NASDAQ (already held -> skipped), Medtronic / Accenture (Irish
    # ISINs, NYSE-only) -> NYSE, Check Point (Israeli ISIN) -> NASDAQ, Tencent
    # (Cayman) -> HKSE, a US OTC shell cross-listed in Frankfurt -> OTC (not
    # covered -> skipped). A company is added only if its primary venue is covered.
    with_isin = ops[ops["isin"].notna()].sort_values("dvol_usd", ascending=False)
    primary = with_isin.drop_duplicates("isin", keep="first")
    # Listings with no ISIN can't be resolved across venues: keep only a
    # listing whose company is domiciled in the venue's own country.
    no_isin = ops[ops["isin"].isna()]
    no_isin = no_isin[no_isin["exchange"].map(EXCHANGE_COUNTRY) == no_isin["country"]]

    cand = pd.concat([primary, no_isin], ignore_index=True)
    new = cand[cand["region"].notna()                             # primary venue is covered
               & ~cand["country"].isin(EXCLUDED_COUNTRIES)
               & ~cand["isin_cty"].isin(EXCLUDED_COUNTRIES)
               & ~cand["symbol"].str.match(_LSE_FOREIGN)
               & ~cand["symbol"].str.contains(_NONOP_SYM_RE)       # preferreds (JPM-PM)
               & ~cand["companyName"].astype(str).str.contains(_NONOP_RE)
               & ~cand["companyName"].astype(str).str.contains(_DR_NAME)
               & (~cand["symbol"].str.endswith(".AX") | cand["symbol"].str.match(_ASX_ORDINARY))
               & (~cand["exchange"].isin(_DOMESTIC_ONLY)
                  | (cand["exchange"].map(EXCHANGE_COUNTRY) == cand["country"]))
               & (cand["mcap_usd"] >= min_mcap)
               & ~cand["symbol"].map(known)
               & ~cand["isin"].isin(known_isins)].copy()
    # Depositary receipts (Canadian CDRs like WMT.TO, Singapore DRs, Vienna
    # certificates) carry their OWN ISIN, so the ISIN rule can't tie them to the
    # company — but their name can. Drop a candidate whose normalized name is
    # already in the universe, and keep one listing per name among candidates
    # (the most-traded: Tencent 0700.HK over its Vienna line; for A/H dual
    # listings the busier line wins, the other is the same fundamentals).
    uni_names = {n for n in uni["name"].astype(str).map(_norm_name) if len(n) >= 5}
    new["_nn"] = new["companyName"].astype(str).map(_norm_name)
    named = new["_nn"].str.len() >= 5
    new = new[~(named & new["_nn"].isin(uni_names))]
    new = new.sort_values("dvol_usd", ascending=False)
    new = new[~(new["_nn"].str.len().ge(5) & new.duplicated("_nn"))]
    new = new.merge(crosswalk[["industry", "u_sector", "u_group", "u_industry"]],
                    on="industry", how="left")
    new = new.sort_values("mcap_usd", ascending=False)

    def bucket(v: float) -> str:
        return next(lbl for lo, lbl in _BUCKETS if v >= lo)

    out = pd.DataFrame({
        "symbol": new["symbol"], "name": new["companyName"],
        "sector": new["u_sector"].fillna(new["sector"]),
        "industry_group": new["u_group"],
        "industry": new["u_industry"].fillna(new["industry"]),
        "currency": new["currency"], "exchange": new["exchange"], "country": new["country"],
        "region": new["region"], "mcap_usd": new["mcap_usd"],
    })
    out["size_bucket"] = out["mcap_usd"].map(bucket)
    out["market_cap"] = out["size_bucket"]
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", type=Path, default=None,
                    help="dir of pre-downloaded profile-bulk part_*.csv (else fetched)")
    ap.add_argument("--min-mcap", type=float, default=50e6, help="USD floor (default $50M)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    prof = fetch_profiles(args.profiles)
    fx = fetch_fx()
    ops_all = prof[_truthy(prof["isActivelyTrading"]) & ~_truthy(prof["isEtf"])
                   & ~_truthy(prof["isFund"]) & ~_truthy(prof["isAdr"])]
    cw = build_crosswalk(ops_all.assign(symbol=ops_all["symbol"].astype(str)), uni)
    new = candidates(prof, uni, fx, args.min_mcap, cw)

    print(f"universe: {len(uni)} | FMP profiles: {len(prof)} | "
          f"crosswalk: {len(cw)} industries (median purity {cw['purity'].median():.0%})")
    print(f"NEW names (>= ${args.min_mcap/1e6:,.0f}M, home venues, ex-IN/RU): {len(new)}")
    print("  by region:", new["region"].value_counts().to_dict())
    print("  by size:  ", new["size_bucket"].value_counts().to_dict())
    if args.dry_run:
        return

    util.atomic_write_text(CROSSWALK_PATH, cw.to_csv(index=False))
    grown = pd.concat([uni, new[UNIVERSE_COLS]], ignore_index=True)
    grown = grown.drop_duplicates("symbol", keep="first")
    util.atomic_to_parquet(grown, config.UNIVERSE_PATH)
    util.atomic_to_parquet(grown, config.DATA_DIR / "universe.parquet")
    print(f"universe {len(uni)} -> {len(grown)} (+{len(grown) - len(uni)}), "
          f"largest-first so widen_fetch.py fetches the biggest names first")


if __name__ == "__main__":
    main()
