"""Build the full US-listed operating-company universe.

Replaces the screen-union universe (selection-biased: only names that
already triggered a prior screen) with the complete SEC ticker map,
filtered to listed operating companies:

  Source: https://www.sec.gov/files/company_tickers_exchange.json
          (ticker, CIK, company name, exchange for every registrant)

  Keep:   NYSE / Nasdaq / NYSE American (MKT) / CBOE listings
  Drop:   - OTC / blank exchange (shells, dark companies)
          - universe_filter exclusions (SPAC warrants/units, preferreds)
          - fund/trust/ETF name tokens (closed-end funds, unit trusts)
          - non-common suffixes (-W, -U, -R handled by universe_filter)

Outputs:
  full_universe.txt     the new, wider universe (supersedes old)
  universe_delta.txt    tickers NEW vs the previous universe -- the
                        work queue for backfilling scans
  universe_meta.json    ticker -> {name, exchange, cik} for the keepers
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")

KEEP_EXCHANGES = {"NYSE", "Nasdaq", "NYSE MKT", "NYSE American", "CBOE",
                  "NYSE Arca"}

# Name tokens that mark funds/trusts/SPAC shells rather than operating
# companies. Conservative: only unambiguous fund vocabulary.
FUND_TOKENS = re.compile(
    r"\b(closed[- ]end|exchange[- ]traded fund|\bETF\b|unit trust|"
    r"municipal (?:bond|income)|tax[- ]free income|"
    r"(?:bond|income|dividend|equity|allocation) fund\b|fund (?:inc|trust)\b|"
    r"acquisition corp|acquisition company|blank check|"
    r"capital corp ii|spac\b)",
    re.I,
)


def main() -> int:
    from edgar import _get
    sys.path.insert(0, str(ROOT))
    from universe_filter import is_excluded

    data = _get("https://www.sec.gov/files/company_tickers_exchange.json").json()
    fields = data["fields"]          # ["cik","name","ticker","exchange"]
    idx = {f: i for i, f in enumerate(fields)}
    rows = data["data"]
    print(f"SEC registry: {len(rows)} ticker entries", file=sys.stderr)

    old = set()
    old_p = ROOT / "full_universe.txt"
    if old_p.exists():
        old = {t.strip().upper() for t in old_p.read_text().splitlines()
               if t.strip()}

    keep: dict[str, dict] = {}
    n_exch = n_filter = n_fund = n_malformed = 0
    for r in rows:
        tk = (r[idx["ticker"]] or "").upper().strip()
        name = r[idx["name"]] or ""
        exch = r[idx["exchange"]] or ""
        cik = r[idx["cik"]]
        if not tk or not re.match(r"^[A-Z]{1,5}$", tk):
            n_malformed += 1
            continue
        if exch not in KEEP_EXCHANGES:
            n_exch += 1
            continue
        bad, _why = is_excluded(tk, name)
        if bad:
            n_filter += 1
            continue
        if FUND_TOKENS.search(name):
            n_fund += 1
            continue
        keep[tk] = {"name": name, "exchange": exch, "cik": cik}

    # Union with the old universe so nothing already-scanned is dropped
    # (old names keep their cached state even if delisted since).
    new_universe = sorted(set(keep) | old)
    delta = sorted(set(keep) - old)

    (ROOT / "full_universe.txt").write_text("\n".join(new_universe))
    (ROOT / "universe_delta.txt").write_text("\n".join(delta))
    (ROOT / "universe_meta.json").write_text(
        json.dumps(keep, indent=1, sort_keys=True))

    print(f"Dropped: {n_exch} off-exchange, {n_filter} universe_filter, "
          f"{n_fund} fund-tokens, {n_malformed} malformed", file=sys.stderr)
    print(f"Kept from registry: {len(keep)}", file=sys.stderr)
    print(f"Old universe: {len(old)}", file=sys.stderr)
    print(f"New universe: {len(new_universe)} "
          f"(delta to backfill: {len(delta)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
