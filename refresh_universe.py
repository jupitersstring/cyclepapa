"""
Full-universe data refresh for the asymmetric-v2 ranking.

Rebuilds asymmetric_v2_universe_audit.csv from scratch with TODAY's data:
  1. Union all leading_*.csv universes -> unique tickers + meta
  2. Download fresh OHLC (3y) for every ticker + SPX benchmark
  3. compute_fip (price FIP, d/w/m) + compute_qulla (RS-FIP, volasym) per ticker
  4. Pre-filter: smooth FIP winner with real liquidity
  5. Fetch fresh fundamentals for every pre-filter survivor
  6. Apply v2 gates (multi-metric floor / catalyst / survival)
  7. Rank with the NaN-neutral policy and write the audit CSV

Output schema matches the previous audit CSV so build_workbook.py runs
unchanged.
"""
from __future__ import annotations

import math
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
import frog_in_pan_screener as scr  # noqa: E402

REPO = "/home/user/cyclepapa"
OUT = f"{REPO}/asymmetric_v2_universe_audit.csv"
LEADING = [
    "leading_dev_lm.csv", "leading_us_small.csv", "leading_us_micro.csv",
    "leading_global_lm.csv", "leading_em_expand.csv",
    "leading_full_global_lm.csv", "leading_em_expand2.csv",
]

# ---------------------------------------------------------------- universe
frames = []
for f in LEADING:
    df = pd.read_csv(f"{REPO}/{f}")
    keep = [c for c in ("symbol", "name", "country", "market_cap_bucket", "sector")
            if c in df.columns]
    frames.append(df[keep])
uni = pd.concat(frames).drop_duplicates(subset="symbol", keep="first")
# Drop preferred-share style tickers (same filter as the prior audit).
uni = uni[~uni["symbol"].astype(str).str.contains(r"-P[A-Z]?$", regex=True)]
uni = uni.set_index("symbol")
symbols = list(uni.index.astype(str))
print(f"[1] universe: {len(symbols)} unique tickers "
      f"({uni['country'].nunique()} countries)", flush=True)

# ------------------------------------------------------------------- OHLC
print("[2] downloading fresh 3y OHLC ...", flush=True)
t0 = time.time()
ohlc_map = scr.download_ohlc(symbols, period="3y", batch=25, sleep_between=1.0,
                             use_cache=True)
print(f"    got OHLC for {len(ohlc_map)}/{len(symbols)} "
      f"({(time.time()-t0)/60:.1f} min)", flush=True)

spx = scr.fetch_spx_close(period="3y")
print(f"    SPX bars: {len(spx)} (last {spx.index[-1].date() if len(spx) else 'n/a'})",
      flush=True)

# ------------------------------------------------- FIP + qulla per ticker
print("[3] computing FIP + qulla metrics ...", flush=True)
rows = {}
n_fip_fail = n_qulla_fail = 0
for sym, frame in ohlc_map.items():
    close = frame["Close"].dropna() if "Close" in frame else pd.Series(dtype=float)
    try:
        fip = scr.compute_fip(sym, close)
    except Exception:
        fip = None
    if fip is None:
        n_fip_fail += 1
        continue
    try:
        q = scr.compute_qulla(sym, frame, spx)
    except Exception:
        q = None
    if q is None:
        n_qulla_fail += 1

    ret = close.pct_change().dropna()
    tail = ret.iloc[-252:]
    nonzero_pct = float((tail != 0).mean()) if len(tail) else float("nan")
    vol60 = float(ret.iloc[-60:].std()) if len(ret) >= 60 else float("nan")

    rows[sym] = {
        "symbol": sym,
        "pret_d": fip.pret_d, "fip_d": fip.fip_d,
        "fip_w": fip.fip_w, "fip_m": fip.fip_m, "pret_m": fip.pret_m,
        "nonzero_pct": nonzero_pct, "realized_vol_60d": vol60,
        "last_price": fip.last_price,
        "rs_pret_d": q.rs_pret_d if q else float("nan"),
        "rs_fip_d": q.rs_fip_d if q else float("nan"),
        "rs_fip_w": q.rs_fip_w if q else float("nan"),
        "rs_fip_w_inflection": q.rs_fip_w_inflection if q else float("nan"),
        "fip_w_minus_d": (q.rs_fip_w - q.rs_fip_d) if q else float("nan"),
        "asym_d_last": q.asym_d_last if q else float("nan"),
        "asym_w_last": q.asym_w_last if q else float("nan"),
        "asym_w_ma_last": q.asym_w_ma_last if q else float("nan"),
        "asym_w_above_ma": q.asym_w_above_ma if q else float("nan"),
        "asym_w_roc5": q.asym_w_roc5 if q else float("nan"),
        "asym_m_last": q.asym_m_last if q else float("nan"),
        "asym_m_ma_last": q.asym_m_ma_last if q else float("nan"),
        "asym_m_above_ma": q.asym_m_above_ma if q else float("nan"),
        "asym_m_roc3": q.asym_m_roc3 if q else float("nan"),
        "asym_m_dist50": abs(q.asym_m_last - 50.0) if q else float("nan"),
        "va_fip_d": q.va_fip_d if q else float("nan"),
    }
print(f"    FIP ok for {len(rows)}; fip-fail {n_fip_fail}; qulla-fail {n_qulla_fail}",
      flush=True)

tech = pd.DataFrame.from_dict(rows, orient="index")

# -------------------------------------------------------------- pre-filter
pre = tech[
    (tech["fip_d"] <= -0.08)
    & (tech["fip_w"] <= -0.10)
    & (tech["pret_d"] > 0)
    & (tech["nonzero_pct"] >= 0.65)
    & (tech["realized_vol_60d"] >= 0.008)
    & (tech["last_price"] >= 1.0)
].copy()
print(f"[4] pre-filter survivors: {len(pre)}", flush=True)

# ------------------------------------------------------------ fundamentals
print(f"[5] fetching fresh fundamentals for {len(pre)} survivors ...", flush=True)


def fetch_extended(symbol: str) -> dict | None:
    import random

    import yfinance as yf
    from yfinance.exceptions import YFRateLimitError

    info, tk = {}, None
    for attempt in range(4):
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            break
        except YFRateLimitError:
            time.sleep(20 * (2 ** attempt) + random.uniform(0, 5))
        except Exception as e:  # noqa: BLE001
            if attempt < 3:
                time.sleep(2 * (2 ** attempt))
                continue
            print(f"    [warn] {symbol}: {type(e).__name__}: {e}", file=sys.stderr)
            return None
    if tk is None or not info:
        return None
    meaningful = ("trailingPE", "marketCap", "enterpriseValue",
                  "totalRevenue", "priceToBook", "revenueGrowth")
    if not any(info.get(k) is not None for k in meaningful):
        return None

    _safe = scr._safe
    rev = scr._annual_revenues(tk)
    rev_growth = rev_growth_prev = float("nan")
    if len(rev) >= 3:
        r0, r1, r2 = rev.iloc[0], rev.iloc[1], rev.iloc[2]
        if r1 and r2 and r1 > 0 and r2 > 0:
            rev_growth = (r0 / r1) - 1.0
            rev_growth_prev = (r1 / r2) - 1.0
    elif len(rev) == 2:
        r0, r1 = rev.iloc[0], rev.iloc[1]
        if r1 and r1 > 0:
            rev_growth = (r0 / r1) - 1.0
    if math.isnan(rev_growth):
        rev_growth = _safe(info.get("revenueGrowth"))
    inflection = (
        rev_growth - rev_growth_prev
        if not (math.isnan(rev_growth) or math.isnan(rev_growth_prev))
        else float("nan")
    )
    mcap = _safe(info.get("marketCap"))
    fcf = _safe(info.get("freeCashflow"))
    return {
        "name": str(info.get("longName") or info.get("shortName") or symbol),
        "sector_ex": str(info.get("sector") or ""),
        "mkt_cap_ex": mcap,
        "pb_fresh": _safe(info.get("priceToBook")),
        "ev_ebitda_fresh": _safe(info.get("enterpriseToEbitda")),
        "ev_sales": _safe(info.get("enterpriseToRevenue")),
        "fcf": fcf,
        "fcf_yield": (fcf / mcap) if (mcap and not math.isnan(mcap)
                                      and not math.isnan(fcf) and mcap > 0)
                     else float("nan"),
        "op_margin_ex": _safe(info.get("operatingMargins")),
        "roe_ex": _safe(info.get("returnOnEquity")),
        "debt_to_equity": _safe(info.get("debtToEquity")),
        "eps_q_growth": _safe(info.get("earningsQuarterlyGrowth")),
        "rev_growth_fresh": rev_growth,
        "rev_growth_inflection": inflection,
    }


from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402

funda: dict[str, dict] = {}
syms_pre = list(pre.index.astype(str))
with ThreadPoolExecutor(max_workers=2) as pool:
    futs = {pool.submit(fetch_extended, s): s for s in syms_pre}
    for n, fut in enumerate(as_completed(futs), start=1):
        s = futs[fut]
        try:
            r = fut.result()
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            funda[s] = r
        if n % 25 == 0:
            print(f"    {n}/{len(syms_pre)} ({len(funda)} ok)", flush=True)
print(f"    fundamentals ok for {len(funda)}/{len(syms_pre)}", flush=True)

fdf = pd.DataFrame.from_dict(funda, orient="index")
df = pre.join(fdf, how="inner")

# Meta from the universe CSVs (bucket / country as scanned).
df = df.join(uni[["country", "market_cap_bucket", "sector"]], how="left")
df["name"] = df["name"].fillna(df.index.to_series())
df["sector_used"] = df["sector_ex"].replace("", np.nan).fillna(df["sector"])

# -------------------------------------------------------------- v2 gates
pb = df["pb_fresh"]
ev = df["ev_ebitda_fresh"]
evs = df["ev_sales"]
fcfy = df["fcf_yield"]
floor_ok = (pb <= 2.0) | (ev <= 12.0) | (evs <= 3.0) | (fcfy >= 0.03)
catalyst_ok = (
    (df["rev_growth_fresh"] >= 0.05)
    & (df["rev_growth_inflection"] >= 0)
    & ((df["op_margin_ex"] >= 0.05) | (df["eps_q_growth"] >= 0))
)
survival_ok = (df["debt_to_equity"] <= 250) | df["debt_to_equity"].isna()
df = df[floor_ok & catalyst_ok & survival_ok].copy()
print(f"[6] v2 survivors after fresh gates: {len(df)}", flush=True)
if df.empty:
    print("No survivors — aborting before overwrite.", flush=True)
    sys.exit(1)

# --------------------------------------------------- scoring (NaN-neutral)
df["pb_use"] = df["pb_fresh"]
df["ev_ebitda_use"] = df["ev_ebitda_fresh"]
df["rev_growth_use"] = df["rev_growth_fresh"]
df["roic_proxy"] = df["op_margin_ex"] * (1.0 / df["ev_sales"])
sec_med = df.groupby("sector_used")["ev_ebitda_use"].transform("median")
df["sec_ev_med"] = sec_med
df["sec_rel_ev"] = df["ev_ebitda_use"] / sec_med


def rank(s: pd.Series, lower: bool = False) -> pd.Series:
    r = s.rank(ascending=not lower, pct=True, na_option="keep")
    return r.fillna(0.5)  # neutral for missing data


df["upside"] = (rank(df["rev_growth_use"]) + rank(df["rev_growth_inflection"])) / 2
df["floor"] = (rank(df["pb_use"], lower=True) + rank(df["ev_ebitda_use"], lower=True)
               + rank(df["ev_sales"], lower=True) + rank(df["fcf_yield"])
               + rank(df["sec_rel_ev"], lower=True)) / 5
df["quality"] = rank(df["roic_proxy"])
df["stealth"] = rank(df["fip_d"] + df["fip_w"], lower=True)
df["asym_v2_score"] = (np.sqrt(df["upside"] * df["floor"])
                       * (0.7 + 0.3 * df["quality"])
                       * (0.8 + 0.2 * df["stealth"]))

# Legacy-schema columns so build_workbook.py runs unchanged.
df["market_cap"] = df["mkt_cap_ex"]
df["last_price_old"] = df["last_price"]
df["pb"] = df["pb_fresh"]
df["ev_ebitda"] = df["ev_ebitda_fresh"]
df["rev_growth"] = df["rev_growth_fresh"]
df["score"] = np.nan

df = df.sort_values("asym_v2_score", ascending=False)
df.index.name = "symbol"
df = df.reset_index()

cols = ["symbol", "name", "country", "market_cap_bucket", "sector", "market_cap",
        "last_price_old", "rs_pret_d", "rs_fip_d", "rs_fip_w",
        "rs_fip_w_inflection", "fip_w_minus_d", "asym_d_last", "asym_w_last",
        "asym_w_ma_last", "asym_w_above_ma", "asym_w_roc5", "asym_m_last",
        "asym_m_ma_last", "asym_m_above_ma", "asym_m_roc3", "asym_m_dist50",
        "va_fip_d", "pb", "ev_ebitda", "rev_growth", "rev_growth_inflection",
        "score", "pret_d", "pret_m", "fip_d", "fip_w", "fip_m", "nonzero_pct",
        "realized_vol_60d", "last_price", "pb_fresh", "ev_ebitda_fresh",
        "rev_growth_fresh", "ev_sales", "fcf", "mkt_cap_ex", "debt_to_equity",
        "op_margin_ex", "roe_ex", "eps_q_growth", "sector_ex", "pb_use",
        "ev_ebitda_use", "rev_growth_use", "fcf_yield", "roic_proxy",
        "sector_used", "sec_ev_med", "sec_rel_ev", "upside", "floor",
        "quality", "stealth", "asym_v2_score"]
df[cols].to_csv(OUT, index=False)
print(f"[7] wrote {len(df)} survivors to {OUT}", flush=True)

print("\n=== TOP 25 (fresh data, NaN-neutral scoring) ===", flush=True)
show = ["symbol", "name", "country", "market_cap_bucket", "sector_used",
        "pret_d", "fip_d", "fip_w", "rev_growth_use", "pb_use",
        "ev_ebitda_use", "fcf_yield", "asym_v2_score"]
with pd.option_context("display.width", 250, "display.max_colwidth", 34):
    print(df[show].head(25).round(3).to_string(index=False), flush=True)
