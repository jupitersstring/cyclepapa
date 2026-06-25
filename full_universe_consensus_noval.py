"""Full-universe consensus WITHOUT the valuation leg.

Some PSU-strong names in our universe don't have yfinance overlay
(816 PSU-scored names have no yf data). When valuation is included
in the consensus, those names get zero on the value leg and lose
rank to names with valuation. This module produces a parallel
ranking that EXCLUDES valuation entirely so structural-only
asymmetry is not hidden by missing valuation data.

Output: full_universe_consensus_noval.csv

Cross-comparison with full_universe_consensus.csv produces:
  consensus_emergent_noval.csv  -- names ranking materially HIGHER
                                   without valuation (likely missing
                                   yf overlay, deserve gap-fill)
"""

from __future__ import annotations

import csv
from pathlib import Path

# Reuse all the scoring functions from full_universe_consensus
from full_universe_consensus import (
    load_layers,
    score_psu_layer,
    score_buyback_layer,
    score_tender_layer,
    score_c10b51_layer,
    score_f4_layer,
    score_f144_layer,
    score_recent_incentive_layer,
    score_special_situations_layer,
    score_turnaround_layer,
    score_opportunistic_insiders_layer,
    score_buyback_insider_overlay_layer,
    score_odd_lot_tender_layer,
    score_tender_mechanism_layer,
    score_voss_cic_layer,
    score_post_ch11_layer,
    score_internalization_layer,
    score_bumpitrage_layer,
    score_spinoff_volume_layer,
    score_arquitos_layer,
    score_coval_stafford_layer,
    score_backstopped_rights_layer,
    score_fdic_call_report_layer,
    score_net_net_ncav_layer,
    score_activist_letter_layer,
    score_form_13f_delta_layer,
    score_biotech_pdufa_layer,
    score_financial_primary_layer,
    score_quarterly_10q_layer,
)

ROOT = Path("/home/user/cyclepapa")


def main() -> int:
    layers = load_layers()
    universe = set(layers["proxy"]) | set(layers["yf"]) | set(layers["bbv"]) \
               | set(layers["tender"]) | set(layers["c10"]) | set(layers["f4"]) \
               | set(layers["f144"])
    universe = {t for t in universe if not t.startswith("CIK")}
    print(f"Full universe: {len(universe)} tickers")

    # Score every layer EXCEPT valuation
    layer_scores = {
        "psu": score_psu_layer(layers, universe),
        "buyback": score_buyback_layer(layers, universe),
        "tender": score_tender_layer(layers, universe),
        "c10b51": score_c10b51_layer(layers, universe),
        "f4_buys": score_f4_layer(layers, universe),
        "f144": score_f144_layer(layers, universe),
        "recent_incentive": score_recent_incentive_layer(layers, universe),
        "special_situations": score_special_situations_layer(layers, universe),
        "turnaround": score_turnaround_layer(layers, universe),
        "opportunistic_insiders": score_opportunistic_insiders_layer(layers, universe),
        "buyback_insider_overlay": score_buyback_insider_overlay_layer(layers, universe),
        "odd_lot_tender": score_odd_lot_tender_layer(layers, universe),
        "tender_mechanism": score_tender_mechanism_layer(layers, universe),
        "voss_cic": score_voss_cic_layer(layers, universe),
        "post_ch11": score_post_ch11_layer(layers, universe),
        "internalization": score_internalization_layer(layers, universe),
        "bumpitrage": score_bumpitrage_layer(layers, universe),
        "spinoff_volume": score_spinoff_volume_layer(layers, universe),
        "arquitos": score_arquitos_layer(layers, universe),
        "coval_stafford": score_coval_stafford_layer(layers, universe),
        "backstopped_rights": score_backstopped_rights_layer(layers, universe),
        "fdic_call_report": score_fdic_call_report_layer(layers, universe),
        "net_net_ncav": score_net_net_ncav_layer(layers, universe),
        "activist_letter": score_activist_letter_layer(layers, universe),
        "form_13f_delta": score_form_13f_delta_layer(layers, universe),
        "biotech_pdufa": score_biotech_pdufa_layer(layers, universe),
        "financial_primary": score_financial_primary_layer(layers, universe),
        "quarterly_10q": score_quarterly_10q_layer(layers, universe),
    }
    print(f"Layers scored (excluding valuation): {len(layer_scores)}")
    for lk, ls in layer_scores.items():
        nz = sum(1 for v in ls.values() if v > 0)
        print(f"  {lk:<22} {nz:>5}/{len(ls)} non-zero")

    # Compute rank per layer
    layer_ranks = {}
    for lk, scores in layer_scores.items():
        order = sorted(scores.items(), key=lambda x: -x[1])
        rank_map = {tk: (i+1, s) for i, (tk, s) in enumerate(order)}
        layer_ranks[lk] = rank_map

    universe_size = len(universe)
    rows = []
    for tk in universe:
        n_layers = 0
        contrib = 0.0
        for lk, ranks in layer_ranks.items():
            rk, sc = ranks.get(tk, (universe_size, 0))
            if sc != 0:
                c = max(0.0, 1.0 - (rk - 1) / 500.0) if sc > 0 else 0
                if c > 0:
                    contrib += c
                    n_layers += 1
                if sc < 0:
                    contrib -= 0.3
        rows.append({
            "ticker": tk,
            "consensus_score": round(contrib, 3),
            "n_layers_firing": n_layers,
            "psu_pts": layer_scores["psu"].get(tk, 0),
            "buyback_pts": layer_scores["buyback"].get(tk, 0),
            "tender_pts": layer_scores["tender"].get(tk, 0),
            "c10b51_pts": layer_scores["c10b51"].get(tk, 0),
            "f4_buys_pts": layer_scores["f4_buys"].get(tk, 0),
            "f144_pts": layer_scores["f144"].get(tk, 0),
            "recent_incentive_pts": layer_scores["recent_incentive"].get(tk, 0),
            "special_sits_pts": layer_scores["special_situations"].get(tk, 0),
            "turnaround_pts": layer_scores["turnaround"].get(tk, 0),
            "opportunistic_pts": layer_scores["opportunistic_insiders"].get(tk, 0),
            "bb_insider_overlay_pts": layer_scores["buyback_insider_overlay"].get(tk, 0),
            "odd_lot_pts": layer_scores["odd_lot_tender"].get(tk, 0),
            "tender_mech_pts": layer_scores["tender_mechanism"].get(tk, 0),
            "voss_cic_pts": layer_scores["voss_cic"].get(tk, 0),
            "post_ch11_pts": layer_scores["post_ch11"].get(tk, 0),
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
        })
    rows.sort(key=lambda r: (-r["n_layers_firing"], -r["consensus_score"]))

    out = ROOT / "full_universe_consensus_noval.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out} ({len(rows)} rows)")

    # Distribution
    from collections import Counter
    print("\nLayer-firing distribution (no valuation):")
    for n, ct in sorted(Counter(r["n_layers_firing"] for r in rows).items(),
                        reverse=True):
        print(f"  {n} layers: {ct} names")

    # Top 30
    print("\n=== TOP 30 (no-valuation ranking) ===")
    print(f"{'#':<3}{'TKR':<8}{'NL':<3}{'CONS':<7}"
          f"{'PSU':<6}{'BB':<6}{'TND':<6}{'C10':<6}"
          f"{'F4':<6}{'RI':<6}{'SS':<6}")
    for i, r in enumerate(rows[:30], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['n_layers_firing']:<3}"
              f"{r['consensus_score']:<7}"
              f"{r['psu_pts']:<6.0f}{r['buyback_pts']:<6.0f}"
              f"{r['tender_pts']:<6.0f}{r['c10b51_pts']:<6.0f}"
              f"{r['f4_buys_pts']:<6.0f}"
              f"{r['recent_incentive_pts']:<6.0f}"
              f"{r['special_sits_pts']:<6.0f}")

    # Cross-comparison with valuation-included ranking
    val_csv = ROOT / "full_universe_consensus.csv"
    if val_csv.exists():
        val_rank = {}
        for i, r in enumerate(csv.DictReader(val_csv.open()), 1):
            val_rank[r["ticker"]] = i

        noval_rank = {r["ticker"]: i+1 for i, r in enumerate(rows)}

        # Names ranking materially higher WITHOUT valuation
        emergent = []
        for tk, nr in noval_rank.items():
            vr = val_rank.get(tk, len(val_rank))
            delta = vr - nr   # positive = ranks higher without valuation
            if nr <= 100 and delta >= 50:
                emergent.append((tk, nr, vr, delta))
        emergent.sort(key=lambda x: -x[3])

        print(f"\n=== TOP 25 emergent without valuation "
              f"(ranks materially higher when val excluded) ===")
        print(f"  {'TKR':<8}{'noval_#':<10}{'val_#':<10}{'lift':<6}")
        for tk, nr, vr, d in emergent[:25]:
            print(f"  {tk:<8}{nr:<10}{vr:<10}{d:<6}")

        # Save emergent list
        emer_out = ROOT / "consensus_emergent_noval.csv"
        with emer_out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["ticker","noval_rank","val_rank","lift"])
            w.writeheader()
            for tk, nr, vr, d in emergent:
                w.writerow({"ticker":tk, "noval_rank":nr,
                             "val_rank":vr, "lift":d})
        print(f"\nwrote {emer_out} ({len(emergent)} emergent names)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
