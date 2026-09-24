# OTC book — hand review (2026-09-24)

I read every tab with the FMP financial panel alongside. ✔ = fixed in this pass.

## Errors found

| Tab | Error | Status |
|---|---|---|
| Cash Shells | Net cash came from SEC XBRL frames, which missed most debt. Portsmouth Square, a levered hotel owner, showed as a cash shell. Same root cause as the main book's Payoff Geometry | ✔ debt cross-checked against FMP `totalDebt` (3,033 tickers corrected) |
| US Net-Nets | FMP data artefacts among the top names: Escalon (net debt "17,442% of mcap"), Eagle Pharmaceuticals (market cap inconsistent with shares), Actelis / CreateAI (FCF yield > 100%). LianBio is a liquidating company, so it's a net-net by construction | Flagged in the financial read; screen still admits them. Fix: exclude `mcap_suspect` names and liquidations |
| US Deep Value | Bank of Utica appears twice (BKUT and BKUTK); Suntex's market cap is inconsistent with its share count | Open: dedupe share classes; exclude `mcap_suspect` |
| OTC Intent | Foreign ordinary and ADR lines of the same company listed twice (Kansai KAEPF/KAEPY, BAT BTDPY/BTDPF) | ✔ deduped by company and by identical evidence |
| OTC Intent | Foreign buyback amounts are in local currency (JPY, HKD) but market cap is in USD, which inflated "size" | ✔ size for foreign lines uses % of shares outstanding only |
| Financial read | Foreign F-share lines report inconsistent share counts across periods ("Kansai diluting 25%/yr"); investment companies' revenue is fair-value income | ✔ flagged and suppressed; banks read on P/B / P/E / ROE |
| All tabs | ~10 of the top names in each screen had no FMP financials at all (GGLT, TOR Minerals, Bank of Utica, Kaanapali) | ✔ financial universe now includes the full OTC quote store (17,035 names) |

## What a reader still can't answer

1. **Can I trade it?** The tier column is a liquidity band, but there is no
   bid/ask spread, share count in the float, or broker availability. Many names
   trade under $5k a day.
2. **Is the net-net real?** NCAV quality isn't assessed: receivables and
   inventory haircuts, related-party assets, going-concern language.
3. **Who controls it?** Controlling holders, going-dark risk and the chance of a
   squeeze-out decide whether the discount closes. The Going Dark tab has
   insider %, but the screens don't.
4. **Will management act?** Now partly answered: the OTC Intent tab and the
   "Mgmt intent" column. That language predicts action (top-decile lift ~1.9×,
   weaker for press releases), not the re-rating.
5. **Foreign OTC:** screened on ratios only. The primary-listing liquidity and
   the ADR ratio aren't shown.

## Improvements (priority)

1. Exclude `mcap_suspect` / `implausible` names from the balance-sheet screens,
   and dedupe share classes (BKUT/BKUTK).
2. Add float, spread and dollar-volume capacity per name.
3. Add a controlling-holder / insider-ownership column to every screen.
4. Flag liquidating companies (LianBio) as a separate "liquidation value" setup.
