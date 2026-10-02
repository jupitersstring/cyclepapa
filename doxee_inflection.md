# Doxee S.p.A. (DOX.MI) — FCF inflection case study

Worked example of the framework on Doxee, Italian SaaS / customer-experience
document-management software. Mkt cap €54m, EV €68m, price €4.64 (May-26).

## The annual trajectory (€m)

| Year | Revenue | YoY | EBITDA | EBITDA margin | CFO  | CapEx | FCF   | Net debt | ND/EBITDA |
|------|---------|-----|--------|---------------|------|-------|-------|----------|-----------|
| 2021 | 21.48   |  –  |  5.72  | 26.6%         | 3.69 | -4.06 | -0.37 |   2.63   | 0.5x      |
| 2022 | 24.62   | +15% |  4.05  | 16.4%         | 4.48 | -6.81 | -2.33 |  13.46   | 3.3x      |
| 2023 | 26.71   |  +8% | -0.70  | -2.6%         | 1.63 | -7.45 | -5.81 |  19.53   | n.m.      |
| 2024 | 28.06   |  +5% |  2.99  | 10.6%         | 2.24 | -3.67 | -1.43 |  17.01   | 5.7x      |

The 2022-23 period was a heavy capitalised-software investment cycle: CapEx
ran at ~28% of revenue, EBITDA collapsed (a classic SaaS reinvestment bust),
and FCF went deeply negative funded by debt (net debt 2.6 → 19.5 in 24 months).

In 2024 the cycle reversed:

* **CapEx halved** — €7.45m → €3.67m, back to ~13% of revenue (2021 norm).
* **EBITDA flipped positive** — −€0.70m → +€2.99m (margin -3% → +11%).
* **FCF burn collapsed** — −€5.81m → −€1.43m (a +€4.38m swing).

## What the framework flags

Output of `fetch_ticker('DOX.MI')` from `yartseva_db.py`:

| Signal                         | Value     | Read                                      |
|--------------------------------|-----------|-------------------------------------------|
| `ebitda_inflection`            | **1**     | YoY sign-flip up: -€0.7m → +€3.0m          |
| `cfo_inflection`               | **1**     | OCF YoY positive after a negative-trend year |
| `fcf_inflection`               | **1**     | FCF less-negative YoY (improvement, not yet positive) |
| `rev_inflection`               | 0         | Sales never went negative                 |
| `ebitda_yoy`                   | **+527%** | from a small negative base                |
| `fcf_yoy`                      | +75%      | improvement vs prior loss                 |
| `ebitda_accel`                 | **+6.44** | huge positive acceleration                |
| `fcf_accel`                    | +2.25     | acceleration in FCF improvement           |
| `cash_conversion` (CFO/EBITDA) | 0.75      | reasonable                                |
| `ebitda_margin_delta_yoy`      | +13.3pp   | margin recovery                           |
| `roce`                         | −8.2%     | EBIT still negative on heavy D&A          |
| `net_debt_ebitda`              | **5.7x**  | the gating risk                           |
| `ev_sales` / `ev_ebitda`       | 2.4x / 22.8x | EV/EBITDA elevated on still-depressed E   |
| `fcf_yield`                    | −2.7%     | will flip on FY25 inflection if it lands  |

**Important nuance on the FCF inflection flag.** The script's flag is
"YoY growth in FCF flipped from ≤0 to >0", so a swing from −€5.81m to
−€1.43m fires it (because (-1.43 − (-5.81)) / 5.81 = +75%). Doxee is
**not yet FCF-positive**; the flag is signalling "the trough is in", not
"first positive print". On the current trajectory FY25 should be the
first positive-FCF year.

## What's already priced in

* `price_yoy` = **+150%** — the stock went from €1.28 (Nov-24 low) to
  €4.64 today, a 3.6x move that began *just as* the FY24 numbers became
  visible.
* `ev_sales_change_yoy` ≈ **+139%** — multiple expansion has already
  happened.
* `not_priced_in_score` = **+0.04** — barely positive. Most of the easy
  re-rating is in the price.
* But `price_minus_ebitda_yoy` = **−3.76** — EBITDA growth (+527%) still
  ran far ahead of price (+151%), so on the operating-leverage axis the
  price has not yet caught the fundamentals fully.

## Yartseva composite

`yartseva_score = 0.244` — middling, despite the clean inflection. Drags:

* Top-line growth modest (+5%).
* ROCE still negative (D&A from prior capitalised spend weighing on EBIT).
* Net debt / EBITDA at 5.7x — leverage is the dominant risk and caps the
  composite.
* The PEG-like valuation factor reads cheap-ish on EV/Sales but the model
  punishes the +5% growth.

## The actionable read

Doxee is a textbook **post-trough inflection**, not a virgin multibagger:

1. The framework correctly tags the EBITDA / CFO / FCF inflection.
2. The market has already priced ~3.6x of recovery — this was a "fast
   money" trade for those who caught the FY24 print.
3. Re-rating from here is gated by three things observable in the next
   two prints: **(a)** FCF crossing into positive territory in FY25,
   **(b)** net debt / EBITDA back below 3x, **(c)** EBITDA margin
   continuing toward 16%+ as software amortisation rolls off.
4. The Yartseva composite (0.24) reflects the residual leverage risk and
   modest top-line — appropriate for a "second-leg" position rather than
   a full-conviction starter.

## How to reproduce

```bash
python -c "
import sys; sys.path.insert(0, '.')
from yartseva_db import fetch_ticker
import dataclasses, json
row = fetch_ticker('DOX.MI', {
    'name': 'Doxee S.p.A.',
    'sector': 'Information Technology',
    'industry': 'Software',
    'market_cap': 'Micro Cap',
    'currency': 'EUR',
})
print(json.dumps(dataclasses.asdict(row), indent=2, default=str))
"
```
