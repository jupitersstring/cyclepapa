"""Analyze backtest_panel.csv: does each PIT signal predict realized 12m fwd return?

Prints decile/bucket mean forward returns, top-minus-bottom spread, Spearman IC,
and a caveats block. Writes BACKTEST_PRERERATING.md.
"""
import numpy as np
import pandas as pd
from scipy import stats

df = pd.read_csv("backtest_panel.csv")
# clip extreme forward returns (data errors / illiquid pops) at +/- 300% for means
df["fwd"] = df["fwd_return"].clip(-0.95, 3.0)
N = len(df)

out = []
def w(s=""):
    out.append(s)
    print(s)

w(f"# Backtest: pre-rerating signals vs realized 12m forward return\n")
w(f"Universe: **{N} US EDGAR filers** with point-in-time fundamentals (filed <= 2025-06-25) "
  f"and a realized forward return over 2025-06-25 -> 2026-06-25.\n")
w(f"Cohort mean fwd return: **{df['fwd'].mean()*100:.1f}%** | median: **{df['fwd'].median()*100:.1f}%**\n")


def ic(col):
    d = df[[col, "fwd"]].dropna()
    if len(d) < 50:
        return None, None, 0
    rho, p = stats.spearmanr(d[col], d["fwd"])
    return rho, p, len(d)


def bucket_table(col, q=10, ascending=True, label=None):
    d = df[[col, "fwd"]].dropna()
    if len(d) < 100:
        w(f"\n### {label or col}: too few obs ({len(d)})")
        return
    try:
        d["bkt"] = pd.qcut(d[col].rank(method="first"), q, labels=False)
    except Exception:
        w(f"\n### {label or col}: qcut failed")
        return
    g = d.groupby("bkt")["fwd"].agg(["mean", "median", "count"])
    rho, p, n = ic(col)
    top, bot = g["mean"].iloc[-1], g["mean"].iloc[0]
    spread = top - bot
    w(f"\n### {label or col}")
    w(f"IC (Spearman): **{rho:+.3f}** (p={p:.3g}, n={n}) | "
      f"top-decile {top*100:+.1f}% vs bottom {bot*100:+.1f}% -> **spread {spread*100:+.1f} pp**")
    w("")
    w("| decile | mean fwd | median | n |")
    w("|---|---|---|---|")
    for b in g.index:
        w(f"| {int(b)} | {g['mean'][b]*100:+.1f}% | {g['median'][b]*100:+.1f}% | {int(g['count'][b])} |")


# --- Canonical Piotroski test: F-score buckets --------------------------------
w("\n---\n## 1. Piotroski F-score (HIGH-confidence anchor; F-score == our P1 spine)")
d = df[["f_score", "fwd"]].dropna()
g = d.groupby("f_score")["fwd"].agg(["mean", "median", "count"])
w("\n| F-score | mean fwd | median | n |")
w("|---|---|---|---|")
for f in g.index:
    w(f"| {int(f)} | {g['mean'][f]*100:+.1f}% | {g['median'][f]*100:+.1f}% | {int(g['count'][f])} |")
lo = df[df["f_score"] <= 2]["fwd"]
hi = df[df["f_score"] >= 7]["fwd"]
if len(lo) > 10 and len(hi) > 10:
    tt = stats.mannwhitneyu(hi.dropna(), lo.dropna(), alternative="greater")
    w(f"\nHigh (F>=7, n={len(hi)}) mean **{hi.mean()*100:+.1f}%** vs "
      f"Low (F<=2, n={len(lo)}) mean **{lo.mean()*100:+.1f}%** -> "
      f"**spread {(hi.mean()-lo.mean())*100:+.1f} pp** (Mann-Whitney p={tt.pvalue:.3g})")
rho, p, n = ic("f_score")
w(f"F-score IC: **{rho:+.3f}** (p={p:.3g}, n={n})")

# --- Other single signals -----------------------------------------------------
w("\n---\n## 2. Individual signals (decile sorts, low->high)")
bucket_table("accrual_quality", label="Sloan accrual quality (higher = cleaner earnings)")
bucket_table("gross_profitability", label="Novy-Marx gross profitability (GP/assets)")
bucket_table("accel", label="N1 revenue 2nd-derivative (accel = yoy_recent - yoy_prior)")

# --- Cheapness --------------------------------------------------------------
w("\n---\n## 3. Cheapness at T (reconstructed from price_at_T = price_now/(1+fwd))")
# invert P/B so 'high bucket = cheapest'
dd = df[(df["pb_T"] > 0) & (df["pb_T"] < 50)].copy()
if len(dd) > 100:
    dd["inv_pb"] = 1 / dd["pb_T"]
    dd["bkt"] = pd.qcut(dd["inv_pb"].rank(method="first"), 10, labels=False)
    g = dd.groupby("bkt")["fwd"].agg(["mean", "median", "count"])
    rho, p = stats.spearmanr(dd["inv_pb"], dd["fwd"])
    w(f"\n### Cheapness by P/B_T (decile 9 = cheapest)")
    w(f"IC(1/PB): **{rho:+.3f}** (p={p:.3g}, n={len(dd)}) | "
      f"cheapest decile {g['mean'].iloc[-1]*100:+.1f}% vs priciest {g['mean'].iloc[0]*100:+.1f}%")
    w("")
    w("| decile | mean fwd | median | n |")
    w("|---|---|---|---|")
    for b in g.index:
        w(f"| {int(b)} | {g['mean'][b]*100:+.1f}% | {g['median'][b]*100:+.1f}% | {int(g['count'][b])} |")

# --- Composite: TURN x DISBELIEF (F-score gated on cheapness) ------------------
w("\n---\n## 4. Composite pre_rerating proxy: strong fundamentals (TURN) x cheap (DISBELIEF)")
cheap_thresh = df["pb_T"].quantile(0.40)   # cheapest 40% by P/B_T
groups = {
    "Strong+Cheap (F>=6 & PB_T<=p40)": df[(df["f_score"] >= 6) & (df["pb_T"] <= cheap_thresh) & (df["pb_T"] > 0)],
    "Strong only (F>=6)": df[df["f_score"] >= 6],
    "Cheap only (PB_T<=p40)": df[(df["pb_T"] <= cheap_thresh) & (df["pb_T"] > 0)],
    "Weak+Expensive (F<=3 & PB_T>p60)": df[(df["f_score"] <= 3) & (df["pb_T"] > df["pb_T"].quantile(0.60))],
    "All": df,
}
w("\n| bucket | n | mean fwd | median | %>0 |")
w("|---|---|---|---|---|")
for name, sub in groups.items():
    s = sub["fwd"].dropna()
    if len(s) < 10:
        continue
    w(f"| {name} | {len(s)} | {s.mean()*100:+.1f}% | {s.median()*100:+.1f}% | {(s>0).mean()*100:.0f}% |")

# --- Caveats ------------------------------------------------------------------
w("\n---\n## Caveats (read before trusting any number)")
w("""
1. **Single cohort / one regime.** This is ONE 12-month window (2025-06 -> 2026-06).
   Spreads are directional evidence, not statistical proof across regimes. A real
   Sharpe requires many independent cohorts.
2. **Survivorship.** Tickers delisted before 2026-06-25 have no forward return and
   are absent. This drops the worst outcomes -> inflates the base rate and can mute
   the measured downside protection of quality/cheapness signals.
3. **Local-currency price return, no dividends.** `momentum_12m` is price-only. For
   the US EDGAR filers this test covers, currency == USD so FX is clean, but total
   return would be modestly higher for dividend payers.
4. **Annual, point-in-time.** Signals use the latest annual filing visible at T
   (10-K), so a name whose turn showed up only in interim quarters is understated.
   No lookahead: every observation is filtered to filed <= 2025-06-25.
5. **Cheapness is reconstructed**, not observed: price_at_T = price_now/(1+fwd_return).
   This is exact for the return numerator but assumes shares constant over the window.
""")

with open("BACKTEST_PRERERATING.md", "w") as fh:
    fh.write("\n".join(out) + "\n")
print("\n[wrote BACKTEST_PRERERATING.md]")
