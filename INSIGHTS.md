# Earnings Inflection — Insights & Watchlist

Findings from `earnings_model` across a global small→mega universe (UK LSE +
US small/mid/large + EU primary listings). Quantitative screens identify
**earnings/operating inflection the price hasn't reflected**; a qualitative
overlay then asks the question screens can't: **is the driver a durable
*secular* shift, a *cyclical* bounce, a *self-help* restructuring, or a value
trap?** Dated June 2026. Not investment advice — a research scaffold.

## Coverage
- Universe: ~10,600 listings → **6,751 with Yahoo data** → **~6,570 operating
  companies** after the quality gate (drops warrants/preferreds/CEFs/BDCs/shells).
- Regions: US 3,569 · EU 2,300 · UK 701 operating. Sizes nano→mega.
- The ~3,900 listing gap is genuinely delisted/renamed (hard 404 from Yahoo on a
  clean IP), now negative-cached so runs don't re-chase them.

## How the screens work (`earnings_model/screens.py`)
All operate on operating companies, rank **within region** (multiples are only
comparable to same-market peers), and apply artifact guardrails: no nano-caps,
require a sane **positive** multiple (EV/EBITDA, fwd P/E, or P/B), de-dupe
cross-listings, and drop ratio-growth blow-ups off a near-zero base. Because
yfinance quarterly data is only ~40% populated, **annual (YoY) is the primary
signal and QoQ enters as a bonus only** — never equal-weighted.

- **yoy-unpriced** — annual growth accel/inflection × cheap × price-dormant.
- **accel-unpriced** — as above + a 20% quarterly bonus.
- **asymmetry** — operating inflection (catalyst) + cheap (downside) + dormant.
- **inflecting-positive** — sales or EBITDA growth crossing from ≤0 to >0.
- **prebreakout** — improving (gated) + dead-money 1–2yr + cheap.

## Qualitative classification of the cross-screen consensus

> The most important lesson of this work: **a screen cannot tell secular from
> cyclical, or real inflection from M&A-masked decline.** The overlay below
> moved names *up* (durable driver, mispriced) and *out* (cheap for a reason).

### 🟢 SECULAR — structural driver the price hasn't caught (highest conviction)

| Name | Region | Secular driver | Why mispriced |
|---|---|---|---|
| **TaskUs** (TASK) | US | AI Services +36% YoY for 6 straight quarters; re-mixing from call-centres → **AI model training, AI safety, AV/robotics data labelling** (~45% of revenue now non-core-CX) | Priced as a declining BPO (4.5× EV/EBITDA, −32%/2yr) while becoming AI picks-and-shovels |
| **Verra Mobility** (VRRM) | US | **Legislated** road-safety camera adoption (Vision Zero + IIJA funding); $998m 5-yr NYC renewal | Down 81%, 4.8× EV/EBITDA — priced as ex-growth; revenue is contracted & recurring |
| **CBIZ** (CBZ) | US | **Structural CPA shortage** forcing mid-market accounting consolidation; now #7 US firm post-Marcum | Down 54% on integration-debt fear; durable pricing power ignored |
| **US natural-gas E&P** (EQT, Expand, Gulfport, CNX, Antero, Range, Comstock) | US | **AI-datacenter power + LNG export** demand; EIA sees strongest 4-yr US electricity growth since 2000, gas price +13% to ~$4.01 for ’26 | A whole cohort at **3–7× EV/EBITDA** still priced on old cyclical-trough gas |

### 🟡 SELF-HELP / RESTRUCTURING — real inflection, idiosyncratic (not a market shift)

| Name | Region | Note |
|---|---|---|
| **Koenig & Bauer** (SKB.DE) | EU | "Massive" order-intake jump + S&T turnaround; crown jewel = **~90% of world banknote printing** + packaging extension. 0.46× P/B. Defensive moat + self-help. |
| **Progress Software** (PRGS) | US | Disciplined acquire-and-integrate infra-software roll-up; cheap (8× EV/EBITDA, 5× fwd P/E). Capital-allocation story, not a market shift. |
| **Sonoco / Silgan** (SON/SLGN) | US | Packaging margin recovery + mix-shift to higher-margin dispensing/closures. Input-cost pass-through normalising. Cyclical-to-structural margin, name-specific. |

### 🟡 CYCLICAL — real, but mean-reverting (needs a macro turn, not a secular shift)

| Name | Region | Note |
|---|---|---|
| **UK housebuilders** (Vistry, Persimmon, Crest, Taylor Wimpey) | UK | Driver is **rate cuts + a *stalled* policy catalyst**. Labour's 1.5m-homes target real but OBR forecasts a **miss** (~1.3m); benefits "late 2026/2027"; Q1'26 registrations *fell 6%*. 15-yr-low prices correctly reflect a *delayed cyclical* recovery. |
| **UK domestic consumer cyclicals** (Topps Tiles, DFS, Vp, Genuit, Motorpoint) | UK | Same cyclical engine — UK consumer recovery. Cheap (7–9× EV/EBITDA), broad EBITDA acceleration, dormant. Cyclical, not secular. |

### 🔴 DISQUALIFIED / VALUE-TRAP — the screen was wrong; the overlay caught it

| Name | Region | Why excluded |
|---|---|---|
| **Xerox** (XRX) | US | EBITDA "inflection" is the **Lexmark acquisition optically lifting numbers**; organic revenue still declining. Print is in *secular decline* — M&A-masked melting ice, not inflection. |
| **Intrum** (INTRUM.ST) | EU | "EBITDA recovery" sits on a **distressed recap** (10% debt write-down, S&P CCC+ out of default), losing the NPL game to lower-levered funds. Equity = survival option. |
| **Conagra / Campbell** (CAG/CPB) | US | Cheap (7–10× P/E) but face a **secular *headwind*** — GLP-1 drugs cutting packaged/ultra-processed food volumes (savoury snacks −~10%). Cheapness is a value trap, not a setup. |
| Low-base biotech (Pliant, Agenus, Keros, Vaxart, Zealand) | US/EU | Score high on ratio-growth off near-zero revenue; binary, pre-profit. Not operating inflection. |
| **Cigna** (CI) | US | Inflecting + cheap (8× P/E) but **PBM reform** could erase 15–20% of segment profit (bipartisan support); 60% of profit concentrated in Evernorth. Policy overhang ≈ the discount. |

## The synthesis
1. **Two clean *industry-level* secular trades:** US natural-gas E&P (AI-power/LNG
   demand vs trough valuations) and US road-safety enforcement (Verra).
2. **Best single secular names the price ignores:** TaskUs (AI re-mix), Verra
   (legislated demand), CBIZ (consolidation).
3. **UK = cyclical, not secular** — a genuine cheap-and-inflecting consumer/housing
   cohort, but the catalyst is rates/policy and partly stalled. Size accordingly.
4. **EU = cheapest on P/B** (German machinery, Nordic names at 0.25–0.6× P/B) but
   mostly self-help/idiosyncratic rather than a shared secular wave.
5. **The overlay earns its keep by *removing* names:** Xerox (M&A-masked decline),
   Intrum (distressed), Conagra/Campbell (GLP-1 headwind), biotech (low-base) —
   all top quant scorers that fail the qualitative test.

## Reproduce
```bash
pip install -r requirements.txt && pip install --no-deps financedatabase
python -m earnings_model build-universe --preset global
python -m earnings_model fetch            # cached; run where Yahoo isn't rate-limited
python -m earnings_model analyze
python -m earnings_model screen yoy-unpriced -n 30
python -m earnings_model screen asymmetry --region EU -n 20
python -m earnings_model cluster
```

## Sources
TaskUs Q1'26 ([SEC 8-K](https://www.sec.gov/Archives/edgar/data/0001829864/000182986426000110/earningsreleaseex991q12026.htm)) ·
Verra NYC $998m ([PRNewswire](https://www.prnewswire.com/news-releases/verra-mobility-and-new-york-city-department-of-transportation-finalize-five-year-998-million-contract-aimed-at-improving-safety-through-expanded-traffic-enforcement-programs-302684983.html)) ·
CBIZ/Marcum ([Accounting Today](https://www.accountingtoday.com/news/cbiz-cpas-readjusts-after-marcum-acquisition)) ·
ZoomInfo/Forrester ([BusinessWire](https://www.businesswire.com/news/home/20260416507537/en/)) ·
Gas/AI-power ([EIA](https://www.eia.gov/pressroom/releases/press582.php), [NGI](https://naturalgasintel.com/news/us-natural-gas-outpacing-oil-demand-as-data-centers-lng-seen-lifting-26-outlook/)) ·
Packaging ([Packaging Dive](https://www.packagingdive.com/news/silgan-q4-full-year-2025-packaging-earnings/811387/)) ·
Koenig & Bauer ([Printweek](https://www.printweek.com/content/news/koenig-bauer-in-radical-revamp)) ·
Xerox ([SEC 8-K](https://www.sec.gov/Archives/edgar/data/0001770450/000177045026000025/ex991xrx331268-ker.htm)) ·
Intrum ([Reorg](https://www.reorg.com/articles/intrum-mandates-houlihan-lokey-and-milbank-as-restructuring-advisors/)) ·
GLP-1/food ([FoodNavigator](https://www.foodnavigator.com/Article/2026/01/23/glp1-demand-are-we-already-seeing-a-slowdown/)) ·
Cigna ([SEC 8-K](https://www.sec.gov/Archives/edgar/data/0001739940/000114036126017971/ef20071317_ex99-1.htm)) ·
UK housing ([Big Issue](https://www.bigissue.com/news/housing/labour-housebuilding-target-private-companies/))
