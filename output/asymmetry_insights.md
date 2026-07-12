# Asymmetry insights — the most asymmetric special-situations (top 100)

Generated from the broad scan (`universe_screen.py`, 1,102 candidates
across 20 sourcing mechanisms) and the asymmetric scan
(`universe_risk_reward.py`, 221 investable names ranked by
`Reward/Risk = (EV× − 1) ÷ Bear-case loss`). 26 names carry hand-built
bottom-up waterfalls (REAL); the rest use the transparent proxy
(universe score × archetype tilt × corroboration boost).

This note reads the ranking analytically — not as a list, but as a map
of *where the asymmetry lives* and *what is driving it*.

---

## 1. The one order-of-magnitude outlier: Solocal (LOCAL, 20.2×)

Nothing else in the universe is close, and the reason is structural, not
cyclical. Post-safeguard, Solocal trades at roughly its **net cash**
while still generating EBITDA — a hard *double-floor* (cash + ongoing
earnings) that caps the bear case at **−15%**. Every other high-reward
name in the book has a bear case of 40–70%; LOCAL's asymmetry comes from
the denominator (tiny downside), not a heroic upside. Ycor (Lévy/Niel)
control removes the agency risk. This is the single cleanest asymmetric
setup in the framework, and it is an outlier by construction: a name can
only score 20× if its downside is genuinely floored.

**Read-through:** the framework should actively hunt for the LOCAL
*shape* — post-restructuring equities trading at/below net cash with
positive EBITDA — because that shape is where the extreme ratios are.
The new post-reorg poller (below) is precisely the instrument for this.

---

## 2. The Latin-American sovereign-recovery cluster (A1) — a *concentrated factor*

Five of the top 21 are Argentine A1 names on the same thesis:

| Rank | Name | RR |
|---:|---|---:|
| 2 | TGS (Transportadora de Gas del Sur) | 4.5× |
| 3 | Edenor | 4.0× |
| 5 | Banco Galicia | 3.6× |
| 8 | Pampa Energía | 3.4× |
| 21 | YPF (REAL) | 2.6× |

This is the most important **portfolio** observation in the scan: the
2nd–8th ranks are *not five independent bets*, they are one macro bet
(Milei-era sovereign-credit normalization) expressed five ways. The
asymmetry is real but correlated — a single Argentine policy reversal
hits all five. Any sizing must treat this as one cluster, not five
positions. YPF is the only one with a hand-built waterfall; the other
four are proxy-ranked and are the highest-value **YAML build-out
candidates** in the book (deep-diligence would confirm or break the
proxy).

---

## 3. The sovereign-industrial-policy cluster (A2) — high skew, cycle-gated

| Name | RR | Bear | Anchor |
|---|---:|---:|---|
| Lithium Americas (LAC) | 3.5× | −60% | DOE ATVM 0%-spread loan + GM JV |
| Salzgitter (SZG) | 3.4× | −45% | EU IAA / KfW green-steel |
| USA Rare Earth (UREE) | 2.6× | −65% | Critical-minerals policy |
| Trilogy Metals (TMQ) | 2.1× | −55% | Critical-minerals policy |
| MP Materials (MP) | 2.0× | −45% | DoD rare-earth offtake |
| Drake & Scull (DSI) | 2.8× | −45% | GCC sovereign-adjacent |

These carry the *highest bear losses* in the top 40 (45–65%) — they are
not floored like LOCAL; they are convex bets on a policy/commodity
inflection. The sovereign anchor (a sub-commercial loan, a binding
offtake, a state green-steel envelope) is what makes them special-sits
rather than pure cycle plays: the anchor compresses the floor and
guarantees the survival path. The asymmetry is genuine but *conditional*
on the anchor's terms holding and the cycle inflecting. Correctly, the
archetype-fixed ranking no longer over-weights these (the prior A2 bug
had inflated everything to A2, distorting the whole book).

---

## 4. The governance-reset cluster (H) — the lowest-bear asymmetry after LOCAL

| Name | RR | Bear |
|---|---:|---:|
| Hitachi Construction Machinery (6305) | 2.8× | **−25%** |
| Doosan Bobcat → Robotics (241560) | 2.6× | **−25%** |
| Thyssenkrupp Steel (TKA) | 3.0× | −45% |

Hitachi and Doosan stand out for the *combination* of a decent ratio and
a **shallow −25% bear** — the Asian-governance-reform regime (Korea
Value-Up / Commercial Act, Japan TSE cost-of-capital disclosure) puts a
policy floor under the re-rate. After LOCAL, these are the two names
whose asymmetry rests most on a capped downside rather than a big upside.
Worth prioritising alongside LOCAL for that reason.

---

## 5. What the *machine sourcing* newly surfaced (corroborated events)

The 20-mechanism sourcing engine is now feeding the ranking, and the
weighted-conviction corroboration layer is doing its job — surfacing
names confirmed by *multiple independent sources*:

- **TruBridge (TBRG, K3, conviction 3.55)** — a delisting-deficiency
  independently confirmed by BOTH the 8-K Item 3.01 filing AND the
  25-NSE delisting form. This is the highest-conviction *machine-sourced*
  signal in the book. Ranks #23 with a realistic 2.6× — correctly *not*
  above Lithium Americas (the prior archetype bug had spuriously placed
  it #2). A going-dark/cure situation worth a primary-doc read.
- **Aptose Biosciences (APTOF, K3)** — Form 15 going-dark + red-flag.
- **Leggett & Platt (LEG, C)** — cross-listed event (ASX + merger-form).
- **Aethlon Medical (AEMD, F2)** — spinoff + red-flag, 3 sources.

These are *less-diligenced* than the REAL anchors — they are leads, not
conclusions — but they are exactly the kind of names a human desk would
never have found by hand, and the corroboration score correctly ranks
the hard, multiply-confirmed ones (TruBridge) above soft single-source
hits.

---

## 6. Coverage completeness — two gaps closed this run

Two systemic issues were found and fixed while validating that the
*entire* framework was being used:

1. **Post-reorg names were being dropped.** The post-reorg poller found
   146 fresh-start / emergence names, but the promotion window only
   scanned the last 7 days while those records span a 90-day filing
   footprint — so only **1 of 146** reached the ranking. Fixed (window →
   120 days, idempotent via the dedup log): post-reorg coverage is now
   **97 names**. This matters because post-reorg equities are the LOCAL
   *shape* (§1) — the richest asymmetry category — and the framework was
   nearly blind to them.

2. **Archetypes were mis-classified.** A stray agency pattern matched the
   word "doc" in boilerplate, tagging ~58% of the top 100 as A2 (the
   highest-weight archetype) and distorting the whole ranking. Fixed:
   the top-100 archetype spread is now realistic (A1 22, H 15, K3 15,
   E 10, G 9, C 5, F2 2) and every archetype — not just A2 — is
   represented, across nine regions.

---

## Where to point the next unit of work

1. **Build YAMLs for the Argentine A1 cluster** (TGS, EDN, GGAL, PAM) —
   they are ranks 2–8 on the proxy; real waterfalls would either confirm
   a genuine top-5 cluster or break it, and it's the single highest-value
   diligence in the book.
2. **Deep-read the post-reorg cohort for the LOCAL shape** — 97 fresh-
   start names now flow through; screen them for net-cash-plus-EBITDA
   double-floors, which is where 20× ratios come from.
3. **Prioritise the two low-bear governance names** (Hitachi 6305,
   Doosan 241560) alongside LOCAL for downside-floored asymmetry.
4. **Treat the Argentine names as one cluster** in any sizing — the
   ranking's rank-2-through-8 concentration is a correlated factor, not
   diversification.
