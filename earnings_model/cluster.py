"""K-means clustering of names by growth / acceleration behaviour.

Standardises the growth+acceleration feature vector, picks ``k`` by silhouette
(unless fixed), and labels each cluster with a human-readable behaviour tag so
you can see *which* cluster is the "inflecting" cohort.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

_GROWTH_COLS = ["revenue_growth", "ebitda_growth", "earnings_growth"]
_ACCEL_COLS = ["revenue_accel", "ebitda_accel", "earnings_accel"]


def prepare_features(df: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, list[str]]:
    feats = [f for f in features if f in df.columns]
    if not feats:
        raise ValueError("None of the requested cluster features are present.")
    X = df[feats].copy()
    keep = X.notna().any(axis=1)  # drop rows with no signal at all
    return X[keep], feats


def run_kmeans(
    df: pd.DataFrame,
    features: list[str] | None = None,
    k: int | None = None,
    k_range=config.KMEANS_K_RANGE,
    random_state: int = config.RANDOM_STATE,
    rank_transform: bool = True,
) -> dict:
    """Cluster ``df`` and return labelled frame + cluster profile.

    Returns a dict with keys: ``labeled`` (df + ``cluster``), ``profile``,
    ``k``, ``silhouette``, ``features``.
    """
    from sklearn.cluster import KMeans
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    features = features or config.CLUSTER_FEATURES
    X_raw, feats = prepare_features(df, features)
    n = len(X_raw)
    if n < 4:
        raise ValueError(f"Too few usable rows to cluster (n={n}).")

    # Heavy-tailed growth/accel features will otherwise dump ~85% of names into
    # one blob and isolate the tails. Rank-transform each feature to its
    # cross-sectional percentile (uniform marginals) so clustering reflects
    # *relative* behaviour, not absolute outliers. NaN -> median rank (0.5).
    if rank_transform:
        Xr = X_raw.rank(pct=True)
        imp = SimpleImputer(strategy="constant", fill_value=0.5).fit_transform(Xr)
    else:
        lo, hi = X_raw.quantile(0.02), X_raw.quantile(0.98)
        imp = SimpleImputer(strategy="median").fit_transform(X_raw.clip(lower=lo, upper=hi, axis=1))
    X = StandardScaler().fit_transform(imp)

    best = None
    if k is None:
        for kk in k_range:
            if kk >= n:
                break
            km = KMeans(n_clusters=kk, n_init=10, random_state=random_state).fit(X)
            try:
                sil = silhouette_score(X, km.labels_)
            except ValueError:
                continue
            if best is None or sil > best[0]:
                best = (sil, kk, km)
        if best is None:
            best = (float("nan"), min(3, n - 1), KMeans(n_clusters=min(3, n - 1), n_init=10,
                                                        random_state=random_state).fit(X))
        silhouette, k, km = best
    else:
        k = min(k, n - 1)
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(X)
        try:
            silhouette = silhouette_score(X, km.labels_)
        except ValueError:
            silhouette = float("nan")

    labeled = df.copy()
    labeled["cluster"] = np.nan
    labeled.loc[X_raw.index, "cluster"] = km.labels_
    profile = _profile(labeled, feats)
    name_map = dict(zip(profile["cluster"], profile["cluster_label"]))
    labeled["cluster_label"] = labeled["cluster"].map(name_map)
    return {
        "labeled": labeled,
        "profile": profile,
        "k": int(k),
        "silhouette": float(silhouette) if silhouette == silhouette else None,
        "features": feats,
    }


def _behaviour_label(row) -> str:
    """Human-readable behaviour tag from a cluster's median growth/accel."""
    def v(k):
        x = row.get(k, np.nan)
        return 0.0 if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
    g, ra = v("revenue_growth"), v("revenue_accel")
    eg, ea = v("earnings_growth"), v("earnings_accel")
    accel = np.nanmean([ra, ea])
    if g >= 0.20:
        return "Hypergrowth, accelerating" if accel > 0 else "Hypergrowth, cooling"
    if g >= 0.07:
        return "Growth + improving" if (accel > 0 or ea > 0) else "Growth, slowing"
    if g <= -0.05 or eg <= -0.15:
        return "Contracting"
    if (ea > 0 or eg > 0) and accel >= 0:
        return "Quietly inflecting"
    if accel < 0 or eg < 0:
        return "Decelerating"
    return "Flat / ex-growth"


def _profile(labeled: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Median feature values per cluster + size + behaviour label.

    Medians (not means) summarise these skewed features sensibly even though the
    clustering itself runs on rank-transformed values.
    """
    rows = labeled.dropna(subset=["cluster"])
    agg = {f: "median" for f in feats}
    for extra in ("inflection_score", "gap_score", "valuation_richness"):
        if extra in labeled.columns:
            agg[extra] = "median"
    prof = rows.groupby("cluster").agg(agg)
    prof["n"] = rows.groupby("cluster").size()
    prof["cluster_label"] = [_behaviour_label(r) for _, r in prof.iterrows()]
    return prof.reset_index()
