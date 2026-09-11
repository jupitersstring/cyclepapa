"""Finalize: integrate cancel_10b5_1 across the full universe.

Re-runs the composite once the universe scan completes. For each
ticker with a non-zero 10b5-1 signal, cross-references with the
prior asymmetry layers and outputs a refreshed ranking.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/home/user/cyclepapa")


def main() -> int:
    cxl = json.loads((ROOT / "cancel_10b5_1.json").read_text())
    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    fz = json.loads((ROOT / "psu_forensics_v2.json").read_text())
    forensic = json.loads((ROOT / "forensic_asymmetry.json").read_text())
    step = {r["ticker"]: r for r in
            csv.DictReader(open(ROOT / "step_change.csv"))}
    sc13d_p = ROOT / "sc13d_recent.json"
    sc13d = json.loads(sc13d_p.read_text()) if sc13d_p.exists() else {}
    sc13d_set = set(sc13d.keys()) if isinstance(sc13d, dict) else set()
    quick_p = ROOT / "yfinance_quick.json"
    quick = json.loads(quick_p.read_text()) if quick_p.exists() else {}

    now = datetime.now(timezone.utc)

    def days_ago(d):
        if not d:
            return None
        try:
            return (now - datetime.strptime(
                d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
        except Exception:
            return None

    def insider_pack(tk):
        rec = f4.get(tk) or {}
        filings = rec.get("filings") or []
        if not filings:
            return {"cluster": 0, "ceo": False, "cfo": False, "tot": 0,
                    "n30": 0, "window_days": None}
        titles = {}
        for b in rec.get("buyer_set") or []:
            p = b.split("|")
            if len(p) >= 2:
                titles[p[0].strip()] = p[1].strip()
        persons_by_date = {}
        has_ceo = has_cfo = False
        n30 = 0
        tot = 0.0
        for fl in filings:
            d = fl.get("date")
            if not d:
                continue
            t = fl.get("title") or titles.get(
                (fl.get("person") or "").strip(), "")
            tl = (t or "").lower()
            if "ceo" in tl or "chief executive" in tl:
                has_ceo = True
            if "cfo" in tl or "chief financial" in tl:
                has_cfo = True
            da = days_ago(d)
            if da is not None and da <= 30:
                n30 += 1
            tot += float(fl.get("dollar") or 0)
            persons_by_date.setdefault(d, set()).add(fl.get("person"))
        dates = sorted(persons_by_date.keys())
        best = 0
        best_window = None
        for i, d1 in enumerate(dates):
            try:
                dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
            except Exception:
                continue
            clu = set()
            for d2 in dates[i:]:
                try:
                    dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
                except Exception:
                    continue
                if (dt2 - dt1).days <= 14:
                    clu |= persons_by_date[d2]
                else:
                    break
            if len(clu) > best:
                best = len(clu)
                best_window = d1
        return {
            "cluster": best, "ceo": has_ceo, "cfo": has_cfo,
            "tot": tot, "n30": n30,
            "window_days": days_ago(best_window),
        }

    def composite(tk):
        ins = insider_pack(tk)
        st = step.get(tk, {})
        fr = forensic.get(tk, {})
        fzn = fz.get(tk, {})
        cx = cxl.get(tk, {})
        score = 0.0
        reasons = []

        # 1. Insider cluster (max 35)
        clu = ins["cluster"]
        wd = ins["window_days"]
        rec_m = 1.0 if (wd is not None and wd <= 30) else (
            0.6 if wd is not None and wd <= 90 else 0.25)
        if clu >= 5:
            score += 25 * rec_m
            reasons.append(f"{clu}-buyer cluster {wd}d ago")
        elif clu >= 4:
            score += 20 * rec_m
            reasons.append(f"{clu}-buyer cluster {wd}d ago")
        elif clu >= 3:
            score += 14 * rec_m
            reasons.append(f"{clu}-buyer cluster {wd}d ago")
        elif clu >= 2:
            score += 6 * rec_m
        if ins["ceo"] and ins["cfo"]:
            score += 12
            reasons.append("CEO+CFO bought")
        elif ins["ceo"]:
            score += 6
            reasons.append("CEO bought")
        if ins["tot"] >= 5e6:
            score += 8
            reasons.append(f"${ins['tot']/1e6:.1f}M insider buys")
        elif ins["tot"] >= 1e6:
            score += 4

        # 2. Valuation tilt (only if we have data)
        q = quick.get(tk) or {}
        if q:
            px = q.get("price")
            lo = q.get("fwk_low")
            hi = q.get("fwk_high")
            pb = q.get("p_b")
            if px and lo and hi and hi > lo:
                dd = (px - lo) / (hi - lo) * 100
                if dd <= 10:
                    score += 18
                    reasons.append(f"{dd:.0f}% above 52w low")
                elif dd <= 25:
                    score += 12
                    reasons.append(f"{dd:.0f}% above 52w low")
                elif dd <= 40:
                    score += 6
            if pb is not None and 0 < pb <= 1.2:
                score += 6
                reasons.append(f"P/B {pb:.1f}")

        # 3. Step-change
        try:
            sc = float(st.get("step_change_score") or 0)
            if sc >= 50:
                score += 22
                reasons.append(f"step-change {sc:.0f}")
            elif sc >= 30:
                score += 12
                reasons.append(f"step-change {sc:.0f}")
            elif sc >= 15:
                score += 5
        except Exception:
            pass

        # 4. Forensic PSU
        try:
            fs = float(fr.get("forensic_score") or 0)
            if fs >= 30:
                score += 15
                reasons.append(f"forensic-PSU {fs:.0f}")
            elif fs >= 20:
                score += 9
                reasons.append(f"forensic-PSU {fs:.0f}")
        except Exception:
            pass

        # 5. 13D
        if tk in sc13d_set:
            score += 6
            reasons.append("13D filed")

        # 6. PSU heavy
        forensics = (fzn or {}).get("forensics") or {}
        psu_pct = (forensics.get("lti_mix") or {}).get("psu_pct")
        if psu_pct and psu_pct >= 70:
            score += 5
            reasons.append(f"PSU {psu_pct}% LTI")

        # 7. 10b5-1 (signed, cap ±25)
        cx_score = float(cx.get("score") or 0)
        cx_capped = max(-25.0, min(25.0, cx_score))
        if cx_capped != 0:
            sign = "+" if cx_capped > 0 else ""
            reasons.append(f"10b5-1 leg {sign}{cx_capped:.0f}")
            score += cx_capped

        return score, reasons, ins, cx_score

    # Build full ranking
    all_tk = (set(cxl.keys()) | set(f4.keys()) | set(forensic.keys()) |
              set(step.keys()) | set(fz.keys()))
    rows = []
    for tk in all_tk:
        sc, reasons, ins, cx_score = composite(tk)
        if sc < 15 and cx_score == 0:
            continue
        q = quick.get(tk, {})
        rows.append({
            "ticker": tk,
            "name": (q.get("name") or "")[:35],
            "mcap_musd": (q.get("mcap") or 0) / 1e6 if q.get("mcap") else None,
            "price": q.get("price"),
            "drawdown_pct": (
                (q.get("price") - q.get("fwk_low")) /
                (q.get("fwk_high") - q.get("fwk_low")) * 100
                if (q.get("price") and q.get("fwk_low") and q.get("fwk_high")
                    and q.get("fwk_high") > q.get("fwk_low")) else None
            ),
            "score": round(sc, 1),
            "cluster": ins["cluster"],
            "ceo_cfo": ins["ceo"] and ins["cfo"],
            "tot_insider_musd": round(ins["tot"] / 1e6, 2),
            "step_change": step.get(tk, {}).get("step_change_score"),
            "cancel_10b5_1": round(cx_score, 1),
            "10b5_term_sell": (cxl.get(tk, {}).get("counts") or {}).get(
                "term_sell", 0),
            "10b5_adopt_sell": (cxl.get(tk, {}).get("counts") or {}).get(
                "adopt_sell", 0),
            "10b5_reasons": " | ".join(
                (cxl.get(tk, {}).get("reasons") or []))[:240],
            "reasons": " | ".join(reasons)[:240],
        })

    rows.sort(key=lambda r: -r["score"])
    with open(ROOT / "asymmetric_full_universe.csv", "w", newline="") as f:
        fields = ["rank", "ticker", "name", "mcap_musd", "price",
                  "drawdown_pct", "score", "cluster", "ceo_cfo",
                  "tot_insider_musd", "step_change",
                  "cancel_10b5_1", "10b5_term_sell", "10b5_adopt_sell",
                  "10b5_reasons", "reasons"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)

    # Top 10b5-1 bullish (sell-plan terminations)
    bull = sorted(
        [(tk, v) for tk, v in cxl.items()
         if (v.get("counts") or {}).get("term_sell", 0) > 0],
        key=lambda kv: -(kv[1].get("score") or 0))
    bear = sorted(
        [(tk, v) for tk, v in cxl.items()
         if (v.get("counts") or {}).get("adopt_sell", 0) > 0],
        key=lambda kv: kv[1].get("score") or 0)

    print(f"\n=== FULL UNIVERSE ASYMMETRY RANKING ===")
    print(f"Total tickers scored: {len(rows)}\n")
    print(f"=== TOP 25 BY INTEGRATED SCORE ===")
    print(f"{'#':<3}{'TKR':<7}{'MCAP':>10}{'PX':>8}{'DD%':>5}"
          f"{'SCR':>5}{'CLU':>4}{'10b5':>6}  REASONS")
    print("-" * 200)
    for i, r in enumerate(rows[:25], 1):
        mc = f"{float(r['mcap_musd']):>9.0f}M" if r['mcap_musd'] else "        ?M"
        px = f"{float(r['price']):>8.2f}" if r['price'] else "       ?"
        dd = f"{float(r['drawdown_pct']):>5.0f}" if r['drawdown_pct'] is not None else "    ?"
        print(f"{i:<3}{r['ticker']:<7}{mc}{px}{dd}{r['score']:>5.0f}"
              f"{r['cluster']:>4}{r['cancel_10b5_1']:>+6.0f}  "
              f"{r['reasons'][:130]}")

    print(f"\n=== TOP 25 BULLISH 10b5-1 (sell-plan terminations) ===")
    print(f"{'#':<3}{'TKR':<7}{'TS':>4}{'AS':>4}{'SCR':>5}  REASONS")
    for i, (tk, v) in enumerate(bull[:25], 1):
        c = v.get("counts", {})
        print(f"{i:<3}{tk:<7}{c.get('term_sell',0):>4}"
              f"{c.get('adopt_sell',0):>4}{v.get('score',0):>5.0f}  "
              f"{(' | '.join(v.get('reasons') or []))[:150]}")

    print(f"\n=== TOP 25 BEARISH 10b5-1 (sell-plan adoptions) ===")
    print(f"{'#':<3}{'TKR':<7}{'AS':>4}{'TS':>4}{'SCR':>5}  REASONS")
    for i, (tk, v) in enumerate(bear[:25], 1):
        c = v.get("counts", {})
        print(f"{i:<3}{tk:<7}{c.get('adopt_sell',0):>4}"
              f"{c.get('term_sell',0):>4}{v.get('score',0):>5.0f}  "
              f"{(' | '.join(v.get('reasons') or []))[:150]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
