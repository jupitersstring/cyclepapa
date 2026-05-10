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
   * **Inflection flag** – YoY-growth sign-flip from ≤0% to >0%
   * **First-positive flag** – the level itself crossed zero from below
     (current TTM/annual > 0 while prior period ≤ 0). Distinct from the
     growth-flip: this fires on the first positive FCF / EBITDA / CFO /
     net income / ROCE print after a loss-making period. Strong Yartseva
     entry signal.
   * **ROCE inflection** – ROCE improving (delta YoY > 0) when the prior
     period was ≤ 0; or ROCE itself crossing zero from below.
5. **Forward-projected break-even** – linear extrapolation of the latest
   period-over-period improvement in FCF (and EBITDA / CFO / NI). Reports
   `*_eta_quarters` / `*_eta_years` plus `fcf_projected_positive_in_n`
   binary flag (= 1 if currently negative, improving, and break-even
   reached within `--projection-n` quarters). Use to surface names that
   *aren't yet* FCF positive but are on a path to be.
6. **"Not priced in" divergence** – fundamental momentum (rev/EBITDA/FCF YoY)
   minus the same window's price return, plus EV/Sales multiple compression
   while sales grew. Positive = price/multiple has not caught up to the
   improving fundamentals.
7. **Cheapness composites** (lower = cheaper):
   * **`cheapness_growth_blend`** = `(1/3)·sales_yoy + (1/3)·ebitda_yoy
     + (1/6)·fcf_yoy + (1/6)·(NCAV / mcap)`
     where NCAV = current assets − total liabilities (Graham).
   * **`cheapness_ev_ebit_vs_growth`** = `EV/EBIT / cheapness_growth_blend`
     (only computed when blend > 0). Sub-7 reads as cheap relative to growth.
   * **`cheapness_under_7x_flag`** – binary trigger: `EV/EBIT < 7x` AND
     blend > 0 (a "cheap *and* growing" filter; Yartseva-style entry).
   * **`cheapness_blend_vs_growth`** = `((P/B + EV/EBIT)/2)
     / ((sales_yoy + ebitda_yoy)/2)`. Lower = cheaper relative to
     blended top-line + EBITDA growth.
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
