"""On-chain enrichment.

Sources
-------
* CoinMetrics community API (no key): network activity per asset: active
  addresses, transactions, transfers, addresses with balance (holder proxy),
  current supply, MVRV, and an estimated market cap for ~840 assets.
* DefiLlama (no key): protocol TVL and fee histories, mapped to tokens.
* Etherscan V2 (key in ETHERSCAN_API_KEY): ERC-20 transfer-level activity
  (daily transfers, unique senders/receivers, first-time receivers) for event
  windows. Etherscan refuses keyless calls, so this layer switches on only
  when the key is present in the environment.

Every source is cached under data/crypto_multibaggers/cache/onchain.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from .config import CACHE_DIR

OC_DIR = CACHE_DIR / "onchain"
CM_BASE = "https://community-api.coinmetrics.io/v4"
LLAMA = "https://api.llama.fi"
ETHERSCAN = "https://api.etherscan.io/v2/api"

CM_METRICS = ["AdrActCnt", "TxCnt", "TxTfrCnt", "AdrBalCnt", "SplyCur", "CapMVRVCur", "CapMrktCurUSD"]
CM_SUFFIX = re.compile(r"_(eth|trx|eos|avaxc|lido|native|omni)$")


def _get(url, params=None, tries=6, timeout=90):
    last = None
    for a in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            last = type(e).__name__
            time.sleep(min(30, 2 ** a))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            time.sleep(min(60, 3 * 2 ** a))
            continue
        return r
    raise RuntimeError(f"GET failed after retries: {last}")


# --------------------------------------------------------------------- CoinMetrics
def cm_catalog() -> list[dict]:
    path = CACHE_DIR / "cm_catalog.json"
    if not path.exists():
        path.write_text(_get(f"{CM_BASE}/catalog-v2/asset-metrics", {"page_size": 10000}).text)
    return json.loads(path.read_text())["data"]


def cm_asset_map(fmp_symbols: set[str]) -> pd.DataFrame:
    """CoinMetrics asset id -> FMP symbol, preferring the native-chain id."""
    rows = []
    for a in cm_catalog():
        ms = {m["metric"] for m in a.get("metrics", []) if any(f.get("frequency") == "1d" for f in m["frequencies"])}
        base = CM_SUFFIX.sub("", a["asset"]).upper()
        if base == "AVAXC":
            base = "AVAX"
        sym = base + "USD"
        if sym not in fmp_symbols:
            continue
        rows.append({"cm_asset": a["asset"], "symbol": sym, "native": a["asset"].upper() == base,
                     "n_onchain": len(ms & set(CM_METRICS)), "has_mcap": "CapMrktEstUSD" in ms})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["symbol", "n_onchain", "native"], ascending=[True, False, False])
    return df.drop_duplicates("symbol")


def cm_fetch(assets: list[str], metrics: list[str], start: str = "2016-01-01") -> pd.DataFrame:
    """Daily asset metrics (long format), paging through next_page_url."""
    params = {"assets": ",".join(assets), "metrics": ",".join(metrics), "frequency": "1d",
              "start_time": start, "page_size": 10000, "ignore_forbidden_errors": "true",
              "ignore_unsupported_errors": "true", "null_as_zero": "false"}
    url, out = f"{CM_BASE}/timeseries/asset-metrics", []
    while url:
        r = _get(url, params)
        if r.status_code != 200:
            raise RuntimeError(f"coinmetrics HTTP {r.status_code}: {r.text[:200]}")
        js = r.json()
        out.extend(js.get("data", []))
        url, params = js.get("next_page_url"), None
        time.sleep(0.7)   # community tier: 10 requests / 6 s
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    for m in metrics:
        if m in df:
            df[m] = pd.to_numeric(df[m], errors="coerce")
    return df.drop(columns=["time"])


def build_coinmetrics(fmp_symbols: set[str]) -> pd.DataFrame:
    OC_DIR.mkdir(parents=True, exist_ok=True)
    amap = cm_asset_map(fmp_symbols)
    amap.to_csv(OC_DIR / "cm_asset_map.csv", index=False)
    frames = []
    oc = amap[amap.n_onchain >= 3].cm_asset.tolist()
    for i in range(0, len(oc), 10):
        frames.append(cm_fetch(oc[i:i + 10], CM_METRICS))
        print(f"  coinmetrics on-chain {min(i + 10, len(oc))}/{len(oc)}", flush=True)
    mc = amap[amap.has_mcap].cm_asset.tolist()
    mframes = []
    for i in range(0, len(mc), 40):
        mframes.append(cm_fetch(mc[i:i + 40], ["CapMrktEstUSD"], start="2018-01-01"))
        print(f"  coinmetrics market cap {min(i + 40, len(mc))}/{len(mc)}", flush=True)
    a = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["asset", "date"])
    b = pd.concat(mframes, ignore_index=True) if mframes else pd.DataFrame(columns=["asset", "date"])
    df = a.merge(b, on=["asset", "date"], how="outer")
    df["symbol"] = df["asset"].map(amap.set_index("cm_asset")["symbol"])
    df.to_parquet(OC_DIR / "coinmetrics.parquet", index=False)
    return df


# --------------------------------------------------------------------- DefiLlama
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def llama_token_map(meta: pd.DataFrame) -> pd.DataFrame:
    """FMP symbol -> DefiLlama gecko_id and protocol slugs.

    A token's TVL is the parent protocol's when one carries the gecko_id
    (Uniswap = v1..v4, Aave = v1..v3), otherwise the sum of the protocols that
    carry it. A match needs the ticker (where DefiLlama lists one) and the
    name or gecko_id to agree, so ticker clashes (HYPE) do not map."""
    path = CACHE_DIR / "llama_lite_protocols2.json"
    if not path.exists():
        path.write_text(_get(f"{LLAMA}/lite/protocols2").text)
    parents = json.loads(path.read_text()).get("parentProtocols", [])
    full = CACHE_DIR / "llama_protocols.json"
    if not full.exists():
        full.write_text(_get(f"{LLAMA}/protocols").text)
    prots = json.loads(full.read_text())
    child_syms: dict[str, set] = {}
    for p in prots:
        if p.get("parentProtocol"):
            child_syms.setdefault(p["parentProtocol"], set()).add(str(p.get("symbol", "")).upper())
    groups: dict[str, dict] = {}
    for pp in parents:
        g = pp.get("gecko_id")
        if g:
            groups[g] = {"slugs": [pp["id"].replace("parent#", "")], "names": [pp["name"]],
                         "symbols": child_syms.get(pp["id"], set()) - {"", "-", "NONE"},
                         "category": pp.get("category")}
    for p in prots:
        g = p.get("gecko_id")
        if g and g not in groups or (g and groups.get(g, {}).get("_child")):
            grp = groups.setdefault(g, {"slugs": [], "names": [], "symbols": set(), "category": p.get("category"),
                                        "_child": True})
            grp["slugs"].append(p.get("slug") or _norm(p["name"]))
            grp["names"].append(p["name"])
            grp["symbols"].add(str(p.get("symbol", "")).upper())
    names = meta["name"].map(_norm)
    tick = pd.Series(meta.index.str.replace(r"USD$", "", regex=True), index=meta.index)
    rows = []
    for gid, grp in groups.items():
        syms = grp["symbols"] - {"", "-", "NONE"}
        cand = tick[tick.isin(syms)].index if syms else tick.index[names == _norm(gid)]
        for s in cand:
            nm = names[s]
            if not nm:
                continue
            ok = nm == _norm(gid) or any(nm == _norm(n) or (len(nm) >= 4 and (nm in _norm(n) or _norm(n) in nm))
                                         for n in grp["names"])
            if ok:
                rows.append({"symbol": s, "gecko_id": gid, "slugs": grp["slugs"], "category": grp["category"]})
                break
    return pd.DataFrame(rows).drop_duplicates("symbol")


def llama_tvl(slug: str) -> pd.Series:
    path = OC_DIR / "llama_tvl" / f"{slug}.json"
    if path.exists():
        js = json.loads(path.read_text())
    else:
        r = _get(f"{LLAMA}/protocol/{slug}")
        if r.status_code != 200:
            return pd.Series(dtype=float)
        js = {"tvl": r.json().get("tvl", [])}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(js))
    t = js.get("tvl") or []
    if not t:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(x["date"], unit="s").normalize(): x.get("totalLiquidityUSD") for x in t}, dtype=float)
    return s[~s.index.duplicated(keep="last")]


def llama_fees(slug: str) -> pd.Series:
    path = OC_DIR / "llama_fees" / f"{slug}.json"
    if path.exists():
        js = json.loads(path.read_text())
    else:
        r = _get(f"{LLAMA}/summary/fees/{slug}", {"dataType": "dailyFees", "excludeTotalDataChartBreakdown": "true"})
        js = {"chart": r.json().get("totalDataChart", []) if r.status_code == 200 else []}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(js))
    ch = js.get("chart") or []
    if not ch:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(int(a), unit="s").normalize(): b for a, b in ch}, dtype=float)
    return s[~s.index.duplicated(keep="last")]


def build_llama(meta: pd.DataFrame, symbols: set[str], workers: int = 6) -> pd.DataFrame:
    OC_DIR.mkdir(parents=True, exist_ok=True)
    tm = llama_token_map(meta)
    tm = tm[tm.symbol.isin(symbols)]
    tm.to_json(OC_DIR / "llama_token_map.json", orient="records")
    slugs = sorted({s for ss in tm.slugs for s in ss})
    print(f"  defillama: {len(tm)} tokens, {len(slugs)} protocol slugs", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        tvl = dict(zip(slugs, ex.map(llama_tvl, slugs)))
        fees = dict(zip(slugs, ex.map(llama_fees, slugs)))
    rows = []
    for _, r in tm.iterrows():
        tv = [tvl[s] for s in r.slugs if len(tvl.get(s, []))]
        fe = [fees[s] for s in r.slugs if len(fees.get(s, []))]
        tvs = pd.concat(tv, axis=1).sum(axis=1, min_count=1) if tv else pd.Series(dtype=float)
        fes = pd.concat(fe, axis=1).sum(axis=1, min_count=1) if fe else pd.Series(dtype=float)
        d = pd.DataFrame({"tvl": tvs, "fees": fes})
        d["symbol"] = r.symbol
        rows.append(d.rename_axis("date").reset_index())
    df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    df.to_parquet(OC_DIR / "defillama.parquet", index=False)
    return df


# --------------------------------------------------------------------- Etherscan
class Etherscan:
    """Minimal Etherscan V2 client (chainid=1). Requires ETHERSCAN_API_KEY."""

    def __init__(self, key: str | None = None, chainid: int = 1, rate: float = 4.5):
        self.key = key or os.environ.get("ETHERSCAN_API_KEY")
        if not self.key:
            raise RuntimeError("ETHERSCAN_API_KEY is not set; Etherscan refuses keyless requests")
        self.chainid, self.min_gap, self._last = chainid, 1.0 / rate, 0.0

    def call(self, **params):
        params.update(chainid=self.chainid, apikey=self.key)
        wait = self.min_gap - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        r = _get(ETHERSCAN, params)
        js = r.json()
        if js.get("status") == "0" and "No transactions" not in str(js.get("message")) \
                and js.get("result") not in ([], None):
            raise RuntimeError(f"etherscan: {js.get('message')}: {str(js.get('result'))[:120]}")
        return js.get("result")

    def block_at(self, ts: int, closest: str = "before") -> int:
        return int(self.call(module="block", action="getblocknobytime", timestamp=ts, closest=closest))

    def token_transfers(self, contract: str, start_block: int, end_block: int, max_pages: int = 50) -> pd.DataFrame:
        """ERC-20 transfers of `contract` between two blocks (split recursively
        when a range exceeds the 10,000-row window)."""
        res = self.call(module="account", action="tokentx", contractaddress=contract, startblock=start_block,
                        endblock=end_block, page=1, offset=10000, sort="asc") or []
        if len(res) >= 10000 and end_block - start_block > 1 and max_pages > 1:
            mid = (start_block + end_block) // 2
            return pd.concat([self.token_transfers(contract, start_block, mid, max_pages // 2),
                              self.token_transfers(contract, mid + 1, end_block, max_pages // 2)])
        return pd.DataFrame(res)


def transfer_activity(tx: pd.DataFrame) -> pd.DataFrame:
    """Daily ERC-20 activity from raw transfers: transfers, unique senders and
    receivers, first-time receivers (new holders within the pulled window)."""
    if tx.empty:
        return pd.DataFrame()
    d = pd.to_datetime(tx["timeStamp"].astype(int), unit="s").dt.normalize()
    tx = tx.assign(date=d)
    first_seen = tx.groupby("to")["date"].min()
    new = first_seen.value_counts().rename("new_receivers")
    g = tx.groupby("date")
    out = pd.DataFrame({"transfers": g.size(), "senders": g["from"].nunique(), "receivers": g["to"].nunique()})
    return out.join(new).fillna({"new_receivers": 0})


# --------------------------------------------------------------------- features
ONCHAIN_FEATURES: dict[str, tuple[str, str]] = {
    "oc_adr_S": ("Active addresses, last 7 days vs baseline", "on-chain"),
    "oc_adr_trend": ("Active addresses, 30d vs prior 30d (days -90..-61)", "on-chain"),
    "oc_tx_S": ("Transactions, last 7 days vs baseline", "on-chain"),
    "oc_tfr_S": ("Transfers, last 7 days vs baseline", "on-chain"),
    "oc_holders_accel": ("Holder growth, 60d vs prior 60d", "on-chain"),
    "oc_holders_60": ("Holder growth, 60d", "on-chain"),
    "oc_supply_365": ("Supply growth, 1y (dilution)", "on-chain"),
    "oc_supply_60": ("Supply growth, 60d", "on-chain"),
    "oc_mvrv": ("MVRV (market / realised value, log)", "on-chain"),
    "oc_mcap": ("Market cap (log, CoinMetrics estimate)", "on-chain"),
    "oc_activity_vs_price": ("Activity growth minus price change, 30d", "on-chain"),
    "tvl_60": ("TVL growth, 60d", "defi"),
    "tvl_vs_price": ("TVL growth minus price change, 60d", "defi"),
    "tvl_mcap": ("TVL / market cap (log)", "defi"),
    "fees_trend": ("Fees, 30d vs prior 30d", "defi"),
}


def load_onchain_panels(dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Wide date x symbol matrices for each on-chain series."""
    out = {}
    cm_path, ll_path = OC_DIR / "coinmetrics.parquet", OC_DIR / "defillama.parquet"
    if cm_path.exists():
        cm = pd.read_parquet(cm_path).dropna(subset=["symbol"])
        for m in CM_METRICS + ["CapMrktEstUSD"]:
            if m in cm:
                w = cm.pivot_table(index="date", columns="symbol", values=m, aggfunc="last")
                out[m] = w.reindex(dates)
    if ll_path.exists():
        ll = pd.read_parquet(ll_path)
        for m in ("tvl", "fees"):
            w = ll.pivot_table(index="date", columns="symbol", values=m, aggfunc="last")
            out[m] = w.reindex(dates).where(lambda x: x > 0)
    return out


def _win_mean(x: np.ndarray, t: np.ndarray, lo: int, hi: int) -> np.ndarray:
    idx = t[:, None] + np.arange(lo, hi + 1)[None, :]
    ok = (idx >= 0) & (idx < len(x))
    g = np.where(ok, x[np.clip(idx, 0, len(x) - 1)], np.nan)
    n = np.sum(~np.isnan(g), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n >= max(2, (hi - lo + 1) // 2), np.nansum(g, 1) / np.maximum(n, 1), np.nan)


def _at(x: np.ndarray, t: np.ndarray, k: int, look: int = 7) -> np.ndarray:
    """last valid value at or before t+k (looking back up to `look` days)."""
    out = np.full(len(t), np.nan)
    for j in range(look + 1):
        i = t + k - j
        ok = (i >= 0) & (i < len(x)) & np.isnan(out)
        out[ok] = x[i[ok]]
    return out


def onchain_features(rows: pd.DataFrame, panels: dict[str, pd.DataFrame], lc: pd.DataFrame) -> pd.DataFrame:
    """On-chain features for rows with columns symbol, t (day-0 index)."""
    res = pd.DataFrame(index=rows.index, columns=list(ONCHAIN_FEATURES), dtype=float)
    for sym, sub in rows.groupby("symbol"):
        t = sub["t"].to_numpy()
        f = {}

        def ser(name):
            w = panels.get(name)
            if w is None or sym not in w:
                return None
            x = w[sym].to_numpy(dtype=float)
            return x if np.any(~np.isnan(x)) else None

        with np.errstate(invalid="ignore", divide="ignore"):
            px = lc[sym].to_numpy() if sym in lc else None
            mom30 = (_at(px, t, -1) - _at(px, t, -31)) if px is not None else np.nan
            mom60 = (_at(px, t, -1) - _at(px, t, -61)) if px is not None else np.nan
            adr = ser("AdrActCnt")
            if adr is not None:
                base = _win_mean(adr, t, -180, -61)
                f["oc_adr_S"] = np.log(_win_mean(adr, t, -7, -1) / base)
                f["oc_adr_trend"] = np.log(_win_mean(adr, t, -30, -1) / _win_mean(adr, t, -90, -61))
                f["oc_activity_vs_price"] = f["oc_adr_trend"] - mom30
            for m, k in (("TxCnt", "oc_tx_S"), ("TxTfrCnt", "oc_tfr_S")):
                x = ser(m)
                if x is not None:
                    f[k] = np.log(_win_mean(x, t, -7, -1) / _win_mean(x, t, -180, -61))
            hb = ser("AdrBalCnt")
            if hb is not None:
                g1 = np.log(_at(hb, t, -1) / _at(hb, t, -61))
                g0 = np.log(_at(hb, t, -61) / _at(hb, t, -121))
                f["oc_holders_60"], f["oc_holders_accel"] = g1, g1 - g0
            sp = ser("SplyCur")
            if sp is not None:
                f["oc_supply_365"] = np.log(_at(sp, t, -1) / _at(sp, t, -366))
                f["oc_supply_60"] = np.log(_at(sp, t, -1) / _at(sp, t, -61))
            mv = ser("CapMVRVCur")
            if mv is not None:
                f["oc_mvrv"] = np.log(_at(mv, t, -1))
            mc = ser("CapMrktEstUSD")
            if mc is None:
                mc = ser("CapMrktCurUSD")
            if mc is not None:
                f["oc_mcap"] = np.log(_at(mc, t, -1))
            tv = ser("tvl")
            if tv is not None:
                f["tvl_60"] = np.log(_at(tv, t, -1) / _at(tv, t, -61))
                f["tvl_vs_price"] = f["tvl_60"] - mom60
                if mc is not None:
                    f["tvl_mcap"] = np.log(_at(tv, t, -1) / _at(mc, t, -1))
            fe = ser("fees")
            if fe is not None:
                f["fees_trend"] = np.log(_win_mean(fe, t, -30, -1) / _win_mean(fe, t, -90, -61))
        for k, v in f.items():
            v = np.where(np.isfinite(v), v, np.nan)
            res.loc[sub.index, k] = v
    return res
