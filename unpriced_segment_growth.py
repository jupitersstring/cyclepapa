"""Unpriced Segment Growth — the EVC/Smadex archetype at its earliest stage.

The pre-rerate setup: a revenue SEGMENT is inflecting (growing materially
faster than the consolidated total, on its way to dominating the mix), but
the SHARE PRICE has not responded — the market is still valuing the legacy
business. Catch it BEFORE the re-rate, when the growth isn't priced in at all.

This screen takes the XBRL segment-inflection candidates (true axis-level
segment data from 10-K filings) and overlays "the market hasn't noticed yet"
filters:

  1. Segment is genuinely inflecting   — excess_growth > 10pp, share < 55%,
                                          dominates within ~10 years
  2. Price is asleep                    — 1-year total return is flat or
                                          negative (the growth isn't being
                                          priced in)
  3. Valuation is still the legacy one  — cheap EV/Sales / EV/EBITDA / P/E
                                          (priced as the old-mix business)
  4. Not in an uptrend                  — trading well below its own recent
                                          high, so momentum hasn't kicked in

Score rewards: strong segment inflection × dormant price × cheap multiple.
The higher the score, the more the segment growth is being ignored by the
tape — exactly the EVC-before-the-Smadex-rerate state.

Output: results_unpriced_segment/screener.csv
"""
from __future__ import annotations
import math
from pathlib import Path
import pandas as pd
import numpy as np

SEG = Path('results_xbrl_segments/screener.csv')
YF_CACHE = Path('.cache/yf')
EDGAR_VAL = Path('results_peg/edgar_valuation.csv')
OUT = Path('results_unpriced_segment'); OUT.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(t))


def _price_perf(ticker: str) -> dict:
    """Return price performance + distance-from-high signals.

    Primary source: the cached daily price series (most precise). Fallback:
    the price-summary fields in the cached info_metrics (regularMarketPrice,
    fiftyTwoWeekChange, twoHundredDayAverage, fiftyTwoWeekHigh) which the
    Yahoo-HTML fetcher populates — this lets SEC-only tickers WITHOUT a price
    series (like EVC) still get a 1-year-performance read, since the Yahoo
    history/chart API is IP-blocked on our egress."""
    p = YF_CACHE / f'{_safe(ticker)}__price.parquet'
    if p.exists():
        try:
            d = pd.read_parquet(p)
            if not d.empty and 'Close' in d.columns:
                s = pd.to_numeric(d['Close'], errors='coerce').dropna()
                if len(s) >= 30:
                    last = float(s.iloc[-1])
                    out = {'price_now': last, '_src': 'series'}
                    if len(s) >= 252:
                        out['perf_1y_pct'] = (last / float(s.iloc[-252]) - 1) * 100
                    if len(s) >= 504:
                        out['perf_2y_pct'] = (last / float(s.iloc[-504]) - 1) * 100
                    win = s.iloc[-504:] if len(s) >= 504 else s
                    hi = float(win.max())
                    if hi > 0:
                        out['pct_below_2y_high'] = (last / hi - 1) * 100
                    if len(s) >= 200:
                        ma200 = float(s.iloc[-200:].mean())
                        if ma200 > 0:
                            out['pct_vs_200dma'] = (last / ma200 - 1) * 100
                    return out
        except Exception:
            pass
    # Fallback: info_metrics price-summary fields (HTML-derived)
    ip = YF_CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if ip.exists():
        try:
            d = pd.read_parquet(ip)
            if not d.empty:
                r0 = d.iloc[0]
                price = r0.get('regularMarketPrice') or r0.get('currentPrice')
                chg = r0.get('fiftyTwoWeekChange')   # decimal (4.18 = +418%)
                hi = r0.get('fiftyTwoWeekHigh')
                ma200 = r0.get('twoHundredDayAverage')
                out = {'_src': 'summary'}
                if price is not None and pd.notna(price):
                    out['price_now'] = float(price)
                if chg is not None and pd.notna(chg):
                    out['perf_1y_pct'] = float(chg) * 100
                if price and hi and pd.notna(price) and pd.notna(hi) and float(hi) > 0:
                    out['pct_below_2y_high'] = (float(price) / float(hi) - 1) * 100
                if price and ma200 and pd.notna(price) and pd.notna(ma200) and float(ma200) > 0:
                    out['pct_vs_200dma'] = (float(price) / float(ma200) - 1) * 100
                if 'perf_1y_pct' in out:
                    return out
        except Exception:
            pass
    return {}


def main():
    if not SEG.exists():
        print('Run xbrl_segment_inflection.py first.')
        return
    seg = pd.read_csv(SEG)
    # EDGAR valuation fallback for cheapness when yfinance is empty
    edgar = {}
    if EDGAR_VAL.exists():
        ev = pd.read_csv(EDGAR_VAL)
        edgar = ev.set_index(ev['ticker'].str.upper()).to_dict('index')

    import re as _re
    MIN_MCAP = 50e6   # drop micro-cap penny-stock noise (ONCO @ $3.7M, etc.)
    print(f'Scanning {len(seg)} segment-inflection candidates for unpriced growth...')
    rows = []
    for _, r in seg.iterrows():
        tk = str(r['ticker'])
        # Skip non-common share classes (preferred/warrant/unit/right)
        if _re.search(r'-P[A-Z]?$|\.PR|-WT$|-WS$|-UN?$|-RT?$', tk):
            continue
        # Segment inflection gates (slightly looser than the strict screen so
        # we catch steady mix-shifts like EVC, not only explosive launches)
        share = r.get('share_now')
        excess = r.get('excess_growth')
        yrs = r.get('years_to_dominate')
        if pd.isna(share) or pd.isna(excess):
            continue
        if share > 0.55:           # still a minority of the mix
            continue
        if excess < 0.10:          # growing >10pp faster than total
            continue
        # Micro-cap floor — a "segment growing" while the stock is down 99.9%
        # at a $3M market cap is a dying penny stock, not an unpriced gem.
        mc = r.get('market_cap')
        if pd.notna(mc) and float(mc) < MIN_MCAP:
            continue

        perf = _price_perf(tk)
        if not perf or 'perf_1y_pct' not in perf:
            continue
        perf_1y = perf['perf_1y_pct']
        # Sanity: a near-total wipeout (-95%+) is a dead company, not unpriced
        if perf_1y <= -95:
            continue
        # "Not priced in" gate: 1-year return is flat-to-down. We allow a
        # little upside (≤25%) since some leakage is normal, but the cleanest
        # setups are genuinely dormant.
        if perf_1y > 25:
            continue

        # Cheapness: prefer the screener's valuation, fall back to EDGAR
        ev_ebitda = r.get('enterpriseToEbitda')
        ev_sales = r.get('enterpriseToRevenue')
        pe = r.get('trailingPE')
        ed = edgar.get(tk.upper(), {})
        if pd.isna(ev_ebitda): ev_ebitda = ed.get('enterpriseToEbitda_edgar')
        if pd.isna(ev_sales):  ev_sales = ed.get('enterpriseToRevenue_edgar')
        if pd.isna(pe):        pe = ed.get('trailingPE_edgar')

        rows.append({
            'ticker': tk,
            'company': r.get('company'),
            'sector': r.get('sector'),
            'industry': r.get('industry'),
            'country': r.get('country'),
            'axis': r.get('axis'),
            'segment': r.get('segment'),
            'share_now': share,
            'seg_growth': r.get('seg_growth'),
            'total_growth': r.get('total_growth'),
            'excess_growth': excess,
            'years_to_dominate': yrs,
            'seg_revenue_now_M': r.get('seg_revenue_now_M'),
            'total_revenue_now_M': r.get('total_revenue_now_M'),
            'perf_1y_pct': perf_1y,
            'perf_2y_pct': perf.get('perf_2y_pct'),
            'pct_below_2y_high': perf.get('pct_below_2y_high'),
            'pct_vs_200dma': perf.get('pct_vs_200dma'),
            'market_cap': r.get('market_cap'),
            'enterpriseToEbitda': ev_ebitda,
            'enterpriseToRevenue': ev_sales,
            'trailingPE': pe,
            'priceToBook': r.get('priceToBook'),
        })

    if not rows:
        print('No unpriced-growth setups found.')
        return
    df = pd.DataFrame(rows)

    # --- Scoring: segment inflection × price dormancy × cheapness ---
    # 1) Inflection strength — excess growth, capped + share-weighted. Reward
    #    the sweet spot (segment big enough to matter, small enough to run).
    excess_capped = df['excess_growth'].clip(upper=2.0)        # cap base-effect
    sweet = 1 - (df['share_now'] - 0.30).abs() / 0.30          # peaks at ~30% share
    sweet = sweet.clip(lower=0.2, upper=1.0)
    inflection = excess_capped * sweet

    # 2) Price dormancy — the more dormant/down the price, the higher. A name
    #    down 30% over 1y while its segment ramps scores highest.
    dormancy = (-df['perf_1y_pct'] / 100).clip(lower=-0.25, upper=1.5) + 0.25
    # Below-high bonus: further below its 2y high = less noticed
    below_high = (-df['pct_below_2y_high'].fillna(0) / 100).clip(lower=0, upper=0.8)

    # 3) Cheapness — low EV/Sales is the cleanest legacy-multiple tell. Rank
    #    within the candidate set (percentile, lower = cheaper = better).
    evs = pd.to_numeric(df['enterpriseToRevenue'], errors='coerce')
    cheap = (1 - evs.rank(pct=True)).fillna(0.5)               # cheap → near 1

    # 4) Viability — separate genuine unpriced-growth from value traps. A
    #    name where the WHOLE business is growing and it's profitable (or
    #    near it) is a real setup (GOGO: total +113%, EV/EBITDA 7, cheap,
    #    beaten down). A cash-burner with a flat total is a trap (OPTT:
    #    total +6%, negative EBITDA). We reward positive total growth and
    #    positive/near-breakeven EV/EBITDA.
    total_g = pd.to_numeric(df['total_growth'], errors='coerce').fillna(0)
    ev_ebd = pd.to_numeric(df['enterpriseToEbitda'], errors='coerce')
    # total-growth contribution: positive total growth is good, capped
    total_g_signal = total_g.clip(lower=-0.2, upper=0.5)
    # profitability: positive & reasonable EV/EBITDA (0..25) scores; negative
    # (loss-making) or absurd (>50) scores 0
    profit_signal = ((ev_ebd > 0) & (ev_ebd <= 25)).astype(float)
    viability = total_g_signal + profit_signal * 0.5

    # Viability tier label for quick triage
    def _tier(row):
        eb = row.get('enterpriseToEbitda')
        tg = row.get('total_growth')
        eb = float(eb) if pd.notna(eb) else None
        tg = float(tg) if pd.notna(tg) else 0
        if eb is not None and 0 < eb <= 25 and tg > 0.05:
            return 'profitable + growing'
        if eb is not None and 0 < eb <= 25:
            return 'profitable'
        if tg > 0.10:
            return 'pre-profit, growing'
        return 'cash-burn / flat'
    df['viability_tier'] = df.apply(_tier, axis=1)

    df['inflection_strength'] = inflection
    df['price_dormancy'] = dormancy + below_high
    df['cheapness'] = cheap
    df['viability'] = viability
    df['unpriced_score'] = (
        inflection * 4.0
        + (dormancy + below_high) * 2.0
        + cheap * 1.5
        + viability * 2.0          # viability now a first-class factor
    )
    df = df.sort_values('unpriced_score', ascending=False)
    df.to_csv(OUT / 'screener.csv', index=False)
    print(f'\nWrote {len(df):,} unpriced-segment-growth setups to {OUT/"screener.csv"}')

    show = df.head(20)[['ticker','company','segment','share_now','seg_growth',
                        'perf_1y_pct','enterpriseToRevenue','unpriced_score']].copy()
    for c in ('share_now','seg_growth'):
        show[c] = (show[c]*100).round(0).astype('Int64').astype(str)+'%'
    for c in ('perf_1y_pct','enterpriseToRevenue','unpriced_score'):
        show[c] = pd.to_numeric(show[c], errors='coerce').round(2)
    pd.set_option('display.width', 220); pd.set_option('display.max_columns', 20)
    print('\nTop 20 — segment ramping, price asleep:')
    print(show.to_string(index=False))


if __name__ == '__main__':
    main()
