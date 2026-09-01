# The Anthropic Incorporation Chart — Silas's Substack Post vs Our Engine

Source: "The Anthropic Astrology Incorporation Chart," Profit With The Planets
Substack, 2026-08-29 (full text extracted via curl; reveals she now publishes
on Substack — a source missed in the earlier corpus crawl). She calls it "the
biggest cluster of financial astrology transits I have ever seen."

## Reverse-engineering her chart date

She never states the incorporation date. Solving from her transit anchors
(Pluto conj chart Saturn "exact 10 January 2027"; the 2028-01-26 Aquarius
eclipse "conjunct the Sun exact") against swisseph:

**2021-01-25** (midday, angles unfixed — her own caveat) fits with combined
error 0.20°:

| Point | Position | Anchor check |
|---|---|---|
| Sun | 5.95 Aqu | 2028-01-26 eclipse at 6.03 Aqu → conj **0.08°** ("exact" ✓) |
| Saturn | 4.53 Aqu | Pluto 2027-01-10 at 4.65 Aqu → **0.12°** ("exact" ✓) |
| Jupiter | 8.56 Aqu | Pluto reaches it 2028 ✓ |
| Mercury | 24.36 Aqu | (4-planet Aquarius stellium) |
| Uranus | 6.78 Tau | **square Sun 0.83°**, sq Jupiter 1.79, sq Saturn 2.25 |
| Neptune | 19.08 Pis | domicile |
| Moon | 29.03 Gem | 29° critical degree |

## Validating her nine claimed transits

| Her claim | Our exact crossings | Verdict |
|---|---|---|
| Pluto conj Saturn: Mar+Jul 2026, exact 10 Jan 2027 | 2026-03-02, 2026-07-18, **2027-01-08** | ✓ within 2 days |
| Pluto conj Sun: Mar 2027, through 2027-28 | 2027-02-23, 2027-07-31, 2028-01-01 | ✓ (she rounds Feb 23 → "March") |
| Pluto conj Jupiter: 2028 into 2029 | 2028-04-07, 2028-06-14, 2029-02-03, 2029-09-01, 2029-12-08 | ✓ — actually five passes, deeper into 2029 than she says |
| Pluto sq Uranus: Mar + Aug 2027 | Pluto crosses 6.78 Aqu (the square point) alongside the Sun passes | ✓ |
| Pluto stations Oct 2026 "on the MC" | Pluto Dx station 2026-10 at 3.07 Aqu | plausible for a midday MC in early Aqu (angles unfixed) |
| 2027-08-02 eclipse opp Sun/Saturn/Jupiter | opp Jupiter **1.44°**, opp Sun 4.05° (wide — she flags wideness herself) | ✓/partial |
| 2028-01-26 eclipse conj Sun exact + Saturn + Jupiter | conj Sun **0.08°**, Saturn 1.50°, Jupiter 2.53° | ✓ |

Fourth external cross-validation of practitioner ephemeris claims against our
engine (after GME Mars 18-Aries, AAPL Uranus ~25-Scorpio, and the
Saturn-Neptune 2026 conjunction) — all agree.

## The sector-key read (our contribution)

Anthropic is an AI company. Compendium AI signature: **Uranus ∧ Mercury ∧
Aquarius** (experimental tier); dual-ruler doctrine gives Aquarius BOTH
Saturn (classical) and Uranus (modern).

The incorporation chart is **maximally AI-loaded under the dual-ruler rule**:

- **Saturn (classical Aquarius ruler) in Aquarius = its own domicile,
  conjunct the Sun 1.42°** — the archetype's traditional ruler dignified and
  fused to company identity.
- **Uranus (modern Aquarius ruler / AI planet) square the Sun 0.83°** — the
  modern ruler in tight hard contact with the same identity point.
- **Mercury (AI/data ruler) in Aquarius**, days from its retrograde station
  (news-sensitivity flavor, same family as MRNA/GME though not within our
  strict station threshold on the 25th).
- Four planets in Aquarius: the *sign of the industry* holds the Sun, both
  benefic/structural rulers and the messenger.

And the entire "biggest cluster she has ever seen" reduces to one clean
mechanism in our key-to-lock terms: **transiting Pluto — now in Aquarius —
walking the loaded Aquarius stellium degree by degree** (Saturn 4.5° → Sun
6.0° → Jupiter 8.6°, 2026→2029), squaring Uranus en route because natal
Uranus squares the stellium natally, while the Aquarius/Leo eclipse series
strikes the same axis (Jan 2028 exact on the Sun). One slow planet + one
loaded sign = nine "separate" transits. The lock is the stellium; Pluto is
the key, and it turns four times.

Her two-scenario read (Pluto-on-MC = BIG institutional money into the IPO,
or the IPO pulled entirely) is faithful Pluto doctrine — same
conjunction-wildcard logic as her NVDA precedent ("Nvidia had this transit
in its IPO chart when it became huge").

## What this means for the framework

1. **Incorporation ≠ IPO chart** — her doctrine and ours agree. If Anthropic
   lists (~late Sep/early Oct 2026 per the post's reporting), the tradeable
   chart is the first-trade chart, which cannot exist until listing day.
   Listing into 3-25 Oct puts the IPO chart inside BOTH Venus retrograde and
   Mercury retrograde in Scorpio — flagged bearish-natal by every rule in
   this repo; a listing after 25 Oct would carry a very different chart.
2. **The IPO chart, when it exists, should be run through sector_screener.py
   on day one** — with Pluto in early-mid Aquarius for years, any listing
   date gives Anthropic a natal Pluto placement that transiting eclipses in
   Aquarius (2027-02-06 at 17.6 Aqu; 2028-01-26 at 6.0 Aqu) will strike.
3. **Model note**: our sector-loading scores planet dignity but not
   *sign-emphasis of the archetype sign* (four planets in Aquarius adds
   nothing directly). The compendium's AI signature explicitly includes
   Aquarius; a sign-emphasis term (+per-planet-in-archetype-sign, tier
   experimental) is the natural v3 upgrade.
4. Silas corpus update: she has a Substack (profitwiththeplanets.substack.com)
   with markets-facing essays; the earlier site crawl missed it.

## Unverifiable / caveats

- All corporate news in her post (S-1 timing, valuations, settlements,
  Pentagon dispute, the export-control item) is her reporting; none of it is
  verifiable from this sandbox and none of it is needed for the astrological
  validation above.
- Midday chart: the MC-based claims (Pluto-on-MC, station "on" the MC) are
  soft; everything planet-to-planet is time-independent to ~0.5° and fully
  validated.
- Conflict-of-interest disclosure, in the spirit of the repo's honesty
  standards: this analysis of Anthropic's chart was performed by Anthropic's
  own model. The ephemeris does not care, and neither did we.
