"""Catalyst verification from FMP news + press releases.

Upgrades Model B's CatalystVerified from an earnings-date proxy to a real,
classified corporate-event check: for each ticker we pull recent press releases
(company-issued = most material) and third-party news, find items inside a
window, and classify them into event types with a magnitude. This is the
literature's single best filter separating a "monster beginning" (move backed by
genuine firm-specific information -> continuation, Dyl et al.) from a random
attention/MAX spike (-> reversal).

    catalyst_verified   1 if a material positive event within the window
    catalyst_magnitude  0..1 by event class (approval/contract/guidance high;
                        conference/analyst low), with a press-release boost
    catalyst_type       the class that fired
    catalyst_negative   dilutive offering / litigation / recall flag

Default universe = current ignition candidates (bounds cost); pass --all for the
whole FMP-cached panel, or --universe <json>.

Usage: python fmp_catalyst.py [--window 14] [--all]
"""
import os, sys, json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
import pandas as pd

BASE = "https://financialmodelingprep.com/stable/"
KEYFILE = "/home/user/cyclepapa/.fmp_key"
OUT = "/tmp/fmp_catalyst.csv"
DELIVER = "/home/user/cyclepapa/data/fmp/catalyst.csv"
NOW = datetime.now(timezone.utc)

# event class -> (magnitude, keywords). Checked high-to-low; first hit wins.
CLASSES = [
    ("approval",     1.00, ["fda approv", "approval", "clearance", "authorized", "authorisation",
                            "ce mark", "granted", "designation", "phase 3", "met primary endpoint"]),
    ("contract",     0.92, ["contract", "order worth", "awarded", "wins ", " win ", "selected by",
                            "purchase order", "deal with", "framework agreement", "tender"]),
    ("guidance",     0.88, ["raises guidance", "raised guidance", "lifts outlook", "boosts outlook",
                            "record revenue", "record quarter", "beats", "tops estimates",
                            "upgrades guidance", "raises forecast", "raises fy"]),
    ("mna",          0.82, ["to acquire", "acquisition", "acquires", "merger", "to merge",
                            "takeover", "buyout", "strategic review", "to be acquired"]),
    ("partnership",  0.72, ["partnership", "collaboration", "strategic partner", "to launch",
                            "launches", "expansion into", "joint venture", "distribution agreement"]),
    ("capital_ret",  0.66, ["buyback", "repurchase", "special dividend", "tender offer",
                            "increases dividend", "raises dividend"]),
    ("earnings",     0.60, ["quarterly results", "reports q", "earnings", "half-year results",
                            "fiscal year results", "trading update", "interim results"]),
    ("analyst",      0.52, ["upgrade", "initiates coverage", "price target raised", "raised to buy",
                            "outperform", "overweight"]),
    ("soft",         0.20, ["presents at", "to present", "conference", "webcast", "investor day",
                            "fireside", "appoints", "names ceo", "hires"]),
]
NEGATIVE = ["offering", "registered direct", "priced ", "prices $", "dilut", "going concern",
            "lawsuit", "investigation", "probe", "recall", "delay", "resignation", "downgrade",
            "cuts guidance", "lowers outlook", "profit warning", "short report"]


def _key():
    return open(KEYFILE).read().strip()


def _get(endpoint, params, key, retries=3):
    params = dict(params); params["apikey"] = key
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.0 * (a + 1))
    return None


def classify(text):
    t = (text or "").lower()
    for cls, mag, kws in CLASSES:
        if any(k in t for k in kws):
            return cls, mag
    return None, 0.0


def catalyst_for(ticker, key, window):
    pr = _get("news/press-releases", {"symbols": ticker, "limit": 20}, key) or []
    nw = _get("news/stock", {"symbols": ticker, "limit": 20}, key) or []
    best_mag = 0.0; best_type = None; neg = 0; days_since = None; from_pr = False
    for src, items in (("pr", pr), ("news", nw)):
        for it in items:
            dt = it.get("publishedDate")
            try:
                d = datetime.fromisoformat(dt.replace("Z", "")).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            age = (NOW - d).days
            if age < 0 or age > window:
                continue
            title = (it.get("title") or "") + " " + (it.get("text") or "")[:300]
            tl = title.lower()
            if any(k in tl for k in NEGATIVE):
                neg = 1
            cls, mag = classify(title)
            if src == "pr":
                mag *= 1.10                       # company-issued = more material
            if mag > best_mag:
                best_mag = min(mag, 1.0); best_type = cls
                days_since = age; from_pr = (src == "pr")
    return {"ticker": ticker, "catalyst_magnitude": round(best_mag, 3),
            "catalyst_type": best_type, "catalyst_verified": int(best_mag >= 0.6),
            "catalyst_negative": neg, "catalyst_days_since": days_since,
            "catalyst_from_pr": int(from_pr)}


def main():
    window = 14
    if "--window" in sys.argv:
        window = int(sys.argv[sys.argv.index("--window") + 1])
    key = _key()
    if "--universe" in sys.argv:
        tickers = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
    elif "--all" in sys.argv:
        tickers = [f[:-5].replace("__", "/") for f in os.listdir("/tmp/fmp_cache")]
    else:
        ig = pd.read_csv("/tmp/ignition_rank.csv")
        tickers = ig[ig.ignition > 0].ticker.astype(str).tolist()
    print(f"catalyst check: {len(tickers)} tickers, window {window}d", file=sys.stderr)
    rows = []
    for i, t in enumerate(tickers):
        rows.append(catalyst_for(t, key, window))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(tickers)}", file=sys.stderr)
        time.sleep(0.03)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    df.to_csv(DELIVER, index=False)
    v = int(df.catalyst_verified.sum())
    print(f"done: {v}/{len(df)} catalyst-verified; "
          f"types: {df[df.catalyst_verified==1].catalyst_type.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
