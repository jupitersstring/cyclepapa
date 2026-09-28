"""Clean daily panel of the FMP crypto universe.

FMP crypto bars report `volume` in USD (BTC ~ $30bn/day), so volume is used
directly as dollar volume. Every coin trades every calendar day; gaps are left
as missing rather than filled.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import CACHE_DIR

PANEL_DIR = CACHE_DIR / "panel"
FIELDS = ["open", "high", "low", "close", "volume"]

# Assets that cannot re-rate by construction: fiat/commodity pegs, wrapped or
# liquid-staking claims on another coin. Caught by behaviour below; the name
# list only backs that up for thinly traded wrappers.
PEG_NAME = re.compile(
    r"(?:^|\b)(?:wrapped|staked|liquid staking|bridged|restaked|tether|usd coin|stablecoin|"
    r"pax gold|tether gold|binance-peg)(?:\b|$)", re.I)
PEG_SYMBOL = re.compile(r"^(?:W|ST|WST|R|CB|M|B|J|SO|EZ|WE|RS|LS|OS|SFRX|FRX|SAVAX|ANKR)?"
                        r"(?:BTC|ETH|SOL|BNB|AVAX|MATIC|POL|FTM|TRX|TON|ADA|DOT|NEAR|KAVA|CRO|HT|OKT)$")


def load_raw(min_date: str = "2014-01-01") -> dict[str, pd.DataFrame]:
    """Wide date x symbol matrices of the raw FMP bars."""
    frames = {f: {} for f in FIELDS}
    for p in sorted((CACHE_DIR / "fmp_eod").glob("*.parquet")):
        d = pd.read_parquet(p)
        d = d[d["date"] >= min_date]
        if d.empty:
            continue
        d = d.set_index("date")
        for f in FIELDS:
            frames[f][p.stem] = d[f]
    idx = pd.date_range(min_date, max(s.index.max() for s in frames["close"].values()), freq="D")
    return {f: pd.DataFrame(frames[f]).reindex(idx).astype("float64") for f in FIELDS}


# tokens backed by a commodity (they track bullion, not crypto demand)
COMMODITY_BACKED = {"KAGUSD", "KAUUSD", "CGOUSD", "DGXUSD", "PMGTUSD", "CGTUSD", "TMTGUSD", "DSLVUSD", "XAUTUSD",
                    "PAXGUSD", "AWGUSD"}

SPLICE_UP = np.log(5.0)      # persistent jump treated as a listing placeholder / redenomination / ticker reuse
SPIKE = np.log(2.5)          # flip-flop threshold
STALE_RUN = 7                # identical closes in a row = frozen / placeholder quote


def _nanmedian_rows(w: np.ndarray) -> np.ndarray:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(w, axis=1)


def _clean_close(x: np.ndarray, vol: np.ndarray | None = None) -> tuple[np.ndarray, int]:
    """Clean one close series (calendar-daily, NaN = no quote). Returns the
    cleaned series and the number of flip-flop days found."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    lx = np.log(np.where(x > 0, x, np.nan))
    nan = np.nan

    # 1. frozen quotes: runs of >= 7 identical closes carry no trading information
    idx = np.where(~np.isnan(lx))[0]
    if len(idx) < 10:
        return np.full_like(lx, nan), 0
    v = lx[idx]
    run_id = np.cumsum(np.r_[True, v[1:] != v[:-1]])
    stale = np.bincount(run_id)[run_id] >= STALE_RUN
    lx[idx[stale]] = nan

    # 2. placeholder / ticker-reuse splice: a >5x rise against the last valid quote
    #    (however long the gap) whose new level holds -> drop all earlier history
    idx = np.where(~np.isnan(lx))[0]
    if len(idx) < 10:
        return np.full_like(lx, nan), 0
    v = lx[idx]
    step = np.r_[0.0, np.diff(v)]
    pad = np.r_[np.full(5, nan), v, np.full(5, nan)]
    w = swv(pad, 5)
    prev_med = _nanmedian_rows(w[:len(v)])          # v[k-5..k-1]
    next_med = _nanmedian_rows(w[5:5 + len(v)])     # v[k..k+4]
    splice = (step > SPLICE_UP) & (next_med - prev_med > np.log(4.0))
    if splice.any():
        lx[: idx[np.where(splice)[0][-1]]] = nan

    # 2b. placeholder above the launch price: a >20x fall whose new level holds,
    #     where the quotes before it traded under 1% of the volume after it
    if vol is not None:
        idx = np.where(~np.isnan(lx))[0]
        if len(idx) >= 10:
            v = lx[idx]
            step = np.r_[0.0, np.diff(v)]
            pad = np.r_[np.full(5, nan), v, np.full(5, nan)]
            w = swv(pad, 5)
            drop = (step < -np.log(20.0)) & (_nanmedian_rows(w[5:5 + len(v)]) - _nanmedian_rows(w[:len(v)]) < -np.log(15.0))
            for k in np.where(drop)[0][::-1]:
                d = idx[k]
                vb = np.nan_to_num(vol[max(d - 30, 0): d])
                va = np.nan_to_num(vol[d: d + 30])
                mb = np.median(vb) if len(vb) else 0.0
                ma = np.median(va) if len(va) else 0.0
                if mb < 0.01 * ma:
                    lx[:d] = nan
                    break

    # 3. isolated bad prints: > 3x from the centred median of 7 quotes while the
    #    quotes either side agree within 2.5x
    for _ in range(3):
        idx = np.where(~np.isnan(lx))[0]
        if len(idx) < 7:
            break
        v = lx[idx]
        med = _nanmedian_rows(swv(np.r_[np.full(3, nan), v, np.full(3, nan)], 7))
        before = _nanmedian_rows(swv(np.r_[np.full(3, nan), v], 3)[: len(v)])
        after = _nanmedian_rows(swv(np.r_[v[1:], np.full(3, nan)], 3)[: len(v)])
        bad = (np.abs(v - med) > np.log(3.0)) & (np.abs(before - after) < np.log(2.5))
        if not bad.any():
            break
        lx[idx[bad]] = nan

    # 4. flip-flops: a >2.5x move undone within five quotes -> mask +/-10 days
    idx = np.where(~np.isnan(lx))[0]
    v = lx[idx]
    step = np.r_[0.0, np.diff(v)]
    base = np.r_[nan, v[:-1]]
    undone = np.zeros(len(v), bool)
    for k in range(1, 6):
        fut = np.full(len(v), nan)
        fut[: max(len(v) - k, 0)] = v[k:]
        undone |= np.abs(fut - base) < np.log(1.5)
    wild = (np.abs(step) > SPIKE) & undone
    for d in idx[wild]:
        lx[max(d - 10, 0): d + 11] = nan
    return np.exp(lx), int(wild.sum())


def clean(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Remove frozen quotes, pre-listing placeholders / ticker reuse, bad prints
    and flip-flop segments, coin by coin.

    Aggregated crypto feeds carry IOU or pre-launch prices (OP at $0.0005, APT at
    $0.004), splice a migrated or re-used ticker onto an old history (LEND ->
    AAVE at 100:1; KUJI and AXL jump 700-1,100x out of frozen quotes) and leave
    isolated bad prints. Each would otherwise manufacture a multibagger.
    """
    cr = raw["close"]
    arr = cr.to_numpy(dtype=float)
    varr = raw["volume"].reindex(columns=cr.columns).to_numpy(dtype=float)
    out_c = np.empty_like(arr)
    flips = {}
    for j, sym in enumerate(cr.columns):
        out_c[:, j], flips[sym] = _clean_close(arr[:, j], varr[:, j])
    c = pd.DataFrame(out_c, index=cr.index, columns=cr.columns)
    c.attrs["n_flipflop"] = flips

    out = {"close": c}
    for f in ("open", "high", "low"):
        x = raw[f].where(raw[f] > 0).where(c.notna())
        out[f] = x
    # repair high/low that exclude the close (common in aggregated crypto bars)
    out["high"] = np.fmax(out["high"], np.fmax(out["open"], c))
    out["low"] = np.fmin(out["low"], np.fmin(out["open"], c))
    v = raw["volume"].where(c.notna())
    out["volume"] = v.where(v >= 0)
    return out


def classify_assets(p: dict[str, pd.DataFrame], names: pd.Series) -> pd.DataFrame:
    """One row per symbol with an exclusion reason ('' if eligible)."""
    c, v = p["close"], p["volume"]
    r = np.log(c).diff()
    n_obs = c.notna().sum()
    med_dv = v.where(v > 0).median()
    zero_share = (v.fillna(0) <= 0).where(c.notna()).mean()
    ann_vol = r.std() * np.sqrt(365)
    near_one = ((c > 0.97) & (c < 1.03)).where(c.notna()).mean()

    n_wild = pd.Series(c.attrs.get("n_flipflop", {}), dtype=float).reindex(c.columns).fillna(0)

    reason = pd.Series("", index=c.columns, dtype=object)
    reason[n_obs < 150] = "short history"
    reason[(reason == "") & (n_wild > 6)] = "corrupt series"
    reason[(reason == "") & c.columns.isin(list(COMMODITY_BACKED))] = "commodity-backed"
    reason[(reason == "") & (near_one > 0.8)] = "stablecoin"
    reason[(reason == "") & (ann_vol < 0.15)] = "pegged / low volatility"
    nm = names.reindex(c.columns).fillna("").str.replace(r"\s+USD$", "", regex=True)
    base = pd.Series(c.columns.str.replace(r"USD$", "", regex=True), index=c.columns)
    reason[(reason == "") & nm.str.contains(PEG_NAME)] = "wrapped / staked claim"
    reason[(reason == "") & base.str.match(PEG_SYMBOL) & ~base.isin(
        ["BTC", "ETH", "SOL", "BNB", "AVAX", "MATIC", "POL", "FTM", "TRX", "TON", "ADA", "DOT", "NEAR",
         "KAVA", "CRO", "HT", "OKT", "MBTC"])] = "wrapped / staked claim"

    # behavioural peg check against liquid majors: near-identical returns and a stable price ratio
    majors = [s for s in ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "AVAXUSD", "MATICUSD", "FTMUSD",
                          "TRXUSD", "TONUSD", "ADAUSD", "DOTUSD", "NEARUSD"] if s in c.columns]
    cand = reason[reason == ""].index.difference(majors)
    for m in majors:
        rc = r[cand].corrwith(r[m], min_periods=90)
        ratio_sd = np.log(c[cand].div(c[m], axis=0)).std()
        pegged = rc.index[((rc > 0.97) & (ratio_sd < 0.15)) | (ratio_sd < 0.05)]
        reason[pegged] = f"pegged to {m[:-3]}"

    # duplicates: same normalised name -> keep the most traded listing
    key = nm.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    tot_dv = v.sum()
    for k, grp in key[reason == ""].groupby(key[reason == ""]):
        if len(grp) > 1 and k:
            keep = tot_dv[grp.index].idxmax()
            for s in grp.index:
                if s != keep:
                    reason[s] = f"duplicate of {keep}"
    return pd.DataFrame({"name": nm, "n_obs": n_obs, "n_wild_days": n_wild,
                         "first": c.apply(pd.Series.first_valid_index),
                         "last": c.apply(pd.Series.last_valid_index), "median_dollar_volume": med_dv,
                         "zero_volume_share": zero_share, "ann_vol": ann_vol, "exclusion": reason})


def market_index(p: dict[str, pd.DataFrame], eligible: list[str], min_dv: float = 1e6,
                 cap: float = 0.2) -> pd.DataFrame:
    """Liquidity-weighted crypto market return (weights: lagged 30-day mean USD
    volume, capped at 20% per coin) and log total USD volume of its members."""
    c, v = p["close"][eligible], p["volume"][eligible]
    r = np.log(c).diff().clip(-0.7, 0.7)
    w = v.rolling(30, min_periods=20).mean().shift(1)
    w = w.where((w >= min_dv) & r.notna())
    w = w.div(w.sum(axis=1), axis=0)
    for _ in range(10):  # iterative capping
        over = w > cap
        if not over.values.any():
            break
        excess = (w - cap).clip(lower=0).sum(axis=1)
        w = w.clip(upper=cap)
        free = w.where(~over & w.notna())
        w = w + free.div(free.sum(axis=1), axis=0).mul(excess, axis=0).fillna(0).where(w.notna())
    mret = (w * r).sum(axis=1, min_count=1)
    mvol = np.log(v.where(w.notna()).sum(axis=1, min_count=1))
    n = w.notna().sum(axis=1)
    return pd.DataFrame({"mret": mret, "mlogvol": mvol, "n_members": n})


def build(min_date: str = "2014-01-01") -> None:
    from .fmp import FMP
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_raw(min_date)
    p = clean(raw)
    names = FMP().crypto_list().set_index("symbol")["name"]
    meta = classify_assets(p, names)
    eligible = meta.index[meta.exclusion == ""].tolist()
    mkt = market_index(p, eligible)
    for f, df in p.items():
        df.to_parquet(PANEL_DIR / f"{f}.parquet")
    meta.to_parquet(PANEL_DIR / "assets.parquet")
    mkt.to_parquet(PANEL_DIR / "market.parquet")
    print(meta.exclusion.replace("", "eligible").str.replace(r" of \w+| to \w+", "", regex=True)
          .value_counts().to_string())


def load() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    p = {f: pd.read_parquet(PANEL_DIR / f"{f}.parquet") for f in FIELDS}
    return p, pd.read_parquet(PANEL_DIR / "assets.parquet"), pd.read_parquet(PANEL_DIR / "market.parquet")


if __name__ == "__main__":
    build()
