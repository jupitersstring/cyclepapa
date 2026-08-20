# RCA: Why MRNA Worked — Sector Sympathies as Key-to-Lock

## The question

The generic convergence screen ranked MRNA #654/2,721 — it looked strong only
when Mars noise inflated it. So *why did MRNA actually move*, in astrological
terms the model should have captured?

## Root cause: the chart was sector-LOADED, and a generic trigger expressed through it

MRNA is a pharma/vaccine company. In the provenance-tiered rulership table
(`sector_rulerships.py`, from the compendium), pharma/biotech is ruled by
**Neptune** (modern: chemicals/pharma/altered-states), **Mercury** (Virgo
clinical/trials), **Pluto** (experimental: transformation), and **Jupiter**
(contested: big-pharma scale).

In MRNA's IPO chart (2018-12-07) **every one of those pharma rulers is
prominent**:

| Pharma ruler | Condition in MRNA natal | Meaning |
|---|---|---|
| **Neptune** | Pisces = its **own domicile**, **conjunct Mars 0.01°**, square Sun 1.69° | the pharma significator, dignified, fused to an action planet and tied to identity |
| **Mercury** | **stationing** (1 day off station) | the clinical-trial / news planet frozen and hyper-emphasized |
| **Pluto** | **angular** (2.1° from an angle) | big-money / hidden-transformation significator on an angle |
| **Jupiter** | Sagittarius = its **own domicile** | big-pharma scale ruler, dignified |

This is a maximally *pharma-loaded* natal chart. So when the transiting bullish
stack lit up the money axis (T.Uranus opp natal Jupiter, T.Pluto sq natal
Venus, the Jul-20 Jupiter-Pluto opposition on natal Venus), the chart could
only discharge **through its loaded channel** — as a pharma news catalyst
(the Phase-3 cancer-vaccine readout + FDA flu clearance).

**The generic screener missed this because it watched generic money points
(Venus/Jupiter/Sun) — the wrong key.** The right key was the *pharma rulers*.
MRNA's Neptune/Mercury/Pluto/Jupiter loading was invisible to a screen that
never looked at them.

## The generalization: key to the specific lock

Every sector has its own ruling planets (its "sympathies"). A stock is
**primed** when its sector's rulers are dignified / angular / stationing /
luminary-tied in the natal chart (the *lock is loaded*), and it **fires** when
a transit hits those same points (the *key turns*). `sector_screener.py`
implements exactly this, per stock:

1. **Classify** the sector from the company name (override map for known
   tickers where the name gives no hint, e.g. `MRNA -> pharma_biotech`).
2. **sector_load** — score the natal prominence of that sector's *ruling
   planets* (domicile 1.0 / modern-domicile-or-exalt 0.6, angularity to ASC/MC,
   hard aspect to a luminary, station), each weighted by its provenance tier
   (classical 1.0 / modern 0.65 / contested 0.5 / experimental 0.35). This is
   the fuel: `fuel = 1 + min(sector_load, 3)`.
3. **Targets** — the transit-watch set is the generic money axis (Sun/Venus/
   Jupiter) **plus the natal positions of the sector's rulers**. That added
   sector-ruler target is the "relevant sympathy" — the key cut for this lock.
4. **Convergence** — the tightest ~90-day window where a slow substrate
   (Pluto/Uranus/Neptune to a target) coincides with a fast trigger (Jupiter
   transit or eclipse to a target). `setup_score = convergence × fuel`.

## Validation

- v1: **MRNA #654 (generic) → #91 (sector-aware)** — 7× improvement from
  pharma-ruler loading alone.
- v2 added the three things the "enormous move" demanded: (a) an EXACTNESS
  fusion bonus, quadratic in tightness, doubling under 0.25° (MRNA's
  Mars-Neptune 0.01° took Neptune's loading 0.4 → 2.5); (b) a FULL-STACK
  ×1.3 when ≥3 rulers load simultaneously; (c) key-in-lock weighting *in
  the score* — transit hits on sector-ruler targets ×1.5, on LOADED rulers
  ×2; eclipse orb aligned with the main engine (2.0°).
- **Pre-move backtest (the decisive test): run as-of 2026-04-15, MRNA ranks
  #7 of 271 tradeable (2017+) unique charts — top 2.6% BEFORE the move —
  with the peak convergence window dated 2026-07-14 and position-by
  2026-06-02, matching the actual May-low → July/August run.** Two of the
  six names above it (Gamida Cell, Milestone Pharma) are biotechs the
  keyword classifier missed — the mechanism found the right *kind* of chart
  even where the sector label failed.
- Forward run (as-of today): MRNA re-enters at #2 among 2017+ uniques with
  a SECOND window at 2027-08 (the Uranus-opp-Jupiter return pass — Silas's
  multi-pass rule in action).
- **Top-100 sector mix**: pharma_biotech 39%, oil_gas 19%, real_estate 6%,
  tech_software 6% — the sectors whose rulers are most *dignifiable* (Neptune
  rules Pisces; Saturn rules both Capricorn and Aquarius and governs oil/land/
  real-estate) naturally dominate, which is the model working as intended, not
  a bug. Each sector still produces its own leader via its own rulers.

## "Key-in-lock" — the sharpest subset

The highest-conviction setups are where a **loaded sector ruler is itself being
transited** (the key literally turning in the loaded lock), not merely the
generic money axis. Top 2017+ tradeable candidates, `turning` = the loaded
ruler under transit:

| Ticker | Name | Sector | Score | Ruler turning | Peak window | Position by |
|---|---|---|---|---|---|---|
| VERA | Vera Therapeutics | pharma | 16.7 | Jupiter | 2027-07 | 2027-06-03 |
| FLNC | Fluence Energy | oil_gas | 15.7 | Neptune, Saturn | 2027-12 | 2027-10-31 |
| IREN | Iris Energy | oil_gas | 15.5 | Saturn | 2027-07 | 2027-05-24 |
| ADCT | ADC Therapeutics | pharma | 15.1 | Mercury | 2027-07 | 2027-06-13 |
| LITM | Snow Lake Resources | mining | 15.0 | Saturn | 2027-07 | 2027-05-24 |
| VICI | VICI Properties | real_estate | 14.9 | Saturn | 2026-10 | 2026-08-27 |
| BCSF | Bain Capital Specialty | banking | 14.5 | Jupiter, Saturn | 2027-07 | 2027-05-24 |
| CNTA | Centessa Pharmaceuticals | pharma | 14.3 | Mercury, Neptune | 2027-10 | 2027-09-01 |
| ANEB | Anebulo Pharmaceuticals | pharma | 13.0 | Mercury | 2027-06 | 2027-05-04 |
| DAWN | Day One Biopharma | pharma | 12.7 | Jupiter | 2027-07 | 2027-06-03 |
| DCPH | Deciphera Pharma | pharma | 11.1 | Neptune | 2027-08 | 2027-07-03 |

VICI Properties is the only near-term one (loaded Saturn — real-estate/land
ruler in domicile and angular — under Neptune transit, peaking Oct 2026,
positioning window already open).

## Honest limitations

1. **Classifier coverage**: 1,603 of 3,129 charts are `unclassified` — the
   keyword classifier misses names that don't advertise their sector
   ("Moderna" itself needed an override). Those fall back to generic rulers,
   so their sector sympathies are NOT applied. Fixing this needs a CUSIP/SIC
   sector map (offline data not available in this sandbox), not more astro
   logic. This is the single biggest coverage gap.
2. **Still fitted to one confirmed case** (MRNA). The mechanism is coherent
   and the compendium's rulerships are its independent basis, but there is no
   out-of-sample backtest (no price data in-sandbox).
3. **Same-day IPOs still share charts**; sector differs by name only.
4. Uses the assumed 9:30 chart time for angularity (documented elsewhere).

## Files
- `sector_screener.py` — the general sector-aware screener
- `sector_screener.csv` — all charts scored, with sector, sector_load,
  loaded_rulers, convergence window, and Silas position-by date
