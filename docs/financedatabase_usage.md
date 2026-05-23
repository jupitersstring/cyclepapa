# financedatabase usage

`financedatabase` (https://github.com/JerBouma/FinanceDatabase) provides the
ticker universe + metadata layer for every screen in this repo. It is
**universe-only** — all price/volume/fundamentals come from yfinance.

## Available methods

```python
import financedatabase as fd

eq = fd.Equities()           # equities (~150k rows)
etfs = fd.ETFs()             # ETFs (~37k rows)

# Filter by metadata - all filter args are optional and accept list or str
eq.select(
    country="United States",                 # str | list
    sector="Information Technology",         # 11 sectors (GICS)
    industry_group="Semiconductors & Semiconductor Equipment",
    industry="Semiconductors",
    currency="USD",
    exchange="NMS",                          # NYQ, NMS, NGM, NCM, ASE, BATS, PCX (ETFs)
    market="us_market",
    market_cap="Mid Cap",                    # Nano|Micro|Small|Mid|Large|Mega
    only_primary_listing=False,              # WARNING: returns ADRs/PNK for non-US
)

# Text search across all string columns (returns DataFrame)
eq.search(name="Tesla")
eq.search(summary="robotics", country="United States")
eq.search(industry="Banking", market_cap="Large Cap")

# Discover available categorical values
eq.show_options()                            # global
eq.show_options(country="Netherlands")       # constrained to NL
eq.show_options(sector="Health Care", show_option="industry")
```

## What financedatabase does NOT provide

> "The aim of this database is explicitly NOT to provide up-to-date
> fundamentals or stock data."

For that we use:
- `yfinance.download(...)` — OHLCV bars (daily, weekly, monthly)
- `yfinance.Ticker(t).info` — fundamentals (P/B, ROE, EV/EBITDA, debt/equity)

## How we use it here

| Code path | fd call |
|---|---|
| `get_universe("us-all")` | `fd.Equities().select(country="United States", market_cap=...)` × 6 caps, dedup, filter to US exchanges |
| `get_universe("us-etfs")` | `fd.ETFs().select()` filtered to PCX/NYQ/NMS/NGM/NCM/ASE/BATS |
| `get_universe("eu-smid")` | `fd.Equities().select(country=...)` × 20 EU countries × Nano..Mid, filtered to 18 EU primary exchanges |
| `get_universe("br-all")` | `fd.Equities().select(country="Brazil")` filtered to SAO (B3) |
| `--sector` CLI flag | `apply_universe_filters(df, sector="Information Technology,Health Care")` |
| `--theme` CLI flag | text search across `name + summary` for keyword(s) |

## CLI examples

```bash
# Default: us-all everything
python3 momentum_rank.py --universe us-all --top 50

# Only US healthcare biotechs
python3 momentum_rank.py --universe us-all --sector "Health Care" --top 30

# Only US semis (industry-level)
python3 momentum_rank.py --universe us-all \
    --industry "Semiconductors" --top 30

# Thematic - find AI/robotics names by description
python3 momentum_rank.py --universe us-all \
    --theme "artificial intelligence,robotics,quantum" --top 30

# Same on EU
python3 momentum_rank.py --universe eu-smid \
    --sector "Information Technology" --top 30
```

## Known issues

- `only_primary_listing=True` for non-US countries returns ADRs and PNK
  pink-sheet listings instead of the home-exchange primary. We do NOT
  use this flag; instead we filter by exchange code (LSE for UK, SAO
  for Brazil, etc.).
- Cap categorization (Mid/Small/etc.) is computed by fd based on
  USD market cap, refreshed roughly weekly. Verify boundaries if the
  cap classification matters precisely.

## Universes currently defined

| Key | fd query | Filtered to exchange(s) | Approx size |
|---|---|---|---|
| us-mid | country=US, cap=Mid | NYQ/NMS/NGM/NCM/ASE/BATS | 1,284 |
| us-micro | country=US, cap=Micro | same | 1,547 |
| us-smid | country=US, cap=Small+Mid | same | 3,761 |
| us-midlarge | country=US, cap=Mid+Large | same | 2,134 |
| us-all | country=US, cap=Nano..Mega | same | 9,249 |
| uk-smid | country=UK, cap=Small+Mid | LSE | 188 |
| uk-midlarge | country=UK, cap=Mid+Large | LSE | 174 |
| uk-all | country=UK, cap=all | LSE | 336 |
| br-all | country=Brazil, cap=Nano..Large | SAO | 553 |
| eu-smid | EU_COUNTRIES, cap=Nano..Mid | EU_PRIMARY_EXCHANGES | 4,549 |
| it-all | country=Italy, cap=all | MIL | 359 |
| de-all | country=Germany, cap=Nano..Mid | GER | 390 |
| us-etfs | ETFs | US_ETF_EXCHANGES (incl. PCX) | 2,192 |
| uk-etfs | ETFs | LSE | 2,062 |
| de-etfs | ETFs | GER | 1,610 |
| it-etfs | ETFs | MIL | 1,307 |
| eu-etfs | ETFs | EU_PRIMARY_EXCHANGES | 7,449 |

Add a new universe by extending `get_universe()` in `scan_failed_bearish.py`.
