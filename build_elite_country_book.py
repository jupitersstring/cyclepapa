"""Elite country book — every archetype made extremely stringent.

Separate from the main country books: it shows only the most exceptional
opportunities per country, where a name qualifies for an archetype ONLY IF

  tiered archetypes (core / watch / exceptional / elite split in
  archetype_tags._tier):
      <name>_elite == 1        top 10% of the core on the archetype's defining
                               continuous measure, OR
      <name>_exceptional == 1  passes the archetype's qualitative exceptional
                               test;  ★ = both
  every other archetype (no tier yet):
      member AND top 5% of that archetype's members by confirm_overall (the
      multi-measure confirmation) AND no red forensic tell
      (fq_forensic_red_count == 0) AND liquid (>= $250k / week USD)
      AND not data-quality flagged

Common guards for every name: common stock, not RED-verdict, not a clinical-
stage biotech (their moves are binary-event driven), market cap >= $10M.

Sheets: Cover (elite counts by archetype x country, how to read), one sheet per
country (>= 1 elite name) ranked by the number of archetypes a name is elite
on, then by entry_confirmed.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import tab_colors
from build_archetype_book import load_data, ARCHETYPE_LABELS, _sheet_safe
from build_harvard_workbook import (Workbook, INK, MUTED, RULE, _font, _section_rule,
                                    _write_money, _write_pct, _write_score, _write_int,
                                    _TXT_ALIGN_LEFT, _NUM_ALIGN_CENTER)
from build_forensic_xr_book import acct_check
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter
from otc_flag import apply_otc_mode
from region_map import classify, ordered_countries

OUT = "elite_country_book.xlsx"


def _label(col: str) -> str:
    return str(ARCHETYPE_LABELS.get(col, col.replace("arch_", ""))).split(" (")[0]


def elite_matrix(df: pd.DataFrame, arch_cols: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(elite 0/1 frame, both-tiers 0/1 frame) over archetypes."""
    n = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
    E, B = pd.DataFrame(index=df.index), pd.DataFrame(index=df.index)
    liquid = n("ts_dvol26_usd") >= 250_000
    clean = ~(n("fq_forensic_red_count") > 0)
    dq_ok = ~(n("data_quality_flag") == 1)
    conf = n("confirm_overall")
    for col in arch_cols:
        name = col[len("arch_"):]
        mem = n(col) == 1
        if not mem.any():
            continue
        if f"{name}_elite" in df.columns or f"{name}_exceptional" in df.columns:
            el = n(f"{name}_elite") == 1
            ex = n(f"{name}_exceptional") == 1
            E[col] = (mem & (el | ex)).astype(int)
            B[col] = (mem & el & ex).astype(int)
        else:
            c = conf.where(mem)
            cut = c.quantile(0.95) if c.notna().sum() >= 20 else np.inf
            E[col] = (mem & (c >= cut) & clean & liquid & dq_ok).fillna(False).astype(int)
            B[col] = 0
    return E, B


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min-mcap", type=float, default=10e6)
    args = ap.parse_args()
    df, arch_cols = load_data(min_mcap=args.min_mcap, otc_mode="all")
    df = apply_otc_mode(df, "ex-otc")
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
    keep = ~(num("non_common_flag") == 1) & ~(num("is_clinical_biotech") == 1)
    if "verdict" in df.columns:
        keep &= df["verdict"].astype(str) != "RED"
    df = df[keep].copy()
    df["src"] = df["src"].fillna("").astype(str).str.upper()
    E, B = elite_matrix(df, arch_cols)
    E = E.loc[:, E.sum() > 0]
    df["elite_n"] = E.sum(axis=1)
    df["elite_both_n"] = B.reindex(columns=E.columns, fill_value=0).sum(axis=1)
    df["elite_list"] = [
        "; ".join(("★ " if B.at[i, c] == 1 else "") + _label(c) for c in E.columns if E.at[i, c] == 1)
        for i in df.index]
    el = df[df["elite_n"] > 0].copy()
    sort_col = "entry_confirmed" if "entry_confirmed" in el.columns else "entry_today_asymmetry"
    el = el.sort_values(["elite_n", "elite_both_n", sort_col], ascending=[False, False, False])
    print(f"  elite names: {len(el):,} across {el['src'].nunique()} countries; "
          f"{E.shape[1]} archetypes contribute", file=sys.stderr)

    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    tab_colors.set_tab(cover, tab_colors.COVER)
    cover.cell(row=2, column=2, value="Elite Country Book — only the most exceptional").font = _font(bold=True, size=14)
    notes = [
        "Each archetype is made extremely stringent. A name appears for an archetype only if:",
        "• tiered archetypes: in the TOP 10% of the core on the archetype's defining measure (elite), or passing its "
        "qualitative exceptional test; ★ = both",
        "• other archetypes: member AND top 5% by multi-measure confirmation AND no red accounting tell AND >= $250k/week "
        "traded AND clean data",
        "Excluded everywhere: preferred / warrant lines, RED verdicts, clinical-stage biotech (binary-event driven).",
        "Country sheets rank names by the number of archetypes they are elite on, then by confirmed entry asymmetry.",
    ]
    for i, t in enumerate(notes, start=4):
        cover.cell(row=i, column=2, value=t).font = _font(italic=(i > 4), color=INK if i == 4 else MUTED)
    _section_rule(cover, 11, "Elite names by archetype (columns = countries with the most elite names)", span_cols=12)
    top_c = el["src"].value_counts().head(10).index.tolist()
    cover.cell(row=12, column=2, value="Archetype").font = _font(bold=True, color=MUTED)
    cover.cell(row=12, column=3, value="All").font = _font(bold=True, color=MUTED)
    for j, c in enumerate(top_c, start=4):
        cover.cell(row=12, column=j, value=c).font = _font(bold=True, color=MUTED)
    r = 13
    for col in sorted(E.columns, key=lambda c: -int(E[c].sum())):
        cover.cell(row=r, column=2, value=_label(col)).font = _font()
        cover.cell(row=r, column=3, value=int(E[col].sum())).font = _font(bold=True)
        for j, c in enumerate(top_c, start=4):
            v = int(E.loc[df["src"] == c, col].sum())
            if v:
                cover.cell(row=r, column=j, value=v).font = _font()
        r += 1
    cover.column_dimensions["B"].width = 40
    cover.sheet_view.showGridLines = False

    hdr = ["#", "Ticker", "Name", "Sector", "Mcap (USD)", "Elite #", "★ #", "Elite archetypes (★ = elite AND exceptional)",
           "EV/EBITDA", "P/E", "P/B", "FCF yld %", "ROCE %", "Mom 12m %", "Accounting check", "Signals"]
    widths = [4, 11, 30, 16, 14, 7, 5, 70, 9, 8, 7, 9, 8, 10, 40, 60]
    for country in ordered_countries(el["src"].value_counts().index.tolist()):
        cdf = el[el["src"] == country]
        if cdf.empty:
            continue
        ws = wb.create_sheet(_sheet_safe(f"{country} ({len(cdf)})"))
        bucket, region = classify(country)
        tab_colors.set_tab(ws, tab_colors.FAMILY_COLORS.get("quality", tab_colors.COVER))
        ws.cell(row=1, column=1, value=f"{country} — {region} ({bucket}): {len(cdf)} elite names").font = _font(bold=True, size=12)
        for j, h in enumerate(hdr, start=1):
            ws.cell(row=3, column=j, value=h).font = _font(bold=True, color=MUTED)
            ws.cell(row=3, column=j).border = Border(bottom=Side(style="thin", color=INK))
        for i, (_, rr) in enumerate(cdf.iterrows(), start=1):
            row = 3 + i
            ws.cell(row=row, column=1, value=i).font = _font(color=MUTED)
            ws.cell(row=row, column=2, value=rr["symbol"]).font = _font(bold=True)
            ws.cell(row=row, column=3, value=str(rr.get("name") or "")[:32])
            ws.cell(row=row, column=4, value=str(rr.get("sector") or "")[:18]).font = _font(color=MUTED)
            _write_money(ws, row, 5, rr.get("market_cap_usd"))
            _write_int(ws, row, 6, int(rr["elite_n"]))
            _write_int(ws, row, 7, int(rr["elite_both_n"]))
            c = ws.cell(row=row, column=8, value=rr["elite_list"]); c.alignment = _TXT_ALIGN_LEFT
            _write_score(ws, row, 9, rr.get("ev_ebitda")); _write_score(ws, row, 10, rr.get("p_e"))
            _write_score(ws, row, 11, rr.get("pb")); _write_pct(ws, row, 12, rr.get("fcf_yield"))
            _write_pct(ws, row, 13, rr.get("roce")); _write_pct(ws, row, 14, rr.get("momentum_12m"))
            ak = acct_check(rr)
            c = ws.cell(row=row, column=15, value=ak)
            c.font = _font(color=("B42318" if ak.startswith("WARN") else INK)); c.alignment = _TXT_ALIGN_LEFT
            c = ws.cell(row=row, column=16, value=str(rr.get("fmp_signals") or "")[:200]); c.alignment = _TXT_ALIGN_LEFT
            for j in range(1, len(hdr) + 1):
                ws.cell(row=row, column=j).border = Border(bottom=Side(style="thin", color=RULE))
        for j, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "D4"
        ws.auto_filter.ref = f"A3:{get_column_letter(len(hdr))}{ws.max_row}"
        ws.sheet_view.showGridLines = False
    wb.save(args.out)
    from harvard_style import sanitize_nan_text
    sanitize_nan_text(args.out)
    print(f"wrote {args.out}: {len(wb.worksheets)} sheets", file=sys.stderr)


if __name__ == "__main__":
    main()
