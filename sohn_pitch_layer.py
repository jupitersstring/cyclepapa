"""Sohn Conference pitch layer.

Public pitches at the Sohn Investment Conference are high-conviction,
reputation-staked ideas from professional managers -- a curated external
signal orthogonal to our EDGAR-derived layers. Longs add, shorts
subtract; conviction decays as the pitch ages (the alpha window for
conference picks concentrates in the months after the pitch).

Source: sohn_pitches.json -- curated from public conference coverage
after each conference (see _meta.sources). This is hand-refreshed, not
scraped: conference lineups have no structured feed.

Output: sohn_pitch_scores.json {ticker: {score, ...}} for the consensus.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "sohn_pitches.json"
OUT = ROOT / "sohn_pitch_scores.json"

BASE = {"main": 15.0, "next_wave": 12.0}
SHORT_MULT = -0.8   # shorts subtract, slightly dampened (borrow/timing risk)


def age_factor(conf_date: str, today: datetime | None = None) -> float:
    if today is None:
        today = datetime.now(timezone.utc)
    try:
        d = datetime.strptime(conf_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return 0.5
    days = (today - d).days
    if days <= 120:
        return 1.0
    if days <= 365:
        return 0.6
    if days <= 540:
        return 0.3
    return 0.0


def score_pitch(p: dict, conf_date: str, today: datetime | None = None) -> float:
    base = BASE.get(p.get("stage") or "main", 12.0)
    if p.get("low_confidence"):
        base *= 0.5
    s = base * age_factor(conf_date, today)
    if (p.get("side") or "long") == "short":
        s *= SHORT_MULT
    return round(s, 1)


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}")
        return 1
    data = json.loads(SRC.read_text())
    conf_date = (data.get("_meta") or {}).get("date") or ""
    out: dict[str, dict] = {}
    for p in data.get("pitches") or []:
        tk = (p.get("ticker") or "").strip().upper()
        if not tk:
            continue
        s = score_pitch(p, conf_date)
        rec = out.setdefault(tk, {"score": 0.0, "pitches": []})
        rec["score"] = round(rec["score"] + s, 1)
        rec["pitches"].append({
            "presenter": p.get("presenter"), "fund": p.get("fund"),
            "side": p.get("side"), "stage": p.get("stage"),
            "conference_date": conf_date, "points": s})
    OUT.write_text(json.dumps(out, indent=2))
    nz = sum(1 for v in out.values() if v["score"] != 0)
    print(f"wrote {OUT} ({len(out)} tickers, {nz} scoring)")
    for tk, v in sorted(out.items(), key=lambda x: -x[1]["score"]):
        ps = v["pitches"][0]
        print(f"  {tk:8}{v['score']:>7.1f}  {ps.get('side')}  "
              f"{(ps.get('presenter') or ps.get('fund') or '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
