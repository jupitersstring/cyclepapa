# Qullamaggie Audit — Comprehensive Framework

Sources cross-referenced:
- https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/
- https://qullamaggie.com/how-to-master-a-setup-episodic-pivots/
- https://qullamaggie.com/some-good-tweetstorms/
- https://qullamaggie.com/nasdaq-comparison-late-90s-vs-today/
- https://qullamaggie.com/natural-gas-multibaggers/

## Setup 1 — Continuation Breakout

### Prior leg (the "big move")
- 30–100%+ rally in **past 1-3 months** (not 6+)
- Duration of the leg: "a few days to a few weeks"
- Universe scan: stocks ranked **top % gainers over 1-month, 3-month, 6-month** windows (multi-window persistence)

### Base / consolidation
- 2 weeks to 2 months
- Higher lows, tightening range
- Volume drying up

### MA surf (defining feature)
- Price "surfs the rising **10-day and 20-day SMA**, sometimes the 50-day"
- NOT the 30-week MA (that's Weinstein)
- "We always use the 10/20 SMA as our guide on the leading momentum stocks"

### Tightness criterion
- **ADR (Average Daily Range %)** is the measure, not weekly ATR
- Stop should not be wider than 1× ATR or **1.5× ADR**
- Implied ADR ≤ ~5% for the setup to work

### Entry
- Range expansion breakout from consolidation
- Buy on opening-range highs of 1-min / 5-min / 60-min candle
- Position scales added through the day if it acts well

### Stop
- Lows of the day
- Never wider than 1× ATR or 1.5× ADR (i.e. cap risk to ~5-7% if ADR ~5%)
- After breakout proceeds 3-5 days: sell 1/3-1/2, move stop to breakeven, trail with 10/20-day SMA

### Position sizing
- 10-20% of account per trade
- Risk per trade: 0.25-1% (rarely > 1%)
- Max 30% in any single stock/ETF overnight

---

## Setup 2 — Episodic Pivot (EP)

### Catalyst
- Gap up ≥ **10%**
- 5 catalyst families: political/regulatory, FDA/biotech, contracts, **earnings/guidance**, sector momentum

### Volume
- Massive volume near open
- "Stock should trade the average daily volume in the first 15-20 minutes"
- Premarket volume preferred (gives confirmation)

### Fundamentals (earnings EPs)
- "Triple-digit YoY EPS and sales growth" ideal; mid/high double-digit works
- Many EPs are pre-revenue but high-sales-growth
- **Big analyst beat** + guidance raise
- **Stock should NOT have rallied past 3-6 months** (surprise factor critical)
- "Best EPs are on stocks that have gone sideways for 3-6 months or more"

### Entry
- 1-min / 5-min / 60-min ORH
- Add through the day if acting well

### Stop
- Lows of the day
- ≤ 1× ATR or 1.5× ADR

### Holding
- "Multi-month moves"; expect to hold weeks to months
- Trail with 10-day or 20-day SMA after surpassing initial stop

---

## Setup 3 — Parabolic Short

### Exhaustion criteria
- Up 50-100%+ in days (large cap)
- Or 300-1000%+ (microcap)
- 3-5+ consecutive up days

### Entry
- Opening range LOW (short)
- OR: wait for first red 5-min candle into VWAP — "VWAP fail" = entry
- Don't be early — let amateurs get squeezed

### Stop
- Highs of the day
- OR reclaim of VWAP if entered on VWAP fail

### Target
- 10-day or 20-day SMA (where the bounce usually happens)

### R/R
- 5-10× risk-reward (vs. 10-20× for breakouts)

---

## Quant-codifiable filters

The screener can capture (without intraday data):

| Element | Daily-bar proxy |
|---|---|
| Prior leg 30-100% in 1-3 months | Best N-day move (N=5,10,15,20,30) in last 90 trading days ≥ 30% |
| Top % gainer universe | 1m + 3m + 6m return percentile rank ≥ 70th |
| Consolidation 2w-2mo | Days since leg-end ∈ [10, 60] |
| Higher lows, tightening | Local lows trend up + range contracts in last N bars |
| 10/20 SMA surf | Price > 10SMA > 20SMA + both rising over last 10 bars |
| ADR tightness | 20-day ADR ≤ 6% |
| Pre-breakout | Within ~5% of consolidation high but not yet breaking |
| Volume dry-up | Last 5d vol < earlier base vol |
| EP gap | (open / prev_close − 1) ≥ 10% with above-avg volume |
| EP pre-EP sideways | 6-month range ≤ 15% before the gap day |
| EP fundamental | rev_g ≥ 0.25 (proxy for high growth) |

Intraday entries (ORH 1m/5m breakouts, VWAP fails) cannot be screened from daily bars, but daily-bar setups identify the candidates.

---

## Our previous implementation gap

The old `prebreakout_screen.py`:
- ✘ Uses 30-week MA (Weinstein), not 10/20-day SMA
- ✘ Requires 6m return ≥ 25% — misses 1-3 month explosive movers
- ✘ Uses ATR (weekly bars) — not ADR (daily)
- ✘ No multi-window % gainer ranking
- ✘ No EP screen at all
- ✘ No parabolic short screen

**Both old + new screens now coexist** — old as Weinstein/O'Neil hybrid, new files (`qullamaggie_screen.py`, `episodic_pivot_screen.py`) for proper Q.
