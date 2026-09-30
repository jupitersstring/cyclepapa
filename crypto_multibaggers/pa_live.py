"""Live price-action check: refresh recent bars from FMP, recompute the
Schabacker / Japanese / Dalton factors and report, for today's tradeable
coins, where the trend-following rules fired in the last few days and each
coin's checklist.

    python -m crypto_multibaggers.pa_live [SYMBOL ...]
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import panel
from . import pa_study as PS
from . import priceaction as PA
from .config import ANALYSIS_DIR
from .fmp import FMP

RECENT_DAYS = 5
CHECK = [  # (column, label)
    ("breakout_55", "55-day closing breakout (last 5 days)"),
    ("strong_candle", "Strong close (marubozu or top quarter of range)"),
    ("no_bear_candles", "No bearish candle pattern in the last 5 days"),
    ("sanyaku", "Ichimoku: all four signals bullish"),
    ("value_up", "Dalton: value migrating higher"),
    ("higher_value", "Dalton: higher, non-overlapping value"),
    ("accept", "Dalton: 2+ closes above prior value high"),
    ("otf", "Dalton: one-timeframing up (higher lows, 3+ days)"),
    ("pattern", "Schabacker breakout in the last 10 days"),
]


def _refresh(symbols, start="2026-08-01", workers=8) -> dict[str, pd.DataFrame]:
    f = FMP(workers=workers)

    def one(s):
        try:
            return s, f.eod(s, start=start)
        except Exception:
            return s, pd.DataFrame()

    with ThreadPoolExecutor(workers) as ex:
        return {s: d for s, d in ex.map(one, symbols) if len(d)}


def run(symbols: list[str] | None = None) -> pd.DataFrame:
    p, meta, mkt = panel.load()
    elig = [s for s in meta.index[meta.exclusion == ""] if s not in panel.COMMODITY_BACKED]
    v7 = p["volume"][elig].iloc[-7:]
    cand = symbols or [s for s in elig if v7[s].mean() >= 100_000 and (v7[s] > 0).sum() >= 6]
    fresh = _refresh(cand)
    rows = []
    for s in cand:
        hist = pd.DataFrame({f: p[f][s] for f in ("open", "high", "low", "close", "volume")}).dropna(subset=["close"])
        if s in fresh:
            fr = fresh[s].set_index("date")[["open", "high", "low", "close", "volume"]]
            hist = pd.concat([hist[hist.index < fr.index.min()], fr])     # fresh bars replace the partial last day
        if len(hist) < 260:
            continue
        idx = pd.date_range(hist.index.min(), hist.index.max(), freq="D")
        hist = hist.reindex(idx)
        c_clean, _ = panel._clean_close(hist["close"].to_numpy(float), hist["volume"].to_numpy(float))
        o = hist["open"].where(~np.isnan(c_clean)).to_numpy(float)
        h = np.fmax(hist["high"].to_numpy(float), np.fmax(o, c_clean))
        l = np.fmin(hist["low"].to_numpy(float), np.fmin(o, c_clean))
        v = hist["volume"].to_numpy(float)
        S = PA.series(o, h, l, c_clean, v)
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            clv = np.where(rng > 0, (c_clean - l) / rng, np.nan)
        sig = PS.entry_signals(S, clv)
        last = len(c_clean) - 1
        recent = slice(last - RECENT_DAYS + 1, last + 1)
        fired = {r: bool(np.nan_to_num(np.asarray(x[recent], float)).any()) for r, x in sig.items()}
        pat10 = np.nan_to_num(S["sch_any_bo"][last - 9:last + 1]).any()
        rows.append({
            "symbol": s, "name": meta.at[s, "name"], "last_date": idx[last].date(), "close": c_clean[last],
            "usd_vol_7d": float(np.nanmean(v[-7:])),
            "breakout_55": bool(np.nan_to_num(S["donchian55"][recent]).any()),
            "strong_candle": bool(S["jp_marubozu"][last] == 1 or clv[last] >= 0.75),
            "no_bear_candles": bool(S["jp_bear5"][last] == 0),
            "sanyaku": bool(S["ichi_sanyaku"][last] == 1),
            "value_up": bool(S["dal_migration"][last] > 0.5),
            "higher_value": bool(S["dal_higher_value"][last] == 1),
            "accept": bool(S["dal_accept"][last] >= 2),
            "otf": bool(S["dal_otf"][last] >= 3),
            "pattern": bool(pat10),
            "kijun_dist_atr": S["ichi_kijun_dist"][last],
            "best_rule_fired": fired.get("don+candles+sanyaku", False),
            "rules_fired": ", ".join(r for r, x in fired.items() if x and r not in ("trigger", "trigger_top")),
        })
    df = pd.DataFrame(rows)
    df["checks"] = df[[c for c, _ in CHECK]].sum(axis=1)
    df = df.sort_values(["best_rule_fired", "checks", "usd_vol_7d"], ascending=False)
    df.to_csv(ANALYSIS_DIR / "pa_live_checklist.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    d = run([s if s.endswith("USD") else s + "USD" for s in sys.argv[1:]] or None)
    print(d.drop(columns=["rules_fired"]).head(40).to_string(index=False))
