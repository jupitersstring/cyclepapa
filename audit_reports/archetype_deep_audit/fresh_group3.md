# Fresh Archetype Deep Audit — Group 3 (28 archetypes)

Fresh-eyes quality read of TOP-OF-BOOK representativeness + methodology soundness.
Ranked by each archetype's own ranking key (ETA, or the named score where one exists).
Already-guarded invariants (financials/REIT/utility leakage, net-cash levered stubs,
sub-$20M growth firers, roce<-5% survivability loss-makers, corruption, preferreds,
sub-$2M shells, clinical biotech in *fundamental* archetypes) are NOT re-flagged.

---

## NEEDS-WORK (lead)

### arch_oak_nav_discount — NEEDS-WORK
**Rep:** Top-of-book is operating securities houses + asset managers, not covered-NAV
closed-end/holdco discounts. 9 of 38 firers are brokers (Orient/Yuhwa/BOOKOOK/Hanyang/
Kyobo/**Daishin** Securities — the very names the code comment says to exclude); plus
Bangkok Commercial Asset Mgmt (nde 17.6, ev_sales 42 — a levered NPL operator).
**Method:** the broker/exchange exclusion regex runs against the *industry* field, but
every Asian securities house carries GICS industry `Capital Markets` (no `securit`/
`broker` token) so the exclusion never bites; meanwhile the positive `_nav_vehicle`
match on `capital market` sweeps them all in. Fix: run the exclusion against the
company **name** too (or a securities/broker flag), and tighten the positive set to
true fund/trust/holdco vehicles.

### arch_oak_order_conversion — NEEDS-WORK
**Rep:** 3798 firers (broadest of the group); top-10 is generic cheap profitable
small-caps — Dongwoo *Farm-to-Table*, James Warren *Tea*, Brook Crompton — businesses
with no order book at all, and identical to the oak_asset_floor / negative_ev top-10.
Nothing reads as backlog->revenue conversion.
**Method:** the lagging proxy (rev_accel>0 OR rev_yoy>0.05, + oper_lev, + ebitda up) is
so generic it = "any growing profitable cheap name," and rev_accel admits flat/declining
top lines (Takamatsu -2%, Brook Crompton flat). Restrict to backlog-relevant sectors
(Capital Goods / Construction & Engineering / Aerospace & Defense) or demand a much
stronger acceleration signal so the proxy actually selects order-driven businesses.

### arch_analyst_awakening — NEEDS-WORK
**Rep:** Top-of-book is a wall of pre-revenue clinical biotech — INMB (rev $50k,
ebitda margin -616x), AVTX (rev $59k), CLDX (rev $1.5M), VOR, VRDN, CSTL. "Analyst
awakening" here = analysts pricing binary drug pipelines, not an early re-rating of an
underappreciated *business*.
**Method:** the screen is pure analyst sentiment (rating + breadth + target upside) with
NO revenue floor, is_operating, or quality gate — and biotech is where coverage +
target-upside are structurally highest, so it dominates. (Not caught by the clinical-
biotech invariant because that guards *fundamental* archetypes; this one is sentiment.)
Add a minimal scale/quality floor (revenue >= $20M, exclude pre-revenue biotech).

### arch_tenbagger_path & arch_tenbagger_credible — NEEDS-WORK (pair)
**Rep:** Both books are dominated by **commodity miners** riding a one-year price surge —
China Gold Intl (+97%), Serabi Gold (#1 of "credible", +65%), Dundee Precious, Bosung
Power (+121%), Zhuzhou Smelter, Star Cement. A cyclical gold producer is not what a
practitioner means by a credible 10-bagger path (a scalable compounder).
**Method:** the arithmetic projects demonstrated revenue growth at a **heroic 18x
terminal P/E** onto businesses whose "growth" is mean-reverting commodity price. The
median-of-bases g10 tempers pure single-year spikes but sustained-CAGR miners still
clear it; the `credible` overlay (real cash / no dilution) does nothing about
cyclicality. Add a resource-cyclical damper or a durable-scalable-growth requirement,
and cap the terminal multiple for producers.

### arch_evsales_derating — NEEDS-WORK
**Rep:** Top-of-book is extreme one-year growth + cyclical/thematic names: Mining
Americas (+1093%), Integra Resources (+719%), PC Jeweller (+416%), Vireo (cannabis),
Orla/ITR miners, BioCryst. The "coiled spring / unpriced durable growth" thesis is
swamped by base-effect explosions.
**Method:** derate_gap = rev_yoy - stock_return with rev_yoy clipped only to +10 (i.e.
+1000%), so base-effect recoveries produce the largest gaps and top the score. Use a
median-of-bases growth (as tenbagger does) or an upper-growth cap, and add a durability
check so a single recovery year can't define the derate.

---

## MINOR

### arch_wolf_seal — MINOR
Rep: 2331 firers; ETA-ranked top-10 is generic cheap Asian microcaps, several with
flat/declining revenue (AWC, Michang -6%, IRC, Takamatsu) — not obviously "earnings
inflection bought on a post-earnings dip." inflection_print does real gating work but
ETA surfaces cheapness, not freshness of the inflection. Method: consider ranking these
by inflection recency/strength rather than raw ETA.

### arch_wolf_compounder — MINOR
Rep: mostly excellent — cheap, accelerating, cash-positive compounders (Medialink,
Kokusai, Kortek, Linkgenesis). Bad apple: **SOGP** (roce -96%, negative EV multiples)
fires because there is an op_margin>0 gate but no ROCE floor. Method: add a modest ROCE
floor so a capital-destroyer can't read as a "compounder."

### arch_liger_asset_backed — MINOR
Rep: **FPIP.ST (Formpipe)** tops it — a premium software name (roce 72%, ev_sales 3.3,
p_s 6.6) that is not "asset-backed" in any book sense; it clears only on net-cash +
pb<3. A few negative-ROCE names (TTEC, Genie). Method: pb<3 is too loose to enforce an
asset anchor — tighten toward pb<1.5 or require a book/NCAV floor.

### arch_liger_lagging_inflect — MINOR
Rep: names **at their 52-week high** fire (FPIP -0.3% off high, mixi -4%), contradicting
"quiet inflection the market hasn't processed." Method: the drawdown leg
(`flat_or_down | beaten_down 0.30`) is satisfied too easily via flat operating trend;
require an actual price lag (off-high or below moving average) for the "lagging" claim.

### arch_liger_neglected_survivor — MINOR
Rep: genuine neglected net-cash microcaps, but the top carries deep-negative-ROCE names
(MKTW -75%, Genie -22%, TTEC -10%). Unlike its sibling lagging_inflect, this screen has
**no `_roce_now_ok`** gate. Method: "survivor" is balance-sheet-defined here so it's
defensible, but a soft ROCE floor would stop capital-destroyers ranking at the top.

### arch_oak_deep_value — MINOR
Rep: core is right (deep sub-book + real cash + cash-generative). Slips: **RFT.AX**
(ebitda margin -49%, op -55%, roce -24%) and Time Watch (op -21%) appear in a screen
that explicitly requires ebitda_ttm>0 — suggests the gate's EBITDA source disagrees with
the displayed one. Method: verify the ebitda_ttm gate reads the same (fresh) EBITDA the
book displays.

### arch_weschler_levered_equity — MINOR
Rep: 954 firers of cheap, net-debt value stocks — broadly on-thesis, but the EV/mcap>=1.75
path admits only-mildly-levered names (Caleffi nde 0.65, HDC nde 1.31) that are not the
"heavily indebted high-torque stub" of the Valassis case. Method: require the EV/mcap
path to also clear a minimum nde (e.g. >=2) so convexity is real; the deleveraging leg
(oper_lev_any suffices) is soft.

### arch_asymmetric_assembly & arch_levered_inflection — MINOR
Rep: the strict conjunction genuinely narrows (155 / 411) and top names show the bad-
headline/better-economics signature. But `heavy_debt` via EV/mcap admits low-nde names
(JFIN nde 0.24, Abalance 0.31, Econocom 0.17) whose thin leverage undercuts the convex-
stub thesis; a few negative-op-margin names (China Primary Energy, Kothari). Method:
same EV/mcap-path nde-floor fix as weschler.

### arch_insider_conviction — MINOR
Rep: insider-buy signal is genuine and high-value; but the "value-oriented" leg is
near-non-binding — `fcf_yield>=0.03 | ev_ebitda<=15` passes almost every profitable
bank, so the pb<1.0 financials discipline is bypassed (FXNC fires at pb 1.48). A melting
nano (**ONCO**, ebitda margin -1627%, mcap $4.5M) slips in on NaN op_margin. Method:
make the value leg actually bind for financials, and tighten `_not_melting` to catch
NaN-op-margin nanos.

### arch_cheap_sales_scaler — MINOR
Rep: reads more as "cheap profitable grower" than "scaling *toward* profit" — most top
names are already solidly profitable (Medialink op 18%, Kortek 13%, IDIS 11%). Faithful
but the near_profit gate (ebitda>0 qualifies) drops the "un-re-rated pre-profit scaler"
distinctiveness. Method: optionally split the already-profitable from the crossing-over
cohort.

### arch_exceptional_evsg — MINOR (near NEEDS-WORK)
Rep: base-effect one-year explosions top the book — **Dong A Eltek (+234%, the exact
name wolf_compounder's comment guards against)** and BioArctic (+346%). Method: EVSG
mechanically rewards the highest growth; add wolf_compounder-style upper-growth cap
(rev_yoy<=1.5) or use median-of-bases growth.

### arch_growth_algo — MINOR
Rep: cheap FCF growers, faithful core; base-effect names (Dong A Eltek again) leak, and
the defining DLO legs (share-count -5% / FCF-per-share +30%) are still unenforced (soft
`not_diluting` only). Method: add the upper-growth cap; enforce the buyback leg as
coverage fills in.

### arch_negative_ev_value — MINOR
Rep: the very top (Dongwoo, Brook Crompton, Michang, China ITS — net cash 75-160% of
mcap) is exactly on-thesis. But the `pb<0.7` OR-leg inflates it to 4323 and many firers
are sub-book, not negative-EV — a mild label/scope stretch. Method: consider separating
the true negative-EV cohort from the sub-book cohort for the label to hold.

### arch_templeton_pessimism — MINOR
Rep: EV/normalized-EBITDA + near-5y-low + off-high core is faithful, but without an
earnings-depression/cyclicality signal it also catches cheap growers merely down from a
high (Dongwoo +9% rev, Z Holdings +22%). Method: add a trough/earnings-below-mid-cycle
condition so "maximum pessimism" reads on depressed earnings, not just a low price.

### arch_lynch_reward — MINOR
Rep: mostly recognizable quiet-progress names (Paylocity, Teradata, Dollar Tree, FTI).
Slip: **IMDX** (ebitda margin -1182%, ev_sales 72, revenue $4M) — a melting nano through
the coil/release legs on NaN op_margin (bypasses `_not_melting`). Method: tighten
`_not_melting` for NaN-op-margin / sub-scale names.

### arch_analyst_rerating_confirmed — MINOR (near NEEDS-WORK)
Rep: the 52w-high confirmation genuinely helps (NVDA is a clean confirmed re-rating), but
with no quality floor the top still carries loss-makers (CTS roce -26%/op -11%, NNBR
roce -6%) and a clinical biotech (SGMT, rev $2M). Method: add the same minimal scale/
quality floor proposed for analyst_awakening.

### arch_tax_efficient — MINOR
Rep: faithful narrow tax-structure screen (etr 3-15% + pretax>0 + op>0); Netease/Q2/
Pegasystems recognizable. China-heavy by construction (low-etr jurisdictions). A couple
of negative-ROCE names (MKTW -75%, IH -27%) pass for lack of a returns floor — consistent
with the narrow "structure not returns" intent, so left as MINOR.

---

## SOUND

### arch_oak_resource_leverage — SOUND
Tight (18 firers), thesis-representative: low-cost, high-margin, cash-rich Materials/
Energy producers bought on weakness (Anglo Platinum, Thor, Monument, Steppe, DRDGOLD).
Sector gate + net-cash + ebitda-margin>=0.25 + cash-yield + beaten-down all pull the
right way. No change needed.

### arch_oak_deleveraging — SOUND
nde 1-3 band + high FCF yield + material capital return (>=6%) + rising-EBITDA trajectory
is a faithful translation; top-of-book is recognizable (Comcast, Indian Oil, GP
Industries). The capital-return requirement is good discipline.

### arch_oak_asset_floor — SOUND
Genuine Graham-floor names: net cash >=40% (or NCAV>=80%) of mcap, pb<1.5, cash-
generative. Top-10 all deeply net-cash sub-book (Dongwoo 0.75, Brook Crompton 0.91,
China ITS 1.59). Matches the archetype's stated (cash-only) limitation honestly.

---

## Cross-cutting observations

1. **Base-effect one-year growth** is the single most common top-of-book distortion —
   Dong A Eltek (+234%), BioArctic (+346%), Mining Americas (+1093%), Integra (+719%)
   recur across exceptional_evsg, growth_algo, evsales_derating, tenbagger. Only
   wolf_compounder carries an explicit upper-growth cap; propagating a median-of-bases
   growth or an upper cap to the other growth screens would fix several at once.
2. **The EV/mcap>=1.75 leverage path** (weschler / asymmetric_assembly / levered_
   inflection) admits names with trivial net-debt/EBITDA, diluting the convex-stub thesis
   in all three — one shared nde-floor fix.
3. **Sentiment/structure screens without a scale floor** (analyst_awakening,
   analyst_rerating_confirmed) let pre-revenue biotech and loss-makers dominate; a shared
   revenue/quality floor would sharpen both.
4. **Top-of-book convergence:** a cluster of cheap net-cash Asian microcaps (Dongwoo,
   Brook Crompton, Medialink, China ITS, Michang) tops ~8 different archetypes because
   ETA ranking dominates; archetypes are weakly differentiated at the very top even when
   their gates differ. Worth confirming the per-archetype score keys (not raw ETA) drive
   the delivered books.

## Verdict table
| Archetype | Verdict |
|---|---|
| arch_oak_nav_discount | NEEDS-WORK |
| arch_oak_order_conversion | NEEDS-WORK |
| arch_analyst_awakening | NEEDS-WORK |
| arch_tenbagger_path | NEEDS-WORK |
| arch_tenbagger_credible | NEEDS-WORK |
| arch_evsales_derating | NEEDS-WORK |
| arch_wolf_seal | MINOR |
| arch_wolf_compounder | MINOR |
| arch_liger_asset_backed | MINOR |
| arch_liger_lagging_inflect | MINOR |
| arch_liger_neglected_survivor | MINOR |
| arch_oak_deep_value | MINOR |
| arch_weschler_levered_equity | MINOR |
| arch_asymmetric_assembly | MINOR |
| arch_levered_inflection | MINOR |
| arch_insider_conviction | MINOR |
| arch_cheap_sales_scaler | MINOR |
| arch_exceptional_evsg | MINOR |
| arch_growth_algo | MINOR |
| arch_negative_ev_value | MINOR |
| arch_templeton_pessimism | MINOR |
| arch_lynch_reward | MINOR |
| arch_analyst_rerating_confirmed | MINOR |
| arch_tax_efficient | MINOR |
| arch_asleep_at_wheel | MINOR (redesign works) |
| arch_oak_resource_leverage | SOUND |
| arch_oak_deleveraging | SOUND |
| arch_oak_asset_floor | SOUND |

## Special note — arch_asleep_at_wheel (redesign judged)
The no-quality-floor / quality-upweighted asleep_score redesign **works**: sorted by
asleep_score the top-of-book is genuinely high-quality underestimated businesses —
Samsung, SK hynix, Newmont, Teradata, Encore, Western Digital, Federated Hermes — high
ROCE, fat margins, profitable, conservatively levered, chronic beaters. This is a clear
improvement over a raw beat-rate sort. One caveat: a few names the market has plainly
*already* woken to rank high on quality alone — PLTR (P/E 149, +1148% momentum) and
SK hynix — which sits awkwardly with "asleep / underestimated." A light expectations or
valuation damper (penalize nosebleed multiples / extended price) would make the
"underestimated" half of the thesis hold as well as the "good business" half. Verdict
MINOR, and the redesign goal is met.
