"""Build the multi-sheet Excel deliverable.

Inputs:
  asymmetry_global.csv                  - quant rankings (4,983 names)
  qualitative_aligned_green.csv         - 26 GREEN from initial 8 region agents
  qualitative_red_avoid.csv             - 19 RED from initial 8 region agents
  qualitative_extended_verdicts.csv     - 80-90 additional verdicts from 4 follow-up agents

Outputs:
  asymmetry_country_workbook.xlsx       - master workbook
    Sheet 1: Master_By_Asymmetry  - top names global, ranked by asymmetry, qualitatively-amended
    Sheet 2: Master_By_Upside     - top names global, ranked by upside potential, qualitatively-amended
    Sheets 3-N: One per country with top 15-20 + verdicts

Qualitative amendment logic:
  GREEN  -> adj_asymmetry = asymmetry_score * 1.10  (10% boost)
  YELLOW -> adj_asymmetry = asymmetry_score * 0.85  (15% haircut)
  RED    -> adj_asymmetry = asymmetry_score * 0.40  (60% haircut - effectively removes from upper ranks)
  (not researched) -> adj_asymmetry = asymmetry_score (unchanged)
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np


def load_quant(p: str = 'asymmetry_global.csv') -> pd.DataFrame:
    df = pd.read_csv(p).drop_duplicates('symbol').sort_values('asymmetry_score', ascending=False)

    # Merge in the framework's intrinsic-value-discount measures from the
    # per-country yartseva snapshots (these fields exist on the raw scans
    # but were not propagated into asymmetry_global.csv).
    extra_cols = [
        'symbol','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
        'not_priced_in_score','revenue_ttm','balance_sheet_date',
    ]
    import glob, os
    yartseva_csvs = sorted(set(
        glob.glob('*_yartseva.csv')
        + glob.glob('us_nano_micro_small_yartseva.csv')
        + glob.glob('italian_yartseva.csv')
    ))
    extra_frames = []
    for f in yartseva_csvs:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in extra_cols)
        except Exception:
            continue
        if 'symbol' in d.columns:
            extra_frames.append(d)
    if extra_frames:
        extra = pd.concat(extra_frames, ignore_index=True).drop_duplicates('symbol', keep='first')
        # Avoid clobbering existing columns from asymmetry_global
        merge_cols = ['symbol'] + [c for c in extra.columns if c != 'symbol' and c not in df.columns]
        df = df.merge(extra[merge_cols], on='symbol', how='left')
    from otc_flag import apply_otc_mode as _apply_otc
    df = _apply_otc(df, 'ex-otc')   # general books: genuine listings only
    return df


def load_verdicts() -> pd.DataFrame:
    """Concat all qualitative verdict CSVs into a single (symbol, verdict, thesis) frame."""
    frames = []
    for path, default in [
        ('qualitative_aligned_green.csv', 'GREEN'),
        ('qualitative_red_avoid.csv', 'RED'),
        ('qualitative_extended_verdicts.csv', None),
    ]:
        if not os.path.exists(path):
            continue
        try:
            d = pd.read_csv(path)
        except pd.errors.ParserError:
            # Some thesis lines have unquoted commas; fall back to python engine
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default is not None:
            d['verdict'] = default
        keep = [c for c in ['symbol','verdict','why','why_avoid','thesis'] if c in d.columns]
        d = d[keep].copy()
        # Standardise the thesis column
        thesis_col = next((c for c in ['why','why_avoid','thesis'] if c in d.columns), None)
        if thesis_col:
            d['thesis'] = d[thesis_col]
        else:
            d['thesis'] = ''
        frames.append(d[['symbol','verdict','thesis']])
    if not frames:
        return pd.DataFrame(columns=['symbol','verdict','thesis'])
    # keep='last' so the LATEST verdict for a symbol wins.  Earlier verdict
    # files load first; qualitative_extended_verdicts.csv is the rolling
    # diligence log and represents the most current view, including any
    # downgrades on previously-GREEN names.
    out = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')
    return out


def amend_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Apply qualitative multiplier to the asymmetry score and the upside score."""
    # Soft multiplier used on the master sheets (keeps RED in the table for
    # transparency, with a heavy haircut).
    mult = {
        'GREEN': 1.10,
        'YELLOW': 0.85,
        'RED': 0.40,
    }
    df['qual_multiplier'] = df['verdict'].map(mult).fillna(1.0)

    # Stricter multiplier for per-country tops: drops RED entirely, gives
    # GREEN a stronger boost, treats UNRESEARCHED as cautious (haven't
    # validated yet so should not lead a country list).
    strict_mult = {
        'GREEN': 1.30,
        'YELLOW': 0.70,
        'RED': 0.0,             # excluded from per-country tops
        'UNRESEARCHED': 0.85,
    }
    df['strict_qual_multiplier'] = df['verdict'].map(strict_mult).fillna(0.85)

    # Multi-measure confirmation upweight (pool-preserving, <=30%): float names
    # up where independent accounting measures + insider alignment agree — the
    # same treatment the archetype books apply via entry_confirmed. Folded into
    # every ranking key below; the raw asymmetry_score is still shown.
    _cfo = pd.to_numeric(df.get('confirm_overall'), errors='coerce').fillna(0.0)
    _bbs = pd.to_numeric(df.get('buyback_score'), errors='coerce').fillna(0.0)
    df['confirm_mult'] = 1.0 + 0.20 * _cfo + 0.10 * _bbs

    df['adj_asymmetry'] = df['asymmetry_score'] * df['qual_multiplier'] * df['confirm_mult']
    df['adj_upside']    = df['upside_score']    * df['qual_multiplier'] * df['confirm_mult']

    # ----- Discount to intrinsic value (entry-today lens) -----
    # Built from the framework's existing measures of how cheap the stock
    # is RIGHT NOW vs intrinsic value (book / NCAV / net cash / EV multiples
    # / not-priced-in). Higher = bigger margin of safety on entry today.
    #
    #   30% net cash / mcap          (cash above debt as % of mcap, capped 0..1)
    #   20% NCAV / mcap              (Graham working-capital cushion, capped 0..1)
    #   20% (1 - pb)                 (sub-book bonus when pb < 1)
    #   15% cash > EV strength       (cash_pct_ev - 1 mapped to 0..1, cap at 3x)
    #   15% not_priced_in_score      (fundamentals running ahead of price)
    def _series(col, default=0.0):
        if col in df.columns:
            return df[col].fillna(default)
        return pd.Series(default, index=df.index)

    def clip01(s):
        return s.clip(0, 1).fillna(0)

    nc_pct  = clip01(_series('net_cash_pct_mcap'))
    ncav    = clip01(_series('ncav_pct_mcap'))
    sub_book = clip01(1.0 - _series('pb', 2.0).clip(lower=0.01))
    cash_ev_strength = clip01(
        (_series('cash_pct_ev') - 1.0).clip(0, 2) / 2.0
    )
    not_priced = clip01(_series('not_priced_in_score'))

    df['intrinsic_discount'] = (
        0.30 * nc_pct
        + 0.20 * ncav
        + 0.20 * sub_book
        + 0.15 * cash_ev_strength
        + 0.15 * not_priced
    )

    # Entry-today asymmetry = the existing asymmetry score scaled by the
    # depth of discount-to-intrinsic-value, then qualitatively amended.
    # The boost factor sits in roughly [0.5, 1.5] so a name with strong
    # framework-measured discount gets a meaningful lift, weak ones get a
    # haircut, but neither dominates the existing quant ranking.
    boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.5, 1.5)

    # POST-RALLY PENALTY (added 2026-06-15 after WDC bug, revised):
    # A name already up >100 pct in 12m is no longer a 'multibagger setup' -
    # it's an in-flight or completed multibagger. DEMOTE but do NOT exclude:
    # extreme-momentum names stay in the list, just ranked lower.
    # Schedule (smoother, floored at 0.40):
    #   mom_12m <= 0.30 (up <30 pct):       factor = 1.00
    #   mom_12m 0.30 to 1.00 (up 30-100):   linear 1.00 -> 0.75
    #   mom_12m 1.00 to 3.00 (up 100-300):  linear 0.75 -> 0.45
    #   mom_12m > 3.00 (up >4x):            factor = 0.40 (floor)
    # WDC at mom_12m 8.76 (up 876 pct): factor 0.40 -> still visible
    # but demoted from rank ~7 to outside top 200.
    mom = _series('momentum_12m').clip(-0.5, None)
    pr_factor = pd.Series(1.0, index=df.index)
    mid_rally = (mom > 0.30) & (mom <= 1.00)
    high_rally = (mom > 1.00) & (mom <= 3.00)
    extreme_rally = mom > 3.00
    pr_factor.loc[mid_rally] = 1.0 - (mom[mid_rally] - 0.30) / 0.70 * 0.25
    pr_factor.loc[high_rally] = 0.75 - (mom[high_rally] - 1.00) / 2.00 * 0.30
    pr_factor.loc[extreme_rally] = 0.40
    df['post_rally_factor'] = pr_factor.round(3)
    df['already_multibagged'] = (mom > 1.0).astype(int)

    df['entry_today_asymmetry'] = (
        df['asymmetry_score'] * boost * df['qual_multiplier'] * pr_factor * df['confirm_mult']
    )
    df['entry_today_upside']    = (
        df['upside_score']    * boost * df['qual_multiplier'] * pr_factor * df['confirm_mult']
    )

    # Strict variants used to sort per-country sheets. RED -> 0 (excluded);
    # GREEN gets +30% boost; YELLOW haircut to 0.70; UNRESEARCHED at 0.85.
    df['country_entry_asymmetry'] = (
        df['asymmetry_score'] * boost * df['strict_qual_multiplier'] * pr_factor * df['confirm_mult']
    )
    df['country_entry_upside']    = (
        df['upside_score']    * boost * df['strict_qual_multiplier'] * pr_factor * df['confirm_mult']
    )

    return df


def compose_thesis(row) -> str:
    bits = []
    # Cluster signals
    if pd.notna(row.get('cluster_n')) and row['cluster_n'] >= 4:
        bits.append(f'{int(row["cluster_n"])}-cluster')
    # Cash floor
    if row.get('cash_gt_ev_flag') == 1:
        bits.append('cash > EV')
    if row.get('graham_net_net_flag') == 1:
        bits.append('Graham net-net')
    if row.get('pew_negative_ev_flag') == 1:
        bits.append('neg-EV')
    # Sub-book
    if pd.notna(row.get('pb')) and 0 < row['pb'] < 1.0:
        bits.append(f'P/B {row["pb"]:.2f}')
    # Insider
    if pd.notna(row.get('insider_ownership_pct')) and row['insider_ownership_pct'] >= 0.30:
        bits.append(f'insider {row["insider_ownership_pct"]:.0%}')
    # Scores
    if pd.notna(row.get('yartseva_score')) and row['yartseva_score'] >= 0.55:
        bits.append(f'yart {row["yartseva_score"]:.2f}')
    if pd.notna(row.get('berezin_score')) and row['berezin_score'] >= 0.50:
        bits.append(f'Berez {row["berezin_score"]:.2f}')
    return '; '.join(bits)


def compose_why(row) -> str:
    """Verbose explanation of why this pick scored high, decomposed by leg.

    The qual-status tag now lists BOTH multipliers in use so the reader
    can see which leg matters where:
      - SOFT applies to Master sheets (adj_asymmetry, adj_upside)
      - STRICT applies to Per-Country and Per-Archetype sheets
        (country_entry_asymmetry; RED excluded entirely)
    Prior version printed only the STRICT mult, which was misleading on
    the Master sheets where the actual mult is +10 pct / -15 pct.
    """
    parts = []

    # 1. Qualitative status
    v = row.get('verdict', 'UNRESEARCHED')
    qt = row.get('thesis', '')
    if v == 'GREEN':
        parts.append(f"[GREEN | soft +10% / strict +30%] {qt}")
    elif v == 'YELLOW':
        parts.append(f"[YELLOW | soft -15% / strict -30%] {qt}")
    elif v == 'RED':
        parts.append(f"[RED | soft -60% / strict EXCLUDED] {qt}")
    else:
        parts.append("[UNRESEARCHED | soft no-change / strict -15%]")

    # 2. Downside floor (intrinsic value cushion)
    floor = []
    if row.get('cash_gt_ev_flag') == 1:
        cev = row.get('cash_pct_ev')
        if pd.notna(cev) and cev > 1:
            floor.append(f"cash {cev:.1f}x EV")
        else:
            floor.append("cash > EV")
    if row.get('graham_net_net_flag') == 1:
        floor.append("Graham net-net")
    nc = row.get('net_cash_pct_mcap')
    if pd.notna(nc) and nc > 0.3:
        floor.append(f"net cash {nc:.0%} of mcap")
    pb = row.get('pb')
    if pd.notna(pb) and 0 < pb < 1.0:
        floor.append(f"P/B {pb:.2f} (sub-book)")
    ncav = row.get('ncav_pct_mcap')
    if pd.notna(ncav) and ncav > 0.5:
        floor.append(f"NCAV {ncav:.0%} of mcap")
    ins = row.get('insider_ownership_pct')
    if pd.notna(ins) and ins >= 0.30:
        floor.append(f"insider {ins:.0%}")
    if floor:
        parts.append("Downside floor: " + ", ".join(floor))

    # 3. Upside drivers (inflection cluster + growth scores)
    upside = []
    cn = row.get('cluster_n')
    if pd.notna(cn) and cn >= 3:
        upside.append(f"{int(cn)} of 7 inflection signals firing")
    yart = row.get('yartseva_score')
    if pd.notna(yart) and yart >= 0.55:
        upside.append(f"Yartseva {yart:.2f}")
    berez = row.get('berezin_score')
    if pd.notna(berez) and berez >= 0.50:
        upside.append(f"Berezin {berez:.2f}")
    npi = row.get('not_priced_in_score')
    if pd.notna(npi) and npi > 0.5:
        upside.append(f"fundamentals running {npi:.1f}x ahead of price")
    if upside:
        parts.append("Upside: " + ", ".join(upside))

    # 4. Score composition
    ida = row.get('intrinsic_discount')
    if pd.notna(ida):
        parts.append(
            f"intrinsic discount {ida:.2f} "
            f"(boost {1.0 + (ida - 0.25):.2f}x)"
        )

    return " | ".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--per-country-n', type=int, default=30)
    p.add_argument('--top-master', type=int, default=200)
    p.add_argument('--out', default='asymmetry_country_workbook.xlsx')
    p.add_argument('--min-mcap', type=float, default=10_000_000)
    args = p.parse_args()

    df = load_quant()
    print(f'loaded quant: {len(df)} rows', file=sys.stderr)
    verdicts = load_verdicts()
    print(f'loaded verdicts: {len(verdicts)} names', file=sys.stderr)

    # Drop any pre-existing verdict/thesis so the merge wins
    df = df.drop(columns=[c for c in ('verdict','thesis') if c in df.columns])
    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    df['thesis']  = df['thesis'].fillna('')

    # Archetype tags - Yellowbrick taxonomy clusters C5/E/F/G + Narrative Lag (A)
    if os.path.exists('archetype_tags.csv'):
        tags = pd.read_csv('archetype_tags.csv')
        # Drop any pre-existing archetype cols from asymmetry_global
        overlap = [c for c in tags.columns if c != 'symbol' and c in df.columns]
        df = df.drop(columns=overlap)
        df = df.merge(tags, on='symbol', how='left')
        for c in tags.columns:
            if c == 'symbol':
                continue
            if c.startswith('arch_') or c == 'archetype_count':
                df[c] = df[c].fillna(0).astype(int)
            elif c == 'archetype_tags_str':
                df[c] = df[c].fillna('')
        print(f'merged archetype tags ({len(tags)} rows)', file=sys.stderr)
    df['quant_thesis'] = df.apply(compose_thesis, axis=1)
    df['full_thesis']  = df.apply(
        lambda r: (r['thesis'] + ' | ' + r['quant_thesis']).strip(' |'),
        axis=1,
    )
    df = amend_scores(df)
    df['why'] = df.apply(compose_why, axis=1)

    df = df[df['market_cap'].fillna(0) >= args.min_mcap]

    # Master rankings - 4 versions:
    #   1. By raw qualitatively-amended asymmetry (full upside)
    #   2. By raw qualitatively-amended upside    (full upside)
    #   3. By ENTRY-TODAY asymmetry  (upside discounted by 12m run-up)
    #   4. By ENTRY-TODAY upside     (upside discounted by 12m run-up)
    master_asym       = df.sort_values('adj_asymmetry', ascending=False).head(args.top_master).copy()
    master_upside     = df.sort_values('adj_upside', ascending=False).head(args.top_master).copy()
    master_entry_asym = df.sort_values('entry_today_asymmetry', ascending=False).head(args.top_master).copy()
    master_entry_ups  = df.sort_values('entry_today_upside', ascending=False).head(args.top_master).copy()

    master_cols = [
        'symbol','name','src','sector','market_cap_bucket','market_cap',
        'verdict',
        'entry_today_asymmetry','entry_today_upside','intrinsic_discount',
        'adj_asymmetry','asymmetry_score','confirm_overall','adj_upside','upside_score',
        'downside_floor_score','cluster_n','yartseva_score','berezin_score',
        'pb','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
        'not_priced_in_score','insider_ownership_pct',
        'cash_gt_ev_flag','graham_net_net_flag',
        'why','full_thesis','thesis',
    ]
    master_cols = [c for c in master_cols if c in df.columns]

    with pd.ExcelWriter(args.out, engine='openpyxl') as xl:
        # Entry-today views first (the more honest "buying today" lists)
        master_entry_asym[master_cols].to_excel(xl, sheet_name='Master_EntryToday_Asymmetry', index=False)
        master_entry_ups[master_cols].to_excel(xl,  sheet_name='Master_EntryToday_Upside', index=False)
        # Then the raw (full-asymmetry-cycle) views
        master_asym[master_cols].to_excel(xl, sheet_name='Master_By_Asymmetry', index=False)
        master_upside[master_cols].to_excel(xl, sheet_name='Master_By_Upside', index=False)

        # ----- Gems sheet: top GREEN multi-archetype + top single-archetype -----
        # Curated, opinionated short list: highest-conviction names where
        # qualitative verdict is GREEN AND quant signals stack across multiple
        # archetype clusters OR single archetype is exceptionally strong.
        gem_cols_show = [
            'symbol','name','src','sector','market_cap_bucket','market_cap',
            'verdict',
            'archetype_count','archetype_tags_str',
            'entry_today_asymmetry','country_entry_asymmetry','intrinsic_discount',
            'cluster_n','yartseva_score','berezin_score',
            'pb','net_cash_pct_mcap','cash_pct_ev','insider_ownership_pct',
            'why','full_thesis','thesis',
        ]
        gem_cols_show = [c for c in gem_cols_show if c in df.columns]
        green_pool = df[df['verdict']=='GREEN'].copy()
        # Multi-archetype gems (>= 2 tags) - the cluster-stacker thesis
        multi_gems = green_pool[green_pool.get('archetype_count', 0) >= 2] \
            .sort_values('entry_today_asymmetry', ascending=False)
        # Single-archetype gems with high asymmetry as complements
        single_gems = green_pool[green_pool.get('archetype_count', 0) == 1] \
            .sort_values('entry_today_asymmetry', ascending=False).head(20)
        gems = pd.concat([multi_gems, single_gems]).drop_duplicates('symbol', keep='first')
        gems[gem_cols_show].to_excel(xl, sheet_name='Gems', index=False)

        # ----- GARP Multibaggers sheet -----
        # v2 methodical screen with forensic fixes:
        # - Live financedatabase lookup for current sector/industry/name
        #   (catches stale-cached errors like ORZCF, TRU.L, PALM.JK, CTO.SI)
        # - REQUIRE positive FCF yield (real GARP generates cash, not just EBITDA)
        # - REQUIRE EBITDA growing YoY (confirms growth in earnings, not just rev)
        # - Industry-level exclusions (Mining/Metals/Pharma/Biotech/Casinos)
        # - SPAC dilution pattern excluded (rev_ttm < 20M AND mcap > 500M)
        # - Dedup by company name (kills NVDR-R + dual-listing duplicates)
        # - Cap rev_yoy <= 100% to filter one-shot M&A pops
        # Output: garp_score = 0.25 yart + 0.30 rev_3y_cagr + 0.25 ROCE + 0.20 EV/EBIT inverse
        garp_path = 'garp_candidates_v2_relaxed.csv'
        if not os.path.exists(garp_path):
            garp_path = 'garp_candidates_v2.csv'
        if os.path.exists(garp_path):
            garp_df = pd.read_csv(garp_path)
            # Merge verdicts so user sees qualitative status alongside
            verdict_map = df[['symbol','verdict','thesis','full_thesis','why']].drop_duplicates('symbol')
            garp_df = garp_df.drop(columns=[c for c in ['verdict','thesis'] if c in garp_df.columns], errors='ignore')
            garp_df = garp_df.merge(verdict_map, on='symbol', how='left')
            garp_df['verdict'] = garp_df['verdict'].fillna('UNRESEARCHED')
            garp_df = garp_df[garp_df['verdict'] != 'RED']
            garp_show = [
                'symbol','name','src','sector','industry','market_cap_bucket','market_cap',
                'verdict','garp_score',
                'rev_3y_cagr','rev_yoy','rev_5y_cagr',
                'ev_ebit','p_e','ebitda_margin','roce',
                'net_debt_ebitda','fcf_yield','net_cash_pct_mcap',
                'insider_ownership_pct','yartseva_score','berezin_score',
                'why','full_thesis','thesis',
            ]
            garp_show = [c for c in garp_show if c in garp_df.columns]
            garp_df.sort_values('garp_score', ascending=False).head(60)[garp_show]\
                .to_excel(xl, sheet_name='GARP_Multibaggers', index=False)

        # ----- Archetype cluster sheets (Yellowbrick taxonomy) -----
        cluster_specs = [
            (
                'ArchC_FixedCostDemandShock',
                ['arch_fixed_cost_demand_shock'],
                'Heavy-asset operators with positive revenue acceleration AND '
                'expanding EBITDA margin - the cluster-C5 setup.',
            ),
            (
                'ArchE_NAV_CapitalDiscipline',
                ['arch_discounted_vehicle', 'arch_capital_discipline'],
                'Sub-book + net-cash (E7) plus insider-aligned conservative '
                'compounders not yet re-rated (E8).',
            ),
            (
                'ArchF_Cyclical',
                ['arch_regime_cyclical', 'arch_dead_option'],
                'Heavy-asset cycle bottoms with margin inflection (F9) or '
                'deep-drawdown profitable orphans (F10).',
            ),
            (
                'ArchG_KPI_BlindSpot',
                ['arch_kpi_threshold', 'arch_blindspot'],
                'First-positive operating prints (G11) and under-covered '
                'small-cap geographies (G12).',
            ),
        ]

        archetype_cols_show = [
            'symbol','name','src','sector','market_cap_bucket','market_cap',
            'verdict',
            'archetype_tags_str',
            'arch_narrative_lag',          # the A modifier
            'country_entry_asymmetry','entry_today_asymmetry','intrinsic_discount',
            'asymmetry_score','upside_score','cluster_n',
            'yartseva_score','berezin_score',
            'pb','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
            'not_priced_in_score','insider_ownership_pct',
            'cash_gt_ev_flag','graham_net_net_flag',
            'why','full_thesis','thesis',
        ]
        archetype_cols_show = [c for c in archetype_cols_show if c in df.columns]

        # qual rank: GREEN best, then YELLOW, then UNRESEARCHED.  RED dropped.
        qual_rank = {'GREEN': 0, 'YELLOW': 1, 'UNRESEARCHED': 2}
        for sheet_name, arch_flags, _desc in cluster_specs:
            mask = pd.Series(False, index=df.index)
            for f in arch_flags:
                if f in df.columns:
                    mask = mask | (df[f] == 1)
            sub = df[mask & (df['verdict'] != 'RED')].copy()
            if sub.empty:
                continue
            sub['_qrank'] = sub['verdict'].map(qual_rank).fillna(2).astype(int)
            sub = sub.sort_values(
                by=['_qrank','country_entry_asymmetry'],
                ascending=[True, False],
            ).head(60)
            sub.drop(columns=['_qrank'])[archetype_cols_show].to_excel(
                xl, sheet_name=sheet_name[:31], index=False
            )

        # ----- Alta Fox Multibagger leg -----
        # Source: altafoxcapital.com 'Makings of a Multibagger' (2020 study of
        # 104 stocks with 350%+ TSR over 5 years).  Their specific screen:
        # country in {UK,SE,DE,NO,AU}, sector in {Tech, Healthcare}, mcap<$2B,
        # below 3x P/S, 20x EV/EBITDA, 30x P/E.  Composite score weights:
        # 20% geo / 15% sector / 15% size / 20% valuation / 15% growth /
        # 10% margin / 5% financial health.  See alta_fox_score.py.
        if os.path.exists('alta_fox_scores.csv'):
            af = pd.read_csv('alta_fox_scores.csv').drop_duplicates('symbol', keep='first')
            af_cols = ['symbol','alta_fox_score','alta_fox_strict_match',
                       'af_country_overrep','af_sector_overrep','af_size_lt_2b',
                       'af_cheap_count','af_growth_21pct','af_financially_healthy']
            df_af = df.merge(af[af_cols], on='symbol', how='left')
            af_show = [
                'symbol','name','src','sector','industry','market_cap_bucket','market_cap',
                'verdict',
                'alta_fox_score','alta_fox_strict_match',
                'af_country_overrep','af_sector_overrep','af_size_lt_2b',
                'af_cheap_count','af_growth_21pct','af_financially_healthy',
                'p_s','ev_ebitda','p_e','ebitda_margin','roce',
                'rev_3y_cagr','rev_yoy','yartseva_score','archetype_count','archetype_tags_str',
                'entry_today_asymmetry','intrinsic_discount','insider_ownership_pct',
                'why','full_thesis','thesis',
            ]
            af_show = [c for c in af_show if c in df_af.columns]
            # Sheet A: strict checklist matches (any qual except RED)
            strict = df_af[(df_af['alta_fox_strict_match']==1) & (df_af['verdict']!='RED')]\
                .sort_values('alta_fox_score', ascending=False)
            if not strict.empty:
                strict[af_show].to_excel(xl, sheet_name='AltaFox_StrictMatch', index=False)
            # Sheet B: top 60 by alta_fox_score regardless of strict match
            top = df_af[df_af['verdict']!='RED']\
                .sort_values('alta_fox_score', ascending=False).head(60)
            top[af_show].to_excel(xl, sheet_name='AltaFox_Top60', index=False)

        # ----- Per-archetype top N (one sheet per tag) -----
        # Eight archetypes from archetype_tags.py (cluster A + C5 + E + F + G).
        # Each sheet: top 40 names with that tag, GREEN-first then YELLOW then
        # UNRESEARCHED, sorted by entry_today_asymmetry within each verdict
        # tier.  RED dropped.
        per_archetype_specs = [
            ('Arch_NarrativeLag',         'arch_narrative_lag'),
            ('Arch_FixedCostDemandShock', 'arch_fixed_cost_demand_shock'),
            ('Arch_DiscountedVehicle',    'arch_discounted_vehicle'),
            ('Arch_CapitalDiscipline',    'arch_capital_discipline'),
            ('Arch_RegimeCyclical',       'arch_regime_cyclical'),
            ('Arch_DeadOption',           'arch_dead_option'),
            ('Arch_KPIThreshold',         'arch_kpi_threshold'),
            ('Arch_BlindSpot',            'arch_blindspot'),
        ]
        for sheet_name, flag in per_archetype_specs:
            if flag not in df.columns:
                continue
            sub = df[(df[flag] == 1) & (df['verdict'] != 'RED')].copy()
            if sub.empty:
                continue
            sub['_qrank'] = sub['verdict'].map(qual_rank).fillna(2).astype(int)
            sub = sub.sort_values(
                by=['_qrank','country_entry_asymmetry'],
                ascending=[True, False],
            ).head(40)
            sub.drop(columns=['_qrank'])[archetype_cols_show].to_excel(
                xl, sheet_name=sheet_name[:31], index=False
            )

        # Per-country summary - top 3 per country by the strict country
        # entry-today asymmetry (drops RED, boosts GREEN, treats
        # UNRESEARCHED cautiously).
        summary_rows = []
        for ctry, _ in df['src'].value_counts().items():
            sub = df[(df['src'] == ctry) & (df['verdict'] != 'RED')] \
                .sort_values('country_entry_asymmetry', ascending=False) \
                .head(3)
            for rank, (_, r) in enumerate(sub.iterrows(), start=1):
                summary_rows.append({
                    'country': ctry,
                    'country_rank': rank,
                    'symbol': r['symbol'],
                    'name': r['name'],
                    'sector': r.get('sector', ''),
                    'market_cap_bucket': r.get('market_cap_bucket', ''),
                    'market_cap': r.get('market_cap', 0),
                    'verdict': r.get('verdict', 'UNRESEARCHED'),
                    'country_entry_asymmetry': r.get('country_entry_asymmetry', 0),
                    'entry_today_asymmetry': r.get('entry_today_asymmetry', 0),
                    'intrinsic_discount': r.get('intrinsic_discount', 0),
                    'cluster_n': r.get('cluster_n', 0),
                    'pb': r.get('pb', 0),
                    'cash_gt_ev_flag': r.get('cash_gt_ev_flag', 0),
                    'insider_ownership_pct': r.get('insider_ownership_pct', 0),
                    'why': r.get('why', ''),
                    'thesis': r.get('full_thesis', ''),
                })
        pd.DataFrame(summary_rows).to_excel(xl, sheet_name='Per_Country_Top3', index=False)

        # Per-country sheets, sorted by adj_asymmetry within country
        per_country_cols = [
            'symbol','name','sector','market_cap_bucket','market_cap',
            'verdict',
            'country_entry_asymmetry','country_entry_upside','intrinsic_discount',
            'entry_today_asymmetry','entry_today_upside',
            'adj_asymmetry','adj_upside','asymmetry_score','confirm_overall','upside_score',
            'cluster_n','yartseva_score','berezin_score',
            'pb','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
            'not_priced_in_score','insider_ownership_pct',
            'cash_gt_ev_flag','graham_net_net_flag','why','full_thesis','thesis',
        ]
        per_country_cols = [c for c in per_country_cols if c in df.columns]

        # Country code -> long name for sheet titles (kept under Excel's 31-char limit)
        country_names = {
            'US':'USA','UK':'UK','DE':'Germany','FR':'France','IT':'Italy','NL':'Netherlands',
            'BE':'Belgium','CH':'Switzerland','IE':'Ireland','SE':'Sweden','NO':'Norway',
            'DK':'Denmark','FI':'Finland','AT':'Austria','ES':'Spain','GR':'Greece','PT':'Portugal',
            'CZ':'Czechia','HU':'Hungary','EE':'Estonia','LV':'Latvia','LT':'Lithuania',
            'PL':'Poland','IS':'Iceland',
            'SA':'SaudiArabia','AR':'Argentina','CL':'Chile','MY':'Malaysia',
            'CN':'China','RO':'Romania',
            'JP':'Japan','HK':'HongKong','KR':'Korea','TW':'Taiwan','SG':'Singapore',
            'IN':'India','ID':'Indonesia','TH':'Thailand','AU':'Australia','NZ':'NewZealand',
            'CA':'Canada','BR':'Brazil','MX':'Mexico','ZA':'SouthAfrica','TR':'Turkey','IL':'Israel',
        }
        # Order by number of survivors per country
        for ctry, _ in df['src'].value_counts().items():
            # Sort per-country sheets by the STRICT entry-today asymmetry
            # (drops RED, boosts GREEN, treats UNRESEARCHED cautiously).
            sub_all = df[df['src'] == ctry]
            sub = sub_all[sub_all['verdict'] != 'RED'] \
                .sort_values('country_entry_asymmetry', ascending=False) \
                .head(args.per_country_n)
            if len(sub) == 0:
                continue
            name = country_names.get(ctry, ctry)
            sheet = f'{name}_{ctry}'[:31]
            sub[per_country_cols].to_excel(xl, sheet_name=sheet, index=False)

    # Harvard house aesthetic: single Cambria 10pt, B&W, no fills,
    # bold header + thin rule, gridlines off, header frozen. Applied as
    # a post-pass so the pandas data logic above stays simple.
    try:
        from harvard_style import apply_harvard_style
        apply_harvard_style(args.out, zebra_rule=True)
        print(f'  applied Harvard style to {args.out}', file=sys.stderr)
    except Exception as e:
        print(f'  warn: harvard_style pass failed: {e}', file=sys.stderr)

    print(f'wrote {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()
