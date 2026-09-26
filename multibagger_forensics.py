"""Forensic examination of the multibaggers — the detective's pass.

The clustering (multibagger_clusters.py) says WHERE multibaggers start from.
This module interrogates them:

  1. HYGIENE      are some "multibaggers" artifacts? (a one-week spike that
                  reverses, a penny price, a split / unit break, a stale tape)
                  — flagged, counted, shown, and excluded from every step below
  2. ANATOMY      what actually produced each run: per-share SALES growth,
                  MARGIN expansion and MULTIPLE re-rating (log decomposition of
                  the price move entry -> +24 months), a typology of runs by
                  their source, and which pre-conditions predict each type
  3. TRAJECTORY   the story over time: every narrative axis from 24 months
                  BEFORE the entry to 24 months after, for multibaggers vs
                  MATCHED lookalikes (same month, market, size and drawdown
                  quintile); which axes LEAD the run (the gap opens before t0)
                  and which only FOLLOW it
  4. SEQUENCE     the order in which the first signs appear (fundamental
                  turn, margin inflection, insider buying, 13D, volume change
                  point, first upgrade / initiation, a new 52-week high)
  5. LOOKALIKES   the dogs that did not bark: within the same starting state
                  (matched lookalikes), what the winners had and the losers
                  did not — paired differences with bootstrap intervals
  6. 3x vs 10x    what separates the runs that kept going
Output: MULTIBAGGER_FORENSICS.md + CSVs (mb_anatomy.csv, mb_trajectory.csv,
mb_sequence.csv, mb_lookalike_diff.csv, mb_hygiene.csv).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc

LABEL = "t3_24"
MD = "MULTIBAGGER_FORENSICS.md"


# --------------------------------------------------------------------------
def prep():
    d = mc.load()
    d = d[~d["bio"]].copy()
    d = d.sort_values(["symbol", "week"]).reset_index(drop=True)
    d["ym"] = d["week"].dt.to_period("M")
    feats = [f for f in mc.FEATS if f in d.columns]
    R = mc.ranked(d, feats)
    B = mc.blocks(R)
    return d, R, B


def hygiene(d: pd.DataFrame, ent: pd.Series) -> pd.DataFrame:
    """Flag entries whose 'multibagger' is likely an artifact."""
    import event_study_base as es
    px = pd.read_parquet(es.PRICES, columns=["symbol", "week", "close"],
                         filters=[("symbol", "in", d.loc[ent, "symbol"].unique().tolist())])
    px = es.attach_usd(px.assign(dvol=np.nan)) if "usd" not in px.columns else px
    px = px.sort_values(["symbol", "week"])
    by = {s: g for s, g in px.groupby("symbol")}
    rows = []
    for i in d.index[ent]:
        s, t = d.at[i, "symbol"], d.at[i, "week"]
        g = by.get(s)
        rec = {"idx": i, "symbol": s, "week": t}
        if g is None:
            rows.append(rec)
            continue
        w = g[(g["week"] > t) & (g["week"] <= t + pd.Timedelta(weeks=104))]
        c0 = d.at[i, "close"]
        r = w["close"].pct_change()
        usd = g["usd"].dropna().iloc[0] if "usd" in g.columns and g["usd"].notna().any() else np.nan
        rec["penny"] = bool(np.isfinite(usd) and c0 * usd < 0.20)
        # one-week jump >= +150% that gives back >= 60% within 8 weeks
        spike = False
        for j in np.where(r.to_numpy() >= 1.5)[0]:
            after = w["close"].iloc[j:j + 9]
            if len(after) > 1 and after.min() <= w["close"].iloc[j] * 0.4:
                spike = True
                break
        rec["spike_reversal"] = spike
        # a unit / split break: a single weekly move of >= 10x or <= 1/10
        rec["unit_break"] = bool(((r >= 9) | (r <= -0.9)).any())
        # stale tape: >= 30% of weeks unchanged
        rec["stale"] = bool((r == 0).mean() >= 0.30) if len(r) > 10 else False
        rows.append(rec)
    h = pd.DataFrame(rows)
    h["artifact"] = h[["penny", "spike_reversal", "unit_break", "stale"]].fillna(False).any(axis=1)
    return h


def _later(d: pd.DataFrame, months: int) -> pd.DataFrame:
    """The same symbol's row `months` later (by calendar month)."""
    k = d[["symbol", "ym"]].copy()
    k["ym"] = k["ym"] + months
    return k.merge(d, on=["symbol", "ym"], how="left", suffixes=("", "_x")).set_index(d.index)


def anatomy(d: pd.DataFrame, ent_idx) -> pd.DataFrame:
    """log(1+R) = dlog(sales/share) + dlog(margin) + dlog(EV-or-price multiple)
    Price identity: P = (P/S) x (S / shares). Margin split when EBIT > 0 at both
    ends: P/S = (P/EBIT) x (EBIT/S)."""
    L = _later(d, 24)
    e = d.loc[ent_idx]
    l = L.loc[ent_idx]
    out = pd.DataFrame(index=ent_idx)
    out["symbol"], out["week"] = e["symbol"], e["week"]
    lr = np.log(l["close"] / e["close"])
    sps0, sps1 = e["rev_ttm"] / e["shares"], l["rev_ttm"] / l["shares"]
    out["log_return"] = lr
    out["sales_ps"] = np.log(sps1 / sps0).where((sps0 > 0) & (sps1 > 0))
    m0, m1 = e["ebit_ttm"] / e["rev_ttm"], l["ebit_ttm"] / l["rev_ttm"]
    okm = (m0 > 0) & (m1 > 0)
    out["margin"] = np.log(m1 / m0).where(okm)
    # multiple = the rest (so the three sum exactly to the log return)
    out["multiple"] = lr - out["sales_ps"] - out["margin"].fillna(0)
    out.loc[~okm, "multiple"] = lr - out["sales_ps"]            # P/S re-rating incl. margin where EBIT <= 0
    tot = out[["sales_ps", "margin", "multiple"]].clip(lower=0).sum(axis=1)
    share = out[["sales_ps", "margin", "multiple"]].clip(lower=0).div(tot.where(tot > 0), axis=0)
    out[["share_sales", "share_margin", "share_multiple"]] = share.values

    def typ(r):
        if not np.isfinite(r["share_sales"]):
            return "undetermined"
        top = max(("growth-led", r["share_sales"]), ("margin-led", r["share_margin"]),
                  ("re-rating-led", r["share_multiple"]), key=lambda x: x[1] if np.isfinite(x[1]) else -1)
        return top[0] if top[1] >= 0.6 else "mixed"
    out["run_type"] = out.apply(typ, axis=1)
    return out


def matched_controls(d: pd.DataFrame, ent_idx, n_per: int = 5, seed: int = 7) -> pd.DataFrame:
    """For each entry: up to n_per lookalikes from the SAME month and market,
    same size quintile and drawdown quintile, that did NOT triple."""
    rng = np.random.default_rng(seed)
    x = d[["ym", "market"]].copy()
    # quintiles within the month (rank-based, safe in thin months)
    x["szq"] = np.floor(d.groupby("ym")["dvol_usd_log"].rank(pct=True) * 4.999)
    x["ddq"] = np.floor(d.groupby("ym")["dist_hi260"].rank(pct=True) * 4.999)
    key = x["ym"].astype(str) + "|" + x["market"].astype(str) + "|" + x["szq"].astype(str) + "|" + x["ddq"].astype(str)
    pool = d[LABEL] == 0
    groups = {k: v.to_numpy() for k, v in key[pool].groupby(key[pool]).groups.items()}
    rows = []
    for i in ent_idx:
        cand = groups.get(key.at[i])
        if cand is None or not len(cand):
            continue
        pick = rng.choice(cand, size=min(n_per, len(cand)), replace=False)
        rows += [(i, j) for j in pick]
    return pd.DataFrame(rows, columns=["case", "ctrl"])


def trajectory(d, B, pairs, offsets=(-24, -18, -12, -9, -6, -3, 0, 3, 6, 12, 24)):
    """Mean narrative-axis score for cases vs their matched controls at each
    month offset; the GAP (case - control) and whether it opens before t0."""
    Bx = B.copy()
    Bx["symbol"], Bx["ym"] = d["symbol"], d["ym"]
    rows = []
    cases, ctrls = pairs["case"].unique(), pairs["ctrl"].to_numpy()
    for off in offsets:
        def at(idx):
            k = d.loc[idx, ["symbol", "ym"]].copy()
            k["ym"] = k["ym"] + off
            return k.merge(Bx, on=["symbol", "ym"], how="left")[list(mc.BLOCKS)]
        c, k = at(cases).mean(), at(ctrls).mean()
        for ax in mc.BLOCKS:
            rows.append({"offset_m": off, "axis": ax, "case": c[ax], "control": k[ax], "gap": c[ax] - k[ax]})
    T = pd.DataFrame(rows)
    piv = T.pivot(index="axis", columns="offset_m", values="gap")
    lead = pd.DataFrame({"gap_t-12": piv.get(-12), "gap_t-6": piv.get(-6), "gap_t0": piv.get(0),
                         "gap_t+6": piv.get(6), "gap_t+12": piv.get(12)})
    lead["opens_before"] = (lead["gap_t-6"].abs() >= 0.03) & (np.sign(lead["gap_t-6"]) == np.sign(lead["gap_t0"]))
    lead["role"] = np.where(lead["opens_before"], "LEADS",
                            np.where(lead["gap_t+6"].abs() > lead["gap_t0"].abs() + 0.03, "FOLLOWS", "at t0 / weak"))
    return T, lead.sort_values("gap_t0", key=lambda s: -s.abs())


SIGNS = {
    "revenue accelerates": lambda r: r["rev_accel"] >= 0.10,
    "EBIT / NI / FCF turns positive": lambda r: (r["ebit_turned"] == 1) | (r["ni_turned"] == 1) | (r.get("fcf_turned") == 1),
    "margin inflects (+3pp y/y)": lambda r: r["opm_d1"] >= 0.03,
    "insider buying (2+ quarters)": lambda r: r["ins_buy_quarters_4q"] >= 2,
    "new 13D holder": lambda r: r["bo_new_holders_12m"] >= 1,
    "volume change point (z >= 1.5)": lambda r: r["dvol_z13"] >= 1.5,
    "first upgrade / initiation": lambda r: (r["upgrades_12m"] >= 1),
    "new 52-week high (>= 98%)": lambda r: r["dist_hi52"] >= 0.98,
    "share count shrinking": lambda r: r["share_g1"] <= -0.02,
}


def sequence(d: pd.DataFrame, ent_idx) -> pd.DataFrame:
    """For each entry: months before (-) / after (+) t0 at which each sign FIRST
    appears inside a -24..+12 month window; median timing, share present."""
    by = {s: g for s, g in d.groupby("symbol")}
    rows = []
    for i in ent_idx:
        s, t = d.at[i, "symbol"], d.at[i, "ym"]
        g = by[s]
        w = g[(g["ym"] >= t - 24) & (g["ym"] <= t + 12)]
        rec = {}
        for nm, fn in SIGNS.items():
            try:
                hit = fn(w).fillna(False) if isinstance(fn(w), pd.Series) else pd.Series(False, index=w.index)
            except KeyError:
                continue
            if hit.any():
                rec[nm] = int((w.loc[hit, "ym"].iloc[0] - t).n)
        rows.append(rec)
    S = pd.DataFrame(rows)
    out = pd.DataFrame({"share_of_runs_with_sign": S.notna().mean(),
                        "median_first_seen_m": S.median(), "q25": S.quantile(0.25), "q75": S.quantile(0.75)})
    return out.sort_values("median_first_seen_m")


def lookalike_diff(d, R, pairs, n_boot: int = 300, seed: int = 7) -> pd.DataFrame:
    """Winners vs their matched lookalikes at t0: mean paired difference of the
    within-month-market rank of every feature, with a bootstrap 90% interval
    over CASES (the dogs that did not bark)."""
    rng = np.random.default_rng(seed)
    feats = [f for f in mc.FEATS if f in R.columns] + [c for c in R.columns if c.startswith("st_")]
    C = R.loc[pairs["case"], feats].to_numpy(float)
    K = R.loc[pairs["ctrl"], feats].to_numpy(float)
    diff = C - K
    # per-case mean difference (over its controls), then bootstrap over cases
    per = pd.DataFrame(diff).groupby(pairs["case"].to_numpy()).mean().to_numpy()
    est = np.nanmean(per, axis=0)
    boots = np.vstack([np.nanmean(per[rng.integers(0, len(per), len(per))], axis=0) for _ in range(n_boot)])
    lo, hi = np.nanpercentile(boots, 5, axis=0), np.nanpercentile(boots, 95, axis=0)
    cov = np.mean(~np.isnan(diff), axis=0)
    out = pd.DataFrame({"feature": feats, "winner_minus_lookalike": est, "ci90_lo": lo, "ci90_hi": hi,
                        "coverage": cov})
    out["significant"] = (out["ci90_lo"] > 0) | (out["ci90_hi"] < 0)
    return out.sort_values("winner_minus_lookalike", key=lambda s: -s.abs())


def ten_vs_three(d, R, ent_idx) -> pd.DataFrame:
    e = d.loc[ent_idx]
    ok = e["fwd_mult_60"].notna()
    big = ok & (e["fwd_mult_60"] >= 10)
    small = ok & (e["fwd_mult_60"] < 5)
    feats = [f for f in mc.FEATS if f in R.columns]
    a, b = R.loc[e.index[big], feats].mean(), R.loc[e.index[small], feats].mean()
    out = pd.DataFrame({"ten_bagger_rank": a, "three_to_five_rank": b, "diff": a - b})
    out.attrs["n"] = (int(big.sum()), int(small.sum()))
    return out.sort_values("diff", key=lambda s: -s.abs())


def main():
    d, R, B = prep()
    ent = mc.entries(d, LABEL)
    ent_all = d.index[ent]
    h = hygiene(d, ent)
    h.to_csv("mb_hygiene.csv", index=False)
    bad = set(h.loc[h["artifact"], "idx"])
    ent_idx = pd.Index([i for i in ent_all if i not in bad])
    an = anatomy(d, ent_idx)
    an.to_csv("mb_anatomy.csv")
    # which pre-conditions predict each run type (mean axis score at entry)
    ax_by_type = B.loc[an.index, list(mc.BLOCKS)].groupby(an["run_type"]).mean()
    pairs = matched_controls(d, ent_idx)
    T, lead = trajectory(d, B, pairs)
    T.to_csv("mb_trajectory.csv", index=False)
    sq = sequence(d, ent_idx)
    sq.to_csv("mb_sequence.csv")
    ld = lookalike_diff(d, R, pairs)
    ld.to_csv("mb_lookalike_diff.csv", index=False)
    tv = ten_vs_three(d, R, ent_idx)

    L = ["# The multibaggers under the microscope — a forensic examination\n"]
    L.append(f"Entries examined: {len(ent_all):,} multibagger episodes (3x held 4 weeks within 24 months; "
             f"non-biotech); matched lookalikes: {len(pairs):,} (same month, market, size and drawdown "
             "quintile, did NOT triple).\n")
    L.append("## 1. Hygiene — artifacts removed before anything else\n")
    L.append(f"- flagged as artifacts: {int(h['artifact'].sum()):,} of {len(h):,} "
             f"({h['artifact'].mean():.1%}): penny {int(h['penny'].sum())}, spike-and-reverse "
             f"{int(h['spike_reversal'].sum())}, unit break {int(h['unit_break'].sum())}, stale tape "
             f"{int(h['stale'].sum())}")
    ex = h[h["artifact"]].head(12)
    if len(ex):
        L.append("- examples: " + "; ".join(f"{r.symbol} {r.week:%Y-%m}" for r in ex.itertuples()))
    L.append("\n## 2. Anatomy — what produced the runs\n")
    L.append(an["run_type"].value_counts(normalize=True).round(3).rename("share").to_frame().to_markdown())
    L.append("\nMedian contribution to the log return (entry -> +24m):\n")
    L.append(an.groupby("run_type")[["log_return", "sales_ps", "margin", "multiple"]].median().round(3).to_markdown())
    L.append("\nThe state at ENTRY by run type (narrative axes; 0.5 = typical for its month and market):\n")
    L.append(ax_by_type.T.round(3).to_markdown())
    L.append("\n## 3. Trajectory — which parts of the story LEAD the run\n")
    L.append("Gap = multibagger minus matched lookalike (narrative-axis score). LEADS = the gap is open 6 months "
             "BEFORE the entry month, in the same direction as at entry.\n")
    L.append(lead.round(3).to_markdown())
    L.append("\n## 4. Sequence — the order in which the signs appear (months relative to entry)\n")
    L.append(sq.round(1).to_markdown())
    L.append("\n## 5. The dogs that did not bark — winners vs lookalikes from the same state\n")
    L.append("Mean paired difference in within-month-market rank (or state prevalence) with a bootstrap 90% "
             "interval; significant rows only, largest first.\n")
    L.append(ld[ld["significant"]].head(40).round(3).to_markdown(index=False))
    L.append(f"\n## 6. 10x vs 3-5x (within 60 months; n = {tv.attrs['n'][0]} vs {tv.attrs['n'][1]})\n")
    L.append(tv.head(25).round(3).to_markdown())
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
