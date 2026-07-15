#!/usr/bin/env python3
"""Segment-level harvester using edgartools (full XBRL parse, dimensional facts).

The SEC companyfacts API drops segment dimensions; edgartools parses the raw
filing XBRL and exposes per-segment (product/service/geography/business-unit)
revenue and operating income.

For each ticker we pull the latest 10-K, extract dimensioned income-statement
facts, group revenue (and operating income where present) by segment member ×
fiscal year, and compute:

  • n_segments, largest_segment_pct (concentration)
  • seg_rev_growth_fastest / _slowest  (YoY of fastest- and slowest-growing seg)
  • seg_growth_dispersion             (std of segment growth rates)
  • seg_mix_shift_pp                  (largest single-segment share change YoY)
  • seg_inflection_flag               (fastest segment accelerating AND gaining
                                       mix share while a legacy segment shrinks)
  • seg_margin_best / _worst          (operating-income segments, if disclosed)
  • seg_high_margin_growing           (the highest-margin segment is also growing)

Multi-worker, resumable. SEC rate-limited via edgartools' own throttle.
"""
import argparse, sys, time, threading, warnings, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

os.environ.setdefault('EDGAR_IDENTITY', 'cyclepapa research cm2whv9sg2@privaterelay.appleid.com')
for v in ('REQUESTS_CA_BUNDLE', 'SSL_CERT_FILE'):
    if os.path.exists('/root/.ccr/ca-bundle.crt'):
        os.environ.setdefault(v, '/root/.ccr/ca-bundle.crt')

from edgar import Company, set_identity
set_identity(os.environ['EDGAR_IDENTITY'])

REV_CONCEPTS = (
    'RevenueFromContractWithCustomerExcludingAssessedTax',
    'RevenueFromContractWithCustomerIncludingAssessedTax',
    'Revenues', 'SalesRevenueNet',
)
# Members that are NOT real operating segments (axis domains / accounting buckets)
NON_SEGMENT = {
    'cost of products sold', 'cost of services sold', 'cost of goods sold',
    'discontinued operations', 'corporate and all other', 'corporate',
    'intersegment elimination', 'eliminations', 'consolidated', 'total',
    'operating segments', 'reportable segments', 'product', 'service', 'products',
    'services', 'all other', 'total segment', 'total segments', 'segment total',
    'reportable segment', 'other segments', 'other segment',
}
# Substrings that disqualify a member (accounting artifacts, not businesses)
JUNK_SUBSTR = (
    'discontinued', 'eliminat', 'intersegment', 'reclassification',
    'accumulated other comprehensive', 'total segment', 'cost of',
    'unallocated', 'reconcil', 'adjustment', 'corporate',
)


def _is_segment_member(label):
    if not label: return False
    l = str(label).strip().lower()
    if l in NON_SEGMENT: return False
    if any(j in l for j in JUNK_SUBSTR): return False
    if len(l) < 2: return False
    return True


def harvest_one(ticker):
    try:
        c = Company(ticker)
        if c is None: return {'ticker': ticker, 'has_segments': False}
        filings = c.get_filings(form="10-K")
        if filings is None or len(filings) == 0:
            return {'ticker': ticker, 'has_segments': False, 'name': getattr(c, 'name', None)}
        # Latest 10-K already carries 2-3 fiscal years of segment data internally.
        # 4 filings = 4× XBRL parse cost for marginal extra history; latest(1) is enough.
        recent = filings.latest(1)
        if not isinstance(recent, list):
            try:
                recent = list(recent)
            except TypeError:
                recent = [recent]

        seg_rev = {}    # {segment: {fy: value}}
        seg_oi  = {}    # {segment: {fy: value}}
        total_rev = {}  # {fy: consolidated revenue}

        parse_error = False
        for fl in recent:
            try:
                xb = fl.xbrl()
                if xb is None: continue
                df = pd.DataFrame(xb.facts.get_facts_with_dimensions())
                if len(df) == 0: continue
                df = df[df['period_type'] == 'duration']
                # Revenue by segment
                rev = df[df['concept'].astype(str).str.split(':').str[-1].isin(REV_CONCEPTS)]
                for _, r in rev.iterrows():
                    fy = r.get('fiscal_year'); val = r.get('numeric_value'); lab = r.get('label')
                    dim = r.get('is_dimensioned')
                    if fy is None or val is None: continue
                    fy = int(fy)
                    if not dim:  # consolidated total
                        total_rev[fy] = max(total_rev.get(fy, 0), float(val))
                    elif _is_segment_member(lab):
                        seg_rev.setdefault(str(lab), {})[fy] = float(val)
                # Operating income by segment
                oi = df[df['concept'].astype(str).str.endswith('OperatingIncomeLoss') & df['is_dimensioned']]
                for _, r in oi.iterrows():
                    fy = r.get('fiscal_year'); val = r.get('numeric_value'); lab = r.get('label')
                    if fy is None or val is None: continue
                    if _is_segment_member(lab):
                        seg_oi.setdefault(str(lab), {})[int(fy)] = float(val)
            except Exception:
                parse_error = True
                continue

        # If the filing(s) failed to parse and we got nothing, treat as retriable
        # (return None) rather than recording a false "no segments" done row.
        if parse_error and not seg_rev:
            return None

        # Keep only segments that have >= 2 years of revenue
        seg_rev = {s: v for s, v in seg_rev.items() if len(v) >= 2}
        if not seg_rev:
            return {'ticker': ticker, 'has_segments': False, 'name': getattr(c, 'name', None)}

        years = sorted({fy for v in seg_rev.values() for fy in v}, reverse=True)
        if len(years) < 2:
            return {'ticker': ticker, 'has_segments': False, 'name': getattr(c, 'name', None)}
        y0, y1 = years[0], years[1]   # latest, prior

        # Per-segment latest YoY growth + latest mix share
        growths, shares_now, shares_prev = {}, {}, {}
        tot_now = sum(v.get(y0, 0) for v in seg_rev.values()) or np.nan
        tot_prev = sum(v.get(y1, 0) for v in seg_rev.values()) or np.nan
        for s, v in seg_rev.items():
            now, prev = v.get(y0), v.get(y1)
            if now is not None and prev is not None and prev != 0:
                growths[s] = now / prev - 1
            if now is not None and tot_now: shares_now[s] = now / tot_now
            if prev is not None and tot_prev: shares_prev[s] = prev / tot_prev

        if not growths:
            return {'ticker': ticker, 'has_segments': False, 'name': getattr(c, 'name', None)}

        g_vals = list(growths.values())
        fastest_seg = max(growths, key=growths.get)
        slowest_seg = min(growths, key=growths.get)
        largest_seg = max(shares_now, key=shares_now.get) if shares_now else None

        # Mix shift: biggest single-segment share change
        mix_shifts = {s: shares_now.get(s, 0) - shares_prev.get(s, 0) for s in seg_rev}
        gainer = max(mix_shifts, key=mix_shifts.get)
        mix_shift_pp = mix_shifts[gainer] * 100

        # Inflection: fastest-growing segment is gaining share AND a legacy seg shrinks
        legacy_shrinking = growths.get(slowest_seg, 0) < 0
        new_gaining = (mix_shifts.get(fastest_seg, 0) > 0.02) and (growths.get(fastest_seg, 0) > 0.10)
        seg_inflection = bool(new_gaining and legacy_shrinking)

        out = {
            'ticker': ticker, 'name': getattr(c, 'name', None), 'has_segments': True,
            'n_segments': len(seg_rev),
            'latest_fy': y0,
            'largest_segment': largest_seg,
            'largest_segment_pct': (shares_now.get(largest_seg) * 100) if largest_seg else None,
            'seg_rev_growth_fastest': growths[fastest_seg] * 100,
            'seg_fastest_name': fastest_seg,
            'seg_rev_growth_slowest': growths[slowest_seg] * 100,
            'seg_slowest_name': slowest_seg,
            'seg_growth_dispersion': float(np.std(g_vals)) * 100,
            'seg_mix_shift_pp': mix_shift_pp,
            'seg_mix_gainer': gainer,
            'seg_inflection_flag': seg_inflection,
        }

        # Segment operating margins (where both rev + oi disclosed for a segment)
        seg_oi = {s: v for s, v in seg_oi.items() if s in seg_rev}
        margins = {}
        for s in seg_oi:
            oi_now = seg_oi[s].get(y0); rv_now = seg_rev[s].get(y0)
            if oi_now is not None and rv_now and rv_now != 0:
                margins[s] = oi_now / rv_now
        if margins:
            best = max(margins, key=margins.get); worst = min(margins, key=margins.get)
            out['seg_margin_best'] = margins[best] * 100
            out['seg_margin_best_name'] = best
            out['seg_margin_worst'] = margins[worst] * 100
            # High-margin segment also growing = positive mix shift toward profit
            out['seg_high_margin_growing'] = bool(growths.get(best, -1) > 0.05 and mix_shifts.get(best, 0) > 0)
        return out
    except Exception:
        # Transient/parse failure — return None so the task loop does NOT write a
        # done row; the ticker stays unrecorded and is retried on the next --resume.
        # (Genuine "company has no segment data" paths above return has_segments=False.)
        return None


ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=4)
ap.add_argument('--checkpoint', type=int, default=50)
ap.add_argument('--resume', action='store_true')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).str.upper().unique().tolist()

# Limit to US-listed (SEC) tickers
if os.path.exists('/tmp/sec_tickers.json'):
    with open('/tmp/sec_tickers.json') as f:
        sec = {v['ticker'].upper() for v in json.load(f).values()}
    syms = [s for s in syms if s in sec]

already = set(); existing = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing = prev.to_dict('records')
        print(f"[seg] resume: {len(already)} done", file=sys.stderr)
    except Exception: pass

todo = [s for s in syms if s not in already]
print(f"[seg] {len(todo)} tickers · {args.workers} workers (full XBRL parse, heavy)", file=sys.stderr)

rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(t):
    r = harvest_one(t)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            el = time.time() - start; rate = done[0]/max(el,0.1)
            eta = (len(todo)-done[0])/max(rate,0.001)/60
            seg = sum(1 for x in rows if x.get('has_segments'))
            print(f"[seg] {done[0]}/{len(todo)}  with-segments {seg}  rate {rate:.2f}/s  ETA {eta:.0f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futs = [ex.submit(task, t) for t in todo]
    for _ in as_completed(futs): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
df = pd.DataFrame(rows)
seg = df[df.get('has_segments', False) == True] if 'has_segments' in df.columns else df
print(f"[seg] DONE: {len(df)} rows, {len(seg)} with segment data", file=sys.stderr)
if 'seg_inflection_flag' in seg.columns:
    print(f"  segment inflections: {int(seg['seg_inflection_flag'].fillna(False).sum())}", file=sys.stderr)
if 'seg_high_margin_growing' in seg.columns:
    print(f"  high-margin-growing: {int(seg['seg_high_margin_growing'].fillna(False).sum())}", file=sys.stderr)
