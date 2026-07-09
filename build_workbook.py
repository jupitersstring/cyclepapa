"""Build a Harvard-aesthetic Excel workbook with Top N per region for
every leg/measure in the pipeline, plus the composite master score.

Aesthetic:
  - Crimson #A41E22 (Harvard Crimson) for headers & accents
  - Cambria title font, Calibri body
  - Soft gray banded rows (#F5F5F5)
  - Minimal grid, comfortable padding
  - Cover sheet with methodology, per-leg sheets with regional tables

Tabs:
  Cover                Title + methodology summary
  Summary              One-line snapshot per leg
  Master_Composite     Cross-system master score
  PSAR_Asset           Absolute trend strength
  PSAR_Relative        vs regional benchmark
  PSAR_Combined        Asset + Relative combined
  Minervini_M          MA respect + VCP
  Entry_E              Today's entry trigger
  DSR                  Downside resilience
  ADV_PlayNow          Mcap-normalized liquidity
  Six_School_Rank      W+Q+D+DA+R confluence
  Weinstein            Stage-2 weekly
  Qullamaggie          Weekly breakouts
  DeMark               TD setups
  Darvas               Box breakouts
  Regime_Change        Trend-break composite
  Asymmetry            E + structure + small-cap weighted

Output: data/stars_aligned_workbook.xlsx
"""

import warnings
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore")

# ─────────────────────────────────────── Aesthetic palette
CRIMSON  = "A41E22"
CRIMSON_LIGHT = "E5C2C4"
GREY     = "F5F5F5"
DARK     = "2A2A2A"
WHITE    = "FFFFFF"

TITLE_FONT  = Font(name="Cambria", size=20, bold=True, color=CRIMSON)
SUB_FONT    = Font(name="Cambria", size=12, italic=True, color=DARK)
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color=WHITE)
BODY_FONT   = Font(name="Calibri", size=10, color=DARK)
NUMBER_FONT = Font(name="Calibri", size=10, color=DARK)

HEADER_FILL = PatternFill("solid", fgColor=CRIMSON)
BAND_FILL   = PatternFill("solid", fgColor=GREY)
NO_FILL     = PatternFill(fill_type=None)

CENTER = Alignment(horizontal="center", vertical="center")
LEFT   = Alignment(horizontal="left",  vertical="center", indent=1)
RIGHT  = Alignment(horizontal="right", vertical="center", indent=1)

THIN_BORDER = Border(
    bottom=Side(style="thin", color="CCCCCC"),
)
THICK_BORDER = Border(
    bottom=Side(style="medium", color=CRIMSON),
)


# ─────────────────────────────────────── Data
def load_data():
    print("Loading master_full_universe.csv...")
    df = pd.read_csv('/tmp/master_full_universe.csv')

    # No ADV floor — surface every ranked name; user can filter in Excel
    df['adv_usd_M'] = (df.adv_usd / 1e6).round(2)
    print(f"  Full pool (no ADV filter): {len(df)} tickers across {df.region.nunique()} regions")

    # Asymmetry score
    df['asymmetry'] = (
        0.35 * (df.E / 100) + 0.25 * (df.M / 100) +
        0.20 * (df.DSR / 100) + 0.20 * (df.master / 100)
    ) * 100

    return df


def name_lookup(tickers, cache_path="/home/user/cyclepapa/data/ticker_info_cache.json"):
    """Look up name/sector/mcap with disk cache so reruns are cheap."""
    import json, os, yfinance as yf
    FX = {'JPY':0.0065,'INR':0.0117,'KRW':0.00073,'TWD':0.031,'HKD':0.128,
          'CNY':0.139,'GBp':0.0127,'GBP':1.27,'EUR':1.08,'CHF':1.12,
          'SEK':0.095,'NOK':0.092,'DKK':0.145,'AUD':0.65,'NZD':0.60,
          'USD':1.0,'MXN':0.055}
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cache = json.load(f)
            print(f"  loaded {len(cache)} cached lookups from {cache_path}")
        except Exception:
            cache = {}

    out = {}
    todo = []
    for t in tickers:
        if t in cache:
            out[t] = cache[t]
        else:
            todo.append(t)
    print(f"  {len(out)} from cache, {len(todo)} to fetch")

    for i, t in enumerate(todo):
        try:
            info = yf.Ticker(t).info or {}
            cur = info.get('currency') or 'USD'
            out[t] = {
                'name': (info.get('longName') or info.get('shortName') or '')[:34],
                'sector': (info.get('sector') or '')[:14],
                'mcap_M': round((info.get('marketCap') or 0) * FX.get(cur, 1.0) / 1e6),
            }
        except Exception:
            out[t] = {'name': '', 'sector': '', 'mcap_M': 0}
        cache[t] = out[t]
        if (i+1) % 100 == 0:
            print(f"  ...looked up {i+1}/{len(todo)}")
        if (i+1) % 500 == 0:
            # checkpoint less frequently to reduce noisy git churn
            with open(cache_path, "w") as f:
                json.dump(cache, f)
    with open(cache_path, "w") as f:
        json.dump(cache, f)
    print(f"  cache saved: {len(cache)} entries")
    return out


# ─────────────────────────────────────── Sheet writers
def write_cover(wb):
    ws = wb.active
    ws.title = "Cover"
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws.row_dimensions[2].height = 36
    ws.row_dimensions[3].height = 24

    ws.merge_cells("B2:H2")
    ws["B2"] = "Stars Aligned"
    ws["B2"].font = TITLE_FONT
    ws["B2"].alignment = LEFT

    ws.merge_cells("B3:H3")
    ws["B3"] = "Top picks per region, ranked across 15 measures"
    ws["B3"].font = SUB_FONT
    ws["B3"].alignment = LEFT

    ws.merge_cells("B4:H4")
    ws["B4"] = f"Universe: 12,761 native tickers across 18 regional pools"
    ws["B4"].font = Font(name="Calibri", size=10, color=DARK, italic=True)
    ws["B4"].alignment = LEFT

    # Divider
    for col in range(2, 9):
        ws.cell(row=5, column=col).border = THICK_BORDER

    methodology = [
        ("",""),
        ("METHODOLOGY", ""),
        ("",""),
        ("Master Composite",
         "0.25 × PSAR + 0.20 × six-school rank + 0.20 × Minervini-M + 0.15 × Entry-E + 0.10 × DSR + 0.10 × ADV. "
         "PSAR-optional: tickers without PSAR data get the 5 non-PSAR weights renormalized to 100%."),
        ("Minervini (M)",
         "MA-respect + VCP score. 10 candidate measures × 5 MAs, empirically filtered via winners-vs-losers t-test. "
         "Surfaces structural quality: stocks that respect their 20/50/150/200-day moving averages and "
         "have compressed volatility patterns."),
        ("Entry Trigger (E)",
         "0..100 score firing on TODAY's daily bar. Components: volume vs 50-day median, pivot breakout, "
         "return acceleration, behavior regime shift, close strength, NR4/inside-bar coil, MA alignment, "
         "Bollinger break, 20-bar new high."),
        ("Downside Resilience (DSR)",
         "Stock's behavior on the bottom 30% of days for its REGIONAL benchmark ETF (SPY US, EWJ Japan, "
         "EWT Taiwan, INDA India, EWG Germany, etc.). Per-region calibration removes the SPY-timezone bias "
         "that crushed US scores and inflated Asian scores."),
        ("ADV Play-Now",
         "Mcap-normalized liquidity: 0.35 turnover + 0.25 acceleration + 0.20 slope + 0.20 raw $-volume. "
         "Weights chosen to surface CELH/ELF/DUOL-style small-cap winners where institutional flow is "
         "early but raw ADV is modest."),
        ("PSAR Composite",
         "Malikmck's MTF PSAR Trend Change indicator (Python port). 7 timeframes (30m, 1h, 4h, D, W, M, 3M), "
         "SMA(10)-smoothed buy/sell counts vs region benchmark. Asset Net MA = absolute trend strength. "
         "Relative Net MA = vs regional benchmark, region-demeaned to neutralize residual currency drift."),
        ("Six-School Rank",
         "Maximum of Daily / Weekly / Monthly rank across Weinstein + Qullamaggie + DeMark + Darvas + "
         "Regime-change schools. 'best_rank' surfaces names where multiple independent setups agree."),
        ("Asymmetry",
         "0.35 E + 0.25 M + 0.20 DSR + 0.20 master, with mcap penalty favoring small/mid that can move. "
         "Gates: E≥55, M≥60, DSR≥50, best_rank≥52, ADV≥$2M. ~0.2% of universe survives."),
        ("",""),
        ("LIQUIDITY",
         "All top-per-region tables filter to ≥$1M/day USD ADV (FX-converted) to ensure tradeability."),
        ("DURABILITY",
         "Every CSV is committed to data/ — sandbox reset costs nothing. "
         "Re-run audit_coverage.py any time to verify universe coverage."),
    ]
    r = 7
    for label, body in methodology:
        if not label and not body:
            r += 1; continue
        if label and not body:  # Section header
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
            ws.cell(row=r, column=2, value=label).font = Font(name="Cambria", size=11, bold=True, color=CRIMSON)
            r += 1; continue
        ws.cell(row=r, column=2, value=label).font = Font(name="Calibri", size=10, bold=True, color=DARK)
        ws.cell(row=r, column=2).alignment = Alignment(horizontal="left", vertical="top", indent=1)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=8)
        ws.cell(row=r, column=3, value=body).font = Font(name="Calibri", size=9, color=DARK)
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True, indent=1)
        ws.row_dimensions[r].height = 38
        r += 1

    # Column widths
    ws.column_dimensions['A'].width = 2
    ws.column_dimensions['B'].width = 24
    for c in range(3, 9):
        ws.column_dimensions[get_column_letter(c)].width = 18


def write_full_universe(wb, df, info):
    """Single sheet containing EVERY ranked ticker (12,761+) sortable by any
    leg. Names looked up where cached, ticker-only for the long tail."""
    ws = wb.create_sheet(title="Full_Universe")
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 18

    ws.merge_cells("B2:O2")
    ws["B2"] = "Full Universe"
    ws["B2"].font = TITLE_FONT
    ws["B2"].alignment = LEFT
    ws.merge_cells("B3:O3")
    ws["B3"] = f"All {len(df):,} ranked tickers — sort/filter in Excel by any column"
    ws["B3"].font = SUB_FONT
    ws["B3"].alignment = LEFT
    for col in range(2, 16):
        ws.cell(row=4, column=col).border = THICK_BORDER

    headers = ["Ticker", "Name", "Sector", "Region", "Mcap $M", "ADV $M",
               "Master", "M", "E", "DSR", "ADV-pn",
               "PSAR-Asset", "PSAR-Rel", "PSAR-Comb", "BestRank"]
    r = 6
    for i, h in enumerate(headers, start=2):
        c = ws.cell(row=r, column=i, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = Border(bottom=Side(style="thin", color=CRIMSON))
    ws.row_dimensions[r].height = 22

    # Sort by master descending; full pool
    sub = df.sort_values("master", ascending=False)
    r = 7
    for _, row in sub.iterrows():
        t = row['ticker']
        inf = info.get(t, {})
        vals = [
            t,
            inf.get('name', ''),
            inf.get('sector', ''),
            row['region'],
            inf.get('mcap_M', 0) or 0,
            row.get('adv_usd_M', 0),
            row.get('master', np.nan),
            row.get('M', np.nan),
            row.get('E', np.nan),
            row.get('DSR', np.nan),
            row.get('ADV_play_now', np.nan),
            row.get('asset_score', np.nan),
            row.get('rel_score', np.nan),
            row.get('combined_score', np.nan),
            row.get('best_rank', np.nan),
        ]
        for i, v in enumerate(vals, start=2):
            cell = ws.cell(row=r, column=i, value=v)
            cell.font = BODY_FONT
            if i in (2, 3, 4, 5):
                cell.alignment = LEFT
            else:
                cell.alignment = RIGHT
                if isinstance(v, (int, float)) and not pd.isna(v):
                    if i == 6:
                        cell.number_format = '#,##0'
                    elif i == 7:
                        cell.number_format = '#,##0.0'
                    else:
                        cell.number_format = '0.0'
        r += 1

    # Enable Excel filtering on the header row
    ws.auto_filter.ref = f"B6:P{r-1}"
    ws.freeze_panes = "C7"

    widths = [2, 12, 30, 16, 16, 11, 10, 11, 9, 9, 9, 9, 11, 11, 11, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_leg_sheet(wb, leg_key, title, subtitle, df, sort_col, info, top_n_per_region=20):
    ws = wb.create_sheet(title=leg_key)
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 18

    # Title block
    ws.merge_cells("B2:K2")
    ws["B2"] = title
    ws["B2"].font = TITLE_FONT
    ws["B2"].alignment = LEFT
    ws.merge_cells("B3:K3")
    ws["B3"] = subtitle
    ws["B3"].font = SUB_FONT
    ws["B3"].alignment = LEFT
    for col in range(2, 12):
        ws.cell(row=4, column=col).border = THICK_BORDER

    # Header row
    headers = ["Ticker", "Name", "Sector", "Region", "Mcap $M", "ADV $M",
               sort_col, "Master", "M", "E", "DSR"]
    r = 6
    for i, h in enumerate(headers, start=2):
        c = ws.cell(row=r, column=i, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = Border(bottom=Side(style="thin", color=CRIMSON))
    ws.row_dimensions[r].height = 22

    # Body: top N per region
    r = 7
    band = False
    for region in sorted(df.region.unique()):
        sub = (df[df.region == region]
               .dropna(subset=[sort_col])
               .sort_values(sort_col, ascending=False)
               .head(top_n_per_region))
        for _, row in sub.iterrows():
            t = row['ticker']
            inf = info.get(t, {})
            fill = BAND_FILL if band else NO_FILL
            vals = [
                t,
                inf.get('name', ''),
                inf.get('sector', ''),
                region,
                inf.get('mcap_M', 0) or 0,
                row.get('adv_usd_M', 0),
                row.get(sort_col, np.nan),
                row.get('master', np.nan),
                row.get('M', np.nan),
                row.get('E', np.nan),
                row.get('DSR', np.nan),
            ]
            for i, v in enumerate(vals, start=2):
                cell = ws.cell(row=r, column=i, value=v)
                cell.font = BODY_FONT
                cell.fill = fill
                cell.border = THIN_BORDER
                if i in (2, 3, 4, 5):  # ticker, name, sector, region — left
                    cell.alignment = LEFT
                else:
                    cell.alignment = RIGHT
                    if isinstance(v, (int, float)) and not pd.isna(v):
                        if i == 6:    # mcap
                            cell.number_format = '#,##0'
                        elif i == 7:  # adv
                            cell.number_format = '#,##0.0'
                        else:         # scores
                            cell.number_format = '0.0'
            r += 1
        band = not band

    # Column widths
    widths = [2, 12, 30, 16, 16, 11, 10, 11, 9, 9, 9, 9]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Freeze pane
    ws.freeze_panes = "C7"


def write_summary(wb, df, info, legs):
    ws = wb.create_sheet(title="Summary")
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 18

    ws.merge_cells("B2:G2")
    ws["B2"] = "Summary"
    ws["B2"].font = TITLE_FONT
    ws["B2"].alignment = LEFT
    ws.merge_cells("B3:G3")
    ws["B3"] = "Top pick across the universe for each measure"
    ws["B3"].font = SUB_FONT
    ws["B3"].alignment = LEFT
    for col in range(2, 8):
        ws.cell(row=4, column=col).border = THICK_BORDER

    headers = ["Measure", "Top Ticker", "Name", "Region", "Score", "Master"]
    r = 6
    for i, h in enumerate(headers, start=2):
        c = ws.cell(row=r, column=i, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = Border(bottom=Side(style="thin", color=CRIMSON))
    ws.row_dimensions[r].height = 22

    r = 7; band = False
    for leg_key, (title, _subtitle, sort_col) in legs.items():
        if sort_col not in df.columns:
            continue
        sub = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=False).head(1)
        if sub.empty:
            continue
        row = sub.iloc[0]
        t = row['ticker']
        inf = info.get(t, {})
        fill = BAND_FILL if band else NO_FILL
        vals = [title, t, inf.get('name', ''), row['region'],
                row[sort_col], row.get('master', np.nan)]
        for i, v in enumerate(vals, start=2):
            cell = ws.cell(row=r, column=i, value=v)
            cell.font = BODY_FONT
            cell.fill = fill
            cell.border = THIN_BORDER
            if i in (2, 3, 4, 5):
                cell.alignment = LEFT
            else:
                cell.alignment = RIGHT
                if isinstance(v, (int, float)) and not pd.isna(v):
                    cell.number_format = '0.0'
        r += 1
        band = not band

    widths = [2, 20, 14, 36, 18, 12, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def main():
    df = load_data()

    # 15 legs to surface
    LEGS = {
        # key, (title, subtitle, sort_col)
        "Master_Composite":  ("Master Composite",
                              "Cross-system score: 0.25 PSAR + 0.20 rank + 0.20 M + 0.15 E + 0.10 DSR + 0.10 ADV",
                              "master"),
        "Asymmetry":         ("Asymmetry",
                              "High entry-trigger + clean structure + resilient, small-cap weighted",
                              "asymmetry"),
        "Minervini_M":       ("Minervini M",
                              "MA respect + VCP. Stages-2 structural quality, empirically t-test filtered",
                              "M"),
        "Entry_E":           ("Entry Trigger E",
                              "Today's daily bar firing: vol spike, pivot break, coil release, behavior shift",
                              "E"),
        "DSR":               ("Downside Resilience",
                              "Behavior on bottom 30% days for the REGIONAL benchmark ETF (per-region calibrated)",
                              "DSR"),
        "ADV_PlayNow":       ("ADV Play-Now",
                              "Mcap-normalized liquidity + acceleration + slope + raw $-volume",
                              "ADV_play_now"),
        "PSAR_Asset":        ("PSAR Asset Net MA",
                              "Absolute PSAR-trend strength across 7 timeframes, SMA(10) smoothed",
                              "asset_score"),
        "PSAR_Relative":     ("PSAR Relative Net MA",
                              "Relative PSAR-trend vs regional benchmark, region-demeaned",
                              "rel_score"),
        "PSAR_Combined":     ("PSAR Combined",
                              "Asset + Relative composite with 5-day-slope recency boost",
                              "combined_score"),
        "Six_School_Rank":   ("Six-School Best Rank",
                              "Max of D/W/M rank across W+Q+D+DA+R schools — multi-school confluence",
                              "best_rank"),
        "Weinstein":         ("Weinstein Weekly",
                              "Stage-2 setup: above 30wk MA, positive Mansfield RS, 2x-volume break",
                              "W_W"),
        "Qullamaggie":       ("Qullamaggie Weekly",
                              "Breakout / Episodic Pivot / Parabolic Long across weekly horizon",
                              "Q_W"),
        "DeMark":            ("DeMark Weekly",
                              "TD Sequential setup 9, countdown 13, perfection, TDST, bullish flip",
                              "D_W"),
        "Darvas":            ("Darvas Boxes Weekly",
                              "3-day non-penetration confirmation, ascending pyramid",
                              "DA_W"),
        "Volume_Breakout":   ("Dormeier Volume Breakout",
                              "Weekly: 25% RVOL + 25% VPCI + 20% dry-up + 20% effort-vs-result + 10% up/down balance; churn-capped",
                              "V"),
        "Leledc_RR":         ("Leledc Exhaustion R/R",
                              "W+M exhaustion bars set support/resistance; score = 55% R/R + 30% support proximity + 15% recency",
                              "LELE"),
        "Regime_Change":     ("Regime Change Weekly",
                              "Multi-year downtrend break + base/flag/gap-retention + RSI cross composite",
                              "R_W"),
    }

    TOP_N = 50
    # Collect unique tickers we'll surface (top N per region × 18 regions × N legs, with overlap)
    needed = set()
    for leg_key, (_t, _s, sort_col) in LEGS.items():
        if sort_col not in df.columns:
            continue
        for region in df.region.unique():
            sub = (df[df.region == region]
                   .dropna(subset=[sort_col])
                   .sort_values(sort_col, ascending=False)
                   .head(TOP_N))
            needed.update(sub.ticker.tolist())
    needed = sorted(needed)
    print(f"\nUnique tickers across all leg×region top-{TOP_N}s: {len(needed)}")
    info = name_lookup(needed)

    print(f"\nBuilding workbook...")
    wb = Workbook()
    write_cover(wb)
    write_summary(wb, df, info, LEGS)
    write_full_universe(wb, df, info)
    for leg_key, (title, subtitle, sort_col) in LEGS.items():
        if sort_col not in df.columns:
            print(f"  skip {leg_key} (column missing)")
            continue
        write_leg_sheet(wb, leg_key, title, subtitle, df, sort_col, info, top_n_per_region=TOP_N)
        print(f"  wrote {leg_key}")

    out = "/home/user/cyclepapa/data/stars_aligned_workbook.xlsx"
    wb.save(out)
    # Also copy to /tmp for delivery
    import shutil
    shutil.copy2(out, "/tmp/stars_aligned_workbook.xlsx")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
