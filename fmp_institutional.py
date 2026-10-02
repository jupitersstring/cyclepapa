"""13F institutional ownership trajectory per US-listed symbol -> fmp_institutional.csv.

Feeds arch_institutional_accumulation: institutions adding while the price is
flat or falling, with extra credit when the ownership share or the buying is
ACCELERATING. Uses FMP institutional-ownership/symbol-positions-summary for
the three most recent complete 13F quarters. Each quarter's summary already
carries its change versus the prior quarter, so three quarters give three
changes: enough for direction, persistence and acceleration.

13F covers US exchange-listed securities (including ADRs), so the scope is
the US-style tickers in the universe. Resumable via CSV checkpoint.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_institutional.csv"
N_QUARTERS = 3


def recent_quarters(today: dt.date | None = None, n: int = N_QUARTERS) -> list[tuple[int, int]]:
    """Most recent n COMPLETE 13F quarters (filing deadline = quarter end + 45d;
    we wait 50d so late filers are in)."""
    today = today or dt.date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    while len(out) < n:
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        q_end = dt.date(y, 3 * q, 30 if q in (2, 3) else 31)
        if (today - q_end).days >= 50:
            out.append((y, q))
    return out


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def enrich_symbol(sym: str, quarters: list[tuple[int, int]]) -> dict:
    rec: dict = {"symbol": sym}
    rows = []
    for (y, q) in quarters:
        d = fc.get_json("institutional-ownership/symbol-positions-summary",
                        {"symbol": sym, "year": y, "quarter": q}, ttl=fc.TTL_SLOW)
        rows.append(d[0] if d else None)
    if not rows or rows[0] is None:
        return rec
    rec["fmp_inst_quarter"] = f"{quarters[0][0]}Q{quarters[0][1]}"
    cur = rows[0]
    rec["fmp_inst_holders"] = _f(cur.get("investorsHolding"))
    rec["fmp_inst_own_pct"] = _f(cur.get("ownershipPercent"))
    rec["fmp_inst_put_call"] = _f(cur.get("putCallRatio"))
    rec["fmp_inst_holders_chg_q0"] = _f(cur.get("investorsHoldingChange"))
    for i, r in enumerate(rows):
        if r is None:
            continue
        last_sh = _f(r.get("lastNumberOf13Fshares"))
        sh_chg = _f(r.get("numberOf13FsharesChange"))
        rec[f"fmp_inst_own_chg_q{i}"] = _f(r.get("ownershipPercentChange"))
        rec[f"fmp_inst_shares_chg_pct_q{i}"] = (sh_chg / last_sh) if (math.isfinite(sh_chg) and math.isfinite(last_sh) and last_sh > 0) else np.nan
        buyers = _f(r.get("newPositions")) + _f(r.get("increasedPositions"))
        sellers = _f(r.get("reducedPositions")) + _f(r.get("closedPositions"))
        rec[f"fmp_inst_new_q{i}"] = _f(r.get("newPositions"))
        if math.isfinite(buyers) and math.isfinite(sellers) and buyers + sellers > 0:
            rec[f"fmp_inst_buy_ratio_q{i}"] = buyers / (buyers + sellers)
    # direction, persistence, acceleration
    sh = [rec.get(f"fmp_inst_shares_chg_pct_q{i}") for i in range(N_QUARTERS)]
    own = [rec.get(f"fmp_inst_own_chg_q{i}") for i in range(N_QUARTERS)]
    br = [rec.get(f"fmp_inst_buy_ratio_q{i}") for i in range(N_QUARTERS)]
    rec["fmp_inst_accum_quarters"] = float(sum(1 for v in sh if v is not None and math.isfinite(v) and v > 0))
    if all(v is not None and math.isfinite(v) for v in own[:2]):
        rec["fmp_inst_own_accel"] = own[0] - own[1]
    if all(v is not None and math.isfinite(v) for v in sh[:2]):
        rec["fmp_inst_purchase_accel"] = sh[0] - sh[1]
    if all(v is not None and math.isfinite(v) for v in br[:2]):
        rec["fmp_inst_buyer_breadth_accel"] = br[0] - br[1]
    return rec


def _flush(rows):
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(OUT):
        both = pd.concat([pd.read_csv(OUT, low_memory=False), new],
                         ignore_index=True).drop_duplicates("symbol", keep="last")
    else:
        both = new
    both.to_csv(OUT + ".tmp", index=False)
    os.replace(OUT + ".tmp", OUT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--checkpoint-every", type=int, default=200)
    ap.add_argument("--gc-max-mb", type=int, default=2000)
    args = ap.parse_args()
    quarters = recent_quarters()
    t = pd.read_csv("archetype_tags.csv", usecols=lambda c: c in {"symbol", "archetype_count"},
                    low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    t = t[~t["symbol"].str.contains(r"\.", regex=True)]          # US-listed (13F scope)
    t["archetype_count"] = pd.to_numeric(t["archetype_count"], errors="coerce").fillna(0)
    syms = t.sort_values("archetype_count", ascending=False)["symbol"].tolist()
    if args.max:
        syms = syms[: args.max]
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    print(f"institutional quarters={quarters}: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    rows = []
    for i, sym in enumerate(todo, 1):
        try:
            rows.append(enrich_symbol(sym, quarters))
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                print(f"  rate limited at {i}; checkpointing", flush=True)
                break
            rows.append({"symbol": sym})
        if i % args.checkpoint_every == 0:
            _flush(rows); rows = []
            st = fc.cache_stats()
            print(f"  institutional {i}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    _flush(rows)
    n = len(pd.read_csv(OUT)) if os.path.exists(OUT) else 0
    print(f"\nwrote {OUT}: {n} rows", flush=True)


if __name__ == "__main__":
    main()
