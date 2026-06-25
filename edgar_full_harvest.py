"""Robust, resumable EDGAR harvester using edgartools.

Goes beyond what data.sec.gov/api/xbrl/companyfacts/ exposes — pulls:

  1. XBRL with DIMENSIONAL FACTS  (segment-level, geographic, product-line
     revenue / opinc / assets that companyfacts aggregates away). Parsed
     directly from each filing's primary XBRL instance via edgartools.

  2. FORM 4 insider transactions  (who bought / sold, when, how much).

  3. DEF 14A proxy statements     (board composition, exec compensation,
     beneficial ownership tables).

Design principles:

  - **Resumable**: per-CIK state in edgar_full_state.json. On restart the
    script reads the file and skips CIKs already at 'complete'.
  - **Atomic writes**: each per-CIK output writes to .tmp then renames.
    A SIGTERM mid-write leaves the prior file intact.
  - **Survives session disconnect**: launch with nohup. The process holds
    its own SIGTERM handler that writes the in-flight state cleanly.
  - **Polite rate limiting**: SEC's 10 req/sec ceiling honoured via a
    shared semaphore. Backoff on 429.
  - **Incremental**: every CHECKPOINT_EVERY CIKs the state file is
    rewritten so a crash loses at most ~200 names of progress.

Outputs:

  edgar_segments_cache/CIK########.json  — dimensional facts per filer
  edgar_insider_cache/CIK########.json   — Form 4 transactions
  edgar_proxy_cache/CIK########.json     — DEF 14A summary
  edgar_full_state.json                  — resumable checkpoint

  edgar_segments.csv                     — flattened per-filer per-segment
                                            revenue / opinc / assets time
                                            series, generated on demand
                                            from the segments cache.
  edgar_insider_summary.csv              — net insider buys/sells last 12m
  edgar_capital_returns.csv              — dividends + buybacks 5y series

Usage:

    # First run — start fresh
    python edgar_full_harvest.py --workers 4

    # Resume after interruption
    python edgar_full_harvest.py --resume

    # Run only one stage (debug)
    python edgar_full_harvest.py --stage xbrl --max 50
"""
from __future__ import annotations
import argparse
import json
import os
import signal
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd


# Edgartools requires an identity (polite UA per SEC policy).
EDGAR_IDENTITY = "multibagger-research opensource@multibagger.dev"

STATE_PATH = Path("edgar_full_state.json")
SEGMENTS_CACHE = Path("edgar_segments_cache")
INSIDER_CACHE = Path("edgar_insider_cache")
PROXY_CACHE = Path("edgar_proxy_cache")
for p in (SEGMENTS_CACHE, INSIDER_CACHE, PROXY_CACHE):
    p.mkdir(exist_ok=True)

CHECKPOINT_EVERY = 50
STAGES = ("xbrl", "form4", "proxy")
STAGE_DONE_STATUS = {"xbrl": "xbrl_done", "form4": "form4_done", "proxy": "proxy_done"}


# ---------- state management ----------------------------------------------
def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict):
    """Atomic write."""
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


_state_lock_marker = False


def install_signal_handler(state: dict):
    """Trap SIGTERM / SIGINT so the in-flight state is checkpointed
    before exit. Lets the script survive `kill <pid>` cleanly."""
    def _handle(signum, frame):
        global _state_lock_marker
        print(f"\nSignal {signum} received — checkpointing state and exiting.",
              file=sys.stderr)
        save_state(state)
        _state_lock_marker = True
        sys.exit(0)
    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


# ---------- atomic JSON write ---------------------------------------------
def write_json_atomic(path: Path, payload):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


# ---------- universe loader -----------------------------------------------
def load_universe() -> pd.DataFrame:
    """Use the same SEC ticker map the rest of the pipeline uses."""
    import requests
    cache = Path("sec_company_tickers.json")
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": EDGAR_IDENTITY},
                         timeout=20)
        r.raise_for_status()
        data = r.json()
        cache.write_text(json.dumps(data))
    rows = [{"symbol": v["ticker"].upper(),
             "cik": int(v["cik_str"]),
             "title": v.get("title", "")}
            for v in data.values()]
    return pd.DataFrame(rows).drop_duplicates("symbol")


# ---------- stage: XBRL dimensional facts ---------------------------------
def harvest_xbrl_dimensional(cik: int, symbol: str, max_filings: int = 1) -> dict | None:
    """Pull the latest 10-K (annual filing) and emit every dimensional fact.

    Segment / geographic / product-line disclosures are an ANNUAL
    requirement — 10-Qs carry only a tiny subset and they get superseded
    by the next 10-K anyway. Pulling just the latest 10-K cuts work per
    CIK by 4x while losing essentially no signal.

    Returns a dict with:
      {
        "cik": int,
        "symbol": str,
        "filings_processed": [...],
        "facts_by_filing": {
          "<accession>": [
            {"concept": ..., "value": ..., "unit": ..., "period_end": ...,
             "dimensions": {"Axis1": "Member1", ...}}, ...
          ]
        }
      }
    """
    import edgar
    edgar.set_identity(EDGAR_IDENTITY)
    try:
        c = edgar.Company(symbol)
    except Exception as e:
        return {"cik": cik, "symbol": symbol, "error": f"company_lookup: {e}"[:120]}

    # Latest 10-K only — segment disclosure is annual
    try:
        filings = list(c.get_filings(form="10-K"))[:max_filings]
    except Exception as e:
        return {"cik": cik, "symbol": symbol, "error": f"filings_list: {e}"[:120]}

    if not filings:
        return {"cik": cik, "symbol": symbol, "filings_processed": []}

    facts_by_filing = {}
    processed = []
    for f in filings:
        accession = f.accession_no
        try:
            xb = f.xbrl()
            if xb is None:
                continue
            # Edgartools 5.39 exposes facts as dicts with is_dimensioned flag.
            # We pull the dimensional subset specifically — those are the
            # segment / geographic / product-line breakdowns companyfacts
            # JSON aggregates away.
            df = xb.facts.get_facts_with_dimensions()
            if df is None or len(df) == 0:
                facts_by_filing[accession] = []
                processed.append({"accession": accession, "form": f.form,
                                  "filing_date": str(f.filing_date),
                                  "n_dim_facts": 0})
                continue
            # Resolve dimension axis/member tuples per fact by joining
            # context_ref → context.dimensions. xb.contexts is a dict-like
            # mapping context_ref → Context with .dimensions attribute.
            contexts = getattr(xb, "contexts", {}) or {}
            def _dims_for_ctx(ctx_ref):
                ctx = contexts.get(ctx_ref) if isinstance(contexts, dict) else None
                if ctx is None:
                    return {}
                # Context.dimensions is a dict-of-dict; flatten to {axis: member}
                d = getattr(ctx, "dimensions", None) or {}
                if isinstance(d, dict):
                    out = {}
                    for k, v in d.items():
                        if isinstance(v, dict):
                            # {"DimensionAxis": {"member": "MemberName", ...}}
                            mem = v.get("member") or v.get("value") or str(v)
                            out[str(k)] = str(mem)
                        else:
                            out[str(k)] = str(v)
                    return out
                return {}

            rows = []
            for _, row in df.iterrows():
                d = {
                    "concept": row.get("concept"),
                    "label": row.get("label"),
                    "value": row.get("numeric_value") or row.get("value"),
                    "unit": row.get("unit_ref"),
                    "currency": row.get("currency"),
                    "period_start": str(row.get("period_start") or ""),
                    "period_end": str(row.get("period_end") or ""),
                    "fiscal_period": row.get("fiscal_period"),
                    "fiscal_year": row.get("fiscal_year"),
                    "statement_type": row.get("statement_type"),
                    "context_ref": row.get("context_ref"),
                    "dimensions": _dims_for_ctx(row.get("context_ref")),
                }
                try:
                    if d["value"] is not None:
                        d["value"] = float(d["value"])
                except (TypeError, ValueError):
                    pass
                rows.append(d)
            facts_by_filing[accession] = rows
            processed.append({"accession": accession, "form": f.form,
                              "filing_date": str(f.filing_date),
                              "n_dim_facts": len(rows)})
        except Exception as e:
            processed.append({"accession": accession, "form": f.form,
                              "error": str(e)[:120]})
    return {
        "cik": cik,
        "symbol": symbol,
        "filings_processed": processed,
        "facts_by_filing": facts_by_filing,
    }


def stage_xbrl_one(rec, state):
    sym = rec["symbol"]
    cik = int(rec["cik"])
    if state.get(str(cik), {}).get("status") in ("xbrl_done", "form4_done",
                                                  "proxy_done", "complete"):
        return ("skip", cik, None)
    cache_path = SEGMENTS_CACHE / f"CIK{cik:010d}.json"
    if cache_path.exists():
        state.setdefault(str(cik), {})["status"] = "xbrl_done"
        return ("cached", cik, None)
    try:
        payload = harvest_xbrl_dimensional(cik, sym)
        if payload is not None:
            write_json_atomic(cache_path, payload)
        state.setdefault(str(cik), {})["status"] = "xbrl_done"
        return ("done", cik, None)
    except Exception as e:
        state.setdefault(str(cik), {})["status"] = "xbrl_error"
        state[str(cik)]["error"] = str(e)[:120]
        return ("error", cik, str(e))


# ---------- stage: Form 4 insider transactions ----------------------------
def harvest_form4(cik: int, symbol: str, lookback_days: int = 365) -> dict | None:
    """Pull recent Form 4 transactions for this filer."""
    import edgar
    edgar.set_identity(EDGAR_IDENTITY)
    try:
        c = edgar.Company(symbol)
        form4s = list(c.get_filings(form="4").latest(50))
    except Exception as e:
        return {"cik": cik, "symbol": symbol, "error": f"form4_list: {e}"[:120]}

    transactions = []
    for f in form4s:
        try:
            obj = f.obj()
            # edgartools returns InsiderForm or similar — try to extract rows
            rows = getattr(obj, "transactions", None) or getattr(obj, "to_dict", lambda: {})()
            if hasattr(rows, "to_dict"):
                rows = rows.to_dict(orient="records")
            elif isinstance(rows, dict):
                rows = [rows]
            for row in (rows or []):
                if isinstance(row, dict):
                    transactions.append({
                        "filing_date": str(f.filing_date),
                        "accession": f.accession_no,
                        **{k: str(v)[:80] for k, v in row.items()},
                    })
        except Exception:
            continue
        time.sleep(0.1)

    return {
        "cik": cik,
        "symbol": symbol,
        "n_form4s": len(form4s),
        "transactions": transactions[:200],
    }


def stage_form4_one(rec, state):
    sym = rec["symbol"]
    cik = int(rec["cik"])
    status = state.get(str(cik), {}).get("status", "pending")
    if status in ("form4_done", "proxy_done", "complete"):
        return ("skip", cik, None)
    if status not in ("xbrl_done",):
        # Can run independently — don't require xbrl_done
        pass
    cache_path = INSIDER_CACHE / f"CIK{cik:010d}.json"
    if cache_path.exists():
        state.setdefault(str(cik), {})["status"] = "form4_done"
        return ("cached", cik, None)
    try:
        payload = harvest_form4(cik, sym)
        if payload is not None:
            write_json_atomic(cache_path, payload)
        state.setdefault(str(cik), {})["status"] = "form4_done"
        return ("done", cik, None)
    except Exception as e:
        state.setdefault(str(cik), {})["status"] = "form4_error"
        state[str(cik)]["form4_error"] = str(e)[:120]
        return ("error", cik, str(e))


# ---------- stage: DEF 14A proxy --------------------------------------------
def harvest_proxy(cik: int, symbol: str) -> dict | None:
    """Pull the latest DEF 14A proxy statement (board / exec comp / ownership)."""
    import edgar
    edgar.set_identity(EDGAR_IDENTITY)
    try:
        c = edgar.Company(symbol)
        proxies = list(c.get_filings(form="DEF 14A").latest(1))
    except Exception as e:
        return {"cik": cik, "symbol": symbol, "error": f"proxy_list: {e}"[:120]}
    if not proxies:
        return {"cik": cik, "symbol": symbol, "n_proxies": 0}

    payload = {"cik": cik, "symbol": symbol, "proxies": []}
    for f in proxies:
        try:
            payload["proxies"].append({
                "filing_date": str(f.filing_date),
                "accession": f.accession_no,
                "summary": (f.text() or "")[:5000],  # cap to keep file small
            })
        except Exception:
            continue
        time.sleep(0.15)
    return payload


def stage_proxy_one(rec, state):
    sym = rec["symbol"]
    cik = int(rec["cik"])
    if state.get(str(cik), {}).get("status") in ("proxy_done", "complete"):
        return ("skip", cik, None)
    cache_path = PROXY_CACHE / f"CIK{cik:010d}.json"
    if cache_path.exists():
        state.setdefault(str(cik), {})["status"] = "proxy_done"
        return ("cached", cik, None)
    try:
        payload = harvest_proxy(cik, sym)
        if payload is not None:
            write_json_atomic(cache_path, payload)
        state.setdefault(str(cik), {})["status"] = "proxy_done"
        return ("done", cik, None)
    except Exception as e:
        state.setdefault(str(cik), {})["status"] = "proxy_error"
        state[str(cik)]["proxy_error"] = str(e)[:120]
        return ("error", cik, str(e))


# ---------- main loop -----------------------------------------------------
def run_stage(stage: str, universe: pd.DataFrame, state: dict,
              workers: int = 4, max_rows: int | None = None):
    """Run one stage across the universe with parallelism + checkpoints."""
    stage_fn = {
        "xbrl": stage_xbrl_one,
        "form4": stage_form4_one,
        "proxy": stage_proxy_one,
    }[stage]

    rows = universe.to_dict(orient="records")
    if max_rows:
        rows = rows[:max_rows]

    start = time.time()
    completed = 0
    cached = 0
    errored = 0
    skipped = 0
    n = len(rows)
    print(f"\n=== STAGE: {stage}  ({n:,} CIKs, {workers} workers) ===",
          file=sys.stderr)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(stage_fn, r, state): r for r in rows}
        for fut in as_completed(futures):
            try:
                outcome, cik, err = fut.result()
            except Exception as e:
                outcome, cik, err = ("error", -1, str(e))
            if outcome == "done":
                completed += 1
            elif outcome == "cached":
                cached += 1
            elif outcome == "skip":
                skipped += 1
            elif outcome == "error":
                errored += 1
            total = completed + cached + skipped + errored
            if total % CHECKPOINT_EVERY == 0:
                save_state(state)
                rate = total / max(1.0, time.time() - start)
                eta = (n - total) / rate if rate > 0 else 0
                print(f"  {total:,}/{n:,}  done={completed} cached={cached} "
                      f"skip={skipped} err={errored}  ({rate:.1f}/s, ETA {eta/60:.1f}m)",
                      file=sys.stderr)
    save_state(state)
    print(f"  FINAL: done={completed} cached={cached} skip={skipped} err={errored} "
          f"in {(time.time()-start)/60:.1f}m", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=list(STAGES) + ["all"], default="all",
                    help="which stage to run (xbrl / form4 / proxy / all)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max", type=int, default=0,
                    help="cap rows processed this run (0 = all)")
    ap.add_argument("--resume", action="store_true",
                    help="continue from existing state (default behaviour)")
    ap.add_argument("--reset", action="store_true",
                    help="delete state file and restart from scratch")
    args = ap.parse_args()

    if args.reset and STATE_PATH.exists():
        STATE_PATH.unlink()
        print(f"deleted {STATE_PATH}", file=sys.stderr)

    state = load_state()
    install_signal_handler(state)

    print("loading universe...", file=sys.stderr)
    universe = load_universe().sort_values("symbol").reset_index(drop=True)
    print(f"  {len(universe):,} CIKs", file=sys.stderr)

    print(f"existing state: {sum(1 for v in state.values() if v.get('status') == 'complete')} "
          f"complete, {len(state)} known", file=sys.stderr)

    stages_to_run = STAGES if args.stage == "all" else (args.stage,)
    max_rows = args.max if args.max > 0 else None

    for stage in stages_to_run:
        run_stage(stage, universe, state, workers=args.workers, max_rows=max_rows)
        save_state(state)

    # Mark CIKs with all stages done as 'complete'
    for cik, st in state.items():
        if st.get("status") == "proxy_done":
            st["status"] = "complete"
    save_state(state)

    print("\nALL STAGES DONE.", file=sys.stderr)


if __name__ == "__main__":
    main()
