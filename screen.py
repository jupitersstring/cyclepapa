"""
Two-screen SMID stock picker.

Screen 1: weekly AND monthly relative-strength breakout vs. index (52w / 12m highs).
Screen 2: max-independent-set on the |corr|>eps graph among survivors,
          weighted by composite momentum score (greedy).
"""

import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

INDEX = "IWM"  # Russell 2000 proxy

# ~150 SMID-cap names spanning sectors. Mostly S&P 400 / S&P 600 constituents.
UNIVERSE = [
    # Industrials
    "SAIA", "WMS", "BLDR", "OC", "ATKR", "CSL", "RBC", "AAON", "CW", "GGG",
    "HUBB", "MLI", "WCC", "AYI", "FSS", "EME", "TREX", "WWD", "GTLS", "AGCO",
    # Financials / banks
    "WTFC", "EWBC", "PNFP", "WAL", "CFR", "FHN", "ZION", "SNV", "WBS", "OZK",
    "CADE", "UMBF", "CBSH", "BOKF", "VLY", "FNB", "ONB",
    # Tech / semis
    "ENTG", "MKSI", "ONTO", "COHR", "FORM", "AMKR", "POWI", "SMCI", "LSCC",
    "QLYS", "BMI", "CIEN", "DV", "TENB", "RAMP", "CALX",
    # Health care
    "MEDP", "BIO", "ICUI", "MASI", "QDEL", "CRL", "PRGO", "PEN", "RGEN",
    "EXEL", "HALO", "NEOG", "GMED",
    # Consumer disc
    "DECK", "BURL", "RH", "PLNT", "FIVE", "TXRH", "WING", "MUSA", "BJ",
    "HBI", "LCII", "MTH", "TPH", "DKS", "OLLI", "URBN", "BOOT",
    # Consumer staples
    "POST", "PFGC", "USFD", "CASY", "INGR", "FLO",
    # Energy / materials
    "MTDR", "RRC", "AR", "PR", "MUR", "CIVI", "CRC", "WFRD", "NOG",
    "EXP", "MLM", "SUM", "CMC", "RS", "ATR", "AMRK",
    # Utilities / real estate
    "IDA", "NWE", "POR", "OGS", "SR", "NJR", "OGE",
    "STAG", "EGP", "REXR", "CUBE", "LSI", "TRNO", "ELS",
    # Communications / media
    "IPG", "WOLF", "LYV",
    # More small/mid quality
    "ESNT", "RYAN", "SF", "EVR", "RJF", "LPLA", "JEF",
    "GNTX", "WSC", "MTZ", "PRIM", "FIX", "DY", "EXLS", "G", "WTW",
    "BRBR", "FTDR", "CHE", "CACI", "BAH",
]


def fetch_prices(tickers: list[str], period: str = "18mo") -> pd.DataFrame:
    print(f"Downloading {len(tickers)} tickers ({period})...", file=sys.stderr)
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    px = raw["Close"].copy()
    px = px.dropna(axis=1, thresh=int(len(px) * 0.9))  # drop spotty names
    return px


def relative_strength_breakout(stock_px: pd.Series, idx_px: pd.Series, freq: str, lookback: int) -> tuple[bool, float]:
    """Resample to freq, compute log(stock/idx), test if last value is the max
    of the trailing `lookback` bars. Returns (is_breakout, current RS - prior max)."""
    s = stock_px.resample(freq).last().dropna()
    i = idx_px.resample(freq).last().dropna()
    df = pd.concat([s, i], axis=1, join="inner").dropna()
    if len(df) < lookback + 2:
        return False, np.nan
    rs = np.log(df.iloc[:, 0] / df.iloc[:, 1])
    window = rs.iloc[-(lookback + 1):-1]  # exclude current bar
    current = rs.iloc[-1]
    margin = current - window.max()
    return bool(current > window.max()), float(margin)


def screen1(px: pd.DataFrame, idx: pd.Series) -> pd.DataFrame:
    rows = []
    for t in px.columns:
        s = px[t].dropna()
        if len(s) < 260:
            continue
        ok_w, m_w = relative_strength_breakout(s, idx, "W-FRI", lookback=52)
        ok_m, m_m = relative_strength_breakout(s, idx, "ME", lookback=12)
        rows.append(
            dict(ticker=t, weekly_break=ok_w, monthly_break=ok_m,
                 w_margin=m_w, m_margin=m_m,
                 score=(m_w if not np.isnan(m_w) else 0) + (m_m if not np.isnan(m_m) else 0))
        )
    out = pd.DataFrame(rows)
    return out[(out.weekly_break) & (out.monthly_break)].sort_values("score", ascending=False)


def screen2_max_indep_set(survivors: pd.DataFrame, px: pd.DataFrame, eps: float = 0.5) -> pd.DataFrame:
    """Greedy max-weight independent set on |corr|>eps graph, weighted by momentum score."""
    tickers = survivors.ticker.tolist()
    if len(tickers) <= 1:
        return survivors.assign(selected=True)
    weekly_ret = px[tickers].resample("W-FRI").last().pct_change().dropna()
    corr = weekly_ret.corr().abs()

    # Order by score desc; greedily admit if max |corr| with chosen <= eps.
    survivors = survivors.set_index("ticker")
    chosen: list[str] = []
    for t in survivors.sort_values("score", ascending=False).index:
        if all(corr.loc[t, c] <= eps for c in chosen):
            chosen.append(t)
    survivors["selected"] = survivors.index.isin(chosen)
    return survivors.reset_index()


def diagnostics(selected: list[str], px: pd.DataFrame) -> dict:
    if len(selected) < 2:
        return {"n": len(selected)}
    weekly_ret = px[selected].resample("W-FRI").last().pct_change().dropna()
    cov = weekly_ret.cov().values
    eig = np.linalg.eigvalsh(cov)
    n_eff = (np.trace(cov) ** 2) / np.trace(cov @ cov)
    corr = weekly_ret.corr().values
    iu = np.triu_indices_from(corr, k=1)
    return {
        "n": len(selected),
        "mean_|corr|": float(np.mean(np.abs(corr[iu]))),
        "max_|corr|": float(np.max(np.abs(corr[iu]))),
        "N_eff_bets": float(n_eff),
        "top_eigenvalue_share": float(eig.max() / eig.sum()),
    }


def main() -> None:
    px_all = fetch_prices(UNIVERSE + [INDEX], period="18mo")
    if INDEX not in px_all.columns:
        raise SystemExit(f"Index {INDEX} missing from data.")
    idx = px_all[INDEX]
    px = px_all.drop(columns=[INDEX])

    survivors = screen1(px, idx)
    print(f"\n=== Screen 1: weekly AND monthly RS breakout vs {INDEX} ===")
    print(f"Survivors: {len(survivors)} / {px.shape[1]} tickers with sufficient history")
    if survivors.empty:
        print("(none)")
        return
    print(survivors.head(30).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    final = screen2_max_indep_set(survivors, px, eps=0.5)
    selected = final[final.selected].ticker.tolist()
    print(f"\n=== Screen 2: max independent set on |weekly corr| > 0.5 ===")
    print(f"Selected portfolio ({len(selected)} names):")
    print(final[final.selected][["ticker", "w_margin", "m_margin", "score"]]
          .to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    diag = diagnostics(selected, px)
    print("\n=== Portfolio diagnostics (weekly returns) ===")
    for k, v in diag.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
