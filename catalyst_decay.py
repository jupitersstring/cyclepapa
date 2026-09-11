"""Catalyst decay -- bounded time-decay for event-driven layers.

SOURCES_AND_ANALYSIS A5: some layers age their signals (emergence, Sohn,
step-change freshness) while others held event catalysts at full strength
forever (a tender/placing/buyback/restructuring event from 14 months ago
scored the same as one filed last week). A stale catalyst should not
impersonate a live one.

"To an extent" (the explicit design instruction): decay is BOUNDED. A
signal fades from 1.0 toward a FLOOR -- never to zero -- because the
underlying structural fact (a company did do a selective buyback, a
distressed name did retire debt below par) still carries information long
after the event; it is only the *urgency/recency* premium that decays.
Half-lives are event-appropriate and generous; floors keep the structural
residue.

Applied at CONSENSUS time (not at scan time) so freshness is always
measured against today, and re-running the ranker re-decays without a
rescan.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Per-layer decay policy: (half_life_days, floor). Floor is the permanent
# structural residue; half_life is how fast the recency premium fades.
DECAY_POLICY = {
    "distressed_stub":     (180, 0.40),   # workout progress: stale steps still matter
    "premium_injection":   (270, 0.45),   # a revealed-preference buy ages slowly
    "selective_buyback":   (270, 0.45),
    "hidden_asset":        (365, 0.55),   # structural setup, decays gently
    "activist_letter":     (120, 0.35),   # activism is the most time-sensitive
    "backstopped_rights":  (180, 0.40),
}


def _parse(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
    except Exception:
        return None


def decay_multiplier(date_str, half_life_days=180, floor=0.4,
                     today: datetime | None = None) -> float:
    """floor + (1-floor) * 0.5^(age/half_life), clamped to [floor, 1.0].

    No date -> 1.0 (cannot decay what we cannot age; better to keep the
    signal than to silently penalise a missing field)."""
    d = _parse(date_str)
    if d is None:
        return 1.0
    if today is None:
        today = datetime.now(timezone.utc)
    age = (today - d).days
    if age <= 0:
        return 1.0
    frac = 0.5 ** (age / float(half_life_days))
    return max(floor, min(1.0, floor + (1.0 - floor) * frac))


def apply(layer_name: str, score: float, date_str) -> float:
    """Decay `score` per the layer's policy. Layers without a policy are
    returned unchanged (structural layers do not decay)."""
    if layer_name not in DECAY_POLICY or not score:
        return score
    hl, floor = DECAY_POLICY[layer_name]
    return round(score * decay_multiplier(date_str, hl, floor), 2)


def record_date(layer_name: str, rec: dict):
    """Best available event date for a record across the layer schemas."""
    if not isinstance(rec, dict):
        return None
    for k in ("date", "filing_date", "emergence_filing_date"):
        if rec.get(k):
            return rec[k]
    evs = rec.get("events") or []
    if evs and isinstance(evs, list):
        return max((e.get("date") or "" for e in evs), default=None) or None
    return None
