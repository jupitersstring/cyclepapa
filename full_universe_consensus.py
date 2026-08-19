"""True full-universe consensus ranker.

The previous consensus_meta_ranker.py joined TRUNCATED top-N files
(informational_buys.csv = 159 rows, bastian_forcing.csv = 22 rows,
etc.). A name moderately strong on every layer might never appear in
any individual file's top-N and thus could not become "convergent."

This module solves that by scoring EVERY one of the 6,169 universe
tickers on EVERY layer using the scoring functions directly (not
truncated output files). It then ranks each layer across the entire
universe and computes consensus from the COMPLETE rank set.

A name's consensus is the sum of layer-rank-decay contributions
across ALL layers it scored above zero on. No top-N truncation.

Output: full_universe_consensus.csv
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_proxy() -> dict:
    proxy = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.load(open(fn))
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in proxy or
                    r.get("filing_date","") > proxy[tk].get("filing_date","")):
                    proxy[tk] = r
    return proxy


def load_layers() -> dict:
    return {
        "proxy": load_proxy(),
        "yf": json.load(open(ROOT / "yfinance_quick.json")),
        "bbv": json.load(open(ROOT / "buyback_verify.json")),
        "tender": json.load(open(ROOT / "tender_scan.json")),
        "c10": json.load(open(ROOT / "cancel_10b5_1.json")),
        "f4": json.load(open(ROOT / "form4_buys.json")),
        "f144": json.load(open(ROOT / "form144_scan.json")),
    }


# ----------------------------------------------------------------------
# Per-layer scoring functions -- score EVERY ticker, even zero-score
# ----------------------------------------------------------------------

def score_psu_layer(layers: dict, universe: set) -> dict:
    """Returns ticker -> psu_score (0 if not scored or no PSU)."""
    out = {}
    proxy = layers["proxy"]
    fwd_event = {
        "revenue_dollar_target": 12, "ebitda_dollar_target": 12,
        "fcf_dollar_target": 12, "operating_margin_target": 10,
        "fda_phase_milestone": 10, "merger_acquisition_close": 12,
        "spin_separation": 10, "asset_sale_named": 12,
        "debt_leverage_target": 10, "restructuring_milestone": 12,
        "chapter11_emergence": 15, "backlog_target": 8,
        "subscriber_arr_target": 8,
    }
    for tk in universe:
        p = proxy.get(tk, {})
        if not p:
            out[tk] = 0.0
            continue
        s = 0.0
        core = p.get("psu_core") or 0
        s += min(core * 0.5, 30)
        for cat in (p.get("cond_cats") or []):
            s += fwd_event.get(cat, 0)
        pct = p.get("psu_pct_lti") or 0
        if pct >= 80: s += 8
        elif pct >= 60: s += 4
        gov = p.get("gov_score") or 0
        s += min(gov * 0.5, 15)
        ps_count = len(p.get("per_share_metrics") or [])
        s += min(ps_count * 2, 10)
        out[tk] = round(s, 1)
    return out


def _num(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None


def score_valuation_layer(layers: dict, universe: set) -> dict:
    yf = layers["yf"]
    out = {}
    for tk in universe:
        y = yf.get(tk, {}) or {}
        s = 0.0
        pb = _num(y.get("p_b"))
        pe = _num(y.get("p_e_trailing"))
        ev_ebitda = _num(y.get("ev_ebitda"))
        if pb and 0 < pb < 0.5: s += 20
        elif pb and 0 < pb < 1.0: s += 12
        elif pb and 0 < pb < 1.5: s += 5
        if pe and 0 < pe < 8: s += 12
        elif pe and 0 < pe < 15: s += 6
        if ev_ebitda and 0 < ev_ebitda < 6: s += 14
        elif ev_ebitda and 0 < ev_ebitda < 10: s += 7
        # Drawdown
        px = _num(y.get("price"))
        hi = _num(y.get("fwk_high"))
        if px and hi and hi > 0:
            dd = (1 - px / hi) * 100
            if dd > 60: s += 10
            elif dd > 40: s += 5
        out[tk] = round(s, 1)
    return out


def score_buyback_layer(layers: dict, universe: set) -> dict:
    bbv = layers["bbv"]
    out = {}
    for tk in universe:
        b = bbv.get(tk, {}) or {}
        pts = b.get("points") or 0
        out[tk] = float(pts)
    return out


def score_tender_layer(layers: dict, universe: set) -> dict:
    tender = layers["tender"]
    out = {}
    for tk in universe:
        t = tender.get(tk, {}) or {}
        s = 0.0
        role = t.get("role")
        if role == "SELF_TENDER": s += 25
        elif role == "TARGET": s += 22
        elif role == "BIDDER": s += 5
        if t.get("has_13e3"): s += 15
        out[tk] = s
    return out


def score_c10b51_layer(layers: dict, universe: set) -> dict:
    c10 = layers["c10"]
    out = {}
    for tk in universe:
        c = c10.get(tk, {}) or {}
        s = c.get("score") or 0
        out[tk] = float(s)
    return out


def score_f4_layer(layers: dict, universe: set) -> dict:
    f4 = layers["f4"]
    out = {}
    for tk in universe:
        f = f4.get(tk, {}) or {}
        s = 0.0
        n_buyers = len(f.get("buyer_set") or [])
        dollar = (f.get("total_dollar") or 0)
        if n_buyers >= 4: s += 18
        elif n_buyers >= 3: s += 12
        elif n_buyers >= 2: s += 6
        if dollar >= 5e6: s += 10
        elif dollar >= 1e6: s += 5
        out[tk] = s
    return out


def score_f144_layer(layers: dict, universe: set) -> dict:
    """Form 144 is BEARISH; return NEGATIVE points."""
    f144 = layers["f144"]
    out = {}
    for tk in universe:
        f = f144.get(tk, {}) or {}
        s = f.get("points") or f.get("score") or 0
        out[tk] = float(s)
    return out


def score_recent_incentive_layer(layers: dict, universe: set) -> dict:
    """Re-derive from existing recent_incentive_asymmetry.csv (full-
    universe rank). Names not in file score 0."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "recent_incentive_asymmetry.csv"
    if f.exists():
        for r in csv.DictReader(f.open()):
            tk = r["ticker"]
            if tk in out:
                try:
                    out[tk] = float(r["score"])
                except Exception:
                    pass
    return out


def score_special_situations_layer(layers: dict, universe: set) -> dict:
    """Re-derive from special_situations_unified.csv."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "special_situations_unified.csv"
    if f.exists():
        # Best score per ticker
        for r in csv.DictReader(f.open()):
            tk = r.get("ticker")
            if tk in out:
                try:
                    s = float(r["score"])
                    if s > out[tk]:
                        out[tk] = s
                except Exception:
                    pass
    return out


def score_turnaround_layer(layers: dict, universe: set) -> dict:
    """Bollenbach-style turnaround-executive signal:
       senior turnaround talent voluntarily into a struggling company
       with an equity-heavy compensation package. Sourced from
       turnaround_signal.csv (built by turnaround_executive_leg.py)."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "turnaround_signal.csv"
    if f.exists():
        for r in csv.DictReader(f.open()):
            tk = r.get("ticker")
            if tk in out:
                try:
                    s = float(r["score"])
                    if s > out[tk]:
                        out[tk] = s
                except Exception:
                    pass
    return out


# ----------------------------------------------------------------------
# Tier-1 additive enhancement layers
# (Cohen-Malloy, Bonaime-Ryngaert, Tauraitis odd-lot, Comment-Jarrell)
# ----------------------------------------------------------------------

def score_opportunistic_insiders_layer(layers: dict, universe: set) -> dict:
    """Cohen-Malloy-Pomorski opportunistic-vs-routine classifier.
    Additive on top of existing f4 layer -- this layer ONLY captures
    the *opportunistic* portion, weighted per Cohen-Malloy.

    Source: opportunistic_insiders.json (built by
    opportunistic_insiders.py). Names without F4 data score 0."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "opportunistic_insiders.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_discretionary_conviction_layer(layers: dict, universe: set) -> dict:
    """Discretionary insider-conviction leg.

    Orthogonal to the raw F4 layer (count + dollar) and the Cohen-Malloy
    opportunistic layer: rewards only the anomalous, tightly-clustered,
    role-weighted, high-conviction open-market buying (code P only). See
    discretionary_insider_conviction.py. Names without a scored row -- or
    without F4 data at all -- score 0."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "discretionary_insider_conviction.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_buyback_insider_overlay_layer(layers: dict, universe: set) -> dict:
    """Bonaime-Ryngaert insider-direction overlay on buyback.
    Returns a score DELTA (positive or negative) that ADDS to the
    existing buyback layer score. Names with no overlay row score 0
    (no change to existing buyback contribution).

    Source: buyback_insider_overlay.json (built by
    buyback_insider_overlay.py)."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "buyback_insider_overlay.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score_delta") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_odd_lot_tender_layer(layers: dict, universe: set) -> dict:
    """Tauraitis/Walker odd-lot tender priority bonus.
    Additive on top of existing tender layer. Names with full odd-lot
    + not-prorated edge score +25; partial language only scores +10.

    Source: tender_odd_lot.json (built by
    tender_odd_lot_and_mechanism.py)."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "tender_odd_lot.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_tender_mechanism_layer(layers: dict, universe: set) -> dict:
    """Comment-Jarrell tender-mechanism multiplier delta.
    Returns score DELTA per Comment-Jarrell (JF 1991): fixed-price =
    base, Dutch = -27%, exchange-offer = -15%, open-market = -82%.
    UNKNOWN returns 0 (neutral -- we don't penalize what we can't
    classify).

    Source: tender_mechanism.json (built by
    tender_odd_lot_and_mechanism.py)."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "tender_mechanism.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score_delta") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------
# Tier-2 additive layers (Voss CIC triangulation, post-Ch11 emergence,
# external-manager internalization, bumpitrage decline, spinoff volume
# timer)
# ----------------------------------------------------------------------

def _load_jscore(path: Path, universe: set, field: str = "score") -> dict:
    out = {tk: 0.0 for tk in universe}
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text())
    except Exception:
        return out
    for tk, v in data.items():
        if tk in out and isinstance(v, dict):
            try:
                out[tk] = float(v.get(field) or 0)
            except Exception:
                pass
    return out


def score_voss_cic_layer(layers: dict, universe: set) -> dict:
    """Voss CIC-amendment triangulation."""
    return _load_jscore(ROOT / "voss_cic_triangulation.json", universe)


def score_post_ch11_layer(layers: dict, universe: set) -> dict:
    """Eberhart-Altman post-Ch11 emergence equity."""
    return _load_jscore(ROOT / "post_ch11_emergence.json", universe)


def score_premium_injection_layer(layers: dict, universe: set) -> dict:
    """Premium capital injection: a sophisticated investor knowingly
    subscribes for newly-issued shares ABOVE market -- the purest
    revealed-preference signal. See premium_injection_scan.py."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "premium_injection_scan.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = max(0.0, float(v.get("score") or 0))
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_distressed_stub_layer(layers: dict, universe: set) -> dict:
    """Distressed-stub progress: stage-gated, finality-filtered value-
    unlock events in capital-structure workouts, with stub-waterfall
    penalties. Only net-positive scores add. See
    distressed_stub_progress.py. Names without a scored event score 0."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "distressed_stub_progress.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = max(0.0, float(v.get("score") or 0))
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_asymmetry_assembly_layer(layers: dict, universe: set) -> dict:
    """PSIX-recipe conjunction layer: a gated, convergence-weighted score
    that fires only when the assembled causal system co-occurs (cheap +
    engine + costly-action alignment). See asymmetry_assembly.py. Names
    without a full assembly score 0."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "asymmetry_assembly.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_sohn_pitch_layer(layers: dict, universe: set) -> dict:
    """Sohn Conference pitches: reputation-staked public ideas from
    professional managers (curated, hand-refreshed per conference).
    Longs add, shorts subtract, age-decayed. See sohn_pitch_layer.py."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "sohn_pitch_scores.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_emergence_crossfeed_layer(layers: dict, universe: set) -> dict:
    """Post-reorg emergence cross-feed from the pollers subsystem
    (capital-structure-screening branch): 5-channel EDGAR emergence
    detection with confidence grading, ~587 entities vs the 29 in this
    engine's own post_ch11 layer. Additive; the correlation stage
    reports overlap with post_ch11 honestly. Scores 0 when the
    snapshot-derived emergence_crossfeed.json is absent."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "emergence_crossfeed.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            for tk, v in data.items():
                if tk in out and isinstance(v, dict):
                    try:
                        out[tk] = float(v.get("score") or 0)
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def score_internalization_layer(layers: dict, universe: set) -> dict:
    """External-manager internalization (Braemar/Ashford)."""
    return _load_jscore(ROOT / "external_manager_internalization.json", universe)


def score_bumpitrage_layer(layers: dict, universe: set) -> dict:
    """Walker bumpitrage tender-decline signal."""
    return _load_jscore(ROOT / "bumpitrage_tender_decline.json", universe)


def score_spinoff_volume_layer(layers: dict, universe: set) -> dict:
    """Rich Howe 40% volume rule entry timer."""
    return _load_jscore(ROOT / "spinoff_volume_timer.json", universe)


# ----------------------------------------------------------------------
# Tier-3 additive layers
# ----------------------------------------------------------------------

def score_arquitos_layer(layers: dict, universe: set) -> dict:
    """Arquitos subsidiary-stake anchor."""
    return _load_jscore(ROOT / "arquitos_subsidiary_anchor.json", universe)


def score_coval_stafford_layer(layers: dict, universe: set) -> dict:
    """Coval-Stafford fire-sale proxy (yfinance approximation)."""
    return _load_jscore(ROOT / "coval_stafford_proxy.json", universe)


def score_backstopped_rights_layer(layers: dict, universe: set) -> dict:
    """Clark Street Value backstopped rights offering."""
    return _load_jscore(ROOT / "backstopped_rights.json", universe)


def score_fdic_call_report_layer(layers: dict, universe: set) -> dict:
    """FDIC Call Report mining for Form 15 dark community banks."""
    return _load_jscore(ROOT / "fdic_call_report_overlay.json", universe)


def score_net_net_ncav_layer(layers: dict, universe: set) -> dict:
    """Net Net Hunter Core-7 NCAV scorecard."""
    return _load_jscore(ROOT / "net_net_ncav.json", universe)


def score_activist_letter_layer(layers: dict, universe: set) -> dict:
    """Pre-13D + 8-K-letter activist feed."""
    return _load_jscore(ROOT / "activist_letter_feed.json", universe)


# Audit-driven additive layers (S1.3 + S2 fills)

def score_form_13f_delta_layer(layers: dict, universe: set) -> dict:
    """13F-delta smart-money / activist accumulation signal."""
    return _load_jscore(ROOT / "form_13f_delta.json", universe)


def score_biotech_pdufa_layer(layers: dict, universe: set) -> dict:
    """Biotech PDUFA calendar primary screen (S1.3 non-PSU complement)."""
    return _load_jscore(ROOT / "biotech_pdufa_calendar.json", universe)


def score_financial_primary_layer(layers: dict, universe: set) -> dict:
    """Financial-sector P/TBV + ROE + buyback primary screen
    (S1.3 non-PSU complement)."""
    return _load_jscore(ROOT / "financial_primary.json", universe)


def score_nport_forced_selling_layer(layers: dict, universe: set) -> dict:
    """Real Coval-Stafford via N-PORT mutual-fund holdings deltas."""
    return _load_jscore(ROOT / "nport_forced_selling.json", universe)


def score_foreign_markets_layer(layers: dict, universe: set) -> dict:
    """Foreign markets (JP TSE PBR<1, KR Value-Up, UK schemes).
    Foreign tickers keep their yfinance suffix (.T, .KS, .L) so they
    are NEVER confused with US tickers. The consensus universe only
    contains US tickers, so this layer's contribution to most rows
    is zero -- but the foreign_markets.json itself is the deliverable.
    A separate convergence is computed in the xlsx tab."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "foreign_markets.json"
    if not f.exists():
        return out
    # Foreign tickers are not in our US universe; we keep them in
    # the separate json. This layer contributes 0 to US tickers,
    # ensuring it doesn't pollute existing scoring.
    return out


def score_quarterly_10q_layer(layers: dict, universe: set) -> dict:
    """Quarterly 10-Q NCAV / current-ratio overlay (S2.4 fresher data)."""
    out = {tk: 0.0 for tk in universe}
    f = ROOT / "quarterly_10q_data.json"
    if not f.exists():
        return out
    try:
        data = json.loads(f.read_text())
    except Exception:
        return out
    for tk, v in data.items():
        if tk not in out or not isinstance(v, dict):
            continue
        s = 0.0
        # Reward names with strong balance sheet from FRESH quarterly data
        ncav = v.get("ncav") or 0
        cr = v.get("current_ratio") or 0
        net_cash = v.get("net_cash") or 0
        if ncav > 0 and cr > 1.5:
            s += 8
        if cr > 2.0:
            s += 6
        if net_cash > 0:
            s += 6
        out[tk] = s
    return out


# ----------------------------------------------------------------------
# Universe build
# ----------------------------------------------------------------------

import re as _re_validate
_TICKER_RX = _re_validate.compile(r"^[A-Z][A-Z0-9.\-]{0,8}$")
_TICKER_BLOCKLIST = {"NONE", "N/A", "NA", "NULL", "NAN", "TBD", "UNKNOWN", ""}


def is_valid_ticker(tk) -> bool:
    """Centralized ticker-validity gate. Rejects parse-artifact junk
    (NONE, N/A, NAN), CIK-style placeholders, and anything that does
    not look like a US exchange symbol. Applied at universe build so
    no single source can leak garbage into the consensus."""
    if not tk or not isinstance(tk, str):
        return False
    t = tk.strip().upper()
    if t in _TICKER_BLOCKLIST:
        return False
    if t.startswith("CIK"):
        return False
    return bool(_TICKER_RX.match(t))


def main() -> int:
    layers = load_layers()
    universe = set(layers["proxy"]) | set(layers["yf"]) | set(layers["bbv"]) \
               | set(layers["tender"]) | set(layers["c10"]) | set(layers["f4"]) \
               | set(layers["f144"])
    raw_n = len(universe)
    universe = {t for t in universe if is_valid_ticker(t)}
    dropped = raw_n - len(universe)
    if dropped:
        print(f"  dropped {dropped} invalid ticker(s) at universe gate")
    print(f"Full universe: {len(universe)} tickers")

    layer_scores = {
        "psu": score_psu_layer(layers, universe),
        "valuation": score_valuation_layer(layers, universe),
        "buyback": score_buyback_layer(layers, universe),
        "tender": score_tender_layer(layers, universe),
        "c10b51": score_c10b51_layer(layers, universe),
        "f4_buys": score_f4_layer(layers, universe),
        "f144": score_f144_layer(layers, universe),
        "recent_incentive": score_recent_incentive_layer(layers, universe),
        "special_situations": score_special_situations_layer(layers, universe),
        "turnaround": score_turnaround_layer(layers, universe),
        # Tier-1 additive enhancement layers (Cohen-Malloy, Bonaime-
        # Ryngaert, Tauraitis odd-lot, Comment-Jarrell) -- each ADDS to
        # (does not replace) the corresponding base layer.
        "opportunistic_insiders": score_opportunistic_insiders_layer(layers, universe),
        "discretionary_conviction": score_discretionary_conviction_layer(layers, universe),
        "buyback_insider_overlay": score_buyback_insider_overlay_layer(layers, universe),
        "odd_lot_tender": score_odd_lot_tender_layer(layers, universe),
        "tender_mechanism": score_tender_mechanism_layer(layers, universe),
        # Tier-2 additive layers
        "voss_cic": score_voss_cic_layer(layers, universe),
        "post_ch11": score_post_ch11_layer(layers, universe),
        "emergence_crossfeed": score_emergence_crossfeed_layer(layers, universe),
        "sohn_pitch": score_sohn_pitch_layer(layers, universe),
        "asymmetry_assembly": score_asymmetry_assembly_layer(layers, universe),
        "distressed_stub": score_distressed_stub_layer(layers, universe),
        "premium_injection": score_premium_injection_layer(layers, universe),
        "internalization": score_internalization_layer(layers, universe),
        "bumpitrage": score_bumpitrage_layer(layers, universe),
        "spinoff_volume": score_spinoff_volume_layer(layers, universe),
        # Tier-3
        "arquitos": score_arquitos_layer(layers, universe),
        "coval_stafford": score_coval_stafford_layer(layers, universe),
        "backstopped_rights": score_backstopped_rights_layer(layers, universe),
        "fdic_call_report": score_fdic_call_report_layer(layers, universe),
        # NCAV + activist feed
        "net_net_ncav": score_net_net_ncav_layer(layers, universe),
        "activist_letter": score_activist_letter_layer(layers, universe),
        # Audit-driven additive (S1.3 + S2)
        "form_13f_delta": score_form_13f_delta_layer(layers, universe),
        "biotech_pdufa": score_biotech_pdufa_layer(layers, universe),
        "financial_primary": score_financial_primary_layer(layers, universe),
        "quarterly_10q": score_quarterly_10q_layer(layers, universe),
        "nport_forced_selling": score_nport_forced_selling_layer(layers, universe),
        # foreign_markets layer intentionally NOT in US consensus -- it
        # lives in its own JSON + xlsx tab to keep universes clean
    }
    print(f"Layers scored: {len(layer_scores)}")
    for lk, ls in layer_scores.items():
        nz = sum(1 for v in ls.values() if v > 0)
        print(f"  {lk:<22} {nz:>5}/{len(ls)} non-zero")

    # Compute layer rank for each ticker per layer
    # (positive scores rank-descended; zeros tie for last)
    layer_ranks = {}
    for lk, scores in layer_scores.items():
        order = sorted(scores.items(), key=lambda x: -x[1])
        rank_map = {}
        for i, (tk, s) in enumerate(order, 1):
            rank_map[tk] = (i, s)
        layer_ranks[lk] = rank_map

    # Consensus contribution from each layer:
    # rank-decay: contribution = max(0, 1 - (rank-1) / topN_threshold)
    # where topN_threshold is layer-specific but the COMPLETE universe
    # is considered, not a truncated file.
    rows = []
    universe_size = len(universe)
    for tk in universe:
        n_screens = 0
        contrib = 0.0
        per_layer_contrib = {}
        for lk, ranks in layer_ranks.items():
            rk, sc = ranks.get(tk, (universe_size, 0))
            # Layer contributes only if score > 0 (or < 0 for f144)
            if sc != 0:
                # Rank-decay across top 500 of universe
                c = max(0.0, 1.0 - (rk - 1) / 500.0) if sc > 0 else 0
                per_layer_contrib[lk] = round(c, 3)
                if c > 0:
                    contrib += c
                    n_screens += 1
                if sc < 0:
                    contrib -= 0.3  # penalty for f144 bearish hits
        rows.append({
            "ticker": tk,
            "consensus_score": round(contrib, 3),
            "n_layers_firing": n_screens,
            "psu_pts": layer_scores["psu"].get(tk, 0),
            "valuation_pts": layer_scores["valuation"].get(tk, 0),
            "buyback_pts": layer_scores["buyback"].get(tk, 0),
            "tender_pts": layer_scores["tender"].get(tk, 0),
            "c10b51_pts": layer_scores["c10b51"].get(tk, 0),
            "f4_buys_pts": layer_scores["f4_buys"].get(tk, 0),
            "f144_pts": layer_scores["f144"].get(tk, 0),
            "recent_incentive_pts": layer_scores["recent_incentive"].get(tk, 0),
            "special_sits_pts": layer_scores["special_situations"].get(tk, 0),
            "turnaround_pts": layer_scores["turnaround"].get(tk, 0),
            "opportunistic_pts": layer_scores["opportunistic_insiders"].get(tk, 0),
            "discretionary_conviction_pts": layer_scores["discretionary_conviction"].get(tk, 0),
            "bb_insider_overlay_pts": layer_scores["buyback_insider_overlay"].get(tk, 0),
            "odd_lot_pts": layer_scores["odd_lot_tender"].get(tk, 0),
            "tender_mech_pts": layer_scores["tender_mechanism"].get(tk, 0),
            "voss_cic_pts": layer_scores["voss_cic"].get(tk, 0),
            "post_ch11_pts": layer_scores["post_ch11"].get(tk, 0),
            "emergence_crossfeed_pts": layer_scores["emergence_crossfeed"].get(tk, 0),
            "sohn_pitch_pts": layer_scores["sohn_pitch"].get(tk, 0),
            "asymmetry_assembly_pts": layer_scores["asymmetry_assembly"].get(tk, 0),
            "distressed_stub_pts": layer_scores["distressed_stub"].get(tk, 0),
            "premium_injection_pts": layer_scores["premium_injection"].get(tk, 0),
            "internalization_pts": layer_scores["internalization"].get(tk, 0),
            "bumpitrage_pts": layer_scores["bumpitrage"].get(tk, 0),
            "spinoff_volume_pts": layer_scores["spinoff_volume"].get(tk, 0),
            "arquitos_pts": layer_scores["arquitos"].get(tk, 0),
            "coval_stafford_pts": layer_scores["coval_stafford"].get(tk, 0),
            "backstopped_rights_pts": layer_scores["backstopped_rights"].get(tk, 0),
            "fdic_call_report_pts": layer_scores["fdic_call_report"].get(tk, 0),
            "net_net_ncav_pts": layer_scores["net_net_ncav"].get(tk, 0),
            "activist_letter_pts": layer_scores["activist_letter"].get(tk, 0),
            "form_13f_delta_pts": layer_scores["form_13f_delta"].get(tk, 0),
            "biotech_pdufa_pts": layer_scores["biotech_pdufa"].get(tk, 0),
            "financial_primary_pts": layer_scores["financial_primary"].get(tk, 0),
            "quarterly_10q_pts": layer_scores["quarterly_10q"].get(tk, 0),
            "nport_forced_selling_pts": layer_scores["nport_forced_selling"].get(tk, 0),
        })

    rows.sort(key=lambda r: (-r["n_layers_firing"], -r["consensus_score"]))

    out = ROOT / "full_universe_consensus.csv"
    fieldnames = list(rows[0].keys())
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out} ({len(rows)} rows)")

    # Print top 30
    print(f"\n=== TOP 30 by n_layers_firing then consensus_score ===")
    print(f"{'#':<3}{'TKR':<8}{'NL':<3}{'CONS':<7}"
          f"{'PSU':<6}{'VAL':<6}{'BB':<6}{'TND':<6}{'C10':<6}"
          f"{'F4':<6}{'RI':<6}{'SS':<6}")
    for i, r in enumerate(rows[:30], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['n_layers_firing']:<3}"
              f"{r['consensus_score']:<7}"
              f"{r['psu_pts']:<6.0f}{r['valuation_pts']:<6.0f}"
              f"{r['buyback_pts']:<6.0f}{r['tender_pts']:<6.0f}"
              f"{r['c10b51_pts']:<6.0f}{r['f4_buys_pts']:<6.0f}"
              f"{r['recent_incentive_pts']:<6.0f}{r['special_sits_pts']:<6.0f}")

    # How many fire on >= N layers?
    from collections import Counter
    by_n = Counter(r["n_layers_firing"] for r in rows)
    print(f"\nLayer-firing distribution:")
    for n in sorted(by_n, reverse=True):
        print(f"  {n} layers firing: {by_n[n]} names")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
