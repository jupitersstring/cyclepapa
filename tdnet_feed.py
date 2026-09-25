"""Japan: TDnet timely disclosures (the exchange's own feed) -> classified events.

TDnet publishes every listed company's timely disclosures, but its public list keeps
only ~31 days, so this module ARCHIVES each day (fmp_cache/tdnet/YYYYMMDD.json) and
the history grows with every run. Titles are classified with a Japanese keyword
taxonomy into the same event vocabulary the US books use:

  buyback / cancellation / self-tender / tender offer (company is the target) / MBO /
  merger or share exchange / subsidiary or asset sale / cross-shareholding sale /
  dividend increase or special dividend / cost-of-capital & PBR plan (TSE request) /
  mid-term plan / shareholder proposal, EGM, takeover-defence response / CEO change /
  guidance revised up or down
  red flags: going-concern note, delisting / supervision, restatement, share consolidation

Company code -> FMP symbol: first four characters + '.T' (130A0 -> 130A.T).
Accuracy (hand-checked random samples of the classified titles, 2026-09-25): 77% on the first
taxonomy -> ~92% after two refinement rounds (remaining misses: EGMs called for non-activist
reasons, a few bidder-side tender notices).

Output: tdnet_events.json {symbol: [{date, time, type, what, title, url}]}
"""

from __future__ import annotations

import html
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path("/home/user/cyclepapa")
ARCH = ROOT / "fmp_cache" / "tdnet"
OUT = ROOT / "tdnet_events.json"
BASE = "https://www.release.tdnet.info/inbs/"
UA = {"User-Agent": "Mozilla/5.0 (cyclepapa research)"}

# (type, English label, pattern) -- first match wins; order matters
TAXONOMY = [
    # red flags (listing-standard breaches, going concern, restated past results)
    ("RED_FLAG_going_concern", "going-concern note", r"継続企業の前提"),
    ("RED_FLAG_delisting_notice", "listing-standard breach / supervision or delisting designation",
     r"監理銘柄|整理銘柄|上場維持基準.{0,10}(?:不適合|抵触|未達)|上場廃止.{0,6}(?:猶予期間|のおそれ)"),
    ("RED_FLAG_non_reliance", "restatement of past results", r"過年度.{0,20}訂正|有価証券報告書.{0,10}訂正報告書"),
    # take-private mechanics (in Japan a share consolidation is the squeeze-out step, not a distress reverse split)
    ("JP_MBO", "management buyout", r"マネジメント・バイアウト|ＭＢＯ|MBO"),
    ("JP_SELF_TENDER", "self-tender offer (company buys its own shares)", r"自己株式の公開買付け"),
    ("JP_HOSTILE_TENDER", "hostile tender offer for the company (board opposes)", r"公開買付け.{0,40}反対|反対の意見表明"),
    ("JP_TENDER_TARGET", "tender offer for the company (board opinion)", r"公開買付け.{0,40}(?:賛同|意見表明)|当社株式.{0,10}公開買付"),
    ("JP_STAKEBUILDING", "stake-building / change of major shareholder", r"買集め|主要株主.{0,6}異動|筆頭株主.{0,6}異動|大株主.{0,6}異動"),
    ("JP_SQUEEZE_OUT", "share consolidation / squeeze-out after a take-private", r"株式併合|株式等売渡請求"),
    ("JP_DELISTING_TAKEOUT", "delisting (typically after a completed take-private)", r"上場廃止"),
    ("JP_TENDER", "tender offer (company as bidder or other)", r"公開買付"),
    # internal reorganisations are not deals
    ("JP_INTERNAL_REORG", "internal reorganisation (group merger / holding-company move)",
     r"連結子会社(?:間|との|の)(?:吸収)?合併|完全子会社.{0,30}(?:吸収)?合併|子会社間|持株会社体制|効力発生日の変更|吸収分割.{0,20}(?:子会社|グループ)"),
    ("JP_INSIDER_BUY", "director / CEO buying the company's shares", r"(?:代表取締役|取締役|社長).{0,30}当社株式の取得"),
    ("JP_NOT_EVENT", "share-compensation plan share purchase", r"株式報酬|株式給付信託|ＥＳＯＰ|ESOP|無償取得"),
    ("JP_BUYBACK_PROGRESS_", "buyback progress / results report", r"自己株式.{0,20}(?:取得状況|取得結果|取得終了|進捗状況)"),
    ("JP_BUYBACK_", "share buyback decided", r"自己株式.{0,6}取得|自社株買い"),
    ("JP_ACQUISITION", "acquisition by the company (share purchase / making a subsidiary)",
     r"株式.{0,4}取得.{0,10}(?:子会社化|完全子会社)|完全子会社化|孫会社化|子会社化|(?<!自己)株式取得"),
    ("JP_MERGER", "merger / business integration with another company", r"株式交換|吸収合併|経営統合|株式移転|合併契約"),
    ("JP_BUYBACK_PROGRESS", "buyback progress / results report", r"自己株式.{0,20}(?:取得状況|取得結果|取得終了)"),
    ("JP_BUYBACK", "share buyback decided", r"自己株式.{0,6}取得|自社株買い"),
    ("JP_CANCEL", "treasury-share cancellation", r"自己株式.{0,4}消却"),
    ("JP_CROSS_SHARE_SALE", "sale of cross-shareholdings / investment securities", r"政策保有株式|投資有価証券.{0,6}売却"),
    ("JP_ASSET_SALE", "sale of a subsidiary / business / asset",
     r"(?:子会社|孫会社).{0,10}(?:株式|持分).{0,6}譲渡|株式譲渡|事業.{0,4}譲渡|固定資産.{0,4}譲渡|子会社.{0,6}異動.{0,10}譲渡"),
    ("JP_DIVIDEND_UP", "dividend raised / special or commemorative dividend", r"増配|特別配当|記念配当"),
    ("JP_DIVIDEND_CUT", "dividend cut or suspended", r"減配|無配"),
    ("JP_PAYOUT_POLICY", "shareholder-return / payout policy change", r"株主還元方針|配当方針|累進配当|配当性向"),
    ("JP_DIVIDEND_REVISION", "dividend forecast revised (direction in the filing)", r"配当予想.{0,6}修正"),
    ("JP_CAPITAL_PLAN", "cost-of-capital & share-price plan (TSE PBR request)", r"資本コストや株価を意識|資本コスト.{0,10}株価|PBR"),
    ("JP_MIDTERM_PLAN", "mid-term business plan", r"中期経営計画"),
    ("JP_ACTIVIST", "shareholder proposal / EGM / takeover-defence response", r"株主提案|臨時株主総会|大量買付|買収防衛|対応方針|株主.{0,6}書簡"),
    ("JP_CEO_CHANGE", "CEO change", r"代表取締役.{0,6}異動|社長.{0,6}交代"),
    ("JP_GUIDANCE_UP", "guidance raised", r"(?:業績|通期).{0,20}上方修正"),
    ("JP_GUIDANCE_DOWN", "guidance cut", r"(?:業績|通期).{0,20}下方修正"),
]
LABEL = {t.rstrip("_"): l for t, l, _ in TAXONOMY}


def _canon(t):
    return t.rstrip("_")


def classify(title):
    if re.match(r"^\s*[（(](?:訂正|取消|変更|開示事項の中止|開示事項の変更|中止)[）)]", title) or "一部訂正" in title \
            or re.match(r"^\s*「.*」の一部(?:変更|訂正)", title) or re.search(r"の中止に関する|撤回|取下げ|取り下げ", title):
        return None                          # a correction / amendment / withdrawal of an earlier notice
    for t, _, rx in TAXONOMY:
        if re.search(rx, title):
            return None if t == "JP_NOT_EVENT" else _canon(t)
    return None


def _get(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def parse(page):
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 4 or not re.fullmatch(r"[0-9A-Z]{5}", cells[1] or ""):
            continue
        pdf = re.findall(r'href="([^"]+\.pdf)"', row)
        out.append({"time": cells[0], "code": cells[1], "company": cells[2], "title": cells[3],
                    "url": BASE + pdf[0] if pdf else None})
    return out


def day(d: date):
    """All disclosures for one day (archived; today's page is refetched)."""
    ARCH.mkdir(parents=True, exist_ok=True)
    f = ARCH / f"{d:%Y%m%d}.json"
    if f.exists() and d < date.today() - timedelta(days=1):
        return json.loads(f.read_text())
    first = _get(f"{BASE}I_list_001_{d:%Y%m%d}.html")
    if first is None:
        return []
    rows = parse(first)
    pages = sorted({int(p) for p in re.findall(rf"I_list_(\d{{3}})_{d:%Y%m%d}\.html", first)} - {1})
    for p in pages:
        t = _get(f"{BASE}I_list_{p:03d}_{d:%Y%m%d}.html")
        if t:
            rows += parse(t)
        time.sleep(0.3)
    f.write_text(json.dumps(rows, ensure_ascii=False))
    return rows


def build(days=32):
    ev = {}
    n_all = 0
    for k in range(days):
        d = date.today() - timedelta(days=k)
        if d.weekday() >= 5:
            continue
        rows = day(d)
        n_all += len(rows)
    # the archive holds every day ever fetched: classify all of it
    for f in sorted(ARCH.glob("*.json")):
        d = f.stem
        dd = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        for r in json.loads(f.read_text()):
            t = classify(r["title"])
            if not t:
                continue
            sym = f"{r['code'][:4]}.T"
            ev.setdefault(sym, []).append({"date": dd, "time": r["time"], "type": t, "what": LABEL[t],
                                           "title": r["title"][:200], "company": r["company"], "url": r["url"]})
    for v in ev.values():
        v.sort(key=lambda e: (e["date"], e["time"]), reverse=True)
    OUT.write_text(json.dumps(ev, ensure_ascii=False, indent=1))
    return ev, n_all


def line(evs, n=3):
    """Short English line for a tab: the latest classified disclosures (red flags first)."""
    if not evs:
        return None
    evs = sorted(evs, key=lambda e: (not e["type"].startswith("RED_FLAG"), e["date"]), reverse=False)
    red = [e for e in evs if e["type"].startswith("RED_FLAG")]
    rest = sorted([e for e in evs if not e["type"].startswith("RED_FLAG")
                   and e["type"] not in ("JP_BUYBACK_PROGRESS", "JP_INTERNAL_REORG", "JP_DIVIDEND_REVISION")],
                  key=lambda e: e["date"], reverse=True)
    prog = sorted([e for e in evs if e["type"] == "JP_BUYBACK_PROGRESS"], key=lambda e: e["date"], reverse=True)
    pick = (red[:1] + rest)[:n]
    if not pick and prog:
        return f"[{prog[0]['date']}] buyback executing (monthly progress report)"
    return " | ".join(("⚠ " if e["type"].startswith("RED_FLAG") else "") + f"[{e['date']}] {e['what']}" for e in pick)


def main() -> int:
    ev, n = build()
    from collections import Counter
    c = Counter(e["type"] for v in ev.values() for e in v)
    print(f"TDnet: {n:,} disclosures fetched over the last month; {sum(c.values()):,} classified at "
          f"{len(ev):,} companies; archive {len(list(ARCH.glob('*.json')))} days")
    for k, v in c.most_common():
        print(f"  {k:<26} {v:>5}  {LABEL[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
