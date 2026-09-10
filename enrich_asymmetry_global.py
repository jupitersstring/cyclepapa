"""Post-pass enrichment of asymmetry_global.csv.

After asymmetry_rank.py writes the deduped universe, this script merges
in archetype tags + verdicts + intrinsic-discount inputs and computes
four NEW columns that close the audit #3 gaps:

  entry_today_asymmetry        asymmetry_score x qual_mult x intrinsic_boost
                               x post_rally_factor — verdict-aware ranking so
                               downstream consumers don't surface REDs.

  archetype_count_pct          archetype_count divided by the count of
                               archetypes ELIGIBLE for the row (26 for US-
                               EDGAR-covered names, 9 for non-EDGAR names
                               that can't hit the 17 EDGAR-required tags).
                               Removes the structural US bias in
                               raw archetype_count.

  archetype_asymmetry_score    sqrt(archetype_count_pct x downside_floor) —
                               parallel ranking on archetype density,
                               wiring together the archetype framework and
                               the asymmetry geometric-mean structure.

  mcap_proxy                   market_cap when available, else book equity
                               (then revenue, then assets). Used to scale
                               size-dependent legs for names like MELI
                               whose mcap is missing.

Run after every rebuild of asymmetry_global.csv.
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd


EDGAR_REQUIRED_ARCHETYPES = {
    # The 25 archetypes that can only fire when EDGAR multi-year + cap-
    # allocation + segment data is present. Non-EDGAR rows can't
    # structurally match these.
    "arch_durable_reinvestment", "arch_cash_reinvest", "arch_roic_inflect",
    "arch_cheap_per_roiic", "arch_tangible_value",
    "arch_lindy_margin", "arch_lindy_fcf", "arch_no_dilution", "arch_lindy_growth",
    "arch_quiet_compounder", "arch_buyback_compounder", "arch_owner_operator",
    "arch_qarp", "arch_reinvest_inflect", "arch_double_inflect",
    "arch_cash_quality", "arch_capital_light_pivot",
    "arch_capital_returner", "arch_low_sbc_quality",
    "arch_tax_efficient", "arch_strong_coverage",
    # NEW: segment-level archetypes (edgartools dimensional XBRL harvest)
    "arch_diversified_segments", "arch_concentrated_segments",
    "arch_geographic_global", "arch_fastest_segment",
}


def load_verdicts() -> pd.DataFrame:
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
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default:
            d['verdict'] = default
        keep = [c for c in ['symbol', 'verdict'] if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=['symbol', 'verdict'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')


def load_intrinsic_inputs() -> pd.DataFrame:
    """Pull net_cash/mcap, NCAV/mcap, cash/EV, not_priced_in from per-country
    yartseva CSVs — same source as the Harvard workbook's intrinsic_discount
    computation, kept consistent here."""
    keep = ['symbol', 'net_cash_pct_mcap', 'ncav_pct_mcap', 'cash_pct_ev',
            'not_priced_in_score']
    frames = []
    for f in sorted(glob.glob('*_yartseva.csv')):
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if not frames:
        return pd.DataFrame(columns=keep)
    df = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asym', default='asymmetry_global.csv')
    ap.add_argument('--arch', default='archetype_tags.csv')
    ap.add_argument('--total-archetypes', type=int, default=34)
    args = ap.parse_args()

    print('loading asymmetry_global, archetype_tags, verdicts...', file=sys.stderr)
    df = pd.read_csv(args.asym)
    # Drop stale suffixed columns from prior enrich runs, plus any stale
    # archetype outputs the master already carries — otherwise the fresh
    # archetype_tags merge below collides and suffixes to *_arch, leaving the
    # STALE archetype_count/bab_score in place (would silently freeze counts
    # whenever new archetypes are added).
    df = df.drop(columns=[c for c in df.columns if c.endswith('_arch')])
    arch_df = pd.read_csv(args.arch).drop_duplicates('symbol')
    verdicts = load_verdicts()
    intrinsic_in = load_intrinsic_inputs()

    arch_cols = [c for c in arch_df.columns if c.startswith('arch_')]
    edgar_arch_cols = [c for c in arch_cols if c in EDGAR_REQUIRED_ARCHETYPES]
    non_edgar_arch_cols = [c for c in arch_cols if c not in EDGAR_REQUIRED_ARCHETYPES]
    print(f'  {len(arch_cols)} archetype columns ({len(edgar_arch_cols)} EDGAR-only, '
          f'{len(non_edgar_arch_cols)} universal)', file=sys.stderr)

    # Propagate the multi-measure CONFIRMATION scores into asymmetry_global so
    # every workbook (not just the three archetype books that merge
    # archetype_tags directly) can apply the same "upweight where independent
    # measures agree" treatment. These are non-boolean, so they survive the
    # arch_-boolean drop at the end.
    confirm_scores = ['confirm_overall', 'alignment_score', 'buyback_score',
                      'inflection_confirm_score', 'oper_leverage_score',
                      'rev_growth_score', 'cheapness_score', 'quality_score',
                      'high_52w_abs', 'high_52w_rel', 'high_52w_both',
                      'analyst_awakening_score', 'lynch_rank',
                      # Archetype-specific ranking keys, propagated so every
                      # book (not just the ones merging archetype_tags.csv
                      # directly) can sort archetype sheets by their own score
                      'tenbagger_score', 'evsales_derate_score',
                      'lynch_reward_score', 'lynch_leg_max',
                      'evsales_derate_gap', 'tenbagger_implied_return',
                      # Not yet emitted by archetype_tags.py — harmless here
                      # (the extra_arch list below filters on arch_df.columns)
                      'seg_inflect_score', 'capital_return_score',
                      'lynch_value_score']
    extra_arch = [c for c in (['archetype_count', 'bab_score', 'is_price_ghost']
                              + confirm_scores)
                  if c in arch_df.columns]
    # Drop EVERY column the arch merge re-supplies (not just count/bab_score):
    # any of them already present from a prior enrich run would otherwise
    # collide, get suffixed to *_arch, and silently freeze at its stale value.
    df = df.drop(columns=[c for c in extra_arch if c in df.columns])
    df = df.merge(arch_df[['symbol'] + arch_cols + extra_arch],
                  on='symbol', how='left', suffixes=('', '_arch'))
    # Drop any pre-existing verdict so the fresh merge wins
    if 'verdict' in df.columns:
        df = df.drop(columns=['verdict'])
    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    mc = ['symbol'] + [c for c in intrinsic_in.columns
                       if c != 'symbol' and c not in df.columns]
    df = df.merge(intrinsic_in[mc], on='symbol', how='left')

    # ----- FRESH MOMENTUM COALESCE (before ETA uses it) -----
    # Stored momentum_12m goes stale while the lynch drive owns Yahoo
    # (corr with the live tape just 0.13; UTZ stored -44% vs live +38%).
    # momentum_12m feeds BOTH the upside leg (u_mom, via the next
    # rebuild_scores cycle) AND post_rally_factor here — the anti-chasing
    # multiplier on ETA, the #1 book ranking key. A name that has already
    # run but shows stale-negative momentum escapes the rally penalty and
    # ranks as a fresh entry. Override from the live lynch roc_12m where the
    # tape is fresh. NB: lynch roc_12m is already a fraction (0.38 = +38%),
    # same scale as momentum_12m.
    try:
        _lm = pd.read_csv('lynch_reward_signals.csv',
                          usecols=['symbol', 'roc_12m', 'stale_tape',
                                   'last_bar_age_days']).drop_duplicates('symbol')
        _lm = df[['symbol']].merge(_lm, on='symbol', how='left')
        _roc = pd.to_numeric(_lm['roc_12m'], errors='coerce').values
        _st = pd.to_numeric(_lm['stale_tape'], errors='coerce').fillna(0).values
        _ag = pd.to_numeric(_lm['last_bar_age_days'], errors='coerce').values
        _ok = (~np.isnan(_roc)) & (_st != 1) & (np.isnan(_ag) | (_ag <= 21))
        _cur = pd.to_numeric(df.get('momentum_12m'), errors='coerce').values
        df['momentum_12m'] = np.where(_ok, _roc, _cur)
        print(f'  refreshed momentum_12m from live lynch tape on '
              f'{int(_ok.sum())} rows', file=sys.stderr)
    except Exception as _e:
        print(f'  momentum refresh skipped ({_e})', file=sys.stderr)

    # ----- mcap_proxy (book-equity fallback for ranking) -----
    # Used to scale size-dependent legs when yfinance market_cap is NaN.
    mcap = df['market_cap'].copy() if 'market_cap' in df.columns else pd.Series(np.nan, index=df.index)
    if 'equity' in df.columns:
        mcap = mcap.fillna(df['equity'].clip(lower=0))
    if 'revenue_ttm' in df.columns:
        mcap = mcap.fillna(df['revenue_ttm'].clip(lower=0))
    if 'assets' in df.columns:
        mcap = mcap.fillna(df['assets'].clip(lower=0) * 0.5)
    df['mcap_proxy'] = mcap

    # ----- intrinsic_discount (same formula as Harvard workbook) -----
    def col(c, d=0.0):
        return df[c].fillna(d) if c in df.columns else pd.Series(d, index=df.index)

    def c01(s):
        return s.clip(0, 1).fillna(0)

    nc = c01(col('net_cash_pct_mcap'))
    ncav = c01(col('ncav_pct_mcap'))
    sub_book = c01(1.0 - col('pb', 2.0).clip(lower=0.01))
    cash_ev = c01((col('cash_pct_ev') - 1.0).clip(0, 2) / 2.0)
    npi = c01(col('not_priced_in_score'))
    df['intrinsic_discount'] = (
        0.30 * nc + 0.20 * ncav + 0.20 * sub_book + 0.15 * cash_ev + 0.15 * npi
    ).round(4)
    # intrinsic_discount is confined to [0,1] -> boost range is
    # [0.75, 1.5] by construction (a 0.5 floor was dead code).
    # Floor lifted 0.75 -> 0.90: intrinsic_discount is a deep-value signal
    # (net cash / ncav / sub-book) large caps structurally lack, so the old
    # 0.75 floor docked every quality large cap 25% on ETA purely for not
    # being asset-cheap. 0.90 keeps the deep-value UPSIDE (up to 1.5x) while
    # cutting the size penalty; pairs with the earnings/solvency downside
    # legs so large caps aren't penalised for size.
    intrinsic_boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.90, 1.5)

    # ----- qual_mult + post_rally_factor -----
    soft_mult = {'GREEN': 1.10, 'YELLOW': 0.85, 'RED': 0.40}
    df['qual_mult'] = df['verdict'].map(soft_mult).fillna(1.0)

    mom = col('momentum_12m').clip(-0.5, None)
    pr = pd.Series(1.0, index=df.index)
    mid = (mom > 0.30) & (mom <= 1.0)
    hi = (mom > 1.0) & (mom <= 3.0)
    ex = mom > 3.0
    pr.loc[mid] = 1.0 - (mom[mid] - 0.30) / 0.70 * 0.25
    pr.loc[hi] = 0.75 - (mom[hi] - 1.0) / 2.0 * 0.30
    pr.loc[ex] = 0.40
    df['post_rally_factor'] = pr.round(3)

    # ----- melt_demotion: DEMOTE genuine melters in ranking, do NOT bar them ---
    # Per user directive ("just demote if melt, not bar; cash-on-cash returns are
    # as important as ROCE; be more benign if ROCE is improving"): a melting name
    # stays in the pool and in every archetype it qualifies for, but sinks in the
    # ranking rather than being excluded. "Melting" credits cash-on-cash returns
    # equally with ROCE (any robust cash lens exempts) and is lenient to improving
    # returns. A name is a genuine ice cube ONLY when it loses money on the
    # operating line AND/OR is deeply ROCE-negative, generates cash on NO lens,
    # AND is not improving. Cash-generative or inflecting names keep factor 1.0.
    _opm_d = col('op_margin'); _roce_d = col('roce')
    # only SIGN-MEANINGFUL absolute cash yields (NOT cash_conversion=CFO/EBITDA,
    # which reads positive when both are negative and would exempt a dead name).
    _cash_ok_d = ((col('fcf_yield') > 0) | (col('owner_earnings_yield') > 0)
                  | (col('robust_cash_yield') > 0) | (col('cfo_yield') > 0)
                  | (col('fcf_margin') > 0))
    _improving_d = ((col('roce_delta_yoy') > 0) | (col('roce_inflection') > 0)
                    | (col('roce_first_positive') > 0) | (col('fcf_inflection') > 0)
                    | (col('op_margin_delta_yoy') > 0) | (col('ebitda_inflection') > 0))
    _exempt_d = _cash_ok_d | _improving_d
    _op_bad_d = _opm_d < 0
    _roce_bad_d = _roce_d < -0.05
    _melt_hard_d = _op_bad_d & _roce_bad_d & ~_exempt_d          # loss AND bad ROCE, no cash, not improving
    _melt_soft_d = (_op_bad_d | _roce_bad_d) & ~_exempt_d & ~_melt_hard_d
    melt_demotion = pd.Series(1.0, index=df.index)
    melt_demotion.loc[_melt_soft_d] = 0.65
    melt_demotion.loc[_melt_hard_d] = 0.40
    df['melt_demotion'] = melt_demotion.round(3)
    print(f'  melt_demotion: {int(_melt_hard_d.sum())} hard (x0.40) + '
          f'{int((_melt_soft_d).sum())} soft (x0.65) demoted; '
          f'{int((melt_demotion >= 1.0).sum())} unaffected', file=sys.stderr)

    # ----- PRICE-GHOST DEDUP: drop wrong-price duplicate lines from ranking -----
    # archetype_tags flags is_price_ghost on a duplicate line of the same
    # security carrying a corrupt-low price (e.g. UMBFO, a ghost of UMBF, at
    # P/B 0.26 vs the real 1.48). Null its ranking scores and its price-derived
    # ratios so it can neither rank in the books nor display a misleading
    # valuation, and the real listing wins the name-dedup.
    if 'is_price_ghost' in df.columns:
        _ghost = pd.to_numeric(df['is_price_ghost'], errors='coerce').fillna(0) == 1
        if _ghost.any():
            for _c in ('asymmetry_score', 'archetype_asymmetry_score',
                       'entry_today_upside', 'yartseva_score', 'berezin_score',
                       'pb', 'p_tb', 'p_e', 'p_s', 'ev_sales', 'ev_ebitda',
                       'ev_ebit', 'fcf_yield', 'earnings_yield', 'dividend_yield'):
                if _c in df.columns:
                    df.loc[_ghost, _c] = np.nan
            print(f'  final gate: nulled {int(_ghost.sum())} price-ghost '
                  f'duplicate lines (ranking + ratios)', file=sys.stderr)

    # ----- entry_today_asymmetry -----
    df['entry_today_asymmetry'] = (
        df['asymmetry_score'].fillna(0)
        * intrinsic_boost
        * df['qual_mult']
        * df['post_rally_factor']
        * df['melt_demotion']          # (user) demote melters, don't bar them
    ).round(6)

    # ----- archetype_count_pct (region-fair denominator) -----
    # A row is EDGAR-eligible if it has at least one EDGAR-only archetype
    # matching (= EDGAR XBRL was present for this name).
    if edgar_arch_cols:
        has_edgar_data = (df[edgar_arch_cols].fillna(0).sum(axis=1) > 0)
        # Or any row carrying multi-year fields:
        for marker in ('roic_lindy', 'm5_engine_score', 'tangible_equity_pct'):
            if marker in df.columns:
                has_edgar_data = has_edgar_data | df[marker].notna()
        # EDGAR-covered rows are eligible for the FULL live taxonomy —
        # derive the denominator from the file, never a CLI constant (the
        # old --total-archetypes default froze at 34 while the taxonomy
        # grew to 69, silently re-inflating the US-coverage bias this
        # column exists to remove).
        archetypes_eligible = np.where(has_edgar_data, len(arch_cols),
                                       len(non_edgar_arch_cols))
    else:
        archetypes_eligible = len(arch_cols)
    df['archetypes_eligible'] = archetypes_eligible
    df['archetype_count'] = df['archetype_count'].fillna(0)
    df['archetype_count_pct'] = (df['archetype_count'] / archetypes_eligible).round(4)

    # ----- archetype_asymmetry_score -----
    # Same geometric-mean structure as the existing asymmetry_score, but
    # using archetype density as the upside leg. Wires the archetype
    # framework into a parallel ranking.
    floor = df['downside_floor_score'].fillna(0).clip(0, 1)
    df['archetype_asymmetry_score'] = np.sqrt(
        df['archetype_count_pct'].clip(0, 1) * floor
    ).round(6)

    # Optional: also incorporate qual_mult into the archetype ranking
    df['entry_today_archetype_asymmetry'] = (
        df['archetype_asymmetry_score']
        * df['qual_mult']
        * df['post_rally_factor']
        * df['melt_demotion']          # (user) demote melters, don't bar them
    ).round(6)

    # ----- convergence_score (Compendium master ranking) -----
    # The reference's OWN top-level rank: (archetype COUNT) x (asymmetry) x
    # (liquidity tier), with the "3+ simultaneous archetypes = highest
    # conviction" line made explicit. Distinct from archetype_asymmetry_score
    # (which is a density x downside geometric mean) because it (a) rewards raw
    # multi-thesis BREADTH and (b) folds in a LIQUIDITY tier the reference
    # insists on — so a name carrying many independent theses at a tradeable
    # size surfaces, instead of being scattered across single-archetype sorts.
    _adv = pd.to_numeric(df.get('avg_dollar_volume'), errors='coerce')
    _liq_tier = np.where(_adv >= 5e6, 1.0,
                np.where(_adv >= 5e5, 0.7,
                np.where(_adv >= 5e4, 0.4, 0.2)))
    _cnt = pd.to_numeric(df['archetype_count'], errors='coerce').fillna(0).clip(0, 12)
    _breadth = (_cnt / 6.0).clip(0, 1)                 # 6 archetypes -> full breadth
    _conv_bonus = np.where(_cnt >= 3, 1.0, 0.6)        # 3+ = the reference's conviction line
    df['convergence_score'] = (
        _breadth * _conv_bonus
        * pd.to_numeric(df['asymmetry_score'], errors='coerce').fillna(0).clip(0, 1)
        * _liq_tier
    ).round(4)

    # Reorder columns so the new ones land in a logical place
    new_cols = ['entry_today_asymmetry', 'archetype_count', 'archetype_count_pct',
                'archetypes_eligible', 'archetype_asymmetry_score',
                'entry_today_archetype_asymmetry', 'convergence_score',
                'mcap_proxy', 'intrinsic_discount', 'qual_mult',
                'post_rally_factor', 'melt_demotion', 'verdict']
    # Drop the per-archetype boolean columns we merged in — they're
    # available via archetype_tags.csv if anyone wants them. Keeps
    # asymmetry_global slim.
    cols_to_drop = [c for c in arch_cols if c in df.columns]
    df = df.drop(columns=cols_to_drop)

    front_existing = [c for c in df.columns if c not in new_cols]
    ordered = front_existing + [c for c in new_cols if c in df.columns]
    df = df[ordered]

    # ---- FINAL INTEGRITY GATE (last writer before the master lands) ----
    import numpy as _np
    # 1. Pence-minted .L market caps: mcap == price*shares with an ABSURD
    #    mcap/revenue (>100x) — Celtic at £21B, Investec at £644B. Plenty of
    #    .L rows legitimately satisfy mcap==p*s (internationals quoting in
    #    EUR/USD/GBP: Compass, IHG, Glanbia) so the revenue test is the
    #    discriminator, not the ratio alone. Null rather than re-import the
    #    minted value from the source files on every enrich.
    _p = pd.to_numeric(df.get('price'), errors='coerce')
    _sh = pd.to_numeric(df.get('shares_outstanding'), errors='coerce')
    _mc = pd.to_numeric(df.get('market_cap'), errors='coerce')
    _rv = pd.to_numeric(df.get('revenue_ttm'), errors='coerce')
    _ratio = _mc / (_p * _sh)
    _minted = (df['symbol'].astype(str).str.endswith('.L')
               & _ratio.between(0.5, 2.0)
               & ((_mc / _rv > 100) | (_rv.isna() & (_p >= 200))))
    if _minted.any():
        print(f'  final gate: nulled {int(_minted.sum())} pence-minted .L '
              f'mcaps: {df.loc[_minted, "symbol"].tolist()[:6]}', file=sys.stderr)
        df.loc[_minted, ['market_cap', 'market_cap_usd']] = _np.nan

    # 2. 52w freshness: quote-time pct_off_52w_high goes stale while the
    #    lynch drive owns Yahoo (UTZ at its 52w high displayed as -48%).
    #    Where the per-name lynch tape is live, its pct_52w_high overrides.
    try:
        _ls = pd.read_csv('lynch_reward_signals.csv',
                          usecols=['symbol', 'pct_52w_high', 'stale_tape',
                                   'last_bar_age_days']).drop_duplicates('symbol')
        _ls = df[['symbol']].merge(_ls, on='symbol', how='left')
        _lp = pd.to_numeric(_ls['pct_52w_high'], errors='coerce').values
        _stale = pd.to_numeric(_ls['stale_tape'], errors='coerce').fillna(0).values
        _age = pd.to_numeric(_ls['last_bar_age_days'], errors='coerce').values
        _fresh = (~_np.isnan(_lp)) & (_stale != 1) & (_np.isnan(_age) | (_age <= 21))
        _cur = pd.to_numeric(df['pct_off_52w_high'], errors='coerce').values
        df['pct_off_52w_high'] = _np.where(_fresh, _lp - 1.0, _cur)
        print(f'  final gate: refreshed pct_off_52w_high from live lynch tape '
              f'on {int(_fresh.sum())} rows', file=sys.stderr)
    except Exception as _e:
        print(f'  final gate: 52w refresh skipped ({_e})', file=sys.stderr)

    # ----- exchange-suffix -> src correction -----
    # src comes from WHICH SCAN FILE a name appeared in, so a line scanned in
    # the wrong batch lands on the wrong COUNTRY TAB (042420.KQ, a KOSDAQ line,
    # was tagged src=JP and topped Japanese tabs). Where the suffix reliably
    # marks the HOME/PRIMARY market, override src from it. DELIBERATELY EXCLUDED:
    # Frankfurt (.F) and the German regional exchanges (.HM/.MU/.BE/.SG/.DU) and
    # Xetra (.DE) — those venues host thousands of foreign UNSPONSORED
    # SECONDARY listings, so mapping them to DE would scatter foreign ghosts
    # onto the German tab (where within-country dedup can't collapse them). This
    # map is only home-primary venues with low foreign-secondary contamination.
    _SUFFIX_SRC = {
        '.KQ': 'KR', '.KS': 'KR', '.T': 'JP', '.BK': 'TH', '.SI': 'SG',
        '.HK': 'HK', '.SS': 'CN', '.SZ': 'CN', '.JK': 'ID', '.NS': 'IN',
        '.BO': 'IN', '.AX': 'AU', '.NZ': 'NZ', '.MI': 'IT', '.TO': 'CA',
        '.V': 'CA', '.SA': 'BR', '.MC': 'ES', '.ST': 'SE', '.OL': 'NO',
        '.CO': 'DK', '.HE': 'FI', '.WA': 'PL', '.TA': 'IL', '.KL': 'MY',
        '.L': 'UK', '.PA': 'FR', '.AS': 'NL', '.SW': 'CH', '.BR': 'BE',
        '.AT': 'GR', '.VI': 'AT', '.IS': 'TR', '.BD': 'HU', '.PR': 'CZ',
        '.IC': 'IS', '.LS': 'PT', '.MX': 'MX',
        # NOTE: .F (Frankfurt) and .DE (Xetra) intentionally OMITTED — they host
        # thousands of foreign unsponsored secondaries; mapping them to DE would
        # flood the German tab with foreign ghosts.
    }
    if 'src' in df.columns:
        _sym_s = df['symbol'].astype(str)
        _sfx = _sym_s.str.extract(r'(\.[A-Z]{1,2})$', expand=False)
        _should = _sfx.map(_SUFFIX_SRC)
        _fixmask = _should.notna() & (df['src'].astype(str) != _should)
        if _fixmask.any():
            df.loc[_fixmask, 'src'] = _should[_fixmask]
            print(f'  final gate: corrected src by exchange suffix on '
                  f'{int(_fixmask.sum())} lines (e.g. .KQ scanned in a JP batch)',
                  file=sys.stderr)

    # Final data-integrity sanitizers (apply_ticker_yf re-fetches raw Yahoo
    # values that bypass the derive-layer guards — these caught 291 impossible
    # FCF yields, 35 zero/neg market caps, 13 absurd div yields on 2026-09-08).
    _fy = pd.to_numeric(df.get('fcf_yield'), errors='coerce')
    df['fcf_yield'] = _fy.where(_fy <= 1.0)                      # >100% = ADR fx mismatch
    _dy = pd.to_numeric(df.get('dividend_yield'), errors='coerce')
    df['dividend_yield'] = _dy.where(_dy <= 0.40)                # >40% = stale/preferred
    # P/B corruption (ADR/units mismatch put Berkshire at pb=0.001, Asian
    # banks at <0.005) — recompute from mcap_usd/equity where that's sane,
    # else null; a <0.05x-book going concern is a data artifact, not value.
    _pb = pd.to_numeric(df.get('pb'), errors='coerce')
    _eq = pd.to_numeric(df.get('equity'), errors='coerce')
    _mc0 = pd.to_numeric(df.get('market_cap_usd'), errors='coerce')
    _impl = (_mc0 / _eq.where(_eq > 0))
    _impl = _impl.where((_impl >= 0.1) & (_impl <= 20))
    _pb_corrupt = (_pb > 0) & (_pb < 0.05)
    if _pb_corrupt.any():
        df['pb'] = _pb.where(~_pb_corrupt, _impl)
        print(f'  final gate: repaired {int(_pb_corrupt.sum())} corrupt pb '
              f'(<0.05x book, ADR/units)', file=sys.stderr)
    if 'p_tb' in df.columns:
        _ptb = pd.to_numeric(df['p_tb'], errors='coerce')
        df['p_tb'] = _ptb.where(~((_ptb > 0) & (_ptb < 0.05)))
    # Sibling ratio artifacts (same ADR/units/pass-through class as pb):
    # P/E<0.5 is impossible for sustainable earnings; a sub-0.02 sales
    # multiple isn't genuine cheapness (units error or commodity pass-through).
    _pe = pd.to_numeric(df.get('p_e'), errors='coerce')
    df['p_e'] = _pe.where(~((_pe > 0) & (_pe < 0.5)))
    _ps = pd.to_numeric(df.get('p_s'), errors='coerce')
    df['p_s'] = _ps.where(~((_ps > 0) & (_ps < 0.02)))
    _evs = pd.to_numeric(df.get('ev_sales'), errors='coerce')
    df['ev_sales'] = _evs.where(~((_evs > 0) & (_evs < 0.02)))
    # Impossible margins: gross margin CANNOT exceed revenue (>1.0); an
    # ebitda/net margin >1.2 is non-operating income (one-off gains, holdco
    # investment income) masquerading as an operating margin.
    _gm = pd.to_numeric(df.get('gross_margin'), errors='coerce')
    df['gross_margin'] = _gm.where(~(_gm > 1.0))
    # ROCE/ROIC > 150% is a one-off-earnings / tiny-capital-base artifact
    # (KROS a licensing windfall showed ROCE 207%) — not a sustainable return.
    for _rc in ('roce', 'roic', 'roic_after_sbc', 'roe'):
        if _rc in df.columns:
            _rv = pd.to_numeric(df[_rc], errors='coerce')
            df[_rc] = _rv.where(~(_rv > 1.5))
    for _mc_ in ('ebitda_margin', 'net_margin', 'pretax_margin'):
        if _mc_ in df.columns:
            _mv = pd.to_numeric(df[_mc_], errors='coerce')
            df[_mc_] = _mv.where(~(_mv > 1.2))

    _mc = pd.to_numeric(df.get('market_cap_usd'), errors='coerce')
    _pr = pd.to_numeric(df.get('price'), errors='coerce')
    _bad_scale = (_mc <= 0) | (_pr <= 0)
    for _c in ('market_cap_usd', 'market_cap', 'price'):
        if _c in df.columns:
            df.loc[_bad_scale.fillna(False), _c] = _np.nan
    if _bad_scale.sum():
        print(f'  final gate: nulled scale on {int(_bad_scale.sum())} '
              f'zero/neg mcap-or-price rows', file=sys.stderr)

    # 52w flag consistency: after refreshing pct_off_52w_high above, a stale
    # high_52w_abs flag can disagree with the fresh percentage — turn the flag
    # off where it now contradicts (>10% below high).
    if 'high_52w_abs' in df.columns and 'pct_off_52w_high' in df.columns:
        _hi = pd.to_numeric(df['high_52w_abs'], errors='coerce')
        _offc = pd.to_numeric(df['pct_off_52w_high'], errors='coerce')
        _clash = (_hi == 1) & (_offc < -0.10)
        for _fc in ('high_52w_abs', 'high_52w_both'):
            if _fc in df.columns:
                df.loc[_clash.fillna(False), _fc] = 0

    if 'name' in df.columns:
        df['name'] = df['name'].astype(str).str.replace('\xa0', ' ', regex=False)

    from master_versions import versioned_replace
    df.to_csv(args.asym + '.tmp', index=False)
    versioned_replace(args.asym + '.tmp', args.asym)   # atomic + pre-image snapshot

    print(f'  wrote enriched {args.asym}: {len(df):,} rows, '
          f'{len(df.columns)} columns', file=sys.stderr)

    # Diagnostics
    print('\nVerdict distribution:')
    print(df['verdict'].value_counts(dropna=False).to_string())
    print(f'\nentry_today_asymmetry distribution:')
    eta = df['entry_today_asymmetry']
    print(f'  mean={eta.mean():.3f}, median={eta.median():.3f}, '
          f'p90={eta.quantile(0.90):.3f}, max={eta.max():.3f}')
    print(f'\narchetype_count_pct distribution (by EDGAR eligibility):')
    edg = df[df['archetypes_eligible'] == args.total_archetypes]
    non = df[df['archetypes_eligible'] != args.total_archetypes]
    if len(edg):
        print(f'  EDGAR-eligible ({len(edg):,}): mean count {edg.archetype_count.mean():.2f}, '
              f'mean pct {edg.archetype_count_pct.mean():.3f}')
    if len(non):
        print(f'  Non-EDGAR    ({len(non):,}): mean count {non.archetype_count.mean():.2f}, '
              f'mean pct {non.archetype_count_pct.mean():.3f}')

    # Top by new score
    print('\nTop 15 by entry_today_archetype_asymmetry:')
    cols_show = ['symbol', 'name', 'src', 'verdict', 'archetype_count',
                 'archetype_count_pct', 'asymmetry_score', 'archetype_asymmetry_score',
                 'entry_today_asymmetry', 'entry_today_archetype_asymmetry']
    cols_show = [c for c in cols_show if c in df.columns]
    print(df.nlargest(15, 'entry_today_archetype_asymmetry')[cols_show].round(3).to_string(index=False))


if __name__ == '__main__':
    main()
