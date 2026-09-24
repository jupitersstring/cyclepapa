"""Sector hygiene on proxy-derived catalyst categories (runs before the
archetype / consensus stages).

The proxy text classifier's `fda_phase_milestone` pattern (Phase 3, CE mark,
marketing authorization, ...) also fires on non-healthcare proxies -- a
pool-supplies distributor's ERP "Phase 3", a paper company's "marketing
authorization". An FDA / clinical milestone only counts for Healthcare
issuers (sector from the quote store); for everyone else it is removed.

Rewrites cond_cats in proxy_scan*.json in place; prints what it removed.
"""
import ast
import glob
import json
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
GATED = {"fda_phase_milestone": {"Healthcare"}}


def cats_of(v):
    if isinstance(v, list):
        return v, "list"
    if isinstance(v, str) and v.startswith("["):
        try:
            return list(ast.literal_eval(v)), "str"
        except (ValueError, SyntaxError):
            return [], "str"
    return [], None


def main() -> int:
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    removed = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        d = json.loads(Path(fn).read_text())
        items = d if isinstance(d, list) else list(d.values())
        changed = False
        for r in items:
            if not isinstance(r, dict) or "cond_cats" not in r:
                continue
            cats, kind = cats_of(r["cond_cats"])
            sector = (yq.get(r.get("ticker")) or {}).get("sector")
            keep = [c for c in cats if c not in GATED or (sector in GATED[c])]
            if len(keep) != len(cats):
                removed.setdefault(r.get("ticker"), sector)
                r["cond_cats"] = keep if kind == "list" else str(keep)
                changed = True
        if changed:
            io_util.write_json(Path(fn), d)
    print(f"proxy hygiene: removed fda_phase_milestone from {len(removed)} non-healthcare issuers "
          f"(e.g. {', '.join(list(removed)[:8])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
