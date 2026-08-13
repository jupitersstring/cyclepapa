"""
Auction/breakout overlay for the 200-week-low screen.
=====================================================
Translates the Dalton (Mind Over Markets / Markets in Profile) auction
framework into features computable from daily OHLCV, on a three-level
hierarchy: monthly context -> WEEKLY operating auction (most important)
-> daily trigger. Alignment across the three is scored 0-100 with the
weekly leg carrying half the weight.

The economic objects preserved (not just stretched candles):
  value        volume-weighted price distributions (POC / 70% value area)
               built from daily bars, composited per timeframe
  migration    does VALUE follow price, or only price move?
  balance      bracket of the prior weeks; breakout means leaving it
  acceptance   repeated closes + value migration beyond the old balance
  rejection    excursion beyond, then back inside (fade material)
  failed low   probe under a multi-month low that is bought back and
               never revisited -- the classic asymmetric long at a
               200-week low, with invalidation just under the probe
  one-timeframing  consecutive higher weekly (daily) lows
  efficiency   |value migration| per unit of realised range: falling
               efficiency = ageing auction
  compression  narrow recent range inside a wide old range = coiled
  friction     Corwin-Schultz spread estimate + Amihud illiquidity from
               daily bars, so a 4:1 chart is not called asymmetric
               before costs

Usage:
    python auction_overlay.py --shortlist ../us_global_shortlist.csv \
        --out ../shortlist_auction.csv [--resume]
    python auction_overlay.py --tickers CMCSA,FISV,ACN --out /tmp/x.csv
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

from yf_screen import make_session
import harmonics

# ----------------------------------------------------------------------
# 1. Pure computational core (unit-tested offline)
# ----------------------------------------------------------------------

def volume_profile(high, low, volume, bins: int = 60):
    """Distribute each bar's volume uniformly across its H-L range.
    Returns (bin_centers, bin_volumes)."""
    h = np.asarray(high, float); l = np.asarray(low, float)
    v = np.asarray(volume, float)
    ok = np.isfinite(h) & np.isfinite(l) & np.isfinite(v) & (h >= l)
    h, l, v = h[ok], l[ok], v[ok]
    if len(h) == 0:
        return np.array([]), np.array([])
    lo, hi = float(l.min()), float(h.max())
    if hi <= lo:
        hi = lo * 1.0001 + 1e-9
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    out = np.zeros(bins)
    for hh, ll, vv in zip(h, l, v):
        if vv <= 0:
            continue
        a = np.searchsorted(edges, ll, 'right') - 1
        b = np.searchsorted(edges, hh, 'left')
        a, b = max(a, 0), min(b, bins - 1)
        n = b - a + 1
        out[a:b + 1] += vv / n
    return centers, out


def poc_value_area(centers, volumes, va_pct: float = 0.70):
    """Standard Market Profile value area: start at the POC bin, greedily
    add the heavier adjacent bin until va_pct of volume is contained.
    Returns (poc, val, vah)."""
    if len(volumes) == 0 or volumes.sum() <= 0:
        return None, None, None
    i = int(np.argmax(volumes))
    total = volumes.sum()
    acc = volumes[i]
    lo = hi = i
    while acc < va_pct * total:
        below = volumes[lo - 1] if lo > 0 else -1.0
        above = volumes[hi + 1] if hi < len(volumes) - 1 else -1.0
        if below < 0 and above < 0:
            break
        if above >= below:
            hi += 1; acc += volumes[hi]
        else:
            lo -= 1; acc += volumes[lo]
    return float(centers[i]), float(centers[lo]), float(centers[hi])


def composite_value(df: pd.DataFrame, va_pct: float = 0.70):
    """(poc, val, vah) for an OHLCV frame window."""
    c, v = volume_profile(df['High'], df['Low'], df['Volume'])
    return poc_value_area(c, v, va_pct)


def resample(daily: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Daily OHLCV -> weekly ('W-FRI') or monthly ('ME') bars."""
    o = daily.resample(rule).agg({'Open': 'first', 'High': 'max',
                                  'Low': 'min', 'Close': 'last',
                                  'Volume': 'sum'})
    return o.dropna(subset=['Close'])


def corwin_schultz(high: pd.Series, low: pd.Series) -> float:
    """Mean Corwin-Schultz (2012) spread estimate from daily H/L.
    Negative two-day estimates are floored at zero (standard practice)."""
    h, l = high.astype(float), low.astype(float)
    with np.errstate(divide='ignore', invalid='ignore'):
        beta = (np.log(h / l) ** 2) + (np.log(h.shift(-1) / l.shift(-1)) ** 2)
        h2 = pd.concat([h, h.shift(-1)], axis=1).max(axis=1)
        l2 = pd.concat([l, l.shift(-1)], axis=1).min(axis=1)
        gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    s = s.clip(lower=0).dropna()
    return float(s.mean()) if len(s) else np.nan


def amihud(close: pd.Series, volume: pd.Series) -> float:
    """Mean |return| per dollar volume (x1e9 for readability)."""
    r = close.pct_change().abs()
    dv = close * volume
    x = (r / dv.replace(0, np.nan)).dropna()
    return float(x.mean() * 1e9) if len(x) else np.nan


def one_timeframing_up(lows: pd.Series) -> int:
    """Consecutive bars (from the latest backwards) whose low held at or
    above the prior bar's low."""
    lo = lows.dropna().values
    n = 0
    for i in range(len(lo) - 1, 0, -1):
        if lo[i] >= lo[i - 1]:
            n += 1
        else:
            break
    return n


def failed_auction_low(weekly: pd.DataFrame, probe_window: int = 8,
                       ref_window: int = 26):
    """Detect a failed auction at the lows: within the last probe_window
    weeks, a week probed under the min low of the ref_window weeks before
    it, closed back above that reference, and no later week traded below
    the probe. Returns (True, probe_low) or (False, None)."""
    w = weekly.dropna(subset=['Low', 'Close'])
    if len(w) < ref_window + 2:
        return False, None
    lows, closes = w['Low'].values, w['Close'].values
    n = len(w)
    for i in range(max(ref_window, n - probe_window), n):
        ref = lows[i - ref_window:i].min()
        if lows[i] < ref and closes[i] > ref:
            if i == n - 1 or lows[i + 1:].min() >= lows[i]:
                return True, float(lows[i])
    return False, None


def weekly_features(weekly: pd.DataFrame) -> dict:
    """The operating-auction leg (most important)."""
    f = {}
    w = weekly.tail(30)
    if len(w) < 20:
        return {'weekly_ok': False}
    f['weekly_ok'] = True
    poc, val, vah = composite_value(w.tail(26))
    f['poc_26w'], f['val_26w'], f['vah_26w'] = poc, val, vah
    close = float(w['Close'].iloc[-1])
    f['close'] = close
    # value migration: recent 4w value centre vs the 13 weeks before them
    poc4, _, _ = composite_value(w.tail(4))
    poc13, _, _ = composite_value(w.tail(17).head(13))
    f['value_migration_up'] = (poc4 is not None and poc13 is not None
                               and poc4 > poc13)
    f['poc_4w'], f['poc_prior13w'] = poc4, poc13
    # bracket of prior 13 weeks, excluding the latest 2 (the move itself)
    br = w.tail(15).head(13)
    bh, bl = float(br['High'].max()), float(br['Low'].min())
    f['bracket_high'], f['bracket_low'] = bh, bl
    last2 = w['Close'].tail(2)
    f['breakout_up'] = close > bh
    f['acceptance_up'] = bool((last2 > bh).all() and f['value_migration_up'])
    f['rejection_up'] = bool(float(w['High'].iloc[-1]) > bh and close <= bh)
    fa, probe = failed_auction_low(weekly)
    f['failed_low'], f['failed_low_level'] = fa, probe
    f['otf_up_weeks'] = one_timeframing_up(w['Low'].tail(9))
    rng4 = float(w['High'].tail(4).max() - w['Low'].tail(4).min())
    rng26 = float(w['High'].tail(26).max() - w['Low'].tail(26).min())
    f['compression_4_26'] = rng4 / rng26 if rng26 > 0 else np.nan
    # volume confirmation: up-week vs down-week volume, last 13 weeks
    t13 = w.tail(13)
    up = t13['Close'] >= t13['Open']
    uv, dv = t13['Volume'][up].mean(), t13['Volume'][~up].mean()
    f['vol_up_down_ratio'] = float(uv / dv) if dv and dv > 0 else np.nan
    # auction efficiency: value progress per unit of range, 8 weeks
    poc_now, _, _ = composite_value(w.tail(26))
    poc_prev, _, _ = composite_value(weekly.tail(34).head(26))
    ranges = (w['High'] - w['Low']).tail(8)
    denom = float(ranges.sum())
    f['auction_efficiency_8w'] = (abs(poc_now - poc_prev) / denom
                                  if (poc_now and poc_prev and denom > 0)
                                  else np.nan)
    return f


def monthly_features(monthly: pd.DataFrame) -> dict:
    """Parent context leg."""
    f = {}
    m = monthly.tail(14)
    if len(m) < 8:
        return {'monthly_ok': False}
    f['monthly_ok'] = True
    poc, val, vah = composite_value(m.tail(12))
    close = float(m['Close'].iloc[-1])
    f['m_poc'], f['m_val'], f['m_vah'] = poc, val, vah
    if vah is not None and close > vah:
        f['m_context'] = 1        # trending above accepted value
    elif val is not None and close < val:
        f['m_context'] = -1       # below value
    else:
        f['m_context'] = 0        # inside balance
    poc_now, _, _ = composite_value(m.tail(6))
    poc_prev, _, _ = composite_value(m.tail(12).head(6))
    f['m_value_migration_up'] = (poc_now is not None and poc_prev is not None
                                 and poc_now > poc_prev)
    return f


def daily_features(daily: pd.DataFrame, weekly_bracket_high) -> dict:
    """Trigger leg."""
    f = {}
    d = daily.tail(70)
    if len(d) < 30:
        return {'daily_ok': False}
    f['daily_ok'] = True
    close = float(d['Close'].iloc[-1])
    br = d.tail(22).head(20)
    f['d_above_20d_bracket'] = close > float(br['High'].max())
    f['d_otf_up_days'] = one_timeframing_up(d['Low'].tail(7))
    lo60 = float(d['Low'].tail(60).min())
    ex = False
    t10 = d.tail(10)
    for _, r in t10.iterrows():
        rng = r['High'] - r['Low']
        if rng > 0 and r['Low'] <= lo60 * 1.001 and \
           (r['Close'] - r['Low']) / rng > 0.6:
            ex = True
    f['d_excess_low'] = ex
    f['d_accepts_weekly_break'] = bool(
        weekly_bracket_high is not None
        and (d['Close'].tail(3) > weekly_bracket_high).all())
    return f


def alignment(mf: dict, wf: dict, df_: dict) -> dict:
    """0-100 confluence score; weekly weighs 0.5, monthly 0.3, daily 0.2."""
    w = 0.0
    if wf.get('weekly_ok'):
        if wf.get('failed_low') or wf.get('acceptance_up'):
            w += 0.40   # the two primary setups; a full weekly leg = 1.0
        if wf.get('value_migration_up'):
            w += 0.20
        if wf.get('otf_up_weeks', 0) >= 3:
            w += 0.15
        r = wf.get('vol_up_down_ratio')
        if r is not None and not np.isnan(r) and r > 1.2:
            w += 0.15
        if wf.get('breakout_up'):
            w += 0.10
        c = wf.get('compression_4_26')
        if c is not None and not np.isnan(c) and c < 0.35 \
                and not wf.get('breakout_up'):
            w += 0.10   # coiled at the edge, pre-breakout
    m = 0.0
    if mf.get('monthly_ok'):
        m += {1: 0.5, 0: 0.3, -1: 0.0}[mf.get('m_context', 0)]
        if mf.get('m_value_migration_up'):
            m += 0.5
    d = 0.0
    if df_.get('daily_ok'):
        if df_.get('d_above_20d_bracket'):
            d += 0.4
        if df_.get('d_excess_low'):
            d += 0.3
        if df_.get('d_accepts_weekly_break'):
            d += 0.3
    score = 100 * (0.5 * min(w, 1.0) + 0.3 * min(m, 1.0) + 0.2 * min(d, 1.0))
    # classification label, weekly-led
    if wf.get('acceptance_up'):
        label = 'accepted_breakout'
    elif wf.get('failed_low'):
        label = 'failed_auction_low'
    elif wf.get('breakout_up'):
        label = 'breakout_unconfirmed'
    elif wf.get('rejection_up'):
        label = 'rejection_at_highs'
    elif wf.get('weekly_ok'):
        label = 'balance'
    else:
        label = 'insufficient_history'
    return {'alignment_score': round(score, 1), 'auction_label': label}


def geometry(wf: dict) -> dict:
    """Structural destination / invalidation and gross RR, weekly-led.
    Destination: POC if below it, else value-area high / measured move.
    Invalidation: failed-low probe if present, else bracket low."""
    out = {'destination': np.nan, 'invalidation': np.nan, 'rr_struct': np.nan}
    if not wf.get('weekly_ok'):
        return out
    close = wf['close']
    poc, vah = wf.get('poc_26w'), wf.get('vah_26w')
    if poc is None:
        return out
    dest = poc if close < poc else (vah if (vah and close < vah) else
                                    close + (vah - poc if vah else 0))
    inval = wf.get('failed_low_level') or wf.get('bracket_low')
    if dest is None or inval is None or close <= inval or dest <= close:
        out['destination'], out['invalidation'] = dest, inval
        return out
    out['destination'], out['invalidation'] = dest, inval
    out['rr_struct'] = round((dest - close) / (close - inval), 2)
    return out

# ----------------------------------------------------------------------
# 2. Pipeline
# ----------------------------------------------------------------------

def analyse_ticker(daily: pd.DataFrame, harm_depth: int = 10,
                   harm_tol: float = 0.15, harm_bars: int = 15) -> dict:
    daily = daily.dropna(subset=['Close'])
    weekly = resample(daily, 'W-FRI')
    monthly = resample(daily, 'ME')
    wf = weekly_features(weekly)
    mf = monthly_features(monthly)
    df_ = daily_features(daily, wf.get('bracket_high'))
    row = {}
    row.update(alignment(mf, wf, df_))
    row.update(geometry(wf))
    keep = ['failed_low', 'failed_low_level', 'breakout_up', 'acceptance_up',
            'rejection_up', 'value_migration_up', 'otf_up_weeks',
            'compression_4_26', 'vol_up_down_ratio', 'auction_efficiency_8w',
            'bracket_high', 'bracket_low', 'poc_26w', 'vah_26w', 'val_26w']
    for k in keep:
        row[k] = wf.get(k)
    row['m_context'] = mf.get('m_context')
    row['m_value_migration_up'] = mf.get('m_value_migration_up')
    for k in ['d_above_20d_bracket', 'd_otf_up_days', 'd_excess_low',
              'd_accepts_weekly_break']:
        row[k] = df_.get(k)
    # Harmonic scanner (TradingView "Harmonic Scanner" port): most recent
    # completion within harm_bars on the daily and the weekly bars.
    hd = harmonics.latest_signal(daily, harm_depth, harm_tol, harm_bars)
    for k, v in hd.items():
        row[k + '_d'] = v
    hw = harmonics.latest_signal(weekly, harm_depth, harm_tol, harm_bars)
    for k, v in hw.items():
        row[k + '_w'] = v
    d90 = daily.tail(90)
    row['cs_spread_pct'] = round(corwin_schultz(d90['High'], d90['Low']) * 100, 3)
    row['amihud_1e9'] = round(amihud(d90['Close'].tail(20), d90['Volume'].tail(20)), 4)
    row['dollar_vol_20d_m'] = round(float(
        (d90['Close'] * d90['Volume']).tail(20).mean() / 1e6), 2)
    return row


def run(args):
    import yfinance as yf
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
        base = pd.DataFrame({'ticker': tickers})
    else:
        base = pd.read_csv(args.shortlist, dtype={'ticker': str},
                           keep_default_na=False)
        tickers = [t for t in base['ticker'] if t]
    ckpt = Path(args.ckpt)
    done = pd.read_parquet(ckpt) if (args.resume and ckpt.exists()) else pd.DataFrame()
    rows = done.to_dict('records') if not done.empty else []
    seen = {r['ticker'] for r in rows}
    todo = [t for t in tickers if t not in seen]
    sess = make_session()
    print(f"Auction overlay on {len(todo)} tickers ({len(seen)} from checkpoint)")
    for k, t in enumerate(todo):
        try:
            px = yf.download(t, period='2y', interval='1d', auto_adjust=True,
                             progress=False, session=sess)
            if px is None or px.empty:
                raise RuntimeError('no data')
            if isinstance(px.columns, pd.MultiIndex):
                px.columns = px.columns.get_level_values(0)
            row = {'ticker': t}
            row.update(analyse_ticker(px, args.harm_depth, args.harm_error / 100,
                                      args.harm_bars))
            rows.append(row)
            pd.DataFrame(rows).to_parquet(ckpt)
        except Exception as e:
            print(f"  [skip] {t}: {type(e).__name__}: {str(e)[:60]}")
        if k % 10 == 0:
            print(f"  {k}/{len(todo)}")
        time.sleep(args.sleep)
    out = pd.DataFrame(rows)
    if out.empty:
        sys.exit("No auction rows produced.")
    merged = base.merge(out, on='ticker', how='left')
    merged = merged.sort_values('alignment_score', ascending=False)
    merged.to_csv(args.out, index=False)
    print(f"Wrote {len(merged)} rows -> {args.out}")
    cols = ['ticker', 'alignment_score', 'auction_label', 'rr_struct',
            'otf_up_weeks', 'value_migration_up', 'cs_spread_pct']
    print(merged[[c for c in cols if c in merged.columns]]
          .head(20).to_string(index=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--shortlist', default='us_global_shortlist.csv')
    p.add_argument('--tickers', default='')
    p.add_argument('--out', default='shortlist_auction.csv')
    p.add_argument('--ckpt', default='.ckpt_auction.parquet')
    p.add_argument('--sleep', type=float, default=0.5)
    p.add_argument('--harm-depth', type=int, default=10,
                   help='harmonic scanner ZigZag depth (script base setting)')
    p.add_argument('--harm-error', type=float, default=15.0,
                   help='harmonic error tolerance in %% (script base setting; '
                        'published default was 5)')
    p.add_argument('--harm-bars', type=int, default=15,
                   help='flag completions within the last N bars')
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    run(args)


if __name__ == '__main__':
    main()
