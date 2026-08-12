# 200-week-low × normalised-FCF-yield × buyback screener

Screens for names trading near their 200-week low that still generate
strong normalised free cash flow and are buying back stock. Two backends:

| Script | Data source | Cost |
|---|---|---|
| `yf_screen.py` | Yahoo Finance via `yfinance` | free |
| `screen_200wlow_fcf_buyback.py` | EODHD All-In-One API | needs `EODHD_KEY` |

Both run in Claude Code cloud sessions: outbound HTTPS goes through the
session's agent proxy, and `requests`/`yfinance` pick up `HTTPS_PROXY` and
`REQUESTS_CA_BUNDLE` from the environment automatically. They also run
unchanged on a local machine.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Rebuild the US universe file (NYSE + NASDAQ + AMEX, ~6k names):
python build_universe_us.py

# Wide US sweep:
python yf_screen.py --universe-file universe_us.csv --out us_shortlist.csv

# Global majors (Wikipedia-scraped at runtime + embedded fallbacks):
python yf_screen.py --universe SP500,FTSE100,NIKKEI225,HSI,DAX,ASX200,KOSPI \
                    --out global_shortlist.csv

# Resume an interrupted run (checkpoints in .ckpt_*.parquet):
python yf_screen.py --universe-file universe_us.csv --resume
```

Filters (tune via flags): `--within-low-pct 15`, `--min-norm-fcf-yield 0.07`,
`--min-buyback-yield 0.03`, `--max-nd-ebitda 4.5`, `--min-price 1.0`,
`--min-weeks 150`.

Why normalised FCF: in a universe defined by "price at multi-year lows",
TTM FCF is depressed by the same shock that broke the price, so screening
on trailing FCF yield systematically excludes the recoverable names. We
use mean(last 5 fiscal-year FCF) over the CURRENT market cap instead.

## Auction/breakout overlay

`auction_overlay.py` layers a Dalton (Market Profile) auction read on top
of the shortlist, from daily OHLCV only, on a monthly -> weekly -> daily
hierarchy with the weekly leg weighted heaviest (50/30/20). Per ticker it
computes volume-profile value (POC / 70% value area), value migration,
13-week bracket breakout + acceptance vs rejection, failed auctions at
the lows (probe under a 26-week low, bought back, never revisited),
weekly one-timeframing, compression, up/down volume confirmation,
auction efficiency, structural destination/invalidation with gross RR,
and friction estimates (Corwin-Schultz spread, Amihud) so chart RR can
be sanity-checked against trading cost.

```bash
python auction_overlay.py --shortlist ../us_global_shortlist.csv \
    --out ../shortlist_auction.csv
python test_auction_overlay.py   # offline synthetic tests
```

`alignment_score` (0-100) rewards monthly/weekly/daily confluence;
`auction_label` classifies the weekly state (accepted_breakout,
failed_auction_low, breakout_unconfirmed, rejection_at_highs, balance).

## Tests

The computational core (label matching, 200w-low distance, FCF/buyback/
net-debt extraction, scoring) is validated offline against synthetic
yfinance-shaped frames — no network needed:

```bash
python test_yf_screen.py
```

## Notes for long runs in cloud sessions

Cloud session containers are ephemeral. Checkpoints (`.ckpt_*.parquet`)
land in the working directory and make `--resume` cheap, but they are
git-ignored — if a full-universe run matters to you, commit/push the
output CSV before the session idles out.
