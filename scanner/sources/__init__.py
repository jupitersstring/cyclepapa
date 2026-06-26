"""
Data-source adapters.

This package separates the "where does the data come from" concern from the
"how do we use it" concern. Each module here documents the exact public
endpoint, mnemonic, and Python-snippet for one data provider. The modules
ship with cached/calibrated current-snapshot data so the scanner runs
without network access; replace _fallback() returns with live loaders to
go quarterly-refreshing.

Live-wiring sequence (per the workflow's adversarial verifier):
    1. bis.py       -- BIS LBS FX-adjusted cross-border credit flows
    2. fred.py      -- FRED Z.1 sector net-lending (US) + NIPA Kalecki-Levy
    3. eurostat.py  -- nasq_10_nf_tr B9 net lending by sector for EZ-19
    4. oecd.py      -- OECD QNA + Financial Accounts for non-EU AE
    5. imf.py       -- IMF datamapper API for WEO + ESR external-position
    6. ecb.py       -- ECB BLS forward credit standards (leading indicator)
    7. national.py  -- PBoC, RBI, BCB, Banxico, BoK, CBRT national-source pulls
"""
