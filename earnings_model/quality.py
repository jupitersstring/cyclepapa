"""Data-quality guardrails applied to the assembled table before scoring.

Two issues that put wrong names in the shortlists, both caught the hard way:

* **Duplicate payloads** — Yahoo serves byte-identical statements for several
  symbols (renamed/merged/related tickers, e.g. ONT carrying Montrose's numbers).
  ``metrics.compute_metrics`` stamps each row with a ``payload_fp`` fingerprint of
  its statement values; here we keep one symbol per fingerprint and flag the rest
  ``dup_payload`` so the screens drop them.
* **Return artifacts** — split/adjustment glitches produce trailing returns of
  +10,000% or −99% that silently drive the dormancy leg. We quarantine returns
  whose magnitude exceeds ``config.RETURN_SANITY_ABS`` to NaN (→ neutral rank).
"""
from __future__ import annotations

import pandas as pd

from . import config

_RETURN_COLS = ["ret_1m", "ret_3m", "ret_6m", "ret_12m", "ret_24m", "ret_36m"]


def flag_duplicate_payloads(df: pd.DataFrame) -> pd.DataFrame:
    """Add a boolean ``dup_payload`` — True for every row sharing a statement
    fingerprint with a kept primary. The primary kept per fingerprint is the
    largest market cap (the real listing), tie-broken by shortest symbol."""
    out = df.copy()
    out["dup_payload"] = False
    if "payload_fp" not in out.columns:
        return out
    fp = out["payload_fp"]
    dup_mask = fp.notna() & fp.duplicated(keep=False)
    if not dup_mask.any():
        return out
    cap = pd.to_numeric(out.get("marketCap"), errors="coerce").fillna(-1)
    sym_len = out["symbol"].astype(str).str.len() if "symbol" in out.columns else 0
    # Rank within each fingerprint group: keep the best (rank 0), flag the rest.
    order = pd.DataFrame({"cap": cap, "sym_len": sym_len, "fp": fp})
    order = order[dup_mask].sort_values(["cap", "sym_len"], ascending=[False, True])
    keep_idx = order.groupby("fp", sort=False).head(1).index
    out.loc[dup_mask, "dup_payload"] = True
    out.loc[out.index.isin(keep_idx), "dup_payload"] = False
    return out


def quarantine_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Null trailing returns whose magnitude exceeds the sanity bound (split
    artifacts / near-zero-base penny moves). Records the count quarantined."""
    out = df.copy()
    bound = config.RETURN_SANITY_ABS
    bad_total = 0
    for c in _RETURN_COLS:
        if c in out.columns:
            col = pd.to_numeric(out[c], errors="coerce")
            bad = col.abs() > bound
            bad_total += int(bad.sum())
            out.loc[bad, c] = pd.NA
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out.attrs["returns_quarantined"] = bad_total
    return out


def apply_quality_flags(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Run all guardrails. Call on the assembled fundamentals table *before*
    scoring so ranks/dormancy are computed on clean inputs."""
    out = quarantine_returns(df)
    out = flag_duplicate_payloads(out)
    if verbose:
        n_dup = int(out.get("dup_payload", pd.Series(dtype=bool)).sum())
        n_ret = out.attrs.get("returns_quarantined", 0)
        print(f"quality: {n_dup} duplicate-payload rows flagged, "
              f"{n_ret} return outliers quarantined")
    return out
