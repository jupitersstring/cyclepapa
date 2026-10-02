"""Normalize malformed foreign tickers to valid Yahoo Finance format.

Audit revealed agents mixed Bloomberg suffixes, mis-handled US dual-class
tickers (dot vs hyphen), left HK tickers unpadded, and ingested a few
garbage rows. This corrects them in fund_positions in place, then the
caller re-enriches via yfinance.
"""
import os, re, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Bloomberg-suffix -> Yahoo-suffix conversions
BLOOMBERG_TO_YAHOO = {
    ".IM": ".MI",   # Milan
    ".FP": ".PA",   # Paris
    ".LN": ".L",    # London
    ".NA": ".AS",   # Amsterdam
    ".GA": ".AT",   # Athens
    ".GR": ".DE",   # Germany/Frankfurt
    ".SG": ".SI",   # Singapore (Bloomberg SP/SG → Yahoo SI)
    ".SW": ".SW",   # Swiss (same)
    ".KA": ".KAR",  # Karachi
    ".BD": ".BD",   # Budapest (Yahoo has no clean BD; leave, will fail gracefully)
    ".CN": ".CN",   # Canadian Securities Exchange (Yahoo uses .CN)
}

# US dual-class tickers that use a HYPHEN on Yahoo, not a dot
US_DUALCLASS = {
    "BRK.A": "BRK-A", "BRK.B": "BRK-B",
    "BF.A": "BF-A", "BF.B": "BF-B",
    "HEI.A": "HEI-A", "LEN.B": "LEN-B", "MOG.A": "MOG-A",
    "CWEN.A": "CWEN-A", "PBR.A": "PBR-A", "TRUE.B": "TRUE-B",
    "UHAL.B": "UHAL-B", "LGF.A": "LGF-A", "LGF.B": "LGF-B",
    "RUSHA.A": "RUSHA",
}

# Specific known fixes (malformed / delisted / garbage)
SPECIFIC = {
    "AKER.BP": "AKRBP.OL",       # Aker BP, Oslo
    "PLX.FP": "PLX.PA",          # Pluxee Paris
    "BFIT.NA": "BFIT.AS",        # Basic-Fit Amsterdam
    "OTOEL.GA": "OTOEL.AT",      # Autohellas Athens
    "LDO.IM": "LDO.MI",          # Leonardo Milan
    "BZU.IM": "BZU.MI",          # Buzzi Milan
    "TISG.MI": "TIT.MI",         # (leave — Telecom Italia already TIT)
    "GNS.LN": "GNS.L", "WISE.LN": "WISE.L",
    "D05.SG": "D05.SI",          # DBS Singapore
    "184.HK": "0184.HK",         # Keck Seng — HK 4-digit padding
    "86.HK": "0086.HK",
}

# Pure garbage to delete (not real securities)
GARBAGE = {"2025.T"}   # "Annual Letter" parse error

# Known delisted/taken-private (no longer trade — remove to avoid false signal)
DELISTED = {
    "6502.T",   # Toshiba — taken private Dec 2023
    "9749.T",   # Fuji Soft — acquired by KKR 2024-25
    "4917.T",   # Mandom — MBO delisted Mar 2026 (Hibiki exited)
    "7718.T",   # Star Micronics — taken private ~Apr 2026 (Taiyo)
}

def pad_hk(t):
    """Hong Kong tickers must be zero-padded to 4 digits before .HK."""
    m = re.match(r"^(\d{1,3})\.HK$", t)
    if m:
        return f"{int(m.group(1)):04d}.HK"
    return t

def run():
    conn = sqlite3.connect(DB)
    distinct = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM fund_positions WHERE ticker IS NOT NULL")]
    n_fix = n_del = 0
    for t in distinct:
        if t in GARBAGE or t in DELISTED:
            conn.execute("DELETE FROM fund_positions WHERE ticker=?", (t,))
            n_del += 1
            print(f"  deleted {'garbage' if t in GARBAGE else 'delisted'}: {t}")
            continue
        new = t
        if t in SPECIFIC:
            new = SPECIFIC[t]
        elif t in US_DUALCLASS:
            new = US_DUALCLASS[t]
        else:
            # Bloomberg suffix conversion
            for bb, yh in BLOOMBERG_TO_YAHOO.items():
                if t.endswith(bb) and bb != yh:
                    new = t[:-len(bb)] + yh
                    break
            new = pad_hk(new)
        if new != t:
            # merge into existing if target already present for same fund
            conn.execute("UPDATE OR IGNORE fund_positions SET ticker=? WHERE ticker=?", (new, t))
            conn.execute("DELETE FROM fund_positions WHERE ticker=?", (t,))  # leftover dups
            n_fix += 1
            print(f"  fixed {t:<14} -> {new}")
    conn.commit()
    print(f"\ndone: {n_fix} tickers normalized, {n_del} garbage/delisted removed")

if __name__ == "__main__":
    run()
