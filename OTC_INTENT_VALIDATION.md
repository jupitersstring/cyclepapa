# OTC management communications -- validation

Generated 2026-09-25 by `otc_comms.py`. Each dated document (press release, 8-K EX-99, shareholder letter, call) is scored on its shareholder-action language and labelled with what the company did over the next two fiscal quarters (diluted share count down >= 2% or dividends up >= 25% / initiated; FMP bulk statements).

| documents | n | base rate | AUC (language) | top-decile hit | lift |
|---|---|---|---|---|---|
| all | 11532 | 18.9% | 0.563 | 36.2% | 1.91x |
| press releases | 9551 | 17.5% | 0.522 | 22.8% | 1.30x |
| 8-K EX-99 | 671 | 11.3% | 0.576 | 23.9% | 2.11x |
| letters | 62 | 8.1% | 0.544 | 16.7% | 2.07x |
| calls | 1248 | 34.2% | 0.610 | 51.6% | 1.51x |
| not already shrinking | 9776 | 15.3% | 0.574 | 32.5% | 2.13x |
