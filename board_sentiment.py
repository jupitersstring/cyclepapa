"""Board-commentary sentiment from results / interim filings.

For each interim-results / final-results / annual-results RNS body
we score the board's posture on a defensive↔constructive axis. The
posture is a leading indicator of corporate-action willingness:

  Defensive  ←  "challenging environment, headwinds, remain confident,
                 long-term, patience"  =  status-quo bias
  Neutral    ←  performance commentary, routine outlook
  Constructive →  "actively reviewing, considering all options, in
                  dialogue with shareholders, evaluating structure"  =
                  catalyst-coming bias

Two extractors:

  (1) Heuristic — keyword density + saturating non-linearity. Free,
      deterministic, ships immediately. Used by default.

  (2) LLM (Anthropic API) — passes the first ~6000 chars of the body
      to claude-haiku for a per-filing rating with a structured prompt.
      Only used when ANTHROPIC_API_KEY is set AND the `anthropic`
      package is installed. Falls back to heuristic on any failure.

Per-URL cache lives in data/investegate/sentiment/. Body text is
hashed into the cache so re-runs are free.

Output: data/board_sentiment.csv  with (ticker, date, score, method,
        n_phrases_defensive, n_phrases_constructive, sample_phrase)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
SENTIMENT_DIR = INV_DIR / "sentiment"
OUT_PATH = HERE / "data" / "board_sentiment.csv"

USER_AGENT = "Mozilla/5.0 (compatible; CyclepapaSentiment/1.0)"

# Slug patterns that contain board commentary worth scoring.
RESULTS_SLUGS = re.compile(
    r"interim-results|half-year(ly)?-results|preliminary-results"
    r"|annual-results|final-results|results-for-(the-)?(year|period)"
    r"|annual-financial-report|chairman.{0,20}statement"
    r"|chief-executive.{0,20}statement|strategic-update"
    r"|investor-update|results-of-strategy-review",
    re.IGNORECASE,
)

DEFENSIVE_PHRASES = [
    "remain confident", "remains confident", "are confident",
    "long-term value", "long term value",
    "long-term opportunity", "long term opportunity",
    "patience", "patient capital",
    "challenging environment", "challenging market",
    "challenging conditions", "headwind", "uncertain",
    "we believe in", "we continue to believe",
    "stay the course", "remain committed to our strategy",
    "continue to deliver", "remain well positioned",
    "no change to our strategy",
]

CONSTRUCTIVE_PHRASES = [
    "actively reviewing", "actively considering", "currently reviewing",
    "considering all options", "all options remain", "all options on the table",
    "evaluating strategic", "exploring strategic", "exploring options",
    "in active dialogue", "engaged with shareholders",
    "engaging with shareholders", "shareholder engagement",
    "managed wind-down", "managed wind down",
    "return of capital", "capital distribution", "tender offer",
    "open-end", "open ended conversion",
    "discount control", "narrow the discount", "address the discount",
    "strategic review", "strategy refresh", "reset and roadmap",
    "responding to shareholder", "we have appointed", "appointed advisers",
    "appointed advisor", "appointed a broker", "appointed a financial adviser",
    "considering proposals", "evaluating proposals",
    "intend to propose", "putting proposals to shareholders",
]


def _compile(phrases: list[str]) -> re.Pattern:
    parts = [re.escape(p).replace(r"\ ", r"\s+") for p in phrases]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


DEFENSIVE_RE = _compile(DEFENSIVE_PHRASES)
CONSTRUCTIVE_RE = _compile(CONSTRUCTIVE_PHRASES)


# ---------------------------------------------------------------------

def _fetch_body(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    import html as _html
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _cache_path(url: str) -> Path:
    SENTIMENT_DIR.mkdir(parents=True, exist_ok=True)
    rns_id = re.sub(r"[^A-Za-z0-9]+", "_", url.rstrip("/").split("/")[-1])
    return SENTIMENT_DIR / f"{rns_id}.json"


def heuristic_score(text: str) -> dict:
    """Return {score, n_defensive, n_constructive, samples}."""
    if not text:
        return {"score": 0.0, "n_defensive": 0, "n_constructive": 0,
                "samples": [], "method": "heuristic"}
    defs = DEFENSIVE_RE.findall(text)
    cons = CONSTRUCTIVE_RE.findall(text)
    n_def = len(defs)
    n_con = len(cons)

    def _sat(x: float) -> float:
        return 1.0 - 1.0 / (1.0 + x / 2.0)

    s_def = _sat(n_def)
    s_con = _sat(n_con)
    # Score: range -1 (purely defensive) to +1 (purely constructive)
    if s_def + s_con == 0:
        score = 0.0
    else:
        score = (s_con - s_def) / (s_con + s_def + 0.05)
    # Snippets — take first matches in context
    samples = []
    for m in DEFENSIVE_RE.finditer(text):
        if len(samples) >= 2:
            break
        i = max(0, m.start() - 30)
        j = min(len(text), m.end() + 30)
        samples.append(f"DEF: …{text[i:j]}…")
    for m in CONSTRUCTIVE_RE.finditer(text):
        if len(samples) >= 4:
            break
        i = max(0, m.start() - 30)
        j = min(len(text), m.end() + 30)
        samples.append(f"CON: …{text[i:j]}…")
    return {
        "score": round(score, 3),
        "n_defensive": n_def,
        "n_constructive": n_con,
        "samples": samples,
        "method": "heuristic",
    }


def llm_score(text: str) -> dict | None:
    """Anthropic-API-based scoring. Returns None if API or SDK missing.

    Prompts the model to read the first 6000 chars and emit a single
    JSON with score [-1, 1], rationale, key_phrases. Costs ~$0.0003
    per filing on Haiku."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "You are scoring a UK closed-end fund board's "
                    "posture from their results commentary on a "
                    "defensive↔constructive axis. Score range -1 "
                    "(highly defensive: 'remain confident in our "
                    "strategy', long-term, patience) to +1 "
                    "(actively considering corporate change: "
                    "strategic review, advisor appointed, return of "
                    "capital proposed). Output ONLY compact JSON like "
                    '{"score": 0.4, "rationale": "...", '
                    '"key_phrases": ["...", "..."]}.\n\n'
                    f"Text: {text[:6000]}"
                ),
            }],
        )
        content = msg.content[0].text if msg.content else "{}"
        rec = json.loads(content)
        return {
            "score": float(rec.get("score") or 0.0),
            "rationale": rec.get("rationale", "")[:200],
            "key_phrases": rec.get("key_phrases", [])[:4],
            "method": "llm",
        }
    except Exception:
        return None


def score_filing(url: str, use_cache: bool = True,
                 try_llm: bool = True) -> dict | None:
    cp = _cache_path(url)
    if use_cache and cp.exists():
        try:
            return json.loads(cp.read_text())
        except Exception:
            pass
    body = _fetch_body(url)
    if not body:
        return None
    res = None
    if try_llm:
        res = llm_score(body)
    if res is None:
        res = heuristic_score(body)
    if use_cache:
        try:
            cp.write_text(json.dumps(res))
        except Exception:
            pass
    return res


def collect(lookback_days: int = 365) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out = []
    for jf in sorted(INV_DIR.glob("*.json")):
        if jf.parent.name != "investegate":
            continue
        epic = jf.stem
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for a in data:
            slug = a.get("raw_slug") or ""
            title = a.get("title") or ""
            if not (RESULTS_SLUGS.search(slug) or RESULTS_SLUGS.search(title)):
                continue
            d = a.get("date") or ""
            try:
                dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if dt < cutoff:
                continue
            res = score_filing(a.get("url") or "", use_cache=True)
            if not res:
                continue
            out.append({
                "ticker": f"{epic}.L",
                "epic": epic,
                "date": d,
                "score": res.get("score", 0.0),
                "method": res.get("method", "heuristic"),
                "n_defensive": res.get("n_defensive", 0),
                "n_constructive": res.get("n_constructive", 0),
                "title": title[:80],
            })
    return out


def per_ticker(rows: list[dict]) -> dict[str, dict]:
    """Roll up to ticker: latest score, most-recent date, n_filings."""
    out: dict[str, dict] = {}
    for r in rows:
        t = r["ticker"]
        cur = out.get(t)
        if cur is None or r["date"] > cur["date"]:
            out[t] = dict(r)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lookback-days", type=int, default=365)
    p.add_argument("--max", type=int, default=200,
                   help="Cap on filings scored this run (HTTP cost)")
    args = p.parse_args()
    # Pass 1: find candidate URLs, sort by recency, score the most recent N
    candidates = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    for jf in INV_DIR.glob("*.json"):
        if jf.parent.name != "investegate":
            continue
        epic = jf.stem
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for a in data:
            slug = a.get("raw_slug") or ""
            title = a.get("title") or ""
            if not (RESULTS_SLUGS.search(slug) or RESULTS_SLUGS.search(title)):
                continue
            d = a.get("date") or ""
            try:
                dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if dt < cutoff:
                continue
            candidates.append({"ticker": f"{epic}.L", "epic": epic,
                               "date": d, "url": a.get("url") or "",
                               "title": title})
    candidates.sort(key=lambda r: r["date"], reverse=True)
    candidates = candidates[: args.max]
    print(f"Scoring {len(candidates)} results filings", file=sys.stderr)
    rows = []
    n_llm = 0
    n_heur = 0
    for c in candidates:
        res = score_filing(c["url"], use_cache=True)
        if not res:
            continue
        if res.get("method") == "llm":
            n_llm += 1
        else:
            n_heur += 1
        rows.append({
            "ticker": c["ticker"], "epic": c["epic"], "date": c["date"],
            "score": res.get("score", 0.0),
            "method": res.get("method", "heuristic"),
            "n_defensive": res.get("n_defensive", 0),
            "n_constructive": res.get("n_constructive", 0),
            "title": c["title"][:80],
        })
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(OUT_PATH, "w", newline="") as f:
            cols = ["ticker", "epic", "date", "score", "method",
                    "n_defensive", "n_constructive", "title"]
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"Wrote {len(rows)} rows to {OUT_PATH} "
              f"(llm={n_llm}, heuristic={n_heur})", file=sys.stderr)
        # Top constructive / defensive
        rows_sorted = sorted(rows, key=lambda r: r["score"], reverse=True)
        print("\nTop CONSTRUCTIVE board commentary:", file=sys.stderr)
        for r in rows_sorted[:8]:
            print(f"  {r['ticker']:<10}  {r['score']:+.2f}  "
                  f"({r['n_constructive']}c/{r['n_defensive']}d)  "
                  f"{r['date']}  {r['title'][:50]}", file=sys.stderr)
        print("\nMost DEFENSIVE:", file=sys.stderr)
        for r in rows_sorted[-8:]:
            print(f"  {r['ticker']:<10}  {r['score']:+.2f}  "
                  f"({r['n_constructive']}c/{r['n_defensive']}d)  "
                  f"{r['date']}  {r['title'][:50]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
