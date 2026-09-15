# Most Asymmetric Opportunities

*Generated 2026-06-02. Universe: 892 unique tickers across all signal
layers (form4_buys, step_change, forensic_asymmetry, psu_forensics_v2,
sc13d_recent). Filtered to mcap ≥ $50M and ≤ $500B. Composite scoring
weights insider cluster (max 35), valuation/drawdown (max 25), event
step-change (max 25), forensic PSU quality (max 15), 13D presence,
and PSU% of LTI. Persistent outputs: `top_asymmetric.{csv,json}`.*

## Methodology — what makes a setup asymmetric

Asymmetric ≠ insider buying alone. The composite requires three independent
signals to point the same way:

1. **Conviction insider behaviour** — multiple distinct C-suite + board
   buyers within a 14-day window, weighted by role (CEO 1.5×, CFO 1.2×,
   Director 0.85×). Cluster recency multiplier (≤30d = 1.0, ≤90d = 0.6).
2. **Valuation tilt** — proximity to 52w low (`drawdown_pct ≤ 25` = +12),
   low P/B (≤ 1.2 = +6).
3. **Structural setup** — step-change event stack (special committee,
   buyback, bid, spin-off), PSU forensic score, 13D activist presence,
   PSU-heavy LTI mix.

Audited insider quality by name. Many high-cluster names turn out to be
either (a) programmatic same-dollar director allocations (HDSN $24K
identical buys, EPAM $7,500 identical buys) which look like clusters but
carry no information, or (b) single-sponsor accumulation (BETR =
Framework Ventures only, ODTX = TPG/Dimension PIPE) which is a financing
not a cluster. These are flagged and downgraded below.

---

## Tier A — Highest conviction (broad cluster, real dollars, deep value)

### 1. FLUT · Flutter Entertainment · $17.5B · $100.70 — score 56
**4% above 52w low**, down 68% from $313.69 high. P/B 1.9. Gambling.

**Insider cluster (May 12, 7 buyers, $1.05M total)** — broad C-suite:
- Taylor Daniel, **President FLUT / CEO FLUT International**, **$251,587**
- Jackson Jeremy, **Chief Executive Officer**, **$244,656**
- Bryant John A, Director, $200,586
- Liu Don, Chief Legal Officer, $150,000
- Bishop James, Chief Operating Officer, $99,751
- Bomhard Stefan, Director, $51,000

SIX C-suite + board members buying inside 48 hours, including CEO,
COO, President, CLO, two directors. This is the cleanest broad-
management cluster on a meaningful-cap name in the universe.

**Why it's asymmetric**: Gambling stocks have re-rated down hard on
state-by-state regulatory worries. Flutter is the global leader in
sports betting with FanDuel as the US asset. At 4% above 52w low with
CEO + COO + President all writing personal checks, the binary is
asymmetric: either the regulatory overhang clears (return to $200+),
or the cycle compresses further. Insiders with the most information
are sized as if it's the former.

### 2. PATK · Patrick Industries · $3.0B · $90.65 — score 47
**10% above 52w low**, P/B 2.5. RV / marine OEM supplier.

**Insider cluster (May 6, $3.5M+ total)** — CEO + senior management:
- **WELCH M SCOTT, Director, $886,670 (plus $1.14M in March)**
- **NEMETH ANDY L, Chief Executive Officer, $880,000**
- Roeder Charles R, President-RV, $505,018
- Augsburger Blake, Director, $34,076

CEO writing an $880K personal check **alongside** a director writing
$887K (his third six- or seven-figure buy in two months) is institutional-
grade signal. Director Welch has cumulatively bought >$2M.

**Why it's asymmetric**: RV cycle bottom — Patrick is the leading
component supplier to Thor / Forest River / Winnebago, OEM volumes
down 35-40% off 2022 peak. CEO + repeat director buys at a 10%-above-
52w-low price point indicate insider view that the cycle is turning.

### 3. SRAD · Sportradar Group · $4.0B · $13.46 — score 47
**9% above 52w low**, P/B 3.7. Sports data / B2B sports betting.

**Insider cluster** — CEO mega-conviction:
- **Koerl Carsten, Chief Executive Officer, $4.55M (May 6) + $3.34M (May 4) + $2.13M (May 7) = $10M+ total**
- Walder Marc, Director, $842,820
- Yabuki Jeffery, Director, $129,400
- Kurtz William, Director, $103,786

CEO writing a $10M+ personal check across three transactions in three
days. **0.25% of total mcap purchased by one person**. The largest
single-name insider-buy conviction in the entire universe.

**Why it's asymmetric**: Sportradar is the upstream data provider for
the sports-betting infrastructure (data feeds, integrity services).
Trades at material discount to peers despite mission-critical
positioning. The CEO is the founder — he knows what he's buying.

### 4. POOL · Pool Corporation · $6.6B · $180.69 — score 46
**5% above 52w low** (down 48% from $345 high). P/B 5.8.

**Insider cluster** — sustained director accumulation:
- **PEREZ DE LA MESA MANUEL J, Director, $1.90M (May 8) + $1.76M (May 14) + $1.09M (Mar 4) + $1.03M (Mar 17) = $5.78M in 90 days**
- St Romain Kenneth G, SVP, $1.22M
- Hope James D, Director, $300K

Director Perez-de-la-Mesa is buying $1-2M chunks repeatedly. Same-name
repeat-buyer is the single-cleanest conviction signal in insider research
(Cohen-Malloy-Pomorski).

**Why it's asymmetric**: Pool Corp is a quasi-monopoly distributor in
US swimming pool supplies. Post-COVID demand normalisation has cratered
the stock. Director with deep operating knowledge is loading up
methodically — the cycle is bottoming.

### 5. GO · Grocery Outlet · $818M · $8.27 — score 47
**19% above 52w low**, P/B 1.0. Discount grocery.

**Insider cluster (March, $7.9M total)** — CEO + founder + sponsor:
- **Potter Jason, President & CEO, $1.69M (Mar 20) + $717K (Mar 25)**
- Lindberg Eric Jr., Director, $1.64M
- Ragatz Erik D., Director, **$882K + $750K + $702K + smaller** (repeat)

Note: Lindberg = founder-family / Ragatz = Hellman & Friedman-linked
sponsor director. The CEO writing a personal $1.7M check on a $818M
mcap company is meaningful — 0.2% of mcap.

**Risk**: Cluster is 87 days old (recency multiplier dampened).

### 6. HFFG · HF Foods Group · $102M · $1.90 — score 41
*(See Forensic Report — Tier 1, microcap with $1.232B PSU revenue hurdle
and CEO+CFO+CAO+Director same-day cluster.)*

---

## Tier B — Real C-suite cluster, smaller dollars or premium valuation

### 7. EVTC · Evertec · $1.4B · $22.57 — score 42
**5% above 52w low**, P/B 2.1. LatAm payments.
Cluster of 4 operating EVPs ($400-490K each, total $1.8M), but **no
CEO/CFO** — entirely operational layer.

### 8. GSHD · Goosehead Insurance · $1.2B · $34.37 — score 44
**1% above 52w low**, down 70% from $113 high. P/B negative (book impaired).
- CEO Miller $184K + CFO Martin $174K + COO Jones $99K + 10% owner Langston $99K.
Real C-suite trio at extreme drawdown — but negative book reflects buyback-funded recapitalisation; the equity is a levered call option.

### 9. OI · O-I Glass · $1.2B · $7.97 — score 44
**1% above 52w low**, P/B 0.9. Glass packaging.
4-buyer cluster including CFO ($20K) + CAO ($102K) + GC ($25K) + SVP ($30K).
Dollars are small but the unanimous senior-management posture matters at deep value.

### 10. ONON · On Holding · $13.1B · $37.52 — score 40
**23% above 52w low**, P/B 5.5. Premium athletic footwear.
3-buyer cluster $6.6M total, CEO bought. Premium-priced but cluster is real.

### 11. NKE · Nike · $64.9B · $43.81 — score 40
**6% above 52w low**, P/B 4.6. Mega-cap brand reset.
4-buyer cluster $3.7M total, CEO bought. Largest-cap meaningful drawdown in set.

### 12. AGBK · AGI Inc · $1.08B · $6.76 — score 50
**6% above 52w low**, P/B 1.2. Brazilian regional bank.
Cluster size 4 but only **Chairman/CEO Testa $200K** is meaningful — the
other three are micro-buys by risk/CTO/sales officers ($3K each).
Single-officer signal despite multi-buyer count.

### 13. HDSN · Hudson Technologies · $222M · $5.27 — score 49
**11% above 52w low**, P/B 0.9. Refrigerant reclaim.
**Programmatic same-day pattern**: 7 buyers all bought EXACTLY $24-25K on
the same day (2026-05-15). This is a director-share-purchase program,
not a conviction cluster. Downgrade.

### 14. EPAM · EPAM Systems · $5.1B · $97.28 — score 48
**6% above 52w low** (down 56% from $222 high), P/B 1.5. IT services.
**Programmatic identical-dollar pattern**: every buyer purchased exactly
$7,500 on 2026-05-04. CEO, CFO, Chief Legal, Controller, CPO, EVP all
the same dollar = annual director matching program. Downgrade.

---

## Tier C — Filtered / single-sponsor (not true insider clusters)

- **ODTX (Odyssey Therapeutics)** — $75M of buys but ALL from TPG GP,
  Dimension Capital, Li Nan, SR ONE on one day = coordinated PIPE
  financing, not a broad insider cluster. Sponsor-class signal only.
- **BETR (Better Home & Finance)** — All "cluster" buys are by Framework
  Ventures IV (existing 10% owner sponsor accumulating). Single-entity.
- **MOBI (Mobia Medical)** — $19M cluster appears sponsor-led; P/B
  negative.
- **XRN (Chiron Real Estate)** — 9-buyer cluster looks broad ($170K CEO +
  $100K CFO + multiple directors) but it's a brand-new IPO with all
  initial directors buying in pursuant to the listing.

---

## Tier D — Step-change driven (no fresh insider cluster but event-driven)

From `step_change.csv` — names with material recent event stacks:

| TKR | Mcap | Px | Event hook |
|---|---|---|---|
| GRND | $2.5B | 13.78 | Special cmte + bid + $500M buyback (20% mcap), all 33d |
| AMCX | $366M | 8.57 | Special cmte + 137% mcap buyback 111d |
| WDAY | $31.9B | 127.83 | Bid + $2.1B buyback + spin, all 28d |
| PAYC | $6.4B | 136.87 | Bid + 31% mcap buyback + spin, 29d |
| RH | $2.5B | 133.89 | 97% mcap buyback + spin, 29d |
| CSGP | $14.2B | 34.72 | Special cmte + bid + $3B buyback, all 33d |
| SOFI | $21.1B | 16.43 | Special cmte + bid + spin + governance reset, 33d |
| KDP | $39.6B | 29.09 | Special cmte + bid + $4B buyback + 4-flag plan delta |

These are *event-driven* asymmetric — the asymmetry comes from the
break-up / sale / spin already in motion, not from insider conviction.

---

## How to size

The asymmetry composite is a ranking, not a sizing recommendation:

- **Tier A** has the best risk/reward — combine clear C-suite cluster
  conviction with proximity to 52w low. FLUT, PATK, SRAD, POOL are
  large enough to size; HFFG and GO are smaller-cap.
- **Tier B** is suitable for tracking — programmatic-pattern names
  (HDSN, EPAM) shouldn't be treated as conviction signals despite the
  cluster headline.
- **Tier C** clusters are sponsor-driven accumulation — these can still
  be alpha (sponsors have information) but the signal is different
  in nature.
- **Tier D** requires deep dive on the specific deal/event — not a
  generic conviction overlay.

---

## Persistence

All outputs committed: `top_asymmetric.csv`, `top_asymmetric.json`,
`MOST_ASYMMETRIC.md`, `yfinance_quick.json` (mcap/drawdown/valuation
overlay). `.gitignore` excludes only ephemerals — everything else
survives any local reset.
