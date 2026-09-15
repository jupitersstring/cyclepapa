"""Mechanism-gated conjunction -- exceptional-return ARCHETYPES, not points.

Additive scoring rewards a name for firing many weak signals. But the
exceptional-return setups are CAUSAL MACHINES: each needs its full
mechanism present, or it doesn't work at all. This module encodes five such
machines as hard gates -- a name qualifies for an archetype only if EVERY
condition holds -- and combines them with the measured payoff geometry
(payoff_geometry.py) so the shape and the "why now" are both required.

  1. COILED-SPRING DELEVER -- a levered enterprise (D/E >= 1) with rising
     operating income is transferring value from debt to a thin equity
     sliver; cheap equity (geometry ratio) turns that into torque.
  2. SUB-CASH BUYBACK -- trades at/below net cash (net-cash floor >= 50%
     of price) AND is actively retiring shares (net-buyback / verified
     repurchase). Management arbitraging its own discount to cash.
  3. FORCED-SELLER EXHAUSTION -- non-fundamental institutional selling
     (N-PORT forced-seller signal) into a real floor, business not burning:
     price dislocated from value by flow, not deterioration.
  4. HIDDEN-ASSET REALISATION (SSP) -- a small, levered stub with a rare
     under-recognised asset and a credit agreement that sweeps disposition
     proceeds to debt paydown (credit_agreement_mine) -- forced value
     transfer to equity.
  5. STATED-UNLOCK TRIANGULATED -- management SAYS it in the MD&A (value-
     unlock / strategic-action language) AND the geometry is cheap AND an
     insider is buying open-market. Words + shape + skin, aligned.
  6. ASSET-SALE MONETIZATION -- a cheap name sells a non-core asset and the
     proceeds transfer value to a thin/levered equity (de-lever torque) or
     are large vs a small cap. The best-MEDIAN catalyst in the backtest
     (+10% / 58% hit).
  7. TENDER-OFFER SQUEEZE -- a tender / Dutch auction / bid in a cheap
     small-cap shrinks float or reveals undervaluation; net-cash-funded
     self-tenders are accretive. Best HIT RATE in the backtest (61%).

Two ANTICIPATORY (latent) archetypes catch the setup BEFORE the catalyst is
announced -- likely to realise value but haven't yet:

  8. ASSET-SALE LATENT -- cheap, levered, under de-lever pressure (credit-
     agreement asset sweep) or already signalling divestiture intent in the
     MD&A, but with NO sale announced.
  9. TENDER-TARGET LATENT -- asset-backed cheapness (near net cash / NCAV) in
     a small controllable cap with a plausible buyer (high insider ownership
     or a self-tender-capable cash pile) and NO bid yet.

Each archetype fires only on full conjunction. The score sums archetype
weights and adds a geometry contribution; a name lighting up TWO or more
machines is the rarest, highest-conviction configuration.

Output: mechanism_gates.json keyed by ticker.
"""

from __future__ import annotations

import json
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "mechanism_gates.json"

ARCH_WEIGHT = {
    "coiled_spring_delever": 12.0,
    "sub_cash_buyback": 14.0,
    "forced_seller_exhaustion": 10.0,
    "hidden_asset_realization": 13.0,
    "stated_unlock_triangulated": 12.0,
    # backtest-validated corporate-action machines (asset-sale had the best
    # median of all 12 event types; tender-offer the best hit rate).
    "asset_sale_monetization": 12.0,
    "tender_offer_squeeze": 10.0,
    # ANTICIPATORY (latent) -- the setup is present but the catalyst has NOT
    # been announced; speculative, so weighted below the confirmed machines.
    "asset_sale_latent": 8.0,
    "tender_target_latent": 8.0,
    # Cundill structured distressed value-injection (hard conjunction already
    # applied by structured_distressed_injection.py).
    "structured_distressed_injection": 13.0,
}
MULTI_MECHANISM_BONUS = 10.0   # two or more machines on one name


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def main() -> int:
    geo = _load("payoff_geometry.json")
    frames = _load("xbrl_frames_store.json")
    yf = _load("yfinance_quick.json")
    net_bb = _load("net_buyback.json")
    bbv = _load("buyback_verify.json")
    f4 = _load("form4_buys.json")
    mda = _load("mda_scan.json")
    nport = _load("nport_forced_selling.json")
    credit = _load("credit_agreement_mine.json")
    rer = _load("rerate_catalysts.json")
    sdi = _load("structured_distressed_injection.json")

    out = {}
    for tk, g in geo.items():
        fr = frames.get(tk) or {}
        y = yf.get(tk) or {}
        ratio = g.get("ratio", 0) or 0
        cheap = ratio >= 3.0
        archetypes = []
        details = {}

        debt = _num(fr.get("debt")); eq = _num(fr.get("equity"))
        de = (debt / eq) if (debt and eq and eq > 0) else None
        op = _num(fr.get("op_income")); op_p = _num(fr.get("op_income_prior"))

        # 1. COILED-SPRING DELEVER
        if de is not None and de >= 1.0 and op is not None and op > 0 \
                and op_p is not None and op > op_p and cheap:
            archetypes.append("coiled_spring_delever")
            details["delever"] = {"d_e": round(de, 2),
                                  "op_income": op, "op_prior": op_p}

        # 2. SUB-CASH BUYBACK
        nb = net_bb.get(tk) or {}
        buying = (_num(nb.get("score")) or 0) > 0 or (tk in bbv)
        if g.get("net_cash_frac", 0) >= 0.50 and buying \
                and not g.get("burning") \
                and g.get("sector") not in ("Financial Services", "Real Estate"):
            archetypes.append("sub_cash_buyback")
            details["sub_cash_buyback"] = {
                "net_cash_frac": g.get("net_cash_frac"),
                "net_buyback_score": nb.get("score"),
                "verified_buyback": tk in bbv}

        # 3. FORCED-SELLER EXHAUSTION
        np_rec = nport.get(tk) or {}
        np_score = _num(np_rec.get("score")) if isinstance(np_rec, dict) else None
        if (np_score or 0) > 0 and cheap and not g.get("burning"):
            archetypes.append("forced_seller_exhaustion")
            details["forced_seller"] = {"nport_score": np_score,
                                        "burning": g.get("burning")}

        # 4. HIDDEN-ASSET REALISATION (SSP)
        cr = credit.get(tk) or {}
        cr_score = _num(cr.get("score")) if isinstance(cr, dict) else None
        if (cr_score or 0) > 0 and g.get("book_frac", 0) and de is not None \
                and de >= 0.5:
            mcap = _num(y.get("mcap")) or 0
            if mcap and mcap < 2e9:
                archetypes.append("hidden_asset_realization")
                details["hidden_asset"] = {"credit_score": cr_score,
                                           "d_e": round(de, 2), "mcap": mcap}

        # 5. STATED-UNLOCK TRIANGULATED
        md = mda.get(tk) or {}
        md_cats = set((md.get("categories") or {}).keys())
        says_unlock = bool(md_cats & {"value_unlock", "strategic_action"})
        insider_buying = tk in f4
        if says_unlock and cheap and insider_buying:
            archetypes.append("stated_unlock_triangulated")
            details["stated_unlock"] = {
                "mda_families": sorted(md_cats),
                "mda_score": md.get("score"),
                "insider_buys": len((f4.get(tk) or {}).get("filings", []))}

        # 6. ASSET-SALE MONETIZATION -- the backtest's best-median catalyst
        #    (+10% / 58% hit). The machine: a cheap name sells a non-core
        #    asset and the proceeds transfer value to a thin/levered equity
        #    (de-lever torque) or are large relative to a small cap.
        cats = set((rer.get(tk) or {}).get("catalyst_types") or [])
        mcap = _num(y.get("mcap")) or 0
        if "ASSET_SALE" in cats and cheap \
                and ((de is not None and de >= 0.5) or (0 < mcap < 2e9)):
            archetypes.append("asset_sale_monetization")
            details["asset_sale"] = {
                "sources": (rer.get(tk) or {}).get("sources_by_bucket", {}).get("ASSET_SALE"),
                "d_e": round(de, 2) if de is not None else None,
                "ratio": ratio, "small_cap": 0 < mcap < 2e9}

        # 7. TENDER-OFFER SQUEEZE -- +5% / 61% hit. A tender (self-tender /
        #    Dutch auction / bid) shrinks the float or reveals undervaluation;
        #    the torque is largest in a cheap small/micro-cap, and a net-cash-
        #    funded self-tender is accretive.
        if "TENDER_OFFER" in cats and cheap and 0 < mcap < 2e9:
            archetypes.append("tender_offer_squeeze")
            details["tender_offer"] = {
                "sources": (rer.get(tk) or {}).get("sources_by_bucket", {}).get("TENDER_OFFER"),
                "ratio": ratio, "mcap": mcap,
                "net_cash_floor": g.get("net_cash_frac", 0) >= 0.30}

        # 8. ASSET-SALE LATENT -- the divestiture setup BEFORE it is announced:
        #    a cheap, levered name under de-lever pressure (credit-agreement
        #    asset sweep) or already signalling intent in the MD&A, but with NO
        #    announced sale yet. Anticipatory -- get in ahead of the catalyst.
        cr = credit.get(tk) or {}
        cr_score = _num(cr.get("score")) if isinstance(cr, dict) else None
        pressure = (cr_score or 0) > 0 or bool(md_cats & {"value_unlock", "strategic_action"})
        no_sale_yet = not (cats & {"ASSET_SALE", "SALE_OF_COMPANY"})
        if pressure and cheap and de is not None and de >= 0.7 \
                and no_sale_yet and 0 < mcap < 5e9:
            archetypes.append("asset_sale_latent")
            details["asset_sale_latent"] = {
                "pressure": "credit-sweep" if (cr_score or 0) > 0 else "mda-intent",
                "d_e": round(de, 2), "ratio": ratio}

        # 9. TENDER-TARGET LATENT -- the take-private / self-tender candidate
        #    BEFORE any bid: asset-backed cheapness (trades near net cash /
        #    NCAV) in a small, controllable cap with a plausible buyer (high
        #    insider ownership that could take it private, or a cash pile that
        #    could fund a self-tender), and NO deal announced. Anticipatory.
        insider_pct = _num(y.get("insider_pct"))
        asset_backed = g.get("floor_source") in ("net-cash", "NCAV")
        buyer = (insider_pct is not None and insider_pct >= 0.20) \
            or (g.get("net_cash_frac", 0) >= 0.30)
        no_deal = not (cats & {"TENDER_OFFER", "SALE_OF_COMPANY", "GOING_PRIVATE"})
        if asset_backed and cheap and 0 < mcap < 1e9 and buyer and no_deal \
                and not g.get("burning"):
            archetypes.append("tender_target_latent")
            details["tender_target_latent"] = {
                "floor_source": g.get("floor_source"),
                "insider_pct": round(insider_pct, 3) if insider_pct is not None else None,
                "net_cash_frac": g.get("net_cash_frac"), "mcap": mcap}

        # 10. STRUCTURED DISTRESSED INJECTION (Cundill / Sibir) -- the scanner
        #     already applies the hard conjunction (structured raise + asset
        #     floor + washout/distress); a scored row IS the archetype.
        sd = sdi.get(tk) or {}
        if (_num(sd.get("score")) or 0) > 0:
            archetypes.append("structured_distressed_injection")
            details["structured_distressed_injection"] = {
                "instrument": sd.get("instrument"),
                "coupon_pct": sd.get("coupon_pct"),
                "senior_secured": sd.get("senior_secured"),
                "drawdown": sd.get("drawdown_from_high")}

        if not archetypes:
            continue
        score = sum(ARCH_WEIGHT[a] for a in archetypes)
        # geometry contribution (bounded) so shape matters within an archetype.
        score += min(g.get("score", 0) * 0.25, 8.0)
        if len(archetypes) >= 2:
            score += MULTI_MECHANISM_BONUS
        out[tk] = {
            "ticker": tk,
            "archetypes": archetypes,
            "n_mechanisms": len(archetypes),
            "geometry_ratio": ratio,
            "geometry_score": g.get("score"),
            "downside_pct": g.get("downside_pct"),
            "upside_pct": g.get("upside_pct"),
            "floor_source": g.get("floor_source"),
            "sector": g.get("sector"),
            "details": details,
            "score": round(score, 1),
        }

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: (-r["n_mechanisms"], -r["score"]))
    print(f"wrote {OUT} ({len(out)} names pass >=1 mechanism gate)")
    from collections import Counter
    c = Counter(a for r in out.values() for a in r["archetypes"])
    for a, n in c.most_common():
        print(f"  {a:<28} {n}")
    print(f"\n{'TKR':<7}{'SCORE':>6}{'MECH':>5}{'RATIO':>7}  ARCHETYPES")
    for r in ranked[:30]:
        print(f"{r['ticker']:<7}{r['score']:>6.1f}{r['n_mechanisms']:>5}"
              f"{r['geometry_ratio']:>7.1f}  {', '.join(r['archetypes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
