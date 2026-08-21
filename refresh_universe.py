"""
Full-universe data refresh for the asymmetric-v2 ranking.

Universe = union of
  (a) every ticker from the prior leading_* scans (large/mid focus), and
  (b) the FULL financedatabase Small Cap + Micro Cap universe for the same
      44 countries (primary listings only) — added on request so small and
      micro caps are scanned globally, not just in the US.

Pipeline (all data fetched fresh via yahoo_fetch — plain-requests client,
since yfinance's curl transport is blocked by this environment's proxy):
  1. Build the universe
  2. Fetch 3y OHLC per ticker (checkpointed to .ohlc_cache.pkl, resumable)
  3. compute_fip + compute_qulla per ticker
  4. Pre-filter: smooth-FIP winner with real liquidity
  5. Fetch fundamentals for every pre-filter survivor
  6. v2 gates (multi-metric floor / catalyst / survival)
  7. NaN-neutral ranking -> asymmetric_v2_universe_audit.csv
"""
from __future__ import annotations

import math
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
import frog_in_pan_screener as scr  # noqa: E402
from yahoo_fetch import YahooClient, wait_until_clear  # noqa: E402

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
lead = pd.concat(frames).drop_duplicates(subset="symbol", keep="first")
lead = lead[~lead["symbol"].astype(str).str.contains(r"-P[A-Z]?$", regex=True)]
lead = lead.set_index("symbol")
countries = sorted(lead["country"].dropna().unique())
print(f"[1] leading universe: {len(lead)} tickers, {len(countries)} countries",
      flush=True)

print("    pulling FD Small+Micro caps for the same countries ...", flush=True)
fd_small = scr.load_universe(
    min_n=0, primary_only=True, countries=countries,
    market_caps=["Small Cap", "Micro Cap"],
)
fd_small = fd_small[~fd_small.index.astype(str).str.contains(r"-P[A-Z]?$", regex=True)]
fd_meta = pd.DataFrame({
    "name": fd_small.get("name"),
    "country": fd_small.get("country"),
    "market_cap_bucket": fd_small.get("market_cap"),
    "sector": fd_small.get("sector"),
}, index=fd_small.index)
fd_meta.index.name = "symbol"
print(f"    FD small+micro (primary-only): {len(fd_meta)}", flush=True)

uni = pd.concat([lead, fd_meta[~fd_meta.index.isin(lead.index)]])
uni = uni[~uni.index.duplicated(keep="first")]
symbols = list(uni.index.astype(str))
print(f"    combined universe: {len(symbols)} tickers", flush=True)

# ------------------------------------------------------------------- OHLC
client = YahooClient(min_interval=0.30)
print("[2] cooling down until Yahoo accepts requests ...", flush=True)
if not wait_until_clear(client):
    print("Yahoo still rate-limiting after 30 min — aborting.", flush=True)
    sys.exit(1)

print("    downloading fresh 3y OHLC (checkpointed) ...", flush=True)
t0 = time.time()
cache = scr._load_ohlc_cache()
todo = [s for s in symbols if s not in cache or scr._is_stale(cache.get(s))]
print(f"    cache holds {len(cache)}; fetching {len(todo)}", flush=True)

from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402

n_ok = n_fail = 0
lock_save = 0
with ThreadPoolExecutor(max_workers=4) as pool:
    futs = {pool.submit(client.get_ohlc, s, "3y"): s for s in todo}
    for n, fut in enumerate(as_completed(futs), start=1):
        s = futs[fut]
        try:
            frame = fut.result()
        except Exception:  # noqa: BLE001
            frame = None
        if frame is not None and len(frame) > 60:
            cache[s] = frame
            n_ok += 1
        else:
            n_fail += 1
        if n % 500 == 0:
            scr._save_ohlc_cache(cache)
            rate = n / max(1e-9, time.time() - t0)
            eta = (len(todo) - n) / max(rate, 1e-9) / 60
            print(f"    {n}/{len(todo)} fetched ({n_ok} ok, {n_fail} miss) "
                  f"— {rate:.1f}/s, ~{eta:.0f} min left", flush=True)
scr._save_ohlc_cache(cache)
print(f"    OHLC done: {n_ok} new ok, {n_fail} missing "
      f"({(time.time()-t0)/60:.1f} min); cache={len(cache)}", flush=True)

spx = None
spx_df = client.get_ohlc("^GSPC", range_="3y")
if spx_df is not None:
    spx = spx_df["Close"].dropna()
print(f"    SPX bars: {len(spx) if spx is not None else 0}", flush=True)
if spx is None or not len(spx):
    print("No SPX benchmark — aborting.", flush=True)
    sys.exit(1)

# ------------------------------------------------- FIP + qulla per ticker
print("[3] computing FIP + qulla metrics ...", flush=True)
rows = {}
n_fip_fail = n_qulla_fail = 0
have = {s: cache[s] for s in symbols if s in cache}
for sym, frame in have.items():
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
print(f"    FIP ok for {len(rows)}; fip-fail {n_fip_fail}; "
      f"qulla-fail {n_qulla_fail}", flush=True)

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
    raw = client.get_fundamentals(symbol)
    if raw is None:
        return None
    # Stub guard: require at least one meaningful field.
    meaningful = ("market_cap", "pb", "ev_ebitda", "ev_sales", "rev_growth_ttm")
    if not any(raw.get(k) == raw.get(k) and raw.get(k) is not None
               for k in meaningful):
        return None

    revs = raw["annual_revenues"]  # most recent first
    rev_growth = rev_growth_prev = float("nan")
    if len(revs) >= 3:
        r0, r1, r2 = revs[0], revs[1], revs[2]
        if r1 and r2 and r1 > 0 and r2 > 0:
            rev_growth = (r0 / r1) - 1.0
            rev_growth_prev = (r1 / r2) - 1.0
    elif len(revs) == 2:
        r0, r1 = revs[0], revs[1]
        if r1 and r1 > 0:
            rev_growth = (r0 / r1) - 1.0
    if math.isnan(rev_growth):
        rev_growth = raw["rev_growth_ttm"]
    inflection = (
        rev_growth - rev_growth_prev
        if not (math.isnan(rev_growth) or math.isnan(rev_growth_prev))
        else float("nan")
    )
    mcap, fcf = raw["market_cap"], raw["fcf"]
    return {
        "name": raw["name"],
        "sector_ex": raw["sector"],
        "mkt_cap_ex": mcap,
        "pb_fresh": raw["pb"],
        "ev_ebitda_fresh": raw["ev_ebitda"],
        "ev_sales": raw["ev_sales"],
        "fcf": fcf,
        "fcf_yield": (fcf / mcap) if (mcap == mcap and fcf == fcf and mcap > 0)
                     else float("nan"),
        "op_margin_ex": raw["op_margin"],
        "roe_ex": raw["roe"],
        "debt_to_equity": raw["debt_to_equity"],
        "eps_q_growth": raw["eps_q_growth"],
        "rev_growth_fresh": rev_growth,
        "rev_growth_inflection": inflection,
    }


funda: dict[str, dict] = {}
syms_pre = list(pre.index.astype(str))
with ThreadPoolExecutor(max_workers=3) as pool:
    futs = {pool.submit(fetch_extended, s): s for s in syms_pre}
    for n, fut in enumerate(as_completed(futs), start=1):
        s = futs[fut]
        try:
            r = fut.result()
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            funda[s] = r
        if n % 50 == 0:
            print(f"    {n}/{len(syms_pre)} ({len(funda)} ok)", flush=True)
print(f"    fundamentals ok for {len(funda)}/{len(syms_pre)}", flush=True)

fdf = pd.DataFrame.from_dict(funda, orient="index")
df = pre.join(fdf, how="inner")

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

print("\n=== TOP 25 (fresh data, expanded universe, NaN-neutral) ===", flush=True)
show = ["symbol", "name", "country", "market_cap_bucket", "sector_used",
        "pret_d", "fip_d", "fip_w", "rev_growth_use", "pb_use",
        "ev_ebitda_use", "fcf_yield", "asym_v2_score"]
with pd.option_context("display.width", 250, "display.max_colwidth", 34):
    print(df[show].head(25).round(3).to_string(index=False), flush=True)
