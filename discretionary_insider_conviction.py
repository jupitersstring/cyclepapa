"""Discretionary insider-conviction leg.

A deliberately SELECTIVE read of open-market insider buying. The base
Form 4 layer (score_f4_layer) rewards any distinct-buyer count plus raw
dollar volume; the Cohen-Malloy layer isolates the opportunistic filers.
This leg is orthogonal to both: it asks *how convicted and how
clustered* the buying is, and rewards only the anomalous, high-signal
configurations that history says carry information.

Population -- form4_buys.json already contains ONLY transaction code P
(open-market purchases). It excludes code A (grants/awards) and code M
(option exercises) by construction (form4_buys_sweep.parse_form4 line
~166). So every buy here is discretionary cash out of pocket -- never an
RSU vest or an automatic acquisition.

What makes a buy score here (all additive, none subtracts from another
layer):

  1. CLUSTER QUALITY (Lakonishok-Lee).  Not just the count of distinct
     insiders, but their temporal concentration.  Several insiders buying
     within a tight window -- and especially on the SAME day -- is the
     canonical high-conviction cluster.  A lone director dribbling in
     over a year is not.  We compute the max distinct insiders inside a
     rolling CLUSTER_WINDOW_DAYS window, and the max distinct insiders on
     any single date.

  2. ROLE-WEIGHTED CONVICTION.  A CEO/CFO buys with the most information;
     a 10% holder may buy for portfolio reasons unrelated to intrinsic
     value.  Dollars are weighted by role, and a C-suite presence is
     flagged.

  3. DOLLAR CONVICTION.  Both aggregate dollars and the single largest
     buyer's dollars (concentrated conviction reads differently from many
     tiny lots).

  4. ANOMALY.  Multiple C-suite officers buying together is rare and
     high-signal.  When the scanner has captured post-transaction
     holdings (an optional enriched field), a buy that materially
     increases an insider's own stake scores as a stronger tell.

Output: discretionary_insider_conviction.json, keyed by ticker.

ADDITIVE: reads form4_buys.json read-only, writes its own file, and is
wired as a separate layer in full_universe_consensus.py.  No existing
weight or file changes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "form4_buys.json"
OUT = ROOT / "discretionary_insider_conviction.json"

# A cluster is distinct insiders buying inside this rolling window.
CLUSTER_WINDOW_DAYS = 45

# Basic ticker sanity (mirrors full_universe_consensus.is_valid_ticker so
# scanner garbage -- NONE, N/A, CIK placeholders -- never enters the file).
_TICKER_BLOCKLIST = {"NONE", "N/A", "NA", "NAN", "NULL", "", "-"}
_TICKER_RX = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def is_valid_ticker(tk) -> bool:
    if not tk or not isinstance(tk, str):
        return False
    t = tk.strip().upper()
    if t in _TICKER_BLOCKLIST or t.startswith("CIK"):
        return False
    return bool(_TICKER_RX.match(t))


def conviction_gate(total_dollar: float) -> float:
    """Dampen cluster credit when the dollars behind it are trivial.

    A 28-insider 'cluster' backed by $10k is a filing artifact, not
    conviction. Real clusters put real cash to work; this scales the
    cluster component by the aggregate dollars committed."""
    if total_dollar >= 2.5e5:
        return 1.0
    if total_dollar >= 1e5:
        return 0.8
    if total_dollar >= 2.5e4:
        return 0.55
    return 0.35


# --- role classification ------------------------------------------------
# Ordered most-informative first; the first pattern that matches wins.
_ROLE_PATTERNS = [
    ("c_suite", re.compile(
        r"\b(CEO|CFO|COO|CTO|C\.E\.O|CHIEF\s+\w+\s+OFFICER|"
        r"CHIEF\s+EXECUTIVE|CHIEF\s+FINANCIAL|CHIEF\s+OPERATING|"
        r"PRESIDENT|PRINCIPAL\s+(EXECUTIVE|FINANCIAL)\s+OFFICER)\b", re.I)),
    ("chair_founder", re.compile(r"\b(CHAIR(MAN|WOMAN|PERSON)?|FOUNDER)\b", re.I)),
    ("senior_officer", re.compile(r"\b(EVP|SVP|EXECUTIVE\s+VICE\s+PRESIDENT|"
                                  r"GENERAL\s+COUNSEL|TREASURER|SECRETARY|"
                                  r"CHIEF|OFFICER)\b", re.I)),
    ("director", re.compile(r"\bDIRECTOR\b", re.I)),
    ("ten_pct", re.compile(r"10\s*%|TEN\s*PERCENT", re.I)),
    ("other_vp", re.compile(r"\b(VP|VICE\s+PRESIDENT|MANAGER)\b", re.I)),
]

# Role -> dollar weight (how much a dollar bought by this role counts).
_ROLE_WEIGHT = {
    "c_suite": 1.6,
    "chair_founder": 1.5,
    "senior_officer": 1.2,
    "director": 1.0,
    "other_vp": 0.9,
    "ten_pct": 0.6,     # may buy for reasons unrelated to intrinsic value
    "unknown": 0.8,
}
_HIGH_INFO = {"c_suite", "chair_founder"}


def classify_role(label: str) -> str:
    """label is the ' | Title' portion of a buyer_set entry."""
    if not label:
        return "unknown"
    for name, rx in _ROLE_PATTERNS:
        if rx.search(label):
            return name
    return "unknown"


def role_from_buyer(entry: str) -> tuple[str, str]:
    """buyer_set entries look like 'NAME | Title'. Return (person, role)."""
    if "|" in entry:
        person, title = entry.split("|", 1)
    else:
        person, title = entry, ""
    return person.strip().upper(), classify_role(title)


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except Exception:
        return None


def cluster_metrics(filings: list[dict]) -> tuple[int, int, int]:
    """Return (cluster_size, same_day_cluster, window_span_days).

    cluster_size    -- max distinct insiders inside any CLUSTER_WINDOW_DAYS
                       rolling window.
    same_day_cluster-- max distinct insiders on a single filing date.
    window_span_days-- the day-span of the window that produced
                       cluster_size (0 if same day / single buyer).
    """
    dated = []  # (datetime, person)
    by_day = defaultdict(set)
    for f in filings:
        d = parse_date(f.get("date"))
        person = (f.get("person") or "").strip().upper()
        if d is None or not person:
            continue
        dated.append((d, person))
        by_day[d].add(person)

    same_day = max((len(v) for v in by_day.values()), default=0)
    if not dated:
        return 0, same_day, 0

    dated.sort(key=lambda x: x[0])
    best_size = 1
    best_span = 0
    # Two-pointer sliding window over sorted dates.
    lo = 0
    for hi in range(len(dated)):
        while (dated[hi][0] - dated[lo][0]).days > CLUSTER_WINDOW_DAYS:
            lo += 1
        window_people = {p for (_, p) in dated[lo:hi + 1]}
        if len(window_people) > best_size:
            best_size = len(window_people)
            best_span = (dated[hi][0] - dated[lo][0]).days
    return best_size, same_day, best_span


def holdings_anomaly(filings: list[dict]) -> float:
    """Bonus from enriched post-transaction data, when present.

    A buy that materially grows an insider's own stake is a stronger
    tell than a token add. Uses the optional 'post_shares' + 'shares'
    fields written by an enriched form4_buys_sweep run; silently returns
    0 when the data predates the enrichment (backward compatible)."""
    best = 0.0
    for f in filings:
        try:
            post = float(f.get("post_shares") or 0)
            sh = float(f.get("shares") or 0)
        except Exception:
            continue
        if post <= 0 or sh <= 0:
            continue
        prior = post - sh
        if prior <= 0:
            # bought from a zero (or near-zero) prior position -- brand-new stake
            best = max(best, 10.0)
            continue
        pct = sh / prior
        if pct >= 0.50:
            best = max(best, 10.0)
        elif pct >= 0.20:
            best = max(best, 5.0)
        elif pct >= 0.10:
            best = max(best, 2.0)
    return best


def score_ticker(rec: dict) -> dict:
    buyer_set = rec.get("buyer_set") or []
    filings = rec.get("filings") or []

    # Distinct insiders + role map (buyer_set is the authoritative roster).
    roles = {}
    for entry in buyer_set:
        person, role = role_from_buyer(entry)
        # keep the most-informative role seen for a person
        if person not in roles or _ROLE_WEIGHT[role] > _ROLE_WEIGHT[roles[person]]:
            roles[person] = role
    n_insiders = len(roles) or len({(f.get("person") or "").upper()
                                    for f in filings if f.get("person")})

    csuite_buyers = sum(1 for r in roles.values() if r in _HIGH_INFO)

    # Per-person dollars (role-weighted).
    person_dollar = defaultdict(float)
    for f in filings:
        person = (f.get("person") or "").strip().upper()
        try:
            person_dollar[person] += float(f.get("dollar") or 0)
        except Exception:
            pass
    total_dollar = float(rec.get("total_dollar") or sum(person_dollar.values()))
    top_person_dollar = max(person_dollar.values(), default=0.0)
    role_weighted_dollar = sum(
        d * _ROLE_WEIGHT.get(roles.get(p, "unknown"), 0.8)
        for p, d in person_dollar.items())

    cluster_size, same_day_cluster, window_span = cluster_metrics(filings)
    anomaly_holdings = holdings_anomaly(filings)

    # --- qualifying bar: SELECTIVE by design ------------------------------
    # This leg exists to isolate the most anomalous, highest-conviction
    # configurations -- not to hand every lone small buyer a couple of
    # points (that is the base F4 layer's job, and duplicating it makes
    # the layer rank-identical to the Cohen-Malloy layer on the same
    # support). A name fires ONLY if at least one is true:
    #   - a genuine multi-insider cluster (2+ distinct buyers in-window)
    #   - an informed buyer (C-suite/Chair) committing real money
    #   - a single buyer of unusual size ($1M+)
    #   - a materially stake-growing buy (enriched data)
    qualifies = (
        cluster_size >= 2
        or same_day_cluster >= 2
        or (csuite_buyers >= 1 and top_person_dollar >= 2.5e5)
        or top_person_dollar >= 1e6
        or anomaly_holdings > 0
    )
    if not qualifies:
        return {
            "n_insiders": n_insiders,
            "cluster_size": cluster_size,
            "same_day_cluster": same_day_cluster,
            "window_span_days": window_span,
            "csuite_buyers": csuite_buyers,
            "total_dollar": round(total_dollar, 0),
            "top_person_dollar": round(top_person_dollar, 0),
            "role_weighted_dollar": round(role_weighted_dollar, 0),
            "roles": sorted(set(roles.values())),
            "cluster_score": 0.0,
            "conviction_score": 0.0,
            "anomaly_score": 0.0,
            "score": 0.0,
            "flags": [],
        }

    # --- cluster score (Lakonishok-Lee: tightness beats raw count) ------
    cluster_score = 0.0
    if cluster_size >= 4:
        cluster_score = 16
    elif cluster_size >= 3:
        cluster_score = 11
    elif cluster_size >= 2:
        cluster_score = 6
    elif cluster_size >= 1:
        cluster_score = 2
    # same-day tight cluster is the strongest configuration
    if same_day_cluster >= 3:
        cluster_score += 8
    elif same_day_cluster >= 2:
        cluster_score += 4
    # gate cluster credit on the dollars actually committed
    cluster_score *= conviction_gate(total_dollar)

    # --- conviction score (role-weighted + concentration) ---------------
    conviction_score = 0.0
    if role_weighted_dollar >= 5e6:
        conviction_score += 12
    elif role_weighted_dollar >= 1e6:
        conviction_score += 7
    elif role_weighted_dollar >= 2.5e5:
        conviction_score += 3
    if top_person_dollar >= 2e6:
        conviction_score += 5
    elif top_person_dollar >= 5e5:
        conviction_score += 2
    if csuite_buyers >= 1:
        conviction_score += 3

    # --- anomaly score --------------------------------------------------
    anomaly_score = 0.0
    if csuite_buyers >= 2:
        anomaly_score += 8          # multiple C-suite buying together is rare
    elif csuite_buyers == 1 and n_insiders == 1 and top_person_dollar >= 1e6:
        anomaly_score += 5          # lone, large, informed, concentrated
    anomaly_score += anomaly_holdings

    score = round(cluster_score + conviction_score + anomaly_score, 1)

    flags = []
    if same_day_cluster >= 2:
        flags.append(f"same-day cluster x{same_day_cluster}")
    if cluster_size >= 3 and window_span > 0:
        flags.append(f"{cluster_size} insiders in {window_span}d")
    if csuite_buyers >= 2:
        flags.append(f"{csuite_buyers} C-suite buyers")
    elif csuite_buyers == 1:
        flags.append("C-suite buyer")
    if top_person_dollar >= 1e6:
        flags.append(f"${top_person_dollar/1e6:.1f}M top buyer")

    return {
        "n_insiders": n_insiders,
        "cluster_size": cluster_size,
        "same_day_cluster": same_day_cluster,
        "window_span_days": window_span,
        "csuite_buyers": csuite_buyers,
        "total_dollar": round(total_dollar, 0),
        "top_person_dollar": round(top_person_dollar, 0),
        "role_weighted_dollar": round(role_weighted_dollar, 0),
        "roles": sorted(set(roles.values())),
        "cluster_score": round(cluster_score, 1),
        "conviction_score": round(conviction_score, 1),
        "anomaly_score": round(anomaly_score, 1),
        "score": score,
        "flags": flags,
    }


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}; run form4_buys_sweep.py first")
        return 1
    f4 = json.loads(SRC.read_text())
    print(f"loaded form4_buys: {len(f4)} tickers (code-P open-market only)")

    out = {}
    skipped = 0
    for tk, rec in f4.items():
        if not isinstance(rec, dict):
            continue
        if not is_valid_ticker(tk):
            skipped += 1
            continue
        out[tk] = score_ticker(rec)
    if skipped:
        print(f"  skipped {skipped} invalid ticker(s)")

    io_util.write_json(OUT, out)
    nz = sum(1 for v in out.values() if v["score"] > 0)
    print(f"wrote {OUT} ({len(out)} tickers, {nz} scoring > 0)")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print("\n=== TOP 25 by discretionary-conviction score ===")
    print(f"{'TKR':<8}{'SCR':>6}{'CLU':>5}{'SD':>4}{'CS':>4}"
          f"{'TOP$M':>8}  FLAGS")
    for tk, v in ranked[:25]:
        print(f"{tk:<8}{v['score']:>6.1f}{v['cluster_size']:>5}"
              f"{v['same_day_cluster']:>4}{v['csuite_buyers']:>4}"
              f"{v['top_person_dollar']/1e6:>8.2f}  {'; '.join(v['flags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
