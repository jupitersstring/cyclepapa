# Darvas Box Breakout Methodology (`darvas2_*`)

A weekly-bar implementation of Nicolas Darvas's box theory, rebuilt so that a
breakout can actually be *detected*. It identifies the most recent consolidation
"box" a stock has formed while pressing against its highs, and flags the moment
price closes up and out of that box on expanding volume.

This is the `darvas2_*` family of fields. It replaces a legacy detector
(`detect_darvas_box`) whose breakout flag was **structurally always false** —
see [Why "darvas2"](#why-darvas2-the-bug-it-fixes).

---

## 1. Inputs and timeframe

- **Bars:** daily OHLCV resampled to **weekly** bars, Friday-anchored
  (`resample("W-FRI")`). All box logic runs on weekly highs, lows, and closes.
- **Minimum history:** 12 weekly bars.
- **52-week high (`h52`):** the max weekly high over the trailing 52 weeks, used
  as the "pressing highs" precondition.

---

## 2. Step 1 — Build the boxes (frozen-ceiling forward scan)

The core idea: a box **ceiling** is a *fixed past swing high*, not a trailing
maximum. Once confirmed, it is **frozen** — later prices are allowed to exceed
it, and that exceedance is precisely what a breakout is.

**Ceiling.** Scan weekly highs left to right, ratcheting a candidate ceiling:

- If a later week's high exceeds the candidate by more than the tolerance
  (`> candidate × (1 + tol)`, `tol = 2%`), the candidate **ratchets up** to that
  new high and the counter resets.
- Otherwise, count the week as "non-exceeding." After **`n_confirm = 2`**
  consecutive non-exceeding weeks, the ceiling is **confirmed and frozen** at the
  candidate high.

**Floor.** From the frozen-ceiling bar, scan forward and ratchet a candidate
floor *down* on any low that undercuts it by more than `tol`. Stop when either:

- a weekly **close breaks above the ceiling** (breakout — floor left provisional), or
- `n_confirm` consecutive higher-lows confirm the floor.

Boxes are **retained even after price later breaks the ceiling**, so the breakout
remains visible. The scan continues past each frozen box, producing a stack of
boxes oldest → newest.

---

## 3. Step 2 — Select the active box

Walk the stack newest → oldest and pick the first box that satisfies all of:

- **Valid geometry:** `floor > 0` and `ceiling > floor`.
- **Pressing the highs (Darvas precondition):** ceiling is within **15%** of the
  52-week high (`ceiling ≥ h52 × (1 − near_52w)`, `near_52w = 0.15`). A box far
  below the highs is not a Darvas setup.
- **Not already run away:** price has **not** extended more than **10%** above the
  ceiling (`last ≤ ceiling × 1.10`, `overext_pct = 10`). If it has, that box is
  considered superseded/stale.

The box immediately older than the active one is retained as `prior_box_top`
(used for base-on-base detection).

---

## 4. Step 3 — Robust floor and derived metrics

The active box's floor is recomputed as the **true lowest low over the box span**
(`min(low[ceiling_bar : last])`) — what a chartist actually draws — rather than
the early-stopping guess from Step 1. This makes degenerate long boxes that hid a
deep drawdown fail the height gate instead of rendering a phantom shallow floor.

From the active box:

| Field | Definition |
|---|---|
| `darvas2_box_top` | frozen ceiling price |
| `darvas2_box_bottom` | true lowest low across the box span |
| `darvas2_box_height_pct` | `(top − bottom) / bottom × 100` — box tightness |
| `darvas2_box_length_weeks` | weeks from ceiling bar to the latest bar |
| `darvas2_pos_in_box_pct` | where the last close sits in the box, 0% = floor, 100% = top |
| `darvas2_dist_from_top_pct` | `(last − top) / top × 100`; **> 0 means broken out** |
| `darvas2_breakout_freshness_w` | weeks since the **first weekly close** above the ceiling (`0` = this week) |
| `darvas2_prior_box_top` | ceiling of the previous stacked box, if any |
| `darvas2_ceiling_at_52w_high` | ceiling within 15% of the 52-week high |
| `darvas2_vol_expansion` | latest weekly volume ≥ **1.3×** the mean of the last 30 weeks |

---

## 5. The breakout flag

`darvas2_breakout = True` when **all** of the following hold:

1. **Broken out but not overextended:** `0 < dist_from_top_pct ≤ 10` — the last
   close is 0–10% above the frozen ceiling.
2. **Fresh:** `0 ≤ breakout_freshness_w ≤ 4` — the breakout happened within the
   last 4 weeks (not a stale, long-ago break).
3. **At the highs:** `ceiling_at_52w_high` is true (within 15% of the 52w high).
4. **Sane box height:** `3% ≤ box_height_pct ≤ 35%` — tight enough to be a real
   base, not so tight it is noise, not so wide it is a trend leg.
5. **Real base length:** `box_length_weeks ≥ 3` — rejects 2-week noise boxes.

`darvas2_breakout_strong = darvas2_breakout AND darvas2_vol_expansion`
(the breakout is confirmed by a volume surge ≥ 1.3× the 30-week average).

---

## 6. Related flags (pre-breakout and structure)

| Flag | Meaning |
|---|---|
| `darvas2_tight` | Mature tight box at the highs: `length ≥ 4w`, `height < 15%`, ceiling at 52w high. A watch-list state. |
| `darvas2_tight_near_top` | Coiled and **not yet** broken out: at 52w high, `height ≤ 12%`, `length ≥ 4w`, last close in the **top 3%** of the box (`dist_from_top_pct ∈ [−3, 0]`), and no breakout yet (`freshness` is null). The "about to go" state. |
| `darvas2_base_on_base` | Stacked bases: a prior box exists, the current ceiling is **above** the prior ceiling, and the current box is `darvas2_tight`. Classic higher-box-on-box accumulation. |

---

## 7. Parameters (defaults)

| Parameter | Default | Role |
|---|---|---|
| `n_confirm` | 2 weeks | consecutive non-exceeding weeks to freeze a ceiling / confirm a floor |
| `tol` | 2% | ratchet tolerance for ceiling/floor moves |
| `near_52w` | 15% | how close the ceiling must be to the 52-week high |
| `overext_pct` | 10% | max extension above ceiling before a box is "superseded" |
| `vol_k` | 1.3× | volume-expansion multiple vs the 30-week average |

Breakout-flag thresholds (Section 5): breakout band `0–10%`, freshness `0–4w`,
height `3–35%`, length `≥ 3w`.

---

## 8. Why "darvas2" — the bug it fixes

The classic/legacy detector defined the box ceiling as a **trailing unbroken
maximum**. Under that definition the current close can *never* be above the
ceiling — the instant price exceeds it, the ceiling redefines upward to include
it. So a "breakout" (close above box top) was **impossible by construction** and
the flag was effectively always false.

`darvas2` fixes this by **freezing** the ceiling once confirmed and **retaining**
boxes after they are broken. The ceiling becomes a fixed reference that a later
close can genuinely exceed, so `dist_from_top_pct > 0` and a finite
`breakout_freshness_w` are real, detectable events.

---

## 9. Reading it in practice

- **`darvas2_tight_near_top`** → coiled at the top of a tight base, primed.
- **`darvas2_breakout` (freshness 0–1)** → just cleared the box this week or last;
  the actionable entry window.
- **`darvas2_breakout_strong`** → same, with volume confirmation.
- **`darvas2_base_on_base`** → higher box stacked on a prior box; accumulation.
- **`dist_from_top_pct` climbing past ~10%** → extended; the box is now stale and
  the setup is no longer "fresh."
