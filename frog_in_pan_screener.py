"""
Frog-in-the-Pan momentum screener for European + UK small/mid-cap equities.

Concept (Da, Gurun, Warachka 2014, "Frog in the Pan"):
    FIP = sign(PRET) * (%neg_days - %pos_days)

A LOW (negative) FIP score for a winner stock means it climbed via many small
continuous moves rather than a few headline jumps. The behavioural claim is
that investors underreact to that drip-feed information, so continuous winners
have stronger forward momentum than discrete winners.

This screener looks for stocks that are:
  - Winners (positive 12m return)
  - "Frog in the pan" on the DAILY timeframe (low daily FIP)
  - LESS frog-in-the-pan on the WEEKLY timeframe (higher weekly FIP)
  - But the weekly FIP is INFLECTING DOWN (becoming smoother on weekly too)

Survivors are then ranked by:
  - Low P/B
  - Low EV/EBITDA
  - High trailing revenue growth
  - High revenue-growth inflection (acceleration)

Run:
    pip install financedatabase yfinance pandas numpy tqdm
    python frog_in_pan_screener.py --out screen.csv
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


EUROPEAN_COUNTRIES = [
    "United Kingdom", "Ireland", "France", "Germany", "Netherlands",
    "Belgium", "Luxembourg", "Switzerland", "Austria", "Italy", "Spain",
    "Portugal", "Sweden", "Norway", "Denmark", "Finland", "Iceland",
    "Poland", "Czech Republic", "Hungary", "Greece", "Cyprus", "Malta",
    "Estonia", "Latvia", "Lithuania", "Slovenia", "Slovakia", "Romania",
    # Crown dependencies / micro-states with Yahoo listings
    "Guernsey", "Jersey", "Isle of Man", "Gibraltar", "Liechtenstein",
    "Monaco", "Macedonia", "Montenegro",
]

SMALL_MID_BUCKETS = ["Small Cap", "Mid Cap"]


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def load_universe(min_n: int = 50) -> pd.DataFrame:
    """Pull European + UK small & mid-caps from financedatabase."""
    import financedatabase as fd

    eq = fd.Equities()
    # financedatabase uses country names as filter keys; market_cap matches Yahoo bucket.
    df = eq.select(country=EUROPEAN_COUNTRIES, market_cap=SMALL_MID_BUCKETS)
    if df is None or df.empty:
        raise RuntimeError("financedatabase returned empty universe; check installation.")
    df = df.copy()
    df.index.name = "symbol"
    df = df[df.index.notna()]
    # Keep only rows with a usable Yahoo suffix (e.g. .L, .PA, .DE, ...)
    df = df[df.index.astype(str).str.contains(r"\.[A-Z]{1,3}$", regex=True)]
    if len(df) < min_n:
        print(f"[warn] universe smaller than expected: {len(df)}", file=sys.stderr)
    return df


# ---------------------------------------------------------------------------
# Frog-in-the-pan core math
# ---------------------------------------------------------------------------

def _fip(returns: pd.Series) -> tuple[float, float]:
    """Return (PRET, FIP) for a clean returns series.

    PRET is compounded return over the window.
    FIP  = sign(PRET) * (%neg - %pos)  with zero-return days excluded.
    """
    r = returns.dropna()
    if len(r) < 20:
        return (np.nan, np.nan)
    pret = float((1.0 + r).prod() - 1.0)
    nz = r[r != 0]
    if len(nz) == 0:
        return (pret, np.nan)
    pct_pos = float((nz > 0).mean())
    pct_neg = float((nz < 0).mean())
    sign = 1.0 if pret > 0 else (-1.0 if pret < 0 else 0.0)
    return (pret, sign * (pct_neg - pct_pos))


@dataclass
class FIPResult:
    symbol: str
    pret_d: float
    fip_d: float
    pret_w: float
    fip_w: float
    fip_w_prev: float        # weekly FIP measured one quarter ago (inflection)
    fip_w_inflection: float  # negative => weekly is becoming smoother
    last_price: float
    n_days: int


def compute_fip(symbol: str, prices: pd.Series) -> FIPResult | None:
    prices = prices.dropna()
    if len(prices) < 260:
        return None

    daily_ret = prices.pct_change()
    # Daily FIP over trailing ~252 trading days.
    pret_d, fip_d = _fip(daily_ret.iloc[-252:])

    # Weekly FIP over trailing ~52 weeks (Friday closes).
    weekly = prices.resample("W-FRI").last().dropna()
    if len(weekly) < 70:
        return None
    weekly_ret = weekly.pct_change()
    pret_w, fip_w = _fip(weekly_ret.iloc[-52:])

    # Weekly FIP one quarter ago (drop most recent ~13 weeks, take 52 before that).
    prev_window = weekly_ret.iloc[-(52 + 13):-13]
    _, fip_w_prev = _fip(prev_window)

    inflection = fip_w - fip_w_prev if not (math.isnan(fip_w) or math.isnan(fip_w_prev)) else np.nan

    return FIPResult(
        symbol=symbol,
        pret_d=pret_d,
        fip_d=fip_d,
        pret_w=pret_w,
        fip_w=fip_w,
        fip_w_prev=fip_w_prev,
        fip_w_inflection=inflection,
        last_price=float(prices.iloc[-1]),
        n_days=len(prices),
    )


# ---------------------------------------------------------------------------
# Price download
# ---------------------------------------------------------------------------

def download_prices(symbols: list[str], period: str = "2y", batch: int = 80) -> dict[str, pd.Series]:
    """Batched yfinance download. Returns {symbol -> adj-close series}."""
    import yfinance as yf

    out: dict[str, pd.Series] = {}
    for i in range(0, len(symbols), batch):
        chunk = symbols[i : i + batch]
        try:
            df = yf.download(
                tickers=" ".join(chunk),
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
            )
        except Exception as e:  # noqa: BLE001
            print(f"[warn] batch {i // batch} download failed: {e}", file=sys.stderr)
            continue

        if isinstance(df.columns, pd.MultiIndex):
            for sym in chunk:
                if sym in df.columns.get_level_values(0):
                    s = df[sym].get("Close")
                    if s is not None and len(s.dropna()) > 0:
                        out[sym] = s.dropna()
        else:
            s = df.get("Close")
            if s is not None and len(s.dropna()) > 0:
                out[chunk[0]] = s.dropna()

        time.sleep(0.4)  # be polite to Yahoo
    return out


# ---------------------------------------------------------------------------
# Fundamentals (per ticker)
# ---------------------------------------------------------------------------

@dataclass
class Fundamentals:
    symbol: str
    pb: float
    ev_ebitda: float
    rev_growth: float           # most recent yoy revenue growth (annual)
    rev_growth_prev: float      # prior yoy revenue growth (annual)
    rev_growth_inflection: float  # rev_growth - rev_growth_prev (acceleration)
    name: str
    sector: str
    market_cap: float


def _safe(v) -> float:
    try:
        if v is None:
            return float("nan")
        f = float(v)
        return f if math.isfinite(f) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _annual_revenues(tk) -> pd.Series:
    """Try a few yfinance entry points for an annual revenue series (most recent first)."""
    for attr in ("income_stmt", "financials"):
        try:
            df = getattr(tk, attr)
            if df is not None and not df.empty:
                for key in ("Total Revenue", "TotalRevenue", "Revenue"):
                    if key in df.index:
                        s = df.loc[key].dropna().astype(float)
                        # yfinance columns are dates with most-recent-first; sort to be safe.
                        s.index = pd.to_datetime(s.index, errors="coerce")
                        s = s.dropna().sort_index(ascending=False)
                        if len(s) >= 2:
                            return s
        except Exception:  # noqa: BLE001
            continue
    return pd.Series(dtype=float)


def fetch_fundamentals(symbol: str) -> Fundamentals | None:
    import yfinance as yf

    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}
    except Exception:  # noqa: BLE001
        return None

    pb = _safe(info.get("priceToBook"))
    ev_ebitda = _safe(info.get("enterpriseToEbitda"))
    rev_growth_info = _safe(info.get("revenueGrowth"))  # trailing yoy from yfinance
    name = str(info.get("longName") or info.get("shortName") or symbol)
    sector = str(info.get("sector") or "")
    mcap = _safe(info.get("marketCap"))

    rev = _annual_revenues(tk)
    rev_growth = float("nan")
    rev_growth_prev = float("nan")
    if len(rev) >= 3:
        r0, r1, r2 = rev.iloc[0], rev.iloc[1], rev.iloc[2]
        if r1 and r2 and r1 > 0 and r2 > 0:
            rev_growth = (r0 / r1) - 1.0
            rev_growth_prev = (r1 / r2) - 1.0
    elif len(rev) == 2:
        r0, r1 = rev.iloc[0], rev.iloc[1]
        if r1 and r1 > 0:
            rev_growth = (r0 / r1) - 1.0

    # Prefer computed annual growth; fall back to yfinance trailing if unavailable.
    if math.isnan(rev_growth):
        rev_growth = rev_growth_info

    inflection = (
        rev_growth - rev_growth_prev
        if not (math.isnan(rev_growth) or math.isnan(rev_growth_prev))
        else float("nan")
    )

    return Fundamentals(
        symbol=symbol,
        pb=pb,
        ev_ebitda=ev_ebitda,
        rev_growth=rev_growth,
        rev_growth_prev=rev_growth_prev,
        rev_growth_inflection=inflection,
        name=name,
        sector=sector,
        market_cap=mcap,
    )


def fetch_fundamentals_parallel(symbols: Iterable[str], workers: int = 8) -> dict[str, Fundamentals]:
    out: dict[str, Fundamentals] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_fundamentals, s): s for s in symbols}
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                f = fut.result()
            except Exception:  # noqa: BLE001
                f = None
            if f is not None:
                out[s] = f
    return out


# ---------------------------------------------------------------------------
# Filtering + ranking
# ---------------------------------------------------------------------------

def filter_fip_candidates(
    fips: list[FIPResult],
    daily_fip_max: float = -0.05,
    require_winner: bool = True,
) -> list[FIPResult]:
    """Daily FIP low (frog), weekly FIP higher than daily (less smooth on weekly),
    weekly FIP inflecting down (becoming smoother)."""
    out = []
    for f in fips:
        if any(map(math.isnan, (f.fip_d, f.fip_w, f.fip_w_inflection, f.pret_d))):
            continue
        if require_winner and f.pret_d <= 0:
            continue
        if f.fip_d > daily_fip_max:
            continue
        if f.fip_w <= f.fip_d:           # weekly should be LESS frog-like than daily
            continue
        if f.fip_w_inflection >= 0:      # weekly must be moving toward smoother
            continue
        out.append(f)
    return out


def _rank(series: pd.Series, ascending: bool) -> pd.Series:
    """Percentile rank in [0, 1]; NaNs get the worst rank (0)."""
    r = series.rank(ascending=ascending, pct=True, na_option="bottom")
    return r.fillna(0.0)


def build_screen_table(
    fips: list[FIPResult],
    funds: dict[str, Fundamentals],
    universe: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    weights = weights or {
        "pb": 0.20,
        "ev_ebitda": 0.25,
        "rev_growth": 0.25,
        "rev_inflection": 0.20,
        "fip_d": 0.10,  # tiebreaker: smoother daily FIP is better
    }

    rows = []
    for f in fips:
        fu = funds.get(f.symbol)
        if fu is None:
            continue
        meta = universe.loc[f.symbol] if f.symbol in universe.index else None
        rows.append({
            "symbol": f.symbol,
            "name": fu.name,
            "sector": fu.sector or (meta["sector"] if meta is not None and "sector" in meta else ""),
            "country": meta["country"] if meta is not None and "country" in meta else "",
            "market_cap_bucket": meta["market_cap"] if meta is not None and "market_cap" in meta else "",
            "market_cap": fu.market_cap,
            "last_price": f.last_price,
            "pret_d": f.pret_d,
            "fip_d": f.fip_d,
            "pret_w": f.pret_w,
            "fip_w": f.fip_w,
            "fip_w_prev": f.fip_w_prev,
            "fip_w_inflection": f.fip_w_inflection,
            "pb": fu.pb,
            "ev_ebitda": fu.ev_ebitda,
            "rev_growth": fu.rev_growth,
            "rev_growth_prev": fu.rev_growth_prev,
            "rev_growth_inflection": fu.rev_growth_inflection,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Guard: P/B and EV/EBITDA should be positive to be meaningful as "low is good".
    pb_clean = df["pb"].where(df["pb"] > 0)
    ev_clean = df["ev_ebitda"].where(df["ev_ebitda"] > 0)

    rank_pb = _rank(pb_clean, ascending=True)            # lower P/B → higher rank
    rank_ev = _rank(ev_clean, ascending=True)            # lower EV/EBITDA → higher rank
    rank_g = _rank(df["rev_growth"], ascending=False)    # higher growth → higher rank
    rank_inf = _rank(df["rev_growth_inflection"], ascending=False)
    rank_fip = _rank(df["fip_d"], ascending=True)        # lower FIP → higher rank

    df["score"] = (
        weights["pb"] * rank_pb
        + weights["ev_ebitda"] * rank_ev
        + weights["rev_growth"] * rank_g
        + weights["rev_inflection"] * rank_inf
        + weights["fip_d"] * rank_fip
    )

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="frog_in_pan_screen.csv", help="Output CSV path.")
    ap.add_argument("--limit", type=int, default=0, help="Cap universe size for a quick run (0 = no cap).")
    ap.add_argument("--daily-fip-max", type=float, default=-0.05,
                    help="Daily FIP must be <= this to qualify (lower = smoother).")
    ap.add_argument("--top", type=int, default=50, help="Print top-N rows to stdout.")
    args = ap.parse_args()

    print("Loading universe (financedatabase, EU + UK, small & mid cap) ...")
    universe = load_universe()
    print(f"  universe size: {len(universe)}")
    symbols = list(universe.index.astype(str))
    if args.limit:
        symbols = symbols[: args.limit]
        universe = universe.loc[symbols]
        print(f"  capped to {len(symbols)} for this run")

    print("Downloading 2y daily prices ...")
    prices = download_prices(symbols)
    print(f"  got prices for {len(prices)}/{len(symbols)} symbols")

    print("Computing FIP scores (daily + weekly + weekly inflection) ...")
    fips: list[FIPResult] = []
    for sym, s in prices.items():
        try:
            r = compute_fip(sym, s)
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            fips.append(r)
    print(f"  FIP computed for {len(fips)} symbols")

    candidates = filter_fip_candidates(fips, daily_fip_max=args.daily_fip_max)
    print(f"  passed FIP filter: {len(candidates)}")

    if not candidates:
        print("No FIP candidates passed the filter. Try loosening --daily-fip-max.")
        return 1

    print("Fetching fundamentals (P/B, EV/EBITDA, revenue growth) ...")
    funds = fetch_fundamentals_parallel([c.symbol for c in candidates])
    print(f"  fundamentals for {len(funds)} candidates")

    table = build_screen_table(candidates, funds, universe)
    if table.empty:
        print("No rows after merging fundamentals.")
        return 1

    table.to_csv(args.out, index=False)
    print(f"\nWrote {len(table)} rows to {args.out}")

    show_cols = [
        "symbol", "name", "country", "market_cap_bucket", "sector",
        "pret_d", "fip_d", "fip_w", "fip_w_inflection",
        "pb", "ev_ebitda", "rev_growth", "rev_growth_inflection", "score",
    ]
    with pd.option_context("display.max_rows", args.top, "display.width", 200, "display.max_colwidth", 32):
        print("\nTop candidates:\n")
        print(table[show_cols].head(args.top).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
