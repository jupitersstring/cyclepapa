"""Financial Modeling Prep client: crypto universe, daily bars and crypto news.

The API key is read from FMP_API_KEY and never logged; errors are re-raised
without the request URL so the key cannot leak into logs or tracebacks.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .config import CACHE_DIR, START_DATE

BASE = "https://financialmodelingprep.com/stable"


class FMPError(RuntimeError):
    pass


class FMP:
    def __init__(self, key: str | None = None, workers: int = 8):
        self.key = key or os.environ.get("FMP_API_KEY")
        if not self.key:
            raise FMPError("FMP_API_KEY is not set")
        self.workers = workers
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=workers * 2, pool_maxsize=workers * 2)
        self.session.mount("https://", adapter)

    def get(self, path: str, **params):
        params["apikey"] = self.key
        last = None
        for attempt in range(7):
            try:
                r = self.session.get(f"{BASE}/{path}", params=params, timeout=120)
            except requests.RequestException as e:  # network hiccup
                last = type(e).__name__
                time.sleep(min(30, 2 ** attempt))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            if r.status_code != 200:
                raise FMPError(f"{path}: HTTP {r.status_code}: {r.text[:200]}")
            try:
                return r.json()
            except ValueError:
                raise FMPError(f"{path}: non-JSON response")
        raise FMPError(f"{path}: giving up after retries ({last})")

    # ----- universe -------------------------------------------------------
    def crypto_list(self, refresh: bool = False) -> pd.DataFrame:
        path = CACHE_DIR / "fmp_crypto_list.json"
        if refresh or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            json.dump(self.get("cryptocurrency-list"), open(path, "w"))
        return pd.DataFrame(json.load(open(path)))

    # ----- daily bars -----------------------------------------------------
    def eod(self, symbol: str, start: str = START_DATE) -> pd.DataFrame:
        js = self.get("historical-price-eod/full", symbol=symbol, **{"from": start})
        df = pd.DataFrame(js)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date")
        return df[["date", "open", "high", "low", "close", "volume", "vwap"]].reset_index(drop=True)

    def download_eod(self, symbols, refresh: bool = False, log_every: int = 250) -> dict:
        out_dir = CACHE_DIR / "fmp_eod"
        out_dir.mkdir(parents=True, exist_ok=True)
        todo = [s for s in symbols if refresh or not (out_dir / f"{s}.parquet").exists()]
        status = {"done": 0, "empty": [], "failed": {}}

        def one(sym):
            df = self.eod(sym)
            if df.empty:
                return sym, "empty"
            df.to_parquet(out_dir / f"{sym}.parquet", index=False)
            return sym, "ok"

        with ThreadPoolExecutor(self.workers) as ex:
            futs = {ex.submit(one, s): s for s in todo}
            for i, f in enumerate(as_completed(futs), 1):
                sym = futs[f]
                try:
                    _, st = f.result()
                    if st == "empty":
                        status["empty"].append(sym)
                    status["done"] += 1
                except Exception as e:  # keep going; record and report
                    status["failed"][sym] = str(e)[:200]
                if i % log_every == 0:
                    print(f"  eod {i}/{len(todo)} (failed {len(status['failed'])})", flush=True)
        return status

    # ----- news (catalyst text for day 0) ---------------------------------
    def crypto_news(self, symbols: str, start: str, end: str, limit: int = 250) -> pd.DataFrame:
        js = self.get("news/crypto", symbols=symbols, **{"from": start, "to": end}, limit=limit)
        return pd.DataFrame(js)
