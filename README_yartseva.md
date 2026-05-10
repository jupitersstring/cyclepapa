# Yartseva-style Italian fundamentals database

`yartseva_db.py` builds a fundamentals snapshot of the Italian (`*.MI`) equity
universe and ranks each name by a Yartseva-inspired multibagger score along
with inflection / acceleration / "not priced in" signals.

## What it does

1. **Universe** – pulled from `financedatabase` (`country='Italy'`, restricted
   to Borsa Italiana `*.MI` listings). Filterable by market-cap bucket
   (`Nano / Micro / Small / Mid / Large`).
2. **Fundamentals** – yfinance quarterly + annual income statement, cash flow
   and balance sheet. Italian smid caps often report semi-annually, so the
   script falls back to annual data for YoY/TTM measures when quarterly is
   sparse.
3. **Per-name metrics** (TTM levels, margins, capital efficiency, valuation):
   * Revenue, EBITDA, CFO, FCF (TTM)
   * EBITDA margin, FCF margin
   * CFO / EBITDA cash conversion
   * ROCE = EBIT / (equity + debt − cash)
   * Net debt / EBITDA
   * EV / Sales, EV / EBITDA, FCF yield
4. **Growth & inflection** on Sales / EBITDA / CFO / FCF:
   * **YoY** – TTM vs prior-year TTM (or annual if quarterly missing)
   * **QoQ-of-TTM** – TTM rolled forward one quarter (where 5+ quarters exist)
   * **Sequential** – latest single quarter vs prior single quarter
   * **Acceleration** – latest YoY growth minus prior YoY growth
   * **Inflection flag** – sign-flip from ≤0% YoY to >0% YoY
5. **"Not priced in" divergence** – fundamental momentum (rev/EBITDA/FCF YoY)
   minus the same window's price return, plus EV/Sales multiple compression
   while sales grew. Positive = price/multiple has not caught up to the
   improving fundamentals.
6. **Yartseva composite** – weighted blend (0–1):

   | weight | factor                                           |
   |-------:|--------------------------------------------------|
   | 0.20   | revenue growth (TTM YoY)                         |
   | 0.15   | revenue acceleration                             |
   | 0.15   | EBITDA-margin expansion (YoY pp)                 |
   | 0.15   | ROCE                                             |
   | 0.10   | cash conversion (CFO / EBITDA)                   |
   | 0.10   | EV/Sales relative to growth (PEG-style)          |
   | 0.10   | FCF yield                                        |
   | 0.05   | leverage (net debt / EBITDA, lower is better)    |

## Usage

```bash
python yartseva_db.py --max 0 --min-bucket "Small Cap" --workers 8 \
    --out italian_yartseva.csv --top 20
```

Flags:

* `--max N`   limit number of tickers (`0` = all in the bucket)
* `--min-bucket` minimum market-cap bucket from financedatabase
* `--workers` parallel yfinance fetchers (default 6)
* `--out`     CSV output path
* `--top`     rows printed in the console summary tables

## Caveats

* yfinance `info` has been flaky for delisted tickers (e.g. `ILTY.MI` 404).
  Those are skipped silently.
* EV/Sales and net-debt/EBITDA are not meaningful for banks/insurers; the
  composite still scores them on growth + cash factors but valuation metrics
  for financials should be ignored manually.
* Quarter-on-quarter (sequential) metrics are not seasonally adjusted.
* FCF YoY can blow up when prior-year FCF is near zero – use the absolute
  level alongside the ratio.

## Output

`italian_yartseva.csv` contains 50 columns per ticker; the script also prints
four ranked tables to stdout:

1. Top by Yartseva multibagger score
2. Inflections (rev / EBITDA / FCF YoY sign-flip up)
3. Top "not priced in" (fundamentals ahead of price + multiple)
4. Top acceleration (Δ YoY-growth, latest period − prior)
