"""The confirmation rule -- the strongest tail edge, made live.

The event study's single biggest discriminator was not a screen but a
TIMING RULE: names the market voted UP >20% within ~a month of the catalyst
tailed 60% of the time (4.0x the 15% base). Buying a catalyst blind is a
coin flip; buying it AFTER the market confirms is how you tilt into the
tail.

This module applies that rule to the live candidate set. For each name with
a corporate-action catalyst (rerate_catalysts), it anchors on the catalyst
DATE (most-recent mention across the MD&A / proxy / tender sources), pulls
the price, and measures the drift since:

  * CONFIRMED  -- >= 1 month since the catalyst AND price up >= +20% -> the
    market has voted; apply the +1m-up lift to the tail odds.
  * PENDING    -- < ~1 month since the catalyst; too soon to judge, watch.
  * FADING     -- price down since the catalyst; the market is voting no.
  * NEUTRAL    -- moved less than the +/-20% / -10% bands.

The confirmed tail odds re-score the tail_odds estimate in the same shrunk
log-odds space, so a CONFIRMED name's probability rises toward the 60%
observed rate and a FADING name's falls. Output: confirmation_rule.json.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import io_util
from rerate_backtest import (chart_monthly, _close_near, _drawdown_from_high,
                             _pre_vol, _range_pos, _trailing_return)

# Monster-rich catalysts from the greatest-trades study (>=+100%/12m rate) --
# note these are DIFFERENT from the median-best catalysts; several are
# lottery tickets with negative medians. For monster hunting they add
# convexity.
MONSTER_CATALYSTS = {"STRATEGIC_REVIEW", "SPINOFF", "CH11_EMERGENCE",
                     "UPLISTING", "ASSET_SALE"}

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "confirmation_rule.json"

CONFIRM_UP = 0.20        # market vote that counts as confirmation
FADE_DOWN = -0.10        # market vote that counts as fading
MIN_MONTHS = 1.0         # need at least a month for the vote to mean something
MAX_MONTHS = 18.0        # ignore stale catalysts
CONFIRM_LIFT = 4.0       # measured post_1m up>20% lift
FADE_LIFT = 0.7
SHRINK = 0.45


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def load_proxy_dates():
    dates = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.load(open(fn))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.values()):
            if isinstance(r, dict) and r.get("ticker") and r.get("filing_date"):
                tk = r["ticker"]
                if tk not in dates or r["filing_date"] > dates[tk]:
                    dates[tk] = r["filing_date"]
    return dates


def catalyst_date(tk, rer_rec, mda, proxy_dates, events8k):
    """Most-recent catalyst mention date across the name's sources. Prefers
    the 8-K announcement date (the cleanest anchor) when present."""
    cands = []
    srcs = rer_rec.get("sources_by_bucket", {})
    uses_incentive = any("incentive" in v for v in srcs.values())
    uses_narrative = any("narrative" in v for v in srcs.values())
    ev = events8k.get(tk) or {}
    for info in ev.values():
        if isinstance(info, dict) and info.get("date"):
            cands.append(info["date"])
    if uses_incentive and tk in proxy_dates:
        cands.append(proxy_dates[tk])
    if uses_narrative and tk in mda:
        for h in (mda[tk].get("hits") or {}).values():
            if h.get("date"):
                cands.append(h["date"])
    return max(cands) if cands else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=150,
                    help="Confirm the top-N candidates by tail odds / rerate.")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    rer = _load("rerate_catalysts.json")
    mda = _load("mda_scan.json")
    odds = _load("tail_odds.json")
    proxy_dates = load_proxy_dates()
    events8k = _load("rerate_events_8k.json")

    # rank candidates: prefer tail-odds, fall back to rerate_score.
    def rank_key(tk):
        o = odds.get(tk) or {}
        return (o.get("est_tail_prob") or 0, (rer.get(tk) or {}).get("rerate_score") or 0)
    cands = sorted(rer.keys(), key=rank_key, reverse=True)[:args.top]

    now = datetime.now(timezone.utc)
    out = {}
    priced = 0
    for tk in cands:
        cd = catalyst_date(tk, rer[tk], mda, proxy_dates, events8k)
        if not cd:
            continue
        try:
            t0 = datetime.strptime(cd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        months = (now - t0).days / 30.0
        if months > MAX_MONTHS or months < 0:
            continue
        series = chart_monthly(tk, "3y")
        time.sleep(args.sleep)
        priced += 1
        if not series:
            continue
        t0_ts = int(t0.timestamp())
        base_px = _close_near(series, t0_ts)
        now_px = series[-1][1] if series else None
        if not base_px or not now_px or base_px <= 0:
            continue
        drift = now_px / base_px - 1.0

        if months < MIN_MONTHS:
            state, lift = "PENDING", 1.0
        elif drift >= CONFIRM_UP:
            state, lift = "CONFIRMED", CONFIRM_LIFT
        elif drift <= FADE_DOWN:
            state, lift = "FADING", FADE_LIFT
        else:
            state, lift = "NEUTRAL", 1.0

        base_p = (odds.get(tk) or {}).get("est_tail_prob") or \
            (odds.get(tk) or {}).get("base_rate") or 0.15
        base_p = min(max(base_p, 1e-3), 0.75)
        base_odds = base_p / (1 - base_p)
        log_odds = math.log(base_odds) + SHRINK * math.log(lift)
        conf_p = 1.0 / (1.0 + math.exp(-log_odds))

        # MONSTER-SETUP fingerprint (greatest-trades study): the biggest
        # re-raters were violent, prolonged WASHOUTS at the catalyst date --
        # deep 24m drawdown, bottom of range, wild pre-event vol, decline just
        # decelerating -- carrying a monster-rich (lottery) catalyst. Measured
        # AT the catalyst date (t0), matching the study.
        dd24 = _drawdown_from_high(series, t0_ts, 24)
        pv = _pre_vol(series, t0_ts, 12)
        rp = _range_pos(series, t0_ts, 12)
        decel = (_trailing_return(series, t0_ts, 3) or 0) \
            - (_trailing_return(series, t0_ts, 12) or 0)
        ms = 0.0; ms_flags = []
        if dd24 is not None and dd24 <= -0.40:
            ms += 3; ms_flags.append(f"deep 24m washout ({dd24*100:.0f}%)")
        if pv is not None and pv >= 0.13:
            ms += 2; ms_flags.append(f"wild vol ({pv:.2f})")
        if rp is not None and rp <= 0.33:
            ms += 2; ms_flags.append("bottom of range")
        if decel >= 0.0:
            ms += 1; ms_flags.append("decelerating")
        cats = set((rer.get(tk) or {}).get("catalyst_types") or [])
        if cats & MONSTER_CATALYSTS:
            ms += 2; ms_flags.append("monster-rich catalyst")

        out[tk] = {
            "ticker": tk,
            "catalyst_date": cd,
            "months_since": round(months, 1),
            "drift_since_catalyst": round(drift, 3),
            "state": state,
            "tail_prob_base": round(base_p, 3),
            "tail_prob_confirmed": round(conf_p, 3),
            "monster_setup": round(ms, 1),
            "monster_flags": ms_flags,
            "drawdown_24m": round(dd24, 3) if dd24 is not None else None,
            "pre_vol": round(pv, 3) if pv is not None else None,
            "catalyst_types": rer[tk].get("catalyst_types"),
            "geometry_ratio": rer[tk].get("geometry_ratio"),
            "sector": rer[tk].get("sector"),
            "rerate_score": rer[tk].get("rerate_score"),
        }

    io_util.write_json(OUT, out)
    from collections import Counter
    c = Counter(v["state"] for v in out.values())
    print(f"confirmed {priced} candidates priced; states: {dict(c)}")
    conf = sorted((v for v in out.values() if v["state"] == "CONFIRMED"),
                  key=lambda r: -r["tail_prob_confirmed"])
    print(f"\n{'TKR':<7}{'STATE':<11}{'since':>6}{'drift':>8}{'tailP':>7}  CATALYSTS")
    for r in conf[:25]:
        print(f"{r['ticker']:<7}{r['state']:<11}{r['months_since']:>5.0f}m"
              f"{r['drift_since_catalyst']*100:>7.0f}%{r['tail_prob_confirmed']*100:>6.0f}%"
              f"  {', '.join(r['catalyst_types'] or [])}")
    # the monster-setup shortlist: the washout fingerprint, regardless of state.
    mons = sorted((v for v in out.values() if v["monster_setup"] >= 6),
                  key=lambda r: -r["monster_setup"])
    print(f"\nMONSTER SETUPS (washout fingerprint, score>=6): {len(mons)}")
    for r in mons[:20]:
        print(f"  {r['ticker']:<7}{r['monster_setup']:>5.1f}  {r['state']:<10}"
              f"  {'; '.join(r['monster_flags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
