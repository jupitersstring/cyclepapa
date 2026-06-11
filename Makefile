.PHONY: refresh init prices edgar validate workbook backtest meta

REFRESH_TICKERS := INMD KBR ROCK NSP SONO RPAY SEER MNRO UAA HHH NRP CDRE

init:    ; python3 pipeline/db.py migrate
prices:  ; python3 pipeline/ingest_prices.py
edgar:   ; python3 pipeline/ingest_edgar.py $(REFRESH_TICKERS)
backtest:; python3 pipeline/backtest.py
meta:    ; python3 pipeline/populate_metadata.py
validate:; python3 pipeline/validate.py
workbook:; python3 pipeline/render_workbook.py

refresh: prices edgar validate workbook
