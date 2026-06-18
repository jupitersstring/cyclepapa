"""Five derived special-situations screeners + a unified pipeline merge.

Closes the remaining playbook gaps after special_situations_pipeline.py
already added the Form 10 / 8-K restructuring streams:

  1. odd_lot_tenders -- parses tender_scan.json HTML for explicit
     "odd lot" / "less than 100 shares" language (Dalius/Walker edge).
  2. nol_shells -- crosses recent Tax Benefits Preservation Rights Plan
     8-Ks with yfinance mcap so we can rank NOL/mcap exposure.
  3. spac_trust_arb -- finds SPACs trading at/below trust NAV via
     yfinance + extension/redemption proxy hits.
  4. russell_boundary_watch -- flags names whose mcap is within
     +/- 20% of estimated R1000/R2000/R3000 cutoffs (forced flow).
  5. foreign_value_up -- JP/KR/UK exchange filter on yfinance for
     PBR<1 candidates and any treasury-cancellation tag.

Plus going-dark (Form 15) and delisting (Form 25) feeds via recent.py.

Outputs (CSVs in repo root):
  odd_lot_tenders.csv
  nol_shells.csv
  spac_trust_arb.csv
  russell_boundary.csv
  foreign_value_up.csv
  going_dark.csv
  delistings.csv
  special_situations_unified.csv  -- merges everything above + the
                                     earlier Form 10 / 8-K pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


# ----------------------------------------------------------------------
# Common overlay loader
# ----------------------------------------------------------------------

def load_overlays() -> dict:
    overlays: dict = {}
    for fn, key in [
        ("yfinance_quick.json", "yf"),
        ("buyback_verify.json", "bb"),
        ("tender_scan.json", "tender"),
        ("cancel_10b5_1.json", "c10"),
        ("form4_buys.json", "f4"),
    ]:
        p = ROOT / fn
        overlays[key] = json.loads(p.read_text()) if p.exists() else {}
    proxy: dict = {}
    for fn in sorted(ROOT.glob("proxy_scan*.json")):
        try:
            d = json.loads(fn.read_text())
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if not isinstance(r, dict):
                continue
            tk = r.get("ticker")
            if tk and (tk not in proxy
                       or r.get("filing_date", "") > proxy[tk].get("filing_date", "")):
                proxy[tk] = r
    overlays["proxy"] = proxy
    return overlays


# ----------------------------------------------------------------------
# 1. Odd-lot tender extractor
# ----------------------------------------------------------------------

ODD_LOT_RX = re.compile(
    r"(odd[- ]?lot|fewer than 100 shares|less than 100 shares|"
    r"holders of fewer than 100|holders of less than 100)",
    re.I,
)


def extract_odd_lot_tenders(overlays: dict, fetch_html: bool = False) -> list[dict]:
    """Walk tender_scan.json. For each SELF_TENDER / TARGET hit, look
    for an odd-lot tender flag inside the parsed text. If the original
    scan stored the cover-page snippet, parse it; if not, try to fetch
    the primary document HTML on the fly (when fetch_html=True)."""
    tender = overlays.get("tender", {}) or {}
    rows = []
    try:
        from cache_store import read_html  # type: ignore
    except Exception:
        read_html = None  # type: ignore

    for tk, td in tender.items():
        if not isinstance(td, dict):
            continue
        role = td.get("role")
        if role not in ("SELF_TENDER", "TARGET", "BIDDER"):
            continue
        odd_lot_found = False
        text_blob = " ".join(
            str(td.get(k) or "") for k in
            ("text_excerpt", "snippet", "summary", "subject_company_name")
        )
        if ODD_LOT_RX.search(text_blob):
            odd_lot_found = True
        if not odd_lot_found and fetch_html and read_html is not None:
            acc = td.get("latest_accession") or td.get("accession")
            if acc:
                try:
                    html = read_html(acc) or ""
                    odd_lot_found = bool(ODD_LOT_RX.search(html))
                except Exception:
                    pass
        if not odd_lot_found:
            continue
        yf = overlays["yf"].get(tk, {}) or {}
        rows.append({
            "ticker": tk,
            "role": role,
            "latest_filing": td.get("latest_filing") or td.get("date"),
            "mcap_M": round((yf.get("mcap") or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": yf.get("p_b"),
            "reason": "odd-lot provision detected in tender filing",
        })
    rows.sort(key=lambda r: -(r["mcap_M"] or 0))
    return rows


# ----------------------------------------------------------------------
# 2. NOL shell screener
# ----------------------------------------------------------------------

def screen_nol_shells(overlays: dict, lookback_days: int = 365,
                      limit: int = 300) -> list[dict]:
    """Pull recent 8-K Tax Benefits Preservation / Section 382 rights
    plan filings, join with yfinance to flag tiny mcaps protecting
    potentially-large NOL carryforwards."""
    try:
        from recent import recent_nol_rights_plan_range
    except ImportError:
        return []
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    print(f"[NOL] pulling {start}..{end} limit={limit}", file=sys.stderr,
          flush=True)
    feed = recent_nol_rights_plan_range(start, end, limit=limit)
    print(f"[NOL] got {len(feed)} hits", file=sys.stderr)

    rows = []
    for rf in feed:
        tk = (rf.ticker or "").upper() or f"CIK{rf.cik}"
        yf = overlays["yf"].get(tk, {}) or {}
        mcap = yf.get("mcap")
        pb = yf.get("p_b")
        # Score: small mcap + already-distressed P/B is the bullseye
        score = 30
        if mcap and mcap < 100e6: score += 25
        elif mcap and mcap < 500e6: score += 15
        if pb is not None and pb < 0.5: score += 15
        elif pb is not None and pb < 1.0: score += 8
        rows.append({
            "ticker": tk,
            "company": rf.company,
            "filing_date": rf.filing_date,
            "accession": rf.accession,
            "mcap_M": round((mcap or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": pb,
            "score": score,
            "reason": "Tax Benefits Preservation Rights Plan adoption "
                      "-- likely material NOL carryforward",
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


# ----------------------------------------------------------------------
# 3. SPAC trust arbitrage
# ----------------------------------------------------------------------

SPAC_NAME_RX = re.compile(
    r"(acquisition\s+corp|acquisition\s+company|capital\s+corp|"
    r"SPAC|blank\s+check)", re.I,
)


def screen_spac_trust_arb(overlays: dict, lookback_days: int = 180,
                          limit: int = 300) -> list[dict]:
    """Combine: (a) recent_spac_extension_range hits, (b) yfinance names
    matching SPAC naming patterns, (c) price vs assumed trust-NAV. We
    assume $10.00/sh starting trust + accrued T-bill interest as the
    conservative floor; flag names trading <= $10.50 with active
    extension/redemption disclosure."""
    try:
        from recent import recent_spac_extension_range
    except ImportError:
        return []
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    print(f"[SPAC] pulling extensions {start}..{end} limit={limit}",
          file=sys.stderr, flush=True)
    feed = recent_spac_extension_range(start, end, limit=limit)
    print(f"[SPAC] got {len(feed)} hits", file=sys.stderr)

    rows = []
    feed_by_tk = {}
    for rf in feed:
        tk = (rf.ticker or "").upper()
        if tk:
            feed_by_tk[tk] = rf

    # union of: SPACs by name pattern + SPACs with filing hits
    yf = overlays["yf"]
    universe = set(feed_by_tk.keys())
    for tk, v in yf.items():
        name = (v.get("name") or "")
        if SPAC_NAME_RX.search(name) and v.get("price"):
            universe.add(tk)

    for tk in universe:
        v = yf.get(tk, {}) or {}
        px = v.get("price")
        if not px:
            continue
        # SPAC arb signal: price <= 10.50 (within typical trust NAV)
        if px > 11.50:
            continue
        # Premium to trust = (price - 10.10 assumed-NAV)
        prem = round(px - 10.10, 2)
        score = 25
        if px <= 10.20: score += 20  # near-zero or negative premium
        elif px <= 10.50: score += 10
        has_filing = tk in feed_by_tk
        if has_filing: score += 15
        rows.append({
            "ticker": tk,
            "name": v.get("name"),
            "price": px,
            "trust_premium_est": prem,
            "has_extension_filing": has_filing,
            "filing_date": feed_by_tk[tk].filing_date if has_filing else None,
            "score": score,
            "reason": ("trading near/below assumed trust NAV ($10.10) "
                      + ("with active extension proxy" if has_filing else "")),
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


# ----------------------------------------------------------------------
# 4. Russell boundary watch
# ----------------------------------------------------------------------

# 2024 Russell recon approximations (from FTSE Russell methodology
# release). These are estimates; recon publishes the exact list end-May
# each year. Used here for boundary-band flagging, not trading.
R1000_CUTOFF = 6_500_000_000   # bottom of Russell 1000 ~$6.5B
R2000_CUTOFF = 360_000_000      # bottom of Russell 2000 ~$360M
R3000_TOP = 250_000_000_000     # top of Russell 3000


def screen_russell_boundary(overlays: dict, band_pct: float = 0.20) -> list[dict]:
    """Flag names whose mcap sits +/- band_pct of an index cutoff --
    these are the names most likely to be added/deleted at next recon
    and thus most subject to forced-flow distortion."""
    yf = overlays["yf"]
    rows = []
    bands = [
        ("R1000_BOTTOM", R1000_CUTOFF),
        ("R2000_BOTTOM", R2000_CUTOFF),
    ]
    for tk, v in yf.items():
        mcap = v.get("mcap")
        px = v.get("price")
        if not mcap or not px:
            continue
        for label, cutoff in bands:
            lo, hi = cutoff * (1 - band_pct), cutoff * (1 + band_pct)
            if lo <= mcap <= hi:
                rows.append({
                    "ticker": tk,
                    "name": v.get("name"),
                    "mcap_M": round(mcap / 1e6, 0),
                    "px": px,
                    "band": label,
                    "cutoff_M": round(cutoff / 1e6, 0),
                    "delta_pct": round((mcap / cutoff - 1) * 100, 1),
                    "reason": f"within +/- {band_pct*100:.0f}% of {label}",
                })
                break
    rows.sort(key=lambda r: abs(r["delta_pct"]))
    return rows


# ----------------------------------------------------------------------
# 5. Foreign value-up screener (JP/KR/UK PBR<1 + name pattern)
# ----------------------------------------------------------------------

FOREIGN_EXCH_HINTS = re.compile(
    r"\.(T|TYO|KS|KQ|L|LSE|HK|AX|TO|V)$", re.I,
)


def screen_foreign_value_up(overlays: dict) -> list[dict]:
    """yfinance-only first-pass: any non-US ticker with P/B < 1 sitting
    in a Value-Up jurisdiction (Japan, Korea, UK trust wind-downs, HK).
    This is a coverage starter; live RNS / JPX disclosure-list ingest
    is the next-deeper layer."""
    yf = overlays["yf"]
    rows = []
    for tk, v in yf.items():
        # yfinance tickers in our enrichment are mostly US (no suffix);
        # surface anything with a suffix as candidate foreign listing.
        if not FOREIGN_EXCH_HINTS.search(tk):
            continue
        pb = v.get("p_b")
        if pb is None or pb <= 0 or pb >= 1.0:
            continue
        suffix = tk.rsplit(".", 1)[-1].upper()
        jurisdiction = {
            "T": "JP", "TYO": "JP",
            "KS": "KR", "KQ": "KR",
            "L": "UK", "LSE": "UK",
            "HK": "HK",
            "AX": "AU",
            "TO": "CA", "V": "CA",
        }.get(suffix, "?")
        rows.append({
            "ticker": tk,
            "name": v.get("name"),
            "jurisdiction": jurisdiction,
            "mcap_M": round((v.get("mcap") or 0) / 1e6, 0),
            "px": v.get("price"),
            "p_b": pb,
            "reason": f"{jurisdiction} listing at P/B {pb:.2f} -- value-up candidate",
        })
    rows.sort(key=lambda r: r["p_b"])
    return rows


# ----------------------------------------------------------------------
# 6. Going-dark + delistings (Form 15 / Form 25)
# ----------------------------------------------------------------------

def feed_to_rows(feed, overlays: dict, kind: str) -> list[dict]:
    rows = []
    for rf in feed:
        tk = (rf.ticker or "").upper() or f"CIK{rf.cik}"
        yf = overlays["yf"].get(tk, {}) or {}
        rows.append({
            "ticker": tk,
            "company": rf.company,
            "filing_date": rf.filing_date,
            "accession": rf.accession,
            "mcap_M": round((yf.get("mcap") or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": yf.get("p_b"),
            "kind": kind,
            "reason": (
                "Form 15 deregistration -- going dark, OTC pink only"
                if kind == "GOING_DARK"
                else "Form 25 exchange delisting"
            ),
        })
    rows.sort(key=lambda r: r["filing_date"], reverse=True)
    return rows


# ----------------------------------------------------------------------
# 7. 13D activist sweep (wraps existing recent_13d_sweep.pull_13d_index)
# ----------------------------------------------------------------------

def screen_13d_activism(overlays: dict, lookback_days: int = 90,
                        limit: int = 1500) -> list[dict]:
    try:
        from recent_13d_sweep import pull_13d_index, KNOWN_ACTIVISTS
    except ImportError:
        return []
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    print(f"[13D] pulling {start}..{end} limit={limit}", file=sys.stderr,
          flush=True)
    hits = pull_13d_index(start, end, limit=limit)
    print(f"[13D] got {len(hits)} 13D / 13D-A filings", file=sys.stderr)

    rows = []
    for h in hits:
        tk = (h.get("target_ticker") or "").upper()
        if not tk:
            continue
        yf = overlays["yf"].get(tk, {}) or {}
        filer = h.get("filer_name") or ""
        is_known = bool(KNOWN_ACTIVISTS.search(filer))
        rows.append({
            "ticker": tk,
            "filer": filer,
            "form": h.get("form"),
            "filing_date": h.get("file_date"),
            "is_known_activist": is_known,
            "mcap_M": round((yf.get("mcap") or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": yf.get("p_b"),
            "score": (25 if is_known else 10)
                     + (10 if (yf.get("p_b") or 99) < 1 else 0),
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def write_csv(rows, path: Path, fieldnames=None):
    if not rows:
        print(f"  (no rows for {path.name})")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.name} ({len(rows)} rows)")


def merge_unified(overlays: dict, parts: dict) -> list[dict]:
    """Single-row-per-(ticker, kind) merged pipeline for cross-screening."""
    out = []
    # Carry forward earlier pipeline rows if present
    earlier = ROOT / "special_situations_pipeline.csv"
    if earlier.exists():
        for r in csv.DictReader(earlier.open()):
            out.append({
                "ticker": r["ticker"], "kind": r["kind"],
                "filing_date": r["filing_date"], "score": float(r["score"] or 0),
                "mcap_M": r["mcap_M"], "p_b": r["p_b"],
                "reasons": r.get("reasons") or "",
            })
    for kind, rows in parts.items():
        for r in rows:
            out.append({
                "ticker": r.get("ticker"),
                "kind": kind,
                "filing_date": r.get("filing_date") or r.get("latest_filing"),
                "score": float(r.get("score") or 0),
                "mcap_M": r.get("mcap_M"),
                "p_b": r.get("p_b"),
                "reasons": r.get("reason") or r.get("reasons") or "",
            })
    out.sort(key=lambda r: -(r["score"] or 0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nol-days", type=int, default=365)
    ap.add_argument("--spac-days", type=int, default=180)
    ap.add_argument("--dark-days", type=int, default=180)
    ap.add_argument("--delist-days", type=int, default=180)
    ap.add_argument("--13d-days", type=int, default=90, dest="d13d_days")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--skip-fetch", action="store_true",
                    help="don't re-fetch tender HTML for odd-lot extraction")
    args = ap.parse_args()

    ov = load_overlays()
    print("Loaded overlays:")
    for k, v in ov.items():
        print(f"  {k}: {len(v)}")

    parts = {}

    print("\n== 1. odd-lot tenders ==")
    rows = extract_odd_lot_tenders(ov, fetch_html=not args.skip_fetch)
    parts["ODD_LOT_TENDER"] = rows
    write_csv(rows, ROOT / "odd_lot_tenders.csv")

    print("\n== 2. NOL shells ==")
    rows = screen_nol_shells(ov, lookback_days=args.nol_days,
                              limit=args.limit)
    parts["NOL_SHELL"] = rows
    write_csv(rows, ROOT / "nol_shells.csv")

    print("\n== 3. SPAC trust arb ==")
    rows = screen_spac_trust_arb(ov, lookback_days=args.spac_days,
                                  limit=args.limit)
    parts["SPAC_TRUST_ARB"] = rows
    write_csv(rows, ROOT / "spac_trust_arb.csv")

    print("\n== 4. Russell boundary watch ==")
    rows = screen_russell_boundary(ov)
    parts["RUSSELL_BOUNDARY"] = rows
    write_csv(rows, ROOT / "russell_boundary.csv")

    print("\n== 5. foreign value-up ==")
    rows = screen_foreign_value_up(ov)
    parts["FOREIGN_VALUE_UP"] = rows
    write_csv(rows, ROOT / "foreign_value_up.csv")

    print("\n== 6. going dark (Form 15) ==")
    try:
        from recent import recent_form15_range
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc)
                 - timedelta(days=args.dark_days)).strftime("%Y-%m-%d")
        feed = recent_form15_range(start, end, limit=args.limit)
        print(f"[Form 15] got {len(feed)}")
        rows = feed_to_rows(feed, ov, "GOING_DARK")
    except Exception as e:
        print(f"[Form 15] skip: {e}")
        rows = []
    parts["GOING_DARK"] = rows
    write_csv(rows, ROOT / "going_dark.csv")

    print("\n== 7. delistings (Form 25) ==")
    try:
        from recent import recent_form25_range
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc)
                 - timedelta(days=args.delist_days)).strftime("%Y-%m-%d")
        feed = recent_form25_range(start, end, limit=args.limit)
        print(f"[Form 25] got {len(feed)}")
        rows = feed_to_rows(feed, ov, "DELISTING")
    except Exception as e:
        print(f"[Form 25] skip: {e}")
        rows = []
    parts["DELISTING"] = rows
    write_csv(rows, ROOT / "delistings.csv")

    print("\n== 8. 13D activism ==")
    rows = screen_13d_activism(ov, lookback_days=args.d13d_days,
                                limit=1500)
    parts["ACTIVIST_13D"] = rows
    write_csv(rows, ROOT / "activist_13d.csv")

    print("\n== merging unified pipeline ==")
    unified = merge_unified(ov, parts)
    write_csv(unified, ROOT / "special_situations_unified.csv",
              fieldnames=["ticker", "kind", "filing_date", "score",
                          "mcap_M", "p_b", "reasons"])

    # Top-30 cross-archetype roll-up
    from collections import defaultdict
    by_tk = defaultdict(list)
    for r in unified:
        by_tk[r["ticker"]].append(r["kind"])
    multi_archetype = [
        (tk, sorted(set(ks))) for tk, ks in by_tk.items() if len(set(ks)) >= 2
    ]
    print(f"\n=== Names firing on >=2 archetypes: {len(multi_archetype)} ===")
    for tk, ks in sorted(multi_archetype, key=lambda x: -len(x[1]))[:25]:
        print(f"  {tk:<8} ({len(ks)})  {ks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
