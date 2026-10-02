"""Refresh 13F holdings to each fund's LATEST 13F-HR (the quarterly roll).

Re-checks every stored book (and every roster CIK) against EDGAR and, when a
newer 13F-HR exists, replaces that fund's holdings with it — the replaced book
becoming the fund's prior quarter when it is the immediately preceding period.

This used to carry its own copy of the parse-and-insert loop, and that copy had
none of the ingest guards: per-account lines were not summed by CUSIP (only the
last account's slice survived), option lines were booked as shares, the CUSIP
authority and bond tagging were skipped, full-dollar filings were not
normalized, and the prior quarter was left two quarters back. It now delegates
to ingest_13f.run(refresh=True), the single guarded path.

Run AFTER: nothing special.  Run BEFORE: ingest_13f_prior.py (priors the roll
could not carry over), build_cusip_map / map_cusip_fmp (any new issuers), then
unified_score + renderers.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f

def run():
    return ingest_13f.run(refresh=True)

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
