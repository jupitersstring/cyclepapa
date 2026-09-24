"""Earnings-call INTENT engine -- is management signalling it will act on the
discount (buy back, tender, return capital, sell assets, run a strategic
review), and is that language NEW?

A systematic linguistic pipeline (pure Python, no model downloads), run over
the FMP transcript store (transcript_fetch.py):

 1. DISCOURSE STRUCTURE -- the call is split into speaker turns; speakers are
    classed operator / analyst (introduced by the operator, labelled
    "Analyst", or question-asking in Q&A) / management (everyone else), and
    the call into PREPARED remarks vs Q&A. Safe-harbour boilerplate dropped.
 2. CLAUSE SEGMENTATION -- management sentences are split into clauses on
    contrastive/concessive connectives (but, however, while, although, ;).
 3. ACTION FRAMES -- each clause is matched against ten intent families
    (BUYBACK, DIVIDEND_RETURN, TENDER, STRATEGIC_REVIEW, MONETIZE, DELEVER,
    GOVERNANCE, COST + two stance families VALUE_GAP, ANTICIPATION).
 4. COMMITMENT (speech-act strength) -- the clause's modal chain is graded on
    a commissive ladder:  REALISED 1.0 (have authorised / completed) >
    COMMITTED 0.9 (will / intend to / plan to) > INTENDED 0.6 (expect / aim /
    prioritise) > DELIBERATIVE 0.35 (evaluating / exploring) ; hedges
    (may / could / over time / opportunistically / if) scale it x0.55;
    unmarked first-person statements 0.45.
 5. AGENCY -- the actor must be the company ("we", "the board", "management");
    otherwise x0.6.
 6. NEGATION SCOPE -- a negation cue (not, no, never, n't, no plans, no
    intention) preceding the action term within the clause flips the frame to
    a NEGATIVE commitment ("we have no plans to sell the company").
 7. SPECIFICITY -- $ amounts, sizes (%/million/billion/shares) and time
    anchors (this quarter, by year-end, next 12 months, 2027) raise it:
    x(1 + 0.5*specificity).
 8. Q&A DYNAMICS -- analyst PRESSURE (questions on capital return / strategy /
    valuation) and management's RESPONSE to them: a committed answer vs
    EVASION ("not going to comment", "too early", "nothing to announce").
 9. NOVELTY -- each family's strength vs the same company's prior three calls:
    new or escalated language is the "recent change" signal.

Family score = top-3 clause scores (1, .5, .25 weights). The interpretable
INTENT score combines action families, value-gap awareness (x-boosted when
paired with a concrete action), anticipation, novelty and Q&A response. A
learned layer (call_intent_model.py) then fits these features to what
companies actually DID next (buybacks, dividend step-ups, action 8-Ks) and
to the forward re-rating, validated out of time.

Outputs: fmp_cache/call_features.jsonl (every call, for training),
         call_intent.json (latest call per ticker: scores, novelty, evidence).
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
STORE = ROOT / "fmp_cache" / "transcripts"
FEAT = ROOT / "fmp_cache" / "call_features.jsonl"
OUT = ROOT / "call_intent.json"

W = r"(?:\w+[-']?\w*\s+)"            # one word + space


def rx(*pats):
    return re.compile("|".join(f"(?:{p})" for p in pats), re.I)


FAMILIES = {
    "BUYBACK": rx(r"\b(?:share|stock)\s+(?:re)?purchase", r"\brepurchas\w*",
                  r"\bbuy\s?-?backs?\b", r"\bbought back\b", r"\bbuying back\b",
                  r"\bbuy back\b", r"\bretir(?:e|ed|ing)\s+" + W + r"{0,2}shares"),
    "DIVIDEND_RETURN": rx(r"\bspecial dividend", r"\b(?:increas|rais|doubl|grow)\w*\s+" + W + r"{0,3}dividend",
                          r"\bdividend\s+(?:increase|hike|growth)", r"\binitiat\w*\s+" + W + r"{0,3}dividend",
                          r"\breinstat\w*\s+" + W + r"{0,3}dividend",
                          r"\breturn(?:ing|ed)?\s+(?:\w+\s+){0,2}(?:capital|cash)\s+to\s+(?:our\s+)?(?:shareholders|stockholders|investors|owners|unitholders)",
                          r"\bcapital return", r"\breturn of capital"),
    "TENDER": rx(r"\btender offer", r"\bdutch auction", r"\bself[- ]tender", r"\bodd[- ]lot"),
    "STRATEGIC_REVIEW": rx(r"\bstrategic alternatives", r"\bstrategic (?:review|options)\b",
                           r"\breview of (?:our |its )?strategic", r"\bsale of the company",
                           r"\bsell(?:ing)? the company", r"\bmaximiz\w*\s+(?:shareholder|stockholder) value",
                           r"\bexplor\w*\s+(?:all |a range of |various |a full range of )?(?:options|alternatives)",
                           r"\b(?:merger|combination) partner", r"\b(?:take|go)[- ]private",
                           r"\b(?:engaged|retained|hired)\s+" + W + r"{0,3}(?:advisors?|advisers?|bankers?)"),
    "MONETIZE": rx(r"\bdivest\w*", r"\bmonetiz\w*", r"\bsale[- ]leaseback", r"\bnon[- ]core",
                   r"\bspin[- ]?(?:off|out)\b", r"\bseparation of\b", r"\bseparate (?:the|our)\s+" + W + r"{0,2}business",
                   r"\bcarve[- ]out", r"\basset sales?\b", r"\bunlock\w*\s+" + W + r"{0,2}value",
                   r"\b(?:sale|sell\w*)\s+(?:of\s+)?(?:our |the |this |that )?" + W +
                   r"{0,3}(?:business|segment|division|unit|assets?|propert(?:y|ies)|portfolio|stake|subsidiar\w+|real estate|land)\b"),
    "DELEVER": rx(r"\bde-?lever\w*", r"\b(?:pa(?:y|ying|id))\s+down\s+" + W + r"{0,2}(?:debt|borrowings)",
                  r"\breduc\w*\s+(?:our\s+)?(?:net\s+)?(?:debt|leverage)\b",
                  r"\brepa(?:y|id|ying)\s+" + W + r"{0,3}(?:notes|debt|term loan|borrowings)"),
    "GOVERNANCE": rx(r"\bcapital allocation (?:committee|review|framework|priorities)",
                     r"\bboard (?:refresh\w*|changes|composition)", r"\bnew (?:independent )?directors?",
                     r"\b(?:added|appointed|welcom\w*)\s+" + W + r"{0,4}(?:to (?:our|the) board|directors?)",
                     r"\b(?:engag\w+|conversations?|dialogue|discussions?) with (?:our\s+)?(?:\w+\s+)?(?:shareholders|stockholders|investors)",
                     r"\bshareholder feedback", r"\bcooperation agreement"),
    "COST": rx(r"\brestructur\w*", r"\bcost[- ](?:reduction|savings|out|takeout)", r"\brightsiz\w*",
               r"\bstreamlin\w*", r"\bheadcount reduction", r"\bsimplif\w*\s+(?:our |the )?(?:business|portfolio|structure)"),
    "VALUE_GAP": rx(r"\bundervalu\w*",
                    r"\bdiscount to\s+" + W + r"{0,2}(?:nav|net asset value|book|intrinsic|tangible book|private market|fair value)",
                    r"\b(?:trad\w+|stock|shares)\s+" + W + r"{0,3}below\s+" + W + r"{0,2}(?:book|nav|net asset value|intrinsic|liquidation|cash)",
                    r"\bsum[- ]of[- ](?:the[- ])?parts",
                    r"\b(?:best|most attractive|compelling|highest[- ]return\w*)\s+(?:use of|investment|opportunit\w+|return)\s+" + W +
                    r"{0,5}(?:our own|our stock|our shares|buying back|repurchas)",
                    r"\b(?:stock|shares?) (?:is|are) (?:cheap|attractive(?:ly priced)?|mispriced|undervalued)"),
    "ANTICIPATION": rx(r"\bstay tuned", r"\bmore to (?:say|share|come)\b",
                       r"\b(?:in|over) the (?:coming|next (?:few|couple of)) (?:weeks|months)",
                       r"\b(?:announce|update|share)\s+" + W + r"{0,4}(?:shortly|soon|in due course)",
                       r"\bupcoming investor day", r"\b(?:host|hold)\w*\s+(?:an?\s+|our\s+)?investor day", r"\b(?:process|discussions?) (?:is |are )?(?:ongoing|underway|progressing|well advanced|advanced)",
                       r"\b(?:advanced|late[- ]stage) (?:discussions|negotiations)"),
}
# weak value-gap cues count only when the clause is about the MARKET's price
GAP_WEAK = rx(r"\bdisconnect\b", r"\bmispric\w*", r"\bintrinsic value",
              r"\b(?:does not|doesn't|do not|don't|fails? to|not)\s+(?:fully |adequately |yet )?reflect\w*")
MARKET_REF = rx(r"\b(?:stock|share) price", r"\bour (?:stock|shares|equity)\b", r"\bvaluation\b",
                r"\bmarket (?:value|cap\w*|price)", r"\b(?:stock|shares) (?:is|are|has|have) (?:been )?trad",
                r"\bpublic market", r"\bthe market\b")
# "repurchased $30m of notes" is deleveraging, not a share buyback
DEBT_OBJ = rx(r"\b(?:repurchas\w*|buy(?:ing)?\s?-?backs?|bought back)\s+(?:\S+\s+){0,6}(?:debt|notes|bonds|debentures|convertibles?|loans?|term loan)\b")
ACTION = ("BUYBACK", "DIVIDEND_RETURN", "TENDER", "STRATEGIC_REVIEW", "MONETIZE",
          "DELEVER", "GOVERNANCE", "COST")
STANCE = ("VALUE_GAP", "ANTICIPATION")
ACT_W = {"TENDER": 1.3, "STRATEGIC_REVIEW": 1.3, "BUYBACK": 1.0, "DIVIDEND_RETURN": 0.9,
         "MONETIZE": 1.0, "GOVERNANCE": 0.6, "DELEVER": 0.4, "COST": 0.25}
SHAREHOLDER_ACT = ("BUYBACK", "DIVIDEND_RETURN", "TENDER", "STRATEGIC_REVIEW", "MONETIZE")

# commissive ladder (checked strongest first)
REALISED = rx(r"\b(?:ha(?:s|ve)|had|we've)\s+(?:\w+\s+){0,2}(?:authoriz|approv|announc|complet|execut|launch|initiat|repurchas|return|sign|clos|enter|declar|retir|sold|divest|agreed|engag|retain|form|bought)\w*",
              r"\b(?:authorized|approved|announced|completed|executed|launched|initiated|repurchased|bought back|returned|signed|closed|declared|retired|sold|divested|agreed|engaged|retained|formed)\b")
COMMITTED = rx(r"\b(?:will|we'll|shall|going to|gonna)\b", r"\bcommitted to\b", r"\bintend(?:s|ed)? to\b",
               r"\bplan(?:s|ning)? to\b", r"\b(?:decided|determined) to\b", r"\bon track to\b",
               r"\bexpect(?:s)? to (?:complete|close|execute|launch|finalize|announce|begin|start)")
INTENDED = rx(r"\bexpect\w*", r"\banticipat\w*", r"\baim\w*\b", r"\btarget\w*", r"\bprioriti[sz]\w*",
              r"\bfocused on\b", r"\bcontinu\w* to\b", r"\bremain committed", r"\blook forward to")
DELIB = rx(r"\bevaluat\w*", r"\bexplor\w*", r"\bconsider\w*", r"\breview\w*", r"\bassess\w*",
           r"\blook(?:ing)? at\b", r"\bweigh\w*", r"\banaly[sz]\w*", r"\bopen to\b", r"\bthink\w* about")
HEDGE = rx(r"\b(?:may|might|could|would|possibly|potentially|perhaps|if|whether|depending|subject to)\b",
           r"\bover time\b", r"\bat some point", r"\bopportunistic\w*")
AGENT = rx(r"\b(?:we|we're|we've|we'll|us|i|i'm|i've|management|the company)\b", r"\bour (?:board|company|team)\b",
           r"\bthe board\b", r"\bboard of directors\b")
NEG = rx(r"\b(?:no|not|never|nothing|neither|nor|without|no longer)\b", r"n't\b",
         r"\bno (?:plans?|intention|interest|desire)\b")
NOT_ONLY = rx(r"\bnot only\b")
EVADE = rx(r"\bnot going to (?:comment|speculate|get into|get ahead)", r"\b(?:don't|do not|won't|can't|cannot) (?:comment|speculate|get into|get ahead)",
           r"\btoo early\b", r"\bpremature\b", r"\bnothing to (?:announce|report|share)",
           r"\bwe'll see\b", r"\bno updates?\b", r"\bnot in a position\b")
MONEY = rx(r"\$\s?\d", r"\b\d[\d,.]*\s?(?:million|billion|mm|bn|%|percent)\b", r"\b\d[\d,.]*\s+shares\b")
TIME = rx(r"\b(?:this|next|the coming) (?:quarter|year|fiscal year|month)", r"\bby (?:the )?(?:end of|year[- ]end|fiscal|q[1-4]|mid)",
          r"\bwithin (?:the next )?\d+ (?:months|days|weeks)", r"\b(?:first|second|third|fourth) (?:quarter|half)",
          r"\b20[2-3]\d\b", r"\bnext \d+ months", r"\b(?:q[1-4]|h[12])\b")
SAFE = rx(r"forward[- ]looking statements", r"actual results", r"risk factors", r"non-gaap",
          r"safe harbor", r"undue reliance", r"annual report on form")
# grammatical aspect: a NEW / escalated programme vs business-as-usual
INCEPTIVE = rx(r"\b(?:new|additional|increased|upsiz\w*|expand\w*|accelerat\w*|larger|doubl\w*|incremental|initiat\w*|launch\w*|commenc\w*|first[- ]ever|begin|began|begun|resum\w*|reinstat\w*|enhanced)\b")
CONTINUATIVE = rx(r"\bcontinu\w*", r"\bongoing\b", r"\bas usual\b", r"\bconsistent with (?:our )?(?:past|prior|historical)",
                  r"\bremain\w*\b", r"\bmaintain\w*", r"\bexisting (?:program|authorization)", r"\bregular\b", r"\broutine\b")
SPLIT = re.compile(r";|\s(?:but|however|while|whereas|although|though)\s|\s-\s", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
TURN = re.compile(r"^([^:\n]{2,70}?)\s?:\s(.*)$", re.S)


# ---------------------------------------------------------------- discourse
def parse_turns(content: str):
    """[(speaker, role, section, text)] -- role in operator/analyst/management."""
    raw = []
    for para in re.split(r"\n+", content or ""):
        m = TURN.match(para.strip())
        if m:
            raw.append([m.group(1).strip(), m.group(2).strip()])
        elif raw and para.strip():
            raw[-1][1] += " " + para.strip()
    introduced = set()
    for sp, tx in raw:
        if sp.lower() == "operator":
            for m in re.finditer(r"(?:comes from|question is from|line of|from the line of|go ahead,?)\s+([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3})", tx):
                introduced.add(m.group(1).split()[-1].lower())
    out, section = [], "PREPARED"
    q_speakers: dict[str, list] = {}
    for sp, tx in raw:
        low = sp.lower()
        if low == "operator":
            if re.search(r"question|q&a|instructions", tx, re.I) and any(r[1] == "management" for r in out):
                section = "QA"
            out.append((sp, "operator", section, tx)); continue
        last = sp.split()[-1].lower() if sp.split() else low
        if "analyst" in low or (section == "QA" and last in introduced):
            role = "analyst"
        else:
            role = "management"
        out.append((sp, role, section, tx))
        if section == "QA":
            q_speakers.setdefault(sp, []).append(tx)
    # Q&A speakers never introduced but who mostly ask questions -> analysts
    prepared_mgmt = {sp for sp, r, s, _ in out if r == "management" and s == "PREPARED"}
    asks = {sp for sp, txs in q_speakers.items()
            if sp not in prepared_mgmt and "executive" not in sp.lower()
            and sum("?" in t for t in txs) >= max(1, 0.6 * len(txs))}
    return [(sp, "analyst" if sp in asks else r, s, t) for sp, r, s, t in out]


def sentences(text):
    return [s.strip() for s in SENT.split(text) if len(s.strip()) > 12]


# ---------------------------------------------------------------- clause scoring
def score_clause(cl: str):
    """{family: (score, strength, neg, spec)} for one clause."""
    res = {}
    debt = bool(DEBT_OBJ.search(cl))
    for fam, pat in FAMILIES.items():
        m = pat.search(cl)
        if fam == "VALUE_GAP" and not m and GAP_WEAK.search(cl) and MARKET_REF.search(cl):
            m = GAP_WEAK.search(cl)
        if fam == "DELEVER" and not m and debt:
            m = DEBT_OBJ.search(cl)
        if not m or (fam == "BUYBACK" and debt):
            continue
        pre = cl[: m.start()]
        spec = min(1.0, 0.5 * bool(MONEY.search(cl)) + 0.5 * bool(TIME.search(cl)))
        if fam in STANCE:
            neg = False                         # stance patterns carry their own negation
            strength = 0.9 if fam == "ANTICIPATION" else 0.8
            if HEDGE.search(cl) and fam == "VALUE_GAP":
                strength *= 0.7
            agency = 1.0
        else:
            # negation inside a conditional/elliptical lead-in ("if we don't, we'll ...") is not scope
            window = re.sub(r"\b(?:if|unless|whether)\b[^,]*,|\b(?:if|or|whether) not\b|\bnot,", " ", pre[-80:], flags=re.I)
            neg = bool(NEG.search(window)) and not NOT_ONLY.search(pre)
            if REALISED.search(cl):
                strength = 1.0
            elif COMMITTED.search(cl):
                strength = 0.9
            elif INTENDED.search(cl):
                strength = 0.6
            elif DELIB.search(cl):
                strength = 0.35
            else:
                strength = 0.45
            if strength < 1.0 and HEDGE.search(cl):
                strength *= 0.55
            agency = 1.0 if AGENT.search(cl) else 0.6
            if INCEPTIVE.search(cl):
                strength *= 1.3
            elif CONTINUATIVE.search(cl):
                strength *= 0.7
        s = strength * agency * (1 + 0.5 * spec)
        res[fam] = (-0.6 * s if neg else s, strength, neg, spec)
    return res


def analyze(content: str):
    turns = parse_turns(content)
    fam_clauses = {f: [] for f in FAMILIES}
    neg_total = 0
    q_total = q_press = a_commit = a_evade = 0
    mgmt_words = 0
    pressed = False
    for sp, role, sec, tx in turns:
        if role == "analyst" and sec == "QA":
            q_total += 1
            pressed = any(FAMILIES[f].search(tx) for f in SHAREHOLDER_ACT + ("VALUE_GAP",))
            q_press += pressed
            continue
        if role != "management":
            continue
        mgmt_words += len(tx.split())
        best_answer = 0.0
        for s in sentences(tx):
            if s.endswith("?") or SAFE.search(s):
                continue
            for cl in SPLIT.split(s):
                if len(cl) < 10:
                    continue
                for fam, (sc, st, ng, spc) in score_clause(cl).items():
                    fam_clauses[fam].append((sc, s[:240], sp, sec))
                    neg_total += ng
                    if fam in SHAREHOLDER_ACT and not ng:
                        best_answer = max(best_answer, st)
        if sec == "QA" and pressed:
            if best_answer >= 0.6:
                a_commit += 1
            elif EVADE.search(tx):
                a_evade += 1
            pressed = False
    feats, evidence = {}, {}
    for fam, lst in fam_clauses.items():
        pos = sorted((c for c in lst if c[0] > 0), key=lambda c: -c[0])
        top = [c[0] for c in pos[:3]]
        feats[fam] = round(sum(w * v for w, v in zip((1.0, 0.5, 0.25), top)), 3)
        feats[fam + "_n"] = len(pos)
        feats[fam + "_neg"] = sum(1 for c in lst if c[0] < 0)
        if pos:
            evidence[fam] = [{"q": c[1], "who": c[2], "sec": c[3], "s": round(c[0], 2)} for c in pos[:2]]
        negs = [c for c in lst if c[0] < 0]
        if negs:
            evidence[fam + "_NEG"] = [{"q": negs[0][1], "who": negs[0][2], "sec": negs[0][3]}]
    feats.update({"neg_total": neg_total, "q_total": q_total, "q_press": q_press,
                  "press_ratio": round(q_press / q_total, 3) if q_total else 0.0,
                  "a_commit": a_commit, "a_evade": a_evade, "mgmt_words": mgmt_words})
    return feats, evidence


def rule_score(f, novelty):
    action = sum(ACT_W[k] * min(f[k], 2.0) for k in ACTION)
    gap = min(f["VALUE_GAP"], 2.0)
    concrete = sum(f[k] for k in SHAREHOLDER_ACT) > 0.8
    return round(action + 0.7 * gap + 0.5 * gap * concrete + 0.8 * min(f["ANTICIPATION"], 2.0)
                 + 0.6 * novelty + 0.4 * f["a_commit"] - 0.4 * f["a_evade"]
                 - 0.3 * min(f["neg_total"], 5), 3)


def novelty_of(cur, prior):
    """Weighted rise of each action family vs its max over the prior 3 calls,
    plus the list of families that are NEW (strong now, absent before)."""
    nov, new = 0.0, []
    for k in ACTION + ("VALUE_GAP",):
        before = max([p[k] for p in prior[-3:]], default=0.0)
        rise = max(0.0, cur[k] - before)
        nov += ACT_W.get(k, 0.7) * min(rise, 2.0)
        if prior and cur[k] >= 0.8 and before < 0.3:
            new.append(k)
    return round(nov, 3), new


def main() -> int:
    calls = {}
    for f in sorted(STORE.glob("*/*.json.gz")):
        try:
            rec = json.load(gzip.open(f, "rt", encoding="utf-8"))
        except Exception:
            continue
        if rec.get("content") and rec.get("date"):
            calls.setdefault(f.parent.name, []).append(rec)
    FEAT.parent.mkdir(exist_ok=True)
    latest = {}
    n = 0
    with open(FEAT, "w") as fh:
        for sym, lst in calls.items():
            lst.sort(key=lambda r: r["date"])
            hist = []
            for rec in lst:
                feats, ev = analyze(rec["content"])
                nov, new = novelty_of(feats, hist)
                row = {"ticker": sym, "date": rec["date"][:10], "period": f"{rec.get('year')}{rec.get('period')}",
                       **feats, "novelty": nov, "new_families": new,
                       "rule_score": rule_score(feats, nov)}
                fh.write(json.dumps(row) + "\n")
                hist.append(feats)
                latest[sym] = (row, ev)
                n += 1
    out = {}
    for sym, (row, ev) in latest.items():
        out[sym] = {**{k: row[k] for k in ("ticker", "date", "period", "rule_score", "novelty",
                                            "new_families", "press_ratio", "a_commit", "a_evade")},
                    "families": {k: row[k] for k in ACTION + STANCE if row[k] > 0},
                    "negated": {k: row[k + "_neg"] for k in ACTION if row[k + "_neg"]},
                    "evidence": ev}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"analysed {n} calls for {len(calls)} names -> {FEAT.name}, {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
