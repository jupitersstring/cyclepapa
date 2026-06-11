# Candidate Schema (v1)

Every candidate is a single YAML file at `data/candidates/<TICKER>.yaml`.
This is the **only** source of truth for the name; all rankings, screens,
and shortlists are generated outputs (see `src/score.py`).

The schema is designed to address the validity threats catalogued in
`methodology_review.md` §1:

- Every load-bearing number carries a `source` tag (§1.5 fix).
- Asymmetry is expressed as a probability-weighted waterfall (§1.3 fix).
- Returns carry an explicit horizon (§1.6 fix).
- Catalyst calendars are dated with probabilities (§2.8 fix).
- Pre-mortems are mandatory per Tier-1 name (§5.3 fix).
- A `history` block enables point-in-time reconstruction (§1.2 fix).

## Source tags

Every fact-bearing field has a sibling `_source` field carrying one of:

- `verified: <doc>, <YYYY-MM-DD>` — read in primary filing
- `reported: <outlet>, <YYYY-MM-DD>` — reputable secondary source
- `unverified` — claim not yet checked; sizing blocked until cleared

Verification is required on the **five key numbers per name** before
sizing: issue price / anchor stake / pro-forma debt / maturity wall /
current market price.

## Required fields

```yaml
ticker: STRING                  # primary trading ticker
isin: STRING | null
name: STRING
jurisdiction: ISO_2             # CA, US, FR, etc.
exchange: STRING                # TSX, NYSE, EPA, HKEX, etc.
sector: STRING
bucket: A | B | C
archetype: [A1|A2|B|C|D|E|F|G]  # one or more
state: watch | option | core | drop | pass
tier: 0 | 1 | 2 | 3 | watch | yellow | pass | null
```

## Deal terms (§1.5 source-tagged)

```yaml
deal:
  date: YYYY-MM-DD
  mechanic: STRING              # one-line description
  fields:
    <field_name>:
      value: NUMBER | STRING | DATE
      source: STRING            # see source tags above
      _note: STRING (optional)
```

Field names should be domain-meaningful (e.g. `rights_price_eur`,
`anchor_reserved_price_eur`, `second_lien_face_m_usd`, `dilution_pct`,
`maturity_after_yyyy`, `liquidation_recovery_pct`, etc.).

## Scorecard inputs (§2 of methodology)

Only the quantifiable dimensions; qualitative ones live in `notes`.

```yaml
scorecard:
  d2_issue_discount_pct:        float | null
  d3_backstop_cost_pct:         float | null
  d4_dilution_pct:              float | null
  d5_delta_wam_months:          int   | null
  d6_debt_tranches_post:        int   | null
  d7_ucc_terminations_pm30d:    int   | null
  d8_mip_strike_over_recap:     float | null
  d9_alignment_gap:             float | null
  d9b_anchor_premium_to_recap:  float | null
  d9c_premium_to_vwap:          float | null
  d9d_liquidation_recovery_pct: float | null
  d11_consensus_ebitda_cagr:    float | null
  d13_altman_z:                 float | null
  d14_liquidity_quarters:       float | null
```

## Catalyst calendar (§2.8)

Each catalyst gets a window, probability, and expected price impact.

```yaml
catalysts:
  - event: STRING
    window: [START_DATE, END_DATE]
    p_favorable: 0.0..1.0
    rerate_if_yes: [low_x, high_x]   # multiples of entry
    hit_if_no:    [low_pct, high_pct] # signed (negative = loss)
    source: STRING
```

## Probabilistic waterfall (§1.3, §2.5)

Three scenarios that sum to 1.0; used by score.py for EV.

```yaml
waterfall:
  bear: {p: 0.x, return_multiple: 0.x, rationale: STRING}
  base: {p: 0.x, return_multiple: 0.x, rationale: STRING}
  bull: {p: 0.x, return_multiple: 0.x, rationale: STRING}
```

Constraints: sum(p) == 1.0; bear ≤ base ≤ bull.

## Anchor identity

```yaml
anchor:
  parties: [STRING, ...]
  pricing:
    reserved_price:   NUMBER | null
    rights_price:     NUMBER | null
    current_price:    NUMBER | null
    currency:         ISO_4217
  stake_pct: NUMBER
  holds_debt:    bool
  holds_equity:  bool
  lockup_months: int | null
  prior_track_record: [STRING, ...]  # other deals this anchor anchored
```

## Triangulation legs (§8 of methodology)

```yaml
triangulation:
  leg1_valuation:        true | false | partial  # PF / through-cycle asymmetry
  leg2_game_theory:      true | false | partial  # cap-stack alignment
  leg3_revealed_pref:    true | false | partial  # insider / 13F evidence
  notes: STRING
```

## Red flags (§2.3) — explicit booleans

```yaml
red_flags:
  parallel_pipe_below_rights:       bool
  asymmetric_voting:                bool
  backstop_warrants_below_terp:     bool
  dip_to_exit_control_transfer:     bool
  springing_maturity_inside_24m:    bool
  stub_under_10pct_no_warrants:     bool
  insider_indemnity_survives:       bool
  insider_net_seller:               bool
  state_backstop_conditional:       bool
  refiled_within_12m:               bool
  new_money_irr_above_50pct:        bool
```

## Kill criteria — falsifiable conditions

```yaml
kill_criteria:
  - STRING                         # each must be measurable
```

## Pre-mortem (§5.3, mandatory Tier ≤ 2)

```yaml
pre_mortem: |
  It is <future date> and this lost ≥70%. What happened?
  Most likely: ...
  Second-most-likely: ...
  Specific document section where this would show up first: ...
```

## History — point-in-time audit (§1.2)

```yaml
history:
  - {date: YYYY-MM-DD, event: STRING, state_after: STRING}
```

## Factor tags (§1.7)

```yaml
factors:
  primary: cycle | policy | idiosyncratic | multiple_norm
  exposures: [STRING, ...]         # e.g. ["lithium", "EV cycle", "US policy"]
```

## Tier rationale

```yaml
tier_rationale: |
  Free-text explaining the tier assignment in terms of the framework's
  gates: triangulation legs, alignment-gap, C7 dated catalyst, archetype,
  active red flags.
```

## Validation rules enforced by `src/score.py`

1. `state` and `tier` must agree (core ⇔ Tier 1; pass ⇔ Tier pass).
2. Tier 1 names must have: ≥3 verified deal fields, dated C7 catalyst,
   waterfall with sum(p)=1.0, no active red flags, written pre-mortem.
3. Stale candidates (no `history` entry in last 30 days) get flagged.
4. Every `value` field must have a sibling `source`.
