"""Classify each ticker as common-equity / preferred / CEF / BDR / etc.

Combines:
  - ticker-pattern rules (suffixes like -P, -U, -W; specific suffix letters
    appended to parent like AFGD = AFG + D = preferred)
  - name regex (Preferred / Subordinated / Trust / Royalty / Cumulative /
    Series A/B/C / Capital Trust / Notes / Income Fund / Municipal)
  - explicit deny-list of known US baby-bonds / preferreds / CEFs

Output column: `security_type` in {common, preferred, baby_bond, cef,
warrant, right, unit, etf, mutual_fund, depositary, unknown}.

USE NOTES:
  - The classifier is conservative: ambiguous = common.
  - It's intended for tagging in display sheets, NOT to drop rows from the
    raw consolidated CSV.
"""

import os
import re
import sys
import warnings
warnings.filterwarnings("ignore")

import pandas as pd


# --- Maintained deny lists --------------------------------------------------
# US baby bonds / preferreds whose name doesn't contain "preferred"/"trust"
KNOWN_BABY_BONDS = {
    "AFGD", "AFGB", "AFGE", "DTB", "DTG", "DTW", "DTY",
    "MGRB", "SIGIP", "SIGIB", "NTRSO", "BHFAN", "BHFAL", "BHFAM", "BHFAO",
    "FITBI", "FITBP", "VLYPO", "OXLCP", "OXLCN", "OXLCM", "OXLCL", "OXLCO",
    "RILYN", "RILYM", "RILYO", "RILYP", "RILYK", "RILYL", "RILYZ",
    "TRINI", "TRINZ",
    # Common preferred patterns (parent + single trailing letter)
    "GSL-PB", "GSL-PC", "PSA-PF", "PSA-PG",
}

# US closed-end funds that flag as Financials in our screens but trade
# discount/premium to NAV (different dynamics)
KNOWN_CEFS = {
    "MFM", "MFV", "MUI", "MUC", "MUH", "MNP", "MEN", "MFL", "MFT", "MQT",
    "MUE", "MUS", "MYD", "MYI", "MYJ", "MYN",
    "BCAT", "BSTZ", "BIGZ", "BGT", "BGY", "BME", "BOE",
    "OXLC", "OXSQ", "FSCO", "ECC", "ECCC", "ECCV", "ECCW", "ECCX",
    "ETV", "ETW", "ETB", "ETG", "ETJ", "ETO", "ETY",
    "EOI", "EOS", "EVT", "EXG", "EFR", "EXD",
    "JFR", "JRO", "JQC", "JPC", "JPT", "JRI", "JTA", "JTD",
    "PDI", "PDO", "PCN", "PCM", "PFL", "PFN", "PHK", "PHT", "PTY", "PCQ",
}

KNOWN_ETF_TICKERS = {
    # Names that came through equity scans but are actually ETFs/trusts
    "GLD", "SLV", "PSLV", "PHYS", "PPLT",
}

# Known iShares Brazilian Depositary Receipts (BDRs) — IShares-type BR tickers
# ending in 39 are BDRs (depositary receipts)


# --- Pattern rules -----------------------------------------------------------

# Ticker-suffix patterns
PREF_SUFFIX_RE = re.compile(r"-P[A-Z]?$|^[A-Z]+-PR[A-Z]?$|\.PR[A-Z]?$")
WARRANT_RE     = re.compile(r"-W[ST]?$|\.WS$|^[A-Z]+W$")
RIGHT_RE       = re.compile(r"-R$|\.R$")
UNIT_RE        = re.compile(r"-U$|\.U$|^[A-Z]+U$")
BR_BDR_RE      = re.compile(r"[0-9]{2}\.SA$")  # Brazilian BDRs end in 31/32/33/34/35/39 etc.

# Name patterns — order matters (more specific first)
NAME_RULES = [
    (re.compile(r"\b(preferred|cumulative|junior subordinated|senior notes?|debentures?)\b", re.I), "preferred"),
    (re.compile(r"\b(baby bonds?|subordinated notes?|notes? due|capital trust)\b", re.I), "baby_bond"),
    (re.compile(r"\b(closed[- ]end fund|municipal income trust|income trust|tax[- ]exempt)\b", re.I), "cef"),
    (re.compile(r"\b(royalty trust|royalty interest)\b", re.I), "royalty_trust"),
    (re.compile(r"\b(spdr|ishares|invesco|first trust|vanguard|wisdomtree|xtrackers|amundi|lyxor|"
                r"direxion|proshares|ucits etf)\b", re.I), "etf"),
    (re.compile(r"\b(mutual fund|open[- ]end fund)\b", re.I), "mutual_fund"),
    (re.compile(r"\b(depositary shares?|depositary receipt|adr|gdr)\b", re.I), "depositary"),
    (re.compile(r"\b(warrants?|w\.t\.|wts?)\b", re.I), "warrant"),
    (re.compile(r"\b(rights?)\b", re.I), "right"),
    (re.compile(r"\bunits?\b", re.I), "unit"),
    (re.compile(r"\bspac\b|special purpose acquisition", re.I), "spac"),
]


def classify(ticker, name):
    """Return security_type for one row."""
    t = str(ticker).upper().strip()
    n = str(name) if isinstance(name, str) else ""

    # Hard deny-lists
    if t in KNOWN_BABY_BONDS:
        return "baby_bond"
    if t in KNOWN_CEFS:
        return "cef"
    if t in KNOWN_ETF_TICKERS:
        return "etf"

    # Pattern checks on ticker
    if WARRANT_RE.search(t):
        return "warrant"
    if RIGHT_RE.search(t):
        return "right"
    if UNIT_RE.search(t):
        return "unit"
    if PREF_SUFFIX_RE.search(t):
        return "preferred"

    # Name-based rules
    for rx, cls in NAME_RULES:
        if rx.search(n):
            return cls

    # Brazilian BDR pattern (e.g. AAPL34.SA, BEEM39.SA)
    if BR_BDR_RE.search(t) and ".SA" in t:
        return "bdr"

    return "common"


def main():
    csv_path = "global_equities_consolidated.csv"
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    df = pd.read_csv(csv_path, index_col=0, low_memory=False)
    print(f"Loaded {len(df)} rows from {csv_path}")

    df["security_type"] = [classify(t, n) for t, n in zip(df.index, df.get("name", ""))]
    print("\nsecurity_type distribution:")
    print(df["security_type"].value_counts().to_string())

    # Sample non-common picks so the user can sanity-check
    print("\nSample of non-COMMON tags:")
    for cls in sorted(df["security_type"].unique()):
        if cls == "common":
            continue
        sub = df[df["security_type"] == cls]
        print(f"\n  --- {cls} ({len(sub)}) ---")
        cols = [c for c in ["name", "_universe", "sector"] if c in sub.columns]
        print(sub.head(10)[cols].to_string())

    df.to_csv(csv_path)
    print(f"\nWrote security_type column to {csv_path}")


if __name__ == "__main__":
    main()
