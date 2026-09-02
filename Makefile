.PHONY: refresh init prices edgar validate workbook backtest meta snapshot restore styles conviction entry fund_monitor positions discover all

REFRESH_TICKERS := INMD KBR ROCK NSP SONO RPAY SEER MNRO UAA HHH NRP CDRE

init:        ; python3 pipeline/db.py migrate
prices:      ; python3 pipeline/ingest_prices.py
edgar:       ; python3 pipeline/ingest_edgar.py $(REFRESH_TICKERS)
backtest:    ; python3 pipeline/backtest.py
meta:        ; python3 pipeline/populate_metadata.py
validate:    ; python3 pipeline/validate.py
fund_monitor:; python3 pipeline/ingest_fund_xlsx.py && python3 pipeline/fund_monitor.py
styles:      ; python3 pipeline/styles_view.py
conviction:  ; python3 pipeline/conviction.py
entry:       ; python3 pipeline/entry_intact.py
discover:    ; python3 pipeline/discover.py all
positions:   ; python3 pipeline/positions_by_style.py
workbook:    ; python3 pipeline/render_workbook.py

# DURABILITY — ALWAYS run after a refresh so the work survives sandbox reset
snapshot:    ; python3 pipeline/snapshot.py dump
restore:     ; python3 pipeline/snapshot.py restore

# Full pipeline. Snapshot is the LAST step — nothing is "done" until it's
# persisted to git-safe CSVs and committed.
refresh: prices edgar conviction entry validate workbook positions snapshot
