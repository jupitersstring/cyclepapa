# Qullamaggie Audit — Methodology Gap

Source: https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/

## Q's three setups (from the blog)

### 1. Continuation Breakout (the "Qullamaggie" pattern)
- **Prior leg**: 30-100%+ move in the past **1-3 months** (days-to-weeks duration)
- **Universe scan**: top % gainers over **1-month, 3-month, 6-month** periods
- **Consolidation**: 2 weeks to 2 months, orderly pullback with higher lows, tightening range
- **MAs surfed during consolidation**: rising **10-day SMA** and **20-day SMA** (sometimes **50-day**)
- **Entry**: actual range-expansion BREAKOUT out of the consolidation (intraday on 1-/5-/60-min)
- **Stop**: lows of the day; cap at the stock's ATR/ADR (~5%)
- **Risk per trade**: 0.25-1%
- **Position management**: scale out 1/3-1/2 after 3-5 days, trail with 10-/20-day SMA
- **Targets**: 10-20×+ initial risk

### 2. Episodic Pivot (EP) — earnings gappers
- Gap up 10%+ on earnings/news catalyst
- Large premarket or open volume (often 1 ADV in first 15-30 min)
- Triple-digit EPS/revenue growth ideal
- Stock should NOT have rallied much in prior 3-6 months (surprise factor)

### 3. Parabolic Short — mean reversion
- Stock up 50-100%+ in days (or 300-1000%+ for microcap) AND up 3-5+ days in a row
- Short on opening-range lows / VWAP fails
- Target: 10- or 20-day SMA

---

## Our `prebreakout_screen.py` vs Q

| Rule | Q says | We have | Verdict |
|---|---|---|---|
| Prior leg | 30-100%+ in **1-3 months** | 6m ≥ 25% AND 12m ≥ 30% | ❌ wrong window (too long) |
| Consolidation duration | **2w-2mo, variable** | Fixed 8 weeks | ⚠ rigid |
| MAs followed | Rising **10-day / 20-day / 50-day SMA** | 30-week MA (Weinstein) | ❌ wrong MAs entirely |
| Range expansion trigger | YES — wait for breakout | NO — we screen the basing phase | ⚠ different stage |
| Position near 52w high | implied | within 3-15% of 52w high | ✓ ok |
| Volume dry-up in base | YES | YES (last 4w < prior 13-26w) | ✓ |
| ATR-tightness | Stop ≤ ATR (~5%) | ATR < 3.5% | ✓ similar |
| MFI 40-65 | NOT in Q's framework | added by us | ⚠ extra |
| Episodic Pivot (EP) | Setup #2 | Not screened | ❌ missing |
| Parabolic Short | Setup #3 | Not screened | ❌ missing |

**Verdict**: our screen is closest to **Weinstein late-Stage-1** mixed with **O'Neil cup-with-handle near-high**, not the Qullamaggie continuation breakout. The defining Q features (10-/20-day SMA surf, scanning top % gainers, range expansion trigger) are absent.

## Plan

1. Build `qullamaggie_screen.py` — proper Q rules: top % gainers (1m/3m/6m), 10/20-day SMA surf, 2w-2mo flexible base, range expansion ready
2. Add `episodic_pivot_screen.py` — earnings gap detector
3. Keep current `prebreakout_screen.py` (relabel as "weinstein_prebreakout") — it IS a useful Weinstein/O'Neil hybrid
