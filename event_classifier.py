"""Learned event-validity classifier: is this filing excerpt a NEW corporate
action of the tagged kind, or a phantom (recital, footnote, bio, cost line,
risk factor, capital raise, someone else's action ...)?

The regex validator in event_detail.py catches the phantom classes it names,
but the long tail (investor-day slides, AGM vote items, a subsidiary's dividend,
warrant terms ...) does not generalise as rules. This model learns it from the
reviewed filings (reviewed/events.json + the excerpt each reviewer read,
reviewed/events_corpus.jsonl.gz).

Features: word 1-2 grams of the excerpt and of the filing's lede (separate
vocabularies), the event family, and the regex validator's signals (which
generic phantom rule fired, recital-by-date, announcement verb, days between
the newest date in the text and the filing).

Honesty: `python3 event_classifier.py` trains on the 'dev' half and scores
the 'holdout' half (never used in tuning), then 5-fold CV over all. The model
used in production is trained on everything; its decision threshold is set
from cross-validation so ~95% of real events are kept.
"""

from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path("/home/user/cyclepapa")
REV = ROOT / "reviewed"
KEEP_REAL = 0.95          # threshold chosen so this share of real events is kept (CV)


def _signals(fam, exc, lede, filed):
    import event_detail as ed
    lead = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", exc)[0] if exc else ""
    v = [1.0 if re.search(rx, lead, re.I | re.M) else 0.0 for rx, _ in ed.GENERIC_NOT_EVENT]
    v.append(1.0 if ed._historical(exc, filed) else 0.0)
    v.append(1.0 if re.search(r"today announced|announced today|\bannounces?\b|entered into", exc, re.I) else 0.0)
    v.append(1.0 if re.search(r"previously (?:announced|disclosed|reported)", exc, re.I) else 0.0)
    v.append(1.0 if re.search(r"\b(?:subsidiary|investee|affiliate)\b[^.]{0,60}\b(?:declared|paid)", exc, re.I) else 0.0)
    v.append(1.0 if re.search(r"slide|presentation|investor day|page \d", exc + " " + lede[:300], re.I) else 0.0)
    v.append(1.0 if re.search(r"results|quarter|fiscal", lede[:300], re.I) else 0.0)
    return v


def _text(fam, exc, lede):
    return f"FAM_{fam} " + exc, lede[:800]


def corpus():
    gold = {g["id"]: g for g in json.loads((REV / "events.json").read_text())}
    rows = []
    with gzip.open(REV / "events_corpus.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            g = gold.get(d["id"])
            if g is not None and d.get("excerpt"):
                rows.append({**d, "y": int(bool(g["is_event"])), "split": g.get("split")})
    return rows


class Model:
    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.v1 = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=30000)
        self.v2 = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=10000)
        self.clf = None
        self.threshold = 0.5

    def _X(self, rows, fit=False):
        from scipy.sparse import csr_matrix, hstack
        a = [_text(r["family"], r["excerpt"], r.get("lede") or "") for r in rows]
        t1 = self.v1.fit_transform([x[0] for x in a]) if fit else self.v1.transform([x[0] for x in a])
        t2 = self.v2.fit_transform([x[1] for x in a]) if fit else self.v2.transform([x[1] for x in a])
        s = csr_matrix(np.array([_signals(r["family"], r["excerpt"], r.get("lede") or "", r.get("filed")) for r in rows]) * 2.0)
        return hstack([t1, 0.5 * t2, s]).tocsr()

    def fit(self, rows):
        from sklearn.linear_model import LogisticRegression
        X = self._X(rows, fit=True)
        y = np.array([r["y"] for r in rows])
        self.clf = LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000).fit(X, y)
        return self

    def proba(self, rows):
        return self.clf.predict_proba(self._X(rows))[:, 1]


def _threshold_for(p_real_of_real, keep=KEEP_REAL):
    return float(np.quantile(p_real_of_real, 1 - keep)) if len(p_real_of_real) else 0.5


def cv_threshold(rows, k=5, seed=7):
    """Out-of-fold P(real) for every row; threshold keeps KEEP_REAL of real events."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(rows))
    oof = np.zeros(len(rows))
    for f in range(k):
        te = idx[f::k]
        tr = np.setdiff1d(idx, te)
        m = Model().fit([rows[i] for i in tr])
        oof[te] = m.proba([rows[i] for i in te])
    y = np.array([r["y"] for r in rows])
    return oof, _threshold_for(oof[y == 1])


def _report(p, y, thr):
    real, fake = p[y == 1], p[y == 0]
    kept = float((real >= thr).mean()) if len(real) else 0
    caught = float((fake < thr).mean()) if len(fake) else 0
    prec = float(((p >= thr) & (y == 1)).sum() / max(1, (p >= thr).sum()))
    return kept, caught, prec


import threading
_LOCK = threading.Lock()


def production():
    with _LOCK:                                   # event_detail calls this from worker threads
        return _production()


@lru_cache(maxsize=1)
def _production():
    """Model trained on every reviewed filing; threshold from 5-fold CV."""
    import os
    rows = corpus()
    if os.environ.get("EVENT_MODEL_TRAIN"):          # the scorecard trains on 'dev' only
        rows = [r for r in rows if r["split"] == os.environ["EVENT_MODEL_TRAIN"]]
    _, thr = cv_threshold(rows)
    m = Model().fit(rows)
    m.threshold = thr
    return m


def p_real(fam, exc, lede, filed):
    try:
        m = production()
    except Exception:
        return None
    return float(m.proba([{"family": fam, "excerpt": exc, "lede": lede, "filed": filed}])[0]), m.threshold


def main() -> int:
    rows = corpus()
    dev = [r for r in rows if r["split"] == "dev"]
    hold = [r for r in rows if r["split"] == "holdout"]
    oof, thr = cv_threshold(dev)                     # threshold from dev only
    m = Model().fit(dev)
    p = m.proba(hold)
    y = np.array([r["y"] for r in hold])
    k, c, pr = _report(p, y, thr)
    from sklearn.metrics import roc_auc_score
    print(f"train dev (n={len(dev)}) -> holdout (n={len(hold)}): AUC {roc_auc_score(y, p):.3f}; "
          f"real kept {k:.0%}, phantoms caught {c:.0%}, precision {pr:.0%} (threshold {thr:.2f})")
    oof, thr = cv_threshold(rows)
    y = np.array([r["y"] for r in rows])
    k, c, pr = _report(oof, y, thr)
    print(f"5-fold CV over all {len(rows)}: AUC {roc_auc_score(y, oof):.3f}; real kept {k:.0%}, "
          f"phantoms caught {c:.0%}, precision {pr:.0%} (threshold {thr:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
