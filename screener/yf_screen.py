"""
200-week-low x normalised FCF yield x buyback screener — yfinance backend.
=========================================================================
Cloud-ready: runs in Claude Code cloud sessions as well as on a local
machine. When HTTPS_PROXY is set (cloud sessions route all outbound
HTTPS through a TLS-intercepting agent proxy), make_session() swaps
yfinance's default TLS fingerprint for one the proxy can handshake;
off-proxy the yfinance default is used untouched. The computational
core is unit-tested offline against synthetic yfinance-shaped data
(see test_yf_screen.py).

Setup:
    pip install -r requirements.txt   # yfinance pandas pyarrow lxml numpy

Usage:
    # Wide US sweep (6,211 names from bundled universe_us.csv):
    python yf_screen.py --universe-file universe_us.csv --out us_shortlist.csv

    # Global majors (Wikipedia-scraped at runtime + embedded fallbacks):
    python yf_screen.py --universe SP500,FTSE100,NIKKEI225,HSI,DAX,ASX200,KOSPI \
                        --out global_shortlist.csv

    # Resume an interrupted run:
    python yf_screen.py --universe-file universe_us.csv --resume

Filters (tune via flags):
    --within-low-pct 15       price within 15%% of its 200-week low
    --min-norm-fcf-yield 0.07 5y-average FCF / current mkt cap >= 7%%
    --min-buyback-yield 0.03  TTM gross buyback / mkt cap >= 3%%
    --max-nd-ebitda 4.5       net debt / 5y avg EBITDA ceiling
    --min-price 1.0 --min-weeks 150

Why normalised FCF: in a universe defined by "price at multi-year lows",
TTM FCF is depressed by the same shock that broke the price. Screening on
trailing FCF yield systematically EXCLUDES the recoverable names. We use
mean(last 5 fiscal-year FCF) over CURRENT market cap.
"""

from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# 1. Fuzzy row matching for yfinance financial statements
#    (labels drift across versions: "Operating Cash Flow" vs
#    "OperatingCashFlow" vs "Total Cash From Operating Activities")
# ----------------------------------------------------------------------

def _norm(label) -> str:
    return re.sub(r'[^a-z]', '', str(label).lower())

def pick(df: pd.DataFrame | None, *aliases: str) -> pd.Series | None:
    """Return the first row of df whose normalised label matches an alias."""
    if df is None or df.empty:
        return None
    idx = {_norm(i): i for i in df.index}
    for a in aliases:
        key = _norm(a)
        if key in idx:
            return df.loc[idx[key]]
    return None

ALIAS = {
    'ocf':      ('OperatingCashFlow', 'TotalCashFromOperatingActivities',
                 'CashFlowFromContinuingOperatingActivities'),
    'capex':    ('CapitalExpenditure', 'CapitalExpenditures',
                 'PurchaseOfPPE', 'NetPPEPurchaseAndSale'),
    'fcf':      ('FreeCashFlow',),
    'buyback':  ('RepurchaseOfCapitalStock', 'CommonStockPayments',
                 'PurchaseOfStock', 'SalePurchaseOfStock'),
    'issuance': ('IssuanceOfCapitalStock', 'CommonStockIssuance',
                 'ProceedsFromStockOptionExercised'),
    'totdebt':  ('TotalDebt',),
    'ltdebt':   ('LongTermDebt', 'LongTermDebtAndCapitalLeaseObligation'),
    'stdebt':   ('CurrentDebt', 'CurrentDebtAndCapitalLeaseObligation',
                 'ShortLongTermDebt'),
    'cash':     ('CashCashEquivalentsAndShortTermInvestments',
                 'CashAndCashEquivalents', 'CashFinancial'),
    'ebitda':   ('EBITDA', 'NormalizedEBITDA'),
}

# ----------------------------------------------------------------------
# 2. Pure computational core (unit-tested offline)
# ----------------------------------------------------------------------

def pct_above_200w_low(prices: pd.Series, min_weeks: int = 150) -> float | None:
    """Distance of last close above the min of the trailing 200 weekly bars."""
    s = prices.dropna()
    if len(s) < min_weeks:
        return None
    tail = s.tail(200)
    low = float(tail.min())
    cur = float(s.iloc[-1])
    if low <= 0:
        return None
    return cur / low - 1.0


def fcf_series_from_cashflow(cf: pd.DataFrame | None, n: int = 5) -> list[float]:
    """Per-fiscal-year FCF, newest first. Prefers reported FCF row; else
    OCF + capex (capex reported negative)."""
    if cf is None or cf.empty:
        return []
    cols = sorted(cf.columns, reverse=True)[:n]
    direct = pick(cf, *ALIAS['fcf'])
    ocf, capex = pick(cf, *ALIAS['ocf']), pick(cf, *ALIAS['capex'])
    out = []
    for c in cols:
        v = None
        if direct is not None and pd.notna(direct.get(c)):
            v = float(direct[c])
        elif ocf is not None and pd.notna(ocf.get(c)):
            cap = float(capex.get(c)) if (capex is not None and pd.notna(capex.get(c))) else 0.0
            v = float(ocf[c]) + cap          # capex already negative
        if v is not None:
            out.append(v)
    return out


def ttm_flow(qcf: pd.DataFrame | None, aliases: tuple, sign: str) -> float:
    """Sum last 4 quarters of a cashflow row. sign='neg' keeps only
    outflows (returned as positive); 'pos' keeps only inflows."""
    row = pick(qcf, *aliases)
    if row is None:
        return 0.0
    vals = [float(v) for v in row.sort_index(ascending=False).head(4) if pd.notna(v)]
    if sign == 'neg':
        return sum(-v for v in vals if v < 0)
    return sum(v for v in vals if v > 0)


def net_debt_from_bs(bs: pd.DataFrame | None) -> float | None:
    if bs is None or bs.empty:
        return None
    col = sorted(bs.columns, reverse=True)[0]
    td = pick(bs, *ALIAS['totdebt'])
    if td is not None and pd.notna(td.get(col)):
        debt = float(td[col])
    else:
        lt, st = pick(bs, *ALIAS['ltdebt']), pick(bs, *ALIAS['stdebt'])
        debt = sum(float(r[col]) for r in (lt, st)
                   if r is not None and pd.notna(r.get(col)))
    cash_row = pick(bs, *ALIAS['cash'])
    cash = float(cash_row[col]) if (cash_row is not None and pd.notna(cash_row.get(col))) else 0.0
    return debt - cash


def ebitda_5y_avg(inc: pd.DataFrame | None, n: int = 5) -> float | None:
    row = pick(inc, *ALIAS['ebitda'])
    if row is None:
        return None
    vals = [float(v) for v in row.sort_index(ascending=False).head(n) if pd.notna(v)]
    return float(np.mean(vals)) if vals else None


def score_row(dist, norm_y, ttm_y, bb_y, net_bb_y, nd_e, mcap, meta) -> dict:
    return {
        'ticker': meta.get('ticker', ''), 'name': meta.get('name', ''),
        'sector': meta.get('sector', ''), 'exchange': meta.get('exchange', ''),
        'pct_above_200w_low': round(dist * 100, 1),
        'norm_fcf_yield_5y_pct': round(norm_y * 100, 2),
        'ttm_fcf_yield_pct': round(ttm_y * 100, 2) if ttm_y is not None else np.nan,
        'buyback_yield_ttm_pct': round(bb_y * 100, 2),
        'net_buyback_yield_ttm_pct': round(net_bb_y * 100, 2),
        'net_debt_5y_ebitda': round(nd_e, 2) if nd_e is not None else np.nan,
        'market_cap_usd_m': round(mcap / 1e6),
        'transience_score': 0.5, 'capital_reset_score': 0.5,
    }

# ----------------------------------------------------------------------
# 3. Universe construction
# ----------------------------------------------------------------------

WIKI = {
    'SP500':     ('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', 'Symbol', ''),
    'SP400':     ('https://en.wikipedia.org/wiki/List_of_S%26P_400_companies', 'Symbol', ''),
    'SP600':     ('https://en.wikipedia.org/wiki/List_of_S%26P_600_companies', 'Symbol', ''),
    'FTSE100':   ('https://en.wikipedia.org/wiki/FTSE_100_Index', 'Ticker', '.L'),
    'FTSE250':   ('https://en.wikipedia.org/wiki/FTSE_250_Index', 'Ticker', '.L'),
    'HSI':       ('https://en.wikipedia.org/wiki/Hang_Seng_Index', 'Ticker', '.HK'),
    'DAX':       ('https://en.wikipedia.org/wiki/DAX', 'Ticker', ''),
    'CAC40':     ('https://en.wikipedia.org/wiki/CAC_40', 'Ticker', ''),
    'ASX200':    ('https://en.wikipedia.org/wiki/S%26P/ASX_200', 'Code', '.AX'),
    'TSX60':     ('https://en.wikipedia.org/wiki/S%26P/TSX_60', 'Symbol', '.TO'),
    'IBOV':      ('https://en.wikipedia.org/wiki/Lista_de_companhias_citadas_no_Ibovespa', 'Código', '.SA'),
}

# Liquid-core fallbacks if Wikipedia scrape fails (curated, not exhaustive)
FALLBACK = {
    'FTSE100':  ['SHEL.L','AZN.L','HSBA.L','ULVR.L','BP.L','GSK.L','RIO.L','REL.L',
                 'DGE.L','BATS.L','RKT.L','NG.L','VOD.L','LLOY.L','BARC.L','TSCO.L',
                 'IMB.L','BT-A.L','KGF.L','MKS.L','WPP.L','STAN.L','PRU.L','LGEN.L'],
    'NIKKEI225':['7203.T','6758.T','8306.T','6861.T','9983.T','8035.T','4063.T',
                 '6501.T','7267.T','8058.T','8031.T','9432.T','6902.T','7974.T',
                 '6098.T','8316.T','8411.T','2914.T','4502.T','6752.T'],
    'HSI':      ['0700.HK','9988.HK','3690.HK','0941.HK','0005.HK','1299.HK',
                 '0388.HK','0939.HK','1398.HK','2318.HK','0883.HK','0857.HK',
                 '1810.HK','9618.HK','2020.HK','0027.HK','0016.HK','0011.HK'],
    'KOSPI':    ['005930.KS','000660.KS','005490.KS','005380.KS','051910.KS',
                 '035420.KS','006400.KS','035720.KS','105560.KS','055550.KS',
                 '096770.KS','066570.KS','003550.KS','017670.KS','034730.KS'],
    'DAX':      ['SAP.DE','SIE.DE','ALV.DE','DTE.DE','AIR.DE','MUV2.DE','BAS.DE',
                 'BAYN.DE','BMW.DE','MBG.DE','VOW3.DE','DBK.DE','IFX.DE','RWE.DE'],
    'CAC40':    ['MC.PA','OR.PA','TTE.PA','SAN.PA','AIR.PA','SU.PA','AI.PA',
                 'BNP.PA','KER.PA','RI.PA','DG.PA','CAP.PA','GLE.PA','STLAM.MI'],
    'ASX200':   ['BHP.AX','CBA.AX','CSL.AX','NAB.AX','WBC.AX','ANZ.AX','WES.AX',
                 'MQG.AX','WDS.AX','TLS.AX','RIO.AX','FMG.AX','QBE.AX','STO.AX'],
}

_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

def _fetch_html(url: str) -> str:
    """Fetch a page with a browser User-Agent (Wikipedia 403s the default
    Python-urllib UA). urllib honors HTTPS_PROXY/SSL_CERT_FILE env vars."""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': _BROWSER_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _nikkei225_tickers() -> list[str]:
    """The Nikkei 225 Wikipedia page no longer carries a constituents table;
    scrape the official index site instead."""
    html = _fetch_html('https://indexes.nikkei.co.jp/en/nkave/index/component')
    codes = sorted(set(re.findall(r'>(\d{4})</td>', html)))
    return [c + '.T' for c in codes]


def build_universe(args) -> pd.DataFrame:
    frames = []
    if args.universe_file:
        df = pd.read_csv(args.universe_file)
        assert 'ticker' in df.columns, "universe file needs a 'ticker' column"
        frames.append(df)
    if args.universe:
        import io
        for u in [x.strip().upper() for x in args.universe.split(',') if x.strip()]:
            tickers = []
            if u == 'NIKKEI225':
                try:
                    tickers = _nikkei225_tickers()
                except Exception as e:
                    print(f"  [warn] Nikkei site fetch failed: {e}")
            elif u in WIKI:
                url, col, suffix = WIKI[u]
                try:
                    tables = pd.read_html(io.StringIO(_fetch_html(url)))
                    for t in tables:
                        if col in t.columns:
                            # dropna before astype: pandas 3.0 keeps NaN as
                            # missing through astype(str), so floats would
                            # otherwise leak into the str comprehension below
                            raw = t[col].dropna().astype(str).str.strip()
                            tickers = [r + suffix if suffix and not r.endswith(suffix)
                                       else r for r in raw if r and r.lower() != 'nan']
                            break
                except Exception as e:
                    print(f"  [warn] Wikipedia fetch failed for {u}: {e}")
            if not tickers and u in FALLBACK:
                tickers = FALLBACK[u]
                print(f"  [info] using embedded fallback list for {u} ({len(tickers)})")
            if tickers:
                frames.append(pd.DataFrame({'ticker': tickers, 'exchange': u,
                                            'index_tag': u, 'name': '', 'sector': ''}))
    if not frames:
        sys.exit("No universe. Pass --universe-file and/or --universe.")
    uni = pd.concat(frames, ignore_index=True)
    uni['ticker'] = uni['ticker'].str.replace('.', '-', regex=False).where(
        ~uni['ticker'].str.contains(r'\.(?:L|T|HK|KS|KQ|DE|PA|AX|TO|SA|MI|AS|SW|ST|OL|HE|CO)$',
                                    regex=True), uni['ticker'])
    uni = uni.drop_duplicates('ticker').reset_index(drop=True)
    print(f"Universe: {len(uni)} tickers")
    return uni

# ----------------------------------------------------------------------
# 4. Pipeline (network side)
# ----------------------------------------------------------------------

def make_session():
    """Yahoo session that survives TLS-intercepting proxies.

    Behind an agent/corporate MITM proxy (e.g. Claude cloud sessions),
    yfinance's default curl_cffi fingerprint (latest Chrome) sends
    post-quantum TLS extensions the proxy can't handshake, so every
    request dies with curl error 35. An older profile handshakes fine,
    and libcurl picks up HTTPS_PROXY + the CA bundle from the
    environment on its own. Off-proxy, return None so yfinance keeps
    its own default session.
    """
    if not (os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')):
        return None
    try:
        from curl_cffi import requests as cr
    except ImportError:
        return None
    return cr.Session(impersonate='chrome110')


def stage1_prices(uni: pd.DataFrame, args, ckpt: Path) -> pd.DataFrame:
    import yfinance as yf
    sess = make_session()
    done = pd.read_parquet(ckpt) if (args.resume and ckpt.exists()) else \
           pd.DataFrame(columns=['ticker', 'dist', 'last_px'])
    seen = set(done['ticker'])
    todo = [t for t in uni['ticker'] if t not in seen]
    print(f"Stage 1: {len(todo)} to price ({len(seen)} from checkpoint)")
    CH = 200
    for i in range(0, len(todo), CH):
        chunk = todo[i:i + CH]
        for attempt in range(4):
            try:
                px = yf.download(chunk, period='5y', interval='1wk',
                                 auto_adjust=True, progress=False, threads=True,
                                 session=sess)['Close']
                break
            except Exception as e:
                wait = 20 * (attempt + 1)
                print(f"  [retry {attempt+1}] {type(e).__name__}: sleeping {wait}s")
                time.sleep(wait)
        else:
            continue
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        rows, got = [], 0
        for t in chunk:
            if t not in px.columns:
                continue          # no data (failed/rate-limited): retry on --resume
            lp = px[t].dropna()
            if lp.empty:
                continue          # ditto
            got += 1
            d = pct_above_200w_low(px[t], args.min_weeks)
            if d is None or lp.iloc[-1] < args.min_price:
                # Legitimately filtered (short history / penny). Checkpoint
                # with dist=NaN so --resume passes don't re-download it;
                # NaN never satisfies the survivor threshold below.
                d = np.nan
            rows.append({'ticker': t, 'dist': d, 'last_px': float(lp.iloc[-1])})
        done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
        done.to_parquet(ckpt)
        surv = (done['dist'] <= args.within_low_pct / 100).sum()
        print(f"  {min(i+CH, len(todo))}/{len(todo)} priced | "
              f"cumulative survivors: {surv}")
        if got < max(1, len(chunk) // 4):
            print(f"  [rate-limited?] only {got}/{len(chunk)} returned data; "
                  f"backing off 90s")
            time.sleep(90)
        time.sleep(1.5)
    missing = len(set(uni['ticker']) - set(done['ticker']))
    if missing:
        print(f"  [note] {missing} tickers still unpriced (failures/rate "
              f"limits); rerun with --resume to retry them")
    out = done[done['dist'] <= args.within_low_pct / 100].copy()
    print(f"Stage 1 survivors (within {args.within_low_pct}% of 200w low): {len(out)}")
    return out


def stage2_fundamentals(surv: pd.DataFrame, uni: pd.DataFrame, args, ckpt: Path) -> pd.DataFrame:
    import yfinance as yf
    sess = make_session()
    meta = uni.set_index('ticker').to_dict('index')
    done = pd.read_parquet(ckpt) if (args.resume and ckpt.exists()) else pd.DataFrame()
    seen = set(done['ticker']) if not done.empty else set()
    rows = done.to_dict('records') if not done.empty else []
    todo = [r for _, r in surv.iterrows() if r['ticker'] not in seen]
    print(f"Stage 2: fundamentals on {len(todo)} survivors")
    for k, r in enumerate(todo):
        t = r['ticker']
        try:
            tk = yf.Ticker(t, session=sess)
            cf_y = tk.cashflow
            fcf5 = fcf_series_from_cashflow(cf_y)
            if len(fcf5) < 3:
                continue
            qcf = tk.quarterly_cashflow
            bb = ttm_flow(qcf, ALIAS['buyback'], 'neg')
            iss = ttm_flow(qcf, ALIAS['issuance'], 'pos')
            fcf_ttm_vals = fcf_series_from_cashflow(qcf, n=4)
            fcf_ttm = sum(fcf_ttm_vals) if len(fcf_ttm_vals) == 4 else None
            try:
                mcap = float(tk.fast_info['market_cap'])
            except Exception:
                mcap = float((tk.info or {}).get('marketCap', 0))
            if not mcap or mcap <= 0:
                continue
            norm_y = float(np.mean(fcf5)) / mcap
            bb_y, net_bb_y = bb / mcap, (bb - iss) / mcap
            nd = net_debt_from_bs(tk.balance_sheet)
            e5 = ebitda_5y_avg(tk.income_stmt)
            nd_e = (nd / e5) if (nd is not None and e5 and e5 > 0) else None
            if norm_y < args.min_norm_fcf_yield:  continue
            if bb_y < args.min_buyback_yield:     continue
            if nd_e is not None and nd_e > args.max_nd_ebitda: continue
            m = meta.get(t, {}); m['ticker'] = t
            rows.append(score_row(r['dist'], norm_y,
                                  (fcf_ttm / mcap) if fcf_ttm is not None else None,
                                  bb_y, net_bb_y, nd_e, mcap, m))
            pd.DataFrame(rows).to_parquet(ckpt)
        except Exception as e:
            if '429' in str(e) or 'Too Many' in str(e):
                print("  [rate-limited] sleeping 60s"); time.sleep(60)
        if k % 25 == 0:
            print(f"  {k}/{len(todo)} | passing: {len(rows)}")
        time.sleep(args.sleep)
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--universe', default='')
    p.add_argument('--universe-file', default='')
    p.add_argument('--within-low-pct', type=float, default=15.0)
    p.add_argument('--min-norm-fcf-yield', type=float, default=0.07)
    p.add_argument('--min-buyback-yield', type=float, default=0.03)
    p.add_argument('--max-nd-ebitda', type=float, default=4.5)
    p.add_argument('--min-price', type=float, default=1.0)
    p.add_argument('--min-weeks', type=int, default=150)
    p.add_argument('--sleep', type=float, default=0.4)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--out', default='shortlist.csv')
    args = p.parse_args()

    uni = build_universe(args)
    ck1, ck2 = Path('.ckpt_prices.parquet'), Path('.ckpt_fund.parquet')
    surv = stage1_prices(uni, args, ck1)
    df = stage2_fundamentals(surv, uni, args, ck2)
    if df.empty:
        print("No names passed. Loosen thresholds."); return
    ranks = df[['norm_fcf_yield_5y_pct', 'net_buyback_yield_ttm_pct']].rank(pct=True)
    df['composite'] = (0.30 * ranks['norm_fcf_yield_5y_pct']
                       + 0.25 * ranks['net_buyback_yield_ttm_pct'].clip(lower=0)
                       + 0.25 * df['transience_score']
                       + 0.20 * df['capital_reset_score'])
    df = df.sort_values('composite', ascending=False)
    df.to_csv(args.out, index=False)
    print(f"\nWrote {len(df)} names -> {args.out}")
    print(df.head(40).to_string(index=False))


if __name__ == '__main__':
    main()
