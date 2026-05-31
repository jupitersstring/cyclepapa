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

    # Winsorize each feature to its [2%, 98%] range first: a handful of
    # loss-makers produce ratio-growth values like -50 that would otherwise
    # dominate the standardized space and collapse everyone else into one blob.
    lo, hi = X_raw.quantile(0.02), X_raw.quantile(0.98)
    X_w = X_raw.clip(lower=lo, upper=hi, axis=1)
    X = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(X_w))

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


def _profile(labeled: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Mean feature values per cluster + size + behaviour label."""
    rows = labeled.dropna(subset=["cluster"])
    agg = {f: "mean" for f in feats}
    for extra in ("inflection_score", "gap_score", "valuation_richness"):
        if extra in labeled.columns:
            agg[extra] = "mean"
    prof = rows.groupby("cluster").agg(agg)
    prof["n"] = rows.groupby("cluster").size()

    growth_cols = [c for c in _GROWTH_COLS if c in feats]
    accel_cols = [c for c in _ACCEL_COLS if c in feats]
    univ_growth_med = labeled[growth_cols].median().mean() if growth_cols else 0.0

    labels = []
    for cl, row in prof.iterrows():
        g = np.nanmean([row[c] for c in growth_cols]) if growth_cols else 0.0
        a = np.nanmean([row[c] for c in accel_cols]) if accel_cols else 0.0
        growth_high = g > univ_growth_med
        accel_pos = a > 0
        if accel_pos and growth_high:
            labels.append("Accelerating leaders")
        elif accel_pos and not growth_high:
            labels.append("Inflecting up (low base)")
        elif not accel_pos and growth_high:
            labels.append("High growth, slowing")
        else:
            labels.append("Lagging / contracting")
    prof["cluster_label"] = labels
    return prof.reset_index()
