"""Wind-down / NAV-discount special-situation screener.

Two-stage workflow:
  1. Pull news from Google News RSS (and any user-supplied RSS feeds for
     special-sits newsletters / blogs) using wind-down / NAV-discount
     keywords; extract LSE-style tickers from headlines and snippets.
  2. For each candidate ticker, pull weekly OHLCV from Yahoo Finance and
     test the setup from the brief: a weekly volume spike with the
     candle sitting near the volume profile POC. MFI(18) "green"
     (rising or above 50) is reported as an optional confirmation.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


DEFAULT_QUERIES = [
    "managed wind-down investment trust",
    "managed wind down investment trust",
    "discount to NAV tender offer investment trust",
    "investment trust liquidation",
    "scheme of reconstruction investment trust",
    "return of capital investment trust",
    "cash exit option investment trust",
    "realisation pool investment trust",
    "continuation vote investment trust",
]

# Newsletter / blog feeds that frequently cover UK closed-end fund
# special situations. The user can edit this list in the UI.
DEFAULT_RSS_FEEDS = [
    "https://quoteddata.com/feed/",
    "https://citywire.com/investment-trust-insider/news/rss",
]

# Words appearing right next to a candidate ticker that lift confidence.
TICKER_CONTEXT_WORDS = (
    "wind", "nav", "discount", "tender", "liquidat", "realisat",
    "realiz", "scheme", "reconstruction", "continuation", "return of capital",
)

# Patterns we trust to actually identify a ticker rather than an acronym.
_TICKER_PATTERNS = [
    re.compile(r"\(\s*(?:LSE|LON|AIM)\s*[:\-]\s*([A-Z]{2,5})\s*\)"),
    re.compile(r"\b(?:LSE|LON|AIM)\s*[:\-]\s*([A-Z]{2,5})\b"),
    re.compile(r"\(\s*([A-Z]{2,5})\.L\s*\)"),
    re.compile(r"\b([A-Z]{2,5})\.L\b"),
    re.compile(r"\bticker[:\s]+([A-Z]{2,5})\b", re.IGNORECASE),
]


def fetch_rss(url: str, max_items: int = 40) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # Handle both RSS 2.0 (<item>) and Atom (<entry>) feeds.
    nodes = list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry"))
    for node in nodes[:max_items]:
        title = (node.findtext("title") or node.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_node = node.find("link")
        link = link_node.text.strip() if link_node is not None and link_node.text else ""
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "")
        published = (
            node.findtext("pubDate")
            or node.findtext("{http://www.w3.org/2005/Atom}updated")
            or node.findtext("{http://www.w3.org/2005/Atom}published")
            or ""
        ).strip()
        description = unescape(
            node.findtext("description")
            or node.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        ).strip()
        items.append({"title": title, "link": link, "pubDate": published, "description": description})
    return items


def google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote_plus(query)
        + "&hl=en-GB&gl=GB&ceid=GB:en"
    )


def extract_tickers(text: str) -> set[str]:
    found: set[str] = set()
    for pat in _TICKER_PATTERNS:
        for m in pat.findall(text):
            sym = m.upper()
            if sym in {"LSE", "LON", "AIM", "PLC", "LTD", "AND", "FOR", "THE"}:
                continue
            found.add(sym)
    return found


def normalise_lse_ticker(sym: str) -> str:
    sym = sym.strip().upper()
    if "." in sym:
        return sym
    return f"{sym}.L"


def weekly_volume_profile(df: pd.DataFrame, bins: int = 60) -> tuple[float | None, np.ndarray | None, np.ndarray | None]:
    """POC of a weekly volume profile, distributing each bar's volume
    uniformly across its (low, high) range."""
    if df.empty:
        return None, None, None
    lo = float(df["Low"].min())
    hi = float(df["High"].max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None, None, None
    edges = np.linspace(lo, hi, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vols = np.zeros(bins)
    for low, high, vol in zip(df["Low"].to_numpy(), df["High"].to_numpy(), df["Volume"].to_numpy()):
        if not (np.isfinite(low) and np.isfinite(high) and np.isfinite(vol)) or high <= low or vol <= 0:
            continue
        lo_idx = max(0, int(np.searchsorted(edges, low, side="right") - 1))
        hi_idx = min(bins - 1, int(np.searchsorted(edges, high, side="right") - 1))
        if hi_idx < lo_idx:
            continue
        n = hi_idx - lo_idx + 1
        vols[lo_idx:hi_idx + 1] += vol / n
    if vols.sum() <= 0:
        return None, None, None
    return float(centers[int(np.argmax(vols))]), centers, vols


def money_flow_index(df: pd.DataFrame, period: int = 18) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    rmf = tp * df["Volume"]
    delta = tp.diff()
    pos = rmf.where(delta > 0, 0.0)
    neg = rmf.where(delta < 0, 0.0)
    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - 100 / (1 + ratio)


def screen_ticker(
    ticker: str,
    *,
    lookback_weeks: int = 260,
    profile_weeks: int = 156,
    vol_spike_mult: float = 2.0,
    poc_proximity_pct: float = 0.07,
    mfi_period: int = 18,
) -> dict:
    try:
        data = yf.download(ticker, period="5y", interval="1wk", progress=False, auto_adjust=False)
    except Exception as exc:
        return {"ticker": ticker, "error": f"download failed: {exc}"}
    if data is None or data.empty:
        return {"ticker": ticker, "error": "no data"}
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["Close", "Volume"]).tail(lookback_weeks)
    if len(data) < max(mfi_period + 5, 30):
        return {"ticker": ticker, "error": "insufficient bars"}

    mfi_series = money_flow_index(data, mfi_period)
    last_mfi = float(mfi_series.iloc[-1]) if pd.notna(mfi_series.iloc[-1]) else np.nan
    prev_mfi = float(mfi_series.iloc[-2]) if pd.notna(mfi_series.iloc[-2]) else np.nan
    mfi_green = (
        np.isfinite(last_mfi)
        and (last_mfi > 50.0 or (np.isfinite(prev_mfi) and last_mfi > prev_mfi))
    )

    avg_vol = data["Volume"].rolling(26).mean()
    last_vol = float(data["Volume"].iloc[-1])
    last_avg = float(avg_vol.iloc[-1]) if pd.notna(avg_vol.iloc[-1]) else np.nan
    vol_ratio = last_vol / last_avg if (np.isfinite(last_avg) and last_avg > 0) else np.nan
    vol_spike = bool(np.isfinite(vol_ratio) and vol_ratio >= vol_spike_mult)

    profile_window = data.tail(min(len(data), profile_weeks))
    poc_price, _, _ = weekly_volume_profile(profile_window)
    last_close = float(data["Close"].iloc[-1])
    if poc_price and poc_price > 0:
        poc_distance_pct = abs(last_close - poc_price) / poc_price
        near_poc = poc_distance_pct <= poc_proximity_pct
    else:
        poc_distance_pct = np.nan
        near_poc = False

    return {
        "ticker": ticker,
        "last_close": last_close,
        "vol_ratio": vol_ratio,
        "vol_spike": vol_spike,
        "poc": poc_price,
        "poc_distance_pct": poc_distance_pct,
        "near_poc": near_poc,
        "mfi": last_mfi,
        "mfi_green": bool(mfi_green),
        "setup_match": bool(vol_spike and near_poc),
    }


def _gather_candidates(news_items: Iterable[dict]) -> dict[str, list[dict]]:
    candidates: dict[str, list[dict]] = {}
    for item in news_items:
        text = f"{item.get('title','')} {item.get('description','')}"
        text_lc = text.lower()
        # Drop hits that don't even mention a wind-down/NAV-style word, to
        # cut down on regex false positives like "PLC" or "GBP".
        if not any(w in text_lc for w in TICKER_CONTEXT_WORDS):
            continue
        for sym in extract_tickers(text):
            candidates.setdefault(normalise_lse_ticker(sym), []).append(item)
    return candidates


def render_nav_discount_finder() -> None:
    st.title("Wind-down / NAV Discount Setup Finder")
    st.caption(
        "Pulls news on managed wind-downs, NAV-discount tenders, and "
        "liquidations, then screens each candidate for a weekly volume "
        "spike near the volume-profile POC. MFI(18) green is reported "
        "as soft confirmation only."
    )

    queries_text = st.text_area(
        "Google News queries (one per line)",
        value="\n".join(DEFAULT_QUERIES),
        height=180,
    )
    feeds_text = st.text_area(
        "Additional RSS feeds — special-sits newsletters, blogs (one URL per line)",
        value="\n".join(DEFAULT_RSS_FEEDS),
        height=120,
    )
    extra_tickers = st.text_input(
        "Manually-added tickers (comma-separated, e.g. RSE.L, NBPE.L)",
        value="",
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        vol_spike_mult = st.number_input("Vol spike × 26w avg", value=2.0, min_value=1.0, step=0.25)
    with col2:
        poc_proximity_pct = st.number_input("POC proximity (frac)", value=0.07, min_value=0.0, max_value=0.5, step=0.01)
    with col3:
        profile_weeks = st.number_input("Profile lookback (weeks)", value=156, min_value=26, max_value=520, step=26)
    with col4:
        mfi_period = st.number_input("MFI length", value=18, min_value=2, max_value=100, step=1)

    require_mfi = st.checkbox("Require MFI green (rising or > 50)", value=False)

    if not st.button("Run scan"):
        return

    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]
    feeds = [f.strip() for f in feeds_text.splitlines() if f.strip()]

    all_items: list[dict] = []
    with st.spinner("Pulling Google News..."):
        for q in queries:
            try:
                for it in fetch_rss(google_news_url(q)):
                    it["source"] = f"news:{q}"
                    all_items.append(it)
            except Exception as exc:
                st.warning(f"News fetch failed for '{q}': {exc}")
    with st.spinner("Pulling newsletter / blog feeds..."):
        for url in feeds:
            try:
                for it in fetch_rss(url):
                    it["source"] = url
                    all_items.append(it)
            except Exception as exc:
                st.warning(f"Feed fetch failed for '{url}': {exc}")

    st.write(f"Retrieved {len(all_items)} news items.")

    ticker_to_news = _gather_candidates(all_items)
    for raw in [t.strip() for t in extra_tickers.split(",") if t.strip()]:
        ticker_to_news.setdefault(normalise_lse_ticker(raw), [])

    st.write(f"Unique candidate tickers: {len(ticker_to_news)}")
    if not ticker_to_news:
        st.info("No tickers extracted — add some manually above and re-run.")
        return

    results: list[dict] = []
    progress = st.progress(0.0)
    for i, sym in enumerate(sorted(ticker_to_news)):
        res = screen_ticker(
            sym,
            profile_weeks=int(profile_weeks),
            vol_spike_mult=float(vol_spike_mult),
            poc_proximity_pct=float(poc_proximity_pct),
            mfi_period=int(mfi_period),
        )
        res["news_count"] = len(ticker_to_news[sym])
        results.append(res)
        progress.progress((i + 1) / len(ticker_to_news))

    df = pd.DataFrame(results)
    if df.empty:
        st.info("No screened results.")
        return

    if require_mfi and "setup_match" in df:
        df["setup_match"] = df["setup_match"] & df["mfi_green"].fillna(False)

    sort_cols = [c for c in ("setup_match", "vol_ratio") if c in df.columns]
    st.subheader("All candidates")
    st.dataframe(df.sort_values(sort_cols, ascending=[False] * len(sort_cols)) if sort_cols else df)

    st.subheader("Setup matches")
    matches = df[df.get("setup_match", False) == True]
    if matches.empty:
        st.write("No tickers cleared the setup filter.")
    else:
        st.dataframe(matches)
        for _, row in matches.iterrows():
            sym = row["ticker"]
            with st.expander(f"{sym} — supporting news"):
                hits = ticker_to_news.get(sym, [])
                if not hits:
                    st.write("(manually added — no news linked)")
                for it in hits[:15]:
                    title = it.get("title", "(no title)") or "(no title)"
                    link = it.get("link", "")
                    when = it.get("pubDate", "")
                    src = it.get("source", "")
                    if link:
                        st.markdown(f"- [{title}]({link}) — {when} _{src}_")
                    else:
                        st.markdown(f"- {title} — {when} _{src}_")
