# cyclepapa

Capital-structure screening framework + working pipeline. Five documents
of methodology; four scripts that actually run.

## Layout

```
data/
  SCHEMA.md             # candidate file format
  candidates/*.yaml     # single source of truth per name
  inbox/<date>/         # daily EDGAR poller output (auto-populated)
src/
  score.py              # YAML → ranked Markdown + EV + Kelly sizing
  edgar_poll.py         # SEC EDGAR full-text daily poller
  waterfall.py          # Monte Carlo over candidate waterfall
output/
  screen_generated.md   # AUTO-GENERATED; never hand-edit
docs (methodology, not generated):
  capital_structure_screening.md  # core framework
  universe.md                     # broad watchlist
  shortlist.md                    # narrative shortlist (legacy; superseded by score.py)
  final.md                        # top 25 with valuation (legacy)
  screen.md                       # strict-discipline screen (legacy)
  methodology_review.md           # validity threats + roadmap
```

## Daily workflow

```bash
make poll       # pull overnight EDGAR full-text hits to data/inbox/
make score      # compile candidate YAMLs → output/screen_generated.md
make waterfall  # Monte Carlo across all candidates
make validate   # schema check only; CI-friendly
```

## Adding a candidate

1. Copy any file from `data/candidates/` as a template.
2. Fill in fields. Tag every load-bearing number with `source:` per
   `data/SCHEMA.md`.
3. Run `make validate`. Fix any errors. Warnings are fine but visible.
4. Run `make score`. Confirm the name appears with sensible tier/EV.

Tier 1 is gated: a candidate cannot enter Tier 1 with unverified deal
fields (sizing-blocked warning) or without a written pre-mortem.

## Why the docs and the code differ

`shortlist.md`, `final.md`, and `screen.md` were assembled by hand
across many iterations. They will drift from the canonical YAML data
unless they are *also* regenerated. The methodology review (see
`methodology_review.md` §4.1) identifies this drift as the single
biggest engineering flaw — and the migration path is to phase those
files out as `output/screen_generated.md` matures. Until then, prefer
the script's output for ranking and the legacy docs for narrative.

## Outstanding work (from `methodology_review.md`)

| Item | Status |
|---|---|
| Canonical YAML data store | ✅ done (3 example candidates) |
| Source-verification ledger | ✅ schema done; ⚠️ all current fields tagged `unverified` |
| EV + ¼-Kelly sizing | ✅ done in `src/score.py` |
| EDGAR poller as code | ✅ done; runnable via `make poll` |
| Monte Carlo waterfall | ✅ done in `src/waterfall.py` |
| Historical base-rate study (≥200 deals) | ❌ todo (highest impact item left) |
| Point-in-time re-scoring of case studies | ❌ todo |
| Bonds-vs-equity divergence monitor | ❌ todo |
| Forecast log + calibration | ❌ todo |
| LLM term-extraction for filings | ❌ todo |
| Merton structural-credit cross-check | ❌ todo |
| Sponsor track-record scorecards | ❌ todo |
| Factor tagging + exposure caps | ⚠️ schema includes; not enforced |
| Options overlay & short-leg design | ❌ todo |
| Cycle-tool integration for C7 | ❌ todo (the `cycle` Streamlit app sits unused) |
