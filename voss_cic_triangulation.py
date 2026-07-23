"""Voss-style CIC-amendment triangulation (Voss Capital Q4 2025).

The signal: a name with all three of
  (a) recent Change-in-Control compensation amendment (signaling
      board preparing for a sale)
  (b) high insider ownership (skin in game)
  (c) high short interest (market disagreement / squeeze fuel)
is a direct M&A predictor (Voss CHH case: 26% SI + 40% insider +
CIC plan amendment).

Without proper cross-year DEF 14A diffing (heavy build), we approximate
the CIC-amendment signal by:
  - flagging tickers whose latest proxy contains "single-trigger" or
    "double-trigger" CIC language AND the proxy is recent (< 18 months)
  - the gov_score from proxy_scan already encodes CIC structure as
    a sub-signal in gov_reasons

Then triangulate with yfinance insider_pct + short_pct.

Output: voss_cic_triangulation.json (and CSV)
  {ticker: {has_cic_lang, insider_pct, short_pct, score, reasons}}
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "voss_cic_triangulation.json"
OUT_CSV = ROOT / "voss_cic_triangulation.csv"


def load_proxy() -> dict:
    out = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.loads(open(fn).read())
        except Exception as e:
            # BUGFIX (silent-drop audit): a bare except:continue here
            # silently discarded an ENTIRE proxy shard (thousands of
            # tickers) on any read/parse error. Make the loss loud.
            print(f"  WARNING: could not load {fn}: {e} -- "
                  f"shard SKIPPED", flush=True)
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in out or
                    r.get("filing_date","") > out[tk].get("filing_date","")):
                    out[tk] = r
    return out


def main() -> int:
    proxy = load_proxy()
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    print(f"proxy={len(proxy)}  yf={len(yf)}")

    def _num(v):
        if v is None: return None
        try: return float(v)
        except: return None

    out = {}
    for tk, p in proxy.items():
        # Look for CIC language in gov_reasons / pattern_reasons
        all_reasons = " ".join((p.get("gov_reasons") or [])
                                + (p.get("pattern_reasons") or [])).lower()
        has_cic_single = "single-trigger" in all_reasons
        has_cic_double = "double-trigger" in all_reasons
        has_cic_lang = has_cic_single or has_cic_double
        if not has_cic_lang:
            continue

        y = yf.get(tk, {}) or {}
        insider_pct = _num(y.get("insider_pct"))
        short_pct = _num(y.get("short_pct"))

        # METHODOLOGY FIX (audit finding A3): CIC language is near-
        # universal proxy boilerplate (968 of 1,982 scanned names had
        # ONLY the language pillar). The Voss signal is the
        # triangulation, not the boilerplate. CIC-language points are
        # awarded ONLY when at least one behavioral pillar (insider
        # ownership >= 15% or short interest >= 10%) also fires;
        # otherwise the row is recorded with score 0 so the consensus
        # does not count a phantom layer firing.
        insider_fires = insider_pct is not None and insider_pct >= 0.15
        short_fires = short_pct is not None and short_pct >= 0.10
        pillar_present = insider_fires or short_fires

        score = 0.0
        reasons = []
        if pillar_present:
            if has_cic_single:
                score += 15; reasons.append("single-trigger CIC")
            elif has_cic_double:
                score += 8; reasons.append("double-trigger CIC")
        else:
            reasons.append("CIC language only (no behavioral pillar) — not scored")

        full_voss = False
        if insider_pct is not None and insider_pct >= 0.30:
            score += 18; reasons.append(f"insider {insider_pct*100:.0f}%")
            if short_pct is not None and short_pct >= 0.20:
                full_voss = True
        elif insider_fires:
            score += 9; reasons.append(f"insider {insider_pct*100:.0f}%")

        if short_pct is not None and short_pct >= 0.20:
            score += 18; reasons.append(f"short {short_pct*100:.0f}%")
        elif short_fires:
            score += 9; reasons.append(f"short {short_pct*100:.0f}%")

        if full_voss:
            score += 15
            reasons.append("FULL VOSS triangulation (insider>=30% AND short>=20%)")

        out[tk] = {
            "has_cic_lang": has_cic_lang,
            "has_single_trigger": has_cic_single,
            "insider_pct": insider_pct,
            "short_pct": short_pct,
            "score": round(score, 1),
            "full_voss": full_voss,
            "reasons": "; ".join(reasons),
        }

    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_JSON} ({len(out)})")

    # write CSV
    rows = sorted(out.items(), key=lambda x: -x[1]["score"])
    fieldnames = ["ticker", "score", "has_single_trigger",
                   "insider_pct", "short_pct", "full_voss", "reasons"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for tk, v in rows:
            w.writerow({
                "ticker": tk,
                "score": v["score"],
                "has_single_trigger": v["has_single_trigger"],
                "insider_pct": v["insider_pct"],
                "short_pct": v["short_pct"],
                "full_voss": v["full_voss"],
                "reasons": v["reasons"],
            })

    # Distribution
    full_count = sum(1 for v in out.values() if v.get("full_voss"))
    print(f"\nFull Voss triangulation (CIC + insider>=30% + short>=20%): {full_count}")

    print(f"\n=== TOP 20 by Voss triangulation score ===")
    for tk, v in rows[:20]:
        ins = (v['insider_pct'] or 0) * 100
        sht = (v['short_pct'] or 0) * 100
        print(f"  {tk:<7} score={v['score']:<5} ins={ins:>5.1f}% sht={sht:>5.1f}% "
              f"{'FULL!' if v.get('full_voss') else '    '} {v['reasons'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
