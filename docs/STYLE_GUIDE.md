# CAR Report Style Guide — *Times Lattice*

The visual language of the Cross-Asset Ranker report (`times-lattice-compact`).

- **Canonical CSS:** [`test-aesthetic-2026-06-28/report_style_presets.py`](test-aesthetic-2026-06-28/report_style_presets.py) → `STYLES["times-lattice-compact"]["css"]`
- **Markup generator:** `app.py` → `_generate_experimental_html()` (+ `_build_band_data`, `_spark_svg`)
- **Reuse note:** [`test-aesthetic-2026-06-28/SAVED_STYLE_TIMES_LATTICE_COMPACT.md`](test-aesthetic-2026-06-28/SAVED_STYLE_TIMES_LATTICE_COMPACT.md)

---

## The look in one paragraph

A 19th-century financial **broadsheet** rebuilt for the screen. Everything is
**Times New Roman at a single 13.5px size**, black ink on white paper, divided
only by **1px hairlines** — no boxes, no shadows, no fills. The nameplate is
**stretched tall** (vertically scaled, never enlarged) over a **fleur-de-lis
divider**. Spacing is **tight and golden-ratio-tuned**, so the page reads dense
and engraved rather than airy. The *only* colours are **lapis blue** (good) and
**crimson** (bad); they appear as thin arrows, eight-point stars, and faint
decile washes behind the small-multiple **rank / OHLC / volume** bands. It should
feel like a printed research sheet you'd find under glass, not a web dashboard.

---

## 1. Principles

1. **One type size.** `h1`, `h2`, `p`, `li`, `td`, `a` are all `1rem`. Hierarchy
   comes from **weight, rules, case, and position — never size.**
2. **Print-first, single theme.** Committed to white paper / black ink; it does
   *not* adapt to dark mode. Identical in the browser and the print PDF.
3. **Hairlines, not boxes.** Structure is drawn with 1px rules (page border, row
   underlines, section tops). No rounded corners, borders-on-fills, or shadows.
4. **Dense by design.** Tight φ-based padding; the page should feel *full*.
5. **Colour is data.** The only non-black inks — lapis and crimson — mean
   *improving* and *deteriorating*. Nothing is coloured for decoration.
6. **Font-independent marks.** Divider, spark bands, triangles, and stars are
   inline SVG / geometry, so they render identically on any platform.

---

## 2. Colour scheme

**Five inks, no more.** Black does the structural work; grey is secondary text;
lapis and crimson are the *only* accents and always carry meaning.

| Swatch | Token | Hex | Role | Where |
|:------:|-------|-----|------|-------|
| ⬛ | `--ink` | `#000000` | primary | text, all rules/borders, OHLC bars, rank line |
| ⬜ | `--paper` | `#ffffff` | ground | page + panel backgrounds |
| ▓ | `--muted` | `#3f3f3f` | secondary text | meta rows, sublines, `.snapshot` labels |
| 🟦 | `--lapis` | `#061933` | **positive** | ▲ improving delta, ✴ improving inflection, ▲ up-skew volume, top-decile wash |
| 🟥 | `--crimson` | `#7a0019` | **negative** | ▼ worsening delta, ✴ deteriorating inflection, ▼ down-skew volume, bottom-decile wash |
| ▤ | neutral grey | `#8a8a8a` | neutral event | plain (non-directional) volume-spike triangle |

**Rules of use**

- Lapis and crimson **never** appear as backgrounds, headings, or borders — only
  as small directional marks and faint washes.
- **Decile shading is those same hues at `fill-opacity: 0.07`** — a dark colour
  reduced to a whisper, never a bright green/red pastel.
- If a new element needs emphasis, reach for **weight or a rule**, not a new
  colour. The palette is closed.

---

## 3. Typography

- **Family:** `"Times New Roman", Times, serif`. On Linux the metric-compatible
  **Liberation Serif** substitutes with no layout shift.
- **Size:** `13.5px`, applied as `1rem` to *every* text element. There is no
  second size anywhere.
- **Leading:** `line-height: 1.16` — deliberately tight, part of the dense feel.
- **Headings:** `font-weight: 700`, `text-transform: uppercase`,
  `letter-spacing: 0`.
- **Numbers:** `font-variant-numeric: tabular-nums` so digit columns align.
- **Links:** ink-coloured, 1px underline, `0.08em` offset — never blue, never a
  colour change on the text.

### The tall masthead (the signature move)

The title is the **same 13.5px** as everything else but is **stretched
vertically** to read like an engraved nameplate:

```css
.masthead strong {
  display: inline-block;
  transform: scaleY(1.45);      /* 45% taller — vertical only */
  transform-origin: 0 82%;      /* grows upward from the baseline */
}
```

Key point: **`scaleY` only.** Width and point size are unchanged, so letters get
*taller and narrower* (a condensed, monumental look) without breaking the
"one size" rule. `transform-origin: 0 82%` pins it near the baseline so it grows
up into the space above, not down through the divider.

---

## 4. Spacing & padding

### 4a. The golden-ratio scale

All gaps come from a φ progression (φ ≈ 1.618). **Do not introduce off-scale
values.**

| Token | rem | φ relation | typical use |
|-------|-----|-----------|-------------|
| `--gap-xs` | `0.236` | φ⁻³ | cell padding, marker gaps, meta-row gaps |
| `--gap-sm` | `0.382` | φ⁻² | rule padding, section-top padding, snapshot gap |
| `--gap-md` | `0.618` | φ⁻¹ | page inner padding, masthead grid gap |
| `--gap-lg` | `1.000` | φ⁰ | section top-margins |
| `--gap-xl` | `1.618` | φ¹ | major group separation |

Grid proportions echo φ too: two-panel blocks split **1 : φ**; the page padding
is `0.618rem 0.9rem` (≈ φ⁻¹ vertical, a touch more horizontal).

### 4b. Exact padding per component (the density spec)

The report reads *tight*. These are the real values — keep them small.

| Component | padding | border |
|-----------|---------|--------|
| `.page` (outer frame) | `0.618rem 0.9rem` | `1px solid ink` all sides |
| `.masthead` | `padding-bottom: 0.382rem` | `1px` bottom |
| `.masthead-divider` | `padding-bottom: 0.382rem`, `gap: 0.55rem` | — (hairlines flank the fleur) |
| `.snapshot` strip | `gap: 0.382rem`, `padding-bottom: 0.382rem` | `1px` bottom |
| `.panel-title` bar | `0.236rem 0.382rem` | `1px` bottom |
| table `th, td` | `0.18rem 0.236rem` | `1px` bottom per row |
| `.meta-row` (box detail) | `0.236rem 0.382rem` | `1px` bottom |
| `.subgroup-label` | `0.236rem 0.382rem` | `1px`, no bottom |
| `.spark` chart band | `margin: 0.382rem`; height `7.854rem` (≈ 5·φ) | — |

Rows are separated by a **single 1px underline**, not padding — that is what
gives the ledger-like density. Cell vertical padding is only `0.18rem`.

---

## 5. Layout

- **Page frame:** one `1px solid` black border wraps the whole broadsheet
  (`.page`, `width: min(142rem, 100vw − 1rem)`, centred, `margin: 0.5rem auto`).
  Print: `@page { margin: 0.35in }`, frame goes edge-to-edge.
- **Masthead → divider → snapshot:** uppercase title + date; a fleur-de-lis
  divider (hairlines flanking an inline-SVG fleur); then a 5-cell snapshot strip
  (assets · breadth · advancing/declining · inflections · biggest move), each
  cell a bold value over a muted label.
- **Panels:** `.panel` = hairline border + uppercase `.panel-title` bar; tables
  inside are borderless with per-row underlines.
- **Lattice sections:** one per asset class in taxonomy order. Scattered
  single-ticker subgroups roll up into broad **display buckets** (e.g.
  *US Styles & Factors*, *Developed / Emerging & Frontier Countries*,
  *Technology & Digital*, *AI / Automation / Digital*, *US Treasuries*). Each is a
  subgroup row (label + aggregate band) beside a `.constituent-grid` of compact
  asset boxes.

---

## 6. Chart-band grammar (`_spark_svg`, `100 × 30` viewBox)

| Element | Rendering |
|---------|-----------|
| **Rank line** | solid **black** polyline; rank 1 at top, `max_rank` at bottom |
| **Price** | **black weekly OHLC bars** (open tick left, close tick right) — chartbook ink, from daily closes |
| **Decile shading** | lapis (top decile) / crimson (bottom decile) rectangles at **7% opacity** |
| **Volume spikes** | all at the **bottom edge**: grey ▲ neutral · lapis ▲ up-skew · crimson ▼ down-skew (spike = weekly vol > `VOL_SPIKE_MULT`×`VOL_SPIKE_WINDOW`-wk median; skew = ≥2:1 up/down-day volume) |
| **Inflection star** | eight-point ✴ by the ticker — **lapis** improving / **crimson** deteriorating |

---

## 7. Content conventions

- **Deltas as arrows:** `▲n` lapis = rank improved (toward 1); `▼n` crimson =
  worsened; `±0` neutral. Never a bare signed number in a rank-move cell.
- **Ranks:** dense sequential `1…N` (raw modal ranks tie/skip).
- **Prices:** one decimal place.
- **Tables:** no Score/%ile columns; complete rankings split into two side-by-side
  panels.
- **Inflections:** primary panel from Ehlers DSP (SuperSmoother + Reflex) with a
  **Strong/Weak** signal; a back reference table shows the simple 2-week-vs-prior-
  2-week slope flip.

---

## 8. Reproduce it

```python
from report_style_presets import get_preset
css = get_preset("times-lattice-compact")["css"]     # the stylesheet
# app.py:_generate_experimental_html(data) emits the matching markup;
# test-aesthetic-2026-06-28/build_styled_reports.py applies a preset to a report.
```

**House rule — do not break §1.** No second type size. No off-φ spacing. No
colour beyond ink / muted-grey / lapis / crimson. No fills or shadows where a
hairline will do. When in doubt, make it *tighter and quieter*, not bigger.
