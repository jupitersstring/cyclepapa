"""Cross-screener convergence report.

Walks every screener output directory, collects tickers that pass each
screener's filter, and surfaces names that show up in multiple lists.
The premise: a name surfaced by one screener is interesting; a name
surfaced by 4+ orthogonal screeners (e.g., inflection AND deep value AND
FCF yield acceleration AND operating leverage) is much more interesting.

Inputs (read from disk, no new fetches needed):
  results_us_wide/ranked.csv               -- multi-variant rolling-β inflection
  results_us_wide/fcf_inflections.csv      -- FCF sign-flip
  results_us_wide/deep_value_screen.csv    -- neg EV + Graham net-net
  results_us_wide/valuation_screen.csv     -- cheap P/B+P/S + inflecting
  results_eu_relaxed/ranked.csv            -- EU multi-variant
  results_canada/ranked.csv                -- Canada multi-variant
  results_uk/growth_uk.csv                 -- UK shallow growth
  results_eu_extra/growth.csv              -- NO/DK shallow growth
  results_52wh/screener.csv                -- 52w-high + cheap-on-growth
  results_multiple_compression/clean.csv   -- EPS up + P/E down + sub-200w
  results_ev_compression/screener.csv      -- sales/EBITDA up + EV/EBITDA down
  results_operating_leverage/screener.csv  -- sales growth + EBITDA margin runway
  results_ev_fcf_leverage/screener.csv     -- sales growth + FCF margin runway
  results_fcf_yield/screener.csv           -- FCF yield inflection/acceleration
  segment_inflection.csv                   -- EVC/Smadex segment pre-rerate
  pre_rerate_setups.csv                    -- segment + valuation triangulation
  results_volasym/volatility_asymmetry.csv -- Pine S&R + asymmetry

Output: convergence/{report.csv, top_picks.md}
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import pandas as pd, numpy as np

OUTDIR = Path('convergence'); OUTDIR.mkdir(exist_ok=True)


SCREENS: list[tuple[str, Path, str, callable]] = [
    # (label, path, ticker_column_or_None_for_index, filter_fn returning True if row passes)
    ('multi_variant_us',     Path('results_us_wide/ranked.csv'),         None,
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 4),
    ('multi_variant_eu',     Path('results_eu_relaxed/ranked.csv'),       None,
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 3),
    ('multi_variant_ca',     Path('results_canada/ranked.csv'),           None,
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 3),
    ('fcf_signflip_strict',  Path('results_us_wide/fcf_inflections.csv'), 'ticker',
        lambda r: r.get('view') == 'quarterly_strict' and r.get('metric') == 'fcf_ps' and r.get('is_flip') == True),
    ('fcf_signflip_ttm',     Path('results_us_wide/fcf_inflections.csv'), 'ticker',
        lambda r: r.get('view') == 'ttm_yoy' and r.get('metric') == 'fcf_ps' and r.get('is_flip') == True),
    ('deep_value_us',        Path('results_us_wide/deep_value_screen.csv'), None,
        lambda r: r.get('is_value_plus_inflection') == True),
    ('cheap_inflecting',     Path('results_us_wide/valuation_screen.csv'), None,
        lambda r: r.get('is_cheap_inflecting') == True),
    ('52wh_cheap',           Path('results_52wh/screener.csv'),           None,
        lambda r: True),    # screener.csv is pre-filtered
    ('multiple_compression', Path('results_multiple_compression/clean.csv'), None,
        lambda r: pd.notna(r.get('multiple_compression_pct')) and r.get('multiple_compression_pct') < -10),
    ('ev_compression',       Path('results_ev_compression/screener.csv'), None,
        lambda r: True),
    ('operating_leverage',   Path('results_operating_leverage/screener.csv'), None,
        lambda r: True),
    ('ev_fcf_leverage',      Path('results_ev_fcf_leverage/screener.csv'), None,
        lambda r: True),
    ('fcf_yield_setup',      Path('results_fcf_yield/screener.csv'),      None,
        lambda r: True),
    ('segment_pre_rerate',   Path('pre_rerate_setups.csv'),               None,
        lambda r: pd.notna(r.get('pre_rerate_score')) and r.get('pre_rerate_score') > 5),
    ('volasym_bullish',      Path('results_volasym/volatility_asymmetry.csv'), None,
        lambda r: r.get('m_state') in ('squeeze','hyper_squeeze') and r.get('m_asym_state') == 'upper'),
]


def main():
    membership: dict[str, set[str]] = defaultdict(set)
    extras: dict[str, dict[str, dict]] = defaultdict(dict)   # ticker -> screen -> sample fields

    for label, path, ticker_col, filt in SCREENS:
        if not path.exists():
            print(f"  [skip] {label:<28} (missing {path})")
            continue
        try:
            df = pd.read_csv(path, index_col=0 if ticker_col is None else None)
        except Exception as exc:
            print(f"  [err]  {label:<28} ({path}): {exc}")
            continue
        n_passed = 0
        for idx, row in df.iterrows():
            try:
                tkr = idx if ticker_col is None else row.get(ticker_col)
                if not isinstance(tkr, str): continue
                tkr = tkr.upper()
                if filt(row):
                    membership[tkr].add(label)
                    n_passed += 1
                    if label not in extras[tkr]:
                        extras[tkr][label] = {k: row.get(k) for k in row.index[:5]}
            except Exception:
                continue
        print(f"  [ok]   {label:<28} ({n_passed} qualifying tickers)")

    print(f"\nTotal unique tickers across all screens: {len(membership)}")

    # Build the convergence table
    rows = []
    for tkr, screens in membership.items():
        rows.append({
            'ticker': tkr,
            'n_screens': len(screens),
            'screens': sorted(screens),
        })
    conv = pd.DataFrame(rows).set_index('ticker')
    conv['screens_joined'] = conv['screens'].apply(lambda s: '; '.join(s))
    conv = conv.sort_values(['n_screens'], ascending=False)
    conv[['n_screens','screens_joined']].to_csv(OUTDIR / 'report.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print("\n===========================================================")
    print("HIGH-CONFIDENCE CONVERGENCE (5+ screeners)")
    print("===========================================================\n")
    high = conv[conv['n_screens'] >= 5]
    print(f"Count: {len(high)}\n")
    for tkr, row in high.iterrows():
        print(f"{tkr:>8}  ({int(row['n_screens'])} screens)")
        for s in row['screens']: print(f"             - {s}")

    print("\n===========================================================")
    print("STRONG CONVERGENCE (4 screeners)")
    print("===========================================================\n")
    mid = conv[conv['n_screens'] == 4]
    print(f"Count: {len(mid)}\n")
    for tkr, row in mid.iterrows():
        print(f"{tkr:>8}  -- {row['screens_joined']}")

    print("\n===========================================================")
    print("MODERATE CONVERGENCE (3 screeners)")
    print("===========================================================\n")
    low = conv[conv['n_screens'] == 3]
    print(f"Count: {len(low)}\n")
    for tkr, row in low.iterrows():
        print(f"{tkr:>8}  -- {row['screens_joined']}")

    # Write a markdown summary
    md_lines = ["# Cross-screener convergence report\n"]
    md_lines.append(f"Total tickers across {len(SCREENS)} screeners: {len(conv)}\n")
    for n_min, label in [(5, "5+ screens"), (4, "4 screens"), (3, "3 screens"), (2, "2 screens")]:
        sub = conv[conv['n_screens'] >= n_min] if label == "5+ screens" else conv[conv['n_screens'] == n_min]
        md_lines.append(f"\n## {label} ({len(sub)} tickers)\n")
        for tkr, row in sub.iterrows():
            md_lines.append(f"- **{tkr}** — {row['screens_joined']}")
    (OUTDIR / 'top_picks.md').write_text('\n'.join(md_lines))
    print(f"\nWrote convergence/report.csv and convergence/top_picks.md")


if __name__ == '__main__':
    main()
