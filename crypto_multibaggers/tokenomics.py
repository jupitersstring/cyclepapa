"""Tokenomics scorecard for a short list of coins.

Float and FDV overhang from CoinGecko (circulating / total / max supply), the
supply growth actually realised over the last year (CoinGecko market cap /
price, cross-checked against CoinMetrics SplyCur where it exists), and value
accrual from DefiLlama (fees, revenue and holders revenue, 30 days annualised,
against market cap). Scheduled unlocks are not available from a free API
(DefiLlama's emissions endpoint is paid), so forward dilution rests on float.

    python -m crypto_multibaggers.tokenomics MNDE XAI IMX ...
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd
import requests

from .config import ANALYSIS_DIR, CACHE_DIR

CG = "https://api.coingecko.com/api/v3"
LLAMA = "https://api.llama.fi"
TK_DIR = CACHE_DIR / "tokenomics"

# ticker -> (coingecko id, defillama fees slug or None)
KNOWN = {
    "MNDE": ("marinade", ["marinade-liquid-staking", "marinade-native", "marinade-select"]), "XAI": ("xai-blockchain", []), "IMX": ("immutable-x", ["immutablex"]),
    "RUNE": ("thorchain", ["thorchain", "thorchain-dex"]), "SAUCE": ("saucerswap", ["saucerswap"]),
    "GRT": ("the-graph", ["the-graph"]), "HBAR": ("hedera-hashgraph", ["hedera"]),
    "CTX": ("cryptex-finance", ["cryptex-finance"]), "LTC": ("litecoin", ["litecoin"]),
    "AVAX": ("avalanche-2", ["avalanche", "avax"]), "SEI": ("sei-network", ["sei"]), "ERG": ("ergo", []),
}


def _get(url, params=None, tries=6):
    for a in range(tries):
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** a)
            continue
        if r.status_code == 429:
            time.sleep(20 + 15 * a)
            continue
        return r
    return None


def _cached(name, fetch):
    path = TK_DIR / name
    if path.exists():
        return json.loads(path.read_text())
    js = fetch()
    if js is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(js))
    return js


def coingecko(cg_id: str) -> dict:
    def f1():
        r = _get(f"{CG}/coins/{cg_id}", {"localization": "false", "tickers": "false", "community_data": "false",
                                           "developer_data": "false", "sparkline": "false"})
        time.sleep(6)
        return r.json() if r is not None and r.status_code == 200 else None

    def f2():
        r = _get(f"{CG}/coins/{cg_id}/market_chart", {"vs_currency": "usd", "days": 365, "interval": "daily"})
        time.sleep(6)
        return r.json() if r is not None and r.status_code == 200 else None

    return {"coin": _cached(f"cg_{cg_id}.json", f1), "chart": _cached(f"cg_chart_{cg_id}.json", f2)}


def llama_flow(slug: str, data_type: str) -> float | None:
    """Last 30 days of a DefiLlama fees series, annualised (USD)."""
    def f():
        r = _get(f"{LLAMA}/summary/fees/{slug}", {"dataType": data_type, "excludeTotalDataChartBreakdown": "true"})
        return r.json() if r is not None and r.status_code == 200 else {"totalDataChart": []}

    js = _cached(f"llama_{slug}_{data_type}.json", f)
    ch = (js or {}).get("totalDataChart") or []
    if len(ch) < 20:
        return None
    s = pd.Series({pd.Timestamp(int(a), unit="s"): b for a, b in ch}, dtype=float).sort_index()
    return float(s.iloc[-30:].sum() * 365 / 30)


def implied_supply_growth(chart: dict | None) -> tuple[float | None, int]:
    """Circulating supply implied by market cap / price: growth over the chart window."""
    if not chart or not chart.get("market_caps") or not chart.get("prices"):
        return None, 0
    mc = pd.Series({a: b for a, b in chart["market_caps"]}, dtype=float)
    px = pd.Series({a: b for a, b in chart["prices"]}, dtype=float)
    sup = (mc / px).replace([np.inf, -np.inf], np.nan).dropna()
    sup = sup[sup > 0]
    if len(sup) < 200:
        return None, len(sup)
    start, end = sup.iloc[:14].median(), sup.iloc[-7:].median()
    days = (sup.index[-1] - sup.index[0]) / 86_400_000
    return float((end / start) ** (365 / days) - 1), len(sup)


def scorecard(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        cg_id, slug = KNOWN[t]
        g = coingecko(cg_id)
        md = (g["coin"] or {}).get("market_data", {})
        circ, total, mx = md.get("circulating_supply"), md.get("total_supply"), md.get("max_supply")
        mcap = (md.get("market_cap") or {}).get("usd")
        fdv = (md.get("fully_diluted_valuation") or {}).get("usd")
        growth, n = implied_supply_growth(g["chart"])
        denom = mx or total
        row = {"coin": t, "cg_id": cg_id, "mcap": mcap, "fdv": fdv, "circulating": circ, "total_supply": total,
               "max_supply": mx, "float": circ / denom if circ and denom else None,
               "fdv_to_mcap": fdv / mcap if fdv and mcap else (denom / circ if circ and denom else None),
               "supply_growth_1y": growth, "supply_obs": n}
        flows = {"fees_ann": [], "revenue_ann": [], "holders_rev_ann": []}
        used = []
        for sl in slug:                      # a protocol split across products is summed
            fees = llama_flow(sl, "dailyFees")
            if fees is None:
                continue
            used.append(sl)
            flows["fees_ann"].append(fees)
            for k, dt in (("revenue_ann", "dailyRevenue"), ("holders_rev_ann", "dailyHoldersRevenue")):
                x = llama_flow(sl, dt)
                if x is not None:
                    flows[k].append(x)
        if used:
            row["llama_slug"] = "+".join(used)
            row.update({k: (sum(v) if v else None) for k, v in flows.items()})
            if mcap:
                for k, y in (("fees_ann", "fees_yield"), ("revenue_ann", "rev_yield"), ("holders_rev_ann", "holder_yield")):
                    row[y] = row[k] / mcap if row.get(k) else None
        rows.append(row)
    df = pd.DataFrame(rows)
    # composite: equal-weight ranks of float (high), realised dilution (low) and value accrual (high)
    accrual = df.get("holder_yield", pd.Series(np.nan, index=df.index)).fillna(df.get("rev_yield")).fillna(0.0)
    df["accrual_yield"] = accrual
    df["score"] = (df["float"].rank(pct=True) + (-df["supply_growth_1y"]).rank(pct=True) + accrual.rank(pct=True)) / 3
    df = df.sort_values("score", ascending=False)
    df.to_csv(ANALYSIS_DIR / "tokenomics_scorecard.csv", index=False)
    return df


if __name__ == "__main__":
    tick = sys.argv[1:] or list(KNOWN)
    pd.set_option("display.width", 250)
    d = scorecard(tick)
    show = d.copy()
    for k in ("mcap", "fdv", "fees_ann", "revenue_ann", "holders_rev_ann"):
        if k in show:
            show[k] = show[k] / 1e6
    print(show.round(4).to_string(index=False))
