# Archetype backtest — what history says, and what it can't

Point-in-time event study over 525 events (2022-06-01..2025-06-30). monster = +100%/12m; big loss = -50%/12m. Confirmation = >=+20% first-month drift (deep_research showed it is the edge).

## Backtestable (catalyst-anchored) archetypes

| archetype | n | all: median | win% | loss>50% | confirmed: mean | confirmed: monster% |
|---|---|---|---|---|---|---|
| asset_sale_monetization | 33 | -4% | 46% | 12% | +11% | 0% |
| tender_offer_squeeze | 8 | -28% | 12% | 25% | +0% | 0% |
| sub_cash_buyback | 22 | -15% | 36% | 14% | +35% | 25% |
| stated_unlock_triangulated | 56 | -5% | 46% | 27% | +13560% | 38% |

**Read with care — the samples are small.** Slicing 417 events by archetype and then by confirmation shrinks each cell to n≈1–40; the confirmed sub-cells are n=0–4, so their means (e.g. stated-unlock confirmed +324%) are driven by one or two names (SYRE +975%) and are DIRECTIONAL, not estimates. What is robust across the whole study still holds here: the RAW archetype medians are weak/negative (asset-sale +0%, tender −26%, sub-cash −15%, stated-unlock −12%), and the money is in the confirmed tail — but the per-archetype confirmed numbers need a wider window to trust. Top realized trades per archetype:
- **asset_sale_monetization**: VSTM +147%, NTRP +100%, OPRT +92%, UPXI +84%
- **tender_offer_squeeze**: BDSX +25%, CYH +-13%, TBPH +-15%, RYAM +-26%
- **sub_cash_buyback**: MYRG +150%, AKA +149%, PEV +130%, PFIE +79%
- **stated_unlock_triangulated**: INRE +107259%, SYRE +975%, IRWD +496%, SVT +340%

## NOT point-in-time backtestable (and why)

These need historical fundamentals or fund-flow we don't have; listing what each would require rather than fabricating a survivorship-biased number.

- **coiled_spring_delever** — needs point-in-time D/E + rising operating income (no historical fundamentals); could add a 'reduce leverage' 8-K event scan.
- **hidden_asset_realization** — needs the point-in-time credit-agreement asset-sweep scan + a small-levered balance sheet; not reconstructable historically.
- **forced_seller_exhaustion** — needs historical N-PORT fund-flow (forced selling); no EDGAR event phrase and no historical flow store.
- **asset_sale_latent** — ANTICIPATORY (the setup BEFORE the sale is announced) -- by definition has no event to anchor; needs a FORWARD tracking study (snapshot today, check for a sale over the next 6-12 months).
- **tender_target_latent** — ANTICIPATORY (take-private candidate before any bid) -- same: needs forward tracking, not a backward event anchor.

## The honest path to backtesting the rest

1. **Coiled-spring delever** is the most sourceable gap: add a 'reduced net leverage' / 'repaid $X of debt' 8-K event scan and anchor a forward-return study on it (same machinery as the catalyst backtest).
2. **The latent/anticipatory archetypes** can only be validated FORWARD: snapshot today's members and track, over 6-12 months, whether they actually announce the sale/tender and how they perform — a prospective hit-rate study, not a backward one.
3. **Balance-sheet archetypes** (sub-cash, hidden-asset, forced-seller) need a point-in-time fundamentals/flow store; the frames store is current-only, so this is a data-acquisition task.
